# 計画書レビュー反映 — 詳細手順

`docs/implement/review.md` の Blocking 指摘を `docs/implement/plan.md` に反映するスキル。
Non-blocking は適用しない。review.md の判定トークンは変更しない。

---

## 3ステップワークフロー

### Step 1: review.md を読む

`docs/implement/review.md` を読み、以下を確認する:

- 判定トークン（最終行: `APPROVED` / `CHANGES_REQUIRED`）
- **Blocking（必須修正）** の一覧
- Non-blocking（推奨）の一覧

`APPROVED` ならそのまま「変更不要。判定は APPROVED です」と報告して終了。

---

### Step 2: plan.md を読む

`docs/implement/plan.md` を読み、各 Blocking 指摘が plan.md のどの箇所に対応するかを特定する。

---

### Step 3: Blocking 指摘を plan.md に反映する

各 Blocking 指摘を plan.md の該当箇所に Edit ツールで反映する。

反映後、以下のフォーマットで報告して停止する:

```
## 変更箇所

- [Blocking 1] {指摘内容の要約}: {行った変更}
- [Blocking 2] {指摘内容の要約}: {行った変更}

## スキップ（Non-blocking）

- {スキップした理由 — 通常は「Non-blocking のため適用外」}
```

---

## 絶対ルール

- **Blocking のみ修正**。Non-blocking は適用しない
- **review.md の判定トークンを変更しない**（CHANGES_REQUIRED / APPROVED はそのまま）
- 指摘にない記述・構造を削除・変更しない
- plan.md の既存の見出し・ステップ番号・完了条件の構造を壊さない
