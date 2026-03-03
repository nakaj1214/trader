"""Configuration loading and validation module.

Loads configuration from YAML files with optional overlays,
validates all settings at startup via Pydantic models, and
provides a typed AppConfig object to the rest of the application.

Load order (later entries override earlier):
  1. config/default.yaml  (required)
  2. config/production.yaml  (optional, merged on top of default)
  3. path passed to load_config(path=...)  (optional CLI override)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings

from src.core.exceptions import ConfigError

ROOT_DIR: Path = Path(__file__).resolve().parent.parent.parent


def get_env(key: str, default: str | None = None) -> str | None:
    """Return the value of an environment variable."""
    return os.environ.get(key, default)


# ---------------------------------------------------------------------------
# Nested config models (all frozen)
# ---------------------------------------------------------------------------


class MarketCapFilterConfig(BaseSettings):
    model_config = {"frozen": True}
    min: int = Field(default=10_000_000_000, ge=0)


class LiquidityFilterConfig(BaseSettings):
    model_config = {"frozen": True}
    min_dollar_volume_us: int = Field(default=1_000_000, ge=0)
    min_dollar_volume_jp: int = Field(default=500_000_000, ge=0)


class GoldenCrossFilterConfig(BaseSettings):
    model_config = {"frozen": True}
    enabled: bool = Field(default=True)


class EarningsExclusionConfig(BaseSettings):
    model_config = {"frozen": True}
    days: int = Field(default=5, ge=0)


class FiltersConfig(BaseSettings):
    model_config = {"frozen": True}
    market_cap: MarketCapFilterConfig = Field(default_factory=MarketCapFilterConfig)
    liquidity: LiquidityFilterConfig = Field(default_factory=LiquidityFilterConfig)
    golden_cross: GoldenCrossFilterConfig = Field(default_factory=GoldenCrossFilterConfig)
    earnings_exclusion: EarningsExclusionConfig = Field(default_factory=EarningsExclusionConfig)


class ScoringConfig(BaseSettings):
    model_config = {"frozen": True}
    weights: dict[str, float] = Field(
        default={
            "price_change_1m": 0.20,
            "volume_trend": 0.15,
            "rsi_score": 0.15,
            "macd_signal": 0.15,
            "fifty2w_score": 0.15,
            "bb_position": 0.10,
            "adx_score": 0.10,
        }
    )

    @field_validator("weights")
    @classmethod
    def weights_must_sum_to_one(cls, v: dict[str, float]) -> dict[str, float]:
        total = sum(v.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"scoring.weights must sum to 1.0, got {total:.6f}")
        return v


class ScreeningConfig(BaseSettings):
    model_config = {"frozen": True}
    markets: list[str] = Field(default=["sp500", "nasdaq100", "nikkei225"])
    top_n: int = Field(default=10, gt=0)
    lookback_days: int = Field(default=252, gt=0)
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)


class ProphetConfig(BaseSettings):
    model_config = {"frozen": True}
    interval_width: float = Field(default=0.95, gt=0.0, lt=1.0)
    changepoint_prior_scale: float = Field(default=0.05, gt=0.0)
    uncertainty_samples: int = Field(default=1000, gt=0)


class GuardrailConfig(BaseSettings):
    model_config = {"frozen": True}
    clip_pct: float = Field(default=30.0, gt=0.0)
    warn_pct: float = Field(default=20.0, gt=0.0)

    @model_validator(mode="after")
    def warn_must_be_less_than_clip(self) -> GuardrailConfig:
        if self.warn_pct >= self.clip_pct:
            raise ValueError(
                f"guardrail.warn_pct ({self.warn_pct}) must be "
                f"less than clip_pct ({self.clip_pct})"
            )
        return self


class EnsembleConfig(BaseSettings):
    model_config = {"frozen": True}
    weights: dict[str, float] = Field(default={"prophet": 0.4, "lightgbm": 0.6})

    @field_validator("weights")
    @classmethod
    def weights_must_sum_to_one(cls, v: dict[str, float]) -> dict[str, float]:
        total = sum(v.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"ensemble.weights must sum to 1.0, got {total:.6f}")
        return v


_VALID_MODELS = {"prophet", "lightgbm", "ensemble"}


class PredictionConfig(BaseSettings):
    model_config = {"frozen": True}
    model: str = Field(default="prophet")
    history_days: int = Field(default=90, gt=0)
    forecast_days: int = Field(default=5, gt=0)
    prophet: ProphetConfig = Field(default_factory=ProphetConfig)
    guardrail: GuardrailConfig = Field(default_factory=GuardrailConfig)
    ensemble: EnsembleConfig = Field(default_factory=EnsembleConfig)

    @field_validator("model")
    @classmethod
    def model_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_MODELS:
            raise ValueError(f"prediction.model must be one of {sorted(_VALID_MODELS)}, got '{v}'")
        return v


class ProviderConfig(BaseSettings):
    model_config = {"frozen": True}
    enabled: bool = Field(default=True)


class PerplexityConfig(BaseSettings):
    model_config = {"frozen": True}
    enabled: bool = Field(default=False)
    model: str = Field(default="sonar")
    max_tickers: int = Field(default=5, gt=0)


class ProvidersConfig(BaseSettings):
    model_config = {"frozen": True}
    jquants: ProviderConfig = Field(default_factory=ProviderConfig)
    finnhub: ProviderConfig = Field(default_factory=ProviderConfig)
    fmp: ProviderConfig = Field(default_factory=ProviderConfig)
    fred: ProviderConfig = Field(default_factory=lambda: ProviderConfig(enabled=False))
    perplexity: PerplexityConfig = Field(default_factory=PerplexityConfig)


class GoogleSheetsConfig(BaseSettings):
    model_config = {"frozen": True}
    spreadsheet_name: str = Field(default="trade")
    worksheet_name: str = Field(default="predictions")


class ExportConfig(BaseSettings):
    model_config = {"frozen": True}
    google_sheets: GoogleSheetsConfig = Field(default_factory=GoogleSheetsConfig)


class SlackConfig(BaseSettings):
    model_config = {"frozen": True}
    enabled: bool = Field(default=True)
    channel: str = Field(default="#stock-alerts")
    chart_enabled: bool = Field(default=True)
    channel_id: str = Field(default="")


class LineConfig(BaseSettings):
    model_config = {"frozen": True}
    enabled: bool = Field(default=False)


class ChartConfig(BaseSettings):
    model_config = {"frozen": True}
    lookback_days: int = Field(default=60, gt=0)


class NotificationConfig(BaseSettings):
    model_config = {"frozen": True}
    slack: SlackConfig = Field(default_factory=SlackConfig)
    line: LineConfig = Field(default_factory=LineConfig)
    beginner_mode: bool = Field(default=True)
    chart: ChartConfig = Field(default_factory=ChartConfig)


class SizingConfig(BaseSettings):
    model_config = {"frozen": True}
    vol_target_ann: float = Field(default=0.10, gt=0.0)
    max_weight_cap: float = Field(default=0.20, gt=0.0, le=1.0)
    stop_loss_multiplier: float = Field(default=1.0, gt=0.0)


class EnrichmentConfig(BaseSettings):
    model_config = {"frozen": True}
    sizing: SizingConfig = Field(default_factory=SizingConfig)


class BacktestConfig(BaseSettings):
    model_config = {"frozen": True}
    num_rules_tested: int = Field(default=1, ge=1)
    num_parameters_tuned: int = Field(default=4, ge=0)
    oos_start: str = Field(default="2025-01-01")
    min_rules_for_pbo: int = Field(default=2, ge=2)


class WalkforwardConfig(BaseSettings):
    model_config = {"frozen": True}
    train_weeks: int = Field(default=52, gt=0)
    test_weeks: int = Field(default=13, gt=0)
    min_train_weeks: int = Field(default=26, gt=0)


class EvaluationConfig(BaseSettings):
    model_config = {"frozen": True}
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    walkforward: WalkforwardConfig = Field(default_factory=WalkforwardConfig)


class DataConfig(BaseSettings):
    model_config = {"frozen": True}
    price_column: str = Field(default="Close")

    @field_validator("price_column")
    @classmethod
    def price_column_must_be_valid(cls, v: str) -> str:
        valid = {"Close", "Adj Close"}
        if v not in valid:
            raise ValueError(f"data.price_column must be one of {sorted(valid)}, got '{v}'")
        return v


class AppConfig(BaseSettings):
    """Top-level application configuration."""

    model_config = {"frozen": True}

    screening: ScreeningConfig = Field(default_factory=ScreeningConfig)
    prediction: PredictionConfig = Field(default_factory=PredictionConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
    enrichment: EnrichmentConfig = Field(default_factory=EnrichmentConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    data: DataConfig = Field(default_factory=DataConfig)


# ---------------------------------------------------------------------------
# YAML loading helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict."""
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse YAML file '{path}': {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Failed to read config file '{path}': {exc}") from exc


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge overlay into base, returning a new dict."""
    result: dict[str, Any] = {**base}
    for key, overlay_value in overlay.items():
        base_value = result.get(key)
        if isinstance(base_value, dict) and isinstance(overlay_value, dict):
            result = {**result, key: _deep_merge(base_value, overlay_value)}
        else:
            result = {**result, key: overlay_value}
    return result


def load_config(path: str | None = None) -> AppConfig:
    """Load, merge, and validate application configuration.

    Args:
        path: Optional path to an additional YAML override file.

    Returns:
        A fully validated, immutable AppConfig instance.

    Raises:
        ConfigError: If the default config is missing, YAML is malformed,
                     or Pydantic validation fails.
    """
    default_path = ROOT_DIR / "config" / "default.yaml"
    production_path = ROOT_DIR / "config" / "production.yaml"

    if not default_path.exists():
        raise ConfigError(
            f"Required default config not found: '{default_path}'. "
            "Create 'config/default.yaml' in the project root."
        )

    merged: dict[str, Any] = _load_yaml(default_path)
    merged = _deep_merge(merged, _load_yaml(production_path))

    if path is not None:
        override_path = Path(path)
        if not override_path.exists():
            raise ConfigError(f"Config override file not found: '{override_path}'")
        merged = _deep_merge(merged, _load_yaml(override_path))

    try:
        return AppConfig.model_validate(merged)
    except Exception as exc:
        raise ConfigError(f"Configuration validation failed: {exc}") from exc
