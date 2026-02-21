"""Finnhub API クライアント

US 株のニュース・センチメントデータを取得する。
FINNHUB_API_KEY が未設定の場合は全関数が {} を返す（degraded mode）。

無料プラン: 60 req/分
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://finnhub.io/api/v1"

_sentiment_cache: dict[str, dict] = {}


def fetch_news_sentiment(ticker: str) -> dict:
    """ticker（例: "AAPL"）のニュース・センチメントを取得する。

    Returns:
        {
            "score": float,         # companyNewsScore (0〜1)
            "bullish_pct": float,   # bullishPercent
            "bearish_pct": float,   # bearishPercent
            "weekly_buzz": float,   # buzz.weeklyAverage
            "signal": str           # "bullish" / "neutral" / "bearish"
        }
        or {} （APIキー未設定・エラー時）
    """
    if ticker in _sentiment_cache:
        return _sentiment_cache[ticker]

    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        return {}

    try:
        r = requests.get(
            f"{BASE_URL}/news-sentiment",
            params={"symbol": ticker, "token": api_key},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

        sentiment = data.get("sentiment", {})
        buzz = data.get("buzz", {})
        bullish = sentiment.get("bullishPercent", 0.5)
        bearish = sentiment.get("bearishPercent", 0.5)

        if bullish >= 0.60:
            signal = "bullish"
        elif bearish >= 0.60:
            signal = "bearish"
        else:
            signal = "neutral"

        result = {
            "score": data.get("companyNewsScore"),
            "bullish_pct": bullish,
            "bearish_pct": bearish,
            "weekly_buzz": buzz.get("weeklyAverage"),
            "signal": signal,
        }
        _sentiment_cache[ticker] = result
        return result
    except Exception:
        logger.warning("Finnhub センチメント取得失敗: %s", ticker)
        _sentiment_cache[ticker] = {}
        return {}
