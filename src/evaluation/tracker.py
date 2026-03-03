"""Prediction tracker: evaluate past predictions against actual prices.

Migrated from src/tracker.py. Uses Repository instead of Google Sheets.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import structlog

from src.data.repository import PredictionRepository, create_database

logger = structlog.get_logger(__name__)


def evaluation_date(prediction_date: str, forecast_days: int = 5) -> datetime:
    """Compute the evaluation date by advancing business days.

    Args:
        prediction_date: Prediction date string (YYYY-MM-DD).
        forecast_days: Number of business days to advance.

    Returns:
        Evaluation datetime.
    """
    pred_dt = datetime.strptime(prediction_date, "%Y-%m-%d")
    current = pred_dt
    bdays_added = 0
    while bdays_added < forecast_days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            bdays_added += 1
    return current


def fetch_close_at(
    tickers: list[str],
    target_date: str,
    forecast_days: int = 5,
) -> dict[str, float]:
    """Fetch closing prices N business days after the prediction date.

    Uses yfinance to get actual trading day data, which correctly
    handles holidays and market closures.

    Args:
        tickers: List of ticker symbols.
        target_date: Prediction date (YYYY-MM-DD).
        forecast_days: Number of business days after prediction.

    Returns:
        Mapping of ticker -> actual closing price.
    """
    if not tickers:
        return {}

    import yfinance as yf

    pred_dt = datetime.strptime(target_date, "%Y-%m-%d")
    start = pred_dt
    end = pred_dt + timedelta(days=forecast_days * 2 + 14)

    prices: dict[str, float] = {}
    batch_str = " ".join(tickers)
    try:
        df = yf.download(batch_str, start=start, end=end, progress=False)
    except Exception:
        logger.exception("close_price_fetch_error", target_date=target_date)
        return {}

    for ticker in tickers:
        try:
            if len(tickers) == 1:
                close = df["Close"].squeeze().dropna()
            else:
                close = df[ticker]["Close"].squeeze().dropna()
            if close.empty:
                continue
            trading_after = close[close.index > pd.Timestamp(pred_dt)]
            if len(trading_after) >= forecast_days:
                prices[ticker] = float(trading_after.iloc[forecast_days - 1])
        except (KeyError, TypeError):
            continue

    logger.info(
        "close_prices_fetched",
        target_date=target_date,
        forecast_days=forecast_days,
        fetched=len(prices),
        total=len(tickers),
    )
    return prices


def track(config: dict[str, Any]) -> dict[str, Any]:
    """Evaluate pending predictions and update their actual prices.

    Reads pending predictions from the DB, fetches actual prices,
    and updates records with actual_price, is_hit, and status.

    Args:
        config: Application configuration dict.

    Returns:
        Accuracy statistics dict from repository.
    """
    db_path = config.get("data", {}).get("db_path", "data/trader.db")
    forecast_days = config.get("prediction", {}).get("forecast_days", 5)

    session_factory = create_database(db_path)

    with session_factory() as session:
        repo = PredictionRepository(session)
        pending = repo.find_pending_tracking()

        if not pending:
            logger.info("no_pending_predictions")
            return repo.get_accuracy_stats()

        dates = sorted({r.date for r in pending})
        target_date = dates[0]
        target_records = [r for r in pending if r.date == target_date]

        tickers = list({r.ticker for r in target_records})
        logger.info(
            "tracking_start",
            target_date=target_date,
            n_records=len(target_records),
            forecast_days=forecast_days,
        )

        actual_prices = fetch_close_at(tickers, target_date, forecast_days)

        updated = 0
        for record in target_records:
            actual_price = actual_prices.get(record.ticker)
            if actual_price is None:
                repo.update_tracking(record.id, 0.0, None)
                continue

            is_hit = actual_price > record.current_price if record.current_price else None
            repo.update_tracking(record.id, actual_price, is_hit)
            updated += 1

        session.commit()
        logger.info("tracking_complete", updated=updated, total=len(target_records))

        return repo.get_accuracy_stats()
