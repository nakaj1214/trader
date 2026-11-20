## 実装計画: スキャン・通知・監視・成績評価の不具合修正（REQ-001〜008）

> 入力: [proposal.md](proposal.md)（2026-11-19）。前の plan.md（REQ-001〜004、`ac17a90` で実装済み）は git `ac17a90` に残る。
> proposal の [要確認] 3 件は推奨案で進める。変える場合は、その Step の実装前に指示する。
> - REQ-001: `available_at` の無い旧 snapshot は `generated_at` で代用する。
> - REQ-003: watchdog だけで判定する（方式 b）。
> - REQ-008: 「接触の可能性」は接触として扱い、1 回だけ通知する。
>
> 1 Step ずつ実装・検証してから次へ進む。監視が止まっている REQ-008 を最初に行う。

### 目的
調査メモの 7 件（成績評価の買値・通知の再試行・監視の検出漏れなど）と、追加調査で見つけた保有銘柄の監視の停止（REQ-008）を直す。

### スコープ
- 含むもの: proposal の REQ-001〜008。REQ-008 は、引け後の実行が「session end is not yet confirmed」で必ず未完了になる問題も含む（受入条件 6「main の実行が成功する」を満たすのに必要）。
- 含まないもの:
  - [prompt.md](prompt.md) に保留した 3 件（うるう年の前年比・場中の手動実行・通知の取り消し）
  - `resend_digest=true` の送信内容、本番の履歴での影響件数の確認（proposal の保留中）
  - スコア係数・分類の閾値・Q06 の閾値、既存の暗号化 snapshot の書き換え

### 影響範囲（変更/追加予定ファイル）
- REQ-008: [position_exit.py](../../src/monitoring/position_exit.py)（`_minute_bars` の照合 :107-139、`evaluate_position` の鮮度判定 :179-186 と接触判定）、[run_position_monitor.py](../../scripts/run_position_monitor.py)（引け後の猶予 :352、引け後の未完了判定 :484、接触時刻 :489、通知本文 :542、過去の取引日の回収 :257）、文書 [docs/playbooks.md:30](../../docs/playbooks.md)・[project-overview.md:114](../project-overview.md)
- REQ-001: [run_inflection_shadow.py](../../scripts/run_inflection_shadow.py)（`persist_report` :193）、[inflection_forward.py](../../src/evaluation/inflection_forward.py)（`_load_inflection_rows` :63）、[inflection_learning.py](../../src/evaluation/inflection_learning.py)（`load_inflection_learning_observations` :94）、[inflection_backtest.py](../../src/evaluation/inflection_backtest.py)（`_evaluation_window` :126、`simulate_signal` :265）、[exit_rules.py](../../src/evaluation/exit_rules.py)（:161）、[rebuild_inflection_forward_validation.py](../../scripts/rebuild_inflection_forward_validation.py)（`entry_rule` の説明 :316・:338）
- REQ-002: [run_inflection_shadow.py](../../scripts/run_inflection_shadow.py)（`_deliver_digest` :264、`main` の呼出し :388）、文書 [docs/playbooks.md](../../docs/playbooks.md)（:53-56）・[project-overview.md:70](../project-overview.md)
- REQ-003・007: [check_workflow_health.py](../../scripts/check_workflow_health.py)（`STAGES` :24、`watchdog_alerts` の成功判定 :151）
- REQ-004: [inflection_learning.py](../../src/evaluation/inflection_learning.py)（`_independence_evidence` :528）
- REQ-005: [rebuild_inflection_forward_validation.py](../../scripts/rebuild_inflection_forward_validation.py)（`_persist_price_hashes` :131）
- REQ-006: [inflection_backtest.py](../../src/evaluation/inflection_backtest.py)（`_finalize_trade` :223-226、呼出し :386）、[exit_rules.py](../../src/evaluation/exit_rules.py)（呼出し :283）
- テスト（すべて既存ファイルに追加・修正）: test_position_exit.py、test_run_position_monitor.py、test_inflection_backtest.py、test_exit_rules.py、test_inflection_forward.py、test_inflection_learning.py、test_inflection_digest.py、test_shadow_health.py、test_workflow_health.py

### 実装ステップ

#### Step 1: 保有銘柄の監視で、1 分足の欠けを日足で補って評価を完了する（REQ-008）
- [ ] `_minute_bars` の「1 分足の合計と日足の完全一致」をやめる。日足は「値が有限・正で、高値・安値と整合し、1 分足の範囲を含む」ことだけを確認する。満たさない、または日足が無い場合は従来どおり `IncompleteQuoteError`。
- [ ] `evaluate_position` で、1 分足で観測できない値を日足で判定する。
  - 寄付: 日足の始値が、前日までの最高値による stop 以下なら `trailing_gap`（寄付の時刻で確定）。
  - 1 分足: 現行どおり、接触した分の時刻で確定。
  - 未観測の値: 1 分足で接触が無く、日足だけにある値のために時系列から接触を否定できないときは、「接触の可能性」として接触扱いにする（`exit_reason` は `daily_possible_touch`）。比べる水準は max(評価後の最高値, 日足の高値) × (1 − stop%)。
    - 日足の高値 > 1 分足の高値（高値の時刻が分からず、その後の安値との順序を決められない）、または日足の安値 < 1 分足の安値のとき: 日足の安値が水準以下なら「可能性」。
    - 日足の終値 ≠ 1 分足の最後の終値のとき: 日足の終値が水準以下なら「可能性」。
    - 例: 既存テストの価格列（09:01 に高値 120 円、09:59 に 100 円、stop 15%）で 09:01 の足だけが欠けると、水準 102 円 ≥ 日足の安値 100 円なので「可能性」になる。分足がそろっていれば、従来どおり 09:59 の接触として確定する。
- [ ] 引け後の未完了判定（:484）は、日足が無いときだけ「session end is not yet confirmed」にする。日足があれば上の規則で判定して `ok` にする。`as_of_at` は 1 分足の最後の時刻のままなので、次の実行が前日を確定した日足でもう一度判定する（`_recover_pending` が checkpoint の日を再判定する既存の仕組み）。
- [ ] 引け後 30 分の猶予内の実行（15:35・15:50）は場中と同じ扱い（`in_session=True`、run_position_monitor.py:352）なので、鮮度判定（20 分、position_exit.py:179-186）で 15:24 の最終分足が 15:50 には古いと判定される。大引け以降の実行で当日の有効な日足があるときは、最終分足にこの鮮度判定を適用しない（大引けまでの未観測分は日足で判定するため）。大引け前の古い分足は、従来どおり `StaleQuoteError` にする。
- [ ] 当日の接触の通知で、新しく接触したときの `triggered_at`（:489）を実行時刻でなく分足で確定した時刻（`touch_at`）にし、通知本文（:542）にもその時刻を出す。寄付での接触は寄付の時刻。日足だけで判定した「接触の可能性」は、時刻が不明と分かる表示にする。二重通知の防止（`last_notified_at`）は変えない。
- [ ] 過去の取引日の回収（`_recover_pending`）も同じ `evaluate_position` を通るので、同じ規則で完了することをテストで確認する。
- [ ] 既存テストのうち、照合の不一致で `IncompleteQuoteError` を期待しているもの（test_position_exit.py:338 の `opening`・`daily_high`・`daily_low`・`stop_bar`・`high_bar`）と、引け後の未完了を期待するもの（test_run_position_monitor.py:576）は、新しい規則の期待値（接触なし／接触の可能性／日足なしは未完了）に書き換える。
- [ ] 文書（playbooks.md:30、project-overview.md:114）の照合の説明を、新しい規則に合わせる。
**検証**: proposal REQ-008 の受入条件 1〜5 をテストで確認する（再現例の形: 1 分足 09:05〜15:24、日足と始値・終値・出来高が違う）。あわせて、15:50 の実行（最終分足 15:24）で評価が完了し、大引け前の古い分足は `StaleQuoteError` のままであること、高値の足だけが欠けたときに「接触の可能性」になること、分足で 12:34 に接触して 12:35 に実行したとき通知に 12:34 が出ることを確認する。`python -m pytest tests/test_position_exit.py tests/test_run_position_monitor.py tests/test_live_quote.py -q`

#### Step 2: 買値を、候補が利用可能になった後の始値にする（REQ-001）
- [ ] `persist_report` で、`storage` に保存時刻 `available_at`（UTC、タイムゾーン付き ISO）を入れる。snapshot は上書きしないので、初回の時刻が残る。
- [ ] snapshot から利用可能時刻を求める小さな関数を inflection_forward.py に置き、forward と learning の両方の読込で使う。`storage.available_at` → 無ければ `generated_at` → どちらも無ければ `None`（現行どおり市場日の翌取引日）。読めない値は `SnapshotLoadError`。候補・対照群の行に `available_at` を持たせる。
- [ ] `_evaluation_window` に `available_at` を渡し、買値の日を「市場日より後」かつ「寄付（XTKS の `session_open`）が `available_at` 以降の最初の取引日」以降に限る。`simulate_signal` と `simulate_exit_rule` は signal の `available_at` を渡す。無い signal（historical の backtest など）は現行どおり。
- [ ] TOPIX ETF との比較（`paired_benchmark_returns`）は取引の実際の買値日に合わせて比べるので、変更しない（テストで確認するだけ）。
- [ ] forward のレポートの `entry_rule` の説明（:316・:338）を、新しい規則に合わせる。
**検証**: proposal REQ-001 の受入条件 1〜4。`python -m pytest tests/test_inflection_backtest.py tests/test_exit_rules.py tests/test_inflection_forward.py tests/test_inflection_learning.py tests/test_shadow_health.py tests/test_inflection_digest.py -q`

#### Step 3: 通知の再試行では、保存済みの snapshot の内容を送る（REQ-002）
- [ ] `_deliver_digest` に復号鍵を渡す（`main` で取得済みのもの）。`resend=false` で、市場日が `pending` かつ snapshot を今回作っていないときは、`OUT_DIR/{市場日}.enc` を復号して送る。復号できない、または市場日が違うときは送らず `pending` のまま（`_recover_pending_digests` と同じ扱い）。
- [ ] 既存テストのうち、snapshot なしで「pending の再送」を確認しているもの（test_inflection_digest.py の `test_pending_digest_is_retried_and_success_is_not_resent`、`test_failed_digest_is_staged_and_retried_from_the_saved_state` など）は、先に snapshot を保存する形に直す。
- [ ] playbooks.md と project-overview.md の再試行の説明に「通常の再試行は保存済みの snapshot の内容を送る」を加える。
**検証**: proposal REQ-002 の受入条件 1〜5。`python -m pytest tests/test_inflection_digest.py tests/test_shadow_health.py -q`

#### Step 4: 休場日にずれ込んだ監視を、前の取引日の未実行として検出する（REQ-003）
- [ ] `watchdog_alerts` の成功判定で、position_monitor の run は、開始日（JST）が取引日のときだけ成功として数える。他の workflow は変えない。
**検証**: proposal REQ-003 の受入条件 1〜3。`python -m pytest tests/test_workflow_health.py tests/test_session_gaps.py -q`

#### Step 5: 業種が一部不明でも、業種の集中を判定する（REQ-004）
- [ ] `_independence_evidence` の集中率を「判明している業種のうち最多の件数 ÷ 全件数」にする。判明している業種が 0 件なら `None`。`sector33:` のラベルは対象外のまま。
**検証**: proposal REQ-004 の受入条件 1〜3。`python -m pytest tests/test_inflection_learning.py -q`

#### Step 6: 価格ハッシュを日付単位で更新する（REQ-005）
- [ ] `_persist_price_hashes` の保存を、銘柄 → 価格種別 → 日付の単位でマージする（今回取得した日付だけ上書き）。訂正の比較（`_changed_price_rows`）は変えない。
**検証**: proposal REQ-005 の受入条件 1〜2。`python -m pytest tests/test_inflection_forward.py tests/test_forward_prices.py -q`

#### Step 7: 売却後の騰落率を、取引所カレンダーの営業日で数える（REQ-006）
- [ ] `_finalize_trade` にカレンダー（準備済みのもの）を渡す。売却日より後の N 番目の取引日を決め、その日の終値が無ければ `None`。カレンダーが無い場合は現行どおり（取得できた終値を数える）。
- [ ] 呼出し元 2 か所（inflection_backtest.py:386、exit_rules.py:283）から、手元のカレンダーを渡す。
**検証**: proposal REQ-006 の受入条件 1〜3。`python -m pytest tests/test_inflection_backtest.py tests/test_exit_rules.py -q`

#### Step 8: 設定エラーを、失敗通知で設定エラーとして表示する（REQ-007）
- [ ] `STAGES` に `configuration` を加える。
**検証**: proposal REQ-007 の受入条件 1〜2。`python -m pytest tests/test_workflow_health.py -q`

### 例外・エラーハンドリング方針
- 監視（REQ-008）: 見逃しより誤報を選ぶ。日足が無い・不正なときは、従来どおり `incomplete` で checkpoint を進めない。
- snapshot の読込（REQ-001）: 利用可能時刻が読めない snapshot は、黙って飛ばさず `SnapshotLoadError` にする（既存の読込と同じ）。
- ダイジェスト（REQ-002）: 送れないときはスキャンを失敗させず、`pending` を残して次回に回す（既存の方針）。
- 公開ログに ticker・会社名・URL・鍵を出さない。

### テスト/検証方針
- 自動テスト: Step ごとに上記の pytest を実行する。最後に forward validation の workflow と同じ範囲（[forward_validation.yml](../../.github/workflows/forward_validation.yml) の pytest 対象）と、監視・通知のテスト（test_position_exit.py・test_run_position_monitor.py・test_inflection_digest.py・test_shadow_health.py・test_workflow_health.py）を 1 回ずつ実行する。
- テストは fake と一時ディレクトリだけを使う。外部 API・実 Slack・実 Sheets・実 snapshot の復号は使わない。
- 手動確認観点（main へ反映した後に Actions 上で確認）:
  - 保有銘柄がある日に、position monitor の 4 回の実行が成功する（REQ-008）。
  - 翌朝の実行で、前日の取引日の再判定が完了する（REQ-008）。
  - 次の scan で、新しい snapshot に `available_at` が入る（REQ-001。鍵のある環境で復号して確認）。

### リスクと対策
1. リスク: REQ-008 で「接触の可能性」が誤報になり、接触として固定される → 対策: 未観測の値（日足だけに現れる安値・終値）が stop 水準以下のときに限る。テストで、1 分足で観測済みの安値では誤報にならないことを確認する。
2. リスク: 9:20 の実行では、1 分足の遅れ（約 15 分）で当日の足がまだ無く `stale` になりうる（今回は扱わない既存の動作）→ 対策: main への反映後に Actions で 9:20 の結果を確認し、問題なら別の要件にする。
3. リスク: REQ-001 で、遅れて保存された過去の snapshot の買値日が変わり、成績が変わる → 対策: 意図した修正。forward と学習は毎回 snapshot から計算し直すので、次の定期実行で反映される。
4. リスク: REQ-005 で、欠けた日の翌日のハッシュは「前日の終値」で正規化しているため、欠けている間は翌日も訂正として記録される（既存の動作）→ 対策: 今回は変えない。受入条件の再現では、訂正の判定を欠けた日（11/5）で確認する。
5. リスク: 既存テストの期待値の書換え（REQ-002・008）で、守るべき既存の挙動まで消す → 対策: 書き換えるのは proposal の Before に当たる期待値だけにし、変更したテストを完了報告に列挙する。

### 完了条件
- [ ] REQ-001〜008 の受入条件のうち、テストで確認するものがすべて PASS する。
- [ ] 最終の pytest（forward validation の範囲と、監視・通知のテスト）が PASS する。
- [ ] 文書（playbooks.md・project-overview.md）が、REQ-002・008 の新しい動作と矛盾しない。
- [ ] Actions 上で確認する受入条件（REQ-008 の 6、REQ-001 の snapshot の時刻）は、main への反映後に確認する項目として完了報告に残す。
