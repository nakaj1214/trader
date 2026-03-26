# open-feature-files

機能名から関連ファイル（JS + CSS + blade.php）の3点セットを特定し、一覧表示する。

## 実行手順

### 1. 機能名の抽出

ユーザーのプロンプトから機能名（feature）を抽出する。
例: 「在庫を修正して」→ `stock`、「発注確認を実装」→ `manager/confirm`

### 2. 関連ファイルの検索

以下のパターンで Glob 検索する:

```
src/public/js/**/*{feature}*.js
src/public/css/**/*{feature}*.css
src/resources/views/**/*{feature}*.blade.php
```

### 3. co-edit ペアの確認

既知の co-edit ペア（よく一緒に編集されるファイル）:

| 機能 | JS | CSS | blade.php |
|------|-----|-----|-----------|
| stock | `home/stock/stock.js` | `home/stock.css` | `home/stock.blade.php` |
| order | `home/order/order.js` | `home/order.css` | `home/order.blade.php` |
| inbound | `home/inbound/inbound.js` | `home/inbound.css` | `home/inbound.blade.php` |
| manager confirm | `manager/manager_confirm.js` | `manager/confirm.css` | `manager/confirm.blade.php` |

### 4. 結果の表示

検出したファイルを一覧表示する:

```
## {feature} 関連ファイル

### JS
- src/public/js/...

### CSS
- src/public/css/...

### View
- src/resources/views/...
```

関連ファイルが見つからない場合は「該当するファイルが見つかりませんでした」と報告する。
