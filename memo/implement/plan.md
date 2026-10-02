## 実装計画: 候補の見える化と、後から取り戻せないデータの記録 — REQ-048 / REQ-049 / REQ-050 / REQ-051

> 入力: [proposal.md](proposal.md)
> 以前の plan.md（REQ-045〜047、実装済み）は [plan_req045-047.md](plan_req045-047.md) に移した。

### 目的
日次の候補を、ローカルでの表示（REQ-048）と Slack のダイジェスト（REQ-049）でユーザーに見えるようにする。あわせて、後から復元できない診断用の特徴量（REQ-050）と、実行できなかった営業日の検出（REQ-051）を、今日から記録し始める。戦略、スコア、分類、snapshot の schema は変えない。

### 前提
- REQ-045〜047 はコミット済み（`c630360`）。コードに他セッションの未コミットの変更はない。
- B1 の実データ取得（`.data/jquants/`）が別プロセスで実行中である。**本計画の作業は、そのプロセスにも `.data/` にも触れない**（コードの変更は、起動済みのプロセスに影響しない）。

### 提案からの変更点（調査で判明した事項）
1. **新しい特徴量の計算は、`_evaluate_candidate` に基準日（`as_of`）を渡して行う。** 経過日数には scan の市場日が必要だが、現状の `_evaluate_candidate` はそれを受け取らない。`select_and_evaluate` が持っている `seed_date`（本番では `expected_date`、B1 の過去検証では `as_of`）を渡すので、過去の日付でも同じ項目が計算される。
2. **Slack への送信は `src/notify/` に置く。** 新しいパッケージが必要で、`src/notify/__init__.py` を作る（`pyproject.toml` は `src*` を含めているので、パッケージ設定の変更は不要）。既存の Position Monitor の `_post_slack` はそのままにする（影響範囲を広げない）。
3. **ダイジェストの再送の限界。** ダイジェストを送るのは `snapshot_created=True` のときだけなので、同じ日の手動再実行で snapshot が既にあれば送らない。1回目の送信が失敗した日は、自動では再送されない。その日の候補は `show_candidates.py` で確認できる（これは設計上の限界として受け入れる）。
4. **欠損の検出は、前の営業日と全期間の件数の2つを使う。** ダイジェストは「前の営業日がない」場合に警告し、全期間の欠損数も1行で添える。

### スコープ
- 含むもの: REQ-048〜051 と、それらのテスト、`project-overview.md` の更新、CI の mypy 対象・起動パスの更新
- 含まないもの: 欠けた日の補完、四半期の業績加速、業種の相対モメンタム、戦略に影響する項目、Slack 以外の通知先

### 影響範囲（変更/追加予定ファイル）
- `src/data/session_gaps.py`（新規）: 欠けた営業日の検出
- `src/screening/inflection_live.py`: `_technical_features`、`_fundamental_features`、`_evaluate_candidate`、`select_and_evaluate`、`FEATURE_DEFAULTS`
- `src/notify/__init__.py`、`src/notify/slack.py`、`src/notify/inflection_digest.py`（新規）: 送信とメッセージの組み立て
- `scripts/run_inflection_shadow.py`: `main` にダイジェストの送信を追加
- `scripts/show_candidates.py`（新規）: ローカルの表示
- `scripts/rebuild_inflection_forward_validation.py`: レポートに `session_coverage`
- テスト: 新規 `tests/test_session_gaps.py`、`tests/test_inflection_digest.py`、`tests/test_show_candidates.py`（新規モジュールごとに専用のテストを置く）。既存の `tests/test_inflection_live.py`、`tests/test_inflection_forward.py`、`tests/test_shadow_health.py` を拡張する
- `.github/workflows/test.yml`（mypy 対象）、`.github/workflows/forward_validation.yml`（起動パスとテスト一覧）、`memo/project-overview.md`

### 実装ステップ

#### Step 0: 基準線と、変更前の出力の固定
- [ ] `pytest tests/` が PASS することを確認する
- [ ] REQ-050 の変更の前に、`tests/test_inflection_live.py` と同じ合成データ（`_scan_multi(MultiCodeFakeClient(), deep_candidates=3, control_sample_size=3)`）の `candidates` と `control_sample` の指紋（`features` のうち新しい項目を除いたものを JSON にして sha256）を取り、記録する（Step 2 の回帰テストで使う）
**検証**: 基準線が PASS し、指紋を記録できている

#### Step 1: REQ-051 — 欠けた営業日の検出
- [ ] `src/data/session_gaps.py`:
  - `missing_sessions(snapshot_dir: Path, through: date) -> list[str]`: `snapshot_dates([snapshot_dir])`（`forward_prices.py` の関数を再利用）の最初の日から `through` までの東証の営業日（`exchange_calendars` の XTKS、`sessions_in_range`）のうち、snapshot がない日を昇順で返す。snapshot が1件もなければ `[]`
  - `previous_session_missing(snapshot_dir: Path, market_date: date) -> str | None`: `market_date` の前の営業日が、最初の snapshot の日以降で、かつ snapshot がなければ、その日付を返す。なければ `None`（最初の snapshot より前の日は欠損と数えない）
  - `session_coverage(snapshot_dir: Path, through: date) -> dict[str, Any]`: `first_snapshot_date`、`last_snapshot_date`、`expected_sessions`、`snapshots`、`missing_sessions` を返す。snapshot がなければ全項目が空・0
  - `latest_settled_session(now: datetime) -> date`: 実行時点で snapshot が存在しているはずの、最新の確定した営業日。既存の `expected_tse_session_date(now)`（`src/data/market_calendar.py`）を使うので、休日、土日、当日の引け前（その日の足がまだ確定していない時刻）を正しく扱う（再レビュー #1）
**検証**: 受入条件 REQ-051 の 1・2

#### Step 2: REQ-050 — 診断用の特徴量
- [ ] `_technical_features` の戻り値に次を追加する（調整後終値 `close` の日次リターン `close.pct_change().dropna()` から）
  - `max_daily_return_20d_pct`: 直近20日の最大（%）
  - `up_day_ratio_20d`、`up_day_ratio_60d`: 前日より上がった日の割合（0〜1）。60日は61本の終値がなければ `None`
  - `daily_volatility_20d_pct`: 直近20日の日次リターンの標準偏差（標本、%）
  - `distance_from_period_high_pct`: `(現在値 / 取得期間の高値 − 1) × 100`（0 以下）
- [ ] `_fundamental_features` の戻り値に `forecast_disclosure_date`（上方修正率に使った直近の予想の `DiscDate`。予想が2件未満なら `None`）を追加する
- [ ] `FEATURE_DEFAULTS` に、上の6項目と `disclosure_age_days`、`forecast_age_days`（いずれも既定 `None`）を追加する
- [ ] `_evaluate_candidate(..., as_of: str)` を追加し、`features` を `{**tech の診断項目, **fundamental, 経過日数}` から、`FEATURE_DEFAULTS` のキーの順に作る。経過日数は `(date(as_of) − date(開示日)).days`（開示日が不正・欠損なら `None`）
- [ ] `select_and_evaluate` が `seed_date` を `as_of` として渡す
**検証**: 受入条件 REQ-050 の 1〜5。Step 0 の指紋を、新しい項目を除いて比べ、一致することを確かめる

#### Step 3: REQ-049 — Slack ダイジェスト
- [ ] `src/notify/slack.py`: `post_text(webhook, text, *, timeout=10)`（`requests.post(webhook, json={"text": text}, timeout=timeout)` と `raise_for_status()`）
- [ ] `src/notify/inflection_digest.py`:
  - `build_digest(report, *, warnings) -> str`: 見出し（「[検証用] JP Inflection 日次候補 {日付}」「売買推奨ではありません。財務データは約{N}週間遅れです」）、件数、EARLY_CANDIDATE（上限10件）、WATCH（上位5件）、警告。各行は「• 銘柄 会社名（市場・業種） スコア 20日リターン 出来高比 理由」。値が `None` の項目は「-」と書く。候補が0件の日は、件数だけにする
  - `daily_warnings(snapshot_dir, market_date) -> list[str]`: `previous_session_missing` による警告と、`missing_sessions` の全期間の欠損数
  - `send_daily_digest(report, *, snapshot_dir, webhook, post=post_text) -> str`: Webhook が空なら `"skipped:no-webhook"`。送信に成功したら `"sent"`。**あらゆる例外を捕まえ**、`"failed:{例外の型名}"` を返す（URL とメッセージは含めない）
- [ ] `run_inflection_shadow.main`: `persist_report` の後、`snapshot_created` が True のときだけ `send_daily_digest` を呼ぶ。False のときは `"skipped:snapshot-existed"`。最後のサマリー行に `digest={状態}` を足す（銘柄名や内容は出さない）
**検証**: 受入条件 REQ-049 の 1〜7

#### Step 4: REQ-048 — ローカル表示スクリプト
- [ ] `scripts/show_candidates.py`: 引数は `--repo-root`、`--date`、`--classification`（複数可、既定は `EARLY_CANDIDATE` と `WATCH`）、`--top`（既定 20）、`--control`
  - 入力: `--date` がなければ `dashboard/data/inflection_candidates.enc`、あれば `dashboard/data/inflection/v3/{date}.enc`。`snapshot_encryption_secret()` と `decrypt_json` で復号する
  - 表: 銘柄、会社名、分類、スコア、20日リターン、出来高比、高値圏（52週／上場来）、市場、業種（なければ「-」）、理由。スコアの高い順。全角文字の幅は `unicodedata.east_asian_width` で揃える
  - 先頭に、日付、strategy_version、schema、分類ごとの件数、財務データの遅延の注意を表示する。`--control` で `control_sample` を表示する（schema 4 でキーがなければ、その旨を表示する）
  - 鍵がない、復号に失敗（鍵違い・破損）、ファイルがない場合は、メッセージを標準エラーに出して、終了コード 1。外部通信をする処理は import しない
**検証**: 受入条件 REQ-048 の 1〜5

#### Step 5: REQ-051 — forward のレポート
- [ ] `rebuild_inflection_forward_validation.py` のレポートに `session_coverage` を追加する。**終点は、最後の snapshot の日付ではなく、実行時点で確定しているはずの最新の営業日**とする: `through = max(latest_settled_session(now), 最後の snapshot の日付)`（再レビュー #1。最後の snapshot を終点にすると、直近で scan が連続して失敗した営業日が、期待する範囲にすら入らず、欠損 0 件に見える）。`now` は、テストで固定できるように、スクリプト内の `_utc_now()`（`datetime.now(UTC)`）から取る。評価の対象と、既存のキーは変えない
**検証**: 受入条件 REQ-051 の 3

#### Step 6: テスト・CI・文書
- [ ] `tests/test_session_gaps.py`: 営業日・土日・祝日が混在する期間（2026-09 の連休を含む）の欠損、snapshot なし、最初の snapshot より前は数えない、`previous_session_missing`、`session_coverage`。加えて（再レビュー #1）`latest_settled_session`: 取引日の引け後は当日、引け前は前の営業日、土日・祝日は直前の営業日を返す
- [ ] `tests/test_inflection_digest.py`:
  - 本文の項目、件数の上限（EARLY 10、WATCH 5）、候補0件、`None` の項目、警告の有無
  - `main` 経由で、`snapshot_created=True` のとき1回だけ送られ、`False` のときは送られない（`post` を差し替える）
  - 失敗（500、タイムアウト、任意の例外）でも `main` が例外を出さず、snapshot は保存されている
  - Webhook なしでは通信しない
  - **標準出力・標準エラーに、銘柄名、会社名、Webhook の URL が含まれない**（`capsys`）
- [ ] `tests/test_show_candidates.py`: 順序、列、絞り込み、`--top`、`--control`、schema 4、鍵なし・鍵違い・日付なしの終了コード、全角幅の揃い、通信しないこと（`requests` と `yfinance` を import していない）
- [ ] `tests/test_inflection_live.py`: 5つの価格の診断値（手計算、履歴不足で `None`）、開示の経過日数（予想が2件未満で `None`、開示日が不正で `None`）、先読みしないこと（判定日より後の価格を変えても同じ）、**Step 0 の指紋との一致**（スコア・分類・候補が変わらない）。既存の `set(candidate["features"]) == set(FEATURE_DEFAULTS)` が、新しい項目を含めて PASS する
- [ ] `tests/test_inflection_forward.py`: レポートに `session_coverage` が出て、既存のキーが変わらない。新しい項目がある snapshot と、ない snapshot の両方を、forward と learning の loader が読める（`tests/test_inflection_learning.py` にも1件）。加えて（再レビュー #1）**実行日時を固定した回帰テスト**: snapshot が 2026-09-25 まで揃っていて、実行時刻が 2026-10-04 09:30 JST のとき、`session_coverage` の欠損に 9/28・9/29・9/30・10/1・10/2 の5営業日が出る（土日、9月の連休は含まれない）。実行時刻が 10/2 の引け前（14:00 JST）なら、10/2 は欠損に含まれず、9/28〜10/1 の4営業日になる。最後の snapshot が確定した最新の営業日と同じなら、欠損は 0 件
- [ ] `tests/test_shadow_health.py`: 新しい項目を含む report が `validate_report` を通る
- [ ] `test.yml` の mypy 対象に、`src/data/session_gaps.py`、`src/notify/slack.py`、`src/notify/inflection_digest.py`、`scripts/show_candidates.py` を追加する。`forward_validation.yml` の起動パスとテスト一覧に、`src/data/session_gaps.py` と `tests/test_session_gaps.py` を追加する
- [ ] `memo/project-overview.md` に、日次のダイジェストと `show_candidates.py` の使い方を追記する
**検証**: `pytest tests/`、`ruff check src scripts tests`、mypy がすべて PASS する

### 例外・エラーハンドリング方針
- **ダイジェストは best-effort。** どんな例外でも scan を失敗させない（snapshot の commit の step を止めない）。ログには型名だけを出す
- 表示スクリプトは、利用者向けのメッセージと終了コード 1 で終わり、スタックトレースを出さない
- 診断用の特徴量は、計算できなければ `None`。例外にしない

### テスト/検証方針
- 自動テスト: `.venv/bin/python -m pytest tests/ -q`、`.venv/bin/ruff check src scripts tests`、`.venv/bin/mypy --ignore-missing-imports <test.yml の対象>`
- 手動確認観点:
  - [ ] push 後の最初の日次 scan で、Slack にダイジェストが届き、Actions のログに銘柄名が出ていない
  - [ ] 同じ日の手動再実行で、2通目が届かない
  - [ ] 最初の schema 5 の snapshot（`show_candidates.py` で確認）に、新しい項目が入っている
  - [ ] 次の週次 forward validation の summary に、`session_coverage` が出ている（9/28 が欠損として出る。さらに、その週に scan が連続で失敗していれば、最後の snapshot より後の営業日も欠損として出る）

### リスクと対策
1. リスク: Slack の失敗が scan の後続（snapshot の commit）を止める → 対策: すべての例外を捕まえ、`main` の失敗テスト（500、タイムアウト、任意の例外）で、snapshot が保存されることを確かめる
2. リスク: 公開リポジトリのログから候補が分かる → 対策: ログには件数と状態だけを出し、`capsys` で銘柄名・会社名・URL が出ないことをテストする
3. リスク: 特徴量の追加がスコアに影響する → 対策: Step 0 の指紋との一致で、スコア・分類・候補が変わらないことを確かめる
4. リスク: 全角文字で表の列がずれる → 対策: 文字の幅を `east_asian_width` で数え、テストで確かめる
5. リスク: 1回目のダイジェストの失敗が自動では再送されない → 対策: 設計上の限界として受け入れる。`show_candidates.py` でその日の候補を確認できる

### 完了条件
- [ ] REQ-048 の受入条件 1〜5、REQ-049 の 1〜7、REQ-050 の 1〜5、REQ-051 の 1〜4 を満たすテストが PASS する
- [ ] スコア、分類、候補、`classification_counts` が変わっていない（指紋の回帰テストが PASS する）
- [ ] `STRATEGY_VERSION` と `REPORT_SCHEMA_VERSION` が変わっていない
- [ ] `pytest`、`ruff`、`mypy` がすべて PASS する
