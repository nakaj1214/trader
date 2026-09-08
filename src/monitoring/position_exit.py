"""Pure trailing-stop evaluation for manually held positions."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from src.data.live_quote import STALE_QUOTE_THRESHOLD_MINUTES, TodayQuote

# Keep the dashboard metric identical to the existing forward-validation metric.
from src.evaluation.inflection_backtest import _true_max_drawdown_pct

JST = ZoneInfo("Asia/Tokyo")
DEFAULT_TRAILING_STOP_PCT = 15.0


class StaleQuoteError(ValueError):
    """Raised when a quote cannot safely represent the evaluation time."""


@dataclass(frozen=True)
class PositionStatus:
    ticker: str
    entry_date: str
    entry_price: float
    as_of_at: str
    quote_source: str
    current_price: float
    high_water_mark: float
    stop_price: float
    trailing_stop_pct: float
    unrealized_pct: float
    distance_to_stop_pct: float
    max_drawdown_pct: float | None
    triggered: bool
    exit_reason: str | None


def _positive(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def _prices(values: pd.Series, name: str) -> pd.Series:
    result = pd.to_numeric(values, errors="coerce")
    if result.isna().any() or any(not math.isfinite(float(value)) or float(value) <= 0 for value in result):
        raise ValueError(f"{name} must contain only finite positive prices")
    result = result.astype(float).copy()
    result.index = pd.to_datetime(result.index, errors="coerce")
    if result.index.isna().any():
        raise ValueError(f"{name} contains an invalid timestamp")
    return result.sort_index()


def evaluate_position(
    entry_price: float,
    entry_date: str,
    prior_confirmed_highs: pd.Series,
    prior_confirmed_closes: pd.Series,
    today_quote: TodayQuote,
    trailing_stop_pct: float,
    evaluated_at: datetime,
    ticker: str,
) -> PositionStatus:
    """Evaluate one position using the backtest's prior-HWM stop ordering."""
    purchase_date = date.fromisoformat(entry_date)
    adjusted_entry = _positive(entry_price, "entry_price")
    stop_pct = _positive(trailing_stop_pct, "trailing_stop_pct")
    if stop_pct >= 100:
        raise ValueError("trailing_stop_pct must be between 0 and 100")
    if evaluated_at.tzinfo is None:
        raise ValueError("evaluated_at must include a timezone")
    evaluated_at = evaluated_at.astimezone(JST)
    if purchase_date > evaluated_at.date():
        raise ValueError("entry_date must not be in the future")

    try:
        quote_at = datetime.fromisoformat(today_quote.as_of_at)
    except ValueError as exc:
        raise StaleQuoteError("quote timestamp is invalid") from exc
    if quote_at.tzinfo is None:
        raise StaleQuoteError("quote timestamp must include a timezone")
    quote_at = quote_at.astimezone(JST)
    age = evaluated_at - quote_at
    if age < timedelta(0):
        raise StaleQuoteError("quote timestamp is in the future")
    if age > timedelta(minutes=STALE_QUOTE_THRESHOLD_MINUTES):
        raise StaleQuoteError("quote is stale")

    opening = _positive(today_quote.open, "quote open")
    high = _positive(today_quote.high_so_far, "quote high")
    low = _positive(today_quote.low_so_far, "quote low")
    last = _positive(today_quote.last_price, "quote last")
    if not low <= min(opening, last) <= max(opening, last) <= high:
        raise ValueError("quote OHLC values are inconsistent")

    highs = _prices(prior_confirmed_highs, "prior_confirmed_highs")
    closes = _prices(prior_confirmed_closes, "prior_confirmed_closes")
    if any(timestamp.date() >= quote_at.date() for timestamp in highs.index.union(closes.index)):
        raise ValueError("prior history must not include the current quote date")
    high_water = adjusted_entry if highs.empty else max(adjusted_entry, float(highs.max()))
    stop_price = high_water * (1.0 - stop_pct / 100.0)
    if opening <= stop_price:
        triggered, exit_reason = True, "trailing_gap"
    elif low <= stop_price:
        triggered, exit_reason = True, "trailing_stop"
    else:
        triggered, exit_reason = False, None

    realized_closes = pd.concat([closes, pd.Series([last], index=[pd.Timestamp(quote_at)], dtype=float)])
    drawdown = _true_max_drawdown_pct(adjusted_entry, realized_closes)
    return PositionStatus(
        ticker=ticker,
        entry_date=entry_date,
        entry_price=round(adjusted_entry, 6),
        as_of_at=quote_at.isoformat(),
        quote_source=today_quote.source,
        current_price=round(last, 6),
        high_water_mark=round(high_water, 6),
        stop_price=round(stop_price, 6),
        trailing_stop_pct=round(stop_pct, 6),
        unrealized_pct=round((last / adjusted_entry - 1.0) * 100.0, 6),
        distance_to_stop_pct=round((last / stop_price - 1.0) * 100.0, 6),
        max_drawdown_pct=round(drawdown, 6) if drawdown is not None else None,
        triggered=triggered,
        exit_reason=exit_reason,
    )
