"""Walk-forward evaluation: rolling window out-of-sample testing.

Migrated from src/walkforward.py. Now supports both DB records
and legacy Sheets-format records.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def compute_walkforward(
    records: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Run walk-forward evaluation on confirmed prediction records.

    Splits confirmed records into rolling train/test windows and
    computes hit rate, MAE, MAPE for each test window.

    Args:
        records: All prediction records (DB or Sheets format).
        config: Application config with evaluation.walkforward settings.

    Returns:
        Walk-forward result dict with config, windows list.
    """
    wf_cfg = config.get("evaluation", {}).get("walkforward", {})
    train_weeks = int(wf_cfg.get("train_weeks", 52))
    test_weeks = int(wf_cfg.get("test_weeks", 13))
    min_train_weeks = int(wf_cfg.get("min_train_weeks", 26))

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result_config = {
        "train_weeks": train_weeks,
        "test_weeks": test_weeks,
        "min_train_weeks": min_train_weeks,
    }

    confirmed: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        status = r.get("status", r.get("ステータス", ""))
        if status not in ("confirmed", "確定済み"):
            continue
        date = r.get("date", r.get("日付", ""))
        if not date:
            continue
        confirmed.setdefault(date, []).append(r)

    weeks_sorted = sorted(confirmed.keys())
    total_weeks = len(weeks_sorted)

    if total_weeks < min_train_weeks + test_weeks:
        logger.info(
            "walkforward_insufficient_data",
            weeks=total_weeks,
            min_required=min_train_weeks + test_weeks,
        )
        return {
            "generated_at": generated_at,
            "config": result_config,
            "windows": [],
        }

    windows: list[dict[str, Any]] = []
    test_start_idx = min_train_weeks

    while test_start_idx + test_weeks <= total_weeks:
        train_start_idx = max(0, test_start_idx - train_weeks)
        train_weeks_actual = test_start_idx - train_start_idx

        if train_weeks_actual < min_train_weeks:
            test_start_idx += test_weeks
            continue

        train_dates = weeks_sorted[train_start_idx:test_start_idx]
        test_dates = weeks_sorted[test_start_idx:test_start_idx + test_weeks]

        test_records: list[dict[str, Any]] = []
        for d in test_dates:
            test_records.extend(confirmed[d])

        stats = _compute_window_stats(test_records)

        windows.append({
            "train_start": train_dates[0],
            "train_end": train_dates[-1],
            "test_start": test_dates[0],
            "test_end": test_dates[-1],
            **stats,
        })

        test_start_idx += test_weeks

    logger.info("walkforward_complete", n_windows=len(windows))

    return {
        "generated_at": generated_at,
        "config": result_config,
        "windows": windows,
    }


def _compute_window_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute hit rate and error metrics for a test window.

    Supports both new (English) and legacy (Japanese) field names.

    Returns:
        Dict with hit_rate_pct, mae, mape, n_predictions.
    """
    evaluable: list[dict[str, Any]] = []
    for r in records:
        hit = r.get("is_hit", r.get("的中", ""))
        if hit in (True, "的中"):
            evaluable.append({**r, "_hit": True})
        elif hit in (False, "外れ"):
            evaluable.append({**r, "_hit": False})

    n = len(evaluable)
    if n == 0:
        return {"hit_rate_pct": None, "mae": None, "mape": None, "n_predictions": 0}

    hits = sum(1 for r in evaluable if r["_hit"])
    hit_rate = round(hits / n * 100, 1)

    abs_errors: list[float] = []
    abs_pct_errors: list[float] = []
    for r in evaluable:
        try:
            predicted = float(
                r.get("predicted_price", r.get("予測価格", "")) or ""
            )
            actual = float(
                r.get("actual_price", r.get("翌週実績価格", "")) or ""
            )
            if actual > 0:
                err = abs(predicted - actual)
                abs_errors.append(err)
                abs_pct_errors.append(err / actual * 100)
        except (ValueError, TypeError):
            continue

    mae = round(sum(abs_errors) / len(abs_errors), 4) if abs_errors else None
    mape = round(sum(abs_pct_errors) / len(abs_pct_errors), 4) if abs_pct_errors else None

    return {
        "hit_rate_pct": hit_rate,
        "mae": mae,
        "mape": mape,
        "n_predictions": n,
    }
