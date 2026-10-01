"""Market regime of a signal date, from the benchmark's closes up to and including that date.

Two independent readings, both strictly point-in-time (nothing after ``signal_date`` is used):

* trend: is the latest close at or above its 200-session simple average?
* volatility: is the 20-session realised volatility (annualised) above the median of the same measure over
  the 252 sessions before today?

Either is ``unknown`` while there is not enough history.
"""

from __future__ import annotations

import math
from itertools import pairwise
from statistics import median

import pandas as pd

TREND_WINDOW = 200
VOLATILITY_WINDOW = 20
VOLATILITY_BASELINE_SESSIONS = 252
TRADING_DAYS_PER_YEAR = 252
# 20 returns for the first rolling value, 252 prior values for the baseline and today's value: 273 closes.
MIN_VOLATILITY_CLOSES = VOLATILITY_BASELINE_SESSIONS + VOLATILITY_WINDOW + 1


def _until(closes: pd.Series, signal_date: str) -> pd.Series:
    if closes.empty:
        return closes
    return closes[closes.index <= pd.Timestamp(signal_date)]


def trend_regime(closes: pd.Series, signal_date: str) -> str:
    """``up`` when the last close is at or above the 200-session average, ``down`` below it."""
    available = _until(closes, signal_date)
    if len(available) < TREND_WINDOW:
        return "unknown"
    window = available.tail(TREND_WINDOW)
    return "up" if float(available.iloc[-1]) >= float(window.mean()) else "down"


def volatility_regime(closes: pd.Series, signal_date: str) -> str:
    """``high`` when today's 20-session volatility exceeds the median of the prior 252 sessions' values."""
    available = _until(closes, signal_date).tail(MIN_VOLATILITY_CLOSES)
    if len(available) < MIN_VOLATILITY_CLOSES:
        return "unknown"
    prices = [float(value) for value in available]
    if any(not math.isfinite(price) or price <= 0 for price in prices):
        return "unknown"
    returns = pd.Series([math.log(later / earlier) for earlier, later in pairwise(prices)])
    volatility = returns.rolling(VOLATILITY_WINDOW).std() * math.sqrt(TRADING_DAYS_PER_YEAR)
    today = float(volatility.iloc[-1])
    baseline = median(float(value) for value in volatility.iloc[-(VOLATILITY_BASELINE_SESSIONS + 1) : -1])
    return "high" if today > baseline else "normal"


def regime_labels(closes: pd.Series, signal_date: str) -> dict[str, str]:
    return {"trend": trend_regime(closes, signal_date), "volatility": volatility_regime(closes, signal_date)}
