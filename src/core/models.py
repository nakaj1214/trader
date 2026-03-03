"""Pydantic v2 data models for the Trader project.

All models are frozen (immutable) and use strict type annotations.
These represent the canonical data structures flowing through
the screening -> prediction -> enrichment -> tracking pipeline.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Stock(BaseModel, frozen=True):
    """A screened stock with technical indicators and composite score."""

    ticker: str
    market: str
    current_price: float
    market_cap: float | None = None
    score: float | None = None
    indicators: dict[str, float] = Field(default_factory=dict)


class Prediction(BaseModel, frozen=True):
    """Prophet-based price forecast for a single ticker."""

    date: str
    ticker: str
    current_price: float
    predicted_price: float
    predicted_change_pct: float
    confidence_interval_pct: float
    prob_up: float | None = None
    prob_up_calibrated: float | None = None
    status: str = "predicted"


class TrackingResult(BaseModel, frozen=True):
    """Outcome of comparing a prediction against the actual closing price."""

    date: str
    ticker: str
    current_price: float
    predicted_price: float
    actual_price: float | None = None
    is_hit: bool | None = None
    status: str = "predicted"


class Enrichment(BaseModel, frozen=True):
    """Enrichment data attached to a predicted ticker before export."""

    ticker: str
    risk: dict | None = None
    events: dict | None = None
    evidence: dict | None = None
    sentiment: dict | None = None
    sizing: dict | None = None


class BacktestResult(BaseModel, frozen=True):
    """Aggregated performance metrics from a backtest run."""

    strategy: str
    cagr: float | None = None
    max_drawdown: float | None = None
    sharpe: float | None = None
    equity_curve: list[float] = Field(default_factory=list)


class RunMeta(BaseModel, frozen=True):
    """Metadata describing a single pipeline run."""

    timestamp: str
    git_hash: str | None = None
    config_hash: str
    python_version: str
