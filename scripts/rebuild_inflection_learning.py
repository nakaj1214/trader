from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.snapshot_crypto import snapshot_encryption_secret
from src.evaluation.inflection_forward import BENCHMARK_TICKER
from src.evaluation.inflection_learning import (
    LEARNING_HORIZONS,
    build_learning_report,
    load_learning_observations,
    public_learning_summary,
)

LEARNING_PRICE_BATCH_SIZE = 50
LEARNING_PRICE_MAX_RETRIES = 2
LEARNING_PRICE_RETRY_BACKOFF_SECONDS = 2.0
LEARNING_PRICE_BATCH_INTERVAL_SECONDS = 0.5


def _extract_ticker_frame(raw: pd.DataFrame, ticker: str, batch_size: int) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    if not isinstance(raw.columns, pd.MultiIndex):
        return raw.copy() if batch_size == 1 else pd.DataFrame()
    for level in range(raw.columns.nlevels):
        if ticker in raw.columns.get_level_values(level):
            frame = raw.xs(ticker, axis=1, level=level, drop_level=True).copy()
            if isinstance(frame.columns, pd.MultiIndex) and frame.columns.nlevels == 1:
                frame.columns = frame.columns.get_level_values(0)
            return frame
    return pd.DataFrame()


def _fetch_learning_histories(
    rows: list[dict[str, Any]],
    *,
    max_horizon: int,
    batch_size: int = LEARNING_PRICE_BATCH_SIZE,
    max_retries: int = LEARNING_PRICE_MAX_RETRIES,
    retry_backoff_seconds: float = LEARNING_PRICE_RETRY_BACKOFF_SECONDS,
    batch_interval_seconds: float = LEARNING_PRICE_BATCH_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, pd.DataFrame]:
    """Fetch adjusted OHLC in bounded yfinance batches instead of ticker-by-ticker."""
    import yfinance as yf

    if (
        batch_size < 1
        or max_retries < 0
        or retry_backoff_seconds < 0
        or batch_interval_seconds < 0
    ):
        raise ValueError("batch/retry timing parameters are invalid")
    if not rows:
        return {}

    by_ticker: dict[str, list[pd.Timestamp]] = {}
    for row in rows:
        ticker = str(row["ticker"])
        by_ticker.setdefault(ticker, []).append(pd.Timestamp(str(row["date"])))

    all_dates = [date for dates in by_ticker.values() for date in dates]
    start = min(all_dates) - timedelta(days=10)
    requested_end = max(all_dates) + timedelta(days=max_horizon * 2 + 30)
    tomorrow = pd.Timestamp.today().normalize() + timedelta(days=1)
    end = min(requested_end, tomorrow)

    histories: dict[str, pd.DataFrame] = {}
    failures: dict[str, str] = {}
    required_columns = {"Open", "High", "Low", "Close"}
    tickers = sorted(by_ticker)

    for offset in range(0, len(tickers), batch_size):
        original_batch = tickers[offset : offset + batch_size]
        pending = list(original_batch)
        last_failure = "empty or missing adjusted OHLC"

        for attempt in range(max_retries + 1):
            if not pending:
                break
            try:
                raw = yf.download(
                    " ".join(pending),
                    start=start.strftime("%Y-%m-%d"),
                    end=end.strftime("%Y-%m-%d"),
                    group_by="ticker",
                    progress=False,
                    auto_adjust=True,
                    actions=False,
                    threads=True,
                    timeout=15,
                )
                last_failure = "empty or missing adjusted OHLC"
            except Exception as exc:  # noqa: BLE001 - provider failures share retry handling
                raw = pd.DataFrame()
                last_failure = f"{type(exc).__name__}: {exc}"

            found: dict[str, pd.DataFrame] = {}
            for ticker in pending:
                frame = _extract_ticker_frame(raw, ticker, len(pending))
                if frame.empty or not required_columns.issubset(frame.columns):
                    continue
                if frame["Close"].dropna().empty:
                    continue
                found[ticker] = frame.dropna(subset=["Close"])

            histories.update(found)
            pending = [ticker for ticker in pending if ticker not in found]
            if pending and attempt < max_retries:
                sleep(retry_backoff_seconds * (2**attempt))

        for ticker in pending:
            failures[ticker] = last_failure

        if offset + batch_size < len(tickers):
            sleep(batch_interval_seconds)

    if failures:
        detail = "; ".join(f"{ticker} ({reason})" for ticker, reason in failures.items())
        raise RuntimeError(f"Learning price retrieval failed: {detail}")
    return histories


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
    price_rows = [dict(observation) for observation in observations]
    price_rows.extend(
        {"ticker": BENCHMARK_TICKER, "date": observation["signal_date"]}
        for observation in observations
    )
    all_histories = _fetch_learning_histories(price_rows, max_horizon=max_horizon)
    benchmark_history = all_histories[BENCHMARK_TICKER]
    histories = {
        ticker: history
        for ticker, history in all_histories.items()
        if ticker != BENCHMARK_TICKER
    }

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
