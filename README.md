# Trader

日本株の短期変化点（inflection）候補を日次で抽出し、将来検証できる形でスナップショットを保存する Python プロジェクトです。

現在の本番経路は **TSE Prime / Standard / Growth の日次 inflection shadow scan** です。旧 Prophet / LightGBM の週次予測パイプラインは `archive/legacy/` に隔離しています。

## 現在の本番フロー

GitHub Actions の `.github/workflows/inflection_shadow.yml` が平日 16:40 JST に実行されます。

1. J-Quants V2 から Prime / Standard / Growth の上場銘柄を取得
2. yfinance から価格・出来高を取得
3. 流動性と短期モメンタムで全銘柄を一次選別
4. 上位候補のみ J-Quants 財務データで深掘り
5. `EARLY_CANDIDATE` / `WATCH` / `OVEREXTENDED` / `NONE` に分類
6. データ健全性を検証
7. 市場データ日をキーに、暗号化したimmutable snapshotと最新候補を保存
8. 失敗時のみ Slack 通知

出力:

```text
dashboard/data/inflection/YYYY-MM-DD.enc   # encrypted immutable market-day snapshot
dashboard/data/inflection_candidates.enc   # encrypted latest snapshot
```

snapshot の日付は **workflow実行日ではなく `latest_price_date`** です。祝日や同日再実行で同じ市場データを再取得しても、既存snapshotは上書きせず、重複signalを作りません。

公開リポジトリ上には候補銘柄やJ-Quants由来の分析結果を平文保存しません。Fernetによる認証付き暗号化を行い、API認証情報とは独立した固定の `SNAPSHOT_ENCRYPTION_KEY` を必須とします。この値を変更すると過去snapshotを復号できなくなるため、ローテーション時は既存データの再暗号化が必要です。

`EARLY_CANDIDATE` は調査候補であり、売買推奨や自動発注シグナルではありません。

## J-Quants Freeの扱い

現在の運用は J-Quants Free を前提とし、財務データの約12週間遅延をsnapshot内の `data_policy` に記録します。現在はshadowデータ蓄積期間なので、この遅延データを使ったsignalは「その時点でFree利用者が観測できたsignal」として保存します。

この期間の成績を、最新決算を即時利用できるリアルタイム戦略の成績とは扱いません。

## スコアリング

本番 scanner は、現時点で安全に取得できる以下の情報だけを使用します。

- 売上成長
- 営業利益成長
- 営業利益率改善
- 黒字転換
- 業績予想上方修正
- 20日 / 60日リターン
- 出来高増加
- 52週高値圏
- 極端な上昇や営業CF悪化のリスクペナルティ

財務比較では、業績予想修正のみの行を最新実績として扱わず、前年の同一期間実績が存在する場合だけYoY比較します。同一年度の訂正値を前年同期として代用しません。

ニュース、提携、大口受注、新規事業などの catalyst は、point-in-time-safe な取得経路が接続されるまで本番スコアから除外しています。

## 再現性

各snapshotには以下を記録します。

- `strategy_version`
- `report_schema_version`
- `source_commit_sha`
- scan parameter
- J-Quants plan / delay weeks
- yfinance / pandas / requests / cryptography の実行時version

本番・テストの主要Python依存関係は `pyproject.toml` でCI確認済みversionへ固定しています。

## データソース

| データ | 本番利用 | 用途 |
|---|---:|---|
| J-Quants V2 Free | Yes | 日本株ユニバース、遅延財務情報 |
| yfinance | Yes | 価格・出来高 |

本番実行に必要な GitHub Secret は `JQUANTS_API_KEY` と `SNAPSHOT_ENCRYPTION_KEY` です。Slack失敗通知を使う場合は `SLACK_WEBHOOK_URL` も設定します。

yfinance は単一providerであり、分割・配当調整漏れ、欠損・破損データ、通貨単位の100倍誤りを完全には検出できません。当面はこのリスクを受容し、cross-provider照合は行いません。異常値検知を追加する場合は、分割情報を取得・伝搬した上で誤検知を避ける設計が必要です。

## GitHub Actionsの運用方針

`main`のbranch protectionは無効で、Shadow ScanとForward Validationのschedule jobは暗号化された生成データだけを`main`へ直接pushします。ソースコードは変更しないため、このdirect pushを意図的に許容しています。

Actionsはfull commit SHAへ固定せず、既存のversion tagを継続利用します。Dependabotも導入しません。個人プロジェクトでの保守負担を優先した決定であり、第三者Action追加や運用規模拡大時に再検討します。

## データ健全性

保存前に以下を検証し、条件を満たさない実行は失敗扱いにします。

- TSE対象ユニバース数
- 価格取得coverage
- 65営業日以上使えるtechnical coverage
- 最新市場日の一致率
- candidate件数整合性・ticker重複
- strategy/schema/source commit metadata
- 主要runtime dependency metadata

J-Quants clientはFreeの5 calls/minを考慮した間隔制御に加えて、429/5xx、`Retry-After`、Timeout、ConnectionErrorを再試行します。yfinanceもbatch失敗・partial batchを再試行し、`auto_adjust=False` / `actions=False` を明示します。

## Forward Validation

新inflection戦略は、蓄積した暗号化snapshotから **`EARLY_CANDIDATE` のみ** を復号して評価します。

評価ルールは結果を見る前に固定しています。

- signal date: snapshotの `latest_price_date`
- entry: 翌営業日始値
- holding: 5 / 20 / 60営業日
- total execution cost: 通常0.2% / 悲観1.2%
- benchmark: `1306.T`（NEXT FUNDS TOPIX ETF）
- benchmarkも同じ翌営業日始値・同じholding・同じ取引コスト
- Closeベースの最大上昇・drawdownと、High/LowベースのMFE/MAEを分離して保存
- strategy return、TOPIX return、excess return、benchmark勝率を保存
- 10% / 15% / 20%のTrailing Stopを、最大60営業日の固定保有と比較
- 固定期間評価は配当込み調整価格、Trailing Stop評価はlive monitorと同じ分割のみ調整した価格を使用
- Trailing Stopは60営業日を経過したsignalの集計と、未成熟signalを含む参考集計を分離
- 同一銘柄の重複signalは、`position_summary` では一つの保有が終了するまで再entryしない

板厚、売買停止、制限値幅による約定確率は未モデル化のため、reportの `execution_limitations` に明記します。

Trailing Stopは前日までの確定済みHigh Water Markから計算します。Stopを下回って寄り付いた場合はStop価格ではなく当日始値で退出し、同日Highを同日Lowより先に観測したと仮定しません。

`.github/workflows/forward_validation.yml` は週次で蓄積snapshotを検証します。snapshotがまだ存在しない期間、または有効な `EARLY_CANDIDATE` がない期間は正常終了します。
銘柄別のtrade行を除いた集計結果は、90日間保持するGitHub Actions artifact `inflection-forward-summary` で確認できます。
評価に使ったOHLCの日次hashは暗号化して保存し、週次実行で過去行の事後訂正を検知します。公開ログには候補tickerを出しません。

## Position Exit Monitor

SBI証券で手動保有している銘柄をGoogle Sheetsから読み、既存backtestと同じ「前日までのHigh Water Mark・当日gap・当日Low到達」の順序でTrailing Stop条件を確認します。自動発注は行いません。

平日9:03 / 12:35 / 15:35 JSTにGitHub Actionsで実行します。GitHub Actionsのscheduleはbest-effortであり、遅延・省略される可能性があるため厳密な定刻監視ではありません。TSE休場日は価格取得前に正常終了します。

Googleスプレッドシートには、次の2つのタブを事前に作成し、サービスアカウントのメールアドレスへ編集権限を付与します。

- `保有銘柄`（手動編集）: `ticker`, `entry_date` (`YYYY-MM-DD`), `entry_price`, `trailing_stop_pct`（任意、既定15%）
- `状況`（システムが毎回上書き）: `ticker`, `entry_date`, `entry_price`, `current_price`, `high_water_mark`, `stop_price`, `trailing_stop_pct`, `unrealized_pct`, `distance_to_stop_pct`, `triggered`, `exit_reason`, `as_of_at`, `quote_source`, `status`, `error`

必要なGitHub Secretは `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_SHEET_ID`, `SLACK_WEBHOOK_URL` です。サービスアカウントではGoogle Sheets APIを有効化し、JSONキーの内容全体を `GOOGLE_SERVICE_ACCOUNT_JSON` に登録します。

live monitorは実約定単価に合わせ、配当調整なし・株式分割のみ補正した価格を使います。forward validationのTrailing Stop評価も同じ価格基準ですが、十分な成熟signalが蓄積するまで既定15%は暫定の検証用アラートであり、確定した売買判断ではありません。

一部銘柄の欠測は `状況` とSlackへ通知して残りを継続します。全銘柄の価格欠測、シート書込失敗、Slack送信失敗は監視停止としてworkflowを失敗させます。状況タブは履歴・監査ログではなく現在地を表示するダッシュボードです。

Slackを送らず状況タブだけを更新するローカル確認は、次で実行します。休場日または市場時間外の手動実行は、正常skipまたはstaleエラーになります。

```bash
python scripts/run_position_monitor.py --dry-run
```

## セットアップ

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

python -m pip install -e ".[dev]"
```

`.env.example` を参考に環境変数を設定します。

ローカルで本番 scanner を実行する場合:

```bash
python scripts/run_inflection_shadow.py
```

## テスト

```bash
python -m pytest tests/
ruff check src scripts tests
```

GitHub Actions の `test.yml` では、全 regression suite と coverage、ruff、本番 inflection 経路の mypy type check を実行します。

## Archive

以前の週次予測、GUI、Docker、設定、データ、テストは `archive/legacy/` に退避しています。現行の実行・CI 対象には含めません。

現時点では暗号化済み `inflection_candidates.enc` を表示・通知へ接続する consumer はありません。shadow scan の目的は、まずデータを安全に蓄積し、再現可能な forward validation を成立させることです。
