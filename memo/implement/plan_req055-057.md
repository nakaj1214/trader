## 実装計画: 記録した特徴量の評価への接続、過熱の事前警告、売却ルール比較の多重比較補正（REQ-055〜057）

> 要件書: [proposal_req055-057.md](proposal_req055-057.md)。**REQ-052〜054（[plan.md](plan.md)）の実装後に着手する**（REQ-055 が、REQ-053・054 の特徴量も扱うため）。`/implement-plans` は `plan.md` を読むので、実装を始めるときは、この内容を `plan.md` に入れ替える。

### 目的
REQ-050・053・054 で記録した特徴量を learning の評価につなぎ（REQ-055）、保有銘柄の過熱を事前に警告し（REQ-056）、売却ルールの比較に多重比較の補正（DSR）を加える（REQ-057）。戦略・スコア・分類・売却ルールの採用は変えない。

### スコープ
- 含むもの: learning の factor ラベルの追加、Monitor の過熱警告、forward のレポートへの `deflated_sharpe` の追加
- 含まないもの: 戦略・スコア・分類・売却ルールの採用の変更、決算日の警告、A8-d、出来高クライマックスの警告、昇格判定の条件の変更、新しい abstraction・ファイル（テストを除く）

### 事前に確認した事実
- learning の観測は、`features`（辞書）と `sector33_code` を持つ（`load_inflection_learning_observations`）。`factor_labels` は、この2つを使っていない。
- Monitor の警告は、`WARNING_DISTANCE_PCT = 3.0`、`_stop_proximity_candidates`、`_warned_today`、`_carry_warning_state`、シートの `last_warned_at`（**1銘柄に1つの列**）で構成される。したがって、警告の種類を増やすと、同じ列を共有する。1銘柄1日1通の方針（要件書）に合う。
- `PositionStatus`（[position_exit.py](../../src/monitoring/position_exit.py)）は、現在値、HWM、stop、含み損益、`distance_to_stop_pct` を持つが、20日前の終値は持たない。`evaluate_position` は `prior_confirmed_closes`（確定終値の系列）を受け取るので、そこから20営業日前の終値を取れる（**Monitor がその系列を何日分取得しているかは未確認**。ステップ2で確認する）。
- forward のレポートは、グループごとに `exit_strategies`（ルール名 → `_exit_strategy_report`）を持つ。各ルールは、`trades`（行）、`matured_summary`、`position_summary`（`select_non_overlapping_trades`）を持つ。

### 影響範囲（変更/追加予定ファイル）
- [src/evaluation/inflection_learning.py](../../src/evaluation/inflection_learning.py): `factor_labels`、区切りの定数
- [scripts/run_position_monitor.py](../../scripts/run_position_monitor.py)、[src/monitoring/position_exit.py](../../src/monitoring/position_exit.py): 過熱の警告
- [src/evaluation/inflection_report.py](../../src/evaluation/inflection_report.py): `deflated_sharpe`
- `tests/test_inflection_learning.py`、Monitor のテスト、`tests/test_inflection_forward.py`（またはレポートのテスト）: 既存ファイルに追記
- 変更しないもの: `inflection_live.py`（本番の scan）、`inflection_backtest.py`、`STRATEGY_VERSION`、`REPORT_SCHEMA_VERSION`

### 実装ステップ

#### Step 1: REQ-055 learning の factor ラベル
- [ ] 区切り（経過日数、上昇日の割合、MAX、ボラティリティ、高値からの距離）を、`inflection_learning.py` の定数として定義する。既存の `_bucket` を使う。
- [ ] `factor_labels` で、`observation["features"]` が辞書で、キーの値が `None` でないときだけ、ラベルを追加する。`sector33_code` があれば `sector33:{コード}` を追加する。
- [ ] REQ-053・054 のキー（`quarterly_*`、`relative_*`）は、キーがあるときだけラベルにする（REQ-052〜054 が未実装でも動く）。
- [ ] 既存のラベルの順序と値を変えない。
**検証**: 受入条件 1〜5（REQ-055）。昇格判定の検定数（`promotion_gate`）がラベルの増加に追従することを、既存のテストの拡張で確認する。

#### Step 2: REQ-056 Monitor の過熱警告
- [ ] `run_position_monitor.py` が `prior_confirmed_closes` を何日分取得しているかを確認する。20営業日分（+現在値）に足りなければ、取得範囲の拡大が必要かを判断し、影響（通信量、実行時間）を報告する。
- [ ] 20営業日前の確定終値と現在値から、20日の上昇率を求める内部関数を追加する（履歴が足りなければ `None`）。閾値は、本番の `OVEREXTENDED` 分類の r20 の閾値（50%）に合わせる（`inflection_live.py` の定数があれば import せず、同じ値を Monitor の定数にして、コメントで対応を明記する。Monitor が scan のモジュールに依存しないため）。
- [ ] 警告の対象の選定（`_stop_proximity_candidates` と同じ形）に、過熱の条件を加える。同じ銘柄に両方の条件が重なるときは、1通にまとめる。`last_warned_at` の仕組み（1営業日に1銘柄1回）は変えない。
- [ ] `triggered`、`exit_reason`、`stop_price` の計算には触れない。
**検証**: 受入条件 1〜5（REQ-056）。

#### Step 3: REQ-057 Deflated Sharpe Ratio
- [ ] `inflection_report.py` に、取引ごとのリターンの系列から Sharpe、歪度、尖度を求める関数と、DSR を求める関数を追加する（標準ライブラリの `statistics`、`math`、`NormalDist` だけ。numpy は `src/` で使わない）。
  - 期待最大 Sharpe: `SR0 = sqrt(V) * ((1 - γ) * Φ⁻¹(1 - 1/N) + γ * Φ⁻¹(1 - 1/(N·e)))`（γ はオイラー・マスケローニ定数、V は N 個の試行の Sharpe の分散）。
  - DSR: `Φ( (SR − SR0) * sqrt(T − 1) / sqrt(1 − skew·SR + (kurt − 1)/4 · SR²) )`（kurt は尖度。正規分布で 3）。
  - T は取引数、N は対象のルールの数。
- [ ] `_build_group_report` の最後（`exit_strategies` を組み立てた後）で、ベースのコストのシナリオの `position_summary` の元の取引のうち、満期までのものが30件以上あるルールだけを対象にして、`deflated_sharpe` を計算し、グループのレポートに加える。対象が2ルール未満なら `{"value": None, "reason": ...}`。
- [ ] 既存のキーと値は変えない。標準偏差が0（全取引が同じリターン）のときは、0 除算を避けて `None` と理由を出す。
**検証**: 受入条件 1〜5（REQ-057）。既知の値（論文の数式を手計算した値）との比較、N が増えると DSR が下がることをテストする。

#### Step 4: 最終確認
- [ ] 新しいラベル、警告、`deflated_sharpe` が、本番の scan の出力（スコア・分類・候補）に影響しないこと。
- [ ] ruff、mypy（CI の対象のファイル）、`pytest tests/ -q`（カバレッジ 80% 以上）。
**検証**: 完了条件の全項目。

### 例外・エラーハンドリング方針
- ラベルの追加は、値が `None`、型が違う、キーがない場合に、例外を出さずにラベルを付けない（learning の再構築を、診断用の特徴量の欠損で止めない）。
- Monitor の過熱警告は、履歴が足りない場合に警告しない。警告の送信の失敗は、既存の stop 接近の警告と同じ扱いにする（Monitor の判定を止めない）。
- DSR は、計算できない場合に `None` と理由を出し、レポートの生成を止めない。
- ログと通知に、個人情報や認証情報を出さない（Monitor の警告は、既存と同じ範囲の情報だけ）。

### テスト/検証方針
- 自動テスト: `.venv/bin/python -m pytest tests/test_inflection_learning.py tests/test_inflection_forward.py -q` と Monitor のテスト（対象）、最後に `.venv/bin/python -m pytest tests/ -q`。`ruff check src scripts tests`、CI と同じ対象の `mypy --ignore-missing-imports`。
- 受入条件のテストが、実装の誤りを検出できることを、一時的にバグを入れて確認する（例: ラベルの境界の `<` と `<=` を入れ替える、警告の閾値を変える、DSR の試行数を固定する）。
- 手動確認観点: Monitor の警告のメッセージの文面。DSR の計算を、論文の数式と手計算で突き合わせる。

### リスクと対策
1. リスク: ラベルが増えると、BH 補正が厳しくなり、既存の factor の昇格が起きにくくなる → 対策: 意図した挙動（多重比較の補正）。レポートの検定数に反映されることを確認し、現在の昇格（`promoted`）の件数が、新しい項目がない観測では変わらないことをテストで確認する（ラベルは値があるときだけ付くため、過去の snapshot の factor の件数は変わらない）。
2. リスク: Monitor が20営業日分の終値を取得しておらず、過熱の警告が常に出ない → 対策: ステップ2の最初に取得範囲を確認する。足りなければ、影響を報告して判断を仰ぐ。
3. リスク: 警告が頻繁に出て、ユーザーの負担になる → 対策: 既存の1営業日1銘柄1回の仕組みを使う。閾値は、本番の `OVEREXTENDED` と同じで、新しい調整値を持たない。
4. リスク: DSR の前提（取引が独立、正規に近い）が満たされない → 対策: 取引は重なりのない取引を使い、取引数が少ないときは `None` にする。出力は参考値で、売却ルールの採用の判断に自動では使わない（備考に明記する）。
5. リスク: REQ-052〜054 が未実装の状態で実装を始めると、REQ-055 の一部のラベルが使えない → 対策: キーがあるときだけラベルにするので、順序に依存せずに動く。ただし、実装は REQ-052〜054 の後を推奨する。

### 完了条件
- [ ] REQ-055 の受入条件 1〜5 が、テストで確認されている
- [ ] REQ-056 の受入条件 1〜5 が、テストで確認されている
- [ ] REQ-057 の受入条件 1〜5 が、テストで確認されている
- [ ] スコア、分類、`candidates`、本番の scan の出力、売却の判定が変わらない
- [ ] `STRATEGY_VERSION`（v3）と `REPORT_SCHEMA_VERSION`（5）が変わっていない
- [ ] ruff、mypy、`pytest tests/ -q` が PASS（カバレッジ 80% 以上）
