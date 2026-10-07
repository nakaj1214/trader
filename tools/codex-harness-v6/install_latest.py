#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

PACKAGE_ROOT = Path(__file__).resolve().parent
INSTALLER_RE = re.compile(r"^install_v(\d+)_(\d+)(?:_(\d+))?(?:_updated)?\.py$")
BASE_VERSION = (6, 0, 0)
REVIEWED_CHAIN_END = (6, 12, 0)

# This hash is produced by the bundled historical updater chain on a pristine
# project. v6.11's reviewed v6.10 baseline differs only in selftest.py. We only
# permit this compatibility path when every other reviewed v6.10 core file
# matches exactly, so arbitrary local drift is never accepted silently.
KNOWN_BUNDLED_V610_SELFTEST_HASHES = {
    "066b7fc025c8f4656ed591a2f44c7e70fce9dbafface75aeb0d19cef195ef6c9",
}

REQUIRED_INSTALLERS = (
    "install.py",
    "install_v6_1.py",
    "install_v6_2.py",
    "install_v6_4.py",
    "install_v6_5.py",
    "install_v6_6.py",
    "install_v6_7.py",
    "install_v6_8.py",
    "install_v6_8_1.py",
    "install_v6_9.py",
    "install_v6_10_updated.py",
    "install_v6_11.py",
    "install_v6_12.py",
)


class InstallLatestError(RuntimeError):
    pass


def format_version(version: tuple[int, int, int]) -> str:
    return ".".join(str(x) for x in version)


def installer_version_from_name(name: str) -> tuple[int, int, int] | None:
    if name == "install.py":
        return BASE_VERSION
    m = INSTALLER_RE.match(name)
    if not m:
        return None
    major, minor, patch = m.groups()
    return int(major), int(minor), int(patch or 0)


def discover_installers() -> dict[tuple[int, int, int], str]:
    """Discover bundled versioned installers instead of hard-coding the latest release.

    If multiple files map to the same semantic version, prefer *_updated.py, then
    the lexicographically last name. This preserves the bundled v6.10 behavior.
    """
    candidates: dict[tuple[int, int, int], list[str]] = {}
    for path in PACKAGE_ROOT.glob("install_v*.py"):
        version = installer_version_from_name(path.name)
        if version is None:
            continue
        candidates.setdefault(version, []).append(path.name)

    selected: dict[tuple[int, int, int], str] = {}
    for version, names in candidates.items():
        names.sort(key=lambda n: ("_updated.py" in n, n))
        selected[version] = names[-1]
    return selected


def latest_bundled_version() -> tuple[int, int, int]:
    installers = discover_installers()
    if not installers:
        raise InstallLatestError("no versioned install_v*.py installers found")
    return max(installers)


def parse_version(text: str | None) -> tuple[int, int, int] | None:
    if not text:
        return None
    raw = text.strip().lstrip("vV")
    parts = raw.split(".")
    if not 1 <= len(parts) <= 3:
        return None
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])  # type: ignore[return-value]


def version_text(target: Path) -> str | None:
    p = target / ".codex/harness/VERSION"
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8", errors="replace").strip()
    return text or None


def current_version(target: Path) -> tuple[int, int, int] | None:
    raw = version_text(target)
    if raw is None:
        return None
    parsed = parse_version(raw)
    if parsed is None:
        raise InstallLatestError(f"invalid Harness VERSION: {raw!r}")
    return parsed


def detect_target(explicit: str | None) -> Path:
    if explicit:
        target = Path(explicit).expanduser().resolve()
    elif PACKAGE_ROOT.parent.name == "tools":
        target = PACKAGE_ROOT.parent.parent.resolve()
    else:
        target = Path.cwd().resolve()
    if not target.is_dir():
        raise InstallLatestError(f"project root does not exist: {target}")
    return target


def validate_package() -> None:
    missing = [name for name in REQUIRED_INSTALLERS if not (PACKAGE_ROOT / name).is_file()]
    if not (PACKAGE_ROOT / "payload").is_dir():
        missing.append("payload/")
    if missing:
        raise InstallLatestError("installer package is incomplete: " + ", ".join(missing))


def bootstrap_pristine_project(target: Path) -> list[Path]:
    """Create only files required by the bundled v6.0 installer to start.

    Existing project files are never overwritten here. Later official installers
    own/merge these files transactionally.
    """
    created: list[Path] = []

    def ensure_file(rel: str, text: str) -> None:
        p = target / rel
        if p.exists():
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        created.append(p)
        print(f"[BOOTSTRAP] created {rel}")

    ensure_file("AGENTS.md", "")
    ensure_file(".codex/config.toml", "")
    ensure_file(".codex/harness/config.json", "{}\n")
    ensure_file(".codex/harness/commands.json", '{"commands": []}\n')
    skills = target / ".agents/skills"
    if not skills.exists():
        skills.mkdir(parents=True, exist_ok=True)
        created.append(skills)
        print("[BOOTSTRAP] created .agents/skills/")
    return created


def cleanup_created(created: Iterable[Path], target: Path) -> None:
    for p in sorted(created, key=lambda x: len(x.parts), reverse=True):
        try:
            if p.is_file() or p.is_symlink():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
        except OSError:
            pass
    # Remove only empty bootstrap parents.
    for p in (target / ".codex/harness", target / ".codex", target / ".agents"):
        try:
            p.rmdir()
        except OSError:
            pass


def child_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("TERM", "xterm")
    return env


def run_installer(script: str, target: Path, *extra: str) -> None:
    cmd = [sys.executable, str(PACKAGE_ROOT / script), "--target", str(target), *extra]
    print("\n" + "=" * 72)
    print(f"[STEP] {script} {' '.join(extra)}".rstrip())
    print("=" * 72)
    cp = subprocess.run(cmd, cwd=target, env=child_env())
    if cp.returncode != 0:
        raise InstallLatestError(f"{script} failed with exit code {cp.returncode}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise InstallLatestError(f"cannot load installer module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def install_v611_reviewed(target: Path) -> None:
    """Install v6.11, allowing only the known pristine-chain selftest variance."""
    module = load_module(PACKAGE_ROOT / "install_v6_11.py", "_adaptive_install_v611")
    reviewed = dict(module.REVIEWED_V610_CORE)
    mismatches: list[tuple[str, str, str]] = []
    for rel, expected in reviewed.items():
        p = target / rel
        actual = sha256(p) if p.is_file() else "MISSING"
        if actual != expected:
            mismatches.append((rel, actual, expected))

    if not mismatches:
        run_installer("install_v6_11.py", target)
        return

    compat_rel = ".codex/harness/scripts/selftest.py"
    if (
        len(mismatches) == 1
        and mismatches[0][0] == compat_rel
        and mismatches[0][1] in KNOWN_BUNDLED_V610_SELFTEST_HASHES
    ):
        actual = mismatches[0][1]
        print("\n[COMPAT] bundled v6.10 selftest variance detected.")
        print("[COMPAT] all other reviewed v6.10 core files match exactly; normalizing through v6.11.")
        module.REVIEWED_V610_CORE[compat_rel] = actual
        try:
            rc = module.apply_plan(module.build_plan(target), False)
        except Exception as exc:  # v6.11 handles rollback internally in apply_plan
            raise InstallLatestError(f"install_v6_11 compatibility normalization failed: {exc}") from exc
        if rc != 0:
            raise InstallLatestError(f"install_v6_11 compatibility normalization failed with exit code {rc}")
        return

    details = ", ".join(f"{rel} ({actual[:12]} != {expected[:12]})" for rel, actual, expected in mismatches[:8])
    raise InstallLatestError(
        "v6.10 reviewed core contains unexpected drift; refusing compatibility override: " + details
    )


def run_selftest(target: Path) -> None:
    script = target / ".codex/harness/scripts/selftest.py"
    if not script.is_file():
        raise InstallLatestError("final selftest.py is missing")
    print("\n" + "=" * 72)
    print("[FINAL] selftest --install-check")
    print("=" * 72)
    cp = subprocess.run(
        [sys.executable, str(script), "--install-check", "--quiet"],
        cwd=target,
        env=child_env(),
    )
    if cp.returncode != 0:
        raise InstallLatestError(f"final selftest failed with exit code {cp.returncode}")


def install_to_latest(target: Path, rename_docs: bool) -> None:
    validate_package()
    installers = discover_installers()
    latest = max(installers)
    latest_text = format_version(latest)
    start_raw = version_text(target)
    version = current_version(target)

    if version is not None and version[0] != 6:
        raise InstallLatestError(f"unsupported Harness major version: {start_raw}")
    if version is not None and version > latest:
        raise InstallLatestError(
            f"target already has newer Harness {start_raw}; bundled latest is {latest_text}; refusing to downgrade"
        )

    print(f"Project root : {target}")
    print(f"Current      : {start_raw or 'not installed'}")
    print(f"Detected     : {', '.join(format_version(v) for v in sorted(installers))}")
    print(f"Target       : {latest_text} ({installers[latest]})")
    print(f"docs/ rename : {'enabled' if rename_docs else 'disabled (preserve docs/)'}")

    bootstrap_created: list[Path] = []
    base_completed = False
    try:
        if version is None:
            bootstrap_created = bootstrap_pristine_project(target)
            run_installer("install.py", target)
            base_completed = True
            version = current_version(target)
            if version != (6, 0, 0):
                raise InstallLatestError(f"base install produced unexpected VERSION: {version_text(target)}")

        assert version is not None

        if version < (6, 1, 0):
            run_installer("install_v6_1.py", target)
            version = current_version(target)
        if version < (6, 2, 0):
            run_installer("install_v6_2.py", target)
            version = current_version(target)
        if version < (6, 4, 0):
            extra = ("--generic",) + (() if rename_docs else ("--no-rename-docs",))
            run_installer("install_v6_4.py", target, *extra)
            version = current_version(target)
        if version < (6, 5, 0):
            extra = ("--generic",) + (() if rename_docs else ("--no-rename-docs",))
            run_installer("install_v6_5.py", target, *extra)
            version = current_version(target)
        if version < (6, 6, 0):
            run_installer("install_v6_6.py", target)
            version = current_version(target)
        if version < (6, 7, 0):
            run_installer("install_v6_7.py", target)
            version = current_version(target)
        if version < (6, 8, 0):
            run_installer("install_v6_8.py", target)
            version = current_version(target)
        if version < (6, 8, 1):
            run_installer("install_v6_8_1.py", target)
            version = current_version(target)
        if version < (6, 9, 0):
            run_installer("install_v6_9.py", target)
            version = current_version(target)
        if version < (6, 10, 0):
            run_installer("install_v6_10_updated.py", target)
            version = current_version(target)

        if version == (6, 10, 0):
            install_v611_reviewed(target)
            version = current_version(target)
        elif version < (6, 11, 0):
            raise InstallLatestError(f"unsupported intermediate VERSION before v6.11: {version_text(target)}")

        if version < (6, 12, 0):
            run_installer("install_v6_12.py", target)
            version = current_version(target)

        # Everything newer than the reviewed historical chain is discovered
        # dynamically. Adding install_v6_13.py (or later) beside this file is
        # therefore enough for install_latest.py to include it automatically.
        for release in sorted(v for v in installers if v > REVIEWED_CHAIN_END):
            if version is not None and version >= release:
                continue
            script = installers[release]
            run_installer(script, target)
            version = current_version(target)
            if version is None or version < release:
                raise InstallLatestError(
                    f"{script} completed but VERSION is {version_text(target)!r}; expected at least {format_version(release)}"
                )

        if version != latest:
            raise InstallLatestError(
                f"unexpected final VERSION: {version_text(target)} (detected latest: {latest_text})"
            )
        run_selftest(target)

    except Exception:
        if bootstrap_created and not base_completed:
            cleanup_created(bootstrap_created, target)
        raise

    print("\n" + "=" * 72)
    print(f"[OK] Adaptive Codex Harness {latest_text} is ready")
    print("=" * 72)
    print("Next: start a new Codex session and run $harness-bootstrap for project-specific commands/configuration.")


def copy_for_dry_run(source: Path, dest: Path) -> None:
    ignored_names = {".git", "node_modules", "vendor", ".harness", ".codex-harness-backup", "__pycache__"}

    def ignore(_dir: str, names: list[str]) -> set[str]:
        return {name for name in names if name in ignored_names}

    shutil.copytree(source, dest, dirs_exist_ok=True, symlinks=True, ignore=ignore)
    # Preserve project-root detection semantics without copying Git internals.
    if (source / ".git").exists() and not (dest / ".git").exists():
        (dest / ".git").mkdir(parents=True, exist_ok=True)


def dry_run(target: Path, rename_docs: bool) -> None:
    print("[DRY-RUN] executing the complete install on an isolated temporary project copy.")
    print("[DRY-RUN] original project will not be modified.")
    with tempfile.TemporaryDirectory(prefix="adaptive-harness-latest-") as td:
        sandbox = Path(td) / "project"
        copy_for_dry_run(target, sandbox)
        install_to_latest(sandbox, rename_docs)
        print(f"\n[DRY-RUN OK] full install to v{format_version(latest_bundled_version())} and final selftest succeeded in the temporary copy.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Install/upgrade Adaptive Codex Harness to the newest install_v*.py release bundled beside this script."
    )
    ap.add_argument("--target", help="Project/workspace root. Auto-detected when this package is under project/tools/.")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the entire install against an isolated temporary copy; do not modify the real project.",
    )
    ap.add_argument(
        "--rename-docs",
        action="store_true",
        help="Allow legacy new-install migration docs/ -> memo/. Default is to preserve docs/.",
    )
    args = ap.parse_args()

    try:
        target = detect_target(args.target)
        if args.dry_run:
            dry_run(target, args.rename_docs)
        else:
            install_to_latest(target, args.rename_docs)
        return 0
    except InstallLatestError as exc:
        print(f"[install_latest:ERROR] {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("[install_latest:ERROR] interrupted by user", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"[install_latest:ERROR] unexpected failure: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
