"""Live Japanese-stock early-inflection scanner.

The scanner is deliberately two-stage:
1) scan all Prime/Standard/Growth stocks with price/volume data;
2) enrich only the strongest early-momentum names with J-Quants fundamentals.

Outputs are research candidates only. They are not BUY recommendations.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import pandas as pd

from src.data.jquants_v2_client import JQuantsV2Client
from src.data.yfinance_prices import fetch_price_data
from src.strategy.inflection import InflectionFeatures, score_inflection

JP_MARKET_CODES = {"0111", "0112", "0113"}  # Prime / Standard / Growth
LIVE_MEASURABLE_MAX_SCORE = 58.0
EARLY_CANDIDATE_SCORE = 70.0
WATCH_SCORE = 52.0
STRATEGY_VERSION = "jp-inflection-shadow-v1"
REPORT_SCHEMA_VERSION = 3
DEFAULT_JQUANTS_PLAN = "free"
DEFAULT_FREE_DELAY_WEEKS = 12


@dataclass(frozen=True)
class LiveCandidate:
    ticker: str
    company_name: str
    market: str
    classification: str
    score: float
    raw_inflection_score: float
    current_price: float
    return_5d_pct: float | None
    return_20d_pct: float | None
    return_60d_pct: float | None
    volume_ratio_20d: float | None
    breakout_52w: bool
    avg_turnover_20d_jpy: float | None
    reasons: list[str]
    limitations: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    if len(close) < 65:
        return None
    volume = pd.to_numeric(df.get("Volume"), errors="coerce").reindex(close.index)
    current = float(close.iloc[-1])
    vol20 = volume.tail(20).mean()
    prev20 = volume.iloc[-40:-20].mean() if len(volume) >= 40 else None
    volume_ratio = None
    if prev20 is not None and pd.notna(prev20) and float(prev20) > 0 and pd.notna(vol20):
        volume_ratio = float(vol20) / float(prev20)
    high52 = float(close.tail(min(252, len(close))).max())
    turnover = None
    if pd.notna(vol20):
        turnover = float((close.tail(20) * volume.tail(20)).mean())
    return {
        "current_price": current,
        "return_5d_pct": _pct_change(close, 5),
        "return_20d_pct": _pct_change(close, 20),
        "return_60d_pct": _pct_change(close, 60),
        "volume_ratio_20d": volume_ratio,
        "breakout_52w": current >= high52 * 0.99,
        "avg_turnover_20d_jpy": turnover,
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
    if t.get("breakout_52w"):
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


def _fundamental_features(rows: list[dict[str, Any]]) -> dict[str, Any]:
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
            upward_revision = (new / old - 1.0) * 100.0

    cashflow_rows = [
        row
        for row in actual_rows
        if str(row.get("CurFYEn") or "") == fiscal_end and _to_float(row.get("CFO")) is not None
    ]
    latest_cfo = _to_float(cashflow_rows[-1].get("CFO")) if cashflow_rows else None

    return {
        "revenue_growth_yoy_pct": revenue_growth,
        "operating_profit_growth_yoy_pct": op_growth,
        "operating_margin_change_pctpt": margin_change,
        "turned_profitable": bool(op is not None and prev_op is not None and op > 0 >= prev_op),
        "upward_revision_pct": upward_revision,
        "negative_operating_cashflow": bool(latest_cfo is not None and latest_cfo < 0),
        "latest_actual_disclosure_date": latest.get("DiscDate"),
        "latest_disclosure_date": rows[-1].get("DiscDate"),
    }


def _normalize_available_score(fundamental: float, momentum: float, risk: float) -> float:
    measurable = fundamental + momentum + risk
    return max(0.0, min(100.0, measurable / LIVE_MEASURABLE_MAX_SCORE * 100.0))


def _classify(score: float, tech: dict[str, Any]) -> str:
    r20 = float(tech.get("return_20d_pct") or 0.0)
    r60 = float(tech.get("return_60d_pct") or 0.0)
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


def scan_japan_inflection(
    *,
    client: JQuantsV2Client | None = None,
    lookback_days: int = 252,
    deep_candidates: int = 25,
    min_turnover_jpy: float = 100_000_000,
) -> dict[str, Any]:
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
    prices = fetch_price_data(tickers, lookback_days)
    preselected: list[tuple[float, str, dict[str, Any]]] = []
    technical_usable_count = 0
    liquid_candidate_count = 0
    latest_dates: list[str] = []

    for ticker, df in prices.items():
        latest_date = _latest_close_date(df)
        if latest_date:
            latest_dates.append(latest_date)
        tech = _technical_features(df)
        if not tech:
            continue
        technical_usable_count += 1
        turnover = tech.get("avg_turnover_20d_jpy")
        if turnover is None or float(turnover) < min_turnover_jpy:
            continue
        liquid_candidate_count += 1
        preselected.append((_pre_score(tech), ticker, tech))

    preselected.sort(reverse=True, key=lambda item: item[0])
    preselected = preselected[:deep_candidates]

    candidates: list[LiveCandidate] = []
    policy = _data_policy()
    delay_weeks = int(policy["jquants_data_delay_weeks"])
    fundamental_limitation = (
        f"J-Quants {policy['jquants_plan']} の財務データは約{delay_weeks}週間遅延。"
        "リアルタイム材料ではなくshadow検証用の遅延ファンダメンタルとして扱う"
        if delay_weeks > 0
        else "財務データの公開時点と取得可能時点を一次情報で確認する必要がある"
    )

    for _, ticker, tech in preselected:
        code = str(ticker_meta[ticker].get("Code") or "")
        fins = client.financial_summary(code)
        fundamental = _fundamental_features(fins)
        features = InflectionFeatures(
            revenue_growth_yoy_pct=fundamental.get("revenue_growth_yoy_pct"),
            operating_profit_growth_yoy_pct=fundamental.get("operating_profit_growth_yoy_pct"),
            operating_margin_change_pctpt=fundamental.get("operating_margin_change_pctpt"),
            turned_profitable=bool(fundamental.get("turned_profitable")),
            upward_revision_pct=fundamental.get("upward_revision_pct"),
            return_20d_pct=tech.get("return_20d_pct"),
            return_60d_pct=tech.get("return_60d_pct"),
            volume_ratio_20d=tech.get("volume_ratio_20d"),
            breakout_52w=bool(tech.get("breakout_52w")),
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
        if tech.get("breakout_52w"):
            reasons.append("52週高値圏")
        candidates.append(
            LiveCandidate(
                ticker=ticker,
                company_name=str(ticker_meta[ticker].get("CoName") or ticker),
                market=str(ticker_meta[ticker].get("MktNm") or ""),
                classification=classification,
                score=round(score, 3),
                raw_inflection_score=raw.total,
                current_price=float(tech["current_price"]),
                return_5d_pct=tech.get("return_5d_pct"),
                return_20d_pct=tech.get("return_20d_pct"),
                return_60d_pct=tech.get("return_60d_pct"),
                volume_ratio_20d=tech.get("volume_ratio_20d"),
                breakout_52w=bool(tech.get("breakout_52w")),
                avg_turnover_20d_jpy=tech.get("avg_turnover_20d_jpy"),
                reasons=reasons,
                limitations=[fundamental_limitation],
            )
        )

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    counts: dict[str, int] = {}
    for item in candidates:
        counts[item.classification] = counts.get(item.classification, 0) + 1

    latest_price_date = max(latest_dates) if latest_dates else None
    latest_price_date_count = sum(date == latest_price_date for date in latest_dates) if latest_price_date else 0

    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "strategy_version": STRATEGY_VERSION,
        "source_commit_sha": os.getenv("GITHUB_SHA") or "local-or-unknown",
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "shadow",
        "universe": "TSE Prime + Standard + Growth",
        "universe_count": len(tickers),
        "price_data_count": len(prices),
        "technical_usable_count": technical_usable_count,
        "liquid_candidate_count": liquid_candidate_count,
        "latest_price_date": latest_price_date,
        "latest_price_date_count": latest_price_date_count,
        "deep_candidate_count": len(preselected),
        "classification_counts": counts,
        "scan_parameters": {
            "lookback_days": lookback_days,
            "deep_candidates": deep_candidates,
            "min_turnover_jpy": min_turnover_jpy,
            "early_candidate_score": EARLY_CANDIDATE_SCORE,
            "watch_score": WATCH_SCORE,
            "measurable_max_score": LIVE_MEASURABLE_MAX_SCORE,
        },
        "data_policy": policy,
        "runtime_versions": _package_versions(),
        "candidates": [candidate.as_dict() for candidate in candidates],
        "notes": [
            "Known historical winners are not whitelisted or special-cased.",
            "EARLY_CANDIDATE is a research flag, not a buy signal.",
            "Catalyst/news evidence is intentionally excluded until a point-in-time-safe source is connected.",
            "Free-tier delayed fundamentals are suitable for pipeline accumulation, not real-time edge validation.",
        ],
    }
