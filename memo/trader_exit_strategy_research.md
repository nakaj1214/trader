# trader リポジトリ 売却タイミング調査レポート

**爆発後の利益をできるだけ残すための Exit Strategy 調査**

- 初回調査日: 2026-09-08
- 最終確認日: 2026-09-08
- 今回の変更: 実コードとの照合、検証上の注意点、外部サービス、Trailing Exitの実装状況を反映

## 1. 結論

現在の `trader` は、**上昇前の買い候補を発見し、固定期間と単純なTrailing Stopを将来検証する仕組み**である。ライブの保有ポジション、高値更新、分割利確、売却アラートを管理する仕組みはまだない。

「最高値そのもので売る」ことは将来情報なしには不可能であるため、目標は **最高値を更新している間は保有し、事前に定めたピークアウト条件で退出して、利益の返上を抑えること**に置く。

- 本番 scanner は候補発見専用で、保有後の継続監視は行わない。
- forward validation は翌営業日始値で入り、5・20・60営業日後の終値を別々に評価する。
- 終値ベース指標に加え、日中 High/Low ベースの MFE/MAE とTrailing Stopの売却結果を記録する。
- 旧パイプラインの損切り機能は `archive/legacy/` にあり、現行経路では使われない。
- 最初に作るべきものはリアルタイム発注ではなく、日足 High/Low を使う Exit 専用バックテストである。

## 2. 現在の本番フロー

現在の production path は、平日 16:40 JST に GitHub Actions で実行される日本株 inflection shadow scan。

1. J-Quants V2 から TSE Prime / Standard / Growth の銘柄を取得
2. yfinance から価格・出来高を取得
3. 流動性と短期モメンタムで一次選別
4. 上位候補のみ J-Quants 財務データで深掘り
5. `EARLY_CANDIDATE` / `WATCH` / `OVEREXTENDED` / `NONE` に分類
6. 暗号化した日次スナップショットを保存
7. 失敗時のみ Slack 通知

`EARLY_CANDIDATE` は調査候補であり、自動売買シグナルではない。

## 3. 現在の売却評価の実態

### 3.1 固定 5・20・60 営業日を評価

`src/evaluation/inflection_backtest.py` の `simulate_signal()` は、**翌営業日始値でエントリーし、指定した `holding_days` 日目の終値で退出**する。既定値は60日だが、現行の `scripts/rebuild_inflection_forward_validation.py` は同じシグナルを 5・20・60 日で評価する。

途中で +50%、+100%、+300% になっても、その時点では売却しない。

### 3.2 最大上昇率は記録済み

`TradeResult` には次の情報がある。

- `entry_price / exit_price`
- `gross_return_pct / net_return_pct`
- `max_return_pct`
- `max_drawdown_pct`
- `explosive_50pct`

既存のシグナル読込と固定期間評価を再利用し、10% / 15% / 20% Trailing Stopを追加済みである。ポジション数量と段階利確はまだ扱わない。

### 3.3 Close 指標と High/Low 指標を分離

`max_return_pct` は保有期間中の `Close` の最大値、`max_drawdown_pct` は `Close` の連続ピークからの下落で計算する。これらを維持したまま、調整済み `High / Low` による `mfe_pct` / `mae_pct` を追加済みである。

指標の意味を混同しないよう、次の名称で分離している。

- **MFE (Maximum Favorable Excursion):** `High` ベースの最大利益方向変動（実装済み）
- **MAE (Maximum Adverse Excursion):** `Low` ベースの最大不利方向変動（実装済み）
- 既存の Close ベース指標は比較用に残す

### 3.4 `net_return_pct` は税引前

現行 forward validation の `net_return_pct` は、gross return から固定の往復コスト 0.2% を引いた値で、`apply_tax=False` のため**税引前**である。口座区分や損益通算に依存する税を一律に混ぜず、税引後指標が必要な場合は前提を明記した別指標にする。

## 4. `OVEREXTENDED` の役割と限界

scanner は、20日上昇率が +50%以上、または60日上昇率が +100%以上の場合を `OVEREXTENDED` とする。また、20日 +50%以上は一次選別スコアでも -25 点になる。

これは新規で追いかけて買うことを避ける判定であり、保有済み銘柄の Exit 判定ではない。急騰した保有銘柄が候補ランキングから外れても監視を継続できるよう、Exit monitor は scanner から分離する必要がある。

## 5. 旧パイプラインの損切り機能

旧 enrichment の `archive/legacy/src/enrichment/sizing_enricher.py` には、20日ボラティリティから損切り幅を設定する `stop_loss_pct` がある。ただし、これは下方向のリスク管理であり、急騰後の利益追随型 Exit ではない。旧コードを現行経路へ戻すより、式の参考だけに留める。

## 6. 現在の実行基盤ではリアルタイム監視できない

本番実行は平日 16:40 JST の1日1回である。日中に急騰して反落する銘柄は、終値付近の情報だけでは高値からの崩れを検知できない。

また GitHub Actions の schedule は高負荷時に遅延し、場合によっては queued job が破棄され得ると公式資料にあるため、短間隔の売却監視基盤には向かない（[GitHub Docs](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows)）。

| 役割 | 適した実行基盤 |
|---|---|
| 全市場から買い候補を探す | 現在の GitHub Actions 日次 scanner |
| 日足 Exit の検証 | 既存 forward validation を拡張したローカル/CI バッチ |
| 保有銘柄のピーク追随 | 市場時間中に常駐する保有銘柄専用プロセス |
| 売却アラート | リアルタイム feed + 人が確認できる通知先 |

## 7. Exit Strategy 候補

| 方式 | 概要 | 判断 |
|---|---|---|
| 固定利確 | +50% / +100% などで退出 | 比較基準。大相場を早売りしやすい |
| 固定 Trailing Stop | 最高値から -10% / -15% / -20% | 最初に検証しやすい。銘柄ごとのボラ差に弱い |
| ATR / Chandelier Exit | 高値から ATR×N 下を売却線にする | 日足 Exit の本命候補 |
| Momentum Break | 短期モメンタム崩れで退出 | 終値確定後の補助条件に向く |
| Volume Climax | 異常出来高と反転を組み合わせる | 定義の自由度が高く、過剰最適化に注意 |
| 移動平均割れ | 終値がトレンド基準線を割る | 単純な比較対象として有用 |
| VWAP割れ | 価格が VWAP を割る | 日中 Exit なら分足/Tick が必要 |
| 段階利確 | 一部利確後、残りを Trailing | 数量と複数約定を扱える段階で検証 |
| Hybrid | 複数条件を組み合わせる | 単純ルールの out-of-sample 優位確認後だけ検討 |

最初は「固定 Trailing」「ATR/Chandelier」「移動平均割れ」の3系統で十分である。Volume Climax、VWAP、Hybrid は日足の単純ルールで不足が確認されるまで増やさない。

## 8. 特に有力な考え方

### 8.1 High Water Mark + ATR / Chandelier

エントリー後の最高値を `High Water Mark` として保持し、価格が最高値を更新している間は保有する。

```text
売却ライン = 保有開始後の確定済み最高値 - ATR × N
```

固定率のTrailing Stopは実装済みで、売却線を前日までの確定済みHigh Water Markから計算する。当日Highで線を引き上げて同日Lowで売る未来情報混入は行わず、gap時はStop価格ではなく当日始値で退出する。ATR / Chandelierは未実装である。

### 8.2 段階利確 + Trailing

例として +100% で25%、+200% で25%を利確し、残り50%を Trailing で追随させる方式がある。ただし閾値や比率は仮説にすぎず、現時点の推奨値ではない。単純な全数 Exit より本当に改善するかを out-of-sample で確認する。

## 9. バックテストで比較する最小セット

同一シグナル・同一エントリー条件で次を比較する。

- 現行基準: 5 / 20 / 60営業日固定
- 固定 Trailing: 10% / 15% / 20%
- ATR / Chandelier: 2ATR / 3ATR / 4ATR
- 終値の移動平均割れ: 少数の代表期間
- 上記で優位が残ったルールだけ、段階利確と組み合わせる

パラメータを増やす前に、期間を時系列で train / validation / out-of-sample に分ける。重複する日次シグナルを独立取引として数える現行集計と、実際の一銘柄一ポジションの集計は分けて報告する。

## 10. 検証で外せない約定ルール

日足 OHLC だけではバー内の値動き順序が分からない。次を事前に固定しない Exit テストは、結果が良くても採用できない。

- 同じ日に利確線と損切り線の両方へ触れた場合は、保守的な側を採るか、その取引を曖昧例として分離する。
- Stop を飛び越えて寄り付いた場合、Stop 価格で約定したと仮定せず、利用可能な最初の価格と slippage を使う。
- Exit 判定にはその時点までに確定した値だけを使い、当日終値で条件成立後に同じ終値で売れたことにしない。
- 分割調整済み OHLC を一貫して使い、`High / Low / Open / Close` の調整方式を混在させない。
- 売買代金、出来高、単元、売買停止、制限値幅を考慮する。東証には日ごとの制限値幅があるため、Stop 到達と約定可能性は同義ではない（[JPX 制限値幅](https://www.jpx.co.jp/equities/trading/domestic/06.html)）。
- 通常0.2%・悲観1.2%の総執行コストシナリオを比較する（実装済み）。

## 11. 評価指標

| 指標 | 定義上の注意 |
|---|---|
| Gross Return | コスト控除前の実現損益 |
| Net Return | 現行では往復コスト控除後・税引前。前提を report に残す |
| MFE / MAE | 調整済み High / Low を使用する |
| Peak Capture Ratio | MFE が正の取引だけで、同じコスト基準の実現利益 ÷ MFE |
| Peak Giveback | MFE と実現利益の差。率と金額を混ぜない |
| Early Exit Return | 売却後の一定期間にどれだけ上昇したか |
| Holding Days | 資金拘束期間 |
| Turnover / Exposure | コストと同時保有数を評価するために必要 |
| Portfolio Max Drawdown | 個別取引の drawdown とは別に、時系列資産曲線から算出 |
| Profit Factor | 同じ集計単位の総利益 ÷ 総損失 |

例えば MFE +400%、同じ基準の実現利益 +340% なら Peak Capture Ratio は85%である。ただし MFE が0以下の取引には適用せず、負の実現利益を含む集計方法も明記する。

## 12. 活用できる外部サービス

2026-09-08 時点の公式情報で確認した。契約条件と価格は導入時に再確認する。

| 優先 | サービス | 活用場所 | 制約と判断 |
|---|---|---|---|
| 1 | [J-Quants API Tick・分足アドオン](https://www.jpx.co.jp/markets/other-data-services/j-quants-api/index.html) | 日中 Exit の過去検証、日足 OHLC のバー内順序解消 | 日次配信でリアルタイムではない。まず日足検証で結果が曖昧な場合だけ追加する |
| 2 | [kabuステーションAPI](https://kabucom.github.io/kabusapi/ptal/push.html) | 保有銘柄のリアルタイム価格監視、将来の発注連携 | WebSocket PUSH は最大50銘柄。kabuステーションを同一PCで常時起動し、毎日の再ログインが必要。Professional/Premium 条件あり（[利用条件](https://kabucom.github.io/kabusapi/ptal/howto.html)、[FAQ](https://kabucom.github.io/kabusapi/ptal/faq.html)）。Python中心の本リポジトリには最も接続しやすい候補 |
| 3 | [TradingView Alerts / Webhook](https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/) | コードを増やさない価格アラートの試作、Webhook から Slack 等へ通知 | 2要素認証が必要。Webhook は3秒超でキャンセルされ、未達もあり得るため、発注の唯一の根拠にはしない |
| 条件付き | [MARKETSPEED II RSS](https://www.rakuten-sec.co.jp/ITS/PRNT_V_TOP_Marketspeed.html) | 楽天証券利用者のリアルタイム監視・発注 | Windows + Excel/VBA 前提。リアルタイム情報と発注機能はあるが、Python経路とは別運用になるため、既に楽天証券を使う場合だけ候補 |
| 後回し | [J-Quants API TDnet 文書アドオン](https://www.jpx.co.jp/corporate/news/news-releases/6020/20260518-01.html) | 下方修正など適時開示を Exit の補助イベントにする | 日中配信だが、まず価格ベースの Exit を検証し、追加価値を分離評価してから使う |
| 不採用 | [J-Quants Pro](https://www.jpx.co.jp/markets/other-data-services/j-quants-pro/) | 法人向けの長期・高機能データ | 法人向けで現段階の個人用 shadow 検証には過剰 |

推奨する最短経路は、**既存の日足データで Exit ルールを比較 → 必要な取引だけ J-Quants 分足/Tick で再検証 → TradingView または kabuステーションAPIで人間確認付きアラート**である。証券口座が未確定なら、broker API の実装を先に始めない。

## 13. 推奨する調査・実装順序

| 優先度 | 項目 | 完了条件 |
|---|---|---|
| 一部完了 | Exit 専用日足バックテスト | 固定期間と10% / 15% / 20% Trailingを比較済み。ATR/Chandelier・MA割れは未実装 |
| 完了 | High/Low ベース MFE/MAE | Close 指標と分離し、調整済み価格で算出済み |
| 一部完了 | 約定モデル | 通常0.2%・悲観1.2%の総執行コストを保存済み。gap等は Exit 実装時に追加 |
| 一部完了 | ポジション単位評価 | 同一銘柄の重複signalは統合済み。銘柄間の資金制約・資産曲線は未実装 |
| A | out-of-sample / forward validation | パラメータ決定期間と評価期間を分離する |
| B | 必要箇所だけ分足/Tick 再検証 | 日足で曖昧な約定と日中 Exit を確認する |
| B | 人間確認付き売却アラート | 保有銘柄だけを監視し、欠測・再接続・重複通知を安全に扱う |
| C | 証券API発注 | 検証環境、kill switch、発注上限、冪等性を確認した後だけ実施 |

## 14. 残っている問題と判断

出口戦略に関係する未解決事項は次のとおり。

1. 固定率Trailing Exitは実装済み。ATR/Chandelier、移動平均割れ、段階利確は未検証である。
2. MFE/MAE は実装済みで、Trailing結果と併せて比較できる。
3. gap時の始値退出と通常・悲観の総執行コスト比較は実装済み。制限値幅、板の流動性による未約定はデータ不足のため残る。
4. 同一銘柄の重複保有は `position_summary` で除外済み。銘柄間の資金制約とportfolio drawdownはまだ表さない。
5. 保有銘柄の状態を管理する ledger と、結果を人へ届ける consumer がない。
6. 日次 GitHub Actions はリアルタイム監視に使えない。
7. Entry 側の欠損年度を複数年 YoY と扱う問題は修正済み。

したがって、次はsnapshotを蓄積し、実装済みTrailingが固定期間基準よりout-of-sampleで改善するかを確認する。優位性が確認できるまでATR等のルール追加、リアルタイム監視、自動売却は行わない。

## 15. 確認した主なリポジトリファイル

- `README.md`
- `.github/workflows/inflection_shadow.yml`
- `scripts/run_inflection_shadow.py`
- `scripts/rebuild_inflection_forward_validation.py`
- `src/screening/inflection_live.py`
- `src/evaluation/inflection_backtest.py`
- `src/evaluation/inflection_forward.py`
- `archive/legacy/src/screening/scorer.py`
- `archive/legacy/src/enrichment/sizing_enricher.py`
- `archive/legacy/dashboard/js/index.js`
- `archive/legacy/dashboard/js/stock.js`

## 16. 本レポートの適用範囲

本レポートは技術的な調査と実装順序の提案であり、売買成果を保証するものではない。サービス仕様は公式情報を根拠にしたが、利用プラン、データ権利、注文仕様は導入時点で再確認する。
