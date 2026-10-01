"""Point-in-time reconstruction of the v3 scan from cached J-Quants history.

Everything a scan on day ``as_of`` may use is derived only from data dated on or
before ``as_of``:

* prices: split-adjusted with the factors up to ``as_of`` (never later splits),
* universe attributes: the latest master dated on or before ``as_of``,
* fundamentals: only disclosures that were available at the 16:40 JST scan time,
  either immediately (``disclosure``) or 12 weeks later (``free_12w``, today's Free plan).

The scoring itself is the live code (``select_and_evaluate``), not a copy.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from src.data.jquants_history import HistoryCache
from src.data.validation import is_finite_number
from src.evaluation.inflection_backtest import (
    BOOTSTRAP_SEED,
    cluster_bootstrap_ci,
    select_non_overlapping_trades,
    simulate_signals,
)
from src.evaluation.inflection_forward import BENCHMARK_TICKER, paired_benchmark_returns
from src.evaluation.inflection_portfolio import simulate_portfolio
from src.evaluation.inflection_recall import compute_tracked_pool_explosion_recall
from src.evaluation.inflection_report import (
    BENCHMARK_ROUND_TRIP_COST_PCT,
    PORTFOLIO_INITIAL_CAPITAL_JPY,
    PORTFOLIO_MAX_POSITIONS,
    PORTFOLIO_POSITION_SIZE_PCT,
    ROUND_TRIP_COST_PCT,
    _build_group_report,
    _summary_only,
)
from src.screening.inflection_live import (
    DEFAULT_CONTROL_SAMPLE_SIZE,
    JP_MARKET_CODES,
    REPORT_SCHEMA_VERSION,
    STRATEGY_VERSION,
    _ticker_from_code,
    select_and_evaluate,
)

JST = ZoneInfo("Asia/Tokyo")
SCAN_TIME = time(16, 40)
FREE_PLAN_LAG_DAYS = 84
LAGS = ("disclosure", "free_12w")
RAW_BAR_COLUMNS = ("O", "H", "L", "C", "Vo", "Va", "AdjFactor")
HISTORY_WINDOW = 252
MASTER_FIELDS = ("Code", "CoName", "Mkt", "MktNm", "S33", "S33Nm")
FINS_FIELDS = (
    "Code", "DiscDate", "DiscTime", "DiscNo", "DocType", "CurPerType", "CurFYEn", "Sales", "OP", "FOP", "CFO",
)


def _is_ordinary_code(code: object) -> bool:
    """Five-digit codes ending in 0 are ordinary shares (and ETFs); they map 1:1 to ``NNNN.T``."""
    text = str(code or "")
    return len(text) == 5 and text.endswith("0")


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TickerBars:
    frame: pd.DataFrame  # raw O/H/L/C/Vo/Va/AdjFactor, DatetimeIndex, rows with a close only
    cum: Any  # float array: product of AdjFactor over strictly later days, aligned with ``frame``


def _build_ticker_bars(day_rows: Iterable[tuple[str, list[dict[str, Any]]]]) -> dict[str, TickerBars]:
    pieces: list[pd.DataFrame] = []
    for day, rows in day_rows:
        kept = [row for row in rows if _is_ordinary_code(row.get("Code"))]
        if not kept:
            continue
        piece = pd.DataFrame.from_records(kept, columns=["Code", *RAW_BAR_COLUMNS])
        piece[list(RAW_BAR_COLUMNS)] = piece[list(RAW_BAR_COLUMNS)].apply(pd.to_numeric, errors="coerce")
        piece["Date"] = pd.Timestamp(day)
        pieces.append(piece)
    if not pieces:
        return {}
    everything = pd.concat(pieces, ignore_index=True).sort_values(["Code", "Date"], kind="stable")
    result: dict[str, TickerBars] = {}
    for code, group in everything.groupby("Code", sort=False):
        factor = group["AdjFactor"].fillna(1.0)
        # cum[i] = product of factor[j] for j > i
        cum = factor.iloc[::-1].cumprod().iloc[::-1].shift(-1, fill_value=1.0).to_numpy(dtype=float)
        has_close = group["C"].notna().to_numpy() & (group["C"].to_numpy(dtype=float) > 0)
        frame = group.loc[has_close, list(RAW_BAR_COLUMNS)].set_index(pd.DatetimeIndex(group.loc[has_close, "Date"]))
        if frame.empty:
            continue
        result[_ticker_from_code(str(code))] = TickerBars(frame=frame, cum=cum[has_close])
    return result


class BarPanel:
    def __init__(self, tickers: dict[str, TickerBars], sessions: list[str]) -> None:
        self._tickers = tickers
        self.sessions = sessions  # every cached trading day, ascending
        self._asof_cache: tuple[str, dict[str, pd.DataFrame]] | None = None

    @classmethod
    def from_rows(cls, rows_by_day: dict[str, list[dict[str, Any]]]) -> BarPanel:
        return cls(_build_ticker_bars(sorted(rows_by_day.items())), sorted(rows_by_day))

    @classmethod
    def from_cache(cls, cache: HistoryCache) -> BarPanel:
        days = cache.days("bars")
        return cls(_build_ticker_bars((day, cache.read("bars", day)) for day in days), days)

    def tickers(self) -> set[str]:
        return set(self._tickers)

    def split_tickers(self) -> list[str]:
        """Tickers with at least one adjustment event (a split or reverse split), sorted."""
        return sorted(
            ticker for ticker, bars in self._tickers.items() if (bars.frame["AdjFactor"].fillna(1.0) != 1.0).any()
        )

    def last_date(self) -> str | None:
        dates = [bars.frame.index[-1] for bars in self._tickers.values()]
        return str(max(dates).date()) if dates else None

    def frames_as_of(self, as_of: str) -> dict[str, pd.DataFrame]:
        """Live-shaped price frames (Close/Volume/Turnover) for tickers with a bar on ``as_of``.

        Close is split-adjusted with only the factors up to ``as_of``, so a split after
        ``as_of`` cannot change anything computed for ``as_of``. Memoized for the last day.
        """
        if self._asof_cache is not None and self._asof_cache[0] == as_of:
            return self._asof_cache[1]
        stamp = pd.Timestamp(as_of)
        frames: dict[str, pd.DataFrame] = {}
        for ticker, bars in self._tickers.items():
            end = int(bars.frame.index.searchsorted(stamp, side="right"))
            if end == 0 or bars.frame.index[end - 1] != stamp:
                continue
            window = slice(max(0, end - HISTORY_WINDOW), end)
            sliced = bars.frame.iloc[window]
            factor = bars.cum[window] / bars.cum[end - 1]
            frames[ticker] = pd.DataFrame(
                {
                    "Close": sliced["C"].to_numpy(dtype=float) * factor,
                    "Volume": sliced["Vo"].to_numpy(dtype=float),
                    "Turnover": sliced["Va"].to_numpy(dtype=float),
                },
                index=sliced.index,
            )
        self._asof_cache = (as_of, frames)
        return frames

    def evaluation_histories(self) -> dict[str, pd.DataFrame]:
        """Open/High/Low/Close on one split-adjusted basis for the whole period (for trade returns)."""
        result: dict[str, pd.DataFrame] = {}
        for ticker, bars in self._tickers.items():
            frame = pd.DataFrame(
                {
                    "Open": bars.frame["O"].to_numpy(dtype=float) * bars.cum,
                    "High": bars.frame["H"].to_numpy(dtype=float) * bars.cum,
                    "Low": bars.frame["L"].to_numpy(dtype=float) * bars.cum,
                    "Close": bars.frame["C"].to_numpy(dtype=float) * bars.cum,
                },
                index=bars.frame.index,
            )
            # Trailing-stop simulation needs complete OHLC, so drop the rare rows missing any of it.
            result[ticker] = frame.dropna()
        return result


# ---------------------------------------------------------------------------
# Master (universe attributes)
# ---------------------------------------------------------------------------


class MasterHistory:
    def __init__(self, masters: dict[str, list[dict[str, Any]]]) -> None:
        self._days = sorted(masters)
        self._meta: dict[str, dict[str, dict[str, Any]]] = {}
        for day, rows in masters.items():
            meta: dict[str, dict[str, Any]] = {}
            for row in rows:
                code = str(row.get("Code") or "")
                if str(row.get("Mkt") or "") not in JP_MARKET_CODES or not _is_ordinary_code(code):
                    continue
                meta[_ticker_from_code(code)] = {key: row.get(key) for key in MASTER_FIELDS}
            self._meta[day] = meta

    @classmethod
    def from_cache(cls, cache: HistoryCache) -> MasterHistory:
        return cls({day: cache.read("master", day) for day in cache.days("master")})

    def as_of(self, day: str) -> tuple[str, dict[str, dict[str, Any]]]:
        """The latest master dated on or before ``day`` (never a later one)."""
        earlier = [candidate for candidate in self._days if candidate <= day]
        if not earlier:
            raise ValueError(f"no master on or before {day}")
        return earlier[-1], self._meta[earlier[-1]]


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FinRow:
    available_disclosure: datetime
    available_free: datetime
    row: dict[str, Any]


def _parse_disclosure(row: dict[str, Any]) -> tuple[datetime, datetime] | None:
    disc_date = str(row.get("DiscDate") or "").strip()
    try:
        day = date.fromisoformat(disc_date)
    except ValueError:
        return None
    raw_time = str(row.get("DiscTime") or "").strip()
    try:
        at = datetime.combine(day, time.fromisoformat(raw_time), tzinfo=JST) if raw_time else None
    except ValueError:
        at = None
    if at is None:  # unknown time: assume the end of the day so it never leaks into that day's scan
        at = datetime.combine(day, time(23, 59), tzinfo=JST)
    free = datetime.combine(day + timedelta(days=FREE_PLAN_LAG_DAYS), time(0, 0), tzinfo=JST)
    return at, free


class PointInTimeFinancials:
    """``financial_summary(code)`` restricted to rows available at the ``as_of`` 16:40 JST scan."""

    def __init__(self, rows_by_code: dict[str, list[_FinRow]], as_of: str, lag: str) -> None:
        if lag not in LAGS:
            raise ValueError(f"lag must be one of {LAGS}")
        self._rows = rows_by_code
        self._cutoff = datetime.combine(date.fromisoformat(as_of), SCAN_TIME, tzinfo=JST)
        self._lag = lag

    def financial_summary(self, code: str) -> list[dict[str, Any]]:
        selected = []
        for item in self._rows.get(code, []):
            available = item.available_disclosure if self._lag == "disclosure" else item.available_free
            if available <= self._cutoff:
                selected.append(item.row)
        return selected


class FinancialsStore:
    def __init__(self, rows: Iterable[dict[str, Any]]) -> None:
        self._rows_by_code: dict[str, list[_FinRow]] = {}
        self.skipped_rows = 0
        for raw in rows:
            parsed = _parse_disclosure(raw)
            code = str(raw.get("Code") or "")
            if parsed is None or not code:
                self.skipped_rows += 1
                continue
            row = {key: raw.get(key) for key in FINS_FIELDS}
            self._rows_by_code.setdefault(code, []).append(_FinRow(parsed[0], parsed[1], row))

    @classmethod
    def from_cache(cls, cache: HistoryCache) -> FinancialsStore:
        def rows() -> Iterable[dict[str, Any]]:
            for day in cache.days("fins"):
                yield from cache.read("fins", day)

        return cls(rows())

    def first_disclosure_date(self) -> str | None:
        dates = [item.available_disclosure.date() for items in self._rows_by_code.values() for item in items]
        return str(min(dates)) if dates else None

    def view(self, as_of: str, lag: str) -> PointInTimeFinancials:
        return PointInTimeFinancials(self._rows_by_code, as_of, lag)


# ---------------------------------------------------------------------------
# Reconstruction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoricalData:
    panel: BarPanel
    masters: MasterHistory
    fins: FinancialsStore

    @classmethod
    def from_cache(cls, cache: HistoryCache) -> HistoricalData:
        return cls(BarPanel.from_cache(cache), MasterHistory.from_cache(cache), FinancialsStore.from_cache(cache))


def reconstruct_scan(
    as_of: str,
    data: HistoricalData,
    *,
    lag: str,
    deep_candidates: int = 25,
    min_turnover_jpy: float = 100_000_000,
    control_sample_size: int = DEFAULT_CONTROL_SAMPLE_SIZE,
    fundamental_limitation: str | None = None,
) -> dict[str, Any]:
    """Re-run the v3 scan as it would have run on ``as_of`` with only then-available data."""
    if control_sample_size < 0:
        raise ValueError("control_sample_size must not be negative")
    master_day, ticker_meta = data.masters.as_of(as_of)
    prices = {ticker: frame for ticker, frame in data.panel.frames_as_of(as_of).items() if ticker in ticker_meta}
    limitation = fundamental_limitation or (
        "Historical reconstruction: fundamentals limited to disclosures available at the scan time "
        f"(lag={lag})"
    )
    selection = select_and_evaluate(
        prices,
        ticker_meta,
        data.fins.view(as_of, lag),
        seed_date=as_of,
        deep_candidates=deep_candidates,
        min_turnover_jpy=min_turnover_jpy,
        control_sample_size=control_sample_size,
        fundamental_limitation=limitation,
    )
    counts = Counter(candidate.classification for candidate in selection.candidates)
    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "mode": "historical",
        "fundamental_lag": lag,
        "master_date": master_day,
        "latest_price_date": as_of,
        "universe_count": len(ticker_meta),
        "price_data_count": len(prices),
        "technical_usable_count": len(selection.technical_usable_tickers),
        "liquid_candidate_count": selection.liquid_candidate_count,
        "deep_candidate_count": selection.deep_candidate_count,
        "classification_counts": dict(counts),
        "candidates": [candidate.as_dict() for candidate in selection.candidates],
        "control_sample_size": control_sample_size,
        "control_sample_seed": selection.control_seed,
        "control_sample": [candidate.as_dict() for candidate in selection.control_sample],
    }


# ---------------------------------------------------------------------------
# Signals, evaluation and the report
# ---------------------------------------------------------------------------

FINS_WARMUP_DAYS = 410 + FREE_PLAN_LAG_DAYS  # a year of YoY base + ~45d to report + the longest lag
DEFAULT_MIN_INDEPENDENT = 100
GROUPS = ("EARLY_CANDIDATE", "WATCH", "NONE", "CONTROL")
REPORT_NOTES = (
    "Evaluation only: the v3 thresholds and weights are used exactly as in production; no parameter was searched or tuned.",
    "Prices are split-adjusted only (J-Quants), while the live scan uses yfinance Adj Close (dividends included).",
    "Only ordinary-share codes (5th digit 0) are scanned, so preferred shares are not represented.",
    (
        "Universe attributes come from the latest master dated on or before each scan day; "
        "listings between month-start masters are covered by extra daily masters."
    ),
    (
        "Delisted names stay in the universe while they trade (no survivorship filter); "
        "their final return is whatever the cached prices show."
    ),
    "Many groups, horizons, stops and two lags are reported; do not over-interpret the best cell.",
    (
        "CONTROL is a date-seeded random draw from every liquid name; EARLY_CANDIDATE/WATCH/NONE are drawn "
        "from the momentum-ranked deep candidates only."
    ),
)


def default_signal_start(data: HistoricalData) -> str | None:
    """First scan day with 252 days of price history AND enough fundamentals history for both lags."""
    first_disclosure = data.fins.first_disclosure_date()
    if len(data.panel.sessions) < HISTORY_WINDOW or first_disclosure is None:
        return None
    history_ready = data.panel.sessions[HISTORY_WINDOW - 1]
    warmed_up = str(date.fromisoformat(first_disclosure) + timedelta(days=FINS_WARMUP_DAYS))
    return max(history_ready, warmed_up)


def signal_days(data: HistoricalData, start: str | None = None) -> list[str]:
    first = start or default_signal_start(data)
    if first is None:
        return []
    return [day for day in data.panel.sessions if day >= first]


def _signal_row(candidate: dict[str, Any], classification: str, day: str) -> dict[str, Any]:
    return {
        "ticker": candidate["ticker"],
        "signal_date": day,
        "date": day,
        "score": candidate["score"],
        "classification": classification,
        "market": candidate.get("market"),
        "avg_turnover_20d_jpy": candidate.get("avg_turnover_20d_jpy"),
    }


def collect_signals(
    data: HistoricalData,
    days: list[str],
    lags: tuple[str, ...] = LAGS,
    *,
    deep_candidates: int = 25,
    min_turnover_jpy: float = 100_000_000,
    control_sample_size: int = DEFAULT_CONTROL_SAMPLE_SIZE,
    log: Callable[[str], None] = print,
) -> dict[str, dict[str, Any]]:
    """Run the reconstruction for every day and lag. Price work is shared across lags per day."""
    collected: dict[str, dict[str, Any]] = {lag: {"signals": [], "yoy": {}} for lag in lags}
    for position, day in enumerate(days, start=1):
        for lag in lags:
            report = reconstruct_scan(
                day,
                data,
                lag=lag,
                deep_candidates=deep_candidates,
                min_turnover_jpy=min_turnover_jpy,
                control_sample_size=control_sample_size,
            )
            signals = collected[lag]["signals"]
            month = collected[lag]["yoy"].setdefault(day[:7], {"observations": 0, "with_yoy": 0})
            for candidate in report["candidates"]:
                signals.append(_signal_row(candidate, candidate["classification"], day))
            for candidate in report["control_sample"]:
                signals.append(_signal_row(candidate, "CONTROL", day))
            for candidate in [*report["candidates"], *report["control_sample"]]:
                month["observations"] += 1
                month["with_yoy"] += candidate["features"].get("revenue_growth_yoy_pct") is not None
        if position % 10 == 0 or position == len(days):
            log(f"reconstructed {position}/{len(days)} days (through {day})")
    for lag in lags:
        collected[lag]["yoy"] = {
            month: counts | {"ratio": round(counts["with_yoy"] / counts["observations"], 4) if counts["observations"] else None}
            for month, counts in sorted(collected[lag]["yoy"].items())
        }
    return collected


def h60_excess_pairs(
    signals: list[dict[str, Any]],
    histories: dict[str, pd.DataFrame],
    benchmark_history: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Independent (one open position per ticker), completed h60 trades with their TOPIX-ETF excess return."""
    trades = simulate_signals(
        signals, histories, holding_days=60, round_trip_cost_pct=ROUND_TRIP_COST_PCT, apply_tax=False
    )
    independent = select_non_overlapping_trades(trades)
    paired = paired_benchmark_returns(
        independent, benchmark_history, round_trip_cost_pct=BENCHMARK_ROUND_TRIP_COST_PCT
    )
    return [
        {"signal_date": trade.signal_date, "excess_return_pct": pair["excess_return_pct"]}
        for trade, pair in zip(independent, paired, strict=True)
    ]


def _valid_pairs(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [pair for pair in pairs if is_finite_number(pair.get("excess_return_pct"))]


def kill_criterion(pairs: list[dict[str, Any]], *, min_independent: int = DEFAULT_MIN_INDEPENDENT) -> dict[str, Any]:
    """Provisional stop rule on the h60 excess return over TOPIX (signal_date-cluster bootstrap).

    ``insufficient_sample`` when there are fewer valid pairs than ``min_independent`` or no CI can be built;
    otherwise ``pass`` iff the CI lower bound is above zero.
    """
    valid = _valid_pairs(pairs)
    values = [float(pair["excess_return_pct"]) for pair in valid]
    dates = [str(pair["signal_date"]) for pair in valid]
    ci = cluster_bootstrap_ci(values, dates)
    result: dict[str, Any] = {
        "metric": "h60 excess return vs 1306.T, independent trades, signal_date-cluster bootstrap 95% CI",
        "min_independent": min_independent,
        "independent_trades": len(pairs),
        "valid_pairs": len(valid),
        "signal_date_clusters": len(set(dates)),
        "mean_excess_return_pct": round(mean(values), 6) if values else None,
        "ci95": list(ci) if ci is not None else None,
        "reason": None,
    }
    if len(valid) < min_independent:
        result |= {"verdict": "insufficient_sample", "reason": "below_min_independent"}
    elif ci is None:
        result |= {"verdict": "insufficient_sample", "reason": "ci_unavailable"}
    else:
        result["verdict"] = "pass" if ci[0] > 0 else "fail"
    return result


def cluster_paired_bootstrap_diff(
    first: dict[str, list[float]],
    second: dict[str, list[float]],
    *,
    n_resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float] | None:
    """95% CI of mean(first) - mean(second), resampling signal_date clusters jointly for both sides.

    ``first``/``second`` map signal_date -> excess returns and must share the same non-empty dates.
    """
    dates = sorted(first)
    if dates != sorted(second) or any(not first[d] or not second[d] for d in dates):
        raise ValueError("both sides need the same non-empty signal dates")
    if len(dates) < 2:
        return None
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_resamples):
        chosen = rng.choices(dates, k=len(dates))
        diffs.append(
            mean(v for d in chosen for v in first[d]) - mean(v for d in chosen for v in second[d])
        )
    diffs.sort()

    def percentile(q: float) -> float:
        position = (len(diffs) - 1) * q
        lower = int(position)
        fraction = position - lower
        return diffs[lower] if not fraction else diffs[lower] + (diffs[lower + 1] - diffs[lower]) * fraction

    alpha = (1.0 - confidence) / 2.0
    return round(percentile(alpha), 6), round(percentile(1.0 - alpha), 6)


def _by_date(pairs: list[dict[str, Any]]) -> dict[str, list[float]]:
    grouped: dict[str, list[float]] = {}
    for pair in _valid_pairs(pairs):
        grouped.setdefault(str(pair["signal_date"]), []).append(float(pair["excess_return_pct"]))
    return grouped


def lag_comparison(pairs_by_lag: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Compare h60 excess return with fundamentals usable at disclosure vs after the 12-week delay."""
    first_lag, second_lag = "disclosure", "free_12w"
    first, second = _by_date(pairs_by_lag[first_lag]), _by_date(pairs_by_lag[second_lag])
    common = sorted(set(first) & set(second))
    per_lag: dict[str, Any] = {}
    for lag, grouped in ((first_lag, first), (second_lag, second)):
        values = [value for date_values in grouped.values() for value in date_values]
        ci = cluster_bootstrap_ci(values, [d for d, vs in grouped.items() for _ in vs])
        per_lag[lag] = {
            "valid_pairs": len(values),
            "signal_dates": len(grouped),
            "mean_excess_return_pct": round(mean(values), 6) if values else None,
            "ci95": list(ci) if ci is not None else None,
            "signal_dates_not_in_both": len(set(grouped) - set(common)),
        }
    difference: dict[str, Any] = {
        "definition": f"mean({first_lag}) - mean({second_lag}); positive means using fundamentals at disclosure helps",
        "common_signal_dates": len(common),
        "mean_difference_pct": None,
        "ci95": None,
        "reason": None,
    }
    if not common:
        difference["reason"] = "no_common_signal_dates"
    else:
        a = {d: first[d] for d in common}
        b = {d: second[d] for d in common}
        difference["mean_difference_pct"] = round(
            mean(v for vs in a.values() for v in vs) - mean(v for vs in b.values() for v in vs), 6
        )
        ci = cluster_paired_bootstrap_diff(a, b)
        difference["ci95"] = list(ci) if ci is not None else None
        if ci is None:
            difference["reason"] = "fewer_than_two_common_signal_dates"
    return {"lags": per_lag, "difference": difference}


def _lag_report(
    signals: list[dict[str, Any]],
    yoy: dict[str, Any],
    histories: dict[str, pd.DataFrame],
    benchmark_history: pd.DataFrame,
    *,
    min_independent: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    groups: dict[str, Any] = {}
    for name in GROUPS:
        subset = [signal for signal in signals if signal["classification"] == name]
        groups[name.lower()] = _build_group_report(
            subset, histories, histories, benchmark_history, [str(signal["signal_date"]) for signal in subset]
        )
    early = [signal for signal in signals if signal["classification"] == "EARLY_CANDIDATE"]
    pairs = h60_excess_pairs(early, histories, benchmark_history)
    early_trades = simulate_signals(
        early, histories, holding_days=60, round_trip_cost_pct=ROUND_TRIP_COST_PCT, apply_tax=False
    )
    report = {
        "signal_count": len(signals),
        "groups": groups,
        "portfolio_summary": simulate_portfolio(
            early,
            early_trades,
            histories,
            pd.DatetimeIndex(benchmark_history.index),
            initial_capital_jpy=PORTFOLIO_INITIAL_CAPITAL_JPY,
            max_positions=PORTFOLIO_MAX_POSITIONS,
            position_size_pct=PORTFOLIO_POSITION_SIZE_PCT,
            round_trip_cost_pct=ROUND_TRIP_COST_PCT,
        ),
        "tracked_pool_explosion_recall": compute_tracked_pool_explosion_recall(
            [signal for signal in signals if signal["classification"] != "CONTROL"], histories
        ),
        "yoy_coverage_by_month": yoy,
        "kill_criterion": kill_criterion(pairs, min_independent=min_independent),
    }
    return report, pairs


def build_backtest_report(
    data: HistoricalData,
    days: list[str],
    *,
    lags: tuple[str, ...] = LAGS,
    deep_candidates: int = 25,
    min_turnover_jpy: float = 100_000_000,
    control_sample_size: int = DEFAULT_CONTROL_SAMPLE_SIZE,
    min_independent: int = DEFAULT_MIN_INDEPENDENT,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    histories = data.panel.evaluation_histories()
    if BENCHMARK_TICKER not in histories:
        raise RuntimeError(f"benchmark {BENCHMARK_TICKER} is not in the cached daily bars")
    benchmark_history = histories[BENCHMARK_TICKER]
    collected = collect_signals(
        data,
        days,
        lags,
        deep_candidates=deep_candidates,
        min_turnover_jpy=min_turnover_jpy,
        control_sample_size=control_sample_size,
        log=log,
    )
    lag_reports: dict[str, Any] = {}
    pairs_by_lag: dict[str, list[dict[str, Any]]] = {}
    for lag in lags:
        lag_reports[lag], pairs_by_lag[lag] = _lag_report(
            collected[lag]["signals"],
            collected[lag]["yoy"],
            histories,
            benchmark_history,
            min_independent=min_independent,
        )
        log(f"evaluated lag={lag}: kill_criterion={lag_reports[lag]['kill_criterion']['verdict']}")
    return {
        "report_type": "inflection_historical_backtest",
        "generated_at": datetime.now(UTC).isoformat(),
        "strategy_version": STRATEGY_VERSION,
        "period": {
            "signal_days": len(days),
            "first_signal_date": days[0] if days else None,
            "last_signal_date": days[-1] if days else None,
            "cache_first_bars_date": data.panel.sessions[0] if data.panel.sessions else None,
            "cache_last_bars_date": data.panel.sessions[-1] if data.panel.sessions else None,
        },
        "parameters": {
            "deep_candidates": deep_candidates,
            "min_turnover_jpy": min_turnover_jpy,
            "control_sample_size": control_sample_size,
            "min_independent": min_independent,
            "fundamentals_warmup_days": FINS_WARMUP_DAYS,
        },
        "notes": list(REPORT_NOTES),
        "lags": lag_reports,
        "lag_comparison": lag_comparison(pairs_by_lag) if {"disclosure", "free_12w"} <= set(lags) else None,
    }


def summary_report(report: dict[str, Any]) -> dict[str, Any]:
    """Aggregates only: trade rows are removed (tickers never appear in the summary)."""
    return _summary_only(report)  # type: ignore[no-any-return]


def check_adjustment(
    evaluation_close: pd.Series,
    fresh_rows: list[dict[str, Any]],
    *,
    tolerance: float = 1e-3,
) -> dict[str, Any]:
    """Compare our one-basis adjusted closes with ``AdjC`` from ONE by-code fetch (a single basis).

    Daily cache files are fetched on different days and so disagree on AdjC after a split; the
    check therefore needs a fresh single-fetch series. The ratio should be one constant.
    """
    fresh = pd.Series(
        {
            pd.Timestamp(str(row["Date"])): float(row["AdjC"])
            for row in fresh_rows
            if row.get("Date") and is_finite_number(row.get("AdjC"))
        },
        dtype=float,
    )
    common = evaluation_close.index.intersection(fresh.index)
    if len(common) < 2:
        return {"checked_days": len(common), "constant": None, "spread": None}
    ratio = evaluation_close.loc[common] / fresh.loc[common]
    spread = float(ratio.max() / ratio.min() - 1.0)
    return {
        "checked_days": len(common),
        "ratio_min": round(float(ratio.min()), 6),
        "ratio_max": round(float(ratio.max()), 6),
        "spread": round(spread, 8),
        "constant": spread <= tolerance,
    }
