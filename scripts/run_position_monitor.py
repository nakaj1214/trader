"""Monitor manually held positions and publish provisional exit alerts."""

from __future__ import annotations

import argparse
import math
import os
from collections.abc import Callable
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, ParamSpec, TypeVar
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import requests

from src.data.live_quote import (
    SplitAdjustedHistory,
    build_today_quote,
    configure_split_history_sharing,
    fetch_session_bars,
    fetch_split_adjusted_history,
    fetch_today_bars,
    latest_one_minute_failure,
    shared_split_history_frames,
)
from src.data.market_calendar import TSE_CALENDAR
from src.data.provider_output import safe_error_details, suppress_provider_output
from src.data.sheets_client import (
    assert_production_writer,
    read_holdings,
    read_status,
    shared_spreadsheet,
    write_status,
)
from src.data.validation import is_finite_number
from src.monitoring.position_exit import (
    DEFAULT_TRAILING_STOP_PCT,
    IncompleteQuoteError,
    StaleQuoteError,
    evaluate_position,
)

JST = ZoneInfo("Asia/Tokyo")
SLACK_TIMEOUT_SECONDS = 10
CLOSE_GRACE_MINUTES = 30
WARNING_DISTANCE_PCT = 3.0  # warn when the price is within this % above the stop (stop not yet hit)
OVEREXTENDED_RETURN_20D_PCT = 50.0  # matches inflection_live._classify's r20 >= 50%; no scan dependency
# The provider keeps 1-minute history only for about this many calendar days. A pending session older than
# this can never be replayed minute by minute, so it is judged on its daily bar instead of blocking forever.
INTRADAY_RETENTION_DAYS = 30
P = ParamSpec("P")
T = TypeVar("T")


def _private_call(function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    with suppress_provider_output():
        return function(*args, **kwargs)


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
    try:
        response = requests.post(webhook, json={"text": text}, timeout=SLACK_TIMEOUT_SECONDS)
        response.raise_for_status()
    except Exception as exc:  # preserve the provider error class and annotate only a safe stage
        exc.monitor_stage = "notification"  # type: ignore[attr-defined]
        raise


def _position_key(row: dict[str, Any]) -> tuple[str, str] | None:
    ticker = str(row.get("ticker") or "").strip()
    try:
        entry_date = date.fromisoformat(str(row.get("entry_date") or "")).isoformat()
    except ValueError:
        return None
    return (ticker, entry_date) if ticker else None


def _unique_rows(rows: list[dict[str, Any]], source: str) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    source_rows: dict[tuple[str, str], int] = {}
    for row_number, row in enumerate(rows, start=2):
        key = _position_key(row)
        if key is None:
            continue
        if key in indexed:
            raise ValueError(f"duplicate position key in {source}: rows {source_rows[key]} and {row_number}")
        indexed[key] = row
        source_rows[key] = row_number
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
    row["as_of_at"] = previous.get("as_of_at", "") if previous else ""


def _daily_session_is_valid(daily: dict[str, Any]) -> bool:
    """Whether a daily bar can be trusted as evidence: finite, positive and consistent High/Low/Close.

    A comparison with NaN is always false, so an unchecked bar would "prove" there was no touch. Open is only used
    for the consistency check when it is itself finite and positive.
    """
    try:
        high, low, close = (float(daily[key]) for key in ("High", "Low", "Close"))
    except (KeyError, TypeError, ValueError):
        return False
    if not all(math.isfinite(value) and value > 0 for value in (high, low, close)):
        return False
    prices = [close]
    try:
        opened = float(daily["Open"])
    except (KeyError, TypeError, ValueError):
        opened = math.nan
    if math.isfinite(opened) and opened > 0:
        prices.append(opened)
    return low <= min(prices) and high >= max(prices)


def _daily_could_touch(prior_high_water: float, daily: dict[str, Any], stop_pct: float) -> bool:
    """Whether a minute-level evaluation of this session could have touched the trailing stop.

    A touch needs a minute low at or under ``high_water * (1 - stop)``, and the high-water mark at any minute is
    at most ``max(prior high-water, the day's high)``; no minute low is under the day's low. So a daily low above
    that level proves there was no touch, while a lower one means "possible" (the intraday order is unknown).
    """
    level = max(prior_high_water, float(daily["High"])) * (1.0 - stop_pct / 100.0)
    return float(daily["Low"]) <= level


def _recover_daily_only(
    ticker: str, purchase_date: date, session: date, history: SplitAdjustedHistory, stop_pct: float,
    daily: dict[str, Any], close: datetime,
) -> dict[str, Any] | None:
    """A session beyond the 1-minute retention: ``None`` when the daily bar rules a touch out, else a recovery row."""
    prior = history.daily_highs.loc[history.daily_highs.index.date < session]
    prior_high_water = history.entry_price if prior.empty else max(history.entry_price, float(prior.max()))
    if not _daily_could_touch(prior_high_water, daily, stop_pct):
        return None
    high_water = max(prior_high_water, float(daily["High"]))
    stop_price = high_water * (1.0 - stop_pct / 100.0)  # the most the stop could have risen to: what the day was judged on
    current_price = float(daily["Close"])
    return {
        "ticker": ticker, "entry_date": purchase_date.isoformat(), "entry_price": round(history.entry_price, 6),
        "current_price": round(current_price, 6),
        "high_water_mark": round(high_water, 6),
        "stop_price": round(stop_price, 6), "trailing_stop_pct": round(stop_pct, 6),
        "unrealized_pct": round((current_price / history.entry_price - 1.0) * 100.0, 6),
        "distance_to_stop_pct": round((current_price / stop_price - 1.0) * 100.0, 6),
        "triggered": True, "exit_reason": "recovered_daily_possible_touch", "as_of_at": close.isoformat(),
        "quote_source": "daily_bar_conservative", "status": "recovered", "error": "",
        "triggered_at": close.isoformat(), "last_notified_at": "",
    }


def _recover_pending(
    ticker: str, purchase_date: date, history: SplitAdjustedHistory, stop_pct: float,
    previous: dict[str, Any] | None, calendar: Any, current: datetime,
) -> dict[str, Any] | None:
    """Replay whole pending days so a partial checkpoint never loses intraday ordering."""
    if previous and _stored_triggered(previous) and str(previous.get("exit_reason", "")).startswith("recovered_"):
        return dict(previous)
    checkpoint = None
    if previous and previous.get("as_of_at"):
        checkpoint = datetime.fromisoformat(str(previous["as_of_at"]))
        if checkpoint.tzinfo is None:
            raise IncompleteQuoteError("stored evaluation checkpoint lacks timezone")
        checkpoint = checkpoint.astimezone(JST)
    sessions = history.daily_bars.index if not history.daily_bars.empty else history.daily_highs.index
    for timestamp in sessions:
        session = timestamp.date()
        if not purchase_date < session < current.date():
            continue
        close = calendar.session_close(session.isoformat()).to_pydatetime().astimezone(JST)
        # Recheck the checkpoint day itself: older monitor versions did not prove its path completeness.
        if checkpoint is not None and session < checkpoint.date():
            continue
        daily = _daily_reference(history, session)
        if daily is not None and daily.get("Volume") == 0 and all(
            not is_finite_number(daily.get(column)) for column in ("Open", "High", "Low", "Close")
        ):
            continue
        bars = fetch_session_bars(ticker, session.isoformat())
        failure = latest_one_minute_failure() if bars is None else None
        if bars is None and daily is not None and (current.date() - session).days > INTRADAY_RETENTION_DAYS:
            if not _daily_session_is_valid(daily):
                raise IncompleteQuoteError("pending historical session daily bar is invalid")
            recovered = _recover_daily_only(ticker, purchase_date, session, history, stop_pct, daily, close)
            if recovered is None:
                continue  # the daily bar proves there was no touch; nothing minute-level is left to replay
            if previous and _stored_triggered(previous) and previous.get("last_notified_at"):
                return dict(previous)
            return recovered
        if bars is not None and daily is not None:
            bars.attrs["daily_bar"] = daily
        quote = None if bars is None else build_today_quote(bars)
        if quote is None or bars is None:
            raise IncompleteQuoteError(
                "pending historical session data is unavailable" + (f" ({failure})" if failure else "")
            )
        status = evaluate_position(
            history.entry_price, purchase_date.isoformat(),
            history.daily_highs.loc[history.daily_highs.index.date < session],
            history.daily_closes.loc[history.daily_closes.index.date < session],
            quote, bars, stop_pct, datetime.fromisoformat(quote.as_of_at) + timedelta(minutes=1),
            ticker, in_session=False,
        )
        if status.triggered:
            if previous and _stored_triggered(previous) and previous.get("last_notified_at"):
                return dict(previous)
            return {**asdict(status), "status": "recovered", "error": "",
                    "exit_reason": f"recovered_{status.exit_reason}", "triggered_at": status.touch_at,
                    "last_notified_at": ""}
        if daily is None and datetime.fromisoformat(quote.as_of_at) < close:
            raise IncompleteQuoteError("pending historical session end is not yet confirmed")
    return None


def _daily_reference(history: SplitAdjustedHistory, session: date) -> dict[str, Any] | None:
    if history.daily_bars.empty:
        return None
    rows = history.daily_bars.loc[history.daily_bars.index.date == session]
    if len(rows) != 1:
        raise IncompleteQuoteError("daily reference for the requested session is missing or duplicated")
    return dict(rows.iloc[0])


def _warned_today(previous_rows: list[dict[str, Any]], today: date) -> dict[str, datetime]:
    """ticker -> latest warning time that falls on ``today`` (JST), taken from EVERY previous row.

    Warnings are deduplicated per ticker, not per (ticker, entry_date) position, so that a position
    swapped out and replaced during the day cannot cause the same ticker to be warned again.
    """
    warned: dict[str, datetime] = {}
    for row in previous_rows:
        ticker = str(row.get("ticker") or "").strip()
        raw = str(row.get("last_warned_at") or "").strip()
        if not ticker or not raw:
            continue
        try:
            when = datetime.fromisoformat(raw)
        except ValueError:
            continue
        when = when.replace(tzinfo=JST) if when.tzinfo is None else when.astimezone(JST)
        if when.date() == today and when > warned.get(ticker, datetime.min.replace(tzinfo=JST)):
            warned[ticker] = when
    return warned


def _stop_proximity_candidates(ok_rows: list[dict[str, Any]], warned_today: dict[str, datetime]) -> list[dict[str, Any]]:
    """One entry per ticker that is close to its stop, not triggered, and not yet warned today."""
    closest: dict[str, dict[str, Any]] = {}
    for row in ok_rows:
        ticker = str(row["ticker"])
        distance = row.get("distance_to_stop_pct")
        if row.get("triggered") is True or ticker in warned_today or isinstance(distance, bool):
            continue
        if not isinstance(distance, (int, float)) or distance > WARNING_DISTANCE_PCT:
            continue
        if ticker not in closest or distance < closest[ticker]["distance_to_stop_pct"]:
            closest[ticker] = row
    return [closest[ticker] for ticker in sorted(closest)]


def _warning_candidates(ok_rows: list[dict[str, Any]], warned_today: dict[str, datetime]) -> list[dict[str, Any]]:
    candidates = {str(row["ticker"]): dict(row) for row in _stop_proximity_candidates(ok_rows, warned_today)}
    for row in candidates.values():
        row["warning_details"] = (
            f"残り{row['distance_to_stop_pct']:.1f}% current={row['current_price']} stop={row['stop_price']}"
        )
    for row in ok_rows:
        ticker = str(row["ticker"])
        change = row.get("return_20d_pct")
        if row.get("triggered") is True or ticker in warned_today:
            continue
        if change is None or not is_finite_number(change) or change < OVEREXTENDED_RETURN_20D_PCT:
            continue
        # Multiple positions of the same ticker share one market return and one warning.
        warning = candidates.setdefault(ticker, {**row, "warning_details": ""})
        if "過熱" not in warning["warning_details"]:
            prefix = warning["warning_details"]
            warning["warning_details"] = (prefix + " / " if prefix else "") + f"過熱: 20日で +{change:.1f}%"
    return [candidates[ticker] for ticker in sorted(candidates)]


def _carry_warning_state(
    rows: list[dict[str, Any]],
    previous_by_key: dict[tuple[str, str], dict[str, Any]],
    warned_today: dict[str, datetime],
    warned_now: dict[str, str],
) -> None:
    """Set ``last_warned_at`` on every row, per ticker.

    The sheet is rewritten from this run's rows only, so the "already warned today" fact must be copied
    onto whichever rows exist now (including new, stale and error rows); otherwise replacing a position
    would erase it and the next run would warn the same ticker again.
    """
    for row in rows:
        ticker = str(row.get("ticker") or "").strip()
        key = _position_key(row)
        previous = previous_by_key.get(key) if key is not None else None
        if ticker in warned_now:
            row["last_warned_at"] = warned_now[ticker]
        elif ticker in warned_today:
            row["last_warned_at"] = warned_today[ticker].isoformat()
        else:
            row["last_warned_at"] = previous.get("last_warned_at", "") if previous else ""


def is_in_session(calendar: Any, when: datetime) -> bool:
    minute = when.replace(second=0, microsecond=0)
    if bool(calendar.is_open_on_minute(minute, ignore_breaks=False)):
        return True
    session = when.date().isoformat()
    if not bool(calendar.is_session(session)):
        return False
    close: datetime = calendar.session_close(session).to_pydatetime().astimezone(JST)
    return timedelta(0) <= when - close <= timedelta(minutes=CLOSE_GRACE_MINUTES)


@shared_spreadsheet()
@shared_split_history_frames()
def run(*, dry_run: bool, evaluated_at: datetime | None = None) -> int:
    assert_production_writer()
    webhook = os.getenv("SLACK_WEBHOOK_URL", "")
    if not dry_run and not webhook:
        raise RuntimeError("SLACK_WEBHOOK_URL is required unless --dry-run is used")
    current = evaluated_at or datetime.now(JST)
    if current.tzinfo is None:
        raise ValueError("evaluated_at must include a timezone")
    current = current.astimezone(JST)

    previous_rows = _private_call(read_status)
    previous_by_key = _unique_rows(previous_rows, "status")
    warned_today = _warned_today(previous_rows, current.date())
    holdings = _private_call(read_holdings)
    _unique_rows(holdings, "holdings")
    if not holdings:
        _private_call(write_status, [])
        print("position monitor complete: holdings=0")
        return 0
    calendar = xcals.get_calendar(TSE_CALENDAR)
    if not bool(calendar.is_session(current.date().isoformat())):
        print(f"position monitor skipped: non-TSE-session date={current.date().isoformat()}")
        return 0
    in_market_window = is_in_session(calendar, current)

    history_starts: dict[str, str] = {}
    for holding in holdings:
        try:
            candidate_ticker = str(holding.get("ticker") or "").strip()
            candidate_date = date.fromisoformat(str(holding.get("entry_date", "")))
            candidate_stop = holding.get("trailing_stop_pct", "")
            candidate_stop = DEFAULT_TRAILING_STOP_PCT if candidate_stop in (None, "") else candidate_stop
            if (not candidate_ticker or candidate_date > current.date()
                    or not bool(calendar.is_session(candidate_date.isoformat()))):
                continue
            _number(holding.get("entry_price", ""), "entry_price")
            if _number(candidate_stop, "trailing_stop_pct") >= 100:
                continue
        except (TypeError, ValueError):
            continue
        history_starts[candidate_ticker] = min(
            history_starts.get(candidate_ticker, candidate_date.isoformat()), candidate_date.isoformat(),
        )
    configure_split_history_sharing(history_starts)
    today_cache: dict[str, Any] = {}
    today_failure: dict[str, str | None] = {}  # the safe category of why a ticker's current bars are missing

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

            history = _private_call(fetch_split_adjusted_history, ticker, purchase_date.isoformat(), entry_price)
            recovered = _private_call(_recover_pending, ticker, purchase_date, history, stop_pct, previous, calendar, current)
            if recovered is not None:
                rows.append(recovered)
                if not recovered.get("last_notified_at"):
                    notifications.append(recovered)
                continue
            if ticker not in today_cache:
                try:
                    today_cache[ticker] = _private_call(fetch_today_bars, ticker)
                except Exception as exc:  # noqa: BLE001 - cache the same acquisition failure for this ticker
                    today_cache[ticker] = exc
                today_failure[ticker] = latest_one_minute_failure()
            cached_bars = today_cache[ticker]
            if isinstance(cached_bars, Exception):
                raise cached_bars
            bars = None if cached_bars is None else cached_bars.copy(deep=True)
            daily = _daily_reference(history, current.date())
            if bars is not None and daily is not None:
                bars.attrs["daily_bar"] = daily
            quote = None if bars is None else _private_call(build_today_quote, bars)
            if bars is None or quote is None:
                failed = _failure_row(
                    ticker=ticker,
                    entry_date=raw_date,
                    entry_price=raw_price,
                    trailing_stop_pct=stop_pct,
                    status="stale",
                    error="current quote is missing or invalid"
                    + (f" ({today_failure[ticker]})" if bars is None and today_failure.get(ticker) else ""),
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
            close = calendar.session_close(current.date().isoformat()).to_pydatetime().astimezone(JST)
            if not status.triggered and current >= close and datetime.fromisoformat(status.as_of_at) < close:
                result.update(status="incomplete", error="session end is not yet confirmed")
            was_triggered = _stored_triggered(previous)
            if previous and was_triggered:
                result["triggered"] = True
                result["exit_reason"] = previous.get("exit_reason", status.exit_reason)
            if result["triggered"]:
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
        except IncompleteQuoteError as exc:
            failed = _failure_row(
                ticker=ticker, entry_date=raw_date, entry_price=raw_price, trailing_stop_pct=stop_value,
                status="incomplete", error=str(exc),
            )
            _preserve_previous_state(failed, previous)
            rows.append(failed)
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
            print(f"position monitor failure: stage=holding row={row_number} {safe_error_details(exc)}")
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

    ok_rows = [row for row in rows if row["status"] in ("ok", "recovered")]
    stale_rows = [row for row in rows if row["status"] in ("stale", "incomplete")]
    error_rows = [row for row in rows if row["status"] == "error"]
    triggered = [row for row in ok_rows if row.get("triggered") is True]
    if not ok_rows:
        _carry_warning_state(rows, previous_by_key, warned_today, {})
        _private_call(write_status, rows)
        raise RuntimeError("position monitor failed: no holdings had a usable current quote")

    slack_error: Exception | None = None
    if not dry_run and notifications:
        details = "\n".join(
            f"• {row['ticker']}: "
            + ("過去の未評価区間の接触回収 " if row["status"] == "recovered" else "現在の接触 ")
            + f"{row['exit_reason']} at={row['triggered_at']} current={row['current_price']} stop={row['stop_price']}"
            for row in notifications
        )
        try:
            _private_call(_post_slack,
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
            _private_call(_post_slack, webhook, "[Position Monitor警告] 一部銘柄を評価できませんでした。\n" + details)
        except Exception as exc:  # noqa: BLE001 - persist status before failing the workflow
            slack_error = slack_error or exc

    warned_now: dict[str, str] = {}
    warnings = _warning_candidates(ok_rows, warned_today)
    if not dry_run and warnings:
        details = "\n".join(
            f"• {row['ticker']}: {row['warning_details']}"
            for row in warnings
        )
        try:
            _private_call(_post_slack,
                webhook,
                f"[検証用アラート] stop まで残り{WARNING_DISTANCE_PCT:g}%以内・過熱の注意喚起。"
                "確定した売買判断ではありません。\n" + details,
            )
            warned_now = {str(row["ticker"]): current.isoformat() for row in warnings}
        except Exception as exc:  # noqa: BLE001 - not marking them warned makes the next run retry
            slack_error = slack_error or exc

    _carry_warning_state(rows, previous_by_key, warned_today, warned_now)
    _private_call(write_status, rows)
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
    try:
        return run(dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001 - publish only a safe stage for the separate failure job
        status = getattr(getattr(exc, "response", None), "status_code", None)
        stage = str(getattr(exc, "monitor_stage", "monitor"))
        if status in (401, 403) or type(exc).__name__ == "RefreshError" or str(exc).startswith("GOOGLE_"):
            stage = "authentication"
        if output_path := os.getenv("GITHUB_OUTPUT"):
            with Path(output_path).open("a", encoding="utf-8") as output:
                output.write(f"failure_stage={stage}\n")
        print(f"position monitor failed: stage={stage} {safe_error_details(exc)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
