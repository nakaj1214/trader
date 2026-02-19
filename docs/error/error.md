python -m src.exporter
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "C:\Users\nakashima\Desktop\trader\src\exporter.py", line 13, in <module>
    from src.sheets import HEADERS, get_client, get_or_create_worksheet
  File "C:\Users\nakashima\Desktop\trader\src\sheets.py", line 11, in <module>
    import gspread
ModuleNotFoundError: No module named 'gspread'

1. .gitignore を修正（!dashboard/data/*.json を追加）
2. ローカルで python -m src.exporter を実行して dashboard/data/*.json を生成
3. JSON を commit / push（Cloudflareで初回表示可能にするため）
4. GitHub で Secrets（APIキー等）と Actions 権限を設定
5. workflow_dispatch で手動実行して自動更新を確認

つまり「初回表示データのpush」と「Secrets設定」は分けてよく、自動実行前にSecretsを入れるのがポイントです。
5. workflow_dispatch で手動実行して自動更新を確認

つまり「初回表示データのpush」と「Secrets設定」は分けてよく、自動実行前にSecretsを入れるのがポイ