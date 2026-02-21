# 運用レビュー追加指摘（ops_review_fix_points.md 以外）

作成日: 2026-02-22  
対象: `.github/workflows/weekly_run.yml`, `src/main.py`, `README.md`

---

## Findings

1. [High] USフローが全市場対象になっており、JPスクリーニングが二重実行される
- 根拠:
  - `src/main.py:42` で `us_markets` を作成しているが未使用
  - `src/main.py:43` が `screen(config, market=None)` のため全市場（US+JP）対象
  - その後 `src/main.py:46`-`src/main.py:51` で `market="nikkei225"` を再実行
- 影響:
  - 実行時間増大、yfinance/API呼び出し増加、ログや運用解釈の不整合
- 修正案:
  - `screen(config, market=None)` を US市場限定呼び出しに変更し、JPは独立実行のまま維持
  - もしくは `run_market_pipeline(market)` で市場別に完全分離

2. [Medium] `export` が1回のワークフロー内で二重実行される
- 根拠:
  - `src/main.py:142`-`src/main.py:153` で `export(config)` 実行
  - `.github/workflows/weekly_run.yml:38`-`.github/workflows/weekly_run.yml:43` で `python -m src.exporter` を再実行
- 影響:
  - 処理時間増、外部依存呼び出し増、失敗時切り分けの難化
- 修正案:
  - Actions側の `Export dashboard data` ステップを削除、または `src.main` 側の export を無効化して責務を1箇所に統一

3. [Medium] Actions の同時実行制御がなく `git push` 競合リスクがある
- 根拠:
  - `.github/workflows/weekly_run.yml:3`-`.github/workflows/weekly_run.yml:6` で `schedule` と `workflow_dispatch` を受ける
  - `.github/workflows/weekly_run.yml:51` で直接 `git push` 実行
  - `concurrency` 設定なし
- 影響:
  - 手動実行と定期実行が重なった際に non-fast-forward で失敗しやすい
- 修正案:
  - workflowに `concurrency` を追加（例: `group: weekly-stock-analysis`, `cancel-in-progress: false`）
  - push前に `git pull --rebase` + リトライを導入

4. [Medium] 本番配信前のテストゲートが workflow に存在しない
- 根拠:
  - `.github/workflows/weekly_run.yml` に `pytest` 実行ステップがない
  - `README.md:214` では `python -m pytest tests/` を実行手順として記載
- 影響:
  - 回帰が混入した状態で `dashboard/data/*.json` がコミット・配信される恐れ
- 修正案:
  - `Install dependencies` 後に `python -m pytest tests/` を追加し、失敗時は以降ステップ停止

5. [Low] 未使用シークレット `OPENAI_API_KEY` が Actions に注入されている
- 根拠:
  - `.github/workflows/weekly_run.yml:31` で `OPENAI_API_KEY` を設定
  - `README.md:141` で「現行コードでは未使用」と明記
- 影響:
  - 不要なシークレット露出、運用複雑化
- 修正案:
  - workflow から `OPENAI_API_KEY` を削除（将来利用時に再追加）

6. [Low] Cloudflare Pages 設定がコード管理されておらず再現性に弱い
- 根拠:
  - リポジトリ内に `wrangler.toml` や Pages 設定ファイルが存在しない
- 影響:
  - デプロイ設定（対象ブランチ/公開ディレクトリ/環境差分）が属人化
- 修正案:
  - Cloudflare 設定値を `docs/` に明文化し、可能な範囲で IaC 化（Wrangler または設定テンプレート）

---

## Open Questions

1. Cloudflare Pages の Build output directory は `dashboard` で固定運用か？
2. JP/US パイプラインは当面「USのみ後続処理、JPはscreenのみ」で維持するか、統一フローへ移行するか？

