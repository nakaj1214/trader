from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
import requests

import scripts.run_inflection_shadow as shadow
from src.data.atomic_write import atomic_write, atomic_write_text
from src.notify.inflection_digest import build_digest, daily_warnings, send_daily_digest
from src.notify.slack import escape, post_text

WEBHOOK = "https://hooks.slack.test/services/T000/B000/SECRETTOKEN"


def candidate(ticker: str, classification: str, score: float = 70.0, **overrides: Any) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "company_name": f"Company {ticker}",
        "market": "プライム",
        "sector33_name": "電気機器",
        "classification": classification,
        "score": score,
        "return_20d_pct": 12.34,
        "volume_ratio_20d": 1.8,
        "reasons": ["売上成長", "出来高増加"],
        **overrides,
    }


def make_report(candidates: list[dict[str, Any]] | None = None, **overrides: Any) -> dict[str, Any]:
    rows = candidates if candidates is not None else [candidate("1111.T", "EARLY_CANDIDATE", 78.2)]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["classification"]] = counts.get(row["classification"], 0) + 1
    return {
        "latest_price_date": "2026-09-30",
        "classification_counts": counts,
        "candidates": rows,
        "data_policy": {"jquants_data_delay_weeks": 12},
        "universe_count": 3,
        "price_data_count": 3,
        "technical_usable_count": 3,
        "market_coverage": {
            market: {"universe": 1, "price_data": 1, "technical_usable": 1, "latest_date_count": 1}
            for market in ("Prime", "Standard", "Growth")
        },
        **overrides,
    }


def snapshot_dir(tmp_path: Path, dates: list[str]) -> Path:
    directory = tmp_path / "v3"
    directory.mkdir(exist_ok=True)
    for day in dates:
        (directory / f"{day}.enc").write_text("x", encoding="utf-8")
    return directory


# --- message ----------------------------------------------------------------------------------------


def test_digest_has_the_disclaimer_counts_and_one_line_per_candidate() -> None:
    report = make_report(
        [
            candidate("1111.T", "EARLY_CANDIDATE", 78.2),
            candidate("2222.T", "WATCH", 60.0, return_20d_pct=-3.0),
            candidate("3333.T", "OVEREXTENDED", 50.0),
        ]
    )

    text = build_digest(report, warnings=[])

    assert text.startswith("[検証用] JP Inflection 日次候補 2026-09-30")
    assert "売買推奨ではありません。財務データは約12週間遅れです。" in text
    assert "EARLY_CANDIDATE 1件 / WATCH 1件 / OVEREXTENDED 1件" in text
    assert "• 1111.T Company 1111.T（プライム・電気機器） 78.2点 20日+12.3% 出来高比1.80 売上成長・出来高増加" in text
    assert "20日-3.0%" in text and "3333.T" not in text  # overextended names are counted, not listed


def test_digest_lists_at_most_10_early_and_5_watch_and_says_how_many_are_hidden() -> None:
    rows = [candidate(f"{n:04d}.T", "EARLY_CANDIDATE", 90 - n) for n in range(12)]
    rows += [candidate(f"{n + 100:04d}.T", "WATCH", 60 - n) for n in range(8)]

    text = build_digest(make_report(rows), warnings=[])

    assert "■ EARLY_CANDIDATE（上位10件）" in text and "（ほか2件）" in text
    assert "■ WATCH（上位5件）" in text and "（ほか3件）" in text
    assert text.count("• ") == 15 and "0010.T" not in text and "0105.T" not in text
    assert len(text) < 4000  # far below Slack's message limit


def test_digest_with_no_candidates_is_a_short_count_only_message() -> None:
    text = build_digest(make_report([]), warnings=[])

    assert "EARLY_CANDIDATE 0件 / WATCH 0件 / OVEREXTENDED 0件" in text and "本日の候補はありません。" in text
    assert "•" not in text


def test_missing_values_are_shown_as_dashes_not_errors() -> None:
    text = build_digest(
        make_report(
            [candidate("1111.T", "EARLY_CANDIDATE", return_20d_pct=None, volume_ratio_20d=None, sector33_name=None,
                       market=None, reasons=[])]
        ),
        warnings=[],
    )

    assert "（-） 70.0点 20日- 出来高比- -" in text


def test_text_is_escaped_for_slack_and_warnings_are_appended() -> None:
    text = build_digest(
        make_report([candidate("1111.T", "EARLY_CANDIDATE", company_name="A&B <Holdings>")]),
        warnings=["前の営業日（2026-09-29）の snapshot がありません。"],
    )

    assert "A&amp;B &lt;Holdings&gt;" in text and "A&B <Holdings>" not in text
    assert text.endswith("⚠ 前の営業日（2026-09-29）の snapshot がありません。")
    assert escape("a & b < c > d") == "a &amp; b &lt; c &gt; d"


def test_the_headline_changes_when_the_data_delay_is_unknown() -> None:
    text = build_digest(make_report(data_policy={"jquants_data_delay_weeks": 0}), warnings=[])

    assert "財務データの公開時点を確認してください。" in text and "週間遅れ" not in text


# --- data-quality warnings ----------------------------------------------------------------------------


def test_warnings_flag_a_skipped_previous_session_and_the_running_total(tmp_path: Path) -> None:
    directory = snapshot_dir(tmp_path, ["2026-09-24", "2026-09-25", "2026-09-29", "2026-09-30"])

    from datetime import date

    assert daily_warnings(directory, date(2026, 9, 29)) == [
        "前の営業日（2026-09-28）の snapshot がありません。scan が失敗した可能性があります。",
        "これまでに snapshot が欠けた営業日: 1日",
    ]
    assert daily_warnings(directory, date(2026, 9, 30)) == ["これまでに snapshot が欠けた営業日: 1日"]


def test_no_warnings_when_nothing_is_missing(tmp_path: Path) -> None:
    from datetime import date

    directory = snapshot_dir(tmp_path, ["2026-09-24", "2026-09-25"])

    assert daily_warnings(directory, date(2026, 9, 25)) == []


# --- sending -----------------------------------------------------------------------------------------


def test_a_digest_is_posted_once_with_the_warnings_included(tmp_path: Path) -> None:
    directory = snapshot_dir(tmp_path, ["2026-09-24", "2026-09-25", "2026-09-29", "2026-09-30"])
    post = Mock()

    status = send_daily_digest(make_report(), snapshot_dir=directory, webhook=WEBHOOK, post=post)

    assert status == "sent"
    post.assert_called_once()
    url, text = post.call_args.args
    assert url == WEBHOOK and "1111.T" in text and "欠けた営業日: 1日" in text


def test_without_a_webhook_nothing_is_sent(tmp_path: Path) -> None:
    post = Mock()

    assert send_daily_digest(make_report(), snapshot_dir=tmp_path, webhook=None, post=post) == "skipped:no-webhook"
    assert send_daily_digest(make_report(), snapshot_dir=tmp_path, webhook="", post=post) == "skipped:no-webhook"
    post.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError(f"cannot reach {WEBHOOK}"),
        requests.Timeout("timed out"),
        requests.HTTPError(f"500 Server Error for url: {WEBHOOK}"),
        RuntimeError("anything at all"),
    ],
)
def test_a_failed_send_returns_only_the_error_type(tmp_path: Path, error: Exception) -> None:
    status = send_daily_digest(make_report(), snapshot_dir=tmp_path, webhook=WEBHOOK, post=Mock(side_effect=error))

    assert status == f"failed:{type(error).__name__}"
    assert WEBHOOK not in status and "SECRETTOKEN" not in status


def test_a_malformed_report_never_raises(tmp_path: Path) -> None:
    assert send_daily_digest({}, snapshot_dir=tmp_path, webhook=WEBHOOK, post=Mock()).startswith("failed:")


def test_post_text_posts_json_with_a_timeout_and_raises_on_http_errors() -> None:
    response = Mock()
    with patch("src.notify.slack.requests.post", return_value=response) as post:
        post_text(WEBHOOK, "hello")
    post.assert_called_once_with(WEBHOOK, json={"text": "hello"}, timeout=10)
    response.raise_for_status.assert_called_once()

    response.raise_for_status.side_effect = requests.HTTPError("500")
    with patch("src.notify.slack.requests.post", return_value=response), pytest.raises(requests.HTTPError):
        post_text(WEBHOOK, "hello")


# --- wired into the scan -----------------------------------------------------------------------------


def run_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    snapshot_created: bool,
    webhook: str | None = WEBHOOK,
    post_effect: Any = None,
) -> tuple[Mock, Mock]:
    directory = snapshot_dir(tmp_path, ["2026-09-29", "2026-09-30"])
    persist = Mock(return_value=(directory / "2026-09-30.enc", snapshot_created))
    post = Mock(side_effect=post_effect)
    if webhook:
        monkeypatch.setenv("SLACK_WEBHOOK_URL", webhook)
    else:
        monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    with (
        patch.object(shadow, "snapshot_encryption_secret", return_value="secret"),
        patch.object(shadow, "scan_japan_inflection", return_value=make_report()),
        patch.object(shadow, "persist_report", persist),
        patch.object(shadow, "OUT_DIR", directory),
        patch("src.notify.slack.requests.post", post),
    ):
        shadow.main()
    return persist, post


def test_main_sends_one_digest_when_it_created_the_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    persist, post = run_main(monkeypatch, tmp_path, snapshot_created=True)

    persist.assert_called_once()
    post.assert_called_once()
    assert post.call_args.args[0] == WEBHOOK and "1111.T" in post.call_args.kwargs["json"]["text"]
    assert "digest=sent" in capsys.readouterr().out


def test_main_does_not_resend_when_the_snapshot_already_existed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, post = run_main(monkeypatch, tmp_path, snapshot_created=False)

    post.assert_not_called()
    assert "digest=skipped:legacy-no-state" in capsys.readouterr().out


def test_main_does_nothing_without_a_webhook(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, post = run_main(monkeypatch, tmp_path, snapshot_created=True, webhook=None)

    post.assert_not_called()
    assert "digest=skipped:no-webhook" in capsys.readouterr().out


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError(f"cannot reach {WEBHOOK} for Company 1111.T"),
        requests.Timeout("timed out"),
        requests.HTTPError(f"500 Server Error for url: {WEBHOOK}"),
        RuntimeError("Company 1111.T exploded"),
    ],
)
def test_a_failed_digest_never_fails_the_scan_and_nothing_sensitive_is_printed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str], error: Exception
) -> None:
    persist, _ = run_main(monkeypatch, tmp_path, snapshot_created=True, post_effect=error)  # must not raise

    persist.assert_called_once()  # the snapshot was written before the digest was attempted
    captured = capsys.readouterr()
    assert f"digest=failed:{type(error).__name__}" in captured.out
    for secret in (WEBHOOK, "SECRETTOKEN", "1111.T", "Company"):
        assert secret not in captured.out and secret not in captured.err


def test_pending_digest_is_retried_and_success_is_not_resent(tmp_path: Path) -> None:
    state = tmp_path / "digest_state.json"
    state.write_text('{"2026-09-30": "pending"}\n', encoding="utf-8")
    report = make_report()
    with patch.object(shadow, "send_daily_digest", return_value="sent") as send:
        assert shadow._deliver_digest(report, snapshot_created=False, state_path=state) == "sent"
        assert shadow._deliver_digest(report, snapshot_created=False, state_path=state) == "skipped:already-succeeded"
    send.assert_called_once()
    assert '"2026-09-30": "succeeded"' in state.read_text(encoding="utf-8")


def test_manual_resend_sends_a_succeeded_digest(tmp_path: Path) -> None:
    state = tmp_path / "digest_state.json"
    state.write_text('{"2026-09-30": "succeeded"}\n', encoding="utf-8")
    with patch.object(shadow, "send_daily_digest", return_value="sent") as send:
        assert shadow._deliver_digest(make_report(), snapshot_created=False, state_path=state, resend=True) == "sent"
    send.assert_called_once()


def test_success_followed_by_state_failure_is_classified_for_possible_duplicate(tmp_path: Path) -> None:
    state = tmp_path / "digest_state.json"
    state.write_text('{"2026-09-30": "pending"}\n', encoding="utf-8")
    with (
        patch.object(shadow, "send_daily_digest", return_value="sent"),
        patch.object(shadow, "_write_digest_state", side_effect=[None, OSError("stopped")]),
    ):
        status = shadow._deliver_digest(make_report(), snapshot_created=False, state_path=state)
    assert status == "sent:state-save-failed"
    assert '"pending"' in state.read_text(encoding="utf-8")


def test_atomic_write_preserves_the_old_file_when_publication_fails(tmp_path: Path) -> None:
    target = tmp_path / "result.json"
    target.write_text("old", encoding="utf-8")
    with patch("src.data.atomic_write.os.replace", side_effect=OSError("stopped")), pytest.raises(OSError):
        atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_immutable_write_and_new_parent(tmp_path: Path) -> None:
    target = tmp_path / "new" / "snapshot.enc"
    assert atomic_write_text(target, "first", overwrite=False) is True
    assert atomic_write_text(target, "second", overwrite=False) is False
    assert target.read_text(encoding="utf-8") == "first"


def test_atomic_write_cleans_up_after_writer_failure(tmp_path: Path) -> None:
    target = tmp_path / "result.json"
    target.write_text("old", encoding="utf-8")

    def fail(handle: Any) -> None:
        handle.write("partial")
        raise OSError("stopped")

    with pytest.raises(OSError):
        atomic_write(target, fail)
    assert target.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob("*.tmp"))
