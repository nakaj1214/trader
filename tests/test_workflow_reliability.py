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


def _job_header(workflow: str, job: str) -> str:
    """The text of one job from its name up to its ``runs-on`` line (conditions and dependencies live there)."""
    start = workflow.index(f"\n  {job}:\n") + 1
    return workflow[start : workflow.index("runs-on:", start)]


def test_the_daily_scan_runs_only_on_main_so_a_branch_cannot_use_production_secrets() -> None:
    workflow = (WORKFLOWS / "inflection_shadow.yml").read_text()

    # The scan uses the production API key, snapshot key and Slack webhook and pushes to the ref it ran on.
    assert "if: github.ref == 'refs/heads/main'" in _job_header(workflow, "scan")
    notify = _job_header(workflow, "notify-failure")
    assert "needs: scan" in notify and "github.ref == 'refs/heads/main'" in notify
    # A skipped scan is neither a failure nor a cancellation, so a branch run raises no failure alert.
    assert "needs.scan.result == 'failure' || needs.scan.result == 'cancelled'" in notify


def test_every_job_that_holds_production_secrets_is_limited_to_main_or_to_scheduled_runs() -> None:
    allowed = {
        # job -> why it may run off main (its writes/notifications are scoped or secret-free)
        ("forward_validation.yml", "validate"): "secret steps are skipped for pull requests",
        ("test.yml", "lint"): "no secrets",
        ("test.yml", "test"): "no secrets",
    }
    for path in WORKFLOWS.glob("*.yml"):
        workflow = path.read_text()
        for job in re.findall(r"^  ([a-z][a-z0-9-]*):\n", workflow.split("\njobs:\n", 1)[1], flags=re.MULTILINE):
            header = _job_header(workflow, job)
            body_start = workflow.index(f"\n  {job}:\n")
            next_job = re.search(r"\n  [a-z][a-z0-9-]*:\n", workflow[body_start + 1 :])
            body = workflow[body_start : body_start + 1 + next_job.start()] if next_job else workflow[body_start:]
            if "secrets." not in body or (path.name, job) in allowed:
                continue
            assert "github.ref == 'refs/heads/main'" in header or "github.event_name == 'schedule'" in header, (
                f"{path.name}:{job} uses secrets but can run on any branch"
            )


def _steps_using_secrets(workflow: str) -> list[tuple[str, str, str]]:
    """(job, step name, step text) for every step whose own text or whose job-level ``env`` reads ``secrets.``."""
    found: list[tuple[str, str, str]] = []
    jobs = workflow.split("\njobs:\n", 1)[1]
    for job_match in re.finditer(r"(?m)^  ([a-z][a-z0-9-]*):\n", jobs):
        end = re.search(r"(?m)^  [a-z][a-z0-9-]*:\n", jobs[job_match.end() :])
        body = jobs[job_match.end() : job_match.end() + end.start()] if end else jobs[job_match.end() :]
        job_header_and_env = body.split("    steps:\n", 1)[0]
        for step in re.split(r"(?m)^      - ", body.split("    steps:\n", 1)[1] if "    steps:\n" in body else ""):
            if "secrets." in step or "secrets." in job_header_and_env:
                name = re.search(r"name: (.+)", step) or re.search(r"id: (.+)", step)
                found.append((job_match.group(1), name.group(1).strip() if name else step[:40], step))
    return found


def test_every_step_that_reads_a_production_secret_runs_only_on_main_or_on_a_schedule() -> None:
    """A step-level check: a job without a main condition may still run for a pull request or a branch, so each
    secret-reading step must carry its own (or its job's) main/schedule condition."""
    offenders: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = path.read_text()
        for job, name, step in _steps_using_secrets(workflow):
            job_text = workflow[workflow.index(f"\n  {job}:\n") :]
            job_text = job_text.split("    steps:\n", 1)[0]
            guarded = any(
                "github.ref == 'refs/heads/main'" in text or "github.event_name == 'schedule'" in text
                for text in (step, job_text)
            )
            if not guarded:
                offenders.append(f"{path.name}:{job}:{name}")
    assert not offenders, f"secret-reading steps that can run on any branch or pull request: {offenders}"


def test_the_forward_decryption_step_needs_main_and_a_non_pull_request_event() -> None:
    workflow = (WORKFLOWS / "forward_validation.yml").read_text()
    step = next(text for job, name, text in _steps_using_secrets(workflow) if name == "Validate accumulated encrypted snapshots")

    # Pull requests (including forks) never get the key, and neither does a manual run of another branch.
    assert "github.event_name != 'pull_request'" in step and "github.ref == 'refs/heads/main'" in step
    # The secret-free regression tests of the same job stay available to pull requests.
    assert "github.ref == 'refs/heads/main'" not in workflow[workflow.index("  validate:") : workflow.index("    steps:")]


def test_every_workflow_states_its_token_permissions_instead_of_inheriting_the_repository_default() -> None:
    for path in WORKFLOWS.glob("*.yml"):
        workflow = path.read_text()
        top_level = workflow.split("\njobs:\n", 1)[0]
        # An explicit top-level block: a missing one would silently follow the repository's default token scope
        # (which may be read-write), and a write scope must be granted per job, never for the whole workflow.
        assert re.search(r"(?m)^permissions:\n(?:  [a-z-]+: (?:read|none)\n)+", top_level), (
            f"{path.name} has no explicit read-only top-level permissions"
        )
