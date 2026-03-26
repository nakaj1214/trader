---
name: error-doc-fix
description: >
  docs/error/error.md のエラー報告を解析し、原因特定→修正→検証を一括実行する。
  「エラーを直して」「error.md を確認して修正」「docs/error/ のエラーを解決」
  と言われたときにトリガーする。
metadata:
  short-description: error.md のエラー → 原因特定 → 修正 → 検証
---

# Error Doc Fix

`docs/error/error.md` に記載されたエラー報告を解析し、
原因特定 → コード修正 → 検証までを一括で実行する。

詳細な手順: [INSTRUCTIONS.md](INSTRUCTIONS.md)

## 想定フロー

```
docs/error/error.md（エラー報告）
    ↓  /error-doc-fix
原因特定 → コード修正 → 検証
    ↓
error.md の該当エラーをコメントアウト（解決済み）
```

## リソース

- [INSTRUCTIONS.md](INSTRUCTIONS.md) — 解析手順・修正ルール・報告テンプレート

## 関連スキル

- [verify-before-fix](../verify-before-fix/SKILL.md): 証拠収集ゲート（修正前に自動連携）
- [systematic-debugging](../systematic-debugging/SKILL.md): 原因不明時のデバッグプロセス
- [fix-escalation](../fix-escalation/SKILL.md): 2回失敗時のエスカレーション
