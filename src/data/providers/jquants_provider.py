"""J-Quants data provider: Japanese stock fundamentals and prices.

Supports V2 (API key) and V1 (mail/password) authentication.
Returns empty results when credentials are missing (degraded mode).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import pandas as pd
import requests
import structlog

from src.data.providers.base import DataProvider, provider_retry

logger = structlog.get_logger(__name__)

BASE_URL_V2 = "https://api.jquants.com/v2"
BASE_URL_V1 = "https://api.jquants.com/v1"


class JQuantsProvider(DataProvider):
    """Data provider for Japanese stock data via J-Quants API."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._id_token: str | None = None

    @property
    def name(self) -> str:
        return "jquants"

    def is_available(self) -> bool:
        """Check if J-Quants credentials are configured."""
        if os.environ.get("JQUANTS_API_KEY"):
            return True
        if os.environ.get("JQUANTS_MAIL_ADDRESS") and os.environ.get("JQUANTS_PASSWORD"):
            return True
        return False

    def _get_auth_header(self) -> dict[str, str] | None:
        """Get authorization header (V2 API key preferred, V1 fallback)."""
        api_key = os.environ.get("JQUANTS_API_KEY")
        if api_key:
            return {"Authorization": f"Bearer {api_key}"}

        id_token = self._get_id_token()
        if id_token:
            return {"Authorization": f"Bearer {id_token}"}
        return None

    def _get_id_token(self) -> str | None:
        """Obtain V1 id_token via refresh token flow."""
        if self._id_token:
            return self._id_token

        mail = os.environ.get("JQUANTS_MAIL_ADDRESS")
        password = os.environ.get("JQUANTS_PASSWORD")
        if not mail or not password:
            return None

        try:
            r = requests.post(
                f"{BASE_URL_V1}/token/auth_user",
                json={"mailaddress": mail, "password": password},
                timeout=10,
            )
            r.raise_for_status()
            refresh_token = r.json()["refreshToken"]

            r2 = requests.post(
                f"{BASE_URL_V1}/token/auth_refresh",
                params={"refreshtoken": refresh_token},
                timeout=10,
            )
            r2.raise_for_status()
            self._id_token = r2.json()["idToken"]
            return self._id_token
        except Exception:
            logger.warning("jquants_auth_failed")
            return None

    def _base_url(self) -> str:
        return BASE_URL_V2 if os.environ.get("JQUANTS_API_KEY") else BASE_URL_V1

    @staticmethod
    def _to_code(ticker: str) -> str:
        """Convert yfinance format '7203.T' to J-Quants '72030'."""
        return ticker.replace(".T", "").zfill(4) + "0"

    @provider_retry
    def fetch_info(self, ticker: str) -> dict[str, Any] | None:
        """Fetch financial data (PBR, ROE, EPS, dividends, etc.)."""
        cache_key = f"financial:{ticker}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        auth = self._get_auth_header()
        if not auth:
            return None

        code = self._to_code(ticker)
        try:
            r = requests.get(
                f"{self._base_url()}/fins/statements",
                params={"code": code},
                headers=auth,
                timeout=15,
            )
            r.raise_for_status()
            statements = r.json().get("statements", [])
            if not statements:
                self._cache_set(cache_key, {})
                return {}

            latest = statements[-1]
            result: dict[str, Any] = {}

            def _try_float(key: str) -> float | None:
                val = latest.get(key)
                if val is None:
                    return None
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return None

            if (pbr := _try_float("PBR")) is not None:
                result["priceToBook"] = pbr
            if (roe := _try_float("ROEAfterTax")) is not None:
                result["returnOnEquity"] = roe / 100.0
            if (eps := _try_float("EPS")) is not None:
                result["eps"] = eps
            if (feps := _try_float("FEPS")) is not None:
                result["forecast_eps"] = feps
            if (div := _try_float("DivAnn")) is not None:
                result["dividend_annual"] = div
            if (pr := _try_float("PayoutRatioAnn")) is not None:
                result["payout_ratio"] = pr / 100.0

            op = _try_float("OP")
            sales = _try_float("Sales")
            if op is not None and sales is not None and sales > 0:
                result["operating_margin"] = op / sales

            if (cfo := _try_float("CFO")) is not None:
                result["cfo"] = cfo

            self._cache_set(cache_key, result)
            return result
        except Exception:
            logger.warning("jquants_financial_fetch_failed", ticker=ticker)
            return None

    @provider_retry
    def fetch_price(
        self,
        ticker: str,
        period: str = "1y",
    ) -> pd.DataFrame | None:
        """Fetch daily price series from J-Quants."""
        cache_key = f"price:{ticker}:{period}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        auth = self._get_auth_header()
        if not auth:
            return None

        code = self._to_code(ticker)
        today = datetime.now()
        from_date = today.replace(year=today.year - 1).strftime("%Y%m%d")
        to_date = today.strftime("%Y%m%d")

        try:
            r = requests.get(
                f"{self._base_url()}/prices/daily_quotes",
                params={"code": code, "from": from_date, "to": to_date},
                headers=auth,
                timeout=15,
            )
            r.raise_for_status()
            quotes = r.json().get("daily_quotes", [])
            if not quotes:
                return None

            df = pd.DataFrame(quotes)
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"])
                df = df.set_index("Date").sort_index()

            numeric_cols = ["Open", "High", "Low", "Close", "Volume",
                            "AdjustmentFactor", "AdjustmentClose", "AdjustmentVolume"]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            self._cache_set(cache_key, df)
            return df
        except Exception:
            logger.warning("jquants_price_fetch_failed", ticker=ticker)
            return None

    @provider_retry
    def fetch_earnings_calendar(self, ticker: str) -> dict[str, Any] | None:
        """Fetch next earnings announcement date."""
        cache_key = f"earnings:{ticker}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        auth = self._get_auth_header()
        if not auth:
            return None

        code = self._to_code(ticker)
        try:
            r = requests.get(
                f"{self._base_url()}/fins/announcement",
                params={"code": code},
                headers=auth,
                timeout=10,
            )
            r.raise_for_status()
            data = r.json().get("announcement", [])
            if not data:
                self._cache_set(cache_key, None)
                return None

            today = datetime.now().date()
            future = [
                d for d in data
                if d.get("Date") and datetime.strptime(d["Date"], "%Y-%m-%d").date() >= today
            ]
            if not future:
                self._cache_set(cache_key, None)
                return None

            next_date = min(future, key=lambda d: d["Date"])
            days = (datetime.strptime(next_date["Date"], "%Y-%m-%d").date() - today).days
            result = {"announcement_date": next_date["Date"], "days_to_earnings": days}
            self._cache_set(cache_key, result)
            return result
        except Exception:
            logger.warning("jquants_earnings_fetch_failed", ticker=ticker)
            return None
