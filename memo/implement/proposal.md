# 修正要件書（verify-before-fix）

> verify-before-fix スキルで生成。証拠に基づく診断結果と修正方針。
> 日時: 2026-10-15
> 対象: ISSUE-11（`test.yml` の token 権限が暗黙）
> 出典: [memo/implement/prompt.md](prompt.md)（問題一覧）、[Codex 最終監査](../../.harness/reports/reliability-final-audit-2026-10-13.md)（Q05）
> 前の要件書: ISSUE-01〜10（REQ-071〜080）は実装済み。ISSUE-09・10 は未コミット。

---

## 診断結果

### 確認した現象

- `test.yml` だけが、workflow にも job にも `permissions` を指定していない。他の 4 つの workflow は、先頭で `permissions: contents: read`（Watchdog は `actions: read` も）を明示している。
- 既存の静的テスト `test_write_permission_is_limited_to_persistence_jobs` は、`contents: write` を**明示している** job しか数えない。指定の無い workflow がリポジトリ既定の write 権限を継承しても検出できない。

### 根本原因

`test.yml` は PR（fork を含む）と main への push で実行されるのに、`GITHUB_TOKEN` の権限を明示していない。実効権限はリポジトリの設定（既定が read か write か）に依存し、この環境では確認できない。静的テストも、「明示が無い」ことを検出する作りではなかった。

### 証拠

| 仮説 | 判定 | 証拠 |
|------|------|------|
| 1. `test.yml` だけ権限指定が無い | 確認 | 5 つの workflow のうち、`test.yml` だけに `permissions` が無い。 |
| 2. 既存の静的テストでは検出できない | 確認 | 明示した `contents: write` だけを数える正規表現。 |
| 3. 読み取り以外が必要な step がある | 棄却 | `test.yml` に `GITHUB_TOKEN`・`gh`・アーティファクト・push・コミット・PR 操作が無い。`checkout`・`setup-python`・`uv sync`・`ruff`・`mypy`・`pytest` だけで、`contents: read` で足りる。 |

---

## 修正要件

### REQ-081: `test.yml` に最小権限を明示し、全 workflow の明示を静的に保証する（ISSUE-11）

- **画面**: GitHub Actions（`test.yml`）と、workflow の静的テスト
- **対象ファイル**: [.github/workflows/test.yml](../../.github/workflows/test.yml)、`tests/test_workflow_reliability.py`、[docs/playbooks.md](../../docs/playbooks.md)（該当箇所のみ。必要なら）
- **Before（現状）**: `test.yml` の権限がリポジトリ既定に依存する。静的テストが、明示の欠落を検出できない。
- **After（期待）**:
  - `test.yml` の先頭に `permissions: contents: read` を明示する。
  - 静的テストで、すべての workflow が、先頭に `permissions:` を持ち、かつ `write` 権限を持つのは既存の 2 つの persistence ジョブだけであることを確認する（明示の欠落も検出する）。
  - 他の workflow、ジョブ、step は変更しない。
- **修正方針**:
  - `test.yml` の `on:` の後に 3 行を追加するだけ。
  - 静的テストは、`.github/workflows/*.yml` の各ファイルについて、`jobs:` より前に `^permissions:` が存在することを確認する。
- **受入条件**:
  1. 静的テストで、全 workflow が先頭に `permissions:` を持つことを確認できる。修正前に `test.yml` が該当して失敗する回帰テストとして追加する。
  2. 既存の workflow テスト（SHA 固定、write 権限、main 限定など）が無変更で PASS。
  3. 全テスト・ruff・mypy（既知 31 件のみ）が通る。
- **baseline への影響**: なし（投資判定・評価の数値に無関係）。
- **未確認（integration）**: 実際の GitHub Actions 上で `test.yml` が `contents: read` だけで通ること（`checkout` などは read で足りる見込み）。ローカルでは確認できない。

---

## 次の手順

- 修正は Phase 5 で実施する。原因と方針は確定済み。
- 続けて ISSUE-12（外部通信拒否 fixture が yfinance の curl_cffi 経路を止めない）に進む。
