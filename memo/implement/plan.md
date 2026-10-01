## 実装計画: J-Quants 過去データによる point-in-time 過去検証 — REQ-039 / REQ-040 / REQ-041

> 入力: [proposal.md](proposal.md)
> 以前の plan.md（REQ-037/038、実装済み）は [plan_req037-038.md](plan_req037-038.md) に移した。

### 目的
現行 v3 のロジックを、J-Quants Free の過去データ（約2年分）の各営業日に point-in-time で適用し、forward と同じ評価器で成績を出す。財務の取得時点を「開示当日」と「開示から12週後」の2通りで比較し、撤退条件を一次判定する。評価専用で、パラメータ探索はしない。

### 前提（Step 0 で満たす）
- REQ-037/038（snapshot schema 5）が**未コミット**である（2026-10-01 時点の `git status` で確認済み）。本計画は REQ-037 で切り出した `_evaluate_candidate` と対照群の処理に依存するため、先にコミットする。
- `.env` に `JQUANTS_API_KEY` を保存済み（gitignore 済み、権限 600）。スクリプトは `.env` を自動では読まないため、実行時に `set -a; . ./.env; set +a` で読み込む。

### 提案からの変更点（調査で判明した事項）
1. **財務のウォームアップ期間を追加する。** 前年同期比には、1年前の同じ期の実績が必要である。キャッシュは 2024-10 頃からしかないため、2025-11 中旬より前のシグナルでは前年の比較対象がなく、財務点が過小になる。シグナル開始日の既定値を `max(252営業日の履歴が揃う日, 財務キャッシュ開始日 + 410日)` とする（410日 ≒ 1年 + 決算発表までの約45日）。レポートには、月ごとの「前年同期比が計算できた候補の割合」を出す。h60 の評価対象は約100営業日（2025-11 中旬〜2026-04-10）になる見込みである。
2. **月初の master に載っていない銘柄（月の途中の IPO）の扱い。** その日に日足があるのに当月の master にない銘柄は、**同じ月の中で最も早い後続の master** から、銘柄の属性（市場区分・社名・業種）だけを補う。価格や財務の情報は使わないので、先読みにはならない。補った件数をレポートに出す。爆発的上昇の候補になりやすい新規上場銘柄を落とさないための措置である。
3. **評価の horizon は forward と同じ 5 / 20 / 60 / 126 / 252 にする**（提案の 120 ではない）。forward の `_build_group_report` をそのまま再利用し、forward と直接比較できるようにするため。期間が足りない horizon は、forward と同じく未完了として扱われる。
4. **調整済み価格は自分で計算する。** J-Quants の `AdjC` は、取得した時点を基準に調整される。取得が数日にまたがり、その間に株式分割があると、日ごとのファイルで基準がずれる。そこで生の `C` と `AdjFactor` から、パネル内で一貫した分割調整済み価格を計算する（リターンと高値比は一律の再スケールに影響されないので、基準日はキャッシュの最終日でよい）。

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
  - bars: XTKS の営業日。fins: 全暦日。master: 各月の第1営業日
  - 保存先は `cache_dir/{kind}/YYYY-MM-DD.json.gz`。gzip の JSON の list。空でも保存する
  - 一時ファイルに書いてから `os.replace` で置き換え、中断時に壊れたファイルを残さない
  - 既にあるファイルはスキップし、呼び出し回数を減らす
  - 範囲外を示す 4xx（`HTTPError` で、ステータスが 400/403/404）の日は `cache_dir/out_of_range.json` に記録して続行する。認証エラー（401）と 429 以外の 5xx は既存の再試行のあとで例外にする
  - 実行の終わりに、取得できた最初と最後の日付、範囲外の日数を表示する
- [ ] `jquants_history.load_cache(cache_dir) -> HistoryCache`（bars、fins、master を読み込む）
**検証**: 受入条件 REQ-039 の 1〜5。fake の `requests.get` を使い、外部接続はしない

#### Step 4: REQ-040 — 価格パネルと point-in-time 財務 client
- [ ] **価格パネル**: bars から銘柄ごとの DataFrame を作る。`Open/High/Low/Close` は分割調整済み（`C × 後続の AdjFactor の累積積`。O/H/L も同様）、`Volume = Vo`（生）、`Turnover = Va`。ticker は `Code` の先頭4桁 + `.T`（live の `_ticker_from_code` を使う）
- [ ] **財務 client**: `PointInTimeFinancials(fins_rows, as_of, lag)` が `financial_summary(code)` を持ち、取得可能時点 ≤ `as_of` 16:40 JST の行だけを返す
  - `lag="disclosure"`: 取得可能時点 = `DiscDate` + `DiscTime`（空なら 23:59）
  - `lag="free_12w"`: 取得可能時点 = `DiscDate` + 84日（日付単位で比較し、時刻は 00:00 とみなす）
  - fins の値は文字列で、空値は空文字（V2 の仕様）。live の `_to_float` がそのまま扱えることを確認する
- [ ] **master の時点参照**: `as_of` 以前で最も近い月の master を使う。日足があるのに載っていない銘柄は、同じ月の中で最も早い後続の master から属性だけを補い、補った件数を数える（変更点 2）
- [ ] **`reconstruct_scan(as_of, cache, *, lag, control_sample_size)`**:
  - ユニバース = 市場区分が Prime/Standard/Growth の銘柄のうち、`as_of` に日足がある銘柄
  - prices = 各銘柄の `as_of` までの末尾252営業日
  - `select_and_evaluate(prices, ticker_meta, PointInTimeFinancials(...), seed_date=as_of, ...)` を呼ぶ
  - live と同じ形の dict（`candidates`、`control_sample`、`latest_price_date=as_of`、`strategy_version`、`report_schema_version`、補った件数）を返す
**検証**: 受入条件 REQ-040 の 1〜4（live との一致は、同じ prices、master、client を `scan_japan_inflection`（価格取得をモック）と `select_and_evaluate` 経由の両方に渡して比較する）。分割を含む合成データで、計算した調整済み価格が連続になることを確認する

#### Step 5: REQ-041 — レポートと撤退判定
- [ ] シグナル期間 = `[max(252営業日の履歴が揃う日, 財務キャッシュ開始日 + 410日), キャッシュの最終営業日]`。引数 `--signal-start` で上書きできる
- [ ] 各ラグについて、期間内の全営業日で `reconstruct_scan` を実行し、forward と同じ形の signal（`ticker`、`signal_date`、`date`、`score`、`classification`、`market`、`avg_turnover_20d_jpy`）を集める。対照群は `classification="CONTROL"` の別グループにする
- [ ] 分類（EARLY_CANDIDATE / WATCH / NONE / CONTROL）ごとに `_build_group_report(signals, histories, histories, benchmark_history, dates)` を呼ぶ（分割調整のみの価格なので、2つの価格基準に同じ dict を渡す）。ベンチマークは bars の `13060` → `1306.T`。[未確認: ETF が日足 API に含まれること。含まれない場合はエラーで停止し、ユーザーに報告する]
- [ ] EARLY_CANDIDATE の h60 について `simulate_portfolio` を forward と同じ設定で実行する。`compute_tracked_pool_explosion_recall` も実行する
- [ ] **ラグ比較**: EARLY_CANDIDATE の h60 の平均超過リターン、その CI、件数を、2つのラグについて並べて出す
- [ ] **`kill_criterion(trades, benchmark_history, *, min_independent=100)`**:
  - h60 の trade を `select_non_overlapping_trades` で独立化する
  - 超過リターンを `paired_benchmark_returns` で求め、`cluster_bootstrap_ci`（signal_date クラスタ）で CI を出す
  - 判定: 独立観測 < 閾値なら `insufficient_sample`、CI の下限 > 0 なら `pass`、それ以外は `fail`
  - 閾値、件数、CI を合わせて記録する
- [ ] 注記: 実際に使った期間、価格調整の差（J-Quants は分割のみ、live は配当込み）、財務のウォームアップ、月の途中の IPO の補完件数、**パラメータ探索をしていないこと**、多重比較の注意
- [ ] 出力: `artifacts/inflection_historical_backtest.json`（全体）、`..._summary.json`（`_summary_only` を適用し、さらに銘柄コードを含むキーを除いたもの）
- [ ] CLI: `--fetch`（取得のみ）、`--start/--end`（取得期間、既定は「今日 − 2年」〜「今日 − 84日」）、`--cache-dir`（既定 `.data/jquants`）、`--signal-start`、`--min-independent`
**検証**: 受入条件 REQ-041 の 1〜5

#### Step 6: テスト・CI・文書
- [ ] `tests/test_jquants_history.py`: ページングの結合、キャッシュのスキップ、中断と再開、範囲外の記録、gitignore（`git check-ignore`）
- [ ] `tests/test_inflection_historical.py`: live との一致、先読みがないこと（未来の日足と財務を加えても結果が不変）、`free_12w` で84日未満の財務を除外すること、上場廃止銘柄の扱い、分割の調整、IPO の補完、ラグ比較で分類が変わる合成ケース、`kill_criterion` の3つの判定（pass / fail（0をまたぐ、全体が負）/ insufficient_sample）、summary に ticker が含まれないこと、合成キャッシュでの CLI の完走
- [ ] `test.yml` の mypy 対象に、新規の src と scripts を追加する
- [ ] `memo/project-overview.md` に、過去検証の位置付け（ローカル専用、評価のみ、出力先）を追記する
**検証**: `pytest tests/`、`ruff check src scripts tests`、mypy がすべて PASS する

#### Step 7: 実データでの取得と実行（ユーザーの確認後）
- [ ] **ユーザーに確認してから**、`set -a; . ./.env; set +a; python scripts/run_inflection_historical_backtest.py --fetch` を実行する（外部 API の呼び出し。約1,500回、5時間前後）。バックグラウンドで実行し、中断した場合は再実行で続きから取得する
- [ ] 取得後、実データで次を確かめる
  - (a) 計算した調整済み価格と、J-Quants の `AdjC` の比が、銘柄ごとに一定である
  - (b) 1306.T が含まれている
  - (c) fins の `DiscTime` の書式
- [ ] 評価を実行し、集計サマリー（銘柄・trade を含まない）を `memo/analysis/historical_backtest_YYYY-MM-DD.md` に書き写す
**検証**: レポートが生成され、`kill_criterion` と2つのラグの比較が記録されている

### 例外・エラーハンドリング方針
- 取得: 再試行は既存の client に任せる。範囲外の日は記録して続行し、それ以外の失敗は例外で止める（キャッシュは日単位で原子的に保存しているので、再実行で再開できる）
- 再現: 日足が252営業日に満たない銘柄は、live と同じく `_technical_features` の結果に従う（21日未満は除外）。財務がなければ live と同じく欠損として扱う
- 評価: キャッシュに必要な日足がない trade は、forward と同じく未完了として扱う。ベンチマークがない場合は停止する
- 秘密情報: API キーをログや出力に書かない。例外のメッセージに URL のクエリ（日付のみ）以外を含めない

### テスト/検証方針
- 自動テスト: `.venv/bin/python -m pytest tests/ -q`、`.venv/bin/ruff check src scripts tests`、`.venv/bin/mypy --ignore-missing-imports <test.yml の対象>`
- 手動確認観点（Step 7）:
  - [ ] 取得が中断しても、再実行で続きから再開される
  - [ ] 実際に取得できた期間の境界日がレポートに記録されている
  - [ ] 調整済み価格の比の検査が通る
  - [ ] `.data/` と `artifacts/` 以外に J-Quants の生データが書かれていない（`git status` がクリーン）

### リスクと対策
1. リスク: 実データの形式（`AdjFactor` の意味、`DiscTime` の書式、ETF の有無）が想定と異なる → 対策: Step 7 の (a)〜(c) で最初に確かめ、違えば評価を実行する前に修正する。単体テストは仕様書に基づく合成データで先に固める
2. リスク: live のリファクタリング（Step 2）で、本番の scan の出力が変わる → 対策: 既存の live テストを無変更で通すことを条件にし、REQ-037 の契約テスト（scan の出力 → 保存前検査 → 両 loader）も通す
3. リスク: 財務のウォームアップ不足や、12週ラグのため財務点が過小になり、結果が戦略の実力を過小評価する → 対策: 月ごとの前年同期比のカバー率を出し、開始日を引数で調整できるようにする。ただし評価前に開始日を決め、結果を見てから動かさない
4. リスク: 結果を見て閾値を調整したくなる（過剰最適化） → 対策: 本計画ではパラメータ探索をしない。レポートに明記する。探索は holdout 付きの別要件にする
5. リスク: J-Quants の生データが公開リポジトリに混入する → 対策: 保存先を `.data/` と `artifacts/` に限定し、テストで gitignore を検査する。memo に書き写すのは集計値だけにする

### 完了条件
- [ ] REQ-039 の受入条件 1〜5、REQ-040 の 1〜5、REQ-041 の 1〜5 を満たすテストが PASS する
- [ ] live の scan と forward の既存テストが無変更で PASS する（Step 1・2 のリファクタリングで挙動が変わっていない）
- [ ] `pytest`、`ruff`、`mypy` がすべて PASS する
- [ ] Step 7 は、ユーザーの確認後に実行する（本計画の自動実行の範囲外）
