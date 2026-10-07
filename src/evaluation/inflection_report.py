"""Report assembly shared by forward validation and the historical backtest.

Moved out of ``scripts/rebuild_inflection_forward_validation.py`` unchanged so both
paths build identically shaped group reports.
"""

from __future__ import annotations

import math
from statistics import NormalDist, mean, pvariance, stdev, variance
from typing import Any

import pandas as pd

from src.evaluation.exit_rules import (
    ChandelierRule,
    ExitRule,
    MovingAverageBreakRule,
    PartialTakeProfitRule,
    TimeStopRule,
    describe_rule,
    simulate_exit_rule,
)
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
    MARKET_BENCHMARK_TICKERS,
    benchmark_returns_by_signal_date,
    enrich_trades_with_benchmark,
    paired_benchmark_returns,
    summarize_benchmark_excess,
)
from src.evaluation.regime import regime_labels

ROUND_TRIP_COST_PCT = 0.2
STRESS_ROUND_TRIP_COST_PCT = 1.2
BENCHMARK_ROUND_TRIP_COST_PCT = 0.05
TAX_RATE_PCT = 20.315
NEW_EXIT_HOLDING_DAYS = 126
DSR_MIN_TRADES = 30
EULER_MASCHERONI = 0.5772156649015329
# Candidate exit rules compared alongside the fixed-percentage trailing stops. Their parameters are fixed
# in advance; they are not searched, so a good-looking cell is not evidence of a tuned optimum.
NEW_EXIT_RULES: dict[str, ExitRule] = {
    "chandelier_3atr22_h126": ChandelierRule(),
    "ma10_break_after20_h126": MovingAverageBreakRule(),
    "time15d_5pct_then_trail15_h126": TimeStopRule(),
    "partial50_half_then_trail15_h126": PartialTakeProfitRule(),
}
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


REGIME_KINDS = {"trend": ("up", "down", "unknown"), "volatility": ("high", "normal", "unknown")}


def _regime_breakdown(completed: list[TradeResult], benchmark_history: pd.DataFrame) -> dict[str, Any]:
    """Results split by the benchmark's trend and volatility regime on each signal date."""
    closes = _series(benchmark_history, "Close")
    pairs = paired_benchmark_returns(
        completed, benchmark_history, round_trip_cost_pct=BENCHMARK_ROUND_TRIP_COST_PCT
    )
    labels_by_date: dict[str, dict[str, str]] = {}
    groups: dict[str, dict[str, list[tuple[float, float | None]]]] = {
        kind: {label: [] for label in labels} for kind, labels in REGIME_KINDS.items()
    }
    for trade, pair in zip(completed, pairs, strict=True):
        if trade.signal_date not in labels_by_date:
            labels_by_date[trade.signal_date] = regime_labels(closes, trade.signal_date)
        excess = pair["excess_return_pct"]
        for kind in REGIME_KINDS:
            groups[kind][labels_by_date[trade.signal_date][kind]].append(
                (float(trade.net_return_pct or 0.0), float(excess) if excess is not None else None)
            )

    def summarize(values: list[tuple[float, float | None]]) -> dict[str, Any]:
        nets = [net for net, _ in values]
        excesses = [excess for _, excess in values if excess is not None]
        return {
            "count": len(values),
            "mean_net_return_pct": round(sum(nets) / len(nets), 6) if nets else None,
            "win_rate_pct": round(sum(net > 0 for net in nets) / len(nets) * 100.0, 3) if nets else None,
            "mean_excess_return_pct": round(sum(excesses) / len(excesses), 6) if excesses else None,
        }

    return {kind: {label: summarize(values) for label, values in labels.items()} for kind, labels in groups.items()}


def _report_breakdowns(
    trades: list[TradeResult],
    benchmark_history: pd.DataFrame,
) -> dict[str, Any]:
    completed = [trade for trade in trades if trade.net_return_pct is not None]
    score_counts = {**{f"{value}-{value + 9}": 0 for value in range(0, 100, 10)}, "100": 0}
    regime_counts = {"up": 0, "down": 0, "unknown": 0}
    for trade in completed:
        score_counts[score_band(trade.score)] += 1
        regime_counts[regime_label(benchmark_history, trade.signal_date)] += 1
    return {
        "score_band_sample_counts": score_counts,
        "regime_sample_counts": regime_counts,
        "regime_breakdown": _regime_breakdown(completed, benchmark_history),
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


def _market_benchmark_excess(
    trades: list[TradeResult],
    market_benchmarks: dict[str, pd.DataFrame],
    ticker_markets: dict[tuple[str, str], str],
) -> dict[str, Any]:
    markets: dict[str, list[TradeResult]] = {}
    for trade in trades:
        market = ticker_markets.get((trade.signal_date, trade.ticker), "unknown")
        markets.setdefault(market, []).append(trade)
    result: dict[str, Any] = {}
    for market, selected in sorted(markets.items()):
        ticker = MARKET_BENCHMARK_TICKERS.get(market)
        history = market_benchmarks.get(ticker) if ticker is not None else None
        if ticker is None or history is None or history.empty:
            result[market] = {
                "benchmark_ticker": ticker, "value": None,
                "reason": "unsupported_market" if ticker is None else "unavailable",
            }
            continue
        paired = paired_benchmark_returns(
            selected, history, round_trip_cost_pct=BENCHMARK_ROUND_TRIP_COST_PCT, benchmark_ticker=ticker,
        )
        rows = [trade.as_dict() | row for trade, row in zip(selected, paired, strict=True)]
        result[market] = {"benchmark_ticker": ticker, **summarize_benchmark_excess(rows)}
    return result


def _exit_strategy_report(
    trades: list[TradeResult],
    stress_trades: list[TradeResult],
    *,
    rule: str,
    max_holding_days: int,
    benchmark_history: pd.DataFrame,
    market_benchmarks: dict[str, pd.DataFrame] | None = None,
    ticker_markets: dict[tuple[str, str], str] | None = None,
    market_benchmark_error: str | None = None,
) -> dict[str, Any]:
    """The per-exit-rule block of a group report (same shape for every rule)."""
    matured_trades = filter_matured(trades)
    matured_stress_trades = filter_matured(stress_trades)
    trade_rows = _paired_trade_rows(trades, benchmark_history)
    stress_trade_rows = _paired_trade_rows(stress_trades, benchmark_history)
    matured_rows = [row for trade, row in zip(trades, trade_rows, strict=True) if trade.horizon_matured is True]
    matured_stress_rows = [
        row for trade, row in zip(stress_trades, stress_trade_rows, strict=True) if trade.horizon_matured is True
    ]
    stress_report = {
        "matured_summary": summarize_trades(matured_stress_trades),
        "raw_summary": summarize_trades(stress_trades),
        "position_summary": summarize_trades(select_non_overlapping_trades(matured_stress_trades)),
        "benchmark_excess": summarize_benchmark_excess(matured_stress_rows),
        **_report_breakdowns(matured_stress_trades, benchmark_history),
        "trades": stress_trade_rows,
    }
    report = {
        "rule": rule,
        "max_holding_days": max_holding_days,
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
    if market_benchmarks is not None and ticker_markets is not None:
        if market_benchmark_error is not None:
            report["market_benchmark_excess"] = {"value": None, "reason": market_benchmark_error}
        else:
            try:
                report["market_benchmark_excess"] = _market_benchmark_excess(
                    matured_trades, market_benchmarks, ticker_markets
                )
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                report["market_benchmark_excess"] = {"value": None, "reason": f"calculation_failed:{type(exc).__name__}"}
    return report


def _return_moments(returns: list[float]) -> dict[str, float] | None:
    """Sample Sharpe and standardized central moments (Pearson kurtosis, normal = 3)."""
    if len(returns) < 2 or not all(math.isfinite(value) for value in returns):
        return None
    try:
        average = mean(returns)
        sample_std = stdev(returns)
        moment_std = math.sqrt(pvariance(returns))
        if sample_std == 0 or moment_std == 0:
            return None
        standardized = [(value - average) / moment_std for value in returns]
        moments = {
            "sharpe": average / sample_std,
            "skew": mean(value**3 for value in standardized),
            "kurt": mean(value**4 for value in standardized),
        }
        return moments if all(math.isfinite(value) for value in moments.values()) else None
    except (OverflowError, ValueError):
        return None


def _deflated_sharpe(
    sharpe: float, skew: float, kurt: float, trade_count: int, sharpe_variance: float, trial_count: int
) -> float | None:
    """Bailey & López de Prado (2014), equation 2; returns are not annualized."""
    if trial_count < 2 or trade_count < DSR_MIN_TRADES:
        return None
    try:
        normal = NormalDist()
        expected_max = math.sqrt(sharpe_variance) * (
            (1.0 - EULER_MASCHERONI) * normal.inv_cdf(1.0 - 1.0 / trial_count)
            + EULER_MASCHERONI * normal.inv_cdf(1.0 - 1.0 / (trial_count * math.e))
        )
        denominator = 1.0 - skew * sharpe + (kurt - 1.0) / 4.0 * sharpe**2
        if denominator <= 0:
            return None
        z = (sharpe - expected_max) * math.sqrt(trade_count - 1) / math.sqrt(denominator)
        return normal.cdf(z) if math.isfinite(z) else None
    except (OverflowError, ValueError):
        return None


def _deflated_sharpe_report(rule_trades: dict[str, list[TradeResult]]) -> dict[str, Any]:
    eligible: dict[str, list[float]] = {}
    for rule, trades in rule_trades.items():
        selected = select_non_overlapping_trades(filter_matured(trades))
        returns = [float(trade.net_return_pct) for trade in selected if trade.net_return_pct is not None]
        if len(returns) >= DSR_MIN_TRADES:
            eligible[rule] = returns
    trial_count = len(eligible)
    caveat = "Reference only: assumes independent trades and trials; does not select an exit rule automatically."
    if trial_count < 2:
        return {"value": None, "reason": "fewer_than_two_rules_with_30_matured_non_overlapping_trades", "trial_count": trial_count}
    moments = {rule: _return_moments(returns) for rule, returns in eligible.items()}
    if any(value is None for value in moments.values()):
        return {"value": None, "reason": "zero_return_std_or_invalid_moments", "trial_count": trial_count}
    valid = {rule: value for rule, value in moments.items() if value is not None}
    best_rule = max(valid, key=lambda rule: valid[rule]["sharpe"])
    best = valid[best_rule]
    trade_count = len(eligible[best_rule])
    value = _deflated_sharpe(
        best["sharpe"], best["skew"], best["kurt"], trade_count,
        variance(item["sharpe"] for item in valid.values()), trial_count,
    )
    return {
        "value": value,
        "reason": None if value is not None else "invalid_dsr_denominator_or_non_finite_result",
        "best_rule": best_rule,
        **best,
        "trial_count": trial_count,
        "trade_count": trade_count,
        "caveat": caveat,
    }


def _build_group_report(
    signals: list[dict[str, Any]],
    histories: dict[str, pd.DataFrame],
    split_histories: dict[str, pd.DataFrame],
    benchmark_history: pd.DataFrame,
    signal_dates: list[str],
    *,
    market_benchmarks: dict[str, pd.DataFrame] | None = None,
    ticker_markets: dict[tuple[str, str], str] | None = None,
    market_benchmark_error: str | None = None,
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
    base_rule_trades: dict[str, list[TradeResult]] = {}
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
            key = f"trailing_{int(trailing_stop_pct)}pct_h{holding_days}"
            base_rule_trades[key] = trades
            exit_strategies[key] = _exit_strategy_report(
                trades,
                stress_trades,
                rule="prior_confirmed_high_water_mark",
                max_holding_days=holding_days,
                benchmark_history=benchmark_history,
                market_benchmarks=market_benchmarks,
                ticker_markets=ticker_markets,
                market_benchmark_error=market_benchmark_error,
            )
    for key, exit_rule in NEW_EXIT_RULES.items():
        rule_trades = [
            simulate_exit_rule(
                signal,
                split_histories.get(str(signal["ticker"]), pd.DataFrame()),
                exit_rule,
                holding_days=NEW_EXIT_HOLDING_DAYS,
                round_trip_cost_pct=ROUND_TRIP_COST_PCT,
            )
            for signal in signals
        ]
        rule_stress_trades = [
            simulate_exit_rule(
                signal,
                split_histories.get(str(signal["ticker"]), pd.DataFrame()),
                exit_rule,
                holding_days=NEW_EXIT_HOLDING_DAYS,
                round_trip_cost_pct=STRESS_ROUND_TRIP_COST_PCT,
            )
            for signal in signals
        ]
        exit_strategies[key] = _exit_strategy_report(
            rule_trades,
            rule_stress_trades,
            rule=describe_rule(exit_rule),
            max_holding_days=NEW_EXIT_HOLDING_DAYS,
            benchmark_history=benchmark_history,
            market_benchmarks=market_benchmarks,
            ticker_markets=ticker_markets,
            market_benchmark_error=market_benchmark_error,
        )
        base_rule_trades[key] = rule_trades
    return {
        "signal_count": len(signals),
        "horizons": horizons,
        "exit_strategies": exit_strategies,
        "deflated_sharpe": _deflated_sharpe_report(base_rule_trades),
    }
