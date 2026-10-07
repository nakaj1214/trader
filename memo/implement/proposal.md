# 実装要件書（REQ-055〜057: 記録した特徴量の評価への接続、過熱の事前警告、売却ルール比較の多重比較補正）

> このファイルは create-plan の入力です（作成済み: [plan_req055-057.md](plan_req055-057.md)）。
> 出典: [memo/analysis/improvement_report_2026-10-01.md](../analysis/improvement_report_2026-10-01.md) の §4（A7 の入力の利用）、B3（過熱の警告）、§4.2（Deflated Sharpe Ratio）。
> 現在の `proposal.md` / `plan.md`（REQ-052〜054）は未実装なので、上書きしないため、別ファイルにした。実装の順序は **REQ-052〜054 が先**（REQ-055 は、REQ-053・054 で増える特徴量も扱う）。

## 背景

- REQ-050（実装済み）、REQ-053・054（計画済み）で、診断用の特徴量を `features` に記録し始めたが、**learning（自己学習）はそれを使っていない**。使わないと、記録した値は評価に反映されない。
- Monitor の警告は、「stop まで残り3%以内」だけである。報告書 B3 は、過熱（20日で +50% 超）の注意喚起を挙げている。
- forward のレポートは、売却ルールを多数並べて比較しているが、多重比較は定性的な注意書き（`multiple_comparisons_caveat`）だけである。

## 決定済みの事項

- **戦略・スコア・分類・候補の選定・売却ルールの採用は変えない。** `STRATEGY_VERSION`（v3）と `REPORT_SCHEMA_VERSION`（5）は変えない。
- 戦略に影響する項目は保留（2026-10-07 ユーザー確認）。
- 自己学習は、重みを直接更新しない現設計を維持する。新しい factor は、既存の昇格判定（Fisher 検定と BH 補正）を通る。

---

## 要件一覧

### REQ-055: 記録した特徴量を、learning の factor ラベルに接続する

- **画面**: なし（learning のレポート）
- **対象ファイル**: [src/evaluation/inflection_learning.py](../../src/evaluation/inflection_learning.py)（`factor_labels`）、`tests/test_inflection_learning.py`
- **Before（現状）**: `factor_labels` は、classification、market、score、return、出来高比、52週高値圏、理由だけをラベルにする。観測には `features`（辞書）と `sector33_code` が渡っているが、使われていない。
- **After（期待）**: `features` に値がある（`None` でない）場合だけ、次のラベルを追加する。値がない観測（過去の snapshot）にはラベルを付けない。
  - `disclosure_age_band`（開示からの経過日数: 〜30日、30〜60日、60〜90日、90日超）
  - `forecast_age_band`（予想修正からの経過日数: 同じ区分）
  - `up_day_ratio_60d_band`、`max_daily_return_20d_band`、`daily_volatility_20d_band`、`distance_from_period_high_band`（それぞれ区切りを定義する）
  - REQ-053・054 の特徴量（`quarterly_sales_growth_accel_pctpt`、`quarterly_op_growth_accel_pctpt`、`relative_return_20d_vs_sector_pct`、`relative_return_60d_vs_sector_pct`）。キーが `features` にあるときだけ。
  - `sector33:{コード}`
  - 区切りは、実装時にコードで定義し、定数にまとめる。区切りの値は診断用の初期値であり、チューニングしない。
- **受入条件**:
  1. 特徴量のある観測で、期待するラベルが付く（区切りの境界値を含む）。
  2. 特徴量のない観測（`features` が `None`、または該当キーがない）で、例外にならず、該当のラベルが付かない。
  3. 既存のラベル（classification、market など）が、変更前と同じである。
  4. 新しいラベルが、昇格判定（BH 補正）の対象に入る。**ラベルが増えると、BH 補正は厳しくなる**。これは意図した挙動で、レポートの `promotion_gate` の検定数に反映される。既存のテストが PASS する。
  5. 新しいラベルを付けても、スコア、分類、候補、本番の scan の出力は変わらない（learning のレポートだけが変わる）。
- **備考**: 現在の snapshot は、新しい特徴量を持つものが少ない。ラベルを付けても、標本が溜まるまで昇格は起きない。

### REQ-056: Monitor に、過熱の事前警告を追加する

- **画面**: Slack（Monitor の警告）、Monitor のシート
- **対象ファイル**: [scripts/run_position_monitor.py](../../scripts/run_position_monitor.py)、[src/monitoring/position_exit.py](../../src/monitoring/position_exit.py)、`tests/` の Monitor のテスト
- **Before（現状）**: 警告は、stop まで残り3%以内（`WARNING_DISTANCE_PCT`）の1種類だけである。急騰した後の過熱の注意喚起はない。
- **After（期待）**:
  - 保有銘柄の現在値が、**20営業日前の確定終値より +50% 以上**高いとき、「過熱: 20日で +N%」の警告を出す（注意喚起のみ。売却の判断・stop の変更はしない）。
  - 閾値 50% は、本番の `OVEREXTENDED` 分類（r20 ≥ 50%）と同じ値にする（定数を共有できるなら共有する）。
  - 警告は、既存の stop 接近の警告と**同じ仕組み**（1営業日に1銘柄1回、`last_warned_at`）で出す。1銘柄に両方の条件が重なる場合は、1通にまとめる。
  - 20営業日分の確定終値がない場合は、警告しない。出来高の指標（出来高クライマックス）は含めない。
- **受入条件**:
  1. 20日前の終値の +50% 以上の合成データで、警告の対象になり、メッセージに銘柄と上昇率が入る。+50% 未満、履歴が20日に満たない場合は対象にならない。
  2. 同じ日に2回目の実行で、同じ銘柄に再度警告しない（stop 接近の警告との重複も含む）。
  3. 両方の条件が重なる銘柄で、1通にまとまる。
  4. 売却の判定（`triggered`、`exit_reason`、`stop_price`）が、変更前と同じである。
  5. 既存の Monitor のテストが PASS する。
- **備考**: 実装時に、Monitor が確定終値の履歴をどの範囲で取得しているかを確認する。20営業日分が取得できていなければ、取得範囲の拡大が必要になる（その場合は、影響を報告する）。

### REQ-057: 売却ルールの比較に、Deflated Sharpe Ratio を加える

- **画面**: なし（forward のレポート）
- **対象ファイル**: [src/evaluation/inflection_report.py](../../src/evaluation/inflection_report.py)、`tests/test_inflection_forward.py`（または report のテスト）
- **Before（現状）**: 売却ルールを多数並べて、最良のものを見られるが、「多数から選んだ最良の成績」の過大評価を補正する指標がない。`multiple_comparisons_caveat` は文章だけである。
- **After（期待）**: 各グループのレポートに、`deflated_sharpe`（追加のキー）を加える。
  - 対象: そのグループの売却ルール（`exit_strategies`）のうち、**ベースのコストのシナリオ**で、満期までの取引（matured）が一定数（既定 30 件）以上あるもの。
  - 各ルールについて、取引ごとのリターンから Sharpe（取引単位。年率化しない）、歪度、尖度を求め、最良のルールを選ぶ。試行数 N = 対象のルールの数として、Bailey & López de Prado (2014) の Deflated Sharpe Ratio（最良のルールの Sharpe が、N 個のランダムな試行の期待最大値を上回る確率）を求める。標準ライブラリだけで計算する（`statistics.NormalDist`）。
  - 出力: 最良のルール名、Sharpe、DSR（確率）、N、取引数。対象が2ルール未満、または取引が30件未満のときは、`None` と理由を出す。
  - 取引は重なりのない取引（既存の `select_non_overlapping_trades`）を使う。
- **受入条件**:
  1. 手計算できる合成のリターンで、Sharpe、歪度、尖度、DSR が期待どおりになる（既知の値との比較）。
  2. N が増えると、同じ Sharpe でも DSR が下がる。
  3. 取引が30件未満、ルールが2つ未満のとき、`None` と理由が出る。
  4. 既存のレポートのキーと値が変わらない（`deflated_sharpe` が増えるだけ）。
  5. 既存のレポートのテストが PASS する。
- **備考**: DSR は、取引が独立であることを前提にする。現在の標本は少ないので、当面は `None` になる可能性が高い。標本が溜まったときのための、先行実装である。

---

## 繰り返し失敗している要件

なし。

---

## 完了済み・保留中

### 完了済み
- REQ-045〜051（売却ルールの比較、相場環境、stop 接近の警告、候補の見える化、診断用の特徴量、欠損営業日）

### 計画済み・未実装
- REQ-052〜054（日次 scan の耐性、四半期の業績の加速、業種の相対モメンタム）: [proposal.md](proposal.md) / [plan.md](plan.md)

### 保留中（今回のスコープ外）
- **決算発表日の警告。** J-Quants の client に決算発表予定日のエンドポイントがない。取得方法の調査が先。
- **A8-d（市場別のベンチマーク）。** 追加のベンチマーク（例: グロース250連動 ETF）の取得と、forward・learning の価格取得の変更が必要。ETF の選定をユーザーに確認してから。
- **出来高クライマックスの警告。** Monitor が出来高の履歴を持っていない。
- **戦略に影響する項目**（A7 の減衰、A8-a・b、相場環境による切り替え、売却ルールの採用、B5）、**B6**（TDnet・EDINET・信用残）。
- **連続する複数週の昇格条件、Beta-Binomial による縮小推定。** 昇格の判定を変えるため、標本が溜まってから。
