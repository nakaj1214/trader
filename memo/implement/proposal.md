# 実装要件書: スキャン・通知・監視・成績評価の不具合修正（2026-11-19）

> このファイルは create-plan の入力です。
> 入力: [issues-2026-11-19.md](issues-2026-11-19.md)（prompt.md の代わり。以下「調査メモ」）。作成 2026-11-19、HEAD `ac17a90`（作業ツリーの未コミット変更は調査メモのみ）。
> 調査メモの 7 件は、すべて現行コードで原因の箇所を確認した。合成データでの再現結果は調査メモの記載に従う。本番の履歴で起きたかどうかと影響件数は未確認（保留中を参照）。
> REQ-008 は調査メモに無い問題で、追加調査で見つけた（Yahoo の実データで確認）。同じ調査で見つけた低優先の 3 件は、[prompt.md](prompt.md) に保留として記録した。
> 前の proposal.md（日次スキャンの欠測と監視・通知 REQ-001〜004、`ac17a90` で実装済み）は git `ac17a90` に残る。

---

## 順序

1. REQ-001 買値を、候補が利用可能になった後の始値にする（高）
2. REQ-002 通知の再試行では、保存済みの snapshot の内容を送る（高）
3. REQ-003 休場日にずれ込んだ保有銘柄監視を、前の取引日の未実行として検出する（高）
4. REQ-004 業種が一部不明でも、業種の集中を判定する（中）
5. REQ-005 価格ハッシュを日付単位で更新し、復旧時の訂正を検出する（中）
6. REQ-006 売却後の騰落率を、取引所カレンダーの営業日で数える（中）
7. REQ-007 設定エラーを、失敗通知で設定エラーとして表示する（低）
8. REQ-008 保有銘柄の監視で、1 分足が寄付・大引けを欠いても評価を完了する（高。監視が止まっているので、最初に着手してもよい）

8 件は互いに独立している（REQ-001 と REQ-006 は同じ [inflection_backtest.py](../../src/evaluation/inflection_backtest.py) を、REQ-003 と REQ-008 は保有銘柄の監視を触るが、直す箇所が別）。1 件ずつ実装・検証する。

## 全要件共通の制約

- スコア係数・分類の閾値・Q06 の閾値（ticker 10 / signal date 5 / 最大業種比率 50%）を変更しない。
- 既存の暗号化 snapshot（`dashboard/data/inflection/v3/*.enc`）を書き換えない。新しい項目を持たない旧 snapshot も、今まで通り読み込めること。
- 外部 API・実 Slack・実 Google Sheets・実 snapshot の復号・永続キャッシュへの書込みをテストで行わない。fake と一時ディレクトリで検証する。
- 公開ログに ticker・会社名・URL・鍵を出さない。
- 成績が変わる修正（REQ-001・004・006）で、過去の出力ファイルを手で直さない。forward validation と学習は毎回 snapshot から計算し直すので、次の定期実行で反映される。

---

## 要件一覧

### REQ-001: 買値を、候補が利用可能になった後の始値にする

- **画面**: なし（フォワード検証と学習の成績）
- **対象ファイル**: [run_inflection_shadow.py](../../scripts/run_inflection_shadow.py)（`persist_report` :193-228）、[inflection_forward.py](../../src/evaluation/inflection_forward.py)（候補の読込 :138）、[inflection_learning.py](../../src/evaluation/inflection_learning.py)（学習データの読込 :190、`simulate_signal` の呼出し :328）、[inflection_backtest.py](../../src/evaluation/inflection_backtest.py)（`_evaluation_window` :126、買値の決定 :135）。[exit_rules.py](../../src/evaluation/exit_rules.py)（:161）も同じ `_evaluation_window` を使う。
- **Before（現状）**:
  - snapshot が持つ時刻は、市場日（`latest_price_date`）と scan の開始時刻（`generated_at`）だけ。評価は市場日を signal_date とし、「市場日より後で最初の始値」を買値にする（:135 `opens.index > signal_date`）。
  - scan の検証は、「`generated_at` の時点で最新の取引日」と市場日が一致すれば通す（[market_calendar.py:14](../../src/data/market_calendar.py#L14)。取引日の大引け前なら前の取引日を返す）。このため 11/19 11:00 JST に動いた遅延 scan は 11/18 分として保存され、すでに過ぎた 11/19 9:00 の始値（110 円）で買ったことになる。
  - scan の cron は平日 16:40 JST。GitHub の schedule は遅れることがある（前回、watchdog が翌日 04:22 に起動した例がある）。
- **After（期待）**:
  - 新しい snapshot は、市場日とは別に、初回保存の時刻（以下 `available_at`、タイムゾーン付き）を持つ。snapshot は上書きしない（`overwrite=False`）ので、2 回目以降の scan で時刻は変わらない。
  - 買値は、`available_at` より後に寄り付く最初の取引日の始値にする。寄付の時刻は取引所カレンダー（XTKS）の開始時刻を使う。再現例（11/19 11:00 保存）では 11/20 の始値になる。
  - 同じ snapshot の候補・対照群は同じ規則で買値を決める。超過収益の比較対象（TOPIX ETF）も候補と同じ買値日にそろえる（現在の比較の作りは実装時に確認する）。
  - 通常の 16:40 実行では、買値は現行と同じ（翌取引日の始値）。
- **受入条件**:
  1. 市場日 11/18・`available_at` 11/19 11:00 JST の候補で、entry_date が 11/20、買値が 11/20 の始値になる（テスト）。
  2. 市場日 11/18・`available_at` 11/18 17:30 JST の候補では、entry_date が 11/19 で、現行と同じ結果になる（テスト）。
  3. `persist_report` が新規の snapshot に保存時刻を入れる。既存の snapshot がある市場日では、snapshot が変わらない（テスト）。
  4. `available_at` を持たない旧 snapshot が読み込め、既存のテスト（test_inflection_forward.py・test_inflection_learning.py・test_inflection_backtest.py・test_exit_rules.py）が通る。
- **備考**:
  - [要確認: 旧 snapshot の扱い] `available_at` を持たない旧 snapshot は、`generated_at`（scan の開始時刻）で代用することを推奨する。全 snapshot に必ずあり、遅延 scan のほとんどを拾える。ただし保存は開始の最大 45 分後なので、8:15〜9:00 に始まった遅延 scan は見逃しうる。代用しない場合は、旧 snapshot は現行どおり（市場日の翌取引日の始値）になる。

### REQ-002: 通知の再試行では、保存済みの snapshot の内容を送る

- **画面**: なし（Slack の日次ダイジェスト）
- **対象ファイル**: [run_inflection_shadow.py](../../scripts/run_inflection_shadow.py)（snapshot 保存 :226、`_deliver_digest` :264、呼出し :388）。文書: [docs/playbooks.md](../../docs/playbooks.md)（:53-56）、[project-overview.md:70](../project-overview.md)。
- **Before（現状）**: 同じ市場日の 2 回目以降の scan では snapshot は作られない（`overwrite=False`）。それでも `_deliver_digest` は今回の scan の report を送る。初回に候補 A を保存し、送信に失敗して `pending` が残る。同じ市場日の再 scan で候補 B が選ばれると、B が送られて `succeeded` になる。snapshot には A が残るので、実際に通知した内容を後から再現できない。
- **After（期待）**: 通常の実行（`resend=false`）で、その市場日が `pending` かつ snapshot が今回作られたものでない場合、保存済みの snapshot を復号して、その内容でダイジェストを送る。送信が成功したら `succeeded` にする。snapshot を復号できない、または市場日が違う場合は送らず、`pending` のまま残す（`_recover_pending_digests` と同じ扱い）。
- **受入条件**:
  1. 1 回目の scan で A を保存して送信失敗、2 回目の scan で B が選ばれたとき、送られる内容が A で、状態が `succeeded` になる（fake の webhook と一時ディレクトリでテスト）。
  2. 新しい市場日の初回（snapshot を今回作った場合）は、今回の report を送る（現行どおり）。
  3. `resend=true` の挙動は変えない（文書どおり、今回の scan の report を送る）。
  4. 既存の通知テスト（test_inflection_digest.py）が通る。
  5. playbooks.md と project-overview.md の再試行の説明が、新しい挙動と矛盾しない（`grep` で確認）。
- **備考**: 復号には鍵が要る。`main` で取得済みの鍵を `_deliver_digest` に渡す。

### REQ-003: 休場日にずれ込んだ保有銘柄監視を、前の取引日の未実行として検出する

- **画面**: なし（Reliability Watchdog の Slack 通知）
- **対象ファイル**: [check_workflow_health.py](../../scripts/check_workflow_health.py)（`_expected_runs` :110、`watchdog_alerts` :130、成功判定 :151）、[run_position_monitor.py](../../scripts/run_position_monitor.py)（休場日判定 :385）。方式によっては [position_monitor.yml](../../.github/workflows/position_monitor.yml) も。
- **Before（現状）**: 監視は「実行時点の JST の日付」が取引日かだけを見る。11/2（月）15:50 の終値監視が 11/3（祝日）04:00 にずれ込むと、保有銘柄があっても価格を確認せず、終了コード 0 を返す。watchdog は、予定（11/2 15:50）から翌平日の最初の cron（11/3 9:20）までに始まった成功 run を 11/2 分の成功と数える。このため、ほかに成功 run が無くても警告が出ない。
- **After（期待）**: 休場日の判定でスキップしただけの run は、前の取引日の監視の成功として数えない。その取引日にほかの成功 run が無ければ、watchdog がその取引日の欠測（`no_successful_run`）を 1 回通知する。
- **受入条件**:
  1. 予定 11/2 15:50 に対し、11/3（祝日）04:00 に始まった成功 run だけがある場合、11/2 分の警告が 1 件出る（テスト）。
  2. 予定当日に成功した run がある場合、および翌取引日の早朝（日付は変わったが取引日）に成功した run がある場合は、警告が出ない（テスト）。
  3. 既存のテスト（test_workflow_health.py・test_run_position_monitor.py）が通る。
- **備考**:
  - [要確認: 方式] 次のどちらかにする。推奨は (b)。
    - (a) 調査メモの方針。監視を実際に完了した市場日を記録し、watchdog が照合する。記録先を新しく決める必要がある。watchdog は保有情報（Google Sheets）を読まない作りで、monitor の workflow は `contents: read` で commit しない。候補は actions/cache・artifact・Sheets の status。
    - (b) watchdog だけで判定する。position_monitor の run は、開始日（JST）が取引日のときだけ、予定の取引日の成功と数える。変更は check_workflow_health.py の成功判定だけ。ただし、保有 0 件で休場日にずれ込んだ run も数えなくなるので、その場合は不要な警告が出る（遅延が休場日にかかったときだけで、まれ）。
  - 休場日にずれ込んだ run で、前の取引日の終値監視をやり直すことはしない（調査メモの範囲は検出）。

### REQ-004: 業種が一部不明でも、業種の集中を判定する

- **画面**: なし（学習結果の分類）
- **対象ファイル**: [inflection_learning.py](../../src/evaluation/inflection_learning.py)（`_independence_evidence` :528、条件 :536）
- **Before（現状）**: 集中率は、全件の業種がそろったとき（`sectors and all(sectors)`）だけ計算する。1 件でも業種不明だと集中率は `None` になり、50% の上限を判定しない。30 件中 29 件が同じ業種・1 件が不明のデータで、`positive_candidate` に分類された。
- **After（期待）**: 分母を全件、分子を「判明している業種のうち最多の件数」にする。50% を超えたら `insufficient`。再現例では 29/30 = 96.667% で `insufficient`。業種が 1 件も判明していない場合（業種を持たない旧 schema の snapshot）は、現行どおり `None` で判定しない。`sector33:` のラベルは現行どおり対象外。
- **受入条件**:
  1. 29 件同じ業種・1 件不明で、`top_sector_share_pct` が 96.667、`independence_status` が `insufficient` になり、`positive_candidate` にならない（テスト）。
  2. 全件の業種が判明している既存のケースは、値が変わらない。
  3. 全件不明のときは `None` のまま（テスト）。
- **備考**: 不明分は「別の業種」として扱われるので、不明が多いと集中を少なく見積もる。調査メモの方針どおり、これは許容する。

### REQ-005: 価格ハッシュを日付単位で更新し、復旧時の訂正を検出する

- **画面**: なし（forward validation の価格訂正の記録）
- **対象ファイル**: [rebuild_inflection_forward_validation.py](../../scripts/rebuild_inflection_forward_validation.py)（`_persist_price_hashes` :131、マージ :143）
- **Before（現状）**: 保存時に `{**前回の hashes, **今回の hashes}` で、銘柄の単位で丸ごと置き換える。今回取得できなかった日付のハッシュは消える。11/4〜6 を保存した後、11/5 だけ欠けたデータで更新すると、11/5 のハッシュが消える。11/5 が復旧したときに高値が 100 から 110 に変わっていても、比べる前回値が無いので、訂正は 0 件になる。
- **After（期待）**: 銘柄・価格種別・日付の単位でマージする。今回取得できた日付だけを上書きし、欠けた日付は前回の値を残す。復旧時は前回の値と比べて訂正を記録する。
- **受入条件**:
  1. 再現手順（11/4〜6 保存 → 11/5 欠け → 11/5 復旧で高値 100→110）で、3 回目に 11/5 の訂正が 1 件記録される（テスト）。
  2. 欠けていない日付と、今回取得しなかった銘柄の扱いは現行と同じ（既存テスト test_forward_prices.py・test_inflection_forward.py）。
- **備考**: 暗号化した価格ハッシュのファイル形式（`schema_version`）は変えない。

### REQ-006: 売却後の騰落率を、取引所カレンダーの営業日で数える

- **画面**: なし（売却後 5・20・60 営業日の参考指標と集計）
- **対象ファイル**: [inflection_backtest.py](../../src/evaluation/inflection_backtest.py)（`_finalize_trade` の `early_exit_return` :223-226）。呼出し元は [inflection_backtest.py:386](../../src/evaluation/inflection_backtest.py#L386) と [exit_rules.py:283](../../src/evaluation/exit_rules.py#L283) の 2 箇所で、どちらも `market_calendar` を持つ。
- **Before（現状）**: 売却日より後の「取得できた終値」を数え、N 件目を使う。途中の株価が欠けると、後ろの日にずれる。11/5 に 100 円で売却し、11/9 が欠けた例では、5 営業日後の 11/12（110 円、+10%）ではなく 11/13（200 円、+100%）を使った。20・60 営業日も同じ。
- **After（期待）**: 取引所カレンダーで売却日から N 営業日後の日付を決め、その日の終値を使う。その日の終値が無ければ `None`（未評価）。カレンダー上で N 営業日後がまだ来ていない場合も `None`（現行と同じ）。
- **受入条件**:
  1. 再現例で 5 営業日後の騰落率が +10% になる（テスト）。
  2. 対象日（11/12）の終値が欠けている場合は `None` になる（テスト）。
  3. 欠損の無い既存のケースは値が変わらない（既存テスト）。
- **備考**: `market_calendar` が渡されない場合（価格履歴の日付をカレンダーとして使う場合）は、現行と同じ結果になる。

### REQ-007: 設定エラーを、失敗通知で設定エラーとして表示する

- **画面**: なし（ワークフローの失敗通知の Slack 文面）
- **対象ファイル**: [check_workflow_health.py](../../scripts/check_workflow_health.py)（`STAGES` :24）、[tests/test_workflow_health.py](../../tests/test_workflow_health.py)
- **Before（現状）**: `JQUANTS_PLAN` が不正だと、scan は `failure_stage=configuration` を出力する（[run_inflection_shadow.py:378](../../scripts/run_inflection_shadow.py#L378)）。workflow はこの値を `FAILURE_STAGE` に渡すが、`STAGES` に `configuration` が無いので、通知は汎用の `kind=workflow_failure` になる。
- **After（期待）**: `STAGES` に `configuration` を加え、通知が `kind=configuration` になる。
- **受入条件**:
  1. `FAILURE_STAGE=configuration` で `failure_alert` を呼ぶと、`kind=configuration` の文面になる（テスト）。
  2. 未知の値は従来どおり `workflow_failure` になる（既存テスト）。

### REQ-008: 保有銘柄の監視が、1分足と日足の不一致で評価を完了できない（調査メモに無い問題）

- **画面**: なし（Position Monitor の Slack 通知と Google Sheets の「状況」）
- **対象ファイル**: [position_exit.py](../../src/monitoring/position_exit.py)（`_minute_bars` の日足との照合 :107-139、不一致の判定 :126）、[run_position_monitor.py](../../scripts/run_position_monitor.py)（日足だけの判定 `_daily_could_touch` :162、過去の取引日の回収 `_recover_pending` :198、全銘柄が評価できないときの失敗 :535）、[test_position_exit.py](../../tests/test_position_exit.py)、[test_run_position_monitor.py](../../tests/test_run_position_monitor.py)。文書: [docs/playbooks.md:30](../../docs/playbooks.md)。
- **Before（現状）**:
  - 1 分足を合計した値（始値・高値・安値・終値・出来高）が日足と完全に一致しないと、評価を打ち切る（`incomplete`）。10/08 の `62ec471` で入った。
  - Yahoo の東証 1 分足は 09:05〜15:24 しかなく、寄付と大引けが入らない。実データ（2026-11-19 取得）で、トヨタ（7203.T）の 11/18 は、終値が 1 分足 3385 円・日足 3391 円、出来高が 1134 万株・1732 万株だった。11/19 の大引け後に 3 銘柄（7203.T・6758.T・9984.T）で試すと、3 銘柄とも不一致で `incomplete` になった。
  - このため、保有銘柄はすべて `incomplete` になり、実行は「no holdings had a usable current quote」で失敗する。過去の取引日の回収も同じ照合を通るので、30 日を過ぎて日足だけで判定する処理に回るまで、ストップへの接触を検出できない。
- **After（期待）**: 1 分足が寄付・大引けを欠いていても、評価を完了する。1 分足で接触を確認できない部分は、日足で保守的に判定する。
  - 日足の安値が stop 水準（その日の高値まで含めた最高値 × (1 − stop%)）より上なら、接触なしとして `ok` にする（`_daily_could_touch` と同じ考え方）。
  - 1 分足で接触を確認できれば、その時刻で通知する（現行どおり）。
  - 日足の安値が stop 水準以下なのに 1 分足では接触していない場合は、見逃さないように「接触の可能性」として通知する。
  - 日足が無い・値が不正な場合は、現行どおり `incomplete` にする。
  - [要確認: 接触の可能性の扱い] 「接触の可能性」を接触（`triggered`）として扱い、一度だけ通知することを推奨する（30 日超の `recovered_daily_possible_touch` と同じ扱い）。日中の順序が分からないので、誤報がありうる。
- **受入条件**:
  1. 1 分足が 09:05〜15:24 だけで、日足と始値・終値・出来高が異なるデータ（再現例の形）で、日足の安値が stop 水準より上なら `status=ok` になる（テスト）。
  2. 同じ形のデータで、1 分足の安値が stop 水準以下なら、その時刻で接触として通知される（テスト）。
  3. 日足の安値だけが stop 水準以下（1 分足では未接触）の場合、接触の可能性として 1 回だけ通知される（テスト）。
  4. 日足が無い場合は `incomplete` のまま（テスト）。過去の取引日の回収（`_recover_pending`）も同じ規則で評価を完了する（テスト）。
  5. 既存のテスト（test_position_exit.py・test_run_position_monitor.py）が、変更した照合の期待値を除いて通る。
  6. 保有銘柄がある日に、main の position monitor の実行が成功する（Actions 上で確認）。
- **備考**: 取引時間中の実行（9:20・12:50・15:35）でも、当日の日足は途中経過なので 1 分足と一致しない。同じ規則で扱う（大引け後と同様に、実データでの確認を推奨）。

---

## 完了済み・保留中

### 完了済み
- なし。

### 保留中（今回のスコープ外）
- **本番の履歴での発生有無と影響件数**: 調査メモで未確認。REQ-001 は既存 snapshot の `generated_at`、REQ-002 は送信状態と snapshot、REQ-005 は価格ハッシュの復号が必要なので、鍵のあるローカル環境で別に確認する。
- **`resend_digest=true` の送信内容**: 今回の scan の report を送る挙動は、文書に明記された仕様なので変えない（REQ-002 は通常の再試行だけを直す）。
