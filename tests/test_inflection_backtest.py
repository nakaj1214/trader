from __future__ import annotations

import pandas as pd

from src.evaluation.inflection_backtest import (
    select_non_overlapping_trades,
    simulate_signal,
    summarize_trades,
)


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


def test_drawdown_is_peak_to_trough_not_entry_to_low() -> None:
    history = _history([100, 100, 100, 100, 100], [100, 120, 150, 105, 130])
    trade = simulate_signal(
        {"ticker": "A.T", "signal_date": "2026-01-01", "score": 80},
        history,
        holding_days=4,
        round_trip_cost_pct=0.0,
    )
    assert trade.max_drawdown_pct == -30.0


def test_mfe_and_mae_use_intraday_high_and_low() -> None:
    index = pd.bdate_range("2026-01-01", periods=4)
    history = pd.DataFrame(
        {
            "Open": [100, 100, 100, 100],
            "High": [100, 120, 180, 130],
            "Low": [100, 90, 80, 100],
            "Close": [100, 110, 120, 110],
        },
        index=index,
    )

    trade = simulate_signal(
        {"ticker": "A.T", "signal_date": "2026-01-01", "score": 80},
        history,
        holding_days=3,
        round_trip_cost_pct=0.0,
    )

    assert trade.max_return_pct == 20.0
    assert trade.mfe_pct == 80.0
    assert trade.mae_pct == -20.0
    assert summarize_trades([trade])["median_mfe_pct"] == 80.0
    assert summarize_trades([trade])["median_mae_pct"] == -20.0


def test_trailing_stop_uses_prior_high_and_actual_gap_open() -> None:
    index = pd.bdate_range("2026-01-01", periods=5)
    history = pd.DataFrame(
        {
            "Open": [100, 100, 105, 90, 90],
            "High": [100, 110, 120, 95, 95],
            "Low": [100, 99, 104, 85, 85],
            "Close": [100, 108, 118, 90, 90],
        },
        index=index,
    )

    trade = simulate_signal(
        {"ticker": "A.T", "signal_date": "2026-01-01", "score": 80},
        history,
        holding_days=4,
        round_trip_cost_pct=0,
        trailing_stop_pct=10,
    )

    assert trade.exit_date == "2026-01-06"
    assert trade.exit_price == 90.0
    assert trade.exit_reason == "trailing_gap"
    assert trade.mfe_pct == 20.0


def test_trailing_stop_does_not_use_same_day_high_to_trigger_itself() -> None:
    index = pd.bdate_range("2026-01-01", periods=5)
    history = pd.DataFrame(
        {
            "Open": [100, 100, 105, 140, 140],
            "High": [100, 110, 150, 145, 145],
            "Low": [100, 99, 100, 130, 130],
            "Close": [100, 108, 145, 135, 135],
        },
        index=index,
    )

    trade = simulate_signal(
        {"ticker": "A.T", "signal_date": "2026-01-01", "score": 80},
        history,
        holding_days=4,
        round_trip_cost_pct=0,
        trailing_stop_pct=10,
    )

    assert trade.exit_date == "2026-01-06"
    assert trade.exit_price == 135.0
    assert trade.exit_reason == "trailing_stop"


def test_non_overlapping_trades_keep_one_position_per_ticker() -> None:
    history = _history(
        [100, 100, 100, 100, 100, 100, 100],
        [100, 101, 102, 103, 104, 105, 106],
    )
    trades = [
        simulate_signal(
            {"ticker": "A.T", "signal_date": date, "score": 80},
            history,
            holding_days=3,
            round_trip_cost_pct=0,
        )
        for date in ("2026-01-01", "2026-01-02", "2026-01-06")
    ]

    selected = select_non_overlapping_trades(trades)

    assert [trade.signal_date for trade in selected] == ["2026-01-01", "2026-01-06"]


def test_summary_reports_outlier_sensitive_metrics() -> None:
    history_a = _history([100, 100, 100], [100, 120, 120])
    history_b = _history([100, 100, 100], [100, 90, 90])
    a = simulate_signal(
        {"ticker": "A.T", "signal_date": "2026-01-01", "score": 80},
        history_a,
        holding_days=2,
        round_trip_cost_pct=0,
    )
    b = simulate_signal(
        {"ticker": "B.T", "signal_date": "2026-01-01", "score": 80},
        history_b,
        holding_days=2,
        round_trip_cost_pct=0,
    )
    summary = summarize_trades([a, b])
    assert summary["completed"] == 2
    assert summary["win_rate_pct"] == 50.0
    assert summary["profit_factor"] == 2.0
