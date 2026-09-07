from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from src.data.yfinance_prices import fetch_price_data


def _single_frame(value: float = 100.0) -> pd.DataFrame:
    index = pd.date_range("2026-09-01", periods=3, freq="B")
    return pd.DataFrame({"Open": value, "High": value, "Low": value, "Close": value, "Volume": 1000}, index=index)


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
