"""Interpretable 'inflection' strategy scoring for Japanese short-term candidates.

The scorer intentionally uses explicit inputs and fixed weights.  It is designed
for point-in-time backtests where every input must have been public at signal time.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class InflectionFeatures:
    revenue_growth_yoy_pct: float | None = None
    revenue_growth_acceleration_pct: float | None = None
    operating_profit_growth_yoy_pct: float | None = None
    operating_margin_change_pctpt: float | None = None
    turned_profitable: bool = False
    upward_revision_pct: float | None = None
    major_order: bool = False
    capacity_expansion: bool = False
    strategic_partnership: bool = False
    new_product_or_business: bool = False
    return_20d_pct: float | None = None
    return_60d_pct: float | None = None
    volume_ratio_20d: float | None = None
    breakout_52w: bool = False
    return_20d_extreme_pct: float | None = None
    equity_financing_risk: bool = False
    going_concern_risk: bool = False
    negative_operating_cashflow: bool = False


@dataclass(frozen=True)
class InflectionScore:
    fundamental: float
    catalyst: float
    momentum: float
    risk_penalty: float
    total: float
    details: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _positive_score(value: float | None, thresholds: tuple[tuple[float, float], ...]) -> float:
    if value is None:
        return 0.0
    score = 0.0
    for threshold, points in thresholds:
        if value >= threshold:
            score = points
    return score


def score_inflection(features: InflectionFeatures) -> InflectionScore:
    details: dict[str, float] = {}

    details["revenue_growth"] = _positive_score(
        features.revenue_growth_yoy_pct,
        ((10.0, 3.0), (20.0, 5.0), (35.0, 7.0)),
    )
    details["revenue_acceleration"] = _positive_score(
        features.revenue_growth_acceleration_pct,
        ((5.0, 3.0), (10.0, 5.0), (20.0, 7.0)),
    )
    details["operating_profit_growth"] = _positive_score(
        features.operating_profit_growth_yoy_pct,
        ((20.0, 4.0), (50.0, 7.0), (100.0, 10.0)),
    )
    details["margin_improvement"] = _positive_score(
        features.operating_margin_change_pctpt,
        ((1.0, 2.0), (3.0, 4.0), (5.0, 6.0)),
    )
    details["turned_profitable"] = 5.0 if features.turned_profitable else 0.0
    details["upward_revision"] = _positive_score(
        features.upward_revision_pct,
        ((5.0, 2.0), (10.0, 3.0), (20.0, 5.0)),
    )
    fundamental = min(40.0, sum(details[key] for key in (
        "revenue_growth",
        "revenue_acceleration",
        "operating_profit_growth",
        "margin_improvement",
        "turned_profitable",
        "upward_revision",
    )))

    details["major_order"] = 8.0 if features.major_order else 0.0
    details["capacity_expansion"] = 6.0 if features.capacity_expansion else 0.0
    details["strategic_partnership"] = 5.0 if features.strategic_partnership else 0.0
    details["new_product_or_business"] = 4.0 if features.new_product_or_business else 0.0
    catalyst = min(25.0, sum(details[key] for key in (
        "major_order",
        "capacity_expansion",
        "strategic_partnership",
        "new_product_or_business",
    )))

    details["return_20d"] = _positive_score(
        features.return_20d_pct,
        ((3.0, 3.0), (8.0, 5.0), (15.0, 6.0)),
    )
    details["return_60d"] = _positive_score(
        features.return_60d_pct,
        ((5.0, 3.0), (15.0, 5.0), (30.0, 6.0)),
    )
    details["volume_ratio"] = _positive_score(
        features.volume_ratio_20d,
        ((1.5, 3.0), (2.0, 5.0), (3.0, 7.0)),
    )
    details["breakout_52w"] = 6.0 if features.breakout_52w else 0.0
    momentum = min(25.0, sum(details[key] for key in (
        "return_20d", "return_60d", "volume_ratio", "breakout_52w"
    )))

    risk_penalty = 0.0
    if features.return_20d_extreme_pct is not None and features.return_20d_extreme_pct >= 80.0:
        details["extreme_runup_penalty"] = -6.0
        risk_penalty -= 6.0
    else:
        details["extreme_runup_penalty"] = 0.0
    if features.equity_financing_risk:
        details["equity_financing_penalty"] = -6.0
        risk_penalty -= 6.0
    else:
        details["equity_financing_penalty"] = 0.0
    if features.going_concern_risk:
        details["going_concern_penalty"] = -10.0
        risk_penalty -= 10.0
    else:
        details["going_concern_penalty"] = 0.0
    if features.negative_operating_cashflow:
        details["negative_cfo_penalty"] = -3.0
        risk_penalty -= 3.0
    else:
        details["negative_cfo_penalty"] = 0.0
    risk_penalty = max(-20.0, risk_penalty)

    total = max(0.0, min(100.0, fundamental + catalyst + momentum + risk_penalty))
    return InflectionScore(
        fundamental=round(fundamental, 3),
        catalyst=round(catalyst, 3),
        momentum=round(momentum, 3),
        risk_penalty=round(risk_penalty, 3),
        total=round(total, 3),
        details=details,
    )


def classify_signal(score: InflectionScore) -> str:
    if score.total >= 75:
        return "strong_candidate"
    if score.total >= 60:
        return "watch"
    return "none"
