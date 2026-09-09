from __future__ import annotations

import json
import logging
import sys
from unittest.mock import patch

import pandas as pd
import pytest

from scripts.rebuild_inflection_forward_validation import (
    BENCHMARK_ROUND_TRIP_COST_PCT,
    SPLIT_ONLY,
    _build_group_report,
    _changed_price_rows,
    _fetch_adjusted_histories,
    _history_row_hashes,
    _persist_price_hashes,
    _report_breakdowns,
    _summary_only,
    regime_label,
)
from scripts.rebuild_inflection_forward_validation import (
    main as rebuild_main,
)
from src.data.snapshot_crypto import decrypt_json, encrypt_json
from src.evaluation.inflection_backtest import simulate_signal
from src.evaluation.inflection_forward import (
    BENCHMARK_TICKER,
    SnapshotLoadError,
    benchmark_returns_by_signal_date,
    enrich_trades_with_benchmark,
    load_inflection_signals,
    paired_benchmark_returns,
    summarize_benchmark_excess,
)

SECRET = "test-snapshot-secret"


def _payload() -> dict:
    return {
        "mode": "shadow",
        "strategy_version": "jp-inflection-shadow-v1",
        "report_schema_version": 3,
        "source_commit_sha": "abc123",
        "latest_price_date": "2026-09-08",
        "storage": {
            "format": "fernet-v1",
            "encrypted": True,
            "key_id": "test",
            "snapshot_date_basis": "latest_price_date",
        },
        "data_policy": {"jquants_plan": "free", "jquants_data_delay_weeks": 12},
        "runtime_versions": {"yfinance": "1.7.0", "pandas": "3.0.5"},
        "candidates": [
            {"ticker": "1111.T", "classification": "EARLY_CANDIDATE", "score": 80.0},
            {"ticker": "2222.T", "classification": "WATCH", "score": 60.0},
        ],
    }


def test_load_inflection_signals_filters_to_early_candidates(tmp_path) -> None:
    snapshot_dir = tmp_path / "inflection"
    snapshot_dir.mkdir()
    payload = _payload()
    (snapshot_dir / "2026-09-08.enc").write_text(encrypt_json(payload, SECRET), encoding="utf-8")

    signals = load_inflection_signals(snapshot_dir, encryption_secret=SECRET)

    assert signals == [
        {
            "ticker": "1111.T",
            "signal_date": "2026-09-08",
            "date": "2026-09-08",
            "score": 80.0,
            "classification": "EARLY_CANDIDATE",
            "strategy_version": "jp-inflection-shadow-v1",
            "report_schema_version": 3,
            "source_commit_sha": "abc123",
            "jquants_plan": "free",
            "jquants_data_delay_weeks": 12,
            "runtime_versions": {"yfinance": "1.7.0", "pandas": "3.0.5"},
        }
    ]


def test_load_inflection_signals_rejects_filename_market_date_mismatch(tmp_path) -> None:
    snapshot_dir = tmp_path / "inflection"
    snapshot_dir.mkdir()
    payload = _payload()
    (snapshot_dir / "2026-09-09.enc").write_text(encrypt_json(payload, SECRET), encoding="utf-8")

    with pytest.raises(SnapshotLoadError, match="metadata/schema"):
        load_inflection_signals(snapshot_dir, encryption_secret=SECRET)


@pytest.mark.parametrize("schema_version", [None, True, "3", 0])
def test_load_inflection_signals_rejects_invalid_schema_version(tmp_path, schema_version: object) -> None:
    snapshot_dir = tmp_path / "inflection"
    snapshot_dir.mkdir()
    payload = _payload()
    payload["report_schema_version"] = schema_version
    (snapshot_dir / "2026-09-08.enc").write_text(encrypt_json(payload, SECRET), encoding="utf-8")

    with pytest.raises(SnapshotLoadError, match="metadata/schema"):
        load_inflection_signals(snapshot_dir, encryption_secret=SECRET)


def test_load_inflection_signals_fails_on_wrong_key(tmp_path) -> None:
    snapshot_dir = tmp_path / "inflection"
    snapshot_dir.mkdir()
    payload = _payload()
    (snapshot_dir / "2026-09-08.enc").write_text(encrypt_json(payload, SECRET), encoding="utf-8")

    with pytest.raises(SnapshotLoadError, match="decrypt or decode"):
        load_inflection_signals(snapshot_dir, encryption_secret="wrong-secret")


def test_load_inflection_signals_ignores_plaintext_json(tmp_path) -> None:
    snapshot_dir = tmp_path / "inflection"
    snapshot_dir.mkdir()
    (snapshot_dir / "2026-09-08.json").write_text('{"ticker":"public"}', encoding="utf-8")

    assert load_inflection_signals(snapshot_dir, encryption_secret=SECRET) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [("strategy_version", "jp-inflection-shadow-v2"), ("report_schema_version", 4)],
)
def test_load_inflection_signals_rejects_mixed_versions(tmp_path, field: str, value: object) -> None:
    snapshot_dir = tmp_path / "inflection"
    snapshot_dir.mkdir()
    first = _payload()
    second = _payload()
    second["latest_price_date"] = "2026-09-09"
    second[field] = value
    (snapshot_dir / "2026-09-08.enc").write_text(encrypt_json(first, SECRET), encoding="utf-8")
    (snapshot_dir / "2026-09-09.enc").write_text(encrypt_json(second, SECRET), encoding="utf-8")

    with pytest.raises(SnapshotLoadError, match="Mixed strategy/schema versions"):
        load_inflection_signals(snapshot_dir, encryption_secret=SECRET)


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -1.0, 101.0])
def test_load_inflection_signals_rejects_invalid_score(tmp_path, score: float) -> None:
    snapshot_dir = tmp_path / "inflection"
    snapshot_dir.mkdir()
    payload = _payload()
    payload["candidates"][0]["score"] = score
    (snapshot_dir / "2026-09-08.enc").write_text(encrypt_json(payload, SECRET), encoding="utf-8")

    with pytest.raises(SnapshotLoadError, match="Invalid candidate score"):
        load_inflection_signals(snapshot_dir, encryption_secret=SECRET)


def test_load_inflection_signals_rejects_missing_score(tmp_path) -> None:
    snapshot_dir = tmp_path / "inflection"
    snapshot_dir.mkdir()
    payload = _payload()
    payload["candidates"][0].pop("score")
    (snapshot_dir / "2026-09-08.enc").write_text(encrypt_json(payload, SECRET), encoding="utf-8")

    with pytest.raises(SnapshotLoadError, match="Invalid candidate score"):
        load_inflection_signals(snapshot_dir, encryption_secret=SECRET)


def _history(open_price: float, closes: list[float]) -> pd.DataFrame:
    index = pd.to_datetime(["2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11"])
    opens = [open_price, open_price, open_price, open_price]
    close_values = [open_price, *closes]
    return pd.DataFrame({"Open": opens, "Close": close_values}, index=index)


def test_topix_benchmark_uses_same_next_open_and_holding_rule() -> None:
    history = _history(100.0, [101.0, 102.0, 103.0])
    returns = benchmark_returns_by_signal_date(
        ["2026-09-08"],
        history,
        holding_days=2,
        round_trip_cost_pct=0.2,
    )

    assert returns["2026-09-08"] == 1.8


def test_enrich_trades_reports_excess_and_beat_rate() -> None:
    strategy_history = _history(100.0, [102.0, 104.0, 105.0])
    trade = simulate_signal(
        {"ticker": "1111.T", "signal_date": "2026-09-08", "score": 80.0},
        strategy_history,
        holding_days=2,
        round_trip_cost_pct=0.2,
    )
    rows = enrich_trades_with_benchmark([trade], {"2026-09-08": 1.8})
    summary = summarize_benchmark_excess(rows)

    assert rows[0]["benchmark_ticker"] == BENCHMARK_TICKER
    assert rows[0]["benchmark_net_return_pct"] == 1.8
    assert rows[0]["excess_return_pct"] == 2.0
    assert rows[0]["beat_benchmark"] is True
    assert summary["evaluated"] == 1
    assert summary["beat_benchmark_rate_pct"] == 100.0


def test_forward_price_fetch_retries_transient_failure() -> None:
    history = pd.DataFrame(
        {"Open": [100.0], "High": [101.0], "Low": [99.0], "Close": [100.0]},
        index=pd.to_datetime(["2026-09-09"]),
    )
    sleeps: list[float] = []
    with patch("yfinance.Ticker") as ticker:
        ticker.return_value.history.side_effect = [RuntimeError("temporary"), history]
        result = _fetch_adjusted_histories(
            [{"ticker": "1111.T", "date": "2026-09-08"}],
            max_horizon=5,
            max_retries=1,
            retry_backoff_seconds=0,
            request_interval_seconds=0,
            sleep=sleeps.append,
        )

    assert result["1111.T"].equals(history)
    assert ticker.return_value.history.call_count == 2
    assert sleeps == [0]


def test_forward_price_fetch_failure_hides_candidate_ticker() -> None:
    with patch("yfinance.Ticker") as ticker:
        ticker.return_value.history.side_effect = RuntimeError("failure for 1111.T")
        with pytest.raises(RuntimeError, match=r"failed for 1 ticker\(s\)") as error:
            _fetch_adjusted_histories(
                [{"ticker": "1111.T", "date": "2026-09-08"}],
                max_horizon=5,
                max_retries=0,
                request_interval_seconds=0,
            )

    assert "1111.T" not in str(error.value)


def test_forward_price_fetch_suppresses_provider_ticker_log(caplog: pytest.LogCaptureFixture) -> None:
    provider_logger = logging.getLogger("yfinance")
    was_disabled = provider_logger.disabled

    def fail_with_log(ticker: str) -> None:
        provider_logger.error("%s: provider failure", ticker)
        raise RuntimeError("provider failure")

    with (
        caplog.at_level(logging.ERROR, logger="yfinance"),
        patch("yfinance.Ticker", side_effect=fail_with_log),
        pytest.raises(RuntimeError, match=r"failed for 1 ticker\(s\)"),
    ):
        _fetch_adjusted_histories(
            [{"ticker": "1111.T", "date": "2026-09-08"}],
            max_horizon=5,
            max_retries=0,
            request_interval_seconds=0,
        )

    assert "1111.T" not in caplog.text
    assert provider_logger.disabled is was_disabled


def test_forward_split_only_fetch_requests_actions_and_adjusts_splits() -> None:
    history = pd.DataFrame(
        {
            "Open": [100.0, 55.0],
            "High": [110.0, 60.0],
            "Low": [90.0, 50.0],
            "Close": [100.0, 55.0],
            "Stock Splits": [0.0, 2.0],
        },
        index=pd.to_datetime(["2026-09-09", "2026-09-10"]),
    )
    with patch("yfinance.Ticker") as ticker:
        ticker.return_value.history.return_value = history
        result = _fetch_adjusted_histories(
            [{"ticker": "1111.T", "date": "2026-09-08"}],
            max_horizon=5,
            request_interval_seconds=0,
            price_basis=SPLIT_ONLY,
        )

    assert ticker.return_value.history.call_args.kwargs["auto_adjust"] is False
    assert ticker.return_value.history.call_args.kwargs["actions"] is True
    assert ticker.return_value.history.call_args.kwargs["raise_errors"] is True
    assert result["1111.T"]["Close"].tolist() == pytest.approx([50.0, 55.0])


def test_price_hashes_are_stable_and_only_common_changed_dates_are_reported() -> None:
    first = pd.DataFrame(
        {"Close": [100, float("nan")], "Low": [90, 91], "High": [110, 111], "Open": [95, 96]},
        index=pd.to_datetime(["2026-09-09", "2026-09-10"]),
    )
    same = first.astype(float)[["Open", "High", "Low", "Close"]]
    original = _history_row_hashes(first)

    assert _history_row_hashes(same) == original
    previous = {"hashes": {"1111.T": {"split_only": original}}}
    appended = dict(original)
    appended["2026-09-11"] = "new"
    assert _changed_price_rows(previous, {"1111.T": {"split_only": appended}}) == []
    appended["2026-09-09"] = "changed"
    assert _changed_price_rows(previous, {"1111.T": {"split_only": appended}}) == [
        {"ticker": "1111.T", "price_basis": "split_only", "date": "2026-09-09"}
    ]


def test_price_hashes_ignore_later_uniform_corporate_action_rescaling() -> None:
    index = pd.to_datetime(["2026-09-08", "2026-09-09"])
    before = pd.DataFrame(
        {"Open": [100.0, 110.0], "High": [105.0, 115.0], "Low": [95.0, 105.0], "Close": [102.0, 112.0]},
        index=index,
    )
    after = before / 2.0
    after.loc[pd.Timestamp("2026-09-10")] = [60.0, 65.0, 58.0, 62.0]

    assert _history_row_hashes(after).keys() > _history_row_hashes(before).keys()
    assert _changed_price_rows(
        {"hashes": {"1111.T": {"split_only": _history_row_hashes(before)}}},
        {"1111.T": {"split_only": _history_row_hashes(after)}},
    ) == []


def test_price_hash_warning_hides_ticker_and_persists_encrypted_details(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "hashes.enc"
    old = {"1111.T": {"split_only": {"2026-09-09": "old"}}}
    new = {"1111.T": {"split_only": {"2026-09-09": "new"}}}
    _persist_price_hashes(path, old, SECRET)
    _persist_price_hashes(path, new, SECRET)

    output = capsys.readouterr().out
    assert '"changed_count": 1' in output
    assert "1111.T" not in output
    assert decrypt_json(path.read_text(encoding="utf-8"), SECRET)["revisions"] == [
        {"ticker": "1111.T", "price_basis": "split_only", "date": "2026-09-09"}
    ]


def test_forward_summary_removes_prediction_rows() -> None:
    report = {
        "signal_count": 1,
        "horizons": {"h5": {"summary": {"completed": 1}, "trades": [{"ticker": "1111.T"}]}},
    }

    assert _summary_only(report) == {
        "signal_count": 1,
        "horizons": {"h5": {"summary": {"completed": 1}}},
    }


def test_load_inflection_signals_can_load_all_tracked_classifications(tmp_path) -> None:
    snapshot_dir = tmp_path / "inflection"
    snapshot_dir.mkdir()
    payload = _payload()
    payload["candidates"].extend(
        [
            {"ticker": "3333.T", "classification": "NONE", "score": 40.0},
            {"ticker": "4444.T", "classification": "OVEREXTENDED", "score": 90.0},
        ]
    )
    (snapshot_dir / "2026-09-08.enc").write_text(encrypt_json(payload, SECRET), encoding="utf-8")

    signals = load_inflection_signals(
        snapshot_dir,
        encryption_secret=SECRET,
        classifications=("EARLY_CANDIDATE", "WATCH", "NONE", "OVEREXTENDED"),
    )

    assert {signal["classification"] for signal in signals} == {
        "EARLY_CANDIDATE",
        "WATCH",
        "NONE",
        "OVEREXTENDED",
    }


def test_paired_benchmark_uses_each_trades_actual_dates() -> None:
    index = pd.bdate_range("2026-01-01", periods=8)
    benchmark = pd.DataFrame(
        {"Open": [100.0] * 8, "Close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0]},
        index=index,
    )
    candidate = benchmark.copy()
    trades = [
        simulate_signal(
            {"ticker": ticker, "signal_date": "2026-01-01", "score": 80},
            candidate,
            holding_days=days,
            round_trip_cost_pct=0,
        )
        for ticker, days in (("A.T", 2), ("B.T", 4))
    ]

    rows = paired_benchmark_returns(
        trades,
        benchmark,
        round_trip_cost_pct=BENCHMARK_ROUND_TRIP_COST_PCT,
    )

    assert rows[0]["benchmark_exit_date"] != rows[1]["benchmark_exit_date"]
    assert rows[0]["benchmark_net_return_pct"] != rows[1]["benchmark_net_return_pct"]


def test_paired_benchmark_rejects_dates_that_invert_after_fill() -> None:
    trade = simulate_signal(
        {"ticker": "A.T", "signal_date": "2026-01-01", "score": 80},
        pd.DataFrame(
            {"Open": [100.0, 100.0], "Close": [100.0, 101.0]},
            index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
        ),
        holding_days=1,
        round_trip_cost_pct=0,
    )
    benchmark = pd.DataFrame(
        {"Open": [float("nan"), 100.0], "Close": [101.0, float("nan")]},
        index=pd.to_datetime(["2026-01-01", "2026-01-05"]),
    )

    row = paired_benchmark_returns([trade], benchmark, round_trip_cost_pct=0)[0]

    assert row["benchmark_net_return_pct"] is None
    assert row["excess_return_pct"] is None


def test_forward_price_fetch_extends_requested_lookback() -> None:
    history = pd.DataFrame(
        {"Open": [100.0], "High": [101.0], "Low": [99.0], "Close": [100.0]},
        index=pd.to_datetime(["2026-09-09"]),
    )
    with patch("yfinance.Ticker") as ticker:
        ticker.return_value.history.return_value = history
        _fetch_adjusted_histories(
            [{"ticker": "1306.T", "date": "2026-09-08"}],
            max_horizon=5,
            extra_lookback_days=35,
            request_interval_seconds=0,
        )

    assert ticker.return_value.history.call_args.kwargs["start"] == "2026-07-25"


@pytest.mark.parametrize(
    ("first", "last", "expected"),
    [(100.0, 99.0, "down"), (100.0, 100.0, "up"), (100.0, 101.0, "up")],
)
def test_regime_label_uses_twenty_session_return(first: float, last: float, expected: str) -> None:
    closes = [first, *([100.0] * 19), last]
    history = pd.DataFrame({"Close": closes}, index=pd.bdate_range("2026-01-01", periods=21))
    assert regime_label(history, str(history.index[-1].date())) == expected


def test_regime_label_reports_unknown_with_fewer_than_twenty_sessions() -> None:
    history = pd.DataFrame(
        {"Close": [100.0] * 20},
        index=pd.bdate_range("2026-01-01", periods=20),
    )
    assert regime_label(history, str(history.index[-1].date())) == "unknown"


def test_group_report_has_all_horizons_stops_and_aligned_breakdowns() -> None:
    index = pd.bdate_range("2025-01-01", periods=340)
    history = pd.DataFrame(
        {
            "Open": [100.0] * 340,
            "High": [105.0] * 340,
            "Low": [95.0] * 340,
            "Close": [100.0] * 340,
        },
        index=index,
    )
    signal_date = str(index[20].date())
    signals = [
        {
            "ticker": "1111.T",
            "signal_date": signal_date,
            "date": signal_date,
            "score": 80.0,
            "classification": "EARLY_CANDIDATE",
        }
    ]

    report = _build_group_report(
        signals,
        {"1111.T": history},
        {"1111.T": history},
        history,
        [signal_date],
    )

    assert set(report["horizons"]) == {"h5", "h20", "h60", "h126", "h252"}
    assert len(report["exit_strategies"]) == 9
    h5 = report["horizons"]["h5"]
    assert h5["summary"]["sample_count"] == sum(h5["score_band_sample_counts"].values())
    assert h5["summary"]["sample_count"] == sum(h5["regime_sample_counts"].values())
    assert h5["trades"][0]["benchmark_net_return_pct"] == -BENCHMARK_ROUND_TRIP_COST_PCT
    assert h5["stress"]["trades"][0]["benchmark_net_return_pct"] == -BENCHMARK_ROUND_TRIP_COST_PCT
    trailing = report["exit_strategies"]["trailing_10pct_h60"]
    assert trailing["trades"][0]["benchmark_net_return_pct"] == -BENCHMARK_ROUND_TRIP_COST_PCT
    assert trailing["stress"]["trades"][0]["benchmark_net_return_pct"] == (
        -BENCHMARK_ROUND_TRIP_COST_PCT
    )
    assert trailing["benchmark_excess"]["evaluated"] == 1


def test_report_breakdowns_exclude_incomplete_trades() -> None:
    complete = simulate_signal(
        {"ticker": "A.T", "signal_date": "2026-01-01", "score": 50},
        pd.DataFrame(
            {"Open": [100.0, 100.0], "Close": [100.0, 100.0]},
            index=pd.bdate_range("2026-01-01", periods=2),
        ),
        holding_days=1,
    )
    incomplete = simulate_signal(
        {"ticker": "B.T", "signal_date": "2026-01-01", "score": 100},
        pd.DataFrame(),
        holding_days=1,
    )
    benchmark = pd.DataFrame(
        {"Close": [100.0] * 21},
        index=pd.bdate_range("2025-12-04", periods=21),
    )

    counts = _report_breakdowns([complete, incomplete], benchmark)

    assert sum(counts["score_band_sample_counts"].values()) == 1
    assert sum(counts["regime_sample_counts"].values()) == 1


def test_main_writes_three_groups_and_tracked_pool_recall(tmp_path, monkeypatch) -> None:
    snapshot_dir = tmp_path / "dashboard" / "data" / "inflection"
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "2026-01-29.enc").write_text("placeholder", encoding="utf-8")
    index = pd.bdate_range("2026-01-01", periods=340)
    history = pd.DataFrame(
        {
            "Open": [100.0] * 340,
            "High": [105.0] * 340,
            "Low": [95.0] * 340,
            "Close": [100.0] * 340,
        },
        index=index,
    )
    signal_date = str(index[20].date())
    observations = [
        {
            "ticker": ticker,
            "signal_date": signal_date,
            "date": signal_date,
            "score": score,
            "classification": classification,
            "strategy_version": "v1",
            "report_schema_version": 3,
        }
        for ticker, score, classification in (
            ("1111.T", 80.0, "EARLY_CANDIDATE"),
            ("2222.T", 60.0, "WATCH"),
            ("3333.T", 40.0, "NONE"),
            ("4444.T", 90.0, "OVEREXTENDED"),
        )
    ]

    def fake_fetch(rows, **_kwargs):
        return {str(row["ticker"]): history for row in rows}

    monkeypatch.setattr(
        "scripts.rebuild_inflection_forward_validation.snapshot_encryption_secret",
        lambda: SECRET,
    )
    monkeypatch.setattr(
        "scripts.rebuild_inflection_forward_validation.load_inflection_signals",
        lambda *_args, **_kwargs: observations,
    )
    monkeypatch.setattr(
        "scripts.rebuild_inflection_forward_validation._fetch_adjusted_histories",
        fake_fetch,
    )
    monkeypatch.setattr(
        "scripts.rebuild_inflection_forward_validation._persist_price_hashes",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rebuild_inflection_forward_validation.py",
            "--repo-root",
            str(tmp_path),
            "--output",
            "artifacts/report.json",
        ],
    )

    assert rebuild_main() == 0
    report = json.loads((tmp_path / "artifacts" / "report.json").read_text(encoding="utf-8"))
    assert set(report["groups"]) == {"early_candidate", "watch", "none"}
    assert report["tracked_pool_explosion_recall"]["exploded_ticker_count"] == 0
    assert report["groups"]["early_candidate"]["signal_count"] == 1
    assert report["groups"]["watch"]["signal_count"] == 1
    assert report["groups"]["none"]["signal_count"] == 1
