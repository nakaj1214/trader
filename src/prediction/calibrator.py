"""Probability calibration: guardrail and Platt scaling.

Guardrail clips extreme predictions.
Platt scaling (future) recalibrates prob_up using logistic regression.
"""

from __future__ import annotations

import math
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def apply_guardrail(
    predicted_change_pct: float,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Apply guardrail to predicted change percentage.

    Clips extreme predictions and flags them.

    Args:
        predicted_change_pct: Raw predicted change (%).
        config: Guardrail config with 'clip_pct' and 'warn_pct' keys.

    Returns:
        Dict with 'predicted_change_pct_clipped' and 'sanity_flags'.
    """
    clip_pct = config.get("clip_pct", 30.0)
    warn_pct = config.get("warn_pct", 20.0)

    clipped = max(-clip_pct, min(clip_pct, predicted_change_pct))

    if abs(predicted_change_pct) > clip_pct:
        flags = ["CLIPPED"]
    elif abs(predicted_change_pct) > warn_pct:
        flags = ["WARN_HIGH"]
    else:
        flags = ["OK"]

    return {
        "predicted_change_pct_clipped": round(clipped, 4),
        "sanity_flags": flags,
    }


def compute_calibration_stats(
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute calibration metrics (Brier score, log-loss, ECE).

    Args:
        samples: List of dicts with 'prob_up' (float) and 'outcome' (0 or 1).

    Returns:
        Dict with brier_score, log_loss, ece, reliability_bins, n_calibrated.
    """
    n = len(samples)
    if n == 0:
        return {
            "brier_score": None,
            "log_loss": None,
            "ece": None,
            "reliability_bins": [],
            "n_calibrated": 0,
        }

    brier = sum((s["prob_up"] - s["outcome"]) ** 2 for s in samples) / n

    eps = 1e-7
    ll = -sum(
        s["outcome"] * math.log(max(s["prob_up"], eps))
        + (1 - s["outcome"]) * math.log(max(1 - s["prob_up"], eps))
        for s in samples
    ) / n

    bin_defs = [
        ("0.5-0.6", 0.5, 0.6),
        ("0.6-0.7", 0.6, 0.7),
        ("0.7-0.8", 0.7, 0.8),
        ("0.8-0.9", 0.8, 0.9),
        ("0.9-1.0", 0.9, 1.01),
    ]
    reliability_bins: list[dict[str, Any]] = []
    ece_sum = 0.0
    for label, lo, hi in bin_defs:
        bin_s = [s for s in samples if lo <= s["prob_up"] < hi]
        if not bin_s:
            continue
        mean_pred = sum(s["prob_up"] for s in bin_s) / len(bin_s)
        empirical = sum(s["outcome"] for s in bin_s) / len(bin_s)
        reliability_bins.append({
            "p_bin": label,
            "n": len(bin_s),
            "mean_pred": round(mean_pred, 3),
            "empirical": round(empirical, 3),
        })
        ece_sum += len(bin_s) * abs(mean_pred - empirical)

    ece = ece_sum / n

    return {
        "brier_score": round(brier, 4),
        "log_loss": round(ll, 4),
        "ece": round(ece, 4),
        "reliability_bins": reliability_bins,
        "n_calibrated": n,
    }


def platt_scaling_calibrate(
    prob_up: float,
    _model_params: dict[str, float] | None = None,
) -> float | None:
    """Apply Platt scaling to recalibrate prob_up.

    Currently a stub. Returns None until sufficient data is available
    to fit the logistic regression parameters (A, B).

    Args:
        prob_up: Raw probability estimate.
        _model_params: Logistic regression params {'A': float, 'B': float}.

    Returns:
        Calibrated probability, or None if params are not available.
    """
    if _model_params is None:
        return None

    a = _model_params.get("A", 0.0)
    b = _model_params.get("B", 0.0)
    logit = a * prob_up + b
    return round(1.0 / (1.0 + math.exp(-logit)), 4)
