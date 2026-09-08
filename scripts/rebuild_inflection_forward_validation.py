from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.inflection_backtest import simulate_signals, summarize_trades
from src.evaluation.inflection_forward import (
    BENCHMARK_TICKER,
    benchmark_returns_by_signal_date,
    enrich_trades_with_benchmark,
    load_inflection_signals,
    summarize_benchmark_excess,
)

ROUND_TRIP_COST_PCT = 0.2
TAX_RATE_PCT = 20.315


def _snapshot_secret() -> str:
    secret = os.getenv("SNAPSHOT_ENCRYPTION_KEY") or os.getenv("JQUANTS_API_KEY")
    if not secret:
        raise RuntimeError("SNAPSHOT_ENCRYPTION_KEY or JQUANTS_API_KEY is required to decrypt snapshots")
    return secret


def _fetch_adjusted_histories(
    rows: list[dict[str, Any]],
    *,
    max_horizon: int,
) -> dict[str, pd.DataFrame]:
    """Fetch split-adjusted OHLC and fail loudly on missing provider data."""
    import yfinance as yf

    by_ticker: dict[str, list[pd.Timestamp]] = {}
    for row in rows:
        ticker = str(row["ticker"])
        by_ticker.setdefault(ticker, []).append(pd.Timestamp(str(row["date"])))

    histories: dict[str, pd.DataFrame] = {}
    failures: dict[str, str] = {}
    for ticker, dates in sorted(by_ticker.items()):
        start = min(dates) - timedelta(days=10)
        end = max(dates) + timedelta(days=max_horizon * 2 + 30)
        try:
            history = yf.Ticker(ticker).history(
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                auto_adjust=True,
                actions=False,
            )
        except Exception as exc:  # noqa: BLE001 - all provider failures are reported together
            failures[ticker] = f"{type(exc).__name__}: {exc}"
            continue
        if history.empty or "Open" not in history.columns or "Close" not in history.columns:
            failures[ticker] = "empty or missing adjusted Open/Close"
            continue
        histories[ticker] = history

    if failures:
        detail = "; ".join(f"{ticker} ({reason})" for ticker, reason in failures.items())
        raise RuntimeError(f"Forward price retrieval failed: {detail}")
    return histories


def main() -> int:
    parser = argparse.ArgumentParser(description="Forward-validate encrypted immutable JP inflection snapshots.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--snapshot-dir", default="dashboard/data/inflection")
    parser.add_argument("--output", default="artifacts/inflection_forward_validation.json")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    snapshot_dir = repo_root / args.snapshot_dir
    encrypted_snapshots = list(snapshot_dir.glob("????-??-??.enc")) if snapshot_dir.exists() else []
    if not encrypted_snapshots:
        print("No encrypted immutable EARLY_CANDIDATE snapshots available yet; nothing to validate.")
        return 0

    signals = load_inflection_signals(snapshot_dir, encryption_secret=_snapshot_secret())
    if not signals:
        print("Encrypted snapshots exist but contain no EARLY_CANDIDATE signals yet.")
        return 0

    histories = _fetch_adjusted_histories(signals, max_horizon=60)
    benchmark_rows = [
        {"ticker": BENCHMARK_TICKER, "date": signal["signal_date"]}
        for signal in signals
    ]
    benchmark_history = _fetch_adjusted_histories(benchmark_rows, max_horizon=60)[BENCHMARK_TICKER]

    report: dict[str, object] = {
        "signal_count": len(signals),
        "evaluation_unit": "independent_daily_signal_observation",
        "portfolio_interpretation": False,
        "entry_rule": "next_trading_day_open",
        "price_adjustment": "split_adjusted_ohlc",
        "round_trip_cost_pct": ROUND_TRIP_COST_PCT,
        "benchmark": {
            "ticker": BENCHMARK_TICKER,
            "name": "NEXT FUNDS TOPIX ETF",
            "entry_rule": "same next-trading-day open",
            "cost_rule": "same round-trip cost as candidate trades",
        },
        "jquants_delay_note": (
            "Free-tier delayed fundamentals are evaluated exactly as observed in each encrypted immutable snapshot."
        ),
        "horizons": {},
    }
    horizons: dict[str, object] = {}
    signal_dates = [str(signal["signal_date"]) for signal in signals]
    for holding_days in (5, 20, 60):
        trades = simulate_signals(
            signals,
            histories,
            holding_days=holding_days,
            round_trip_cost_pct=ROUND_TRIP_COST_PCT,
            tax_rate_pct=TAX_RATE_PCT,
            apply_tax=False,
        )
        benchmark_returns = benchmark_returns_by_signal_date(
            signal_dates,
            benchmark_history,
            holding_days=holding_days,
            round_trip_cost_pct=ROUND_TRIP_COST_PCT,
        )
        trade_rows = enrich_trades_with_benchmark(trades, benchmark_returns)
        horizons[f"h{holding_days}"] = {
            "summary": summarize_trades(trades),
            "benchmark_excess": summarize_benchmark_excess(trade_rows),
            "trades": trade_rows,
        }
    report["horizons"] = horizons

    output = repo_root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"signal_count": len(signals), "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
