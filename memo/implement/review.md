# Phase 0+1 実装レビュー（最終）

確認日: 2026-09-09
対象: 更新後の `memo/implement/plan.md`（REQ-001〜REQ-007）

## 判定

**実装可。計画上のブロッカーは解消済みで、コード実装とローカル検証を完了した。**

## 実装結果

- REQ-001: market-date coverage失敗時に日付分布とstale ticker例を出す診断を追加した。
- REQ-002/003/007: 確定済みのdirect push、Actions tag pin継続、yfinance単一providerリスク受容をworkflowコメントとREADMEへ反映した。
- REQ-004: `horizon_matured`を追加し、Trailing Stop集計をmatured-onlyとrawに分離した。
- REQ-005: 固定期間はtotal-return adjusted、Trailing Stopはsplit-only OHLCを使用するよう分離した。
- REQ-006: 価格基準・日付行単位の暗号化ハッシュを追加し、共通日付だけを比較するscheduled限定の永続化jobを追加した。公開ログにはtickerを出さない。

## 検証

- 全体テスト: 128 passed、coverage 91.22%。
- 最終修正後の影響範囲: 75 passed。providerログ抑止の最終修正後: 25 passed。
- `ruff`、`mypy`、`git diff --check`: pass。
- 独立レビュー: `PASS`。

## 残る運用確認

REQ-001の根本原因対応とPhase 1の実データ検証は、更新したShadow Scanを`workflow_dispatch`で実行して診断結果を取得した後に行う。Shadow Scanの3営業日連続成功確認も未実施であり、今回のローカル実装には含めない。
