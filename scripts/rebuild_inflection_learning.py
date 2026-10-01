from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.forward_prices import DEFAULT_CACHE_RELATIVE_PATH, fetch_price_histories, shared_price_window
from src.data.snapshot_crypto import snapshot_encryption_secret
from src.evaluation.inflection_forward import BENCHMARK_TICKER
from src.evaluation.inflection_learning import (
    build_learning_report,
    load_inflection_learning_observations,
    public_learning_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild cumulative self-learning knowledge from encrypted JP inflection snapshots."
    )
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--snapshot-dir", default="dashboard/data/inflection/v3")
    parser.add_argument("--legacy-snapshot-dir", default="dashboard/data/inflection")
    parser.add_argument(
        "--promotion-strategy-version",
        default="jp-inflection-shadow-v3",
        help="Strategy version that promotion statistics are scoped to. Other "
        "strategy versions (e.g. legacy snapshots) still feed cumulative analysis "
        "but never become promotion candidates.",
    )
    parser.add_argument("--output", default="artifacts/inflection_learning.json")
    parser.add_argument("--summary-output", default="artifacts/inflection_learning_summary.json")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    snapshot_dir = repo_root / args.snapshot_dir
    legacy_snapshot_dir = repo_root / args.legacy_snapshot_dir

    def _load(directory: Path) -> list[dict[str, Any]]:
        if not directory.exists() or not list(directory.glob("????-??-??.enc")):
            return []
        return load_inflection_learning_observations(
            directory,
            encryption_secret=snapshot_encryption_secret(),
        )

    observations = sorted(
        _load(legacy_snapshot_dir) + _load(snapshot_dir),
        key=lambda row: (str(row["signal_date"]), str(row["ticker"])),
    )

    histories: dict[str, pd.DataFrame] = {}
    benchmark_history = pd.DataFrame()
    if observations:
        # Same window and cache as forward validation, so tickers it already fetched are not fetched again.
        window = shared_price_window([snapshot_dir, legacy_snapshot_dir], datetime.now(UTC).date())
        if window is None:
            raise RuntimeError("no snapshot files to size the price window")
        tickers = sorted({str(observation["ticker"]) for observation in observations} | {BENCHMARK_TICKER})
        fetched = fetch_price_histories(
            tickers,
            *window,
            cache_path=repo_root / DEFAULT_CACHE_RELATIVE_PATH,
            required={BENCHMARK_TICKER},
        )
        all_histories = fetched.total_return()
        benchmark_history = all_histories[BENCHMARK_TICKER]
        histories = {ticker: history for ticker, history in all_histories.items() if ticker != BENCHMARK_TICKER}

    report = build_learning_report(
        observations,
        histories,
        benchmark_history,
        promotion_strategy_version=args.promotion_strategy_version,
    )
    report["price_unavailable_ticker_count"] = len({str(row["ticker"]) for row in observations} - set(histories))
    output = repo_root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary_output = repo_root / args.summary_output
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(
        json.dumps(public_learning_summary(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "observation_count": len(observations),
                "lesson_count": len(report.get("lessons", [])),
                "postmortem_count": len(report.get("postmortems", [])),
                "output": str(output),
                "summary_output": str(summary_output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
