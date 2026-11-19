# 実装要件書: 日次スキャンの欠測と、監視・通知状態の修正（2026-11-19）

> このファイルは create-plan の入力です。
> 入力: [prompt.md](prompt.md) → [inflection_scan_and_scoring_review_2026-11-19.md](../analysis/inflection_scan_and_scoring_review_2026-11-19.md)（以下「調査メモ」）。作成 2026-11-19、HEAD `7ca257b`。
> 調査メモの 3 項目と係数・閾値の判断は、現行コードと集計 JSON（`.harness/runtime/pull-review-20261119/`）で確認した。数値（学習集計の 286/130/0/0 件、52 週高値圏の 123 件・−1.30%・0.47 倍・q 0.325、20 営業日の分類別の表）はすべて JSON と一致した。Actions のログは手元から読めないため、タイムアウトの時刻は調査メモの記載に従う。
> 調査メモに無い問題として、REQ-001 の「ログが即時出力されない」、REQ-002（時間切れが別の失敗として通知される）、REQ-003 の Position Monitor への波及、REQ-004 の文書の誤りを追加した。
> 前の proposal.md（一次選別の測定 REQ-001〜003、実装済み）は git `92576d8` に残る。

---

## 順序

1. REQ-001 日次スキャンの停止箇所を特定して復旧する（最優先。他と独立）
2. REQ-002 時間切れを、失敗通知で他の失敗と区別する
3. REQ-003 日付をまたいだ監視でも、直近の取引日の欠測を検出する
4. REQ-004 ダイジェストの送信状態を Git に保存する

REQ-002〜004 は小さく、REQ-001 と並行してもよい。ただし 1 件ずつ実装・検証する。

## 全要件共通の制約

- スコア係数・EARLY 70 / WATCH 52・過熱除外・Q06 閾値（ticker 10 / signal date 5 / 最大業種比率 50%）を変更しない。
- 価格の品質基準（`MIN_PRICE_COVERAGE`・`MIN_LATEST_DATE_COVERAGE`）を緩めて保存を通さない。深掘り件数（25）と対照群の件数（25）も変えない（結果が変わるため）。
- 外部 API・実 Slack・実 snapshot の復号・永続キャッシュへの書込みをテストで行わない。検証は fake と一時ディレクトリで行う。Actions 上の確認は main で行う。
- 公開ログに ticker・会社名・URL・鍵を出さない。

---

## 要件一覧

### REQ-001: 日次スキャンの停止箇所を特定して復旧する

- **画面**: なし（`JP Inflection Shadow Scan` workflow のログと snapshot）
- **対象ファイル**: [inflection_live.py](../../src/screening/inflection_live.py)（`scan_japan_inflection` :786）、[run_inflection_shadow.py](../../scripts/run_inflection_shadow.py)（`main`）、[inflection_shadow.yml](../../.github/workflows/inflection_shadow.yml)（`timeout-minutes: 45` :29、scan step :71-79）
- **Before（現状）**:
  - 11/4〜11/18 の 11 回すべてで、scan step が 45 分 00〜09 秒でキャンセルされ、保存まで進まなかった。最後の snapshot は 11/02。9/14〜11/18 の 43 営業日のうち、snapshot があるのは 27 日。欠測 16 日のうち、9/28・10/5・10/8・10/13・10/19 の 5 日は散発的に欠け、原因は確認していない。
  - 処理は「銘柄一覧（J-Quants）→ 価格（yfinance、50 銘柄ずつ）→ 品質基準を満たすまで 180 秒・420 秒待って再取得 → EDINET 60 日分 → 財務（J-Quants、深掘り 25 件と対照群 25 件）」の順。段階ごとの開始・経過時間・件数を出していないので、どこで止まったか分からない。
  - J-Quants の呼出しは 12.2 秒以上の間隔を空ける（[jquants_v2_client.py:55](../../src/data/jquants_v2_client.py#L55)）。財務だけで 50 回以上（約 10 分以上）かかる。
  - **調査メモに無い問題**: ログは `print` で、`flush` も `PYTHONUNBUFFERED` も無い。Actions では標準出力がまとめて書き出されるため、キャンセルされたときに直前のログが残らないことがある。段階ログを足しても、このままでは止まった箇所が見えない可能性がある。
- **After（期待）**:
  - 段階 A（計測）: 各段階（銘柄一覧・価格の初回取得・各再取得と待機・EDINET・財務の評価）の開始・経過秒・処理件数が、その時点でログに出る（バッファに溜めない）。件数だけを出し、ticker や本文は出さない。
  - 段階 B（復旧）: 段階 A のログで遅い段階を特定し、その段階の待機・再試行を見直す。品質基準を満たした当日分の snapshot が、45 分以内に保存・commit される。 [要確認: 具体的な修正は原因の特定後に記述する。`verify-before-fix` で扱うことを推奨]
- **受入条件**:
  1. fake の client と provider で `scan_japan_inflection` を実行すると、段階ログがこの順に出て、ticker・会社名・URL が含まれない（テスト）。
  2. ログが即時に出る。`flush=True`、または workflow の `PYTHONUNBUFFERED=1` を静的テストで確認する。
  3. 段階 A を入れた main の run のログで、止まった段階が分かる（Actions 上で確認）。
  4. 段階 B の後、main の通常実行で当日の snapshot が commit される（Actions 上で確認）。
- **備考**:
  - [要確認: 時間切れの延長] `timeout-minutes` を延ばすのは、原因が直せない場合の最後の手段とするか。延ばす場合も上限を決める。
  - 散発的な 5 日の欠測も、同じ段階ログで原因を確認する。原因が別なら、別の要件にする。

### REQ-002: 時間切れを、失敗通知で他の失敗と区別する（調査メモに無い問題）

- **画面**: なし（失敗通知の Slack 文面）
- **対象ファイル**: [inflection_shadow.yml](../../.github/workflows/inflection_shadow.yml)（`failure_stage` :33、`FAILURE_STAGE` :125）、[check_workflow_health.py](../../scripts/check_workflow_health.py)（`STAGES` :24、`failure_alert` :60）。`notify-failure` を持つ他の 3 workflow（[position_monitor.yml](../../.github/workflows/position_monitor.yml) :25/:83、[forward_validation.yml](../../.github/workflows/forward_validation.yml) :29/:141/:198、[reliability_watchdog.yml](../../.github/workflows/reliability_watchdog.yml) :19/:102）も同じ作りなので揃える。
- **Before（現状）**: job がキャンセルされると、scan の出力に `failure_stage` が無いため、`'data_acquisition'` に置き換わる。11 回の時間切れは、Slack では `kind=data_acquisition`（データ取得の失敗）として届いたはず。API の失敗と時間切れを通知から区別できない。他の 3 workflow も、キャンセル時は `monitor`・`forward`・`watchdog` という汎用の段階になる。
- **After（期待）**: `needs.<job>.result == 'cancelled'` のとき、通知の kind が `cancelled`（時間切れ、または手動の取消）になる。GitHub の結果では、時間切れと手動の取消は区別できない。
- **受入条件**:
  1. `FAILURE_STAGE=cancelled` で `failure_alert` を呼ぶと、`kind=cancelled` の文面になる（テスト）。
  2. 4 workflow で、キャンセル時に `cancelled` が渡ることを静的テストで確認する。
  3. 既存の失敗の分類（`price_retry_exhausted` など）と既存テストは変わらない。

### REQ-003: 日付をまたいだ監視でも、直近の取引日の欠測を検出する

- **画面**: なし（Reliability Watchdog の Slack 通知）
- **対象ファイル**: [check_workflow_health.py](../../scripts/check_workflow_health.py)（`_expected_runs` :103、`watchdog_alerts` :124）、[session_gaps.py](../../src/data/session_gaps.py)（`expected_snapshot_missing` :35）
- **Before（現状）**: watchdog（cron は 20:10 JST）の 11/18 分は、11/19 の 04:22 JST に起動した。`_expected_runs` は「今日（JST）が取引日で、今日の予定時刻から 2 時間たったか」だけを見る。04:22 の時点では、11/19 の scan はまだ対象外になる。`expected_snapshot_missing` も、直近の確定取引日（11/18）が今日（11/19）でなければ `None` を返す。このため 11/18 の欠測を検出できなかった。
  - **調査メモに無い問題**: 同じ関数が Position Monitor（15:50 JST）も判定しているので、Monitor の欠測も同じ条件で見逃す。土曜の watchdog も、金曜の分を確認しない。
- **After（期待）**: workflow ごとに、「予定時刻から 2 時間の猶予が過ぎた、直近の取引日」を求める。その日の実行結果と snapshot（scan のみ）を照合する。翌日の早朝や週末に起動しても、前の取引日の欠測を検出する。同じ欠測は 1 回だけ通知する（既存の `deadman:{workflow}:{予定時刻}` の key と、送信済みの一覧で重複を防ぐ）。
- **受入条件**:
  1. now = 11/19 04:22 JST で 11/18 の snapshot と成功した run が無い場合、11/18 分の通知が 1 件出る（テスト）。
  2. 同じ key が送信済みなら、次の watchdog では再通知しない（テスト）。
  3. 既存のケース（当日 20:10 の起動、休日、初回 snapshot の前）の結果が変わらない。Position Monitor の判定も同じ規則で通る（テスト）。
- **備考**: 照合するのは直近の 1 取引日だけにする。過去の欠測をさかのぼって通知することはしない（調査メモの範囲）。

### REQ-004: ダイジェストの送信状態を Git に保存する

- **画面**: なし（Slack ダイジェストの再送）
- **対象ファイル**: [.gitignore](../../.gitignore)（`*.json` :15）、[inflection_shadow.yml](../../.github/workflows/inflection_shadow.yml)（`git add dashboard/data/inflection/` :87）、[tests/test_workflow_reliability.py](../../tests/test_workflow_reliability.py)。文書: [project-overview.md:70](../project-overview.md)、[docs/playbooks.md](../../docs/playbooks.md)（:38-45）、[actions-verification-runbook-2026-10-19.md](actions-verification-runbook-2026-10-19.md)（:39）。
- **Before（現状）**:
  - `*.json` の除外設定で、`dashboard/data/inflection/digest_state.json` は `git add` から外れる（`git check-ignore` で確認済み。履歴にも一度も入っていない）。runner は毎回この状態ファイルなしで始まる。
  - そのため、送信に失敗した日の `pending` は次の run に引き継がれない。前の取引日の再送（`_recover_pending_digests`、ISSUE-18）は、Actions 上では一度も働かない。同じ日の再実行も `skipped:legacy-no-state` になる。10 月の修正（ISSUE-06・16・18）は、ローカルのテストでしか確認されていなかった。
  - **調査メモに無い問題（文書）**: project-overview.md:70 に、10 月に削除したはずの記述「状態ファイルの初回保存失敗は run を失敗させます」が残っている（ISSUE-20 は英語の playbooks だけを直した）。runbook :39 は「`digest_state.json` は repo 内」と書いているが、実際は repo に無い。
- **After（期待）**: 除外設定に `!dashboard/data/inflection/digest_state.json` を加え、scan の Commit step で snapshot と一緒に commit される。中身は日付と `pending`/`succeeded` だけで、銘柄は含まない。文書は実際の動作と一致する。
- **受入条件**:
  1. `git check-ignore dashboard/data/inflection/digest_state.json` が「除外されない」になる（静的テスト。他の `*.json` の除外は維持）。
  2. fake の webhook で、1 回目は送信失敗（`pending` が残る）、2 回目は同じ状態ファイルから再送して `succeeded` になる。状態ファイルが一時 Git リポジトリの `git add dashboard/data/inflection/` で stage される（テスト）。
  3. 既存の通知テストが変わらずに PASS する。
  4. project-overview.md・playbooks.md・runbook の digest 状態の記述が、互いに、また現行の動作と矛盾しない（`grep` で確認）。
- **備考**: 状態ファイルは、次に成功した scan で初めて commit される。過去分を補う必要は無い（調査メモによると、今回の pull で追加された 8 日分はログ上すべて送信成功）。

---

## 完了済み・保留中

### 完了済み
- なし。

### 保留中（今回のスコープ外）
- **52 週高値圏の加点（+10 点）の検証**: スキャンの復旧（REQ-001）の後に行う。同じ日・同じ銘柄集合で、この加点だけを変え、上位 25 銘柄の入れ替わりと急騰前の発見率を比べる（調査メモの方針）。実装では、52 週高値圏と上場来高値圏が同じ加点を共有している（[inflection_live.py:216](../../src/screening/inflection_live.py#L216)）。上場来高値圏は 5 営業日で独立 3 件しか無いので、分けて評価できるかも確認する。
- **EARLY 70 / WATCH 52・過熱除外**: 維持する（調査メモの判断。20 営業日の 95% 区間が EARLY・WATCH ともゼロをまたぐ）。
- **60・120 営業日の成績**: 独立観測が 0 件。標本が溜まるのを待つ。
- 5・20 営業日で、成熟したのに価格不足で判定できない観測が各 4 件ある（`price_unavailable`）。昇格判定の保留の原因だが、銘柄の終了理由が分からないので、今回は扱わない。
