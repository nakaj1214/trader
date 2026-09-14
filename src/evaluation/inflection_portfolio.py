"""Portfolio-level simulation for point-in-time inflection trades."""

from __future__ import annotations

from collections import Counter
from math import isfinite
from statistics import median
from typing import Any

import pandas as pd

from src.evaluation.inflection_backtest import (
    TradeResult,
    _series,
    _true_max_drawdown_pct,
    summarize_trades,
)


def simulate_portfolio(
    signals: list[dict[str, Any]],
    trades: list[TradeResult],
    histories: dict[str, pd.DataFrame],
    calendar: pd.DatetimeIndex,
    *,
    initial_capital_jpy: float,
    max_positions: int,
    position_size_pct: float,
    round_trip_cost_pct: float,
) -> dict[str, Any]:
    """Simulate fixed-size positions and mark them to market on ``calendar``.

    Individual closes are forward-filled onto the benchmark calendar to absorb
    exchange/data-date mismatches, with no fill limit. Open positions use a
    hypothetical liquidation value including the fixed round-trip cost. Entries
    occur at the open; positions exiting that date still occupy cash and a slot
    until that day's close. Turnover is the period-total entry allocation divided
    by mean equity, not an annualized value.
    """
    if len(signals) != len(trades):
        raise ValueError("signals and trades must have equal length")
    if not isfinite(initial_capital_jpy) or initial_capital_jpy <= 0:
        raise ValueError("initial_capital_jpy must be positive and finite")
    if isinstance(max_positions, bool) or max_positions < 1:
        raise ValueError("max_positions must be at least 1")
    if not isfinite(position_size_pct) or not 0 < position_size_pct <= 1:
        raise ValueError("position_size_pct must be between 0 and 1")
    if max_positions * position_size_pct > 1.0 + 1e-9:
        raise ValueError("max_positions * position_size_pct must not exceed 1")
    if not isfinite(round_trip_cost_pct) or not 0 <= round_trip_cost_pct <= 100:
        raise ValueError("round_trip_cost_pct must be finite and between 0 and 100")

    allocation = initial_capital_jpy * position_size_pct
    candidates = sorted(
        (
            (pd.Timestamp(trade.entry_date), signal, trade)
            for signal, trade in zip(signals, trades, strict=True)
            if trade.entry_date is not None
        ),
        key=lambda item: (item[0], -item[2].score, item[2].ticker),
    )
    empty = {
        "config": {
            "initial_capital_jpy": initial_capital_jpy,
            "max_positions": max_positions,
            "position_size_pct": position_size_pct,
            "round_trip_cost_pct": round_trip_cost_pct,
            "source_horizon": "h60",
            "source_cost_scenario": "base",
        },
        "entered_position_count": 0,
        "completed_trade_count": 0,
        "open_positions_at_cutoff_count": 0,
        "skipped_ticker_conflict_count": 0,
        "skipped_slot_full_count": 0,
        "skipped_insufficient_cash_count": 0,
        "final_equity_jpy": None,
        "cagr_pct": None,
        "max_drawdown_pct": None,
        "elapsed_calendar_days": 0,
        "mean_open_position_count": None,
        "max_open_position_count": 0,
        "mean_cash_utilization_pct": None,
        "turnover_ratio_period_total": None,
        "exposure_by_market_pct": {},
        "avg_turnover_capacity_ratio_median": None,
        "equity_curve": [],
        "trade_summary": summarize_trades([]),
        "caveat": (
            "EARLY_CANDIDATE h60/base-cost only; open positions include hypothetical liquidation "
            "cost. Sector limits and lot/ADV capacity are not modeled. CAGR and drawdown are not "
            "meaningful until sufficient snapshots accumulate."
        ),
    }
    if not candidates:
        return empty

    dates = pd.DatetimeIndex(calendar).tz_localize(None).normalize().drop_duplicates().sort_values()
    first_entry = candidates[0][0].normalize()
    dates = dates[dates >= first_entry]
    event_dates = {
        date.normalize()
        for _, _, trade in candidates
        for date in (
            pd.Timestamp(trade.entry_date),
            *([pd.Timestamp(trade.exit_date)] if trade.exit_date is not None else []),
        )
    }
    if dates.empty or not event_dates.issubset(set(dates)):
        raise ValueError("calendar must contain every executable trade entry and exit date")

    entries: dict[pd.Timestamp, list[tuple[dict[str, Any], TradeResult]]] = {}
    for entry_date, signal, trade in candidates:
        entries.setdefault(entry_date.normalize(), []).append((signal, trade))
    closes = {ticker: _series(history, "Close").reindex(dates).ffill() for ticker, history in histories.items()}
    cash = float(initial_capital_jpy)
    open_positions: dict[str, tuple[dict[str, Any], TradeResult, float]] = {}
    executed: list[tuple[dict[str, Any], TradeResult]] = []
    skipped = Counter[str]()
    equity_values: list[float] = []
    open_counts: list[int] = []
    cash_utilization: list[float] = []

    for date in dates:
        # Entries are priced at the open, so same-day close proceeds cannot fund them.
        for signal, trade in entries.get(date, []):
            if trade.ticker in open_positions:
                skipped["ticker_conflict"] += 1
            elif len(open_positions) >= max_positions:
                skipped["slot_full"] += 1
            elif cash + 1e-9 < allocation:
                skipped["insufficient_cash"] += 1
            else:
                if trade.entry_price is None or trade.entry_price <= 0:
                    raise ValueError("executable trades require a positive entry price")
                if trade.exit_date is not None and trade.net_return_pct is None:
                    raise ValueError("completed executable trades require a net return")
                cash -= allocation
                open_positions[trade.ticker] = (signal, trade, allocation / trade.entry_price)
                executed.append((signal, trade))

        for ticker, (_, trade, _) in list(open_positions.items()):
            if trade.exit_date is not None and pd.Timestamp(trade.exit_date).normalize() == date:
                assert trade.net_return_pct is not None
                cash += allocation * (1.0 + float(trade.net_return_pct) / 100.0)
                del open_positions[ticker]

        market_value = 0.0
        for ticker, (_, _, shares) in open_positions.items():
            close = closes.get(ticker, pd.Series(dtype=float)).get(date)
            if close is None or pd.isna(close):
                raise ValueError(f"missing Close for open position on {date.date()}: {ticker}")
            market_value += shares * float(close) - allocation * round_trip_cost_pct / 100.0
        equity = cash + market_value
        equity_values.append(equity)
        open_counts.append(len(open_positions))
        cash_utilization.append(market_value / equity * 100.0 if equity > 0 else 0.0)

    if not executed:
        return empty | {
            "skipped_ticker_conflict_count": skipped["ticker_conflict"],
            "skipped_slot_full_count": skipped["slot_full"],
            "skipped_insufficient_cash_count": skipped["insufficient_cash"],
        }

    first_executed = min(pd.Timestamp(trade.entry_date) for _, trade in executed)
    active_slice = dates >= first_executed
    equity_series = pd.Series(equity_values, index=dates, dtype=float)[active_slice]
    open_count_series = pd.Series(open_counts, index=dates)[active_slice]
    cash_utilization_series = pd.Series(cash_utilization, index=dates)[active_slice]
    final_equity = float(equity_series.iloc[-1])
    elapsed_days = int((equity_series.index[-1] - equity_series.index[0]).days)
    completed_trades = [trade for _, trade in executed if trade.exit_date is not None]
    markets = Counter(str(signal.get("market") or "unknown") for signal, _ in executed)
    capacities: list[float] = []
    for signal, _ in executed:
        turnover = signal.get("avg_turnover_20d_jpy")
        if turnover is None or isinstance(turnover, bool):
            continue
        try:
            value = float(turnover)
        except (TypeError, ValueError):
            continue
        if isfinite(value) and value > 0:
            capacities.append(allocation / value)
    max_drawdown = _true_max_drawdown_pct(initial_capital_jpy, equity_series)
    assert max_drawdown is not None
    return empty | {
        "entered_position_count": len(executed),
        "completed_trade_count": len(completed_trades),
        "open_positions_at_cutoff_count": len(open_positions),
        "skipped_ticker_conflict_count": skipped["ticker_conflict"],
        "skipped_slot_full_count": skipped["slot_full"],
        "skipped_insufficient_cash_count": skipped["insufficient_cash"],
        "final_equity_jpy": round(final_equity, 6),
        "cagr_pct": (
            round(((final_equity / initial_capital_jpy) ** (365.25 / elapsed_days) - 1) * 100, 6)
            if elapsed_days > 0 and final_equity > 0
            else None
        ),
        "max_drawdown_pct": round(max_drawdown, 6),
        "elapsed_calendar_days": elapsed_days,
        "mean_open_position_count": round(float(open_count_series.mean()), 6),
        "max_open_position_count": int(open_count_series.max()),
        "mean_cash_utilization_pct": round(float(cash_utilization_series.mean()), 6),
        "turnover_ratio_period_total": round(len(executed) * allocation / float(equity_series.mean()), 6),
        "exposure_by_market_pct": {
            market: round(count / len(executed) * 100.0, 3) for market, count in sorted(markets.items())
        },
        "avg_turnover_capacity_ratio_median": (round(median(capacities), 6) if capacities else None),
        "equity_curve": [
            {"date": str(date.date()), "equity_jpy": round(value, 6)} for date, value in equity_series.items()
        ],
        "trade_summary": summarize_trades(completed_trades),
    }
