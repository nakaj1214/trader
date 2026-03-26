"""勤務時間判定ユーティリティ。

平日 8:00〜16:59 を勤務時間とし、それ以外（平日時間外・土日）は False を返す。
勤務時間の開始・終了は環境変数でカスタマイズ可能:
  SLACK_WORK_HOURS_START (デフォルト: 8)
  SLACK_WORK_HOURS_END   (デフォルト: 17)
"""

import sys
from datetime import datetime
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent.parent  # .claude/hooks/
sys.path.insert(0, str(_HOOKS_DIR))
from lib.env import get as _env

DEFAULT_START = 8
DEFAULT_END = 17


def _parse_hour(value: str, default: int) -> int:
    """環境変数の値を整数に変換する。パース失敗時はデフォルト値を返す。"""
    if not value:
        return default
    try:
        hour = int(value)
        if 0 <= hour <= 23:
            return hour
        print(
            f"[work_hours] invalid hour value: {value}, using default {default}",
            file=sys.stderr,
        )
        return default
    except ValueError:
        print(
            f"[work_hours] failed to parse hour: {value}, using default {default}",
            file=sys.stderr,
        )
        return default


def is_work_hours(now: datetime | None = None) -> bool:
    """勤務時間内（平日 START:00〜END-1:59）なら True を返す。

    テスト用に now を注入可能。
    """
    if now is None:
        now = datetime.now()

    # 土日はスキップ (Monday=0, Sunday=6)
    if now.weekday() >= 5:
        return False

    start = _parse_hour(_env("SLACK_WORK_HOURS_START"), DEFAULT_START)
    end = _parse_hour(_env("SLACK_WORK_HOURS_END"), DEFAULT_END)

    return start <= now.hour < end
