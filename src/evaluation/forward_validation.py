"""Forward validation of historical prediction snapshots.

This module reconstructs predictions exactly as they were committed to Git and
compares them with prices observed later.  It is intentionally independent from
the current prediction code so changes to the model cannot rewrite history.
"""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

import pandas as pd


@dataclass(frozen=True)
class GitSnapshot:
    sha: str
    committed_at: str
    payload: dict[str, Any]


def _git(repo_root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


def iter_prediction_snapshots(
    repo_root: Path,
    source_path: str = "dashboard/data/predictions_jp.json",
    since: str | None = None,
    until: str | None = None,
) -> list[GitSnapshot]:
    """Read every committed version of a prediction JSON file, oldest first."""
    args = ["log", "--reverse", "--format=%H\t%cI"]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    args.extend(["--", source_path])

    snapshots: list[GitSnapshot] = []
    for line in _git(repo_root, *args).splitlines():
        if not line.strip():
            continue
        sha, committed_at = line.split("\t", 1)
        try:
            raw = _git(repo_root, "show", f"{sha}:{source_path}")
            payload = json.loads(raw)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("predictions"), list):
            snapshots.append(GitSnapshot(sha=sha, committed_at=committed_at, payload=payload))
    return snapshots


def reconstruct_predictions(snapshots: Iterable[GitSnapshot]) -> list[dict[str, Any]]:
    """Return the earliest committed copy of each (prediction date, ticker)."""
    reconstructed: dict[tuple[str, str], dict[str, Any]] = {}
    for snapshot in snapshots:
        for prediction in snapshot.payload.get("predictions", []):
            if not isinstance(prediction, dict):
                continue
            date = str(prediction.get("date") or "")
            ticker = str(prediction.get("ticker") or "")
            if not date or not ticker:
                continue
            key = (date, ticker)
            if key in reconstructed:
                continue
            row = dict(prediction)
            row["source_commit"] = snapshot.sha
            row["source_commit_at"] = snapshot.committed_at
            reconstructed[key] = row
    return sorted(reconstructed.values(), key=lambda row: (row["date"], row["ticker"]))


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _close_series(history: pd.DataFrame) -> pd.Series:
    if history.empty or "Close" not in history.columns:
        return pd.Series(dtype=float)
    close = history["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = pd.to_numeric(close, errors="coerce").dropna()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.sort_index()


def evaluate_prediction(
    prediction: dict[str, Any],
    history: pd.DataFrame,
    horizons: tuple[int, ...] = (5, 20, 60),
    reference_tolerance_pct: float = 1.0,
) -> dict[str, Any]:
    """Compare one immutable historical prediction with later market prices."""
    result = dict(prediction)
    pred_date = pd.Timestamp(str(prediction["date"]))
    current_price = _safe_float(prediction.get("current_price"))
    predicted_price = _safe_float(prediction.get("predicted_price"))
    close = _close_series(history)

    before_or_on = close[close.index <= pred_date]
    after = close[close.index > pred_date]

    reference_close = float(before_or_on.iloc[-1]) if not before_or_on.empty else None
    result["reference_close"] = reference_close
    if current_price and reference_close is not None:
        diff_pct = (reference_close / current_price - 1.0) * 100.0
        result["reference_price_diff_pct"] = round(diff_pct, 6)
        result["reference_price_match"] = abs(diff_pct) <= reference_tolerance_pct
    else:
        result["reference_price_diff_pct"] = None
        result["reference_price_match"] = None

    for horizon in horizons:
        prefix = f"h{horizon}"
        if len(after) < horizon:
            result[f"{prefix}_close"] = None
            result[f"{prefix}_return_pct"] = None
            result[f"{prefix}_direction_hit"] = None
            result[f"{prefix}_forecast_abs_error_pct"] = None
            result[f"{prefix}_max_return_pct"] = None
            result[f"{prefix}_max_drawdown_pct"] = None
            continue

        window = after.iloc[:horizon]
        actual_close = float(window.iloc[horizon - 1])
        result[f"{prefix}_close"] = actual_close

        if current_price:
            actual_return = (actual_close / current_price - 1.0) * 100.0
            result[f"{prefix}_return_pct"] = round(actual_return, 6)
            result[f"{prefix}_max_return_pct"] = round((float(window.max()) / current_price - 1.0) * 100.0, 6)
            result[f"{prefix}_max_drawdown_pct"] = round((float(window.min()) / current_price - 1.0) * 100.0, 6)
            if predicted_price is not None:
                predicted_direction = predicted_price > current_price
                actual_direction = actual_close > current_price
                result[f"{prefix}_direction_hit"] = predicted_direction == actual_direction
            else:
                result[f"{prefix}_direction_hit"] = None
        else:
            result[f"{prefix}_return_pct"] = None
            result[f"{prefix}_max_return_pct"] = None
            result[f"{prefix}_max_drawdown_pct"] = None
            result[f"{prefix}_direction_hit"] = None

        if predicted_price is not None and actual_close:
            result[f"{prefix}_forecast_abs_error_pct"] = round(
                abs(predicted_price - actual_close) / actual_close * 100.0,
                6,
            )
        else:
            result[f"{prefix}_forecast_abs_error_pct"] = None

    return result


def fetch_histories_yfinance(
    predictions: Iterable[dict[str, Any]],
    max_horizon: int = 60,
) -> dict[str, pd.DataFrame]:
    """Fetch each ticker once, covering all prediction dates and evaluation horizons."""
    import yfinance as yf

    rows = list(predictions)
    by_ticker: dict[str, list[pd.Timestamp]] = {}
    for row in rows:
        by_ticker.setdefault(str(row["ticker"]), []).append(pd.Timestamp(str(row["date"])))

    histories: dict[str, pd.DataFrame] = {}
    for ticker, dates in sorted(by_ticker.items()):
        start = min(dates) - timedelta(days=10)
        end = max(dates) + timedelta(days=max_horizon * 2 + 30)
        try:
            history = yf.Ticker(ticker).history(
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                auto_adjust=False,
                actions=False,
            )
        except Exception:
            history = pd.DataFrame()
        histories[ticker] = history
    return histories


def evaluate_predictions(
    predictions: Iterable[dict[str, Any]],
    histories: dict[str, pd.DataFrame],
    horizons: tuple[int, ...] = (5, 20, 60),
    reference_tolerance_pct: float = 1.0,
) -> list[dict[str, Any]]:
    return [
        evaluate_prediction(
            prediction=row,
            history=histories.get(str(row["ticker"]), pd.DataFrame()),
            horizons=horizons,
            reference_tolerance_pct=reference_tolerance_pct,
        )
        for row in predictions
    ]


def _metric_values(rows: Iterable[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = _safe_float(row.get(key))
        if value is not None:
            values.append(value)
    return values


def _bool_rate(rows: Iterable[dict[str, Any]], key: str) -> tuple[int, float | None]:
    values = [row.get(key) for row in rows if isinstance(row.get(key), bool)]
    if not values:
        return 0, None
    return len(values), sum(bool(value) for value in values) / len(values) * 100.0


def summarize_evaluations(
    rows: list[dict[str, Any]],
    horizons: tuple[int, ...] = (5, 20, 60),
) -> dict[str, Any]:
    """Build metrics that distinguish data correctness from strategy performance."""
    summary: dict[str, Any] = {
        "prediction_count": len(rows),
        "prediction_dates": len({row.get("date") for row in rows}),
        "tickers": len({row.get("ticker") for row in rows}),
    }

    reference_n, reference_rate = _bool_rate(rows, "reference_price_match")
    reference_diff = [abs(v) for v in _metric_values(rows, "reference_price_diff_pct")]
    summary["data_quality"] = {
        "reference_price_checked": reference_n,
        "reference_price_match_rate_pct": round(reference_rate, 3) if reference_rate is not None else None,
        "reference_price_median_abs_diff_pct": round(median(reference_diff), 6) if reference_diff else None,
        "reference_price_max_abs_diff_pct": round(max(reference_diff), 6) if reference_diff else None,
    }

    performance: dict[str, Any] = {}
    for horizon in horizons:
        prefix = f"h{horizon}"
        returns = _metric_values(rows, f"{prefix}_return_pct")
        forecast_errors = _metric_values(rows, f"{prefix}_forecast_abs_error_pct")
        max_returns = _metric_values(rows, f"{prefix}_max_return_pct")
        drawdowns = _metric_values(rows, f"{prefix}_max_drawdown_pct")
        n_direction, direction_rate = _bool_rate(rows, f"{prefix}_direction_hit")
        performance[prefix] = {
            "evaluated": len(returns),
            "direction_checked": n_direction,
            "direction_hit_rate_pct": round(direction_rate, 3) if direction_rate is not None else None,
            "mean_return_pct": round(mean(returns), 6) if returns else None,
            "median_return_pct": round(median(returns), 6) if returns else None,
            "win_rate_pct": round(sum(value > 0 for value in returns) / len(returns) * 100.0, 3) if returns else None,
            "median_forecast_abs_error_pct": round(median(forecast_errors), 6) if forecast_errors else None,
            "mean_max_return_pct": round(mean(max_returns), 6) if max_returns else None,
            "median_max_drawdown_pct": round(median(drawdowns), 6) if drawdowns else None,
            "explosive_50pct_count": sum(value >= 50.0 for value in max_returns),
        }
    summary["performance"] = performance

    by_month: dict[str, dict[str, Any]] = {}
    months = sorted({str(row.get("date", ""))[:7] for row in rows if row.get("date")})
    for month in months:
        month_rows = [row for row in rows if str(row.get("date", "")).startswith(month)]
        n, hit_rate = _bool_rate(month_rows, "h5_direction_hit")
        returns = _metric_values(month_rows, "h5_return_pct")
        by_month[month] = {
            "predictions": len(month_rows),
            "evaluated": len(returns),
            "direction_checked": n,
            "direction_hit_rate_pct": round(hit_rate, 3) if hit_rate is not None else None,
            "mean_return_pct": round(mean(returns), 6) if returns else None,
            "median_return_pct": round(median(returns), 6) if returns else None,
        }
    summary["by_month"] = by_month
    return summary
