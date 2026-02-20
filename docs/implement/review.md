# ヘルプ機能レビュー（USER_GUIDE.md 準拠）

## 結論
- `index.html` / `accuracy.html` / `simulator.html` / `stock.html` にヘルプ導線（`?`ボタン）は実装されています。
- ただし、ユーザー向けヘルプ文言に不整合があり、修正が必要です。

## 指摘事項と修正案

### 1. HELP_CONTENT の誤字（優先度: 高）
- 対象: `dashboard/js/app.js:95`, `dashboard/js/app.js:97`, `dashboard/js/app.js:103`, `dashboard/js/app.js:104`, `dashboard/js/app.js:108`, `dashboard/js/app.js:132`
- 事象: Unicodeエスケープ文字列に誤りがあり、表示文言が不自然（例: 「銅柄4」「銃柄」「倉想」）。
- 修正案:
  - `\u9283\u67c4` を `\u9298\u67c4`（銘柄）へ統一
  - `\u4ed3\u60f3` を `\u4eee\u60f3`（仮想）へ修正
  - `\u6bce\u9031\u306e\u4e0a\u6607\u4e88\u6e2c\u9285\u67c04\u3092` を `\u6bce\u9031\u306e\u4e0a\u6607\u4e88\u6e2c\u9298\u67c4\u3092` へ修正
- 備考: 文字列を Unicode エスケープで保持する場合は、同種文字列（銘柄/仮想）を一括置換すると取りこぼしを防げます。

### 2. USER_GUIDE の LINE 補助通知説明がヘルプに未反映（優先度: 中）
- 根拠: `docs/guide/USER_GUIDE.md:8`, `docs/guide/USER_GUIDE.md:36`, `docs/guide/USER_GUIDE.md:37`, `docs/guide/USER_GUIDE.md:38`
- 事象: ヘルプモーダル（`dashboard/js/app.js` の `HELP_CONTENT`）に LINE 補助通知の説明がない。
- 修正案:
  - 「このシステムでできること」に以下を追加:
    - `必要に応じて LINE で「Slack確認リマインド」を受け取る`
  - 追記（短文）:
    - `LINEは補助通知です（Slack確認の促進）`
    - `LINE失敗時でも Slack が届いていれば運用は継続されます`

### 3. simulator ページ見出しの用語不一致（優先度: 低）
- 対象: `dashboard/simulator.html:34`
- 事象: 見出しが「料金シミュレータ」になっており、ガイドの「投資シミュレータ」と不一致。
- 修正案:
  - `料金シミュレータ` → `投資シミュレータ`

## 受け入れ確認チェック
- ヘルプモーダル内で「銘柄」「仮想」が正しく表示される
- ヘルプモーダル内に LINE 補助通知の説明が表示される
- `simulator.html` の見出しが「投資シミュレータ」になっている
