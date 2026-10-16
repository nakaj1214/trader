"""One batched price fetch shared by forward validation and self-learning.

Raw OHLC plus corporate actions are downloaded once, in batches, and both price bases are
derived from them instead of being fetched separately:

* split-only: Yahoo's ``auto_adjust=False`` OHLC as returned (already split-adjusted),
* total-return: yfinance's own ``auto_adjust`` applied to the same raw frames.

A pickle cache under ``artifacts/`` lets the second consumer in the same CI job skip tickers the first
already fetched. The cache is an optimisation only: an unreadable file is ignored.
"""

from __future__ import annotations

import pickle
import re
import time
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
from yfinance.utils import auto_adjust

from src.data.atomic_write import atomic_write_bytes
from src.data.jquants_history import tse_sessions
from src.data.provider_output import ProviderFailureCategory, classify_provider_failure, suppress_provider_output
from src.data.validation import validate_ohlcv
from src.data.yfinance_prices import _drop_unquoted_bars, _extract_ticker_frame

BATCH_SIZE = 50
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 2.0
BATCH_INTERVAL_SECONDS = 0.5
MAX_FAILURE_RATIO = 0.05  # tolerate delistings; a provider outage still fails closed
DEFAULT_CACHE_RELATIVE_PATH = "artifacts/price_cache.pkl"  # gitignored; shared within one CI job
# The regime needs 273 prior benchmark closes (252 + 20 + 1). 420 calendar days left only 3 sessions of slack in
# the worst week of 2025-26, so 460 (worst case 303 sessions) is used; it also covers 60 sessions for volatility.
PRIOR_HISTORY_DAYS = 460
REQUIRED_COLUMNS = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
_SNAPSHOT_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.enc$")


def snapshot_dates(snapshot_dirs: Iterable[Path]) -> list[date]:
    """Dates taken from ``YYYY-MM-DD.enc`` file names (nothing is decrypted); missing dirs are ignored."""
    dates: list[date] = []
    for directory in snapshot_dirs:
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            match = _SNAPSHOT_NAME.match(path.name)
            if match:
                try:
                    dates.append(date.fromisoformat(match.group(1)))
                except ValueError:
                    continue
    return sorted(dates)


def shared_price_window(snapshot_dirs: Iterable[Path], today: date) -> tuple[date, date] | None:
    """The one fetch window both consumers use: earliest snapshot - 100 days .. tomorrow.

    ``snapshot_dirs`` must be the directories the caller actually reads (CLI-resolved), so a
    non-default input still gets its full prior history. ``None`` when there is no snapshot.
    """
    dates = snapshot_dates(snapshot_dirs)
    if not dates:
        return None
    return dates[0] - timedelta(days=PRIOR_HISTORY_DAYS), today + timedelta(days=1)


def legacy_hash_window(frame: pd.DataFrame, start: date) -> pd.DataFrame:
    """Rows from ``start`` on.

    Price hashes normalise the first row of a frame by itself and every other row by the previous
    close, so extending the fetch window backwards would change old hashes and look like revisions.
    Hashing only the historic window keeps them comparable.
    """
    index = pd.DatetimeIndex(frame.index)
    if index.tz is not None:
        index = index.tz_localize(None)
    return frame.loc[index >= pd.Timestamp(start)]


@dataclass
class PriceHistories:
    raw: dict[str, pd.DataFrame]
    start: date
    end: date
    unavailable: int = 0
    failures: dict[str, int] = field(default_factory=dict)

    def split_only(self) -> dict[str, pd.DataFrame]:
        """Yahoo's OHLC with ``auto_adjust=False`` (already split-adjusted), as fetched."""
        return dict(self.raw)

    def total_return(self) -> dict[str, pd.DataFrame]:
        """OHLC scaled by Adj Close / Close, using yfinance's own implementation."""
        result = {}
        for ticker, frame in self.raw.items():
            if validate_ohlcv(frame, require_volume=False):
                raise ValueError("Invalid adjusted price history")
            adjusted = auto_adjust(frame)
            if validate_ohlcv(adjusted, require_volume=False):
                raise ValueError("Invalid adjusted price history")
            result[ticker] = adjusted
        return result


def _valid_history_frame(frame: Any) -> bool:
    return (isinstance(frame, pd.DataFrame) and REQUIRED_COLUMNS.issubset(frame.columns)
            and not validate_ohlcv(frame) and not validate_ohlcv(auto_adjust(frame)))


def _price_window(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    dates = pd.DatetimeIndex(frame.index).tz_localize(None).normalize()
    return frame.loc[(dates >= pd.Timestamp(start)) & (dates < pd.Timestamp(end))].copy()


def _covers_sessions(frame: pd.DataFrame, sessions: pd.DatetimeIndex) -> bool:
    dates = pd.DatetimeIndex(frame.index).tz_localize(None).normalize()
    return bool(sessions.isin(dates).all())


def _load_cache(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    try:
        loaded = pickle.loads(path.read_bytes())
        entries = loaded["entries"]
        return entries if isinstance(entries, dict) else {}
    except Exception:  # noqa: BLE001 - any unreadable cache just means a full fetch
        return {}


def _save_cache(path: Path | None, entries: dict[str, dict[str, Any]]) -> None:
    if path is None:
        return
    atomic_write_bytes(path, pickle.dumps({"entries": entries}))  # also creates the parent directory


def _download_batch(
    tickers: list[str], start: date, end: date, diagnostics: dict[str, int] | None = None
) -> pd.DataFrame:
    try:
        with suppress_provider_output():
            return yf.download(
                " ".join(tickers),
                start=start.isoformat(),
                end=end.isoformat(),
                group_by="ticker",
                progress=False,
                auto_adjust=False,
                actions=True,
                threads=True,
                timeout=15,
            )
    except Exception as exc:
        category = classify_provider_failure(exc)
        if category == ProviderFailureCategory.UNEXPECTED:
            raise
        if diagnostics is not None:
            diagnostics[category] = diagnostics.get(category, 0) + 1
        return pd.DataFrame()


def _failure_summary(failures: dict[str, int]) -> str:
    """`` (timeout=2, empty=1)``: safe category names and counts only; empty when nothing was counted."""
    if not failures:
        return ""
    return " (" + ", ".join(f"{category}={count}" for category, count in sorted(failures.items())) + ")"


def fetch_price_histories(
    tickers: Iterable[str],
    start: date,
    end: date,
    *,
    cache_path: Path | None = None,
    required: Collection[str] = (),
    batch_size: int = BATCH_SIZE,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
    batch_interval_seconds: float = BATCH_INTERVAL_SECONDS,
    max_failure_ratio: float = MAX_FAILURE_RATIO,
    sleep: Callable[[float], None] = time.sleep,
    diagnostics: dict[str, int] | None = None,
) -> PriceHistories:
    """Fetch raw OHLC + actions for ``tickers`` over ``[start, end)`` in bounded batches.

    Reuse a cache only when its actual valid sessions cover the requested window. Ordinary
    IPO/halting histories remain available, but incomplete windows are refetched next time.
    Required benchmarks must cover every TSE session; failed retrievals raise without naming tickers.
    """
    if batch_size < 1 or max_retries < 0 or retry_backoff_seconds < 0 or batch_interval_seconds < 0:
        raise ValueError("batch/retry timing parameters are invalid")
    if start >= end:
        raise ValueError("price window must have start before exclusive end")
    sessions = pd.DatetimeIndex(tse_sessions(start, end - timedelta(days=1)))
    wanted = sorted(set(tickers))
    failures = diagnostics if diagnostics is not None else {}
    entries = _load_cache(cache_path)
    raw: dict[str, pd.DataFrame] = {}
    for ticker in wanted:
        entry = entries.get(ticker)
        if (isinstance(entry, dict) and isinstance(entry.get("start"), date) and isinstance(entry.get("end"), date)
                and entry["start"] <= start and entry["end"] >= end and _valid_history_frame(entry.get("frame"))
                and _covers_sessions(entry["frame"], sessions)):
            raw[ticker] = _price_window(entry["frame"], start, end)

    to_fetch = [ticker for ticker in wanted if ticker not in raw]
    for offset in range(0, len(to_fetch), batch_size):
        pending = list(to_fetch[offset : offset + batch_size])
        for attempt in range(max_retries + 1):
            if not pending:
                break
            downloaded = _download_batch(pending, start, end, failures)
            if downloaded.empty:
                failures[ProviderFailureCategory.EMPTY] = failures.get(ProviderFailureCategory.EMPTY, 0) + 1
            found: dict[str, pd.DataFrame] = {}
            for ticker in pending:
                frame = _extract_ticker_frame(downloaded, ticker, len(pending))
                if not REQUIRED_COLUMNS.issubset(frame.columns):
                    continue
                frame = _drop_unquoted_bars(frame)
                if _valid_history_frame(frame):
                    frame = _price_window(frame, start, end)
                    if not frame.empty and (ticker not in required or _covers_sessions(frame, sessions)):
                        found[ticker] = frame
            raw.update(found)
            pending = [ticker for ticker in pending if ticker not in found]
            if pending and attempt < max_retries:
                sleep(retry_backoff_seconds * (2**attempt))
        if offset + batch_size < len(to_fetch):
            sleep(batch_interval_seconds)

    missing = [ticker for ticker in wanted if ticker not in raw]
    causes = _failure_summary(failures)
    if set(required) & set(missing):
        raise RuntimeError("Required price history is unavailable" + causes)
    if len(missing) > len(wanted) * max_failure_ratio:
        raise RuntimeError(f"Price retrieval failed for {len(missing)} ticker(s)" + causes)

    if to_fetch:
        for ticker in to_fetch:
            if ticker in raw:
                entries[ticker] = {"frame": raw[ticker], "start": start, "end": end}
        _save_cache(cache_path, entries)
    return PriceHistories(raw=raw, start=start, end=end, unavailable=len(missing), failures=dict(failures))
