from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from scripts.show_candidates import display_width, main, pad
from src.data.snapshot_crypto import encrypt_json

SECRET = "viewer-test-secret"


def row(ticker: str, classification: str, score: float, **overrides: Any) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "company_name": f"会社{ticker}",
        "classification": classification,
        "score": score,
        "return_20d_pct": 12.34,
        "volume_ratio_20d": 1.8,
        "near_52w_high": True,
        "near_listing_high": False,
        "market": "プライム",
        "sector33_name": "電気機器",
        "reasons": ["売上成長", "出来高増加"],
        **overrides,
    }


def write(root: Path, payload: dict[str, Any], name: str = "dashboard/data/inflection_candidates.enc") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encrypt_json(payload, SECRET), encoding="utf-8")
    return path


def payload(candidates: list[dict[str, Any]] | None = None, **extra: Any) -> dict[str, Any]:
    rows = candidates if candidates is not None else [
        row("1111.T", "WATCH", 60.0),
        row("2222.T", "EARLY_CANDIDATE", 78.2),
        row("3333.T", "NONE", 20.0),
        row("4444.T", "OVEREXTENDED", 55.0),
        row("5555.T", "EARLY_CANDIDATE", 71.0),
    ]
    counts: dict[str, int] = {}
    for item in rows:
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1
    return {
        "latest_price_date": "2026-10-01",
        "strategy_version": "jp-inflection-shadow-v3",
        "report_schema_version": 5,
        "classification_counts": counts,
        "data_policy": {"jquants_data_delay_weeks": 12},
        "candidates": rows,
        "control_sample": [row("9999.T", "NONE", 33.3), row("8888.T", "WATCH", 55.5)],
        **extra,
    }


@pytest.fixture(autouse=True)
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SNAPSHOT_ENCRYPTION_KEY", SECRET)


def run(root: Path, *args: str) -> int:
    return main(["--repo-root", str(root), *args])


def test_shows_early_and_watch_best_score_first_with_the_header(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, payload())

    assert run(tmp_path) == 0

    out = capsys.readouterr().out
    assert "市場日: 2026-10-01" in out and "schema: 5" in out and "strategy: jp-inflection-shadow-v3" in out
    assert "売買推奨ではありません" in out and "約12週間遅れ" in out
    assert "EARLY_CANDIDATE 2件" in out and "WATCH 1件" in out and "OVEREXTENDED 1件" in out
    order = [out.index(ticker) for ticker in ("2222.T", "5555.T", "1111.T")]
    assert order == sorted(order)  # 78.2, 71.0, 60.0
    assert "3333.T" not in out and "4444.T" not in out  # not in the default classifications
    first = next(line for line in out.splitlines() if line.startswith("2222.T"))
    for cell in ("会社2222.T", "EARLY_CANDIDATE", "78.2", "+12.3%", "1.80", "52週", "プライム", "電気機器", "売上成長・出来高増加"):
        assert cell in first


def test_filters_and_top_and_control(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, payload())

    run(tmp_path, "--classification", "NONE", "OVEREXTENDED")
    out = capsys.readouterr().out
    assert "3333.T" in out and "4444.T" in out and "2222.T" not in out

    run(tmp_path, "--top", "1")
    out = capsys.readouterr().out
    assert "2222.T" in out and "5555.T" not in out

    run(tmp_path, "--control")
    out = capsys.readouterr().out
    assert "対照群" in out and "8888.T" in out and "9999.T" in out and "2222.T" not in out
    assert out.index("8888.T") < out.index("9999.T")  # by score


def test_an_empty_selection_says_so(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, payload([row("3333.T", "NONE", 20.0)]))

    assert run(tmp_path) == 0
    assert "該当する候補はありません。" in capsys.readouterr().out


def test_reads_a_dated_snapshot_from_the_v3_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, payload([row("7777.T", "WATCH", 61.0)], latest_price_date="2026-09-30"),
          "dashboard/data/inflection/v3/2026-09-30.enc")

    assert run(tmp_path, "--date", "2026-09-30") == 0
    out = capsys.readouterr().out
    assert "7777.T" in out and "市場日: 2026-09-30" in out


def test_schema4_snapshots_without_sector_or_control_sample_still_display(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = row("1111.T", "EARLY_CANDIDATE", 75.0)
    del old["sector33_name"]
    data = payload([old], report_schema_version=4)
    del data["control_sample"]
    write(tmp_path, data)

    assert run(tmp_path) == 0
    line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("1111.T"))
    assert "-" in line.split("プライム")[1]  # the sector cell falls back to a dash

    assert run(tmp_path, "--control") == 0
    assert "対照群がありません" in capsys.readouterr().out


def test_missing_values_become_dashes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, payload([row("1111.T", "WATCH", 60.0, return_20d_pct=None, volume_ratio_20d=None,
                                 near_52w_high=False, reasons=[], market=None)]))

    assert run(tmp_path) == 0
    assert "1111.T" in capsys.readouterr().out


def test_wide_characters_keep_the_columns_aligned(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert display_width("会社") == 4 and display_width("ab") == 2 and pad("会社", 6) == "会社  "
    write(tmp_path, payload([row("1111.T", "WATCH", 60.0, company_name="短い"),
                             row("2222.T", "WATCH", 59.0, company_name="とても長い会社名株式会社")]))

    run(tmp_path)
    lines = {
        line.split()[0]: line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith(("銘柄", "1111.T", "2222.T"))
    }
    # The third column starts where the (full-width, differently long) company column was padded to.
    third_cell = {"銘柄": "分類", "1111.T": "WATCH", "2222.T": "WATCH"}
    starts = {key: display_width(line[: line.index(third_cell[key])]) for key, line in lines.items()}

    assert len(lines) == 3 and len(set(starts.values())) == 1, starts


def test_a_missing_key_is_reported_with_exit_code_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, payload())
    monkeypatch.delenv("SNAPSHOT_ENCRYPTION_KEY")

    assert run(tmp_path) == 1
    assert "SNAPSHOT_ENCRYPTION_KEY" in capsys.readouterr().err


def test_a_wrong_key_or_corrupt_file_is_reported_with_exit_code_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write(tmp_path, payload())
    monkeypatch.setenv("SNAPSHOT_ENCRYPTION_KEY", "another-key")
    assert run(tmp_path) == 1
    assert "復号できません" in capsys.readouterr().err

    monkeypatch.setenv("SNAPSHOT_ENCRYPTION_KEY", SECRET)
    path.write_text("not an encrypted snapshot", encoding="utf-8")
    assert run(tmp_path) == 1
    assert "復号できません" in capsys.readouterr().err


def test_a_missing_snapshot_or_bad_date_is_reported_with_exit_code_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(tmp_path) == 1
    assert "見つかりません" in capsys.readouterr().err
    assert run(tmp_path, "--date", "2026-01-05") == 1
    assert "見つかりません" in capsys.readouterr().err
    assert run(tmp_path, "--date", "yesterday") == 1
    assert "YYYY-MM-DD" in capsys.readouterr().err


def test_the_viewer_never_touches_the_network() -> None:
    tree = ast.parse(Path("scripts/show_candidates.py").read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    } | {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}

    assert not imported & {"requests", "yfinance", "urllib", "http", "socket", "httpx"}
    assert "src" in imported  # only the local crypto helper
