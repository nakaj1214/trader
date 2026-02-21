"""共通メタデータ生成: 予測/評価系JSON に付与する各種メタ情報。

- build_common_meta: as_of_utc / data_coverage_weeks
- build_run_meta: run_timestamp / git_commit / config_hash / data_source_flags（Phase 0）
"""

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def build_common_meta(records: list[dict]) -> dict:
    """予測/評価系JSON 用の共通メタデータを返す。

    Args:
        records: Google Sheets の全レコード（的中フィールドを含む）

    Returns:
        {"as_of_utc": str, "data_coverage_weeks": int}
    """
    as_of_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    confirmed_dates = set(
        r["日付"]
        for r in records
        if r.get("的中") in ("的中", "外れ")
    )
    data_coverage_weeks = len(confirmed_dates)

    return {
        "as_of_utc": as_of_utc,
        "data_coverage_weeks": data_coverage_weeks,
    }


def _get_git_commit() -> str:
    """現在の git commit hash（先頭7桁）を返す。取得失敗時は "unknown"。"""
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
    return "unknown"


def _get_config_hash(config_path: Path) -> str:
    """config.yaml の SHA-256 先頭8桁を返す。読み取り失敗時は "unknown"。"""
    try:
        content = config_path.read_bytes()
        return hashlib.sha256(content).hexdigest()[:8]
    except Exception:
        return "unknown"


def build_run_meta(config: dict) -> dict:
    """実行メタデータを構築する（Phase 0: 再現性担保）。

    Args:
        config: load_config() で取得した設定辞書。

    Returns:
        {
            "run_timestamp": str,        # ISO 8601 UTC
            "git_commit": str,           # git commit hash 先頭7桁
            "config_hash": str,          # config.yaml の SHA-256 先頭8桁
            "data_source_flags": dict,   # 各外部APIの有効/無効フラグ
        }
    """
    from src.utils import CONFIG_PATH

    run_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    git_commit = _get_git_commit()
    config_hash = _get_config_hash(CONFIG_PATH)

    data_source_flags = {
        "jquants": config.get("jquants", {}).get("enabled", False),
        "finnhub": config.get("finnhub", {}).get("enabled", False),
        "fmp": config.get("fmp", {}).get("enabled", False),
        "fred": bool(__import__("os").environ.get("FRED_API_KEY")),
        "google_sheets": True,
    }

    return {
        "run_timestamp": run_timestamp,
        "git_commit": git_commit,
        "config_hash": config_hash,
        "data_source_flags": data_source_flags,
    }


def save_config_snapshot(config: dict, run_meta: dict) -> None:
    """実行時の config + run_meta を artifacts/ へスナップショット保存する（Phase 0）。

    artifacts/ は .gitignore 対象のため、シークレットの誤コミットを防ぐ。
    保存失敗は警告のみとし、メイン処理を停止しない。
    """
    import logging
    import os

    from src.utils import ROOT_DIR

    logger = logging.getLogger(__name__)

    artifacts_dir = ROOT_DIR / "artifacts"
    try:
        artifacts_dir.mkdir(exist_ok=True)
        snapshot = {**run_meta, "config": config}
        snapshot_path = artifacts_dir / "config_snapshot.json"
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("config スナップショット保存: %s", snapshot_path)
    except Exception:
        logger.warning("config スナップショット保存に失敗しました（処理を続行）", exc_info=True)
