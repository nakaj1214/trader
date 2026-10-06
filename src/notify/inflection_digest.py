"""Daily Slack digest of the day's inflection candidates.

The digest is best-effort: a failure here must never fail the scan (the snapshot commit step runs
after it), and nothing about the candidates may reach the job log (the repository is public).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from src.data.session_gaps import missing_sessions, previous_session_missing
from src.notify.slack import escape, post_text

EARLY_LIMIT = 10
WATCH_LIMIT = 5


def _pct(value: Any) -> str:
    return f"{float(value):+.1f}%" if isinstance(value, (int, float)) and not isinstance(value, bool) else "-"


def _number(value: Any, spec: str) -> str:
    return format(float(value), spec) if isinstance(value, (int, float)) and not isinstance(value, bool) else "-"


def _line(candidate: dict[str, Any]) -> str:
    place = "・".join(str(part) for part in (candidate.get("market"), candidate.get("sector33_name")) if part) or "-"
    reasons = "・".join(str(reason) for reason in candidate.get("reasons") or []) or "-"
    name = escape(str(candidate.get("company_name") or ""))
    return (
        f"• {escape(str(candidate.get('ticker')))} {name}（{escape(place)}） "
        f"{_number(candidate.get('score'), '.1f')}点 20日{_pct(candidate.get('return_20d_pct'))} "
        f"出来高比{_number(candidate.get('volume_ratio_20d'), '.2f')} {escape(reasons)}"
    )


def _section(title: str, rows: list[dict[str, Any]], limit: int) -> list[str]:
    shown = rows[:limit]
    heading = f"■ {title}" + (f"（上位{limit}件）" if len(rows) > limit else "")
    lines = [heading, *(_line(row) for row in shown)]
    if len(rows) > limit:
        lines.append(f"（ほか{len(rows) - limit}件）")
    return lines


def build_digest(report: dict[str, Any], *, warnings: list[str]) -> str:
    """The message text for one scan day."""
    counts = report.get("classification_counts") or {}
    delay = (report.get("data_policy") or {}).get("jquants_data_delay_weeks")
    delay_text = f"財務データは約{delay}週間遅れです。" if delay else "財務データの公開時点を確認してください。"
    candidates = [row for row in report.get("candidates") or [] if isinstance(row, dict)]
    lines = [
        f"[検証用] JP Inflection 日次候補 {report.get('latest_price_date')}",
        f"売買推奨ではありません。{delay_text}",
        (
            f"EARLY_CANDIDATE {counts.get('EARLY_CANDIDATE', 0)}件 / WATCH {counts.get('WATCH', 0)}件 / "
            f"OVEREXTENDED {counts.get('OVEREXTENDED', 0)}件"
        ),
    ]
    early = [row for row in candidates if row.get("classification") == "EARLY_CANDIDATE"]
    watch = [row for row in candidates if row.get("classification") == "WATCH"]
    if early:
        lines += _section("EARLY_CANDIDATE", early, EARLY_LIMIT)
    if watch:
        lines += _section("WATCH", watch, WATCH_LIMIT)
    if not early and not watch:
        lines.append("本日の候補はありません。")
    lines += [f"⚠ {warning}" for warning in warnings]
    return "\n".join(lines)


def daily_warnings(snapshot_dir: Path, market_date: date) -> list[str]:
    """Data-quality warnings: a skipped previous session, and the total of skipped sessions so far."""
    warnings: list[str] = []
    previous = previous_session_missing(snapshot_dir, market_date)
    if previous:
        warnings.append(f"前の営業日（{previous}）の snapshot がありません。scan が失敗した可能性があります。")
    total = len(missing_sessions(snapshot_dir, market_date))
    if total:
        warnings.append(f"これまでに snapshot が欠けた営業日: {total}日")
    return warnings


def send_daily_digest(
    report: dict[str, Any],
    *,
    snapshot_dir: Path,
    webhook: str | None,
    post: Callable[[str, str], None] = post_text,
) -> str:
    """Send the digest; returns a status string that is safe to log (no candidate data, no URL)."""
    if not webhook:
        return "skipped:no-webhook"
    try:
        warnings = daily_warnings(snapshot_dir, date.fromisoformat(str(report["latest_price_date"])))
        post(webhook, build_digest(report, warnings=warnings))
    except Exception as exc:  # noqa: BLE001 - best-effort: never fail the scan; log only the type
        return f"failed:{type(exc).__name__}"
    return "sent"
