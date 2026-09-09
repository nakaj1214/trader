"""Best-effort market data for the manual position exit monitor."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

JST = ZoneInfo("Asia/Tokyo")
STALE_QUOTE_THRESHOLD_MINUTES = 60


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
    if values.isna().any() or any(
        not math.isfinite(float(value)) or float(value) < 0 for value in values
    ):
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


def split_adjust_ohlc(history: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """Put raw OHLC rows on one split-only price scale as of the given date."""
    frame = history.copy()
    frame.index = _jst_index(frame.index)
    ratios = _split_ratios(frame)
    for column in ("Open", "High", "Low", "Close"):
        if column not in frame:
            continue
        frame[column] = [
            float(value) / _later_split_factor(ratios, timestamp.date(), as_of)
            if pd.notna(value)
            else float("nan")
            for timestamp, value in pd.to_numeric(frame[column], errors="coerce").items()
        ]
    return frame


def fetch_split_adjusted_history(
    ticker: str,
    entry_date: str,
    entry_price: float,
) -> SplitAdjustedHistory:
    """Return prior confirmed OHLC on the current split-only price scale."""
    purchase_date = date.fromisoformat(entry_date)
    current_date = _now_jst().date()
    adjusted_entry = _positive(entry_price)
    history = yf.Ticker(ticker).history(
        start=entry_date,
        auto_adjust=False,
        actions=True,
        timeout=15,
    )
    if history.empty:
        if purchase_date < current_date:
            raise ValueError("daily history is missing for an existing position")
        return SplitAdjustedHistory(
            adjusted_entry,
            pd.Series(dtype=float),
            pd.Series(dtype=float),
        )

    frame = split_adjust_ohlc(history, current_date)
    row_dates = pd.Series(frame.index.date, index=frame.index)
    adjusted_entry /= _later_split_factor(_split_ratios(frame), purchase_date, current_date)
    prior_mask = row_dates < current_date
    prior = frame.loc[prior_mask]
    if prior.empty:
        if purchase_date < current_date:
            raise ValueError("prior confirmed daily history is missing")
        return SplitAdjustedHistory(
            adjusted_entry,
            pd.Series(dtype=float),
            pd.Series(dtype=float),
        )
    if not {"High", "Close"}.issubset(prior.columns):
        raise ValueError("daily history is missing High or Close")

    return SplitAdjustedHistory(
        entry_price=adjusted_entry,
        daily_highs=pd.Series([_positive(value) for value in prior["High"]], index=prior.index),
        daily_closes=pd.Series([_positive(value) for value in prior["Close"]], index=prior.index),
    )


def fetch_today_quote(ticker: str) -> TodayQuote | None:
    """Build a coherent quote from timestamped one-minute bars."""
    try:
        frame = yf.Ticker(ticker).history(
            period="1d",
            interval="1m",
            auto_adjust=False,
            actions=False,
            prepost=False,
            timeout=15,
        )
        if frame.empty or not {"Open", "High", "Low", "Close"}.issubset(frame.columns):
            return None
        if pd.DatetimeIndex(frame.index).tz is None:
            return None
        frame = frame.copy()
        frame.index = _jst_index(frame.index)
        now = _now_jst()
        today = frame.loc[[timestamp.date() == now.date() for timestamp in frame.index]]
        if today.empty or today.index[-1] > now:
            return None
        opening = _positive(today["Open"].iloc[0])
        high = _positive(pd.to_numeric(today["High"], errors="coerce").max())
        low = _positive(pd.to_numeric(today["Low"], errors="coerce").min())
        last = _positive(today["Close"].iloc[-1])
        if not low <= min(opening, last) <= max(opening, last) <= high:
            return None
        return TodayQuote(opening, high, low, last, today.index[-1].isoformat())
    except Exception:  # noqa: BLE001 - provider and malformed response failures are equivalent here
        return None
