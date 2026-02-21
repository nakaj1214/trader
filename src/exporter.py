"""ダッシュボード用JSONエクスポーター

Google Sheets のデータを JSON に変換して dashboard/data/ に出力する。
失敗時は前回データを保持（空ファイル上書き禁止）。

enricher の実行責務を一本化: enrichment はこのモジュールからのみ呼び出す。
"""

import json
import logging
import math
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

from src.meta import build_common_meta
from src.predictor import compute_prob_up
from src.sheets import get_client, get_or_create_worksheet
from src.utils import ROOT_DIR, load_config

logger = logging.getLogger(__name__)

DASHBOARD_DIR = ROOT_DIR / "dashboard"
DATA_DIR = DASHBOARD_DIR / "data"


def _to_float(value) -> float:
    """数値に変換する。変換不能な場合は 0.0 を返す。"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _to_float_or_none(value):
    """数値に変換する。空文字・N/A・変換不能な場合は None を返す。"""
    if value == "" or value == "N/A" or value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def fetch_all_records(config: dict) -> list[dict]:
    """Google Sheets から全レコードを取得する。

    Args:
        config: 設定辞書。

    Returns:
        辞書のリスト（各行がヘッダーをキーとした辞書）。
    """
    sheets_cfg = config["google_sheets"]
    client = get_client()
    ws = get_or_create_worksheet(
        client, sheets_cfg["spreadsheet_name"], sheets_cfg["worksheet_name"]
    )
    return ws.get_all_records()


def apply_guardrail(predicted_change_pct: float, config: dict) -> dict:
    """予測上昇率にガードレールを適用する。

    Returns:
        {
            "predicted_change_pct_clipped": float,  # クリップ後の値
            "sanity_flags": list[str],              # "OK" / "WARN_HIGH" / "CLIPPED"
        }
    """
    clip = config.get("guardrail", {}).get("clip_pct", 30.0)
    warn = config.get("guardrail", {}).get("warn_pct", 20.0)

    clipped = max(-clip, min(clip, predicted_change_pct))
    if abs(predicted_change_pct) > clip:
        flags = ["CLIPPED"]
    elif abs(predicted_change_pct) > warn:
        flags = ["WARN_HIGH"]
    else:
        flags = ["OK"]

    return {
        "predicted_change_pct_clipped": round(clipped, 4),
        "sanity_flags": flags,
    }


def build_predictions_json(
    records: list[dict], enrichment: dict | None = None, config: dict | None = None
) -> list[dict]:
    """全レコードを predictions.json 形式に変換する。

    Args:
        records: Google Sheets の全レコード
        enrichment: {(date, ticker): {risk: ..., events: ..., evidence: ..., explanations: ...}}
        config: 設定辞書。guardrail 設定に使用する。
    """
    if enrichment is None:
        enrichment = {}

    results = []
    for r in records:
        pct = _to_float(r["予測上昇率(%)"])
        item = {
            "date": r["日付"],
            "ticker": r["ティッカー"],
            "current_price": _to_float(r["現在価格"]),
            "predicted_price": _to_float(r["予測価格"]),
            "predicted_change_pct": pct,
            "ci_pct": _to_float(r["信頼区間(%)"]),
            "actual_price": _to_float_or_none(r["翌週実績価格"]),
            "status": r["ステータス"],
            "hit": r["的中"] if r["的中"] else None,
        }

        # Phase 5: ガードレール
        if config is not None:
            guardrail = apply_guardrail(pct, config)
            item["predicted_change_pct_clipped"] = guardrail["predicted_change_pct_clipped"]
            item["sanity_flags"] = guardrail["sanity_flags"]

        # Phase 7: 上昇確率
        item["prob_up"] = compute_prob_up(pct, _to_float(r["信頼区間(%)"]))
        item["prob_up_calibrated"] = None

        # enrichment は (date, ticker) キーで最新週のみ存在
        key = (r["日付"], r["ティッカー"])
        ticker_data = enrichment.get(key, {})
        if ticker_data:
            if ticker_data.get("risk"):
                item["risk"] = ticker_data["risk"]
            if ticker_data.get("events"):
                item["events"] = ticker_data["events"]
            if ticker_data.get("evidence"):
                item["evidence"] = ticker_data["evidence"]
            if ticker_data.get("explanations"):
                item["explanations"] = ticker_data["explanations"]
            if ticker_data.get("sizing"):
                item["sizing"] = ticker_data["sizing"]
            # Phase 11: Short Interest（補助情報）
            if ticker_data.get("short_interest"):
                item["short_interest"] = ticker_data["short_interest"]
            # Phase 12: Institutional Holders（静的参照情報）
            if ticker_data.get("institutional"):
                item["institutional"] = ticker_data["institutional"]
            # Phase 13: 52週高値スコア（in 判定で 0.0 を保持）
            if "fifty2w_score" in ticker_data:
                item["fifty2w_score"] = ticker_data["fifty2w_score"]
            if "fifty2w_pct_from_high" in ticker_data:
                item["fifty2w_pct_from_high"] = ticker_data["fifty2w_pct_from_high"]
            # Phase 18: Finnhub ニュース・センチメント（US 株のみ）
            if "news_sentiment" in ticker_data:
                item["news_sentiment"] = ticker_data["news_sentiment"]
            # Phase 24: 決算禁則警告（JP 株のみ）
            if "earnings_warning" in ticker_data:
                item["earnings_warning"] = ticker_data["earnings_warning"]

        results.append(item)
    return results


def build_accuracy_json(records: list[dict]) -> dict:
    """的中率データを accuracy.json 形式で返す。"""
    evaluable = [
        r
        for r in records
        if r.get("ステータス") == "確定済み" and r.get("的中") in ("的中", "外れ")
    ]

    # 週ごとに集計
    weekly: dict[str, dict] = {}
    for r in evaluable:
        date = r["日付"]
        if date not in weekly:
            weekly[date] = {"hits": 0, "total": 0}
        weekly[date]["total"] += 1
        if r["的中"] == "的中":
            weekly[date]["hits"] += 1

    weekly_list = []
    for date in sorted(weekly.keys()):
        w = weekly[date]
        weekly_list.append(
            {
                "date": date,
                "hits": w["hits"],
                "total": w["total"],
                "hit_rate_pct": round(w["hits"] / w["total"] * 100, 1)
                if w["total"] > 0
                else 0.0,
            }
        )

    # 累計
    cum_hits = sum(w["hits"] for w in weekly.values())
    cum_total = sum(w["total"] for w in weekly.values())

    accuracy = {
        "updated_at": datetime.now().astimezone().isoformat(),
        "weekly": weekly_list,
        "cumulative": {
            "hit_rate_pct": round(cum_hits / cum_total * 100, 1)
            if cum_total > 0
            else 0.0,
            "hits": cum_hits,
            "total": cum_total,
        },
    }

    # Phase 4: 予測誤差分析
    accuracy["error_analysis"] = build_error_analysis(records)

    # Phase 7: 共通メタデータ + 校正指標
    accuracy.update(build_common_meta(records))
    accuracy["calibration"] = build_calibration_metrics(records)

    return accuracy


def _compute_calibration_stats(samples: list[dict]) -> dict:
    """prob_up とアウトカムのリストから校正指標（Brier/log-loss/ECE）を算出する。

    Args:
        samples: [{"prob_up": float, "outcome": int (0 or 1)}, ...] のリスト

    Returns:
        brier_score, log_loss, ece, reliability_bins, n_calibrated を含む辞書
    """
    n = len(samples)
    if n == 0:
        return {
            "brier_score": None,
            "log_loss": None,
            "ece": None,
            "reliability_bins": [],
            "n_calibrated": 0,
        }

    brier = sum((s["prob_up"] - s["outcome"]) ** 2 for s in samples) / n

    eps = 1e-7
    ll = -sum(
        s["outcome"] * math.log(max(s["prob_up"], eps))
        + (1 - s["outcome"]) * math.log(max(1 - s["prob_up"], eps))
        for s in samples
    ) / n

    # 信頼性ビン (0.5〜1.0 を 5 分割: 上昇予測のみ対象)
    bin_defs = [
        ("0.5-0.6", 0.5, 0.6),
        ("0.6-0.7", 0.6, 0.7),
        ("0.7-0.8", 0.7, 0.8),
        ("0.8-0.9", 0.8, 0.9),
        ("0.9-1.0", 0.9, 1.01),
    ]
    reliability_bins = []
    ece_sum = 0.0
    for label, lo, hi in bin_defs:
        bin_s = [s for s in samples if lo <= s["prob_up"] < hi]
        if not bin_s:
            continue
        mean_pred = sum(s["prob_up"] for s in bin_s) / len(bin_s)
        empirical = sum(s["outcome"] for s in bin_s) / len(bin_s)
        reliability_bins.append({
            "p_bin": label,
            "n": len(bin_s),
            "mean_pred": round(mean_pred, 3),
            "empirical": round(empirical, 3),
        })
        ece_sum += len(bin_s) * abs(mean_pred - empirical)

    ece = ece_sum / n
    return {
        "brier_score": round(brier, 4),
        "log_loss": round(ll, 4),
        "ece": round(ece, 4),
        "reliability_bins": reliability_bins,
        "n_calibrated": n,
    }


def build_calibration_metrics(records: list[dict]) -> dict:
    """確定済みレコードから校正指標（全期間 + 直近N週）を構築する。

    prob_up は predicted_change_pct と ci_pct から正規分布近似で算出する。

    Returns:
        {"overall": {...}, "recent_n_weeks": {...}}
    """
    samples = []
    for r in records:
        if r.get("ステータス") != "確定済み":
            continue
        try:
            actual = float(r["翌週実績価格"])
            current = float(r["現在価格"])
        except (ValueError, TypeError):
            continue
        if actual <= 0 or current <= 0:
            continue
        predicted_pct = _to_float(r.get("予測上昇率(%)", 0))
        ci = _to_float(r.get("信頼区間(%)", 0))
        outcome = 1 if actual > current else 0
        prob = compute_prob_up(predicted_pct, ci)
        samples.append({"prob_up": prob, "outcome": outcome, "date": r["日付"]})

    overall = _compute_calibration_stats(samples)

    recent_n = 12
    all_dates = sorted(set(s["date"] for s in samples))
    if len(all_dates) > recent_n:
        cutoff = set(all_dates[-recent_n:])
        recent_samples = [s for s in samples if s["date"] in cutoff]
    else:
        recent_samples = samples

    recent_stats = _compute_calibration_stats(recent_samples)
    recent_stats["n_weeks"] = min(recent_n, len(all_dates))

    return {"overall": overall, "recent_n_weeks": recent_stats}


def build_error_analysis(records: list[dict]) -> dict:
    """予測上昇率 vs 実際変動率の誤差分析データを構築する。"""
    # 確定済み + 実績あり のレコードのみ対象
    confirmed = []
    for r in records:
        if r.get("ステータス") != "確定済み":
            continue
        actual = _to_float_or_none(r.get("翌週実績価格"))
        current = _to_float(r.get("現在価格", 0))
        predicted_pct = _to_float(r.get("予測上昇率(%)", 0))
        if actual is None or current <= 0:
            continue
        actual_pct = (actual - current) / current * 100
        confirmed.append({
            "predicted_pct": predicted_pct,
            "actual_pct": actual_pct,
            "hit": r.get("的中"),
        })

    if not confirmed:
        return {
            "mae_pct": None,
            "bins": [],
            "notes": "予測上昇率の帯ごとに実績変動率を比較。MAEは予測と実績の平均絶対誤差。",
        }

    # MAE
    errors = [abs(c["predicted_pct"] - c["actual_pct"]) for c in confirmed]
    mae = round(sum(errors) / len(errors), 1)

    # ビン分割
    bin_defs = [
        ("0-5%", 0, 5),
        ("5-10%", 5, 10),
        ("10-20%", 10, 20),
        ("20%+", 20, float("inf")),
    ]

    bins = []
    for label, lo, hi in bin_defs:
        in_bin = [c for c in confirmed if lo <= c["predicted_pct"] < hi]
        if not in_bin:
            continue
        avg_pred = round(sum(c["predicted_pct"] for c in in_bin) / len(in_bin), 1)
        avg_actual = round(sum(c["actual_pct"] for c in in_bin) / len(in_bin), 1)
        hits = sum(1 for c in in_bin if c["hit"] == "的中")
        hit_rate = round(hits / len(in_bin) * 100, 1)
        bins.append({
            "range": label,
            "avg_predicted_pct": avg_pred,
            "avg_actual_pct": avg_actual,
            "hit_rate_pct": hit_rate,
            "count": len(in_bin),
        })

    return {
        "mae_pct": mae,
        "bins": bins,
        "notes": "予測上昇率の帯ごとに実績変動率を比較。MAEは予測と実績の平均絶対誤差。",
    }


def build_stock_history_json(records: list[dict]) -> dict:
    """銘柄別の価格履歴を stock_history.json 形式で返す。"""
    history: dict[str, list] = {}
    for r in records:
        ticker = r["ティッカー"]
        if ticker not in history:
            history[ticker] = []
        entry: dict = {
            "date": r["日付"],
            "predicted_price": _to_float(r["予測価格"]),
        }
        actual = _to_float_or_none(r["翌週実績価格"])
        if actual is not None:
            entry["actual_price"] = actual
        history[ticker].append(entry)

    # 各銘柄を日付順にソート
    for ticker in history:
        history[ticker].sort(key=lambda x: x["date"])

    return history


def _safe_write_json(data, filepath: Path) -> bool:
    """非空データのみファイルに書き出す。空なら前回データを保持。"""
    if not data:
        logger.warning("データが空のため書き出しスキップ: %s", filepath)
        return False

    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = filepath.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(filepath)
        logger.info("JSON出力完了: %s", filepath)
        return True
    except Exception:
        logger.exception("JSON書き出しエラー: %s", filepath)
        if tmp_path.exists():
            tmp_path.unlink()
        return False


def _is_drive_quota_exceeded_error(exc: Exception) -> bool:
    """Google Drive の保存容量超過エラーかどうかを判定する。"""
    message = str(exc).lower()
    return "drive storage quota" in message and "exceeded" in message


def _fetch_price_data(tickers: list[str], period: str) -> dict[str, object]:
    """yfinance で複数銘柄の株価データを一括取得し {ticker: DataFrame} で返す。

    SPY を含む場合は "SPY" キーにも格納される。
    取得失敗銘柄はスキップする。
    """
    if not tickers:
        return {}

    tickers_str = " ".join(tickers)
    try:
        raw = yf.download(tickers_str, period=period, group_by="ticker", progress=False)
    except Exception:
        logger.exception("株価データ取得に失敗 (period=%s, %d 銘柄)", period, len(tickers))
        return {}

    result: dict = {}
    for ticker in tickers:
        try:
            if len(tickers) == 1:
                df = raw.copy()
            elif ticker in raw.columns.get_level_values(0):
                df = raw[ticker].copy()
            else:
                continue
            df = df.dropna(subset=["Close"])
            if not df.empty:
                result[ticker] = df
        except (KeyError, TypeError):
            continue
    return result


def _build_enrichment(records: list[dict], config: dict) -> dict:
    """最新週の予測銘柄に対して enrichment データを構築する。"""
    from src.enricher import enrich

    # 最新週の日付を特定
    dates = sorted(set(r["日付"] for r in records))
    if not dates:
        return {}
    latest_date = dates[-1]

    # 最新週の予測済みティッカーを抽出
    latest_tickers = list(set(
        r["ティッカー"]
        for r in records
        if r["日付"] == latest_date and r.get("ステータス") == "予測済み"
    ))
    if not latest_tickers:
        return {}

    logger.info("enrichment 対象: %d 銘柄 (%s)", len(latest_tickers), latest_date)

    # 長期株価データを一括取得 (period="400d" で252営業日を確実に含む)
    price_data = _fetch_price_data(latest_tickers + ["SPY"], period="400d")
    stock_data = {t: df for t, df in price_data.items() if t != "SPY"}
    spy_df = price_data.get("SPY")

    if spy_df is None or spy_df.empty:
        logger.warning("SPY データ取得失敗。enrichment をスキップします。")
        return {}

    return enrich(latest_tickers, latest_date, stock_data, spy_df, config)


def _build_comparison(records: list[dict], config: dict | None = None) -> dict | None:
    """フェーズ6: 3戦略の比較データを構築する。

    - AI 戦略: 確定済みレコードの等金額平均リターン
    - 12-1モメンタム: 過去全ティッカーの 12-1 モメンタム上位 10 銘柄
    - SPY: ベンチマーク

    Returns:
        comparison.json 相当の辞書。データ不足時は None。
    """
    from src import baseline as _bl

    # 過去に登場した全ティッカー (+ SPY) を 2y 分ダウンロード
    all_tickers = list(set(r["ティッカー"] for r in records))
    if not all_tickers:
        return None

    logger.info("baseline 用株価取得: %d 銘柄 (period=2y)", len(all_tickers))
    price_data = _fetch_price_data(all_tickers + ["SPY"], period="2y")
    prices = {t: df for t, df in price_data.items() if t != "SPY"}
    spy_df = price_data.get("SPY")

    # AI 週次リターン
    ai_returns, ai_equity = _bl.compute_ai_weekly_returns(records)

    # 12-1 モメンタム
    mom_returns, mom_equity = _bl.compute_baseline_momentum(prices, top_n=10)

    # SPY
    if spy_df is not None and not spy_df.empty:
        spy_returns, spy_equity = _bl.compute_spy_weekly_returns(spy_df)
    else:
        spy_returns, spy_equity = pd.Series(dtype=float), []

    if ai_returns.empty and mom_returns.empty and spy_returns.empty:
        logger.info("baseline comparison: 全戦略のデータが不足しています")
        return None

    comp = _bl.build_comparison_json(
        ai_returns, ai_equity,
        mom_returns, mom_equity,
        spy_returns, spy_equity,
    )
    # Phase 7: 共通メタデータを付与
    comp.update(build_common_meta(records))
    # Phase 9: バックテスト品質開示
    comp["backtest_hygiene"] = _bl.build_backtest_hygiene(config, records)
    return comp


def _split_records_by_market(records: list[dict]) -> dict[str, list[dict]]:
    """レコードをティッカーのサフィックスで市場別に分割する。

    - .T で終わるティッカー → "jp"
    - それ以外               → "us"
    """
    from src.enricher import is_jp_ticker

    us_records = [r for r in records if not is_jp_ticker(r.get("ティッカー", ""))]
    jp_records = [r for r in records if is_jp_ticker(r.get("ティッカー", ""))]
    return {"us": us_records, "jp": jp_records}


def export(config: dict | None = None) -> bool:
    """Google Sheets からデータを取得し、ダッシュボード用JSONを出力する。

    Phase 15: 市場別ファイル出力
    - predictions_us.json: 米国株（S&P500 / NASDAQ100）
    - predictions_jp.json: 日本株（日経225）
    - predictions.json:    後方互換のため米国株データを引き続き出力
                           既存の dashboard/index.html 等が参照するため残す。
                           Phase 16 移行完了後に削除可能。
    """
    if config is None:
        config = load_config()

    try:
        records = fetch_all_records(config)
    except Exception as exc:
        if _is_drive_quota_exceeded_error(exc):
            logger.warning(
                "Google Drive の保存容量超過のため、今回のエクスポートをスキップします。"
            )
            return True
        logger.exception("Google Sheets からのデータ取得に失敗")
        return False

    if not records:
        logger.warning("シートにデータがありません。エクスポートをスキップします。")
        return False

    # Phase 15: 市場別にレコードを分割
    by_market = _split_records_by_market(records)
    us_records = by_market["us"]
    jp_records = by_market["jp"]
    logger.info("レコード分割: US=%d件, JP=%d件", len(us_records), len(jp_records))

    # enrichment (リスク指標・イベント・エビデンス・説明)
    enrichment = {}
    try:
        enrichment = _build_enrichment(records, config)
        if enrichment:
            logger.info("enrichment 完了: %d 銘柄", len(enrichment))
    except Exception:
        logger.exception("enrichment でエラーが発生しましたが、処理を続行します")

    # --- 米国株 predictions ---
    us_predictions_list = build_predictions_json(us_records, enrichment, config)
    if us_predictions_list:
        us_meta = build_common_meta(us_records)
        us_predictions_json = {**us_meta, "predictions": us_predictions_list}
        # predictions_us.json (Phase 16 の us/ ページ用)
        _safe_write_json(us_predictions_json, DATA_DIR / "predictions_us.json")
        # predictions.json (後方互換: 既存 dashboard/index.html が参照)
        r_pred = _safe_write_json(us_predictions_json, DATA_DIR / "predictions.json")
    else:
        logger.warning("US データが空のため predictions_us.json / predictions.json をスキップ")
        r_pred = False

    # --- 日本株 predictions (Phase 15) ---
    if jp_records:
        jp_predictions_list = build_predictions_json(jp_records, enrichment, config)
        if jp_predictions_list:
            jp_meta = build_common_meta(jp_records)
            jp_predictions_json = {**jp_meta, "predictions": jp_predictions_list}
            _safe_write_json(jp_predictions_json, DATA_DIR / "predictions_jp.json")
            logger.info("predictions_jp.json 出力完了")
        else:
            logger.warning("JP データが空のため predictions_jp.json をスキップ")
    else:
        logger.info("JP レコードなし: predictions_jp.json をスキップ")

    # accuracy / stock_history は全レコード対象（市場横断）
    accuracy = build_accuracy_json(records)
    stock_history = build_stock_history_json(records)

    results = [
        r_pred,
        _safe_write_json(accuracy, DATA_DIR / "accuracy.json"),
        _safe_write_json(stock_history, DATA_DIR / "stock_history.json"),
    ]

    # Phase 6: ベースライン比較 (comparison.json)
    try:
        comparison = _build_comparison(records, config)
        if comparison:
            _safe_write_json(comparison, DATA_DIR / "comparison.json")
            logger.info("comparison.json 出力完了")
    except Exception:
        logger.exception("baseline comparison でエラーが発生しましたが、処理を続行します")

    # Phase 10: マクロ指標統合 (macro.json) - FRED_API_KEY がある場合のみ実行
    fred_api_key = os.environ.get("FRED_API_KEY")
    if fred_api_key:
        try:
            from src.macro_fetcher import build_macro_json
            macro = build_macro_json(fred_api_key)
            _safe_write_json(macro, DATA_DIR / "macro.json")
            logger.info("macro.json 出力完了")
        except Exception:
            logger.exception("macro.json 生成でエラーが発生しましたが、処理を続行します")
    else:
        logger.info("FRED_API_KEY が未設定のため macro.json 生成をスキップします")

    success = all(results)
    if success:
        logger.info("全JSONエクスポート完了")
    else:
        logger.warning("一部JSONエクスポートに失敗")
    return success


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    ok = export()
    sys.exit(0 if ok else 1)
