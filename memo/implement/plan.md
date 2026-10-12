## 実装計画: Stage 4B — CI・通知・保存・障害診断（REQ-062〜067）

### 目的
Q03/Q04/Q05/Q07/Q09 を、投資判定の数値を変えずに実装し（CI信頼性・secret/権限・通知状態・provider障害診断・保存耐障害性）、境界を回帰テストで固定する。Stage 4A は確定済み baseline で、再設計しない。

### スコープ
- 含むもの: REQ-062（Forward PR 検証範囲と secret 分離）、REQ-063（ダイジェストの状態分離と再送）、REQ-064（uv.lock・Action SHA・最小権限）、REQ-065（provider 失敗分類・Retry-After 上限）、REQ-066（atomic write）、REQ-067（境界テスト）
- 含まないもの: Stage 4C（Q08/B09）、Growth、Q06 閾値の変更、mypy 既知 31件の解消、新特徴量・スコア・閾値・重み、過去 snapshot 書換え、archive 変更、無関係な依存更新、全面リファクタリング

### 調査結果（実装の前提）
- **[確認済]** `uv.lock` は存在し `uv lock --check --offline` が通る（53 packages、pyproject と同期）。pyproject は直接依存を `==` で固定済み。CI は全 workflow で `pip install -e .` / `".[dev]"`（`uv.lock` 未使用）。ローカル uv は 0.9.21。Python は CI で 3.11。
- **[確認済]** 使用中の Action は 6 種: `checkout@v7`（11箇所）、`setup-python@v7`（6）、`cache/restore@v4`（5）、`cache/save@v4`（5）、`upload-artifact@v7`（3）、`download-artifact@v7`（1）。`gh` コマンドは未インストールのため、タグ→SHA は `git ls-remote --tags`（読み取り専用）で解決できる。解決済み（2026-10-12 時点、いずれも軽量タグで `^{}` なし）:
  - checkout v7 = `3d3c42e5aac5ba805825da76410c181273ba90b1`（v7.0.1 と同一）
  - setup-python v7 = `5fda3b95a4ea91299a34e894583c3862153e4b97`
  - cache v4 = `0057852bfaa89a56745cba8c7296529d2fc39830`
  - upload-artifact v7 = `cf430e030ddbb5b0abf93d22962f4752f3646cd9`
  - download-artifact v7 = `37930b1c2abaa49bbe596cd826c3c89aef350131`
  実装時に再度 ls-remote で同値を確認してから置換する（浮動タグなので日付を記録）。
- **[確認済]** `forward_validation.yml` の `pull_request.paths` は 28 個の手列挙（`src/screening/**`・`inflection_historical.py`・`inflection_report.py`・`pyproject.toml`・`uv.lock` を含まない）。`validate` ジョブは PR でも `SNAPSHOT_ENCRYPTION_KEY` を使う `rebuild_inflection_forward_validation.py` を実行する。workflow 全体 `contents: read`、`persist-price-hashes` のみ `contents: write`（schedule 限定）。
- **[確認済]** `inflection_shadow.yml` は workflow 全体が `contents: write`、`scan` ジョブに `SLACK_WEBHOOK_URL`・`SNAPSHOT_ENCRYPTION_KEY` が job env、`JQUANTS_API_KEY`/`EDINET_API_KEY` が scan ステップ env。push は同ジョブ内の Commit ステップ。
- **[確認済]** `test.yml` は PR で lint/mypy/pytest を回す（secret 不要）。`pull_request_target` は全 workflow で未使用 [未確認: 実装時に grep で再確認]。
- **[確認済]** ダイジェスト: `_deliver_digest` は `snapshot_created=False` だと `skipped:snapshot-existed`。`send_daily_digest` は webhook 無し→`skipped:no-webhook`、例外→`failed:<型名>`、成功→`sent`。結果は stdout のステータス文字列のみで、永続状態は無い。送信は Git push より前に行われる。
- **[確認済]** 保存: `persist_report` は `snapshot.exists()` で immutable を守るが、書込みは `write_text` 直書き（snapshot と `latest_path`）。snapshot 列挙は `^YYYY-MM-DD.enc` 完全一致（`snapshot_dates`）と `glob("????-??-??.enc")` のため、`*.tmp` 名の一時ファイルは読込・欠損判定に混入しない。直書きは他に `rebuild_inflection_forward_validation.py:145,373,375`、`rebuild_inflection_learning.py:88,92`、`run_inflection_historical_backtest.py:146,152`。既存の安全パターンは `jquants_history.py:99-101,135-136`、`edinet.py:310-312`、`check_workflow_health.py:49-50`。
- **[確認済]** 広い except: `yfinance_prices.py:112`、`forward_prices.py:133,158`、`live_quote.py:101,166,188,207`。Retry-After: `jquants_v2_client.py:86-90`（非負のみ）、`edinet.py:139-141`（有限のみ、負数・上限なし）。
- **[未確認]** `yfinance_prices.py` の retry 内部構造と、`live_quote.py:101` が既に保持している分類情報の範囲（実装 Step 4 の冒頭で読む）。`run_position_monitor.py` の取得失敗の扱い。

### 影響範囲（変更/追加予定ファイル）
- `.github/workflows/forward_validation.yml`: path filter 見直し、secret 不要/必要の分離（REQ-062）、Action SHA 固定・lockfile install・権限（REQ-064）
- `.github/workflows/test.yml`, `inflection_shadow.yml`, `position_monitor.yml`, `reliability_watchdog.yml`: Action SHA 固定、lockfile install、権限最小化（REQ-064）
- `dashboard/data/inflection/digest_state.json`（新規、小さな状態ファイル。日付→`pending`/`succeeded`）: 通知状態の永続化（REQ-063）。実 repo のファイルは作らず、テストは一時ディレクトリのみ
- `scripts/run_inflection_shadow.py`: ダイジェスト状態の分離・再送（REQ-063）、snapshot/latest の atomic write（REQ-066）
- `src/notify/inflection_digest.py`、`src/notify/slack.py`: 送信結果の分類（REQ-063）
- `src/data/yfinance_prices.py`、`forward_prices.py`、`live_quote.py`、`provider_output.py`、`jquants_v2_client.py`、`edinet.py`: 失敗分類・Retry-After 上限（REQ-065）
- `scripts/rebuild_inflection_forward_validation.py`、`rebuild_inflection_learning.py`、`run_inflection_historical_backtest.py`: atomic write（REQ-066）
- 共通の atomic write helper: 既存の `os.replace` パターンを 1 箇所に寄せる場合のみ新規（候補 `src/data/atomic_write.py`）。既存 3 箇所の流儀と重複するため、**新設は最小限**（既存関数で足りれば再利用）。
- `docs/playbooks.md`: 通知の保証境界（REQ-063）と、障害分類の読み方（REQ-065）を短く追記
- `tests/test_workflow_reliability.py`、`tests/test_inflection_digest.py`、`tests/test_yfinance_prices.py`、`tests/test_forward_prices.py`、`tests/test_live_quote.py`、`tests/test_jquants_v2_client.py`、`tests/test_edinet.py`、`tests/test_inflection_forward.py`、`tests/test_inflection_learning.py`: 既存ファイルを拡張（新規ファイルは、既存で検証できない場合のみ）
- `tests/conftest.py`: 変更しない（Stage 4A の外部通信拒否を維持）

### 実装ステップ

実装順は「リスクが低く独立 → 依存あり」: Q09 → Q07 → Q04 → Q05 → Q03 → Q10 まとめ。Q04 の状態表現が Q09 の書込みに依存するため Q09 を先に行う。各 Step 完了時に対象テスト＋直前までの回帰を実行する。

#### Step 1: Q09 — atomic write（REQ-066）
- [ ] 既存パターン（`jquants_history.py`/`edinet.py`/`check_workflow_health.py`）を比較し、再利用する関数または 1 つの小さな helper（temp 書込み→flush→fsync→`os.replace`、同一ディレクトリの `.tmp` サフィックス、失敗時の temp 削除）を決める
- [ ] 失敗再現テストを先に書き、現行の直書きで旧ファイルが破損することを示す（`write_text` を途中で例外にする fake で確認）
- [ ] `persist_report` の snapshot と latest を atomic 化。snapshot は「存在しない場合のみ作成」を維持（`os.link`/排他作成で二重実行競合も防ぐ。`FileExistsError` は既存扱い）
- [ ] rebuild 系 3 スクリプトの JSON/summary/hash 書込みを atomic 化（親ディレクトリは `mkdir(parents=True, exist_ok=True)`）
- [ ] 複数ファイル間（snapshot と latest）は transaction にしない。順序（snapshot→latest）と「どちらかだけ残り得る」境界を docstring に明記
**検証**: write 途中失敗 / flush 失敗 / replace 前停止 / replace 失敗で旧ファイルが無傷、二重実行、既存 immutable snapshot 不変、新規 output directory、temp が snapshot 列挙に出ない。保存バイト列が従来と同一。

#### Step 2: Q07 — provider 失敗の安全な分類（REQ-065）
- [ ] `yfinance_prices.py`・`forward_prices.py`・`live_quote.py` の現行 except を読み、既に分類している箇所（`live_quote.py:101`）を基準に、安全な分類 enum/文字列（timeout / rate_limit / server_error / protocol / empty / invalid_ohlcv / validation / auth / unexpected）を 1 箇所（`provider_output.py` を拡張）に定義
- [ ] 例外→分類の純関数（HTTP status・例外型のみ参照。メッセージ本文・URL は見ない）。想定外（TypeError 等）は `unexpected` とし、**再 raise する経路と「ログして継続」する経路を区別**（握り潰さない）
- [ ] 「データなし」へ畳む箇所に分類結果（件数・分類別カウント・retry 回数）を付与。公開出力は分類名と件数のみ（ticker・URL・response body・生例外本文は出さない。Q02 の保護を維持）
- [ ] `Retry-After` の共通パース関数（有限・非負・上限 N 秒）を 1 つ作り、J-Quants と EDINET の両方で利用（上限値は既存の最大待機設定に合わせ実装時に決定）
- [ ] 修正前に失敗するテスト: `inf`/`nan`/負/巨大 Retry-After、TypeError が「データなし」に変わること
**検証**: fake provider で timeout/429/500/malformed/empty/invalid price/TypeError を各 1 ケース。公開出力に ticker/URL/秘密が無い。正常入力の取得結果は不変（既存テスト無変更で通る）。

#### Step 3: Q04 — ダイジェスト状態分離と再送（REQ-063）
- [ ] `send_daily_digest` の戻りを維持しつつ、状態語彙を定義: `snapshot_created` / `persisted`（保存成功）/ `notification_attempted` / `notification_succeeded` / `published`（Git 反映は workflow ステップの outcome で表現）
- [ ] 状態の置き場所（run をまたいで残す）: `dashboard/data/inflection/digest_state.json` に日付ごとの `{"<market_date>": "pending" | "succeeded"}` を持つ小さな状態ファイルを新設する（理由: `GITHUB_OUTPUT`/stdout は同一 run 内の情報で、次の通常実行へ通知成功・失敗を渡せないため。Actions 出力だけの案は採用しない）。ファイルは Step 1 の atomic write で書く。既存の Commit ステップが `git add dashboard/data/inflection/` を行うため、snapshot と同じコミットで反映される。`snapshot_dates`/`glob("????-??-??.enc")` に一致しない名前なので欠損判定・learning には影響しない。直近 30 日分のみ保持する。
- [ ] `_deliver_digest` の判定（通常実行。読むのは checkout 済みのリポジトリ上の状態）: ① 状態ファイルに当日エントリが無く snapshot も無い → snapshot 作成と同時に `pending` を書き、Slack 送信。② 当日 `pending` → 送信（snapshot が既存でも送る。Slack 失敗後の通常再実行が該当）。③ 当日 `succeeded` → `skipped:already-succeeded`。④ snapshot が既存で状態エントリが無い（状態ファイル導入前の旧 snapshot）→ 従来どおり送らず `skipped:legacy-no-state`。書込み順は「状態 `pending`（atomic）→ snapshot（atomic）→ Slack 送信 → 成功時のみ `succeeded`（atomic）→ workflow が Commit/push」。webhook 未設定は `skipped:no-webhook` として `pending` のまま。
- [ ] 再送: `workflow_dispatch` 入力 `resend_digest`（既定 false、schedule では無効）。true のとき状態に関係なく送信し、成功時に `succeeded` を書く。再送は scan を再実行して得た新しい report から作るため、元の snapshot（immutable、再書込みしない）とは内容が異なり得る。復号は `SNAPSHOT_ENCRYPTION_KEY` を持つ scan ジョブ内でのみ行い、再送のために snapshot を復号しない。
- [ ] 保証できない境界を `docs/playbooks.md` に明記し、「Exactly once を保証しない（at-least-once を目指す）」と書く: Slack 受理後に状態保存が失敗、または状態保存後に Git push が失敗 → コミットされていないため次の run は `pending`（または snapshot 未作成）から再実行され、重複通知し得る。Slack が受理しても配信されなかった場合は `succeeded` になるため、手動再送で補う。
**検証**: fake Slack と一時ディレクトリで、障害境界を状態ファイルの内容で検証する。(1) Slack 送信前に停止（状態は `pending`、または未コミット）→ 通常再実行で送られる／(2) Slack 成功後に状態保存失敗 → 状態は `pending` のまま、通常再実行で重複し得ることを分類・文書化／(3) 状態保存後に Git push 失敗（push 前の状態を再現）→ 再実行で重複し得ることを確認／(4) 同日通常再実行（`succeeded`）は送らない／(5) 手動再送は `succeeded` でも送られ、状態が更新される／(6) 再送後の通常実行は `succeeded` のため送らない／(7) 旧 snapshot（状態エントリ無し）は送らない。ステータス文字列・公開ログに候補情報が無い。

#### Step 4: Q05 — lockfile・Action SHA・最小権限（REQ-064）
- [ ] 依存導入: 新しい Action を追加せず、`python -m pip install uv==0.9.21`（現行ローカルと同一、固定）→ `uv sync --frozen`（または `uv export --frozen` を `pip install -r`）に置換。dev 依存は `--extra dev`。`uv.lock` と現行環境の差があれば更新せず報告
- [ ] 全 `uses:` を Step の調査結果の SHA に置換し、`# actions/checkout v7` 形式のコメントで元タグを残す。置換前に `git ls-remote` を再実行して同値を確認
- [ ] 権限棚卸し表を作る（workflow/job/step × contents/pull-requests/actions/secret/push）。`inflection_shadow.yml` は workflow 全体を `contents: read` にし、Commit ステップを持つジョブ（または分離ジョブ）のみ `contents: write`。secret は必要ステップの env にのみ置く（job env の `SLACK_WEBHOOK_URL`/`SNAPSHOT_ENCRYPTION_KEY` を必要ステップへ移動できるか確認）
- [ ] checkout の `persist-credentials: false` を push 不要ジョブで検討（変更する場合は影響を確認）
- [ ] 静的テスト（`tests/test_workflow_reliability.py`）を追加: 全 `uses:` が 40 桁 SHA、write 権限は push ジョブのみ、`pull_request_target` 不使用、不要権限なし、依存導入が lockfile ベース
**検証**: 静的テスト PASS。`uv.lock` に差分なし（または説明済み）。CI の実環境で解決されるパッケージが現行ローカル環境と同一であることを `uv sync --frozen` の dry-run/`uv pip list` で比較。

#### Step 5: Q03 — Forward PR 検証範囲と secret 条件（REQ-062）
- [ ] `forward_validation.yml` の `pull_request` トリガーを再設計: 軽量・secret 不要ジョブ（pytest の Forward/評価関連、lint、型検査相当）は広い path（`src/**`、`scripts/**`、`tests/**`、`pyproject.toml`、`uv.lock`、workflow 自身）で起動
- [ ] 復号を伴う `validate` の snapshot 検証は `schedule`/`workflow_dispatch`（secret あり）に限定し、PR では実行しない。PR で secret が無い場合の skip を条件式（`github.event_name != 'pull_request'`）で明示。fork 由来（`github.event.pull_request.head.repo.fork`）でも secret 参照ステップが走らない構造にする
- [ ] `pull_request_target` は使わない。secret は `schedule`/`workflow_dispatch`/push のジョブにのみ渡す
- [ ] 失敗通知ジョブ（`notify-failure`、既存）が PR で動かないことを確認（既存の `github.ref == 'refs/heads/main'` 条件）
- [ ] 静的テスト: 変更カテゴリ別（screening/evaluation/report/historical/forward/共有コード/data validation/依存定義/workflow）に対して該当 path が filter に含まれること、event × secret の組合せごとに secret 参照ステップの実行条件を検証
**検証**: 静的テスト PASS（same-repo PR / fork PR / push / schedule / workflow_dispatch × secret あり/なし）。実 Actions 上の挙動は未確認として報告。

#### Step 6: Q10 — Stage 4B 境界テストの整理（REQ-067）
- [ ] Step 1〜5 で追加した境界テストを一覧化し、REQ-062〜066 の受入条件が全て 1 つ以上のテストに対応することを確認
- [ ] 不足分のみ追加（secret なし PR、Slack 失敗と再送、通知成功・保存失敗、provider timeout/429/500、生ログ漏洩防止、atomic write 失敗、immutable、permissions）
- [ ] coverage 目的だけのテストは追加しない。`tests/conftest.py` の外部通信拒否を維持
**検証**: 外部通信試行数 0。

#### Step 7: 全体検証と報告
- [ ] 対象テスト → Stage 4A 回帰 → 第1〜第3段階回帰 → 全テスト（約7分）→ coverage → ruff → mypy（31 件のエラー内容を変更前とファイル/メッセージ単位で比較）
- [ ] 保存済み snapshot（`dashboard/data/inflection/`）・archive の `git status` 差分が 0、外部通信試行数 0
- [ ] baseline 確認: 候補・EARLY_CANDIDATE・スコア・outcome・portfolio・learning 入力が有効入力で不変（既存の回帰テストと同一入力の before/after 比較）
- [ ] 独立レビュー（secret 漏洩・ログ漏洩・二重通知・通知消失・ファイル破損・PR 検証漏れ・provider 障害の握り潰し・回帰）。重大な問題のみ修正
- [ ] `.harness/reports/reliability-stage4b-2026-10-12.md` に報告（形式は proposal の「完了報告」）。Stage 4C へ進まず停止

### 例外・エラーハンドリング方針
- 失敗は「分類して残す」。正常系の戻り値を変えない（空 DataFrame/None を返す既存契約は維持し、分類は付随情報で渡す）。想定外例外は握り潰さず上位へ伝える。
- 公開ログ・Slack・stdout には分類名・件数・HTTP status・retry 回数のみ。ticker・URL・response body・生例外本文・secret は出さない。
- 保存は「旧ファイル維持」を最優先。temp は同一ディレクトリ、失敗時に削除。immutable snapshot は上書きしない。
- 通知は best-effort のまま（スキャンを失敗させない）。「少なくとも 1 回送る」を目指すが exactly-once は保証しない。

### テスト/検証方針
- 自動テスト: `uv run --offline pytest -q -p no:cacheprovider tests/<対象>`（対象別）→ 全テスト `uv run --offline pytest -q -p no:cacheprovider` → `uv run --offline ruff check src scripts tests` → `uv run --offline mypy src scripts`
- 手動確認観点: workflow YAML の権限・条件式を目視（`pull_request_target` 無し、fork で secret 参照ステップが走らない）。実 Actions・実 Slack は確認不能（報告で分離）。
- baseline: 有効入力での戦略数値不変を、既存テストの無変更通過と代表入力の before/after 比較で確認。

### リスクと対策
1. リスク: `uv sync --frozen` への置換で CI の解決結果が変わり、既存テストが CI でだけ落ちる → 対策: ローカルで `uv sync --frozen` した環境で全テストを実行。差があれば lockfile を機械更新せず内容を報告。
2. リスク: Action SHA 固定が浮動タグ（v7）の現在位置とずれる、または非公式 fork の SHA を指す → 対策: 公式リポジトリへの `git ls-remote` のみ使用し、置換前に再確認、コメントに日付と元タグを記録。
3. リスク: path filter 単純化で PR のたびに重い処理が走る → 対策: 重い復号処理は PR で走らせず、軽量検証のみ全 PR。
4. リスク: ダイジェスト状態ファイルの導入で設計が過剰になる／状態の書込みと Git push の順序で重複・消失が起きる → 対策: 状態は `pending`/`succeeded` の 2 値と日付のみ、atomic write で書き、snapshot と同一コミットで push する。旧 snapshot は送らない（`skipped:legacy-no-state`）。完全な exactly-once は目標にせず、重複し得る境界を文書化する。
5. リスク: atomic write 化で書込み先 FS の挙動（Windows/WSL の replace）が変わる → 対策: 同一ディレクトリ temp + `os.replace`、既存パターンと同じ流儀。保存バイト列の同一性テスト。
6. リスク: Q07 の分類追加が公開ログに情報を漏らす → 対策: 分類は列挙型のみ、例外本文を見る処理を作らない。Q02 の漏洩テストを再実行。
7. リスク: 既存テストが旧挙動（広い except による握り潰し）を固定している → 対策: 該当テストは意図を確認し、新仕様（分類して残す・想定外は伝播）に合わせる場合は理由を報告。単なる合わせ込みはしない。

### 完了条件
- [ ] REQ-062: 変更カテゴリごとの検証起動と、secret あり/なし × イベント別の静的テストが PASS。fork PR に secret を渡す構成が無い
- [ ] REQ-063: 通知状態（`pending`/`succeeded`）が run をまたいで保存され、通常実行の判定規則（①〜④）と障害境界 7 ケースが fake Slack でテスト済み。保証できない境界が `docs/playbooks.md` に明記
- [ ] REQ-064: 全 Action が SHA 固定（元タグコメント付き）、依存は `uv.lock` から導入、権限・secret が最小化され静的テスト PASS
- [ ] REQ-065: 分類 9 種が fake provider で区別され、公開出力に機微情報なし、Retry-After が有限・非負・上限付き。想定外例外は握り潰されない
- [ ] REQ-066: 該当書込みが atomic、旧ファイル維持・immutable・二重実行・新規 dir・temp 非混入のテスト PASS
- [ ] REQ-067: 境界テストが各 REQ に対応。外部通信試行数 0
- [ ] 全テスト PASS、ruff PASS、mypy 新規エラー 0（31 件の内容差分なし）、保存済み snapshot・archive 変更 0、戦略数値 baseline 不変
- [ ] Stage 4B レポート作成後に停止（Stage 4C 未着手）
