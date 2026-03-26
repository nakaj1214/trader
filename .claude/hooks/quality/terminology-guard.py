#!/usr/bin/env python3
"""
PreToolUse フック: ExitPlanMode / AskUserQuestion 実行前に
用語の一貫性チェックを強制するリマインダーを注入する。

背景 (2026-03-19):
会話中に「クエリビルダ = DB::connection()->table()」
「Eloquent Builder = $model->newQuery()」と区別して議論していたのに、
AskUserQuestion の選択肢で Eloquent Builder を「クエリビルダ」と記述してしまった。
このフックは、ユーザーに提示する内容を出力する前に
用語の正確性を自己チェックさせるためのもの。
"""

import json
import sys


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in ("ExitPlanMode", "AskUserQuestion"):
        sys.exit(0)

    context = (
        "[terminology-guard] ユーザーへの提示前チェック:\n"
        "  1. この会話で区別して使ってきた用語を混同していないか？\n"
        "  2. 技術用語を「まあ伝わるだろう」で雑に書いていないか？\n"
        "  3. 選択肢・説明文の記述が事実と一致しているか？\n"
        "  → 問題があれば修正してから再度ツールを呼ぶこと。"
    )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": context,
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
