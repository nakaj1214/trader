"""Run metadata generation for reproducibility tracking.

Produces RunMeta instances containing git hash, config hash,
timestamps, and data source flags for each pipeline execution.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog

from src.core.config import ROOT_DIR
from src.core.models import RunMeta

logger = structlog.get_logger(__name__)


def _get_git_hash() -> str | None:
    """Return the short git commit hash, or None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _get_config_hash() -> str:
    """Return the SHA-256 hex digest of the default config file."""
    config_path = ROOT_DIR / "config" / "default.yaml"
    try:
        content = config_path.read_bytes()
        return hashlib.sha256(content).hexdigest()
    except Exception:
        logger.warning("config_hash_failed", path=str(config_path))
        return "unknown"


def build_run_meta() -> RunMeta:
    """Build metadata for the current pipeline run."""
    return RunMeta(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        git_hash=_get_git_hash(),
        config_hash=_get_config_hash(),
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    )


def save_config_snapshot(config_dict: dict, run_meta: RunMeta) -> None:
    """Save a config + metadata snapshot to artifacts/ for audit purposes.

    The artifacts/ directory is .gitignore-d to prevent secret leakage.
    Failures are logged as warnings and do not halt the pipeline.
    """
    artifacts_dir = ROOT_DIR / "artifacts"
    try:
        artifacts_dir.mkdir(exist_ok=True)
        snapshot = {
            **run_meta.model_dump(),
            "config": config_dict,
        }
        snapshot_path = artifacts_dir / "config_snapshot.json"
        snapshot_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("config_snapshot_saved", path=str(snapshot_path))
    except Exception:
        logger.warning("config_snapshot_save_failed", exc_info=True)
