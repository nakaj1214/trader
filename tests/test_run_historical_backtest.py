from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import requests

import scripts.run_inflection_historical_backtest as cli
from scripts.run_inflection_historical_backtest import fetch_range_from_args, main, verify_adjustment
from src.data.jquants_history import _write_day, default_fetch_range
from src.evaluation.inflection_historical import BarPanel, FinancialsStore, HistoricalData, MasterHistory
from tests.test_inflection_historical import CODES, DATES, _bar, _bars, _fins, _master
from tests.test_jquants_history import FakeClient, _http_error


def _write_cache(root: Path) -> Path:
    cache = root / ".data" / "jquants"
    for day, rows in _bars().items():
        _write_day(cache, "bars", day, rows)
    _write_day(cache, "master", DATES[0], _master())
    fins = _fins()
    for code in CODES:
        _write_day(cache, "fins", "2026-02-01", [row for row in fins if row["Code"] == code and row["DiscDate"] == "2026-02-01"])
    return cache


def test_cli_default_range_is_the_shared_default_range() -> None:
    namespace = argparse.Namespace(start=None, end=None)
    assert fetch_range_from_args(namespace, date(2026, 10, 1)) == default_fetch_range(date(2026, 10, 1))
    custom = argparse.Namespace(start="2025-01-06", end="2025-02-03")
    assert fetch_range_from_args(custom, date(2026, 10, 1)) == (date(2025, 1, 6), date(2025, 2, 3))
    with pytest.raises(ValueError, match="after end"):
        fetch_range_from_args(argparse.Namespace(start="2025-03-01", end="2025-02-01"), date(2026, 10, 1))


def test_fetch_uses_the_shared_default_range(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[tuple[date, date]] = []
    monkeypatch.setattr(cli, "default_fetch_range", lambda today: (date(2026, 1, 5), date(2026, 1, 6)))
    monkeypatch.setattr(cli, "_client", lambda: FakeClient())
    monkeypatch.setattr(cli, "fetch_range", lambda client, start, end, cache_dir: seen.append((start, end)) or {})

    assert main(["--repo-root", str(tmp_path), "--fetch"]) == 0
    assert seen == [(date(2026, 1, 5), date(2026, 1, 6))]


def test_fetch_stops_with_a_clear_message_on_a_boundary_4xx(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class Boundary(FakeClient):
        def daily_bars(self, date: str) -> list[dict[str, Any]]:
            if date >= "2026-01-07":
                raise _http_error(403, "outside your plan")
            return super().daily_bars(date)

    monkeypatch.setattr(cli, "_client", lambda: Boundary())
    code = main(["--repo-root", str(tmp_path), "--fetch", "--start", "2026-01-05", "--end", "2026-01-09"])

    assert code == 2
    error = capsys.readouterr().err
    assert "HTTP 403" in error and "outside your plan" in error and "resume" in error
    assert sorted(p.name for p in (tmp_path / ".data/jquants/bars").iterdir()) == [
        "2026-01-05.json.gz",
        "2026-01-06.json.gz",
    ]


def test_probe_reports_both_edges_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    client = FakeClient()
    monkeypatch.setattr(cli, "_client", lambda: client)

    assert main(["--repo-root", str(tmp_path), "--probe", "--start", "2026-01-05", "--end", "2026-01-09"]) == 0
    assert json.loads(capsys.readouterr().out)["first"]["date"] == "2026-01-05"
    assert len(client.calls) == 2 and not (tmp_path / ".data").exists()


def test_a_missing_api_key_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JQUANTS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="JQUANTS_API_KEY"):
        cli._client()


def test_evaluation_without_a_cache_points_to_fetch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--repo-root", str(tmp_path)]) == 1
    assert "--fetch" in capsys.readouterr().err


def test_full_run_writes_a_report_and_a_ticker_free_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_cache(tmp_path)

    # A short window keeps the evaluation (~30 trade simulations per signal) fast; production runs are hours.
    code = main(["--repo-root", str(tmp_path), "--signal-start", DATES[295]])

    assert code == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["signal_days"] == len([d for d in DATES if d >= DATES[295]]) == 5
    assert set(out["kill_criterion"]) == {"disclosure", "free_12w"}
    full = json.loads((tmp_path / "artifacts/inflection_historical_backtest.json").read_text(encoding="utf-8"))
    summary_text = (tmp_path / "artifacts/inflection_historical_backtest_summary.json").read_text(encoding="utf-8")
    assert full["lags"]["disclosure"]["groups"]["control"]["signal_count"] > 0
    assert '"trades"' not in summary_text
    assert not any(f"{c[:4]}.T" in summary_text for c in CODES)


def test_no_scan_days_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_cache(tmp_path)  # the default start (fundamentals warm-up) is beyond this short cache
    assert main(["--repo-root", str(tmp_path)]) == 1
    assert "No scan days" in capsys.readouterr().err


class ByCodeClient:
    def __init__(self, adj_close: dict[str, float]) -> None:
        self.adj_close = adj_close
        self.calls: list[str] = []

    def daily_bars_by_code(self, code: str) -> list[dict[str, Any]]:
        self.calls.append(code)
        return [{"Date": day, "AdjC": value} for day, value in self.adj_close.items()]


def _split_data() -> HistoricalData:
    days = ["2026-01-05", "2026-01-06", "2026-01-07"]
    bars = {
        days[0]: [_bar("11110", 100.0, 1000.0, 1.0), _bar("22220", 10.0, 1000.0)],
        days[1]: [_bar("11110", 50.0, 1000.0, 0.5), _bar("22220", 10.0, 1000.0)],
        days[2]: [_bar("11110", 50.0, 1000.0), _bar("22220", 10.0, 1000.0)],
    }
    return HistoricalData(BarPanel.from_rows(bars), MasterHistory({days[0]: _master()}), FinancialsStore([]))


def test_verify_adjustment_only_checks_split_tickers_with_a_single_by_code_fetch() -> None:
    data = _split_data()
    client = ByCodeClient({"2026-01-05": 50.0, "2026-01-06": 50.0, "2026-01-07": 50.0})

    results = verify_adjustment(client, data, 5)

    assert client.calls == ["11110"]  # the ticker without a split is skipped; one call per checked ticker
    assert results[0]["ticker"] == "1111.T" and results[0]["constant"] is True
    assert verify_adjustment(client, data, 0) == []


def test_verify_adjustment_flags_a_wrong_adjustment() -> None:
    wrong = ByCodeClient({"2026-01-05": 100.0, "2026-01-06": 50.0, "2026-01-07": 50.0})
    assert verify_adjustment(wrong, _split_data(), 5)[0]["constant"] is False


def test_verify_adjustment_exit_codes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cache = tmp_path / ".data" / "jquants"
    days = ["2026-01-05", "2026-01-06", "2026-01-07"]
    for day, rows in {
        days[0]: [_bar("11110", 100.0, 1000.0, 1.0)],
        days[1]: [_bar("11110", 50.0, 1000.0, 0.5)],
        days[2]: [_bar("11110", 50.0, 1000.0)],
    }.items():
        _write_day(cache, "bars", day, rows)
    monkeypatch.setattr(cli, "_client", lambda: ByCodeClient(dict.fromkeys(days, 50.0)))
    assert main(["--repo-root", str(tmp_path), "--verify-adjustment", "3"]) == 0
    capsys.readouterr()

    monkeypatch.setattr(cli, "_client", lambda: ByCodeClient({days[0]: 100.0, days[1]: 50.0, days[2]: 50.0}))
    assert main(["--repo-root", str(tmp_path), "--verify-adjustment", "3"]) == 1


def test_verify_adjustment_stops_on_4xx(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from src.data.jquants_history import HistoryFetchStopped

    cache = tmp_path / ".data" / "jquants"
    for day, rows in {"2026-01-05": [_bar("11110", 100.0, 1000.0, 1.0)], "2026-01-06": [_bar("11110", 50.0, 1000.0, 0.5)]}.items():
        _write_day(cache, "bars", day, rows)

    class Rejecting:
        def daily_bars_by_code(self, code: str) -> list[dict[str, Any]]:
            raise HistoryFetchStopped("HTTP 403")

    monkeypatch.setattr(cli, "_client", lambda: Rejecting())
    assert main(["--repo-root", str(tmp_path), "--verify-adjustment", "1"]) == 2


def test_requests_error_other_than_4xx_is_not_swallowed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class Down(FakeClient):
        def daily_bars(self, date: str) -> list[dict[str, Any]]:
            raise _http_error(503)

    monkeypatch.setattr(cli, "_client", lambda: Down())
    with pytest.raises(requests.HTTPError):
        main(["--repo-root", str(tmp_path), "--fetch", "--start", "2026-01-05", "--end", "2026-01-05"])


def test_the_client_waits_out_a_transient_429_instead_of_giving_up_after_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 429 ended a multi-hour fetch after the default ~14 s of retries; the CLI must be more patient."""
    monkeypatch.setenv("JQUANTS_API_KEY", "key")

    client = cli._client()

    waits = [client.retry_backoff * 2**attempt for attempt in range(client.max_retries)]
    assert waits == [15.0, 30.0, 60.0, 120.0, 240.0]
    assert sum(waits) > 7 * 60 and client.min_interval >= 12.0  # the per-request spacing is unchanged
