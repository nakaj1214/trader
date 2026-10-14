"""Run the production Japanese inflection scanner and persist an immutable daily snapshot."""
from __future__ import annotations

import json
import os
from datetime import date as calendar_date
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.data.atomic_write import atomic_write_text
from src.data.market_calendar import expected_tse_session_date
from src.data.provider_output import safe_error_details
from src.data.snapshot_crypto import encrypt_json, key_id, snapshot_encryption_secret
from src.data.validation import is_finite_number
from src.notify.inflection_digest import send_daily_digest
from src.notify.slack import post_text
from src.screening.inflection_live import (
    MIN_LATEST_DATE_COVERAGE,
    MIN_PRICE_COVERAGE,
    DataPolicyConfigError,
    PriceDataRetryExhausted,
    scan_japan_inflection,
)

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "dashboard" / "data" / "inflection" / "v3"
LATEST = ROOT / "dashboard" / "data" / "inflection_candidates.enc"
DIGEST_STATE = OUT_DIR.parent / "digest_state.json"
JST = ZoneInfo("Asia/Tokyo")

MIN_UNIVERSE_COUNT = 3000
MIN_TECHNICAL_COVERAGE = 0.60
MARKET_NAMES = ("Prime", "Standard", "Growth")
MARKET_COVERAGE_FIELDS = ("universe", "price_data", "technical_usable", "latest_date_count")
RAW_FEATURES_SINCE_SCHEMA = 5


def _validate_schema5_row(row: object, where: str) -> str:
    """Check one candidate/control row against what the learning loader will require; return its ticker."""
    if not isinstance(row, dict):
        raise RuntimeError(f"DATA_HEALTH: {where} row is not an object")  # noqa: TRY004 - DATA_HEALTH is RuntimeError by contract
    ticker = row.get("ticker")
    if not isinstance(ticker, str) or not ticker.strip():
        raise RuntimeError(f"DATA_HEALTH: {where} ticker missing or invalid")
    if not isinstance(row.get("features"), dict) or not isinstance(row.get("score_details"), dict):
        raise RuntimeError(  # noqa: TRY004 - DATA_HEALTH is RuntimeError by contract
            f"DATA_HEALTH: {where} features/score_details missing: {ticker}"
        )
    if not is_finite_number(row.get("pre_score")):
        raise RuntimeError(f"DATA_HEALTH: {where} pre_score is not a finite number: {ticker}")
    return ticker


def validate_report(report: dict[str, Any]) -> None:
    """Reject incomplete, stale or inconsistent scan results before they are persisted."""
    universe = int(report.get("universe_count") or 0)
    price_data = int(report.get("price_data_count") or 0)
    technical_usable = int(report.get("technical_usable_count") or 0)
    latest_date_count = int(report.get("latest_price_date_count") or 0)
    latest_price_date = report.get("latest_price_date")
    generated_at = report.get("generated_at")
    deep_count = int(report.get("deep_candidate_count") or 0)
    candidates = report.get("candidates")
    market_coverage = report.get("market_coverage")

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
            f"date={latest_price_date}, {latest_date_count}/{price_data} ({latest_date_coverage:.1%}), "
            f"histogram={report.get('latest_date_histogram')}, "
            f"stale_tickers_sample={report.get('stale_tickers_sample')}"
        )

    try:
        calendar_date.fromisoformat(str(latest_price_date))
    except ValueError as exc:
        raise RuntimeError(f"DATA_HEALTH: invalid latest market date: {latest_price_date}") from exc
    if not generated_at:
        raise RuntimeError("DATA_HEALTH: generated_at metadata missing")
    try:
        expected_market_date = expected_tse_session_date(str(generated_at))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"DATA_HEALTH: invalid generated_at metadata: {generated_at}") from exc
    if str(latest_price_date) != expected_market_date:
        raise RuntimeError(
            "DATA_HEALTH: market data is stale for the TSE calendar: "
            f"latest={latest_price_date}, expected={expected_market_date}"
        )

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

    schema_version = report.get("report_schema_version")
    if isinstance(schema_version, int) and not isinstance(schema_version, bool) and (
        schema_version >= RAW_FEATURES_SINCE_SCHEMA
    ):
        for row in candidates:
            _validate_schema5_row(row, "candidate")
        control = report.get("control_sample")
        control_size = report.get("control_sample_size")
        if (
            not isinstance(control, list)
            or isinstance(control_size, bool)
            or not isinstance(control_size, int)
            or control_size < 0
        ):
            raise RuntimeError("DATA_HEALTH: control sample metadata missing or invalid")
        liquid = int(report.get("liquid_candidate_count") or 0)
        if len(control) != min(control_size, liquid):
            raise RuntimeError(
                "DATA_HEALTH: control sample size mismatch: "
                f"control_sample={len(control)}, expected={min(control_size, liquid)}"
            )
        control_tickers = [_validate_schema5_row(row, "control sample") for row in control]
        if len(control_tickers) != len(set(control_tickers)):
            raise RuntimeError("DATA_HEALTH: duplicate control sample tickers detected")

    if not isinstance(market_coverage, dict) or set(market_coverage) != set(MARKET_NAMES):
        raise RuntimeError("DATA_HEALTH: invalid market coverage keys")
    market_totals = dict.fromkeys(MARKET_COVERAGE_FIELDS, 0)
    for market in MARKET_NAMES:
        row = market_coverage[market]
        if not isinstance(row, dict) or set(row) != set(MARKET_COVERAGE_FIELDS):
            raise RuntimeError(f"DATA_HEALTH: invalid market coverage fields: {market}")
        for field in MARKET_COVERAGE_FIELDS:
            value = row[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RuntimeError(f"DATA_HEALTH: invalid market coverage value: {market}.{field}")
            market_totals[field] += value

    expected_totals = {
        "universe": universe,
        "price_data": price_data,
        "technical_usable": technical_usable,
        "latest_date_count": latest_date_count,
    }
    if market_totals != expected_totals:
        raise RuntimeError(
            f"DATA_HEALTH: market coverage totals mismatch: {market_totals} != {expected_totals}"
        )

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


def persist_report(
    report: dict[str, Any],
    *,
    encryption_secret: str,
    out_dir: Path = OUT_DIR,
    latest_path: Path = LATEST,
    date: str | None = None,
    digest_state: Path | None = None,
) -> tuple[Path, bool]:
    """Persist encrypted latest output and create one immutable snapshot per market-data date.

    With ``digest_state`` a brand-new market day is marked ``pending`` BEFORE its snapshot is written, so a stop
    anywhere after that still leaves a snapshot whose digest is owed (not one mistaken for a legacy snapshot).
    """
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

    if digest_state is not None and not snapshot.exists():
        _mark_digest_pending(digest_state, market_date)
    snapshot_created = atomic_write_text(snapshot, payload, overwrite=False)

    atomic_write_text(latest_path, payload)
    return snapshot, snapshot_created


def _digest_states(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or any(
        not isinstance(day, str) or state not in {"pending", "succeeded"} for day, state in loaded.items()
    ):
        raise ValueError("invalid digest state")
    return loaded


def _write_digest_state(path: Path, states: dict[str, str]) -> None:
    atomic_write_text(path, json.dumps(dict(sorted(states.items())[-30:]), sort_keys=True) + "\n")


def _digest_state_path() -> Path:
    return OUT_DIR.parent / DIGEST_STATE.name


def _mark_digest_pending(path: Path, market_date: str) -> None:
    """Best effort: a missing or damaged state file must never stop the snapshot from being saved."""
    try:
        states = _digest_states(path)
        if market_date not in states:
            states[market_date] = "pending"
            _write_digest_state(path, states)
    except (OSError, ValueError):
        pass  # _deliver_digest reports the state problem; it will not send what it cannot track


def _deliver_digest(
    report: dict[str, Any], *, snapshot_created: bool, state_path: Path | None = None, resend: bool = False
) -> str:
    """Persist pending/succeeded around best-effort delivery; Git publication is a later step.

    A state file that cannot be read or written is reported, never raised: the scan and its snapshot are
    already saved, and sending without a record of it could repeat the digest tomorrow.
    """
    state_path = state_path or _digest_state_path()
    market_date = str(report["latest_price_date"])
    try:
        states = _digest_states(state_path)
    except (OSError, ValueError):
        return "failed:digest-state-invalid"
    state = states.get(market_date)
    if not resend and state == "succeeded":
        return "skipped:already-succeeded"
    if not resend and state is None and not snapshot_created:
        return "skipped:legacy-no-state"
    states[market_date] = "pending"
    try:
        _write_digest_state(state_path, states)
    except OSError:
        return "failed:digest-state-unwritable"
    status = send_daily_digest(report, snapshot_dir=OUT_DIR, webhook=os.getenv("SLACK_WEBHOOK_URL"))
    if status == "sent":
        states[market_date] = "succeeded"
        try:
            _write_digest_state(state_path, states)
        except OSError:
            return "sent:state-save-failed"
    return status


DIGEST_STATE_ALERT = (
    "[JP Inflection] 日次ダイジェストを送れませんでした。通知状態ファイル（digest_state.json）が読めない・書けない状態です。"
    "snapshot は保存済みです。ファイルの内容を確認して修正（または削除）してください。"
)


def _alert_digest_state(webhook: str | None) -> str:
    """Tell the operator, on the same channel, that the digest cannot be tracked; fixed text, nothing sensitive."""
    if not webhook:
        return "skipped:no-webhook"
    try:
        post_text(webhook, DIGEST_STATE_ALERT)
    except Exception as exc:  # noqa: BLE001 - an alert must never fail the scan; log only the type
        return f"failed:{type(exc).__name__}"
    return "sent"


def main() -> None:
    try:
        encryption_secret = snapshot_encryption_secret()
    except Exception as exc:
        _publish_failure_stage("authentication", exc)
        raise
    try:
        report = scan_japan_inflection()
    except PriceDataRetryExhausted as exc:
        if output_path := os.getenv("GITHUB_OUTPUT"):
            with Path(output_path).open("a", encoding="utf-8") as output:
                output.writelines(f"{key}={value}\n" for key, value in exc.details.items())
        raise
    except Exception as exc:
        _publish_failure_stage("configuration" if isinstance(exc, DataPolicyConfigError) else "data_acquisition", exc)
        raise
    try:
        snapshot, snapshot_created = persist_report(
            report, encryption_secret=encryption_secret, digest_state=_digest_state_path(),
        )
    except Exception as exc:
        _publish_failure_stage("snapshot_save", exc)
        raise
    try:
        digest_status = _deliver_digest(
            report,
            snapshot_created=snapshot_created,
            resend=os.getenv("RESEND_DIGEST", "false").lower() == "true",
        )
    except Exception as exc:  # noqa: BLE001 - the snapshot is saved; the digest must never fail the scan
        digest_status = f"failed:{type(exc).__name__}"
    digest_alert = ""
    if digest_status.startswith("failed:"):
        # Visible on the run summary page without opening the log (the status itself is a fixed, safe string).
        print(f"::warning title=Daily digest not sent::{digest_status}")
        if digest_status.startswith("failed:digest-state"):  # Slack itself works; use it to say the state is broken
            digest_alert = f" digest_alert={_alert_digest_state(os.getenv('SLACK_WEBHOOK_URL'))}"

    counts = report.get("classification_counts", {})
    market_summary = " ".join(
        f"{market.lower()}_coverage="
        f"price:{(row['price_data'] / row['universe'] if row['universe'] else 0):.1%},"
        f"technical:{(row['technical_usable'] / row['universe'] if row['universe'] else 0):.1%},"
        f"latest:{(row['latest_date_count'] / row['price_data'] if row['price_data'] else 0):.1%}"
        for market, row in report["market_coverage"].items()
    )
    print(
        "inflection shadow scan complete: "
        f"universe={report.get('universe_count')} "
        f"price_data={report.get('price_data_count')} "
        f"technical={report.get('technical_usable_count')} "
        f"market_date={report.get('latest_price_date')} "
        f"early={counts.get('EARLY_CANDIDATE', 0)} "
        f"watch={counts.get('WATCH', 0)} "
        f"overextended={counts.get('OVEREXTENDED', 0)} "
        f"{market_summary} "
        f"snapshot={snapshot.name} "
        f"snapshot_created={snapshot_created} "
        f"digest={digest_status}{digest_alert}"
    )


def _publish_failure_stage(stage: str, error: Exception) -> None:
    status = getattr(getattr(error, "response", None), "status_code", None)
    if status in (401, 403) or str(error).startswith("JQUANTS_API_KEY"):
        stage = "authentication"
    elif str(error).startswith("DATA_HEALTH:"):
        stage = "data_validation"
    if output_path := os.getenv("GITHUB_OUTPUT"):
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write(f"failure_stage={stage}\n")


def cli() -> int:
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - keep ticker samples and provider credentials out of public tracebacks
        print(f"inflection shadow scan failed: {safe_error_details(exc)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
