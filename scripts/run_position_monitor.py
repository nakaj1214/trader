"""Monitor manually held positions and publish provisional exit alerts."""
from __future__ import annotations

import argparse
import math
import os
from dataclasses import asdict
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import requests

from src.data.live_quote import fetch_split_adjusted_history, fetch_today_quote
from src.data.market_calendar import TSE_CALENDAR
from src.data.sheets_client import read_holdings, write_status
from src.monitoring.position_exit import (
    DEFAULT_TRAILING_STOP_PCT,
    StaleQuoteError,
    evaluate_position,
)

JST = ZoneInfo("Asia/Tokyo")
SLACK_TIMEOUT_SECONDS = 10


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
    }


def _post_slack(webhook: str, text: str) -> None:
    response = requests.post(webhook, json={"text": text}, timeout=SLACK_TIMEOUT_SECONDS)
    response.raise_for_status()


def run(*, dry_run: bool, evaluated_at: datetime | None = None) -> int:
    webhook = os.getenv("SLACK_WEBHOOK_URL", "")
    if not dry_run and not webhook:
        raise RuntimeError("SLACK_WEBHOOK_URL is required unless --dry-run is used")
    current = evaluated_at or datetime.now(JST)
    if current.tzinfo is None:
        raise ValueError("evaluated_at must include a timezone")
    current = current.astimezone(JST)

    holdings = read_holdings()
    if not holdings:
        write_status([])
        print("position monitor complete: holdings=0")
        return 0
    calendar = xcals.get_calendar(TSE_CALENDAR)
    if not bool(calendar.is_session(current.date().isoformat())):
        print(f"position monitor skipped: non-TSE-session date={current.date().isoformat()}")
        return 0

    rows: list[dict[str, Any]] = []
    for row_number, holding in enumerate(holdings, start=2):
        ticker = str(holding.get("ticker") or "").strip()
        raw_date = holding.get("entry_date", "")
        raw_price = holding.get("entry_price", "")
        raw_stop = holding.get("trailing_stop_pct", "")
        stop_value: object = DEFAULT_TRAILING_STOP_PCT if raw_stop in (None, "") else raw_stop
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
            quote = fetch_today_quote(ticker)
            if quote is None:
                rows.append(
                    _failure_row(
                        ticker=ticker,
                        entry_date=raw_date,
                        entry_price=raw_price,
                        trailing_stop_pct=stop_pct,
                        status="stale",
                        error="current quote is missing or invalid",
                    )
                )
                continue
            status = evaluate_position(
                history.entry_price,
                purchase_date.isoformat(),
                history.daily_highs,
                history.daily_closes,
                quote,
                stop_pct,
                current,
                ticker,
            )
            rows.append({**asdict(status), "status": "ok", "error": ""})
        except StaleQuoteError as exc:
            rows.append(
                _failure_row(
                    ticker=ticker,
                    entry_date=raw_date,
                    entry_price=raw_price,
                    trailing_stop_pct=stop_value,
                    status="stale",
                    error=str(exc),
                )
            )
        except Exception as exc:  # noqa: BLE001 - one bad holding must not hide the others
            rows.append(
                _failure_row(
                    ticker=ticker,
                    entry_date=raw_date,
                    entry_price=raw_price,
                    trailing_stop_pct=stop_value,
                    status="error",
                    error=f"row {row_number}: {exc}",
                )
            )

    write_status(rows)
    ok_rows = [row for row in rows if row["status"] == "ok"]
    stale_rows = [row for row in rows if row["status"] == "stale"]
    error_rows = [row for row in rows if row["status"] == "error"]
    triggered = [row for row in ok_rows if row.get("triggered") is True]
    if not ok_rows:
        raise RuntimeError("position monitor failed: no holdings had a usable current quote")

    if not dry_run and triggered:
        details = "\n".join(
            f"• {row['ticker']}: {row['exit_reason']} current={row['current_price']} stop={row['stop_price']}"
            for row in triggered
        )
        # ponytail: at most three scheduled alerts daily; add persisted deduplication only if that becomes noisy.
        _post_slack(
            webhook,
            "[検証用アラート] Trailing Stop条件を検知しました。確定した売買判断ではありません。"
            " GitHub Actionsの実行時刻はbest-effortです。\n"
            + details,
        )
    if not dry_run and (stale_rows or error_rows):
        details = "\n".join(f"• {row['ticker']}: {row['status']} {row['error']}" for row in stale_rows + error_rows)
        _post_slack(webhook, "[Position Monitor警告] 一部銘柄を評価できませんでした。\n" + details)

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
