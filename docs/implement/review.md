# plan.md レビュー（2026-02-22 再レビュー）

> 対象: `docs/implement/plan.md`（2026-02-22 改訂版、Phase 0〜6 構成）

---

## Findings

現時点で High / Medium の指摘はありません。

### [Low] Phase 1 受入条件に `walkforward.json` スキーマへの参照が不足

- **根拠:** Phase 1 タスクで出力スキーマを定義しているが、受入条件には「`walkforward.json` が出力される」とあるだけでスキーマとの突き合わせ条件が書かれていない。
- **影響:** テスト実装者がスキーマ定義を見落とす可能性がある。
- **修正提案:** 受入条件に「`windows[*]` に `train_start / train_end / test_start / test_end / hit_rate_pct / mae / mape / n_predictions` が含まれることをテストで保証する」を追記する。

### [Low] `docs/implement/changelog.md` が未作成

- **根拠:** Phase 1 の"ルール固定期間"運用フローで「`docs/implement/changelog.md` に日付・理由を記録する」と明記されているが、ファイルが存在しない。
- **影響:** 実装者が初回ルール変更時にどこに書くか迷う。
- **修正提案:** `docs/implement/changelog.md` を空テンプレートとして作成する（実装前でも作成可能）。

---

## Resolved From Previous Review

- **旧 Findings（フェーズ25 predict/predict_stock 方向の誤記）**: 旧 plan.md が全面改訂されたため、当該記述は削除済み。
- **フェーズ22 APIバージョン制御の矛盾**: 旧 plan.md 由来。新 plan.md は J-Quants を `jquants_fetcher.py` + `config.jquants.enabled` で管理する方針に統一されており、矛盾なし。
- **フェーズ23 流動性閾値の曖昧さ**: 旧 plan.md 由来。新 plan.md では `min_avg_dollar_volume_us` / `min_avg_dollar_volume_jp` として実装済みのため対象外。

---

## Summary

新 plan.md（Phase 0〜6）は前版と比べて実行順序の矛盾・具体性不足が解消されており、全体の整合性は高い。
Low 指摘 2 件（walkforward テスト条件・changelog.md 未作成）を対処すれば、実装開始の条件を満たす。
