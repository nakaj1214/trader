"""ダッシュボード用JSONエクスポーター

Google Sheets のデータを JSON に変換して dashboard/data/ に出力する。
失敗時は前回データを保持（空ファイル上書き禁止）。
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from src.sheets import HEADERS, get_client, get_or_create_worksheet
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


def build_predictions_json(records: list[dict]) -> list[dict]:
    """全レコードを predictions.json 形式に変換する。"""
    results = []
    for r in records:
        results.append(
            {
                "date": r["日付"],
                "ticker": r["ティッカー"],
                "current_price": _to_float(r["現在価格"]),
                "predicted_price": _to_float(r["予測価格"]),
                "predicted_change_pct": _to_float(r["予測上昇率(%)"]),
                "ci_pct": _to_float(r["信頼区間(%)"]),
                "actual_price": _to_float_or_none(r["翌週実績価格"]),
                "status": r["ステータス"],
                "hit": r["的中"] if r["的中"] else None,
            }
        )
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

    return {
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


def export(config: dict | None = None) -> bool:
    """Google Sheets からデータを取得し、ダッシュボード用JSONを出力する。"""
    if config is None:
        config = load_config()

    try:
        records = fetch_all_records(config)
    except Exception:
        logger.exception("Google Sheets からのデータ取得に失敗")
        return False

    if not records:
        logger.warning("シートにデータがありません。エクスポートをスキップします。")
        return False

    predictions = build_predictions_json(records)
    accuracy = build_accuracy_json(records)
    stock_history = build_stock_history_json(records)

    results = [
        _safe_write_json(predictions, DATA_DIR / "predictions.json"),
        _safe_write_json(accuracy, DATA_DIR / "accuracy.json"),
        _safe_write_json(stock_history, DATA_DIR / "stock_history.json"),
    ]

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
