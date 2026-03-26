---
name: js-css-sync-check
description: JS ファイルの UI スタイル変更後に、対応する CSS ファイルの同期チェックを促す。JS+CSS のペア変更忘れを防止し、スタイル不整合バグを未然に防ぐ。セル描画・選択ハイライト・ボーダー描画などの UI 変更時に特に有効。
---

# js-css-sync-check

JS ファイルで UI スタイルに関わる変更を行った後、対応する CSS ファイルの確認・更新を促すスキル。

## トリガー条件

以下のいずれかに該当する JS 編集が行われた場合:
- `className`、`classList`、`style.`、`cssText` の操作
- `box-shadow`、`border`、`outline`、`background` 等のスタイルプロパティ
- `::before`、`::after` 等の疑似要素に関連するクラス操作

## 実行フロー

1. INSTRUCTIONS.md の手順に従って実行する
