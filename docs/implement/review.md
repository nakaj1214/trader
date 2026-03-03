# レビュー対象
- 対象: `docs/implement/plan.md`
- レビュー日: 2026-03-03
- レビュアー: Codex (GPT-5)

---

# まず結論
- 判定: **APPROVED**
- 要約: 前回までの主要論点（config移行表の実キー整合、JSON出力先移行戦略、行数記載、CSV移設タスク）は反映済みで、実装着手可能な計画品質に到達している。

---

# Findings（優先度順）

## Non-blocking
1. `beginner_mode` の所属ドメインがやや曖昧
- 参照: `docs/implement/plan.md:205,252`
- 内容: 現行 `display.beginner_mode` を `notification.beginner_mode` に移す設計になっている一方、用途説明は「用語辞書連動」で通知以外にも拡張可能な性質がある。
- 提案: `ui.beginner_mode` か `report.beginner_mode` のような中立ドメインに置くか、`notification.beginner_mode` に固定する理由を1行追記すると実装時の迷いが減る。

2. `/legacy/` 併存方針の実装ステップが明示されていない
- 参照: `docs/implement/plan.md:486`
- 内容: リスク対策で「`/legacy/` パスで旧版アクセス」とあるが、Step 10/12 のチェックリストに作業項目がない。
- 提案: Step 10 か Step 12 に「legacy ルーティング/配置手順」を1項目追加する。

---

# 確認済み（主な改善点）
- `config.yaml` 実キーに整合した移行表へ更新済み（`docs/implement/plan.md:181-237`）。
- 行数記載が実測に整合（`docs/implement/plan.md:135-138,351`）。
- `data/universes` へのCSV移設が Step 4 に明記済み（`docs/implement/plan.md:297-300`）。
- JSON 出力先の移行期間方針が定義済み（`docs/implement/plan.md:377-379,393,410-411,448`）。

---

# 総評
- Blocking 指摘はなし。現時点で Phase A 実装を開始して問題ない。
