#!/usr/bin/env python3
"""
.claude スキル品質監査スクリプト。

以下を検出して markdown レポートを生成する:
  - evals.json が存在しないスキル
  - SKILL.md が 30 行を超えているスキル（二段階ロード崩壊の兆候）
  - registry/skills.yaml に登録されていないスキル（孤立スキル）
  - description が類似しているスキル（重複候補）

使い方:
    python .claude/meta/health-check.py              # コンソール出力
    python .claude/meta/health-check.py --save       # .claude/docs/memory/ に保存

"""

import os
import re
import sys
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent
SHARED_DIR = SCRIPT_DIR.parent
SKILLS_DIR = SHARED_DIR / "skills"
REGISTRY_PATH = SHARED_DIR / "registry" / "skills.yaml"
MEMORY_DIR = SHARED_DIR / "docs" / "memory"

SKILL_MD_LINE_LIMIT = 30


def collect_skill_dirs(skills_dir: Path) -> list[tuple[Path, str]]:
    """直接スキルとネストスキル両方を収集する。"""
    result = []
    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir():
            continue
        if (d / "SKILL.md").exists():
            result.append((d, d.name))
        else:
            for sub in sorted(d.iterdir()):
                if sub.is_dir() and (sub / "SKILL.md").exists():
                    result.append((sub, f"{d.name}/{sub.name}"))
    return result


def load_registry_paths(registry_path: Path) -> set[str]:
    """registry/skills.yaml から path の集合を抽出する（簡易パース）。"""
    if not registry_path.exists():
        return set()
    text = registry_path.read_text(encoding="utf-8")
    return set(re.findall(r"path:\s*(\S+)", text))


def get_description(skill_dir: Path) -> str:
    """SKILL.md から description を抽出する。"""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return ""
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return ""
    fm = m.group(1)
    desc_m = re.search(r"^description:\s*(>[-]?|[|][-]?)\s*\n((?:[ \t]+.+\n?)+)", fm, re.MULTILINE)
    if desc_m:
        lines = desc_m.group(2).splitlines()
        return " ".join(l.strip() for l in lines if l.strip())[:150]
    inline = re.search(r'^description:\s*"?(.+?)"?\s*$', fm, re.MULTILINE)
    if inline:
        return inline.group(1).strip()[:150]
    return ""


def check_skills(skill_dirs: list[tuple[Path, str]], registry_paths: set[str]) -> dict:
    issues = {
        "missing_evals": [],
        "oversized_skill_md": [],
        "unregistered": [],
    }
    descriptions = {}

    for skill_dir, label in skill_dirs:
        # evals.json チェック
        has_evals = (skill_dir / "evals.json").exists() or (skill_dir / "evaluations" / "evals.json").exists()
        if not has_evals:
            issues["missing_evals"].append(label)

        # SKILL.md 行数チェック
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            line_count = len(skill_md.read_text(encoding="utf-8").splitlines())
            if line_count > SKILL_MD_LINE_LIMIT:
                issues["oversized_skill_md"].append((label, line_count))

        # registry 登録チェック
        rel_parts = skill_dir.relative_to(SHARED_DIR).parts
        rel_path = "/".join(rel_parts) + "/SKILL.md"
        if registry_paths and rel_path not in registry_paths:
            issues["unregistered"].append(label)

        # description 収集（重複候補検出用）
        desc = get_description(skill_dir)
        if desc:
            descriptions[label] = desc

    # 重複候補（description の先頭 60 文字が一致）
    desc_map: dict[str, list[str]] = {}
    for label, desc in descriptions.items():
        key = desc[:60].lower()
        desc_map.setdefault(key, []).append(label)
    issues["duplicates"] = [(labels, descriptions[labels[0]][:80]) for labels in desc_map.values() if len(labels) > 1]

    return issues


def format_report(issues: dict, total: int) -> str:
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# スキル品質レポート — {date}", ""]
    lines.append(f"対象スキル数: **{total}**")
    lines.append("")

    # サマリー
    n_evals = len(issues["missing_evals"])
    n_over = len(issues["oversized_skill_md"])
    n_unreg = len(issues["unregistered"])
    n_dup = len(issues["duplicates"])
    ok = all(v == 0 for v in [n_evals, n_over, n_unreg, n_dup])

    lines.append("## サマリー")
    lines.append("")
    lines.append(f"| チェック項目 | 件数 | 状態 |")
    lines.append(f"|------------|------|------|")
    lines.append(f"| evals.json 欠損 | {n_evals} | {'✅' if n_evals == 0 else '⚠️'} |")
    lines.append(f"| SKILL.md 肥大化（>{SKILL_MD_LINE_LIMIT}行） | {n_over} | {'✅' if n_over == 0 else '⚠️'} |")
    lines.append(f"| registry 未登録 | {n_unreg} | {'✅' if n_unreg == 0 else '⚠️'} |")
    lines.append(f"| description 重複候補 | {n_dup} | {'✅' if n_dup == 0 else 'ℹ️'} |")
    lines.append("")

    if ok:
        lines.append("> すべてのチェックをパスしました。")
        return "\n".join(lines)

    # 詳細
    if issues["missing_evals"]:
        lines.append("## evals.json 欠損スキル")
        lines.append("")
        lines.append("以下のスキルに `evals.json` が存在しません。")
        lines.append("")
        for label in issues["missing_evals"]:
            lines.append(f"- `{label}`")
        lines.append("")

    if issues["oversized_skill_md"]:
        lines.append(f"## SKILL.md が {SKILL_MD_LINE_LIMIT} 行超のスキル")
        lines.append("")
        lines.append("二段階ロードが崩壊している可能性があります。詳細を INSTRUCTIONS.md に移動してください。")
        lines.append("")
        lines.append("| スキル | 行数 |")
        lines.append("|-------|------|")
        for label, count in issues["oversized_skill_md"]:
            lines.append(f"| `{label}` | {count} |")
        lines.append("")

    if issues["unregistered"]:
        lines.append("## registry/skills.yaml 未登録スキル")
        lines.append("")
        lines.append("`meta/generate-registry.py` を再実行してください。")
        lines.append("")
        for label in issues["unregistered"]:
            lines.append(f"- `{label}`")
        lines.append("")

    if issues["duplicates"]:
        lines.append("## description 重複候補")
        lines.append("")
        lines.append("description の先頭が類似しているスキルです。統合を検討してください。")
        lines.append("")
        for labels, desc_preview in issues["duplicates"]:
            lines.append(f"- {' / '.join(f'`{l}`' for l in labels)}")
            lines.append(f"  > {desc_preview}...")
        lines.append("")

    return "\n".join(lines)


def main():
    save = "--save" in sys.argv

    if not SKILLS_DIR.exists():
        print(f"Error: skills directory not found: {SKILLS_DIR}", file=sys.stderr)
        sys.exit(1)

    skill_dirs = collect_skill_dirs(SKILLS_DIR)
    registry_paths = load_registry_paths(REGISTRY_PATH)
    issues = check_skills(skill_dirs, registry_paths)
    report = format_report(issues, total=len(skill_dirs))

    if save:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        out_path = MEMORY_DIR / f"HEALTH-{date_str}.md"
        out_path.write_text(report, encoding="utf-8")
        sys.stdout.write(f"Saved: {out_path}\n")
    else:
        # Windows ターミナルの cp932 問題を回避して UTF-8 で出力
        sys.stdout.buffer.write(report.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
