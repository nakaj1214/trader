## 実装計画: 日次スキャンの欠測と、監視・通知状態の修正（REQ-001〜004）

> 入力: [proposal.md](proposal.md)（2026-11-19）。前の plan.md（一次選別の測定 REQ-001〜003）は git `92576d8` に残る。
> 1 ステップずつ実装・検証してから次へ進む。REQ-001 の段階 B（遅い段階の修正）は原因が未確定なので、本計画では実装せず `verify-before-fix` に回す。

### 目的
11/4 から毎日止まっている日次スキャンについて、止まった段階をログで特定できるようにする（REQ-001 段階 A）。あわせて、時間切れの通知（REQ-002）、日付をまたいだ監視（REQ-003）、ダイジェスト状態の保存（REQ-004）を直し、同じ種類の障害を見逃さないようにする。

### スコープ
- 含むもの:
  - スキャンの段階ログと、ログの即時出力（REQ-001 段階 A）
  - 失敗通知で、キャンセルを `cancelled` として区別する（4 workflow）
  - watchdog が、猶予の過ぎた直近の取引日を照合する
  - `digest_state.json` を Git の保存対象にし、文書 3 か所を実際の動作に合わせる
- 含まないもの:
  - REQ-001 段階 B（遅い段階の待機・再試行の見直し）。段階 A のログを Actions で取ってから `verify-before-fix` で扱う。
  - `timeout-minutes` の変更（[要確認] proposal REQ-001 備考）
  - 52 週高値圏の加点の検証、係数・EARLY/WATCH 閾値・品質基準・深掘り件数・対照群件数の変更
  - 過去の欠測（9/28 など）をさかのぼって通知すること

### 影響範囲（変更/追加予定ファイル）
- [src/screening/inflection_live.py](../../src/screening/inflection_live.py): `scan_japan_inflection`（:786）に段階ログを追加する。`select_and_evaluate`（:698）は historical の backtest と共有なので触らない（ログが大量に出るため）。
- [.github/workflows/inflection_shadow.yml](../../.github/workflows/inflection_shadow.yml): scan step（:71-79）の env に `PYTHONUNBUFFERED: '1'`、notify-failure の `FAILURE_STAGE`（:125）に cancelled の分岐。
- [.github/workflows/position_monitor.yml](../../.github/workflows/position_monitor.yml) :83、[reliability_watchdog.yml](../../.github/workflows/reliability_watchdog.yml) :102、[forward_validation.yml](../../.github/workflows/forward_validation.yml) :198: `FAILURE_STAGE` に cancelled の分岐。
- [scripts/check_workflow_health.py](../../scripts/check_workflow_health.py): `STAGES`（:24）に `cancelled`。`_expected_runs`（:103）を「猶予の過ぎた直近の取引日」に変更。`watchdog_alerts`（:124）は、その取引日を snapshot の照合に渡す。
- [src/data/session_gaps.py](../../src/data/session_gaps.py): `expected_snapshot_missing`（:35）は、`now` から日付を求めず、watchdog が求めた取引日を受け取る。呼出し元は watchdog とテストだけ（grep で確認済み）。`latest_settled_session` は forward の再構築（[rebuild_inflection_forward_validation.py:161](../../scripts/rebuild_inflection_forward_validation.py#L161)）も使うので変えない。
- [.gitignore](../../.gitignore): `*.json`（:15）の後に `!dashboard/data/inflection/digest_state.json`。
- 文書: [project-overview.md:70](../project-overview.md)、[docs/playbooks.md](../../docs/playbooks.md)（:37-38）、[actions-verification-runbook-2026-10-19.md:39](actions-verification-runbook-2026-10-19.md)。
- テスト（既存ファイルに追加）: `tests/test_inflection_live.py`、`tests/test_workflow_reliability.py`、`tests/test_workflow_health.py`、`tests/test_session_gaps.py`。

### 実装ステップ

#### Step 1: スキャンの段階ログ（REQ-001 段階 A）
- [ ] `scan_japan_inflection` の開始時に `time.monotonic()` を取り、各段階の開始と終了で 1 行ずつ出す。形式は `SCAN_STAGE: stage=<名前> event=start|end elapsed=<開始からの秒> <件数>=<n>`、`print(..., flush=True)`。
  - 段階: `master`（終了時に universe 件数）→ `prices`（初回取得。終了時に取得件数）→ `price_retry`（再取得ごと。開始時に対象件数、終了時に取得件数。待機は既存の `DATA_HEALTH_RETRY` 行が出す）→ `edinet`（キーがあるとき。終了時に件数、または unavailable）→ `selection`（終了時に深掘り件数・対照群件数）。
  - 出すのは件数と秒だけ。ticker・会社名・URL・例外の本文は出さない。
- [ ] 既存の `DATA_HEALTH_RETRY` / `DATA_HEALTH_RECOVERED` の行にも `flush=True` を付ける。
- [ ] `inflection_shadow.yml` の scan step の env に `PYTHONUNBUFFERED: '1'` を加える（`run_inflection_shadow.py` を含め、step 内の出力をすべて即時にする）。
- [ ] テスト（`tests/test_inflection_live.py`）: 既存の fake（`FakeJQuantsClient`、`fetch_price_data` の patch、:455 付近の書き方）でスキャンし、`capsys` で `SCAN_STAGE` の行が master → prices → selection の順に出ること、ticker（例 `1111.T`）と会社名が出ないことを確認する。再取得するケース（`test_scan_retries_only_stale_tickers_and_recovers` の条件）で `price_retry` が出ることも確認する。
- [ ] テスト（`tests/test_workflow_reliability.py`）: scan step の env の `PYTHONUNBUFFERED` が `'1'` であること。

**検証**: `.venv/bin/python -m pytest -q tests/test_inflection_live.py tests/test_workflow_reliability.py` が PASS。既存の scan のテストは変えない。

#### Step 2: 時間切れを `cancelled` として通知する（REQ-002）
- [ ] `check_workflow_health.py` の `STAGES` に `"cancelled"` を加える（未知の段階は `workflow_failure` になるため）。
- [ ] 4 workflow の notify-failure の `FAILURE_STAGE` の先頭に、キャンセルの分岐を置く。
  - `inflection_shadow.yml`: `needs.scan.result == 'cancelled' && 'cancelled' || <現行の式>`
  - `position_monitor.yml`: `needs.monitor.result == 'cancelled' && 'cancelled' || ...`
  - `reliability_watchdog.yml`: `needs.watchdog.result == 'cancelled' && 'cancelled' || ...`
  - `forward_validation.yml`: `(needs.validate.result == 'cancelled' || needs.persist-price-hashes.result == 'cancelled') && 'cancelled' || ...`
- [ ] `failure_alert`（:69）: 段階が `cancelled` のときは、`retry_exhausted=true` があっても本文の kind を `price_retry_exhausted` に上書きしない（scan の通知ジョブは結果にかかわらず再試行情報も渡すため）。
- [ ] テスト（`tests/test_workflow_health.py`）: `FAILURE_STAGE=cancelled` の `failure_alert` が `kind=cancelled` になる。`FAILURE_STAGE=cancelled` と `retry_exhausted=true` を一緒に渡しても `kind=cancelled` になる。キャンセルでない再試行上限到達は、従来どおり `kind=price_retry_exhausted`（既存の `test_rerun_attempts_share_one_failure_identity_and_keep_retry_details` を変えずに PASS させる）。
- [ ] テスト（`tests/test_workflow_reliability.py`）: notify-failure を持つ 4 workflow すべてで、`FAILURE_STAGE` に、依存 job の `result == 'cancelled'` から `'cancelled'` への分岐があること。

**検証**: `.venv/bin/python -m pytest -q tests/test_workflow_health.py tests/test_workflow_reliability.py` が PASS。`price_retry_exhausted` の既存テストは変えない。

> Step 1・2 は一緒に main に入れる。スキャンは現在毎日時間切れになっているので、次の run で段階ログと `kind=cancelled` の両方を確認でき、段階 B の証拠になる。

#### Step 3: 段階 B の扱い（実装しない）
- [ ] Step 1・2 が main に入った後の run のログで、最後に `event=start` が出て、`end` が出ていない段階を特定する。
- [ ] その段階を入力にして `verify-before-fix` を行う（別の計画）。`timeout-minutes` の延長はユーザーの判断を待つ。

**検証**: 止まった段階がログから 1 つに決まる（Actions 上。ユーザーがログを共有）。

#### Step 4: watchdog が、猶予の過ぎた直近の取引日を照合する（REQ-003）
- [ ] `_expected_runs(now)`: Position Monitor（15:50）と scan（16:40）について、今日以前の TSE 取引日のうち「予定時刻 + 2 時間 ≤ now」となる最新の日の予定時刻を返す。取引日は `session_gaps.sessions_between(today - 14 日, today)` で得る。forward（日曜 09:30）は変えない。
- [ ] `expected_snapshot_missing(snapshot_dir, session)`: 受け取った取引日の snapshot が無ければ、その日付を返す。`watchdog_alerts` は `expected.date()` を渡す。
- [ ] `watchdog_alerts` の実行の照合（:135 の `expected <= started <= now`）を、対象の取引日に属する実行だけに絞る。範囲は「対象日の予定時刻 ≤ 開始 < 対象日の次の平日の最初の cron 時刻」（Position Monitor は 09:20、scan は 16:40。[position_monitor.yml:5-9](../../.github/workflows/position_monitor.yml#L5-L9)）。上限は東証の取引日ではなく平日で決める。cron は月〜金に設定されていて、平日の休場日（例 11/3）にも動くため、取引日で区切ると休場日の実行が前の取引日の分に数えられてしまう。監視の対象日は、これまでどおり東証の取引日から選ぶ。成功の判定と、通知済みの失敗による抑止（`known_failure`）の両方にこの範囲を使う。翌日の成功や失敗通知で、前日の欠測が隠れないようにするため。
- [ ] 通知の key は既存の `deadman:{workflow}:{予定時刻}` のまま。同じ欠測を翌朝・週末に見ても key が同じなので、`notify_once` の送信済み一覧で 2 回目は送らない。既存の「原因別の失敗通知を送り済みなら deadman を出さない」もそのまま。
- [ ] 新しいテスト（`tests/test_workflow_health.py`）:
  - now = 2026-11-19 04:22 JST、11/18 の snapshot と run が無い → 11/18 16:40 の scan について通知 1 件（Position Monitor も 11/18 15:50 について 1 件）。
  - 2026-11-18 20:10 と 2026-11-19 04:22 の 2 回の watchdog で、11/18 分の key が一致する（→ 2 回目は `notify_once` が送らない）。
  - 土曜（2026-10-03 20:10）は、金曜（10/02）の予定時刻を照合する。
  - now = 2026-11-19 16:00 JST、11/18 は Position Monitor が未実行で、11/19 09:20 の run だけが成功 → 11/18 15:50 について通知 1 件（翌日の成功が前日を隠さない）。
  - 同じ条件で、11/19 の失敗 run の `failure:` key が送信済みでも、11/18 の通知は抑止されない。
  - 11/18 分の run が遅れて 11/19 04:00 に始まり成功した場合は、11/18 の成功として扱い、通知しない。
  - 平日の休場日をまたぐ場合: now = 2026-11-03（火・休場日）20:10 JST、11/2（月）の Position Monitor は未実行で、11/3 09:20 の run だけが成功 → 11/2 15:50 について通知 1 件。11/3 の失敗 run の `failure:` key だけが送信済みの場合も、11/2 の通知は抑止されない。
  - 11/2 分の run が遅れて 11/3 04:00 に始まり成功した場合は、11/2 の成功として扱い、通知しない。
- [ ] **既存テストのうち、旧ルール（今日の分だけ見る）を前提にした 4 件は、新ルールに合わせて assertion を変える。** これは proposal REQ-003 が判定ルール自体を変えるためで、実装に合わせるための書換えではない。守る性質「実行中の当日と、休日そのものを欠測としない」は、各テストに assertion として残す。
  - `test_weekends_and_exchange_holidays_do_not_require_a_monitor_or_scan`（休日の起動 → 前の取引日の予定時刻になる。休日の日付が予定時刻にならないことを確認）
  - `test_scheduler_grace_avoids_alerting_before_a_run_is_expected`（10/08 16:00 → 予定は 10/07。10/08 の予定は入らない）
  - `tests/test_session_gaps.py` の `test_snapshot_deadman_ignores_preclose_weekends_and_holidays` と `test_watchdog_requires_an_expected_snapshot_even_when_none_has_ever_existed`（引数が取引日になる。初回 snapshot の前でも、その 1 日だけを返し、過去の欠測を並べないことを確認）
- [ ] proposal REQ-003 の受入条件 3「休日 … の結果が変わらない」は、上の性質（休日そのものを欠測にしない）として扱う。休日に前の取引日を照合するのは、REQ-003 の目的どおりの変化。

**検証**: `.venv/bin/python -m pytest -q tests/test_workflow_health.py tests/test_session_gaps.py` が PASS。`rebuild_inflection_forward_validation.py` 側のテストも変わらない。

#### Step 5: ダイジェスト状態を Git に保存する（REQ-004）
- [ ] `.gitignore` の `*.json` の後に `!dashboard/data/inflection/digest_state.json` を加える。workflow の `git add dashboard/data/inflection/`（:87）はそのままでよい。
- [ ] テスト（`tests/test_workflow_reliability.py`）: `git check-ignore --no-index -q dashboard/data/inflection/digest_state.json` が終了コード 1（除外されない）、同じ場所の別の `*.json` は 0（除外されたまま）。`git add` も同じ除外規則を使うので、Commit step で stage されることの確認になる。
- [ ] 文書の修正:
  - project-overview.md:70: 「状態ファイルの初回保存失敗はrunを失敗させます」を削除し、状態の異常は通知だけを止め、snapshot の保存は続ける（best-effort）と書く。状態ファイルが snapshot と一緒に commit されることを書き足す。
  - playbooks.md:37-38: 状態ファイルが scan job の Commit step で snapshot と一緒に commit され、次の run に引き継がれることを 1 文足す。
  - runbook:39: 「`digest_state.json` は repo 内」を、この修正以降は repo に commit される、という記述に直す。
- [ ] テスト（`tests/test_inflection_digest.py`）: proposal の受入条件 2。既存の再送テスト（:289、:643）は `pending` を用意して始めるので、送信失敗から通して確認する。
  1. 一時ディレクトリで `git init` し、リポジトリの `.gitignore` を複製する。
  2. `send_daily_digest` を失敗する fake にして `_deliver_digest` を呼び、一時ディレクトリの `dashboard/data/inflection/digest_state.json` に `pending` が残ることを確認する。
  3. 本番の Commit step と同じ `git add dashboard/data/inflection/` を実行し、`git ls-files --cached` に `digest_state.json` が入ることを確認する。
  4. その状態ファイルを使い、送信が成功する fake で再送して `succeeded` になることを確認する。
  - git は外部通信をしない。conftest は socket と curl_cffi だけを止めるので、子プロセスの git は使える。

**検証**: `.venv/bin/python -m pytest -q tests/test_workflow_reliability.py tests/test_inflection_digest.py` が PASS。`grep -rn "digest_state" docs memo/project-overview.md memo/implement/actions-verification-runbook-2026-10-19.md` の記述が互いに矛盾しない。

### 例外・エラーハンドリング方針
- 段階ログは `print` だけで、失敗してもスキャンを止める処理は加えない。既存の例外の流れ（`PriceDataRetryExhausted`、`_publish_failure_stage`）は変えない。
- watchdog の取引日の計算で、カレンダーに 14 日以内の取引日が無い場合は、その workflow を照合しない（現行で休日に照合しないのと同じ扱い）。
- `digest_state.json` の読み書きの失敗時の扱い（best-effort）は変えない。

### テスト/検証方針
- 自動テスト: 各 Step の対象テストを `.venv/bin/python -m pytest -q <files>` で実行する。最後に 1 回、`.venv/bin/python -m pytest -q` と `ruff check` を実行する。
- 手動確認観点（main に入れた後、Actions 上。ユーザー作業）:
  - [ ] scan のログに `SCAN_STAGE` の行が順に出て、キャンセル直前の段階が分かる。
  - [ ] 時間切れの run の失敗通知が `kind=cancelled` になる。
  - [ ] 次の watchdog（翌朝に遅れて起動しても）が、前の取引日の欠測を 1 回だけ通知する。
  - [ ] スキャンが復旧した後の最初の成功で、`git ls-files dashboard/data/inflection/digest_state.json` にファイルが出る。

### リスクと対策
1. リスク: 段階ログから ticker などが公開ログに漏れる → 対策: 件数と秒だけを出す形にし、テストで ticker・会社名が無いことを確認する。
2. リスク: REQ-003 で既存テスト 4 件の assertion を変えるため、意図しない挙動の変化が紛れる → 対策: 変える assertion を上の 4 件に限り、「実行中の当日と休日を欠測としない」性質を各テストに残す。差分で、それ以外のテストに変更が無いことを確認する。
3. リスク: 週末や翌朝の watchdog が同じ欠測を再通知する → 対策: key を予定時刻で固定し、`notify_once` の送信済み一覧で防ぐ。送信済み一覧は actions/cache に依存するので、その復元に失敗すると重複し得る（現行と同じ制約。新たな対策はしない）。
4. リスク: `digest_state.json` の commit が他の自動 commit と衝突する → 対策: 書くのは scan job だけで、concurrency group で直列化され、Commit step は `git pull --rebase` してから push する。forward の自動 commit は別のファイル（価格ハッシュ）。
5. リスク: 段階 A を入れても、止まった段階が 1 つに決まらない（例: 価格の取得中に止まり、その中の遅れ方が分からない）→ 対策: 段階 B の `verify-before-fix` で、その段階に絞って細かいログを追加する。最初から全段階を細かく計測はしない。

### 完了条件
- [ ] REQ-001 段階 A: fake のスキャンで段階ログが順に出て、ticker・会社名・URL が含まれない。scan step に `PYTHONUNBUFFERED=1` がある（静的テスト）。
- [ ] REQ-002: `FAILURE_STAGE=cancelled` で `kind=cancelled` になる（`retry_exhausted=true` が一緒でも）。4 workflow でキャンセル時に `cancelled` が渡る（静的テスト）。既存の分類は不変。
- [ ] REQ-003: 11/19 04:22 JST の watchdog が 11/18 の欠測を 1 件通知し、同じ key は再送しない。土曜は金曜を照合する。翌日（平日の休場日を含む）の成功や失敗通知が前日の欠測を隠さない。実行中の当日と休日は欠測にしない。
- [ ] REQ-004: `digest_state.json` が除外されず、他の `*.json` は除外されたまま。送信失敗で残った状態ファイルが一時リポジトリの `git add` で stage され、その状態での再送が `succeeded` になる。既存の通知テストが PASS。文書 3 か所が一致する。
- [ ] 全テストと ruff が PASS。
- [ ] Actions 上の確認（上の手動確認観点）は、ユーザーが main で確認する。REQ-001 段階 B と、スキャンの復旧（proposal REQ-001 受入条件 4）は、この計画の完了条件に含めない。
