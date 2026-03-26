# 課題: Slack トークンの平文保存を解消する

## 現状の問題

`.claude/.env` に Slack のトークン（`SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_CHANNEL_ID`, `SLACK_APPROVER_USER_ID`）が平文でハードコードされている。

`.gitignore` で Git には含まれていないが、ローカルディスク上に平文で露出しており、セキュリティリスクがある。

## 期待する状態

- Slack トークンが平文ファイルに直接書かれていない
- 既存のフック（`slack_approval.py`, `notify-slack.py` 等）が引き続き動作する
- トークンのローテーション手順が明確になっている

## 補足

- 現在のトークンはローテーション（再発行）が必要
- `.claude/hooks/` 配下のスクリプトがこれらの環境変数を参照している
