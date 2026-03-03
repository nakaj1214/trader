"""Alpha survey: academic anomaly statistical verification.

Migrated from src/alpha_survey.py. Records anomaly test results
as reference information (not used in scoring).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from src.core.config import ROOT_DIR

logger = structlog.get_logger(__name__)

DATA_DIR: Path = ROOT_DIR / "dashboard" / "data"
ALPHA_SURVEY_PATH: Path = DATA_DIR / "alpha_survey.json"

ANOMALY_META: dict[str, dict[str, Any]] = {
    "short_interest_effect": {
        "label": "Short Interest Effect",
        "score_included": False,
        "note": "Assumes equal-weight. Effect may be weak for cap-weighted large caps.",
    },
    "earnings_momentum": {
        "label": "Earnings Momentum Effect",
        "score_included": False,
        "note": "Based on SUE (Standardized Unexpected Earnings). Under evaluation.",
    },
}


def run_anomaly_test(
    anomaly_name: str,
    lookback_weeks: int = 52,
) -> dict[str, Any]:
    """Run a single anomaly test.

    Currently returns insufficient_data until enough data accumulates.

    Args:
        anomaly_name: Anomaly identifier key.
        lookback_weeks: Number of weeks for test window.

    Returns:
        Test result dict with name, n_observations, t_stat, p_value, sharpe, status.
    """
    return {
        "name": anomaly_name,
        "n_observations": 0,
        "t_stat": None,
        "p_value": None,
        "sharpe": None,
        "status": "insufficient_data",
    }


def build_alpha_survey_json(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build alpha_survey.json from anomaly test results.

    Marks entries with n_observations < 52 as insufficient_data.

    Args:
        results: List of run_anomaly_test outputs.

    Returns:
        Dict with as_of_utc and anomalies list.
    """
    anomalies: list[dict[str, Any]] = []
    for r in results:
        meta = ANOMALY_META.get(r["name"], {})
        n = r.get("n_observations", 0)
        status = "insufficient_data" if n < 52 else r.get("status", "insufficient_data")

        anomalies.append({
            "name": r["name"],
            "label": meta.get("label", r["name"]),
            "n_observations": n,
            "t_stat": r.get("t_stat"),
            "p_value": r.get("p_value"),
            "sharpe": r.get("sharpe"),
            "status": status,
            "score_included": meta.get("score_included", False),
            "note": meta.get("note", ""),
        })

    return {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "anomalies": anomalies,
    }


def run_and_export() -> bool:
    """Run all anomaly tests and export alpha_survey.json.

    Returns:
        True on success, False on failure.
    """
    anomaly_names = list(ANOMALY_META.keys())
    results = [run_anomaly_test(name) for name in anomaly_names]
    data = build_alpha_survey_json(results)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = ALPHA_SURVEY_PATH.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(ALPHA_SURVEY_PATH)
        logger.info("alpha_survey_exported")
        return True
    except Exception:
        logger.exception("alpha_survey_export_failed")
        if tmp.exists():
            tmp.unlink()
        return False
