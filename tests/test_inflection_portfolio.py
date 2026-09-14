from __future__ import annotations

import pandas as pd
import pytest

from src.evaluation.inflection_backtest import TradeResult
from src.evaluation.inflection_portfolio import simulate_portfolio


def _trade(
    ticker: str,
    entry_date: str,
    exit_date: str | None,
    *,
    score: float = 80.0,
    net_return_pct: float = 0.0,
    gross_return_pct: float | None = None,
) -> TradeResult:
    completed = exit_date is not None
    gross_return_pct = net_return_pct if gross_return_pct is None else gross_return_pct
    return TradeResult(
        ticker=ticker,
        signal_date=str((pd.Timestamp(entry_date) - pd.Timedelta(days=1)).date()),
        score=score,
        entry_date=entry_date,
        entry_price=100.0,
        exit_date=exit_date,
        exit_price=100.0 * (1 + gross_return_pct / 100) if completed else None,
        gross_return_pct=gross_return_pct if completed else None,
        net_return_pct=net_return_pct if completed else None,
        max_return_pct=gross_return_pct if completed else None,
        max_drawdown_pct=min(gross_return_pct, 0.0) if completed else None,
        explosive_50pct=False if completed else None,
        horizon_matured=completed,
    )


def _history(dates: pd.DatetimeIndex, closes: list[float] | None = None) -> pd.DataFrame:
    values = closes or [100.0] * len(dates)
    return pd.DataFrame({"Close": values}, index=dates)


def _simulate(
    signals: list[dict],
    trades: list[TradeResult],
    dates: pd.DatetimeIndex,
    histories: dict[str, pd.DataFrame] | None = None,
    *,
    capital: float = 1_000.0,
    max_positions: int = 2,
    position_size_pct: float = 0.5,
    cost: float = 0.0,
) -> dict:
    return simulate_portfolio(
        signals,
        trades,
        histories or {trade.ticker: _history(dates) for trade in trades},
        dates,
        initial_capital_jpy=capital,
        max_positions=max_positions,
        position_size_pct=position_size_pct,
        round_trip_cost_pct=cost,
    )


def test_executes_positions_and_reports_market_and_capacity_diagnostics() -> None:
    dates = pd.to_datetime(["2026-01-02", "2026-01-05"])
    trades = [
        _trade("A.T", "2026-01-02", "2026-01-05", net_return_pct=10),
        _trade("B.T", "2026-01-02", "2026-01-05", net_return_pct=-10),
    ]
    signals = [
        {"market": "Prime", "avg_turnover_20d_jpy": 10_000},
        {"market": None, "avg_turnover_20d_jpy": None},
    ]

    result = _simulate(signals, trades, dates)

    assert result["entered_position_count"] == 2
    assert result["completed_trade_count"] == 2
    assert result["open_positions_at_cutoff_count"] == 0
    assert result["final_equity_jpy"] == pytest.approx(1_000)
    assert result["max_open_position_count"] == 2
    assert result["exposure_by_market_pct"] == {"Prime": 50.0, "unknown": 50.0}
    assert result["avg_turnover_capacity_ratio_median"] == pytest.approx(0.05)
    assert result["trade_summary"]["sample_count"] == 2


def test_same_day_candidates_prioritize_score_and_are_not_deferred() -> None:
    dates = pd.to_datetime(["2026-01-02", "2026-01-05"])
    trades = [
        _trade("LOW.T", "2026-01-02", "2026-01-05", score=70, net_return_pct=-50),
        _trade("HIGH.T", "2026-01-02", "2026-01-05", score=90, net_return_pct=10),
    ]

    result = _simulate([{}, {}], trades, dates, max_positions=1, position_size_pct=1)

    assert result["entered_position_count"] == 1
    assert result["skipped_slot_full_count"] == 1
    assert result["final_equity_jpy"] == pytest.approx(1_100)


def test_rejects_overlapping_same_ticker_position() -> None:
    dates = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"])
    trades = [
        _trade("A.T", "2026-01-02", "2026-01-06", net_return_pct=10),
        _trade("A.T", "2026-01-05", "2026-01-07", net_return_pct=50),
    ]

    result = _simulate([{}, {}], trades, dates)

    assert result["entered_position_count"] == 1
    assert result["skipped_ticker_conflict_count"] == 1
    assert result["final_equity_jpy"] == pytest.approx(1_050)


def test_marks_to_market_daily_and_calculates_drawdown_and_cagr() -> None:
    dates = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
    trade = _trade("A.T", "2026-01-02", "2026-01-06", net_return_pct=10)

    result = _simulate(
        [{}],
        [trade],
        dates,
        {"A.T": _history(dates, [100, 80, 110])},
        max_positions=1,
        position_size_pct=1,
    )

    elapsed_days = 4
    expected_cagr = ((1.1 ** (365.25 / elapsed_days)) - 1) * 100
    assert result["final_equity_jpy"] == pytest.approx(1_100)
    assert result["max_drawdown_pct"] == pytest.approx(-20)
    assert result["cagr_pct"] == pytest.approx(expected_cagr, rel=1e-6)
    assert [point["equity_jpy"] for point in result["equity_curve"]] == [1_000, 800, 1_100]


def test_does_not_reuse_close_proceeds_for_same_day_open_entry() -> None:
    dates = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
    trades = [
        _trade("A.T", "2026-01-02", "2026-01-05", net_return_pct=10),
        _trade("B.T", "2026-01-05", "2026-01-06", net_return_pct=50),
    ]

    result = _simulate([{}, {}], trades, dates, max_positions=1, position_size_pct=1)

    assert result["entered_position_count"] == 1
    assert result["skipped_slot_full_count"] == 1
    assert result["final_equity_jpy"] == pytest.approx(1_100)


def test_skips_entry_after_realized_loss_leaves_too_little_cash() -> None:
    dates = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"])
    trades = [
        _trade("LOSS.T", "2026-01-02", "2026-01-05", net_return_pct=-100),
        _trade("HIGH.T", "2026-01-06", "2026-01-07", score=90),
        _trade("LOW.T", "2026-01-06", "2026-01-07", score=70),
    ]

    result = _simulate([{}, {}, {}], trades, dates)

    assert result["entered_position_count"] == 2
    assert result["skipped_insufficient_cash_count"] == 1


def test_empty_and_invalid_inputs() -> None:
    empty = _simulate([], [], pd.DatetimeIndex([]))
    assert empty["entered_position_count"] == 0
    assert empty["final_equity_jpy"] is None
    assert empty["equity_curve"] == []

    with pytest.raises(ValueError, match="must not exceed"):
        _simulate([], [], pd.DatetimeIndex([]), max_positions=3, position_size_pct=0.5)
    with pytest.raises(ValueError, match="equal length"):
        _simulate([{}], [], pd.DatetimeIndex([]))


def test_unmatured_high_score_trade_wins_slot_without_lookahead() -> None:
    dates = pd.to_datetime(["2026-01-02", "2026-01-05"])
    trades = [
        _trade("LOW.T", "2026-01-02", "2026-01-05", score=70, net_return_pct=50),
        _trade("HIGH.T", "2026-01-02", None, score=90),
    ]

    result = _simulate([{}, {}], trades, dates, max_positions=1, position_size_pct=1)

    assert result["entered_position_count"] == 1
    assert result["completed_trade_count"] == 0
    assert result["open_positions_at_cutoff_count"] == 1
    assert result["skipped_slot_full_count"] == 1
    assert result["trade_summary"]["sample_count"] == 0


def test_open_position_is_valued_through_cutoff_and_included_in_entry_diagnostics() -> None:
    dates = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
    trade = _trade("A.T", "2026-01-02", None)
    signal = {"market": "Prime", "avg_turnover_20d_jpy": 10_000}

    result = _simulate(
        [signal],
        [trade],
        dates,
        {"A.T": _history(dates, [100, 110, 120])},
        max_positions=1,
        position_size_pct=1,
        cost=0.2,
    )

    assert result["equity_curve"][-1] == {"date": "2026-01-06", "equity_jpy": 1_198}
    assert result["final_equity_jpy"] == pytest.approx(1_198)
    assert result["mean_cash_utilization_pct"] is not None
    assert result["turnover_ratio_period_total"] is not None
    assert result["exposure_by_market_pct"] == {"Prime": 100.0}
    assert result["avg_turnover_capacity_ratio_median"] == pytest.approx(0.1)
    assert result["trade_summary"]["sample_count"] == 0


@pytest.mark.parametrize(("close", "gross_return"), [(120.0, 20.0), (80.0, -20.0)])
def test_open_position_cost_matches_completed_trade_value(close: float, gross_return: float) -> None:
    dates = pd.to_datetime(["2026-01-02", "2026-01-05"])
    history = {"A.T": _history(dates, [100, close])}
    open_result = _simulate(
        [{}],
        [_trade("A.T", "2026-01-02", None)],
        dates,
        history,
        max_positions=1,
        position_size_pct=1,
        cost=0.2,
    )
    completed_result = _simulate(
        [{}],
        [
            _trade(
                "A.T",
                "2026-01-02",
                "2026-01-05",
                gross_return_pct=gross_return,
                net_return_pct=gross_return - 0.2,
            )
        ],
        dates,
        history,
        max_positions=1,
        position_size_pct=1,
        cost=0.2,
    )
    no_cost_result = _simulate(
        [{}],
        [_trade("A.T", "2026-01-02", None)],
        dates,
        history,
        max_positions=1,
        position_size_pct=1,
    )

    assert open_result["final_equity_jpy"] == pytest.approx(completed_result["final_equity_jpy"])
    assert no_cost_result["final_equity_jpy"] - open_result["final_equity_jpy"] == pytest.approx(2)


@pytest.mark.parametrize("cost", [float("nan"), float("inf"), -0.1, 100.1])
def test_rejects_invalid_round_trip_cost(cost: float) -> None:
    with pytest.raises(ValueError, match="round_trip_cost_pct"):
        _simulate([], [], pd.DatetimeIndex([]), cost=cost)
