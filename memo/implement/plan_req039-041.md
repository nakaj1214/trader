## 実装計画: J-Quants 過去データによる point-in-time 過去検証 — REQ-039 / REQ-040 / REQ-041

> 入力: [proposal.md](proposal.md)
> 以前の plan.md（REQ-037/038、実装済み）は [plan_req037-038.md](plan_req037-038.md) に移した。

### 目的
現行 v3 のロジックを、J-Quants Free の過去データ（約2年分）の各営業日に point-in-time で適用し、forward と同じ評価器で成績を出す。財務の取得時点を「開示当日」と「開示から12週後」の2通りで比較し、撤退条件を一次判定する。評価専用で、パラメータ探索はしない。

### 前提（Step 0 で満たす）
- REQ-037/038（snapshot schema 5）が**未コミット**である（2026-10-01 時点の `git status` で確認済み）。本計画は REQ-037 で切り出した `_evaluate_candidate` と対照群の処理に依存するため、先にコミットする。
- `.env` に `JQUANTS_API_KEY` を保存済み（gitignore 済み、権限 600）。スクリプトは `.env` を自動では読まないため、実行時に `set -a; . ./.env; set +a` で読み込む。

### 提案からの変更点（調査で判明した事項）
1. **財務のウォームアップ期間を追加する。** 前年同期比には、1年前の同じ期の実績が必要である。キャッシュは 2024-10 頃からしかないため、それより前の比較対象は取れない。シグナル開始日の既定値を `max(252営業日の履歴が揃う日, 財務キャッシュ開始日 + 494日)` とする。494日は、1年 + 決算発表までの約45日（410日）に、**最長ラグの84日（`free_12w`）を加えた値**である。これにより、両ラグとも前年同期の行がキャッシュ内に入る（review #4）。ラグごとに、月ごとの「前年同期比が計算できた候補の割合」をレポートに出す。494日でも全銘柄の比較可能性は保証されないため、このカバー率の確認は続ける。**評価できる期間は大きく縮む。** 2026-10-01 時点の試算（取得期間 2024-10-08〜2026-07-02、両端に7日の余裕）では、シグナル開始日が 2026-02-14 で、h60 が完了するのは 2026-04-03 までの**33営業日（deep candidate 約825件）**しかない。h5 と h20 は、より長い期間で評価できる。EARLY_CANDIDATE はこのうちの一部なので、**撤退判定は `insufficient_sample` になる可能性が高い**。これは手法の欠陥ではなく、Free プランの「2年」という期間と「12週ラグの比較」を両立させるための代償である。結果が出たら、レポート §8 の判断材料（Light プランなら過去5年分で、同じ条件で約3年分を評価できる）として扱う。
2. **月の途中の IPO など、月初の master に載っていない銘柄の扱い（point-in-time）。** master は月初に取得するが、取得段階で日足を先に取得し、**ある日の日足に、その日以前の最新の master にない銘柄が現れたら、その日の master を追加で取得してキャッシュする**。ただし、同じ銘柄について追加取得するのは1回だけにする（追加取得しても master に載らない銘柄は、master 外として記録し、以後は追加取得しない）。scan の再現では、常に **`as_of` 以前で最新の master** だけを使い、未来の master は一切参照しない（review #2）。追加取得の回数はレポートに出す。爆発的上昇の候補になりやすい新規上場銘柄を、上場当日から拾えるようにするための措置である。
3. **評価の horizon は forward と同じ 5 / 20 / 60 / 126 / 252 にする**（提案の 120 ではない）。forward の `_build_group_report` をそのまま再利用し、forward と直接比較できるようにするため。期間が足りない horizon は、forward と同じく未完了として扱われる。
4. **調整済み価格は自分で計算し、用途ごとに基準日を分ける。** J-Quants の `AdjC` は取得時点を基準に調整されるため、取得が数日にまたがると基準がずれる。そこで生の `C` と `AdjFactor` から計算する。`cum(d)` = `d` より後の全 `AdjFactor` の積とすると、次のようになる（review #3）。
   - **scan の再現用**（`as_of` 基準）: `adj_asof(d) = C(d) × cum(d) / cum(as_of)`。これは `d` から `as_of` までの係数だけを掛けたものと等しく、`as_of` より後の分割に影響されない。このため `current_price` などを含む出力全体が、未来の日足の追加に対して不変になる
   - **評価用**（全期間で一貫した基準）: `adj_eval(d) = C(d) × cum(d)`。trade のリターンは比なので、基準日によらない

### スコープ
- 含むもの: REQ-039（取得とキャッシュ）、REQ-040（過去の scan の再現）、REQ-041（レポート、ラグ比較、撤退判定）、それらのテスト。forward の集計補助関数を `src/` へ移動（挙動は変えない）。CI の mypy 対象の追加
- 含まないもの: 閾値・重みの探索、ストップ高・安の約定不能の扱い、12週以降の価格補完、TOB の exit 扱い、CI での実行、J-Quants の有料プランへの切り替え

### 影響範囲（変更/追加予定ファイル）
- `src/data/jquants_v2_client.py`: `daily_bars(date)`、`financial_summary_by_date(date)` を追加
- `src/data/jquants_history.py`（新規）: 期間の一括取得、再開可能なキャッシュ、キャッシュの読み込み
- `src/screening/inflection_live.py`: 選定・評価・対照群の処理（L510〜575）を `select_and_evaluate()` に切り出す（live の出力は変えない）
- `src/evaluation/inflection_report.py`（新規）: `scripts/rebuild_inflection_forward_validation.py` から `_build_group_report`、`_summary_only`、`regime_label`、`_report_breakdowns`、`_paired_trade_rows` と関連定数を移す
- `scripts/rebuild_inflection_forward_validation.py`: 上記を import して使う（挙動は変えない）
- `src/evaluation/inflection_historical.py`（新規）: 価格パネルの構築、point-in-time 財務 client、`reconstruct_scan`、`kill_criterion`、レポートの組み立て
- `scripts/run_inflection_historical_backtest.py`（新規）: CLI（`--fetch`、期間、キャッシュ先、撤退閾値）
- `tests/test_jquants_history.py`、`tests/test_inflection_historical.py`（新規）、`tests/test_jquants_v2_client.py`（追記）
- `.github/workflows/test.yml`: mypy の対象に新規 src/scripts を追加
- `memo/project-overview.md`: 過去検証の位置付けを1段落追記

### 実装ステップ

#### Step 0: 前提を満たす
- [ ] REQ-037/038 の変更（`git status` の M ファイルと proposal/plan のリネーム）をコミットする。push はしない（ユーザーの指示があるまで）
**検証**: `git status` で REQ-037/038 の差分が残っていない。`pytest tests/` が PASS する

#### Step 1: forward の集計補助関数を `src/evaluation/inflection_report.py` に移す（挙動は変えない）
- [ ] `_build_group_report`、`_report_breakdowns`、`_paired_trade_rows`、`regime_label`、`_summary_only` と、それらが使う定数（`ROUND_TRIP_COST_PCT`、`STRESS_ROUND_TRIP_COST_PCT`、`BENCHMARK_ROUND_TRIP_COST_PCT`、`TAX_RATE_PCT`）を移す
- [ ] forward スクリプトはそれらを import する。既存テストが参照する名前（`tests/test_inflection_forward.py` がスクリプトから import している名前）は、スクリプトから re-export して互換を保つ
**検証**: `tests/test_inflection_forward.py` が無変更で PASS する

#### Step 2: live の選定・評価処理を `select_and_evaluate()` に切り出す（挙動は変えない）
- [ ] 戻り値: `candidates`（スコア順）、`control_sample`、`control_seed`、`technical_usable_tickers`（set）、`liquid_candidate_count`、`deep_candidate_count`
- [ ] 引数: `prices`、`ticker_meta`、`client`（`financial_summary(code)` を持つ任意のオブジェクト。`typing.Protocol` で型を定義）、`seed_date`、`deep_candidates`、`min_turnover_jpy`、`control_sample_size`、`fundamental_limitation`
- [ ] `scan_japan_inflection` は、市場別 coverage の集計（`technical_usable` の市場別件数）を、戻り値の `technical_usable_tickers` から計算する
**検証**: `tests/test_inflection_live.py` が無変更で PASS する

#### Step 3: REQ-039 — client の追加メソッドと、再開可能なキャッシュ
- [ ] `JQuantsV2Client.daily_bars(date)` → `_get("/equities/bars/daily", {"date": date})`
- [ ] `JQuantsV2Client.financial_summary_by_date(date)` → `_get("/fins/summary", {"date": date})`
- [ ] `jquants_history.fetch_range(client, start, end, cache_dir, *, kinds=("bars","fins","master"))`:
  - bars: XTKS の営業日。fins: 全暦日。master: 各月の第1営業日に加え、変更点 2 の追加取得（日足にその日以前の最新 master にない銘柄が現れた日の master。同じ銘柄の追加取得は1回だけで、それでも載らない銘柄は `cache_dir/non_master_codes.json` に記録する）。取得順は bars → master → fins とする
  - 保存先は `cache_dir/{kind}/YYYY-MM-DD.json.gz`。gzip の JSON の list。空でも保存する
  - 一時ファイルに書いてから `os.replace` で置き換え、中断時に壊れたファイルを残さない
  - 既にあるファイルはスキップし、呼び出し回数を減らす
  - **4xx はステータスで分類しない。すべて停止する**（review #1）。公式仕様では 400 はパラメータ不正、403 は無効・期限切れのキーやプラン権限でも返るため、ステータスだけでは「範囲外」と区別できない。停止時のメッセージには、ステータス、kind、日付、応答本文の `message`（キーは含めない）を出す。429 と 5xx は、既存 client の再試行に任せる
  - 範囲外の日付は、取得を始める前に避ける。取得期間の既定値は「今日 − 2年 + 7日」〜「今日 − 84日 − 7日」とする（両端に7日の余裕を持たせる）。`--probe` オプションで、開始日と終了日の bars を1回ずつ取得し、範囲内かどうかを確かめられるようにする。範囲外で停止した場合は、ユーザーが `--start` / `--end` を調整して再実行する（取得済みの日はキャッシュ済みなので、無駄にならない）
  - 実行の終わりに、取得できた最初と最後の日付と、master の追加取得の回数を表示する
- [ ] `jquants_history.load_cache(cache_dir) -> HistoryCache`（bars、fins、master を読み込む）
**検証**: 受入条件 REQ-039 の 1〜5。fake の `requests.get` を使い、外部接続はしない。受入条件 4（範囲外）は、review #1 に従って「4xx（400 のパラメータ不正、403 の無効キー）で停止し、それまでのキャッシュが残ること」に置き換えて検証する。master の追加取得が、新しい銘柄が現れた日に1回だけ行われることも確認する

#### Step 4: REQ-040 — 価格パネルと point-in-time 財務 client
- [ ] **価格パネル**: bars から銘柄ごとの生の DataFrame（`O/H/L/C/Vo/Va/AdjFactor`）と `cum(d)` を作る。ticker は `Code` の先頭4桁 + `.T`（live の `_ticker_from_code` を使う）
  - scan の再現用: `price_frame_as_of(ticker, as_of)` が、`as_of` までの末尾252営業日を `adj_asof` で返す（`Close`、`Open/High/Low` も同じ係数）。`Volume = Vo`（生）、`Turnover = Va`
  - 評価用: `evaluation_histories()` が、全期間を `adj_eval` で返す
- [ ] **財務 client**: `PointInTimeFinancials(fins_rows, as_of, lag)` が `financial_summary(code)` を持ち、取得可能時点 ≤ `as_of` 16:40 JST の行だけを返す
  - `lag="disclosure"`: 取得可能時点 = `DiscDate` + `DiscTime`（空なら 23:59）
  - `lag="free_12w"`: 取得可能時点 = `DiscDate` + 84日（日付単位で比較し、時刻は 00:00 とみなす）
  - fins の値は文字列で、空値は空文字（V2 の仕様）。live の `_to_float` がそのまま扱えることを確認する
- [ ] **master の時点参照**: キャッシュ内の master のうち、日付が `as_of` 以前で最新のものを使う（月初分と追加取得分を区別しない）。未来の master は参照しない（変更点 2）
- [ ] **`reconstruct_scan(as_of, cache, *, lag, control_sample_size)`**:
  - ユニバース = 市場区分が Prime/Standard/Growth の銘柄のうち、`as_of` に日足がある銘柄
  - prices = 各銘柄の `as_of` までの末尾252営業日
  - `select_and_evaluate(prices, ticker_meta, PointInTimeFinancials(...), seed_date=as_of, ...)` を呼ぶ
  - live と同じ形の dict（`candidates`、`control_sample`、`latest_price_date=as_of`、`strategy_version`、`report_schema_version`、補った件数）を返す
**検証**: 受入条件 REQ-040 の 1〜4。
- **live との一致**は、共通 helper ではなく、**実際の `reconstruct_scan`** の出力と、同じ価格・master・財務を与えた `scan_japan_inflection`（価格取得と J-Quants をモック）の出力を比べる（review #2）
- **未来データへの不変性**: `as_of` より後に (a) 株式分割を含む日足、(b) 開示行、(c) 市場区分を変えた master や新しい銘柄を含む master を追加しても、`candidates` と `control_sample` の全体（`current_price` を含む）が変わらないことを確認する（review #2・#3）
- 月の途中に上場した銘柄が、上場日から対象になることを確認する
- 分割を含む合成データで、`adj_asof` と `adj_eval` の比が銘柄ごとに一定になることを確認する
- **取得基準が異なる合成例**: 分割の前に取得したファイル（C=100、AdjC=100）と後に取得したファイル（C=50、AdjC=50、AdjFactor=0.5）が混在していても、自前の `adj_eval` が両日とも 50 になり、Step 7 (a) の検査関数（同じ取得時点のデータとの比較）を通ることを確認する（review 再指摘 #2）

#### Step 5: REQ-041 — レポートと撤退判定
- [ ] シグナル期間 = `[max(252営業日の履歴が揃う日, 財務キャッシュ開始日 + 494日), キャッシュの最終営業日]`（変更点 1）。2つのラグで**共通**の期間とする。引数 `--signal-start` で上書きできる
- [ ] ラグごとに、月ごとの前年同期比のカバー率（`features.revenue_growth_yoy_pct` が null でない候補の割合）を出す
- [ ] 各ラグについて、期間内の全営業日で `reconstruct_scan` を実行し、forward と同じ形の signal（`ticker`、`signal_date`、`date`、`score`、`classification`、`market`、`avg_turnover_20d_jpy`）を集める。対照群は `classification="CONTROL"` の別グループにする
- [ ] 分類（EARLY_CANDIDATE / WATCH / NONE / CONTROL）ごとに `_build_group_report(signals, histories, histories, benchmark_history, dates)` を呼ぶ（分割調整のみの価格なので、2つの価格基準に同じ dict を渡す）。ベンチマークは bars の `13060` → `1306.T`。[未確認: ETF が日足 API に含まれること。含まれない場合はエラーで停止し、ユーザーに報告する]
- [ ] EARLY_CANDIDATE の h60 について `simulate_portfolio` を forward と同じ設定で実行する。`compute_tracked_pool_explosion_recall` も実行する
- [ ] **ラグ比較**（review #5）: EARLY_CANDIDATE の h60 について、各ラグの平均超過リターン、CI、件数を出す。加えて、**差とその 95% CI** を出す
  - 差の符号: `disclosure − free_12w`（正なら、財務を早く使えることに価値がある）
  - 比較対象: 両ラグとも有効な超過リターン（下記の有効ペア）が1件以上ある signal_date に限定する。除外した日数をラグ別に記録する
  - CI: `cluster_paired_bootstrap_diff()` を新規に作る（`inflection_historical.py` 内。既存の `cluster_bootstrap_ci` は変えない）。比較対象の signal_date を同じ乱数列で**まとめて**再標本化し、各反復で「その日付集合に属する各ラグの trade の平均」の差を計算する。seed は既存の `BOOTSTRAP_SEED`
  - ラグごとに選ばれる銘柄や件数が違ってもよい（各ラグの平均は、そのラグの trade で計算する）
  - どちらかのラグに有効な trade がない、または比較対象の日付が2日未満の場合は、差と CI を `null` にし、理由を記録する
- [ ] **`kill_criterion(trades, benchmark_history, *, min_independent=100)`**（review #6）:
  - h60 の**完了した** trade を `select_non_overlapping_trades` で独立化する
  - `paired_benchmark_returns` で超過リターンを求め、`excess_return_pct` が有限の値の行（**有効ペア**）だけを使う
  - CI は有効ペアについて `cluster_bootstrap_ci`（signal_date クラスタ）で求める
  - 判定:
    - 有効ペアが閾値未満、または CI が作れない（クラスタが2個未満で `None`）なら `insufficient_sample`。理由（`below_min_independent` / `ci_unavailable`）を記録する
    - CI の下限が 0 より大きければ `pass`
    - それ以外は `fail`
  - 記録項目: 判定、理由、閾値、独立化後の trade 数、有効ペア数、signal_date クラスタ数、CI
- [ ] 注記: 実際に使った期間、価格調整の差（J-Quants は分割のみ、live は配当込み）、財務のウォームアップ、月の途中の IPO の補完件数、**パラメータ探索をしていないこと**、多重比較の注意
- [ ] 出力: `artifacts/inflection_historical_backtest.json`（全体）、`..._summary.json`（`_summary_only` を適用し、さらに銘柄コードを含むキーを除いたもの）
- [ ] CLI:
  - `--fetch`（取得のみ）
  - `--probe`（開始日と終了日の bars を1回ずつ取得して範囲内か確かめるだけ。キャッシュは書かない）
  - `--verify-adjustment N`（Step 7 (a) の検査）
  - `--start/--end`（取得期間。既定は Step 3 と同じ「今日 − 2年 + 7日」〜「今日 − 84日 − 7日」。**既定値の定義は1か所（`jquants_history.default_fetch_range(today)`）にまとめ、CLI と取得処理の両方がそれを使う**）
  - `--cache-dir`（既定 `.data/jquants`）、`--signal-start`、`--min-independent`
**検証**: 受入条件 REQ-041 の 1〜5

#### Step 6: テスト・CI・文書
- [ ] `tests/test_jquants_history.py`:
  - ページングの結合、キャッシュのスキップ、中断と再開、gitignore（`git check-ignore`）
  - **4xx で停止すること**（400 のパラメータ不正、403 の無効キーで停止し、それまでのキャッシュが残る。全日を範囲外として続行しない）（review #1）
  - master の追加取得が、新しい銘柄が現れた日に1回だけ行われ、master 外の銘柄は二度と取得しない
  - `--probe` が開始日と終了日の bars を1回ずつだけ呼ぶ
  - **CLI の既定期間と取得処理の既定期間が同じ**（どちらも `default_fetch_range` を使う）。その既定期間の境界日で 4xx が返った場合にも停止する（review 再指摘 #1）
- [ ] `tests/test_inflection_historical.py`:
  - **実際の `reconstruct_scan`** と live の一致
  - 未来データへの不変性（分割を含む日足、開示行、市場区分を変えた master や新しい銘柄を含む master を追加しても、`current_price` を含む出力全体が不変）
  - `free_12w` で84日未満の財務を除外すること
  - 上場廃止銘柄の扱い
  - 月の途中に上場した銘柄が上場日から対象になること
  - `adj_asof` と `adj_eval` の比が一定であること
  - 開始境界の付近で、両ラグとも前年同期の行を取得できる合成ケース（494日）（review #4）
  - ラグ比較で分類が変わる合成ケース
  - 差と CI の計算（既知の差を持つ合成データで符号と値を確認し、日付を共有した再標本化の決定性も確認する。片側が空の場合、比較対象日が2日未満の場合は `null` と理由を記録する）（review #5）
  - `kill_criterion` の判定: pass、fail（0をまたぐ、全体が負）、insufficient_sample（閾値未満、**単一 signal_date で CI が作れない**、**ベンチマーク欠損で有効ペアが減る**）（review #6）
  - summary に ticker が含まれないこと
  - 合成キャッシュでの CLI の完走
- [ ] `test.yml` の mypy 対象に、新規の src と scripts を追加する
- [ ] `memo/project-overview.md` に、過去検証の位置付け（ローカル専用、評価のみ、出力先）を追記する
**検証**: `pytest tests/`、`ruff check src scripts tests`、mypy がすべて PASS する

#### Step 7: 実データでの取得と実行（ユーザーの確認後）
- [ ] **ユーザーに確認してから**、`set -a; . ./.env; set +a; python scripts/run_inflection_historical_backtest.py --fetch` を実行する（外部 API の呼び出し。約1,500回、5時間前後）。バックグラウンドで実行し、中断した場合は再実行で続きから取得する
- [ ] 取得後、実データで次を確かめる
  - (a) **調整の検査**（`--verify-adjustment N`）: キャッシュ内で `AdjFactor ≠ 1` の日がある銘柄から最大 N 銘柄（既定 5）を選び、銘柄コード指定の日足（`/equities/bars/daily?code=`）を**1回の呼び出しで全期間取得**する（同じ取得時点・同じ調整基準のデータになる）。そのデータの中で、自前の `adj_eval` と `AdjC` の比が一定であることを確かめる。日付ごとのキャッシュファイルの `AdjC` とは比較しない（ファイルごとに取得時点が異なり、正しい調整でも比が一定にならないため。review 再指摘 #2）。追加の呼び出しは N 回
- [ ] client に `daily_bars_by_code(code)`（`_get("/equities/bars/daily", {"code": code})`）を追加する（検査専用）
  - (b) 1306.T が含まれている
  - (c) fins の `DiscTime` の書式
- [ ] 評価を実行し、集計サマリー（銘柄・trade を含まない）を `memo/analysis/historical_backtest_YYYY-MM-DD.md` に書き写す
**検証**: レポートが生成され、`kill_criterion` と2つのラグの比較が記録されている

### 例外・エラーハンドリング方針
- 取得: 429 と 5xx の再試行は既存の client に任せる。**4xx はステータスによらず停止する**（範囲外の可能性があっても続行しない）。取得済みのキャッシュは日単位で原子的に保存しているので残り、`--start` / `--end` を調整して再実行すれば続きから再開できる（Step 3 と同じ規則）
- 再現: 日足が252営業日に満たない銘柄は、live と同じく `_technical_features` の結果に従う（21日未満は除外）。財務がなければ live と同じく欠損として扱う
- 評価: キャッシュに必要な日足がない trade は、forward と同じく未完了として扱う。ベンチマークがない場合は停止する
- 秘密情報: API キーをログや出力に書かない。例外のメッセージに URL のクエリ（日付のみ）以外を含めない

### テスト/検証方針
- 自動テスト: `.venv/bin/python -m pytest tests/ -q`、`.venv/bin/ruff check src scripts tests`、`.venv/bin/mypy --ignore-missing-imports <test.yml の対象>`
- 手動確認観点（Step 7）:
  - [ ] 取得が中断しても、再実行で続きから再開される
  - [ ] 実際に取得できた期間の境界日がレポートに記録されている
  - [ ] `--verify-adjustment` の検査（同じ取得時点のデータとの比が一定）が通る
  - [ ] `.data/` と `artifacts/` 以外に J-Quants の生データが書かれていない（`git status` がクリーン）

### リスクと対策
1. リスク: 実データの形式（`AdjFactor` の意味、`DiscTime` の書式、ETF の有無）が想定と異なる → 対策: Step 7 の (a)〜(c) で最初に確かめ、違えば評価を実行する前に修正する。単体テストは仕様書に基づく合成データで先に固める
2. リスク: live のリファクタリング（Step 2）で、本番の scan の出力が変わる → 対策: 既存の live テストを無変更で通すことを条件にし、REQ-037 の契約テスト（scan の出力 → 保存前検査 → 両 loader）も通す
3. リスク: 財務のウォームアップ不足や、12週ラグのため財務点が過小になり、結果が戦略の実力を過小評価する → 対策: 月ごとの前年同期比のカバー率を出し、開始日を引数で調整できるようにする。ただし評価前に開始日を決め、結果を見てから動かさない
4. リスク: 結果を見て閾値を調整したくなる（過剰最適化） → 対策: 本計画ではパラメータ探索をしない。レポートに明記する。探索は holdout 付きの別要件にする
5. リスク: J-Quants の生データが公開リポジトリに混入する → 対策: 保存先を `.data/` と `artifacts/` に限定し、テストで gitignore を検査する。memo に書き写すのは集計値だけにする

### 完了条件
- [ ] REQ-039 の受入条件 1〜5（**条件 4 は改訂版**: 4xx で停止し、取得済みのキャッシュが残る。proposal.md も同じ内容に更新済み）、REQ-040 の 1〜5、REQ-041 の 1〜5 を満たすテストが PASS する
- [ ] live の scan と forward の既存テストが無変更で PASS する（Step 1・2 のリファクタリングで挙動が変わっていない）
- [ ] `pytest`、`ruff`、`mypy` がすべて PASS する
- [ ] Step 7 は、ユーザーの確認後に実行する（本計画の自動実行の範囲外）
