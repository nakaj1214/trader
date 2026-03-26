---
name: create-proposal
description: >
  docs/implement/prompt.md（ユーザーの自由な依頼文）を読み込み、構造化した
  docs/implement/proposal.md（実装要件書）を生成する。品質チェック（7項目）で
  曖昧な記述・繰り返し失敗パターン・具体性不足を検出し、必要に応じてリライトする。
  create-plan とは独立したスキル。「要件を整理して」「proposalを作って」
  「prompt.mdから要件書を作って」と言われたときにトリガーする。
metadata:
  short-description: prompt.md → proposal.md（要件構造化 + 品質チェック）
---

# Create Proposal

`docs/implement/prompt.md`（ユーザーの依頼文）を読み込み、
構造化した `docs/implement/proposal.md`（実装要件書）を生成する。

create-plan とは独立しており、単体で実行できる。
生成後は `/create-plan` で計画書に変換できる。

詳細な手順: [INSTRUCTIONS.md](INSTRUCTIONS.md)

## 想定フロー

```
prompt.md（自由な依頼文）
    ↓  /create-proposal
proposal.md（構造化された要件書）
    ↓  /create-plan
plan.md（実装計画書）
    ↓  /implement-plans
実装
```

## リソース

- [INSTRUCTIONS.md](INSTRUCTIONS.md) — 構造化テンプレート・品質チェック基準・リライトロジック

## 関連スキル

- [create-plan](../create-plan/SKILL.md): proposal.md → plan.md（後続）
- [proposal-quality-gate](../proposal-quality-gate/SKILL.md): proposal.md の品質チェック（create-plan 内で使用）
- [implement-plans](../implement-plans/SKILL.md): plan.md の実装
