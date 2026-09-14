from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from scripts.rebuild_inflection_learning import _fetch_learning_histories
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
    )

    assert report["strategy_versions"] == ["jp-inflection-shadow-v3", "jp-inflection-shadow-v4"]
    assert report["promotion_scope_strategy_version"] == "jp-inflection-shadow-v4"


@pytest.mark.parametrize("schema_version", [None, 3, 4.0, "4", 5, True])
def test_loader_rejects_unsupported_schema(tmp_path: Path, schema_version: object) -> None:
    payload = _payload()
    payload["report_schema_version"] = schema_version
    _write_snapshot(tmp_path, payload)

    with pytest.raises(SnapshotLoadError, match="metadata/schema"):
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
    )

    assert report["promotion_gate"]["automatic_production_weight_update"] is False
    public = public_learning_summary(report)
    assert "observations" not in public
    assert "postmortems" not in public
    assert "1111.T" not in str(public)


def test_learning_price_fetcher_batches_tickers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    index = pd.date_range("2026-01-02", periods=10, freq="B")

    def fake_download(tickers: str, **kwargs: object) -> pd.DataFrame:
        del kwargs
        names = tickers.split()
        calls.append(names)
        values = {
            (ticker, column): [100.0] * len(index) for ticker in names for column in ("Open", "High", "Low", "Close")
        }
        frame = pd.DataFrame(values, index=index)
        frame.columns = pd.MultiIndex.from_tuples(frame.columns)
        return frame

    monkeypatch.setattr("yfinance.download", fake_download)
    rows = [
        {"ticker": "1111.T", "date": "2026-01-05"},
        {"ticker": "2222.T", "date": "2026-01-05"},
        {"ticker": "3333.T", "date": "2026-01-05"},
    ]

    histories = _fetch_learning_histories(
        rows,
        max_horizon=5,
        batch_size=2,
        max_retries=0,
        batch_interval_seconds=0.0,
        sleep=lambda _: None,
    )

    assert set(histories) == {"1111.T", "2222.T", "3333.T"}
    assert calls == [["1111.T", "2222.T"], ["3333.T"]]


def test_learning_price_failure_hides_provider_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_text = "SECRET.T provider detail"

    def fake_download(*args: object, **kwargs: object) -> pd.DataFrame:
        del args, kwargs
        print(secret_text)
        print(secret_text, file=sys.stderr)
        logging.getLogger("yfinance").error(secret_text)
        raise RuntimeError(secret_text)

    monkeypatch.setattr("yfinance.download", fake_download)
    with pytest.raises(RuntimeError, match=r"failed for 1 ticker\(s\)") as error:
        _fetch_learning_histories(
            [{"ticker": "SECRET.T", "date": "2026-01-05"}],
            max_horizon=5,
            max_retries=0,
            batch_interval_seconds=0.0,
            sleep=lambda _: None,
        )

    captured = capsys.readouterr()
    for hidden in ("SECRET.T", "provider detail"):
        assert hidden not in str(error.value)
        assert hidden not in captured.out
        assert hidden not in captured.err
        assert hidden not in caplog.text


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
