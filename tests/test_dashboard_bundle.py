from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from cryptography.exceptions import InvalidTag

from scripts import build_dashboard
from src.dashboard.bundle import (
    BENCHMARK_TICKER,
    build_bundle,
    chart_series,
    chart_tickers,
    decrypt_bundle,
    encrypt_bundle,
    load_snapshots,
    signal_performance,
)
from src.data.snapshot_crypto import encrypt_json

SECRET = "snapshot-test-secret"
PASSWORD = "viewer-password-123"
ROOT = Path(__file__).resolve().parents[1]


def candidate(ticker: str, classification: str, score: float = 60.0) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "company_name": f"会社{ticker[:4]}",
        "market": "グロース",
        "classification": classification,
        "live_normalized_score": score,
        "score": score,
        "current_price": 1000.0,
        "return_20d_pct": 12.5,
        "volume_ratio_20d": 1.8,
        "near_52w_high": True,
        "sector33_name": "電気機器",
        "reasons": ["売上成長", "出来高増加"],
        "features": {"revenue_growth_yoy_pct": 25.0, "operating_profit_growth_yoy_pct": None},
        "score_details": {"revenue_growth": 5.0, "return_20d": 5.0, "note": "ignored"},
    }


def report(day: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "latest_price_date": day,
        "strategy_version": "jp-inflection-shadow-v3",
        "universe_count": 3800,
        "liquid_candidate_count": 900,
        "data_policy": {"jquants_plan": "free", "jquants_data_delay_weeks": 12},
        "scan_parameters": {"early_candidate_score": 70.0, "watch_score": 52.0},
        "candidates": candidates,
    }


def bars(start: str, closes: list[float], opens: list[float] | None = None) -> pd.DataFrame:
    index = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame(
        {"Open": opens or closes, "Close": closes, "Volume": [1000.0] * len(closes)}, index=index
    )


def write_snapshots(directory: Path, reports: list[dict[str, Any]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for item in reports:
        (directory / f"{item['latest_price_date']}.enc").write_text(encrypt_json(item, SECRET), encoding="utf-8")


DAYS = ["2026-10-01", "2026-10-02", "2026-10-05"]
REPORTS = [
    report(DAYS[0], [candidate("1111.T", "EARLY_CANDIDATE", 75.0), candidate("2222.T", "NONE", 30.0)]),
    report(DAYS[1], [candidate("1111.T", "WATCH", 60.0), candidate("2222.T", "NONE", 31.0)]),
    report(DAYS[2], [
        candidate("1111.T", "EARLY_CANDIDATE", 72.0),
        candidate("2222.T", "NONE", 32.0),
        candidate("3333.T", "OVEREXTENDED", 80.0),
    ]),
]


def test_signal_performance_enters_at_the_next_sessions_open_and_compares_the_same_dates() -> None:
    prices = bars("2026-10-01", [100.0, 104.0, 120.0, 110.0], opens=[99.0, 100.0, 118.0, 112.0])
    benchmark = bars("2026-10-01", [1000.0, 1000.0, 1010.0, 1020.0], opens=[1000.0, 1000.0, 1005.0, 1015.0])

    result = signal_performance(prices, "2026-10-01", benchmark)

    # Signal after the 10/1 close: entry is the 10/2 open (100), the latest close is 110 on 10/6.
    assert result["status"] == "ok"
    assert (result["entry_date"], result["entry_price"], result["last_date"]) == ("2026-10-02", 100.0, "2026-10-06")
    assert (result["return_pct"], result["max_return_pct"], result["min_return_pct"]) == (10.0, 20.0, 4.0)
    assert result["sessions"] == 3
    assert result["benchmark_return_pct"] == pytest.approx(2.0)  # 10/2 open 1000 -> 10/6 close 1020


def test_signal_performance_skips_a_missing_open_and_reports_waiting_or_missing_prices() -> None:
    prices = bars("2026-10-01", [100.0, 101.0, 102.0], opens=[100.0, float("nan"), 101.5])
    result = signal_performance(prices, "2026-10-01", None)
    assert result["entry_date"] == "2026-10-05" and result["entry_price"] == 101.5
    assert result["benchmark_return_pct"] is None

    assert signal_performance(prices, "2026-10-05", None) == {"status": "waiting"}  # nothing traded after it yet
    assert signal_performance(None, "2026-10-01", None) == {"status": "no_prices"}


def test_chart_series_keeps_the_latest_sessions_and_tolerates_a_timezone_and_missing_volume() -> None:
    frame = bars("2026-01-05", [float(n) for n in range(1, 151)])
    frame.index = frame.index.tz_localize("Asia/Tokyo")
    frame.iloc[-1, frame.columns.get_loc("Volume")] = float("nan")

    rows = chart_series(frame, sessions=120)

    assert rows is not None and len(rows) == 120
    assert rows[0][1] == 31.0 and rows[-1][1] == 150.0
    assert rows[-1][2] is None and rows[-2][2] == 1000


def test_bundle_covers_the_latest_day_history_and_past_signals(tmp_path: Path) -> None:
    write_snapshots(tmp_path, REPORTS)
    (tmp_path / "2026-10-06.enc").write_text(encrypt_json(report("2026-10-07", []), SECRET), encoding="utf-8")
    (tmp_path / "notes.enc").write_text("ignored", encoding="utf-8")

    reports, skipped = load_snapshots(tmp_path, SECRET)
    prices = {
        "1111.T": bars("2026-10-01", [100.0, 105.0, 110.0, 120.0]),
        "3333.T": bars("2026-10-01", [50.0, 55.0, 60.0, 65.0]),
        BENCHMARK_TICKER: bars("2026-10-01", [1000.0, 1000.0, 1000.0, 1000.0]),
    }
    bundle = build_bundle(reports, prices, generated_at="2026-10-05T17:00:00+09:00", skipped_snapshots=skipped)

    assert skipped == 1  # a file whose content names another day is not that day's snapshot
    assert [day["date"] for day in bundle["days"]] == DAYS
    assert bundle["latest_price_date"] == "2026-10-05"
    assert bundle["latest"]["counts"] == {"EARLY_CANDIDATE": 1, "NONE": 1, "OVEREXTENDED": 1}
    latest = {row["ticker"]: row for row in bundle["latest"]["candidates"]}
    assert latest["1111.T"]["streak"] == 3 and latest["2222.T"]["streak"] == 0
    assert latest["1111.T"]["features"]["operating_profit_growth_yoy_pct"] is None  # missing stays missing
    assert latest["1111.T"]["score_details"] == {"revenue_growth": 5.0, "return_20d": 5.0}

    # Only EARLY/WATCH days are signals; the first one is where the result is measured from.
    assert [signal["ticker"] for signal in bundle["signals"]] == ["1111.T"]
    signal = bundle["signals"][0]
    assert (signal["first_signal_date"], signal["signal_days"], signal["ever_early"]) == ("2026-10-01", 3, True)
    assert signal["performance"]["entry_date"] == "2026-10-02" and signal["performance"]["return_pct"] == 14.2857

    # Charts for signals and for the newest charted classes, not for NONE; the benchmark separately.
    assert sorted(bundle["prices"]) == ["1111.T", "3333.T"]
    assert chart_tickers(reports) == ["1111.T", "3333.T"]
    assert bundle["benchmark"]["series"][-1][1] == 1000.0
    assert bundle["diagnostics"] == {"snapshots": 3, "skipped_snapshots": 1, "missing_prices": 0}
    json.dumps(bundle, allow_nan=False)


def test_encryption_round_trip_rejects_a_short_or_wrong_password() -> None:
    bundle = {"format": "trader-dashboard-v1", "name": "会社"}
    text = encrypt_bundle(bundle, PASSWORD, iterations=1000)

    assert decrypt_bundle(text, PASSWORD) == bundle
    assert "会社" not in text and json.loads(text)["kdf"]["iterations"] == 1000
    with pytest.raises(InvalidTag):
        decrypt_bundle(text, PASSWORD + "x")
    with pytest.raises(ValueError, match="12"):
        encrypt_bundle(bundle, "short")


def test_main_writes_an_encrypted_bundle_without_printing_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_snapshots(tmp_path / "v3", REPORTS)
    monkeypatch.setenv("SNAPSHOT_ENCRYPTION_KEY", SECRET)
    monkeypatch.setenv("DASHBOARD_PASSWORD", PASSWORD)
    requested: list[list[str]] = []

    def fetch(tickers: list[str]) -> dict[str, pd.DataFrame]:
        requested.append(tickers)
        return {ticker: bars("2026-10-01", [100.0, 101.0, 102.0, 103.0]) for ticker in tickers}

    output = tmp_path / "out" / "dashboard.enc"
    assert build_dashboard.main(["--snapshot-dir", str(tmp_path / "v3"), "--output", str(output)], fetch=fetch) == 0

    log = capsys.readouterr().out
    assert requested == [["1111.T", "1306.T", "3333.T"]]
    assert "dashboard=written days=3 skipped=0 tickers=2 missing_prices=0" in log
    text = output.read_text(encoding="utf-8")
    for secret_text in ("1111.T", "会社", "グロース"):  # none can occur in base64 by chance
        assert secret_text not in log and secret_text not in text
    assert decrypt_bundle(text, PASSWORD)["latest_price_date"] == "2026-10-05"


def test_main_skips_without_a_password_and_reports_only_the_error_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_snapshots(tmp_path / "v3", REPORTS)
    output = tmp_path / "dashboard.enc"
    args = ["--snapshot-dir", str(tmp_path / "v3"), "--output", str(output)]
    monkeypatch.setenv("SNAPSHOT_ENCRYPTION_KEY", SECRET)

    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    assert build_dashboard.main(args) == 0
    assert "DASHBOARD_PASSWORD is not set" in capsys.readouterr().out and not output.exists()

    monkeypatch.setenv("DASHBOARD_PASSWORD", "short")
    assert build_dashboard.main(args) == 1
    assert "12+ characters" in capsys.readouterr().out and not output.exists()

    def failing(tickers: list[str]) -> dict[str, pd.DataFrame]:
        raise RuntimeError(f"provider rejected {tickers[0]}")

    monkeypatch.setenv("DASHBOARD_PASSWORD", PASSWORD)
    assert build_dashboard.main(args, fetch=failing) == 1
    log = capsys.readouterr().out
    assert "::error title=Dashboard build failed::RuntimeError" in log and "1111" not in log
    assert not output.exists()

    monkeypatch.setenv("SNAPSHOT_ENCRYPTION_KEY", "another-key")  # nothing decrypts: no empty dashboard
    assert build_dashboard.main(args) == 1
    assert "ValueError" in capsys.readouterr().out and not output.exists()


def test_the_browser_decrypts_what_python_encrypts(tmp_path: Path) -> None:
    """Run dashboard/js/crypto.js under Node's Web Crypto: the same API the browser uses."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    bundle = {"format": "trader-dashboard-v1", "name": "会社", "values": [1.5, None, True]}
    envelope = tmp_path / "bundle.enc"
    envelope.write_text(encrypt_bundle(bundle, "パスワードは十二文字以上です", iterations=1000), encoding="utf-8")
    module = (ROOT / "dashboard" / "js" / "crypto.js").as_uri()
    script = (
        f"import {{ WrongPasswordError, decryptBundle }} from {json.dumps(module)};"
        "import { readFileSync } from 'node:fs';"
        "const text = readFileSync(process.argv[1], 'utf8');"
        "console.log(JSON.stringify(await decryptBundle(text, process.argv[2])));"
        "await decryptBundle(text, 'wrong-password-123').then(\n"
        "  () => process.exit(3), (error) => { if (!(error instanceof WrongPasswordError)) process.exit(4); });"
    )
    result = subprocess.run(
        [node, "--input-type=module", "-e", script, str(envelope), "パスワードは十二文字以上です"],
        capture_output=True, text=True, timeout=60, check=False,
    )

    assert result.returncode == 0, result.stderr[-400:]
    assert json.loads(result.stdout) == bundle
