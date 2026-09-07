from __future__ import annotations

from src.strategy.inflection import InflectionFeatures, classify_signal, score_inflection


def test_strong_inflection_candidate_scores_high() -> None:
    features = InflectionFeatures(
        revenue_growth_yoy_pct=40,
        revenue_growth_acceleration_pct=20,
        operating_profit_growth_yoy_pct=120,
        operating_margin_change_pctpt=5,
        turned_profitable=False,
        upward_revision_pct=25,
        major_order=True,
        capacity_expansion=True,
        strategic_partnership=True,
        new_product_or_business=True,
        return_20d_pct=16,
        return_60d_pct=35,
        volume_ratio_20d=3.2,
        breakout_52w=True,
    )
    score = score_inflection(features)
    assert score.fundamental >= 30
    assert score.catalyst >= 20
    assert score.momentum >= 20
    assert score.total >= 75
    assert classify_signal(score) == "strong_candidate"


def test_risk_penalties_can_downgrade_candidate() -> None:
    features = InflectionFeatures(
        revenue_growth_yoy_pct=35,
        operating_profit_growth_yoy_pct=100,
        upward_revision_pct=20,
        major_order=True,
        return_20d_pct=20,
        return_60d_pct=30,
        volume_ratio_20d=3.0,
        breakout_52w=True,
        return_20d_extreme_pct=100,
        equity_financing_risk=True,
        going_concern_risk=True,
        negative_operating_cashflow=True,
    )
    score = score_inflection(features)
    assert score.risk_penalty == -20.0
    assert score.total < 75


def test_empty_features_do_not_create_signal() -> None:
    score = score_inflection(InflectionFeatures())
    assert score.total == 0.0
    assert classify_signal(score) == "none"
