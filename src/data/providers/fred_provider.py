"""FRED data provider: macro indicators (policy rates, yield curve, VIX).

Returns empty results when FRED_API_KEY is not set (degraded mode).
"""

from __future__ import annotations

import json as _json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any

import structlog

from src.data.providers.base import DataProvider, provider_retry

logger = structlog.get_logger(__name__)

FRED_SERIES: dict[str, str] = {
    "FEDFUNDS": "%",
    "T10Y2Y": "%",
    "VIXCLS": "pts",
}

VIX_RISK_OFF_THRESHOLD = 25.0
T10Y2Y_RISK_OFF_THRESHOLD = 0.0


class FREDProvider(DataProvider):
    """Data provider for macro indicators via FRED API."""

    @property
    def name(self) -> str:
        return "fred"

    def is_available(self) -> bool:
        """Check if FRED_API_KEY is configured."""
        return bool(os.environ.get("FRED_API_KEY"))

    @provider_retry
    def fetch_series(self, series_id: str) -> dict[str, Any] | None:
        """Fetch the latest observation for a FRED series.

        Returns:
            Dict with latest_value and latest_date, or None on failure.
        """
        cache_key = f"series:{series_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        api_key = os.environ.get("FRED_API_KEY")
        if not api_key:
            return None

        try:
            url = (
                "https://api.stlouisfed.org/fred/series/observations"
                f"?series_id={series_id}&api_key={api_key}&file_type=json"
                "&sort_order=desc&limit=1"
            )
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = _json.loads(resp.read().decode())

            observations = data.get("observations", [])
            if not observations:
                return None

            latest = observations[0]
            raw_val = latest.get("value", ".")
            if raw_val == ".":
                return None

            result: dict[str, Any] = {
                "latest_value": round(float(raw_val), 4),
                "latest_date": latest.get("date", ""),
            }
            self._cache_set(cache_key, result)
            return result
        except Exception:
            logger.warning("fred_series_failed", series_id=series_id)
            return None

    def fetch_info(self, ticker: str) -> dict[str, Any] | None:
        """Build macro.json schema dict from all FRED series.

        The ticker parameter is ignored; this fetches all configured series.

        Returns:
            Dict conforming to macro.json schema with series data and
            risk-off regime assessment.
        """
        cache_key = "macro_json"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        if not self.is_available():
            return None

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        series_result: dict[str, Any] = {}
        latest_dates: list[str] = []

        for series_id, unit in FRED_SERIES.items():
            obs = self.fetch_series(series_id)
            if obs is None:
                logger.warning("fred_series_skipped", series_id=series_id)
                continue
            series_result[series_id] = {
                "latest_value": obs["latest_value"],
                "unit": unit,
            }
            if obs.get("latest_date"):
                latest_dates.append(obs["latest_date"])

        data_as_of_utc = (min(latest_dates) + "T00:00:00Z") if latest_dates else now_utc

        vix = series_result.get("VIXCLS", {}).get("latest_value")
        t10y2y = series_result.get("T10Y2Y", {}).get("latest_value")

        is_risk_off = False
        risk_reasons: list[str] = []
        if vix is not None and vix > VIX_RISK_OFF_THRESHOLD:
            is_risk_off = True
            risk_reasons.append(f"VIX={vix:.1f} > {VIX_RISK_OFF_THRESHOLD}")
        if t10y2y is not None and t10y2y < T10Y2Y_RISK_OFF_THRESHOLD:
            is_risk_off = True
            risk_reasons.append(f"T10Y2Y={t10y2y:.2f}% (inverted yield curve)")

        regime_note = (
            "Risk-off: " + " / ".join(risk_reasons)
            if is_risk_off
            else "Normal: VIX <= 25 and yield curve positive"
        )

        result: dict[str, Any] = {
            "as_of_utc": now_utc,
            "data_as_of_utc": data_as_of_utc,
            "series": series_result,
            "regime": {
                "is_risk_off": is_risk_off,
                "note": regime_note,
            },
        }
        self._cache_set(cache_key, result)
        return result
