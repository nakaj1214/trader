from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.benchmark import (  # noqa: E402
    add_benchmark_excess_returns,
    benchmark_returns_for_dates,
    summarize_excess_returns,
)
from src.evaluation.forward_validation import (  # noqa: E402
    evaluate_predictions,
    fetch_histories_yfinance,
    iter_prediction_snapshots,
    reconstruct_predictions,
    summarize_evaluations,
)
from src.evaluation.inflection_backtest import (  # noqa: E402
    simulate_signals,
    summarize_trades,
)

BENCHMARK_SYMBOL = "1306.T"
BENCHMARK_NAME = "NF TOPIX ETF (TOPIX total-return proxy)"
ROUND_TRIP_COST_PCT = 0.2
TAX_RATE_PCT = 20.315


def _compact_row(row: dict, horizon: int | None = None) -> dict:
    result = {
        "date": row.get("date"),
        "ticker": row.get("ticker"),
        "current_price": row.get("current_price"),
        "reference_close": row.get("reference_close"),
        "reference_price_diff_pct": row.get("reference_price_diff_pct"),
        "source_commit": row.get("source_commit"),
    }
    if horizon is not None:
        result.update({
            f"h{horizon}_return_pct": row.get(f"h{horizon}_return_pct"),
            f"h{horizon}_max_return_pct": row.get(f"h{horizon}_max_return_pct"),
            f"h{horizon}_max_drawdown_pct": row.get(f"h{horizon}_max_drawdown_pct"),
            f"h{horizon}_benchmark_return_pct": row.get(f"h{horizon}_benchmark_return_pct"),
            f"h{horizon}_excess_return_pct": row.get(f"h{horizon}_excess_return_pct"),
        })
    return result


def _fetch_benchmark(predictions: list[dict]) -> object:
    dates = [str(row["date"]) for row in predictions]
    start = min(dates)
    return yf.Ticker(BENCHMARK_SYMBOL).history(
        start=start,
        auto_adjust=False,
        actions=False,
    )


def _tradable_summary(
    predictions: list[dict],
    histories: dict,
    holding_days: int,
    apply_tax: bool,
) -> dict:
    signals = [
        {
            "ticker": str(row["ticker"]),
            "signal_date": str(row["date"]),
            "score": float(row.get("predicted_change_pct") or 0.0),
        }
        for row in predictions
    ]
    trades = simulate_signals(
        signals,
        histories,
        holding_days=holding_days,
        round_trip_cost_pct=ROUND_TRIP_COST_PCT,
        tax_rate_pct=TAX_RATE_PCT,
        apply_tax=apply_tax,
    )
    result = summarize_trades(trades)
    result["holding_days"] = holding_days
    result["entry_rule"] = "next_trading_day_open"
    result["exit_rule"] = f"close_after_{holding_days}_trading_days"
    result["round_trip_cost_pct"] = ROUND_TRIP_COST_PCT
    result["tax_rate_pct"] = TAX_RATE_PCT if apply_tax else 0.0
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild committed JP predictions and compare them with later prices."
    )
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
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
    evaluated = evaluate_predictions(
        predictions,
        histories,
        horizons=(5, 20, 60),
        forecast_horizon=5,
    )

    benchmark_history = _fetch_benchmark(predictions)
    benchmark = benchmark_returns_for_dates(
        {str(row["date"]) for row in predictions},
        benchmark_history,
        horizons=(5, 20, 60),
    )
    evaluated = add_benchmark_excess_returns(evaluated, benchmark, horizons=(5, 20, 60))

    summary = summarize_evaluations(evaluated, horizons=(5, 20, 60))
    summary["benchmark"] = {
        "symbol": BENCHMARK_SYMBOL,
        "name": BENCHMARK_NAME,
        "excess_returns": summarize_excess_returns(evaluated, horizons=(5, 20, 60)),
    }
    summary["tradable_candidate_test"] = {
        "note": "Historical trader candidates, not the new inflection strategy. Uses buyable next-day open and fixed holding periods.",
        "pre_tax": {
            f"h{h}": _tradable_summary(predictions, histories, h, apply_tax=False)
            for h in (5, 20, 60)
        },
        "taxable_account_simple": {
            f"h{h}": _tradable_summary(predictions, histories, h, apply_tax=True)
            for h in (5, 20, 60)
        },
    }
    summary["source"] = {
        "repository": "nakaj1214/trader",
        "source_path": "dashboard/data/predictions_jp.json",
        "since": args.since,
        "until": args.until,
        "snapshot_count": len(snapshots),
    }

    mismatches = [row for row in evaluated if row.get("reference_price_match") is False]
    mismatches.sort(
        key=lambda row: abs(float(row.get("reference_price_diff_pct") or 0.0)),
        reverse=True,
    )
    summary["data_quality"]["reference_price_mismatches"] = [
        _compact_row(row) for row in mismatches
    ]

    for horizon in (20, 60):
        explosive = [
            row
            for row in evaluated
            if isinstance(row.get(f"h{horizon}_max_return_pct"), (int, float))
            and float(row[f"h{horizon}_max_return_pct"]) >= 50.0
        ]
        explosive.sort(
            key=lambda row: float(row[f"h{horizon}_max_return_pct"]),
            reverse=True,
        )
        summary["performance"][f"h{horizon}"]["explosive_candidates"] = [
            _compact_row(row, horizon=horizon) for row in explosive
        ]

    h5_rows = [
        row for row in evaluated if isinstance(row.get("h5_return_pct"), (int, float))
    ]
    summary["performance"]["h5"]["best_candidates"] = [
        _compact_row(row, horizon=5)
        for row in sorted(
            h5_rows,
            key=lambda row: float(row["h5_return_pct"]),
            reverse=True,
        )[:10]
    ]
    summary["performance"]["h5"]["worst_candidates"] = [
        _compact_row(row, horizon=5)
        for row in sorted(h5_rows, key=lambda row: float(row["h5_return_pct"]))[:10]
    ]

    output_path = repo_root / args.output
    summary_path = repo_root / args.summary
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(evaluated, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        "forward validation complete: "
        f"snapshots={len(snapshots)} predictions={len(evaluated)} "
        f"output={output_path} summary={summary_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
