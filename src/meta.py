"""共通メタデータ生成: 予測/評価系JSON に付与する as_of_utc と data_coverage_weeks。"""

from datetime import datetime, timezone


def build_common_meta(records: list[dict]) -> dict:
    """予測/評価系JSON 用の共通メタデータを返す。

    Args:
        records: Google Sheets の全レコード（的中フィールドを含む）

    Returns:
        {"as_of_utc": str, "data_coverage_weeks": int}
    """
    as_of_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    confirmed_dates = set(
        r["日付"]
        for r in records
        if r.get("的中") in ("的中", "外れ")
    )
    data_coverage_weeks = len(confirmed_dates)

    return {
        "as_of_utc": as_of_utc,
        "data_coverage_weeks": data_coverage_weeks,
    }
