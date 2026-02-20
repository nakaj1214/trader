"""アルファサーベイモジュール

学術的なアノマリーの統計検証結果を記録する。
スコアリングには使わず、参考情報として提供する。

n_observations < 52 の場合は insufficient_data を返す。
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.utils import ROOT_DIR

logger = logging.getLogger(__name__)

DATA_DIR = ROOT_DIR / "dashboard" / "data"
ALPHA_SURVEY_PATH = DATA_DIR / "alpha_survey.json"

# 検証対象アノマリーのメタデータ
_ANOMALY_META: dict[str, dict] = {
    "short_interest_effect": {
        "label": "空売り残高効果",
        "score_included": False,
        "note": "equally-weighted前提。大型株（時価加重）では効果弱い可能性",
    },
    "earnings_momentum": {
        "label": "決算モメンタム効果",
        "score_included": False,
        "note": "SUE（標準化予期外利益）に基づく効果。検証中",
    },
}


def run_anomaly_test(anomaly_name: str, lookback_weeks: int = 52) -> dict:
    """アノマリーテストを実行し結果を返す。

    現時点では蓄積データが不足しているため insufficient_data を返す。
    将来的に蓄積データが揃った時点で統計検証ロジックを実装する。

    Args:
        anomaly_name: アノマリー識別子
        lookback_weeks: 検証に使う週数

    Returns:
        {name, n_observations, t_stat, p_value, sharpe, status}
    """
    return {
        "name": anomaly_name,
        "n_observations": 0,
        "t_stat": None,
        "p_value": None,
        "sharpe": None,
        "status": "insufficient_data",
    }


def build_alpha_survey_json(results: list[dict]) -> dict:
    """アノマリー検証結果を alpha_survey.json 形式に変換する。

    n_observations < 52 のエントリは status を insufficient_data に設定する。

    Args:
        results: run_anomaly_test の結果リスト

    Returns:
        {as_of_utc, anomalies} 形式の辞書
    """
    anomalies = []
    for r in results:
        meta = _ANOMALY_META.get(r["name"], {})
        n = r.get("n_observations", 0)
        status = "insufficient_data" if n < 52 else r.get("status", "insufficient_data")

        entry = {
            "name": r["name"],
            "label": meta.get("label", r["name"]),
            "n_observations": n,
            "t_stat": r.get("t_stat"),
            "p_value": r.get("p_value"),
            "sharpe": r.get("sharpe"),
            "status": status,
            "score_included": meta.get("score_included", False),
            "note": meta.get("note", ""),
        }
        anomalies.append(entry)

    return {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "anomalies": anomalies,
    }


def run_and_export() -> bool:
    """全アノマリーを検証して alpha_survey.json を出力する。

    Returns:
        出力成功時 True、失敗時 False
    """
    anomaly_names = list(_ANOMALY_META.keys())
    results = [run_anomaly_test(name) for name in anomaly_names]
    data = build_alpha_survey_json(results)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = ALPHA_SURVEY_PATH.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(ALPHA_SURVEY_PATH)
        logger.info("alpha_survey.json 出力完了")
        return True
    except Exception:
        logger.exception("alpha_survey.json 出力失敗")
        if tmp.exists():
            tmp.unlink()
        return False
