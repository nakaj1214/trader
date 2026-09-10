# Trader プロジェクト概要

最終確認日: 2026-09-08

## 目的と現在地

Trader は、株価・出来高・財務情報から調査候補を抽出し、その後の成績を検証する Python プロジェクトです。

現在の正規の本番経路は、日本の Prime / Standard / Growth 市場を対象にした日次の **inflection shadow scan** です。これは売買や自動発注を行う仕組みではなく、短期的な変化の初期候補を記録し、将来データで戦略の有効性を評価するための観測系です。

Prophet / LightGBM を中心とする旧予測パイプライン、SQLite / Google Sheets、Slack / LINE、旧 JSON ダッシュボードは `archive/legacy/` に隔離しており、実行・package・CI の対象外です。

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
| forward validation | `src/evaluation/inflection_forward.py`, `src/evaluation/inflection_backtest.py` |

スコアは、売上・営業利益・利益率・黒字転換・上方修正などのファンダメンタル、20日 / 60日リターン・出来高・52週高値などのモメンタム、過熱・営業 CF などのリスクを合成します。ニュースや材料は point-in-time-safe な取得経路がないため、本番スコアには含めません。

### Archive

`archive/legacy/` は旧実装の参照用保管場所です。通常の変更、import、lint、test、workflow からは参照しません。再利用する場合は必要な部分だけを現行コードへ移植します。

## データと再現性

現行 scan の出力先:

```text
dashboard/data/inflection/YYYY-MM-DD.enc
dashboard/data/inflection_candidates.enc
```

- 日付キーは実行日ではなく `latest_price_date`
- 日次ファイルは同じ市場日には上書きしない
- 候補情報は Fernet で認証付き暗号化
- `strategy_version`、schema version、Git SHA、scan parameters、主要ライブラリの version を保存
- J-Quants Free の約 12 週間遅延を metadata に明記
- 専用の `SNAPSHOT_ENCRYPTION_KEY` を推奨し、未設定時のみ `JQUANTS_API_KEY` を鍵素材に利用

週次検証は暗号化済み snapshot から `EARLY_CANDIDATE` のみを読み、翌営業日始値で entry、5 / 20 / 60 営業日保有、往復コスト 0.2%、TOPIX ETF (`1306.T`) 比較という固定ルールで評価します。

## 設定・依存関係

- Python 3.11 以上
- Python の正規 package metadata: `pyproject.toml`
- secrets / 環境変数の一覧: `.env.example`

標準セットアップ:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

現行 JP scan の最低限の secret は `JQUANTS_API_KEY` です。

## CI / 運用

| Workflow | 役割 |
|---|---|
| `test.yml` | Python regression、ruff、現行経路の mypy と coverage |
| `inflection_shadow.yml` | 平日の日次 scan、暗号化 snapshot の commit、失敗時 Slack 通知 |
| `forward_validation.yml` | 週次および関連 PR の forward validation |
| `position_monitor.yml` | 平日3回（9:03/12:35/15:35 JST、best-effort）のPosition Exit Monitor。保有銘柄（Googleスプレッドシート）のTrailing Stop状況を評価しSlack通知（実装済み・本番運用中） |

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
