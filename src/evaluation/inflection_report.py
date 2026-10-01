"""Report assembly shared by forward validation and the historical backtest.

Moved out of ``scripts/rebuild_inflection_forward_validation.py`` unchanged so both
paths build identically shaped group reports.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.evaluation.inflection_backtest import (
    TradeResult,
    _series,
    filter_matured,
    score_band,
    select_non_overlapping_trades,
    simulate_signals,
    summarize_trades,
)
from src.evaluation.inflection_forward import (
    benchmark_returns_by_signal_date,
    enrich_trades_with_benchmark,
    paired_benchmark_returns,
    summarize_benchmark_excess,
)

ROUND_TRIP_COST_PCT = 0.2
STRESS_ROUND_TRIP_COST_PCT = 1.2
BENCHMARK_ROUND_TRIP_COST_PCT = 0.05
TAX_RATE_PCT = 20.315
PORTFOLIO_INITIAL_CAPITAL_JPY = 3_000_000.0
PORTFOLIO_MAX_POSITIONS = 8
PORTFOLIO_POSITION_SIZE_PCT = 1 / PORTFOLIO_MAX_POSITIONS


def _summary_only(value: Any) -> Any:
    """Remove prediction-level trade rows from an otherwise useful report."""
    if isinstance(value, dict):
        return {key: _summary_only(item) for key, item in value.items() if key != "trades"}
    if isinstance(value, list):
        return [_summary_only(item) for item in value]
    return value


def regime_label(benchmark_history: pd.DataFrame, signal_date: str) -> str:
    closes = _series(benchmark_history, "Close")
    available = closes[closes.index <= pd.Timestamp(signal_date)]
    if len(available) < 21:
        return "unknown"
    return "up" if float(available.iloc[-1]) >= float(available.iloc[-21]) else "down"


def _report_breakdowns(
    trades: list[TradeResult],
    benchmark_history: pd.DataFrame,
) -> dict[str, dict[str, int]]:
    completed = [trade for trade in trades if trade.net_return_pct is not None]
    score_counts = {**{f"{value}-{value + 9}": 0 for value in range(0, 100, 10)}, "100": 0}
    regime_counts = {"up": 0, "down": 0, "unknown": 0}
    for trade in completed:
        score_counts[score_band(trade.score)] += 1
        regime_counts[regime_label(benchmark_history, trade.signal_date)] += 1
    return {
        "score_band_sample_counts": score_counts,
        "regime_sample_counts": regime_counts,
    }


def _paired_trade_rows(
    trades: list[TradeResult],
    benchmark_history: pd.DataFrame,
) -> list[dict[str, Any]]:
    benchmarks = paired_benchmark_returns(
        trades,
        benchmark_history,
        round_trip_cost_pct=BENCHMARK_ROUND_TRIP_COST_PCT,
    )
    return [trade.as_dict() | benchmark for trade, benchmark in zip(trades, benchmarks, strict=True)]


def _build_group_report(
    signals: list[dict[str, Any]],
    histories: dict[str, pd.DataFrame],
    split_histories: dict[str, pd.DataFrame],
    benchmark_history: pd.DataFrame,
    signal_dates: list[str],
) -> dict[str, Any]:
    horizons: dict[str, object] = {}
    for holding_days in (5, 20, 60, 126, 252):
        trades = simulate_signals(
            signals,
            histories,
            holding_days=holding_days,
            round_trip_cost_pct=ROUND_TRIP_COST_PCT,
            tax_rate_pct=TAX_RATE_PCT,
            apply_tax=False,
        )
        benchmark_returns = benchmark_returns_by_signal_date(
            signal_dates,
            benchmark_history,
            holding_days=holding_days,
            round_trip_cost_pct=BENCHMARK_ROUND_TRIP_COST_PCT,
        )
        trade_rows = enrich_trades_with_benchmark(trades, benchmark_returns)
        stress_trades = simulate_signals(
            signals,
            histories,
            holding_days=holding_days,
            round_trip_cost_pct=STRESS_ROUND_TRIP_COST_PCT,
            tax_rate_pct=TAX_RATE_PCT,
            apply_tax=False,
        )
        stress_trade_rows = enrich_trades_with_benchmark(stress_trades, benchmark_returns)
        stress_report: dict[str, Any] = {
            "summary": summarize_trades(stress_trades),
            "position_summary": summarize_trades(select_non_overlapping_trades(stress_trades)),
            "benchmark_excess": summarize_benchmark_excess(stress_trade_rows),
            **_report_breakdowns(stress_trades, benchmark_history),
            "trades": stress_trade_rows,
        }
        horizons[f"h{holding_days}"] = {
            "summary": summarize_trades(trades),
            "position_summary": summarize_trades(select_non_overlapping_trades(trades)),
            "benchmark_excess": summarize_benchmark_excess(trade_rows),
            **_report_breakdowns(trades, benchmark_history),
            "trades": trade_rows,
            "stress": stress_report,
        }

    exit_strategies: dict[str, object] = {}
    for trailing_stop_pct in (10.0, 15.0, 20.0):
        for holding_days in (60, 126, 252):
            trades = simulate_signals(
                signals,
                split_histories,
                holding_days=holding_days,
                round_trip_cost_pct=ROUND_TRIP_COST_PCT,
                apply_tax=False,
                trailing_stop_pct=trailing_stop_pct,
            )
            stress_trades = simulate_signals(
                signals,
                split_histories,
                holding_days=holding_days,
                round_trip_cost_pct=STRESS_ROUND_TRIP_COST_PCT,
                apply_tax=False,
                trailing_stop_pct=trailing_stop_pct,
            )
            matured_trades = filter_matured(trades)
            matured_stress_trades = filter_matured(stress_trades)
            trade_rows = _paired_trade_rows(trades, benchmark_history)
            stress_trade_rows = _paired_trade_rows(stress_trades, benchmark_history)
            matured_rows = [
                row for trade, row in zip(trades, trade_rows, strict=True) if trade.horizon_matured is True
            ]
            matured_stress_rows = [
                row
                for trade, row in zip(stress_trades, stress_trade_rows, strict=True)
                if trade.horizon_matured is True
            ]
            stress_report = {
                "matured_summary": summarize_trades(matured_stress_trades),
                "raw_summary": summarize_trades(stress_trades),
                "position_summary": summarize_trades(
                    select_non_overlapping_trades(matured_stress_trades)
                ),
                "benchmark_excess": summarize_benchmark_excess(matured_stress_rows),
                **_report_breakdowns(matured_stress_trades, benchmark_history),
                "trades": stress_trade_rows,
            }
            exit_strategies[f"trailing_{int(trailing_stop_pct)}pct_h{holding_days}"] = {
                "rule": "prior_confirmed_high_water_mark",
                "max_holding_days": holding_days,
                "eligible_count": len(matured_trades),
                "censored_count": sum(trade.horizon_matured is False for trade in trades),
                "matured_summary": summarize_trades(matured_trades),
                "raw_summary": summarize_trades(trades),
                "position_summary": summarize_trades(select_non_overlapping_trades(matured_trades)),
                "benchmark_excess": summarize_benchmark_excess(matured_rows),
                **_report_breakdowns(matured_trades, benchmark_history),
                "trades": trade_rows,
                "stress": stress_report,
            }
    return {
        "signal_count": len(signals),
        "horizons": horizons,
        "exit_strategies": exit_strategies,
    }
