"""Lock the production scheduling and notification boundaries without running Actions."""

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def test_actions_are_sha_pinned_and_dependencies_use_the_lockfile() -> None:
    for path in WORKFLOWS.glob("*.yml"):
        workflow = path.read_text()
        assert "pull_request_target" not in workflow
        assert "pip install -e" not in workflow
        for line in workflow.splitlines():
            if "uses:" in line:
                assert re.search(r"uses: ([^@]+)@[0-9a-f]{40} # \1 v\d+", line), f"unpinned action: {path}: {line}"
        if "actions/setup-python@" in workflow:
            assert "uv sync --frozen" in workflow


def test_forward_pr_paths_and_secret_boundary_are_explicit() -> None:
    workflow = (WORKFLOWS / "forward_validation.yml").read_text()
    pull_request = workflow.split("pull_request:", 1)[1].split("schedule:", 1)[0]
    for path in ('"src/**"', '"scripts/**"', '"tests/**"', '"pyproject.toml"', '"uv.lock"'):
        assert path in pull_request
    validation = workflow.split("name: Validate accumulated encrypted snapshots", 1)[1].split("- name:", 1)[0]
    assert "if: github.event_name != 'pull_request'" in validation
    assert "SNAPSHOT_ENCRYPTION_KEY" in validation


def test_write_permission_is_limited_to_persistence_jobs() -> None:
    writable: list[tuple[str, str]] = []
    pattern = r"(?m)^  ([\w-]+):\n(?:(?!^  [\w-]+:).)*?^    permissions:\n(?:(?!^    \S).)*?contents: write"
    for path in WORKFLOWS.glob("*.yml"):
        writable.extend((path.name, match.group(1)) for match in re.finditer(pattern, path.read_text(), re.DOTALL))
    assert sorted(writable) == [("forward_validation.yml", "persist-price-hashes"), ("inflection_shadow.yml", "scan")]


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
