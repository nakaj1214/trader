---
name: create-plan
description: |
  Reads docs/implement/proposal.md and creates docs/implement/plan.md.
  Then creates a test file (docs/tests/{feature}.test.js or .test.html) and verifies behavior.
  Reports results and stops — does NOT auto-start implement-plans.
  Codex レビューループ版は /codex-loop-create-plan を使うこと。
metadata:
  short-description: Proposal → Plan + テストファイル作成（報告して停止）
  dependencies: []
---

# Create Plan

`docs/implement/proposal.md` を読み込み、`docs/implement/plan.md` を作成する。
その後テストファイルを作成して挙動を確認し、結果を報告して停止する（自動実装しない）。

詳細な手順: [INSTRUCTIONS.md](INSTRUCTIONS.md)

## リソース

- [INSTRUCTIONS.md](INSTRUCTIONS.md) — 5ステップワークフロー（Read → Investigate → Create → Test → Done）
- [codex-loop-create-plan](../codex-loop-create-plan/SKILL.md) — Codex レビューループ版（旧 create-plan）
