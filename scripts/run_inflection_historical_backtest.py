"""Local-only point-in-time backtest of the v3 scan on cached J-Quants history.

    set -a; . ./.env; set +a
    python scripts/run_inflection_historical_backtest.py --probe     # is the range reachable?
    python scripts/run_inflection_historical_backtest.py --fetch     # resumable; hours on the Free plan
    python scripts/run_inflection_historical_backtest.py --verify-adjustment 5
    python scripts/run_inflection_historical_backtest.py             # evaluate from the cache

Evaluation only: no thresholds or weights are searched. The cache and the outputs stay out of git.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.jquants_history import (
    HistoryFetchStopped,
    default_fetch_range,
    fetch_range,
    load_cache,
    probe,
)
from src.data.jquants_v2_client import JQuantsV2Client
from src.evaluation.inflection_historical import (
    DEFAULT_MIN_INDEPENDENT,
    HistoricalData,
    build_backtest_report,
    check_adjustment,
    signal_days,
    summary_report,
)

DEFAULT_CACHE_DIR = ".data/jquants"
JST = ZoneInfo("Asia/Tokyo")


def _client() -> JQuantsV2Client:
    client = JQuantsV2Client()
    if not client.is_available():
        raise RuntimeError("JQUANTS_API_KEY is required (for example: set -a; . ./.env; set +a)")
    return client


def fetch_range_from_args(args: argparse.Namespace, today: date) -> tuple[date, date]:
    """``--start/--end`` override the shared default range (``default_fetch_range``)."""
    default_start, default_end = default_fetch_range(today)
    start = date.fromisoformat(args.start) if args.start else default_start
    end = date.fromisoformat(args.end) if args.end else default_end
    if start > end:
        raise ValueError(f"start {start} is after end {end}")
    return start, end


def verify_adjustment(client: Any, data: HistoricalData, count: int) -> list[dict[str, Any]]:
    """Check our split adjustment on up to ``count`` tickers that had a split in the cache.

    Each check fetches the ticker's whole history in ONE call (one adjustment basis) and
    compares its AdjC with our adjusted closes. Daily cache files are never the reference
    because files fetched before/after a split disagree on AdjC.
    """
    histories = data.panel.evaluation_histories()
    results = []
    for ticker in data.panel.split_tickers()[:count]:
        rows = client.daily_bars_by_code(f"{ticker[:4]}0")
        results.append({"ticker": ticker} | check_adjustment(histories[ticker]["Close"], rows))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Point-in-time backtest of the v3 scan on cached J-Quants history.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    parser.add_argument("--fetch", action="store_true", help="fetch and cache the range (resumable), then stop")
    parser.add_argument("--probe", action="store_true", help="request the first/last day once each, then stop")
    parser.add_argument("--verify-adjustment", type=int, metavar="N", help="check split adjustment on N tickers")
    parser.add_argument("--start", help="fetch start (default: shared default range)")
    parser.add_argument("--end", help="fetch end (default: shared default range)")
    parser.add_argument("--signal-start", help="first scan day (default: price and fundamentals warm-up)")
    parser.add_argument("--min-independent", type=int, default=DEFAULT_MIN_INDEPENDENT)
    parser.add_argument("--output", default="artifacts/inflection_historical_backtest.json")
    parser.add_argument("--summary-output", default="artifacts/inflection_historical_backtest_summary.json")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    cache_dir = repo_root / args.cache_dir
    try:
        if args.probe or args.fetch:
            start, end = fetch_range_from_args(args, datetime.now(JST).date())
            if args.probe:
                print(json.dumps(probe(_client(), start, end), ensure_ascii=False))
                return 0
            print(json.dumps(fetch_range(_client(), start, end, cache_dir), ensure_ascii=False))
            return 0
    except HistoryFetchStopped as exc:
        print(f"STOPPED: {exc}\nCached days are kept; adjust --start/--end and re-run to resume.", file=sys.stderr)
        return 2

    cache = load_cache(cache_dir)
    if not cache.days("bars"):
        print(f"No cached bars under {cache_dir}; run with --fetch first.", file=sys.stderr)
        return 1
    data = HistoricalData.from_cache(cache)

    if args.verify_adjustment is not None:
        try:
            checks = verify_adjustment(_client(), data, args.verify_adjustment)
        except HistoryFetchStopped as exc:
            print(f"STOPPED: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(checks, ensure_ascii=False, indent=2))
        return 0 if checks and all(check["constant"] for check in checks) else 1

    days = signal_days(data, args.signal_start)
    if not days:
        print("No scan days: the cache lacks 252 days of prices or enough fundamentals history.", file=sys.stderr)
        return 1
    report = build_backtest_report(data, days, min_independent=args.min_independent)

    output = repo_root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_output = repo_root / args.summary_output
    summary_output.write_text(
        json.dumps(summary_report(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "signal_days": len(days),
                "kill_criterion": {lag: item["kill_criterion"]["verdict"] for lag, item in report["lags"].items()},
                "lag_difference": (report["lag_comparison"] or {}).get("difference"),
                "output": str(output),
                "summary_output": str(summary_output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
