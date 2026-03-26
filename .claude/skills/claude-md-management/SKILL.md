---
name: claude-md-improver
description: >
  Audits and improves CLAUDE.md files across a repository by scanning all instances, evaluating quality against a rubric, generating a quality report, and applying targeted updates. Use when asked to review, audit, update, improve, or fix CLAUDE.md files, or when the user mentions "CLAUDE.md maintenance" or "project memory optimization."
  リポジトリ内の全CLAUDE.mdファイルを監査・評価・改善するスキル。全ファイルをスキャンして品質レポートを出力し、ターゲットを絞った改善を適用する。CLAUDE.mdの確認・監査・更新・改善依頼時、またはプロジェクトメモリ最適化に言及したときに使用する。
tools: Read, Glob, Grep, Bash, Edit
---

# CLAUDE.md改善スキル

コードベース全体のCLAUDE.mdファイルを監査・評価・改善して、Claude Codeが最適なプロジェクトコンテキストを持てるようにする。

詳細な手順: [INSTRUCTIONS.md](INSTRUCTIONS.md)

## リソース

- [INSTRUCTIONS.md](INSTRUCTIONS.md) — 5フェーズのワークフロー・品質評価基準・差分フォーマット・テンプレートの全内容
- [evaluations/evals.json](evaluations/evals.json) — テストケース（作成推奨）
