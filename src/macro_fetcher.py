"""フェーズ10: マクロ指標統合（FRED）

FRED API から主要系列を取得し、macro.json を生成する。
FRED_API_KEY 環境変数がない場合は呼び出し元がスキップする。
"""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 取得対象 FRED 系列: {series_id: unit}
FRED_SERIES = {
    "FEDFUNDS": "%",       # FFレート
    "T10Y2Y":   "%",       # 10年-2年スプレッド（逆イールドの目安）
    "VIXCLS":   "pts",     # VIX
}

# リスクオフ判定しきい値
VIX_RISK_OFF_THRESHOLD = 25.0
T10Y2Y_RISK_OFF_THRESHOLD = 0.0   # 負転でリスクオフ


def fetch_fred_series(series_id: str, api_key: str) -> dict | None:
    """FRED API から系列の最新値を取得する。

    Args:
        series_id: FRED 系列 ID（例: "FEDFUNDS"）
        api_key:   FRED API キー

    Returns:
        {"latest_value": float, "latest_date": str} または None（取得失敗時）
    """
    try:
        import urllib.request
        import json as _json

        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={api_key}&file_type=json"
            "&sort_order=desc&limit=1"
        )
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = _json.loads(resp.read().decode())

        observations = data.get("observations", [])
        if not observations:
            return None

        latest = observations[0]
        raw_val = latest.get("value", ".")
        if raw_val == ".":
            return None

        return {
            "latest_value": round(float(raw_val), 4),
            "latest_date": latest.get("date", ""),
        }
    except Exception:
        logger.exception("FRED 系列取得に失敗: %s", series_id)
        return None


def build_macro_json(api_key: str) -> dict:
    """FRED API から主要系列を取得し macro.json スキーマの辞書を返す。

    Args:
        api_key: FRED API キー

    Returns:
        macro.json スキーマに準拠した辞書。
        取得失敗系列はスキップし、成功分だけ格納する。
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    series_result: dict = {}
    latest_dates: list[str] = []

    for series_id, unit in FRED_SERIES.items():
        obs = fetch_fred_series(series_id, api_key)
        if obs is None:
            logger.warning("FRED 系列スキップ: %s", series_id)
            continue
        series_result[series_id] = {
            "latest_value": obs["latest_value"],
            "unit": unit,
        }
        if obs.get("latest_date"):
            latest_dates.append(obs["latest_date"])

    # data_as_of_utc: 取得できた系列の最新基準日（最古値を使用）
    data_as_of_utc = (min(latest_dates) + "T00:00:00Z") if latest_dates else now_utc

    # リスクオフ判定
    vix = series_result.get("VIXCLS", {}).get("latest_value")
    t10y2y = series_result.get("T10Y2Y", {}).get("latest_value")

    is_risk_off = False
    risk_reasons: list[str] = []
    if vix is not None and vix > VIX_RISK_OFF_THRESHOLD:
        is_risk_off = True
        risk_reasons.append(f"VIX={vix:.1f} > {VIX_RISK_OFF_THRESHOLD}")
    if t10y2y is not None and t10y2y < T10Y2Y_RISK_OFF_THRESHOLD:
        is_risk_off = True
        risk_reasons.append(f"T10Y2Y={t10y2y:.2f}% (逆イールド)")

    regime_note = (
        "リスクオフ: " + " / ".join(risk_reasons)
        if is_risk_off
        else "VIX > 25 またはイールドカーブ負転でリスクオフ"
    )

    return {
        "as_of_utc": now_utc,
        "data_as_of_utc": data_as_of_utc,
        "series": series_result,
        "regime": {
            "is_risk_off": is_risk_off,
            "note": regime_note,
        },
    }
