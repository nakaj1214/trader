from __future__ import annotations

import logging
from unittest.mock import patch

import pandas as pd
import pytest

from src.data.yfinance_prices import fetch_price_data


def test_scanner_provider_print_and_foreign_logger_are_private(capsys, caplog) -> None:
    hidden = "9999.T 2026-08-04 private-token"
    def fail(*args, **kwargs):
        print(hidden)
        logging.getLogger("fake.provider").error(hidden)
        raise RuntimeError(hidden)
    with patch("src.data.yfinance_prices.yf.download", side_effect=fail):
        assert fetch_price_data(["9999.T"], 30, max_retries=0, sleep=lambda _: None) == {}
    public = capsys.readouterr().out + caplog.text
    assert "9999.T" not in public and "2026-08-04" not in public and "private-token" not in public


def _single_frame(value: float = 100.0) -> pd.DataFrame:
    index = pd.date_range("2026-09-01", periods=3, freq="B")
    return pd.DataFrame(
        {"Open": value, "High": value, "Low": value, "Close": value, "Adj Close": value, "Volume": 1000},
        index=index,
    )


def test_fetch_price_data_uses_explicit_unadjusted_prices() -> None:
    with patch("src.data.yfinance_prices.yf.download", return_value=_single_frame()) as download:
        result = fetch_price_data(["1111.T"], 252, max_retries=0, sleep=lambda _: None)

    assert list(result) == ["1111.T"]
    kwargs = download.call_args.kwargs
    assert kwargs["auto_adjust"] is False
    assert kwargs["actions"] is False


def test_fetch_price_data_retries_provider_exception() -> None:
    with patch(
        "src.data.yfinance_prices.yf.download",
        side_effect=[RuntimeError("temporary"), _single_frame()],
    ) as download:
        result = fetch_price_data(
            ["1111.T"],
            252,
            max_retries=1,
            retry_backoff_seconds=0,
            sleep=lambda _: None,
        )

    assert list(result) == ["1111.T"]
    assert download.call_count == 2


def test_fetch_price_data_retries_only_missing_symbols_from_partial_batch() -> None:
    index = pd.date_range("2026-09-01", periods=3, freq="B")
    columns = pd.MultiIndex.from_product([["1111.T"], ["Open", "High", "Low", "Close", "Adj Close", "Volume"]])
    partial = pd.DataFrame([[100, 100, 100, 100, 100, 1000]] * 3, index=index, columns=columns)

    with patch(
        "src.data.yfinance_prices.yf.download",
        side_effect=[partial, _single_frame(200.0)],
    ) as download:
        result = fetch_price_data(
            ["1111.T", "2222.T"],
            252,
            max_retries=1,
            retry_backoff_seconds=0,
            sleep=lambda _: None,
        )

    assert set(result) == {"1111.T", "2222.T"}
    assert download.call_args_list[1].args[0] == "2222.T"


def test_singleton_multiindex_retry_is_unwrapped() -> None:
    index = pd.date_range("2026-09-01", periods=3, freq="B")
    columns = pd.MultiIndex.from_product(
        [["Close", "High", "Low", "Open", "Adj Close", "Volume"], ["2222.T"]],
        names=["Price", "Ticker"],
    )
    singleton = pd.DataFrame(
        [[200, 200, 200, 200, 200, 1000]] * 3,
        index=index,
        columns=columns,
    )
    with patch("src.data.yfinance_prices.yf.download", return_value=singleton):
        result = fetch_price_data(["2222.T"], 252, max_retries=0, sleep=lambda _: None)

    assert list(result) == ["2222.T"]
    assert float(result["2222.T"]["Close"].iloc[-1]) == 200.0


def test_adjusted_close_keeps_observed_volume_and_raw_turnover_separate() -> None:
    index = pd.date_range("2026-09-01", periods=3, freq="B")
    raw = pd.DataFrame(
        {
            "Open": [100.0, 50.0, 51.0],
            "High": [101.0, 51.0, 52.0],
            "Low": [99.0, 49.0, 50.0],
            "Close": [100.0, 50.0, 51.0],
            "Adj Close": [50.0, 50.0, 51.0],
            "Volume": [1000.0, 2000.0, 2200.0],
        },
        index=index,
    )
    with patch("src.data.yfinance_prices.yf.download", return_value=raw):
        result = fetch_price_data(["1111.T"], 252, max_retries=0, sleep=lambda _: None)["1111.T"]

    assert result["Close"].tolist() == [50.0, 50.0, 51.0]
    assert result["Volume"].tolist() == raw["Volume"].tolist()
    raw_turnover = raw["Close"] * raw["Volume"]
    pd.testing.assert_series_equal(result["Turnover"], raw_turnover, check_names=False)


def test_dividend_adjustment_does_not_change_volume() -> None:
    raw = _single_frame()
    raw["Adj Close"] = [98.0, 100.0, 100.0]

    with patch("src.data.yfinance_prices.yf.download", return_value=raw):
        result = fetch_price_data(["1111.T"], 252, max_retries=0, sleep=lambda _: None)["1111.T"]

    assert result["Volume"].tolist() == [1000, 1000, 1000]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 0.0, -1.0])
@pytest.mark.parametrize("all_rows", [False, True])
def test_invalid_adjusted_prices_never_fall_back_to_raw(value: float, all_rows: bool) -> None:
    frame = _single_frame()
    frame.loc[frame.index if all_rows else frame.index[:1], "Adj Close"] = value
    with patch("src.data.yfinance_prices.yf.download", return_value=frame):
        assert fetch_price_data(["1111.T"], 252, max_retries=0, sleep=lambda _: None) == {}


def test_scanner_retries_invalid_adjustments_and_accepts_recovery() -> None:
    bad = _single_frame()
    bad.loc[bad.index[-1], "Adj Close"] = float("nan")
    with patch("src.data.yfinance_prices.yf.download", side_effect=[bad, _single_frame()]) as download:
        result = fetch_price_data(["1111.T"], 252, max_retries=1, sleep=lambda _: None)
    assert download.call_count == 2
    assert result["1111.T"]["Close"].tolist() == [100.0] * 3


@pytest.mark.parametrize("kind", ["missing_adjusted", "partial_raw_nan", "turnover_overflow", "adjustment_overflow"])
def test_scanner_rejects_missing_and_invalid_normalized_values(kind: str) -> None:
    frame = _single_frame()
    if kind == "missing_adjusted":
        frame = frame.drop(columns=["Adj Close"])
    elif kind == "partial_raw_nan":
        frame.loc[frame.index[0], "Close"] = float("nan")
    elif kind == "turnover_overflow":
        frame["Volume"] = 1e308
    else:
        frame["Close"] = frame["Low"] = 1e-300
        frame["Adj Close"] = 1e300
    with patch("src.data.yfinance_prices.yf.download", return_value=frame):
        assert fetch_price_data(["1111.T"], 252, max_retries=0, sleep=lambda _: None) == {}


def test_scanner_omits_an_unquoted_zero_volume_bar_but_keeps_valid_prices() -> None:
    frame = _single_frame()
    frame.loc[frame.index[1], ["Open", "High", "Low", "Close", "Adj Close"]] = float("nan")
    frame.loc[frame.index[1], "Volume"] = 0
    with patch("src.data.yfinance_prices.yf.download", return_value=frame):
        result = fetch_price_data(["1111.T"], 252, max_retries=0, sleep=lambda _: None)
    pd.testing.assert_index_equal(result["1111.T"].index, frame.index[[0, 2]])


def test_valid_adjusted_flat_ohlc_is_not_rejected_for_floating_point_roundoff() -> None:
    frame = _single_frame(618.99)
    frame["Adj Close"] = 854.06  # 618.99 * (854.06 / 618.99) = 854.0599999999998.
    with patch("src.data.yfinance_prices.yf.download", return_value=frame):
        result = fetch_price_data(["1111.T"], 252, max_retries=0, sleep=lambda _: None)
    assert result["1111.T"]["Close"].tolist() == [854.06] * 3
