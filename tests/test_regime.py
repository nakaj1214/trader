from __future__ import annotations

import math

import pandas as pd
import pytest

from src.evaluation.regime import (
    MIN_VOLATILITY_CLOSES,
    regime_labels,
    trend_regime,
    volatility_regime,
)


def closes_from(returns: list[float], start: str = "2024-01-04", base: float = 100.0) -> pd.Series:
    prices = [base]
    for value in returns:
        prices.append(prices[-1] * math.exp(value))
    return pd.Series(prices, index=pd.bdate_range(start, periods=len(prices)), dtype=float)


def last_day(closes: pd.Series) -> str:
    return str(closes.index[-1].date())


def alternating(amplitude: float, count: int) -> list[float]:
    return [amplitude if i % 2 == 0 else -amplitude for i in range(count)]


# --- trend ----------------------------------------------------------------------------------------


def test_trend_is_up_above_and_down_below_the_200_session_average() -> None:
    rising = closes_from([0.002] * 250)
    falling = closes_from([-0.002] * 250)

    assert trend_regime(rising, last_day(rising)) == "up"
    assert trend_regime(falling, last_day(falling)) == "down"


def test_trend_at_exactly_the_average_counts_as_up() -> None:
    flat = pd.Series(100.0, index=pd.bdate_range("2024-01-04", periods=250))

    assert trend_regime(flat, last_day(flat)) == "up"


def test_trend_needs_200_sessions() -> None:
    closes = closes_from([0.002] * 250)

    assert trend_regime(closes.iloc[:199], last_day(closes.iloc[:199])) == "unknown"
    assert trend_regime(closes.iloc[:200], last_day(closes.iloc[:200])) == "up"


# --- volatility -------------------------------------------------------------------------------------


def test_volatility_is_high_when_recent_moves_dwarf_the_prior_year() -> None:
    closes = closes_from(alternating(0.005, 253) + alternating(0.03, 20))

    assert volatility_regime(closes, last_day(closes)) == "high"


def test_volatility_is_normal_when_recent_moves_are_calmer_than_the_prior_year() -> None:
    closes = closes_from(alternating(0.03, 253) + alternating(0.005, 20))

    assert volatility_regime(closes, last_day(closes)) == "normal"


def test_volatility_of_a_flat_market_is_normal_not_high() -> None:
    flat = pd.Series(100.0, index=pd.bdate_range("2024-01-04", periods=300))

    assert volatility_regime(flat, last_day(flat)) == "normal"


def test_volatility_needs_273_closes() -> None:
    closes = closes_from(alternating(0.01, 300))
    short = closes.iloc[: MIN_VOLATILITY_CLOSES - 1]
    enough = closes.iloc[:MIN_VOLATILITY_CLOSES]

    assert MIN_VOLATILITY_CLOSES == 273
    assert volatility_regime(short, last_day(short)) == "unknown"
    assert volatility_regime(enough, last_day(enough)) in {"high", "normal"}


def test_volatility_is_unknown_for_a_non_positive_price() -> None:
    closes = closes_from(alternating(0.01, 300))
    broken = closes.copy()
    broken.iloc[-5] = 0.0

    assert volatility_regime(broken, last_day(broken)) == "unknown"


# --- no look-ahead, empty input ---------------------------------------------------------------------


def test_prices_after_the_signal_date_never_change_the_regime() -> None:
    closes = closes_from(alternating(0.005, 253) + alternating(0.03, 20) + [0.002] * 40)
    signal_date = str(closes.index[290].date())
    before = regime_labels(closes, signal_date)

    shocked = closes.copy()
    shocked.iloc[291:] *= 0.1  # a later crash must not leak into the reading on the signal date

    assert regime_labels(shocked, signal_date) == before
    assert before == {"trend": "up", "volatility": "high"}


def test_empty_benchmark_gives_unknown() -> None:
    assert regime_labels(pd.Series(dtype=float), "2026-01-05") == {"trend": "unknown", "volatility": "unknown"}


@pytest.mark.parametrize("signal_date", ["2020-01-01", "2024-01-04"])
def test_a_signal_date_before_enough_history_is_unknown(signal_date: str) -> None:
    closes = closes_from([0.001] * 300)

    assert regime_labels(closes, signal_date) == {"trend": "unknown", "volatility": "unknown"}
