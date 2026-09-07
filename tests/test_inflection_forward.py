from __future__ import annotations

import pandas as pd

from src.data.snapshot_crypto import encrypt_json
from src.evaluation.inflection_backtest import simulate_signal
from src.evaluation.inflection_forward import (
    BENCHMARK_TICKER,
    benchmark_returns_by_signal_date,
    enrich_trades_with_benchmark,
    load_inflection_signals,
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

    assert load_inflection_signals(snapshot_dir, encryption_secret=SECRET) == []


def test_load_inflection_signals_ignores_plaintext_json(tmp_path) -> None:
    snapshot_dir = tmp_path / "inflection"
    snapshot_dir.mkdir()
    (snapshot_dir / "2026-09-08.json").write_text('{"ticker":"public"}', encoding="utf-8")

    assert load_inflection_signals(snapshot_dir, encryption_secret=SECRET) == []


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
