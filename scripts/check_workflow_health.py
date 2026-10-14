"""Failure notifications and a separately scheduled deadman check. Never reads holding details."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # Failure jobs run without installing the package.
from src.data.quiet_output import suppress_provider_output

STATE = ROOT / ".harness" / "state" / "workflow-alerts.json"
WORKFLOWS = ("inflection_shadow.yml", "position_monitor.yml", "forward_validation.yml", "reliability_watchdog.yml")
STAGES = {"authentication", "checkout", "setup", "install", "data_acquisition", "data_validation",
          "snapshot_save", "git_push", "forward", "monitor", "watchdog", "notification", "workflow_failure"}
HTTP_TIMEOUT_SECONDS = 10


def notify_once(alerts: list[dict[str, str]], state_path: Path, webhook: str) -> int:
    """Mark a batch delivered only after HTTP success; no blind POST retry after an ambiguous timeout."""
    sent = json.loads(state_path.read_text()) if state_path.exists() else []
    if not isinstance(sent, list) or any(not isinstance(key, str) for key in sent):
        raise ValueError("notification state is invalid")
    pending = [alert for alert in alerts if alert["key"] not in sent]
    if not pending:
        print(f"workflow health: new_alerts=0 suppressed={len(alerts)}")
        return 0
    if not webhook:
        raise RuntimeError("notification destination is not configured")
    text = "[Workflow reliability] " + "\n".join(alert["text"] for alert in pending)
    request = urllib.request.Request(
        webhook, data=json.dumps({"text": text}).encode(), headers={"Content-Type": "application/json"}, method="POST",
    )
    with suppress_provider_output(), urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError("notification HTTP status was unsuccessful")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(json.dumps((sent + [alert["key"] for alert in pending])[-200:]) + "\n")
    temporary.replace(state_path)
    print(f"workflow health: delivered={len(pending)} suppressed={len(alerts) - len(pending)}")
    return 0


def _repository() -> str:
    repository = os.getenv("GITHUB_REPOSITORY", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("GitHub repository context is invalid")
    return repository


def failure_alert() -> dict[str, str]:
    workflow = os.getenv("WORKFLOW_NAME", "")
    if workflow not in WORKFLOWS:
        raise ValueError("workflow name is invalid")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    if not run_id.isdigit():
        raise ValueError("workflow run context is invalid")
    stage = os.getenv("FAILURE_STAGE", "workflow_failure")
    if stage not in STAGES:
        stage = "workflow_failure"
    details = json.loads(os.getenv("RETRY_DETAILS_JSON") or "{}")
    lines = [f"workflow={workflow} kind={stage}", f"run=https://github.com/{_repository()}/actions/runs/{run_id}"]
    if isinstance(details, dict) and details.get("retry_exhausted") == "true":
        lines[0] = f"workflow={workflow} kind=price_retry_exhausted"
        for key in ("expected_date", "universe", "missing", "price_data", "price_coverage", "latest_coverage",
                    "latest_dates", "dropped_future_bars", "failed_gate", "attempts"):
            value = str(details.get(key, ""))
            pattern = r"[0-9.%,:\-]+" if key != "failed_gate" else r"(?:price_coverage|latest_coverage)(?:,(?:price_coverage|latest_coverage))*"
            if re.fullmatch(pattern, value):
                lines.append(f"{key}={value}")
    return {"key": f"failure:{workflow}:{run_id}", "text": "\n".join(lines)}


def _github_runs(workflow: str) -> list[dict[str, Any]]:
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GitHub read authentication is not configured")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{_repository()}/actions/workflows/{workflow}/runs?branch=main&per_page=100",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    with suppress_provider_output(), urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read(1_048_577))
    if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
        raise TypeError("GitHub workflow response is invalid")
    runs = payload["workflow_runs"]
    if any(not isinstance(run, dict) for run in runs):
        raise TypeError("GitHub workflow run is invalid")
    return list(runs)


def _expected_runs(now: datetime) -> dict[str, datetime]:
    import exchange_calendars as xcals

    from src.data.market_calendar import TSE_CALENDAR

    if now.tzinfo is None:
        raise ValueError("watchdog time must include a timezone")
    japan = now.astimezone(JST)
    expected: dict[str, datetime] = {}
    # Two hours of scheduler grace; the deadman check never labels an in-flight normal run missing.
    if bool(xcals.get_calendar(TSE_CALENDAR).is_session(japan.date().isoformat())):
        for workflow, hour, minute in (("position_monitor.yml", 15, 50), ("inflection_shadow.yml", 16, 40)):
            scheduled = japan.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if japan >= scheduled + timedelta(hours=2):
                expected[workflow] = scheduled
    sunday = (japan - timedelta(days=(japan.weekday() + 1) % 7)).replace(hour=9, minute=30, second=0, microsecond=0)
    if japan >= sunday + timedelta(hours=2):
        expected["forward_validation.yml"] = sunday
    return expected


def watchdog_alerts(now: datetime, snapshot_dir: Path, sent: list[str]) -> list[dict[str, str]]:
    from src.data.session_gaps import expected_snapshot_missing

    alerts: list[dict[str, str]] = []
    for workflow, expected in _expected_runs(now).items():
        runs = _github_runs(workflow)
        relevant = []
        events = ("schedule",) if workflow == "forward_validation.yml" else ("schedule", "workflow_dispatch")
        for run in runs:
            if run.get("head_branch") != "main" or run.get("event") not in events:
                continue
            started = datetime.fromisoformat(str(run.get("run_started_at") or run.get("created_at")))
            if started.tzinfo is None:
                raise ValueError("GitHub workflow timestamp lacks timezone")
            if expected <= started <= now:
                relevant.append(run)
        success = any(run.get("conclusion") == "success" for run in relevant)
        snapshot_missing = (expected_snapshot_missing(snapshot_dir, now) is not None
                            if workflow == "inflection_shadow.yml" else False)
        if success and not snapshot_missing:
            continue
        known_failure = any(f"failure:{workflow}:{run.get('id')}" in sent for run in relevant)
        if known_failure and not success:
            continue  # Existing cause-specific alert already covers this failed expected execution.
        kind = "snapshot_missing" if snapshot_missing else "no_successful_run"
        if not relevant and not success:
            kind = "not_started" if not snapshot_missing else "not_started_snapshot_missing"
        alerts.append({"key": f"deadman:{workflow}:{expected.isoformat()}",
                       "text": f"workflow={workflow} kind={kind} expected={expected.isoformat()} runs={len(relevant)}"})
    return alerts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notify-failure", action="store_true")
    parser.add_argument("--state", type=Path, default=STATE)
    parser.add_argument("--snapshot-dir", type=Path, default=ROOT / "dashboard/data/inflection/v3")
    args = parser.parse_args(argv)
    try:
        if args.notify_failure:
            alerts = [failure_alert()]
        else:
            sent = json.loads(args.state.read_text()) if args.state.exists() else []
            if not isinstance(sent, list) or any(not isinstance(key, str) for key in sent):
                raise ValueError("notification state is invalid")
            alerts = watchdog_alerts(datetime.now(UTC), args.snapshot_dir, sent)
        return notify_once(alerts, args.state, os.getenv("SLACK_WEBHOOK_URL", ""))
    except Exception as exc:  # noqa: BLE001 - public diagnostics must never include provider exception bodies
        status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
        print(f"workflow health failed: stage={'notification' if args.notify_failure else 'watchdog'} "
              f"type={type(exc).__name__} http_status={status}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
