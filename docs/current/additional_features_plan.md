# proposal.md確認後 追加機能計画書

作成日: 2026-02-18  
対象: `docs/archive/memo/proposal.md`

## 1. proposal.md チェック結果

### 1.1 要件棚卸し

- 追加機能要件
  - 通知強化: `LINE二重通知` または `Slack確認ボタン + 未確認時1分おきリマインド`
  - GUI化: Cloudflare上で動く静的Webサイトで可視化
- 疑問点（回答必須）
  - SBI/楽天GUIで十分か
  - OpenAI/Gemini/Claude併用の効果
  - 3APIの月額コスト
  - 木曜+日曜運用の精度影響
  - 1万円スタートの妥当性
- 現行実装との差分
  - 現行通知は Slack が主、LINE は補助通知（`src/notifier.py`, `src/line_notifier.py`）
  - Slackは Webhook-only 構成で、ボタン押下イベントは受けられない
  - GUI (`dashboard/`) は未実装
  - 定期実行は日曜1回（`.github/workflows/weekly_run.yml`）

### 1.2 整合/不整合

- 整合
  - LINE併用の方向性は現行実装に沿う
  - Cloudflare静的GUIの方向性は既存計画（`plan_cloudflare_pages.md`）と整合
- 不整合
  - Slack確認ボタンは Webhook-only では不可（Slack App/Bot化が必要）
  - 「OpenAIでニュース収集」は現行コード未実装（将来Phase扱い）

## 2. 追加機能ロードマップ（Phase 1〜3）

### Phase 1（短期）: LINE二重通知の実運用化

目的: 通知見逃しリスクの低減を、現行構成の範囲で実現する。

実施内容:
- 現行の LINE 補助通知を正式運用仕様として文書化
- `config.yaml` の `line.enabled` の運用ルールを定義
- 失敗時方針を明確化: Slack成功を優先し、LINE失敗でジョブ全体は失敗にしない

受け入れ条件:
- `line.enabled=true` で Slack後にLINE通知が送られる
- LINE API失敗時でもワークフローの主処理は継続

### Phase 2（中期）: Slack確認ボタン + 未確認リマインド

目的: 「見た/未確認」をシステムで判定し、未確認時のみ再通知する。

前提:
- Webhook-only では実現不可のため Slack App/Bot を追加採用する

追加予定インターフェース:
- 環境変数
  - `SLACK_BOT_TOKEN`
  - `SLACK_SIGNING_SECRET`
- 設定
  - `notifications.slack_ack.enabled`
  - `notifications.slack_ack.remind_interval_min`
  - `notifications.slack_ack.max_reminds`

仕様:
- 初回投稿に「確認済み」ボタンを付与
- ボタン未押下なら1分間隔で再通知
- `max_reminds` 到達で停止（無限通知防止）
- 状態管理は KV/DB を使用（Cloudflare KV想定）

受け入れ条件:
- 押下済みメッセージには追加リマインドが出ない
- 未押下メッセージのみ指定回数内でリマインドされる

### Phase 3（中期）: Cloudflare静的GUI

目的: 表形式中心の閲覧から、可視化中心の運用に移行する。

仕様:
- `dashboard/` 配下に静的ページを作成（Chart.js）
- 週次エクスポートで `predictions.json` / `accuracy.json` / `stock_history.json` を生成
- ルーティングは静的互換の `stock.html?ticker=...` で統一

受け入れ条件:
- Cloudflare Pagesで自動デプロイできる
- 予測推移・的中率推移・銘柄詳細が閲覧できる

## 3. 仕様（通知、GUI、スケジュール）

### 3.1 通知仕様

- 本番の主通知は Slack
- LINE は補助通知
- 将来Phaseで Slack App/Bot を追加し、確認ボタン方式へ拡張

### 3.2 GUI仕様

- 配信基盤: Cloudflare Pages
- 表示: 週次サマリー、的中率推移、銘柄別推移
- データ供給: GitHub Actions で JSON を更新

### 3.3 スケジュール仕様

- 本番デフォルト: 日曜1回実行を維持
- 木曜+日曜は「精度向上を前提にしない検証運用」として定義
- 比較期間: 8〜12週間
- 比較指標:
  - 的中率
  - 最大ドローダウン
  - 通知ノイズ（通知数/確認率）
  - 手数料控除後損益

## 4. リスク・運用ルール・受け入れ条件

### 4.1 主なリスク

- Slack App導入でSecrets/権限管理が複雑化
- リマインド過多による運用疲れ
- GUI化後のデータ整合性崩れ（SheetsとJSON）
- 木曜追加実行で売買回数増加に伴う手数料影響

### 4.2 運用ルール

- 運用開始は Phase 1 から（段階導入）
- Phase 2 は「確認ログの保存先」が確定してから着手
- Phase 3 は exporter 仕様を先に固定してからUI実装
- 週2回運用は検証期間が終了するまで本番固定化しない

### 4.3 ドキュメント受け入れ条件

- `proposal.md` の追加機能要望が全て本計画に反映されている
- 現行実装との差分が明示されている
- 将来拡張に必要な公開インターフェース変更が明記されている

## 5. 公開インターフェース変更（計画）

- `config.yaml` に通知制御セクション追加予定
- `.env.example` に Slack Bot 用シークレット追加予定
- `.github/workflows/weekly_run.yml` に週2回検証運用の記述追加予定（採用時のみ）

## 6. トレーサビリティ表（proposal.md -> 本計画）

| proposal.md の要求 | 本計画の反映先 |
|---|---|
| LINE二重通知 | 2章 Phase 1 / 3.1 |
| Slack確認ボタン+1分リマインド | 2章 Phase 2 / 5章 |
| Cloudflareで静的GUI | 2章 Phase 3 / 3.2 |
| 木曜+日曜運用の効果検証 | 3.3 |
| 実装との整合確認 | 1.2 / 4.3 |
