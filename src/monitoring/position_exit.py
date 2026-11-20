"""Pure trailing-stop evaluation for manually held positions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

from src.data.live_quote import (
    STALE_QUOTE_THRESHOLD_MINUTES_IN_SESSION,
    STALE_QUOTE_THRESHOLD_MINUTES_OUTSIDE_SESSION,
    TodayQuote,
)
from src.data.market_calendar import TSE_CALENDAR

# Keep the dashboard metric identical to the existing forward-validation metric.
from src.evaluation.inflection_backtest import _true_max_drawdown_pct

JST = ZoneInfo("Asia/Tokyo")
DEFAULT_TRAILING_STOP_PCT = 15.0


class StaleQuoteError(ValueError):
    """Raised when a quote cannot safely represent the evaluation time."""


class IncompleteQuoteError(ValueError):
    """Raised when an unevaluated price interval cannot be confirmed."""


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
    return_20d_pct: float | None = None
    touch_at: str | None = None


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


def _return_20d_pct(closes: pd.Series, current_price: float) -> float | None:
    """The current quote is day 0, so the 20th preceding close is day -20."""
    if len(closes) < 20:
        return None
    return (current_price / float(closes.iloc[-20]) - 1.0) * 100.0


def _below(left: float, right: float) -> bool:
    return left < right and not math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-9)


def _minute_bars(
    values: pd.DataFrame, quote_at: datetime, evaluated_at: datetime,
) -> tuple[pd.DataFrame, dict[str, float]]:
    required = {"Open", "High", "Low", "Close"}
    if values.empty or not required.issubset(values.columns):
        raise ValueError("today_bars must contain OHLC rows")
    index = pd.DatetimeIndex(values.index)
    if index.tz is None:
        raise ValueError("today_bars timestamps must include a timezone")
    if index.has_duplicates:
        raise ValueError("today_bars timestamps must be unique")
    frame = values.loc[:, ["Open", "High", "Low", "Close"]].copy()
    frame.index = index.tz_convert(JST)
    if quote_at.date() != evaluated_at.date() or any(
        timestamp.date() != evaluated_at.date() for timestamp in frame.index
    ):
        raise ValueError("today_bars must be from the evaluation date")
    if any(timestamp > quote_at or timestamp > evaluated_at for timestamp in frame.index):
        raise ValueError("today_bars must not contain future rows")
    for column in required:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame.isna().any().any() or any(
        not math.isfinite(float(value)) or float(value) <= 0 for value in frame.to_numpy().ravel()
    ):
        raise ValueError("today_bars must contain only finite positive prices")
    if any(row.Low > min(row.Open, row.Close) or max(row.Open, row.Close) > row.High for row in frame.itertuples()):
        raise ValueError("today_bars OHLC values are inconsistent")
    frame = frame.sort_index()
    reference = values.attrs.get("daily_bar")
    if values.attrs.get("requested_date") != quote_at.date().isoformat() or not isinstance(reference, dict):
        raise IncompleteQuoteError("price path lacks full-session request or daily reference evidence")
    required_daily = required | {"Volume"}
    if not required_daily.issubset(reference) or "Volume" not in values:
        raise IncompleteQuoteError("price path lacks daily OHLC and volume evidence")
    try:
        daily = {key: float(reference[key]) for key in required_daily}
        volume = pd.to_numeric(values["Volume"], errors="coerce")
        if any(not math.isfinite(value) or value <= 0 for key, value in daily.items() if key != "Volume"):
            raise ValueError
        if daily["Volume"] < 0 or not math.isfinite(daily["Volume"]):
            raise ValueError
        if any(not math.isfinite(float(value)) or value < 0 for value in volume):
            raise ValueError
        if (_below(min(daily["Open"], daily["Close"], float(frame["Low"].min())), daily["Low"])
                or _below(daily["High"], max(daily["Open"], daily["Close"], float(frame["High"].max())))):
            raise IncompleteQuoteError("daily range does not contain the daily and minute prices")
        if daily["Volume"] == 0 and (volume.gt(0).any() or daily["High"] != daily["Low"]):
            raise IncompleteQuoteError("zero-volume daily bar contains trading activity")
        calendar = xcals.get_calendar(TSE_CALENDAR)
        session = quote_at.date().isoformat()
        opening, closing = calendar.session_open(session), calendar.session_close(session)
        morning_end, afternoon_start = calendar.session_break_start(session), calendar.session_break_end(session)
        for timestamp in frame.index:
            if not (opening <= timestamp <= morning_end or afternoon_start <= timestamp <= closing):
                raise IncompleteQuoteError("minute path contains rows outside TSE trading hours")
        for position, bar in enumerate(frame.itertuples()):
            if float(volume.loc[bar.Index]) == 0 and not bar.Open == bar.High == bar.Low == bar.Close:
                raise IncompleteQuoteError("zero-volume minute has a changing price")
            if float(volume.loc[bar.Index]) == 0 and position and bar.Open != frame["Close"].iloc[position - 1]:
                raise IncompleteQuoteError("zero-volume minute changes the preceding price")
        frame["Volume"] = volume.astype(float)
    except (TypeError, ValueError) as exc:
        if isinstance(exc, IncompleteQuoteError):
            raise
        raise IncompleteQuoteError("price path reference or volume is invalid") from None
    return frame, daily


def evaluate_position(
    entry_price: float,
    entry_date: str,
    prior_confirmed_highs: pd.Series,
    prior_confirmed_closes: pd.Series,
    today_quote: TodayQuote,
    today_bars: pd.DataFrame,
    trailing_stop_pct: float,
    evaluated_at: datetime,
    ticker: str,
    *,
    in_session: bool,
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
    stale_minutes = (
        STALE_QUOTE_THRESHOLD_MINUTES_IN_SESSION if in_session else STALE_QUOTE_THRESHOLD_MINUTES_OUTSIDE_SESSION
    )
    calendar = xcals.get_calendar(TSE_CALENDAR)
    session = quote_at.date().isoformat()
    if age > timedelta(minutes=stale_minutes) and (
        quote_at.date() != evaluated_at.date() or evaluated_at < calendar.session_close(session)
    ):
        raise StaleQuoteError("quote is stale")

    opening = _positive(today_quote.open, "quote open")
    high = _positive(today_quote.high_so_far, "quote high")
    low = _positive(today_quote.low_so_far, "quote low")
    last = _positive(today_quote.last_price, "quote last")
    if not low <= min(opening, last) <= max(opening, last) <= high:
        raise ValueError("quote OHLC values are inconsistent")
    bars, daily = _minute_bars(today_bars, quote_at, evaluated_at)
    if bars.index[-1] != pd.Timestamp(quote_at):
        raise ValueError("today_bars and quote timestamps do not match")

    highs = _prices(prior_confirmed_highs, "prior_confirmed_highs")
    closes = _prices(prior_confirmed_closes, "prior_confirmed_closes")
    if any(timestamp.date() >= quote_at.date() for timestamp in highs.index.union(closes.index)):
        raise ValueError("prior history must not include the current quote date")
    high_water = adjusted_entry if highs.empty else max(adjusted_entry, float(highs.max()))
    stop_price = high_water * (1.0 - stop_pct / 100.0)
    triggered, exit_reason = False, None
    touch_at = None
    if purchase_date < evaluated_at.date() and daily["Volume"] > 0:
        trades = bars.loc[bars["Volume"] > 0]
        session_open = calendar.session_open(session)
        observed_volume = float(trades["Volume"].sum())
        # On thin stocks the opening trade can be later than the exchange's scheduled open.
        opening_observed = (not trades.empty and math.isclose(daily["Open"], float(trades["Open"].iloc[0]))
                            and (observed_volume == daily["Volume"] or trades.index[0] == session_open))
        if daily["Open"] <= stop_price:
            triggered, exit_reason = True, "trailing_gap"
            touch_at = (trades.index[0] if opening_observed else session_open.tz_convert(JST)).isoformat()
        elif not opening_observed:
            # The opening auction preceded this partial minute path.
            high_water = max(high_water, daily["Open"])
        for bar in trades.itertuples():
            if triggered:
                break
            stop_price = high_water * (1.0 - stop_pct / 100.0)
            if bar.Open <= stop_price:
                triggered, exit_reason = True, "trailing_gap"
                touch_at = pd.Timestamp(bar.Index).isoformat()
                break
            if bar.Low <= stop_price:
                triggered, exit_reason = True, "trailing_stop"
                touch_at = pd.Timestamp(bar.Index).isoformat()
                break
            high_water = max(high_water, float(bar.High))
        if not triggered:
            high_water = max(high_water, daily["High"])
            stop_price = high_water * (1.0 - stop_pct / 100.0)
            unseen_extreme = trades.empty or _below(float(trades["High"].max()), daily["High"]) or _below(
                daily["Low"], float(trades["Low"].min())
            )
            unseen_close = trades.empty or not math.isclose(daily["Close"], float(trades["Close"].iloc[-1]))
            # A volume shortfall gives no price or time for the omitted trades.
            if (unseen_extreme and daily["Low"] <= stop_price) or (unseen_close and daily["Close"] <= stop_price):
                triggered, exit_reason = True, "daily_possible_touch"

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
        return_20d_pct=_return_20d_pct(closes, last),
        touch_at=touch_at,
    )
