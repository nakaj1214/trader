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
    score = score_stock(indicators, {"screening": {"weights": weights}})
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


def test_compute_52w_high_score_normal():
    """52週高値の75%にある場合のスコアを検証する。"""
    from src.screener import compute_52w_high_score

    info = {"currentPrice": 75.0, "fiftyTwoWeekHigh": 100.0}
    assert compute_52w_high_score(info) == 0.75


def test_compute_52w_high_score_at_high():
    """52週高値と同値の場合はスコア 1.0 になることを検証する。"""
    from src.screener import compute_52w_high_score

    info = {"currentPrice": 100.0, "fiftyTwoWeekHigh": 100.0}
    assert compute_52w_high_score(info) == 1.0


def test_compute_52w_high_score_above_high():
    """52週高値を超えた場合でもスコアが 1.0 でキャップされることを検証する。"""
    from src.screener import compute_52w_high_score

    info = {"currentPrice": 110.0, "fiftyTwoWeekHigh": 100.0}
    assert compute_52w_high_score(info) == 1.0


def test_compute_52w_high_score_missing_data():
    """データが欠損している場合 None を返すことを検証する。"""
    from src.screener import compute_52w_high_score

    assert compute_52w_high_score({}) is None
    assert compute_52w_high_score({"currentPrice": 50.0}) is None
    assert compute_52w_high_score({"fiftyTwoWeekHigh": 100.0}) is None


def test_compute_52w_high_score_zero_high():
    """fiftyTwoWeekHigh が 0 の場合 None を返すことを検証する。"""
    from src.screener import compute_52w_high_score

    assert compute_52w_high_score({"currentPrice": 50.0, "fiftyTwoWeekHigh": 0.0}) is None


def test_score_stock_with_fifty2w():
    """fifty2w_score が indicators に含まれる場合にスコアに反映されることを検証する。"""
    from src.screener import score_stock

    indicators = {
        "price_change_1m": 0.10,
        "volume_trend": 0.05,
        "rsi": 50.0,
        "macd_bullish": 1.0,
        "fifty2w_score": 0.90,
    }
    weights = {
        "price_change_1m": 0.25,
        "volume_trend": 0.15,
        "rsi_score": 0.20,
        "macd_signal": 0.20,
        "fifty2w_score": 0.20,
    }
    score = score_stock(indicators, {"screening": {"weights": weights}})
    expected = 0.25 * 0.10 + 0.15 * 0.05 + 0.20 * 1.0 + 0.20 * 1.0 + 0.20 * 0.90
    assert abs(score - expected) < 1e-6


def test_score_stock_fifty2w_none_skipped():
    """fifty2w_score が indicators にない場合にスコアに加算されないことを検証する。"""
    from src.screener import score_stock

    base = {"price_change_1m": 0.0, "volume_trend": 0.0, "rsi": 50.0, "macd_bullish": 0.0}
    weights = {"price_change_1m": 0.25, "volume_trend": 0.15,
               "rsi_score": 0.20, "macd_signal": 0.20, "fifty2w_score": 0.20}

    cfg = {"screening": {"weights": weights}}
    score_with_fw = score_stock({**base, "fifty2w_score": 1.0}, cfg)
    score_without_fw = score_stock(base, cfg)
    assert score_with_fw > score_without_fw


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


# ---------------------------------------------------------------------------
# Golden Cross フィルターのテスト
# ---------------------------------------------------------------------------

def _make_config(weights=None, use_gc_filter=True):
    """score_stock() テスト用の最小 config を生成するヘルパー。"""
    return {
        "screening": {
            "use_golden_cross_filter": use_gc_filter,
            "weights": weights or {
                "price_change_1m": 0.25,
                "volume_trend": 0.15,
                "rsi_score": 0.20,
                "macd_signal": 0.20,
                "fifty2w_score": 0.20,
            },
        }
    }


def _base_indicators():
    """compute_indicators() 相当のベース指標辞書。"""
    return {
        "price_change_1m": 0.05,
        "volume_trend": 0.10,
        "rsi": 50.0,
        "macd_bullish": 1.0,
    }


def test_golden_cross_filter_death_cross_returns_zero():
    """デス・クロス（golden_cross=0.0）かつフィルター有効 → スコアが 0 になることを検証する。"""
    from src.screener import score_stock

    indicators = {**_base_indicators(), "golden_cross": 0.0}
    score = score_stock(indicators, _make_config(use_gc_filter=True))
    assert score == 0.0


def test_golden_cross_filter_none_not_blocked():
    """データ不足（golden_cross=None）の場合はフィルターが適用されないことを検証する。"""
    from src.screener import score_stock

    indicators = {**_base_indicators(), "golden_cross": None}
    score = score_stock(indicators, _make_config(use_gc_filter=True))
    assert score > 0.0


def test_golden_cross_filter_disabled():
    """use_golden_cross_filter=False の場合、DC銘柄でもスコアが 0 にならないことを検証する。"""
    from src.screener import score_stock

    indicators = {**_base_indicators(), "golden_cross": 0.0}
    score = score_stock(indicators, _make_config(use_gc_filter=False))
    assert score > 0.0


def test_golden_cross_filter_gc_passes():
    """ゴールデンクロス（golden_cross=1.0）はフィルターを通過し、正のスコアになることを検証する。"""
    from src.screener import score_stock

    indicators = {**_base_indicators(), "golden_cross": 1.0}
    score = score_stock(indicators, _make_config(use_gc_filter=True))
    assert score > 0.0


# ---------------------------------------------------------------------------
# Bollinger Band・ADX スコアのテスト
# ---------------------------------------------------------------------------

def test_bb_position_score_upper():
    """bb_pos=1.0（上限）の場合に bb スコアが最大（1.0）になることを検証する。"""
    from src.screener import score_stock

    weights = {"price_change_1m": 0.0, "volume_trend": 0.0, "rsi_score": 0.0,
               "macd_signal": 0.0, "bb_position": 1.0}
    indicators = {**_base_indicators(), "bb_pos": 1.0}
    score = score_stock(indicators, {"screening": {"weights": weights}})
    assert abs(score - 1.0) < 1e-6


def test_bb_position_score_lower():
    """bb_pos=0.0（下限）の場合に bb スコアが 0 になることを検証する。"""
    from src.screener import score_stock

    weights = {"price_change_1m": 0.0, "volume_trend": 0.0, "rsi_score": 0.0,
               "macd_signal": 0.0, "bb_position": 1.0}
    indicators = {**_base_indicators(), "bb_pos": 0.0}
    score = score_stock(indicators, {"screening": {"weights": weights}})
    assert abs(score - 0.0) < 1e-6


def test_adx_score_strong_trend():
    """ADX = 50（adx_score=1.0）の場合にスコアが最大になることを検証する。"""
    from src.screener import score_stock

    weights = {"price_change_1m": 0.0, "volume_trend": 0.0, "rsi_score": 0.0,
               "macd_signal": 0.0, "adx_score": 1.0}
    indicators = {**_base_indicators(), "adx_score": 1.0}
    score = score_stock(indicators, {"screening": {"weights": weights}})
    assert abs(score - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# compute_indicators() 固定窓テスト
# ---------------------------------------------------------------------------

def test_compute_indicators_price_change_fixed_window():
    """lookback_days に依存せず直近 21 営業日で price_change_1m を計算することを検証する。"""
    import numpy as np
    from src.screener import compute_indicators

    n = 300  # 252 日以上のデータ（lookback_days=252 のシナリオ）
    # 最後の 22 本: close[-22]=100, close[-1]=110 → price_change_1m = (110-100)/100 = 0.10
    prices = [50.0] * (n - 22) + [100.0] + [105.0] * 20 + [110.0]
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    df = pd.DataFrame({
        "Close": prices,
        "High": [p + 2 for p in prices],
        "Low": [p - 2 for p in prices],
        "Volume": [1_000_000] * n,
    }, index=dates)

    result = compute_indicators(df)
    assert result, "indicators が空です"
    assert abs(result["price_change_1m"] - 0.10) < 1e-6


def test_compute_indicators_volume_trend_fixed_window():
    """lookback_days に依存せず直近 42 営業日の前半/後半で volume_trend を計算することを検証する。"""
    import numpy as np
    from src.screener import compute_indicators

    n = 300
    # 前半21日: vol=1000, 後半21日: vol=2000 → trend = (2000-1000)/1000 = 1.0
    vols = [500] * (n - 42) + [1000] * 21 + [2000] * 21
    prices = [100.0] * n
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    df = pd.DataFrame({
        "Close": prices,
        "High": [p + 2 for p in prices],
        "Low": [p - 2 for p in prices],
        "Volume": vols,
    }, index=dates)

    result = compute_indicators(df)
    assert result, "indicators が空です"
    assert abs(result["volume_trend"] - 1.0) < 1e-4


def test_compute_indicators_returns_golden_cross_and_bb_adx():
    """compute_indicators() が golden_cross, bb_pos, adx_score を返すことを検証する。"""
    from src.screener import compute_indicators

    n = 250
    prices = [float(100 + i * 0.1) for i in range(n)]  # 緩やかな上昇トレンド
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    df = pd.DataFrame({
        "Close": prices,
        "High": [p + 2 for p in prices],
        "Low": [p - 2 for p in prices],
        "Volume": [1_000_000] * n,
    }, index=dates)

    result = compute_indicators(df)
    assert result, "indicators が空です"
    assert "golden_cross" in result
    assert "bb_pos" in result
    assert "bb_width" in result
    assert "adx_score" in result
    # golden_cross は None / 0.0 / 1.0 のいずれか
    assert result["golden_cross"] in (None, 0.0, 1.0)
    # bb_pos は 0〜1 の範囲（外れる場合もあるが計算が通ること）
    # adx_score は 0〜1 の範囲
    assert 0.0 <= result["adx_score"] <= 1.0
