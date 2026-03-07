"""Tests for src.orchestrator."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.orchestrator import (
    PipelineResult,
    StepResult,
    _concat_predictions,
    _step_screen,
    _step_predict,
    _step_track,
    run_pipeline,
)


class TestPipelineResult:

    def test_ok_when_all_succeed(self) -> None:
        result = PipelineResult(steps=[
            StepResult(name="a", success=True),
            StepResult(name="b", success=True),
        ])
        assert result.ok is True

    def test_not_ok_when_any_fails(self) -> None:
        result = PipelineResult(steps=[
            StepResult(name="a", success=True),
            StepResult(name="b", success=False, error="boom"),
        ])
        assert result.ok is False

    def test_summary_includes_all_steps(self) -> None:
        result = PipelineResult(steps=[
            StepResult(name="a", success=True),
        ])
        summary = result.summary()
        assert summary["ok"] is True
        assert len(summary["steps"]) == 1


class TestConcatPredictions:

    def test_both_empty(self) -> None:
        result = _concat_predictions(pd.DataFrame(), pd.DataFrame())
        assert result.empty

    def test_one_empty(self) -> None:
        df = pd.DataFrame({"ticker": ["AAPL"]})
        result = _concat_predictions(df, pd.DataFrame())
        assert len(result) == 1

    def test_both_non_empty(self) -> None:
        us = pd.DataFrame({"ticker": ["AAPL"]})
        jp = pd.DataFrame({"ticker": ["7203.T"]})
        result = _concat_predictions(us, jp)
        assert len(result) == 2


class TestStepScreen:

    @patch("src.screening.scorer.screen")
    def test_empty_markets_skipped(self, mock_screen: MagicMock) -> None:
        result = PipelineResult()
        df = _step_screen(result, {}, [], label="us")
        assert df.empty
        assert result.steps[0].data == "skipped"
        mock_screen.assert_not_called()

    @patch("src.screening.scorer.screen")
    def test_returns_screened_df(
        self, mock_screen: MagicMock, sample_config: dict[str, Any]
    ) -> None:
        mock_screen.return_value = pd.DataFrame({
            "ticker": ["AAPL"], "current_price": [150.0], "score": [0.8]
        })
        result = PipelineResult()
        df = _step_screen(result, sample_config, ["sp500"], label="us")
        assert len(df) == 1
        assert result.steps[0].success is True

    @patch("src.screening.scorer.screen", side_effect=Exception("network error"))
    def test_handles_exception(
        self, mock_screen: MagicMock, sample_config: dict[str, Any]
    ) -> None:
        result = PipelineResult()
        df = _step_screen(result, sample_config, ["sp500"], label="us")
        assert df.empty
        assert result.steps[0].success is False


class TestStepPredict:

    @patch("src.prediction.ensemble.predict")
    def test_empty_screened_skipped(self, mock_predict: MagicMock) -> None:
        result = PipelineResult()
        df = _step_predict(result, pd.DataFrame(), {}, label="us")
        assert df.empty
        assert result.steps[0].data == "skipped"
        mock_predict.assert_not_called()

    @patch("src.prediction.ensemble.predict")
    def test_returns_predictions(
        self, mock_predict: MagicMock, sample_predictions_df: pd.DataFrame
    ) -> None:
        mock_predict.return_value = sample_predictions_df
        result = PipelineResult()
        screened = pd.DataFrame({"ticker": ["AAPL", "MSFT"]})
        df = _step_predict(result, screened, {}, label="us")
        assert len(df) == 2
        assert result.steps[0].success is True


class TestStepTrack:

    @patch("src.evaluation.tracker.track")
    def test_returns_accuracy(self, mock_track: MagicMock) -> None:
        mock_track.return_value = {
            "hits": 3, "total": 5, "hit_rate_pct": 60.0,
        }
        result = PipelineResult()
        accuracy = _step_track(result, {})
        assert accuracy is not None
        assert accuracy["hits"] == 3
        assert result.steps[0].success is True

    @patch("src.evaluation.tracker.track", side_effect=Exception("db error"))
    def test_handles_exception(self, mock_track: MagicMock) -> None:
        result = PipelineResult()
        accuracy = _step_track(result, {})
        assert accuracy is None
        assert result.steps[0].success is False


class TestRunPipeline:

    @patch("src.orchestrator._step_export")
    @patch("src.orchestrator._step_enrich", return_value={})
    @patch("src.orchestrator._step_track", return_value=None)
    @patch("src.orchestrator._step_predict", return_value=pd.DataFrame())
    @patch("src.orchestrator._step_screen", return_value=pd.DataFrame())
    def test_dry_run_skips_side_effects(
        self,
        mock_screen: MagicMock,
        mock_predict: MagicMock,
        mock_track: MagicMock,
        mock_enrich: MagicMock,
        mock_export: MagicMock,
        sample_config: dict[str, Any],
    ) -> None:
        result = run_pipeline(sample_config, dry_run=True)
        persist_steps = [s for s in result.steps if s.name == "persist"]
        assert len(persist_steps) == 1
        assert persist_steps[0].data == "dry_run"

        notify_steps = [s for s in result.steps if s.name == "notify"]
        assert len(notify_steps) == 1
        assert notify_steps[0].data == "dry_run"
