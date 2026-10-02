## 実装計画: 売却ルールの比較検証、相場環境の層別評価、stop 接近の事前警告 — REQ-045 / REQ-046 / REQ-047

> 入力: [proposal.md](proposal.md)
> 以前の plan.md（REQ-042〜044、実装済み）は [plan_req042-044.md](plan_req042-044.md) に移した。

### 目的
売却ルールの候補4つを、既存の trailing stop と同じ約定の仮定で比較できるようにする（REQ-045）。相場環境（トレンドとボラティリティ）を point-in-time で判定し、自己学習の factor と成績の層別集計に加える（REQ-046）。Position Monitor に、stop まで残り 3% 以下の事前警告を加える（REQ-047）。戦略、snapshot、Monitor の売却判定は変えない。

### 前提
- REQ-042〜044 はコミット済み（`324a765`）。作業ツリーに未コミットのコード変更はない（2026-10-01 に `git status` と `git diff HEAD` で確認済み。残っているのは proposal/plan のリネームと新しい proposal.md だけ）。

### 提案からの変更点（調査で判明した事項）
1. **取得期間の延長幅を 420日 から 460日 にする。** トレンドの判定（200日移動平均）とボラティリティの判定（252日分の20日ボラティリティの中央値）には、シグナル日より前に 252 + 20 + 1 = 273本の終値が必要である。2025-01〜2026-09 の各週について TSE の営業日を数えると、420日では最悪 276本（余裕3本）しかなく、Yahoo の欠損日が数日あるだけで最初のシグナルが `unknown` になる。460日なら最悪でも 303本ある。
2. **既存の trailing stop と同じ約定の仮定を確実に保つため、`simulate_signal` の「売却後の指標計算」部分を共通関数として切り出し、新しいシミュレーターも同じ関数を使う。** 受入条件 1（新しいシミュレーターで trailing を表すと、既存と一致する）は、固定 seed の合成データ200通りで確かめる。
3. **段階利確は、利確済みの数量と残りの数量を持つ状態として判定する**（review #2）。時系列が確定している寄付を先に処理し、寄付で利確しても、同じ日の残りの数量に対する stop の判定は続ける。「stop を先とみなす」（保守的な仮定）は、**寄付では利確が成立せず、日中に目標と stop の両方に触れて、順序が分からない場合だけ**に限る。利確は最初の1回だけで、以後は残りの数量の trailing だけを判定する。
4. **ATR は、判定日の前日までの22日の True Range の単純平均とする**（Wilder 平滑化ではない。計算が単純で、先読みしないことをテストで確かめやすい）。保有開始前の価格も使う。22日分の履歴がない場合は、その trade を `insufficient_history` として未完了扱いにする。
5. **複数回に分けて売る trade では、損益の計算と、最終の売却価格を分けて扱う**（review #1）。損益（粗利益・純利益）は、各売却の割合で加重平均する。`TradeResult.exit_date` と `exit_price` は**最後に売った日と、その実際の約定価格**とし、加重平均の価格は入れない。株価に関する指標（最大リターン、最大ドローダウン、MFE、MAE、ピークからの戻し、売却後のリターン）は、**ポジションの価値ではなく株価の動き**で測り、期間は最後に売った日までとする。売却後のリターンの基準は、最後の約定価格である。各回の売却は、`TradeResult` に追加する任意のフィールド `exit_legs`（`[[日付, 価格, 割合], ...]`、既定値 `None`）に記録する。1回で売る trade では、`exit_legs` は `None` のままで、他のすべての値は従来と同じになる。

### スコープ
- 含むもの: REQ-045、REQ-046、REQ-047 と、それらのテスト
- 含まないもの: 売却ルールの Monitor への採用、regime による戦略の切り替え、決算発表日と過熱の警告、Deflated Sharpe Ratio、パラメータの探索

### 影響範囲（変更/追加予定ファイル）
- `src/evaluation/inflection_backtest.py`: `simulate_signal` の売却後の指標計算を `_finalize_trade()` に切り出す（挙動は変えない）
- `src/evaluation/exit_rules.py`（新規）: 4つのルールと、1日ずつ判定するシミュレーター `simulate_exit_rule()`
- `src/evaluation/inflection_report.py`: exit 比較の集計ブロックを関数にまとめ、新しいルールを追加する。`_report_breakdowns` に regime 別の成績を追加する
- `src/evaluation/regime.py`（新規）: トレンドとボラティリティの判定
- `src/evaluation/inflection_learning.py`: 評価時に regime の factor ラベルを付ける
- `src/data/forward_prices.py`: `PRIOR_HISTORY_DAYS` を 100 → 460
- `scripts/run_position_monitor.py`、`src/data/sheets_client.py`: 事前警告と `last_warned_at` 列
- テスト: `tests/test_exit_rules.py`、`tests/test_regime.py`（新規。新しいモジュールにはそれぞれ専用のテストを置くのが、探しやすく、モジュールとの対応も明確なため）、`tests/test_inflection_backtest.py`、`tests/test_inflection_forward.py`、`tests/test_inflection_learning.py`、`tests/test_forward_prices.py`、`tests/test_run_position_monitor.py`、`tests/test_sheets_client.py`（既存を拡張）
- `.github/workflows/test.yml`（mypy 対象）、`.github/workflows/forward_validation.yml`（起動パスとテスト一覧）

### 実装ステップ

#### Step 1: `simulate_signal` の指標計算を切り出す（挙動は変えない）
- [ ] `simulate_signal` のうち、売却が決まった後の処理（`realized_closes` の作成から `TradeResult` の生成まで: 粗利益、最大リターン、最大ドローダウン、MFE、MAE、ピークからの戻し、ピーク捕捉率、売却後のリターン）を、`_finalize_trade(ticker, signal_date, score, entry_date, entry_price, exits, window, highs, lows, closes, *, exit_reason, has_full_horizon, round_trip_cost_pct, apply_tax, tax_rate_pct)` に切り出す
  - `exits` は `[(日付, 価格, 割合), ...]`。trailing では割合 1.0 の1件。粗利益は `Σ 割合 × (価格 / entry − 1)` とする（変更点 5）
  - `exit_date` と `exit_price` は `exits` の最後の要素の日付と価格（実際の約定価格）。ピークからの戻しと売却後のリターンは、最後の約定価格を基準にする。最大リターン・最大ドローダウン・MFE・MAE は、entry から最後の売却日までの株価で測る
  - `exits` が2件以上なら `exit_legs` に記録する。1件なら `None`（従来の出力と同じ）
  - `TradeResult` に `exit_legs: list[list[Any]] | None = None` を末尾に追加する（既定値があるので、既存の生成箇所は変わらない）
- [ ] `simulate_signal` は、売却の判定だけを行い、`_finalize_trade` を呼ぶ形にする
**検証**: `tests/test_inflection_backtest.py` と `tests/test_inflection_forward.py` が無変更で PASS する

#### Step 2: REQ-045 — 売却ルールのシミュレーター
- [ ] `exit_rules.py` に、ルールを frozen dataclass で定義する
  - `TrailingRule(stop_pct)`（受入条件 1 の比較用）
  - `ChandelierRule(atr_multiple=3.0, atr_window=22)`
  - `MovingAverageBreakRule(ema_span=10, activation_gain_pct=20.0)`
  - `TimeStopRule(check_day=15, min_gain_pct=5.0, then_trailing_pct=15.0)`
  - `PartialTakeProfitRule(target_gain_pct=50.0, fraction=0.5, trailing_pct=15.0)`
- [ ] `simulate_exit_rule(signal, history, rule, *, holding_days, round_trip_cost_pct)`:
  - entry は `simulate_signal` と同じ（シグナル日の翌営業日の寄付）
  - 保有0日目から1日ずつ判定する。判定の順序は既存の trailing と同じ（その日の寄付 → 日中の安値・高値 → 終値）
  - **Chandelier**: stop = 前日までの HWM − 3.0 × 前日までの ATR(22)。寄付が stop 以下なら寄付で、安値が stop 以下なら stop 価格で売る。HWM はその日の判定のあとに高値で更新する
  - **移動平均割れ**: 終値までの最大含み益（終値基準）が +20% 以上になった日以降、終値が10日 EMA（`ewm(span=10, adjust=False)`、保有開始前の終値も使う）を下回ったら、**翌営業日の寄付**で売る。その日が最大保有日数の最終日なら、その日の終値で売る
  - **時間 stop**: 15営業日目（保有0日目から数えて14日目）の終値で含み益が +5% 未満なら、翌営業日の寄付で売る。そうでなければ、翌日から trailing 15%（HWM は entry と15日目までの高値の最大値から始める）
  - **段階利確**（変更点 3）: 状態として「残りの割合」（初め 1.0）と「利確済みか」を持つ。trailing 15% の stop は、前日までの HWM から計算し、残りの数量にかけ続ける。1日の判定は次の順に行う
    1. 寄付が stop 以下: 残りを全量、寄付で売って終了
    2. まだ利確しておらず、寄付が +50% 以上: 半分を寄付で売り、利確済みにする（**この日の判定は続ける**）
    3. 日中:
       - 利確済み（前の日まで、または手順2で利確した）で、安値が stop 以下: 残りを stop 価格で売って終了
       - まだ利確しておらず、安値が stop 以下かつ高値が +50% 以上（順序が不明）: stop を先とみなし、残りを全量 stop 価格で売って終了
       - まだ利確しておらず、高値だけが +50% 以上: 半分を +50% の価格で売り、利確済みにする
       - まだ利確しておらず、安値だけが stop 以下: 全量を stop 価格で売って終了
    4. 終了していなければ、その日の高値で HWM を更新する
    - 例（review #2）: entry=100、前日までの HWM=140（stop=119）、当日の O/H/L=160/165/115 → 半分を 160（寄付）、残りを 119（stop）で売る
    - 利確は1回だけ。利確済みの後に再び +50% 以上になっても、追加では売らない
  - 最大保有日数に達したら、その日の終値で残りを売る
  - 判定の途中で将来の日足がなくなり、売却が決まっていなければ、既存と同じく未完了（`horizon_matured=False`、損益 `None`）
  - ATR の履歴が足りなければ `exit_reason="insufficient_history"` の未完了とする（変更点 4）
  - O/H/L のいずれかに NaN があれば、既存の trailing と同じく `ValueError`
  - 結果は `_finalize_trade` で `TradeResult` を作る。`exit_reason` には、ルールに応じた値（`chandelier_stop`、`chandelier_gap`、`ma_break`、`time_stop`、`partial_then_trailing_stop` など）を入れる
**検証**: 受入条件 REQ-045 の 1〜4、6

#### Step 3: REQ-045 — exit 比較に新しいルールを追加する
- [ ] `_build_group_report` の exit 比較のブロック（1つのルール × 保有日数について、通常コストと stress コストの集計を作る部分）を、`_exit_strategy_report(trades, stress_trades, *, rule, holding_days, benchmark_history)` にまとめる。既存の9通りは、この関数を使って同じ値を作る
- [ ] 新しい4つのルールを、最大保有日数 126 で追加する。キーは `chandelier_3atr22_h126`、`ma10_break_after20_h126`、`time15d_5pct_then_trail15_h126`、`partial50_half_then_trail15_h126`。`rule` の欄に、パラメータを含むルールの説明を入れる
**検証**: 受入条件 REQ-045 の 5（既存の9通りの値が変わらない。リファクタの前後で `_build_group_report` の出力を比べる回帰テストを追加する）

#### Step 4: REQ-046 — 相場環境の判定
- [ ] `regime.py` に次を置く。どちらも `signal_date` 以前の終値だけを使う
  - `trend_regime(closes, signal_date) -> "up" | "down" | "unknown"`: 最新の終値 ≥ 直近200本の単純平均なら `up`、未満なら `down`、200本未満なら `unknown`
  - `volatility_regime(closes, signal_date) -> "high" | "normal" | "unknown"`: 日次対数リターンの直近20本の標準偏差 × √252 を当日の値とし、直近252営業日分の同じ値の中央値より大きければ `high`、それ以外は `normal`。273本未満なら `unknown`
- [ ] `PRIOR_HISTORY_DAYS` を 460 にする（変更点 1）。コメントに必要本数の根拠を書く
**検証**: 受入条件 REQ-046 の 1、2

#### Step 5: REQ-046 — 自己学習と層別集計
- [ ] learning の `evaluate_learning_observations` で、ベンチマークの終値から各観測の regime を判定し、`factor_labels` の結果に `regime_trend:...` と `regime_vol:...` を追加する（`factor_labels` 関数自体は変えない）
- [ ] `_report_breakdowns` に `regime_breakdown` を追加する。トレンドとボラティリティのそれぞれについて、regime ごとの件数、平均の純リターン、勝率、平均超過リターン（`paired_benchmark_returns`）を出す。既存の `score_band_sample_counts` と `regime_sample_counts` は変えない
**検証**: 受入条件 REQ-046 の 3〜5

#### Step 6: REQ-047 — Position Monitor の事前警告
- [ ] `STATUS_COLUMNS` の末尾に `last_warned_at` を追加する
- [ ] `run_position_monitor.py` に `WARNING_DISTANCE_PCT = 3.0` を置く
- [ ] **警告の重複は、ポジション（`ticker` と `entry_date` の組）ではなく、ticker 単位で防ぐ**（review #3。要件は「同じ銘柄・同じ日には1回だけ」）。triggered の通知のキー（ポジション単位）は変えない
  - 前回の状況シートの**全行**から、`last_warned_at` の日付（JST）が今日の ticker を集め、「今日すでに警告した ticker」とする
  - 今回の行のうち、`status="ok"` で、triggered でなく、`distance_to_stop_pct ≤ 3.0` の行を、ticker ごとにまとめる。同じ ticker の行が複数あれば、`distance_to_stop_pct` が最も小さい値を代表にする
  - 「今日すでに警告した ticker」を除いた ticker を、警告の対象にする。1つの ticker はメッセージに1回だけ載せる
- [ ] 警告は、triggered の通知とは別の1通の Slack メッセージで送る。文言は「[検証用アラート] stop まで残り x% の銘柄があります。確定した売買判断ではありません。」で始める
- [ ] **`last_warned_at` は、行ではなく ticker 単位で引き継ぐ**（再レビュー #1）。`write_status` は毎回、今回の行だけで状況シートを書き直すため、行単位で引き継ぐと、同じ日に古い行が消えたときに警告済みの記録も消え、次の実行で同じ ticker を再び警告してしまう
  - 前回の状況シートの全行から、ticker ごとに「今日（JST）の日付の `last_warned_at` のうち最新の時刻」を求め、`warned_today: dict[ticker, 時刻]` とする（上の「今日すでに警告した ticker」はこの dict のキー）
  - 今回の**すべての行**（`status` が ok・stale・error のどれでも、新しい行でも）について、`last_warned_at` を次のように決める
    1. 今回の送信に成功した ticker の行: 今の時刻
    2. それ以外で、ticker が `warned_today` にある行: `warned_today[ticker]` の時刻（前回の自分の行がない新しい行も含む）
    3. それ以外: 前回の自分の行（同じ `ticker` と `entry_date`）の値。なければ空
  - 送信に失敗した場合は、手順1の時刻を作らない（その ticker は手順2・3で決まる）
  - `_preserve_previous_state` の `last_warned_at` の扱いも、この規則に合わせる
- [ ] `--dry-run` では送信しない（既存と同じ）
**検証**: 受入条件 REQ-047 の 1〜5

#### Step 7: テスト・CI
- [ ] `tests/test_exit_rules.py`:
  - 受入条件 1: 固定 seed の合成 OHLC 200通りで、`TrailingRule(15)` の結果が `simulate_signal(trailing_stop_pct=15)` の `TradeResult` と全フィールドで一致する
  - 各ルールの手計算ケース: ギャップダウン、日中の stop、翌日の寄付での売却、最大保有日数の満了、条件に当たらない場合、未完了
  - 段階利確（review #1・#2）:
    - 2つの売却の価格が異なり、最後の売却後は株価が横ばいのケースで、損益が加重平均（例: 100 → 半分を 150、残りを 170 → 粗利益 +60%）になり、`exit_price` は 170、売却後のリターンは 0% になる（加重平均の 160 を基準にした +6.25% にならない）
    - 寄付で利確 → 同じ日に残りが stop（O/H/L=160/165/115、stop=119 → 半分 160、残り 119）
    - 寄付で利確が成立せず、日中に目標と stop の両方に触れる → 残りを全量 stop
    - 利確した後の日に再び目標以上になっても、追加で売らない
    - `exit_legs` が記録され、1回で売る trade（trailing など）では `None` のままで、他の値は従来と同じ
  - 先読みがないこと: 判定日より後の価格を変えても、その日までの判定（売却日・価格）が変わらない（ATR、EMA、含み益）
  - ATR の履歴不足で `insufficient_history`、O/H/L の NaN で `ValueError`
- [ ] `tests/test_inflection_forward.py`: 既存の9通りの値が変わらないこと（リファクタの前の出力を固定値として比べる）、新しい4つのキーが出ること
- [ ] `tests/test_regime.py`: 判定の境界、履歴不足、先読みがないこと
- [ ] `tests/test_inflection_learning.py`: regime のラベルが factor に入り、BH の family に含まれる
- [ ] `tests/test_forward_prices.py`: 取得期間の開始が 460日前になる。価格ハッシュの切り出しは変わらない（既存の回帰テストが PASS する）
- [ ] `tests/test_run_position_monitor.py`、`tests/test_sheets_client.py`: 受入条件 REQ-047 の 1〜5。加えて（review #3）:
  - 同じ ticker・異なる `entry_date` の2行が**同時に** stop に接近 → 警告は1回で、メッセージにその ticker は1回だけ載る。両方の行に `last_warned_at` が記録される
  - 同じ ticker の2行が、同じ日の**別々の実行で順に**接近（1回目の実行では1行だけ接近）→ 2回目の実行では警告しない
  - 翌日は再び警告できる
  - 前回の状況シートにない新しい行でも、その ticker が今日すでに警告済みなら警告しない
  - **同じ日の3回の実行**（再レビュー #1）: (1) ticker A・購入日 X の行で警告する → (2) 保有を A・購入日 Y に入れ替える（X の行は消える）。警告せず、Y の行に (1) の警告時刻が書かれる → (3) 同じ日にもう一度実行しても警告しない。翌日の実行では再び警告できる
  - stale・error の行に、`warned_today` の時刻が引き継がれる
  - 送信に失敗した場合、新しい警告時刻が作られず、次の実行で再送される
- [ ] `test.yml` の mypy 対象と、`forward_validation.yml` の起動パス・テスト一覧に、新規モジュールとテストを追加する
**検証**: `pytest tests/`、`ruff check src scripts tests`、mypy がすべて PASS する

### 例外・エラーハンドリング方針
- シミュレーター: 価格の欠損（O/H/L の NaN）は既存どおり `ValueError`。履歴不足は例外にせず、未完了として集計から除く
- regime: 履歴不足は `unknown` とし、例外にしない
- Monitor: Slack の送信に失敗した場合は、既存の triggered 通知と同じく、状況シートを書いてから例外を投げる。送信できなかった警告は `last_warned_at` を更新しない（次回の実行で再送される）

### テスト/検証方針
- 自動テスト: `.venv/bin/python -m pytest tests/ -q`、`.venv/bin/ruff check src scripts tests`、`.venv/bin/mypy --ignore-missing-imports <test.yml の対象>`
- 手動確認観点:
  - [ ] push 後、最初の週次 forward validation の summary に、新しい4つの exit キーと `regime_breakdown` が出ている
  - [ ] 実行時間が大きく延びていない（シミュレーションが4ルール × 2コスト × 3グループ分増える）
  - [ ] Position Monitor の初回実行で、状況シートに `last_warned_at` 列が追加される

### リスクと対策
1. リスク: リファクタ（Step 1・3）で、既存の trailing と exit 比較の値が変わる → 対策: 既存テストを無変更で通し、さらにリファクタ前の出力を固定値として比べる回帰テストを追加する
2. リスク: ルールの数が増え、最も良かったルールを過大に評価する → 対策: パラメータは1組に固定し、探索しない。レポートの `multiple_comparisons_caveat` は維持する。Deflated Sharpe Ratio は保留中の別要件
3. リスク: 段階利確の「同じ日に stop と目標」の仮定が、実際の約定と違う → 対策: 保守的な仮定（stop が先）を採り、`rule` の説明に明記する
4. リスク: 取得期間の延長で、週次 CI の実行時間が延びる → 対策: 増えるのは1銘柄あたりの行数だけで、API の呼び出し回数は変わらない。手動確認で実行時間を見る
5. リスク: 状況シートの列の追加で、既存のシートと列がずれる → 対策: `write_status` は毎回見出し行から書き直すので、列の追加は自動で反映される。読み込み側は列名で値を取るので、古いシートに `last_warned_at` がなくても動く（テストで確認する）

### 完了条件
- [ ] REQ-045 の受入条件 1〜6、REQ-046 の 1〜5、REQ-047 の 1〜5 を満たすテストが PASS する
- [ ] 既存の trailing の結果と、exit 比較の9通りの値が変わっていない
- [ ] 戦略、snapshot、Monitor の売却判定が変わっていない（live、shadow health、position exit のテストが無変更で PASS する）
- [ ] `pytest`、`ruff`、`mypy` がすべて PASS する
