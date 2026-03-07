"""Tests for src.prediction modules."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.prediction.base import PredictionModel
from src.prediction.calibrator import apply_guardrail, compute_calibration_stats
from src.prediction.prophet_model import ProphetModel, compute_prob_up


class TestComputeProbUp:

    def test_positive_change(self) -> None:
        prob = compute_prob_up(5.0, 8.0)
        assert 0.5 < prob < 1.0

    def test_negative_change(self) -> None:
        prob = compute_prob_up(-5.0, 8.0)
        assert 0.0 < prob < 0.5

    def test_zero_ci(self) -> None:
        assert compute_prob_up(5.0, 0.0) == 1.0
        assert compute_prob_up(-5.0, 0.0) == 0.0

    def test_symmetry(self) -> None:
        p_pos = compute_prob_up(5.0, 8.0)
        p_neg = compute_prob_up(-5.0, 8.0)
        assert abs((p_pos + p_neg) - 1.0) < 0.01


class TestApplyGuardrail:

    def test_no_clip(self) -> None:
        result = apply_guardrail(5.0, {"clip_pct": 30.0, "warn_pct": 20.0})
        assert result["predicted_change_pct_clipped"] == 5.0
        assert result["sanity_flags"] == ["OK"]

    def test_warn(self) -> None:
        result = apply_guardrail(25.0, {"clip_pct": 30.0, "warn_pct": 20.0})
        assert result["predicted_change_pct_clipped"] == 25.0
        assert result["sanity_flags"] == ["WARN_HIGH"]

    def test_clip(self) -> None:
        result = apply_guardrail(50.0, {"clip_pct": 30.0, "warn_pct": 20.0})
        assert result["predicted_change_pct_clipped"] == 30.0
        assert result["sanity_flags"] == ["CLIPPED"]

    def test_negative_clip(self) -> None:
        result = apply_guardrail(-50.0, {"clip_pct": 30.0, "warn_pct": 20.0})
        assert result["predicted_change_pct_clipped"] == -30.0


class TestComputeCalibrationStats:

    def test_empty_samples(self) -> None:
        stats = compute_calibration_stats([])
        assert stats["brier_score"] is None
        assert stats["n_calibrated"] == 0

    def test_perfect_calibration(self) -> None:
        samples = [
            {"prob_up": 1.0, "outcome": 1},
            {"prob_up": 0.0, "outcome": 0},
        ]
        stats = compute_calibration_stats(samples)
        assert stats["brier_score"] == 0.0

    def test_worst_calibration(self) -> None:
        samples = [
            {"prob_up": 1.0, "outcome": 0},
            {"prob_up": 0.0, "outcome": 1},
        ]
        stats = compute_calibration_stats(samples)
        assert stats["brier_score"] == 1.0


class TestProphetModel:

    def test_name(self) -> None:
        model = ProphetModel()
        assert model.name == "prophet"

    def test_insufficient_history(self) -> None:
        model = ProphetModel()
        short_history = pd.DataFrame({"ds": pd.date_range("2024-01-01", periods=5), "y": range(5)})
        result = model.predict_stock("AAPL", short_history, 5, {})
        assert result is None

    def test_empty_history(self) -> None:
        model = ProphetModel()
        result = model.predict_stock("AAPL", pd.DataFrame(), 5, {})
        assert result is None


class TestPredictionModelABC:

    def test_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            PredictionModel()  # type: ignore[abstract]

    def test_predict_batch_default(self) -> None:
        model = ProphetModel()
        results = model.predict_batch(
            tickers=["AAPL"],
            history_map={"AAPL": pd.DataFrame()},
            forecast_days=5,
            config={},
        )
        assert results == []
