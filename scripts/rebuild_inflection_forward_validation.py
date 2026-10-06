from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.forward_prices import (
    DEFAULT_CACHE_RELATIVE_PATH,
    fetch_price_histories,
    legacy_hash_window,
    shared_price_window,
    snapshot_dates,
)
from src.data.session_gaps import latest_settled_session, session_coverage
from src.data.snapshot_crypto import decrypt_json, encrypt_json, snapshot_encryption_secret
from src.evaluation.explosion import explosion_definitions
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

TOTAL_RETURN_ADJUSTED = "total_return_adjusted"
SPLIT_ONLY = "split_only"
PRICE_HASH_SCHEMA_VERSION = 1


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


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _snapshot_session_coverage(snapshot_dir: Path) -> dict[str, Any]:
    """Which trading sessions have no snapshot, up to the newest session that should have one by now.

    The end is the clock's latest settled session, not the last snapshot: otherwise a run of failed
    scans after the last good snapshot would not even count as expected sessions.
    """
    dates = snapshot_dates([snapshot_dir])
    through = latest_settled_session(_utc_now())
    if dates:
        through = max(through, dates[-1])
    return session_coverage(snapshot_dir, through)


def _legacy_hash_starts(rows: list[dict[str, Any]]) -> dict[str, date]:
    """Where each ticker's price history used to start (earliest signal - 10 days; the benchmark - 45).

    Hashes are computed from this window only so that fetching more history for volatility does
    not change them (see ``legacy_hash_window``).
    """
    earliest: dict[str, date] = {}
    for row in rows:
        signal = date.fromisoformat(str(row["date"]))
        ticker = str(row["ticker"])
        earliest[ticker] = min(signal, earliest.get(ticker, signal))
    starts = {ticker: day - timedelta(days=10) for ticker, day in earliest.items()}
    starts[BENCHMARK_TICKER] = min(earliest.values()) - timedelta(days=10 + 35)
    return starts


def main() -> int:
    parser = argparse.ArgumentParser(description="Forward-validate encrypted immutable JP inflection snapshots.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--snapshot-dir", default="dashboard/data/inflection/v3")
    parser.add_argument(
        "--legacy-snapshot-dir",
        default="dashboard/data/inflection",
        help="Only sizes the shared price window (legacy snapshots are not evaluated here).",
    )
    parser.add_argument("--output", default="artifacts/inflection_forward_validation.json")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    snapshot_dir = repo_root / args.snapshot_dir
    legacy_snapshot_dir = repo_root / args.legacy_snapshot_dir
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

    window = shared_price_window([snapshot_dir, legacy_snapshot_dir], datetime.now(UTC).date())
    if window is None:
        raise RuntimeError("no snapshot files to size the price window")
    observed = sorted({str(observation["ticker"]) for observation in all_observations})
    fetched = fetch_price_histories(
        [*observed, BENCHMARK_TICKER],
        *window,
        cache_path=repo_root / DEFAULT_CACHE_RELATIVE_PATH,
        required={BENCHMARK_TICKER},
    )
    total_return = fetched.total_return()
    benchmark_history = total_return.pop(BENCHMARK_TICKER)
    histories = total_return
    split_histories = {
        ticker: frame for ticker, frame in fetched.split_only().items() if ticker != BENCHMARK_TICKER
    }
    if fetched.unavailable:
        print(json.dumps({"price_unavailable_ticker_count": fetched.unavailable}))
    starts = _legacy_hash_starts(all_observations)
    price_hashes = _price_hashes(
        {
            TOTAL_RETURN_ADJUSTED: {
                **{ticker: legacy_hash_window(frame, starts[ticker]) for ticker, frame in histories.items()},
                BENCHMARK_TICKER: legacy_hash_window(benchmark_history, starts[BENCHMARK_TICKER]),
            },
            SPLIT_ONLY: {
                ticker: legacy_hash_window(frame, starts[ticker]) for ticker, frame in split_histories.items()
            },
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
        "session_coverage": _snapshot_session_coverage(snapshot_dir),
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
        "explosion_definitions": explosion_definitions(),
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
