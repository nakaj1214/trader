---
name: doing-something
# ↑ gerund形式推奨: processing-pdfs, analyzing-spreadsheets, writing-reports
# 小文字・ハイフン区切り・最大64文字。"anthropic" "claude" は使用不可
description: >
  [第三者視点で記述] このスキルは〜を行う。〜の場面で使用する。
  具体的なキーワードとトリガーフレーズを含める。最大1024文字。
  NG: "I can help you..." / "You can use this..."
  例: "Extracts text from PDF files and saves to output.txt.
  Use when working with PDF files or when the user mentions PDFs, forms, or document extraction."
---

# [スキル名]

[1〜2行の概要。このスキルが何をするかを簡潔に。]

詳細な手順: [INSTRUCTIONS.md](INSTRUCTIONS.md)

## リソース

| ファイル | 内容 | ロードタイミング |
|--------|------|------------|
| [INSTRUCTIONS.md](INSTRUCTIONS.md) | ワークフローと詳細指示 | スキル起動時 |
| [evaluations/evals.json](evaluations/evals.json) | テストケース（精度保証） | 開発・改善時 |
| [references/guide.md](references/guide.md) | 参照ドキュメント | 必要に応じて |
| [scripts/process.py](scripts/process.py) | 実行スクリプト | 実行時のみ |

---

<!-- ===== 以下はSKILL作成ガイド。作成完了後に削除する ===== -->

## SKILL作成のベストプラクティス

### ディレクトリ構造（推奨）

```
skill-name/
├── SKILL.md              # 必須: フロントマター + 概要 + 参照リンク（500行以内）
├── INSTRUCTIONS.md       # 詳細なワークフロー（二段階ロード設計）
├── evaluations/          # 精度保証に必須（eval-driven development）
│   └── evals.json
├── references/           # 詳細参照資料（ドメイン別に分割可）
│   ├── guide.md
│   └── advanced.md
├── scripts/              # 実行スクリプト（コンテキストを消費しない）
│   └── process.py
└── assets/               # 出力用テンプレートファイル
    └── template.md
```

### 設計原則: 二段階ロード

コンテキストウィンドウは共有資源。常に注入されるのは **name + description のみ**:

1. **Stage 1（常時）**: フロントマター（name, description）〜200バイト
2. **Stage 2（スキル起動時）**: SKILL.md 本文（500行以内推奨）
3. **Stage 3（必要時）**: INSTRUCTIONS.md, references/ など（無制限）

→ SKILL.md 本文は「目次」として機能させ、詳細は INSTRUCTIONS.md へ

### evaluations/evals.json の構造

**評価は SKILL.md を書く前に作成する（評価駆動開発）**

```json
{
  "skill_name": "skill-name",
  "evals": [
    {
      "id": 1,
      "prompt": "実際のユーザーが言いそうな自然なプロンプト",
      "expected_output": "期待される振る舞いの説明",
      "files": [],
      "assertions": [
        "assertion 1: 確認すべき具体的な動作",
        "assertion 2: 確認すべき具体的な動作"
      ]
    },
    {
      "id": 2,
      "prompt": "別のシナリオ（典型的なユースケース）",
      "expected_output": "期待される振る舞い",
      "files": [],
      "assertions": []
    },
    {
      "id": 3,
      "prompt": "エッジケースのシナリオ",
      "expected_output": "期待される振る舞い",
      "files": [],
      "assertions": []
    }
  ]
}
```

### SDK・Claude -p との統合（チーム・組織での運用）

個人を超えてチームや自動化パイプラインで使うには:

```bash
# Claude Code CLIでの非対話実行（-p = print mode）
claude -p "PDFからテキストを抽出して" \
  --skill ./skills/processing-pdfs/

# パイプラインでの利用
echo "このファイルを処理して" | claude -p --skill ./skills/skill-name/
```

```python
# Anthropic Agent SDK での利用
import anthropic

client = anthropic.Anthropic()
# スキルをシステムプロンプトに組み込むか、
# Agent SDK の skill 機能を使用する
```

### テストのチェックリスト

- [ ] evaluations/evals.json に最低3つの eval がある
- [ ] eval 作成後に SKILL.md を書いた（評価駆動開発）
- [ ] description は第三者視点（"I can..." は NG）
- [ ] description に「何をするか」と「いつ使うか」が含まれる
- [ ] SKILL.md 本文は500行以内
- [ ] 参照ファイルは SKILL.md から1レベルの深さ
- [ ] Haiku・Sonnet・Opus の全モデルでテスト済み
- [ ] ファイルパスはすべて `/` 区切り（`\` は使わない）
