from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.evaluation.forward_validation import (
    evaluate_predictions,
    fetch_histories_yfinance,
    iter_prediction_snapshots,
    reconstruct_predictions,
    summarize_evaluations,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild committed JP predictions and compare them with later prices.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--since", default="2026-02-18")
    parser.add_argument("--until", default=None)
    parser.add_argument("--output", default="artifacts/forward_validation.json")
    parser.add_argument("--summary", default="artifacts/forward_validation_summary.json")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    snapshots = iter_prediction_snapshots(repo_root, since=args.since, until=args.until)
    predictions = reconstruct_predictions(snapshots)
    if not predictions:
        raise SystemExit("No committed predictions found")

    histories = fetch_histories_yfinance(predictions, max_horizon=60)
    evaluated = evaluate_predictions(predictions, histories, horizons=(5, 20, 60))
    summary = summarize_evaluations(evaluated, horizons=(5, 20, 60))
    summary["source"] = {
        "repository": "nakaj1214/trader",
        "source_path": "dashboard/data/predictions_jp.json",
        "since": args.since,
        "until": args.until,
        "snapshot_count": len(snapshots),
    }

    output_path = repo_root / args.output
    summary_path = repo_root / args.summary
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(evaluated, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
