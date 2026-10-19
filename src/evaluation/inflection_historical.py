"""Point-in-time reconstruction of the v3 scan from cached J-Quants history.

Everything a scan on day ``as_of`` may use is derived only from data dated on or
before ``as_of``:

* prices: split-adjusted with the factors up to ``as_of`` (never later splits),
* universe attributes: the latest master dated on or before ``as_of``,
* fundamentals: known disclosure timestamps before the conservative provider day
  boundary (``disclosure``), or strictly older than 12 weeks (``free_12w``).
  Exact historical API delivery times are not recorded in the cache.

The scoring itself is the live code (``select_and_evaluate``), not a copy.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from src.data.jquants_history import HistoryCache
from src.data.jquants_v2_client import financial_disclosure_at, financial_rows_as_of
from src.data.validation import is_finite_number, validate_ohlcv
from src.evaluation.inflection_backtest import (
    BOOTSTRAP_SEED,
    TradeResult,
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
    _is_ordinary_code,
    _ticker_from_code,
    select_and_evaluate,
)

JST = ZoneInfo("Asia/Tokyo")
FREE_PLAN_LAG_DAYS = 84
LAGS = ("disclosure", "free_12w")
RAW_BAR_COLUMNS = ("O", "H", "L", "C", "Vo", "Va", "AdjFactor", "ExRT")
HISTORY_WINDOW = 252
MASTER_FIELDS = ("Code", "CoName", "Mkt", "MktNm", "S33", "S33Nm")
FINS_FIELDS = (
    "Code", "DiscDate", "DiscTime", "DiscNo", "DocType", "CurPerType", "CurFYEn", "CurFYSt", "CurPerSt", "CurPerEn",
    "Sales", "OP", "FOP", "CFO",
)


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TickerBars:
    frame: pd.DataFrame  # raw O/H/L/C/Vo/Va/AdjFactor, DatetimeIndex, rows with a close only
    cum: Any  # float array: product of AdjFactor over strictly later days, aligned with ``frame``
    volume_cum: Any  # same basis, excluding rights issues whose factor does not change share units


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
        raw = group.set_index("Date").rename(columns={"O": "Open", "H": "High", "L": "Low", "C": "Close",
                                                     "Vo": "Volume", "Va": "Turnover"})
        # A no-trade bar may carry a split factor even though all OHLC are missing.
        quoted = raw.dropna(how="all", subset=["Open", "High", "Low", "Close"])
        factor = group["AdjFactor"]
        if (not factor.map(lambda value: is_finite_number(value) and value > 0).all()
                or (not quoted.empty and validate_ohlcv(quoted)) or raw.index.has_duplicates):
            raise ValueError("Invalid historical price or adjustment factor")
        factor = group["AdjFactor"].fillna(1.0)
        if (factor.ne(1.0) & ~group["ExRT"].isin([1, 2, 3])).any():
            raise ValueError("Unknown historical volume adjustment event")
        # cum[i] = product of factor[j] for j > i
        cum = factor.iloc[::-1].cumprod().iloc[::-1].shift(-1, fill_value=1.0).to_numpy(dtype=float)
        volume_factor = factor.where(group["ExRT"].ne(3), 1.0)
        volume_cum = volume_factor.iloc[::-1].cumprod().iloc[::-1].shift(-1, fill_value=1.0).to_numpy(dtype=float)
        has_close = group["C"].notna().to_numpy() & (group["C"].to_numpy(dtype=float) > 0)
        frame = group.loc[has_close, list(RAW_BAR_COLUMNS)].set_index(pd.DatetimeIndex(group.loc[has_close, "Date"]))
        if frame.empty:
            continue
        result[_ticker_from_code(str(code))] = TickerBars(frame=frame, cum=cum[has_close], volume_cum=volume_cum[has_close])
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

        Close and Volume use the price and share units at ``as_of``. Rights issues
        adjust prices only, and later events cannot change an earlier scan. Memoized for the last day.
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
            volume_factor = bars.volume_cum[window] / bars.volume_cum[end - 1]
            frame = pd.DataFrame(
                {
                    "Close": sliced["C"].to_numpy(dtype=float) * factor,
                    "Volume": sliced["Vo"].to_numpy(dtype=float) / volume_factor,
                    "Turnover": sliced["Va"].to_numpy(dtype=float),
                },
                index=sliced.index,
            )
            if (not frame.map(is_finite_number).all().all() or (frame["Close"] <= 0).any()
                    or (frame[["Volume", "Turnover"]] < 0).any().any()):
                raise ValueError("Invalid historical price after adjustment")
            frames[ticker] = frame
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
            frame = frame.dropna()
            if validate_ohlcv(frame, require_volume=False):
                raise ValueError("Invalid historical price after adjustment")
            result[ticker] = frame
        return result


# ---------------------------------------------------------------------------
# Master (universe attributes)
# ---------------------------------------------------------------------------


class MasterHistory:
    def __init__(
        self,
        masters: Mapping[str, list[dict[str, Any]]] | Iterable[tuple[str, list[dict[str, Any]]]],
    ) -> None:
        """Keep only the fields scans use, one master day at a time.

        Days are consumed one by one (so raw rows are never all in memory at once), and a row that is
        identical on several days is stored once and shared: 188 daily masters of ~4,400 rows differ by a
        handful of listings, and holding each separately took over a gigabyte.
        """
        pairs = masters.items() if isinstance(masters, Mapping) else masters
        self._meta: dict[str, dict[str, dict[str, Any]]] = {}
        shared: dict[tuple[Any, ...], dict[str, Any]] = {}
        for day, rows in pairs:
            meta: dict[str, dict[str, Any]] = {}
            for row in rows:
                code = str(row.get("Code") or "")
                if str(row.get("Mkt") or "") not in JP_MARKET_CODES or not _is_ordinary_code(code):
                    continue
                fields = tuple(row.get(key) for key in MASTER_FIELDS)
                meta[_ticker_from_code(code)] = shared.setdefault(fields, dict(zip(MASTER_FIELDS, fields, strict=True)))
            self._meta[day] = meta
        self._days = sorted(self._meta)

    @classmethod
    def from_cache(cls, cache: HistoryCache) -> MasterHistory:
        return cls((day, cache.read("master", day)) for day in cache.days("master"))

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
    disclosed_at: datetime
    row: dict[str, Any]


class PointInTimeFinancials:
    """Apply the live eligibility boundary without guessing a historical API delivery time."""

    def __init__(self, rows_by_code: dict[str, list[_FinRow]], as_of: str, lag: str) -> None:
        if lag not in LAGS:
            raise ValueError(f"lag must be one of {LAGS}")
        self._rows = rows_by_code
        self._as_of = as_of
        self._lag = lag

    def financial_summary(self, code: str) -> list[dict[str, Any]]:
        return financial_rows_as_of(
            [item.row for item in self._rows.get(code, [])], self._as_of,
            FREE_PLAN_LAG_DAYS if self._lag == "free_12w" else 0,
        )


class FinancialsStore:
    def __init__(self, rows: Iterable[dict[str, Any]]) -> None:
        self._rows_by_code: dict[str, list[_FinRow]] = {}
        self.skipped_rows = 0
        for raw in rows:
            parsed = financial_disclosure_at(raw)
            code = str(raw.get("Code") or "")
            if parsed is None or not code:
                self.skipped_rows += 1
                continue
            row = {key: raw.get(key) for key in FINS_FIELDS}
            self._rows_by_code.setdefault(code, []).append(_FinRow(parsed, row))

    @classmethod
    def from_cache(cls, cache: HistoryCache) -> FinancialsStore:
        def rows() -> Iterable[dict[str, Any]]:
            for day in cache.days("fins"):
                yield from cache.read("fins", day)

        return cls(rows())

    def first_disclosure_date(self) -> str | None:
        dates = [item.disclosed_at.date() for items in self._rows_by_code.values() for item in items]
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
        "Historical reconstruction: conservative disclosure/plan eligibility boundary; "
        f"exact provider availability is unknown (lag={lag})"
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
        "unconfirmed price endings remain unevaluated; last Close is not a settlement price."
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


def _h60_trades(
    signals: list[dict[str, Any]],
    histories: dict[str, pd.DataFrame],
    benchmark_history: pd.DataFrame,
    market_calendar: pd.DatetimeIndex | None,
) -> list[TradeResult]:
    return simulate_signals(
        signals, histories, holding_days=60, round_trip_cost_pct=ROUND_TRIP_COST_PCT, apply_tax=False,
        market_calendar=pd.DatetimeIndex(benchmark_history.index if market_calendar is None else market_calendar),
    )


def _excess_lower_bound(
    trade: TradeResult, benchmark_history: pd.DataFrame, market_calendar: pd.DatetimeIndex | None = None,
) -> float | None:
    """A floor for a stock-side-unresolved trade's excess return, or ``None`` when none can be proven.

    The stock cannot lose more than 100% (plus its cost); the benchmark return is at most the best close seen in the
    60-session window from the entry (a superset of the true span). The floor needs the benchmark's valid Open on the
    entry day and a valid Close on every market session of that window: a gap means no proven floor, and no later
    day stands in for it.
    """
    if not trade.entry_date or benchmark_history.empty or market_calendar is None:
        return None  # the ETF's own dates cannot vouch for a complete window: a calendar is required
    calendar = pd.DatetimeIndex(market_calendar)
    entry_day = pd.Timestamp(trade.entry_date)
    sessions = calendar[calendar >= entry_day][:62]
    if len(sessions) < 62 or sessions[0] != entry_day:
        return None
    if not sessions.isin(benchmark_history.index).all():
        return None
    window = benchmark_history.loc[sessions]
    entry = float(window["Open"].iloc[0])
    closes = window["Close"].astype(float)
    if not math.isfinite(entry) or not entry > 0 or not closes.map(math.isfinite).all() or not (closes > 0).all():
        return None
    best_benchmark = (float(closes.max()) / entry - 1.0) * 100.0 - BENCHMARK_ROUND_TRIP_COST_PCT
    return -(100.0 + ROUND_TRIP_COST_PCT) - best_benchmark


def unresolved_h60_outcomes(
    signals: list[dict[str, Any]],
    histories: dict[str, pd.DataFrame],
    benchmark_history: pd.DataFrame,
    market_calendar: pd.DatetimeIndex | None = None,
) -> list[dict[str, Any]]:
    """Matured h60 trades that cannot be evaluated, or evaluated but not compared with the benchmark.

    Each row has its real ``signal_date`` (so it joins the same-day cluster) and ``excess_lower_bound`` (``None``
    when no floor can be proven, which is always so for a missing benchmark span: the benchmark has no upper bound).
    """
    trades = _h60_trades(signals, histories, benchmark_history, market_calendar)
    # One position per ticker, as for the valid pairs: a later signal on a held ticker is not another outcome.
    independent = select_non_overlapping_trades(trades, include_unfinished=True)
    rows = [
        {
            "signal_date": trade.signal_date,
            "excess_lower_bound": _excess_lower_bound(trade, benchmark_history, market_calendar),
        }
        for trade in independent
        if trade.horizon_matured is True and trade.net_return_pct is None
    ]
    paired = paired_benchmark_returns(
        independent, benchmark_history, round_trip_cost_pct=BENCHMARK_ROUND_TRIP_COST_PCT
    )
    rows += [
        {"signal_date": trade.signal_date, "excess_lower_bound": None}
        for trade, pair in zip(independent, paired, strict=True)
        if trade.net_return_pct is not None and pair["excess_return_pct"] is None
    ]
    return rows


def unresolved_matured_h60(
    signals: list[dict[str, Any]],
    histories: dict[str, pd.DataFrame],
    benchmark_history: pd.DataFrame,
    market_calendar: pd.DatetimeIndex | None = None,
) -> int:
    return len(unresolved_h60_outcomes(signals, histories, benchmark_history, market_calendar))


def h60_excess_pairs(
    signals: list[dict[str, Any]],
    histories: dict[str, pd.DataFrame],
    benchmark_history: pd.DataFrame,
    market_calendar: pd.DatetimeIndex | None = None,
) -> list[dict[str, Any]]:
    """Independent (one open position per ticker), completed h60 trades with their TOPIX-ETF excess return."""
    trades = _h60_trades(signals, histories, benchmark_history, market_calendar)
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


def kill_criterion(
    pairs: list[dict[str, Any]],
    *,
    min_independent: int = DEFAULT_MIN_INDEPENDENT,
    unresolved_matured: int = 0,
    unresolved_outcomes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Provisional stop rule on the h60 excess return over TOPIX (signal_date-cluster bootstrap).

    Matured h60 outcomes that are unresolved (stock side or no benchmark span) are never ignored. With any of them
    the verdict is ``incomplete``, except a ``pass`` that still holds with each one at a proven floor of its
    excess return, or a ``fail`` that still holds with each one at an unbounded gain (``unresolved_outcomes``:
    real ``signal_date`` and ``excess_lower_bound``).
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
        "unresolved_matured": unresolved_matured,
        "reason": None,
    }
    if (
        unresolved_matured > 0 and len(valid) >= min_independent and ci is not None
        and unresolved_outcomes and len(unresolved_outcomes) == unresolved_matured
    ):
        # The bootstrap lower bound never falls when an unresolved value rises, so two limits decide it: every
        # unresolved outcome at its proven floor (a pass must survive that) or at an unbounded gain (a fail must
        # survive that, i.e. the lower bound is <= 0 whatever the unknowns are). Anything between stays incomplete.
        all_dates = [*dates, *[str(row["signal_date"]) for row in unresolved_outcomes]]
        bounds = [row.get("excess_lower_bound") for row in unresolved_outcomes]
        worst = (
            cluster_bootstrap_ci([*values, *[float(row["excess_lower_bound"]) for row in unresolved_outcomes]], all_dates)
            if all(is_finite_number(bound) for bound in bounds) else None
        )
        # Exactly the limit of letting every unresolved value grow: a resample drawing one of them has mean +inf.
        ceiling = cluster_bootstrap_ci(
            [*values, *[0.0] * unresolved_matured], all_dates,
            unbounded=[False] * len(values) + [True] * unresolved_matured,
        )
        result["sensitivity"] = {
            "worst_ci95": list(worst) if worst is not None else None,
            "ceiling_ci95": [bound if math.isfinite(bound) else None for bound in ceiling] if ceiling else None,
        }
        if worst is not None and worst[0] > 0:
            result["verdict"] = "pass"
        elif ceiling is not None and ceiling[0] <= 0:  # an inf bound is never <= 0
            result["verdict"] = "fail"
        else:
            result |= {"verdict": "incomplete", "reason": "matured_unresolved_outcomes"}
    elif unresolved_matured > 0:
        result |= {"verdict": "incomplete", "reason": "matured_unresolved_outcomes"}
    elif len(valid) < min_independent:
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
    market_calendar: pd.DatetimeIndex | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    calendar = pd.DatetimeIndex(benchmark_history.index if market_calendar is None else market_calendar)
    groups: dict[str, Any] = {}
    for name in GROUPS:
        subset = [signal for signal in signals if signal["classification"] == name]
        groups[name.lower()] = _build_group_report(
            subset, histories, histories, benchmark_history, [str(signal["signal_date"]) for signal in subset],
            market_calendar=calendar,
        )
    early = [signal for signal in signals if signal["classification"] == "EARLY_CANDIDATE"]
    pairs = h60_excess_pairs(early, histories, benchmark_history, calendar)
    unresolved = unresolved_h60_outcomes(early, histories, benchmark_history, calendar)
    early_trades = simulate_signals(
        early, histories, holding_days=60, round_trip_cost_pct=ROUND_TRIP_COST_PCT, apply_tax=False,
        market_calendar=calendar,
    )
    report = {
        "signal_count": len(signals),
        "groups": groups,
        "portfolio_summary": simulate_portfolio(
            early,
            early_trades,
            histories,
            calendar,
            initial_capital_jpy=PORTFOLIO_INITIAL_CAPITAL_JPY,
            max_positions=PORTFOLIO_MAX_POSITIONS,
            position_size_pct=PORTFOLIO_POSITION_SIZE_PCT,
            round_trip_cost_pct=ROUND_TRIP_COST_PCT,
        ),
        "tracked_pool_explosion_recall": compute_tracked_pool_explosion_recall(
            [signal for signal in signals if signal["classification"] != "CONTROL"], histories
        ),
        "yoy_coverage_by_month": yoy,
        "kill_criterion": kill_criterion(
            pairs,
            min_independent=min_independent,
            unresolved_matured=len(unresolved),
            unresolved_outcomes=unresolved,
        ),
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
    include_trades: bool = True,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Assemble the report. ``include_trades=False`` drops every per-trade row as soon as a lag is evaluated,
    which keeps the peak memory to one lag's rows instead of both (the rows dominate it)."""
    histories = data.panel.evaluation_histories()
    if BENCHMARK_TICKER not in histories:
        raise RuntimeError(f"benchmark {BENCHMARK_TICKER} is not in the cached daily bars")
    benchmark_history = histories[BENCHMARK_TICKER]
    # Every cached market session, so a day the benchmark and a stock both lack still counts as missing.
    market_calendar = pd.DatetimeIndex(pd.to_datetime(data.panel.sessions))
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
            market_calendar=market_calendar,
        )
        if not include_trades:
            lag_reports[lag] = _summary_only(lag_reports[lag])
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
