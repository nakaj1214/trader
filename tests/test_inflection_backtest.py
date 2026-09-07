from __future__ import annotations

import pandas as pd

from src.evaluation.inflection_backtest import simulate_signal, summarize_trades


def _history(opens: list[float], closes: list[float]) -> pd.DataFrame:
    idx = pd.bdate_range("2026-01-01", periods=len(opens))
    return pd.DataFrame({"Open": opens, "Close": closes}, index=idx)


def test_signal_enters_next_trading_day_open() -> None:
    history = _history(
        [100, 110, 120, 130, 140, 150],
        [100, 112, 122, 132, 142, 160],
    )
    trade = simulate_signal(
        {"ticker": "A.T", "signal_date": "2026-01-01", "score": 80},
        history,
        holding_days=5,
        round_trip_cost_pct=0.0,
    )
    assert trade.entry_date == "2026-01-02"
    assert trade.entry_price == 110.0
    assert trade.exit_price == 160.0
    assert round(trade.gross_return_pct or 0, 6) == round((160 / 110 - 1) * 100, 6)


def test_tax_applies_only_to_positive_net_profit() -> None:
    history = _history([100, 100, 100], [100, 110, 120])
    untaxed = simulate_signal(
        {"ticker": "A.T", "signal_date": "2026-01-01", "score": 80},
        history,
        holding_days=2,
        round_trip_cost_pct=0.0,
        apply_tax=False,
    )
    taxed = simulate_signal(
        {"ticker": "A.T", "signal_date": "2026-01-01", "score": 80},
        history,
        holding_days=2,
        round_trip_cost_pct=0.0,
        apply_tax=True,
    )
    assert taxed.net_return_pct is not None
    assert untaxed.net_return_pct is not None
    assert taxed.net_return_pct < untaxed.net_return_pct


def test_explosive_label_uses_intraperiod_peak() -> None:
    history = _history([100, 100, 100, 100], [100, 160, 120, 110])
    trade = simulate_signal(
        {"ticker": "A.T", "signal_date": "2026-01-01", "score": 80},
        history,
        holding_days=3,
        round_trip_cost_pct=0.0,
    )
    assert trade.explosive_50pct is True
    assert trade.max_return_pct == 60.0


def test_summary_reports_outlier_sensitive_metrics() -> None:
    history_a = _history([100, 100, 100], [100, 120, 120])
    history_b = _history([100, 100, 100], [100, 90, 90])
    a = simulate_signal({"ticker": "A.T", "signal_date": "2026-01-01", "score": 80}, history_a, holding_days=2, round_trip_cost_pct=0)
    b = simulate_signal({"ticker": "B.T", "signal_date": "2026-01-01", "score": 80}, history_b, holding_days=2, round_trip_cost_pct=0)
    summary = summarize_trades([a, b])
    assert summary["completed"] == 2
    assert summary["win_rate_pct"] == 50.0
    assert summary["profit_factor"] == 2.0
