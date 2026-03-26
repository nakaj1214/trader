#!/usr/bin/env python3
"""
PreCompact hook: 自動コンパクション直前にハンドオーバーとスキル候補レポートを生成する。

Claude Code が会話を自動圧縮する直前に発火し:
1. 会話トランスクリプトを intact なうちに読み込む
2. claude -p (並列) でハンドオーバー要約とパターン分析を生成
3. .claude/docs/memory/ に以下を保存:
   - HANDOVER-YYYY-MM-DD.md      — 次セッションへの引き継ぎ
   - SKILL-SUGGESTIONS-YYYY-MM-DD.md — 自動化候補レポート

matcher: "auto" = 自動コンパクションのみ（手動 /compact は除外）

Environment variables (optional):
  HANDOVER_MEMORY_DIR - 出力先ディレクトリ (default: .claude/docs/memory)
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# lib/ を import パスに追加（hooks/ ディレクトリを指す）
_HOOKS_DIR = Path(__file__).resolve().parent.parent  # .claude/hooks/
sys.path.insert(0, str(_HOOKS_DIR))
from lib.transcript import read as read_transcript
from lib.claude_p import run as claude_run
from lib.jsonl_io import append_jsonl, read_jsonl_safe

# Path resolution (portable across projects)
_PROJECT_ROOT = _HOOKS_DIR.parent.parent  # project root

MEMORY_DIR = os.environ.get(
    "HANDOVER_MEMORY_DIR",
    str(_PROJECT_ROOT / ".claude" / "docs" / "memory"),
)
EDIT_LOG_PATH = str(_PROJECT_ROOT / ".claude" / "logs" / "edit-history.jsonl")
QUEUE_PATH = os.path.join(MEMORY_DIR, "AUTO-MATERIALIZE-QUEUE.jsonl")
MIN_EDIT_ENTRIES = 10

HANDOVER_PROMPT = """\
You are generating a handover document for the next Claude session.
Based on the conversation transcript provided, create a concise but complete handover document in Markdown.

Use this exact structure:

# Handover — {date}

## Session Summary
(1-3 sentences: purpose and outcome)

## Completed Work
- (bullet list of completed tasks)

## Incomplete Work
- [ ] (task) — (current status and next step)

## Key Decisions
| Decision | Reason |
|----------|--------|
| ... | ... |

## Issues & Solutions
(problems encountered and how they were resolved)

## Gotchas & Notes
(important things to watch out for)

## Next Steps
1. (highest priority)
2. ...

## Important Files
| File | Role | Status |
|------|------|--------|
| ... | ... | changed/new/reviewed |

Rules:
- Write in the same language as the conversation (Japanese if the conversation is in Japanese)
- Be specific and actionable — the next Claude should be able to resume work immediately
- Keep it concise; skip sections that have nothing to report
"""

SUGGESTIONS_PROMPT = """\
You are analyzing a Claude Code conversation transcript to identify automation opportunities.

Based on the transcript, find recurring patterns and gaps that could be improved with new skills, agents, or hooks.

Use this exact structure:

# スキル候補レポート — {date}

## 検出されたパターン
(会話中に繰り返し登場したタスク・質問・操作を箇条書きで)

## スキル候補
| スキル名 | トリガー条件 | 内容 | 優先度 |
|---------|------------|------|--------|
| ... | (ユーザーが言いそうなフレーズ) | ... | 高/中/低 |

## エージェント候補
| エージェント名 | ユースケース | 専門化内容 | 優先度 |
|--------------|------------|-----------|--------|
| ... | ... | ... | 高/中/低 |

## フック候補
| フック種別 | トリガー | アクション | 優先度 |
|-----------|---------|-----------|--------|
| ... | ... | ... | 高/中/低 |

## 観察事項
(パターンとして検出されたが自動化優先度が低いもの)

Rules:
- Write in Japanese
- Only suggest if the pattern appeared 2+ times OR is clearly high value
- Be specific: include example trigger phrases and expected output
- Skip sections with nothing to report
- If no meaningful patterns found, write "このセッションでは特筆すべきパターンは検出されませんでした。"
"""


def generate_handover(transcript: str) -> str:
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    prompt = HANDOVER_PROMPT.format(date=date)
    content = claude_run(f"{prompt}\n\n---\n\nTRANSCRIPT:\n\n{transcript}")
    if content.startswith("("):
        return f"# Handover — {date}\n\n{content}"
    return content


def generate_suggestions(transcript: str) -> str:
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    prompt = SUGGESTIONS_PROMPT.format(date=date)
    content = claude_run(f"{prompt}\n\n---\n\nTRANSCRIPT:\n\n{transcript}")
    if content.startswith("("):
        return f"# スキル候補レポート — {date}\n\n{content}"
    return content


EDIT_ANALYSIS_PROMPT = """\
以下は Claude Code セッション中の編集ログ（JSONL形式）です。
このログからパターンを分析し、以下を出力してください。

# 編集パターン分析 — {date}

## 1. 繰り返し編集パターン
- 同じファイルへの複数回編集（手戻り？）
- 同じ種類の変更の繰り返し（自動化候補）
- 構文エラー後の修正（防止可能？）

## 2. 影響分析パターン
- 編集 A → 編集 B の因果関係
- 毎回セットで変更されるファイルペア

## 3. 問題のある編集パターン
- 構文エラーを出した編集
- 直後に revert された編集
- 同じ箇所への複数回修正

## Hook 候補
| 検出パターン | 防止方法 | Hook 種別 | 実装案 |
|-------------|---------|-----------|--------|

## Skill 候補
| 繰り返しパターン | 自動化方法 | Skill 名 | トリガー条件 |
|----------------|-----------|----------|-------------|

## 学習事項
| 観察 | 原因推定 | 改善アクション |
|------|---------|---------------|

Rules:
- Write in Japanese
- Be specific with file names and patterns
- Skip sections with nothing to report
- If no meaningful patterns found, write "このセッションでは特筆すべき編集パターンは検出されませんでした。"
"""


def generate_edit_analysis(edit_log_content: str) -> str | None:
    """Analyze edit history log and generate patterns report."""
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    prompt = EDIT_ANALYSIS_PROMPT.format(date=date)
    content = claude_run(f"{prompt}\n\n---\n\n編集ログ:\n\n{edit_log_content}")
    if content.startswith("("):
        return f"# 編集パターン分析 — {date}\n\n{content}"
    return content


def save_doc(content: str, filename: str, tags: list[str] | None = None) -> str:
    Path(MEMORY_DIR).mkdir(parents=True, exist_ok=True)
    output_path = os.path.join(MEMORY_DIR, filename)
    if tags:
        date_str = datetime.now().strftime("%Y-%m-%d")
        frontmatter = f"---\ntags: {tags}\nscope: session\ndate: {date_str}\n---\n\n"
        content = frontmatter + content
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    # "auto"（自動コンパクション）と "manual"（手動 /compact）の両方に対応
    if data.get("trigger") not in ("auto", "manual"):
        sys.exit(0)

    transcript_path = data.get("transcript_path", "")
    if not transcript_path or not os.path.exists(transcript_path):
        print("[pre-compact-handover] transcript not found, skipping.", file=sys.stderr)
        sys.exit(0)

    transcript = read_transcript(transcript_path)
    date_str = datetime.now().strftime("%Y-%m-%d-%H%M")

    # Handover 生成は /handover スキルに一本化（重複生成防止）
    tasks = {
        "suggestions": (generate_suggestions, f"SKILL-SUGGESTIONS-{date_str}.md",  ["session", "automation"]),
    }

    # Check if edit history has enough entries for analysis
    edit_analysis_filename = None
    edit_log_content = None
    if os.path.isfile(EDIT_LOG_PATH):
        edit_entries = read_jsonl_safe(EDIT_LOG_PATH)
        if len(edit_entries) >= MIN_EDIT_ENTRIES:
            edit_log_content = "\n".join(
                json.dumps(e, ensure_ascii=False) for e in edit_entries
            )
            edit_analysis_filename = f"EDIT-PATTERNS-{date_str}.md"

    max_workers = 3 if edit_log_content else 2

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fn, transcript): (filename, tags)
            for fn, filename, tags in tasks.values()
        }

        # Add edit analysis task if enough data
        if edit_log_content and edit_analysis_filename:
            futures[executor.submit(generate_edit_analysis, edit_log_content)] = (
                edit_analysis_filename,
                ["session", "edit-patterns"],
            )

        for future in as_completed(futures):
            filename, tags = futures[future]
            try:
                content = future.result()
                if content is None:
                    continue
                path = save_doc(content, filename, tags=tags)
                print(f"[pre-compact-handover] Saved: {path}", file=sys.stderr)

                # Add to materialize queue for edit patterns
                if filename.startswith("EDIT-PATTERNS-"):
                    try:
                        queue_entry = json.dumps({
                            "ts": datetime.now().isoformat(),
                            "source": filename,
                            "status": "pending",
                            "type": "edit-patterns",
                        }, ensure_ascii=False)
                        append_jsonl(QUEUE_PATH, queue_entry)
                        print(f"[pre-compact-handover] Queued: {filename}", file=sys.stderr)
                    except Exception as qe:
                        print(f"[pre-compact-handover] Queue write failed: {qe}", file=sys.stderr)

            except Exception as e:
                print(f"[pre-compact-handover] Task failed for {filename}: {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
