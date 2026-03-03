"""Evidence enricher: factor-based z-score signals.

Migrated from src/enricher.py compute_evidence_signals().
Computes momentum, value, quality, and low-risk z-scores
relative to the peer group.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import structlog

from src.enrichment.base import Enricher

logger = structlog.get_logger(__name__)

MOMENTUM_END_DAYS = 22
MOMENTUM_SPAN_DAYS = 252
MOMENTUM_MIN_DAYS = MOMENTUM_END_DAYS + MOMENTUM_SPAN_DAYS

EVIDENCE_WEIGHTS: dict[str, float] = {
    "momentum_z": 0.3,
    "value_z": 0.25,
    "quality_z": 0.25,
    "low_risk_z": 0.2,
}


class EvidenceEnricher(Enricher):
    """Compute factor-based evidence signals relative to peer group."""

    @property
    def name(self) -> str:
        return "evidence"

    def enrich_ticker(
        self,
        ticker: str,
        stock_df: pd.DataFrame | None,
        info: dict[str, Any],
        config: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Compute evidence z-scores for a single ticker.

        Requires peer_data in kwargs for cross-sectional z-score computation.
        """
        peer_data = kwargs.get("peer_data", [])
        if not peer_data:
            return None

        risk_data = kwargs.get("risk_data", {})
        vol_20d = risk_data.get("vol_20d_ann", 0.0) if risk_data else 0.0

        return compute_evidence_signals(ticker, info, vol_20d, peer_data)


def compute_evidence_signals(
    ticker: str,
    ticker_info: dict[str, Any],
    ticker_vol_20d: float,
    peer_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute factor z-scores relative to peer group.

    Args:
        ticker: Target ticker symbol.
        ticker_info: Info dict for the target ticker.
        ticker_vol_20d: Pre-computed 20d annualized vol.
        peer_data: List of peer dicts with 'ticker', 'info', 'df' keys.

    Returns:
        Dict with momentum_z, value_z, quality_z, low_risk_z, composite.
    """
    momentum_z = _compute_momentum_z(ticker, peer_data)
    value_z = _compute_value_z(ticker_info, peer_data)
    quality_z = _compute_quality_z(ticker_info, peer_data)
    low_risk_z = _compute_low_risk_z(ticker_vol_20d, peer_data)

    z_values = {
        "momentum_z": momentum_z,
        "value_z": value_z,
        "quality_z": quality_z,
        "low_risk_z": low_risk_z,
    }

    composite = _compute_composite(z_values)

    return {
        "momentum_z": _safe_round(momentum_z, 2),
        "value_z": _safe_round(value_z, 2),
        "quality_z": _safe_round(quality_z, 2),
        "low_risk_z": _safe_round(low_risk_z, 2),
        "composite": composite,
    }


def _z_score(val: float | None, values: list[float | None]) -> float | None:
    """Compute z-score of val within a list of values."""
    if val is None:
        return None
    arr = np.array([v for v in values if v is not None])
    if len(arr) < 2 or np.std(arr) == 0:
        return 0.0
    return float((val - np.mean(arr)) / np.std(arr))


def _safe_round(value: float | None, digits: int) -> float | None:
    """Round a value if not None."""
    return round(value, digits) if value is not None else None


def _calc_momentum(peer: dict[str, Any]) -> float | None:
    """Compute 12-1 momentum for a single peer."""
    df = peer.get("df")
    if df is None or len(df) < MOMENTUM_MIN_DAYS:
        return None
    close = df["Close"].squeeze()
    end_price = float(close.iloc[-MOMENTUM_END_DAYS])
    start_price = float(close.iloc[-MOMENTUM_MIN_DAYS])
    if start_price <= 0:
        return None
    return (end_price - start_price) / start_price


def _compute_momentum_z(
    ticker: str, peer_data: list[dict[str, Any]]
) -> float | None:
    """Compute momentum z-score."""
    all_momentum = [_calc_momentum(p) for p in peer_data]
    ticker_peer = next((p for p in peer_data if p["ticker"] == ticker), None)
    ticker_momentum = _calc_momentum(ticker_peer) if ticker_peer else None
    return _z_score(ticker_momentum, all_momentum)


def _compute_value_z(
    ticker_info: dict[str, Any], peer_data: list[dict[str, Any]]
) -> float | None:
    """Compute value z-score (inverse P/B)."""
    def _calc_value(peer: dict[str, Any]) -> float | None:
        pb = peer.get("info", {}).get("priceToBook")
        return 1.0 / pb if pb and pb > 0 else None

    all_value = [_calc_value(p) for p in peer_data]
    ticker_value = _calc_value({"info": ticker_info})
    return _z_score(ticker_value, all_value)


def _compute_quality_z(
    ticker_info: dict[str, Any], peer_data: list[dict[str, Any]]
) -> float | None:
    """Compute quality z-score (ROE)."""
    def _calc_quality(peer: dict[str, Any]) -> float | None:
        roe = peer.get("info", {}).get("returnOnEquity")
        return float(roe) if roe is not None else None

    all_quality = [_calc_quality(p) for p in peer_data]
    ticker_quality = _calc_quality({"info": ticker_info})
    return _z_score(ticker_quality, all_quality)


def _compute_low_risk_z(
    ticker_vol_20d: float, peer_data: list[dict[str, Any]]
) -> float | None:
    """Compute low-risk z-score (inverse volatility)."""
    def _calc_low_risk(peer: dict[str, Any]) -> float | None:
        vol = peer.get("vol_20d")
        return 1.0 / vol if vol and vol > 0 else None

    all_low_risk = [_calc_low_risk(p) for p in peer_data]
    ticker_low_risk = 1.0 / ticker_vol_20d if ticker_vol_20d > 0 else None
    return _z_score(ticker_low_risk, all_low_risk)


def _compute_composite(z_values: dict[str, float | None]) -> int | None:
    """Compute weighted composite score (0-100 scale)."""
    weighted_sum = 0.0
    total_weight = 0.0
    for key, w in EVIDENCE_WEIGHTS.items():
        val = z_values.get(key)
        if val is not None:
            weighted_sum += w * val
            total_weight += w

    if total_weight <= 0:
        return None

    raw_composite = weighted_sum / total_weight
    return max(0, min(100, round((raw_composite + 3) / 6 * 100)))
