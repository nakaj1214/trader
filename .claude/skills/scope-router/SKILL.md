---
name: scope-router
description: >
  チャットから機能追加・バグ修正の実装依頼を受けたとき、作業規模を自動判定して適切なワークフローにルーティングする。
  1ファイル・単純な変更は直接実装、1ファイルでも複雑な場合は create-plan、
  複数ファイルにまたがる場合は create-proposal → create-plan に派生する。
  「〜を実装して」「〜を追加して」「〜を修正して」「〜のバグを直して」などの依頼が来たときにトリガーする。
---

# スコープルーター

詳細な手順: [INSTRUCTIONS.md](INSTRUCTIONS.md)

## リソース

- [INSTRUCTIONS.md](INSTRUCTIONS.md) — 規模判定ロジックとルーティング手順

## 関連スキル

- [create-proposal](../create-proposal/SKILL.md): 要件書生成（中・大規模で使用）
- [create-plan](../create-plan/SKILL.md): 実装計画生成（中・大規模で使用）
- [verify-before-fix](../verify-before-fix/SKILL.md): バグ修正前の証拠収集
