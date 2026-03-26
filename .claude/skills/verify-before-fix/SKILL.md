---
name: verify-before-fix
description: >
  バグ修正・機能修正に着手する前に、推測ではなく証拠を収集して原因を特定するゲートスキル。
  フロントエンド問題では antigravity IDE でスクリーンショット・DOM キャプチャ・コンソールログを取得し、
  バックエンド問題では docker compose exec によるログ・クエリ確認、Python ではテスト実行で検証する。
  「直して」「バグ修正して」「改善されていない」「動かない」と言われたとき、
  または proposal.md に修正依頼が記載されているときにトリガーする。
  証拠が揃うまでコード修正に進むことを禁止し、推測による時間浪費を防止する。
---

# 証拠に基づく修正ゲート

詳細な手順: [INSTRUCTIONS.md](INSTRUCTIONS.md)

## リソース

- [INSTRUCTIONS.md](INSTRUCTIONS.md) — 5フェーズの検証プロセス・レイヤー別検証手段・停止条件
- [references/browser-verification.md](references/browser-verification.md) — antigravity ブラウザ検証手段
- [evaluations/evals.json](evaluations/evals.json) — テストケース

## 関連スキル

- [systematic-debugging](../systematic-debugging/SKILL.md): 4段階デバッグプロセス（本スキルで原因特定後に使用）
- [fix-escalation](../fix-escalation/SKILL.md): 2回失敗時の方針転換強制（本スキルの停止条件と連動）
- [code-review](../code-review/SKILL.md): コード品質レビュー
