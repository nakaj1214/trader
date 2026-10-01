"""Day-by-day exit-rule simulator for comparing ways of selling a position.

Every rule shares the fill conventions of the existing trailing stop in ``simulate_signal``:

* entry is the open of the first session after the signal date;
* each session is decided in time order: the open first, then the day's low/high, then the close;
* the stop level is computed from the high-water mark of PREVIOUS sessions only;
* an open at or below the stop fills at the open (gap), an intraday low at or below it fills at the stop;
* a rule that decides on a close sells at the NEXT session's open (selling at the very close it was
  judged on would look ahead);
* a position still open at the end of the holding window is sold at that last close.

Nothing a rule uses on day D (ATR, EMA, gains, highs) may come from a later day. The parameters of each
rule are fixed up front and are not searched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.evaluation.inflection_backtest import TradeResult, _finalize_trade, _series


@dataclass(frozen=True)
class TrailingRule:
    stop_pct: float


@dataclass(frozen=True)
class ChandelierRule:
    atr_multiple: float = 3.0
    atr_window: int = 22


@dataclass(frozen=True)
class MovingAverageBreakRule:
    ema_span: int = 10
    activation_gain_pct: float = 20.0


@dataclass(frozen=True)
class TimeStopRule:
    check_day: int = 15
    min_gain_pct: float = 5.0
    then_trailing_pct: float = 15.0


@dataclass(frozen=True)
class PartialTakeProfitRule:
    target_gain_pct: float = 50.0
    fraction: float = 0.5
    trailing_pct: float = 15.0


ExitRule = TrailingRule | ChandelierRule | MovingAverageBreakRule | TimeStopRule | PartialTakeProfitRule


def describe_rule(rule: ExitRule) -> str:
    """Human-readable rule text, with its fixed parameters, for reports."""
    if isinstance(rule, TrailingRule):
        return f"trailing stop {rule.stop_pct:g}% below the prior high-water mark"
    if isinstance(rule, ChandelierRule):
        return (
            f"stop = prior high-water mark - {rule.atr_multiple:g} x ATR({rule.atr_window}) of the prior sessions; "
            "gap fills at the open"
        )
    if isinstance(rule, MovingAverageBreakRule):
        return (
            f"after a +{rule.activation_gain_pct:g}% close, sell at the next open when the close falls below the "
            f"{rule.ema_span}-day EMA"
        )
    if isinstance(rule, TimeStopRule):
        return (
            f"sell at the next open if the close of session {rule.check_day} is below +{rule.min_gain_pct:g}%; "
            f"otherwise trail {rule.then_trailing_pct:g}%"
        )
    return (
        f"sell {rule.fraction:g} at +{rule.target_gain_pct:g}% (a gap above fills at the open), trail "
        f"{rule.trailing_pct:g}% on the rest; if a stop and the target are both touched in one session with no "
        "known order, the stop is assumed first"
    )


@dataclass
class _State:
    hwm: float
    max_close: float
    remaining: float = 1.0
    booked: bool = False
    pending_reason: str | None = None


def _atr_before(frame: pd.DataFrame, window: int) -> pd.Series:
    """ATR for each session = mean true range of the ``window`` sessions BEFORE it."""
    previous_close = frame["Close"].shift(1)
    true_range = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - previous_close).abs(),
            (frame["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1, skipna=False)
    return true_range.rolling(window).mean().shift(1)


def _incomplete(
    ticker: str,
    signal_date: pd.Timestamp,
    score: float,
    entry_date: pd.Timestamp | None,
    entry_price: float | None,
    *,
    horizon_matured: bool | None,
    reason: str | None = None,
) -> TradeResult:
    return TradeResult(
        ticker,
        str(signal_date.date()),
        score,
        str(entry_date.date()) if entry_date is not None else None,
        entry_price,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        exit_reason=reason,
        horizon_matured=horizon_matured,
    )


def simulate_exit_rule(
    signal: dict[str, Any],
    history: pd.DataFrame,
    rule: ExitRule,
    *,
    holding_days: int = 126,
    round_trip_cost_pct: float = 0.2,
    apply_tax: bool = False,
    tax_rate_pct: float = 20.315,
) -> TradeResult:
    """Simulate one entry under ``rule`` for at most ``holding_days`` sessions."""
    if holding_days < 1:
        raise ValueError("holding_days must be at least 1")
    if round_trip_cost_pct < 0:
        raise ValueError("round_trip_cost_pct must not be negative")
    ticker = str(signal["ticker"])
    signal_date = pd.Timestamp(str(signal["signal_date"]))
    score = float(signal.get("score", 0.0))
    opens, closes = _series(history, "Open"), _series(history, "Close")
    highs, lows = _series(history, "High"), _series(history, "Low")
    if opens.empty or closes.empty:
        return _incomplete(ticker, signal_date, score, None, None, horizon_matured=None)
    after_open = opens[opens.index > signal_date]
    if after_open.empty:
        return _incomplete(ticker, signal_date, score, None, None, horizon_matured=None)
    entry_date = pd.Timestamp(after_open.index[0])
    entry_price = float(after_open.iloc[0])
    future_closes = closes[closes.index >= entry_date]
    has_full_horizon = len(future_closes) >= holding_days
    if entry_price <= 0 or future_closes.empty:
        return _incomplete(
            ticker, signal_date, score, entry_date, entry_price, horizon_matured=has_full_horizon
        )

    window = future_closes.iloc[:holding_days]
    window_opens, window_highs, window_lows = (
        opens.reindex(window.index),
        highs.reindex(window.index),
        lows.reindex(window.index),
    )
    if window_opens.isna().any() or window_highs.isna().any() or window_lows.isna().any():
        raise ValueError("exit rules require complete Open/High/Low data")

    atr: pd.Series | None = None
    if isinstance(rule, ChandelierRule):
        ohlc = pd.concat({"High": highs, "Low": lows, "Close": closes}, axis=1).dropna()
        atr = _atr_before(ohlc, rule.atr_window).reindex(window.index)
        if atr.isna().any():
            return _incomplete(
                ticker, signal_date, score, entry_date, entry_price, horizon_matured=False, reason="insufficient_history"
            )
    ema = (
        closes.ewm(span=rule.ema_span, adjust=False).mean().reindex(window.index)
        if isinstance(rule, MovingAverageBreakRule)
        else None
    )

    state = _State(hwm=entry_price, max_close=entry_price)
    legs: list[tuple[pd.Timestamp, float, float]] = []
    metric_highs, metric_lows = [entry_price], [entry_price]
    final: tuple[pd.Timestamp, float, str, str] | None = None  # (date, price, reason, convention)

    def trail_stop(percent: float) -> float:
        return state.hwm * (1.0 - percent / 100.0)

    for position, date in enumerate(window.index):
        day_open, day_high = float(window_opens.iloc[position]), float(window_highs.iloc[position])
        day_low, day_close = float(window_lows.iloc[position]), float(window.iloc[position])

        if state.pending_reason is not None:  # a rule decided on yesterday's close: sell at today's open
            final = (date, day_open, state.pending_reason, "open")
            break

        stop: float | None = None
        gap_reason = stop_reason = ""
        if isinstance(rule, TrailingRule):
            stop, gap_reason, stop_reason = trail_stop(rule.stop_pct), "trailing_gap", "trailing_stop"
        elif isinstance(rule, ChandelierRule) and atr is not None:
            stop = state.hwm - rule.atr_multiple * float(atr.iloc[position])
            gap_reason, stop_reason = "chandelier_gap", "chandelier_stop"
        elif isinstance(rule, TimeStopRule) and position >= rule.check_day:
            stop, gap_reason, stop_reason = trail_stop(rule.then_trailing_pct), "time_trailing_gap", "time_trailing_stop"
        elif isinstance(rule, PartialTakeProfitRule):
            stop, gap_reason, stop_reason = trail_stop(rule.trailing_pct), "partial_trailing_gap", "partial_trailing_stop"

        if stop is not None and day_open <= stop:
            final = (date, day_open, gap_reason, "open")
            break

        if isinstance(rule, PartialTakeProfitRule):
            assert stop is not None  # always set for this rule above
            target = entry_price * (1.0 + rule.target_gain_pct / 100.0)
            if not state.booked and day_open >= target:  # the open is known first: book, then keep judging the day
                legs.append((date, day_open, rule.fraction))
                state.remaining -= rule.fraction
                state.booked = True
            touched_stop = day_low <= stop
            if state.booked and touched_stop:
                final = (date, stop, stop_reason, "stop")
                break
            if not state.booked:
                if touched_stop and day_high >= target:  # order unknown within the day: assume the stop came first
                    final = (date, stop, stop_reason, "stop")
                    break
                if day_high >= target:
                    legs.append((date, target, rule.fraction))
                    state.remaining -= rule.fraction
                    state.booked = True
                elif touched_stop:
                    final = (date, stop, stop_reason, "stop")
                    break
        elif stop is not None and day_low <= stop:
            final = (date, stop, stop_reason, "stop")
            break

        metric_highs.append(day_high)
        metric_lows.append(day_low)
        state.hwm = max(state.hwm, day_high)

        if isinstance(rule, MovingAverageBreakRule) and ema is not None:
            armed = (state.max_close / entry_price - 1.0) * 100.0 >= rule.activation_gain_pct
            if armed and day_close < float(ema.iloc[position]):
                state.pending_reason = "ma_break"
            state.max_close = max(state.max_close, day_close)
        elif isinstance(rule, TimeStopRule) and position == rule.check_day - 1:
            if (day_close / entry_price - 1.0) * 100.0 < rule.min_gain_pct:
                state.pending_reason = "time_stop"

    if final is None:
        if not has_full_horizon:
            return _incomplete(ticker, signal_date, score, entry_date, entry_price, horizon_matured=False)
        final = (window.index[-1], float(window.iloc[-1]), "holding_period_close", "close")

    exit_date, exit_price, reason, convention = final
    if convention == "open":
        metric_highs.append(exit_price)
        metric_lows.append(exit_price)
    elif convention == "stop":
        metric_highs.append(float(window_opens.loc[exit_date]))
        metric_lows.append(exit_price)
    realized_closes = pd.concat(
        [window[window.index < exit_date], pd.Series([exit_price], index=[exit_date], dtype=float)]
    )
    return _finalize_trade(
        ticker=ticker,
        signal_date=signal_date,
        score=score,
        entry_date=entry_date,
        entry_price=entry_price,
        exits=[*legs, (exit_date, exit_price, state.remaining)],
        exit_reason=reason,
        realized_closes=realized_closes,
        metric_highs=metric_highs,
        metric_lows=metric_lows,
        closes=closes,
        has_full_horizon=has_full_horizon,
        round_trip_cost_pct=round_trip_cost_pct,
        apply_tax=apply_tax,
        tax_rate_pct=tax_rate_pct,
    )
