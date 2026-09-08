"""Benchmark comparison utilities for candidate forward returns."""

from __future__ import annotations

from collections.abc import Iterable
from statistics import mean, median
from typing import Any

import pandas as pd


def benchmark_returns_for_dates(
    dates: Iterable[str],
    history: pd.DataFrame,
    horizons: tuple[int, ...] = (5, 20, 60),
) -> dict[str, dict[int, float | None]]:
    """Compute benchmark close-to-close forward returns after each signal date."""
    if history.empty or "Close" not in history.columns:
        return {date: {h: None for h in horizons} for date in dates}
    close = history["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = pd.to_numeric(close, errors="coerce").dropna()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    close = close.sort_index()

    results: dict[str, dict[int, float | None]] = {}
    for date in dates:
        signal_date = pd.Timestamp(date)
        before = close[close.index <= signal_date]
        after = close[close.index > signal_date]
        if before.empty:
            results[date] = {h: None for h in horizons}
            continue
        base = float(before.iloc[-1])
        row: dict[int, float | None] = {}
        for horizon in horizons:
            row[horizon] = (
                (float(after.iloc[horizon - 1]) / base - 1.0) * 100.0
                if len(after) >= horizon and base > 0
                else None
            )
        results[date] = row
    return results


def add_benchmark_excess_returns(
    rows: Iterable[dict[str, Any]],
    benchmark: dict[str, dict[int, float | None]],
    horizons: tuple[int, ...] = (5, 20, 60),
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        date = str(row.get("date") or "")
        for horizon in horizons:
            bret = benchmark.get(date, {}).get(horizon)
            cret = row.get(f"h{horizon}_return_pct")
            row[f"h{horizon}_benchmark_return_pct"] = round(bret, 6) if bret is not None else None
            if isinstance(cret, (int, float)) and bret is not None:
                row[f"h{horizon}_excess_return_pct"] = round(float(cret) - bret, 6)
            else:
                row[f"h{horizon}_excess_return_pct"] = None
        enriched.append(row)
    return enriched


def summarize_excess_returns(
    rows: Iterable[dict[str, Any]],
    horizons: tuple[int, ...] = (5, 20, 60),
) -> dict[str, Any]:
    rows = list(rows)
    result: dict[str, Any] = {}
    for horizon in horizons:
        values = [
            float(row[f"h{horizon}_excess_return_pct"])
            for row in rows
            if isinstance(row.get(f"h{horizon}_excess_return_pct"), (int, float))
        ]
        result[f"h{horizon}"] = {
            "evaluated": len(values),
            "mean_excess_return_pct": round(mean(values), 6) if values else None,
            "median_excess_return_pct": round(median(values), 6) if values else None,
            "beat_benchmark_rate_pct": (
                round(sum(value > 0 for value in values) / len(values) * 100.0, 3)
                if values
                else None
            ),
        }
    return result
