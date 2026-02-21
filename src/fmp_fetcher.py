"""Financial Modeling Prep API クライアント

US 株・JP 株の財務データ（PBR・ROE）を取得し、yfinance / J-Quants の
null を最終フォールバックとして補完する。
FMP_API_KEY が未設定の場合は全関数が {} を返す（degraded mode）。

無料プラン制限: 250 req/日
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://financialmodelingprep.com/api/v3"

_metrics_cache: dict[str, dict] = {}


def fetch_key_metrics(ticker: str) -> dict:
    """ticker（例: "AAPL" または "7203.T"）の最新四半期財務指標を取得する。

    JP 株の場合は ticker をそのまま渡す（FMP は "7203.T" 形式に対応）。

    Returns:
        {"priceToBook": float, "returnOnEquity": float} or {}
    """
    if ticker in _metrics_cache:
        return _metrics_cache[ticker]

    api_key = os.environ.get("FMP_API_KEY")
    if not api_key:
        return {}

    try:
        r = requests.get(
            f"{BASE_URL}/key-metrics/{ticker}",
            params={"period": "quarter", "limit": 1, "apikey": api_key},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            _metrics_cache[ticker] = {}
            return {}

        latest = data[0]
        result = {}
        if (pb := latest.get("pbRatio")) is not None:
            try:
                result["priceToBook"] = float(pb)
            except (ValueError, TypeError):
                pass
        if (roe := latest.get("roe")) is not None:
            try:
                result["returnOnEquity"] = float(roe)  # FMP は小数（0.12 = 12%）
            except (ValueError, TypeError):
                pass
        _metrics_cache[ticker] = result
        return result
    except Exception:
        logger.warning("FMP key-metrics 取得失敗: %s", ticker)
        _metrics_cache[ticker] = {}
        return {}
