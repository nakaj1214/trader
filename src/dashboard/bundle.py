"""Build the encrypted data bundle that the static dashboard decrypts in the viewer's browser.

The repository is public, so the bundle is encrypted like the snapshots, but with its own viewer password:
PBKDF2-SHA256 derives an AES-256-GCM key, which the browser's Web Crypto API can derive and use the same way.
Only the encrypted bundle is published; nothing here prints a ticker or a company name.
"""

from __future__ import annotations

import base64
import gzip
import json
import math
import os
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.data.snapshot_crypto import decrypt_json
from src.data.validation import is_finite_number

BUNDLE_FORMAT = "trader-dashboard-v1"
BUNDLE_SCHEMA_VERSION = 1
KDF_ITERATIONS = 600_000
MIN_PASSWORD_LENGTH = 12  # the bundle is public, so a short password could be guessed offline
HISTORY_SNAPSHOTS = 60  # market days of snapshots behind the history and the past-signal results
CHART_SESSIONS = 120  # daily closes kept per ticker for the charts
SIGNAL_CLASSES = ("EARLY_CANDIDATE", "WATCH")
CHARTED_CLASSES = ("EARLY_CANDIDATE", "WATCH", "OVEREXTENDED")
BENCHMARK_TICKER = "1306.T"  # TOPIX ETF, the same benchmark as forward validation
_SNAPSHOT_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.enc$")

_CANDIDATE_FIELDS = (
    "ticker", "company_name", "market", "classification", "sector33_name", "current_price",
    "return_5d_pct", "return_20d_pct", "return_60d_pct", "volume_ratio_20d", "near_52w_high",
    "avg_turnover_20d_jpy", "pre_score",
)
_FEATURE_FIELDS = (
    "revenue_growth_yoy_pct", "operating_profit_growth_yoy_pct", "operating_margin_change_pctpt",
    "turned_profitable", "upward_revision_pct", "negative_operating_cashflow", "distance_from_period_high_pct",
    "max_daily_return_20d_pct", "up_day_ratio_20d", "daily_volatility_20d_pct", "disclosure_age_days",
    "relative_return_20d_vs_sector_pct",
)


def _clean(value: Any) -> Any:
    """A JSON-safe scalar: bools and strings as they are, finite numbers rounded, anything else ``None``."""
    if isinstance(value, (bool, str)):
        return value
    if is_finite_number(value):
        return round(float(value), 4)
    return None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def load_snapshots(snapshot_dir: Path, secret: str, limit: int = HISTORY_SNAPSHOTS) -> tuple[list[dict[str, Any]], int]:
    """The newest ``limit`` snapshot files that decrypt to their own market day, oldest first, and the skip count."""
    files = sorted(path for path in snapshot_dir.glob("*.enc") if _SNAPSHOT_NAME.match(path.name))
    reports: list[dict[str, Any]] = []
    skipped = 0
    for path in files[-limit:]:
        try:
            report = decrypt_json(path.read_text(encoding="utf-8"), secret)
        except (OSError, ValueError, TypeError):
            skipped += 1
            continue
        if str(report.get("latest_price_date")) != path.stem or not isinstance(report.get("candidates"), list):
            skipped += 1
            continue
        reports.append(report)
    return reports, skipped


def _candidates(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in report["candidates"] if isinstance(c, dict) and isinstance(c.get("ticker"), str)]


def _score(candidate: dict[str, Any]) -> Any:
    return _clean(candidate.get("live_normalized_score", candidate.get("score")))


def _histories(reports: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Per ticker, its classification on each stored day it was among the deeply evaluated names."""
    rows: dict[str, list[dict[str, Any]]] = {}
    for report in reports:
        day = str(report["latest_price_date"])
        for candidate in _candidates(report):
            rows.setdefault(candidate["ticker"], []).append(
                {"date": day, "classification": str(candidate.get("classification")), "score": _score(candidate)}
            )
    return rows


def _streak(history: list[dict[str, Any]], days: list[str]) -> int:
    """How many of the latest stored days in a row (up to the newest) the ticker was EARLY_CANDIDATE or WATCH."""
    signalled = {row["date"] for row in history if row["classification"] in SIGNAL_CLASSES}
    count = 0
    for day in reversed(days):
        if day not in signalled:
            break
        count += 1
    return count


def candidate_view(candidate: dict[str, Any], history: list[dict[str, Any]], days: list[str]) -> dict[str, Any]:
    view: dict[str, Any] = {key: _clean(candidate.get(key)) for key in _CANDIDATE_FIELDS}
    view["score"] = _score(candidate)
    features = _mapping(candidate.get("features"))
    view["features"] = {key: _clean(features.get(key)) for key in _FEATURE_FIELDS}
    details = _mapping(candidate.get("score_details"))
    view["score_details"] = {str(key): _clean(value) for key, value in details.items() if is_finite_number(value)}
    reasons = candidate.get("reasons")
    view["reasons"] = [str(reason) for reason in reasons] if isinstance(reasons, list) else []
    view["history"] = history
    view["streak"] = _streak(history, days)
    return view


def _daily(frame: pd.DataFrame | None) -> pd.DataFrame | None:
    """Open/Close/Volume on a tz-naive, sorted, de-duplicated date index; ``None`` without usable columns."""
    if frame is None or frame.empty or not {"Open", "Close"}.issubset(frame.columns):
        return None
    index = pd.DatetimeIndex(frame.index)
    if index.tz is not None:
        index = index.tz_localize(None)
    columns = [column for column in ("Open", "Close", "Volume") if column in frame.columns]
    daily = frame[columns].apply(pd.to_numeric, errors="coerce").set_axis(index.normalize())
    return daily[~daily.index.duplicated(keep="last")].sort_index()


def _positive(series: pd.Series) -> pd.Series:
    return series[series.map(lambda value: math.isfinite(value) and value > 0)]


def signal_performance(
    frame: pd.DataFrame | None, signal_date: str, benchmark: pd.DataFrame | None
) -> dict[str, Any]:
    """Gross price change from the next session's open after the signal to the latest close (no costs or tax).

    ``waiting`` means no session with an open has traded since the signal yet; ``no_prices`` means none were fetched.
    """
    daily = _daily(frame)
    if daily is None:
        return {"status": "no_prices"}
    after = daily[daily.index > pd.Timestamp(signal_date)]
    opens = _positive(after["Open"])
    if opens.empty:
        return {"status": "waiting"}
    entry_day = opens.index[0]
    entry = float(opens.iloc[0])
    closes = _positive(after["Close"][after.index >= entry_day])
    if closes.empty:
        return {"status": "waiting"}
    last_day = closes.index[-1]
    result: dict[str, Any] = {
        "status": "ok",
        "entry_date": str(entry_day.date()),
        "entry_price": round(entry, 4),
        "last_date": str(last_day.date()),
        "last_price": round(float(closes.iloc[-1]), 4),
        "sessions": len(closes),
        "return_pct": round((float(closes.iloc[-1]) / entry - 1.0) * 100.0, 4),
        "max_return_pct": round((float(closes.max()) / entry - 1.0) * 100.0, 4),
        "min_return_pct": round((float(closes.min()) / entry - 1.0) * 100.0, 4),
        "benchmark_return_pct": None,
    }
    bench = _daily(benchmark)
    if bench is not None and entry_day in bench.index and last_day in bench.index:
        bench_open, bench_close = float(bench.at[entry_day, "Open"]), float(bench.at[last_day, "Close"])
        if all(math.isfinite(value) and value > 0 for value in (bench_open, bench_close)):
            result["benchmark_return_pct"] = round((bench_close / bench_open - 1.0) * 100.0, 4)
    return result


def chart_series(frame: pd.DataFrame | None, sessions: int = CHART_SESSIONS) -> list[list[Any]] | None:
    """The last ``sessions`` valid closes as ``[date, close, volume]`` rows for the charts."""
    daily = _daily(frame)
    if daily is None:
        return None
    closes = _positive(daily["Close"]).tail(sessions)
    if closes.empty:
        return None
    volumes = daily["Volume"] if "Volume" in daily.columns else pd.Series(dtype=float)
    rows: list[list[Any]] = []
    for day, close in closes.items():
        volume = volumes.get(day)
        rows.append([
            str(pd.Timestamp(day).date()),
            round(float(close), 2),
            int(volume) if volume is not None and math.isfinite(volume) and volume >= 0 else None,
        ])
    return rows


def _first_signals(histories: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """Per ticker that was EARLY_CANDIDATE or WATCH at least once: its first such day and how often it was."""
    signals: dict[str, dict[str, Any]] = {}
    for ticker, history in histories.items():
        flagged = [row for row in history if row["classification"] in SIGNAL_CLASSES]
        if flagged:
            signals[ticker] = {
                "first_signal_date": flagged[0]["date"],
                "first_classification": flagged[0]["classification"],
                "ever_early": any(row["classification"] == "EARLY_CANDIDATE" for row in flagged),
                "signal_days": len(flagged),
                "last_signal_date": flagged[-1]["date"],
            }
    return signals


def chart_tickers(reports: list[dict[str, Any]]) -> list[str]:
    """Tickers that need prices: every past EARLY/WATCH signal and the newest day's charted classes."""
    if not reports:
        return []
    tickers = set(_first_signals(_histories(reports)))
    tickers |= {c["ticker"] for c in _candidates(reports[-1]) if c.get("classification") in CHARTED_CLASSES}
    return sorted(tickers)


def _count_classes(report: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in _candidates(report):
        key = str(candidate.get("classification"))
        counts[key] = counts.get(key, 0) + 1
    return counts


def build_bundle(
    reports: list[dict[str, Any]],
    prices: dict[str, pd.DataFrame],
    *,
    generated_at: str,
    skipped_snapshots: int = 0,
) -> dict[str, Any]:
    """Everything the dashboard shows, from the stored snapshots (oldest first) and fetched daily prices."""
    if not reports:
        raise ValueError("no readable snapshot")
    latest = reports[-1]
    days = [str(report["latest_price_date"]) for report in reports]
    histories = _histories(reports)
    benchmark = prices.get(BENCHMARK_TICKER)
    policy = _mapping(latest.get("data_policy"))
    parameters = _mapping(latest.get("scan_parameters"))
    names: dict[str, dict[str, Any]] = {}
    for report in reports:  # the newest name, market and sector seen for each ticker
        for candidate in _candidates(report):
            names[candidate["ticker"]] = {
                key: _clean(candidate.get(key)) for key in ("company_name", "market", "sector33_name")
            }

    signals = []
    for ticker, signal in sorted(_first_signals(histories).items(), key=lambda item: item[1]["first_signal_date"]):
        signals.append({
            "ticker": ticker,
            **names[ticker],
            **signal,
            "history": histories[ticker],
            "performance": signal_performance(prices.get(ticker), signal["first_signal_date"], benchmark),
        })

    wanted = set(chart_tickers(reports))
    series = {ticker: chart_series(prices.get(ticker)) for ticker in sorted(wanted)}
    return {
        "format": BUNDLE_FORMAT,
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "latest_price_date": days[-1],
        "strategy_version": _clean(latest.get("strategy_version")),
        "data_policy": {key: _clean(policy.get(key)) for key in ("jquants_plan", "jquants_data_delay_weeks")},
        "thresholds": {key: _clean(parameters.get(key)) for key in ("early_candidate_score", "watch_score")},
        "latest": {
            "date": days[-1],
            "universe_count": _clean(latest.get("universe_count")),
            "liquid_candidate_count": _clean(latest.get("liquid_candidate_count")),
            "counts": _count_classes(latest),
            "candidates": [
                candidate_view(candidate, histories[candidate["ticker"]], days) for candidate in _candidates(latest)
            ],
        },
        "days": [
            {
                "date": str(report["latest_price_date"]),
                "counts": _count_classes(report),
                "universe_count": _clean(report.get("universe_count")),
                "liquid_candidate_count": _clean(report.get("liquid_candidate_count")),
            }
            for report in reports
        ],
        "signals": signals,
        "prices": {ticker: rows for ticker, rows in series.items() if rows},
        "benchmark": {"ticker": BENCHMARK_TICKER, "series": chart_series(benchmark)},
        "diagnostics": {
            "snapshots": len(reports),
            "skipped_snapshots": skipped_snapshots,
            "missing_prices": sum(1 for rows in series.values() if not rows),
        },
    }


def _derive_key(password: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    # NFC on both sides, so a phone keyboard's composed characters match the stored secret.
    return kdf.derive(unicodedata.normalize("NFC", password).encode("utf-8"))


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def encrypt_bundle(
    bundle: dict[str, Any],
    password: str,
    *,
    iterations: int = KDF_ITERATIONS,
    salt: bytes | None = None,
    nonce: bytes | None = None,
) -> str:
    """Gzip and encrypt the bundle into a JSON envelope (AES-256-GCM, key from PBKDF2-SHA256)."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"the dashboard password needs at least {MIN_PASSWORD_LENGTH} characters")
    salt = salt if salt is not None else os.urandom(16)
    nonce = nonce if nonce is not None else os.urandom(12)
    raw = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    sealed = AESGCM(_derive_key(password, salt, iterations)).encrypt(
        nonce, gzip.compress(raw, mtime=0), BUNDLE_FORMAT.encode("ascii")
    )
    envelope = {
        "format": BUNDLE_FORMAT,
        "kdf": {"name": "PBKDF2", "hash": "SHA-256", "iterations": iterations, "salt": _b64(salt)},
        "cipher": {"name": "AES-GCM", "iv": _b64(nonce), "additional_data": BUNDLE_FORMAT},
        "compression": "gzip",
        "data": _b64(sealed),
    }
    return json.dumps(envelope, separators=(",", ":")) + "\n"


def decrypt_bundle(text: str, password: str) -> dict[str, Any]:
    """The inverse of :func:`encrypt_bundle` (the browser does the same with Web Crypto)."""
    envelope = json.loads(text)
    if not isinstance(envelope, dict) or envelope.get("format") != BUNDLE_FORMAT:
        raise ValueError("unsupported dashboard bundle format")
    kdf, cipher = envelope["kdf"], envelope["cipher"]
    key = _derive_key(password, base64.b64decode(kdf["salt"]), int(kdf["iterations"]))
    raw = AESGCM(key).decrypt(
        base64.b64decode(cipher["iv"]), base64.b64decode(envelope["data"]), BUNDLE_FORMAT.encode("ascii")
    )
    bundle = json.loads(gzip.decompress(raw).decode("utf-8"))
    if not isinstance(bundle, dict):
        raise TypeError("the dashboard bundle must be a JSON object")
    return bundle


def tickers_with_benchmark(tickers: Iterable[str]) -> list[str]:
    return sorted(set(tickers) | {BENCHMARK_TICKER})
