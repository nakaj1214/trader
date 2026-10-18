# Trader プロジェクト概要

最終確認日: 2026-10-12（コード・workflow 照合。実サービスの再確認は未実施）

## 目的と現在地

Trader は、株価・出来高・財務情報から調査候補を抽出し、その後の成績を検証する Python プロジェクトです。

現在の正規の本番経路は、日本の Prime / Standard / Growth 市場を対象にした日次の **inflection shadow scan** です。これは売買や自動発注を行う仕組みではなく、短期的な変化の初期候補を記録し、将来データで戦略の有効性を評価するための観測系です。

Prophet / LightGBM を中心とする旧予測パイプライン、旧 SQLite / Google Sheets 連携・Slack / LINE 通知、旧 JSON ダッシュボードは `archive/legacy/` に隔離しており、実行・package・CI の対象外です。現行の Position Monitor は別の Google Sheets / Slack 連携を使います。

## システム構成

### 現行本番: JP inflection shadow

```text
GitHub Actions（平日 16:40 JST）
  -> J-Quants V2: 対象銘柄と遅延財務情報
  -> yfinance: 価格・出来高
  -> 流動性・モメンタムによる一次選別
  -> 上位 25 銘柄の財務スコアリング
  -> EARLY_CANDIDATE / WATCH / OVEREXTENDED / NONE
  -> データ健全性検証
  -> Fernet 暗号化 snapshot を Git に保存
  -> 週次 forward validation
```

主要ファイル:

| 責務 | ファイル |
|---|---|
| 定期実行 | `.github/workflows/inflection_shadow.yml` |
| 実行・検証・保存 | `scripts/run_inflection_shadow.py` |
| 二段階スキャン | `src/screening/inflection_live.py` |
| スコア規則 | `src/strategy/inflection.py` |
| J-Quants V2 接続 | `src/data/jquants_v2_client.py` |
| yfinance 一括取得 | `src/data/yfinance_prices.py` |
| 東証営業日判定 | `src/data/market_calendar.py` |
| snapshot 暗号化 | `src/data/snapshot_crypto.py` |
| forward validation / 自己改善学習 | `src/evaluation/inflection_forward.py`, `src/evaluation/inflection_backtest.py`, `src/evaluation/inflection_portfolio.py`, `src/evaluation/inflection_learning.py` |

スコアは、売上・営業利益・利益率・黒字転換・上方修正などのファンダメンタル、20日 / 60日リターン・出来高・52週高値または取得可能な上場来期間の高値などのモメンタム、過熱・営業 CF などのリスクを合成します。ニュースや材料は point-in-time-safe な取得経路がないため、本番スコアには含めません。

### Archive

`archive/legacy/` は旧実装の参照用保管場所です。通常の変更、import、lint、test、workflow からは参照しません。再利用する場合は必要な部分だけを現行コードへ移植します。

## データと再現性

現行 scan の出力先:

```text
dashboard/data/inflection/v3/YYYY-MM-DD.enc
dashboard/data/inflection_candidates.enc
```

- 日付キーは実行日ではなく `latest_price_date`
- 日次ファイルは同じ市場日には上書きしない
- 候補情報は Fernet で認証付き暗号化
- `strategy_version`、schema version、Git SHA、scan parameters、主要ライブラリの version を保存
- J-Quants の宣言したプラン・遅延を metadata に明記（Free は12週間以上。API取得可能時刻が不明な遅延境界日の開示は除外）
- 専用の `SNAPSHOT_ENCRYPTION_KEY` は必須。`JQUANTS_API_KEY` への fallback はない
- snapshot・latest・評価成果物は単一ファイルごとに atomic write。複数ファイル全体の transaction は保証しない

REQ-018適用後のsnapshotはstrategy v3として`inflection/v3/`へ分離します（schema 4、2026-10-01以降はschema 5）。schema 5はschema 4のcandidateに生の財務特徴量・スコア内訳・`pre_score`・33業種コードを追加し、別キー`control_sample`に流動性通過銘柄からの無作為抽出（日付由来のseedで決定的）を保存します。forward validationはschema 4と5を同一系列として読み、`control_sample`は評価・学習の入力に混ぜません。既存v2 snapshotは保持しますがv3のforward validationには混在させないため、評価系列は非連続です。

週次検証は暗号化済み snapshot を `EARLY_CANDIDATE`・`WATCH`・`NONE` の群に分け、翌営業日始値で entry（その日に始値が無い銘柄は次に始値がある日で entry し、診断の `entry_delay_sessions` に遅れた営業日数を記録）、5 / 20 / 60 / 126 / 252 営業日保有、往復コスト 0.2%（ストレス1.2%）で評価します。TOPIX ETF (`1306.T`、往復コスト0.05%) と比較し、市場別ベンチマーク（グロースは `2516.T`、プライム・スタンダードは `1306.T`）も併記します。追加ETFの取得失敗は市場別比較の欠損として扱います。

候補の確認方法は2つあります。(1) 日次 scan は候補のダイジェスト（EARLY_CANDIDATE 上限10件、WATCH 上位5件、件数、欠損営業日の警告）を`SLACK_WEBHOOK_URL`へ送ります。`dashboard/data/inflection/digest_state.json` の市場日別 `pending` は通常再実行で再送し、`succeeded` は送信を省略します。状態のない旧snapshotは通常再送しません。`workflow_dispatch` の `resend_digest=true` は明示再送で、再scanのreportを使うため元snapshotと内容が異なり得ます。Slack送信失敗はbest-effortですが、状態ファイルの初回保存失敗はrunを失敗させます。処理順はsnapshot・latest保存→通知状態とSlack送信→workflowのGit反映です。Slack受理後に状態保存やpushが失敗すると重複し得るため、exactly-onceは保証しません。公開ログに候補銘柄は出しません。(2) ローカルでは`SNAPSHOT_ENCRYPTION_KEY`を設定して`python scripts/show_candidates.py`を実行すると、最新または`--date`指定の snapshot を復号して表で表示します（`--classification`、`--top`、`--control`。外部通信はしません）。

snapshotの各candidateの`features`には、スコアに使わない診断値も記録します（開示・予想修正からの経過日数、20日の最大日次リターン、20日・60日の上昇日割合、20日の日次ボラティリティ、高値からの距離）。後から再現できない値を今のうちから蓄積するためで、スコア・分類・候補は変わりません。forward validationのレポートには、東証の営業日とsnapshotを突き合わせた`session_coverage`（欠けた営業日。終点は実行時点で確定しているはずの最新営業日）が入ります。

EDINETの大量保有報告の取得・live scanへの診断値記録・learningのfactor接続は実装済みで、fake/unit testで検証しています。`EDINET_API_KEY` があるとlive取得を試み、取得失敗・未設定は欠損として扱い、スコアへは採用しません。過去検証への接続は、後日消去される提出情報を復元できないため見送りです。実APIの発行会社対応等は2026-10-07のprobeメモで確認済みですが、本番での継続取得・Slack配信までの統合は今回未確認です。

自己改善学習はschema 3〜5の暗号化snapshotから全区分のcandidateを読み、strategy versionをまたいで5 / 20 / 60 / 120営業日の事後成績を集計します。未対応schemaや不正なmetadata・candidate型はfail closedで拒否し、学習結果は次期strategy versionへの提案に限定して本番の重みを自動更新しません。

過去検証（ローカル専用・評価のみ）は`scripts/run_inflection_historical_backtest.py`で実行します。J-Quants Freeの過去データ（約2年分）を`.data/jquants/`へ再開可能に取得（`--fetch`）し、現行v3のロジックを過去の各営業日にpoint-in-timeで再現して（`src/evaluation/inflection_historical.py`）forwardと同じ評価器で集計します。財務を開示当日から使える場合と12週後から使える場合（現行Freeの状態）を比較し、60営業日の対TOPIX超過リターンの信頼区間による撤退条件の一次判定（暫定基準: 独立観測100件以上）を出力します。閾値・重みの探索は行わず、取得データと出力（`artifacts/`）はgit管理外です。Freeプランの2年という期間のため、60営業日の成績まで確定する期間は約1か月分にとどまります。

ポートフォリオ評価は `EARLY_CANDIDATE` の60営業日保有・通常コストだけを対象に、初期資金300万円、最大8銘柄、1銘柄12.5%の固定配分で算出します。これらはユーザー未確認の既定値です。セクター上限、100株単位、ADVによる発注制限は未実装です。終値欠損は前方補完せず、その日のequityと期間のMax Drawdownを欠損にします。最終日のequityが不明ならCAGRも欠損です。CAGRとMax Drawdownは十分なsnapshot蓄積後にのみ意味を持ちます。

## 設定・依存関係

- Python 3.11 以上
- Python の正規 package metadata: `pyproject.toml`
- secrets / 環境変数の一覧: `.env.example`

標準セットアップ:

```bash
python -m pip install uv==0.9.21
uv sync --frozen --extra dev
source .venv/bin/activate
```

現行 JP scan の必須secretは `JQUANTS_API_KEY` と固定の `SNAPSHOT_ENCRYPTION_KEY` です。Slack配信には `SLACK_WEBHOOK_URL`、EDINET診断には `EDINET_API_KEY` を追加します。Position Monitorは `GOOGLE_CREDENTIALS_JSON`・`GOOGLE_SHEET_ID` と、通常実行では `SLACK_WEBHOOK_URL` が必須です（`--dry-run` だけはSlack不要。ただしSheets書込みは行う）。`.env.example` は名前と例を示すだけで、CLIは `.env` を自動読込みしません。実行環境へexportしてください。

`JQUANTS_PLAN` は `free` / `light` / `standard` / `premium`、`JQUANTS_DATA_DELAY_WEEKS` は非負整数です。省略時はFreeが12週、他プランが0週。Freeで12未満、未知のプラン、不正な整数は設定エラーとなり、usableな値へ補正しません。日次workflowは現在 `free` / `12` を指定しています。

## CI / 運用

| Workflow | 役割 |
|---|---|
| `test.yml` | Python regression、ruff、現行経路の mypy と coverage |
| `inflection_shadow.yml` | 平日16:40 JSTのscan（main限定）、暗号化snapshot・通知状態のcommit、Slackダイジェスト。手動実行で `resend_digest` 指定可 |
| `forward_validation.yml` | 日曜09:30 JSTとmainの手動実行で暗号化snapshotを評価（復号stepはmain限定。ブランチの手動実行とPR（fork含む）はsecret不要の回帰テストのみ）。learning・price hash pushはscheduleのみ |
| `position_monitor.yml` | 平日09:20 / 12:50 / 15:35 / 15:50 JSTのstop監視・引け確認。mainの手動実行可。Google Sheets更新とSlack通知は実装・fake検証済みで、実サービスの再確認は未実施 |
| `reliability_watchdog.yml` | 毎日20:10 JSTとmainの手動実行でworkflowの失敗・未起動・snapshot欠落を確認しSlack通知 |

scheduleはbest-effortです。scanもMonitorもmain限定（scanはブランチから手動実行してもジョブがスキップされ、本番のsecret・Slack・pushを使いません。ブランチでの確認はローカル実行かテストで行います）で、concurrencyはscanがref別、Monitorが `position-monitor-production`、障害通知とWatchdogは `workflow-reliability-notifications` で直列化し、いずれも実行中のcancelをしません。Testはref別で古いrunをcancelします。Action参照はSHA固定、依存は `uv.lock` の `uv sync --frozen` から導入します。`contents: write` の明示付与はsnapshotをpushするscan jobと週次hash保存jobだけで、障害通知・Watchdogは `actions: read` / `contents: read`。Testにはworkflow/jobの明示permissions指定がありません。secretは必要stepへ渡し、`pull_request_target` は使いません。

Monitorは前回の `as_of_at` を検証済みcheckpointとして、未評価区間のstop接触を回収します。引け足が不足する状態は `incomplete` で、stop非接触の確認ではありません。1分足の保持期間（30日）より古い未評価の営業日は日足で保守的に判定し、安値が stop 水準以下なら `recovered_daily_possible_touch`（接触の可能性。日中の順序は不明なので誤報があり得る）として1回だけ通知、上回っていれば接触なしとして先へ進みます。`triggered_at`・`last_notified_at`・`last_warned_at` を保持し、通知・Sheets保存の片方だけ成功した境界は手動確認が必要です。branch・通常のローカル実行はproduction writer制限で拒否されます。Watchdogの2時間grace、通知cache消失時の重複、Actions全体停止時の限界は `docs/playbooks.md` を参照してください。

ローカルの主な確認コマンド:

```bash
python -m pytest tests/
ruff check src scripts tests
python scripts/run_inflection_shadow.py
```

本番 scan は外部 API を利用し、暗号化 snapshot を書き出します。単なる動作確認として無断実行しないでください。

## 保守時の判断基準

- 現行戦略の変更は `inflection_live.py`、`inflection.py`、日次 snapshot、forward validation を一組として確認する。
- snapshot schema や暗号鍵を変える場合は、過去 `.enc` の復号互換性を先に決める。
- `archive/legacy/` は参照専用とし、旧経路をそのまま復活させない。
- 確認済みの問題は `review.md` を参照する。
