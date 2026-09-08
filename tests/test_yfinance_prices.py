from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from src.data.yfinance_prices import fetch_price_data


def _single_frame(value: float = 100.0) -> pd.DataFrame:
    index = pd.date_range("2026-09-01", periods=3, freq="B")
    return pd.DataFrame(
        {"Open": value, "High": value, "Low": value, "Close": value, "Volume": 1000},
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
    columns = pd.MultiIndex.from_product([["1111.T"], ["Open", "High", "Low", "Close", "Volume"]])
    partial = pd.DataFrame([[100, 100, 100, 100, 1000]] * 3, index=index, columns=columns)

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
        [["Close", "High", "Low", "Open", "Volume"], ["2222.T"]],
        names=["Price", "Ticker"],
    )
    singleton = pd.DataFrame(
        [[200, 200, 200, 200, 1000]] * 3,
        index=index,
        columns=columns,
    )
    with patch("src.data.yfinance_prices.yf.download", return_value=singleton):
        result = fetch_price_data(["2222.T"], 252, max_retries=0, sleep=lambda _: None)

    assert list(result) == ["2222.T"]
    assert float(result["2222.T"]["Close"].iloc[-1]) == 200.0


def test_adj_close_normalizes_split_without_changing_turnover() -> None:
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
    raw_turnover = raw["Close"] * raw["Volume"]
    normalized_turnover = result["Close"] * result["Volume"]
    pd.testing.assert_series_equal(normalized_turnover, raw_turnover, check_names=False)
