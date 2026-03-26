#!/usr/bin/env python3
"""
.claude/ 内の英語 .md ファイルを日本語に一括翻訳するスクリプト。

使い方:
    python scripts/translate_to_japanese.py              # ドライラン（翻訳対象を表示）
    python scripts/translate_to_japanese.py --run         # 実行
    python scripts/translate_to_japanese.py --run --resume # 途中から再開
"""

import os
import re
import subprocess
import sys
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_DIR = ROOT / ".claude"
PROGRESS_FILE = ROOT / "scripts" / ".translate_progress.json"

# Skip these directories entirely
SKIP_DIRS = {
    "docs/memory", "staging", "logs", ".claudeignore",
}

# Skip these specific files (already Japanese or must stay English)
SKIP_FILES = {
    "CLAUDE.md", "GUIDE.md", "STRUCTURE.md",
}

# Skip SKILL.md files (need English descriptions for routing)
SKIP_PATTERNS = [
    r"SKILL\.md$",
    r"evals\.json$",
    r"\.py$",
    r"\.sh$",
    r"\.json$",
    r"\.yaml$",
    r"\.yml$",
    r"\.txt$",
    r"\.html$",
    r"\.js$",
    r"\.dot$",
    r"\.xml$",
]

TRANSLATION_PROMPT = """あなたは技術文書の翻訳者です。以下の英語のMarkdownファイルを日本語に翻訳してください。

重要なルール:
1. コードブロック（```で囲まれた部分）の中身はそのまま残す（コメントのみ日本語に）
2. YAMLフロントマター（---で囲まれた部分）のキー名はそのまま残し、値のみ翻訳
3. ファイルパス、URL、コマンド名、技術用語（API、JSON、Git等）は英語のまま
4. 変数名、関数名、クラス名は英語のまま
5. テーブルのヘッダーと内容は日本語に翻訳
6. 見出し（#）は日本語に翻訳
7. Markdownの書式（リンク、太字、リスト等）は保持
8. インラインコード（`バッククォート`で囲まれた部分）の中身はそのまま
9. 出力はMarkdownのみ（説明文や前置きは不要）
10. すでに日本語の部分はそのまま残す

ファイル内容:
"""


def japanese_ratio(text: str) -> float:
    """Calculate the ratio of Japanese characters in text (excluding code blocks)."""
    # Remove code blocks
    no_code = re.sub(r"```[\s\S]*?```", "", text)
    no_code = re.sub(r"`[^`]+`", "", no_code)

    if not no_code.strip():
        return 1.0  # Empty after removing code = treat as Japanese

    jp_chars = len(re.findall(r"[\u3000-\u9fff\uff00-\uffef]", no_code))
    total_alpha = len(re.findall(r"[a-zA-Z]", no_code))

    total = jp_chars + total_alpha
    if total == 0:
        return 1.0

    return jp_chars / total


def should_skip(rel_path: str) -> bool:
    """Check if file should be skipped."""
    # Skip directories
    for skip_dir in SKIP_DIRS:
        if rel_path.startswith(skip_dir):
            return True

    # Skip specific files
    basename = os.path.basename(rel_path)
    if basename in SKIP_FILES:
        return True

    # Skip patterns
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, rel_path):
            return True

    return False


def find_english_files() -> list[tuple[Path, str, float]]:
    """Find .md files that are primarily English."""
    results = []

    for md_file in sorted(CLAUDE_DIR.rglob("*.md")):
        rel = str(md_file.relative_to(CLAUDE_DIR)).replace("\\", "/")

        if should_skip(rel):
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        if len(content.strip()) < 50:  # Skip tiny files
            continue

        ratio = japanese_ratio(content)

        # Only translate files that are less than 25% Japanese
        if ratio < 0.25:
            results.append((md_file, rel, ratio))

    return results


def load_progress() -> set[str]:
    """Load previously translated files."""
    if PROGRESS_FILE.exists():
        data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        return set(data.get("completed", []))
    return set()


def save_progress(completed: set[str]):
    """Save translation progress."""
    PROGRESS_FILE.write_text(
        json.dumps({"completed": sorted(completed)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def translate_file(file_path: Path, content: str) -> str | None:
    """Translate a file using claude -p."""
    prompt = TRANSLATION_PROMPT + content

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(ROOT),
        )

        if result.returncode != 0:
            print(f"  ERROR: claude -p failed: {result.stderr[:200]}", file=sys.stderr)
            return None

        translated = result.stdout.strip()

        # Basic validation: output should not be empty
        if len(translated) < len(content) * 0.3:
            print(f"  WARNING: Translation too short ({len(translated)} vs {len(content)})", file=sys.stderr)
            return None

        return translated

    except subprocess.TimeoutExpired:
        print(f"  ERROR: Timeout translating {file_path.name}", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("ERROR: 'claude' command not found. Install Claude Code CLI first.", file=sys.stderr)
        sys.exit(1)


def main():
    is_run = "--run" in sys.argv
    is_resume = "--resume" in sys.argv

    print("=" * 60)
    print(".claude/ 英語ファイル → 日本語 翻訳スクリプト")
    print("=" * 60)
    print()

    files = find_english_files()

    if not files:
        print("翻訳対象のファイルが見つかりませんでした。")
        return

    # Load progress for resume
    completed = load_progress() if is_resume else set()

    # Filter out already completed
    remaining = [(f, r, ratio) for f, r, ratio in files if r not in completed]

    print(f"翻訳対象: {len(files)} ファイル")
    if completed:
        print(f"翻訳済み: {len(completed)} ファイル")
    print(f"残り: {len(remaining)} ファイル")
    print()

    # Group by category for display
    categories: dict[str, list] = {}
    for file_path, rel, ratio in remaining:
        parts = rel.split("/")
        cat = parts[0] if len(parts) > 1 else "root"
        categories.setdefault(cat, []).append((file_path, rel, ratio))

    for cat, cat_files in sorted(categories.items()):
        print(f"[{cat}] ({len(cat_files)} files)")
        for _, rel, ratio in cat_files:
            jp_pct = f"{ratio*100:.1f}%"
            print(f"  {rel} (JP: {jp_pct})")
        print()

    if not is_run:
        print("---")
        print("ドライランです。実行するには --run を付けてください:")
        print("  python scripts/translate_to_japanese.py --run")
        print("  python scripts/translate_to_japanese.py --run --resume  # 途中から再開")
        return

    # Execute translations
    print("=" * 60)
    print("翻訳を開始します...")
    print("=" * 60)
    print()

    success = 0
    fail = 0

    for i, (file_path, rel, ratio) in enumerate(remaining, 1):
        print(f"[{i}/{len(remaining)}] {rel} ...", end=" ", flush=True)

        content = file_path.read_text(encoding="utf-8")
        translated = translate_file(file_path, content)

        if translated:
            file_path.write_text(translated, encoding="utf-8")
            completed.add(rel)
            save_progress(completed)
            success += 1
            print("OK")
        else:
            fail += 1
            print("FAIL")

        # Small delay to avoid rate limiting
        time.sleep(1)

    print()
    print("=" * 60)
    print(f"完了: {success} 成功, {fail} 失敗")
    print("=" * 60)


if __name__ == "__main__":
    main()
