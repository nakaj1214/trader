"""エンリッチメントモジュール

予測銘柄にリスク指標・イベント情報・エビデンス指標・スコア内訳を付与する。
exporter からのみ呼び出される設計。
"""

import logging
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase 15: 市場判定ヘルパー
# ---------------------------------------------------------------------------

def is_jp_ticker(ticker: str) -> bool:
    """日本株ティッカーかどうかを判定する。yfinance 形式（例: 7203.T）は末尾が '.T'。"""
    return str(ticker).upper().endswith(".T")


# ---------------------------------------------------------------------------
# Phase 1: Risk metrics
# ---------------------------------------------------------------------------

def compute_risk_metrics(
    df: pd.DataFrame, spy_df: pd.DataFrame, lookback_days: int = 90
) -> dict:
    """1銘柄のリスク指標を算出する。

    呼び出し元（exporter）が事前に取得した株価 DataFrame を受け取る。
    関数内部では yfinance を呼び出さない。

    Args:
        df: 対象銘柄の株価 DataFrame（Close 列を含む）
        spy_df: SPY の株価 DataFrame（beta 算出用）
        lookback_days: beta の計算窓（デフォルト90営業日）

    Returns:
        {
            "vol_20d_ann": float,
            "vol_60d_ann": float,
            "beta": float,
            "max_drawdown_1y": float,
        }
    """
    close = df["Close"].squeeze()
    returns = close.pct_change().dropna()

    # ボラティリティ (20日年率)
    if len(returns) >= 20:
        vol_20 = float(returns.iloc[-20:].std() * math.sqrt(252))
    else:
        vol_20 = float(returns.std() * math.sqrt(252)) if len(returns) > 1 else 0.0

    # ボラティリティ (60日年率)
    if len(returns) >= 60:
        vol_60 = float(returns.iloc[-60:].std() * math.sqrt(252))
    else:
        vol_60 = float(returns.std() * math.sqrt(252)) if len(returns) > 1 else 0.0

    # β (S&P500 に対する)
    spy_close = spy_df["Close"].squeeze()
    spy_returns = spy_close.pct_change().dropna()

    # 共通インデックスで揃える
    common_idx = returns.index.intersection(spy_returns.index)
    if len(common_idx) >= max(lookback_days, 20):
        r = returns.loc[common_idx].iloc[-lookback_days:]
        s = spy_returns.loc[common_idx].iloc[-lookback_days:]
    else:
        r = returns.loc[common_idx]
        s = spy_returns.loc[common_idx]

    if len(r) > 1 and s.var() > 0:
        cov = np.cov(r.values, s.values)[0][1]
        beta = float(cov / s.var())
    else:
        beta = 1.0

    # 最大ドローダウン (1年 = 252営業日)
    dd_window = min(252, len(close))
    dd_close = close.iloc[-dd_window:]
    cummax = dd_close.cummax()
    drawdown = (dd_close - cummax) / cummax
    max_dd = float(drawdown.min()) if len(drawdown) > 0 else 0.0

    return {
        "vol_20d_ann": round(vol_20, 4),
        "vol_60d_ann": round(vol_60, 4),
        "beta": round(beta, 2),
        "max_drawdown_1y": round(max_dd, 4),
    }


# ---------------------------------------------------------------------------
# Phase 8: Position sizing
# ---------------------------------------------------------------------------

def compute_sizing(vol_ann: float, config: dict) -> dict:
    """ボラティリティターゲット法でポジションサイズと損切り水準を算出する。

    Args:
        vol_ann: 年率換算ボラティリティ（例: 0.25 = 25%）
        config: 設定辞書（sizing セクションを含む）

    Returns:
        {
            "vol_target_ann": float,
            "max_position_weight": float,
            "stop_loss_pct": float,
            "stop_loss_rationale": str,
        }
    """
    sizing_cfg = config.get("sizing", {})
    vol_target = sizing_cfg.get("vol_target_ann", 0.10)
    max_cap = sizing_cfg.get("max_weight_cap", 0.20)
    sl_mult = sizing_cfg.get("stop_loss_multiplier", 1.0)

    if vol_ann > 0:
        raw_weight = vol_target / vol_ann
        max_weight = round(min(raw_weight, max_cap), 4)
        # 月次ボラティリティ = 年率ボラ / sqrt(12)
        monthly_vol = vol_ann / math.sqrt(12)
        stop_loss = round(-sl_mult * monthly_vol, 4)
        rationale = "20日ボラティリティに基づく月次リスク推定値"
    else:
        max_weight = round(max_cap, 4)
        stop_loss = None
        rationale = "ボラティリティデータなし"

    return {
        "vol_target_ann": vol_target,
        "max_position_weight": max_weight,
        "stop_loss_pct": stop_loss,
        "stop_loss_rationale": rationale,
    }


# ---------------------------------------------------------------------------
# Phase 1: Events
# ---------------------------------------------------------------------------

def fetch_events(ticker: str) -> list[dict]:
    """決算日・配当落ち日を yfinance .info から取得する。

    Returns:
        [
            {"type": "earnings", "date": "2026-03-05", "days_to": 14},
            {"type": "dividend_ex", "date": "2026-03-20", "days_to": 29},
        ]
    """
    events = []
    today = datetime.now(timezone.utc).date()

    try:
        info = yf.Ticker(ticker).info
    except Exception:
        logger.warning("イベント情報取得失敗: %s", ticker)
        return events

    # 決算日
    earnings_raw = info.get("earningsDate")
    if earnings_raw:
        dates_list = earnings_raw if isinstance(earnings_raw, list) else [earnings_raw]
        for ed in dates_list:
            try:
                if hasattr(ed, "date"):
                    d = ed.date() if callable(ed.date) else ed.date
                else:
                    d = pd.Timestamp(ed).date()
                days_to = (d - today).days
                if days_to >= 0:
                    events.append({
                        "type": "earnings",
                        "date": d.isoformat(),
                        "days_to": days_to,
                    })
            except Exception:
                continue

    # 配当落ち日
    ex_div_raw = info.get("exDividendDate")
    if ex_div_raw:
        try:
            if hasattr(ex_div_raw, "date"):
                d = ex_div_raw.date() if callable(ex_div_raw.date) else ex_div_raw.date
            else:
                d = pd.Timestamp(ex_div_raw).date()
            days_to = (d - today).days
            if days_to >= 0:
                events.append({
                    "type": "dividend_ex",
                    "date": d.isoformat(),
                    "days_to": days_to,
                })
        except Exception:
            pass

    return events


def _fetch_info(ticker: str) -> dict:
    """yfinance .info を取得する。フェーズ1(events)とフェーズ2(evidence)で共通化。"""
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        logger.warning(".info 取得失敗: %s", ticker)
        return {}


def fetch_events_from_info(info: dict, ticker: str) -> list[dict]:
    """事前取得済みの info 辞書からイベントを抽出する。"""
    events = []
    today = datetime.now(timezone.utc).date()

    # 決算日
    earnings_raw = info.get("earningsDate")
    if earnings_raw:
        dates_list = earnings_raw if isinstance(earnings_raw, list) else [earnings_raw]
        for ed in dates_list:
            try:
                if hasattr(ed, "date"):
                    d = ed.date() if callable(ed.date) else ed.date
                else:
                    d = pd.Timestamp(ed).date()
                days_to = (d - today).days
                if days_to >= 0:
                    events.append({
                        "type": "earnings",
                        "date": d.isoformat(),
                        "days_to": days_to,
                    })
            except Exception:
                continue

    # 配当落ち日
    ex_div_raw = info.get("exDividendDate")
    if ex_div_raw:
        try:
            if hasattr(ex_div_raw, "date"):
                d = ex_div_raw.date() if callable(ex_div_raw.date) else ex_div_raw.date
            else:
                d = pd.Timestamp(ex_div_raw).date()
            days_to = (d - today).days
            if days_to >= 0:
                events.append({
                    "type": "dividend_ex",
                    "date": d.isoformat(),
                    "days_to": days_to,
                })
        except Exception:
            pass

    return events


# ---------------------------------------------------------------------------
# Phase 3: Explanations (score breakdown)
# ---------------------------------------------------------------------------

# 因子名 → (config重みキー, 日本語テキストテンプレート)
_FACTOR_META = {
    "price_change_1m": ("price_change_1m", "1ヶ月株価上昇率が高い"),
    "volume_trend": ("volume_trend", "出来高が増加傾向"),
    "rsi": ("rsi_score", "RSIが安定圏にある"),
    "macd_bullish": ("macd_signal", "MACD買いシグナル"),
}


def _transform_score(factor_key: str, raw_value: float) -> float:
    """score_stock と同じ変換ロジックを適用する。"""
    if factor_key == "rsi":
        if 40 <= raw_value <= 60:
            return 1.0
        elif 30 <= raw_value <= 70:
            return 0.5
        else:
            return 0.0
    elif factor_key == "macd_bullish":
        return raw_value  # 0.0 or 1.0
    else:
        return max(0.0, raw_value)


def compute_explanations(
    ticker: str, df: pd.DataFrame, config: dict
) -> dict:
    """screener の関数を再利用してスコア内訳を算出する。

    関数内部で日付ベースの期間切り出しを行う。呼び出し側は長期 DataFrame を
    そのまま渡す。

    Args:
        ticker: ティッカーシンボル（表示用）
        df: yf.download で取得済みの長期株価 DataFrame
        config: config.yaml の設定辞書

    Returns:
        {
            "factors": [{"factor": ..., "weight_key": ..., "impact": ..., "text": ...}, ...],
            "recalculated_at": "...",
            "note": "エクスポート時点の指標値に基づく再計算結果"
        }
    """
    from src.screener import compute_indicators

    lookback = config["screening"]["lookback_days"]  # カレンダー日
    cutoff = df.index.max() - pd.Timedelta(days=lookback)
    sliced_df = df.loc[df.index >= cutoff]

    if len(sliced_df) < 14:
        return {
            "factors": [],
            "recalculated_at": datetime.now(timezone.utc).isoformat(),
            "note": "エクスポート時点の指標値に基づく再計算結果",
        }

    indicators = compute_indicators(sliced_df)
    if not indicators:
        return {
            "factors": [],
            "recalculated_at": datetime.now(timezone.utc).isoformat(),
            "note": "エクスポート時点の指標値に基づく再計算結果",
        }

    weights = config["screening"].get("weights", {})
    factors = []

    for factor_key, (weight_key, text_template) in _FACTOR_META.items():
        raw_value = indicators.get(factor_key)
        if raw_value is None:
            continue
        transformed = _transform_score(factor_key, raw_value)
        weight = weights.get(weight_key, 0.25)
        impact = round(transformed * weight, 4)

        factors.append({
            "factor": factor_key,
            "weight_key": weight_key,
            "impact": impact,
            "text": text_template,
        })

    # 寄与度降順で上位3項目
    factors.sort(key=lambda x: x["impact"], reverse=True)
    factors = factors[:3]

    return {
        "factors": factors,
        "recalculated_at": datetime.now(timezone.utc).isoformat(),
        "note": "エクスポート時点の指標値に基づく再計算結果",
    }


# ---------------------------------------------------------------------------
# Phase 2: Evidence signals
# ---------------------------------------------------------------------------

def compute_evidence_signals(
    ticker: str,
    ticker_info: dict,
    ticker_vol_20d: float,
    peer_data: list[dict],
) -> dict:
    """銘柄のエビデンス指標を対象銘柄群内の z-score で算出する。

    Args:
        ticker: 対象ティッカー
        ticker_info: yf.Ticker(ticker).info の結果
        ticker_vol_20d: フェーズ1で算出済みの20日ボラティリティ
        peer_data: 全銘柄の [{"ticker": ..., "info": ..., "vol_20d": ..., "df": ...}]

    Returns:
        {
            "momentum_z": float,
            "value_z": float,
            "quality_z": float,
            "low_risk_z": float,
            "composite": float,
        }
    """
    def _z_score(val, values):
        arr = np.array([v for v in values if v is not None])
        if len(arr) < 2 or np.std(arr) == 0:
            return 0.0
        return float((val - np.mean(arr)) / np.std(arr))

    # --- Momentum: 12ヶ月リターン (直近1ヶ月除外) ---
    # 標準的な「12-1モメンタム」: end = t-1ヶ月 (≈22営業日前), start = t-13ヶ月 (≈end-252営業日)
    # 必要な最小行数: 22 (1ヶ月) + 252 (12ヶ月) = 274営業日
    _MOMENTUM_END = 22    # 直近1ヶ月のスキップ (営業日)
    _MOMENTUM_SPAN = 252  # 12ヶ月 (営業日)
    _MOMENTUM_MIN = _MOMENTUM_END + _MOMENTUM_SPAN  # 274

    def _calc_momentum(peer):
        df = peer.get("df")
        if df is None or len(df) < _MOMENTUM_MIN:
            return None
        close = df["Close"].squeeze()
        end_price = float(close.iloc[-_MOMENTUM_END])           # 1ヶ月前
        start_price = float(close.iloc[-_MOMENTUM_MIN])        # 13ヶ月前 (= end から12ヶ月前)
        if start_price <= 0:
            return None
        return (end_price - start_price) / start_price

    all_momentum = [_calc_momentum(p) for p in peer_data]
    ticker_peer = next((p for p in peer_data if p["ticker"] == ticker), None)
    ticker_momentum = _calc_momentum(ticker_peer) if ticker_peer else None
    momentum_z = _z_score(ticker_momentum, all_momentum) if ticker_momentum is not None else None

    # --- Value: P/B の逆数 ---
    def _calc_value(peer):
        pb = peer.get("info", {}).get("priceToBook")
        if pb and pb > 0:
            return 1.0 / pb
        return None

    all_value = [_calc_value(p) for p in peer_data]
    ticker_value = _calc_value({"info": ticker_info})
    value_z = _z_score(ticker_value, all_value) if ticker_value is not None else None

    # --- Quality: ROE ---
    def _calc_quality(peer):
        roe = peer.get("info", {}).get("returnOnEquity")
        if roe is not None:
            return float(roe)
        return None

    all_quality = [_calc_quality(p) for p in peer_data]
    ticker_quality = _calc_quality({"info": ticker_info})
    quality_z = _z_score(ticker_quality, all_quality) if ticker_quality is not None else None

    # --- Low Risk: ボラティリティの逆数 ---
    def _calc_low_risk(peer):
        vol = peer.get("vol_20d")
        if vol and vol > 0:
            return 1.0 / vol
        return None

    all_low_risk = [_calc_low_risk(p) for p in peer_data]
    ticker_low_risk = 1.0 / ticker_vol_20d if ticker_vol_20d and ticker_vol_20d > 0 else None
    low_risk_z = _z_score(ticker_low_risk, all_low_risk) if ticker_low_risk is not None else None

    # --- Composite ---
    z_values = {
        "momentum_z": momentum_z,
        "value_z": value_z,
        "quality_z": quality_z,
        "low_risk_z": low_risk_z,
    }
    weights = {"momentum_z": 0.3, "value_z": 0.25, "quality_z": 0.25, "low_risk_z": 0.2}

    weighted_sum = 0.0
    total_weight = 0.0
    for key, w in weights.items():
        if z_values[key] is not None:
            weighted_sum += w * z_values[key]
            total_weight += w

    if total_weight > 0:
        raw_composite = weighted_sum / total_weight
        # z-score を 0-100 に変換 (z=-3 → 0, z=+3 → 100)
        composite = max(0, min(100, round((raw_composite + 3) / 6 * 100)))
    else:
        composite = None

    return {
        "momentum_z": round(momentum_z, 2) if momentum_z is not None else None,
        "value_z": round(value_z, 2) if value_z is not None else None,
        "quality_z": round(quality_z, 2) if quality_z is not None else None,
        "low_risk_z": round(low_risk_z, 2) if low_risk_z is not None else None,
        "composite": composite,
    }


# ---------------------------------------------------------------------------
# Phase 11: Short Interest（補助情報・スコアリング対象外）
# ---------------------------------------------------------------------------

def enrich_short_interest(ticker: str, info: dict) -> dict | None:
    """空売りデータを補助情報として返す。スコアリングには使わない。

    Args:
        ticker: ティッカーシンボル（ログ用）
        info: 事前取得済みの yf.Ticker(t).info

    Returns:
        {"short_ratio": float|None, "short_pct_float": float|None,
         "signal": str, "data_note": str} または None（取得失敗時）
    """
    try:
        short_ratio = info.get("shortRatio")
        short_pct = info.get("shortPercentOfFloat")

        if short_pct is not None:
            pct = float(short_pct)
            if pct > 0.20:
                signal = "high_short"
            elif pct > 0.10:
                signal = "moderate_short"
            else:
                signal = "neutral"
        else:
            signal = "neutral"

        return {
            "short_ratio": round(float(short_ratio), 2) if short_ratio is not None else None,
            "short_pct_float": round(float(short_pct), 4) if short_pct is not None else None,
            "signal": signal,
            "data_note": "月次更新・参考値（yfinance）",
        }
    except Exception:
        logger.warning("空売りデータ取得失敗: %s", ticker)
        return None


# ---------------------------------------------------------------------------
# Phase 12: Institutional Holders（静的参照情報のみ）
# ---------------------------------------------------------------------------

def enrich_institutional_holders(ticker: str) -> dict | None:
    """機関投資家保有状況を静的参照情報として返す。トレンドシグナルとして使わない。

    Args:
        ticker: ティッカーシンボル

    Returns:
        {"institutional_pct": float|None, "top5_holders": list[str],
         "data_note": str} または None（取得失敗時）
    """
    try:
        t = yf.Ticker(ticker)
        inst_df = t.institutional_holders
        info = t.info or {}

        if inst_df is None or inst_df.empty:
            return None

        # カラム名を動的に特定
        name_col = next(
            (c for c in inst_df.columns if "holder" in c.lower() or "name" in c.lower()),
            inst_df.columns[0] if len(inst_df.columns) > 0 else None,
        )
        top5 = []
        if name_col:
            top5 = [str(h) for h in inst_df[name_col].dropna().head(5).tolist()]

        inst_pct = info.get("heldPercentInstitutions")

        return {
            "institutional_pct": round(float(inst_pct), 4) if inst_pct is not None else None,
            "top5_holders": top5,
            "data_note": "四半期報告（45〜75日遅延）・参考値",
        }
    except Exception:
        logger.warning("機関投資家データ取得失敗: %s", ticker)
        return None


# ---------------------------------------------------------------------------
# Phase 13: 52-Week High Momentum（スコアリング因子）
# ---------------------------------------------------------------------------

def enrich_52w_high(ticker: str, info: dict) -> dict | None:
    """52週高値モメンタム指標を返す。

    Args:
        ticker: ティッカーシンボル（ログ用）
        info: 事前取得済みの yf.Ticker(t).info

    Returns:
        {"fifty2w_score": float, "fifty2w_pct_from_high": float} または None
    """
    try:
        current = info.get("currentPrice") or info.get("regularMarketPrice")
        high52 = info.get("fiftyTwoWeekHigh")

        if current is None or high52 is None:
            return None

        current = float(current)
        high52 = float(high52)
        if high52 <= 0:
            return None

        ratio = current / high52
        return {
            "fifty2w_score": round(min(ratio, 1.0), 4),
            "fifty2w_pct_from_high": round(ratio - 1.0, 4),
        }
    except Exception:
        logger.warning("52週高値データ取得失敗: %s", ticker)
        return None


# ---------------------------------------------------------------------------
# Phase 1+2+3 統合: enrich
# ---------------------------------------------------------------------------

def enrich(
    tickers: list[str],
    date: str,
    stock_data: dict[str, pd.DataFrame],
    spy_df: pd.DataFrame,
    config: dict,
) -> dict:
    """最新週の予測銘柄に対してリスク指標・イベント・エビデンス・説明を付与する。

    Args:
        tickers: 最新週の予測対象ティッカーリスト
        date: 最新週の日付文字列
        stock_data: {ticker: DataFrame} 長期株価データ
        spy_df: SPY の DataFrame
        config: config.yaml 設定辞書

    Returns:
        {(date, ticker): {"risk": {...}, "events": [...], "evidence": {...},
         "explanations": {...}, "short_interest": {...}, "institutional": {...},
         "fifty2w_score": float, "fifty2w_pct_from_high": float}}
    """
    enrichment: dict[tuple, dict] = {}

    # Phase 1: .info を各銘柄で1回だけ取得（Phase 2/11/13 と共有）
    info_cache: dict[str, dict] = {}
    risk_cache: dict[str, dict] = {}

    for ticker in tickers:
        info_cache[ticker] = _fetch_info(ticker)

    # Phase 1: リスク指標 + イベント
    for ticker in tickers:
        df = stock_data.get(ticker)
        if df is None or df.empty:
            continue

        risk = compute_risk_metrics(df, spy_df)
        risk_cache[ticker] = risk
        events = fetch_events_from_info(info_cache[ticker], ticker)

        # Phase 8: ポジションサイジング
        sizing = compute_sizing(risk.get("vol_20d_ann", 0.0), config)

        enrichment[(date, ticker)] = {
            "risk": risk,
            "events": events,
            "sizing": sizing,
        }

    # Phase 3: Explanations
    for ticker in tickers:
        df = stock_data.get(ticker)
        if df is None or df.empty:
            continue

        explanations = compute_explanations(ticker, df, config)
        key = (date, ticker)
        if key in enrichment:
            enrichment[key]["explanations"] = explanations

    # Phase 2: Evidence signals
    peer_data = []
    for ticker in tickers:
        peer_data.append({
            "ticker": ticker,
            "info": info_cache.get(ticker, {}),
            "vol_20d": risk_cache.get(ticker, {}).get("vol_20d_ann"),
            "df": stock_data.get(ticker),
        })

    for ticker in tickers:
        evidence = compute_evidence_signals(
            ticker,
            info_cache.get(ticker, {}),
            risk_cache.get(ticker, {}).get("vol_20d_ann", 0.0),
            peer_data,
        )
        key = (date, ticker)
        if key in enrichment:
            enrichment[key]["evidence"] = evidence

    # Phase 11: Short Interest（補助情報）
    for ticker in tickers:
        key = (date, ticker)
        if key not in enrichment:
            continue
        si = enrich_short_interest(ticker, info_cache.get(ticker, {}))
        if si is not None:
            enrichment[key]["short_interest"] = si

    # Phase 12: Institutional Holders（静的参照情報）
    for ticker in tickers:
        key = (date, ticker)
        if key not in enrichment:
            continue
        inst = enrich_institutional_holders(ticker)
        if inst is not None:
            enrichment[key]["institutional"] = inst

    # Phase 13: 52-Week High Momentum
    for ticker in tickers:
        key = (date, ticker)
        if key not in enrichment:
            continue
        fw = enrich_52w_high(ticker, info_cache.get(ticker, {}))
        if fw is not None:
            enrichment[key]["fifty2w_score"] = fw["fifty2w_score"]
            enrichment[key]["fifty2w_pct_from_high"] = fw["fifty2w_pct_from_high"]

    return enrichment
