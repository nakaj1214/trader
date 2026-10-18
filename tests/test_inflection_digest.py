from __future__ import annotations

import json
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


# --- the digest state is settled before the snapshot exists, and its faults never stop the scan (ISSUE-06) --------


def _latest_write_fails_once(real: Any) -> Any:
    failed = {"done": False}

    def write(path: Path, text: str, **kwargs: Any) -> bool:
        if path.name == "latest.enc" and not failed["done"]:
            failed["done"] = True
            raise OSError("disk full")  # the latest file, written right after the snapshot
        return real(path, text, **kwargs)

    return write


def test_a_failed_latest_write_after_the_snapshot_still_leaves_the_digest_pending(tmp_path: Path) -> None:
    from tests.test_shadow_health import SECRET, _healthy_report

    out_dir, latest, state = tmp_path / "v3", tmp_path / "latest.enc", tmp_path / "digest_state.json"
    report = _healthy_report()
    with (
        patch.object(shadow, "atomic_write_text", _latest_write_fails_once(shadow.atomic_write_text)),
        pytest.raises(OSError, match="disk full"),
    ):
        shadow.persist_report(
            report, encryption_secret=SECRET, out_dir=out_dir, latest_path=latest, digest_state=state,
        )
    assert (out_dir / "2026-09-07.enc").exists() and '"2026-09-07": "pending"' in state.read_text(encoding="utf-8")

    snapshot, created = shadow.persist_report(
        report, encryption_secret=SECRET, out_dir=out_dir, latest_path=latest, digest_state=state,
    )
    with patch.object(shadow, "send_daily_digest", return_value="sent") as send:
        status = shadow._deliver_digest(report, snapshot_created=created, state_path=state)

    assert created is False and snapshot.exists()
    assert status == "sent" and send.call_count == 1  # not "skipped:legacy-no-state"
    assert '"2026-09-07": "succeeded"' in state.read_text(encoding="utf-8")


def test_an_existing_snapshot_without_state_stays_a_legacy_snapshot(tmp_path: Path) -> None:
    from tests.test_shadow_health import SECRET, _healthy_report

    out_dir, latest, state = tmp_path / "v3", tmp_path / "latest.enc", tmp_path / "digest_state.json"
    shadow.persist_report(_healthy_report(), encryption_secret=SECRET, out_dir=out_dir, latest_path=latest)
    assert not state.exists()  # written before the state file existed

    shadow.persist_report(
        _healthy_report(), encryption_secret=SECRET, out_dir=out_dir, latest_path=latest, digest_state=state,
    )

    assert not state.exists()  # no "pending" is invented for a snapshot that was already there
    with patch.object(shadow, "send_daily_digest", return_value="sent") as send:
        assert shadow._deliver_digest(_healthy_report(), snapshot_created=False, state_path=state) == (
            "skipped:legacy-no-state"
        )
    send.assert_not_called()


@pytest.mark.parametrize("content", ["{not json", '{"2026-09-30": "weird"}', "[]"], ids=["bad_json", "bad_value", "list"])
def test_a_corrupt_digest_state_is_reported_not_raised_and_never_rewritten(tmp_path: Path, content: str) -> None:
    state = tmp_path / "digest_state.json"
    state.write_text(content, encoding="utf-8")
    with patch.object(shadow, "send_daily_digest", return_value="sent") as send:
        status = shadow._deliver_digest(make_report(), snapshot_created=True, state_path=state)

    assert status == "failed:digest-state-invalid"
    send.assert_not_called()  # an untracked send could be repeated tomorrow
    assert state.read_text(encoding="utf-8") == content


def test_an_unwritable_pending_state_blocks_the_send_without_raising(tmp_path: Path) -> None:
    state = tmp_path / "digest_state.json"
    with (
        patch.object(shadow, "_write_digest_state", side_effect=OSError("read-only")),
        patch.object(shadow, "send_daily_digest", return_value="sent") as send,
    ):
        status = shadow._deliver_digest(make_report(), snapshot_created=True, state_path=state)

    assert status == "failed:digest-state-unwritable"
    send.assert_not_called()


def test_main_completes_and_reports_a_corrupt_digest_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = snapshot_dir(tmp_path, ["2026-09-29", "2026-09-30"])
    (directory.parent / "digest_state.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", WEBHOOK)
    persist = Mock(return_value=(directory / "2026-09-30.enc", True))
    with (
        patch.object(shadow, "snapshot_encryption_secret", return_value="secret"),
        patch.object(shadow, "scan_japan_inflection", return_value=make_report()),
        patch.object(shadow, "persist_report", persist),
        patch.object(shadow, "OUT_DIR", directory),
        patch("src.notify.slack.requests.post") as post,
    ):
        shadow.main()  # must not raise: the snapshot is already saved and has to be committed

    persist.assert_called_once()
    post.assert_called_once()  # only the state alert (the digest itself is withheld); see the alert tests below
    assert "日次ダイジェストを送れませんでした" in post.call_args.kwargs["json"]["text"]
    assert "digest=failed:digest-state-invalid" in capsys.readouterr().out


def test_main_turns_an_unexpected_digest_error_into_a_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = snapshot_dir(tmp_path, ["2026-09-29", "2026-09-30"])
    monkeypatch.setenv("SLACK_WEBHOOK_URL", WEBHOOK)
    with (
        patch.object(shadow, "snapshot_encryption_secret", return_value="secret"),
        patch.object(shadow, "scan_japan_inflection", return_value=make_report()),
        patch.object(shadow, "persist_report", Mock(return_value=(directory / "2026-09-30.enc", True))),
        patch.object(shadow, "_deliver_digest", side_effect=RuntimeError("boom")),
        patch.object(shadow, "OUT_DIR", directory),
    ):
        shadow.main()

    assert "digest=failed:RuntimeError" in capsys.readouterr().out


# --- a digest that cannot be tracked is surfaced, not just logged ------------------------------------------------


def _main_with_digest_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, content: str | None, webhook: str | None = WEBHOOK,
    alert_effect: Any = None,
) -> tuple[Mock, str, str]:
    directory = snapshot_dir(tmp_path, ["2026-09-29", "2026-09-30"])
    if content is not None:
        (directory.parent / "digest_state.json").write_text(content, encoding="utf-8")
    if webhook:
        monkeypatch.setenv("SLACK_WEBHOOK_URL", webhook)
    else:
        monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    post = Mock(side_effect=alert_effect)
    with (
        patch.object(shadow, "snapshot_encryption_secret", return_value="secret"),
        patch.object(shadow, "scan_japan_inflection", return_value=make_report()),
        patch.object(shadow, "persist_report", Mock(return_value=(directory / "2026-09-30.enc", True))),
        patch.object(shadow, "OUT_DIR", directory),
        patch("src.notify.slack.requests.post", post),
    ):
        shadow.main()
    return post, "", ""


def test_a_corrupt_digest_state_raises_a_slack_alert_and_a_github_annotation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    post, _, _ = _main_with_digest_state(monkeypatch, tmp_path, content="{not json")

    out = capsys.readouterr().out
    post.assert_called_once()  # the digest itself is not sent; only the alert is
    text = post.call_args.kwargs["json"]["text"]
    assert "digest_state.json" in text and "日次ダイジェスト" in text
    for hidden in (WEBHOOK, "SECRETTOKEN", "1111.T", "Company"):
        assert hidden not in text and hidden not in out
    assert "digest=failed:digest-state-invalid" in out and "digest_alert=sent" in out
    assert "::warning" in out  # visible on the run page without opening the log


def test_the_alert_is_skipped_without_a_webhook_but_the_annotation_remains(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    post, _, _ = _main_with_digest_state(monkeypatch, tmp_path, content="[]", webhook=None)

    out = capsys.readouterr().out
    post.assert_not_called()
    assert "digest_alert=skipped:no-webhook" in out and "::warning" in out


def test_a_failing_alert_never_fails_the_scan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _main_with_digest_state(monkeypatch, tmp_path, content="{not json", alert_effect=requests.ConnectionError("down"))

    out = capsys.readouterr().out
    assert "digest_alert=failed:ConnectionError" in out and "SECRETTOKEN" not in out


def test_a_healthy_digest_state_raises_no_alert_and_no_annotation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    post, _, _ = _main_with_digest_state(monkeypatch, tmp_path, content='{"2026-09-30": "pending"}\n')

    out = capsys.readouterr().out
    post.assert_called_once()  # the digest itself
    assert "digest=sent" in out and "digest_alert" not in out and "::warning" not in out


def test_a_slack_failure_is_annotated_but_does_not_trigger_a_second_slack_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    post, _, _ = _main_with_digest_state(
        monkeypatch, tmp_path, content=None, alert_effect=requests.ConnectionError("down"),
    )

    out = capsys.readouterr().out
    assert post.call_count == 1  # only the digest attempt: the same channel is not used to report its own failure
    assert "digest=failed:ConnectionError" in out and "::warning" in out and "digest_alert" not in out


def test_a_sent_digest_whose_state_was_not_saved_is_annotated_without_a_second_slack_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(shadow, "_deliver_digest", return_value="sent:state-save-failed"):
        post, _, _ = _main_with_digest_state(monkeypatch, tmp_path, content='{"2026-09-30": "pending"}\n')

    out = capsys.readouterr().out
    assert "digest=sent:state-save-failed" in out and "::warning" in out  # it may repeat tomorrow (ISSUE-21)
    post.assert_not_called()  # the digest was mocked away; nothing else is sent over the same channel


# --- a digest-state VALUE of any type is "invalid", never an unexpected exception (ISSUE-16) --------------------


UNHASHABLE_OR_ODD_VALUES = ['[]', '{}', '[1, 2]', '{"a": 1}', '[[]]', '1', 'null', 'true', '1.5']


@pytest.mark.parametrize("value", UNHASHABLE_OR_ODD_VALUES, ids=lambda v: v.replace(" ", ""))
def test_a_digest_state_value_of_any_type_never_stops_the_snapshot_from_being_saved(tmp_path: Path, value: str) -> None:
    from tests.test_shadow_health import SECRET, _healthy_report

    out_dir, latest, state = tmp_path / "v3", tmp_path / "latest.enc", tmp_path / "digest_state.json"
    state.write_text(f'{{"2026-09-07": {value}}}', encoding="utf-8")
    before = state.read_text(encoding="utf-8")

    snapshot, created = shadow.persist_report(
        _healthy_report(), encryption_secret=SECRET, out_dir=out_dir, latest_path=latest, digest_state=state,
    )

    assert created is True and snapshot.exists()
    assert state.read_text(encoding="utf-8") == before  # the damaged file is never rewritten


@pytest.mark.parametrize("value", UNHASHABLE_OR_ODD_VALUES, ids=lambda v: v.replace(" ", ""))
def test_a_digest_state_value_of_any_type_is_reported_as_invalid_without_sending(tmp_path: Path, value: str) -> None:
    state = tmp_path / "digest_state.json"
    state.write_text(f'{{"2026-09-30": {value}}}', encoding="utf-8")
    with patch.object(shadow, "send_daily_digest", return_value="sent") as send:
        status = shadow._deliver_digest(make_report(), snapshot_created=True, state_path=state)

    assert status == "failed:digest-state-invalid"
    send.assert_not_called()
    assert state.read_text(encoding="utf-8") == f'{{"2026-09-30": {value}}}'


def test_main_finishes_and_alerts_when_a_digest_state_value_is_a_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    post, _, _ = _main_with_digest_state(monkeypatch, tmp_path, content='{"2026-09-30": []}')

    out = capsys.readouterr().out
    assert "digest=failed:digest-state-invalid" in out and "digest_alert=sent" in out
    post.assert_called_once()  # only the state alert; the digest itself is withheld


def test_valid_digest_states_are_still_accepted(tmp_path: Path) -> None:
    state = tmp_path / "digest_state.json"
    state.write_text('{"2026-09-29": "succeeded", "2026-09-30": "pending"}', encoding="utf-8")

    assert shadow._digest_states(state) == {"2026-09-29": "succeeded", "2026-09-30": "pending"}


# --- a digest still pending from the last three market days is sent again from its saved snapshot (ISSUE-18) ----


def _write_snapshot(directory: Path, day: str, *, tickers: tuple[str, ...] = ("1111.T",), claimed_day: str | None = None) -> None:
    from src.data.snapshot_crypto import encrypt_json

    report = make_report([candidate(ticker, "EARLY_CANDIDATE", 78.2) for ticker in tickers],
                         latest_price_date=claimed_day or day)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{day}.enc").write_text(encrypt_json(report, "secret"), encoding="utf-8")


def _recover(tmp_path: Path, state: dict[str, str], *, today: str = "2026-10-02", webhook: str | None = WEBHOOK,
             sent: Mock | None = None, days: tuple[str, ...] = ("2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01")) -> tuple[str, Mock]:
    directory = tmp_path / "v3"
    for day in days:
        _write_snapshot(directory, day)
    state_path = directory.parent / "digest_state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    post = sent or Mock(return_value="sent")
    with patch.object(shadow, "send_daily_digest", post):
        summary = shadow._recover_pending_digests(
            today, state_path=state_path, snapshot_dir=directory, secret="secret", webhook=webhook,
        )
    return summary, post


def test_yesterdays_pending_digest_is_sent_again_and_marked_succeeded(tmp_path: Path) -> None:
    summary, post = _recover(tmp_path, {"2026-10-01": "pending", "2026-10-02": "succeeded"})

    assert summary == "sent:1,failed:0,skipped:0"
    sent_report = post.call_args.args[0]
    assert sent_report["latest_price_date"] == "2026-10-01"  # the saved snapshot's own day, not today's report
    assert json.loads((tmp_path / "digest_state.json").read_text())["2026-10-01"] == "succeeded"


def test_a_recovered_digest_is_not_sent_a_second_time(tmp_path: Path) -> None:
    state = {"2026-10-01": "pending", "2026-10-02": "succeeded"}
    _recover(tmp_path, state)
    summary, post = _recover(tmp_path, json.loads((tmp_path / "digest_state.json").read_text()))

    assert summary == "sent:0,failed:0,skipped:0"
    post.assert_not_called()


def test_only_the_last_three_market_days_are_recovered(tmp_path: Path) -> None:
    state = {"2026-09-28": "pending", "2026-09-29": "pending", "2026-09-30": "pending", "2026-10-01": "pending"}
    summary, post = _recover(tmp_path, state)

    assert summary == "sent:3,failed:0,skipped:0"
    assert sorted(call.args[0]["latest_price_date"] for call in post.call_args_list) == [
        "2026-09-29", "2026-09-30", "2026-10-01",
    ]
    assert json.loads((tmp_path / "digest_state.json").read_text())["2026-09-28"] == "pending"  # too old: left alone


def test_a_weekend_between_the_days_does_not_shorten_the_window(tmp_path: Path) -> None:
    # Monday 2026-10-05: the three market days before it are Fri 10/2, Thu 10/1 and Wed 9/30.
    state = {"2026-09-29": "pending", "2026-09-30": "pending", "2026-10-02": "pending"}
    summary, post = _recover(tmp_path, state, today="2026-10-05", days=("2026-09-29", "2026-09-30", "2026-10-02"))

    assert summary == "sent:2,failed:0,skipped:0"
    assert sorted(call.args[0]["latest_price_date"] for call in post.call_args_list) == ["2026-09-30", "2026-10-02"]


def test_a_day_without_a_usable_snapshot_stays_pending_without_an_error(tmp_path: Path) -> None:
    directory = tmp_path / "v3"
    directory.mkdir()
    _write_snapshot(directory, "2026-10-01", claimed_day="2026-09-15")  # a snapshot that names a different day
    (directory / "2026-09-30.enc").write_text("not an encrypted snapshot", encoding="utf-8")
    state_path = directory.parent / "digest_state.json"
    state_path.write_text('{"2026-09-29": "pending", "2026-09-30": "pending", "2026-10-01": "pending"}', encoding="utf-8")
    with patch.object(shadow, "send_daily_digest", Mock(return_value="sent")) as post:
        summary = shadow._recover_pending_digests(
            "2026-10-02", state_path=state_path, snapshot_dir=directory, secret="secret", webhook=WEBHOOK,
        )

    assert summary == "sent:0,failed:0,skipped:3"  # no file / undecryptable / wrong day
    post.assert_not_called()
    assert set(json.loads(state_path.read_text()).values()) == {"pending"}


def test_a_failed_recovery_send_leaves_the_day_pending_for_the_next_run(tmp_path: Path) -> None:
    summary, _ = _recover(tmp_path, {"2026-10-01": "pending"}, sent=Mock(return_value="failed:ConnectionError"))

    assert summary == "sent:0,failed:1,skipped:0"
    assert json.loads((tmp_path / "digest_state.json").read_text())["2026-10-01"] == "pending"


def test_no_recovery_is_attempted_without_a_webhook_or_with_a_damaged_state(tmp_path: Path) -> None:
    summary, post = _recover(tmp_path, {"2026-10-01": "pending"}, webhook=None)
    assert summary == "skipped:no-webhook"
    post.assert_not_called()

    directory = tmp_path / "other" / "v3"
    _write_snapshot(directory, "2026-10-01")
    damaged = directory.parent / "digest_state.json"
    damaged.write_text('{"2026-10-01": []}', encoding="utf-8")
    with patch.object(shadow, "send_daily_digest", Mock(return_value="sent")) as again:
        summary = shadow._recover_pending_digests(
            "2026-10-02", state_path=damaged, snapshot_dir=directory, secret="secret", webhook=WEBHOOK,
        )
    assert summary == "skipped:digest-state-invalid"
    again.assert_not_called()
    assert damaged.read_text() == '{"2026-10-01": []}'


def test_days_that_are_succeeded_or_unknown_are_never_recovered(tmp_path: Path) -> None:
    # 09-29: succeeded. 09-30 and 10-01 have no entry at all (snapshots from before the state file existed).
    summary, post = _recover(tmp_path, {"2026-09-29": "succeeded"})

    assert summary == "sent:0,failed:0,skipped:0"
    post.assert_not_called()


def test_main_reports_the_recovery_without_leaking_anything(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "v3"
    _write_snapshot(directory, "2026-09-29")
    (directory.parent / "digest_state.json").write_text('{"2026-09-29": "pending"}', encoding="utf-8")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", WEBHOOK)
    monkeypatch.setattr(shadow, "snapshot_encryption_secret", lambda: "secret")
    post = Mock()
    with (
        patch.object(shadow, "scan_japan_inflection", return_value=make_report()),
        patch.object(shadow, "persist_report", Mock(return_value=(directory / "2026-09-30.enc", True))),
        patch.object(shadow, "OUT_DIR", directory),
        patch("src.notify.slack.requests.post", post),
    ):
        shadow.main()

    out = capsys.readouterr().out
    assert "digest_recovery=sent:1,failed:0,skipped:0" in out
    for hidden in (WEBHOOK, "SECRETTOKEN", "1111.T", "Company"):
        assert hidden not in out
    assert post.call_count == 2  # today's digest and the recovered one
