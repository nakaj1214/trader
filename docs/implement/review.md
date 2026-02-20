# plan.md レビュー（2026-02-20 再レビュー）

## Findings
- 新規の High / Medium 指摘はありません。

## Resolved From Previous Review
- フェーズ11/12のUI導線不整合は解消済み。
  - `dashboard/stock.html` に `short-interest-panel` / `institutional-panel` が追加され、`stock.js` 側の描画先と一致。
  - 根拠: `docs/implement/plan.md:31`, `docs/implement/plan.md:70`, `dashboard/stock.html:44`, `dashboard/stock.html:47`, `dashboard/js/stock.js:298`, `dashboard/js/stock.js:324`
- フェーズ15の設定構造不整合は解消済み。
  - `config.yaml` 例が `screening.markets` 配下へ修正され、実装参照構造と一致。
  - 根拠: `docs/implement/plan.md:251`, `docs/implement/plan.md:258`, `config.yaml:4`, `src/screener.py:225`

## Residual Risks / Testing Gaps
- フェーズ11/12のUI接続は手動確認前提になっているため、`short-interest-panel` / `institutional-panel` のDOM存在を担保する軽量フロントエンドテスト（または静的検証）を追加すると再発防止に有効です。
- フェーズ15/16は将来計画として妥当ですが、`predictions_us.json` / `predictions_jp.json` 分離時に既存 `exporter.py` の出力契約（`predictions.json`）をどう互換維持するかを、着手時に明文化しておくと移行が安全です。

## Summary
- 現在の `plan.md` は、前回レビューで挙げた主要不整合を解消済みです。
- 現時点では実装計画として着手可能な品質です。
