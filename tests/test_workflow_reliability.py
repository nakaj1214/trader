"""Lock the production scheduling and notification boundaries without running Actions."""

from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def test_position_monitor_serializes_the_shared_state_only_on_main() -> None:
    workflow = (WORKFLOWS / "position_monitor.yml").read_text()
    assert "group: position-monitor-production" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    concurrency = workflow.split("concurrency:", 1)[1].split("runs-on:", 1)[0]
    assert "github.ref_name" not in concurrency and "secrets." not in concurrency


def test_failures_are_reported_by_separate_jobs_and_missing_runs_by_a_watchdog() -> None:
    for name in ("inflection_shadow.yml", "forward_validation.yml", "position_monitor.yml"):
        workflow = (WORKFLOWS / name).read_text()
        assert "notify-failure:" in workflow
        assert "always()" in workflow
        assert "check_workflow_health.py --notify-failure" in workflow
    assert (WORKFLOWS / "reliability_watchdog.yml").exists()
