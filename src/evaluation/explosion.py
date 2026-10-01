"""Single home for what "explosive" means in each evaluation, so the definitions cannot drift.

The three definitions answer different questions and are intentionally NOT interchangeable:

* ``HORIZON_MAX_RETURN_PCT`` (learning): the best close-to-entry return reached *during the holding
  period* of a given horizon. Used for factor statistics and promotion.
* ``FIXED_MAX_RETURN_PCT`` (backtest ``explosive_50pct``): the best return reached during the
  holding period, one fixed bar for every horizon.
* ``TRACKED_POOL_*`` (recall): a *close* at least +50% above the first observed close within a
  252-session search window, regardless of any holding period.

The volatility-normalised definition (``VOL_EXPLOSION_K``) is diagnostic only and never feeds promotion.
"""

from __future__ import annotations

import math
from itertools import pairwise
from statistics import stdev
from typing import Any

import pandas as pd

HORIZON_MAX_RETURN_PCT: dict[int, float] = {5: 15.0, 20: 25.0, 60: 40.0, 120: 60.0}
FIXED_MAX_RETURN_PCT = 50.0
TRACKED_POOL_THRESHOLD_PCT = 50.0
TRACKED_POOL_SEARCH_DAYS = 252
VOL_EXPLOSION_K = 3.0
VOL_LOOKBACK_SESSIONS = 60


def explosion_definitions() -> dict[str, Any]:
    """The definitions in force, for embedding in reports."""
    return {
        "horizon_max_return_pct": {f"h{horizon}": value for horizon, value in HORIZON_MAX_RETURN_PCT.items()},
        "fixed_max_return_pct": FIXED_MAX_RETURN_PCT,
        "tracked_pool": {
            "close_gain_pct": TRACKED_POOL_THRESHOLD_PCT,
            "search_sessions": TRACKED_POOL_SEARCH_DAYS,
        },
        "volatility_normalised": {
            "k": VOL_EXPLOSION_K,
            "lookback_sessions": VOL_LOOKBACK_SESSIONS,
            "rule": "log(1 + max_return) >= k * sigma_daily_log_return * sqrt(horizon); diagnostic only",
        },
    }


def realized_volatility(
    closes: pd.Series,
    signal_date: str,
    lookback: int = VOL_LOOKBACK_SESSIONS,
) -> float | None:
    """Sample std of daily log returns over the ``lookback`` sessions ending on ``signal_date``.

    ``closes`` is a positive-price series with a tz-naive DatetimeIndex. Only closes dated on or
    before ``signal_date`` are used, so later prices cannot leak in. ``None`` when there are fewer
    than ``lookback + 1`` closes or the series is flat (a zero sigma makes the rule meaningless).
    """
    window = closes[closes.index <= pd.Timestamp(signal_date)].tail(lookback + 1)
    prices = [float(value) for value in window if math.isfinite(float(value)) and float(value) > 0]
    if len(window) < lookback + 1 or len(prices) != len(window):
        return None
    sigma = stdev([math.log(later / earlier) for earlier, later in pairwise(prices)])
    return sigma if math.isfinite(sigma) and sigma > 0 else None


def is_vol_explosion(
    max_return_pct: float | None,
    sigma: float | None,
    horizon: int,
    k: float = VOL_EXPLOSION_K,
) -> bool | None:
    """Whether the best return during ``horizon`` sessions exceeds ``k`` daily-sigma random-walk moves.

    ``None`` (not False) when it cannot be decided: a missing maximum return (horizon not
    complete) or a missing sigma (short history).
    """
    if max_return_pct is None or sigma is None:
        return None
    if max_return_pct <= -100.0:
        return False
    return math.log1p(max_return_pct / 100.0) >= k * sigma * math.sqrt(horizon)
