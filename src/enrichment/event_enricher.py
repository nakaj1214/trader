"""Event enricher: earnings dates, dividends, earnings warnings.

Migrated from src/enricher.py fetch_events / fetch_events_from_info / _fetch_earnings_warning.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import structlog

from src.enrichment.base import Enricher, is_jp_ticker

logger = structlog.get_logger(__name__)


class EventEnricher(Enricher):
    """Detect upcoming events: earnings, ex-dividend, earnings warnings."""

    @property
    def name(self) -> str:
        return "events"

    def enrich_ticker(
        self,
        ticker: str,
        stock_df: pd.DataFrame | None,
        info: dict[str, Any],
        config: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Extract events from ticker info.

        Returns dict with 'upcoming' event list and optional 'earnings_warning'.
        """
        events = extract_events_from_info(info, ticker)
        result: dict[str, Any] = {"upcoming": events}

        earnings_warning = _fetch_earnings_warning(ticker, config)
        if earnings_warning is not None:
            result["earnings_warning"] = earnings_warning

        return result if events or earnings_warning else None


def extract_events_from_info(info: dict[str, Any], ticker: str) -> list[dict[str, Any]]:
    """Extract earnings and ex-dividend events from pre-fetched info dict.

    Args:
        info: yfinance .info dict or provider info dict.
        ticker: Ticker symbol (for logging).

    Returns:
        List of event dicts with type, date, days_to fields.
    """
    events: list[dict[str, Any]] = []
    today = datetime.now(timezone.utc).date()

    earnings_raw = info.get("earningsDate")
    if earnings_raw:
        dates_list = earnings_raw if isinstance(earnings_raw, list) else [earnings_raw]
        for ed in dates_list:
            try:
                d = _parse_event_date(ed)
                if d is None:
                    continue
                days_to = (d - today).days
                if days_to >= 0:
                    events.append({
                        "type": "earnings",
                        "date": d.isoformat(),
                        "days_to": days_to,
                    })
            except Exception:
                continue

    ex_div_raw = info.get("exDividendDate")
    if ex_div_raw:
        try:
            d = _parse_event_date(ex_div_raw)
            if d is not None:
                days_to = (d - today).days
                if days_to >= 0:
                    events.append({
                        "type": "dividend_ex",
                        "date": d.isoformat(),
                        "days_to": days_to,
                    })
        except Exception:
            pass

    return events


def _parse_event_date(raw_date: Any) -> Any:
    """Parse various date formats from yfinance info."""
    if hasattr(raw_date, "date"):
        return raw_date.date() if callable(raw_date.date) else raw_date.date
    return pd.Timestamp(raw_date).date()


def _fetch_earnings_warning(
    ticker: str,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """Check JP stock earnings proximity for exclusion warning.

    Returns warning dict if earnings are within threshold days, else None.
    """
    if not is_jp_ticker(ticker):
        return None

    threshold = config.get("screening", {}).get("filters", {}).get(
        "earnings_exclusion", {}
    ).get("days", 0)
    if threshold <= 0:
        return None

    try:
        from src.data.providers.jquants_provider import JQuantsProvider

        provider = JQuantsProvider()
        if not provider.is_available():
            return None
        cal = provider.fetch_earnings_calendar(ticker)
        if cal is None:
            return None
        days = cal["days_to_earnings"]
        return {
            "announcement_date": cal["announcement_date"],
            "days_to_earnings": days,
            "exclude": days <= threshold,
        }
    except Exception:
        logger.warning("earnings_warning_fetch_failed", ticker=ticker)
        return None
