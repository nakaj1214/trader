"""Show the day's inflection candidates from an encrypted snapshot (local only, no network).

    export SNAPSHOT_ENCRYPTION_KEY=...        # the same key the scan used
    python scripts/show_candidates.py                       # latest snapshot: EARLY_CANDIDATE + WATCH
    python scripts/show_candidates.py --date 2026-10-01     # one stored market day
    python scripts/show_candidates.py --classification NONE --top 5
    python scripts/show_candidates.py --control             # the random control sample instead

Candidates are research flags, not buy recommendations.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.snapshot_crypto import decrypt_json, snapshot_encryption_secret

LATEST = "dashboard/data/inflection_candidates.enc"
SNAPSHOT_DIR = "dashboard/data/inflection/v3"
CLASSIFICATIONS = ("EARLY_CANDIDATE", "WATCH", "NONE", "OVEREXTENDED")
HEADERS = ("銘柄", "会社名", "分類", "スコア", "20日", "出来高比", "高値", "市場", "業種", "理由")


def display_width(text: str) -> int:
    """Terminal columns used by ``text`` (full-width characters take two)."""
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)


def pad(text: str, width: int) -> str:
    return text + " " * (width - display_width(text))


def _number(value: Any, spec: str, suffix: str = "") -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "-"
    return format(float(value), spec) + suffix


def candidate_row(candidate: dict[str, Any]) -> list[str]:
    high = "52週" if candidate.get("near_52w_high") else "上場来" if candidate.get("near_listing_high") else "-"
    return [
        str(candidate.get("ticker") or "-"),
        str(candidate.get("company_name") or "-"),
        str(candidate.get("classification") or "-"),
        _number(candidate.get("score"), ".1f"),
        _number(candidate.get("return_20d_pct"), "+.1f", "%"),
        _number(candidate.get("volume_ratio_20d"), ".2f"),
        high,
        str(candidate.get("market") or "-"),
        str(candidate.get("sector33_name") or "-"),  # absent in schema 4 snapshots
        "・".join(str(reason) for reason in candidate.get("reasons") or []) or "-",
    ]


def render_table(candidates: list[dict[str, Any]]) -> str:
    rows = [list(HEADERS), *(candidate_row(candidate) for candidate in candidates)]
    widths = [max(display_width(row[column]) for row in rows) for column in range(len(HEADERS))]
    return "\n".join("  ".join(pad(cell, widths[index]) for index, cell in enumerate(row)).rstrip() for row in rows)


def _by_score(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(candidates, key=lambda row: -float(row["score"]) if isinstance(row.get("score"), (int, float)) else 0.0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show inflection candidates from an encrypted snapshot.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--date", help="market date YYYY-MM-DD (default: the latest snapshot)")
    parser.add_argument("--classification", nargs="+", choices=CLASSIFICATIONS, default=["EARLY_CANDIDATE", "WATCH"])
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--control", action="store_true", help="show the random control sample instead")
    args = parser.parse_args(argv)

    root = Path(args.repo_root)
    if args.date:
        try:
            day = date.fromisoformat(args.date).isoformat()
        except ValueError:
            print(f"--date は YYYY-MM-DD で指定してください: {args.date}", file=sys.stderr)
            return 1
        path = root / SNAPSHOT_DIR / f"{day}.enc"
    else:
        path = root / LATEST
    if not path.exists():
        print(f"snapshot が見つかりません: {path}", file=sys.stderr)
        return 1
    try:
        secret = snapshot_encryption_secret()
    except RuntimeError:
        print("SNAPSHOT_ENCRYPTION_KEY が設定されていません（scan と同じ鍵が必要です）。", file=sys.stderr)
        return 1
    try:
        payload = decrypt_json(path.read_text(encoding="utf-8"), secret)
    except (ValueError, TypeError, OSError):
        print("snapshot を復号できません（鍵が違うか、ファイルが壊れています）。", file=sys.stderr)
        return 1

    counts = payload.get("classification_counts") or {}
    delay = (payload.get("data_policy") or {}).get("jquants_data_delay_weeks")
    print(f"市場日: {payload.get('latest_price_date')}  strategy: {payload.get('strategy_version')}  "
          f"schema: {payload.get('report_schema_version')}")
    print("  ".join(f"{name} {counts.get(name, 0)}件" for name in CLASSIFICATIONS))
    print(f"※候補は調査対象であり、売買推奨ではありません。財務データは約{delay}週間遅れです。" if delay
          else "※候補は調査対象であり、売買推奨ではありません。")
    if args.control:
        control = payload.get("control_sample")
        if not isinstance(control, list):
            print("この snapshot には対照群がありません（schema 5 より前）。")
            return 0
        print("\n対照群（流動性のある銘柄からの無作為抽出。分類は参考）")
        selected = _by_score([row for row in control if isinstance(row, dict)])[: args.top]
    else:
        wanted = set(args.classification)
        candidates = [row for row in payload.get("candidates") or [] if isinstance(row, dict)]
        selected = _by_score([row for row in candidates if row.get("classification") in wanted])[: args.top]
        print()
    print(render_table(selected) if selected else "該当する候補はありません。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
