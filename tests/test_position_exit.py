from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.data.live_quote import TodayQuote
from src.monitoring.position_exit import StaleQuoteError, evaluate_position

JST = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 9, 8, 12, 35, tzinfo=JST)


def _quote(**changes: object) -> TodayQuote:
    quote = TodayQuote(110.0, 115.0, 109.0, 112.0, (NOW - timedelta(minutes=1)).isoformat())
    return replace(quote, **changes)


def _bar_frame(quote: TodayQuote) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [quote.open],
            "High": [quote.high_so_far],
            "Low": [quote.low_so_far],
            "Close": [quote.last_price],
        },
        index=pd.DatetimeIndex([quote.as_of_at]),
    )


def _evaluate(
    quote: TodayQuote,
    highs: list[float] | None = None,
    *,
    bars: pd.DataFrame | None = None,
    entry_date: str = "2026-09-01",
    in_session: bool = False,
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
        _bar_frame(quote) if bars is None else bars,
        10.0,
        NOW,
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


def test_quote_exactly_at_stale_boundary_is_accepted() -> None:
    status = _evaluate(_quote(as_of_at=(NOW - timedelta(minutes=60)).isoformat()), [110.0])

    assert status.triggered is False


def test_in_session_quote_uses_ten_minute_stale_threshold() -> None:
    accepted = _evaluate(
        _quote(as_of_at=(NOW - timedelta(minutes=9)).isoformat()),
        [],
        in_session=True,
    )

    assert accepted.triggered is False
    with pytest.raises(StaleQuoteError, match="stale"):
        _evaluate(
            _quote(as_of_at=(NOW - timedelta(minutes=11)).isoformat()),
            [],
            in_session=True,
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
        bars.iloc[0] = [110.0, 115.0, 113.0, 112.0]
    elif case == "high":
        bars.iloc[0] = [110.0, 111.0, 109.0, 112.0]
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
