"""Dashboard JSON exporter: generates predictions, accuracy, and comparison JSON.

Migrated from src/exporter.py. Reads from DB instead of Google Sheets.
Writes to dashboard/data/ for Cloudflare Pages deployment.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from src.core.config import ROOT_DIR
from src.enrichment.base import is_jp_ticker
from src.prediction.calibrator import apply_guardrail
from src.prediction.prophet_model import compute_prob_up

logger = structlog.get_logger(__name__)

DASHBOARD_DIR: Path = ROOT_DIR / "dashboard"
DATA_DIR: Path = DASHBOARD_DIR / "data"


def safe_write_json(data: Any, filepath: Path) -> bool:
    """Atomically write JSON data to file.

    Writes to a temp file first, then renames. Skips write if data is empty.

    Args:
        data: JSON-serializable data.
        filepath: Target file path.

    Returns:
        True if written successfully, False otherwise.
    """
    if not data:
        logger.warning("empty_data_skip_write", path=str(filepath))
        return False

    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = filepath.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(filepath)
        logger.info("json_exported", path=str(filepath))
        return True
    except Exception:
        logger.exception("json_write_error", path=str(filepath))
        if tmp_path.exists():
            tmp_path.unlink()
        return False


def build_predictions_json(
    records: list[dict[str, Any]],
    enrichment: dict[tuple[str, str], dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build predictions.json data from prediction records.

    Args:
        records: Prediction records (DB format or legacy Sheets format).
        enrichment: Optional enrichment data keyed by (date, ticker).
        config: App config for guardrail settings.

    Returns:
        List of prediction dicts for JSON output.
    """
    if enrichment is None:
        enrichment = {}

    guardrail_cfg = (
        config.get("prediction", {}).get("guardrail", {}) if config else {}
    )

    results: list[dict[str, Any]] = []
    for r in records:
        date = r.get("date", r.get("日付", ""))
        ticker = r.get("ticker", r.get("ティッカー", ""))
        pct = _to_float(r.get("predicted_change_pct", r.get("予測上昇率(%)", 0)))
        ci = _to_float(r.get("confidence_interval_pct", r.get("信頼区間(%)", 0)))

        item: dict[str, Any] = {
            "date": date,
            "ticker": ticker,
            "current_price": _to_float(r.get("current_price", r.get("現在価格", 0))),
            "predicted_price": _to_float(r.get("predicted_price", r.get("予測価格", 0))),
            "predicted_change_pct": pct,
            "ci_pct": ci,
            "actual_price": _to_float_or_none(r.get("actual_price", r.get("翌週実績価格"))),
            "status": r.get("status", r.get("ステータス", "")),
            "hit": _normalize_hit(r),
        }

        if config is not None:
            guardrail = apply_guardrail(pct, guardrail_cfg)
            item["predicted_change_pct_clipped"] = guardrail["predicted_change_pct_clipped"]
            item["sanity_flags"] = guardrail["sanity_flags"]

        item["prob_up"] = compute_prob_up(pct, ci)
        item["prob_up_calibrated"] = r.get("prob_up_calibrated")

        key = (date, ticker)
        ticker_data = enrichment.get(key, {})
        if ticker_data:
            _merge_enrichment(item, ticker_data)

        results.append(item)
    return results


def build_accuracy_json(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build accuracy.json from prediction records.

    Args:
        records: All prediction records.

    Returns:
        Accuracy data dict with weekly and cumulative stats.
    """
    from src.evaluation.calibration_metrics import build_calibration_metrics

    evaluable = _get_evaluable_records(records)

    weekly: dict[str, dict[str, int]] = {}
    for r in evaluable:
        date = r.get("date", r.get("日付", ""))
        if date not in weekly:
            weekly[date] = {"hits": 0, "total": 0}
        weekly[date]["total"] += 1
        if _is_hit(r):
            weekly[date]["hits"] += 1

    weekly_list: list[dict[str, Any]] = []
    for date in sorted(weekly.keys()):
        w = weekly[date]
        weekly_list.append({
            "date": date,
            "hits": w["hits"],
            "total": w["total"],
            "hit_rate_pct": round(w["hits"] / w["total"] * 100, 1) if w["total"] > 0 else 0.0,
        })

    cum_hits = sum(w["hits"] for w in weekly.values())
    cum_total = sum(w["total"] for w in weekly.values())

    accuracy: dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "weekly": weekly_list,
        "cumulative": {
            "hit_rate_pct": round(cum_hits / cum_total * 100, 1) if cum_total > 0 else 0.0,
            "hits": cum_hits,
            "total": cum_total,
        },
    }

    accuracy["error_analysis"] = build_error_analysis(records)
    accuracy["calibration"] = build_calibration_metrics(records)

    return accuracy


def build_error_analysis(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build prediction error analysis by predicted-change bins.

    Args:
        records: All prediction records.

    Returns:
        Dict with mae_pct, bins, notes.
    """
    confirmed: list[dict[str, float]] = []
    for r in records:
        status = r.get("status", r.get("ステータス", ""))
        if status not in ("confirmed", "確定済み"):
            continue
        actual = _to_float_or_none(r.get("actual_price", r.get("翌週実績価格")))
        current = _to_float(r.get("current_price", r.get("現在価格", 0)))
        predicted_pct = _to_float(r.get("predicted_change_pct", r.get("予測上昇率(%)", 0)))
        if actual is None or current <= 0:
            continue
        actual_pct = (actual - current) / current * 100
        confirmed.append({"predicted_pct": predicted_pct, "actual_pct": actual_pct})

    if not confirmed:
        return {"mae_pct": None, "bins": [], "notes": "Prediction error by predicted-change band."}

    errors = [abs(c["predicted_pct"] - c["actual_pct"]) for c in confirmed]
    mae = round(sum(errors) / len(errors), 1)

    bin_defs = [("0-5%", 0, 5), ("5-10%", 5, 10), ("10-20%", 10, 20), ("20%+", 20, float("inf"))]
    bins: list[dict[str, Any]] = []
    for label, lo, hi in bin_defs:
        in_bin = [c for c in confirmed if lo <= c["predicted_pct"] < hi]
        if not in_bin:
            continue
        avg_pred = round(sum(c["predicted_pct"] for c in in_bin) / len(in_bin), 1)
        avg_actual = round(sum(c["actual_pct"] for c in in_bin) / len(in_bin), 1)
        bins.append({
            "range": label,
            "avg_predicted_pct": avg_pred,
            "avg_actual_pct": avg_actual,
            "count": len(in_bin),
        })

    return {
        "mae_pct": mae,
        "bins": bins,
        "notes": "Prediction error by predicted-change band. MAE = mean absolute error.",
    }


def build_stock_history_json(
    records: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Build stock_history.json from prediction records.

    Args:
        records: All prediction records.

    Returns:
        Mapping of ticker -> list of date/price entries.
    """
    history: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        ticker = r.get("ticker", r.get("ティッカー", ""))
        date = r.get("date", r.get("日付", ""))
        if ticker not in history:
            history[ticker] = []
        entry: dict[str, Any] = {
            "date": date,
            "predicted_price": _to_float(r.get("predicted_price", r.get("予測価格", 0))),
        }
        actual = _to_float_or_none(r.get("actual_price", r.get("翌週実績価格")))
        if actual is not None:
            entry["actual_price"] = actual
        history[ticker].append(entry)

    for ticker in history:
        history[ticker].sort(key=lambda x: x["date"])

    return history


def split_records_by_market(
    records: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Split records into US and JP markets based on ticker suffix.

    Returns:
        Dict with 'us' and 'jp' record lists.
    """
    us_records = [r for r in records if not is_jp_ticker(r.get("ticker", r.get("ティッカー", "")))]
    jp_records = [r for r in records if is_jp_ticker(r.get("ticker", r.get("ティッカー", "")))]
    return {"us": us_records, "jp": jp_records}


def export_dashboard_json(
    records: list[dict[str, Any]],
    enrichment: dict[tuple[str, str], dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
) -> bool:
    """Export all dashboard JSON files.

    Args:
        records: All prediction records.
        enrichment: Optional enrichment data.
        config: Application config.

    Returns:
        True if all exports succeeded.
    """
    by_market = split_records_by_market(records)
    us_records = by_market["us"]
    jp_records = by_market["jp"]

    results: list[bool] = []

    us_preds = build_predictions_json(us_records, enrichment, config)
    if us_preds:
        results.append(safe_write_json({"predictions": us_preds}, DATA_DIR / "predictions_us.json"))
        results.append(safe_write_json({"predictions": us_preds}, DATA_DIR / "predictions.json"))

    if jp_records:
        jp_preds = build_predictions_json(jp_records, enrichment, config)
        if jp_preds:
            results.append(safe_write_json({"predictions": jp_preds}, DATA_DIR / "predictions_jp.json"))

    accuracy = build_accuracy_json(records)
    results.append(safe_write_json(accuracy, DATA_DIR / "accuracy.json"))

    stock_history = build_stock_history_json(records)
    results.append(safe_write_json(stock_history, DATA_DIR / "stock_history.json"))

    return all(results) if results else False


# --- Private helpers ---

def _to_float(value: Any) -> float:
    """Convert to float, returning 0.0 on failure."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _to_float_or_none(value: Any) -> float | None:
    """Convert to float, returning None for empty/N/A/failure."""
    if value is None or value == "" or value == "N/A":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _normalize_hit(record: dict[str, Any]) -> str | None:
    """Normalize hit field to string."""
    hit = record.get("is_hit", record.get("的中"))
    if hit is True or hit == "的中":
        return "的中"
    if hit is False or hit == "外れ":
        return "外れ"
    return None


def _is_hit(record: dict[str, Any]) -> bool:
    """Check if a record is a hit."""
    hit = record.get("is_hit", record.get("的中"))
    return hit is True or hit == "的中"


def _get_evaluable_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter to confirmed records with evaluable hit status."""
    evaluable: list[dict[str, Any]] = []
    for r in records:
        status = r.get("status", r.get("ステータス", ""))
        if status not in ("confirmed", "確定済み"):
            continue
        hit = r.get("is_hit", r.get("的中"))
        if hit in (True, False, "的中", "外れ"):
            evaluable.append(r)
    return evaluable


def _merge_enrichment(item: dict[str, Any], ticker_data: dict[str, Any]) -> None:
    """Merge enrichment data into a prediction item dict."""
    enrichment_keys = [
        "risk", "events", "evidence", "explanations", "sizing",
        "short_interest", "institutional", "news_sentiment",
        "earnings_warning", "jp_fundamentals", "jp_listed_info",
    ]
    for key in enrichment_keys:
        if key in ticker_data:
            item[key] = ticker_data[key]

    scalar_keys = ["fifty2w_score", "fifty2w_pct_from_high"]
    for key in scalar_keys:
        if key in ticker_data:
            item[key] = ticker_data[key]

    if "sentiment" in ticker_data:
        for sub_key in ["news_sentiment", "short_interest", "fifty2w_score", "fifty2w_pct_from_high"]:
            if sub_key in ticker_data["sentiment"]:
                item[sub_key] = ticker_data["sentiment"][sub_key]
