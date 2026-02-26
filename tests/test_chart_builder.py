"""chart_builder のテスト: PNG 生成、データ不足時の安全処理。"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# @patch デコレータ解決のためモジュールを事前インポート
import src.chart_builder  # noqa: F401


def _make_df(n: int) -> pd.DataFrame:
    """テスト用 OHLCV DataFrame を生成するヘルパー。"""
    prices = [float(100 + i * 0.1) for i in range(n)]
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "Close": prices,
            "Open": [p - 0.5 for p in prices],
            "High": [p + 2 for p in prices],
            "Low": [p - 2 for p in prices],
            "Volume": [1_000_000] * n,
        },
        index=dates,
    )


CONFIG = {
    "notifications": {"chart_lookback_days": 60},
}


@patch("src.chart_builder.yf.download")
def test_build_stock_chart_returns_png_bytes(mock_download):
    """十分なデータがある場合に PNG バイト列を返すことを検証する。"""
    from src.chart_builder import build_stock_chart

    mock_download.return_value = _make_df(400)

    result = build_stock_chart("AAPL", 252, CONFIG)

    assert result is not None
    assert isinstance(result, bytes)
    # PNG マジックバイト確認
    assert result[:8] == b"\x89PNG\r\n\x1a\n"


@patch("src.chart_builder.yf.download")
def test_build_stock_chart_insufficient_data_returns_none(mock_download):
    """データが 20 本未満の場合に None を返し、例外を起こさないことを検証する。"""
    from src.chart_builder import build_stock_chart

    mock_download.return_value = _make_df(10)

    result = build_stock_chart("AAPL", 252, CONFIG)

    assert result is None


@patch("src.chart_builder.yf.download")
def test_build_stock_chart_empty_data_returns_none(mock_download):
    """データが空の場合に None を返すことを検証する。"""
    from src.chart_builder import build_stock_chart

    mock_download.return_value = pd.DataFrame()

    result = build_stock_chart("AAPL", 252, CONFIG)

    assert result is None


@patch("src.chart_builder.yf.download")
def test_build_stock_chart_download_error_returns_none(mock_download):
    """yfinance 取得エラー時に None を返し、例外を伝播させないことを検証する。"""
    from src.chart_builder import build_stock_chart

    mock_download.side_effect = Exception("network error")

    result = build_stock_chart("AAPL", 252, CONFIG)

    assert result is None


@patch("src.chart_builder.yf.download")
def test_build_stock_chart_fetch_period_uses_calendar_factor(mock_download):
    """データ取得時にカレンダー日補正（× 1.5）が適用されることを検証する。"""
    from src.chart_builder import build_stock_chart

    mock_download.return_value = _make_df(400)

    build_stock_chart("AAPL", 252, CONFIG)

    call_kwargs = mock_download.call_args
    # max(60, 252) * 1.5 = 378d が period として渡される
    period_used = call_kwargs.kwargs.get("period") or call_kwargs.args[1] if call_kwargs.args else None
    if period_used is None:
        period_used = call_kwargs.kwargs.get("period")
    assert period_used == "378d"
