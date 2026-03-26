---
name: skill-stocktake
description: Audits Claude skills and commands using a quality checklist + AI holistic judgment. Claude のスキルとコマンドを品質チェックリスト＋AI総合判断で監査する。月次メンテナンスに使用。
tools: Read, Write, Edit, Bash, Grep, Glob
origin: everything-claude-code
---

# スキル棚卸し

出典: [everything-claude-code](https://github.com/affaan-m/everything-claude-code) `skills/skill-stocktake`

## 概要

Claude のスキルとコマンドを「品質チェックリスト＋AI 総合判断」で監査する。
Quick Scan（5〜10分）と Full Stocktake（20〜30分）の2モードで動作。

## 対象ディレクトリ

- `~/.claude/skills/`（グローバル）
- `{cwd}/.claude/skills/`（プロジェクトレベル）

## モード選択

| モード | 条件 | 所要時間 |
|--------|------|---------|
| **Quick Scan** | `results.json` が存在する場合（変更されたスキルのみ再評価） | 5〜10分 |
| **Full Stocktake** | `results.json` がない場合、または明示的に `full` 指定 | 20〜30分 |

## 4フェーズプロセス

### Phase 1 — インベントリ
`scripts/scan.sh` でスキルファイルを列挙し、フロントマターを抽出、更新日時を収集してサマリーテーブルを作成。

### Phase 2 — 品質評価
サブエージェント（Explore エージェント、Opus モデル）が各スキルに以下のチェックリストを適用:

- [ ] コンテンツの重複がないか
- [ ] 技術的参照が最新か（WebSearch でツール/API を確認）
- [ ] 使用頻度は十分か
- [ ] MEMORY.md / CLAUDE.md との整合性

### 評価結果

| 判定 | 意味 |
|------|------|
| **Keep** | そのまま維持 |
| **Improve** | 内容の改善が必要 |
| **Update** | 技術的参照の更新が必要 |
| **Retire** | 廃止推奨 |
| **Merge into [X]** | 別スキルへの統合推奨 |

### Phase 3 — サマリーテーブル
判定と理由を一覧表示。

### Phase 4 — 統合
retire/merge アクションの前に詳細な根拠を提示。改善提案はユーザー承認が必要。

## 結果の保存

`~/.claude/skills/skill-stocktake/results.json` にキャッシュ:

```json
{
  "timestamp": "2026-03-08T12:00:00Z",
  "mode": "full",
  "skills": [
    {
      "name": "example-skill",
      "verdict": "Keep",
      "reasoning": "アクティブに使用されており品質も良好"
    }
  ]
}
```
