"""J-Quants API クライアント

日本株の財務データ（PBR・ROE）を取得し、yfinance の null を補完する。
JQUANTS_API_KEY または JQUANTS_MAIL_ADDRESS + JQUANTS_PASSWORD が未設定の場合は
全関数が {} / None を返す（degraded mode）。

認証フロー（V2 優先 - Phase 22）:
  V2: JQUANTS_API_KEY を Bearer トークンとして直接使用
  V1 フォールバック（後方互換）:
    1. POST /v1/token/auth_user (mail + password) → refresh_token
    2. POST /v1/token/auth_refresh (refresh_token) → id_token
    3. GET  /v1/fins/statements?code=<5桁コード> (Authorization: Bearer <id_token>)
"""

import logging
import os
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

BASE_URL_V2 = "https://api.jquants.com/v2"
BASE_URL_V1 = "https://api.jquants.com/v1"

# セッション内キャッシュ（再実行時の重複取得を防ぐ）
_id_token_cache: str | None = None
_financial_cache: dict[str, dict] = {}
_earnings_cache: dict[str, dict | None] = {}


def _get_id_token() -> str | None:
    """J-Quants id_token を取得する（V1 トークンフロー、セッション内キャッシュあり）。"""
    global _id_token_cache
    if _id_token_cache:
        return _id_token_cache
    mail = os.environ.get("JQUANTS_MAIL_ADDRESS")
    password = os.environ.get("JQUANTS_PASSWORD")
    if not mail or not password:
        return None
    try:
        # Step 1: refresh_token
        r = requests.post(
            f"{BASE_URL_V1}/token/auth_user",
            json={"mailaddress": mail, "password": password},
            timeout=10,
        )
        r.raise_for_status()
        refresh_token = r.json()["refreshToken"]
        # Step 2: id_token
        r2 = requests.post(
            f"{BASE_URL_V1}/token/auth_refresh",
            params={"refreshtoken": refresh_token},
            timeout=10,
        )
        r2.raise_for_status()
        _id_token_cache = r2.json()["idToken"]
        return _id_token_cache
    except Exception:
        logger.warning("J-Quants 認証失敗（JQUANTS_MAIL_ADDRESS / JQUANTS_PASSWORD を確認）")
        return None


def _get_auth_header() -> dict | None:
    """V2（APIキー）または V1（トークンフロー）の認証ヘッダーを返す（Phase 22）。

    V2 優先: JQUANTS_API_KEY が設定されていれば直接 Bearer で使用。
    V1 フォールバック: JQUANTS_MAIL_ADDRESS + JQUANTS_PASSWORD から idToken を取得。
    どちらも未設定 → None を返す（degraded mode）。
    """
    api_key = os.environ.get("JQUANTS_API_KEY")
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}
    # V1 フォールバック（後方互換）
    id_token = _get_id_token()
    if id_token:
        return {"Authorization": f"Bearer {id_token}"}
    return None


def fetch_financial_data(ticker: str) -> dict:
    """ticker（例: "7203.T"）の最新四半期財務データを取得する（V2/V1 自動選択）。

    yfinance 形式 "7203.T" → J-Quants は "72030"（4桁 + 末尾 0）に変換。

    Returns:
        {"priceToBook": float, "returnOnEquity": float} or {}
    """
    if ticker in _financial_cache:
        return _financial_cache[ticker]

    auth_header = _get_auth_header()
    if not auth_header:
        return {}

    base_url = BASE_URL_V2 if os.environ.get("JQUANTS_API_KEY") else BASE_URL_V1
    # "7203.T" → "72030"（4桁ゼロ埋め + 末尾 0）
    code = ticker.replace(".T", "").zfill(4) + "0"
    try:
        r = requests.get(
            f"{base_url}/fins/statements",
            params={"code": code},
            headers=auth_header,
            timeout=15,
        )
        r.raise_for_status()
        statements = r.json().get("statements", [])
        if not statements:
            _financial_cache[ticker] = {}
            return {}

        # 最新レコードを使用
        latest = statements[-1]
        result = {}
        if (pbr := latest.get("PBR")) is not None:
            try:
                result["priceToBook"] = float(pbr)
            except (ValueError, TypeError):
                pass
        if (roe := latest.get("ROEAfterTax")) is not None:
            try:
                result["returnOnEquity"] = float(roe) / 100.0  # % → 小数
            except (ValueError, TypeError):
                pass
        _financial_cache[ticker] = result
        return result
    except Exception:
        logger.warning("J-Quants fins/statements 取得失敗: %s", ticker)
        _financial_cache[ticker] = {}
        return {}


def fetch_earnings_calendar(ticker: str) -> dict | None:
    """ticker（例: "7203.T"）の次回決算発表予定を取得する（Phase 24）。

    Returns:
        {"announcement_date": "2026-05-10", "days_to_earnings": 78} or None（未取得・エラー）
    """
    if ticker in _earnings_cache:
        return _earnings_cache[ticker]

    auth_header = _get_auth_header()
    if not auth_header:
        _earnings_cache[ticker] = None
        return None

    base_url = BASE_URL_V2 if os.environ.get("JQUANTS_API_KEY") else BASE_URL_V1
    code = ticker.replace(".T", "").zfill(4) + "0"
    try:
        r = requests.get(
            f"{base_url}/fins/announcement",
            params={"code": code},
            headers=auth_header,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json().get("announcement", [])
        if not data:
            _earnings_cache[ticker] = None
            return None

        # 最も近い未来の決算日を取得
        today = datetime.now().date()
        future = [
            d for d in data
            if d.get("Date") and datetime.strptime(d["Date"], "%Y-%m-%d").date() >= today
        ]
        if not future:
            _earnings_cache[ticker] = None
            return None

        next_date = min(future, key=lambda d: d["Date"])
        days = (datetime.strptime(next_date["Date"], "%Y-%m-%d").date() - today).days
        result = {"announcement_date": next_date["Date"], "days_to_earnings": days}
        _earnings_cache[ticker] = result
        return result
    except Exception:
        logger.warning("J-Quants 決算カレンダー取得失敗: %s", ticker)
        _earnings_cache[ticker] = None
        return None
