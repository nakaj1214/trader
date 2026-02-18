# LINE Bot 通知機能 計画書

> 最終更新: 2026-02-18

## 背景・目的

現在の通知手段は Slack Incoming Webhook のみだが、以下の課題がある:

- Slack の通知を見逃す可能性がある（特にモバイル環境）
- 普段 Slack を使わないユーザには通知が届きにくい

**LINE Bot を追加することで、日常的に使う LINE アプリで予測結果を受け取れるようにする。**

---

## 機能概要

```
毎週日曜 9:00 (JST)
  ↓
既存ワークフロー (スクリーニング → 予測 → 記録 → 追跡)
  ↓
通知 (Slack + LINE の両方に送信)
  ↓
ユーザがLINEで予測レポートを受信
```

### 通知内容（LINE に送るメッセージ）

Slack と同等の内容を LINE のメッセージ形式に最適化して送信する:

```
📊 週間AI株式予測レポート (2026-02-22)

【今週の上昇予測銘柄】
1. AAPL: $250.00 → $265.00 (+6.0%)
2. MSFT: $420.00 → $438.00 (+4.3%)

【先週の的中率】
的中: 6/8銘柄 (75.0%)

詳細はスプレッドシートを確認 →
https://docs.google.com/spreadsheets/d/xxx
```

---

## 技術設計

### 方式: LINE Messaging API (Push Message)

Slack の Webhook-only 方針と同様に、**一方向のプッシュ通知** とする。
ユーザからの対話機能（チャットボット）は初期スコープに含めない。

### アーキテクチャ

```
src/main.py (オーケストレーター)
  ↓
src/notifier.py (既存: Slack通知)
  ↓ 追加
src/line_notifier.py (新規: LINE通知)
  ↓
LINE Messaging API (Push Message)
  ↓
ユーザの LINE アプリ
```

### LINE Messaging API の仕組み

1. **LINE Developers** でチャネル（Bot）を作成
2. **チャネルアクセストークン** を取得
3. ユーザが Bot を友だち追加すると **ユーザID** が取得できる
4. Push Message API でユーザIDに対してメッセージを送信

### 必要な環境変数

| 変数名 | 説明 |
|--------|------|
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API のチャネルアクセストークン |
| `LINE_USER_ID` | 通知先ユーザの LINE ユーザID（またはグループID） |

### 新規ファイル: `src/line_notifier.py`

```python
"""LINE Messaging API によるプッシュ通知"""

import logging
import requests
from src.utils import get_env

logger = logging.getLogger(__name__)

LINE_API_URL = "https://api.line.me/v2/bot/message/push"


def build_line_message(report_text: str) -> dict:
    """Slack用レポートテキストをLINEメッセージ形式に変換する。"""
    # Slack のマークダウン記法を除去 (*bold* → bold)
    clean_text = report_text.replace("*", "").replace("_", "")
    return {
        "type": "text",
        "text": clean_text,
    }


def send_to_line(text: str) -> bool:
    """LINE Push Message API でメッセージを送信する。"""
    token = get_env("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = get_env("LINE_USER_ID")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "to": user_id,
        "messages": [build_line_message(text)],
    }

    try:
        resp = requests.post(LINE_API_URL, json=payload, headers=headers, timeout=30)
        if resp.status_code == 200:
            logger.info("LINE通知送信成功")
            return True
        else:
            logger.error("LINE通知失敗: status=%d, body=%s", resp.status_code, resp.text)
            return False
    except requests.RequestException:
        logger.exception("LINE通知送信エラー")
        return False
```

### 既存コードへの変更

#### `src/notifier.py` の `notify()` 関数を拡張

```python
def notify(predictions_df, accuracy=None, config=None):
    """レポートを生成してSlackとLINEに送信する。"""
    report = build_report(predictions_df, accuracy, config)

    # Slack通知
    slack_ok = send_to_slack(report)

    # LINE通知 (設定されている場合のみ)
    line_ok = True
    if config.get("line", {}).get("enabled", False):
        from src.line_notifier import send_to_line
        line_ok = send_to_line(report)

    return slack_ok and line_ok
```

#### `config.yaml` への追加

```yaml
# LINE通知設定
line:
  enabled: false  # true にするとLINE通知が有効になる
```

#### `.env.example` への追加

```
# LINE Messaging API
LINE_CHANNEL_ACCESS_TOKEN=your-channel-access-token
LINE_USER_ID=your-line-user-id
```

#### GitHub Actions Secrets への追加

| Secret名 | 用途 |
|----------|------|
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Bot のチャネルアクセストークン |
| `LINE_USER_ID` | 通知先ユーザID |

---

## LINE Bot セットアップ手順（ユーザ向け）

### 1. LINE Developers でチャネルを作成

1. [LINE Developers](https://developers.line.biz/) にログイン
2. プロバイダーを作成（初回のみ）
3. 「Messaging API」チャネルを新規作成
4. チャネル名: 例「AI Stock Predictor」

### 2. チャネルアクセストークンを取得

1. 作成したチャネルの「Messaging API」タブを開く
2. 「チャネルアクセストークン（長期）」を発行
3. `.env` の `LINE_CHANNEL_ACCESS_TOKEN` にセット

### 3. Bot を友だち追加してユーザIDを取得

1. チャネルの「Messaging API」タブにある QR コードをスキャンして友だち追加
2. 「基本設定」タブの「あなたのユーザID」をコピー
3. `.env` の `LINE_USER_ID` にセット

### 4. config.yaml で LINE 通知を有効化

```yaml
line:
  enabled: true
```

---

## コスト見積もり

| 項目 | 費用 | 備考 |
|------|------|------|
| LINE Messaging API (無料プラン) | $0 | 月200通まで無料 |
| 本ツールの利用 | 月4〜5通 | 週1回通知 × 月4週 |

**無料枠内で十分運用可能。**

---

## 実装スケジュール

| フェーズ | 作業内容 | 所要時間 |
|---------|---------|---------|
| 1 | `src/line_notifier.py` 新規作成 | 0.5日 |
| 2 | `src/notifier.py` の拡張 | 0.5日 |
| 3 | config.yaml / .env.example の更新 | 0.5日 |
| 4 | テスト作成・実行 | 0.5日 |
| 5 | ドキュメント更新 | 0.5日 |

**合計: 約2.5日**

---

## リスクと対策

| リスク | 対策 |
|-------|------|
| LINE API の仕様変更 | 公式SDKの利用を検討（`line-bot-sdk`） |
| 無料枠の超過 | 月200通の制限は週1通知では問題なし |
| LINE トークンの期限切れ | 長期トークンを使用（期限なし） |
| ユーザIDの管理 | 環境変数で管理、複数ユーザ対応は将来検討 |

---

## 将来の拡張

- **複数ユーザへの配信**: ユーザIDをリストで管理し、一括送信
- **Flex Message 対応**: LINE のリッチメッセージでグラフ付き通知
- **対話機能**: 「RSIとは？」のような質問に Bot が回答する機能
- **LINE グループ通知**: グループIDを指定してグループに配信
