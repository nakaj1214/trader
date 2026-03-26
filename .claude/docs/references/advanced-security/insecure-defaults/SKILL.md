---
name: insecure-defaults
description: "本番環境でアプリを安全でない状態で動作させる fail-open な危険デフォルト値（ハードコードされたシークレット、弱い認証、緩いセキュリティ設定）を検出する。セキュリティ監査、設定管理のレビュー、環境変数の取り扱い分析に使用する。"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
---

# Insecure Defaults Detection

詳細な手順: [INSTRUCTIONS.md](INSTRUCTIONS.md)

## リソース

- [INSTRUCTIONS.md](INSTRUCTIONS.md) — 詳細手順・ルール・例
