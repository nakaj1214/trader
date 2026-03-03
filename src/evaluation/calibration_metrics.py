"""Calibration metrics: Brier score, ECE, reliability analysis.

Provides build_calibration_metrics() for accuracy.json export.
Re-uses calibrator.compute_calibration_stats() for the core math.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.prediction.calibrator import compute_calibration_stats
from src.prediction.prophet_model import compute_prob_up

logger = structlog.get_logger(__name__)


def build_calibration_metrics(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build calibration metrics from confirmed prediction records.

    Computes overall and recent-N-weeks calibration stats.
    Supports both new (English) and legacy (Japanese) field names.

    Args:
        records: All prediction records (DB or Sheets format).

    Returns:
        Dict with 'overall' and 'recent_n_weeks' calibration data.
    """
    samples: list[dict[str, Any]] = []

    for r in records:
        status = r.get("status", r.get("ステータス", ""))
        if status not in ("confirmed", "確定済み"):
            continue

        try:
            actual = float(r.get("actual_price", r.get("翌週実績価格", "")))
            current = float(r.get("current_price", r.get("現在価格", "")))
        except (ValueError, TypeError):
            continue
        if actual <= 0 or current <= 0:
            continue

        predicted_pct = _to_float(r.get("predicted_change_pct", r.get("予測上昇率(%)", 0)))
        ci = _to_float(r.get("confidence_interval_pct", r.get("信頼区間(%)", 0)))
        outcome = 1 if actual > current else 0
        prob = compute_prob_up(predicted_pct, ci)

        date = r.get("date", r.get("日付", ""))
        samples.append({"prob_up": prob, "outcome": outcome, "date": date})

    overall = compute_calibration_stats(samples)

    recent_n = 12
    all_dates = sorted({s["date"] for s in samples})
    if len(all_dates) > recent_n:
        cutoff = set(all_dates[-recent_n:])
        recent_samples = [s for s in samples if s["date"] in cutoff]
    else:
        recent_samples = samples

    recent_stats = compute_calibration_stats(recent_samples)
    recent_stats["n_weeks"] = min(recent_n, len(all_dates))

    return {"overall": overall, "recent_n_weeks": recent_stats}


def _to_float(value: Any) -> float:
    """Convert to float, returning 0.0 on failure."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
