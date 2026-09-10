from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.data.live_quote import (
    build_today_quote,
    fetch_split_adjusted_history,
    fetch_today_bars,
    fetch_today_quote,
    split_adjust_ohlc,
)

JST = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 9, 8, 9, 3, tzinfo=JST)


def _daily_history(dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "High": [120.0] * len(dates),
            "Close": [110.0] * len(dates),
            "Stock Splits": [0.0] * len(dates),
        },
        index=pd.DatetimeIndex(dates, tz=JST),
    )


def test_split_adjusts_all_ohlc_without_dividend_adjustment() -> None:
    index = pd.DatetimeIndex(["2026-09-01", "2026-09-03"], tz=JST)
    history = pd.DataFrame(
        {
            "Open": [100.0, 55.0],
            "High": [110.0, 60.0],
            "Low": [90.0, 50.0],
            "Close": [100.0, 55.0],
            "Dividends": [10.0, 0.0],
            "Stock Splits": [0.0, 2.0],
        },
        index=index,
    )

    adjusted = split_adjust_ohlc(history, NOW.date())

    assert adjusted.loc[index[0], ["Open", "High", "Low", "Close"]].tolist() == pytest.approx([50.0, 55.0, 45.0, 50.0])
    assert adjusted.loc[index[1], "Close"] == 55.0
    assert adjusted["Dividends"].tolist() == [10.0, 0.0]


def test_split_history_excludes_entry_and_current_dates() -> None:
    dates = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-07", "2026-09-08"]
    history = _daily_history(dates)
    history.loc[pd.Timestamp("2026-09-03", tz=JST), "Stock Splits"] = 2.0
    history.loc[pd.Timestamp("2026-09-08", tz=JST), "Stock Splits"] = 3.0
    ticker = Mock()
    ticker.history.return_value = history
    with (
        patch("src.data.live_quote.yf.Ticker", return_value=ticker),
        patch("src.data.live_quote._now_jst", return_value=NOW),
    ):
        result = fetch_split_adjusted_history("1111.T", "2026-09-01", 100.0)

    assert result.entry_price == pytest.approx(100.0 / 6.0)
    assert [timestamp.date().isoformat() for timestamp in result.daily_highs.index] == dates[1:-1]
    assert result.daily_highs.tolist() == pytest.approx([20.0, 40.0, 40.0, 40.0])


def test_entry_day_allows_empty_raw_history() -> None:
    ticker = Mock()
    ticker.history.return_value = pd.DataFrame()
    with (
        patch("src.data.live_quote.yf.Ticker", return_value=ticker),
        patch("src.data.live_quote._now_jst", return_value=NOW),
    ):
        result = fetch_split_adjusted_history("1111.T", NOW.date().isoformat(), 100.0)

    assert result.entry_price == 100.0
    assert result.daily_highs.empty
    assert result.daily_closes.empty


def test_next_session_allows_no_intervening_daily_history() -> None:
    next_session = datetime(2026, 9, 2, 9, 3, tzinfo=JST)
    ticker = Mock()
    ticker.history.return_value = _daily_history(["2026-09-01", "2026-09-02"])
    with (
        patch("src.data.live_quote.yf.Ticker", return_value=ticker),
        patch("src.data.live_quote._now_jst", return_value=next_session),
    ):
        result = fetch_split_adjusted_history("1111.T", "2026-09-01", 100.0)

    assert result.daily_highs.empty
    assert result.daily_closes.empty


def test_existing_position_requires_complete_prior_daily_history() -> None:
    ticker = Mock()
    ticker.history.return_value = _daily_history(["2026-09-01", "2026-09-02", "2026-09-08"])
    with (
        patch("src.data.live_quote.yf.Ticker", return_value=ticker),
        patch("src.data.live_quote._now_jst", return_value=NOW),
        pytest.raises(ValueError, match="prior confirmed daily history"),
    ):
        fetch_split_adjusted_history("1111.T", "2026-09-01", 100.0)


def test_existing_position_rejects_empty_raw_history() -> None:
    ticker = Mock()
    ticker.history.return_value = pd.DataFrame()
    with (
        patch("src.data.live_quote.yf.Ticker", return_value=ticker),
        patch("src.data.live_quote._now_jst", return_value=NOW),
        pytest.raises(ValueError, match="daily history"),
    ):
        fetch_split_adjusted_history("1111.T", "2026-09-07", 100.0)


def test_today_bars_are_filtered_sorted_and_aggregated() -> None:
    previous_day = NOW - timedelta(days=1)
    index = pd.DatetimeIndex([NOW - timedelta(minutes=1), previous_day, NOW - timedelta(minutes=2)])
    frame = pd.DataFrame(
        {
            "Open": [103.0, 90.0, 100.0],
            "High": [110.0, 95.0, 105.0],
            "Low": [102.0, 85.0, 99.0],
            "Close": [108.0, 92.0, 103.0],
        },
        index=index,
    )
    ticker = Mock()
    ticker.history.return_value = frame
    with (
        patch("src.data.live_quote.yf.Ticker", return_value=ticker),
        patch("src.data.live_quote._now_jst", return_value=NOW),
    ):
        bars = fetch_today_bars("1111.T")

    assert bars is not None
    assert bars.index.tolist() == sorted(index[[0, 2]].tolist())
    quote = build_today_quote(bars)
    assert quote is not None
    assert (quote.open, quote.high_so_far, quote.low_so_far, quote.last_price) == (100.0, 110.0, 99.0, 108.0)
    assert quote.as_of_at == (NOW - timedelta(minutes=1)).isoformat()


def test_today_quote_is_a_thin_bar_wrapper() -> None:
    bars = pd.DataFrame(
        {"Open": [100.0], "High": [105.0], "Low": [99.0], "Close": [103.0]},
        index=pd.DatetimeIndex([NOW - timedelta(minutes=1)]),
    )
    with patch("src.data.live_quote.fetch_today_bars", return_value=bars) as fetch:
        quote = fetch_today_quote("1111.T")

    assert quote is not None
    fetch.assert_called_once_with("1111.T")


@pytest.mark.parametrize(
    "frame",
    [
        pd.DataFrame(),
        pd.DataFrame(
            {"Open": [100.0], "High": [110.0], "Low": [99.0], "Close": [108.0]},
            index=pd.DatetimeIndex(["2026-09-08 09:02"]),
        ),
        pd.DataFrame(
            {"Open": [100.0], "High": [110.0], "Low": [99.0], "Close": [108.0]},
            index=pd.DatetimeIndex([NOW + timedelta(minutes=1)]),
        ),
    ],
)
def test_today_bars_reject_missing_or_untrustworthy_data(frame: pd.DataFrame) -> None:
    ticker = Mock()
    ticker.history.return_value = frame
    with (
        patch("src.data.live_quote.yf.Ticker", return_value=ticker),
        patch("src.data.live_quote._now_jst", return_value=NOW),
    ):
        assert fetch_today_bars("1111.T") is None


def test_today_bars_converts_provider_failure_to_none() -> None:
    ticker = Mock()
    ticker.history.side_effect = RuntimeError("provider unavailable")
    with patch("src.data.live_quote.yf.Ticker", return_value=ticker):
        assert fetch_today_bars("1111.T") is None
