"""Ensemble controller: combines predictions from multiple models.

Currently delegates to Prophet only. When LightGBM or other models
become available, this module handles weighted averaging and
conflict resolution.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

from src.prediction.base import PredictionModel
from src.prediction.calibrator import apply_guardrail
from src.prediction.prophet_model import ProphetModel, compute_prob_up, fetch_history

logger = structlog.get_logger(__name__)


def _get_active_models(config: dict[str, Any]) -> list[PredictionModel]:
    """Instantiate active prediction models based on config.

    Args:
        config: Full app config dict.

    Returns:
        List of active PredictionModel instances.
    """
    models: list[PredictionModel] = []

    model_name = config.get("prediction", {}).get("model", "prophet")

    if model_name in ("prophet", "ensemble"):
        models.append(ProphetModel())

    if model_name == "ensemble":
        from src.prediction.lightgbm_model import LightGBMModel

        models.append(LightGBMModel())

    if not models:
        models.append(ProphetModel())

    return models


def _weighted_average(
    predictions: list[dict[str, Any]],
    weights: dict[str, float] | None = None,
) -> dict[str, Any] | None:
    """Compute weighted average of predictions from multiple models.

    Args:
        predictions: Non-empty list of prediction dicts.
        weights: Model name -> weight mapping. Equal weights if None.

    Returns:
        Merged prediction dict, or None if no valid predictions.
    """
    valid = [p for p in predictions if p is not None]
    if not valid:
        return None
    if len(valid) == 1:
        return valid[0]

    if weights is None:
        w = 1.0 / len(valid)
        weight_map = {p["model"]: w for p in valid}
    else:
        weight_map = weights

    total_weight = sum(weight_map.get(p["model"], 0.0) for p in valid)
    if total_weight <= 0:
        total_weight = len(valid)
        weight_map = {p["model"]: 1.0 for p in valid}

    avg_fields = [
        "predicted_price", "predicted_change_pct",
        "ci_lower", "ci_upper", "ci_pct",
    ]

    merged = dict(valid[0])
    for field in avg_fields:
        weighted_sum = sum(
            p.get(field, 0.0) * weight_map.get(p["model"], 1.0)
            for p in valid
        )
        merged[field] = round(weighted_sum / total_weight, 2)

    merged["prob_up"] = compute_prob_up(
        merged["predicted_change_pct"], merged["ci_pct"]
    )
    merged["model"] = "+".join(p["model"] for p in valid)
    return merged


def predict(
    screened_df: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    """Run ensemble prediction on screened stocks.

    Args:
        screened_df: DataFrame with 'ticker' column from screening.
        config: Full application config dict.

    Returns:
        DataFrame of bullish predictions sorted by predicted_change_pct desc.
    """
    pred_cfg = config.get("prediction", {})
    history_days = pred_cfg.get("history_days", 90)
    forecast_days = pred_cfg.get("forecast_days", 5)
    prophet_cfg = config.get("prediction", {}).get("prophet", {})
    guardrail_cfg = config.get("prediction", {}).get("guardrail", {})
    ensemble_weights = pred_cfg.get("ensemble", {}).get("weights", None)

    models = _get_active_models(config)
    tickers = screened_df["ticker"].tolist()
    logger.info("prediction_start", n_tickers=len(tickers), models=[m.name for m in models])

    results: list[dict[str, Any]] = []
    for ticker in tickers:
        history = fetch_history(ticker, history_days)
        if history.empty:
            logger.warning("empty_history", ticker=ticker)
            continue

        model_predictions: list[dict[str, Any]] = []
        for model in models:
            model_cfg = prophet_cfg if model.name == "prophet" else {}
            pred = model.predict_stock(ticker, history, forecast_days, model_cfg)
            if pred is not None:
                model_predictions.append(pred)

        merged = _weighted_average(model_predictions, ensemble_weights)
        if merged is None:
            continue

        guardrail = apply_guardrail(merged["predicted_change_pct"], guardrail_cfg)
        merged["predicted_change_pct_clipped"] = guardrail["predicted_change_pct_clipped"]
        merged["sanity_flags"] = guardrail["sanity_flags"]

        results.append(merged)

    if not results:
        logger.warning("no_predictions_generated")
        return pd.DataFrame()

    result_df = pd.DataFrame(results)

    bullish_df = result_df[result_df["predicted_change_pct"] > 0].copy()
    bullish_df = bullish_df.sort_values("predicted_change_pct", ascending=False)
    bullish_df = bullish_df.reset_index(drop=True)

    logger.info(
        "prediction_complete",
        total=len(result_df),
        bullish=len(bullish_df),
    )
    return bullish_df
