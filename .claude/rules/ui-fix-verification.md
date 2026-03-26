---
paths:
  - "**/*.js"
  - "**/*.css"
  - "**/*.scss"
  - "**/*.html"
  - "**/*.blade.php"
---

# UI 修正検証ルール

検証プロセス全般は `/verify-before-fix` スキルを参照。
このルールはフロントエンド固有の **解釈ミス防止** と **実行パス確認** に特化する。

---

## 要件を文字通りに読む

`prompt.md` / `proposal.md` やバグレポート（日本語）を読む際:

- "〜が存在している" = 削除する
- "文字がない" = テキストを追加する
- "中央になってない" = `vertical-align: middle` または同等のものを追加
- "大きさが違う" = padding/height/font-size を統一する

**最もシンプルな修正から始める。** 5分以内で終わるはずの修正に時間がかかっている場合は要件を読み直す。

"改善されていない（N回目）" は **要件を読み間違えている** ことを意味する。

---

## UI 変更後の実行パス確認

### イベントハンドラー
- jQuery セレクターが実際に DOM に一致するか？
- イベントはバインド時に存在する親要素に委譲されているか？

### 非同期操作
- `ajax.reload()` にリロード後の処理用コールバックがあるか？
- スクロール復元はデータレンダリング完了後に呼ばれているか？

### CSS オーバーライド
- JS で注入されるすべてのプロパティを確認する（`background` だけでなく `box-shadow`、`outline`、`border` も）
- 注入スタイルの `!important` に勝つために `#id` セレクターを使用する

### このプロジェクト固有のコンポーネント
- タブ: `<div class="tab" data-tab="...">` — Bootstrap の `<a data-bs-toggle="tab">` ではない
- DataTables Scroller: `scroller.toPosition(rowIndex)` を使用 — `scrollTop(px)` ではない
