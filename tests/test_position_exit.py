from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.data.live_quote import TodayQuote
from src.monitoring.position_exit import IncompleteQuoteError, StaleQuoteError, _return_20d_pct, evaluate_position

JST = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 9, 8, 12, 35, tzinfo=JST)


@pytest.mark.parametrize(("count", "expected"), [(19, None), (20, 50.0), (21, 50.0)])
def test_twentieth_prior_close_is_used_for_the_overheating_return(count: int, expected: float | None) -> None:
    closes = pd.Series([999.0] * max(0, count - 20) + [100.0] * min(count, 20))
    assert _return_20d_pct(closes, 150.0) == expected


def test_overheating_return_leaves_the_exit_decision_unchanged() -> None:
    quote = _quote()
    highs = pd.Series([120.0], index=pd.to_datetime(["2026-09-07"]))
    statuses = []
    for count in (19, 20):
        closes = pd.Series([70.0] * count, index=pd.bdate_range(end="2026-09-07", periods=count))
        statuses.append(evaluate_position(
            100.0, "2026-07-01", highs, closes, quote, _bar_frame(quote), 10.0, NOW, "1111.T", in_session=False
        ))
    assert statuses[0].return_20d_pct is None
    assert statuses[1].return_20d_pct == pytest.approx(60.0)
    assert (statuses[0].triggered, statuses[0].exit_reason, statuses[0].stop_price) == (
        statuses[1].triggered, statuses[1].exit_reason, statuses[1].stop_price
    )


def _quote(**changes: object) -> TodayQuote:
    quote = TodayQuote(110.0, 115.0, 109.0, 112.0, (NOW - timedelta(minutes=1)).isoformat())
    return replace(quote, **changes)


def _bar_frame(quote: TodayQuote) -> pd.DataFrame:
    return _certify(pd.DataFrame(
        {
            "Open": [quote.open],
            "High": [quote.high_so_far],
            "Low": [quote.low_so_far],
            "Close": [quote.last_price],
        },
        index=pd.DatetimeIndex([quote.as_of_at]),
    ))


def _certify(frame: pd.DataFrame) -> pd.DataFrame:
    """Supply an independent daily feed for the existing stop-ordering unit fixtures."""
    frame["Volume"] = 1.0
    frame.attrs = {"requested_date": frame.index[-1].date().isoformat(), "daily_bar": {
        "Open": float(frame["Open"].iloc[0]), "High": float(frame["High"].max()),
        "Low": float(frame["Low"].min()), "Close": float(frame["Close"].iloc[-1]), "Volume": float(len(frame)),
    }}
    return frame


def _evaluate(
    quote: TodayQuote,
    highs: list[float] | None = None,
    *,
    bars: pd.DataFrame | None = None,
    entry_date: str = "2026-09-01",
    in_session: bool = False,
    evaluated_at: datetime = NOW,
):
    index = pd.to_datetime(["2026-09-04", "2026-09-07"][: len(highs or [])])
    closes = (
        pd.Series(dtype=float)
        if entry_date == NOW.date().isoformat()
        else pd.Series([105.0, 110.0], index=pd.to_datetime(["2026-09-04", "2026-09-07"]))
    )
    return evaluate_position(
        100.0,
        entry_date,
        pd.Series(highs or [], index=index, dtype=float),
        closes,
        quote,
        _bar_frame(quote) if bars is None else (_certify(bars) if not bars.attrs else bars),
        10.0,
        evaluated_at,
        "1111.T",
        in_session=in_session,
    )


def test_evaluate_position_matches_gap_and_low_touch_ordering() -> None:
    gap = _evaluate(_quote(open=100.0, low_so_far=99.0), [120.0])
    touch = _evaluate(_quote(open=110.0, low_so_far=107.0), [120.0])

    assert gap.exit_reason == "trailing_gap"
    assert touch.exit_reason == "trailing_stop"
    assert gap.stop_price == 108.0


def test_minute_bars_update_high_water_only_after_stop_check() -> None:
    index = pd.DatetimeIndex([NOW - timedelta(minutes=2), NOW - timedelta(minutes=1)])
    bars = pd.DataFrame(
        {
            "Open": [100.0, 140.0],
            "High": [150.0, 145.0],
            "Low": [95.0, 130.0],
            "Close": [140.0, 135.0],
        },
        index=index,
    )
    quote = TodayQuote(100.0, 150.0, 95.0, 135.0, index[-1].isoformat())

    status = _evaluate(quote, [], bars=bars)

    assert status.triggered is True
    assert status.exit_reason == "trailing_stop"
    assert status.stop_price == 135.0


def test_same_bar_high_is_not_used_before_its_low() -> None:
    index = pd.DatetimeIndex([NOW - timedelta(minutes=1)])
    bars = pd.DataFrame(
        {"Open": [100.0], "High": [150.0], "Low": [95.0], "Close": [140.0]},
        index=index,
    )
    quote = TodayQuote(100.0, 150.0, 95.0, 140.0, index[-1].isoformat())

    status = _evaluate(quote, [], bars=bars)

    assert status.triggered is False
    assert status.high_water_mark == 150.0
    assert status.stop_price == 135.0


def test_entry_day_skips_intraday_stop_evaluation() -> None:
    quote = _quote(open=50.0, high_so_far=60.0, low_so_far=40.0, last_price=55.0)

    status = _evaluate(quote, [], entry_date=NOW.date().isoformat())

    assert status.triggered is False
    assert status.high_water_mark == 100.0
    assert status.stop_price == 90.0


def test_next_session_does_not_recover_excluded_entry_day_high() -> None:
    index = pd.DatetimeIndex([NOW - timedelta(minutes=1)])
    bars = pd.DataFrame(
        {"Open": [120.0], "High": [120.0], "Low": [120.0], "Close": [120.0]},
        index=index,
    )
    quote = TodayQuote(120.0, 120.0, 120.0, 120.0, index[-1].isoformat())

    # The entry-day high of 150 is intentionally absent from confirmed history.
    status = evaluate_position(
        100.0,
        "2026-09-07",
        pd.Series(dtype=float),
        pd.Series(dtype=float),
        quote,
        _certify(bars),
        15.0,
        NOW,
        "1111.T",
        in_session=False,
    )

    assert status.triggered is False
    assert status.high_water_mark == 120.0
    assert status.stop_price == 102.0


def test_quote_exactly_at_stale_boundary_is_accepted() -> None:
    at = NOW.replace(hour=14)
    status = _evaluate(_quote(as_of_at=(at - timedelta(minutes=60)).isoformat()), [110.0], evaluated_at=at)

    assert status.triggered is False


def test_in_session_quote_uses_twenty_minute_stale_threshold() -> None:
    at = NOW.replace(hour=10)
    accepted = _evaluate(
        _quote(as_of_at=(at - timedelta(minutes=19)).isoformat()),
        [],
        in_session=True,
        evaluated_at=at,
    )

    assert accepted.triggered is False
    with pytest.raises(StaleQuoteError, match="stale"):
        _evaluate(
            _quote(as_of_at=(at - timedelta(minutes=21)).isoformat()),
            [],
            in_session=True,
            evaluated_at=at,
        )


@pytest.mark.parametrize(
    "quote,evaluated_at",
    [
        (_quote(as_of_at=(NOW - timedelta(minutes=61)).isoformat()), NOW),
        (_quote(as_of_at=(NOW + timedelta(minutes=1)).isoformat()), NOW),
        (_quote(as_of_at="2026-09-08T12:34:00"), NOW),
    ],
)
def test_evaluate_position_rejects_unusable_quote_time(quote: TodayQuote, evaluated_at: datetime) -> None:
    with pytest.raises(StaleQuoteError):
        evaluate_position(
            100.0,
            "2026-09-01",
            pd.Series(dtype=float),
            pd.Series(dtype=float),
            quote,
            _bar_frame(quote),
            10.0,
            evaluated_at,
            "1111.T",
            in_session=False,
        )


def test_evaluate_position_requires_aware_evaluation_time() -> None:
    quote = _quote()
    with pytest.raises(ValueError, match="timezone"):
        evaluate_position(
            100.0,
            "2026-09-01",
            pd.Series(dtype=float),
            pd.Series(dtype=float),
            quote,
            _bar_frame(quote),
            10.0,
            NOW.replace(tzinfo=None),
            "1111.T",
            in_session=False,
        )


@pytest.mark.parametrize("entry_price", [0.0, float("nan"), float("inf")])
def test_evaluate_position_rejects_invalid_entry_price(entry_price: float) -> None:
    quote = _quote()
    with pytest.raises(ValueError, match="entry_price"):
        evaluate_position(
            entry_price,
            "2026-09-01",
            pd.Series(dtype=float),
            pd.Series(dtype=float),
            quote,
            _bar_frame(quote),
            10.0,
            NOW,
            "1111.T",
            in_session=False,
        )


def _invalid_bars(case: str) -> tuple[TodayQuote, pd.DataFrame]:
    quote = _quote()
    bars = _bar_frame(quote)
    if case == "nan":
        bars.iloc[0, bars.columns.get_loc("High")] = float("nan")
    elif case == "non_positive":
        bars.iloc[0, bars.columns.get_loc("Low")] = 0.0
    elif case == "low":
        bars.loc[:, ["Open", "High", "Low", "Close"]] = [110.0, 115.0, 113.0, 112.0]
    elif case == "high":
        bars.loc[:, ["Open", "High", "Low", "Close"]] = [110.0, 111.0, 109.0, 112.0]
    elif case == "naive":
        bars.index = bars.index.tz_localize(None)
    elif case == "wrong_date":
        bars.index = bars.index - timedelta(days=1)
    elif case == "duplicate":
        bars = pd.concat([bars, bars])
    elif case == "future":
        future = bars.copy()
        future.index = future.index + timedelta(minutes=1)
        bars = pd.concat([bars, future])
    return quote, bars


@pytest.mark.parametrize(
    "case",
    ["nan", "non_positive", "low", "high", "naive", "wrong_date", "duplicate", "future"],
)
def test_evaluate_position_rejects_invalid_minute_bars(case: str) -> None:
    quote, bars = _invalid_bars(case)

    with pytest.raises(ValueError, match="today_bars"):
        _evaluate(quote, [], bars=bars)


def test_evaluate_position_rejects_current_day_in_prior_history() -> None:
    quote = _quote()
    with pytest.raises(ValueError, match="current quote date"):
        evaluate_position(
            100.0,
            "2026-09-01",
            pd.Series([120.0], index=pd.to_datetime(["2026-09-08"])),
            pd.Series(dtype=float),
            quote,
            _bar_frame(quote),
            10.0,
            NOW,
            "1111.T",
            in_session=False,
        )


def _reference_path(*, touch: bool = False, high_update: bool = False) -> pd.DataFrame:
    frame = pd.DataFrame(
        {"Open": [100.0, 100.0, 100.0], "High": [100.0, 120.0 if high_update else 100.0, 100.0],
         "Low": [100.0, 80.0 if touch else 100.0, 100.0], "Close": [100.0, 100.0, 100.0],
         "Volume": [10.0, 10.0, 10.0]},
        index=pd.DatetimeIndex(["2026-09-08 09:00", "2026-09-08 09:01", "2026-09-08 09:59"], tz=JST),
    )
    frame.attrs = {"requested_date": "2026-09-08", "daily_bar": {
        "Open": 100.0, "High": 120.0 if high_update else 100.0,
        "Low": 80.0 if touch else 100.0, "Close": 100.0, "Volume": 30.0,
    }}
    return frame


def _evaluate_reference(frame: pd.DataFrame):
    from src.data.live_quote import build_today_quote

    quote = build_today_quote(frame)
    assert quote is not None
    return evaluate_position(
        100.0, "2026-09-07", pd.Series(dtype=float), pd.Series(dtype=float), quote, frame, 15.0,
        datetime(2026, 9, 8, 10, 0, tzinfo=JST), "1111.T", in_session=True,
    )


@pytest.mark.parametrize("case", ["stop_bar", "high_bar", "opening", "latest_only", "daily_high", "daily_low"])
def test_fresh_final_timestamp_does_not_prove_a_complete_minute_path(case: str) -> None:
    frame = _reference_path(touch=case == "stop_bar", high_update=case == "high_bar")
    if case in ("stop_bar", "high_bar"):
        frame = frame.drop(frame.index[1])
    elif case == "opening":
        frame = frame.iloc[1:]
    elif case == "latest_only":
        frame = frame.iloc[-1:]
    else:
        frame.attrs["daily_bar"]["High" if case == "daily_high" else "Low"] = 150.0 if case == "daily_high" else 70.0
    with pytest.raises(IncompleteQuoteError):
        _evaluate_reference(frame)


def test_missing_daily_or_request_evidence_is_indeterminate() -> None:
    frame = _reference_path()
    frame.attrs.clear()
    with pytest.raises(IncompleteQuoteError):
        _evaluate_reference(frame)


def test_thin_trading_and_no_trade_minutes_are_not_required_to_have_bars() -> None:
    assert _evaluate_reference(_reference_path()).triggered is False


def test_lunch_break_is_not_a_missing_price_interval() -> None:
    frame = _reference_path()
    frame.index = pd.DatetimeIndex(["2026-09-08 09:00", "2026-09-08 11:29", "2026-09-08 12:30"], tz=JST)
    from src.data.live_quote import build_today_quote

    quote = build_today_quote(frame)
    assert quote is not None
    result = evaluate_position(
        100.0, "2026-09-07", pd.Series(dtype=float), pd.Series(dtype=float), quote, frame, 15.0,
        datetime(2026, 9, 8, 12, 31, tzinfo=JST), "1111.T", in_session=True,
    )
    assert result.triggered is False


def test_halted_interval_is_accepted_only_when_all_daily_trades_are_accounted_for() -> None:
    frame = _reference_path().iloc[[0, 2]].copy()
    frame.attrs["daily_bar"]["Volume"] = 20.0
    assert _evaluate_reference(frame).triggered is False
    frame.attrs["daily_bar"]["Volume"] = 30.0
    with pytest.raises(IncompleteQuoteError):
        _evaluate_reference(frame)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), -1.0])
def test_invalid_minute_volume_is_not_a_complete_price_path(value: float) -> None:
    frame = _reference_path()
    frame.iloc[1, frame.columns.get_loc("Volume")] = value
    with pytest.raises(IncompleteQuoteError):
        _evaluate_reference(frame)


def test_zero_trade_padding_cannot_raise_high_water_before_the_first_actual_trade() -> None:
    frame = _reference_path()
    frame.loc[:, ["Open", "High", "Low", "Close", "Volume"]] = [
        [150.0, 150.0, 150.0, 150.0, 0.0],
        [150.0, 180.0, 110.0, 180.0, 10.0],
        [180.0, 180.0, 180.0, 180.0, 10.0],
    ]
    frame.attrs["daily_bar"] = {"Open": 150.0, "High": 180.0, "Low": 110.0, "Close": 180.0, "Volume": 20.0}
    status = _evaluate_reference(frame)
    assert status.triggered is False and status.high_water_mark == 180.0


def test_a_verified_closing_path_is_still_usable_when_the_closing_job_is_delayed() -> None:
    from src.data.live_quote import build_today_quote

    frame = _reference_path()
    frame.index = pd.DatetimeIndex(["2026-09-08 09:00", "2026-09-08 15:25", "2026-09-08 15:30"], tz=JST)
    quote = build_today_quote(frame)
    assert quote is not None
    status = evaluate_position(
        100.0, "2026-09-07", pd.Series(dtype=float), pd.Series(dtype=float), quote, frame, 15.0,
        datetime(2026, 9, 8, 16, 45, tzinfo=JST), "1111.T", in_session=False,
    )
    assert status.triggered is False and status.as_of_at == quote.as_of_at
