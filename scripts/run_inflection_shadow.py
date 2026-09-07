"""Run the production Japanese inflection scanner and persist an immutable daily snapshot."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.screening.inflection_live import scan_japan_inflection

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "dashboard" / "data" / "inflection"
LATEST = ROOT / "dashboard" / "data" / "inflection_candidates.json"
JST = ZoneInfo("Asia/Tokyo")

MIN_UNIVERSE_COUNT = 3000
MIN_PRICE_COVERAGE = 0.70


def validate_report(report: dict[str, Any]) -> None:
    """Reject incomplete or inconsistent scan results before they are persisted."""
    universe = int(report.get("universe_count") or 0)
    price_data = int(report.get("price_data_count") or 0)
    deep_count = int(report.get("deep_candidate_count") or 0)
    candidates = report.get("candidates")

    if universe < MIN_UNIVERSE_COUNT:
        raise RuntimeError(
            f"DATA_HEALTH: universe too small: {universe} < {MIN_UNIVERSE_COUNT}"
        )

    if universe <= 0 or price_data / universe < MIN_PRICE_COVERAGE:
        coverage = (price_data / universe) if universe > 0 else 0.0
        raise RuntimeError(
            "DATA_HEALTH: price coverage too low: "
            f"{price_data}/{universe} ({coverage:.1%})"
        )

    if deep_count <= 0:
        raise RuntimeError("DATA_HEALTH: no deep candidates were produced")

    if not isinstance(candidates, list) or len(candidates) != deep_count:
        actual = len(candidates) if isinstance(candidates, list) else "invalid"
        raise RuntimeError(
            "DATA_HEALTH: candidate count mismatch: "
            f"deep_candidate_count={deep_count}, candidates={actual}"
        )

    tickers = [
        str(row.get("ticker") or "")
        for row in candidates
        if isinstance(row, dict)
    ]
    if len(tickers) != len(candidates) or any(not ticker for ticker in tickers):
        raise RuntimeError("DATA_HEALTH: candidate ticker missing or invalid")
    if len(tickers) != len(set(tickers)):
        raise RuntimeError("DATA_HEALTH: duplicate candidate tickers detected")


def snapshot_date(now: datetime | None = None) -> str:
    """Return the calendar date in Japan used for the immutable snapshot filename."""
    current = now or datetime.now(JST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=JST)
    return current.astimezone(JST).strftime("%Y-%m-%d")


def main() -> None:
    report = scan_japan_inflection()
    validate_report(report)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = OUT_DIR / f"{snapshot_date()}.json"
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    snapshot.write_text(payload + "\n", encoding="utf-8")
    LATEST.write_text(payload + "\n", encoding="utf-8")

    counts = report.get("classification_counts", {})
    print(
        "inflection shadow scan complete: "
        f"universe={report.get('universe_count')} "
        f"price_data={report.get('price_data_count')} "
        f"early={counts.get('EARLY_CANDIDATE', 0)} "
        f"watch={counts.get('WATCH', 0)} "
        f"overextended={counts.get('OVEREXTENDED', 0)}"
    )


if __name__ == "__main__":
    main()
