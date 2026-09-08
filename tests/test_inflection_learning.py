from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.snapshot_crypto import encrypt_json
from src.evaluation.inflection_learning import (
    build_learning_report,
    evaluate_learning_observations,
    load_learning_observations,
    public_learning_summary,
)


def _history(values: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-02", periods=len(values), freq="B")
    close = pd.Series(values, index=index, dtype=float)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
        }
    )


def test_load_learning_observations_uses_all_deep_candidates(tmp_path: Path) -> None:
    secret = "test-learning-key"
    payload = {
        "mode": "shadow",
        "strategy_version": "jp-inflection-shadow-v2",
        "report_schema_version": 3,
        "latest_price_date": "2026-01-05",
        "candidates": [
            {
                "ticker": "1111.T",
                "classification": "EARLY_CANDIDATE",
                "score": 80.0,
                "return_20d_pct": 18.0,
                "return_60d_pct": 28.0,
                "volume_ratio_20d": 1.8,
                "breakout_52w": True,
                "reasons": ["売上成長", "出来高増加"],
            },
            {
                "ticker": "2222.T",
                "classification": "WATCH",
                "score": 63.0,
                "return_20d_pct": 9.0,
                "return_60d_pct": 20.0,
                "volume_ratio_20d": 1.4,
                "breakout_52w": False,
                "reasons": [],
            },
        ],
    }
    path = tmp_path / "2026-01-05.enc"
    path.write_text(encrypt_json(payload, secret), encoding="utf-8")

    observations = load_learning_observations(tmp_path, encryption_secret=secret)

    assert [row["ticker"] for row in observations] == ["1111.T", "2222.T"]
    assert observations[0]["classification"] == "EARLY_CANDIDATE"
    assert observations[1]["classification"] == "WATCH"
    assert observations[0]["reasons"] == ["売上成長", "出来高増加"]


def test_evaluation_records_prediction_miss_and_missed_explosion() -> None:
    observations = [
        {
            "ticker": "1111.T",
            "signal_date": "2026-01-05",
            "date": "2026-01-05",
            "classification": "EARLY_CANDIDATE",
            "score": 82.0,
            "market": "Prime",
            "return_20d_pct": 20.0,
            "return_60d_pct": 30.0,
            "volume_ratio_20d": 1.8,
            "breakout_52w": True,
            "reasons": ["出来高増加"],
            "strategy_version": "jp-inflection-shadow-v2",
        },
        {
            "ticker": "2222.T",
            "signal_date": "2026-01-05",
            "date": "2026-01-05",
            "classification": "WATCH",
            "score": 60.0,
            "market": "Growth",
            "return_20d_pct": 8.0,
            "return_60d_pct": 12.0,
            "volume_ratio_20d": 1.6,
            "breakout_52w": False,
            "reasons": ["営業利益急増"],
            "strategy_version": "jp-inflection-shadow-v2",
        },
    ]
    falling = [100.0] + [100.0 - index * 0.5 for index in range(1, 150)]
    rising = [100.0 + index * 0.7 for index in range(150)]
    benchmark = _history([100.0] * 150)

    evaluated = evaluate_learning_observations(
        observations,
        {"1111.T": _history(falling), "2222.T": _history(rising)},
        benchmark,
    )

    early = next(row for row in evaluated if row["ticker"] == "1111.T")
    watch = next(row for row in evaluated if row["ticker"] == "2222.T")
    assert "negative_absolute_return" in early["prediction_miss_reasons"]
    assert "volume_without_followthrough" in early["prediction_miss_reasons"]
    assert watch["missed_explosion"] is True
    assert 60 in watch["explosion_horizons"] or 120 in watch["explosion_horizons"]


def test_learning_report_promotes_only_aggregate_evidence_and_public_summary_has_no_tickers() -> None:
    observations: list[dict[str, object]] = []
    histories: dict[str, pd.DataFrame] = {}
    for index in range(30):
        ticker = f"W{index:03d}.T"
        observations.append(
            {
                "ticker": ticker,
                "signal_date": "2026-01-05",
                "date": "2026-01-05",
                "classification": "WATCH",
                "score": 62.0,
                "market": "Growth",
                "return_20d_pct": 10.0,
                "return_60d_pct": 18.0,
                "volume_ratio_20d": 1.7,
                "breakout_52w": False,
                "reasons": ["出来高増加"],
                "strategy_version": "jp-inflection-shadow-v2",
            }
        )
        histories[ticker] = _history([100.0 + day * 0.8 for day in range(150)])
    for index in range(30):
        ticker = f"N{index:03d}.T"
        observations.append(
            {
                "ticker": ticker,
                "signal_date": "2026-01-05",
                "date": "2026-01-05",
                "classification": "NONE",
                "score": 40.0,
                "market": "Prime",
                "return_20d_pct": -2.0,
                "return_60d_pct": 0.0,
                "volume_ratio_20d": 0.9,
                "breakout_52w": False,
                "reasons": [],
                "strategy_version": "jp-inflection-shadow-v2",
            }
        )
        histories[ticker] = _history([100.0] * 150)

    report = build_learning_report(observations, histories, _history([100.0] * 150))
    h20_factors = {item["factor"]: item for item in report["factor_statistics"]["h20"]}

    assert h20_factors["classification:WATCH"]["promotion_status"] == "positive_candidate"
    assert any(lesson["factor"] == "classification:WATCH" for lesson in report["lessons"])

    public = public_learning_summary(report)
    assert "observations" not in public
    assert "postmortems" not in public
    assert "1111.T" not in str(public)
