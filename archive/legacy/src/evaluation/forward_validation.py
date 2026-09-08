"""Forward validation of immutable historical prediction snapshots."""
from __future__ import annotations

import json
import math
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class GitSnapshot:
    sha: str
    committed_at: str
    payload: dict[str, Any]


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def iter_prediction_snapshots(
    repo_root: Path,
    source_path: str = "dashboard/data/predictions_jp.json",
    since: str | None = None,
    until: str | None = None,
) -> list[GitSnapshot]:
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
            payload = json.loads(_git(repo_root, "show", f"{sha}:{source_path}"))
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("predictions"), list):
            snapshots.append(GitSnapshot(sha, committed_at, payload))
    return snapshots


def reconstruct_predictions(snapshots: Iterable[GitSnapshot]) -> list[dict[str, Any]]:
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
            if key not in reconstructed:
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


def _infer_corporate_action_scale(
    stored_price: float | None,
    historical_price: float | None,
    tolerance_pct: float = 1.0,
) -> float:
    """Infer common split ratios when a provider retrospectively adjusts history."""
    if not stored_price or not historical_price:
        return 1.0
    ratio = stored_price / historical_price
    common = (0.1, 0.2, 0.25, 0.5, 2.0, 4.0, 5.0, 10.0)
    for candidate in common:
        if abs(ratio / candidate - 1.0) * 100.0 <= tolerance_pct:
            return candidate
    return 1.0


def _max_drawdown_pct(entry_price: float, closes: pd.Series) -> float | None:
    """Return true peak-to-trough drawdown, including entry as the initial peak."""
    if entry_price <= 0 or closes.empty:
        return None
    values = pd.concat(
        [pd.Series([entry_price], index=[closes.index[0] - pd.Timedelta(microseconds=1)]), closes]
    ).astype(float)
    running_peak = values.cummax()
    drawdowns = (values / running_peak - 1.0) * 100.0
    return float(drawdowns.min())


def evaluate_prediction(
    prediction: dict[str, Any],
    history: pd.DataFrame,
    horizons: tuple[int, ...] = (5, 20, 60),
    reference_tolerance_pct: float = 1.0,
    forecast_horizon: int = 5,
) -> dict[str, Any]:
    result = dict(prediction)
    pred_date = pd.Timestamp(str(prediction["date"]))
    current_price = _safe_float(prediction.get("current_price"))
    predicted_price = _safe_float(prediction.get("predicted_price"))
    close_raw = _close_series(history)

    raw_before = close_raw[close_raw.index <= pred_date]
    raw_reference = float(raw_before.iloc[-1]) if not raw_before.empty else None
    scale = _infer_corporate_action_scale(current_price, raw_reference)
    close = close_raw * scale
    before_or_on = close[close.index <= pred_date]
    after = close[close.index > pred_date]
    reference_close = float(before_or_on.iloc[-1]) if not before_or_on.empty else None

    result["corporate_action_scale"] = scale
    result["raw_reference_close"] = raw_reference
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
        for suffix in (
            "close",
            "return_pct",
            "direction_hit",
            "forecast_abs_error_pct",
            "max_return_pct",
            "min_return_pct",
            "max_drawdown_pct",
        ):
            result[f"{prefix}_{suffix}"] = None
        if len(after) < horizon:
            continue
        window = after.iloc[:horizon]
        actual_close = float(window.iloc[horizon - 1])
        result[f"{prefix}_close"] = actual_close
        if current_price:
            result[f"{prefix}_return_pct"] = round((actual_close / current_price - 1.0) * 100.0, 6)
            result[f"{prefix}_max_return_pct"] = round(
                (float(window.max()) / current_price - 1.0) * 100.0, 6
            )
            result[f"{prefix}_min_return_pct"] = round(
                (float(window.min()) / current_price - 1.0) * 100.0, 6
            )
            max_drawdown = _max_drawdown_pct(current_price, window)
            result[f"{prefix}_max_drawdown_pct"] = (
                round(max_drawdown, 6) if max_drawdown is not None else None
            )
        if horizon == forecast_horizon and current_price and predicted_price is not None:
            result[f"{prefix}_direction_hit"] = (predicted_price > current_price) == (
                actual_close > current_price
            )
            result[f"{prefix}_forecast_abs_error_pct"] = round(
                abs(predicted_price - actual_close) / actual_close * 100.0, 6
            )
    return result


def fetch_histories_yfinance(
    predictions: Iterable[dict[str, Any]], max_horizon: int = 60
) -> dict[str, pd.DataFrame]:
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
            histories[ticker] = yf.Ticker(ticker).history(
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                auto_adjust=False,
                actions=False,
            )
        except Exception:  # noqa: BLE001 - provider failures are isolated per ticker
            histories[ticker] = pd.DataFrame()
    return histories


def evaluate_predictions(
    predictions: Iterable[dict[str, Any]],
    histories: dict[str, pd.DataFrame],
    horizons: tuple[int, ...] = (5, 20, 60),
    reference_tolerance_pct: float = 1.0,
    forecast_horizon: int = 5,
) -> list[dict[str, Any]]:
    return [
        evaluate_prediction(
            row,
            histories.get(str(row["ticker"]), pd.DataFrame()),
            horizons,
            reference_tolerance_pct,
            forecast_horizon,
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
    return len(values), sum(bool(v) for v in values) / len(values) * 100.0


def summarize_evaluations(
    rows: list[dict[str, Any]], horizons: tuple[int, ...] = (5, 20, 60)
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "prediction_count": len(rows),
        "prediction_dates": len({r.get("date") for r in rows}),
        "tickers": len({r.get("ticker") for r in rows}),
    }
    n, rate = _bool_rate(rows, "reference_price_match")
    diffs = [abs(v) for v in _metric_values(rows, "reference_price_diff_pct")]
    scaled = [
        r
        for r in rows
        if _safe_float(r.get("corporate_action_scale")) not in (None, 1.0)
    ]
    summary["data_quality"] = {
        "reference_price_checked": n,
        "reference_price_match_rate_pct": round(rate, 3) if rate is not None else None,
        "reference_price_median_abs_diff_pct": round(median(diffs), 6) if diffs else None,
        "reference_price_max_abs_diff_pct": round(max(diffs), 6) if diffs else None,
        "corporate_action_normalized_count": len(scaled),
    }
    performance: dict[str, Any] = {}
    for horizon in horizons:
        p = f"h{horizon}"
        returns = _metric_values(rows, f"{p}_return_pct")
        errors = _metric_values(rows, f"{p}_forecast_abs_error_pct")
        maxima = _metric_values(rows, f"{p}_max_return_pct")
        drawdowns = _metric_values(rows, f"{p}_max_drawdown_pct")
        ndir, drate = _bool_rate(rows, f"{p}_direction_hit")
        performance[p] = {
            "evaluated": len(returns),
            "direction_checked": ndir,
            "direction_hit_rate_pct": round(drate, 3) if drate is not None else None,
            "mean_return_pct": round(mean(returns), 6) if returns else None,
            "median_return_pct": round(median(returns), 6) if returns else None,
            "win_rate_pct": (
                round(sum(v > 0 for v in returns) / len(returns) * 100.0, 3)
                if returns
                else None
            ),
            "median_forecast_abs_error_pct": round(median(errors), 6) if errors else None,
            "mean_max_return_pct": round(mean(maxima), 6) if maxima else None,
            "median_max_drawdown_pct": round(median(drawdowns), 6) if drawdowns else None,
            "explosive_50pct_count": sum(v >= 50.0 for v in maxima),
        }
    summary["performance"] = performance
    monthly: dict[str, dict[str, Any]] = {}
    for month in sorted({str(r.get("date", ""))[:7] for r in rows if r.get("date")}):
        mrows = [r for r in rows if str(r.get("date", "")).startswith(month)]
        ndir, drate = _bool_rate(mrows, "h5_direction_hit")
        returns = _metric_values(mrows, "h5_return_pct")
        monthly[month] = {
            "predictions": len(mrows),
            "evaluated": len(returns),
            "direction_checked": ndir,
            "direction_hit_rate_pct": round(drate, 3) if drate is not None else None,
            "mean_return_pct": round(mean(returns), 6) if returns else None,
            "median_return_pct": round(median(returns), 6) if returns else None,
        }
    summary["by_month"] = monthly
    return summary