"""Tests for src.screening modules (universe, filters, indicators, scorer)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.screening.filters import (
    FilterChain,
    GoldenCrossFilter,
    LiquidityFilter,
    MarketCapFilter,
)
from src.screening.indicators import (
    calc_52w_high_momentum,
    calc_adx,
    calc_bollinger_position,
    calc_macd_signal,
    calc_price_change_1m,
    calc_rsi,
    calc_volume_trend,
)
from src.screening.scorer import score_stocks, select_top_n
from src.screening.universe import load_universe


class TestUniverse:

    def test_load_sp500(self) -> None:
        tickers = load_universe("sp500")
        assert len(tickers) > 0
        assert all(isinstance(t, str) for t in tickers)

    def test_load_nonexistent(self) -> None:
        tickers = load_universe("nonexistent_market")
        assert tickers == []

    def test_no_duplicates(self) -> None:
        tickers = load_universe("sp500")
        assert len(tickers) == len(set(tickers))


class TestMarketCapFilter:

    def test_filters_below_threshold(self) -> None:
        df = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "market_cap": [5e9, 15e9, None],
        })
        f = MarketCapFilter()
        result = f.apply(df, {"filters": {"market_cap": {"min": 10e9}}})
        assert len(result) == 2  # B (above) + C (None retained)

    def test_zero_threshold_passes_all(self) -> None:
        df = pd.DataFrame({"ticker": ["A"], "market_cap": [1.0]})
        f = MarketCapFilter()
        result = f.apply(df, {"filters": {"market_cap": {"min": 0}}})
        assert len(result) == 1


class TestLiquidityFilter:

    def test_filters_illiquid(self) -> None:
        df = pd.DataFrame({
            "ticker": ["AAPL", "TINY"],
            "avg_dollar_volume": [5_000_000, 100],
        })
        f = LiquidityFilter()
        result = f.apply(df, {"filters": {"liquidity": {
            "min_dollar_volume_us": 1_000_000,
            "min_dollar_volume_jp": 0,
        }}})
        assert len(result) == 1
        assert result.iloc[0]["ticker"] == "AAPL"


class TestGoldenCrossFilter:

    def test_filters_death_cross(self) -> None:
        df = pd.DataFrame({
            "ticker": ["A", "B", "C"],
            "golden_cross": [1.0, 0.0, None],
        })
        f = GoldenCrossFilter()
        result = f.apply(df, {"filters": {"golden_cross": {"enabled": True}}})
        assert len(result) == 2  # A (golden) + C (None retained)

    def test_disabled_passes_all(self) -> None:
        df = pd.DataFrame({"ticker": ["A"], "golden_cross": [0.0]})
        f = GoldenCrossFilter()
        result = f.apply(df, {"filters": {"golden_cross": {"enabled": False}}})
        assert len(result) == 1


class TestFilterChain:

    def test_applies_all_filters(self) -> None:
        df = pd.DataFrame({
            "ticker": ["A", "B"],
            "market_cap": [100e9, 1e6],
            "avg_dollar_volume": [5e6, 5e6],
            "golden_cross": [1.0, 1.0],
        })
        chain = FilterChain()
        result = chain.apply(df, {"filters": {
            "market_cap": {"min": 10e9},
            "liquidity": {"min_dollar_volume_us": 0, "min_dollar_volume_jp": 0},
            "golden_cross": {"enabled": True},
        }})
        assert len(result) == 1


class TestIndicators:

    @pytest.fixture
    def price_df(self) -> pd.DataFrame:
        dates = pd.date_range("2024-01-01", periods=60, freq="B")
        return pd.DataFrame({
            "Open": [100.0 + i * 0.5 for i in range(60)],
            "High": [101.0 + i * 0.5 for i in range(60)],
            "Low": [99.0 + i * 0.5 for i in range(60)],
            "Close": [100.0 + i * 0.5 for i in range(60)],
            "Volume": [1_000_000] * 60,
        }, index=dates)

    def test_price_change_1m(self, price_df: pd.DataFrame) -> None:
        result = calc_price_change_1m(price_df)
        assert not result.empty
        assert result.iloc[0] > 0

    def test_volume_trend(self, price_df: pd.DataFrame) -> None:
        result = calc_volume_trend(price_df)
        assert not result.empty

    def test_rsi(self, price_df: pd.DataFrame) -> None:
        result = calc_rsi(price_df)
        assert not result.empty
        assert 0 <= result.iloc[0] <= 100

    def test_macd_signal(self, price_df: pd.DataFrame) -> None:
        result = calc_macd_signal(price_df)
        assert not result.empty
        assert result.iloc[0] in (0.0, 1.0)

    def test_bollinger_position(self, price_df: pd.DataFrame) -> None:
        result = calc_bollinger_position(price_df)
        assert not result.empty
        assert 0 <= result.iloc[0] <= 1

    def test_adx(self, price_df: pd.DataFrame) -> None:
        result = calc_adx(price_df)
        assert not result.empty
        assert 0 <= result.iloc[0] <= 1

    def test_52w_high_momentum(self, price_df: pd.DataFrame) -> None:
        result = calc_52w_high_momentum(price_df)
        assert not result.empty
        assert 0 < result.iloc[0] <= 1

    def test_insufficient_data(self) -> None:
        short = pd.DataFrame({"Close": [1, 2, 3]})
        assert calc_rsi(short).empty
        assert calc_price_change_1m(short).empty


class TestScorer:

    def test_score_stocks(self) -> None:
        indicators = pd.DataFrame({
            "price_change_1m": [0.05, 0.10],
            "volume_trend": [0.5, 0.3],
            "rsi": [55.0, 45.0],
            "macd_bullish": [1.0, 0.0],
            "bb_pos": [0.7, 0.3],
            "adx_score": [0.6, 0.4],
            "fifty2w_score": [0.9, 0.8],
        }, index=["AAPL", "MSFT"])

        weights = {
            "price_change_1m": 0.20,
            "volume_trend": 0.15,
            "rsi_score": 0.15,
            "macd_signal": 0.15,
            "fifty2w_score": 0.15,
            "bb_position": 0.10,
            "adx_score": 0.10,
        }
        scores = score_stocks(indicators, weights)
        assert len(scores) == 2
        assert scores["AAPL"] > scores["MSFT"]

    def test_select_top_n(self) -> None:
        scores = pd.Series({"A": 0.9, "B": 0.7, "C": 0.8})
        top = select_top_n(scores, 2)
        assert top == ["A", "C"]

    def test_select_top_n_empty(self) -> None:
        assert select_top_n(pd.Series(dtype=float), 5) == []
