"""Build the encrypted dashboard bundle from the stored snapshots (run by the daily scan after it saves one).

    export SNAPSHOT_ENCRYPTION_KEY=...   # reads the encrypted daily snapshots
    export DASHBOARD_PASSWORD=...        # the viewer password typed into the dashboard (12+ characters)
    python scripts/build_dashboard.py

Without DASHBOARD_PASSWORD the build is skipped (exit 0). The log carries counts only: the repository is public,
so no ticker or company name is printed, and a failure reports only its error type.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.dashboard.bundle import (
    CHART_SESSIONS,
    HISTORY_SNAPSHOTS,
    MIN_PASSWORD_LENGTH,
    build_bundle,
    chart_tickers,
    encrypt_bundle,
    load_snapshots,
    tickers_with_benchmark,
)
from src.data.atomic_write import atomic_write_text
from src.data.snapshot_crypto import snapshot_encryption_secret
from src.data.yfinance_prices import fetch_price_data

SNAPSHOT_DIR = REPO_ROOT / "dashboard" / "data" / "inflection" / "v3"
OUTPUT = REPO_ROOT / "dashboard" / "data" / "dashboard.enc"
# Enough calendar history for the oldest stored signal's results plus the chart window (fetch_price_data pads it).
LOOKBACK_SESSIONS = HISTORY_SNAPSHOTS + CHART_SESSIONS + 20
JST = ZoneInfo("Asia/Tokyo")

PriceFetcher = Callable[[list[str]], dict[str, pd.DataFrame]]


def _fetch(tickers: list[str]) -> dict[str, pd.DataFrame]:
    return fetch_price_data(tickers, LOOKBACK_SESSIONS)


def build(
    *, snapshot_dir: Path, output: Path, secret: str, password: str, fetch: PriceFetcher = _fetch,
    now: datetime | None = None,
) -> dict[str, int]:
    reports, skipped = load_snapshots(snapshot_dir, secret)
    if not reports:
        raise ValueError("no readable snapshot")
    tickers = chart_tickers(reports)
    prices = fetch(tickers_with_benchmark(tickers))
    generated_at = (now or datetime.now(JST)).isoformat(timespec="seconds")
    bundle = build_bundle(reports, prices, generated_at=generated_at, skipped_snapshots=skipped)
    atomic_write_text(output, encrypt_bundle(bundle, password))
    return {
        "days": len(reports),
        "skipped": skipped,
        "tickers": len(tickers),
        "missing_prices": int(bundle["diagnostics"]["missing_prices"]),
    }


def main(argv: list[str] | None = None, *, fetch: PriceFetcher = _fetch) -> int:
    parser = argparse.ArgumentParser(description="Build the encrypted dashboard bundle.")
    parser.add_argument("--snapshot-dir", type=Path, default=SNAPSHOT_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)

    password = os.getenv("DASHBOARD_PASSWORD", "")
    if not password:
        print("::warning title=Dashboard not updated::DASHBOARD_PASSWORD is not set")
        return 0
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"::error title=Dashboard build failed::DASHBOARD_PASSWORD needs {MIN_PASSWORD_LENGTH}+ characters")
        return 1
    try:
        counts = build(
            snapshot_dir=args.snapshot_dir, output=args.output, secret=snapshot_encryption_secret(),
            password=password, fetch=fetch,
        )
    except Exception as exc:  # noqa: BLE001 - print the type only: a message could name a ticker
        print(f"::error title=Dashboard build failed::{type(exc).__name__}")
        return 1
    print("dashboard=written " + " ".join(f"{key}={value}" for key, value in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
