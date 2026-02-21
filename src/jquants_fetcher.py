"""J-Quants API クライアント

日本株の財務データ（PBR・ROE・EPS・配当・営業利益率等）、銘柄マスタ、価格系列を取得する。
JQUANTS_API_KEY または JQUANTS_MAIL_ADDRESS + JQUANTS_PASSWORD が未設定の場合は
全関数が {} / None / 空 DataFrame を返す（degraded mode）。

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

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL_V2 = "https://api.jquants.com/v2"
BASE_URL_V1 = "https://api.jquants.com/v1"

# セッション内キャッシュ（再実行時の重複取得を防ぐ）
_id_token_cache: str | None = None
_financial_cache: dict[str, dict] = {}
_earnings_cache: dict[str, dict | None] = {}
_listed_info_cache: dict[str, dict] = {}
_price_series_cache: dict[str, pd.DataFrame] = {}


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


def _to_code(ticker: str) -> str:
    """yfinance 形式 "7203.T" → J-Quants は "72030"（4桁ゼロ埋め + 末尾 0）に変換。"""
    return ticker.replace(".T", "").zfill(4) + "0"


def _base_url() -> str:
    return BASE_URL_V2 if os.environ.get("JQUANTS_API_KEY") else BASE_URL_V1


def fetch_financial_data(ticker: str) -> dict:
    """ticker（例: "7203.T"）の最新四半期財務データを取得する（V2/V1 自動選択）。

    Returns:
        {
            "priceToBook": float,       # PBR
            "returnOnEquity": float,    # ROE（小数。例: 0.12 = 12%）
            "eps": float,               # EPS 一株当たり当期純利益（実績）
            "forecast_eps": float,      # FEPS 今期予想 EPS
            "dividend_annual": float,   # DivAnn 年間配当（円）
            "payout_ratio": float,      # PayoutRatioAnn 配当性向（小数）
            "operating_margin": float,  # OP/Sales 営業利益率（小数）
            "cfo": float,               # CFO 営業キャッシュフロー（円）
        }
        取得できなかったキーは含まれない。認証情報なし・エラー時は {}。
    """
    if ticker in _financial_cache:
        return _financial_cache[ticker]

    auth_header = _get_auth_header()
    if not auth_header:
        return {}

    code = _to_code(ticker)
    try:
        r = requests.get(
            f"{_base_url()}/fins/statements",
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
        result: dict = {}

        def _try_float(key: str) -> float | None:
            val = latest.get(key)
            if val is None:
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        # --- 既存フィールド（Phase 17） ---
        if (pbr := _try_float("PBR")) is not None:
            result["priceToBook"] = pbr
        if (roe := _try_float("ROEAfterTax")) is not None:
            result["returnOnEquity"] = roe / 100.0  # % → 小数

        # --- 追加フィールド（sample_data_v2 連携） ---
        if (eps := _try_float("EPS")) is not None:
            result["eps"] = eps

        if (feps := _try_float("FEPS")) is not None:
            result["forecast_eps"] = feps

        if (div := _try_float("DivAnn")) is not None:
            result["dividend_annual"] = div

        if (pr := _try_float("PayoutRatioAnn")) is not None:
            result["payout_ratio"] = pr / 100.0  # % → 小数

        # 営業利益率 = OP / Sales（両方が取れた場合のみ）
        op = _try_float("OP")
        sales = _try_float("Sales")
        if op is not None and sales is not None and sales > 0:
            result["operating_margin"] = op / sales

        if (cfo := _try_float("CFO")) is not None:
            result["cfo"] = cfo

        _financial_cache[ticker] = result
        return result
    except Exception:
        logger.warning("J-Quants fins/statements 取得失敗: %s", ticker)
        _financial_cache[ticker] = {}
        return {}


def fetch_listed_info(ticker: str) -> dict:
    """ticker（例: "7203.T"）の銘柄マスタ情報を取得する。

    J-Quants /listed/info エンドポイントを使用。
    Listed Issue Master.csv（sample_data_v2）に相当するデータ。

    Returns:
        {
            "company_name": str,      # CoName   会社名
            "sector_17": str,         # S17Nm    17業種分類名
            "sector_33": str,         # S33Nm    33業種分類名
            "market_section": str,    # MktNm    市場区分（プライム/スタンダード/グロース）
            "scale_category": str,    # ScaleCat 規模区分（TOPIX Large70 等）
        }
        認証情報なし・エラー時は {}。
    """
    if ticker in _listed_info_cache:
        return _listed_info_cache[ticker]

    auth_header = _get_auth_header()
    if not auth_header:
        return {}

    code = _to_code(ticker)
    try:
        r = requests.get(
            f"{_base_url()}/listed/info",
            params={"code": code},
            headers=auth_header,
            timeout=10,
        )
        r.raise_for_status()
        info_list = r.json().get("info", [])
        if not info_list:
            _listed_info_cache[ticker] = {}
            return {}

        record = info_list[0]
        result = {}
        for src_key, dst_key in [
            ("CoName",   "company_name"),
            ("S17Nm",    "sector_17"),
            ("S33Nm",    "sector_33"),
            ("MktNm",    "market_section"),
            ("ScaleCat", "scale_category"),
        ]:
            val = record.get(src_key)
            if val is not None:
                result[dst_key] = str(val)

        _listed_info_cache[ticker] = result
        return result
    except Exception:
        logger.warning("J-Quants listed/info 取得失敗: %s", ticker)
        _listed_info_cache[ticker] = {}
        return {}


def fetch_price_series(
    ticker: str,
    from_date: str,
    to_date: str,
) -> pd.DataFrame:
    """ticker の株価時系列（分割調整済み）を取得する。

    J-Quants /prices/daily_quotes エンドポイントを使用。
    Stock Prices (OHLC).csv（sample_data_v2）に相当するデータ。

    AdjustmentClose（AdjC）は分割・配当調整済み終値であり、
    yfinance "Close" の配当落ち疑似下落問題を根本的に解消する。

    Args:
        ticker:    yfinance 形式（例: "7203.T"）
        from_date: "YYYYMMDD" 形式（例: "20240101"）
        to_date:   "YYYYMMDD" 形式（例: "20241231"）

    Returns:
        DataFrame with index=Date（DatetimeIndex）and columns:
            Open, High, Low, Close, Volume,
            AdjustmentFactor, AdjustmentClose, AdjustmentVolume
        認証情報なし・データなし・エラー時は空 DataFrame。

    Note:
        将来的に screener/predictor で yfinance の JP 株価データを
        このデータに切り替えることで price_column 問題を根本解決できる。
        現在は screener/predictor の yfinance 呼び出しはそのまま維持し、
        本関数は追加データソースとして利用する。
    """
    cache_key = f"{ticker}:{from_date}:{to_date}"
    if cache_key in _price_series_cache:
        return _price_series_cache[cache_key]

    auth_header = _get_auth_header()
    if not auth_header:
        return pd.DataFrame()

    code = _to_code(ticker)
    try:
        r = requests.get(
            f"{_base_url()}/prices/daily_quotes",
            params={"code": code, "from": from_date, "to": to_date},
            headers=auth_header,
            timeout=15,
        )
        r.raise_for_status()
        quotes = r.json().get("daily_quotes", [])
        if not quotes:
            _price_series_cache[cache_key] = pd.DataFrame()
            return pd.DataFrame()

        df = pd.DataFrame(quotes)

        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date").sort_index()

        numeric_cols = [
            "Open", "High", "Low", "Close", "Volume",
            "AdjustmentFactor", "AdjustmentClose", "AdjustmentVolume",
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        _price_series_cache[cache_key] = df
        return df
    except Exception:
        logger.warning("J-Quants prices/daily_quotes 取得失敗: %s", ticker)
        _price_series_cache[cache_key] = pd.DataFrame()
        return pd.DataFrame()


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

    code = _to_code(ticker)
    try:
        r = requests.get(
            f"{_base_url()}/fins/announcement",
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
