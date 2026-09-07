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
7. 日次スナップショットと最新候補を保存
8. 失敗時のみ Slack 通知

出力:

```text
dashboard/data/inflection/YYYY-MM-DD.json   # immutable daily snapshot
dashboard/data/inflection_candidates.json   # latest snapshot
```

`EARLY_CANDIDATE` は調査候補であり、売買推奨や自動発注シグナルではありません。

## スコアリング

本番 scanner は、現時点で point-in-time に取得できる以下の情報だけを使用します。

- 売上成長
- 営業利益成長
- 営業利益率改善
- 黒字転換
- 業績予想上方修正
- 20日 / 60日リターン
- 出来高増加
- 52週高値圏
- 極端な上昇や営業CF悪化のリスクペナルティ

ニュース、提携、大口受注、新規事業などの catalyst は、point-in-time-safe な取得経路が接続されるまで本番スコアから除外しています。

## データソース

| データ | 本番利用 | 用途 |
|---|---:|---|
| J-Quants V2 | Yes | 日本株ユニバース、財務情報 |
| yfinance | Yes | 価格・出来高 |
| EDINET API v2 | No | point-in-time 検証用ユーティリティ。live scan には未接続 |
| Finnhub / FMP / FRED | No | 旧パイプライン向け補完機能 |

本番実行に必要な GitHub Secret は `JQUANTS_API_KEY` です。Slack失敗通知を使う場合は `SLACK_WEBHOOK_URL` も設定します。

## 検証

`src/evaluation/` には以下を用意しています。

- immutable signal を使う inflection backtest
- 翌営業日始値での約定シミュレーション
- TOPIX proxy との benchmark 比較
- 取引コスト、税引き、最大上昇率、最大ドローダウン
- 旧予測データの git 履歴からの forward validation
- point-in-time filtering / OHLCV validation

新しい inflection 戦略については、日次スナップショットが蓄積した後に forward validation を行う前提です。過去の旧予測パイプラインの成績を、新戦略の実績として扱わないでください。

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

GitHub Actions の `test.yml` では、全 regression suite に加えて、本番 inflection 経路・J-Quants client・point-in-time / validation / evaluation の coverage を確認します。

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

現時点では `inflection_candidates.json` を表示・通知へ接続する consumer は本番経路に含めていません。shadow scan の目的はまずデータを蓄積し、再現可能な forward validation を成立させることです。
