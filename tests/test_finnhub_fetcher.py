"""Finnhub API クライアントのテスト（モック使用）"""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestFetchNewsSentiment:
    def setup_method(self):
        """各テスト前にキャッシュをリセットする。"""
        import src.finnhub_fetcher as fh
        fh._sentiment_cache = {}

    def test_returns_empty_when_no_api_key(self):
        """FINNHUB_API_KEY 未設定 → {} を返す。"""
        env = {k: v for k, v in os.environ.items() if k != "FINNHUB_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            from src.finnhub_fetcher import fetch_news_sentiment
            result = fetch_news_sentiment("AAPL")
        assert result == {}

    def test_bullish_signal_when_bullish_pct_high(self):
        """bullishPercent >= 0.60 → signal="bullish" になること。"""
        import src.finnhub_fetcher as fh

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "companyNewsScore": 0.72,
            "sentiment": {"bullishPercent": 0.75, "bearishPercent": 0.25},
            "buzz": {"weeklyAverage": 5.2},
        }
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.dict(os.environ, {"FINNHUB_API_KEY": "test_key"}),
            patch("src.finnhub_fetcher.requests.get", return_value=mock_resp),
        ):
            from src.finnhub_fetcher import fetch_news_sentiment
            result = fetch_news_sentiment("AAPL")

        assert result["signal"] == "bullish"
        assert result["bullish_pct"] == pytest.approx(0.75)

    def test_bearish_signal_when_bearish_pct_high(self):
        """bearishPercent >= 0.60 → signal="bearish" になること。"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "companyNewsScore": 0.30,
            "sentiment": {"bullishPercent": 0.35, "bearishPercent": 0.65},
            "buzz": {"weeklyAverage": 3.0},
        }
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.dict(os.environ, {"FINNHUB_API_KEY": "test_key"}),
            patch("src.finnhub_fetcher.requests.get", return_value=mock_resp),
        ):
            from src.finnhub_fetcher import fetch_news_sentiment
            result = fetch_news_sentiment("META")

        assert result["signal"] == "bearish"

    def test_neutral_signal_when_neither_threshold_met(self):
        """どちらの閾値も未満 → signal="neutral" になること。"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "companyNewsScore": 0.50,
            "sentiment": {"bullishPercent": 0.55, "bearishPercent": 0.45},
            "buzz": {"weeklyAverage": 2.0},
        }
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.dict(os.environ, {"FINNHUB_API_KEY": "test_key"}),
            patch("src.finnhub_fetcher.requests.get", return_value=mock_resp),
        ):
            from src.finnhub_fetcher import fetch_news_sentiment
            result = fetch_news_sentiment("MSFT")

        assert result["signal"] == "neutral"

    def test_returns_empty_on_request_error(self):
        """API エラー時でも {} を返し、処理が継続する。"""
        with (
            patch.dict(os.environ, {"FINNHUB_API_KEY": "test_key"}),
            patch("src.finnhub_fetcher.requests.get", side_effect=Exception("timeout")),
        ):
            from src.finnhub_fetcher import fetch_news_sentiment
            result = fetch_news_sentiment("GOOG")

        assert result == {}

    def test_cache_prevents_duplicate_calls(self):
        """同じティッカーの 2 回目以降はキャッシュを返す。"""
        import src.finnhub_fetcher as fh
        fh._sentiment_cache["AAPL"] = {"signal": "bullish", "score": 0.8,
                                        "bullish_pct": 0.8, "bearish_pct": 0.2,
                                        "weekly_buzz": 5.0}

        with patch("src.finnhub_fetcher.requests.get") as mock_get:
            from src.finnhub_fetcher import fetch_news_sentiment
            result = fetch_news_sentiment("AAPL")

        mock_get.assert_not_called()
        assert result["signal"] == "bullish"
