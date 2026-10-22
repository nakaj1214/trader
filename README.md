# trader

日本株（東証 Prime / Standard / Growth）の短期的な変化の初期候補を毎営業日記録し、将来の値動きで戦略を検証する観測系です。売買・自動発注は行いません。

## 構成

| 処理 | 実行 | 入口 |
|---|---|---|
| 日次 inflection shadow scan（暗号化 snapshot・Slack ダイジェスト） | 平日 16:40 JST | `scripts/run_inflection_shadow.py` |
| Forward validation・自己改善学習 | 日曜 09:30 JST | `scripts/rebuild_inflection_forward_validation.py`, `scripts/rebuild_inflection_learning.py` |
| 保有銘柄の stop 監視（Google Sheets・Slack） | 平日 4 回 | `scripts/run_position_monitor.py` |
| workflow の失敗・未起動の監視 | 毎日 20:10 JST | `scripts/check_workflow_health.py` |
| 過去データでの検証（ローカル専用） | 手動 | `scripts/run_inflection_historical_backtest.py` |
| 保存済み候補の表示（ローカル、要 `SNAPSHOT_ENCRYPTION_KEY`） | 手動 | `scripts/show_candidates.py` |
| ダッシュボードのデータ作成（日次 scan の直後） | 平日 16:40 JST | `scripts/build_dashboard.py` → `dashboard/` |

定期実行は `.github/workflows/` の GitHub Actions で、本番は `main` だけで動きます。コードは `src/`、旧実装は参照専用の `archive/legacy/` にあります。

## セットアップと確認

```bash
python -m pip install uv==0.9.21
uv sync --frozen --extra dev
source .venv/bin/activate

python -m pytest tests/
ruff check src scripts tests
mypy --ignore-missing-imports src scripts
```

必要な環境変数は `.env.example` を参照してください（`.env` は自動では読み込みません）。scan や Monitor は外部 API・Slack・Google Sheets を使うため、動作確認のために無断で実行しないでください。テストは外部通信を遮断して動きます。

## ダッシュボード

`dashboard/` はブラウザで見る静的ページです（外部ライブラリなし）。日次 scan の後に、直近60営業日の候補・株価・過去の候補のその後を1つにまとめ、専用パスワードで暗号化して `dashboard/data/dashboard.enc` に commit します。リポジトリは公開なので、復号は閲覧者の端末の中だけで行います（PBKDF2-SHA256 → AES-256-GCM）。

初回の設定（GitHub の画面で行います）:

1. Settings → Secrets and variables → Actions → **New repository secret** で `DASHBOARD_PASSWORD` を作る。12文字以上。暗号文は公開されるので、長いパスフレーズにしてください。
2. Settings → Pages → Source を **Deploy from a branch**、Branch を `main` / `/ (root)` にして保存する。ページは `https://<ユーザー名>.github.io/trader/dashboard/` です（データは毎回 `main` から直接読むので、Pages の再構築を待ちません）。
3. （任意）同じ画面の **Variables** に `DASHBOARD_URL`（上のページの URL）を作ると、Slack の日次ダイジェストにリンクが付きます。
4. Actions → JP Inflection Shadow Scan → **Run workflow**（`main`）で、すぐにデータを作れます。以後は平日 16:40 に自動で更新されます。

手元で見る場合は `python -m http.server -d dashboard 8000` を実行し、`http://localhost:8000/` を開きます（`file://` では動きません）。

## 詳しい資料

- [memo/project-overview.md](memo/project-overview.md): 設計・データ・CI の全体像
- [docs/playbooks.md](docs/playbooks.md): 障害時の対応手順
- [archive/README.md](archive/README.md): 旧実装の扱い
