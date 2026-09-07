"""Live Japanese-stock early-inflection scanner.

The scanner is deliberately two-stage:
1) scan all Prime/Standard/Growth stocks with price/volume data;
2) enrich only the strongest early-momentum names with J-Quants fundamentals.

Outputs are research candidates only.  They are not BUY recommendations.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from src.data.jquants_v2_client import JQuantsV2Client
from src.screening.scorer import _fetch_price_data
from src.strategy.inflection import InflectionFeatures, score_inflection

JP_MARKET_CODES = {"0111", "0112", "0113"}  # Prime / Standard / Growth
LIVE_MEASURABLE_MAX_SCORE = 58.0
EARLY_CANDIDATE_SCORE = 70.0
WATCH_SCORE = 52.0


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


def _pre_score(t: dict[str, Any]) -> float:
    r5 = float(t.get("return_5d_pct") or 0.0)
    r20 = float(t.get("return_20d_pct") or 0.0)
    vr = float(t.get("volume_ratio_20d") or 1.0)
    score = max(0.0, min(r5, 12.0)) * 1.0
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


def _fundamental_features(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = sorted(rows, key=lambda r: (str(r.get("DiscDate") or ""), str(r.get("DiscTime") or "")))
    if not rows:
        return {}
    latest = rows[-1]
    period_type = latest.get("CurPerType")
    same_period = [r for r in rows if r.get("CurPerType") == period_type]
    previous = same_period[-2] if len(same_period) >= 2 else None

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
    if sales and prev_sales and op is not None and prev_op is not None:
        margin_change = (op / sales - prev_op / prev_sales) * 100.0

    upward_revision = None
    fiscal_end = latest.get("CurFYEn")
    forecast_rows = [r for r in rows if r.get("CurFYEn") == fiscal_end and _to_float(r.get("FOP")) is not None]
    if len(forecast_rows) >= 2:
        old = _to_float(forecast_rows[-2].get("FOP"))
        new = _to_float(forecast_rows[-1].get("FOP"))
        if old not in (None, 0) and new is not None:
            upward_revision = (new / old - 1.0) * 100.0

    return {
        "revenue_growth_yoy_pct": revenue_growth,
        "operating_profit_growth_yoy_pct": op_growth,
        "operating_margin_change_pctpt": margin_change,
        "turned_profitable": bool(op is not None and prev_op is not None and op > 0 >= prev_op),
        "upward_revision_pct": upward_revision,
        "negative_operating_cashflow": bool((_to_float(latest.get("CFO")) or 0.0) < 0),
        "latest_disclosure_date": latest.get("DiscDate"),
    }


def _normalize_available_score(fundamental: float, momentum: float, risk: float) -> float:
    """Normalize only the inputs that the live pipeline can currently populate.

    Live fundamentals can contribute at most 33 points because revenue acceleration
    is not available yet. Momentum contributes 25, so the measurable positive
    maximum is 58. Catalyst fields are intentionally excluded until a point-in-time
    safe source is connected. Risk penalties still reduce the normalized score.
    """
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

    master = [r for r in client.listed_issues() if str(r.get("Mkt") or "") in JP_MARKET_CODES]
    ticker_meta: dict[str, dict[str, Any]] = {}
    for row in master:
        code = str(row.get("Code") or "")
        if len(code) < 4:
            continue
        ticker_meta[_ticker_from_code(code)] = row

    tickers = sorted(ticker_meta)
    prices = _fetch_price_data(tickers, lookback_days)
    preselected: list[tuple[float, str, dict[str, Any]]] = []
    for ticker, df in prices.items():
        tech = _technical_features(df)
        if not tech:
            continue
        turnover = tech.get("avg_turnover_20d_jpy")
        if turnover is None or float(turnover) < min_turnover_jpy:
            continue
        preselected.append((_pre_score(tech), ticker, tech))
    preselected.sort(reverse=True, key=lambda x: x[0])
    preselected = preselected[:deep_candidates]

    candidates: list[LiveCandidate] = []
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
        limitations = ["J-Quants Freeの財務データは遅延するため、最新材料は別途一次情報確認が必要"]
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
                limitations=limitations,
            )
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    counts: dict[str, int] = {}
    for item in candidates:
        counts[item.classification] = counts.get(item.classification, 0) + 1

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "shadow",
        "universe": "TSE Prime + Standard + Growth",
        "universe_count": len(tickers),
        "price_data_count": len(prices),
        "deep_candidate_count": len(preselected),
        "classification_counts": counts,
        "candidates": [c.as_dict() for c in candidates],
        "notes": [
            "Known historical winners are not whitelisted or special-cased.",
            "EARLY_CANDIDATE is a research flag, not a buy signal.",
            "Catalyst/news evidence is intentionally excluded until a point-in-time-safe source is connected.",
        ],
    }
