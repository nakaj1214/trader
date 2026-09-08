"""Load encrypted JP inflection snapshots and support benchmark-aware forward validation."""
from __future__ import annotations

from pathlib import Path
from statistics import mean, median
from typing import Any

import pandas as pd

from src.data.snapshot_crypto import decrypt_json
from src.evaluation.inflection_backtest import TradeResult, simulate_signal

BENCHMARK_TICKER = "1306.T"  # NEXT FUNDS TOPIX ETF


class SnapshotLoadError(RuntimeError):
    """Raised when an encrypted inflection snapshot cannot be trusted."""


def load_inflection_signals(
    snapshot_dir: Path,
    *,
    encryption_secret: str,
    classifications: tuple[str, ...] = ("EARLY_CANDIDATE",),
) -> list[dict[str, Any]]:
    """Return one immutable signal row per market-data date/ticker.

    Only encrypted ``YYYY-MM-DD.enc`` snapshots are accepted. Any encrypted
    snapshot that cannot be decrypted or does not satisfy the expected schema
    aborts validation instead of being silently skipped.
    """
    signals: dict[tuple[str, str], dict[str, Any]] = {}
    if not snapshot_dir.exists():
        return []

    for path in sorted(snapshot_dir.glob("????-??-??.enc")):
        try:
            payload = decrypt_json(path.read_text(encoding="utf-8"), encryption_secret)
        except (OSError, TypeError, ValueError) as exc:
            raise SnapshotLoadError(f"Could not decrypt or decode snapshot: {path.name}") from exc
        if payload.get("mode") != "shadow":
            raise SnapshotLoadError(f"Invalid snapshot mode: {path.name}")

        strategy_version = str(payload.get("strategy_version") or "")
        source_commit = str(payload.get("source_commit_sha") or "")
        schema_version = payload.get("report_schema_version")
        market_date = str(payload.get("latest_price_date") or "")
        storage = payload.get("storage")
        if (
            not strategy_version
            or not source_commit
            or schema_version is None
            or market_date != path.stem
            or not isinstance(storage, dict)
            or storage.get("encrypted") is not True
            or storage.get("snapshot_date_basis") != "latest_price_date"
        ):
            raise SnapshotLoadError(f"Invalid snapshot metadata/schema: {path.name}")

        candidates = payload.get("candidates")
        if not isinstance(candidates, list):
            raise SnapshotLoadError(f"Invalid candidates payload: {path.name}")
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise SnapshotLoadError(f"Invalid candidate row: {path.name}")
            classification = str(candidate.get("classification") or "")
            ticker = str(candidate.get("ticker") or "")
            if not ticker:
                raise SnapshotLoadError(f"Candidate ticker missing: {path.name}")
            if classification not in classifications:
                continue
            key = (market_date, ticker)
            if key in signals:
                continue
            try:
                score = float(candidate.get("score") or 0.0)
            except (TypeError, ValueError) as exc:
                raise SnapshotLoadError(f"Invalid candidate score: {path.name}:{ticker}") from exc
            signals[key] = {
                "ticker": ticker,
                "signal_date": market_date,
                "date": market_date,
                "score": score,
                "classification": classification,
                "strategy_version": strategy_version,
                "report_schema_version": schema_version,
                "source_commit_sha": source_commit,
                "jquants_plan": (payload.get("data_policy") or {}).get("jquants_plan"),
                "jquants_data_delay_weeks": (payload.get("data_policy") or {}).get(
                    "jquants_data_delay_weeks"
                ),
                "runtime_versions": payload.get("runtime_versions"),
            }

    return sorted(signals.values(), key=lambda row: (row["signal_date"], row["ticker"]))


def benchmark_returns_by_signal_date(
    signal_dates: list[str],
    benchmark_history: pd.DataFrame,
    *,
    holding_days: int,
    round_trip_cost_pct: float,
) -> dict[str, float | None]:
    """Simulate an investable TOPIX ETF alternative using identical entry/exit rules."""
    result: dict[str, float | None] = {}
    for signal_date in sorted(set(signal_dates)):
        trade = simulate_signal(
            {"ticker": BENCHMARK_TICKER, "signal_date": signal_date, "score": 0.0},
            benchmark_history,
            holding_days=holding_days,
            round_trip_cost_pct=round_trip_cost_pct,
            apply_tax=False,
        )
        result[signal_date] = trade.net_return_pct
    return result


def enrich_trades_with_benchmark(
    trades: list[TradeResult],
    benchmark_returns: dict[str, float | None],
) -> list[dict[str, Any]]:
    """Attach TOPIX ETF return, excess return and beat flag to each trade."""
    rows: list[dict[str, Any]] = []
    for trade in trades:
        row = trade.as_dict()
        benchmark_return = benchmark_returns.get(trade.signal_date)
        row["benchmark_ticker"] = BENCHMARK_TICKER
        row["benchmark_net_return_pct"] = benchmark_return
        if trade.net_return_pct is not None and benchmark_return is not None:
            excess = float(trade.net_return_pct) - float(benchmark_return)
            row["excess_return_pct"] = round(excess, 6)
            row["beat_benchmark"] = excess > 0
        else:
            row["excess_return_pct"] = None
            row["beat_benchmark"] = None
        rows.append(row)
    return rows


def summarize_benchmark_excess(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize completed strategy-vs-TOPIX excess returns."""
    values = [
        float(row["excess_return_pct"])
        for row in rows
        if isinstance(row.get("excess_return_pct"), (int, float))
    ]
    if not values:
        return {
            "evaluated": 0,
            "mean_excess_return_pct": None,
            "median_excess_return_pct": None,
            "beat_benchmark_rate_pct": None,
        }
    return {
        "evaluated": len(values),
        "mean_excess_return_pct": round(mean(values), 6),
        "median_excess_return_pct": round(median(values), 6),
        "beat_benchmark_rate_pct": round(sum(value > 0 for value in values) / len(values) * 100.0, 3),
    }
