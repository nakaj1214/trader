---
name: fix-escalation
description: >
  同じバグに対して修正が2回失敗したとき、試行履歴を根拠にエスカレーション調査を強制するスキル。
  試行ごとの仮説・修正内容・失敗理由を tasks/fix-attempts.md に自動記録し、
  2回失敗で「視点を変えた再調査」を強制する。方針転換なしの3回目修正を禁止する。
  「何度直しても直らない」「N回目の修正」「また同じバグ」「改善されていない」と
  言われたとき、または verify-before-fix の停止条件が発動したときにトリガーする。
metadata:
  short-description: 2回失敗で方針転換を強制。試行履歴の自動記録 + エスカレーション調査
---

# 修正エスカレーション

同じバグに2回失敗したら方針転換を強制する。試行履歴を自動記録し、堂々巡りを防止する。

詳細な手順: [INSTRUCTIONS.md](INSTRUCTIONS.md)

## フロー概要

```
バグ報告 / 「改善されていない」
    ↓
Step 1: 履歴確認（tasks/fix-attempts.md）
    ↓
    ├─ 0-1回失敗 → Step 2: 通常デバッグ記録
    └─ 2回+失敗 → Step 3-4: エスカレーション調査 + 方針転換
    ↓
Step 5: 修正実施 + 結果記録
    ↓
Step 6: 検証（成功→完了 / 失敗→Step 1 に戻る）
```

## リソース

- [INSTRUCTIONS.md](INSTRUCTIONS.md) — 6ステップフロー・エスカレーション手順・試行履歴フォーマット
- [references/attempt-template.md](references/attempt-template.md) — fix-attempts.md のテンプレート

## 関連スキル

- [verify-before-fix](../verify-before-fix/SKILL.md): 証拠収集ゲート（前段で連携）
- [systematic-debugging](../systematic-debugging/SKILL.md): 4段階デバッグ（Step 2 で手順を利用）
- [feedback-loop](../feedback-loop/SKILL.md): 学習記録（解決後に連携）

## Hook

`fix-escalation-detector.py` — ユーザーメッセージから失敗パターンを検知し、
試行履歴をコンテキストに注入する（settings.json に登録済み）。
