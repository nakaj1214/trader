# 過去検証（B1）の結果 2026-10-06

期間: 2026-02-16〜2026-07-03（94営業日）。戦略 v3 の閾値は本番と同じで、調整していない。銘柄は含めない。
実行: 再構成 約31分、全体 約48分、最大メモリ 1.09GB。出力: `artifacts/inflection_historical_backtest_summary.json`（gitignore）。

| | disclosure | free_12w |
|---|---|---|
| EARLY_CANDIDATE のシグナル | 102 | 82 |
| 独立した取引（h60 完了） | 18 | 10 |
| h60 の対TOPIX超過リターン | +2.6%（95%CI −15.7〜+21.9） | +6.8%（CI −8.2〜+24.9） |
| 撤退判定 | insufficient_sample | insufficient_sample |
| 追跡プールの爆発銘柄の検出率 | 31.6%（24/76） | 25.0%（19/76） |
| YoY の取得率 | 97〜98% | 91〜94% |

lag の差（disclosure − free_12w）: 平均 −4.1%、CI −34.4〜+22.5、共通のシグナル日 7。

## 結論
標本が少なく（必要100件に対し18件・10件）、戦略の良し悪しも lag の差も判断できない。
EARLY_CANDIDATE の h60 は、期間が短く完了数が少ない。シグナル開始は財務 warmup（494日）で 2026-02-16 が下限。
次は forward の日次 snapshot の蓄積で、同じ基準の判定を待つ。
