"""Backtest engine for point-in-time inflection signals.

The engine intentionally accepts precomputed immutable signals. Signal creation
and trade simulation are separated so future information cannot silently leak
into historical scoring.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from statistics import mean, median
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class TradeResult:
    ticker: str
    signal_date: str
    score: float
    entry_date: str | None
    entry_price: float | None
    exit_date: str | None
    exit_price: float | None
    gross_return_pct: float | None
    net_return_pct: float | None
    max_return_pct: float | None
    max_drawdown_pct: float | None
    explosive_50pct: bool | None
    mfe_pct: float | None = None
    mae_pct: float | None = None
    exit_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _series(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty or column not in frame.columns:
        return pd.Series(dtype=float)
    result = frame[column]
    if isinstance(result, pd.DataFrame):
        result = result.iloc[:, 0]
    result = pd.to_numeric(result, errors="coerce").dropna()
    result.index = pd.to_datetime(result.index).tz_localize(None)
    return result.sort_index()


def _true_max_drawdown_pct(entry_price: float, closes: pd.Series) -> float | None:
    """Return the maximum peak-to-trough drawdown after entry."""
    if entry_price <= 0 or closes.empty:
        return None
    values = pd.concat(
        [pd.Series([entry_price], index=[closes.index[0] - pd.Timedelta(microseconds=1)]), closes]
    ).astype(float)
    running_peak = values.cummax()
    drawdowns = (values / running_peak - 1.0) * 100.0
    return float(drawdowns.min())


def simulate_signal(
    signal: dict[str, Any],
    history: pd.DataFrame,
    holding_days: int = 60,
    round_trip_cost_pct: float = 0.2,
    tax_rate_pct: float = 20.315,
    apply_tax: bool = False,
    trailing_stop_pct: float | None = None,
) -> TradeResult:
    """Buy at next open and exit at the horizon or an optional trailing stop."""
    if holding_days < 1:
        raise ValueError("holding_days must be at least 1")
    if round_trip_cost_pct < 0:
        raise ValueError("round_trip_cost_pct must not be negative")
    if not 0 <= tax_rate_pct <= 100:
        raise ValueError("tax_rate_pct must be between 0 and 100")
    if trailing_stop_pct is not None and not 0 < trailing_stop_pct < 100:
        raise ValueError("trailing_stop_pct must be between 0 and 100")
    ticker = str(signal["ticker"])
    signal_date = pd.Timestamp(str(signal["signal_date"]))
    score = float(signal.get("score", 0.0))
    opens = _series(history, "Open")
    closes = _series(history, "Close")
    highs = _series(history, "High")
    lows = _series(history, "Low")
    if opens.empty or closes.empty:
        return TradeResult(ticker, str(signal_date.date()), score, None, None, None, None, None, None, None, None, None)

    after_open = opens[opens.index > signal_date]
    if after_open.empty:
        return TradeResult(ticker, str(signal_date.date()), score, None, None, None, None, None, None, None, None, None)
    entry_date = after_open.index[0]
    entry_price = float(after_open.iloc[0])

    future_closes = closes[closes.index >= entry_date]
    if len(future_closes) < holding_days or entry_price <= 0:
        return TradeResult(
            ticker,
            str(signal_date.date()),
            score,
            str(entry_date.date()),
            entry_price,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )

    window = future_closes.iloc[:holding_days]
    exit_date = window.index[-1]
    exit_price = float(window.iloc[-1])
    exit_reason = "holding_period_close"
    metric_highs = [entry_price]
    metric_lows = [entry_price]

    if trailing_stop_pct is not None:
        window_opens = opens.reindex(window.index)
        window_highs = highs.reindex(window.index)
        window_lows = lows.reindex(window.index)
        if window_opens.isna().any() or window_highs.isna().any() or window_lows.isna().any():
            raise ValueError("trailing stop requires complete Open/High/Low data")

        high_water = entry_price
        for date in window.index:
            day_open = float(window_opens.loc[date])
            day_high = float(window_highs.loc[date])
            day_low = float(window_lows.loc[date])
            stop_price = high_water * (1.0 - trailing_stop_pct / 100.0)
            if day_open <= stop_price:
                exit_date, exit_price, exit_reason = date, day_open, "trailing_gap"
                metric_highs.append(day_open)
                metric_lows.append(day_open)
                break
            if day_low <= stop_price:
                exit_date, exit_price, exit_reason = date, stop_price, "trailing_stop"
                metric_highs.append(day_open)
                metric_lows.append(stop_price)
                break
            metric_highs.append(day_high)
            metric_lows.append(day_low)
            high_water = max(high_water, day_high)
    else:
        window_highs = highs.reindex(window.index).dropna()
        window_lows = lows.reindex(window.index).dropna()
        if len(window_highs) == holding_days:
            metric_highs.extend(float(value) for value in window_highs)
        if len(window_lows) == holding_days:
            metric_lows.extend(float(value) for value in window_lows)

    if exit_reason == "holding_period_close":
        realized_closes = window[window.index <= exit_date]
    else:
        realized_closes = pd.concat(
            [
                window[window.index < exit_date],
                pd.Series([exit_price], index=[exit_date], dtype=float),
            ]
        )
    gross = (exit_price / entry_price - 1.0) * 100.0
    max_return = (float(realized_closes.max()) / entry_price - 1.0) * 100.0
    max_drawdown = _true_max_drawdown_pct(entry_price, realized_closes)
    mfe = (max(metric_highs) / entry_price - 1.0) * 100.0 if len(metric_highs) > 1 else None
    mae = (min(metric_lows) / entry_price - 1.0) * 100.0 if len(metric_lows) > 1 else None
    net = gross - round_trip_cost_pct
    if apply_tax and net > 0:
        net *= 1.0 - tax_rate_pct / 100.0

    return TradeResult(
        ticker=ticker,
        signal_date=str(signal_date.date()),
        score=score,
        entry_date=str(entry_date.date()),
        entry_price=round(entry_price, 6),
        exit_date=str(exit_date.date()),
        exit_price=round(exit_price, 6),
        gross_return_pct=round(gross, 6),
        net_return_pct=round(net, 6),
        max_return_pct=round(max_return, 6),
        max_drawdown_pct=round(max_drawdown, 6) if max_drawdown is not None else None,
        explosive_50pct=max_return >= 50.0,
        mfe_pct=round(mfe, 6) if mfe is not None else None,
        mae_pct=round(mae, 6) if mae is not None else None,
        exit_reason=exit_reason,
    )


def simulate_signals(
    signals: Iterable[dict[str, Any]],
    histories: dict[str, pd.DataFrame],
    **kwargs: Any,
) -> list[TradeResult]:
    return [
        simulate_signal(signal, histories.get(str(signal["ticker"]), pd.DataFrame()), **kwargs)
        for signal in signals
    ]


def select_non_overlapping_trades(trades: Iterable[TradeResult]) -> list[TradeResult]:
    """Keep at most one open position per ticker, ordered by actual entry time."""
    selected: list[TradeResult] = []
    occupied_until: dict[str, str] = {}
    completed = sorted(
        (trade for trade in trades if trade.entry_date and trade.exit_date),
        key=lambda trade: (str(trade.entry_date), trade.ticker, trade.signal_date),
    )
    for trade in completed:
        if str(trade.entry_date) <= occupied_until.get(trade.ticker, ""):
            continue
        selected.append(trade)
        occupied_until[trade.ticker] = str(trade.exit_date)
    return selected


def summarize_trades(trades: Iterable[TradeResult]) -> dict[str, Any]:
    trades = list(trades)
    completed = [trade for trade in trades if trade.net_return_pct is not None]
    returns = [float(trade.net_return_pct) for trade in completed if trade.net_return_pct is not None]
    gross = [float(trade.gross_return_pct) for trade in completed if trade.gross_return_pct is not None]
    winners = [value for value in returns if value > 0]
    losers = [value for value in returns if value < 0]
    max_returns = [float(trade.max_return_pct) for trade in completed if trade.max_return_pct is not None]
    drawdowns = [float(trade.max_drawdown_pct) for trade in completed if trade.max_drawdown_pct is not None]
    mfe = [float(trade.mfe_pct) for trade in completed if trade.mfe_pct is not None]
    mae = [float(trade.mae_pct) for trade in completed if trade.mae_pct is not None]
    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    return {
        "signals": len(trades),
        "completed": len(completed),
        "win_rate_pct": round(len(winners) / len(returns) * 100.0, 3) if returns else None,
        "mean_gross_return_pct": round(mean(gross), 6) if gross else None,
        "mean_net_return_pct": round(mean(returns), 6) if returns else None,
        "median_net_return_pct": round(median(returns), 6) if returns else None,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0 else None,
        "explosive_50pct_count": sum(value >= 50.0 for value in max_returns),
        "explosive_50pct_rate_pct": (
            round(sum(value >= 50.0 for value in max_returns) / len(max_returns) * 100.0, 3)
            if max_returns
            else None
        ),
        "median_max_drawdown_pct": round(median(drawdowns), 6) if drawdowns else None,
        "median_mfe_pct": round(median(mfe), 6) if mfe else None,
        "median_mae_pct": round(median(mae), 6) if mae else None,
    }
