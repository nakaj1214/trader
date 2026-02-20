# サービス・ロジック一覧（改善用棚卸し）

## 目的
このプロジェクトで現在採用している外部サービス・基盤・主要ロジックを一覧化し、改善検討の起点にする。

## 対象範囲
- バックエンド: `src/`
- ダッシュボード: `dashboard/`
- 運用: `.github/workflows/weekly_run.yml`
- 設定: `config.yaml`

---

## 1. 採用サービス / 基盤一覧

| 区分 | サービス / 基盤 | 用途 | 主な利用箇所 | 現状 |
|---|---|---|---|---|
| 市場データ | `yfinance` | 株価・指標・企業情報取得 | `src/screener.py`, `src/predictor.py`, `src/tracker.py`, `src/enricher.py`, `src/exporter.py` | 稼働中 |
| 予測エンジン | `Prophet` | 週次価格予測（信頼区間含む） | `src/predictor.py` | 稼働中 |
| テクニカル指標 | `ta` | RSI / MACD 等の算出 | `src/screener.py` | 稼働中 |
| データ永続化 | Google Sheets (`gspread`, `google-auth`) | 予測・実績履歴の保存 | `src/sheets.py`, `src/tracker.py`, `src/exporter.py` | 稼働中 |
| 通知 | Slack Incoming Webhook | 週次レポート配信 | `src/notifier.py` | 稼働中 |
| 補助通知 | LINE Messaging API | Slack確認リマインド | `src/line_notifier.py`, `src/notifier.py` | 任意有効 |
| マクロデータ | FRED API | 金利・イールド・VIX取得 | `src/macro_fetcher.py`, `src/exporter.py` | APIキー時のみ稼働 |
| 可視化 | Chart.js (CDN) | グラフ描画 | `dashboard/*.html`, `dashboard/js/*.js` | 稼働中 |
| バッチ実行 | GitHub Actions | 週次実行とデータ更新 | `.github/workflows/weekly_run.yml` | 稼働中 |
| 設定管理 | `pyyaml`, `.env` | 設定 / Secrets管理 | `src/utils.py`, `config.yaml` | 稼働中 |
| 互換設定 | OpenAI APIキー | 将来拡張用（現状未使用） | `config.yaml`, `.github/workflows/weekly_run.yml`, `README.md` | 未使用 |

---

## 2. 主要ロジック一覧

| ロジック | 概要 | 入力 | 出力 | 主な実装 |
|---|---|---|---|---|
| スクリーニング | 価格変化・出来高・RSI・MACD・52週高値でスコアリングし上位抽出 | 銘柄CSV + 市場データ | Top N銘柄DF | `src/screener.py` |
| 価格予測 | Prophetで将来価格とCIを算出し、上昇予測のみ採用 | スクリーニング結果 | 予測DF | `src/predictor.py` |
| 上昇確率化 | `predicted_change_pct` と `ci_pct` から `prob_up` 算出 | 予測値 / CI | `prob_up` | `src/predictor.py`, `src/exporter.py` |
| 実績追跡 | 予測日からN営業日後の終値取得、的中判定、未取得は評価不能でクローズ | Sheets履歴 + 市場データ | 更新済みSheets + 的中率 | `src/tracker.py`, `src/sheets.py` |
| ガードレール | 予測率の警告/クリップ（`WARN_HIGH`, `CLIPPED`） | 予測率 + 閾値設定 | クリップ値 / フラグ | `src/exporter.py` |
| リスク指標 | 年率ボラ、β、最大DDの算出 | 銘柄価格 + SPY | `risk` | `src/enricher.py` |
| ポジションサイジング | ボラターゲットで最大比率と損切り水準を計算 | `vol_20d_ann` + `sizing`設定 | `sizing` | `src/enricher.py` |
| イベント注釈 | 決算日・配当落ち日を抽出 | `yf.Ticker().info` | `events` | `src/enricher.py` |
| エビデンス指標 | momentum/value/quality/low-riskのZスコア化 | 銘柄群データ | `evidence` | `src/enricher.py` |
| 選出理由 | 重みと指標から説明文を生成 | 指標 + 重み | `explanations` | `src/enricher.py` |
| Short Interest補助情報 | 空売り比率等を参考表示用に付与 | `shortRatio`, `shortPercentOfFloat` | `short_interest` | `src/enricher.py`, `src/exporter.py` |
| 機関投資家情報 | 上位保有者・機関保有率を参考表示 | `institutional_holders`, `heldPercentInstitutions` | `institutional` | `src/enricher.py`, `src/exporter.py` |
| 52週高値因子 | `current/high52` で因子スコア化し出力 | `currentPrice`, `fiftyTwoWeekHigh` | `fifty2w_score`, `fifty2w_pct_from_high` | `src/screener.py`, `src/enricher.py`, `src/exporter.py` |
| 誤差分析 | MAEと予測帯別の実績比較 | 確定済み履歴 | `accuracy.error_analysis` | `src/exporter.py` |
| 校正分析 | Brier/log-loss/ECE/reliabilityを全期間+直近で算出 | 確定済み履歴 | `accuracy.calibration` | `src/exporter.py` |
| 戦略比較 | AI vs 12-1モメンタム vs SPY比較 | 履歴 + 価格系列 | `comparison.json` | `src/baseline.py`, `src/exporter.py` |
| バックテスト品質開示 | 試行数・PBO等（現状は簡略/一部プレースホルダ） | backtest設定 + 履歴 | `backtest_hygiene` | `src/baseline.py` |
| マクロレジーム判定 | FRED系列から risk-off 判定 | FRED系列 | `macro.json.regime` | `src/macro_fetcher.py` |
| アルファサーベイ | アノマリー検証結果のJSON化（現状は`insufficient_data`中心） | アノマリー定義 | `alpha_survey.json` | `src/alpha_survey.py` |

---

## 3. 主要成果物（dashboard/data）

| ファイル | 主用途 | 生成元 |
|---|---|---|
| `predictions.json` | 最新/履歴予測表示 | `src/exporter.py` |
| `accuracy.json` | 的中率・誤差・校正表示 | `src/exporter.py` |
| `stock_history.json` | 銘柄別推移表示 | `src/exporter.py` |
| `comparison.json` | 戦略比較・品質開示 | `src/exporter.py` + `src/baseline.py` |
| `macro.json` | マクロバナー表示 | `src/macro_fetcher.py` + `src/exporter.py` |
| `alpha_survey.json` | アノマリー検証表示 | `src/alpha_survey.py` |

---

## 4. 改善検討で優先確認すべき点

1. `yfinance` 依存箇所が多いため、失敗時の代替データ戦略と再試行設計を定義する。  
2. バックテスト品質指標（PBO / Reality Check / Deflated Sharpe）は簡略実装のため、本計算への置換計画を作る。  
3. マルチ市場（US/JP）分離を進める際に、`predictions.json` 互換レイヤー（`predictions_us/jp.json` との整合）を先に設計する。  
4. OpenAI設定は現状未使用のため、利用開始か削除かの方針を明確化する。
