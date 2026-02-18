# `copilot/add-user-readme-and-notifications` 作成ファイル レビュー

対象として、ユーザ向けドキュメント追加と通知機能追加に関係する以下を確認しました。

- `README.md`
- `docs/USER_GUIDE.md`
- `.github/workflows/weekly_run.yml`
- `.env.example`
- `config.yaml`
- `src/notifier.py`
- `src/line_notifier.py`
- `tests/test_line_notifier.py`

## 問題点

1. **README の Secrets 記載が実装とずれている**
   - `README.md` の「自動実行（GitHub Actions）」では `OPENAI_API_KEY / GOOGLE_CREDENTIALS_JSON / SLACK_WEBHOOK_URL` の3つのみ案内されています。
   - 一方でワークフロー（`.github/workflows/weekly_run.yml`）は `LINE_CHANNEL_ACCESS_TOKEN` と `LINE_USER_ID` も参照しています。
   - LINE 通知を有効化する際の設定要件が README だけでは分かりません。

2. **LINE 通知文面の Slack チャンネル名が固定値**
   - LINE 文面内で `#stock-alerts` がハードコードされています（`src/line_notifier.py`）。
   - ただし設定ファイルには `slack.channel` があり、チャンネルを変更可能な構成です（`config.yaml`）。
   - Slack 側チャンネルを変更すると、LINE の案内文だけ古いチャンネル名のままになる可能性があります。

3. **テスト実行手順に対する依存関係不足**
   - `README.md` では `pytest tests/` 実行を案内しています。
   - しかし `requirements.txt` に `pytest` が含まれていないため、初期状態では `pytest: command not found` になりやすいです。
   - 開発者向け導線としては、`requirements-dev.txt` 追加や README での補足が必要です。

## 不明点（確認したい事項）

1. **LINE 通知失敗時の扱いは仕様通りか**
   - `notify()` は Slack 成否のみを戻し、LINE 失敗は全体失敗にしない実装です（`src/notifier.py`）。
   - 補助通知として割り切る方針なら妥当ですが、運用要件として「LINE 必達」が必要かどうか確認したいです。

2. **ユーザガイドの通知説明スコープ**
   - `docs/USER_GUIDE.md` は通知説明が実質 Slack 中心で、LINE の有効化条件・用途が明示されていません。
   - 「ユーザガイド」に LINE も含めるのか、技術者向けドキュメントに限定するのか、期待スコープを確認したいです。
