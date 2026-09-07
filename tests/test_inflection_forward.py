from __future__ import annotations

import json

from src.evaluation.inflection_forward import load_inflection_signals


def test_load_inflection_signals_filters_to_early_candidates(tmp_path) -> None:
    snapshot_dir = tmp_path / "inflection"
    snapshot_dir.mkdir()
    payload = {
        "mode": "shadow",
        "strategy_version": "jp-inflection-shadow-v1",
        "report_schema_version": 2,
        "source_commit_sha": "abc123",
        "data_policy": {"jquants_plan": "free", "jquants_data_delay_weeks": 12},
        "candidates": [
            {"ticker": "1111.T", "classification": "EARLY_CANDIDATE", "score": 80.0},
            {"ticker": "2222.T", "classification": "WATCH", "score": 60.0},
        ],
    }
    (snapshot_dir / "2026-09-08.json").write_text(json.dumps(payload), encoding="utf-8")

    signals = load_inflection_signals(snapshot_dir)

    assert signals == [
        {
            "ticker": "1111.T",
            "signal_date": "2026-09-08",
            "date": "2026-09-08",
            "score": 80.0,
            "classification": "EARLY_CANDIDATE",
            "strategy_version": "jp-inflection-shadow-v1",
            "report_schema_version": 2,
            "source_commit_sha": "abc123",
            "jquants_plan": "free",
            "jquants_data_delay_weeks": 12,
        }
    ]


def test_load_inflection_signals_ignores_snapshots_without_reproducibility_metadata(tmp_path) -> None:
    snapshot_dir = tmp_path / "inflection"
    snapshot_dir.mkdir()
    payload = {
        "mode": "shadow",
        "candidates": [{"ticker": "1111.T", "classification": "EARLY_CANDIDATE", "score": 80.0}],
    }
    (snapshot_dir / "2026-09-08.json").write_text(json.dumps(payload), encoding="utf-8")

    assert load_inflection_signals(snapshot_dir) == []
