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
) -> TradeResult:
    """Buy at next trading day's open and exit at holding-day close."""
    ticker = str(signal["ticker"])
    signal_date = pd.Timestamp(str(signal["signal_date"]))
    score = float(signal.get("score", 0.0))
    opens = _series(history, "Open")
    closes = _series(history, "Close")
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
    gross = (exit_price / entry_price - 1.0) * 100.0
    max_return = (float(window.max()) / entry_price - 1.0) * 100.0
    max_drawdown = _true_max_drawdown_pct(entry_price, window)
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


def summarize_trades(trades: Iterable[TradeResult]) -> dict[str, Any]:
    trades = list(trades)
    completed = [trade for trade in trades if trade.net_return_pct is not None]
    returns = [float(trade.net_return_pct) for trade in completed if trade.net_return_pct is not None]
    gross = [float(trade.gross_return_pct) for trade in completed if trade.gross_return_pct is not None]
    winners = [value for value in returns if value > 0]
    losers = [value for value in returns if value < 0]
    max_returns = [float(trade.max_return_pct) for trade in completed if trade.max_return_pct is not None]
    drawdowns = [float(trade.max_drawdown_pct) for trade in completed if trade.max_drawdown_pct is not None]
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
    }