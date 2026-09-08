from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.rebuild_inflection_forward_validation import _fetch_adjusted_histories
from src.data.snapshot_crypto import snapshot_encryption_secret
from src.evaluation.inflection_forward import BENCHMARK_TICKER
from src.evaluation.inflection_learning import (
    LEARNING_HORIZONS,
    build_learning_report,
    load_learning_observations,
    public_learning_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild cumulative self-learning knowledge from encrypted JP inflection snapshots."
    )
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--snapshot-dir", default="dashboard/data/inflection")
    parser.add_argument("--output", default="artifacts/inflection_learning.json")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    snapshot_dir = repo_root / args.snapshot_dir
    encrypted_snapshots = list(snapshot_dir.glob("????-??-??.enc")) if snapshot_dir.exists() else []
    if not encrypted_snapshots:
        print("No encrypted immutable snapshots available yet; nothing to learn.")
        return 0

    observations = load_learning_observations(
        snapshot_dir,
        encryption_secret=snapshot_encryption_secret(),
    )
    if not observations:
        print("Encrypted snapshots exist but contain no deep-scan candidates to learn from.")
        return 0

    max_horizon = max(LEARNING_HORIZONS)
    histories = _fetch_adjusted_histories(
        observations,
        max_horizon=max_horizon,
        request_interval_seconds=0.2,
    )
    benchmark_rows = [
        {"ticker": BENCHMARK_TICKER, "date": observation["signal_date"]}
        for observation in observations
    ]
    benchmark_history = _fetch_adjusted_histories(
        benchmark_rows,
        max_horizon=max_horizon,
        request_interval_seconds=0.2,
    )[BENCHMARK_TICKER]

    report = build_learning_report(observations, histories, benchmark_history)
    output = repo_root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary_output = output.with_name(f"{output.stem}_summary.json")
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
