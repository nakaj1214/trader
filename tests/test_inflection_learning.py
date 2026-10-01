from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from scripts.rebuild_inflection_learning import main as rebuild_main
from src.data.snapshot_crypto import encrypt_json
from src.evaluation.inflection_forward import SnapshotLoadError
from src.evaluation.inflection_learning import (
    _bucket,
    _factor_statistics,
    _independent_rows,
    _lessons,
    _prediction_miss_reasons,
    build_learning_report,
    evaluate_learning_observations,
    factor_labels,
    load_inflection_learning_observations,
    public_learning_summary,
)

SECRET = "test-snapshot-secret"


def _history(values: list[float], start: str = "2026-01-02") -> pd.DataFrame:
    index = pd.date_range(start, periods=len(values), freq="B")
    close = pd.Series(values, index=index, dtype=float)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
        }
    )


def _candidate(ticker: str = "1111.T", classification: str = "EARLY_CANDIDATE") -> dict[str, Any]:
    return {
        "ticker": ticker,
        "classification": classification,
        "score": 80.0,
        "raw_inflection_score": 46.0,
        "market": "Prime",
        "return_5d_pct": 5.0,
        "return_20d_pct": 18.0,
        "return_60d_pct": 28.0,
        "volume_ratio_20d": 1.8,
        "near_52w_high": True,
        "near_listing_high": False,
        "avg_turnover_20d_jpy": 50_000_000.0,
        "reasons": ["売上成長", "出来高増加"],
    }


def _payload(
    market_date: str = "2026-01-05",
    *,
    strategy_version: str = "jp-inflection-shadow-v3",
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "mode": "shadow",
        "strategy_version": strategy_version,
        "report_schema_version": 4,
        "source_commit_sha": "abc123",
        "latest_price_date": market_date,
        "storage": {
            "encrypted": True,
            "snapshot_date_basis": "latest_price_date",
        },
        "candidates": candidates if candidates is not None else [_candidate()],
    }


def _legacy_candidate(ticker: str = "1111.T", classification: str = "EARLY_CANDIDATE") -> dict[str, Any]:
    """A schema-3 (jp-inflection-shadow-v2) candidate: breakout_52w, no near_*_high split."""
    candidate = _candidate(ticker, classification)
    del candidate["near_52w_high"]
    del candidate["near_listing_high"]
    candidate["breakout_52w"] = True
    return candidate


def legacy_payload(
    market_date: str = "2026-01-05",
    *,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _payload(
        market_date,
        strategy_version="jp-inflection-shadow-v2",
        candidates=candidates if candidates is not None else [_legacy_candidate()],
    ) | {"report_schema_version": 3}


def _write_snapshot(directory: Path, payload: dict[str, Any]) -> None:
    market_date = str(payload["latest_price_date"])
    (directory / f"{market_date}.enc").write_text(
        encrypt_json(payload, SECRET),
        encoding="utf-8",
    )


def test_loader_uses_all_candidates_and_current_high_factors(tmp_path: Path) -> None:
    watch = _candidate("2222.T", "WATCH")
    watch["near_52w_high"] = False
    watch["near_listing_high"] = True
    _write_snapshot(tmp_path, _payload(candidates=[_candidate(), watch]))

    observations = load_inflection_learning_observations(tmp_path, encryption_secret=SECRET)

    assert [row["classification"] for row in observations] == ["EARLY_CANDIDATE", "WATCH"]
    assert "near_52w_high:True" in factor_labels(observations[0])
    assert "near_listing_high:True" in factor_labels(observations[1])
    assert all("breakout_52w" not in label for row in observations for label in factor_labels(row))


def test_loader_allows_multiple_strategy_versions_with_schema_four(tmp_path: Path) -> None:
    _write_snapshot(
        tmp_path,
        _payload("2026-01-05", strategy_version="jp-inflection-shadow-v3", candidates=[_candidate()]),
    )
    _write_snapshot(
        tmp_path,
        _payload(
            "2026-01-06",
            strategy_version="jp-inflection-shadow-v4",
            candidates=[_candidate("2222.T", "WATCH")],
        ),
    )

    observations = load_inflection_learning_observations(tmp_path, encryption_secret=SECRET)
    report = build_learning_report(
        observations,
        {"1111.T": _history([100.0] * 150), "2222.T": _history([100.0] * 150)},
        _history([100.0] * 150),
        promotion_strategy_version="jp-inflection-shadow-v4",
    )

    assert report["strategy_versions"] == ["jp-inflection-shadow-v3", "jp-inflection-shadow-v4"]
    assert report["promotion_scope_strategy_version"] == "jp-inflection-shadow-v4"


def test_promotion_scope_is_explicit_not_latest_observation(tmp_path: Path) -> None:
    """A newer legacy snapshot must not silently become the promotion target."""
    _write_snapshot(
        tmp_path,
        _payload("2026-01-05", strategy_version="jp-inflection-shadow-v3", candidates=[_candidate()]),
    )
    _write_snapshot(
        tmp_path,
        legacy_payload(
            "2026-01-06",
            candidates=[_legacy_candidate("2222.T", "WATCH")],
        ),
    )

    observations = load_inflection_learning_observations(tmp_path, encryption_secret=SECRET)
    report = build_learning_report(
        observations,
        {"1111.T": _history([100.0] * 150), "2222.T": _history([100.0] * 150)},
        _history([100.0] * 150),
        promotion_strategy_version="jp-inflection-shadow-v3",
    )

    assert report["strategy_versions"] == ["jp-inflection-shadow-v2", "jp-inflection-shadow-v3"]
    assert report["promotion_scope_strategy_version"] == "jp-inflection-shadow-v3"
    assert report["observation_count"] == 2


def test_loader_reads_legacy_schema_three_without_mapping_to_near_high_fields(tmp_path: Path) -> None:
    _write_snapshot(tmp_path, legacy_payload())

    observations = load_inflection_learning_observations(tmp_path, encryption_secret=SECRET)

    assert len(observations) == 1
    row = observations[0]
    assert row["strategy_version"] == "jp-inflection-shadow-v2"
    assert row["report_schema_version"] == 3
    assert row["legacy_breakout_52w"] is True
    assert row["near_52w_high"] is None
    assert row["near_listing_high"] is None

    labels = factor_labels(row)
    assert "legacy_breakout_52w:True" in labels
    assert not any(label.startswith("near_52w_high:") for label in labels)
    assert not any(label.startswith("near_listing_high:") for label in labels)


def test_loader_rejects_legacy_candidate_missing_breakout_flag(tmp_path: Path) -> None:
    candidate = _legacy_candidate()
    del candidate["breakout_52w"]
    _write_snapshot(tmp_path, legacy_payload(candidates=[candidate]))

    with pytest.raises(SnapshotLoadError, match="legacy candidate breakout flag"):
        load_inflection_learning_observations(tmp_path, encryption_secret=SECRET)


def test_legacy_only_snapshots_produce_no_promotion_candidates_for_current_strategy(
    tmp_path: Path,
) -> None:
    """Regression test for the bug in memo/trader_self_learning_legacy_data_issue_2026-09-14.md:
    legacy v2 data must never become the promotion target just because v3 snapshots
    are missing or fail to load.
    """
    _write_snapshot(tmp_path, legacy_payload())

    observations = load_inflection_learning_observations(tmp_path, encryption_secret=SECRET)
    report = build_learning_report(
        observations,
        {"1111.T": _history([100.0] * 150)},
        _history([100.0] * 150),
        promotion_strategy_version="jp-inflection-shadow-v3",
    )

    assert report["strategy_versions"] == ["jp-inflection-shadow-v2"]
    assert report["promotion_scope_strategy_version"] == "jp-inflection-shadow-v3"
    assert report["observation_count"] == 1
    assert all(count == 0 for count in report["promotion_independent_observation_counts"].values())
    assert report["lessons"] == []


@pytest.mark.parametrize("schema_version", [None, 4.0, "4", 6, True])
def test_loader_rejects_unsupported_schema(tmp_path: Path, schema_version: object) -> None:
    payload = _payload()
    payload["report_schema_version"] = schema_version
    _write_snapshot(tmp_path, payload)

    with pytest.raises(SnapshotLoadError, match="metadata/schema"):
        load_inflection_learning_observations(tmp_path, encryption_secret=SECRET)


def _candidate_v5(ticker: str = "1111.T", **overrides: Any) -> dict[str, Any]:
    return _candidate(ticker) | {
        "features": {"revenue_growth_yoy_pct": 25.0, "turned_profitable": False},
        "score_details": {"fundamental": 12.0, "momentum": 18.0},
        "pre_score": 41.5,
        "sector33_code": "3650",
        "sector33_name": "電気機器",
    } | overrides


def _payload_v5(market_date: str = "2026-01-06", **candidate_overrides: Any) -> dict[str, Any]:
    return _payload(market_date, candidates=[_candidate_v5(**candidate_overrides)]) | {"report_schema_version": 5}


def test_loader_reads_schema5_fields_and_mixes_with_schema3_and_4(tmp_path: Path) -> None:
    _write_snapshot(tmp_path, legacy_payload("2026-01-02"))
    _write_snapshot(tmp_path, _payload("2026-01-05"))
    _write_snapshot(tmp_path, _payload_v5("2026-01-06"))

    rows = {row["signal_date"]: row for row in load_inflection_learning_observations(tmp_path, encryption_secret=SECRET)}

    assert [rows[d]["report_schema_version"] for d in sorted(rows)] == [3, 4, 5]
    new = rows["2026-01-06"]
    assert new["features"] == {"revenue_growth_yoy_pct": 25.0, "turned_profitable": False}
    assert new["score_details"] == {"fundamental": 12.0, "momentum": 18.0}
    assert new["pre_score"] == 41.5 and new["sector33_code"] == "3650"
    assert new["near_52w_high"] is True and new["legacy_breakout_52w"] is None
    for older in (rows["2026-01-02"], rows["2026-01-05"]):
        assert older["features"] is None and older["pre_score"] is None and older["sector33_code"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"features": None},
        {"features": ["not", "a", "dict"]},
        {"score_details": None},
        {"pre_score": None},
        {"pre_score": float("nan")},
        {"pre_score": float("inf")},
        {"pre_score": True},
        {"pre_score": "41.5"},
    ],
)
def test_loader_rejects_invalid_schema5_candidate_fields(tmp_path: Path, overrides: dict[str, Any]) -> None:
    _write_snapshot(tmp_path, _payload_v5(**overrides))

    with pytest.raises(SnapshotLoadError, match="schema-5 candidate fields"):
        load_inflection_learning_observations(tmp_path, encryption_secret=SECRET)


def test_loader_rejects_schema5_candidate_missing_a_field(tmp_path: Path) -> None:
    payload = _payload_v5()
    del payload["candidates"][0]["features"]
    _write_snapshot(tmp_path, payload)

    with pytest.raises(SnapshotLoadError, match="schema-5 candidate fields"):
        load_inflection_learning_observations(tmp_path, encryption_secret=SECRET)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_commit_sha", None),
        ("source_commit_sha", ""),
        ("storage", None),
        ("storage", {"encrypted": False, "snapshot_date_basis": "latest_price_date"}),
        ("storage", {"encrypted": True, "snapshot_date_basis": "generated_at"}),
    ],
)
def test_loader_rejects_untrusted_metadata(tmp_path: Path, field: str, value: object) -> None:
    payload = _payload()
    payload[field] = value
    _write_snapshot(tmp_path, payload)

    with pytest.raises(SnapshotLoadError, match="metadata/schema"):
        load_inflection_learning_observations(tmp_path, encryption_secret=SECRET)


@pytest.mark.parametrize("score", [None, True, float("nan"), float("inf"), -1.0, 101.0])
def test_loader_rejects_invalid_score(tmp_path: Path, score: object) -> None:
    candidate = _candidate()
    candidate["score"] = score
    _write_snapshot(tmp_path, _payload(candidates=[candidate]))

    with pytest.raises(SnapshotLoadError, match="Invalid candidate score"):
        load_inflection_learning_observations(tmp_path, encryption_secret=SECRET)


@pytest.mark.parametrize("field", ["near_52w_high", "near_listing_high"])
@pytest.mark.parametrize("value", ["false", 0, 1, None, pytest.param("missing", id="missing-key")])
def test_loader_rejects_non_boolean_high_flags(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    candidate = _candidate()
    if value == "missing":
        candidate.pop(field)
    else:
        candidate[field] = value
    _write_snapshot(tmp_path, _payload(candidates=[candidate]))

    with pytest.raises(SnapshotLoadError, match="high-proximity flags"):
        load_inflection_learning_observations(tmp_path, encryption_secret=SECRET)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_optional_non_finite_factor_is_missing(tmp_path: Path, value: float) -> None:
    candidate = _candidate()
    candidate["return_20d_pct"] = value
    _write_snapshot(tmp_path, _payload(candidates=[candidate]))

    observation = load_inflection_learning_observations(tmp_path, encryption_secret=SECRET)[0]

    assert observation["return_20d_pct"] is None
    assert _bucket(observation["return_20d_pct"], (0.0,), ("negative", "positive")) == "missing"


def test_independent_rows_use_actual_entry_and_exit_dates() -> None:
    rows = [
        {
            "id": "first",
            "ticker": "1111.T",
            "signal_date": "2026-01-05",
            "horizons": {
                "h5": {
                    "completed": True,
                    "entry_date": "2026-01-08",
                    "exit_date": "2026-01-12",
                }
            },
        },
        {
            "id": "overlap",
            "ticker": "1111.T",
            "signal_date": "2026-01-04",
            "horizons": {
                "h5": {
                    "completed": True,
                    "entry_date": "2026-01-10",
                    "exit_date": "2026-01-14",
                }
            },
        },
        {
            "id": "after",
            "ticker": "1111.T",
            "signal_date": "2026-01-06",
            "horizons": {
                "h5": {
                    "completed": True,
                    "entry_date": "2026-01-13",
                    "exit_date": "2026-01-19",
                }
            },
        },
    ]

    assert [row["id"] for row in _independent_rows(rows, 5)] == ["first", "after"]


def test_evaluation_pairs_benchmark_to_actual_trade_dates() -> None:
    observation = {
        **_candidate(classification="WATCH"),
        "signal_date": "2026-01-05",
        "date": "2026-01-05",
        "strategy_version": "jp-inflection-shadow-v3",
    }
    target = _history([100.0, 105.0, 110.0, 115.0, 120.0, 125.0], start="2026-01-09")
    benchmark = _history([100.0 + index for index in range(20)])

    evaluated = evaluate_learning_observations(
        [observation],
        {"1111.T": target},
        benchmark,
        horizons=(5,),
    )[0]
    outcome = evaluated["horizons"]["h5"]

    assert outcome["entry_date"] == "2026-01-09"
    assert outcome["benchmark_entry_date"] == "2026-01-09"
    assert outcome["exit_date"] == outcome["benchmark_exit_date"] == "2026-01-15"
    assert outcome["explosive"] is True
    assert evaluated["missed_explosion"] is True


@pytest.mark.parametrize(
    ("near_52w", "near_listing", "expected", "absent"),
    [
        (True, False, "near_52w_high_failed_to_outperform", "near_listing_high_failed_to_outperform"),
        (False, True, "near_listing_high_failed_to_outperform", "near_52w_high_failed_to_outperform"),
    ],
)
def test_prediction_miss_reasons_keep_high_types_separate(
    near_52w: bool,
    near_listing: bool,
    expected: str,
    absent: str,
) -> None:
    row = {
        **_candidate(),
        "near_52w_high": near_52w,
        "near_listing_high": near_listing,
        "horizons": {
            "h20": {
                "completed": True,
                "net_return_pct": -1.0,
                "excess_return_pct": -1.0,
                "max_return_pct": 2.0,
            }
        },
    }

    reasons = _prediction_miss_reasons(row)

    assert expected in reasons
    assert absent not in reasons


def test_factor_statistics_cover_positive_negative_and_hold_promotions() -> None:
    rows: list[dict[str, Any]] = []
    for factor, count, explosive, excess in [
        ("positive", 30, True, 1.0),
        ("negative", 30, False, -1.0),
        ("hold", 5, True, 1.0),
    ]:
        rows.extend(
            {
                "factor_labels": [factor],
                "horizons": {
                    "h20": {
                        "explosive": explosive,
                        "excess_return_pct": excess,
                    }
                },
            }
            for _ in range(count)
        )

    statistics = {
        row["factor"]: row
        for row in _factor_statistics(
            rows,
            horizon=20,
            baseline={"explosion_rate_pct": 50.0},
        )
    }

    assert statistics["positive"]["promotion_status"] == "positive_candidate"
    assert statistics["negative"]["promotion_status"] == "negative_candidate"
    assert statistics["hold"]["promotion_status"] == "hold"
    lessons = {row["factor"]: row for row in _lessons({"h20": list(statistics.values())})}
    assert lessons["positive"]["direction"] == "increase_attention"
    assert lessons["negative"]["direction"] == "decrease_attention"
    assert "hold" not in lessons


def test_learning_report_never_auto_applies_and_public_summary_has_no_tickers() -> None:
    observation = {
        **_candidate(),
        "signal_date": "2026-01-05",
        "date": "2026-01-05",
        "strategy_version": "jp-inflection-shadow-v3",
    }
    report = build_learning_report(
        [observation],
        {"1111.T": _history([100.0] * 150)},
        _history([100.0] * 150),
        promotion_strategy_version="jp-inflection-shadow-v3",
    )

    assert report["promotion_gate"]["automatic_production_weight_update"] is False
    public = public_learning_summary(report)
    assert "observations" not in public
    assert "postmortems" not in public
    assert "1111.T" not in str(public)


def test_rebuild_without_snapshots_writes_full_and_public_reports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rebuild_inflection_learning.py",
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert rebuild_main() == 0

    full = json.loads((tmp_path / "artifacts/inflection_learning.json").read_text(encoding="utf-8"))
    public = json.loads((tmp_path / "artifacts/inflection_learning_summary.json").read_text(encoding="utf-8"))
    assert full["observation_count"] == public["observation_count"] == 0
    assert "observations" in full
    assert "observations" not in public


def _calm_then_rally(after: list[float]) -> pd.DataFrame:
    before = [100.0 * (1.002 if index % 2 else 1.0) for index in range(80)]
    return _history(before + after)


def test_vol_explosion_is_diagnostic_and_none_for_incomplete_horizons() -> None:
    """Review #3: a recent observation has 61+ prior closes but no future yet for long horizons."""
    history = _calm_then_rally([102.0, 108.0, 115.0, 122.0, 130.0, 135.0, 136.0, 137.0, 138.0, 139.0, 140.0, 141.0])
    signal_date = str(history.index[79].date())
    observation = {
        **_candidate(classification="WATCH"),
        "signal_date": signal_date,
        "date": signal_date,
        "strategy_version": "jp-inflection-shadow-v3",
    }
    benchmark = _history([100.0 + index for index in range(len(history))])

    evaluated = evaluate_learning_observations([observation], {"1111.T": history}, benchmark)[0]

    assert evaluated["realized_volatility_60d"] == pytest.approx(0.002, rel=0.05)
    h5 = evaluated["horizons"]["h5"]
    assert h5["completed"] is True and h5["explosive"] is True and h5["vol_explosive"] is True
    for key in ("h20", "h60", "h120"):
        assert evaluated["horizons"][key]["completed"] is False
        assert evaluated["horizons"][key]["max_return_pct"] is None
        assert evaluated["horizons"][key]["vol_explosive"] is None

    report = build_learning_report(
        [observation],
        {"1111.T": history},
        benchmark,
        promotion_strategy_version="jp-inflection-shadow-v3",
    )  # completes despite the undecidable horizons
    assert report["explosion_definitions"]["volatility_normalised"]["k"] == 3.0
    assert "explosion_definitions" in public_learning_summary(report)


def test_vol_explosion_is_none_without_enough_prior_history() -> None:
    history = _history([100.0 + index for index in range(30)])  # signal on day 10: far fewer than 61 closes
    signal_date = str(history.index[10].date())
    observation = {
        **_candidate(classification="WATCH"),
        "signal_date": signal_date,
        "date": signal_date,
        "strategy_version": "jp-inflection-shadow-v3",
    }

    evaluated = evaluate_learning_observations([observation], {"1111.T": history}, _history([100.0] * 30), horizons=(5,))[0]

    assert evaluated["realized_volatility_60d"] is None
    assert evaluated["horizons"]["h5"]["completed"] is True
    assert evaluated["horizons"]["h5"]["vol_explosive"] is None
    assert evaluated["horizons"]["h5"]["explosive"] in (True, False)  # the production definition is unaffected


# --- REQ-043: significance testing and multiple-comparison correction ----------------------------


def test_fisher_exact_matches_known_values() -> None:
    from src.evaluation.inflection_learning import fisher_exact_two_sided

    assert fisher_exact_two_sided(3, 1, 1, 3) == pytest.approx(34 / 70)  # Fisher's tea-tasting example
    assert fisher_exact_two_sided(0, 5, 5, 0) == pytest.approx(2 / 252)
    assert fisher_exact_two_sided(8, 2, 1, 5) == pytest.approx(0.034965, rel=1e-4)  # scipy documentation example
    # symmetric in swapping rows/columns
    assert fisher_exact_two_sided(8, 1, 2, 5) == pytest.approx(fisher_exact_two_sided(8, 2, 1, 5))


def test_fisher_exact_handles_degenerate_tables_and_rejects_negatives() -> None:
    from src.evaluation.inflection_learning import fisher_exact_two_sided

    assert fisher_exact_two_sided(3, 0, 2, 0) == 1.0  # everything exploded
    assert fisher_exact_two_sided(0, 3, 0, 2) == 1.0  # nothing exploded
    assert fisher_exact_two_sided(0, 0, 0, 0) == 1.0
    with pytest.raises(ValueError, match="negative"):
        fisher_exact_two_sided(-1, 2, 3, 4)


def test_benjamini_hochberg_matches_known_examples_and_enforces_monotonicity() -> None:
    from src.evaluation.inflection_learning import benjamini_hochberg

    assert benjamini_hochberg([0.01, 0.04, 0.03, 0.005]) == pytest.approx([0.02, 0.04, 0.04, 0.02])
    # raw p*m/rank is 0.03, 0.045, 0.031: the middle value must be pulled down to stay monotone
    assert benjamini_hochberg([0.01, 0.03, 0.031]) == pytest.approx([0.03, 0.031, 0.031])
    assert benjamini_hochberg([0.9, 0.8]) == pytest.approx([0.9, 0.9])
    assert benjamini_hochberg([0.5]) == [0.5]
    assert benjamini_hochberg([]) == []
    assert all(q <= 1.0 for q in benjamini_hochberg([0.6, 0.7, 0.99]))


def test_wilson_interval_matches_reference_values() -> None:
    from src.evaluation.inflection_learning import wilson_interval

    assert wilson_interval(0, 10) == pytest.approx((0.0, 0.27754), abs=1e-4)
    low, high = wilson_interval(5, 10) or (0.0, 0.0)
    assert (low + high) / 2 == pytest.approx(0.5) and high - low < 0.6
    assert wilson_interval(0, 0) is None


def _rows(factor: str, count: int, exploded: int, excess: float = 1.0) -> list[dict[str, Any]]:
    return [
        {
            "factor_labels": [factor],
            "horizons": {"h20": {"explosive": index < exploded, "excess_return_pct": excess}},
        }
        for index in range(count)
    ]


def test_factor_statistics_report_the_two_by_two_test_and_interval() -> None:
    from src.evaluation.inflection_learning import fisher_exact_two_sided

    rows = _rows("strong", 100, 40) + _rows("other", 100, 10)

    statistics = {row["factor"]: row for row in _factor_statistics(rows, horizon=20, baseline={"explosion_rate_pct": 25.0})}

    assert statistics["strong"]["fisher_p_value"] == pytest.approx(fisher_exact_two_sided(40, 60, 10, 90), rel=1e-5)
    assert statistics["strong"]["fisher_p_value"] < 1e-5
    low, high = statistics["strong"]["explosion_rate_ci95"]
    assert low < 40.0 < high
    assert statistics["strong"]["bh_q_value"] is None  # filled in only by the family-wide correction
    assert statistics["strong"]["uncorrected_direction"] == "positive_candidate"


def test_a_factor_present_on_every_row_has_no_table_to_test() -> None:
    statistics = _factor_statistics(_rows("always", 40, 10), horizon=20, baseline={"explosion_rate_pct": 25.0})

    assert statistics[0]["fisher_p_value"] is None and statistics[0]["explosion_rate_ci95"] is not None


def _stat(name: str, p: float | None, status: str = "hold", n: int = 50) -> dict[str, Any]:
    return {
        "factor": name,
        "independent_observations": n,
        "fisher_p_value": p,
        "bh_q_value": None,
        "uncorrected_direction": status,
        "promotion_status": status,
    }


def test_one_chance_p_value_among_160_tests_is_not_promoted() -> None:
    from src.evaluation.inflection_learning import _apply_multiple_testing

    family = {f"h{h}": [_stat(f"f{h}-{i}", 0.30 + i * 0.01) for i in range(40)] for h in (5, 20, 60, 120)}
    family["h20"][7] = _stat("lucky", 0.04, "positive_candidate")

    tests = _apply_multiple_testing(family)

    lucky = next(s for stats in family.values() for s in stats if s["factor"] == "lucky")
    assert tests == 160
    assert lucky["promotion_status"] == "hold" and lucky["uncorrected_direction"] == "positive_candidate"
    # BH pulls q down to the smallest raw value over all larger ranks: the largest p (0.69) at rank 160.
    assert lucky["bh_q_value"] == pytest.approx(0.69)


def test_a_clearly_significant_factor_survives_the_correction() -> None:
    from src.evaluation.inflection_learning import _apply_multiple_testing

    family = {f"h{h}": [_stat(f"f{h}-{i}", 0.30 + i * 0.01) for i in range(40)] for h in (5, 20, 60, 120)}
    family["h60"][3] = _stat("real", 1e-6, "negative_candidate", n=120)

    _apply_multiple_testing(family)

    real = next(s for s in family["h60"] if s["factor"] == "real")
    assert real["promotion_status"] == "negative_candidate" and real["bh_q_value"] < 0.001
    assert family["h60"][0]["factor"] == "real"  # promoted factors sort first


def test_candidates_without_a_testable_table_are_demoted_and_left_out_of_the_family() -> None:
    from src.evaluation.inflection_learning import _apply_multiple_testing

    family = {"h20": [_stat("untestable", None, "positive_candidate"), _stat("a", 0.2), _stat("b", 0.3)]}

    assert _apply_multiple_testing(family) == 2
    untestable = next(s for s in family["h20"] if s["factor"] == "untestable")
    assert untestable["promotion_status"] == "hold" and untestable["bh_q_value"] is None


def test_promotion_requires_the_q_value_not_only_lift_and_excess_return() -> None:
    """A factor that passes the old lift rule but is not significant is no longer promoted."""
    rows = _rows("weak", 30, 12) + _rows("rest", 100, 25)

    stats = _factor_statistics(rows, horizon=20, baseline={"explosion_rate_pct": 37 / 130 * 100})
    weak_before = next(s for s in stats if s["factor"] == "weak")
    assert weak_before["promotion_status"] == "positive_candidate"  # old rule: n >= 30, lift 1.4, excess > 0
    assert weak_before["fisher_p_value"] > 0.10

    from src.evaluation.inflection_learning import _apply_multiple_testing

    family = {"h20": stats}
    _apply_multiple_testing(family)
    weak_after = next(s for s in family["h20"] if s["factor"] == "weak")
    assert weak_after["promotion_status"] == "hold" and weak_after["bh_q_value"] > 0.10
    assert _lessons(family) == []


def test_report_records_the_test_family_and_exposes_p_and_q_values() -> None:
    history = _history([100.0 + index * 0.5 for index in range(160)])
    signal_date = str(history.index[10].date())
    observation = {
        **_candidate(classification="WATCH"),
        "signal_date": signal_date,
        "date": signal_date,
        "strategy_version": "jp-inflection-shadow-v3",
    }

    report = build_learning_report(
        [observation], {"1111.T": history}, _history([100.0 + index for index in range(160)]),
        promotion_strategy_version="jp-inflection-shadow-v3",
    )

    gate = report["promotion_gate"]
    assert gate["maximum_bh_q_value"] == 0.10 and "benjamini_hochberg" in gate["correction"]
    assert "fisher" in gate["test"] and isinstance(gate["tests_in_family"], int)
    public = public_learning_summary(report)
    first = public["promotion_factor_statistics"]["h20"][0]
    assert {"fisher_p_value", "bh_q_value", "explosion_rate_ci95", "uncorrected_direction"} <= set(first)
    assert any("uncorrected" in text for text in report["limitations"])


def test_main_fetches_once_over_the_shared_window_for_cli_given_snapshot_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Legacy and v3 observations share one window sized from the directories actually passed."""
    from datetime import date, timedelta

    from src.data.forward_prices import PriceHistories

    v3, legacy = tmp_path / "fixtures" / "v3", tmp_path / "fixtures" / "legacy"
    for directory in (v3, legacy):
        directory.mkdir(parents=True)
    _write_snapshot(v3, _payload("2026-01-06", candidates=[_candidate("1111.T")]))
    _write_snapshot(legacy, legacy_payload("2026-01-02", candidates=[_legacy_candidate("2222.T")]))
    history = _history([100.0 + index for index in range(200)], start="2025-09-01")
    history["Adj Close"] = history["Close"]
    calls: list[dict[str, Any]] = []

    def fake_fetch(tickers: list[str], start: date, end: date, **kwargs: Any) -> PriceHistories:
        calls.append({"tickers": sorted(tickers), "start": start, "end": end, **kwargs})
        return PriceHistories(raw=dict.fromkeys(tickers, history), start=start, end=end)

    monkeypatch.setenv("SNAPSHOT_ENCRYPTION_KEY", SECRET)
    monkeypatch.setattr("scripts.rebuild_inflection_learning.fetch_price_histories", fake_fetch)
    monkeypatch.setattr(
        sys,
        "argv",
        ["x", "--repo-root", str(tmp_path), "--snapshot-dir", "fixtures/v3", "--legacy-snapshot-dir", "fixtures/legacy"],
    )

    assert rebuild_main() == 0

    assert len(calls) == 1
    assert calls[0]["tickers"] == ["1111.T", "1306.T", "2222.T"]
    assert calls[0]["start"] == date(2026, 1, 2) - timedelta(days=100)  # the legacy directory's earliest snapshot
    assert calls[0]["required"] == {"1306.T"}
    assert calls[0]["cache_path"] == tmp_path / "artifacts" / "price_cache.pkl"
    full = json.loads((tmp_path / "artifacts/inflection_learning.json").read_text(encoding="utf-8"))
    assert full["observation_count"] == 2
    assert full["price_unavailable_ticker_count"] == 0
