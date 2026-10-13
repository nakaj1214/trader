## 実装計画: Stage 4C — 重複処理の削減と文書整合（REQ-068〜070）

### 目的
Q08 を「計測 → 重複が確認できた箇所だけ 1 run 内で共有」で実施し、B09 で現行仕様を説明する文書を現在の実装に合わせる。正常入力に対する投資結果・スコア・通知対象は 1 件も変えない（baseline-preserving）。Stage 4A/4B は完了済みの baseline として扱い、再設計しない。

### スコープ
- 含むもの: REQ-068（Position Monitor の ticker 単位の取得共有、Sheets 接続の run 内共有、評価系列の run 内共有）、REQ-069（現行仕様文書の更新）、REQ-070（Stage 4C 境界テスト）
- 含まないもの: Growth、Stage 4A/4B の再設計、Q06 閾値、スコア・閾値・重み、永続 cache・外部 cache・DB・multiprocessing・async・並列取得・memoization framework・新依存、過去レポートの書換え、Harness infrastructure、mypy 既知 31件の解消、archive・過去 snapshot の変更

### 調査結果（実装の前提）
- **[確認済]** Stage 4B は完了済み。完了報告 `.harness/reports/reliability-stage4b-2026-10-12.md` が存在し、通知状態・再送（`scripts/run_inflection_shadow.py`）、atomic write（`src/data/atomic_write.py`）、workflow の SHA 固定・lockfile 導入・PR secret 分離は dev5 コミットに含まれる。baseline はこの状態。
- **[確認済]** Position Monitor（[run_position_monitor.py](../../scripts/run_position_monitor.py) `run`）の保有行ループは、行ごとに `fetch_split_adjusted_history(ticker, purchase_date, entry_price)`（行 329）と `fetch_today_bars(ticker)`（行 336）を `_private_call` 経由で呼ぶ。行ごとに `_recover_pending`（履歴・checkpoint 依存、取引固有）と `evaluate_position`（entry・stop・購入日依存）を実行する。同一 ticker の複数 position は取得が重複する。
- **[確認済]** `fetch_split_adjusted_history`（[live_quote.py:92](../../src/data/live_quote.py)）は `yf.Ticker(ticker).history(start=entry_date, …)` を 1 回呼び、その frame から (a) 購入日以降の確定足 `prior`、(b) 購入日の split 補正済み entry、(c) `daily_bars=frame` を作る。provider 呼出しは `start` に依存するが、取引固有なのは entry 補正（`_later_split_factor`）と `prior` の切り出し・欠損判定（`purchase_date` 依存）で、frame 取得自体は ticker 単位。
- **[確認済]** `fetch_today_bars(ticker)` は `_now_jst()` を内部で取り、ticker ごとに独立した 1 分足を返す。呼出し側は `bars.attrs["daily_bar"] = daily` で**共有した DataFrame を書き換える**ため、共有する場合は position ごとに copy が必須。`fetch_today_bars` は想定外例外を再 raise する（Q07）。
- **[確認済]** Sheets（[sheets_client.py:37-49](../../src/data/sheets_client.py)）は `read_status`・`read_holdings`・`write_status` が呼出しごとに `_worksheet()`（認証＋`open_by_key`＋`worksheet`）を行う。`run()` は通常 3 回（holdings 0 件の早期終了時は `read_status`＋`read_holdings`＋`write_status([])`）。呼出し元は `run_position_monitor.py` のみ。既存テスト（`test_run_position_monitor.py`、`test_sheets_client.py`）は `scripts.run_position_monitor.read_status` などを patch しており、関数名・戻り値・失敗注入（`test_run_position_monitor.py:694`）は変えられない。
- **[確認済]** 評価（[inflection_report.py](../../src/evaluation/inflection_report.py) の horizon ループ）は 5 horizon × 通常/ストレス cost で `simulate_signals` と `_paired_trade_rows` を呼ぶ。`simulate_signal`（[inflection_backtest.py:240](../../src/evaluation/inflection_backtest.py)）は signal ごとに `_series(history, "Open"/"Close"/"High"/"Low")` を 4 回呼び（`pd.to_numeric`・tz 除去・重複/非正値検査・sort）、`_evaluation_window` でカレンダーの `normalize().drop_duplicates().sort_values()` も行う。同じ history に対して 10 回（5×2）繰り返される。`paired_benchmark_returns`（[inflection_forward.py:176](../../src/evaluation/inflection_forward.py)）も呼出しごとに benchmark の `_series` を 2 回作る。
- **[未確認]** 上記の重複回数・時間・メモリの実測（Step 1 で計測する）。ほか `inflection_forward.py`・`inflection_learning.py` に同種の再計算があるか（Step 1 で呼出し回数を計数して判断）。
- **[確認済]** B09 の対象文書: 現行仕様を説明する文書は [memo/project-overview.md](../project-overview.md)・[docs/playbooks.md](../../docs/playbooks.md)（Stage 4B 追記済み）・[.env.example](../../.env.example)（17 行）。`README` は存在しない。`project-overview.md` に既知の古い記述: 「専用鍵未設定時は `JQUANTS_API_KEY` を鍵素材に利用」（行 63）、「最低限の secret は `JQUANTS_API_KEY`」（行 93）、「標準セットアップ `pip install -e ".[dev]"`」（`uv.lock` 利用に未対応）、`position_monitor.yml` の時刻「9:03/12:35/15:35」（行 102、現行 9:20/12:50）。過去記録（`memo/analysis/`・`memo/research/`・`.harness/reports/` 過去分・`proposal_req*.md`・`plan_req*.md`）は変更しない。これらは現行 workflow・`.env.example`・コードと突き合わせて Step 6 で最終確定する。

### 影響範囲（変更/追加予定ファイル）
計測で重複が確認できた項目のみ変更する。効果が小さい項目は「変更不要」と報告する。
- [scripts/run_position_monitor.py](../../scripts/run_position_monitor.py): ticker 単位の市場データ取得の run 内共有（取引固有計算は position ごとに独立）
- [src/data/live_quote.py](../../src/data/live_quote.py): 履歴 frame の取得と購入日固有の切り出し・entry 補正の分離（必要な場合のみ。公開関数のシグネチャと戻り値は維持）
- [src/data/sheets_client.py](../../src/data/sheets_client.py): 1 run 内の spreadsheet 共有（context manager。外では従来どおり呼出しごとに接続）
- [src/evaluation/inflection_backtest.py](../../src/evaluation/inflection_backtest.py)・[inflection_report.py](../../src/evaluation/inflection_report.py)・[inflection_forward.py](../../src/evaluation/inflection_forward.py): 正規化済み系列の run 内共有（immutable）。計測で効果が小さければ変更しない
- [memo/project-overview.md](../project-overview.md)、[docs/playbooks.md](../../docs/playbooks.md): B09 の文書更新（`.env.example` は照合のみ。不一致は報告し、値は変更しない）
- テスト: `tests/test_run_position_monitor.py`、`tests/test_live_quote.py`、`tests/test_sheets_client.py`、`tests/test_inflection_backtest.py`、`tests/test_inflection_forward.py` を拡張。`tests/conftest.py` は変更しない
- 計測用の一時スクリプトと before/after の結果 JSON は `.harness/runtime/stage4c/`（transient）に置く。リポジトリに恒久的な計測ツールは追加しない

### 実装ステップ

実装順: 計測（before 固定）→ Monitor 取得共有 → Sheets 共有 → 評価系列共有 → 境界テスト整理 → B09 → 検証・報告。各 Step は「対象テスト → 直前までの回帰」を通してから次へ進む。

#### Step 1: 計測と before の固定（REQ-068）
- [ ] fixed-size synthetic/fake の計測ハーネス（一時スクリプト）を `.harness/runtime/stage4c/` に作る。外部通信は `tests/conftest.py` 相当の遮断を前提に、全 provider/Sheets を fake にする
- [ ] Monitor: N ticker × M position（同一 ticker に複数購入日を含む。例: 20 position、うち 6 ticker が 2〜4 位置）で、`fetch_split_adjusted_history`・`fetch_today_bars` の呼出し数（総数／ticker 別）、`gspread.authorize` と `open_by_key` の回数、read/write 回数を計数する
- [ ] 評価: 固定サイズ synthetic（例: 50 signal × 5 horizon × 2 cost）で `_series`、`_evaluation_window` のカレンダー正規化、`paired_benchmark_returns` の benchmark 正規化の呼出し回数を計数（`mock.patch` のラッパで計数。実行ロジックは変えない）。実行時間（`time.perf_counter`）と peak memory（`tracemalloc`）も記録
- [ ] **before の出力そのもの**を保存する: Monitor の全 rows・通知対象・書込み内容、評価レポート dict（JSON 化）、portfolio/learning 入力。Step 2 以降の完全一致比較の基準にする
- [ ] 計測結果から、変更する項目と「変更不要」とする項目を決め、以降の Step に反映する（効果が小さい項目は無理に変更しない）
**検証**: before の呼出し回数が具体的な数値で記録され、before 出力が保存されている。コード変更なし。

#### Step 2: Position Monitor の ticker 単位の取得共有（REQ-068 / 受入: 同一 ticker で取得 1 回）
- [ ] `run` 内にだけ存在する ticker 単位の共有（run のローカル dict。モジュールグローバルにしない）を作る。`fetch_today_bars(ticker)` は ticker ごとに 1 回。**成功値と失敗（例外）の両方を保存**し、同一 ticker の各 position は同じ結果を受ける（例外は同じ種類を再 raise。想定外例外は従来どおり行ごとの error 行になり、他 ticker の position に伝播しない）
- [ ] 共有した `bars` は position ごとに `copy()` して `attrs["daily_bar"]` などの書込みを各 position に閉じる（cross contamination 防止）
- [ ] 履歴 frame: `yf.Ticker(...).history(start=…)` は ticker ごとに 1 回（同一 ticker の最も早い購入日から）。購入日固有の切り出し（`prior_mask`）、`expected_dates` 欠損判定、split 補正済み entry（`_later_split_factor`）、`SplitAdjustedHistory` の組立は position ごとに独立して実行する。frame は共有 DataFrame を直接渡さず、position ごとに切り出して copy する。**同一入力で `fetch_split_adjusted_history` を単体で呼んだ場合と結果が一致すること**を保つ（Step 1 の before 出力と比較）
- [ ] 取得を共有できない条件（購入日が異なると結果が変わり得る箇所）が見つかった場合は、その箇所は共有せず報告する
- [ ] 気配時刻: 共有により同一 ticker の position が同じ `bars`（同一時刻）を使うことを、結果への影響（現状は position ごとに異なり得る）として報告。正常入力の結果が変わる場合は原因を調査して差を許容しない
**検証**: 同一 ticker 複数 position で provider 呼出しが 1 回。異なる購入日の rows が before と完全一致。ある ticker の失敗は同一 ticker の position だけに及び、他 ticker は影響なし。共有 DataFrame への書込みが他 position に波及しない。

#### Step 3: Sheets 接続の run 内共有（REQ-068）
- [ ] `sheets_client` に context manager（例: `shared_spreadsheet()`）を追加。内部で認証と `open_by_key` を最大 1 回行い、`with` ブロック内の `_worksheet(name)` はその spreadsheet から worksheet を取得する。ブロック外・未使用の呼出しは従来どおり（既存テスト・他の呼出しに影響なし）
- [ ] `run_position_monitor.run` は `with shared_spreadsheet():` で read/write を囲む。公開関数 `read_holdings`・`read_status`・`write_status` のシグネチャ・戻り値・`assert_production_writer`・batch 更新（`batch_update` の requests）・失敗時の例外種別は変更しない
- [ ] 接続の失敗はキャッシュしない（失敗後の再試行・認証エラーは従来どおり各呼出しに伝わる）。長寿命グローバル接続・pool は作らない
**検証**: 1 run の `gspread.authorize`／`open_by_key` が 3 → 1（holdings 0 件の経路も確認）。`test_sheets_client.py` の既存ケース無変更で PASS。認証エラー・書込み失敗・C07 writer 排他（`assert_production_writer`）の挙動が変わらない。書込み内容が before と一致。

#### Step 4: 評価系列・統計の run 内共有（REQ-068）
- [ ] Step 1 の計測で重複が有意な場合のみ実施。共有対象は正規化済みの**読み取り専用**の中間結果（例: 履歴ごとの `_series` 4 本、正規化済みカレンダー、benchmark の Open/Close）。`pd.Series` をそのまま共有せず、書込み不可（copy-on-use または `values` の read-only 化）にして後続の相互影響を防ぐ。浮動小数点の演算順序は変えない（同じ関数を同じ順序で呼ぶだけで、結果の再利用に限る）
- [ ] 共有の単位は 1 つのレポート構築（`inflection_report` の horizon ループ）内に限る。呼出し側で一度だけ準備し、既存関数にはオプション引数で渡す（既存の呼出し・シグネチャは後方互換のまま。引数省略時は従来動作）。モジュールレベルの cache や `lru_cache` は使わない
- [ ] 効果が小さい（呼出し削減が構造的に意味を持たない、またはメモリ増が上回る）場合は変更せず「変更不要」と報告する
**検証**: 共有後も `simulate_signals`・`paired_benchmark_returns` の出力（trade rows、benchmark 列、レポート dict）が before と完全一致（キー順・値）。`_series` の呼出し回数が構造的に減る。共有物を変更しようとしても例外になる／元の history が変化しない。

#### Step 5: Stage 4C 境界テスト（REQ-070）
- [ ] Step 2〜4 で追加した境界テストを一覧化し、受入条件の各項目に対応を付ける: 同一 ticker 複数 position で価格取得 1 回／異なる購入日の結果維持／cross contamination なし／provider 失敗の非伝播／Sheets 共有後の結果維持／最適化前後の評価結果一致
- [ ] before 出力との比較は、保存した期待値または「共有を使わない経路」との比較で durable なテストにする（`.harness/runtime/` のファイルに依存しない）
- [ ] B09 のために文書値を固定する大量テストは追加しない。workflow 時刻・secret 名などは、既存の `tests/test_workflow_reliability.py` の仕組みで自動照合が合理的な項目のみ
**検証**: 外部通信試行数 0、保存済み snapshot・archive 変更 0。

#### Step 6: B09 — 現行仕様文書の整合（REQ-069）
- [ ] 現行 workflow・`.env.example`・コードを正として、`memo/project-overview.md` と `docs/playbooks.md` を項目ごとに照合する: セットアップ（必須環境変数、`JQUANTS_PLAN`/`JQUANTS_DATA_DELAY_WEEKS` と validation、`SNAPSHOT_ENCRYPTION_KEY` の扱い、Slack、Google Sheets、EDINET key）、Actions（一覧・schedule・dispatch・concurrency・permissions・secret・`uv.lock`・Action SHA）、Forward Validation（PR の secret 分離・fork）、Position Monitor（実行時刻・stop 回収・checkpoint・incomplete・writer 制限・concurrency・通知状態）、通知（snapshot 生成→保存→Git 反映→Slack→通知状態→再送。exactly-once を保証しない）、Watchdog、provider 障害分類、atomic write（単一ファイルのみ。複数成果物の transaction ではない）、EDINET（コード接続済み／test 済み／live・historical・learning 利用／実 API 確認の有無）
- [ ] 各事実は `grep`／workflow・コードの Read で確認してから書く（推測を事実として書かない。確認できないものは「未確認」と書く）。機能状態は implemented／tested with fake・unit test／integration not verified／production enabled／production unverified を自然な日本語で区別する
- [ ] 更新は現行仕様を説明する文書の該当箇所に限り、最小 diff で行う（全面書換えしない）。過去記録は変更しない。判断に迷う文書は変更せず報告する
- [ ] 更新した各文書について「何が古かったか」「何に合わせたか」を表にまとめる（レポート用）。`.env.example` との不一致は報告のみ
**検証**: `git diff --stat` が現行仕様文書だけであること、過去記録（`memo/analysis/`・`memo/research/`・`.harness/reports/` の既存ファイル・`proposal_req*`・`plan_req*`）に今回の差分がないこと（作業開始前にユーザーが削除済みの `proposal_req*` / `plan_req*` の退避ファイルは今回の差分に含めない。git 履歴から復元可能）。文書記載の時刻・secret 名・環境変数が workflow・`.env.example` と一致。

#### Step 7: 全体検証と報告
- [ ] Q08 対象テスト → Stage 4C 境界テスト → Stage 4A 回帰 → Stage 4B 回帰 → 第1〜第3段階回帰 → 全テスト（約7分）→ coverage → ruff → mypy（既知 31件を内容で比較し新規 0）
- [ ] 外部通信試行数、`git diff --check`、task 対象の minimal diff guard、保存済み snapshot 差分、archive 差分、`uv.lock` 差分（なし）を確認
- [ ] Step 1 の before 出力と after を比較し、candidate／EARLY_CANDIDATE／classification／score／feature 値／stop 判定／notification 対象／outcome／portfolio／benchmark／learning 入力・出力が完全一致であることを確認。1 件でも差があれば原因を調査（結果差を許容しない）
- [ ] Harness 正式入口は、既存の `plan.md`/`proposal.md` 全面差替えによる停止かどうかを区別して報告（Harness infrastructure は変更しない）
- [ ] 独立レビュー（結果同等性、cross contamination、失敗の誤伝播、Sheets 排他・retry、文書の誤記・過剰主張）。重大な問題のみ修正して再検証
- [ ] `.harness/reports/reliability-stage4c-2026-10-12.md` に報告（形式は proposal の「完了報告」1〜9）。Growth へ進まず停止

### 例外・エラーハンドリング方針
- 共有は「取得結果（成功値または例外）を ticker ごとに run 内で 1 回だけ作り、position ごとに独立に消費する」。失敗は同一 ticker の position に一貫して伝え、他 ticker・他 position の固有計算には伝播させない。想定外例外（Q07）を握り潰さない。
- Sheets は共有に失敗しても従来の挙動（呼出しごとに接続）に戻れる構造にし、接続失敗をキャッシュしない。
- 共有する中間結果は読み取り専用（copy または書込み不可）。可変 DataFrame を position・horizon 間で共有しない。
- 公開ログに ticker・保有明細・URL・秘密情報を出さない（Q02/Q07 を維持）。

### テスト/検証方針
- 自動テスト: `uv run --offline pytest -q -p no:cacheprovider tests/<対象>` → 全テスト `uv run --offline pytest -q -p no:cacheprovider` → `uv run --offline ruff check src scripts tests` → `uv run --offline mypy src scripts`
- 結果同等性: Step 1 の before 出力と after の完全一致（`==`、キー順を含む JSON 比較）。構造指標（provider call 数・Sheets connection 数・`_series` 呼出し数）を before/after の数値で報告。実行時間・peak memory は参考値（小さな差を根拠にしない）。
- 手動確認観点: 文書の各事実が workflow・`.env.example`・コードと一致していること、過去記録が無変更であること。実 GitHub Actions・実 Slack・実 provider・実 Google Sheets は確認不能（報告で分離）。

### リスクと対策
1. リスク: 履歴 frame を ticker 単位で共有すると、`start` が異なる従来の取得と微妙に結果が変わる（欠損判定・`daily_bars` の範囲） → 対策: 共有 frame を購入日で切り出して同一にし、単体呼出しとの完全一致を比較テストで固定。一致しない箇所は共有しない。
2. リスク: 共有 `bars` の `attrs` や DataFrame を一方が書き換える → 対策: position ごとに copy。cross contamination テストを追加。
3. リスク: Sheets の spreadsheet 共有で retry・認証エラー・writer 排他の挙動が変わる → 対策: context manager 内に限定、失敗はキャッシュしない、公開関数のシグネチャ・batch 内容を変えない。既存テスト無変更で PASS。
4. リスク: 評価系列の共有で浮動小数点順序や dtype が変わり結果が微小に変わる → 対策: 同じ演算を同じ順序で行い、結果の再利用に限定。before 出力との完全一致比較。差が出れば採用しない。
5. リスク: 計測の結果、重複が小さく最適化の効果が薄い → 対策: 無理に変更せず「変更不要」と報告（依頼文が許容）。
6. リスク: 文書更新で未確認の事実を断定する、または過去記録を誤って書き換える → 対策: 各事実を workflow・コードで確認してから書く。差分を現行仕様文書に限定し、過去記録の差分 0 を確認。
7. リスク: 作業ツリーに過去ファイルの削除などの未コミット差分があり、task 対象の差分ガードが判定しにくい → 対策: 変更ファイルを列挙して task 対象を指定。Harness の既存停止理由は区別して報告。

### 完了条件
- [ ] REQ-068: before/after の provider call 数・Sheets connection 数が具体的な数値で報告され、重複が構造的に減った（または「変更不要」の根拠が示された）。正常入力の全指標が完全一致。禁止された最適化（永続 cache・並列・新依存等）を導入していない
- [ ] REQ-069: 現行仕様文書が現行コード・workflow・`.env.example` と一致し、機能状態が区別されている。exactly-once・複数成果物の transaction を主張していない。過去記録は無変更。更新した文書ごとの「古かった点／合わせた先」と、変更しなかった文書が報告されている
- [ ] REQ-070: 境界テストが受入条件に対応。外部通信試行数 0、保存済み snapshot・archive 変更 0
- [ ] 全テスト PASS、ruff PASS、mypy 新規エラー 0（既知 31件の内容差分なし）、`uv.lock` 差分なし、`git diff --check` と task 対象 minimal diff guard の結果が報告されている
- [ ] Stage 4A/4B・第1〜第3段階の回帰 PASS
- [ ] Stage 4C レポート作成後に停止（Growth 未着手）
