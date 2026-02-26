"""チャート生成モジュール

yfinance でデータを取得し、終値 + SMA + Bollinger Band + 出来高チャートを
PNG バイト列として返す。Slack Bot Token による画像 upload で使用する。
"""

import io
import logging

import pandas as pd
import ta
import yfinance as yf

logger = logging.getLogger(__name__)

# A-1 fetch_stock_data() と同じ補正係数
CALENDAR_DAY_FACTOR = 1.5


def build_stock_chart(ticker: str, lookback_days: int, config: dict) -> bytes | None:
    """yfinance でデータを再取得し、OHLCV + SMA + BB チャートを PNG バイト列で返す。

    Args:
        ticker: 銘柄ティッカー（例: "AAPL"）。
        lookback_days: config.yaml の screening.lookback_days（未使用、互換のため残す）。
        config: 設定辞書。notifications.chart_lookback_days を参照する。

    Returns:
        PNG バイト列。データ不足（< 20 本）の場合は None を返す（例外を起こさない）。
    """
    chart_display_days = config.get("notifications", {}).get("chart_lookback_days", 60)

    # SMA200 計算に必要な営業日数（200 本）を確保した上でカレンダー日補正を適用
    chart_fetch_days = max(chart_display_days, 252)
    chart_fetch_period = f"{int(chart_fetch_days * CALENDAR_DAY_FACTOR)}d"

    try:
        df = yf.download(ticker, period=chart_fetch_period, progress=False, auto_adjust=True)
    except Exception:
        logger.exception("チャートデータ取得エラー: %s", ticker)
        return None

    if df.empty or len(df) < 20:
        logger.warning("チャートデータ不足（%d本）: %s — スキップ", len(df), ticker)
        return None

    close = df["Close"].squeeze()
    volume = df["Volume"].squeeze()

    # SMA を全データで計算し、表示範囲だけ tail で切り出す
    sma20 = close.rolling(20).mean().tail(chart_display_days)
    sma50 = close.rolling(50).mean().tail(chart_display_days)
    sma200 = close.rolling(200).mean().tail(chart_display_days) if len(close) >= 200 else None

    # Bollinger Band (20日, 2σ)
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband().tail(chart_display_days)
    bb_lower = bb.bollinger_lband().tail(chart_display_days)

    # 表示データ
    display_close = close.tail(chart_display_days)
    display_volume = volume.tail(chart_display_days)

    # matplotlib は CI 環境での GUI バックエンド問題を避けるため遅延 import する
    import matplotlib
    matplotlib.use("Agg")  # 非対話型バックエンド（CI 環境必須、pyplot import 前に設定）
    import matplotlib.pyplot as plt

    # --- プロット ---
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12, 8), gridspec_kw={"height_ratios": [3, 1]}
    )
    fig.suptitle(f"{ticker} — 直近 {chart_display_days} 日", fontsize=14)

    ax1.plot(display_close.index, display_close.values, label="終値", color="black", linewidth=1.5)
    ax1.plot(sma20.index, sma20.values, label="SMA20", color="blue", linewidth=1.0, alpha=0.8)
    ax1.plot(sma50.index, sma50.values, label="SMA50", color="orange", linewidth=1.0, alpha=0.8)
    if sma200 is not None:
        ax1.plot(sma200.index, sma200.values, label="SMA200", color="red", linewidth=1.0, alpha=0.8)
    ax1.fill_between(
        bb_upper.index, bb_upper.values, bb_lower.values, alpha=0.1, color="gray", label="BB"
    )
    ax1.plot(bb_upper.index, bb_upper.values, color="gray", linewidth=0.5, linestyle="--")
    ax1.plot(bb_lower.index, bb_lower.values, color="gray", linewidth=0.5, linestyle="--")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylabel("価格", fontsize=8)

    ax2.bar(display_volume.index, display_volume.values, color="steelblue", alpha=0.7)
    ax2.set_ylabel("出来高", fontsize=8)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
