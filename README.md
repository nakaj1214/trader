# Trader

日本株の短期変化点（inflection）候補を日次で抽出し、将来検証できる形でスナップショットを保存する Python プロジェクトです。

現在の本番経路は **TSE Prime / Standard / Growth の日次 inflection shadow scan** です。旧 Prophet / LightGBM の週次予測パイプラインはコードとして残していますが、本番スケジュールでは実行しません。

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

公開リポジトリ上には候補銘柄やJ-Quants由来の分析結果を平文保存しません。Fernetによる認証付き暗号化を行い、`SNAPSHOT_ENCRYPTION_KEY` を設定した場合はそのキーを使用します。未設定時は、最初の定期実行を止めないため、既に必須の `JQUANTS_API_KEY` を暗号化キー素材としてフォールバック利用します。J-Quants APIキーを変更する前に専用の `SNAPSHOT_ENCRYPTION_KEY` を設定しておくことを推奨します。

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
| EDINET API v2 | No | point-in-time 検証用ユーティリティ。live scan には未接続 |
| Finnhub / FMP / FRED | No | 旧パイプライン向け補完機能 |

本番実行に必要な GitHub Secret は `JQUANTS_API_KEY` です。暗号化専用の `SNAPSHOT_ENCRYPTION_KEY` は推奨、Slack失敗通知を使う場合は `SLACK_WEBHOOK_URL` も設定します。

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
- round-trip cost: 0.2%
- benchmark: `1306.T`（NEXT FUNDS TOPIX ETF）
- benchmarkも同じ翌営業日始値・同じholding・同じ取引コスト
- strategy return、TOPIX return、excess return、benchmark勝率を保存

`.github/workflows/forward_validation.yml` は週次で蓄積snapshotを検証します。snapshotがまだ存在しない期間、または有効な `EARLY_CANDIDATE` がない期間は正常終了します。

旧 `predictions_jp.json` のforward validationも比較用に残しますが、その過去成績を新inflection戦略の実績として扱いません。

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

GitHub Actions の `test.yml` では、全regression suite、本番inflection経路、J-Quants/yfinance、暗号化、point-in-time、forward validationのcoverageに加え、本番inflection経路のmypy type checkを実行します。

## 旧パイプライン

以下は既存機能との比較・調査用途としてリポジトリに残っています。

- `python -m src.cli run`
- US / Nikkei225 screening
- Prophet / LightGBM prediction
- enrichment / notification / Google Sheets
- legacy dashboard data
- `config/default.yaml` の多くの設定

これらは現在の日次 JP inflection production workflow からは呼ばれません。

## Dashboard

`dashboard-v2` は SvelteKit でビルドされます。Cloudflare Pages への公開は GitHub Actions 内の明示的 deploy step ではなく、リポジトリ連携側の設定に依存します。

現時点では暗号化済み `inflection_candidates.enc` を表示・通知へ接続するconsumerは本番経路に含めていません。shadow scan の目的はまずデータを安全に蓄積し、再現可能なforward validationを成立させることです。
