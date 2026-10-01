from __future__ import annotations

import inspect
import math

import pandas as pd
import pytest

import src.evaluation.inflection_backtest as backtest
from src.evaluation import explosion
from src.evaluation.inflection_backtest import TradeResult, summarize_trades
from src.evaluation.inflection_learning import EXPLOSION_MAX_RETURN_PCT
from src.evaluation.inflection_recall import compute_tracked_pool_explosion_recall


def _closes(returns: list[float], start: str = "2026-01-02", base: float = 100.0) -> pd.Series:
    prices = [base]
    for value in returns:
        prices.append(prices[-1] * math.exp(value))
    return pd.Series(prices, index=pd.date_range(start, periods=len(prices), freq="B"), dtype=float)


def test_definitions_keep_their_pre_consolidation_values() -> None:
    assert explosion.HORIZON_MAX_RETURN_PCT == {5: 15.0, 20: 25.0, 60: 40.0, 120: 60.0}
    assert explosion.FIXED_MAX_RETURN_PCT == 50.0
    assert (explosion.TRACKED_POOL_THRESHOLD_PCT, explosion.TRACKED_POOL_SEARCH_DAYS) == (50.0, 252)
    assert (explosion.VOL_EXPLOSION_K, explosion.VOL_LOOKBACK_SESSIONS) == (3.0, 60)


def test_consumers_read_the_shared_constants() -> None:
    assert EXPLOSION_MAX_RETURN_PCT is explosion.HORIZON_MAX_RETURN_PCT
    defaults = inspect.signature(compute_tracked_pool_explosion_recall).parameters
    assert defaults["explosion_threshold_pct"].default == explosion.TRACKED_POOL_THRESHOLD_PCT
    assert defaults["search_horizon_days"].default == explosion.TRACKED_POOL_SEARCH_DAYS


def test_backtest_flags_use_the_shared_fixed_bar(monkeypatch: pytest.MonkeyPatch) -> None:
    trade = TradeResult(
        "1111.T", "2026-01-05", 80.0, "2026-01-06", 100.0, "2026-04-06", 120.0, 20.0, 19.8, 20.0, -5.0, False
    )

    assert summarize_trades([trade])["explosive_50pct_count"] == 0
    monkeypatch.setattr(backtest, "FIXED_MAX_RETURN_PCT", 10.0)
    assert summarize_trades([trade])["explosive_50pct_count"] == 1


def test_definitions_are_exposed_for_reports() -> None:
    definitions = explosion.explosion_definitions()
    assert definitions["horizon_max_return_pct"]["h60"] == 40.0
    assert definitions["tracked_pool"] == {"close_gain_pct": 50.0, "search_sessions": 252}
    assert definitions["volatility_normalised"]["k"] == 3.0


def test_realized_volatility_matches_the_sample_std_of_log_returns() -> None:
    closes = _closes([0.01, -0.01] * 30)  # 61 closes, 60 returns of +-1%

    sigma = explosion.realized_volatility(closes, str(closes.index[-1].date()))

    assert sigma == pytest.approx(math.sqrt(60 * 0.01**2 / 59))


def test_realized_volatility_ignores_prices_after_the_signal_date() -> None:
    closes = _closes([0.01, -0.01] * 40)
    signal_date = str(closes.index[70].date())
    baseline = explosion.realized_volatility(closes, signal_date)

    shocked = closes.copy()
    shocked.iloc[71:] *= 5.0  # a later spike must not change sigma on the signal date

    assert baseline is not None and explosion.realized_volatility(shocked, signal_date) == baseline


def test_realized_volatility_needs_61_closes_and_a_moving_price() -> None:
    enough = _closes([0.01, -0.01] * 30)
    assert explosion.realized_volatility(enough.iloc[1:], str(enough.index[-1].date())) is None  # only 60 closes
    flat = pd.Series(100.0, index=enough.index)
    assert explosion.realized_volatility(flat, str(flat.index[-1].date())) is None
    assert explosion.realized_volatility(enough.iloc[:0], "2026-06-01") is None
    with_gap = enough.copy()
    with_gap.iloc[10] = float("nan")
    assert explosion.realized_volatility(with_gap, str(enough.index[-1].date())) is None


def test_the_same_max_return_is_explosive_for_a_calm_stock_only() -> None:
    calm, wild = 0.005, 0.05

    assert explosion.is_vol_explosion(30.0, calm, 20) is True
    assert explosion.is_vol_explosion(30.0, wild, 20) is False


@pytest.mark.parametrize(("max_return", "sigma"), [(None, 0.01), (30.0, None), (None, None)])
def test_vol_explosion_is_undecided_when_an_input_is_missing(max_return: float | None, sigma: float | None) -> None:
    assert explosion.is_vol_explosion(max_return, sigma, 20) is None


def test_vol_explosion_handles_a_total_loss() -> None:
    assert explosion.is_vol_explosion(-100.0, 0.01, 20) is False
