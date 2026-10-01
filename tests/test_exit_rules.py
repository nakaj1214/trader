from __future__ import annotations

import hashlib
import json
import math
import random

import pandas as pd
import pytest

from src.evaluation.exit_rules import (
    ChandelierRule,
    ExitRule,
    MovingAverageBreakRule,
    PartialTakeProfitRule,
    TimeStopRule,
    TrailingRule,
    describe_rule,
    simulate_exit_rule,
)
from src.evaluation.inflection_backtest import TradeResult, simulate_signal

Row = tuple[float, float, float, float]  # open, high, low, close


def history(rows: list[Row], start: str = "2025-01-06") -> pd.DataFrame:
    index = pd.bdate_range(start, periods=len(rows))
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=index)


def flat(count: int, price: float = 100.0, spread: float = 1.0) -> list[Row]:
    return [(price, price + spread, price - spread, price)] * count


def run(
    prefix: list[Row],
    days: list[Row],
    rule: ExitRule,
    *,
    holding_days: int = 126,
    cost: float = 0.2,
) -> TradeResult:
    """``prefix`` rows come before the signal; the entry is the open of the first row of ``days``."""
    frame = history([*prefix, *days])
    signal = {"ticker": "1111.T", "signal_date": str(frame.index[len(prefix) - 1].date()), "score": 80.0}
    return simulate_exit_rule(signal, frame, rule, holding_days=holding_days, round_trip_cost_pct=cost)


def date_of(offset: int, prefix_len: int) -> str:
    return str(pd.bdate_range("2025-01-06", periods=prefix_len + offset + 1)[-1].date())


def synthetic_history(seed: int, n: int = 320) -> pd.DataFrame:
    rng = random.Random(seed)
    close, rows = 100.0, []
    for _ in range(n):
        open_ = close * math.exp(rng.gauss(0.0, 0.01))
        close = open_ * math.exp(rng.gauss(0.001, 0.02))
        rows.append(
            (
                open_,
                max(open_, close) * (1 + abs(rng.gauss(0, 0.008))),
                min(open_, close) * (1 - abs(rng.gauss(0, 0.008))),
                close,
            )
        )
    return history(rows)


# --- 1. the simulator reproduces the existing trailing stop exactly ---------------------------------


def test_trailing_rule_matches_simulate_signal_on_synthetic_walks() -> None:
    compared = 0
    reasons: set[str | None] = set()
    for seed in range(60):
        frame = synthetic_history(seed)
        signal = {"ticker": f"{seed:04d}.T", "signal_date": str(frame.index[40 + seed % 90].date()), "score": 75.0}
        for stop in (10.0, 15.0, 20.0):
            for days in (5, 60, 126, 252):
                expected = simulate_signal(signal, frame, holding_days=days, round_trip_cost_pct=0.2, trailing_stop_pct=stop)
                actual = simulate_exit_rule(signal, frame, TrailingRule(stop), holding_days=days, round_trip_cost_pct=0.2)
                assert actual == expected, (seed, stop, days)
                reasons.add(expected.exit_reason)
                compared += 1
    assert compared == 720
    assert {"trailing_gap", "trailing_stop", "holding_period_close", None} <= reasons  # every path was exercised


# --- Chandelier -------------------------------------------------------------------------------------


def test_chandelier_stop_uses_the_prior_hwm_and_the_prior_sessions_atr() -> None:
    # 30 flat sessions have a true range of 2. Day 1 adds a true range of 10, so on day 2
    # ATR = (21 * 2 + 10) / 22 and the stop = 110 - 3 * ATR.
    trade = run(
        flat(30),
        [(100.0, 110.0, 100.0, 108.0), (108.0, 112.0, 90.0, 95.0), (95.0, 96.0, 94.0, 95.0)],
        ChandelierRule(),
        holding_days=3,
    )

    expected_stop = 110.0 - 3.0 * (21 * 2 + 10) / 22
    assert trade.exit_reason == "chandelier_stop" and trade.exit_date == date_of(1, 30)
    assert trade.exit_price == pytest.approx(expected_stop, abs=1e-5)
    assert trade.net_return_pct == pytest.approx((expected_stop / 100.0 - 1) * 100 - 0.2, abs=1e-4)


def test_chandelier_gap_below_the_stop_fills_at_the_open() -> None:
    trade = run(
        flat(30),
        [(100.0, 110.0, 100.0, 108.0), (100.0, 101.0, 98.0, 99.0), (99.0, 100.0, 98.0, 99.0)],
        ChandelierRule(),
        holding_days=3,
    )

    assert trade.exit_reason == "chandelier_gap" and trade.exit_price == 100.0


def test_chandelier_without_enough_prior_history_is_censored_not_guessed() -> None:
    trade = run(flat(10), [(100.0, 101.0, 99.0, 100.0)] * 5, ChandelierRule(), holding_days=5)

    assert trade.exit_reason == "insufficient_history" and trade.exit_date is None
    assert trade.horizon_matured is False and trade.net_return_pct is None


def test_chandelier_holds_to_the_horizon_when_never_touched() -> None:
    trade = run(flat(30), [(100.0, 101.0, 99.0, 100.0 + i) for i in range(5)], ChandelierRule(), holding_days=5)

    assert trade.exit_reason == "holding_period_close" and trade.exit_price == 104.0


# --- moving-average break ---------------------------------------------------------------------------


def test_ma_break_sells_at_the_next_open_after_a_20_percent_close() -> None:
    days: list[Row] = [
        (100.0, 125.0, 100.0, 125.0),  # +25% close arms the rule from the next session
        (125.0, 130.0, 120.0, 130.0),  # well above the 10-day EMA
        (130.0, 131.0, 100.0, 101.0),  # closes below the EMA: sell at the NEXT open
        (103.0, 108.0, 102.0, 105.0),
        (105.0, 106.0, 100.0, 100.0),
    ]
    trade = run(flat(30), days, MovingAverageBreakRule(), holding_days=5)

    assert trade.exit_reason == "ma_break" and trade.exit_date == date_of(3, 30)
    assert trade.exit_price == 103.0  # not the 101 close the decision was made on
    assert trade.net_return_pct == pytest.approx(3.0 - 0.2)


def test_ma_break_is_ignored_until_the_position_has_gained_20_percent() -> None:
    days: list[Row] = [(100.0, 110.0, 100.0, 110.0), (110.0, 111.0, 90.0, 92.0), (92.0, 93.0, 85.0, 86.0)]
    trade = run(flat(30), days, MovingAverageBreakRule(), holding_days=3)

    assert trade.exit_reason == "holding_period_close" and trade.exit_price == 86.0


def test_ma_break_decided_on_the_last_session_sells_at_that_close() -> None:
    days: list[Row] = [(100.0, 125.0, 100.0, 125.0), (125.0, 126.0, 99.0, 100.0)]
    trade = run(flat(30), days, MovingAverageBreakRule(), holding_days=2)

    assert trade.exit_reason == "holding_period_close" and trade.exit_price == 100.0


def test_ma_break_decided_on_the_last_available_day_without_a_full_horizon_is_censored() -> None:
    days: list[Row] = [(100.0, 125.0, 100.0, 125.0), (125.0, 126.0, 99.0, 100.0)]
    trade = run(flat(30), days, MovingAverageBreakRule(), holding_days=10)

    assert trade.exit_date is None and trade.horizon_matured is False


# --- time stop --------------------------------------------------------------------------------------


def test_time_stop_sells_at_the_open_after_a_weak_15th_session() -> None:
    days: list[Row] = [(100.0, 103.0, 99.0, 102.0)] * 14 + [(102.0, 103.0, 101.0, 102.0)] + [(101.0, 102.0, 100.0, 101.0)] * 5
    trade = run(flat(5), days, TimeStopRule(), holding_days=20)

    assert trade.exit_reason == "time_stop" and trade.exit_date == date_of(15, 5) and trade.exit_price == 101.0


def test_time_stop_has_no_stop_before_the_check_and_then_trails_15_percent() -> None:
    days: list[Row] = [(100.0, 104.0, 99.0, 103.0)] * 4
    days += [(103.0, 105.0, 85.0, 104.0)]  # a deep dip before the check must not exit
    days += [(104.0, 112.0, 103.0, 110.0)] * 9 + [(110.0, 111.0, 109.0, 110.0)]  # session 15 closes at +10%
    days += [(110.0, 111.0, 108.0, 109.0), (109.0, 110.0, 90.0, 95.0), (95.0, 96.0, 94.0, 95.0)]
    trade = run(flat(5), days, TimeStopRule(), holding_days=20)

    assert trade.exit_reason == "time_trailing_stop"
    assert trade.exit_price == pytest.approx(112.0 * 0.85)  # HWM from every high through session 14
    assert trade.exit_date == date_of(16, 5)


def test_time_stop_censored_when_data_ends_before_the_check() -> None:
    trade = run(flat(5), [(100.0, 101.0, 99.0, 100.0)] * 8, TimeStopRule(), holding_days=20)

    assert trade.exit_date is None and trade.horizon_matured is False


# --- partial take-profit ----------------------------------------------------------------------------


def test_open_above_target_books_half_then_the_same_day_stop_still_applies() -> None:
    """Review example: HWM 140 -> stop 119; open 160 books half; the low of 115 stops the rest at 119."""
    days: list[Row] = [(100.0, 140.0, 100.0, 138.0), (160.0, 165.0, 115.0, 120.0), (120.0, 121.0, 119.0, 120.0)]
    trade = run(flat(5), days, PartialTakeProfitRule(), holding_days=3)

    assert trade.exit_legs == [[date_of(1, 5), 160.0, 0.5], [date_of(1, 5), pytest.approx(119.0), 0.5]]
    assert trade.exit_price == pytest.approx(119.0) and trade.exit_reason == "partial_trailing_stop"
    assert trade.gross_return_pct == pytest.approx(0.5 * 60.0 + 0.5 * 19.0)


def test_target_and_stop_touched_in_one_session_assumes_the_stop_first() -> None:
    days: list[Row] = [(100.0, 155.0, 80.0, 120.0), (120.0, 121.0, 119.0, 120.0)]
    trade = run(flat(5), days, PartialTakeProfitRule(), holding_days=2)

    assert trade.exit_price == pytest.approx(85.0) and trade.exit_legs is None
    assert trade.gross_return_pct == pytest.approx(-15.0)


def test_intraday_target_books_half_at_the_target_price_and_trails_the_rest() -> None:
    days: list[Row] = [(100.0, 155.0, 99.0, 150.0), (150.0, 152.0, 130.0, 131.0), (131.0, 132.0, 130.0, 131.0)]
    trade = run(flat(5), days, PartialTakeProfitRule(), holding_days=3)

    assert trade.exit_legs == [[date_of(0, 5), 150.0, 0.5], [date_of(1, 5), pytest.approx(155.0 * 0.85), 0.5]]
    assert trade.gross_return_pct == pytest.approx(0.5 * 50.0 + 0.5 * (155.0 * 0.85 - 100.0))


def test_the_target_is_booked_only_once() -> None:
    days: list[Row] = [(100.0, 155.0, 99.0, 150.0), (150.0, 170.0, 149.0, 168.0), (168.0, 172.0, 167.0, 170.0)]
    trade = run(flat(5), days, PartialTakeProfitRule(), holding_days=3)

    assert trade.exit_reason == "holding_period_close" and len(trade.exit_legs or []) == 2
    assert trade.gross_return_pct == pytest.approx(0.5 * 50.0 + 0.5 * 70.0)


def test_gap_below_the_stop_after_booking_sells_the_remainder_at_the_open() -> None:
    days: list[Row] = [(100.0, 160.0, 99.0, 155.0), (120.0, 125.0, 118.0, 120.0), (120.0, 121.0, 119.0, 120.0)]
    trade = run(flat(5), days, PartialTakeProfitRule(), holding_days=3)

    assert trade.exit_reason == "partial_trailing_gap" and trade.exit_price == 120.0
    assert trade.gross_return_pct == pytest.approx(0.5 * 50.0 + 0.5 * 20.0)


def test_partial_exit_is_anchored_on_the_last_fill_not_a_blended_price() -> None:
    """Review #1: sold half at 150 and the rest at 170, then the stock stays at 170."""
    days: list[Row] = [(100.0, 150.0, 100.0, 150.0), (170.0, 200.0, 168.0, 190.0), (190.0, 195.0, 160.0, 165.0)]
    days += [(170.0, 170.0, 170.0, 170.0)] * 25
    trade = run(flat(5), days, PartialTakeProfitRule(), holding_days=3)

    assert trade.exit_price == pytest.approx(170.0)  # the last real fill, not the blended 160
    assert trade.gross_return_pct == pytest.approx(60.0)
    assert trade.early_exit_return_5d_pct == pytest.approx(0.0)  # a blended 160 would wrongly give +6.25%
    # Measured on the stock's closes up to the last sale (the 190 close on day 2), never on the blended price.
    assert trade.max_return_pct == pytest.approx(90.0)


# --- no look-ahead ----------------------------------------------------------------------------------


EXIT_FIELDS = ("exit_date", "exit_price", "exit_reason", "gross_return_pct", "net_return_pct", "exit_legs")
ALL_RULES: list[ExitRule] = [
    TrailingRule(15.0),
    ChandelierRule(),
    MovingAverageBreakRule(),
    TimeStopRule(),
    PartialTakeProfitRule(),
]


@pytest.mark.parametrize("rule", ALL_RULES, ids=lambda rule: type(rule).__name__)
def test_a_decision_never_depends_on_prices_after_the_exit_session(rule: ExitRule) -> None:
    decided = 0
    for seed in range(120):
        frame = synthetic_history(seed)
        signal = {"ticker": "1111.T", "signal_date": str(frame.index[40 + seed % 90].date()), "score": 80.0}
        full = simulate_exit_rule(signal, frame, rule, holding_days=126)
        if full.exit_date is None:
            continue
        truncated = simulate_exit_rule(signal, frame.loc[: pd.Timestamp(full.exit_date)], rule, holding_days=126)
        assert {field: getattr(truncated, field) for field in EXIT_FIELDS} == {
            field: getattr(full, field) for field in EXIT_FIELDS
        }, (type(rule).__name__, seed)
        decided += 1
    assert decided > 40  # the property was checked on plenty of real exits


def test_atr_and_ema_ignore_later_prices() -> None:
    days: list[Row] = [(100.0, 125.0, 100.0, 125.0), (125.0, 130.0, 120.0, 130.0), (130.0, 131.0, 100.0, 101.0)]
    base = run(flat(30), [*days, (103.0, 108.0, 102.0, 105.0), (105.0, 106.0, 100.0, 100.0)], MovingAverageBreakRule(), holding_days=5)
    shocked = run(flat(30), [*days, (103.0, 108.0, 102.0, 105.0), (500.0, 900.0, 400.0, 800.0)], MovingAverageBreakRule(), holding_days=5)

    assert base.exit_date == shocked.exit_date and base.exit_price == shocked.exit_price == 103.0


# --- misc contracts ---------------------------------------------------------------------------------


def test_missing_ohlc_inside_the_window_raises_like_the_existing_trailing_stop() -> None:
    frame = history([*flat(30), (100.0, 101.0, 99.0, 100.0), (100.0, float("nan"), 99.0, 100.0), (100.0, 101.0, 99.0, 100.0)])
    signal = {"ticker": "1111.T", "signal_date": str(frame.index[29].date()), "score": 80.0}

    with pytest.raises(ValueError, match="complete Open/High/Low"):
        simulate_exit_rule(signal, frame, ChandelierRule(), holding_days=3)


def test_invalid_arguments_are_rejected() -> None:
    frame = history(flat(40))
    signal = {"ticker": "1111.T", "signal_date": str(frame.index[10].date())}
    with pytest.raises(ValueError, match="holding_days"):
        simulate_exit_rule(signal, frame, TrailingRule(15.0), holding_days=0)
    with pytest.raises(ValueError, match="round_trip_cost_pct"):
        simulate_exit_rule(signal, frame, TrailingRule(15.0), round_trip_cost_pct=-1.0)


def test_no_future_data_means_no_entry() -> None:
    frame = history(flat(10))
    trade = simulate_exit_rule({"ticker": "1111.T", "signal_date": str(frame.index[-1].date())}, frame, TrailingRule(15.0))

    assert trade.entry_date is None and trade.exit_date is None


def test_single_sale_trades_have_no_exit_legs_and_rules_describe_their_parameters() -> None:
    trade = run(flat(30), [(100.0, 101.0, 99.0, 100.0)] * 3, ChandelierRule(), holding_days=3)
    assert trade.exit_legs is None
    texts = [describe_rule(rule) for rule in ALL_RULES]
    assert "15%" in texts[0] and "3 x ATR(22)" in texts[1] and "10-day EMA" in texts[2]
    assert "session 15" in texts[3] and "stop is assumed first" in texts[4]


def test_synthetic_walk_generator_is_pinned() -> None:
    """The equivalence and look-ahead tests rely on this exact generator, so pin its output."""
    blob = json.dumps(synthetic_history(7).round(8).to_dict("list"), sort_keys=True)

    assert hashlib.sha256(blob.encode()).hexdigest()[:16] == "22a8bbee485f6d5b"
    assert not synthetic_history(7).equals(synthetic_history(8))
