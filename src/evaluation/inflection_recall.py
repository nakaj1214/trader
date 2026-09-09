"""Explosion recall metrics for the observed inflection-candidate pool."""

from __future__ import annotations

from statistics import median
from typing import Any

import pandas as pd

from src.evaluation.inflection_backtest import _series


def compute_tracked_pool_explosion_recall(
    observations: list[dict[str, Any]],
    histories: dict[str, pd.DataFrame],
    *,
    explosion_threshold_pct: float = 50.0,
    search_horizon_days: int = 252,
) -> dict[str, Any]:
    """Measure pre-explosion detection within tickers observed by the daily scan."""
    if explosion_threshold_pct <= 0:
        raise ValueError("explosion_threshold_pct must be positive")
    if search_horizon_days < 1:
        raise ValueError("search_horizon_days must be at least 1")

    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for observation in observations:
        by_ticker.setdefault(str(observation["ticker"]), []).append(observation)

    exploded = 0
    detected = 0
    excluded_no_price = 0
    lead_times: list[int] = []
    for ticker, timeline in by_ticker.items():
        timeline.sort(key=lambda row: str(row["signal_date"]))
        baseline_date = pd.Timestamp(str(timeline[0]["signal_date"]))
        closes = _series(histories.get(ticker, pd.DataFrame()), "Close")
        baseline_candidates = closes[closes.index <= baseline_date]
        if baseline_candidates.empty or float(baseline_candidates.iloc[-1]) <= 0:
            excluded_no_price += 1
            continue
        effective_baseline_date = baseline_candidates.index[-1]
        baseline_price = float(baseline_candidates.iloc[-1])
        future = closes[closes.index > effective_baseline_date].iloc[:search_horizon_days]
        threshold = baseline_price * (1.0 + explosion_threshold_pct / 100.0)
        hits = future[future >= threshold]
        if hits.empty:
            continue
        explosion_date = hits.index[0]
        exploded += 1
        detection_dates = [
            pd.Timestamp(str(row["signal_date"]))
            for row in timeline
            if str(row.get("classification")) in {"EARLY_CANDIDATE", "WATCH"}
            and pd.Timestamp(str(row["signal_date"])) < explosion_date
        ]
        if detection_dates:
            detected += 1
            lead_times.append((explosion_date - min(detection_dates)).days)

    return {
        "tracked_pool_explosion_recall_pct": (
            round(detected / exploded * 100.0, 3) if exploded else None
        ),
        "exploded_ticker_count": exploded,
        "detected_ticker_count": detected,
        "detection_lead_time_median_days": float(median(lead_times)) if lead_times else None,
        "excluded_no_price_count": excluded_no_price,
        "definition_note": (
            "全市場ではなく、日次スキャンでdeep_candidatesに一度でも入った銘柄プール内でのRecall"
        ),
    }
