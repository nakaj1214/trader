from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import sys
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.live_quote import split_adjust_ohlc
from src.data.snapshot_crypto import decrypt_json, encrypt_json, snapshot_encryption_secret
from src.evaluation.inflection_backtest import (
    simulate_signals,
)
from src.evaluation.inflection_forward import (
    BENCHMARK_TICKER,
    load_inflection_signals,
)
from src.evaluation.inflection_portfolio import simulate_portfolio
from src.evaluation.inflection_recall import compute_tracked_pool_explosion_recall
from src.evaluation.inflection_report import (  # noqa: F401 - re-exported for existing tests
    BENCHMARK_ROUND_TRIP_COST_PCT,
    PORTFOLIO_INITIAL_CAPITAL_JPY,
    PORTFOLIO_MAX_POSITIONS,
    PORTFOLIO_POSITION_SIZE_PCT,
    ROUND_TRIP_COST_PCT,
    STRESS_ROUND_TRIP_COST_PCT,
    TAX_RATE_PCT,
    _build_group_report,
    _paired_trade_rows,
    _report_breakdowns,
    _summary_only,
    regime_label,
)

DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 2.0
DEFAULT_REQUEST_INTERVAL_SECONDS = 0.5
TOTAL_RETURN_ADJUSTED = "total_return_adjusted"
SPLIT_ONLY = "split_only"
PRICE_HASH_SCHEMA_VERSION = 1
MAX_PRICE_FAILURE_RATIO = 0.05


def _fetch_adjusted_histories(
    rows: list[dict[str, Any]],
    *,
    max_horizon: int,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
    request_interval_seconds: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    price_basis: str = TOTAL_RETURN_ADJUSTED,
    extra_lookback_days: int = 0,
) -> dict[str, pd.DataFrame]:
    """Fetch OHLC on the requested price basis with bounded retries."""
    import yfinance as yf

    if (
        max_retries < 0
        or retry_backoff_seconds < 0
        or request_interval_seconds < 0
        or extra_lookback_days < 0
    ):
        raise ValueError("retry and request timing parameters must not be negative")
    if price_basis not in {TOTAL_RETURN_ADJUSTED, SPLIT_ONLY}:
        raise ValueError(f"unsupported price basis: {price_basis}")

    by_ticker: dict[str, list[pd.Timestamp]] = {}
    for row in rows:
        ticker = str(row["ticker"])
        by_ticker.setdefault(ticker, []).append(pd.Timestamp(str(row["date"])))

    histories: dict[str, pd.DataFrame] = {}
    failures: dict[str, str] = {}
    provider_logger = logging.getLogger("yfinance")
    ticker_dates = sorted(by_ticker.items())
    required_columns = {"Open", "High", "Low", "Close"}
    for index, (ticker, dates) in enumerate(ticker_dates):
        start = min(dates) - timedelta(days=10 + extra_lookback_days)
        end = max(dates) + timedelta(days=max_horizon * 2 + 30)
        failure = "empty or missing adjusted OHLC"
        for attempt in range(max_retries + 1):
            try:
                was_disabled = provider_logger.disabled
                provider_logger.disabled = True
                try:
                    history = yf.Ticker(ticker).history(
                        start=start.strftime("%Y-%m-%d"),
                        end=end.strftime("%Y-%m-%d"),
                        auto_adjust=price_basis == TOTAL_RETURN_ADJUSTED,
                        actions=price_basis == SPLIT_ONLY,
                        timeout=15,
                        raise_errors=True,
                    )
                finally:
                    provider_logger.disabled = was_disabled
                if not history.empty and required_columns.issubset(history.columns):
                    if price_basis == SPLIT_ONLY:
                        history = split_adjust_ohlc(history, pd.Timestamp(history.index[-1]).date())
                    histories[ticker] = history
                    break
                failure = "empty or missing adjusted OHLC"
            except Exception as exc:  # noqa: BLE001 - provider failures share retry handling
                failure = f"{type(exc).__name__}: {exc}"
            if attempt < max_retries:
                sleep(retry_backoff_seconds * (2**attempt))
        else:
            failures[ticker] = failure
        if index + 1 < len(ticker_dates):
            sleep(request_interval_seconds)

    # Delisted (TOB/MBO) names stop returning prices; tolerate a few so one delisting
    # cannot block every later report, but fail closed on a provider-wide outage.
    if len(failures) > len(ticker_dates) * MAX_PRICE_FAILURE_RATIO:
        raise RuntimeError(f"Forward price retrieval failed for {len(failures)} ticker(s)")
    if failures:
        print(json.dumps({"price_unavailable_ticker_count": len(failures), "price_basis": price_basis}))
    return histories


def _history_row_hashes(history: pd.DataFrame) -> dict[str, str]:
    """Hash scale-invariant OHLC ratios so later corporate actions are harmless."""
    columns = ("Open", "High", "Low", "Close")
    missing = [column for column in columns if column not in history]
    if missing:
        raise ValueError(f"price history is missing OHLC columns: {','.join(missing)}")
    index = pd.DatetimeIndex(pd.to_datetime(history.index, errors="coerce"))
    if index.isna().any():
        raise ValueError("price history contains an invalid date")
    if index.tz is not None:
        index = index.tz_localize(None)

    result: dict[str, str] = {}
    numeric = history[list(columns)].apply(pd.to_numeric, errors="coerce")
    for position, timestamp in enumerate(index):
        date_key = str(timestamp.date())
        if date_key in result:
            raise ValueError(f"price history contains duplicate date: {date_key}")
        row = numeric.iloc[position]
        candidates = ([numeric.iloc[position - 1]["Close"]] if position else []) + list(row)
        scale = next(
            (
                float(value)
                for value in candidates
                if pd.notna(value) and math.isfinite(float(value)) and float(value) > 0
            ),
            1.0,
        )
        values: list[str] = []
        for value in row:
            number = float(value)
            if math.isinf(number):
                raise ValueError("price history contains an infinite OHLC value")
            values.append("null" if math.isnan(number) else f"{number / scale:.9f}")
        result[date_key] = hashlib.sha256("|".join(values).encode("ascii")).hexdigest()
    return result


def _price_hashes(
    histories_by_basis: dict[str, dict[str, pd.DataFrame]],
) -> dict[str, dict[str, dict[str, str]]]:
    result: dict[str, dict[str, dict[str, str]]] = {}
    for basis, histories in histories_by_basis.items():
        for ticker, history in histories.items():
            result.setdefault(ticker, {})[basis] = _history_row_hashes(history)
    return result


def _changed_price_rows(
    previous: dict[str, Any],
    current: dict[str, dict[str, dict[str, str]]],
) -> list[dict[str, str]]:
    old_hashes = previous.get("hashes", {})
    if not isinstance(old_hashes, dict):
        raise TypeError("price hash payload has invalid hashes")
    changed: list[dict[str, str]] = []
    for ticker, bases in current.items():
        old_bases = old_hashes.get(ticker, {})
        if not isinstance(old_bases, dict):
            continue
        for basis, rows in bases.items():
            old_rows = old_bases.get(basis, {})
            if not isinstance(old_rows, dict):
                continue
            for date_key in sorted(rows.keys() & old_rows.keys()):
                if rows[date_key] != old_rows[date_key]:
                    changed.append({"ticker": ticker, "price_basis": basis, "date": date_key})
    return changed


def _persist_price_hashes(
    path: Path,
    hashes: dict[str, dict[str, dict[str, str]]],
    secret: str,
) -> list[dict[str, str]]:
    previous = decrypt_json(path.read_text(encoding="utf-8"), secret) if path.exists() else {}
    changed = _changed_price_rows(previous, hashes)
    for basis, count in sorted(Counter(row["price_basis"] for row in changed).items()):
        print(json.dumps({"price_basis": basis, "changed_count": count}))
    payload: dict[str, Any] = {
        "schema_version": PRICE_HASH_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "hashes": hashes,
        "revisions": changed,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encrypt_json(payload, secret), encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Forward-validate encrypted immutable JP inflection snapshots.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--snapshot-dir", default="dashboard/data/inflection/v3")
    parser.add_argument("--output", default="artifacts/inflection_forward_validation.json")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    snapshot_dir = repo_root / args.snapshot_dir
    encrypted_snapshots = list(snapshot_dir.glob("????-??-??.enc")) if snapshot_dir.exists() else []
    if not encrypted_snapshots:
        print("No encrypted immutable EARLY_CANDIDATE snapshots available yet; nothing to validate.")
        return 0

    encryption_secret = snapshot_encryption_secret()
    all_observations = load_inflection_signals(
        snapshot_dir,
        encryption_secret=encryption_secret,
        classifications=("EARLY_CANDIDATE", "WATCH", "NONE", "OVEREXTENDED"),
    )
    if not all_observations:
        print("Encrypted snapshots exist but contain no tracked inflection observations yet.")
        return 0

    histories = _fetch_adjusted_histories(all_observations, max_horizon=252)
    split_histories = _fetch_adjusted_histories(
        all_observations,
        max_horizon=252,
        price_basis=SPLIT_ONLY,
    )
    benchmark_rows = [
        {"ticker": BENCHMARK_TICKER, "date": signal["signal_date"]}
        for signal in all_observations
    ]
    benchmark_history = _fetch_adjusted_histories(
        benchmark_rows,
        max_horizon=252,
        extra_lookback_days=35,
    )[BENCHMARK_TICKER]
    price_hashes = _price_hashes(
        {
            TOTAL_RETURN_ADJUSTED: {**histories, BENCHMARK_TICKER: benchmark_history},
            SPLIT_ONLY: split_histories,
        }
    )
    _persist_price_hashes(
        repo_root / "dashboard/data/inflection_forward_price_hashes.enc",
        price_hashes,
        encryption_secret,
    )

    recall = compute_tracked_pool_explosion_recall(all_observations, histories)
    observed_tickers = {str(row["ticker"]) for row in all_observations}
    report: dict[str, object] = {
        "signal_count": len(all_observations),
        "price_unavailable_ticker_count": len(
            observed_tickers - (set(histories) & set(split_histories))
        ),
        "strategy_version": all_observations[0]["strategy_version"],
        "report_schema_version": all_observations[0]["report_schema_version"],
        "evaluation_unit": "independent_daily_signal_observation",
        "portfolio_interpretation": True,
        "portfolio_interpretation_note": (
            "portfolio_summary simulates EARLY_CANDIDATE signals only, with a 60-session holding "
            "period and base transaction cost. Other horizon/exit combinations remain trade-level "
            "evaluations. Same-day close proceeds are not reused for open entries. Sector limits are "
            "not modeled; market exposure is diagnostic only. CAGR and drawdown are not meaningful "
            "until sufficient snapshots accumulate. Open positions are valued with hypothetical "
            "liquidation cost, and missing closes are forward-filled without a day limit. Initial "
            "capital, maximum positions, and allocation are unconfirmed defaults; see config."
        ),
        "entry_rule": "next_trading_day_open",
        "price_adjustment": {
            "horizons": TOTAL_RETURN_ADJUSTED,
            "exit_strategies": SPLIT_ONLY,
        },
        "round_trip_cost_pct": ROUND_TRIP_COST_PCT,
        "execution_cost_scenarios_pct": {
            "base": ROUND_TRIP_COST_PCT,
            "stress": STRESS_ROUND_TRIP_COST_PCT,
            "benchmark": BENCHMARK_ROUND_TRIP_COST_PCT,
        },
        "execution_limitations": [
            "order_book_depth_not_modeled",
            "trading_halts_not_modeled",
            "price_limit_fill_probability_not_modeled",
            "position_capacity_not_modeled",
            "lot_size_not_modeled",
        ],
        "same_ticker_overlap_policy": "one_open_position_per_ticker",
        "benchmark": {
            "ticker": BENCHMARK_TICKER,
            "name": "NEXT FUNDS TOPIX ETF",
            "entry_rule": "same next-trading-day open",
            "cost_rule": (
                f"fixed {BENCHMARK_ROUND_TRIP_COST_PCT}% round-trip regardless of base/stress scenario"
            ),
        },
        "jquants_delay_note": (
            "Free-tier delayed fundamentals are evaluated exactly as observed in each encrypted immutable snapshot."
        ),
        "regime_definition": (
            "TOPIX 20-session return through signal date; zero is up; insufficient history is unknown"
        ),
        "multiple_comparisons_caveat": (
            "Many group, horizon, and stop combinations are reported; do not over-interpret the best result."
        ),
        "tracked_pool_explosion_recall": recall,
        "groups": {},
    }
    groups: dict[str, object] = {}
    for classification in ("EARLY_CANDIDATE", "WATCH", "NONE"):
        signals = [
            observation
            for observation in all_observations
            if observation["classification"] == classification
        ]
        groups[classification.lower()] = _build_group_report(
            signals,
            histories,
            split_histories,
            benchmark_history,
            [str(signal["signal_date"]) for signal in signals],
        )
    report["groups"] = groups
    portfolio_signals = [
        observation
        for observation in all_observations
        if observation["classification"] == "EARLY_CANDIDATE"
    ]
    portfolio_trades = simulate_signals(
        portfolio_signals,
        histories,
        holding_days=60,
        round_trip_cost_pct=ROUND_TRIP_COST_PCT,
        apply_tax=False,
    )
    report["portfolio_summary"] = simulate_portfolio(
        portfolio_signals,
        portfolio_trades,
        histories,
        pd.DatetimeIndex(benchmark_history.index),
        initial_capital_jpy=PORTFOLIO_INITIAL_CAPITAL_JPY,
        max_positions=PORTFOLIO_MAX_POSITIONS,
        position_size_pct=PORTFOLIO_POSITION_SIZE_PCT,
        round_trip_cost_pct=ROUND_TRIP_COST_PCT,
    )

    output = repo_root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_output = output.with_name(f"{output.stem}_summary.json")
    summary_output.write_text(
        json.dumps(_summary_only(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "signal_count": len(all_observations),
                "output": str(output),
                "summary_output": str(summary_output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
