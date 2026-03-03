"""Sizing enricher: volatility-target position sizing.

Migrated from src/enricher.py compute_sizing().
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
import structlog

from src.enrichment.base import Enricher

logger = structlog.get_logger(__name__)


class SizingEnricher(Enricher):
    """Compute position sizing based on volatility targeting."""

    @property
    def name(self) -> str:
        return "sizing"

    def enrich_ticker(
        self,
        ticker: str,
        stock_df: pd.DataFrame | None,
        info: dict[str, Any],
        config: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Compute position sizing for a ticker.

        Uses vol_20d_ann from risk enricher output if available.
        """
        risk_data = kwargs.get("risk_data", {})
        vol_ann = risk_data.get("vol_20d_ann", 0.0) if risk_data else 0.0

        if vol_ann <= 0 and stock_df is not None and not stock_df.empty:
            close = stock_df["Close"].squeeze()
            returns = close.pct_change().dropna()
            if len(returns) >= 20:
                vol_ann = float(returns.iloc[-20:].std() * math.sqrt(252))

        sizing_cfg = config.get("enrichment", {}).get("sizing", {})
        return compute_sizing(vol_ann, sizing_cfg)


def compute_sizing(
    vol_ann: float,
    sizing_cfg: dict[str, Any],
) -> dict[str, Any]:
    """Compute position size and stop-loss using volatility targeting.

    Args:
        vol_ann: Annualized volatility (e.g. 0.25 = 25%).
        sizing_cfg: Config with vol_target_ann, max_weight_cap, stop_loss_multiplier.

    Returns:
        Dict with vol_target_ann, max_position_weight, stop_loss_pct,
        stop_loss_rationale.
    """
    vol_target = sizing_cfg.get("vol_target_ann", 0.10)
    max_cap = sizing_cfg.get("max_weight_cap", 0.20)
    sl_mult = sizing_cfg.get("stop_loss_multiplier", 1.0)

    if vol_ann > 0:
        raw_weight = vol_target / vol_ann
        max_weight = round(min(raw_weight, max_cap), 4)
        monthly_vol = vol_ann / math.sqrt(12)
        stop_loss = round(-sl_mult * monthly_vol, 4)
        rationale = "Monthly risk estimate based on 20d volatility"
    else:
        max_weight = round(max_cap, 4)
        stop_loss = None
        rationale = "No volatility data available"

    return {
        "vol_target_ann": vol_target,
        "max_position_weight": max_weight,
        "stop_loss_pct": stop_loss,
        "stop_loss_rationale": rationale,
    }
