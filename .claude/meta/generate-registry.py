#!/usr/bin/env python3
"""
.claude/registry/skills.yaml を生成するスクリプト。

使い方:
    python .claude/meta/generate-registry.py

全スキルの SKILL.md フロントマターを読み込み、
ルーティング用インデックスファイルを出力する。
"""

import os
import re
import sys
from pathlib import Path
from datetime import datetime

# 実行場所に依存しないパス解決
SCRIPT_DIR = Path(__file__).parent
SHARED_DIR = SCRIPT_DIR.parent
SKILLS_DIR = SHARED_DIR / "skills"
OUTPUT_PATH = SHARED_DIR / "registry" / "skills.yaml"

# スキル名 → タグ の対応（正規表現で判定）
TAG_RULES = [
    (r"^css-",                      ["css", "frontend"]),
    (r"^frontend-",                 ["frontend", "ui"]),
    (r"^vba-",                      ["vba", "office"]),
    (r"tdd|test.driven",            ["testing"]),
    (r"security|advanced.security", ["security"]),
    (r"handover",                   ["session", "memory"]),
    (r"^git$",                      ["git"]),
    (r"debug",                      ["debugging"]),
    (r"skill.creator|health.check", ["meta"]),
    (r"^mcp",                       ["mcp"]),
    (r"claude.md|claude.code",      ["config"]),
    (r"plan|writing.plan",          ["planning"]),
    (r"brainstorm",                 ["planning"]),
    (r"wolfram",                    ["math"]),
    (r"accessibility",              ["accessibility"]),
    (r"^init$",                     ["setup"]),
    (r"plugin.dev",                 ["plugin"]),
    (r"hookify",                    ["hooks"]),
    (r"agents$",                    ["agents"]),
]

# スキル name → トリガーフレーズリスト
TRIGGER_MAP = {
    "accessibility":              ["アクセシビリティ", "WCAG", "a11y", "スクリーンリーダー", "aria"],
    "brainstorming":              ["ブレスト", "要件整理", "brainstorm", "アイデア出し"],
    "claude-automation-recommender": ["Claude Code設定", "自動化推薦", "フック推薦"],
    "claude-md-improver":         ["CLAUDE.md", "claude.md改善", "claude.md更新"],
    "code-review":                ["コードレビュー", "review", "レビュー"],
    "create-plan":                ["計画作成", "plan作成", "proposal"],
    "css-features":               ["モダンCSS", "CSS 2024", "CSSネスト", "コンテナクエリ", ":has()", "@layer"],
    "css-layout":                 ["CSSレイアウト", "Grid", "Flexbox", "レスポンシブ"],
    "css-organization":           ["CSS設計", "BEM", "デザインシステム", "CSS変数"],
    "design-tracker":             ["設計記録", "アーキテクチャ記録", "DESIGN.md記録", "DESIGN.md更新", "設計ドキュメント更新"],
    "implement-plans":            ["計画実行", "計画に従って"],
    "frontend-design":            ["フロントエンド設計", "UIデザイン", "コンポーネント設計", "UI/UX", "モバイルファースト"],
    "debug":                      ["デバッグ", "バグ修正", "エラー調査"],
    "git":                        ["git", "コミット", "ブランチ", "プルリクエスト", "PR"],
    "handover":                   ["引き継ぎ", "handover", "セッション終了"],
    "writing-hookify-rules":      ["hookify", "フックルール", "hookify作成"],
    "init":                       ["プロジェクト初期化", "init", "初期設定"],
    "mcp-builder":                ["MCP", "MCPサーバー", "Model Context Protocol"],
    "pwf":                        ["長期タスク", "計画ファイル", "セッション間継続"],
    "research-lib":               ["ライブラリ調査", "パッケージ調査", "ライブラリドキュメント更新", "docs/libraries更新"],
    "skill-creator":              ["スキル作成", "新スキル", "skill作成"],
    "simplify":                   ["リファクタ", "シンプル化", "コード整理"],
    "systematic-debugging":       ["デバッグ", "バグ", "4段階デバッグ"],
    "tdd-workflow":               ["TDD", "テスト駆動開発", "Red-Green-Refactor", "テスト哲学", "テスト原則", "テスト設計"],
    "esp32":                      ["ESP32", "ESP32-S3", "PlatformIO", "IoT", "マイコン"],
    "raspberry-pi":               ["Raspberry Pi", "ラズパイ", "GPIO", "gpiozero"],
    "docker-dev":                 ["Docker", "docker compose", "コンテナ開発"],
    "vba-core":                   ["VBA基礎", "VBAエラー処理", "VBAベストプラクティス"],
    "vba-development":            ["VBA開発", "VBAワークフロー"],
    "vba-excel":                  ["Excel VBA", "VBAシート操作"],
    "vba-patterns":               ["VBAパターン", "VBA最終行", "VBAユーティリティ"],
    "wolfram-foundation-tool":    ["Wolfram", "Wolfram Alpha", "数学的証明"],
    "writing-plans":              ["実装計画", "計画書作成", "タスク分割"],
    "advanced-security":          ["高度なセキュリティ", "セキュリティ実装詳細"],
    "security":                   ["セキュリティ", "脆弱性", "OWASP"],
    "plugin-dev":                 ["プラグイン開発", "Claude Codeプラグイン", "command開発"],
    "agents":                     ["エージェント作成", "サブエージェント", "agents.md"],
    # nested skills
    "codeql":                          ["CodeQL", "静的解析", "セキュリティスキャン"],
    "insecure-defaults":               ["安全でないデフォルト", "セキュリティ設定"],
    "sarif-parsing":                   ["SARIF", "セキュリティレポート"],
    "semgrep":                         ["semgrep", "コード静的解析"],
    "dispatching-parallel-agents":     ["並列エージェント", "エージェント分散"],
    "receiving-code-review":           ["コードレビュー受け取り", "レビュー対応"],
    "requesting-code-review":          ["コードレビュー依頼", "レビュー依頼"],
    "subagent-driven-development":     ["サブエージェント開発", "エージェント駆動"],
    "using-superpowers":               ["Claude超能力", "Claude拡張機能"],
    "verification-before-completion":  ["完了前確認", "タスク検証"],
    "writing-skills":                  ["スキル記述", "スキルの書き方"],
    "finishing-a-development-branch":  ["開発ブランチ完了", "ブランチ終了"],
    "git-worktrees":                   ["gitワークツリー", "worktree", "並列git"],
    "agent-development":               ["エージェント開発", "agent.md作成"],
    "command-development":             ["コマンド開発", "スラッシュコマンド作成"],
    "hook-development":                ["フック開発", "hook作成", "hooks.py"],
    "mcp-integration":                 ["MCP統合", "MCPクライアント"],
    "plugin-settings":                 ["プラグイン設定", "settings.json"],
    "plugin-structure":                ["プラグイン構造", "ディレクトリ構成"],
    "owasp-security":                  ["OWASP", "セキュリティ脆弱性", "Web脆弱性"],
    "varlock":                         ["varlock", "変数ロック", "環境変数セキュリティ"],
}


def get_tags(name: str) -> list[str]:
    tags = []
    for pattern, tag_list in TAG_RULES:
        if re.search(pattern, name, re.IGNORECASE):
            for t in tag_list:
                if t not in tags:
                    tags.append(t)
    return tags


def parse_frontmatter(text: str) -> dict:
    """YAML フロントマターを簡易パース（--- で囲まれた先頭ブロック）。"""
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    fm_text = m.group(1)

    result = {}
    # name と description だけ抽出（PyYAML なしでも動くシンプルパース）
    name_m = re.search(r"^name:\s*(.+)$", fm_text, re.MULTILINE)
    if name_m:
        result["name"] = name_m.group(1).strip()

    # description: > or description: | or description: "..." or description: plain
    desc_m = re.search(r"^description:\s*(>[-]?|[|][-]?)\s*\n((?:[ \t]+.+\n?)+)", fm_text, re.MULTILINE)
    if desc_m:
        lines = desc_m.group(2).splitlines()
        result["description"] = " ".join(l.strip() for l in lines if l.strip())
    else:
        desc_inline = re.search(r'^description:\s*"?(.+?)"?\s*$', fm_text, re.MULTILINE)
        if desc_inline:
            result["description"] = desc_inline.group(1).strip()

    return result


def yaml_str(s: str, indent: int = 6) -> str:
    """文字列を YAML 安全な形式に変換。"""
    s = s.replace('"', '\\"').replace("\n", " ")
    return f'"{s}"'


def generate_entry(skill_dir: Path) -> str | None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None

    try:
        text = skill_md.read_text(encoding="utf-8")
    except Exception:
        return None

    fm = parse_frontmatter(text)
    if not fm.get("name"):
        return None

    name = fm["name"]
    description = fm.get("description", "").strip()
    # 長すぎる description は切る
    if len(description) > 200:
        description = description[:197] + "..."

    # ネストスキルのパスを正しく解決（skills/group/sub/SKILL.md）
    rel_parts = skill_dir.relative_to(SHARED_DIR).parts
    rel_path = "/".join(rel_parts) + "/SKILL.md"
    tags = get_tags(name)
    triggers = TRIGGER_MAP.get(name, [])

    lines = [f"  - name: {name}"]
    lines.append(f"    path: {rel_path}")
    if description:
        lines.append(f"    description: {yaml_str(description)}")
    if tags:
        lines.append(f"    tags: [{', '.join(tags)}]")
    else:
        lines.append(f"    tags: []")
    if triggers:
        lines.append(f"    triggers:")
        for t in triggers:
            lines.append(f'      - "{t}"')
    else:
        lines.append(f"    triggers: []")

    return "\n".join(lines)


def collect_skill_dirs(skills_dir: Path) -> list[tuple[Path, str]]:
    """スキルディレクトリを収集する。ネストスキル（サブディレクトリ）も対応。"""
    result = []
    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir():
            continue
        if (d / "SKILL.md").exists():
            # 直接スキル
            result.append((d, d.name))
        else:
            # ネストスキル（サブディレクトリを探す）
            for sub in sorted(d.iterdir()):
                if sub.is_dir() and (sub / "SKILL.md").exists():
                    result.append((sub, f"{d.name}/{sub.name}"))
    return result


def main():
    if not SKILLS_DIR.exists():
        print(f"Error: skills directory not found: {SKILLS_DIR}", file=sys.stderr)
        sys.exit(1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    entries = []
    skipped = []
    for skill_dir, label in collect_skill_dirs(SKILLS_DIR):
        entry = generate_entry(skill_dir)
        if entry:
            entries.append(entry)
        else:
            skipped.append(label)

    now = datetime.now().strftime("%Y-%m-%d")
    header = f"""\
# .claude スキルルーティングインデックス
#
# このファイルは meta/generate-registry.py で自動生成される。
# スキルを追加・変更したら再生成すること:
#   python .claude/meta/generate-registry.py
#
# Claude はこのファイルを読むことで、全 SKILL.md を個別ロードせずに
# どのスキルが存在するかを把握し、適切なスキルへルーティングできる。
#
# generated: {now}

version: "1.0"
generated: "{now}"

skills:
"""

    content = header + "\n\n".join(entries) + "\n"
    OUTPUT_PATH.write_text(content, encoding="utf-8")

    print(f"Generated: {OUTPUT_PATH}")
    print(f"  Skills: {len(entries)}")
    if skipped:
        print(f"  Skipped (no SKILL.md or no name): {skipped}")


if __name__ == "__main__":
    main()
