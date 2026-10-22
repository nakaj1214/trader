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

## 詳しい資料

- [memo/project-overview.md](memo/project-overview.md): 設計・データ・CI の全体像
- [docs/playbooks.md](docs/playbooks.md): 障害時の対応手順
- [archive/README.md](archive/README.md): 旧実装の扱い
