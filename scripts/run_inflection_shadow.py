"""Run the production Japanese inflection scanner and persist an immutable daily snapshot."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.data.snapshot_crypto import encrypt_json, key_id
from src.screening.inflection_live import scan_japan_inflection

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "dashboard" / "data" / "inflection"
LATEST = ROOT / "dashboard" / "data" / "inflection_candidates.enc"
JST = ZoneInfo("Asia/Tokyo")

MIN_UNIVERSE_COUNT = 3000
MIN_PRICE_COVERAGE = 0.70
MIN_TECHNICAL_COVERAGE = 0.60
MIN_LATEST_DATE_COVERAGE = 0.80


def validate_report(report: dict[str, Any]) -> None:
    """Reject incomplete or inconsistent scan results before they are persisted."""
    universe = int(report.get("universe_count") or 0)
    price_data = int(report.get("price_data_count") or 0)
    technical_usable = int(report.get("technical_usable_count") or 0)
    latest_date_count = int(report.get("latest_price_date_count") or 0)
    latest_price_date = report.get("latest_price_date")
    deep_count = int(report.get("deep_candidate_count") or 0)
    candidates = report.get("candidates")

    if universe < MIN_UNIVERSE_COUNT:
        raise RuntimeError(f"DATA_HEALTH: universe too small: {universe} < {MIN_UNIVERSE_COUNT}")

    price_coverage = (price_data / universe) if universe > 0 else 0.0
    if price_coverage < MIN_PRICE_COVERAGE:
        raise RuntimeError(
            "DATA_HEALTH: price coverage too low: "
            f"{price_data}/{universe} ({price_coverage:.1%})"
        )

    technical_coverage = (technical_usable / universe) if universe > 0 else 0.0
    if technical_coverage < MIN_TECHNICAL_COVERAGE:
        raise RuntimeError(
            "DATA_HEALTH: technical coverage too low: "
            f"{technical_usable}/{universe} ({technical_coverage:.1%})"
        )

    latest_date_coverage = (latest_date_count / price_data) if price_data > 0 else 0.0
    if not latest_price_date or latest_date_coverage < MIN_LATEST_DATE_COVERAGE:
        raise RuntimeError(
            "DATA_HEALTH: latest market-date coverage too low: "
            f"date={latest_price_date}, {latest_date_count}/{price_data} ({latest_date_coverage:.1%})"
        )

    try:
        datetime.strptime(str(latest_price_date), "%Y-%m-%d")
    except ValueError as exc:
        raise RuntimeError(f"DATA_HEALTH: invalid latest market date: {latest_price_date}") from exc

    if deep_count <= 0:
        raise RuntimeError("DATA_HEALTH: no deep candidates were produced")

    if not isinstance(candidates, list) or len(candidates) != deep_count:
        actual = len(candidates) if isinstance(candidates, list) else "invalid"
        raise RuntimeError(
            "DATA_HEALTH: candidate count mismatch: "
            f"deep_candidate_count={deep_count}, candidates={actual}"
        )

    tickers = [str(row.get("ticker") or "") for row in candidates if isinstance(row, dict)]
    if len(tickers) != len(candidates) or any(not ticker for ticker in tickers):
        raise RuntimeError("DATA_HEALTH: candidate ticker missing or invalid")
    if len(tickers) != len(set(tickers)):
        raise RuntimeError("DATA_HEALTH: duplicate candidate tickers detected")

    if not report.get("strategy_version") or not report.get("report_schema_version"):
        raise RuntimeError("DATA_HEALTH: strategy/schema version metadata missing")
    if not report.get("source_commit_sha"):
        raise RuntimeError("DATA_HEALTH: source commit metadata missing")
    runtime_versions = report.get("runtime_versions")
    if not isinstance(runtime_versions, dict) or not runtime_versions.get("yfinance") or not runtime_versions.get("pandas"):
        raise RuntimeError("DATA_HEALTH: runtime dependency metadata missing")


def snapshot_date(now: datetime | None = None) -> str:
    """Return the current Japan calendar date for diagnostics and tests."""
    current = now or datetime.now(JST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=JST)
    return current.astimezone(JST).strftime("%Y-%m-%d")


def snapshot_secret() -> str:
    """Use a dedicated storage key when present, otherwise the already-required J-Quants key.

    The fallback keeps the first scheduled run self-contained. Set SNAPSHOT_ENCRYPTION_KEY
    before rotating JQUANTS_API_KEY so historical snapshots remain decryptable.
    """
    secret = os.getenv("SNAPSHOT_ENCRYPTION_KEY") or os.getenv("JQUANTS_API_KEY")
    if not secret:
        raise RuntimeError("SNAPSHOT_ENCRYPTION_KEY or JQUANTS_API_KEY is required for encrypted snapshot storage")
    return secret


def persist_report(
    report: dict[str, Any],
    *,
    encryption_secret: str,
    out_dir: Path = OUT_DIR,
    latest_path: Path = LATEST,
    date: str | None = None,
) -> tuple[Path, bool]:
    """Persist encrypted latest output and create one immutable snapshot per market-data date."""
    validate_report(report)
    market_date = str(report["latest_price_date"])
    snapshot_key = date or market_date
    if date is not None and date != market_date:
        raise ValueError(f"snapshot date must match latest_price_date: {date} != {market_date}")

    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = out_dir / f"{snapshot_key}.enc"
    stored_report = dict(report)
    stored_report["storage"] = {
        "format": "fernet-v1",
        "encrypted": True,
        "key_id": key_id(encryption_secret),
        "snapshot_date_basis": "latest_price_date",
    }
    payload = encrypt_json(stored_report, encryption_secret)

    snapshot_created = False
    if not snapshot.exists():
        snapshot.write_text(payload, encoding="utf-8")
        snapshot_created = True

    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(payload, encoding="utf-8")
    return snapshot, snapshot_created


def main() -> None:
    report = scan_japan_inflection()
    snapshot, snapshot_created = persist_report(report, encryption_secret=snapshot_secret())

    counts = report.get("classification_counts", {})
    print(
        "inflection shadow scan complete: "
        f"universe={report.get('universe_count')} "
        f"price_data={report.get('price_data_count')} "
        f"technical={report.get('technical_usable_count')} "
        f"market_date={report.get('latest_price_date')} "
        f"early={counts.get('EARLY_CANDIDATE', 0)} "
        f"watch={counts.get('WATCH', 0)} "
        f"overextended={counts.get('OVEREXTENDED', 0)} "
        f"snapshot={snapshot.name} "
        f"snapshot_created={snapshot_created}"
    )


if __name__ == "__main__":
    main()
