---
name: propose-one
description: >
  docs/implement/prompt.md から課題を1つだけ選び、create-proposal → create-plan を順に実行する。
  「1個ずつ確実に修正」のワークフローを強制し、複数課題を同時に扱うことで生じる混乱を防ぐ。
  「1つだけ実装して」「一個ずつ進めて」「propose-one」「最初のタスクだけ」と言われたときにトリガーする。
  create-proposal + create-plan の単一課題版ラッパー。
metadata:
  short-description: prompt.md → 1課題選択 → proposal.md → plan.md
  dependencies:
    - create-proposal
    - create-plan
---

# 単一課題の計画実行

prompt.md から課題を1つ選んで create-proposal → create-plan を順に実行する。

詳細な手順: [INSTRUCTIONS.md](INSTRUCTIONS.md)

## 想定フロー

```
prompt.md（複数課題）
    ↓  ユーザーが1つ選択
prompt.md（選択課題のみ抽出）
    ↓  create-proposal（品質チェック付き）
proposal.md（構造化された要件書）
    ↓  create-plan（Codex レビュー付き）
plan.md（実装計画書）
```

## リソース

- [INSTRUCTIONS.md](INSTRUCTIONS.md) — 課題選択 → create-proposal → create-plan の手順

## 関連スキル

- [create-proposal](../create-proposal/SKILL.md): prompt.md → proposal.md（Step 2 で使用）
- [create-plan](../create-plan/SKILL.md): proposal.md → plan.md（Step 3 で使用）
- [implement-plans](../implement-plans/SKILL.md): plan.md の実装（後続）
