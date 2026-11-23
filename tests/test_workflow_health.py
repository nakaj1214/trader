from __future__ import annotations

import json
import urllib.error
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request
from zoneinfo import ZoneInfo

import pytest

from scripts.check_workflow_health import (
    HTTP_TIMEOUT_SECONDS,
    _expected_runs,
    _github_runs,
    failure_alert,
    main,
    notify_once,
    watchdog_alerts,
)

JST = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 10, 8, 20, 10, tzinfo=JST)


def _success(start: str) -> list[dict]:
    return [{"id": 1, "head_branch": "main", "event": "schedule", "run_started_at": start,
             "conclusion": "success"}]


def _runs(workflow: str, window: tuple[datetime, datetime] | None = None) -> list[dict]:
    times = {"position_monitor.yml": "2026-10-08T15:55:00+09:00",
             "inflection_shadow.yml": "2026-10-08T16:50:00+09:00",
             "forward_validation.yml": "2026-10-04T09:40:00+09:00"}
    return _success(times[workflow])


def test_watchdog_detects_a_monitor_that_never_started_without_reading_sheets(tmp_path: Path) -> None:
    (tmp_path / "2026-10-08.enc").write_text("fake encrypted snapshot")
    with patch("scripts.check_workflow_health._github_runs", side_effect=lambda w, _: [] if w == "position_monitor.yml" else _runs(w)):
        alerts = watchdog_alerts(NOW, tmp_path, [])
    assert len(alerts) == 1
    assert "position_monitor.yml kind=not_started" in alerts[0]["text"]


def test_initial_state_without_snapshots_is_a_missing_scan_not_a_healthy_system(tmp_path: Path) -> None:
    with patch("scripts.check_workflow_health._github_runs", side_effect=lambda w, _: [] if w == "inflection_shadow.yml" else _runs(w)):
        alerts = watchdog_alerts(NOW, tmp_path, [])
    assert len(alerts) == 1 and "not_started_snapshot_missing" in alerts[0]["text"]


def test_successful_rerun_and_committed_snapshot_recover_watchdog_health(tmp_path: Path) -> None:
    (tmp_path / "2026-10-08.enc").write_text("fake encrypted snapshot")
    with patch("scripts.check_workflow_health._github_runs", side_effect=_runs):
        assert watchdog_alerts(NOW, tmp_path, []) == []


def test_manual_forward_without_weekly_processing_does_not_satisfy_scheduled_run(tmp_path: Path) -> None:
    (tmp_path / "2026-10-08.enc").write_text("fake encrypted snapshot")
    manual = [{**_runs("forward_validation.yml")[0], "event": "workflow_dispatch"}]
    with patch("scripts.check_workflow_health._github_runs", side_effect=lambda w, _: manual if w == "forward_validation.yml" else _runs(w)):
        alerts = watchdog_alerts(NOW, tmp_path, [])
    assert len(alerts) == 1
    assert "forward_validation.yml kind=not_started" in alerts[0]["text"]


def test_cause_specific_failure_already_delivered_does_not_generate_a_second_deadman_alert(tmp_path: Path) -> None:
    (tmp_path / "2026-10-08.enc").write_text("fake encrypted snapshot")
    failed = [{**_runs("position_monitor.yml")[0], "conclusion": "failure"}]
    with patch("scripts.check_workflow_health._github_runs", side_effect=lambda w, _: failed if w == "position_monitor.yml" else _runs(w)):
        assert watchdog_alerts(NOW, tmp_path, ["failure:position_monitor.yml:1"]) == []


@pytest.mark.parametrize(("day", "friday"), [
    ("2026-10-03", "2026-10-02"), ("2026-10-10", "2026-10-09"),
    ("2026-10-11", "2026-10-09"), ("2026-10-12", "2026-10-09"),
])
def test_weekends_and_exchange_holidays_check_the_previous_market_day(day: str, friday: str) -> None:
    expected = _expected_runs(datetime.fromisoformat(f"{day}T20:10:00+09:00"))
    assert expected["position_monitor.yml"] == datetime.fromisoformat(f"{friday}T15:50:00+09:00")
    assert expected["inflection_shadow.yml"] == datetime.fromisoformat(f"{friday}T16:40:00+09:00")
    assert "forward_validation.yml" in expected


def test_scheduler_grace_avoids_alerting_before_a_run_is_expected() -> None:
    expected = _expected_runs(NOW.replace(hour=16))
    assert expected["position_monitor.yml"] == NOW.replace(day=7, hour=15, minute=50)
    assert expected["inflection_shadow.yml"] == NOW.replace(day=7, hour=16, minute=40)
    expected = _expected_runs(NOW.replace(hour=17, minute=50))
    assert expected["position_monitor.yml"] == NOW.replace(hour=15, minute=50)
    assert expected["inflection_shadow.yml"] == NOW.replace(day=7, hour=16, minute=40)


def test_overnight_watchdog_does_not_resend_the_previous_sessions_alerts(tmp_path: Path) -> None:
    weekly = _success("2026-11-15T09:40:00+09:00")
    with patch("scripts.check_workflow_health._github_runs", side_effect=lambda w, _: weekly if w == "forward_validation.yml" else []):
        evening = watchdog_alerts(datetime(2026, 11, 18, 20, 10, tzinfo=JST), tmp_path, [])
        keys = [alert["key"] for alert in evening]
        morning = watchdog_alerts(datetime(2026, 11, 19, 4, 22, tzinfo=JST), tmp_path, keys)
    assert set(keys) == {
        "deadman:position_monitor.yml:2026-11-18T15:50:00+09:00",
        "deadman:inflection_shadow.yml:2026-11-18T16:40:00+09:00",
    }
    assert morning == evening and any("kind=not_started_snapshot_missing" in a["text"] for a in morning)
    state = tmp_path / "alerts.json"
    state.write_text(json.dumps(keys))
    assert notify_once(morning, state, "") == 0


@pytest.mark.parametrize(("now", "session"), [
    (datetime(2026, 11, 19, 17, 0, tzinfo=JST), "2026-11-18"),
    (datetime(2026, 11, 3, 20, 10, tzinfo=JST), "2026-11-02"),  # weekday exchange holiday
])
@pytest.mark.parametrize(("workflow", "first_cron", "closing_cron"), [
    ("position_monitor.yml", "09:20", "15:50"), ("inflection_shadow.yml", "16:40", "16:40"),
])
@pytest.mark.parametrize(("overnight", "conclusion"), [(True, "success"), (False, "success"), (False, "failure")])
def test_daily_run_attribution_ends_at_the_next_weekday_cron(
    tmp_path: Path, now: datetime, session: str, workflow: str, first_cron: str, closing_cron: str,
    overnight: bool, conclusion: str,
) -> None:
    (tmp_path / f"{session}.enc").touch()
    start = "04:00" if overnight else first_cron
    run = {**_success(f"{now.date()}T{start}:00+09:00")[0], "conclusion": conclusion}
    sent = [f"failure:{workflow}:1"] if conclusion == "failure" else []
    with patch("scripts.check_workflow_health._github_runs", side_effect=lambda w, _: [run] if w == workflow else []):
        alerts = watchdog_alerts(now, tmp_path, sent)
    keys = [alert["key"] for alert in alerts if alert["key"].startswith(f"deadman:{workflow}:")]
    holiday_skip = workflow == "position_monitor.yml" and now.date().isoformat() == "2026-11-03" and overnight
    assert keys == ([] if overnight and not holiday_skip else [f"deadman:{workflow}:{session}T{closing_cron}:00+09:00"])
    if holiday_skip:
        assert any("position_monitor.yml kind=no_successful_run" in alert["text"] for alert in alerts)


def test_delivered_alert_is_persisted_once_and_a_rerun_sends_nothing(tmp_path: Path) -> None:
    response = Mock(status=200)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    state = tmp_path / "alerts.json"
    alert = {"key": "deadman:test", "text": "kind=not_started"}
    with patch("scripts.check_workflow_health.urllib.request.urlopen", return_value=response) as post:
        assert notify_once([alert], state, "https://example.test/private-webhook") == 0
        assert notify_once([alert], state, "https://example.test/private-webhook") == 0
    assert post.call_count == 1
    assert post.call_args.kwargs["timeout"] == HTTP_TIMEOUT_SECONDS
    assert json.loads(state.read_text()) == ["deadman:test"]


@pytest.mark.parametrize("error", [TimeoutError("private-webhook 9999.T 2026-08-04"),
    urllib.error.HTTPError("https://example.test/private-webhook", 500, "private response", {}, None)])
def test_notification_timeout_or_500_is_visible_safe_and_not_marked_delivered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture, error: Exception
) -> None:
    monkeypatch.setenv("WORKFLOW_NAME", "position_monitor.yml")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/trader")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/private-webhook")
    state = tmp_path / "alerts.json"
    with patch("scripts.check_workflow_health.urllib.request.urlopen", side_effect=error) as post:
        assert main(["--notify-failure", "--state", str(state)]) == 1
    assert post.call_count == 1 and not state.exists()
    logs = capsys.readouterr().out
    assert "workflow health failed" in logs and type(error).__name__ in logs
    assert "private-webhook" not in logs and "9999.T" not in logs and "2026-08-04" not in logs


@pytest.mark.parametrize("details", [{}, {"retry_exhausted": "true"}])
def test_cancelled_job_is_reported_as_cancelled(monkeypatch: pytest.MonkeyPatch, details: dict) -> None:
    monkeypatch.setenv("WORKFLOW_NAME", "inflection_shadow.yml")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/trader")
    monkeypatch.setenv("FAILURE_STAGE", "cancelled")
    monkeypatch.setenv("RETRY_DETAILS_JSON", json.dumps(details))
    assert failure_alert()["text"].splitlines()[0] == "workflow=inflection_shadow.yml kind=cancelled"


@pytest.mark.parametrize(("stage", "kind"), [("configuration", "configuration"), ("unrecognized", "workflow_failure")])
def test_failure_alert_classifies_configuration_errors(monkeypatch: pytest.MonkeyPatch, stage: str, kind: str) -> None:
    monkeypatch.setenv("WORKFLOW_NAME", "inflection_shadow.yml")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/trader")
    monkeypatch.setenv("FAILURE_STAGE", stage)
    monkeypatch.delenv("RETRY_DETAILS_JSON", raising=False)
    assert failure_alert()["text"].splitlines()[0] == f"workflow=inflection_shadow.yml kind={kind}"


def test_rerun_attempts_share_one_failure_identity_and_keep_retry_details(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOW_NAME", "inflection_shadow.yml")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/trader")
    monkeypatch.setenv("RETRY_DETAILS_JSON", json.dumps({"retry_exhausted": "true", "attempts": "3",
        "expected_date": "2026-10-08", "latest_coverage": "60.0%", "failed_gate": "latest_coverage"}))
    first = failure_alert()
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    assert failure_alert()["key"] == first["key"]
    assert "price_retry_exhausted" in first["text"] and "attempts=3" in first["text"]
    assert "latest_coverage=60.0%" in first["text"]


def test_github_200_without_workflow_runs_is_not_treated_as_an_unstarted_monitor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "private-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/trader")
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = b'{"message":"invalid"}'
    with (patch("scripts.check_workflow_health.urllib.request.urlopen", return_value=response),
          pytest.raises(TypeError, match="workflow response")):
        list(_github_runs("position_monitor.yml"))


@pytest.mark.parametrize(("workflow", "events"), [
    ("forward_validation.yml", ["schedule"]), ("position_monitor.yml", ["schedule", "workflow_dispatch"]),
])
def test_scheduled_runs_are_fetched_apart_from_manual_runs(
    monkeypatch: pytest.MonkeyPatch, workflow: str, events: list[str],
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "private-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/trader")
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = b'{"total_count": 0, "workflow_runs": []}'
    with patch("scripts.check_workflow_health.urllib.request.urlopen", return_value=response) as fetch:
        list(_github_runs(workflow))
    urls = [call.args[0].full_url for call in fetch.call_args_list]
    assert [url.split("event=")[1].split("&")[0] for url in urls] == events
    assert all("per_page=50" in url for url in urls)


@pytest.mark.parametrize("newer_manual_runs", [49, 50, 51])
def test_paginated_manual_recovery_counts_after_a_failed_friday_schedule(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, newer_manual_runs: int,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "private-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/trader")
    friday = datetime(2026, 10, 9, 15, 50, tzinfo=JST)
    holiday = datetime(2026, 10, 12, 20, 10, tzinfo=JST)
    scheduled = {**_success(friday.isoformat())[0], "created_at": friday.isoformat(), "conclusion": "failure"}
    recovery = {**scheduled, "id": 2, "event": "workflow_dispatch", "conclusion": "success",
                "created_at": (friday - timedelta(days=1)).isoformat(),
                "run_started_at": (friday + timedelta(minutes=5)).isoformat()}
    newer = [{**recovery, "id": 3 + i, "created_at": (friday + timedelta(minutes=i + 10)).isoformat(),
              "run_started_at": holiday.isoformat()} for i in reversed(range(newer_manual_runs))]
    attempts: list[int] = []

    def fetch(request: Request, *, timeout: int) -> BytesIO:
        query = parse_qs(urlsplit(request.full_url).query)
        begin, end = map(datetime.fromisoformat, query["created"][0].split(".."))
        assert end == holiday.replace(hour=9, minute=20)
        manual = query["event"] == ["workflow_dispatch"]
        rows = [run for run in (newer + [recovery] if manual else [scheduled])
                if begin <= datetime.fromisoformat(run["created_at"]) <= end]
        page = int(query["page"][0])
        if manual:
            attempts.append(page)
        size = int(query["per_page"][0])
        return BytesIO(json.dumps({"total_count": len(rows), "workflow_runs": rows[(page - 1) * size:page * size]}).encode())

    with (patch("scripts.check_workflow_health._expected_runs", return_value={"position_monitor.yml": friday}),
          patch("scripts.check_workflow_health.urllib.request.urlopen", side_effect=fetch)):
        assert watchdog_alerts(holiday, tmp_path, []) == []
    assert attempts == ([1] if newer_manual_runs == 49 else [1, 2])


@pytest.mark.parametrize("failure", ["http", "missing_page", "search_limit"])
def test_unreadable_history_does_not_emit_an_unstarted_alert(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture, failure: str,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "private-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/trader")
    def fetch_page(request: Request, *, timeout: int) -> BytesIO:
        query = parse_qs(urlsplit(request.full_url).query)
        if query["event"] == ["workflow_dispatch"]:
            return BytesIO(b'{"total_count": 0, "workflow_runs": []}')
        page = int(query["page"][0])
        if failure == "http" and page == 2:
            raise urllib.error.HTTPError("https://example.test", 503, "unavailable", {}, None)
        total = 1001 if failure == "search_limit" else 51
        rows = [{**_runs("position_monitor.yml")[0], "id": page * 50 + i, "conclusion": "failure"} for i in range(50)]
        if failure == "missing_page" and page == 2:
            rows = []
        return BytesIO(json.dumps({"total_count": total, "workflow_runs": rows}).encode())

    with (patch("scripts.check_workflow_health.urllib.request.urlopen", side_effect=fetch_page) as fetch,
          patch("scripts.check_workflow_health.notify_once") as notify):
        assert main(["--state", str(tmp_path / "alerts.json")]) == 1
    notify.assert_not_called()
    assert fetch.call_count == (21 if failure == "search_limit" else 3)
    output = capsys.readouterr().out
    assert "stage=watchdog" in output and "not_started" not in output
    if failure == "http":
        assert "type=HTTPError http_status=503" in output


@pytest.mark.parametrize("scheduled_error", [False, True])
def test_success_on_first_page_settles_health_even_when_search_is_capped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, scheduled_error: bool,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "private-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/trader")
    expected = NOW.replace(hour=15, minute=50)

    def fetch_page(request: Request, *, timeout: int) -> BytesIO:
        query = parse_qs(urlsplit(request.full_url).query)
        event = query["event"][0]
        assert query["page"] == ["1"]
        if scheduled_error and event == "schedule":
            raise urllib.error.URLError("scheduled runs unavailable")
        batch = [{**_success(expected.isoformat())[0], "id": i, "event": event} for i in range(50)]
        return BytesIO(json.dumps({"total_count": 1500, "workflow_runs": batch}).encode())

    with (patch("scripts.check_workflow_health._expected_runs", return_value={"position_monitor.yml": expected}),
          patch("scripts.check_workflow_health.urllib.request.urlopen", side_effect=fetch_page) as fetch):
        assert watchdog_alerts(NOW, tmp_path, []) == []
    assert fetch.call_count == (2 if scheduled_error else 1)


def test_new_success_without_expected_snapshot_is_not_hidden_by_an_older_failure(tmp_path: Path) -> None:
    with patch("scripts.check_workflow_health._github_runs", side_effect=_runs):
        alerts = watchdog_alerts(NOW, tmp_path, ["failure:inflection_shadow.yml:1"])
    assert len(alerts) == 1 and "kind=snapshot_missing" in alerts[0]["text"]


# --- the failure notifier needs nothing but the standard library (ISSUE-08) --------------------------------------


def _bare_python() -> list[str]:
    """The current interpreter with site-packages disabled: what a runner python without our dependencies sees."""
    import sys

    return [sys.executable, "-B", "-S"]


def test_the_failure_notifier_starts_without_any_third_party_package() -> None:
    import subprocess

    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [*_bare_python(), str(root / "scripts" / "check_workflow_health.py"), "--help"],
        capture_output=True, text=True, timeout=60, check=False, cwd=root,
    )

    assert result.returncode == 0, result.stderr[-400:]
    assert "ModuleNotFoundError" not in result.stderr


def test_a_failure_notification_is_delivered_from_a_python_without_third_party_packages(tmp_path: Path) -> None:
    import http.server
    import os
    import subprocess
    import threading

    received: list[dict] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = Path(__file__).resolve().parents[1]
    state = tmp_path / "alerts.json"
    env = {
        "PATH": os.environ.get("PATH", ""), "WORKFLOW_NAME": "inflection_shadow.yml", "GITHUB_RUN_ID": "123456",
        "GITHUB_REPOSITORY": "owner/repo", "FAILURE_STAGE": "snapshot_save",
        "SLACK_WEBHOOK_URL": f"http://127.0.0.1:{server.server_address[1]}/hook",
    }
    try:
        result = subprocess.run(
            [*_bare_python(), str(root / "scripts" / "check_workflow_health.py"), "--notify-failure",
             "--state", str(state)],
            capture_output=True, text=True, timeout=60, check=False, cwd=root, env=env,
        )
    finally:
        server.shutdown()

    assert result.returncode == 0, result.stdout[-300:] + result.stderr[-300:]
    assert len(received) == 1
    assert "workflow=inflection_shadow.yml kind=snapshot_save" in received[0]["text"]
    assert "actions/runs/123456" in received[0]["text"]
    assert "127.0.0.1" not in received[0]["text"]  # the webhook address is never part of the message
    assert json.loads(state.read_text()) == ["failure:inflection_shadow.yml:123456"]
