"""Run the production Japanese inflection scanner and persist an immutable daily snapshot."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.screening.inflection_live import scan_japan_inflection

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "dashboard" / "data" / "inflection"
LATEST = ROOT / "dashboard" / "data" / "inflection_candidates.json"


def main() -> None:
    report = scan_japan_inflection()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    snapshot = OUT_DIR / f"{stamp}.json"
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
