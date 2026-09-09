from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.data.live_quote import fetch_split_adjusted_history, fetch_today_quote, split_adjust_ohlc

JST = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 9, 8, 9, 3, tzinfo=JST)


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

    assert adjusted.loc[index[0], ["Open", "High", "Low", "Close"]].tolist() == pytest.approx(
        [50.0, 55.0, 45.0, 50.0]
    )
    assert adjusted.loc[index[1], "Close"] == 55.0
    assert adjusted["Dividends"].tolist() == [10.0, 0.0]


def test_split_history_uses_date_specific_factors_and_excludes_today_bar() -> None:
    index = pd.DatetimeIndex(
        ["2026-09-01", "2026-09-03", "2026-09-05", "2026-09-08"], tz=JST
    )
    history = pd.DataFrame(
        {
            "High": [120.0, 60.0, 70.0, 30.0],
            "Close": [110.0, 55.0, 65.0, 28.0],
            "Dividends": [0.0, 10.0, 0.0, 0.0],
            "Stock Splits": [0.0, 2.0, 0.0, 3.0],
        },
        index=index,
    )
    ticker = Mock()
    ticker.history.return_value = history
    with patch("src.data.live_quote.yf.Ticker", return_value=ticker), patch(
        "src.data.live_quote._now_jst", return_value=NOW
    ):
        result = fetch_split_adjusted_history("1111.T", "2026-09-01", 100.0)

    assert result.entry_price == pytest.approx(100.0 / 6.0)
    assert result.daily_highs.tolist() == pytest.approx([20.0, 20.0, 70.0 / 3.0])
    assert result.daily_closes.tolist() == pytest.approx([110.0 / 6.0, 55.0 / 3.0, 65.0 / 3.0])
    assert all(timestamp.date() < NOW.date() for timestamp in result.daily_highs.index)


def test_today_quote_uses_last_bar_timestamp_and_aggregates_session() -> None:
    index = pd.DatetimeIndex([NOW - timedelta(minutes=2), NOW - timedelta(minutes=1)])
    frame = pd.DataFrame(
        {"Open": [100.0, 103.0], "High": [105.0, 110.0], "Low": [99.0, 102.0], "Close": [103.0, 108.0]},
        index=index,
    )
    ticker = Mock()
    ticker.history.return_value = frame
    with patch("src.data.live_quote.yf.Ticker", return_value=ticker), patch(
        "src.data.live_quote._now_jst", return_value=NOW
    ):
        quote = fetch_today_quote("1111.T")

    assert quote is not None
    assert quote.open == 100.0
    assert quote.high_so_far == 110.0
    assert quote.low_so_far == 99.0
    assert quote.last_price == 108.0
    assert quote.as_of_at == index[-1].isoformat()


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
        pd.DataFrame(
            {"Open": [100.0], "High": [101.0], "Low": [99.0], "Close": [108.0]},
            index=pd.DatetimeIndex([NOW - timedelta(minutes=1)]),
        ),
    ],
)
def test_today_quote_rejects_missing_or_untrustworthy_bars(frame: pd.DataFrame) -> None:
    ticker = Mock()
    ticker.history.return_value = frame
    with patch("src.data.live_quote.yf.Ticker", return_value=ticker), patch(
        "src.data.live_quote._now_jst", return_value=NOW
    ):
        assert fetch_today_quote("1111.T") is None


def test_today_quote_converts_provider_failure_to_none() -> None:
    ticker = Mock()
    ticker.history.side_effect = RuntimeError("provider unavailable")
    with patch("src.data.live_quote.yf.Ticker", return_value=ticker):
        assert fetch_today_quote("1111.T") is None


def test_existing_position_requires_prior_daily_history() -> None:
    ticker = Mock()
    ticker.history.return_value = pd.DataFrame()
    with patch("src.data.live_quote.yf.Ticker", return_value=ticker), patch(
        "src.data.live_quote._now_jst", return_value=NOW
    ), pytest.raises(ValueError, match="daily history"):
        fetch_split_adjusted_history("1111.T", "2026-09-07", 100.0)
