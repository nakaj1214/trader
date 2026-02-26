"""ステップ1: 自動スクリーニング

グローバル市場から成長ポテンシャルの高い銘柄トップNを抽出する。
銘柄ユニバースは data/*.csv の静的リストから読み込み、
yfinance でデータを取得、ta でテクニカル指標を算出してスコアリングする。
"""

import logging
import time
from pathlib import Path

import pandas as pd
import ta
import yfinance as yf

from src.utils import DATA_DIR, load_config

logger = logging.getLogger(__name__)


def load_tickers(markets: list[str]) -> list[str]:
    """data/*.csv から対象市場の銘柄ティッカーを読み込む。"""
    tickers: list[str] = []
    for market in markets:
        csv_path = DATA_DIR / f"{market}.csv"
        if not csv_path.exists():
            logger.warning("銘柄リストが見つかりません: %s", csv_path)
            continue
        df = pd.read_csv(csv_path)
        if "ticker" not in df.columns:
            logger.warning("CSV に 'ticker' 列がありません、スキップ: %s", csv_path)
            continue
        tickers.extend(df["ticker"].dropna().tolist())
    # 重複を除去しつつ順序を保持
    return list(dict.fromkeys(tickers))


def fetch_stock_data(
    tickers: list[str], lookback_days: int
) -> dict[str, pd.DataFrame]:
    """yfinance で各銘柄の株価データを取得する。"""
    # SMA200 計算に必要な営業日数を確保するため、カレンダー日補正（× 1.5）を適用する
    # 例: lookback_days=252 → 252 × 1.5 ≈ 378 カレンダー日 ≈ 270 営業日
    CALENDAR_DAY_FACTOR = 1.5
    period = f"{int(lookback_days * CALENDAR_DAY_FACTOR)}d"
    data: dict[str, pd.DataFrame] = {}
    # バッチで取得 (レート制限回避のため小分け)
    batch_size = 50
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        logger.info(
            "データ取得中... %d/%d 銘柄", min(i + batch_size, len(tickers)), len(tickers)
        )
        batch_str = " ".join(batch)
        try:
            raw = yf.download(batch_str, period=period, group_by="ticker", progress=False)
        except Exception:
            logger.exception("バッチ取得エラー (銘柄 %d-%d)", i, i + len(batch))
            continue

        for ticker in batch:
            try:
                if len(batch) == 1:
                    df = raw.copy()
                else:
                    df = raw[ticker].copy()
                # 有効なデータがあるかチェック
                if df.empty or df["Close"].dropna().empty:
                    continue
                df = df.dropna(subset=["Close"])
                data[ticker] = df
            except (KeyError, TypeError):
                continue

        if i + batch_size < len(tickers):
            time.sleep(1)  # レート制限回避

    logger.info("データ取得完了: %d/%d 銘柄", len(data), len(tickers))
    return data


# ---------------------------------------------------------------------------
# Phase 13: 52-Week High Momentum
# ---------------------------------------------------------------------------

def compute_52w_high_score(info: dict) -> float | None:
    """52週高値モメンタムスコアを算出する。

    currentPrice / fiftyTwoWeekHigh の比率でスコア化。
    1.0 に近いほど（52週高値付近）高スコア。
    取得失敗時は None。
    """
    current = info.get("currentPrice") or info.get("regularMarketPrice")
    high52 = info.get("fiftyTwoWeekHigh")
    if not current or not high52:
        return None
    try:
        high52 = float(high52)
        if high52 <= 0:
            return None
        return round(min(float(current) / high52, 1.0), 4)
    except (ValueError, TypeError):
        return None


def _fetch_52w_data(tickers: list[str]) -> dict[str, dict]:
    """各銘柄の52週高値スコアと乖離率を取得する。

    取得失敗時は {"score": None, "pct_from_high": None} を格納。
    """
    result: dict[str, dict] = {}
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info or {}
            score = compute_52w_high_score(info)
            if score is not None:
                high52 = float(info.get("fiftyTwoWeekHigh", 0))
                current = float(info.get("currentPrice") or info.get("regularMarketPrice", 0))
                pct_from_high = round(current / high52 - 1.0, 4) if high52 > 0 else None
            else:
                pct_from_high = None
            result[ticker] = {"score": score, "pct_from_high": pct_from_high}
        except Exception:
            result[ticker] = {"score": None, "pct_from_high": None}
    return result


def _fetch_market_caps(tickers: list[str]) -> dict[str, float | None]:
    """yfinance で各銘柄の時価総額を取得する。

    取得失敗時は None を格納（0扱いにしない）。
    """
    caps: dict[str, float | None] = {}
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            cap = info.get("marketCap")
            caps[ticker] = float(cap) if cap else None
        except Exception:
            caps[ticker] = None
    return caps


def compute_indicators(df: pd.DataFrame) -> dict:
    """テクニカル指標を算出してスコアリング用の辞書を返す。"""
    close = df["Close"].squeeze()
    volume = df["Volume"].squeeze()

    if len(close) < 14:
        return {}

    current_price = float(close.iloc[-1])

    # 直近1ヶ月の株価変動率（固定窓: 直近21営業日 ≒ 1ヶ月 — lookback_days に依存しない）
    price_change_1m = (
        (close.iloc[-1] - close.iloc[-22]) / close.iloc[-22]
        if len(close) >= 22 else (close.iloc[-1] - close.iloc[0]) / close.iloc[0]
    )

    # 出来高トレンド（固定窓: 直近42営業日を前半/後半21日ずつ比較 — lookback_days に依存しない）
    VOL_WINDOW = 42
    vol_data = volume.iloc[-VOL_WINDOW:] if len(volume) >= VOL_WINDOW else volume
    mid = len(vol_data) // 2
    vol_first = vol_data.iloc[:mid].mean()
    vol_second = vol_data.iloc[mid:].mean()
    volume_trend = (vol_second - vol_first) / vol_first if vol_first > 0 else 0.0

    # RSI (14日)
    rsi = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]

    # MACD
    macd_ind = ta.trend.MACD(close)
    macd_val = macd_ind.macd().iloc[-1]
    macd_signal_val = macd_ind.macd_signal().iloc[-1]
    macd_bullish = 1.0 if macd_val > macd_signal_val else 0.0

    # Golden Cross: SMA50 > SMA200（None=データ不足, 1.0=GC, 0.0=DC）
    if len(close) < 200:
        logger.warning("データ不足（%d本）: SMA200 計算不可。golden_cross=None。", len(close))
        golden_cross = None
    else:
        sma50 = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        if pd.isna(sma50) or pd.isna(sma200):
            golden_cross = None
        elif sma50 > sma200:
            golden_cross = 1.0
        else:
            golden_cross = 0.0

    # Bollinger Band (20日, 2σ)
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    bb_mavg = bb.bollinger_mavg().iloc[-1]
    bb_width = (bb_upper - bb_lower) / bb_mavg if bb_mavg > 0 else 0.0
    bb_pos = (current_price - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5

    # ADX (14日) — トレンド強度（25+: トレンドあり, 50+: 強いトレンド）
    # High/Low 列が存在しない場合（テスト用 DataFrame 等）はデフォルト値を使用
    if "High" in df.columns and "Low" in df.columns:
        adx_ind = ta.trend.ADXIndicator(
            high=df["High"].squeeze(),
            low=df["Low"].squeeze(),
            close=close,
            window=14,
        )
        adx_val = adx_ind.adx().iloc[-1]
        adx_score = min(float(adx_val) / 50.0, 1.0) if not pd.isna(adx_val) else 0.5
    else:
        adx_score = 0.5

    return {
        "current_price": current_price,
        "price_change_1m": float(price_change_1m),
        "volume_trend": float(volume_trend),
        "rsi": float(rsi),
        "macd_bullish": float(macd_bullish),
        "golden_cross": golden_cross,
        "bb_pos": float(bb_pos),
        "bb_width": float(bb_width),
        "adx_score": float(adx_score),
    }


def score_stock(indicators: dict, config: dict) -> float:
    """指標にウェイトをかけてスコアを算出する。

    Args:
        indicators: compute_indicators() の戻り値。
        config: config.yaml の全設定辞書。weights と use_golden_cross_filter を内部で取得する。
    """
    use_gc_filter = config.get("screening", {}).get("use_golden_cross_filter", True)
    weights = config.get("screening", {}).get("weights", {})

    # Golden Cross ハードフィルター（DC確定かつフィルター有効 → スコア強制 0）
    # None（データ不足）は除外しない。use_gc_filter=False 時はスキップ。
    gc = indicators.get("golden_cross")
    if use_gc_filter and gc is not None and gc == 0.0:
        return 0.0

    # 株価上昇率スコア (正の値ほど高い)
    price_score = max(0.0, indicators["price_change_1m"])

    # 出来高トレンドスコア (増加傾向ほど高い)
    vol_score = max(0.0, indicators["volume_trend"])

    # RSIスコア (30-70の中間帯が高評価、極端な値は減点)
    rsi = indicators["rsi"]
    if 40 <= rsi <= 60:
        rsi_score = 1.0
    elif 30 <= rsi <= 70:
        rsi_score = 0.5
    else:
        rsi_score = 0.0

    # MACDシグナルスコア
    macd_score = indicators["macd_bullish"]

    # Bollinger Band スコア: 中央〜上限にいるほど高評価
    bb_score = min(max(indicators.get("bb_pos", 0.5), 0.0), 1.0)

    # ADX スコア
    adx_score_val = indicators.get("adx_score", 0.5)

    score = (
        weights.get("price_change_1m", 0.3) * price_score
        + weights.get("volume_trend", 0.2) * vol_score
        + weights.get("rsi_score", 0.25) * rsi_score
        + weights.get("macd_signal", 0.25) * macd_score
        + weights.get("bb_position", 0.0) * bb_score
        + weights.get("adx_score", 0.0) * adx_score_val
    )

    # Phase 13: 52週高値モメンタムスコア (None はスキップ)
    fifty2w = indicators.get("fifty2w_score")
    if fifty2w is not None:
        score += weights.get("fifty2w_score", 0.0) * fifty2w

    return score


def screen(config: dict | None = None, market: str | None = None) -> pd.DataFrame:
    """メインのスクリーニング処理。成長株トップNを返す。

    Args:
        config: 設定辞書。None の場合はデフォルト設定を読み込む。
        market: スクリーニング対象市場（例: "sp500", "nikkei225"）。
                None の場合は config の全市場を対象とする。

    Returns:
        DataFrame with columns:
            ticker, current_price, price_change_1m, volume_trend,
            rsi, macd_bullish, score
    """
    if config is None:
        config = load_config()

    screening_cfg = config["screening"]
    markets = [market] if market is not None else screening_cfg["markets"]
    top_n = screening_cfg.get("top_n", 10)
    lookback_days = screening_cfg.get("lookback_days", 30)

    # 銘柄リスト読み込み
    tickers = load_tickers(markets)
    logger.info("対象銘柄数: %d", len(tickers))

    min_market_cap = screening_cfg.get("min_market_cap", 0)

    # 株価データ取得
    stock_data = fetch_stock_data(tickers, lookback_days)

    # 時価総額フィルタ [#4]
    if min_market_cap > 0:
        filtered_tickers = list(stock_data.keys())
        logger.info("時価総額フィルタ適用: 最低 %s", f"{min_market_cap:,.0f}")
        market_caps = _fetch_market_caps(filtered_tickers)
        for ticker in filtered_tickers:
            cap = market_caps.get(ticker)
            # 取得失敗(None)は除外せず残す [再レビュー #2]
            if cap is not None and cap < min_market_cap:
                stock_data.pop(ticker, None)
        n_unknown = sum(1 for t in stock_data if market_caps.get(t) is None)
        logger.info("時価総額フィルタ後: %d 銘柄 (未取得: %d)", len(stock_data), n_unknown)

    # Phase 23: 流動性フィルタ（日次平均売買代金 ADDV、US/JP 通貨別閾値）
    min_addv_us = screening_cfg.get("min_avg_dollar_volume_us", 0)
    min_addv_jp = screening_cfg.get("min_avg_dollar_volume_jp", 0)
    if min_addv_us > 0 or min_addv_jp > 0:
        before = len(stock_data)
        for ticker in list(stock_data.keys()):
            is_jp = ticker.endswith(".T")
            threshold = min_addv_jp if is_jp else min_addv_us
            if threshold <= 0:
                continue
            df = stock_data[ticker]
            close = df["Close"].squeeze()
            volume = df["Volume"].squeeze()
            addv = float((volume * close).mean())
            if addv < threshold:
                stock_data.pop(ticker, None)
        logger.info(
            "流動性フィルタ後: %d → %d 銘柄 (ADDV 閾値未満を除外)",
            before, len(stock_data),
        )

    # Phase 13: 52週高値データ取得
    remaining_tickers = list(stock_data.keys())
    fifty2w_data = _fetch_52w_data(remaining_tickers)

    # テクニカル指標算出 + スコアリング
    results = []
    for ticker, df in stock_data.items():
        indicators = compute_indicators(df)
        if not indicators:
            continue
        # 52週高値スコアをインジケータに追加
        fw = fifty2w_data.get(ticker, {})
        if fw.get("score") is not None:
            indicators["fifty2w_score"] = fw["score"]
        if fw.get("pct_from_high") is not None:
            indicators["fifty2w_pct_from_high"] = fw["pct_from_high"]
        score = score_stock(indicators, config)
        results.append({"ticker": ticker, **indicators, "score": score})

    if not results:
        logger.warning("スクリーニング結果が空です")
        return pd.DataFrame()

    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values("score", ascending=False).head(top_n)
    result_df = result_df.reset_index(drop=True)

    logger.info("スクリーニング完了: トップ%d銘柄を選出", len(result_df))
    return result_df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    df = screen()
    if not df.empty:
        print("\n=== 成長株トップ10 ===")
        print(df.to_string(index=False))
