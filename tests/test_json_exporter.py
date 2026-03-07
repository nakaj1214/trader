"""Tests for src.export.json_exporter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.export.json_exporter import (
    build_accuracy_json,
    build_predictions_json,
    build_stock_history_json,
    safe_write_json,
    split_records_by_market,
)


class TestBuildPredictionsJson:

    def test_basic_schema(self, sample_prediction_records: list[dict[str, Any]]) -> None:
        result = build_predictions_json(sample_prediction_records)
        assert len(result) == 3
        first = result[0]
        assert "date" in first
        assert "ticker" in first
        assert "current_price" in first
        assert "predicted_price" in first
        assert "prob_up" in first

    def test_empty_records(self) -> None:
        result = build_predictions_json([])
        assert result == []

    def test_enrichment_merged(
        self, sample_prediction_records: list[dict[str, Any]]
    ) -> None:
        enrichment = {
            ("2025-01-06", "AAPL"): {
                "risk": {"vol_20d_ann": 0.25},
                "events": {"next_earnings": "2025-02-01"},
            }
        }
        result = build_predictions_json(
            sample_prediction_records, enrichment=enrichment
        )
        aapl = [r for r in result if r["ticker"] == "AAPL"][0]
        assert "risk" in aapl
        assert aapl["risk"]["vol_20d_ann"] == 0.25


class TestBuildAccuracyJson:

    def test_has_required_keys(
        self, sample_prediction_records: list[dict[str, Any]]
    ) -> None:
        result = build_accuracy_json(sample_prediction_records)
        assert "updated_at" in result
        assert "weekly" in result
        assert "cumulative" in result

    def test_cumulative_stats(
        self, sample_prediction_records: list[dict[str, Any]]
    ) -> None:
        result = build_accuracy_json(sample_prediction_records)
        cum = result["cumulative"]
        assert cum["total"] == 2  # 2 confirmed with hit status
        assert cum["hits"] == 1  # AAPL hit

    def test_empty_records(self) -> None:
        result = build_accuracy_json([])
        assert result["cumulative"]["total"] == 0


class TestBuildStockHistoryJson:

    def test_groups_by_ticker(
        self, sample_prediction_records: list[dict[str, Any]]
    ) -> None:
        result = build_stock_history_json(sample_prediction_records)
        assert "AAPL" in result
        assert "MSFT" in result
        assert len(result["AAPL"]) == 1

    def test_actual_price_included(
        self, sample_prediction_records: list[dict[str, Any]]
    ) -> None:
        result = build_stock_history_json(sample_prediction_records)
        aapl_entry = result["AAPL"][0]
        assert "actual_price" in aapl_entry
        assert aapl_entry["actual_price"] == 155.0

    def test_no_actual_price_excluded(
        self, sample_prediction_records: list[dict[str, Any]]
    ) -> None:
        result = build_stock_history_json(sample_prediction_records)
        googl_entry = result["GOOGL"][0]
        assert "actual_price" not in googl_entry


class TestSplitRecordsByMarket:

    def test_splits_us_and_jp(self) -> None:
        records = [
            {"ticker": "AAPL"},
            {"ticker": "7203.T"},
            {"ticker": "MSFT"},
        ]
        by_market = split_records_by_market(records)
        assert len(by_market["us"]) == 2
        assert len(by_market["jp"]) == 1


class TestSafeWriteJson:

    def test_writes_json(self, tmp_path: Path) -> None:
        filepath = tmp_path / "test.json"
        data = {"key": "value"}
        assert safe_write_json(data, filepath) is True
        with open(filepath) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_skips_empty(self, tmp_path: Path) -> None:
        filepath = tmp_path / "empty.json"
        assert safe_write_json({}, filepath) is False
        assert not filepath.exists()

    def test_atomic_write_no_tmp_leftover(self, tmp_path: Path) -> None:
        filepath = tmp_path / "atomic.json"
        safe_write_json({"ok": True}, filepath)
        assert not filepath.with_suffix(".tmp").exists()
