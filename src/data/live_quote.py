"""Best-effort market data for the manual position exit monitor."""

from __future__ import annotations

import math
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd
import yfinance as yf

from src.data.market_calendar import TSE_CALENDAR
from src.data.provider_output import (
    ProviderFailure,
    ProviderFailureCategory,
    classify_provider_failure,
    suppress_provider_output,
)

JST = ZoneInfo("Asia/Tokyo")
# yfinance TSE 1m bars lag ~15 min (measured 2026-10-01); 20 leaves one bar of slack.
STALE_QUOTE_THRESHOLD_MINUTES_IN_SESSION = 20
STALE_QUOTE_THRESHOLD_MINUTES_OUTSIDE_SESSION = 60


@dataclass
class _SharedHistoryFrames:
    earliest_dates: dict[str, str] = field(default_factory=dict)
    frames: dict[str, pd.DataFrame | Exception] = field(default_factory=dict)


_SHARED_HISTORY_FRAMES: ContextVar[_SharedHistoryFrames | None] = ContextVar(
    "shared_history_frames", default=None,
)


@dataclass(frozen=True)
class TodayQuote:
    open: float
    high_so_far: float
    low_so_far: float
    last_price: float
    as_of_at: str
    source: str = "yfinance_1m_bar"


@dataclass(frozen=True)
class SplitAdjustedHistory:
    entry_price: float
    daily_highs: pd.Series
    daily_closes: pd.Series
    daily_bars: pd.DataFrame = field(default_factory=pd.DataFrame)


def _now_jst() -> datetime:
    return datetime.now(JST)


def _jst_index(index: pd.Index) -> pd.DatetimeIndex:
    converted = pd.DatetimeIndex(pd.to_datetime(index, errors="coerce"))
    if converted.isna().any():
        raise ValueError("price history contains an invalid timestamp")
    if converted.tz is None:
        return converted.tz_localize(JST)
    return converted.tz_convert(JST)


def _positive(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("price values must be finite and positive")
    return number


def _split_ratios(frame: pd.DataFrame) -> dict[date, float]:
    values = (
        pd.to_numeric(frame["Stock Splits"], errors="coerce")
        if "Stock Splits" in frame
        else pd.Series(0.0, index=frame.index)
    )
    if values.isna().any() or any(not math.isfinite(float(value)) or float(value) < 0 for value in values):
        raise ValueError("split ratios must be finite and non-negative")
    ratios: dict[date, float] = {}
    for timestamp, value in values.items():
        ratio = float(value)
        if ratio > 0:
            split_date = timestamp.date()
            ratios[split_date] = ratios.get(split_date, 1.0) * _positive(ratio)
    return ratios


def _later_split_factor(ratios: dict[date, float], value_date: date, as_of: date) -> float:
    factor = 1.0
    for split_date, ratio in ratios.items():
        if value_date < split_date <= as_of:
            factor *= ratio
    return _positive(factor)


@contextmanager
def shared_split_history_frames() -> Iterator[None]:
    """Share raw provider frames within one monitor run and discard them on exit."""
    token = _SHARED_HISTORY_FRAMES.set(_SharedHistoryFrames())
    try:
        yield
    finally:
        _SHARED_HISTORY_FRAMES.reset(token)


def configure_split_history_sharing(earliest_dates: dict[str, str]) -> None:
    shared = _SHARED_HISTORY_FRAMES.get()
    if shared is not None:
        shared.earliest_dates = dict(earliest_dates)


def _fetch_daily_history_frame(ticker: str, start: str) -> pd.DataFrame:
    try:
        with suppress_provider_output():
            return yf.Ticker(ticker).history(
                start=start, auto_adjust=False, actions=True, keepna=True, timeout=15,
            )
    except Exception as exc:  # noqa: BLE001 - retain causal type/status without exposing the provider body
        raise ProviderFailure("daily_history", exc) from None


def fetch_split_adjusted_history(
    ticker: str,
    entry_date: str,
    entry_price: float,
) -> SplitAdjustedHistory:
    """Return prior confirmed OHLC on the current split-only price scale."""
    purchase_date = date.fromisoformat(entry_date)
    current_date = _now_jst().date()
    adjusted_entry = _positive(entry_price)
    shared = _SHARED_HISTORY_FRAMES.get()
    provider_start = shared.earliest_dates.get(ticker, entry_date) if shared is not None else entry_date
    if shared is not None and ticker in shared.earliest_dates:
        cached = shared.frames.get(ticker)
        if cached is None:
            try:
                cached = _fetch_daily_history_frame(ticker, provider_start)
            except ProviderFailure as exc:
                cached = exc
            shared.frames[ticker] = cached
        if isinstance(cached, Exception):
            raise cached
        history = cached
    else:
        history = _fetch_daily_history_frame(ticker, provider_start)
    if history.empty:
        if purchase_date < current_date:
            raise ValueError("daily history is missing for an existing position")
        return SplitAdjustedHistory(
            adjusted_entry,
            pd.Series(dtype=float),
            pd.Series(dtype=float),
        )

    if not {"High", "Close"}.issubset(history.columns):
        raise ValueError("daily history is missing High or Close")
    # Yahoo already returns auto_adjust=False OHLC split-adjusted as of fetch time;
    # only the user's raw entry price needs the later split ratios.
    frame = history.copy()
    frame.index = _jst_index(frame.index)
    if provider_start != entry_date:
        frame = frame.loc[frame.index.date >= purchase_date].copy()
        if frame.empty:
            if purchase_date < current_date:
                raise ValueError("daily history is missing for an existing position")
            return SplitAdjustedHistory(
                adjusted_entry,
                pd.Series(dtype=float),
                pd.Series(dtype=float),
            )
    if pd.Index(frame.index.date).has_duplicates:
        raise ValueError("daily history contains duplicate dates")
    row_dates = pd.Series(frame.index.date, index=frame.index)
    adjusted_entry /= _later_split_factor(_split_ratios(frame), purchase_date, current_date)
    prior_mask = (row_dates > purchase_date) & (row_dates < current_date)
    prior = frame.loc[prior_mask]
    calendar = xcals.get_calendar(TSE_CALENDAR)
    expected_dates = {
        timestamp.date()
        for timestamp in calendar.sessions_in_range(purchase_date.isoformat(), current_date.isoformat())
        if purchase_date < timestamp.date() < current_date
    }
    actual_dates = set(prior.index.date)
    if actual_dates != expected_dates:
        raise ValueError("prior confirmed daily history is missing")
    if {"Open", "High", "Low", "Close", "Volume"}.issubset(prior.columns):
        # A confirmed zero-trade day is not a missing trading session.
        unquoted = prior[["Open", "High", "Low", "Close"]].isna().all(axis=1) & (prior["Volume"] == 0)
        prior = prior.loc[~unquoted]

    return SplitAdjustedHistory(
        entry_price=adjusted_entry,
        daily_highs=pd.Series([_positive(value) for value in prior["High"]], index=prior.index),
        daily_closes=pd.Series([_positive(value) for value in prior["Close"]], index=prior.index),
        daily_bars=frame,
    )


def fetch_today_bars(ticker: str, *, diagnostics: dict[str, int] | None = None) -> pd.DataFrame | None:
    """Return today's timestamped one-minute bars in JST."""
    try:
        with suppress_provider_output():
            frame = yf.Ticker(ticker).history(
                period="1d", interval="1m", auto_adjust=False, actions=False, prepost=False, timeout=15,
            )
        if frame.empty or not {"Open", "High", "Low", "Close"}.issubset(frame.columns):
            return None
        if pd.DatetimeIndex(frame.index).tz is None:
            return None
        frame = frame.copy()
        frame.index = _jst_index(frame.index)
        frame = frame.sort_index()
        now = _now_jst()
        today = frame.loc[[timestamp.date() == now.date() for timestamp in frame.index]]
        if today.empty or today.index[-1] > now:
            return None
        today.attrs["requested_date"] = now.date().isoformat()
        return today
    except Exception as exc:
        category = classify_provider_failure(exc)
        if category == ProviderFailureCategory.UNEXPECTED:
            raise
        if diagnostics is not None:
            diagnostics[category] = diagnostics.get(category, 0) + 1
        return None


def fetch_session_bars(
    ticker: str, session_date: str, *, diagnostics: dict[str, int] | None = None
) -> pd.DataFrame | None:
    """Retrieve a pending session, including its closing auction, without caching failures."""
    session = date.fromisoformat(session_date)
    try:
        with suppress_provider_output():
            frame = yf.Ticker(ticker).history(
                start=session.isoformat(), end=(session + timedelta(days=1)).isoformat(),
                interval="1m", auto_adjust=False, actions=False, prepost=False, timeout=15,
            )
        if frame.empty or not {"Open", "High", "Low", "Close"}.issubset(frame.columns):
            return None
        if pd.DatetimeIndex(frame.index).tz is None:
            return None
        frame = frame.copy()
        frame.index = _jst_index(frame.index)
        result = frame.loc[frame.index.date == session].sort_index()
        result.attrs["requested_date"] = session.isoformat()
        return result
    except Exception as exc:
        category = classify_provider_failure(exc)
        if category == ProviderFailureCategory.UNEXPECTED:
            raise
        if diagnostics is not None:
            diagnostics[category] = diagnostics.get(category, 0) + 1
        return None


def build_today_quote(bars: pd.DataFrame, *, diagnostics: dict[str, int] | None = None) -> TodayQuote | None:
    """Build a coherent aggregate quote from one-minute bars."""
    try:
        if bars.empty or not {"Open", "High", "Low", "Close"}.issubset(bars.columns):
            return None
        frame = bars.sort_index()
        if pd.DatetimeIndex(frame.index).tz is None:
            return None
        opening = _positive(frame["Open"].iloc[0])
        high = _positive(pd.to_numeric(frame["High"], errors="coerce").max())
        low = _positive(pd.to_numeric(frame["Low"], errors="coerce").min())
        last = _positive(frame["Close"].iloc[-1])
        if not low <= min(opening, last) <= max(opening, last) <= high:
            return None
        return TodayQuote(opening, high, low, last, frame.index[-1].isoformat())
    except (ValueError, KeyError, IndexError):
        if diagnostics is not None:
            diagnostics[ProviderFailureCategory.INVALID_OHLCV] = (
                diagnostics.get(ProviderFailureCategory.INVALID_OHLCV, 0) + 1
            )
        return None


def fetch_today_quote(ticker: str) -> TodayQuote | None:
    """Build a coherent quote from timestamped one-minute bars."""
    bars = fetch_today_bars(ticker)
    return None if bars is None else build_today_quote(bars)
