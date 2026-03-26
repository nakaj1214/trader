## プロジェクト概要

Laravel+jQuery の在庫管理システム。Docker Compose で MariaDB + PHP + phpMyAdmin を構成。

## コア原則

- **シンプル第一**: 影響するコードを最小限に。過剰設計しない
- **根本原因を修正**: 一時的な修正は避ける
- **人間が最終責任者**: エージェントの成果物はすべて人間がレビュー・承認する

## ワークフロー

- 3ステップ以上のタスクは Plan モード
- 調査と実装を混ぜない。調査で方針確定 → 実装
- 終了時 `/handover`
- バグ修正前に `verify-before-fix` で証拠収集

## タスク管理

- 計画 → `tasks/todo.md` に書く → 進捗記録 → 完了マーク
- 修正を受けたら `.claude/docs/lessons.md` を更新

## セッション開始チェック

1. `.claude/docs/PROJECT-PROFILE.md`
2. `.claude/docs/user-preferences.md`
3. `.claude/docs/memory/HANDOVER-*.md`（最新）
4. `.claude/docs/lessons.md`（直近3件）

## フィードバック記録

修正を受けたら feedback-loop スキルの手順に従う。

## トラブルシューティング

`.claude/docs/playbooks.md` を参照。
