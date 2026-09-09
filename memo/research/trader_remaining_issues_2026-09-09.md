# Trader 残存課題・漏れ・誤りの総合整理

作成日: 2026-09-09  
対象: `nakaj1214/trader` main ブランチ、および `memo/analysis/literature_and_ops_review_2026-09-08.md` 等の調査ファイル

## 1. 結論

現在の `trader` は、コード品質・point-in-time設計・暗号化snapshot・forward validation・Position Exit Monitor などの基盤はかなり整備されている。

一方で、プロジェクト本来の目的である

> 爆発的に上昇する可能性がある株をできるだけ早く発見し、買い候補として通知し、購入後はできるだけ高値付近まで利益を伸ばし、上昇終了・反落時に売却候補として通知する

という実運用に対しては、まだ重要な不足が残っている。

特に大きいのは次の点である。

- 日次 Shadow Scan が実際にはまだ正常稼働しておらず、immutable snapshot が蓄積されていない
- `EARLY_CANDIDATE` を実際の買い通知へ接続する consumer が存在しない
- J-Quants Free の約12週間遅延が「爆発前の早期発見」という目的と競合する
- Forward Validation が「選んだ株が上がったか」は見るが、「実際に爆発した株をどれだけ事前に捕まえられたか」を評価していない
- 現状は 5 / 20 / 60 営業日までしか主に評価しておらず、半年・1年のトレンド継続や早売りを検証できない
- Exit Monitor が当日高値を HWM に反映しないため、日中の急騰後急落を十分に捕まえられない
- GitHub Actions の schedule は売却タイミング監視には定刻性が不足する
- スコア閾値、重み、Top25一次選別、出来高加点などが十分に実証されていない
- Deep Research 文書内にも、文献解釈や現行実装状態に関する修正すべき記述がある

したがって、現時点では **研究・shadow validation段階から、実เงินจริงの売買支援段階へ完全移行する前に、以下の課題を順に解消する必要がある。**

---

# 2. P0: 実運用前に必ず確認・修正すべき問題

## 2.1 Shadow Scan が実際に失敗している

2026-09-08 の `JP Inflection Shadow Scan` は failure で終了している。

原因は `SNAPSHOT_ENCRYPTION_KEY` が GitHub Actions 側で未設定だったこと。

実行ログ上では次のエラーになっている。

```text
RuntimeError: SNAPSHOT_ENCRYPTION_KEY is required
```

そのため `dashboard/data/inflection/` には `.gitkeep` しか存在せず、実市場から取得した immutable snapshot はまだ蓄積されていない。

### 影響

- Forward Validation の仕組みはあるが、実際の検証対象データがまだ存在しない
- `EARLY_CANDIDATE` が実市場で優位なのか検証できていない
- 5 / 20 / 60 / 126 / 252 日評価以前に、そもそも forward データの蓄積が始まっていない

### 推奨対応

1. GitHub Secret `SNAPSHOT_ENCRYPTION_KEY` を設定
2. Shadow Scan の成功を確認
3. `dashboard/data/inflection/YYYY-MM-DD.enc` が日次で生成・commitされることを確認
4. 1日成功だけでなく数営業日連続で正常稼働を確認する

---

## 2.2 「買い候補を通知して買う」経路がまだ存在しない

現在の README でも `EARLY_CANDIDATE` は research flag であり、売買推奨ではないと定義されている。

また、暗号化済み `inflection_candidates.enc` を表示・Slack通知へ接続する consumer は存在しない。

### 現在

```text
全市場Scan
→ EARLY_CANDIDATE生成
→ encrypted snapshot保存
→ Forward Validation
```

### 想定している最終運用

```text
全市場Scan
→ 買い候補抽出
→ Slack等で通知
→ 人間確認
→ SBI証券で購入
→ 保有銘柄台帳登録
→ Exit Monitor
→ 売却候補通知
→ 人間確認
→ SBI証券で売却
```

### 問題

後半の Exit Monitor は存在するが、前半の「買い通知」が未完成。

### 推奨対応

Forward Validationで一定の条件を満たすまでは `EARLY_CANDIDATE` を研究用のまま維持し、

- `research_candidate`
- `validated_buy_candidate`

を明確に分離する。

実売買通知へ昇格する条件も事前に決める。

---

## 2.3 J-Quants Free の約12週間遅延

現在の workflow は以下を固定している。

```yaml
JQUANTS_PLAN: free
JQUANTS_DATA_DELAY_WEEKS: '12'
```

現在の scanner は

- 売上成長
- 営業利益成長
- 黒字転換
- 営業利益率改善
- 上方修正

などを使うが、Freeプランでは財務データが約12週間遅延する。

### 問題

「業績変化を市場より早く検知して爆発前に買う」という用途では、約3か月の遅延は大きい。

現状の実態は、

```text
価格・出来高で既に動き始めた銘柄
+
約12週間遅延した財務情報
```

を使った candidate 判定に近い。

### 推奨対応

- 現在の Free signal を「Freeユーザーがその時点で観測できたshadow signal」として継続保存
- 実売買用候補を作るなら、最新決算・適時開示を利用できるpoint-in-time-safeな情報源を別途検討
- Free戦略とリアルタイム戦略の成績を混在させない

---

## 2.4 GitHub Actions の schedule を Exit Monitor に使う問題

Position Exit Monitor は平日 3 回、

- 09:03 JST
- 12:35 JST
- 15:35 JST

に動く設計。

しかし GitHub Actions の scheduled workflow は定刻実行を保証しない。

実際に 2026-09-08 の Shadow Scan は 16:40 JST 予定だったが、実行開始は約 21:16 JST で、約4時間半遅延している。

### 問題

買い候補の日次Scanでは数時間遅れても翌営業日の売買に間に合う可能性がある。

しかし Exit Monitor では、

```text
12:35予定
→ 数時間後に実行
```

となると売却判断として意味を失う。

### 推奨対応

- GitHub Actions は日次分析・Forward Validation用として維持
- Exit Monitor は「best-effort警告」と明記したまま運用
- 実เงินจริงの高値追随Exitを重視する段階では、常駐プロセスやより定刻性の高い実行基盤へ移行を検討

---

# 3. P1: 買い候補発見ロジックの重要な不足

## 3.1 Top25しか財務分析しない

`scan_japan_inflection()` は全市場を価格・出来高で一次選別したあと、

```python
preselected = preselected[:deep_candidates]
```

でデフォルト25銘柄だけ財務分析する。

### 問題

例えば、

```text
業績急改善
株価 +2%
出来高 1.1倍
52週高値ではない
```

という、まだ市場が十分反応していない銘柄は一次選別上位に入れず、財務分析すらされない可能性がある。

一方、

```text
株価 +20%
出来高 3倍
52週高値付近
```

の銘柄は上位に入りやすい。

そのため現状は、

> 爆発前より、爆発開始後を検出しやすい

構造になっている可能性がある。

### 推奨検証

`deep_candidates` を、

- 25
- 50
- 100
- 200

で比較し、Explosion Recall と実行時間を確認する。

---

## 3.2 Explosion Recall がない

現在は、

> EARLY_CANDIDATEになった株がその後上がったか

を評価している。

しかし本来の目的は、

> 実際に爆発した株をどれだけ爆発前に捕まえられたか

でもある。

### 必須追加指標

```text
Explosion Recall
= 爆発前に検出できた銘柄数
  ÷
  実際に爆発した銘柄数
```

例:

```text
1年間に +50%以上上昇した銘柄 = 100
Traderが事前発見 = 12

Explosion Recall = 12%
```

candidateの成績が良くても Recall が低ければ、目的を達成できていない。

### Detection Lead Time も必要

```text
Detection Lead Time
= 初回candidate日から
  +50%到達日までの日数
```

これにより、

- 爆発20日前に発見
- 爆発2日前に発見
- 既に爆発後

を区別できる。

---

## 3.3 新規上場銘柄は約65営業日対象外

`_technical_features()` は、

```python
if len(close) < 65:
    return None
```

となっている。

### 影響

IPO後65営業日未満の銘柄は候補に入らない。

爆発的な値動きが上場初期に起きる銘柄を完全に取り逃す。

また65〜251営業日の銘柄について `breakout_52w` と呼んでいるが、実際には「52週高値」ではなく「取得可能期間中の最高値（実質上場来高値）」。

### 推奨対応

- 新規上場銘柄を別ルールに分離
- `near_52w_high`
- `near_listing_high`

を区別する

---

## 3.4 score の意味が二重化している

`src/strategy/inflection.py` の理論スコアと live scanner の正規化スコアは同じ100点ではない。

live scanner は利用できない Catalyst 項目を除外し、

```text
利用可能最大値 58
→ 100点換算
```

している。

さらに、

汎用側:

```text
strong_candidate >= 75
watch >= 60
```

live側:

```text
EARLY_CANDIDATE >= 70
WATCH >= 52
```

となっている。

### 問題

同じ `score=70` でも意味が違う。

将来別consumerが `score_inflection()` の値と live score を混同するリスクがある。

### 推奨対応

- `raw_inflection_score`
- `live_normalized_score`

を明確に区別
- classification関数も一本化または名称を明示

---

## 3.5 70点という閾値が未検証

現在は `EARLY_CANDIDATE >= 70` だが、70が最適という実証はない。

### 推奨評価

| score band | 20d | 60d | 126d | 252d | 爆発率 | TOPIX超過 |
|---|---:|---:|---:|---:|---:|---:|
| 50-59 | | | | | | |
| 60-69 | | | | | | |
| 70-79 | | | | | | |
| 80-89 | | | | | | |
| 90+ | | | | | | |

WATCHも対照群としてForward Validationへ含める。

---

## 3.6 スコア重み自体が未検証

例:

- 売上成長
- 営業利益成長
- 黒字転換
- 出来高
- 52週高値

などの方向性には文献上一定の妥当性がある。

しかし、

```text
営業利益急増 = 10点
黒字転換 = 5点
出来高 = 7点
52週高値 = 6点
```

という具体的配点はヒューリスティック。

### 推奨

Feature Ablation を行う。

```text
全部入り
vs
Volumeなし
vs
52週高値なし
vs
業績成長なし
vs
上方修正なし
```

これにより本当に効く要素を特定する。

---

## 3.7 市場区分ごとのデータcoverageがない

現在は全市場合計で、

- price coverage
- technical coverage
- latest date coverage

を判定する。

### 問題

例えば、

```text
Prime 95%
Standard 90%
Growth 30%
```

でも全体では閾値を超える可能性がある。

爆発銘柄探索では Growth 欠損は特に重要。

### 推奨

以下を個別保存・health checkする。

```text
Prime coverage
Standard coverage
Growth coverage
```

---

# 4. Forward Validation の不足

## 4.1 5 / 20 / 60営業日では短い

現在は、

- 5日
- 20日
- 60日

が主な固定評価期間。

しかし大きく伸びるモメンタム株は3か月を超えて上昇する可能性がある。

### 推奨

最低限、

```text
5 / 20 / 60 / 126
```

を評価。

可能なら、

```text
252
```

も長期参考として追加。

意味:

- 5営業日: 約1週間
- 20営業日: 約1か月
- 60営業日: 約3か月
- 126営業日: 約6か月
- 252営業日: 約1年

---

## 4.2 Exit検証も60日で打ち切られている

実運用のPosition Exit Monitorは無期限に保有できる。

しかし backtest の Trailing Stop 評価は最大60営業日。

### 問題

```text
実運用
→ 6か月保有可能

検証
→ 60日しか見ていない
```

という不整合。

### 推奨

Trailing Stopも、

- 60
- 126
- 252

で比較する。

例:

```text
Trailing 10% × 126d
Trailing 15% × 126d
Trailing 20% × 126d

Trailing 10% × 252d
Trailing 15% × 252d
Trailing 20% × 252d
```

---

## 4.3 Early Exit Return が必要

売却後にその株がさらに上がったかを測る必要がある。

### 追加指標

- Exit後5日Return
- Exit後20日Return
- Exit後60日Return

### 意味

売却後に毎回さらに +30〜50% 上がるなら、

> Exitが早すぎる

売却後すぐ大きく下落するなら、

> Exitが有効

と判断できる。

---

## 4.4 Peak Capture / Peak Giveback が必要

最高値そのもので売ることは不可能なので、

> 最高値に対してどれだけ利益を残せたか

を評価する。

### Peak Giveback

```text
Peak Giveback
= (Peak Price - Exit Price) / Peak Price
```

### Peak Capture Ratio

```text
Peak Capture Ratio
= Realized Profit / MFE
```

MFEが正の取引だけで扱う。

---

## 4.5 統計的信頼性の評価が弱い

現在は主に、

- 平均
- 中央値
- 勝率
- Profit Factor
- benchmark勝率

等。

### 問題

sample数が少ないと偶然でも高い成績になる。

### 推奨追加

- sample count
- bootstrap confidence interval
- median confidence interval
- score band別件数
- market regime別件数
- rolling期間別成績

少なくとも「平均 +12%」だけでなく、

```text
n=7
95% CI = -8% ～ +31%
```

のように不確実性を見せる。

---

## 4.6 WATCHを対照群に使っていない

Forward Validationはデフォルトで `EARLY_CANDIDATE` だけ。

### 問題

EARLYが本当にWATCHより良いのか分からない。

### 推奨

- EARLY
- WATCH
- NONEからサンプルした対照群

を分けて追跡。

---

## 4.7 ポートフォリオ評価がない

個別tradeの成績が良くても、実際に資産が増えるとは限らない。

不足:

- 最大同時保有数
- 1銘柄あたり配分
- 資金不足時の順位選択
- 同業種集中
- Portfolio Drawdown
- Equity Curve
- Cash utilization
- Exposure

### 推奨

単一trade評価とは別にPortfolio Simulationを追加。

---

## 4.8 TOPIXとcandidateに同じ取引コストを適用している

TOPIX ETF と個別Growth株では、

- spread
- 板厚
- slippage
- market impact

が異なる。

同じ往復コストを両者に引くと excess return ではかなり相殺される。

### 推奨

少なくとも、

```text
Benchmark cost
Individual stock normal cost
Individual stock stress cost
```

を分離。

---

# 5. Exit Monitor の不足

## 5.1 当日HighをHWMへ反映していない

`TodayQuote` では、

- Open
- High so far
- Low so far
- Last

を取得している。

しかし Trailing Stop のHWMは、

```text
entry_price
or
前日までの確定High
```

だけ。

### 例

```text
昨日までのHWM 1,000円

今日
09:00 1,000
11:00 1,500
14:00 1,200
```

15% Trailingなら本来、

```text
1,500 × 0.85 = 1,275
```

付近が売却候補になる。

しかし現在は、

```text
1,000 × 0.85 = 850
```

のままなので何も通知されない。

### 推奨

live監視ではすでに1分足を取得しているため、

分足を時系列順に処理する。

```text
各1分bar
→ HWM更新
→ 次のbarでStop判定
```

これなら未来情報を使わずに当日HWMを利用できる。

---

## 5.2 60分stale許容はExit用途には長い

現在、

```python
STALE_QUOTE_THRESHOLD_MINUTES = 60
```

### 問題

15:35時点で14:40のデータでも正常扱いされ得る。

「今売るか」を判断するには古すぎる。

### 推奨

データソースの実際の遅延特性を確認して、Exit用途はより厳しい鮮度基準へ変更する。

---

## 5.3 同じTriggerを1日複数回通知する

現在は 09:03 / 12:35 / 15:35 の各実行で条件が成立していれば同じ銘柄を再通知できる。

### 推奨

状態遷移ベースにする。

```text
false → true
```

になったときだけ通知。

必要なら、

- triggered_at
- last_notified_at
- trigger_reason

を台帳へ保存。

---

## 5.4 Google Sheets の status 書き込みが非原子的

`clear()` → `update()` の2段階。

途中失敗すると status sheet が一時的に空になる。

### 推奨

優先度は低いが、

- staging sheet
- batch update
- temporary range

などで原子性を高める。

---

## 5.5 実売買履歴が残らない

現在の「状況」シートは現在値ダッシュボードで、履歴ではない。

### 問題

実際に、

- どの通知で買ったか
- いくらで買ったか
- どのExit通知で売ったか
- 実際の約定価格
- 通知から約定まで何分かかったか

を後から評価できない。

### 必須追加

Trade Ledger。

例:

```text
ticker
signal_id
candidate_date
notification_at
entry_order_at
entry_fill_at
entry_price
exit_signal_at
exit_fill_at
exit_price
exit_reason
realized_return
max_mfe
max_mae
peak_giveback
```

これにより「モデル」ではなく「実際の人間運用込み」の成績を評価できる。

---

# 6. Deep Research / memo 内の修正すべき記述

## 6.1 Jegadeesh & Titman (1993) の説明

文書では、

> 同業種内の相対順位でモメンタムを測定

という趣旨になっている。

これは正確ではない。

Jegadeesh & Titman (1993) の代表的戦略は、過去リターンを基に winner / loser ポートフォリオを形成するクロスセクショナルモメンタム。

「業種momentum」は Moskowitz & Grinblatt (1999) などの方が近い。

### 修正方針

TOPIX/業種相対Returnの導入自体は妥当だが、

> Jegadeesh & Titman に忠実だから

という説明は修正する。

---

## 6.2 「52週高値ブレイクアウト」の表現

コードは、

```python
current >= high52 * 0.99
```

なので、

> 52週高値ブレイクアウト

ではなく、

> 52週高値から1%以内

に近い。

George & Hwang (2004) も52週高値への近さを扱う研究。

### 推奨

変数名を、

```text
breakout_52w
```

から、

```text
near_52w_high
```

へ変更検討。

---

## 6.3 出来高研究の解釈

文書では出来高増加を「反転リスク」としてやや単純化している。

実際には、

- momentumの持続性
- lifecycle
- 後の反転

の両方と関係する。

### 推奨

Volume単独で良い/悪いと決めず、

```text
Return × Volume × Holding Horizon
```

のinteractionとして実測する。

---

## 6.4 Piotroski の引用がTraderへ直接的ではない

Piotroski F-score は主に高 Book-to-Market銘柄を財務情報で選別するValue Investing研究。

Traderの「爆発前のinflection」を直接裏付ける研究ではない。

PEADの方が業績変化との関係は近いが、現在のJ-Quants Freeは12週遅延なので、

> 決算発表直後のPEADを利用している

とは言えない。

### 推奨

文献と実装の関係を、

- 方向性が近い
- 直接的根拠
- 参考程度

に分ける。

---

## 6.5 文書が現行実装に追いついていない

`memo/trader_exit_strategy_research.md` には、

> Position Exit Monitorは計画済み・未実装

という古い記述が残っている。

現在は `scripts/run_position_monitor.py` が実装済み。

### 問題

Codexや他AIがmemoを参照した際、

> 未実装なので作る

と誤判断する可能性がある。

### 推奨

`memo/project-overview.md`
`memo/trader_exit_strategy_research.md`
`memo/analysis/*`

の状態表記を、

```text
未実装
実装済み
検証中
本番採用
```

で統一する。

---

# 7. 推奨する評価期間

固定期間評価は以下を推奨。

| Horizon | 意味 |
|---|---|
| 5営業日 | 初動 |
| 20営業日 | 約1か月 |
| 60営業日 | 約3か月 |
| 126営業日 | 約6か月 |
| 252営業日 | 約1年 |

ただし、126 / 252日を単純に追加するだけでは不十分。

本来見るべきなのは、

```text
Entry Signal
+
Exit Strategy
```

を一つの取引として評価した結果。

### Exit Strategy 比較候補

- Fixed hold
- Trailing 10%
- Trailing 15%
- Trailing 20%
- ATR / Chandelier
- Moving Average Break
- 将来的に段階利確

---

# 8. 推奨する新しい評価指標

最低限以下を追加する。

## Entry側

- Explosion Recall
- Detection Lead Time
- Precision
- score band別爆発率
- TOPIX excess return
- market regime別成績
- market区分別成績
- deep_candidates別Recall

## Exit側

- MFE
- MAE
- Peak Capture Ratio
- Peak Giveback
- Early Exit Return 5d
- Early Exit Return 20d
- Early Exit Return 60d
- Holding Days
- Exit後最大上昇
- Exit後最大下落

## Portfolio側

- CAGR
- Portfolio Max Drawdown
- Equity Curve
- Exposure
- Turnover
- Win Rate
- Profit Factor
- Sharpe / Sortino（必要なら）
- 最大同時保有数
- 業種集中度

## 統計側

- sample count
- bootstrap confidence interval
- regime別sample数
- score band別sample数

---

# 9. 推奨する対応順

## Phase 1: 動作正常化

1. `SNAPSHOT_ENCRYPTION_KEY` を設定
2. Shadow Scan を正常稼働させる
3. snapshotが毎営業日蓄積されることを確認
4. Forward Validation artifactを定期確認する

## Phase 2: 評価設計の補強

5. 5 / 20 / 60 / 126 / 252日へ拡張
6. WATCHを対照群へ追加
7. score band別成績を追加
8. Explosion Recall を追加
9. Detection Lead Time を追加
10. market regime / market区分別に評価

## Phase 3: 買い側の取りこぼし改善

11. deep_candidates 25 / 50 / 100 / 200 を比較
12. 新規上場銘柄を別ロジック化
13. Feature Ablation
14. TOPIX / 業種相対momentumを比較
15. 最新ファンダ取得方法を検討

## Phase 4: Exit改善

16. Trailingを126 / 252日まで評価
17. Peak Capture / Givebackを追加
18. Early Exit Returnを追加
19. live監視で分足順序による当日HWM更新を検討
20. stale thresholdをExit用途向けに見直す

## Phase 5: 実運用化

21. Trade Ledgerを追加
22. 買い候補notification consumerを実装
23. research candidate と validated buy candidate を分離
24. Portfolio Simulationを追加
25. Promotion条件を満たした戦略だけ実売買候補へ昇格

---

# 10. 実売買へのPromotion条件案

以下は固定値ではなく、事前にルール化するための枠組み。

例:

```text
最低sample数を満たす
+
TOPIX超過Returnが正
+
中央値も正
+
複数market regimeで極端に崩れない
+
Explosion Recallが一定水準
+
Portfolio Drawdownが許容範囲
+
Exit戦略が固定保有より改善
```

これを満たすまでは、

```text
EARLY_CANDIDATE = research
```

として扱う。

---

# 11. 現時点で最重要の考え方

このプロジェクトは、

> Traderが選んだ株が上がったか

だけでは不十分。

本来は、

```text
実際に爆発した株
↓
Traderは何日前に見つけたか
↓
何%を捕まえられたか
↓
買ったあとどこまで利益を伸ばせたか
↓
最高値からどれだけ利益を返して売ったか
↓
実際の人間の約定を含めても利益が残ったか
```

まで一連で評価すべき。

したがって最終的な評価軸は、

```text
Discovery Quality
+
Entry Quality
+
Exit Quality
+
Portfolio Quality
+
Operational Reliability
```

の5つに分けるのが望ましい。

---

# 12. 最終判断

現行 `trader` の基盤そのものは良い方向へ改善されている。

特に、

- point-in-time-safe設計
- immutable snapshot
- version/schema固定
- benchmark比較
- High/LowベースMFE/MAE
- gapを考慮したTrailing
- 実約定価格尺度を意識したPosition Exit Monitor
- fail-closedな検証

は有用。

一方で、現状はまだ

> 「実際に儲かる売買システム」

ではなく、

> 「実際に儲かる可能性がある戦略を検証するための研究・観測基盤」

の段階。

特に優先度が高いのは、

1. Shadow Scanの正常稼働
2. 実データsnapshotの蓄積
3. Explosion Recall
4. 126 / 252日評価
5. Top25取りこぼし検証
6. score threshold / weightの検証
7. ExitのPeak Capture / Early Exit評価
8. GitHub Actions依存のExit監視の見直し
9. 実売買Trade Ledger
10. Forward Validation結果に基づくPromotionルール

である。

これらを順に埋めることで、`trader` を単なる候補抽出ツールから、

> 「爆発前の発見 → 買い候補通知 → 保有 → 売却候補通知 → 実績から改善」

まで一貫した運用システムへ発展させられる。
