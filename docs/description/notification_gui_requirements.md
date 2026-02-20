# Slack + LINE 併用通知 / GUI 詳細仕様・要件定義計画書

作成日: 2026-02-18
対象リポジトリ: `trader-main`

## 1. 目的

`src` の現行コードを前提に、以下2領域の実装可能な詳細仕様と要件を定義する。

1. Slack と LINE を併用した通知機能
2. Cloudflare Pages 上で動作する GUI（可視化ダッシュボード）

本書は「実装前の仕様確定」を目的とし、コード変更は別タスクで実施する。

## 2. 現状（As-Is）整理

### 2.1 実行フロー

現行実装の処理順序は以下。

1. スクリーニング (`src/screener.py`)
2. 予測 (`src/predictor.py`)
3. 前週追跡 (`src/tracker.py`)
4. Sheets記録 (`src/sheets.py`)
5. 通知 (`src/notifier.py`)

根拠: `src/main.py`

### 2.2 通知の現状

- Slack
  - Incoming Webhook でテキスト通知（`send_to_slack`）
  - 通知本文は `build_report` で生成（上昇予測・的中率・用語メモ）
- LINE
  - `config.yaml` の `line.enabled` が true の場合のみ送信
  - Slack全文ではなく、LINE向け短文（Slack確認促進）を送信
  - LINE失敗時も全体成功判定は Slack に依存（補助通知扱い）
- スケジュール
  - GitHub Actions 日曜1回（UTC 00:00 / JST 09:00）

根拠: `src/notifier.py`, `src/line_notifier.py`, `config.yaml`, `.github/workflows/weekly_run.yml`

### 2.3 GUI の現状

- `dashboard/` は未実装
- 可視化データのエクスポート処理（`src/exporter.py`）も未実装
- データ元は Google Sheets（ヘッダは `src/sheets.py` の `HEADERS`）

## 3. To-Be（目標像）

### 3.1 通知

- Phase 1: 現行通知の運用品質向上（Slack主 + LINE補助）
- Phase 2: Slack確認ボタン + 未確認リマインド（Bot化）

### 3.2 GUI

- Cloudflare Pages で静的ダッシュボードを配信
- 予測・的中率・銘柄別推移を週次更新のJSONから表示

## 4. スコープ

### 4.1 本計画の実装対象

- Slack+LINE併用通知の仕様確定
- GUI情報設計（画面、データスキーマ、更新フロー）
- 設定・Secrets・運用ルールの定義
- テストと受け入れ基準の定義

### 4.2 非スコープ

- 売買自動執行
- LLMによるニュース収集ロジック実装
- GUIの本番デザイン最適化（UI微調整）

## 5. 通知機能 要件定義

### 5.1 機能要件（通知）

| ID | 要件 | 優先度 |
|---|---|---|
| NTF-01 | Slack通知を主経路として週次送信する | Must |
| NTF-02 | LINE通知を補助経路として同一実行内で送信可能にする | Must |
| NTF-03 | LINE送信失敗時でも Slack成功ならジョブは成功扱いにする | Must |
| NTF-04 | LINEメッセージに「レポート到着」「銘柄数」「Slack確認導線」を含める | Must |
| NTF-05 | 通知有効/無効を設定で切り替え可能にする | Must |
| NTF-06 | Slack確認ボタンと未確認リマインドを将来拡張として実装可能にする | Should |
| NTF-07 | 通知ログ（成功/失敗、ステータスコード、通知先）を構造化出力する | Should |

### 5.2 通知仕様（Phase 1: 現行拡張）

- Slack本文仕様
  - レポートタイトル（日付）
  - 今週の上昇予測銘柄（ticker/current/predicted/change/ci）
  - 先週的中率と累計
  - Sheets参照情報
- LINE本文仕様
  - Slack通知を受けたことを知らせる短文
  - 銘柄数（検出可能な場合）
  - Slack確認文言
- 成否判定
  - `result = slack_ok`
  - line失敗は warning/error ログのみ

### 5.3 通知仕様（Phase 2: Bot化）

#### 追加インターフェース

- Env
  - `SLACK_BOT_TOKEN`
  - `SLACK_SIGNING_SECRET`
- Config
  - `notifications.slack_ack.enabled`
  - `notifications.slack_ack.remind_interval_min`（既定: 1）
  - `notifications.slack_ack.max_reminds`（既定: 5）

#### 挙動

1. 初回メッセージを Block Kit で投稿（「確認済み」ボタン付き）
2. 押下イベントを受信し、対象通知IDを `acked=true` に更新
3. 未押下の通知のみ `interval_min` 間隔で再通知
4. `max_reminds` 到達で停止

#### 状態管理

- 保存先: Cloudflare KV（第一候補）
- Key例: `notif:{date}:{run_id}:{message_ts}`
- 値例: `{ acked, remind_count, channel, created_at, last_remind_at }`

## 6. GUI 要件定義

### 6.1 機能要件（GUI）

| ID | 要件 | 優先度 |
|---|---|---|
| GUI-01 | 週次サマリー（予測銘柄一覧）を表示する | Must |
| GUI-02 | 的中率推移（週次・累計）を表示する | Must |
| GUI-03 | 銘柄別に実績/予測の時系列を表示する | Must |
| GUI-04 | モバイル表示に対応する（レスポンシブ） | Must |
| GUI-05 | データ未更新時に最終更新時刻と警告表示を出す | Should |
| GUI-06 | 銘柄・期間フィルタを提供する | Should |

### 6.2 画面仕様

1. `dashboard/index.html`
- 週次予測サマリーカード
- 的中率チャート
- 最終更新日時

2. `dashboard/stock.html?ticker=XXX`
- 選択銘柄の価格推移（実績 + 予測）
- 予測履歴テーブル

3. `dashboard/accuracy.html`
- 週次的中率・累計的中率
- 銘柄別的中率ランキング

### 6.3 データ供給仕様

新規モジュール: `src/exporter.py`

- 生成物
  - `dashboard/data/predictions.json`
  - `dashboard/data/accuracy.json`
  - `dashboard/data/stock_history.json`
- 更新タイミング
  - 週次ジョブ完了後
- 失敗時
  - 前回JSONを保持（空ファイル上書き禁止）

### 6.4 データスキーマ（案）

`predictions.json`:
```json
[
  {
    "date": "2026-02-22",
    "ticker": "AAPL",
    "current_price": 250.0,
    "predicted_price": 265.0,
    "predicted_change_pct": 6.0,
    "ci_pct": 3.2,
    "actual_price": 263.5,
    "status": "確定済み",
    "hit": "的中"
  }
]
```

`accuracy.json`:
```json
{
  "updated_at": "2026-02-22T09:02:10+09:00",
  "weekly": [
    { "date": "2026-02-22", "hit_rate_pct": 75.0, "hits": 6, "total": 8 }
  ],
  "cumulative": { "hit_rate_pct": 71.2, "hits": 57, "total": 80 }
}
```

`stock_history.json`:
```json
{
  "AAPL": [
    { "date": "2026-01-01", "close": 245.2 }
  ]
}
```

## 7. 非機能要件

### 7.1 可用性

- 通知: Slack失敗はジョブ失敗、LINE失敗は非致命
- GUI: 静的配信を維持し、バックエンド障害に依存しない

### 7.2 性能

- 通知送信処理: 60秒以内
- GUI初回表示: 3秒以内（主要チャート描画まで）

### 7.3 セキュリティ

- トークンは全て Secrets / env 管理
- GUIには秘密情報を埋め込まない
- Slack Interactivity endpoint は署名検証必須（Phase 2）

### 7.4 運用性

- 主要イベント（予測件数、通知成否、export成否）をINFOログ化
- 失敗はERRORで理由を残す（HTTP status/body など）

## 8. ワークフロー変更要件

`.github/workflows/weekly_run.yml` の将来変更:

1. 通常実行（日曜）
- 現行のまま維持

2. 検証実行（木曜追加、任意）
- `schedule` に木曜cronを追加
- 検証フラグ（例: `RUN_MODE=experiment`）で本番通知と分離可能にする

3. GUI更新
- `python -m src.exporter` を追加
- 生成JSONのコミット/デプロイ手順を追加

## 9. テスト要件

### 9.1 通知

- Unit
  - Slack本文生成（空データ/通常データ）
  - LINE短文生成（銘柄数あり/なし）
  - LINE失敗時の継続動作
- Integration
  - `notify()` で Slack->LINE 順呼び出し
  - `line.enabled` のON/OFF切替

### 9.2 GUI

- Unit
  - exporterのJSONスキーマ検証
  - 欠損値/空データ時のフォールバック
- E2E
  - index/stock/accuracy が表示可能
  - データ更新後に画面反映される

### 9.3 受け入れ基準

- Slack+LINE併用通知が実環境で動作
- LINE失敗時でもSlack成功でジョブ成功
- GUIで週次予測と的中率を閲覧可能
- 仕様書記載の設定キーで挙動が再現できる

## 10. 実装フェーズ計画

### Phase A（1〜2日）

- 通知仕様の明文化と既存挙動テスト補強
- `line.enabled` 運用ルール確定

### Phase B（3〜5日）

- Slack Bot化（確認ボタン + リマインド）
- KV保存と署名検証実装

### Phase C（4〜7日）

- exporter実装
- dashboard静的ページ実装
- Cloudflare Pages連携

## 11. リスクと対策

| リスク | 対策 |
|---|---|
| Slack Bot化で実装が肥大化 | Phase分離し、先にPhase Aを本番化 |
| リマインドが過剰 | `max_reminds` と quiet time を設定 |
| GUIデータ不整合 | exporterでバリデーションし、失敗時は前回データ維持 |
| 木曜追加で運用負荷増 | 検証モードで限定実施し、8〜12週で判断 |

## 12. 参照コード

- `src/main.py`
- `src/notifier.py`
- `src/line_notifier.py`
- `src/sheets.py`
- `src/tracker.py`
- `config.yaml`
- `.github/workflows/weekly_run.yml`
- `tests/test_line_notifier.py`
