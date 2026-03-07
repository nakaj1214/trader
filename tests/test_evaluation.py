"""Tests for src.evaluation modules."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from src.evaluation.alpha_survey import build_alpha_survey_json, run_anomaly_test
from src.evaluation.backtest import (
    build_backtest_hygiene,
    equity_curve,
    portfolio_stats,
)
from src.evaluation.walkforward import compute_walkforward


class TestPortfolioStats:

    def test_basic_stats(self) -> None:
        returns = pd.Series([0.01, 0.02, -0.01, 0.015, 0.005] * 10)
        stats = portfolio_stats(returns)
        assert stats["cagr"] is not None
        assert stats["max_drawdown"] is not None
        assert stats["sharpe"] is not None

    def test_too_few_returns(self) -> None:
        stats = portfolio_stats(pd.Series([0.01, 0.02]))
        assert stats["cagr"] is None

    def test_positive_returns(self) -> None:
        returns = pd.Series([0.01] * 52)
        stats = portfolio_stats(returns)
        assert stats["cagr"] is not None
        assert stats["cagr"] > 0
        assert stats["max_drawdown"] == 0.0


class TestEquityCurve:

    def test_basic_curve(self) -> None:
        dates = pd.date_range("2024-01-01", periods=4, freq="W")
        returns = pd.Series([0.01, 0.02, -0.01, 0.015], index=dates)
        curve = equity_curve(returns)
        assert len(curve) == 4
        assert curve[0]["equity"] > 0


class TestBuildBacktestHygiene:

    def test_basic_hygiene(self, sample_config: dict[str, Any]) -> None:
        records = [
            {"date": "2025-01-06", "is_hit": True, "status": "confirmed"},
            {"date": "2025-01-06", "is_hit": False, "status": "confirmed"},
        ]
        result = build_backtest_hygiene(sample_config, records)
        assert "num_rules_tested" in result
        assert "data_coverage_weeks" in result

    def test_insufficient_trials(self, sample_config: dict[str, Any]) -> None:
        result = build_backtest_hygiene(sample_config, [])
        assert result["data_coverage_weeks"] == 0


class TestAlphaSurvey:

    def test_run_anomaly_test_returns_insufficient(self) -> None:
        result = run_anomaly_test("short_interest_effect")
        assert result["status"] == "insufficient_data"
        assert result["n_observations"] == 0

    def test_build_alpha_survey_json(self) -> None:
        results = [run_anomaly_test("short_interest_effect")]
        data = build_alpha_survey_json(results)
        assert "as_of_utc" in data
        assert len(data["anomalies"]) == 1
        assert data["anomalies"][0]["status"] == "insufficient_data"


class TestWalkforward:

    def test_insufficient_data(self, sample_config: dict[str, Any]) -> None:
        records: list[dict[str, Any]] = [
            {"date": "2025-01-06", "status": "confirmed", "is_hit": True},
        ]
        result = compute_walkforward(records, sample_config)
        assert result["windows"] == []

    def test_enough_data_produces_windows(self, sample_config: dict[str, Any]) -> None:
        records: list[dict[str, Any]] = []
        dates = pd.date_range("2024-01-01", periods=52, freq="W")
        for d in dates:
            records.append({
                "date": d.strftime("%Y-%m-%d"),
                "status": "confirmed",
                "is_hit": True,
                "predicted_price": 110.0,
                "actual_price": 112.0,
            })

        config = {
            **sample_config,
            "evaluation": {
                "walkforward": {
                    "train_weeks": 26,
                    "test_weeks": 13,
                    "min_train_weeks": 26,
                }
            },
        }
        result = compute_walkforward(records, config)
        assert len(result["windows"]) >= 1
