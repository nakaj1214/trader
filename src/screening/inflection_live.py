"""Live Japanese-stock early-inflection scanner.

The scanner is deliberately two-stage:
1) scan all Prime/Standard/Growth stocks with price/volume data;
2) enrich only the strongest early-momentum names with J-Quants fundamentals.

Outputs are research candidates only. They are not BUY recommendations.
"""
from __future__ import annotations

import hashlib
import math
import os
import random
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from importlib.metadata import PackageNotFoundError, version
from statistics import median
from typing import Any, Protocol

import pandas as pd

from src.data.edinet import EdinetError, fetch_live_holder_filings, holder_filing_features
from src.data.jquants_v2_client import JQuantsV2Client
from src.data.market_calendar import expected_tse_session_date
from src.data.yfinance_prices import fetch_price_data
from src.strategy.inflection import InflectionFeatures, score_inflection

JP_MARKET_NAMES = {"0111": "Prime", "0112": "Standard", "0113": "Growth"}
JP_MARKET_CODES = set(JP_MARKET_NAMES)
# Live data cannot measure revenue acceleration or catalyst points, so its positive
# raw-score ceiling is 58 rather than the generic scorer's 100-point scale.
LIVE_MEASURABLE_MAX_SCORE = 58.0
EARLY_CANDIDATE_SCORE = 70.0
WATCH_SCORE = 52.0
STRATEGY_VERSION = "jp-inflection-shadow-v3"
REPORT_SCHEMA_VERSION = 5
DEFAULT_JQUANTS_PLAN = "free"
DEFAULT_FREE_DELAY_WEEKS = 12
MIN_PRICE_COVERAGE = 0.70
MIN_LATEST_DATE_COVERAGE = 0.80
DEFAULT_PRICE_RETRY_COUNT = 2
DEFAULT_PRICE_RETRY_WAIT_SECONDS = "180,420"
DEFAULT_CONTROL_SAMPLE_SIZE = 25
# Raw fundamental inputs persisted per candidate (schema 5) so later learning can use
# values that cannot be reconstructed point-in-time. Missing data keeps every key.
FEATURE_DEFAULTS: dict[str, Any] = {
    "revenue_growth_yoy_pct": None,
    "operating_profit_growth_yoy_pct": None,
    "operating_margin_change_pctpt": None,
    "turned_profitable": False,
    "upward_revision_pct": None,
    "negative_operating_cashflow": False,
    "latest_actual_disclosure_date": None,
    "latest_disclosure_date": None,
    # Diagnostics recorded for later study; none of them enters the score.
    "forecast_disclosure_date": None,
    "disclosure_age_days": None,
    "forecast_age_days": None,
    "max_daily_return_20d_pct": None,
    "up_day_ratio_20d": None,
    "up_day_ratio_60d": None,
    "daily_volatility_20d_pct": None,
    "distance_from_period_high_pct": None,
    "quarterly_sales_growth_yoy_pct": None,
    "quarterly_op_growth_yoy_pct": None,
    "quarterly_sales_growth_accel_pctpt": None,
    "quarterly_op_growth_accel_pctpt": None,
    "sector33_return_20d_pct": None,
    "sector33_return_60d_pct": None,
    "relative_return_20d_vs_sector_pct": None,
    "relative_return_60d_vs_sector_pct": None,
    "major_holder_filings_60d": None,
    "major_holder_new_filings_60d": None,
    "days_since_major_holder_filing": None,
}
TECH_DIAGNOSTIC_KEYS = (
    "max_daily_return_20d_pct",
    "up_day_ratio_20d",
    "up_day_ratio_60d",
    "daily_volatility_20d_pct",
    "distance_from_period_high_pct",
)


class PriceDataRetryExhausted(RuntimeError):
    def __init__(self, details: dict[str, str]) -> None:
        self.details = details
        super().__init__(
            "DATA_HEALTH: price data retries exhausted: "
            + ", ".join(f"{key}={value}" for key, value in details.items())
        )


@dataclass(frozen=True)
class LiveCandidate:
    ticker: str
    company_name: str
    market: str
    classification: str
    live_normalized_score: float
    raw_inflection_score: float
    current_price: float
    return_5d_pct: float | None
    return_20d_pct: float | None
    return_60d_pct: float | None
    volume_ratio_20d: float | None
    near_52w_high: bool
    near_listing_high: bool
    avg_turnover_20d_jpy: float | None
    reasons: list[str]
    limitations: list[str]
    features: dict[str, Any]
    score_details: dict[str, float]
    pre_score: float
    sector33_code: str | None
    sector33_name: str | None

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["score"] = result["live_normalized_score"]  # schema-3 compatibility alias
        return result


def _ticker_from_code(code: str) -> str:
    code = str(code).strip()
    return f"{code[:4]}.T"


def _pct_change(close: pd.Series, days: int) -> float | None:
    if len(close) <= days:
        return None
    base = float(close.iloc[-days - 1])
    last = float(close.iloc[-1])
    if base <= 0:
        return None
    return (last / base - 1.0) * 100.0


def _technical_features(df: pd.DataFrame) -> dict[str, Any] | None:
    close = pd.to_numeric(df.get("Close"), errors="coerce").dropna()
    if len(close) < 21:
        return None
    volume = pd.to_numeric(df.get("Volume"), errors="coerce").reindex(close.index)
    current = float(close.iloc[-1])
    vol20 = volume.tail(20).mean()
    prev20 = volume.iloc[-40:-20].mean() if len(volume) >= 40 else None
    volume_ratio = None
    if prev20 is not None and pd.notna(prev20) and float(prev20) > 0 and pd.notna(vol20):
        volume_ratio = float(vol20) / float(prev20)
    available_high = float(close.tail(252).max())
    turnover_values = (
        pd.to_numeric(df["Turnover"], errors="coerce").reindex(close.index)
        if "Turnover" in df.columns
        else close * volume
    )
    turnover = float(turnover_values.tail(20).mean()) if turnover_values.tail(20).notna().any() else None
    daily = close.pct_change().dropna()
    daily = daily[daily.abs() != float("inf")]
    last20, last60 = daily.tail(20), daily.tail(60)
    return {
        "current_price": current,
        "return_5d_pct": _pct_change(close, 5),
        "return_20d_pct": _pct_change(close, 20),
        "return_60d_pct": _pct_change(close, 60),
        "volume_ratio_20d": volume_ratio,
        "near_52w_high": len(close) >= 252 and current >= available_high * 0.99,
        "near_listing_high": len(close) < 252 and current >= available_high * 0.99,
        "avg_turnover_20d_jpy": turnover,
        "max_daily_return_20d_pct": float(last20.max()) * 100.0 if len(last20) == 20 else None,
        "up_day_ratio_20d": float((last20 > 0).mean()) if len(last20) == 20 else None,
        "up_day_ratio_60d": float((last60 > 0).mean()) if len(last60) == 60 else None,
        "daily_volatility_20d_pct": float(last20.std()) * 100.0 if len(last20) == 20 else None,
        "distance_from_period_high_pct": (current / available_high - 1.0) * 100.0 if available_high > 0 else None,
    }


def _latest_close_date(df: pd.DataFrame) -> str | None:
    close = pd.to_numeric(df.get("Close"), errors="coerce").dropna()
    if close.empty:
        return None
    timestamp = pd.Timestamp(close.index[-1])
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_localize(None)
    return str(timestamp.date())


def _pre_score(t: dict[str, Any]) -> float:
    r5 = float(t.get("return_5d_pct") or 0.0)
    r20 = float(t.get("return_20d_pct") or 0.0)
    vr = float(t.get("volume_ratio_20d") or 1.0)
    score = max(0.0, min(r5, 12.0))
    score += max(0.0, min(r20, 30.0)) * 0.7
    score += max(0.0, min(vr - 1.0, 3.0)) * 8.0
    if t.get("near_52w_high") or t.get("near_listing_high"):
        score += 10.0
    if r20 >= 50.0:
        score -= 25.0
    return score


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, "", "-"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("DiscDate") or ""),
        str(row.get("DiscTime") or ""),
        str(row.get("DiscNo") or ""),
    )


def _has_actual_financials(row: dict[str, Any]) -> bool:
    return _to_float(row.get("Sales")) is not None or _to_float(row.get("OP")) is not None


def _previous_comparable_actual(
    actual_rows: list[dict[str, Any]],
    latest: dict[str, Any],
) -> dict[str, Any] | None:
    """Return a prior-fiscal-year actual for the same period, never a same-year correction."""
    period_type = str(latest.get("CurPerType") or "")
    latest_fiscal_end = str(latest.get("CurFYEn") or "")
    if not period_type or not latest_fiscal_end:
        return None
    try:
        prior_fiscal_end = str((pd.Timestamp(latest_fiscal_end) - pd.DateOffset(years=1)).date())
    except (TypeError, ValueError):
        return None
    candidates = [
        row
        for row in actual_rows
        if row is not latest
        and str(row.get("CurPerType") or "") == period_type
        and str(row.get("CurFYEn") or "") == prior_fiscal_end
    ]
    return candidates[-1] if candidates else None


def _fundamental_features(rows: list[dict[str, Any]], *, as_of: str | None = None) -> dict[str, Any]:
    rows = sorted(rows, key=_row_sort_key)
    actual_rows = [row for row in rows if _has_actual_financials(row)]
    if not actual_rows:
        return {}

    latest = actual_rows[-1]
    previous = _previous_comparable_actual(actual_rows, latest)

    sales = _to_float(latest.get("Sales"))
    prev_sales = _to_float(previous.get("Sales")) if previous else None
    op = _to_float(latest.get("OP"))
    prev_op = _to_float(previous.get("OP")) if previous else None

    revenue_growth = None
    if sales is not None and prev_sales not in (None, 0):
        revenue_growth = (sales / prev_sales - 1.0) * 100.0

    op_growth = None
    if op is not None and prev_op not in (None, 0) and prev_op > 0:
        op_growth = (op / prev_op - 1.0) * 100.0

    margin_change = None
    if sales not in (None, 0) and prev_sales not in (None, 0) and op is not None and prev_op is not None:
        margin_change = (op / sales - prev_op / prev_sales) * 100.0

    fiscal_end = str(latest.get("CurFYEn") or "")
    forecast_rows = [
        row
        for row in rows
        if str(row.get("CurFYEn") or "") == fiscal_end and _to_float(row.get("FOP")) is not None
    ]
    upward_revision = None
    if len(forecast_rows) >= 2:
        old = _to_float(forecast_rows[-2].get("FOP"))
        new = _to_float(forecast_rows[-1].get("FOP"))
        if old not in (None, 0) and new is not None:
            upward_revision = (new - old) / abs(old) * 100.0

    cashflow_rows = [
        row
        for row in actual_rows
        if str(row.get("CurFYEn") or "") == fiscal_end and _to_float(row.get("CFO")) is not None
    ]
    latest_cfo = _to_float(cashflow_rows[-1].get("CFO")) if cashflow_rows else None

    return {
        # The live client returns full history; bound only the new diagnostics so legacy scores stay unchanged.
        **_quarterly_features(
            [row for row in actual_rows if as_of is None or str(row.get("DiscDate") or "") <= as_of]
        ),
        "revenue_growth_yoy_pct": revenue_growth,
        "operating_profit_growth_yoy_pct": op_growth,
        "operating_margin_change_pctpt": margin_change,
        "turned_profitable": bool(op is not None and prev_op is not None and op > 0 >= prev_op),
        "upward_revision_pct": upward_revision,
        "negative_operating_cashflow": bool(latest_cfo is not None and latest_cfo < 0),
        "latest_actual_disclosure_date": latest.get("DiscDate"),
        "latest_disclosure_date": rows[-1].get("DiscDate"),
        "forecast_disclosure_date": forecast_rows[-1].get("DiscDate") if len(forecast_rows) >= 2 else None,
    }


def _quarterly_features(actual_rows: list[dict[str, Any]]) -> dict[str, float | None]:
    """Compare standalone quarters within one reporting basis; missing inputs stay missing."""
    result: dict[str, float | None] = {
        "quarterly_sales_growth_yoy_pct": None,
        "quarterly_op_growth_yoy_pct": None,
        "quarterly_sales_growth_accel_pctpt": None,
        "quarterly_op_growth_accel_pctpt": None,
    }
    if not actual_rows:
        return result
    latest = actual_rows[-1]
    periods = {"1Q": 1, "2Q": 2, "3Q": 3, "FY": 4, "4Q": 4}
    quarter = periods.get(str(latest.get("CurPerType")))
    _, marker, basis = str(latest.get("DocType") or "").partition("FinancialStatements_")
    if quarter is None or not marker or not basis:
        return result
    try:
        fiscal_end = date.fromisoformat(str(latest.get("CurFYEn")))
    except ValueError:
        return result

    cumulative: dict[tuple[str, int], dict[str, Any]] = {}
    for row in actual_rows:
        period = str(row.get("CurPerType") or "")
        doc_period, _, row_basis = str(row.get("DocType") or "").partition("FinancialStatements_")
        if period not in periods or periods.get(doc_period) != periods[period] or row_basis != basis:
            continue
        # Live rows include period dates; reject irregular fiscal periods when available.
        if row.get("CurPerSt") and row.get("CurPerEn"):
            try:
                start = pd.Timestamp(row["CurPerSt"])
                end = pd.Timestamp(row["CurPerEn"])
                if start + pd.DateOffset(months=3 * periods[period]) - pd.Timedelta(days=1) != end:
                    continue
            except (TypeError, ValueError):
                continue
        cumulative[(str(row.get("CurFYEn")), periods[period])] = row

    def prior_year(end: str) -> str:
        return str((pd.Timestamp(end) - pd.DateOffset(years=1)).date())

    def standalone(end: str, q: int, column: str) -> float | None:
        value = _to_float(cumulative.get((end, q), {}).get(column))
        previous = 0.0 if q == 1 else _to_float(cumulative.get((end, q - 1), {}).get(column))
        if value is None or previous is None or not math.isfinite(value) or not math.isfinite(previous):
            return None
        return value - previous

    def growth(end: str, q: int, column: str) -> float | None:
        value = standalone(end, q, column)
        previous = standalone(prior_year(end), q, column)
        if value is None or previous is None or previous == 0 or (column == "OP" and previous < 0):
            return None
        return (value / previous - 1.0) * 100.0

    end = str(fiscal_end)
    prev_end, prev_quarter = (prior_year(end), 4) if quarter == 1 else (end, quarter - 1)
    for column, label in (("Sales", "sales"), ("OP", "op")):
        current = growth(end, quarter, column)
        previous = growth(prev_end, prev_quarter, column)
        result[f"quarterly_{label}_growth_yoy_pct"] = current
        if current is not None and previous is not None:
            result[f"quarterly_{label}_growth_accel_pctpt"] = current - previous
    return result


def _normalize_available_score(fundamental: float, momentum: float, risk: float) -> float:
    measurable = fundamental + momentum + risk
    return max(0.0, min(100.0, measurable / LIVE_MEASURABLE_MAX_SCORE * 100.0))


def _classify(score: float, tech: dict[str, Any]) -> str:
    """Classify the 0-100 live-normalized score using live thresholds."""
    r20 = float(tech.get("return_20d_pct") or 0.0)
    r60 = float(tech.get("return_60d_pct") or 0.0)
    # ponytail: short histories have no r60, so overextension relies on r20;
    # add an IPO-specific threshold only after forward validation supports one.
    if r20 >= 50.0 or r60 >= 100.0:
        return "OVEREXTENDED"
    if score >= EARLY_CANDIDATE_SCORE and r20 > 0 and float(tech.get("volume_ratio_20d") or 0.0) >= 1.25:
        return "EARLY_CANDIDATE"
    if score >= WATCH_SCORE:
        return "WATCH"
    return "NONE"


def _data_policy() -> dict[str, Any]:
    plan = os.getenv("JQUANTS_PLAN", DEFAULT_JQUANTS_PLAN).strip().lower() or DEFAULT_JQUANTS_PLAN
    default_delay = DEFAULT_FREE_DELAY_WEEKS if plan == "free" else 0
    try:
        delay_weeks = int(os.getenv("JQUANTS_DATA_DELAY_WEEKS", str(default_delay)))
    except ValueError:
        delay_weeks = default_delay
    return {
        "jquants_plan": plan,
        "jquants_data_delay_weeks": max(0, delay_weeks),
        "price_source": "yfinance",
        "fundamental_source": "J-Quants V2 financial summary",
    }


def _package_versions() -> dict[str, str]:
    result: dict[str, str] = {}
    for package in ("yfinance", "pandas", "requests", "cryptography"):
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = "not-installed"
    return result


def _price_retry_waits() -> list[float]:
    count_text = os.getenv("INFLECTION_PRICE_RETRY_COUNT", str(DEFAULT_PRICE_RETRY_COUNT))
    waits_text = os.getenv(
        "INFLECTION_PRICE_RETRY_WAIT_SECONDS", DEFAULT_PRICE_RETRY_WAIT_SECONDS
    )
    try:
        count = int(count_text)
        waits = [] if not waits_text.strip() else [float(value) for value in waits_text.split(",")]
    except ValueError as exc:
        raise ValueError("invalid inflection price retry configuration") from exc
    if count < 0 or len(waits) != count or any(wait < 0 or not math.isfinite(wait) for wait in waits):
        raise ValueError("invalid inflection price retry configuration")
    return waits


def _age_days(as_of: str, disclosed: object) -> int | None:
    """Days from a disclosure date to the scan's market date; ``None`` when either is missing or malformed."""
    if not disclosed:
        return None
    try:
        return (date.fromisoformat(as_of) - date.fromisoformat(str(disclosed))).days
    except ValueError:
        return None


def _clean_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _evaluate_candidate(
    ticker: str,
    tech: dict[str, Any],
    *,
    client: FinancialSource,
    ticker_meta: dict[str, dict[str, Any]],
    fundamental_limitation: str,
    as_of: str,
    sector_returns: dict[str, dict[int, float]] | None = None,
    holder_filings: list[dict[str, Any]] | None = None,
) -> LiveCandidate:
    code = str(ticker_meta[ticker].get("Code") or "")
    fins = client.financial_summary(code)
    fundamental = _fundamental_features(fins, as_of=as_of)
    features = InflectionFeatures(
        revenue_growth_yoy_pct=fundamental.get("revenue_growth_yoy_pct"),
        operating_profit_growth_yoy_pct=fundamental.get("operating_profit_growth_yoy_pct"),
        operating_margin_change_pctpt=fundamental.get("operating_margin_change_pctpt"),
        turned_profitable=bool(fundamental.get("turned_profitable")),
        upward_revision_pct=fundamental.get("upward_revision_pct"),
        return_20d_pct=tech.get("return_20d_pct"),
        return_60d_pct=tech.get("return_60d_pct"),
        volume_ratio_20d=tech.get("volume_ratio_20d"),
        near_52w_high=bool(tech.get("near_52w_high")),
        near_listing_high=bool(tech.get("near_listing_high")),
        return_20d_extreme_pct=tech.get("return_20d_pct"),
        negative_operating_cashflow=bool(fundamental.get("negative_operating_cashflow")),
    )
    raw = score_inflection(features)
    score = _normalize_available_score(raw.fundamental, raw.momentum, raw.risk_penalty)
    classification = _classify(score, tech)
    reasons = []
    if (fundamental.get("revenue_growth_yoy_pct") or 0) >= 20:
        reasons.append("売上成長")
    if (fundamental.get("operating_profit_growth_yoy_pct") or 0) >= 50:
        reasons.append("営業利益急増")
    if fundamental.get("turned_profitable"):
        reasons.append("営業黒字転換")
    if (fundamental.get("upward_revision_pct") or 0) >= 10:
        reasons.append("業績予想上方修正")
    if (tech.get("volume_ratio_20d") or 0) >= 1.5:
        reasons.append("出来高増加")
    if tech.get("near_52w_high"):
        reasons.append("52週高値圏")
    if tech.get("near_listing_high"):
        reasons.append("上場来高値圏")
    source: dict[str, Any] = {
        **fundamental,
        **{key: tech.get(key) for key in TECH_DIAGNOSTIC_KEYS},
        "disclosure_age_days": _age_days(as_of, fundamental.get("latest_actual_disclosure_date")),
        "forecast_age_days": _age_days(as_of, fundamental.get("forecast_disclosure_date")),
        **holder_filing_features(
            holder_filings, ticker, date.fromisoformat(as_of), datetime.fromisoformat(f"{as_of}T16:40:00+09:00"),
        ),
    }
    sector = _clean_text(ticker_meta[ticker].get("S33"))
    for horizon in (20, 60):
        own = tech.get(f"return_{horizon}d_pct")
        sector_return = (sector_returns or {}).get(sector or "", {}).get(horizon)
        if own is not None and sector_return is not None:
            source[f"sector33_return_{horizon}d_pct"] = sector_return
            source[f"relative_return_{horizon}d_vs_sector_pct"] = float(own) - sector_return
    return LiveCandidate(
        ticker=ticker,
        company_name=str(ticker_meta[ticker].get("CoName") or ticker),
        market=str(ticker_meta[ticker].get("MktNm") or ""),
        classification=classification,
        live_normalized_score=round(score, 3),
        raw_inflection_score=raw.total,
        current_price=float(tech["current_price"]),
        return_5d_pct=tech.get("return_5d_pct"),
        return_20d_pct=tech.get("return_20d_pct"),
        return_60d_pct=tech.get("return_60d_pct"),
        volume_ratio_20d=tech.get("volume_ratio_20d"),
        near_52w_high=bool(tech.get("near_52w_high")),
        near_listing_high=bool(tech.get("near_listing_high")),
        avg_turnover_20d_jpy=tech.get("avg_turnover_20d_jpy"),
        reasons=reasons,
        limitations=[fundamental_limitation],
        features={
            key: (bool(source.get(key)) if isinstance(default, bool) else source.get(key, default))
            for key, default in FEATURE_DEFAULTS.items()
        },
        score_details={
            **raw.details,
            "fundamental": raw.fundamental,
            "momentum": raw.momentum,
            "risk_penalty": raw.risk_penalty,
        },
        pre_score=round(_pre_score(tech), 6),
        sector33_code=_clean_text(ticker_meta[ticker].get("S33")),
        sector33_name=_clean_text(ticker_meta[ticker].get("S33Nm")),
    )


class FinancialSource(Protocol):
    """Anything that can return J-Quants-style financial summary rows for a 5-digit code."""

    def financial_summary(self, code: str) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class Selection:
    candidates: list[LiveCandidate]  # deep candidates, best score first
    control_sample: list[LiveCandidate]
    control_seed: int
    technical_usable_tickers: set[str]
    liquid_candidate_count: int
    deep_candidate_count: int


def select_and_evaluate(
    prices: dict[str, pd.DataFrame],
    ticker_meta: dict[str, dict[str, Any]],
    client: FinancialSource,
    *,
    seed_date: str,
    deep_candidates: int,
    min_turnover_jpy: float,
    control_sample_size: int,
    fundamental_limitation: str,
    holder_filings: list[dict[str, Any]] | None = None,
) -> Selection:
    """Pick the deep candidates and the control sample from already-fetched prices.

    Shared by the live scan and the historical backtest so both apply identical logic.
    """
    preselected: list[tuple[float, str, dict[str, Any]]] = []
    technical_usable: set[str] = set()
    sector_samples: dict[str, dict[int, list[float]]] = {}
    for ticker, df in prices.items():
        tech = _technical_features(df)
        if not tech:
            continue
        technical_usable.add(ticker)
        sector = _clean_text(ticker_meta[ticker].get("S33"))
        if sector:
            samples = sector_samples.setdefault(sector, {20: [], 60: []})
            for horizon in (20, 60):
                value = tech.get(f"return_{horizon}d_pct")
                if value is not None and math.isfinite(float(value)):
                    samples[horizon].append(float(value))
        turnover = tech.get("avg_turnover_20d_jpy")
        if turnover is None or float(turnover) < min_turnover_jpy:
            continue
        preselected.append((_pre_score(tech), ticker, tech))

    sector_returns = {
        sector: {horizon: median(values) for horizon, values in samples.items() if len(values) >= 5}
        for sector, samples in sector_samples.items()
    }
    preselected.sort(reverse=True, key=lambda item: item[0])
    liquid = list(preselected)
    preselected = preselected[:deep_candidates]

    candidates: list[LiveCandidate] = []
    for _, ticker, tech in preselected:
        candidates.append(
            _evaluate_candidate(
                ticker,
                tech,
                client=client,
                ticker_meta=ticker_meta,
                fundamental_limitation=fundamental_limitation,
                as_of=seed_date,
                sector_returns=sector_returns,
                holder_filings=holder_filings,
            )
        )

    # Control sample: unbiased draw from every liquid name, evaluated exactly like the deep
    # candidates but kept apart so existing candidate-based statistics are unchanged.
    # The seed depends only on the market date, so re-running a day reproduces the draw.
    control_seed = int.from_bytes(hashlib.sha256(seed_date.encode("utf-8")).digest()[:8], "big")
    evaluated = {candidate.ticker: candidate for candidate in candidates}
    technicals = {ticker: tech for _, ticker, tech in liquid}
    control_sample: list[LiveCandidate] = []
    if control_sample_size > 0:
        drawn = random.Random(control_seed).sample(sorted(technicals), k=min(control_sample_size, len(technicals)))
        for ticker in sorted(drawn):
            if ticker not in evaluated:
                evaluated[ticker] = _evaluate_candidate(
                    ticker,
                    technicals[ticker],
                    client=client,
                    ticker_meta=ticker_meta,
                    fundamental_limitation=fundamental_limitation,
                    as_of=seed_date,
                    sector_returns=sector_returns,
                    holder_filings=holder_filings,
                )
            control_sample.append(evaluated[ticker])

    candidates.sort(key=lambda candidate: candidate.live_normalized_score, reverse=True)
    return Selection(
        candidates=candidates,
        control_sample=control_sample,
        control_seed=control_seed,
        technical_usable_tickers=technical_usable,
        liquid_candidate_count=len(liquid),
        deep_candidate_count=len(preselected),
    )


def _drop_future_bars(prices: dict[str, pd.DataFrame], expected_date: str) -> set[str]:
    """Trim by the provider's local market date, preserving the original index and values."""
    dropped: set[str] = set()
    for ticker, frame in prices.items():
        try:
            index = pd.DatetimeIndex(pd.to_datetime(frame.index, format="mixed")).tz_localize(None).normalize()
        except (TypeError, ValueError):
            continue
        future = index > pd.Timestamp(expected_date)
        if future.any():
            prices[ticker] = frame.loc[~future]
            dropped.add(ticker)
    return dropped


def scan_japan_inflection(
    *,
    client: JQuantsV2Client | None = None,
    lookback_days: int = 252,
    deep_candidates: int = 25,
    min_turnover_jpy: float = 100_000_000,
    control_sample_size: int = DEFAULT_CONTROL_SAMPLE_SIZE,
) -> dict[str, Any]:
    if control_sample_size < 0:
        raise ValueError("control_sample_size must not be negative")
    generated_at = datetime.now(UTC).isoformat()
    expected_date = expected_tse_session_date(generated_at)
    retry_waits = _price_retry_waits()
    client = client or JQuantsV2Client()
    if not client.is_available():
        raise RuntimeError("JQUANTS_API_KEY is required for the production JP universe")

    master = [row for row in client.listed_issues() if str(row.get("Mkt") or "") in JP_MARKET_CODES]
    ticker_meta: dict[str, dict[str, Any]] = {}
    for row in master:
        code = str(row.get("Code") or "")
        if len(code) < 4:
            continue
        ticker_meta[_ticker_from_code(code)] = row

    tickers = sorted(ticker_meta)
    market_coverage = {
        market: {"universe": 0, "price_data": 0, "technical_usable": 0, "latest_date_count": 0}
        for market in JP_MARKET_NAMES.values()
    }
    for metadata in ticker_meta.values():
        market_code = str(metadata.get("Mkt") or "")
        try:
            market_coverage[JP_MARKET_NAMES[market_code]]["universe"] += 1
        except KeyError as exc:
            raise RuntimeError(f"DATA_HEALTH: unexpected market code: {market_code}") from exc

    prices = fetch_price_data(tickers, lookback_days)
    latest_dates: dict[str, str] = {}
    dropped_future: set[str] = set()
    for attempt in range(len(retry_waits) + 1):
        dropped_future.update(_drop_future_bars(prices, expected_date))
        latest_dates = {
            ticker: latest_date
            for ticker, frame in prices.items()
            if (latest_date := _latest_close_date(frame)) is not None
        }
        price_data = len(prices)
        histogram = ",".join(
            f"{day}:{count}" for day, count in sorted(Counter(latest_dates.values()).items(), reverse=True)[:5]
        )
        fresh = sum(value == expected_date for value in latest_dates.values())
        price_coverage = price_data / len(tickers) if tickers else 0.0
        latest_coverage = fresh / price_data if price_data else 0.0
        failed_gates = [
            name
            for name, failed in (
                ("price_coverage", price_coverage < MIN_PRICE_COVERAGE),
                ("latest_coverage", latest_coverage < MIN_LATEST_DATE_COVERAGE),
            )
            if failed
        ]
        if not failed_gates:
            if attempt:
                print(
                    "DATA_HEALTH_RECOVERED: "
                    f"attempt={attempt} universe={len(tickers)} missing={len(tickers) - price_data} "
                    f"price_data={price_data} price_coverage={price_coverage:.1%} "
                    f"fresh={fresh} latest_coverage={latest_coverage:.1%}"
                )
            break

        retry_tickers = [
            ticker
            for ticker in tickers
            if ticker not in prices or latest_dates.get(ticker) != expected_date
        ]
        if attempt == len(retry_waits):
            raise PriceDataRetryExhausted(
                {
                    "retry_exhausted": "true",
                    "expected_date": expected_date,
                    "universe": str(len(tickers)),
                    "missing": str(len(tickers) - price_data),
                    "price_data": str(price_data),
                    "price_coverage": f"{price_coverage:.1%}",
                    "latest_coverage": f"{latest_coverage:.1%}",
                    "failed_gate": ",".join(failed_gates),
                    "attempts": str(attempt + 1),
                    "latest_dates": histogram,
                    "dropped_future_bars": str(len(dropped_future)),
                }
            )
        if not retry_tickers:
            break
        wait = retry_waits[attempt]
        print(
            "DATA_HEALTH_RETRY: "
            f"attempt={attempt + 1}/{len(retry_waits)} expected_date={expected_date} "
            f"universe={len(tickers)} missing={len(tickers) - price_data} "
            f"price_data={price_data} price_coverage={price_coverage:.1%} "
            f"fresh={fresh} latest_coverage={latest_coverage:.1%} "
            f"failed_gate={','.join(failed_gates)} wait={wait:g}s "
            f"latest_dates={histogram} dropped_future_bars={len(dropped_future)}"
        )
        time.sleep(wait)
        prices.update(fetch_price_data(retry_tickers, lookback_days))

    # Price coverage per market (the technical features are computed in select_and_evaluate).
    for ticker, df in prices.items():
        market_code = str(ticker_meta[ticker].get("Mkt") or "")
        market_coverage[JP_MARKET_NAMES[market_code]]["price_data"] += 1
        latest_date = _latest_close_date(df)
        if latest_date:
            latest_dates[ticker] = latest_date

    policy = _data_policy()
    delay_weeks = int(policy["jquants_data_delay_weeks"])
    fundamental_limitation = (
        f"J-Quants {policy['jquants_plan']} の財務データは約{delay_weeks}週間遅延。"
        "リアルタイム材料ではなくshadow検証用の遅延ファンダメンタルとして扱う"
        if delay_weeks > 0
        else "財務データの公開時点と取得可能時点を一次情報で確認する必要がある"
    )
    holder_filings = None
    if os.getenv("EDINET_API_KEY", "").strip():
        try:
            holder_filings = fetch_live_holder_filings(expected_date)
            # Validate all filing metadata before evaluating either candidate pool.
            holder_filing_features(holder_filings, "", date.fromisoformat(expected_date),
                                   datetime.fromisoformat(f"{expected_date}T16:40:00+09:00"))
        except EdinetError as exc:
            holder_filings = None
            print(f"EDINET_UNAVAILABLE: {type(exc).__name__} days=60")
    selection = select_and_evaluate(
        prices,
        ticker_meta,
        client,
        seed_date=expected_date,
        deep_candidates=deep_candidates,
        min_turnover_jpy=min_turnover_jpy,
        control_sample_size=control_sample_size,
        fundamental_limitation=fundamental_limitation,
        holder_filings=holder_filings,
    )
    candidates = selection.candidates
    control_sample = selection.control_sample
    technical_usable_count = len(selection.technical_usable_tickers)
    liquid_candidate_count = selection.liquid_candidate_count
    for ticker in selection.technical_usable_tickers:
        market_code = str(ticker_meta[ticker].get("Mkt") or "")
        market_coverage[JP_MARKET_NAMES[market_code]]["technical_usable"] += 1
    counts: dict[str, int] = {}
    for item in candidates:
        counts[item.classification] = counts.get(item.classification, 0) + 1

    latest_price_date = expected_date
    latest_price_date_count = sum(value == expected_date for value in latest_dates.values())
    for ticker, value in latest_dates.items():
        if value == expected_date:
            market_code = str(ticker_meta[ticker].get("Mkt") or "")
            market_coverage[JP_MARKET_NAMES[market_code]]["latest_date_count"] += 1
    latest_date_histogram = dict(
        sorted(Counter(latest_dates.values()).items(), reverse=True)[:5]
    )
    stale_tickers_sample = sorted(
        ticker for ticker, value in latest_dates.items() if value != expected_date
    )[:20]

    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "source_commit_sha": os.getenv("GITHUB_SHA") or "local-or-unknown",
        "generated_at": generated_at,
        "mode": "shadow",
        "universe": "TSE Prime + Standard + Growth",
        "universe_count": len(tickers),
        "price_data_count": len(prices),
        "technical_usable_count": technical_usable_count,
        "liquid_candidate_count": liquid_candidate_count,
        "latest_price_date": latest_price_date,
        "latest_price_date_count": latest_price_date_count,
        "market_coverage": market_coverage,
        "latest_date_histogram": latest_date_histogram,
        "stale_tickers_sample": stale_tickers_sample,
        "deep_candidate_count": selection.deep_candidate_count,
        "classification_counts": counts,
        "scan_parameters": {
            "lookback_days": lookback_days,
            "deep_candidates": deep_candidates,
            "min_turnover_jpy": min_turnover_jpy,
            "control_sample_size": control_sample_size,
            "early_candidate_score": EARLY_CANDIDATE_SCORE,
            "watch_score": WATCH_SCORE,
            "measurable_max_score": LIVE_MEASURABLE_MAX_SCORE,
        },
        "data_policy": policy,
        "runtime_versions": _package_versions(),
        "candidates": [candidate.as_dict() for candidate in candidates],
        "control_sample_size": control_sample_size,
        "control_sample_seed": selection.control_seed,
        "control_sample": [candidate.as_dict() for candidate in control_sample],
        "notes": [
            "Known historical winners are not whitelisted or special-cased.",
            "EARLY_CANDIDATE is a research flag, not a buy signal.",
            "Catalyst/news evidence is intentionally excluded until a point-in-time-safe source is connected.",
            "Free-tier delayed fundamentals are suitable for pipeline accumulation, not real-time edge validation.",
        ],
    }
