"""Tests for src.core.config."""

from __future__ import annotations

import pytest

from src.core.config import (
    AppConfig,
    _deep_merge,
    load_config,
)
from src.core.exceptions import ConfigError


class TestDeepMerge:

    def test_shallow_merge(self) -> None:
        base = {"a": 1, "b": 2}
        overlay = {"b": 3, "c": 4}
        result = _deep_merge(base, overlay)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self) -> None:
        base = {"a": {"x": 1, "y": 2}}
        overlay = {"a": {"y": 3, "z": 4}}
        result = _deep_merge(base, overlay)
        assert result == {"a": {"x": 1, "y": 3, "z": 4}}

    def test_does_not_mutate_base(self) -> None:
        base = {"a": {"x": 1}}
        overlay = {"a": {"y": 2}}
        _deep_merge(base, overlay)
        assert base == {"a": {"x": 1}}


class TestLoadConfig:

    def test_default_config_loads(self) -> None:
        cfg = load_config()
        assert isinstance(cfg, AppConfig)
        assert cfg.screening.top_n > 0
        assert cfg.prediction.forecast_days > 0

    def test_test_config_overlay(self) -> None:
        cfg = load_config(path="config/test.yaml")
        assert cfg.screening.top_n == 3
        assert cfg.notification.slack.enabled is False

    def test_invalid_path_raises(self) -> None:
        with pytest.raises(ConfigError):
            load_config(path="nonexistent.yaml")


class TestAppConfigValidation:

    def test_weights_must_sum_to_one(self) -> None:
        bad_weights = {
            "price_change_1m": 0.50,
            "volume_trend": 0.50,
            "rsi_score": 0.50,
        }
        with pytest.raises(Exception, match="sum to 1.0"):
            AppConfig(
                screening={"scoring": {"weights": bad_weights}},
            )

    def test_invalid_prediction_model(self) -> None:
        with pytest.raises(Exception, match="prediction.model"):
            AppConfig(prediction={"model": "invalid_model"})

    def test_warn_must_be_less_than_clip(self) -> None:
        with pytest.raises(Exception, match="warn_pct"):
            AppConfig(
                prediction={"guardrail": {"clip_pct": 10.0, "warn_pct": 20.0}},
            )

    def test_frozen_config(self) -> None:
        cfg = AppConfig()
        with pytest.raises(Exception):
            cfg.screening = None  # type: ignore[assignment]
