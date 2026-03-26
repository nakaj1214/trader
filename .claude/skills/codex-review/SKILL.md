---
name: codex-review
description: |
  指定されたドキュメントファイルに対して Codex（gpt-5.4）レビューループを実行する。
  MCP サーバー経由で Codex を呼び出し（base-instructions でプロジェクト instruction 読み込みを回避）、
  APPROVED になるか最大反復回数に達するまで、各ラウンドで Claude がブロッキング問題を修正する。
  異なる AI モデル（GPT系）による独立レビューで、Claude の自己レビューでは検出できない問題を発見する。
  トリガー: "Codex review", "codex-review", "review with Codex", "Codex loop"。
metadata:
  short-description: Codex review loop via MCP (gpt-5.4, cross-model review)
---

# Codex Review

指定されたドキュメントファイルに対して Codex MCP サーバー経由でレビューループを実行する。
APPROVED になるまで（または最大反復回数に達するまで）、Codex レビュー → Claude 修正 を繰り返す。

詳細な手順: [INSTRUCTIONS.md](INSTRUCTIONS.md)

## リソース

| ファイル | 内容 | ロードタイミング |
|--------|------|------------|
| [INSTRUCTIONS.md](INSTRUCTIONS.md) | ワークフローと詳細指示 | スキル起動時 |
