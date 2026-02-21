"""Phase 1: ウォークフォワード評価モジュール

Google Sheets の確定済みレコードを使い、期間分割評価（ウォークフォワード）を実施する。

計算フロー:
  1. 確定済みレコードを日付順にソート
  2. train_weeks 分のウィンドウでルール確定期間を定義
  3. 続く test_weeks 分のウィンドウで的中率・誤差指標を算出
  4. 窓を test_weeks ずつずらして繰り返す

出力: dashboard/data/walkforward.json
スキーマ:
  {
    "generated_at": "2025-01-01T00:00:00Z",
    "config": {"train_weeks": 52, "test_weeks": 13, "min_train_weeks": 26},
    "windows": [
      {
        "train_start": "2023-01-01",
        "train_end":   "2023-12-31",
        "test_start":  "2024-01-01",
        "test_end":    "2024-03-31",
        "hit_rate_pct": 60.0,
        "mae": 1.23,
        "mape": 2.45,
        "n_predictions": 30
      }
    ]
  }

注意: データ不足時は windows: [] で出力し、エラー終了しない。
"""

import logging
import math
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _parse_date(date_str: str) -> datetime:
    """YYYY-MM-DD 文字列を datetime に変換する。"""
    return datetime.strptime(date_str, "%Y-%m-%d")


def _compute_window_stats(week_records: list[dict]) -> dict:
    """1ウィンドウ分のレコードから的中率・誤差指標を算出する。

    Args:
        week_records: 「的中」「外れ」のレコードのみ（評価不能は除外済み）

    Returns:
        {
            "hit_rate_pct": float | None,
            "mae": float | None,
            "mape": float | None,
            "n_predictions": int,
        }
    """
    evaluable = [
        r for r in week_records
        if r.get("的中") in ("的中", "外れ")
    ]
    n = len(evaluable)
    if n == 0:
        return {"hit_rate_pct": None, "mae": None, "mape": None, "n_predictions": 0}

    hits = sum(1 for r in evaluable if r["的中"] == "的中")
    hit_rate = round(hits / n * 100, 1)

    abs_errors: list[float] = []
    abs_pct_errors: list[float] = []
    for r in evaluable:
        try:
            predicted = float(r.get("予測価格", "") or "")
            actual = float(r.get("翌週実績価格", "") or "")
            if actual > 0:
                err = abs(predicted - actual)
                abs_errors.append(err)
                abs_pct_errors.append(err / actual * 100)
        except (ValueError, TypeError):
            continue

    mae = round(sum(abs_errors) / len(abs_errors), 4) if abs_errors else None
    mape = round(sum(abs_pct_errors) / len(abs_pct_errors), 4) if abs_pct_errors else None

    return {
        "hit_rate_pct": hit_rate,
        "mae": mae,
        "mape": mape,
        "n_predictions": n,
    }


def compute_walkforward(records: list[dict], config: dict) -> dict:
    """ウォークフォワード評価を実施し、結果辞書を返す。

    Args:
        records: Google Sheets の全レコード（確定済みを含む）
        config: load_config() で取得した設定辞書

    Returns:
        walkforward.json スキーマに準拠した辞書。
    """
    wf_cfg = config.get("walkforward", {})
    train_weeks = int(wf_cfg.get("train_weeks", 52))
    test_weeks = int(wf_cfg.get("test_weeks", 13))
    min_train_weeks = int(wf_cfg.get("min_train_weeks", 26))

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result_config = {
        "train_weeks": train_weeks,
        "test_weeks": test_weeks,
        "min_train_weeks": min_train_weeks,
    }

    # 確定済みレコードを週ごとにグループ化（日付をキーとして使用）
    confirmed: dict[str, list[dict]] = {}
    for r in records:
        if r.get("ステータス") != "確定済み":
            continue
        date = r.get("日付", "")
        if not date:
            continue
        confirmed.setdefault(date, []).append(r)

    weeks_sorted = sorted(confirmed.keys())
    total_weeks = len(weeks_sorted)

    if total_weeks < min_train_weeks + test_weeks:
        logger.info(
            "walkforward: データ不足 (%d 週 / 最低 %d 週必要)。windows=[] で出力します。",
            total_weeks,
            min_train_weeks + test_weeks,
        )
        return {
            "generated_at": generated_at,
            "config": result_config,
            "windows": [],
        }

    windows: list[dict] = []
    # 最初のトレイン窓は min_train_weeks から開始し、test_weeks ずつずらす
    test_start_idx = min_train_weeks
    while test_start_idx + test_weeks <= total_weeks:
        train_start_idx = max(0, test_start_idx - train_weeks)
        train_weeks_actual = test_start_idx - train_start_idx

        if train_weeks_actual < min_train_weeks:
            test_start_idx += test_weeks
            continue

        train_dates = weeks_sorted[train_start_idx:test_start_idx]
        test_dates = weeks_sorted[test_start_idx:test_start_idx + test_weeks]

        # テストウィンドウの全レコードを収集
        test_records: list[dict] = []
        for d in test_dates:
            test_records.extend(confirmed[d])

        stats = _compute_window_stats(test_records)

        windows.append({
            "train_start": train_dates[0],
            "train_end": train_dates[-1],
            "test_start": test_dates[0],
            "test_end": test_dates[-1],
            **stats,
        })

        test_start_idx += test_weeks

    logger.info("walkforward: %d ウィンドウ算出完了", len(windows))

    return {
        "generated_at": generated_at,
        "config": result_config,
        "windows": windows,
    }
