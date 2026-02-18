# srcレビュー修正点

作成日: 2026-02-18
対象: `trader-main/src`

## 1. LINE通知のチャンネル名ハードコード修正

### 問題
- `src/line_notifier.py` の文面が `#stock-alerts` 固定。
- `config.yaml` の `slack.channel` を変更してもLINE文面に反映されない。

### 修正方針
- `build_line_message()` に `slack_channel` 引数を追加（デフォルト `#stock-alerts`）。
- `notify()` から `config["slack"]["channel"]` を渡す。
- `send_to_line()` も `slack_channel` を受け取って `build_line_message()` に渡す。

### 変更対象
- `src/line_notifier.py`
- `src/notifier.py`

---

## 2. Slack無効時の戻り値修正

### 問題
- `notifications.slack.enabled: false` のとき `notify()` が `False` を返し、
  `main.py` 側で「Slack通知失敗」と誤判定される。

### 修正方針
- Slack通知無効時は「失敗」ではなく「スキップ成功」として扱う。
- `notify()` の戻り値仕様を以下に統一:
  - Slack有効: 送信結果 (`slack_result.success`)
  - Slack無効: `True`（意図的スキップ）

### 変更対象
- `src/notifier.py`

---

## 3. line_notifier の内部依存解消

### 問題
- `src/line_notifier.py` が `src.notifier` の内部関数 `_log_notification_result` に依存。
- notifier側の内部構造変更で壊れやすい。

### 修正方針
- `_log_notification_result` を `src/utils.py` などの共通モジュールへ移動し公開関数化。
- `notifier.py` / `line_notifier.py` の両方から共通関数を使用。
- もしくは最小対応として `line_notifier.py` 側で独立してログ出力実装（内部importを廃止）。

### 変更対象
- `src/line_notifier.py`
- `src/notifier.py`
- （共通化する場合）`src/utils.py`

---

## 実施順（推奨）

1. 修正点2（戻り値）
2. 修正点1（チャンネル可変化）
3. 修正点3（内部依存解消）

---

## 受け入れ確認

- `notifications.slack.enabled=false` で `main.py` が「失敗」ログを出さない。
- `config.yaml` の `slack.channel` を変更するとLINE文面も同値に変わる。
- `line_notifier.py` が `from src.notifier import _...` の内部依存を持たない。
