from __future__ import annotations

import logging
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.data.live_quote import (
    build_today_quote,
    fetch_session_bars,
    fetch_split_adjusted_history,
    fetch_today_bars,
    fetch_today_quote,
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


def test_split_history_excludes_entry_and_current_dates() -> None:
    dates = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-07", "2026-09-08"]
    # Yahoo returns auto_adjust=False rows already split-adjusted as of fetch time
    # (e.g. 7203.T closed 2077 the day before its 2021-09-29 1:5 split, raw ~10,000).
    history = _daily_history(dates)
    history["High"] = [20.0, 21.0, 22.0, 23.0, 24.0, 25.0]
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
    assert result.daily_highs.tolist() == pytest.approx([21.0, 22.0, 23.0, 24.0])


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


def test_recovery_requests_a_whole_day_including_the_close_and_returns_its_request_date() -> None:
    index = pd.DatetimeIndex(["2026-09-08 15:25", "2026-09-08 15:30", "2026-09-09 09:00"], tz=JST)
    frame = pd.DataFrame({"Open": [100.0]*3, "High": [100.0]*3, "Low": [80.0,100.0,100.0],
                          "Close": [100.0]*3, "Volume": [10.0]*3}, index=index)
    ticker = Mock()
    ticker.history.return_value = frame
    with patch("src.data.live_quote.yf.Ticker", return_value=ticker):
        result = fetch_session_bars("1111.T", "2026-09-08")
    ticker.history.assert_called_once_with(
        start="2026-09-08", end="2026-09-09", interval="1m", auto_adjust=False,
        actions=False, prepost=False, timeout=15,
    )
    assert result is not None and len(result) == 2
    assert result.attrs["requested_date"] == "2026-09-08"


def test_confirmed_no_trade_day_is_not_a_missing_daily_session() -> None:
    frame = _daily_history(["2026-09-07", "2026-09-08", "2026-09-09"])
    frame["Open"], frame["Low"], frame["Volume"] = 110.0, 100.0, 10.0
    frame.loc[pd.Timestamp("2026-09-08", tz=JST), ["Open", "High", "Low", "Close"]] = float("nan")
    frame.loc[pd.Timestamp("2026-09-08", tz=JST), "Volume"] = 0.0
    ticker = Mock()
    # Match yfinance's real default cleanup: wholly unquoted zero-volume rows are dropped unless keepna=True.
    ticker.history.side_effect = lambda **kwargs: frame if kwargs.get("keepna") else frame.drop(
        pd.Timestamp("2026-09-08", tz=JST)
    )
    with (patch("src.data.live_quote.yf.Ticker", return_value=ticker),
          patch("src.data.live_quote._now_jst", return_value=datetime(2026, 9, 9, 9, 20, tzinfo=JST))):
        result = fetch_split_adjusted_history("1111.T", "2026-09-07", 100.0)
    assert result.daily_highs.empty and result.daily_closes.empty
    assert pd.Timestamp("2026-09-08", tz=JST) in result.daily_bars.index


def test_live_history_provider_cannot_publish_holdings_through_print_logger_or_exception(
    capsys: pytest.CaptureFixture, caplog: pytest.LogCaptureFixture
) -> None:
    hidden = "9999.T purchase=2026-08-04 private-token"
    def fail(**kwargs):
        print(hidden)
        logging.getLogger("fake.credentials").error(hidden)
        raise RuntimeError(hidden)
    ticker = Mock()
    ticker.history.side_effect = fail
    with patch("src.data.live_quote.yf.Ticker", return_value=ticker), pytest.raises(RuntimeError) as error:
        fetch_split_adjusted_history("9999.T", "2026-08-04", 100.0)
    public = capsys.readouterr().out + caplog.text + str(error.value)
    for value in ("9999.T", "2026-08-04", "private-token"):
        assert value not in public
    assert "RuntimeError" in str(error.value)


@pytest.mark.parametrize("fails", [False, True])
def test_private_output_boundary_restores_logging_after_success_and_failure(fails: bool, caplog) -> None:
    from src.data.provider_output import suppress_provider_output

    previous = logging.root.manager.disable
    try:
        with suppress_provider_output():
            logging.getLogger("fake.credentials").error("private-token")
            if fails:
                raise RuntimeError("private-token")
    except RuntimeError:
        pass
    assert logging.root.manager.disable == previous
    logging.getLogger("safe.diagnostics").error("safe provider stage completed")
    assert "private-token" not in caplog.text and "safe provider stage completed" in caplog.text
