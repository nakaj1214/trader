"""Monitor manually held positions and publish provisional exit alerts."""

from __future__ import annotations

import argparse
import math
import os
from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import requests

from src.data.live_quote import build_today_quote, fetch_split_adjusted_history, fetch_today_bars
from src.data.market_calendar import TSE_CALENDAR
from src.data.sheets_client import read_holdings, read_status, write_status
from src.monitoring.position_exit import (
    DEFAULT_TRAILING_STOP_PCT,
    StaleQuoteError,
    evaluate_position,
)

JST = ZoneInfo("Asia/Tokyo")
SLACK_TIMEOUT_SECONDS = 10
CLOSE_GRACE_MINUTES = 30


def _number(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def _failure_row(
    *,
    ticker: str,
    entry_date: object,
    entry_price: object,
    trailing_stop_pct: object,
    status: str,
    error: str,
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "entry_date": entry_date,
        "entry_price": entry_price,
        "trailing_stop_pct": trailing_stop_pct,
        "triggered": False,
        "status": status,
        "error": error,
        "triggered_at": "",
        "last_notified_at": "",
    }


def _post_slack(webhook: str, text: str) -> None:
    response = requests.post(webhook, json={"text": text}, timeout=SLACK_TIMEOUT_SECONDS)
    response.raise_for_status()


def _position_key(row: dict[str, Any]) -> tuple[str, str] | None:
    ticker = str(row.get("ticker") or "").strip()
    try:
        entry_date = date.fromisoformat(str(row.get("entry_date") or "")).isoformat()
    except ValueError:
        return None
    return (ticker, entry_date) if ticker else None


def _unique_rows(rows: list[dict[str, Any]], source: str) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = _position_key(row)
        if key is None:
            continue
        if key in indexed:
            raise ValueError(f"duplicate position key in {source}: {key[0]} {key[1]}")
        indexed[key] = row
    return indexed


def _stored_triggered(row: dict[str, Any] | None) -> bool:
    if row is None or row.get("triggered") in (None, "", False, 0, "FALSE", "false"):
        return False
    if row.get("triggered") in (True, 1, "TRUE", "true"):
        return True
    raise ValueError("stored triggered state is invalid")


def _preserve_previous_state(row: dict[str, Any], previous: dict[str, Any] | None) -> None:
    triggered = _stored_triggered(previous)
    row["triggered"] = triggered
    row["exit_reason"] = previous.get("exit_reason", "") if previous and triggered else ""
    row["triggered_at"] = previous.get("triggered_at", "") if previous and triggered else ""
    row["last_notified_at"] = previous.get("last_notified_at", "") if previous and triggered else ""


def is_in_session(calendar: Any, when: datetime) -> bool:
    minute = when.replace(second=0, microsecond=0)
    if bool(calendar.is_open_on_minute(minute, ignore_breaks=False)):
        return True
    session = when.date().isoformat()
    if not bool(calendar.is_session(session)):
        return False
    close: datetime = calendar.session_close(session).to_pydatetime().astimezone(JST)
    return timedelta(0) <= when - close <= timedelta(minutes=CLOSE_GRACE_MINUTES)


def run(*, dry_run: bool, evaluated_at: datetime | None = None) -> int:
    webhook = os.getenv("SLACK_WEBHOOK_URL", "")
    if not dry_run and not webhook:
        raise RuntimeError("SLACK_WEBHOOK_URL is required unless --dry-run is used")
    current = evaluated_at or datetime.now(JST)
    if current.tzinfo is None:
        raise ValueError("evaluated_at must include a timezone")
    current = current.astimezone(JST)

    previous_rows = read_status()
    previous_by_key = _unique_rows(previous_rows, "status")
    holdings = read_holdings()
    _unique_rows(holdings, "holdings")
    if not holdings:
        write_status([])
        print("position monitor complete: holdings=0")
        return 0
    calendar = xcals.get_calendar(TSE_CALENDAR)
    if not bool(calendar.is_session(current.date().isoformat())):
        print(f"position monitor skipped: non-TSE-session date={current.date().isoformat()}")
        return 0
    in_market_window = is_in_session(calendar, current)

    rows: list[dict[str, Any]] = []
    notifications: list[dict[str, Any]] = []
    for row_number, holding in enumerate(holdings, start=2):
        ticker = str(holding.get("ticker") or "").strip()
        raw_date = holding.get("entry_date", "")
        raw_price = holding.get("entry_price", "")
        raw_stop = holding.get("trailing_stop_pct", "")
        stop_value: object = DEFAULT_TRAILING_STOP_PCT if raw_stop in (None, "") else raw_stop
        key = _position_key(holding)
        previous = previous_by_key.get(key) if key is not None else None
        try:
            if not ticker:
                raise ValueError("ticker is required")
            purchase_date = date.fromisoformat(str(raw_date))
            if purchase_date > current.date():
                raise ValueError("entry_date must not be in the future")
            if not bool(calendar.is_session(purchase_date.isoformat())):
                raise ValueError("entry_date must be a TSE session")
            entry_price = _number(raw_price, "entry_price")
            stop_pct = _number(stop_value, "trailing_stop_pct")
            if stop_pct >= 100:
                raise ValueError("trailing_stop_pct must be between 0 and 100")

            history = fetch_split_adjusted_history(ticker, purchase_date.isoformat(), entry_price)
            bars = fetch_today_bars(ticker)
            quote = None if bars is None else build_today_quote(bars)
            if bars is None or quote is None:
                failed = _failure_row(
                    ticker=ticker,
                    entry_date=raw_date,
                    entry_price=raw_price,
                    trailing_stop_pct=stop_pct,
                    status="stale",
                    error="current quote is missing or invalid",
                )
                _preserve_previous_state(failed, previous)
                rows.append(failed)
                continue
            status = evaluate_position(
                history.entry_price,
                purchase_date.isoformat(),
                history.daily_highs,
                history.daily_closes,
                quote,
                bars,
                stop_pct,
                current,
                ticker,
                in_session=in_market_window,
            )
            result = {**asdict(status), "status": "ok", "error": ""}
            was_triggered = _stored_triggered(previous)
            if status.triggered:
                result["triggered_at"] = (
                    previous.get("triggered_at") if previous and was_triggered else current.isoformat()
                ) or current.isoformat()
                result["last_notified_at"] = previous.get("last_notified_at", "") if previous and was_triggered else ""
                if not result["last_notified_at"]:
                    notifications.append(result)
            else:
                result["triggered_at"] = ""
                result["last_notified_at"] = ""
            rows.append(result)
        except StaleQuoteError as exc:
            failed = _failure_row(
                ticker=ticker,
                entry_date=raw_date,
                entry_price=raw_price,
                trailing_stop_pct=stop_value,
                status="stale",
                error=str(exc),
            )
            _preserve_previous_state(failed, previous)
            rows.append(failed)
        except Exception as exc:  # noqa: BLE001 - one bad holding must not hide the others
            failed = _failure_row(
                ticker=ticker,
                entry_date=raw_date,
                entry_price=raw_price,
                trailing_stop_pct=stop_value,
                status="error",
                error=f"row {row_number}: {exc}",
            )
            _preserve_previous_state(failed, previous)
            rows.append(failed)

    ok_rows = [row for row in rows if row["status"] == "ok"]
    stale_rows = [row for row in rows if row["status"] == "stale"]
    error_rows = [row for row in rows if row["status"] == "error"]
    triggered = [row for row in ok_rows if row.get("triggered") is True]
    if not ok_rows:
        write_status(rows)
        raise RuntimeError("position monitor failed: no holdings had a usable current quote")

    slack_error: Exception | None = None
    if not dry_run and notifications:
        details = "\n".join(
            f"• {row['ticker']}: {row['exit_reason']} current={row['current_price']} stop={row['stop_price']}"
            for row in notifications
        )
        try:
            _post_slack(
                webhook,
                "[検証用アラート] Trailing Stop条件を検知しました。確定した売買判断ではありません。"
                " GitHub Actionsの実行時刻はbest-effortです。\n" + details,
            )
            for row in notifications:
                row["last_notified_at"] = current.isoformat()
        except Exception as exc:  # noqa: BLE001 - persist retry state before failing the workflow
            slack_error = exc
    if not dry_run and (stale_rows or error_rows):
        details = "\n".join(f"• {row['ticker']}: {row['status']} {row['error']}" for row in stale_rows + error_rows)
        try:
            _post_slack(webhook, "[Position Monitor警告] 一部銘柄を評価できませんでした。\n" + details)
        except Exception as exc:  # noqa: BLE001 - persist status before failing the workflow
            slack_error = slack_error or exc

    write_status(rows)
    if slack_error is not None:
        raise slack_error

    print(
        "position monitor complete: "
        f"holdings={len(rows)} ok={len(ok_rows)} stale={len(stale_rows)} "
        f"error={len(error_rows)} triggered={len(triggered)} dry_run={dry_run}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Monitor manual positions for provisional trailing-stop alerts.")
    parser.add_argument("--dry-run", action="store_true", help="write status without sending Slack notifications")
    args = parser.parse_args(argv)
    return run(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
