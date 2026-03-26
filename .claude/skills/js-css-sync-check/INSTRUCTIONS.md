# js-css-sync-check 実行手順

## 目的

JS ファイルで UI スタイルに関わる変更を行った際、対応する CSS ファイルの同期確認を行い、
スタイル不整合（JS で参照するクラスが CSS に定義されていない等）を防止する。

### なぜこのスキルが必要か

編集パターン分析で繰り返し観察された問題:
- `excel_range_select_copy.js` の描画手法変更のたびに `stock.css` の追従修正が必要だった（6回以上）
- JS 側で `box-shadow` → `outline` → `::after` と手法を変える度に CSS の書き直しが発生
- JS と CSS の変更がバラバラに行われ、中間状態で表示が崩れる

## 手順

### Step 1: 変更された JS ファイルの特定

編集対象の JS ファイルから、スタイル関連の変更を抽出する。

検出キーワード:
- `className`, `classList.add`, `classList.remove`, `classList.toggle`
- `style.`, `cssText`
- `box-shadow`, `border`, `outline`, `background`, `opacity`
- `SELECTED_CLASS`, `HIGHLIGHT_CLASS` 等のスタイル定数
- `position`, `z-index`, `::before`, `::after`

### Step 2: 対応する CSS ファイルの特定

以下のヒューリスティックで対応 CSS を特定する:

1. **同名ファイル**: `stock.js` -> `stock.css`
2. **同ディレクトリの CSS**: JS と同じディレクトリまたは `css/` サブディレクトリ
3. **既知のペア**（プロジェクト固有）:
   - `excel_range_select_copy.js` <-> `stock.css`
   - `stock.js` <-> `stock.css`
   - `datatable.js` <-> `stock.css`
4. **Blade テンプレートからの参照**: 対応する `.blade.php` ファイルで `<link>` タグから CSS パスを取得

### Step 3: CSS 同期チェック

JS の変更内容に基づいて、CSS ファイルで以下を確認する:

1. **クラス名の定義確認**: JS で追加・参照するクラスが CSS に定義されているか
2. **プロパティの整合性**: JS で inline style として設定するプロパティが CSS の既存ルールと衝突しないか
3. **疑似要素の定義**: `::before` / `::after` を JS から操作する場合、CSS に基本定義があるか
4. **メディアクエリへの影響**: レスポンシブスタイルが変更の影響を受けないか

### Step 4: レポート出力

以下の形式で結果を報告する:

```
## JS-CSS 同期チェック結果

### 変更された JS ファイル
- {file_path}: {変更概要}

### 対応する CSS ファイル
- {css_path}: {確認結果}

### 必要なアクション
- [ ] {CSS 側で必要な変更があれば記載}
- [x] 同期確認済み（変更不要の場合）
```

## 注意事項

- CSS の変更は JS の変更と同じコミットに含めること
- スタイル手法を変更する場合（例: `box-shadow` -> `::after`）は、CSS 側の旧スタイル定義の削除も忘れずに行う
- 不明な場合は `/verify-before-fix` で実際の表示を確認してから CSS を修正する
