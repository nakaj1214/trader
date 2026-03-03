"""Technical indicator calculations for stock screening.

Each function takes a price DataFrame and returns a single-element
Series with the computed indicator value (or an empty Series on failure).
"""

from __future__ import annotations

import pandas as pd
import ta
import structlog

logger = structlog.get_logger(__name__)

MIN_ROWS_REQUIRED: int = 14
PRICE_CHANGE_WINDOW: int = 22
VOLUME_TREND_WINDOW: int = 42


def calc_price_change_1m(prices: pd.DataFrame) -> pd.Series:
    """Calculate 1-month price change rate (~22 trading days)."""
    close = _extract_close(prices)
    if close is None or len(close) < MIN_ROWS_REQUIRED:
        return pd.Series(dtype=float)

    if len(close) >= PRICE_CHANGE_WINDOW + 1:
        base = float(close.iloc[-(PRICE_CHANGE_WINDOW + 1)])
    else:
        base = float(close.iloc[0])

    if base == 0.0:
        return pd.Series([0.0], index=[close.index[-1]])

    change = (float(close.iloc[-1]) - base) / base
    return pd.Series([change], index=[close.index[-1]])


def calc_volume_trend(prices: pd.DataFrame) -> pd.Series:
    """Calculate volume trend by comparing recent vs. earlier average volume."""
    if "Volume" not in prices.columns:
        return pd.Series(dtype=float)

    volume = prices["Volume"].squeeze()
    if len(volume) < MIN_ROWS_REQUIRED:
        return pd.Series(dtype=float)

    vol_window = volume.iloc[-VOLUME_TREND_WINDOW:] if len(volume) >= VOLUME_TREND_WINDOW else volume
    mid = len(vol_window) // 2
    first_mean = float(vol_window.iloc[:mid].mean())

    if first_mean <= 0.0:
        return pd.Series([0.0], index=[prices.index[-1]])

    second_mean = float(vol_window.iloc[mid:].mean())
    trend = (second_mean - first_mean) / first_mean
    return pd.Series([trend], index=[prices.index[-1]])


def calc_rsi(prices: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate the Relative Strength Index (RSI)."""
    close = _extract_close(prices)
    if close is None or len(close) < period + 1:
        return pd.Series(dtype=float)

    rsi_series = ta.momentum.RSIIndicator(close, window=period).rsi()
    latest = rsi_series.iloc[-1]

    if pd.isna(latest):
        return pd.Series(dtype=float)

    return pd.Series([float(latest)], index=[close.index[-1]])


def calc_macd_signal(prices: pd.DataFrame) -> pd.Series:
    """Calculate binary MACD bullish signal (1.0 = bullish, 0.0 = bearish)."""
    close = _extract_close(prices)
    if close is None or len(close) < 35:
        return pd.Series(dtype=float)

    macd_ind = ta.trend.MACD(close)
    macd_val = macd_ind.macd().iloc[-1]
    signal_val = macd_ind.macd_signal().iloc[-1]

    if pd.isna(macd_val) or pd.isna(signal_val):
        return pd.Series(dtype=float)

    bullish = 1.0 if float(macd_val) > float(signal_val) else 0.0
    return pd.Series([bullish], index=[close.index[-1]])


def calc_bollinger_position(prices: pd.DataFrame) -> pd.Series:
    """Calculate price position within Bollinger Bands [0, 1]."""
    close = _extract_close(prices)
    if close is None or len(close) < 20:
        return pd.Series(dtype=float)

    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    upper = float(bb.bollinger_hband().iloc[-1])
    lower = float(bb.bollinger_lband().iloc[-1])
    current = float(close.iloc[-1])

    band_width = upper - lower
    if band_width <= 0.0:
        return pd.Series([0.5], index=[close.index[-1]])

    position = max(0.0, min((current - lower) / band_width, 1.0))
    return pd.Series([position], index=[close.index[-1]])


def calc_adx(prices: pd.DataFrame) -> pd.Series:
    """Calculate ADX trend strength score normalized to [0, 1]."""
    if "High" not in prices.columns or "Low" not in prices.columns:
        return pd.Series(dtype=float)

    close = _extract_close(prices)
    if close is None or len(close) < 15:
        return pd.Series(dtype=float)

    adx_ind = ta.trend.ADXIndicator(
        high=prices["High"].squeeze(),
        low=prices["Low"].squeeze(),
        close=close,
        window=14,
    )
    adx_val = adx_ind.adx().iloc[-1]

    if pd.isna(adx_val):
        return pd.Series([0.5], index=[close.index[-1]])

    score = min(float(adx_val) / 50.0, 1.0)
    return pd.Series([score], index=[close.index[-1]])


def calc_52w_high_momentum(prices: pd.DataFrame) -> pd.Series:
    """Calculate 52-week high momentum (current / 52-week high)."""
    close = _extract_close(prices)
    if close is None or len(close) < 2:
        return pd.Series(dtype=float)

    window = close.iloc[-252:] if len(close) >= 252 else close
    high_52w = float(window.max())
    current = float(close.iloc[-1])

    if high_52w <= 0.0:
        return pd.Series(dtype=float)

    score = round(min(current / high_52w, 1.0), 4)
    return pd.Series([score], index=[close.index[-1]])


def _extract_close(prices: pd.DataFrame) -> pd.Series | None:
    """Extract the Close column, returning None if unavailable."""
    if "Close" not in prices.columns:
        return None
    close: pd.Series = prices["Close"].squeeze()
    if close.dropna().empty:
        return None
    return close
