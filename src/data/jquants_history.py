"""Resumable local cache of J-Quants daily data for the historical backtest.

One gzip-JSON file per day and kind under ``cache_dir``::

    bars/YYYY-MM-DD.json.gz    all listed issues' daily bars for that session
    master/YYYY-MM-DD.json.gz  listed-issue master as of that day
    fins/YYYY-MM-DD.json.gz    every financial summary disclosed that calendar day

Files are written atomically and an existing file is never fetched again, so an
interrupted run resumes where it stopped. The cache holds third-party data and must
stay out of git (``.data/`` is gitignored).
"""

from __future__ import annotations

import gzip
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Protocol

import exchange_calendars as xcals
import pandas as pd
import requests

from src.data.market_calendar import TSE_CALENDAR

KINDS = ("bars", "master", "fins")
FREE_PLAN_DELAY_DAYS = 84
EDGE_MARGIN_DAYS = 7
NON_MASTER_FILE = "non_master_codes.json"


class HistoryFetchStopped(RuntimeError):
    """A 4xx response ended the run. Cached days are kept; adjust the range and re-run."""


class HistoryClient(Protocol):
    def daily_bars(self, date: str) -> list[dict[str, Any]]: ...

    def listed_issues(self, date: str | None = None) -> list[dict[str, Any]]: ...

    def financial_summary_by_date(self, date: str) -> list[dict[str, Any]]: ...


def default_fetch_range(today: date) -> tuple[date, date]:
    """Free plan window (2 years back .. 12 weeks back) shrunk by a margin at both ends.

    The single definition used by both the CLI and the fetcher.
    """
    start = (pd.Timestamp(today) - pd.DateOffset(years=2)).date() + timedelta(days=EDGE_MARGIN_DAYS)
    end = today - timedelta(days=FREE_PLAN_DELAY_DAYS + EDGE_MARGIN_DAYS)
    return start, end


def _path(cache_dir: Path, kind: str, day: str) -> Path:
    return cache_dir / kind / f"{day}.json.gz"


def read_day(cache_dir: Path, kind: str, day: str) -> list[dict[str, Any]]:
    with gzip.open(_path(cache_dir, kind, day), "rt", encoding="utf-8") as handle:
        rows = json.load(handle)
    if not isinstance(rows, list):
        raise TypeError(f"cached {kind}/{day} must contain a list")
    return rows


def _write_day(cache_dir: Path, kind: str, day: str, rows: list[dict[str, Any]]) -> None:
    path = _path(cache_dir, kind, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


@dataclass(frozen=True)
class HistoryCache:
    cache_dir: Path

    def days(self, kind: str) -> list[str]:
        folder = self.cache_dir / kind
        if not folder.exists():
            return []
        return sorted(path.name.removesuffix(".json.gz") for path in folder.glob("????-??-??.json.gz"))

    def read(self, kind: str, day: str) -> list[dict[str, Any]]:
        return read_day(self.cache_dir, kind, day)

    def non_master_codes(self) -> set[str]:
        return _read_non_master(self.cache_dir)


def load_cache(cache_dir: Path) -> HistoryCache:
    return HistoryCache(Path(cache_dir))


def _read_non_master(cache_dir: Path) -> set[str]:
    path = cache_dir / NON_MASTER_FILE
    if not path.exists():
        return set()
    return {str(code) for code in json.loads(path.read_text(encoding="utf-8"))}


def _write_non_master(cache_dir: Path, codes: set[str]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache_dir / f"{NON_MASTER_FILE}.tmp"
    tmp.write_text(json.dumps(sorted(codes)), encoding="utf-8")
    os.replace(tmp, cache_dir / NON_MASTER_FILE)


def _stop_message(kind: str, day: str, exc: requests.HTTPError) -> str:
    response = exc.response
    status = getattr(response, "status_code", "unknown")
    detail = ""
    try:
        body = response.json() if response is not None else {}
        detail = str(body.get("message", "")) if isinstance(body, dict) else ""
    except (ValueError, AttributeError):
        pass
    return f"J-Quants returned HTTP {status} for {kind} {day}: {detail or 'no message'}"


def _call(fetch: Callable[[str], list[dict[str, Any]]], kind: str, day: str) -> list[dict[str, Any]]:
    """Run one request. Every 4xx stops the run: 400 is bad parameters and 403 can also mean
    an invalid key or plan permission, so the status alone cannot say "out of range".
    429 (after the client's own retries) and 5xx propagate unchanged."""
    try:
        return fetch(day)
    except requests.HTTPError as exc:
        status = getattr(exc.response, "status_code", None)
        if isinstance(status, int) and 400 <= status < 500 and status != 429:
            raise HistoryFetchStopped(_stop_message(kind, day, exc)) from exc
        raise


def tse_sessions(start: date, end: date) -> list[str]:
    calendar = xcals.get_calendar(TSE_CALENDAR)
    return [str(session.date()) for session in calendar.sessions_in_range(start.isoformat(), end.isoformat())]


def monthly_master_days(sessions: list[str]) -> list[str]:
    """First in-range session of every month, so a master exists on or before every session."""
    seen: set[str] = set()
    result: list[str] = []
    for day in sessions:
        month = day[:7]
        if month not in seen:
            seen.add(month)
            result.append(day)
    return result


def _codes(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("Code") or "") for row in rows if row.get("Code")}


def fetch_range(
    client: HistoryClient,
    start: date,
    end: date,
    cache_dir: Path,
    *,
    kinds: tuple[str, ...] = KINDS,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Fetch and cache bars, master and fins for ``[start, end]``; skip cached days."""
    unknown = set(kinds) - set(KINDS)
    if unknown:
        raise ValueError(f"unknown kinds: {sorted(unknown)}")
    cache_dir = Path(cache_dir)
    sessions = tse_sessions(start, end)
    fetched = dict.fromkeys(KINDS, 0)
    extra_master_fetches = 0

    if "bars" in kinds:
        for day in sessions:
            if not _path(cache_dir, "bars", day).exists():
                _write_day(cache_dir, "bars", day, _call(client.daily_bars, "bars", day))
                fetched["bars"] += 1
                log(f"bars {day} fetched")

    if "master" in kinds:
        for day in monthly_master_days(sessions):
            if not _path(cache_dir, "master", day).exists():
                _write_day(cache_dir, "master", day, _call(client.listed_issues, "master", day))
                fetched["master"] += 1
                log(f"master {day} fetched")
        extra_master_fetches = _fetch_extra_masters(client, sessions, cache_dir, log)
        fetched["master"] += extra_master_fetches

    if "fins" in kinds:
        day_cursor = start
        while day_cursor <= end:
            day = day_cursor.isoformat()
            if not _path(cache_dir, "fins", day).exists():
                _write_day(cache_dir, "fins", day, _call(client.financial_summary_by_date, "fins", day))
                fetched["fins"] += 1
                log(f"fins {day} fetched")
            day_cursor += timedelta(days=1)

    cache = load_cache(cache_dir)
    bars_days = cache.days("bars")
    return {
        "fetched": fetched,
        "extra_master_fetches": extra_master_fetches,
        "first_bars_date": bars_days[0] if bars_days else None,
        "last_bars_date": bars_days[-1] if bars_days else None,
    }


def _fetch_extra_masters(
    client: HistoryClient,
    sessions: list[str],
    cache_dir: Path,
    log: Callable[[str], None],
) -> int:
    """Add a master for any day whose bars show a code unknown to the latest earlier master.

    Each such code triggers at most one extra fetch; a code that still is not in master
    afterwards (ETFs, REITs, ...) is remembered and never triggers another.
    """
    cache = load_cache(cache_dir)
    master_days = [day for day in cache.days("master")]
    codes_by_master = {day: _codes(cache.read("master", day)) for day in master_days}
    non_master = cache.non_master_codes()
    extra = 0
    for day in sessions:
        if not _path(cache_dir, "bars", day).exists():
            continue
        earlier = [m for m in sorted(codes_by_master) if m <= day]
        if not earlier:
            continue
        missing = {code for code in _codes(read_day(cache_dir, "bars", day)) if code not in codes_by_master[earlier[-1]]}
        missing -= non_master
        if not missing:
            continue
        if day not in codes_by_master:
            if not _path(cache_dir, "master", day).exists():
                _write_day(cache_dir, "master", day, _call(client.listed_issues, "master", day))
            codes_by_master[day] = _codes(read_day(cache_dir, "master", day))
            extra += 1
            log(f"master {day} fetched (new codes in bars: {len(missing)})")
        still_missing = missing - codes_by_master[day]
        if still_missing:
            non_master |= still_missing
            _write_non_master(cache_dir, non_master)
    return extra


def probe(client: HistoryClient, start: date, end: date) -> dict[str, Any]:
    """Request the first and last session's bars once each, writing nothing."""
    sessions = tse_sessions(start, end)
    if not sessions:
        raise ValueError("no TSE sessions in the requested range")
    result: dict[str, Any] = {}
    for label, day in (("first", sessions[0]), ("last", sessions[-1])):
        rows = _call(client.daily_bars, "bars", day)
        result[label] = {"date": day, "rows": len(rows)}
    return result
