# plan.md レビュー（2026-02-21 再レビュー）

## Findings
1. [Low] フェーズ25の `config` 受け渡し説明で呼び出し方向が逆になっている
- 根拠: `docs/implement/plan.md:1626` に「`predict_stock()` が `predict()` を呼ぶ際」とありますが、実コードは `predict()` から `predict_stock()` を呼ぶ構造です（`src/predictor.py:57`, `src/predictor.py:111`）。同様の方向表現がステップにも残っています（`docs/implement/plan.md:1636`）。
- 影響: 実装者が引数受け渡しの改修箇所を誤認する可能性があります。
- 修正提案: 文言を「`predict()` が `predict_stock()` を呼ぶ際に `config`（または prophet設定）を渡す」に修正してください。

## Resolved From Previous Review
- フェーズ22: APIバージョン制御の矛盾は解消済み。
  - `config` 制御をやめ、`JQUANTS_API_KEY` 有無で自動判定する方針に統一されています。
  - 根拠: `docs/implement/plan.md:1089`, `docs/implement/plan.md:1139`
- フェーズ23: 流動性閾値仕様の曖昧さは解消済み。
  - US/JP 別閾値（`min_avg_dollar_volume_us` / `min_avg_dollar_volume_jp`）で仕様・実装案・受け入れ条件が揃っています。
  - 根拠: `docs/implement/plan.md:1219`, `docs/implement/plan.md:1260`, `docs/implement/plan.md:1315`

## Summary
- 新規の High / Medium 指摘はありません。実装前に上記 Low 1件の文言を直せば、計画としての整合性は高い状態です。
