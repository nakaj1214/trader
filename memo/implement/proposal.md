# 実装要件書（REQ-048〜051: 候補の見える化と、後から取り戻せないデータの記録）

> このファイルは create-plan の入力です。
> 出典: [memo/analysis/improvement_report_2026-10-01.md](../analysis/improvement_report_2026-10-01.md) の A1、A6、A7（入力のみ）、§4.1 の価格特徴量（propose-one で選択）。
> 以前の要件書: REQ-001〜047 → それぞれ `proposal_req*.md`

## 背景

- **A1（P0）:** 日次 scan の結果は暗号化された snapshot にしか残らず、通知は失敗時の Slack だけである。「予測とタイミングをユーザに促す」というプロジェクトの目的に対して、候補を見る手段がない。
- **データ記録:** snapshot に記録しなかった日の値は、point-in-time で後から復元できない（REQ-037 と同じ理由）。スコアや分類を変えずに、将来の学習・検証で使える値を、今のうちから snapshot に記録し始める。

## 決定済みの事項（2026-10-02 ユーザー確認）

- **Slack の送り先はユーザー本人だけである。** したがって、候補（銘柄名を含む）を Slack に送ってよい。
- 公開リポジトリの GitHub Actions のログは誰でも読める。**Slack の本文はログに出さない**（件数だけを出す）。

## 共通の設計判断

- **戦略・スコア・分類・候補の選定は変えない。** `STRATEGY_VERSION`（v3）と `REPORT_SCHEMA_VERSION`（5）は変えない。snapshot に足すのは、`features`（辞書）の中の項目だけである。
- **新しい項目は、過去の snapshot には存在しない。** 読む側は、項目がなくても動くこと（学習・評価は今のところ新項目を使わない）。
- **日次 scan を、通知の失敗で止めない。** scan の後続の step（snapshot の commit）が、Slack の失敗で実行されなくなってはならない。

---

## 要件一覧

### REQ-048: 保存済みの候補をローカルで表示するスクリプトを追加する（A1a）

- **画面**: ターミナル（ローカル実行）
- **対象ファイル**: 新規 `scripts/show_candidates.py`、新規 `tests/test_show_candidates.py`
- **Before（現状）**: snapshot は暗号化されており、候補の中身を見る手段がない。
- **After（期待）**: `python scripts/show_candidates.py` が、`SNAPSHOT_ENCRYPTION_KEY`（環境変数）で snapshot を復号し、候補の表を表示する。外部への通信はしない。
  - 既定の入力は、最新の snapshot（`dashboard/data/inflection_candidates.enc`）。`--date YYYY-MM-DD` で `dashboard/data/inflection/v3/YYYY-MM-DD.enc` を指定できる。
  - `--classification` で分類を絞れる（既定は `EARLY_CANDIDATE` と `WATCH`）。`--top N` で件数を絞れる（既定 20）。`--control` で、対照群（`control_sample`）を表示する。
  - 表の列: 銘柄、会社名、分類、スコア、20日リターン、出来高比、52週高値圏／上場来高値圏、市場、業種（schema 5 のみ）、理由。スコアの高い順に並べる。
  - 表の先頭に、日付、strategy_version、schema、各分類の件数、財務データの遅延の注意を表示する。
  - 鍵がない、復号に失敗した、指定の日付がない場合は、分かりやすいメッセージを出して、終了コード 1 で終わる。
- **受入条件**:
  1. 合成の snapshot（暗号化）を表示して、スコアの高い順に、必要な列が出る。
  2. 分類の絞り込み、`--top`、`--control` が効く。
  3. schema 4 の snapshot（業種なし）でも例外にならない。
  4. 鍵がない、鍵が違う、日付の snapshot がない、の3つで、メッセージと終了コード 1 になる。
  5. 外部通信をしない（ネットワークを呼ぶ処理を import していない）。

### REQ-049: 日次 scan の後に、候補のダイジェストを Slack に送る（A1b）

- **画面**: Slack
- **対象ファイル**:
  - 新規: `src/notify/inflection_digest.py`（メッセージの組み立てと送信）
  - 変更: [scripts/run_inflection_shadow.py](../../scripts/run_inflection_shadow.py)（`main`）
  - テスト: 新規 `tests/test_inflection_digest.py`、既存 `tests/test_shadow_health.py`
- **Before（現状）**: Slack に通知するのは scan が失敗したときだけである。
- **After（期待）**:
  - scan が成功し、**その日の snapshot を新しく作成したとき**（`snapshot_created` が True のとき）だけ、ダイジェストを1通送る。同じ市場日の再実行（snapshot が既にある）では送らない。
  - メッセージの内容（日本語）:
    - 見出し: 「[検証用] JP Inflection 日次候補 {日付}」と「売買推奨ではありません。財務データは約N週間遅れです」
    - 件数: EARLY_CANDIDATE / WATCH / OVEREXTENDED
    - EARLY_CANDIDATE を全件（上限10件）、WATCH を上位5件。各行は、銘柄、会社名、市場・業種、スコア、20日リターン、出来高比、理由
    - 欠損した営業日がある場合の警告（REQ-051。前の営業日の snapshot がない、など）
  - 送信は best-effort とする。**送信に失敗しても、scan の終了コードを失敗にしない**（snapshot の commit を妨げない）。失敗時は、例外の型名だけをログに出す（URL やメッセージの内容は出さない）。
  - `SLACK_WEBHOOK_URL` が設定されていなければ、何もしない。
  - ログには、候補の銘柄名や内容を出さない。出すのは「ダイジェストを送信した／送信しなかった」と、件数だけである。
  - Slack のメッセージの長さの上限に収まるようにする（上記の件数の上限で足りる）。
- **受入条件**:
  1. `snapshot_created=True` のとき、ダイジェストが1回だけ送られ、本文に必要な項目が含まれる。
  2. `snapshot_created=False`（再実行）のときは送られない。
  3. Webhook が 500 を返す、タイムアウトする、といった失敗でも、`main` が例外を出さずに終了し、snapshot は保存されている。
  4. `SLACK_WEBHOOK_URL` がないときは、通信しない。
  5. 標準出力・標準エラーに、銘柄名、会社名、Webhook の URL が含まれない。
  6. 候補が0件の日にも、件数だけの短いメッセージが送られる。
  7. 既存の scan のテストが PASS する。
- **備考**: `inflection_shadow.yml` の job には、すでに `SLACK_WEBHOOK_URL` が環境変数として渡されているので、workflow の変更は不要である。

### REQ-050: 後から取り戻せない診断用の特徴量を snapshot に記録する（A7 の入力、§4.1）

- **画面**: なし（snapshot の `features`）
- **対象ファイル**:
  - 変更: [src/screening/inflection_live.py](../../src/screening/inflection_live.py)（`_technical_features`、`_fundamental_features`、`_evaluate_candidate`、`FEATURE_DEFAULTS`）
  - テスト: `tests/test_inflection_live.py`
- **Before（現状）**: `features` には、財務の数値と、開示日（`latest_actual_disclosure_date`、`latest_disclosure_date`）だけがある。価格系の診断値と、開示や予想修正からの経過日数がない。
- **After（期待）**: `features` に、次の項目を追加する（すべて**スコアには使わない**）。値が計算できなければ `None`。
  - **開示の経過日数**（A7 の入力）:
    - `forecast_disclosure_date`: 上方修正率の計算に使った、直近の予想の開示日（予想が2件未満なら `None`）
    - `disclosure_age_days`: scan の市場日 − `latest_actual_disclosure_date`（日数）
    - `forecast_age_days`: scan の市場日 − `forecast_disclosure_date`（日数）
  - **価格の診断値**（`_technical_features` で計算する。調整後終値を使う）:
    - `max_daily_return_20d_pct`: 直近20営業日の、日次リターンの最大値（MAX 効果）
    - `up_day_ratio_20d`、`up_day_ratio_60d`: 直近20日・60日で、前日より上がった日の割合（Frog-in-the-Pan の元データ）
    - `daily_volatility_20d_pct`: 直近20営業日の日次リターンの標準偏差（%）
    - `distance_from_period_high_pct`: 現在値が、取得期間内の高値より何%下にあるか（0 以下。52週高値の連続値）
  - 計算に必要な履歴が足りない場合（20日分、60日分に満たない）は `None`。
  - 経過日数は、scan の市場日（`seed_date`）を基準にする。B1 の過去検証の `reconstruct_scan` も同じ関数を通るので、同じ項目が過去の日付でも計算される。
  - 既存の `features` のキーと値は変えない。`reports` の `features` のキー一覧（`FEATURE_DEFAULTS`）に、上記を追加する。
- **受入条件**:
  1. 手計算できる価格系列で、5つの価格の診断値が期待どおりになる（履歴不足で `None` になることを含む）。
  2. 開示日の合成データで、`disclosure_age_days` と `forecast_age_days` が期待どおりになる。予想が2件未満のとき `forecast_*` が `None` になる。
  3. 新しい項目を足しても、スコア、分類、`candidates`、`classification_counts` が変わらない（変更前後の出力を比べる回帰テスト）。
  4. `validate_report`、forward の loader、learning の loader が、新しい項目がある snapshot と、ない snapshot の両方を読める。
  5. 判定日より後の価格を変えても、計算された診断値が変わらない（先読みしない）。

### REQ-051: 実行できなかった営業日を検出し、レポートと通知に出す（A6）

- **画面**: forward のレポート（`inflection_forward_validation_summary.json`）、Slack のダイジェスト、scan のログ
- **対象ファイル**:
  - 新規: `src/data/session_gaps.py`
  - 変更: [scripts/rebuild_inflection_forward_validation.py](../../scripts/rebuild_inflection_forward_validation.py)、`src/notify/inflection_digest.py`（REQ-049）
  - テスト: 新規 `tests/test_session_gaps.py`、既存 `tests/test_inflection_forward.py`
- **Before（現状）**: 日次 scan が失敗した日は、snapshot が欠けるだけで、どこにも記録されない。実際に 2026-09-28 が欠けている。
- **After（期待）**:
  - `missing_sessions(snapshot_dir, through)` が、「最初の snapshot の日付から `through` までの東証の営業日」のうち、`YYYY-MM-DD.enc` が存在しない日の一覧を返す。東証の営業日は、既存の `exchange_calendars`（XTKS）で求める。
  - forward のレポートに、`session_coverage`（期待した営業日数、snapshot の数、欠けた日の一覧）を追加する。評価の対象は変えない。
  - 日次の Slack ダイジェストに、直近の営業日（scan の市場日の前日までの営業日）に snapshot がない場合の警告を載せる。
  - 欠けた日の補完（過去の価格から作り直すこと）は、本要件に含めない。
- **受入条件**:
  1. 営業日、土日、祝日が混在する期間で、欠けた営業日だけが返る（祝日を欠損と数えない）。
  2. snapshot が1件もないとき、空の一覧を返す。
  3. forward のレポートに `session_coverage` が出て、既存のキーは変わらない。
  4. 前の営業日の snapshot がないとき、ダイジェストに警告が出る。ないときは出ない。

---

## 繰り返し失敗している要件

なし。

---

## 完了済み・保留中

### 完了済み
- REQ-045〜047（売却ルールの比較、相場環境、事前警告）: コミット済み（`c630360`）、未 push

### 保留中（今回のスコープ外）
- **四半期ごとの業績の加速**（Chordia & Shivakumar、報告書 §4.1）。J-Quants の財務サマリーは累計値で、単独の四半期の値を作るには、期間の種類（`CurPerType`）の意味を実データで確かめる必要がある。B1 の取得が終われば、`.data/jquants/fins/` に実データがあるので、それを見てから別の要件にする。
- **業種の相対モメンタム、TDnet・EDINET などの追加データ**（REQ-022、B6）。取得方法と利用規約の調査が先である。
- **戦略に影響する項目**（A7 の減衰、A8-a・b、相場環境による戦略の切り替え）。B1 の結果を見てから判断する。
- **Slack 以外の通知先、通知時刻の変更**。
