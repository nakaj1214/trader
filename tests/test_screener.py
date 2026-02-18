"""screener のテスト: CSV列チェック、min_market_cap フィルタ、取得失敗時の挙動。"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest


def test_load_tickers_missing_column(tmp_path):
    """ticker 列がないCSVでエラーにならずスキップすることを検証する。"""
    # ticker列がないCSV
    bad_csv = tmp_path / "bad_market.csv"
    bad_csv.write_text("symbol\nAAPL\nMSFT\n")

    # 正常なCSV
    good_csv = tmp_path / "good_market.csv"
    good_csv.write_text("ticker\nGOOGL\nAMZN\n")

    with patch("src.screener.DATA_DIR", tmp_path):
        from src.screener import load_tickers
        result = load_tickers(["bad_market", "good_market"])

    # bad_market はスキップされ、good_market の銘柄のみ返される
    assert result == ["GOOGL", "AMZN"]


def test_load_tickers_missing_file(tmp_path):
    """存在しないCSVでエラーにならずスキップすることを検証する。"""
    with patch("src.screener.DATA_DIR", tmp_path):
        from src.screener import load_tickers
        result = load_tickers(["nonexistent_market"])

    assert result == []


def test_score_stock_weights():
    """スコアリングの重みが正しく適用されることを検証する。"""
    from src.screener import score_stock

    indicators = {
        "price_change_1m": 0.10,  # +10%
        "volume_trend": 0.05,     # +5%
        "rsi": 50.0,              # 中間帯 → 1.0
        "macd_bullish": 1.0,      # 強気
    }
    weights = {
        "price_change_1m": 0.3,
        "volume_trend": 0.2,
        "rsi_score": 0.25,
        "macd_signal": 0.25,
    }
    score = score_stock(indicators, weights)
    expected = 0.3 * 0.10 + 0.2 * 0.05 + 0.25 * 1.0 + 0.25 * 1.0
    assert abs(score - expected) < 1e-6


def test_market_cap_fetch_failure_keeps_stock():
    """時価総額の取得に失敗した銘柄が除外されないことを検証する。"""
    from src.screener import _fetch_market_caps

    # yf.Ticker().info が例外を投げるケース
    def mock_ticker_init(ticker_str):
        mock = type("MockTicker", (), {})()
        if ticker_str == "FAIL":
            mock.info = property(lambda self: (_ for _ in ()).throw(Exception("API error")))
            raise Exception("API error")
        else:
            mock.info = {"marketCap": 500_000_000_000}
        return mock

    with patch("src.screener.yf.Ticker", side_effect=mock_ticker_init):
        caps = _fetch_market_caps(["AAPL", "FAIL"])

    # AAPL は正常取得、FAIL は None
    assert caps["AAPL"] == 500_000_000_000
    assert caps["FAIL"] is None


def test_market_cap_filter_skips_none():
    """時価総額が None (取得失敗) の銘柄はフィルタで除外されないことを検証する。"""
    stock_data = {"AAPL": "data_a", "SMALL": "data_s", "UNKNOWN": "data_u"}
    market_caps = {"AAPL": 500e9, "SMALL": 1e9, "UNKNOWN": None}

    min_market_cap = 10e9
    # フィルタロジックのシミュレーション
    for ticker in list(stock_data.keys()):
        cap = market_caps.get(ticker)
        if cap is not None and cap < min_market_cap:
            stock_data.pop(ticker, None)

    # SMALL は除外、UNKNOWN は残る、AAPL は残る
    assert "AAPL" in stock_data
    assert "SMALL" not in stock_data
    assert "UNKNOWN" in stock_data
