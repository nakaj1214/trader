---
name: semgrep
description: >
  並列サブエージェントを使用してコードベースに Semgrep 静的解析スキャンを実行する。
  利用可能な場合は自動的に Semgrep Pro を検出しクロスファイル解析に使用する。
  脆弱性スキャン、Semgrep によるセキュリティ監査、バグ検出、静的解析の依頼時に使用する。
  多言語コードベースとトリアージ用に並列ワーカーを起動する。
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
  - Write
  - Task
  - AskUserQuestion
  - TaskCreate
  - TaskList
  - TaskUpdate
  - WebFetch
---

# Semgrep Security Scan

詳細な手順: [INSTRUCTIONS.md](INSTRUCTIONS.md)

## リソース

- [INSTRUCTIONS.md](INSTRUCTIONS.md) — 詳細手順・ルール・例
