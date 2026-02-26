# plan.md レビュー（2026-02-26 / research6 反映版・再レビュー3）

> 対象: `docs/implement/plan.md`（Antigravity × TradingView 記事 — 活用・差分実装計画）
> 参照: `docs/gpt_reseach/research6.md`, 現行コード (`src/`, `config.yaml`, `tests/`, `.github/workflows/weekly_run.yml`)

---

## Findings

High / Medium / Low いずれも新規指摘はありません。

---

## Resolved From Previous Review

- `fetch_stock_data()` のカレンダー日補正（`×1.5`）が明記され、`252d` による SMA200 不足リスクへの対策が追加された（`docs/implement/plan.md:66-81`）。
- 短期指標の意味崩れに対し、`price_change_1m`/`volume_trend` の固定窓化方針が追加された（`docs/implement/plan.md:85-117`）。
- `score_stock` シグネチャ変更に伴う既存テスト更新対象が明記された（`docs/implement/plan.md:174-184`）。
- `SLACK_BOT_TOKEN` の workflow 注入位置（job-level env）が明記された（`docs/implement/plan.md:378-388`）。
- Slack チャンネル ID 設計（`notifications.slack_channel_id`）と名前→ID解決ロジックが追記された（`docs/implement/plan.md:400-427`, `docs/implement/plan.md:523`）。
- `.env.example` への `SLACK_BOT_TOKEN` 追記が影響範囲に追加された（`docs/implement/plan.md:369`）。
- 前回残課題だった `chart_builder` 側の営業日200本確保仕様が、カレンダー日補正を含めて明文化された（`docs/implement/plan.md:287-301`）。

---

## Residual Risk / Testing Gap

- 本レビューは計画書レビューのため、実装反映後の実測結果（pytest / workflow 実行結果）は未確認。

---

## Summary

現時点の `docs/implement/plan.md` は、これまでの指摘事項が解消されており、実装着手可能な内容です。
