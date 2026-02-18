# docsレビュー結果

対象:
- `docs/PLAN.md`
- `docs/stock_prediction_comparison.md`

## Findings（重大度順）

### High

1. Slack実装方針が矛盾しており、このままでは`/stock-help`が実装不可
- 根拠: `docs/PLAN.md:69` は Incoming Webhook 前提。一方で `docs/PLAN.md:133` はインタラクティブUI、`docs/PLAN.md:145` は Slash Command、`docs/PLAN.md:334` は Slack Bot 前提。
- 影響: Webhookだけでは Slash Command/対話応答を実装できず、要件を満たせない。
- 修正案: `Webhook-only` に機能を縮退するか、Slack App(Bot)を正式採用するかを先に確定する。

2. 認証情報設計が機能要件に不足
- 根拠: `docs/PLAN.md:367` の Secrets 一覧に `SLACK_BOT_TOKEN` と `SLACK_SIGNING_SECRET` がない。
- 影響: Bot/Slash Command を有効化できない。
- 修正案: Secrets表とセットアップ手順を Bot 構成に合わせて更新する。

### Medium

3. OpenAI利用方針が文書間で不整合
- 根拠: `docs/PLAN.md:67` と `docs/PLAN.md:84` は `gpt-4o-mini` 前提の低コスト補助利用。`docs/stock_prediction_comparison.md:8` と `docs/stock_prediction_comparison.md:34` は GPT-4o 前提の高コスト想定。
- 影響: モデル選定、予算感、実装優先度の判断がぶれる。
- 修正案: 本プロジェクト採用モデルを1つ明記し、比較資料は「参考条件」を明示する。

4. 価格・性能前提の鮮度が不明
- 根拠: `docs/PLAN.md:83` と `docs/stock_prediction_comparison.md:32` の単価、`docs/stock_prediction_comparison.md:19` のカットオフ記述に確認日がない。
- 影響: 時間経過で見積と運用実態が乖離する。
- 修正案: 各数値に「最終確認日」を追記し、定期見直しタスクを追加する。

5. Prophetセットアップ手順が古い可能性
- 根拠: `docs/stock_prediction_comparison.md:142` が `pip install pystan prophet` を案内。
- 影響: 環境によっては導入失敗や不要依存の追加を招く。
- 修正案: 検証済みのインストール手順とバージョンを明記する。

6. 実行タイミングと評価ロジックの基準時刻が曖昧
- 根拠: `docs/PLAN.md:54` と `docs/PLAN.md:363` は毎週日曜実行、`docs/PLAN.md:279` は現在価格で実績判定。
- 影響: 休場日や市場タイムゾーンの差で判定の再現性が下がる。
- 修正案: 判定基準を「対象市場の最終営業日終値」などで固定する。

### Low

7. フェーズ説明の連続性が崩れている
- 根拠: `docs/PLAN.md:226` で Phase 1 を説明した後、`docs/PLAN.md:242` で Phase 3 に飛んでいる。
- 影響: 実装順序の理解がしづらい。
- 修正案: Phase 2（scikit-learn統合）をステップ2節にも追記する。

8. `yfinance`で指数構成銘柄を直接取得する前提が強い
- 根拠: `docs/PLAN.md:198`。
- 影響: 実装時に銘柄ユニバース取得で詰まりやすい。
- 修正案: 構成銘柄ソース（静的リスト/別API）を別途定義する。

## Open Questions

1. Slack連携は `Webhook-only` と `Bot/Slash Command対応` のどちらを正式スコープにしますか。
2. OpenAIモデルは `gpt-4o-mini` 固定で進めますか（比較資料は参考用途に限定）。

## 変更サマリ

- docs配下2ファイルをレビューし、重大度付きの指摘8件を整理。
- 実装ブロッカーになり得る Slack 設計矛盾を最優先課題として特定。
