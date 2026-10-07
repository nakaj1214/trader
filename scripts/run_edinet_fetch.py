"""EDINET list probe and resumable local acquisition.

    set -a; . ./.env; set +a
    python scripts/run_edinet_fetch.py --probe 2026-10-06
    python scripts/run_edinet_fetch.py --fetch --start 2024-10-01 --end 2026-07-01
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.edinet import JST, EdinetClient, EdinetError, fetch_range, probe


def _date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() == value:
            return parsed
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("date must be YYYY-MM-DD")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe or cache EDINET document-list metadata.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--probe", type=_date, metavar="DATE")
    mode.add_argument("--fetch", action="store_true")
    parser.add_argument("--start", type=_date)
    parser.add_argument("--end", type=_date)
    parser.add_argument("--cache-dir", type=Path, default=REPO_ROOT / ".data/edinet/filings")
    args = parser.parse_args(argv)
    if args.fetch and (args.start is None or args.end is None):
        parser.error("--fetch requires --start and --end")
    if args.probe and (args.start is not None or args.end is not None):
        parser.error("--start and --end require --fetch")
    if args.fetch and args.start > args.end:
        parser.error("--start must not be after --end")
    if (args.probe or args.end) > datetime.now(JST).date():
        parser.error("dates must not be in the future")
    try:
        client = EdinetClient()
        result = (
            probe(client, args.probe.isoformat())
            if args.probe else fetch_range(client, args.start, args.end, args.cache_dir)
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except EdinetError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"EDINET cache failure: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
