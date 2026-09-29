# JP Inflection Shadow Scan 再試行機能 計画レビュー

レビュー日: 2026-09-29

対象: `memo/implement/plan.md`

## 結論

前回の残件2点が計画に反映されていないため、実装は見送ります。

## 指摘事項

### P2: provider 層の変更は不要

Section 6 は依然として `src/data/yfinance_prices.py` へ stale 再取得・置換処理を追加し、`tests/test_yfinance_prices.py` も変更対象にしています。

既存 `fetch_price_data()` は任意の ticker subset を取得できます。期待営業日を知る scanner 側で、既存関数の結果を更新するだけで足ります。

```python
prices.update(fetch_price_data(retry_tickers, lookback_days))
```

`src/data/yfinance_prices.py` と `tests/test_yfinance_prices.py` を修正対象から外してください。

### P2: J-Quants retry は今回の対象外

Section 10 の「J-Quants 一時通信エラー | 必要に応じて別 retry」も未変更です。回数・待機・対象例外・テストが定義されておらず、今回の Yahoo 株価再試行とは独立した要件です。

今回は「即 Failure」と明記し、J-Quants retry は別計画にしてください。

## 修正条件

1. stale 再取得は scanner から既存 `fetch_price_data()` を再利用する。
2. J-Quants retry は今回の対象から外す。
