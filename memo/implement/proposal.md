# 修正要件書（verify-before-fix）

> verify-before-fix スキルで生成。証拠に基づく診断結果と修正方針。
> 日時: 2026-10-15
> 対象: ISSUE-10（日次 scan workflow に main ブランチの限定が無い）。方針は「scan ジョブを main に限定する」（ユーザー判断、2026-10-15）。
> 出典: [memo/implement/prompt.md](prompt.md)（問題一覧）
> 前の要件書: ISSUE-01〜09（REQ-071〜079）は実装済み。ISSUE-09 は未コミット。

---

## 診断結果

### 確認した現象

- Monitor・Watchdog・各 `notify-failure` は `if: github.ref == 'refs/heads/main'` で main に限定されているが、日次 scan の `scan` ジョブには無い。
- `scan` は `JQUANTS_API_KEY`・`SLACK_WEBHOOK_URL`・`SNAPSHOT_ENCRYPTION_KEY` を使い、push 先は実行したブランチ（`origin "${{ github.ref_name }}"`）。snapshot の保存先はどのブランチでも同じパス（`dashboard/data/inflection/v3`）。したがって、別ブランチから手動実行（`workflow_dispatch`）すると、本番の secret で scan を回し、本番の Slack に通知し、そのブランチへ snapshot を push する。

### 根本原因

欠陥というより、**ブランチ別の実行を許す設計と、本番の secret・Slack への到達が切り分けられていない**こと。

- ブランチ別の実行は意図した設計だった: concurrency のコメント「手動のブランチ実行が、定時の main の実行を取り消さない」、`project-overview.md` の「scan はブランチ別 concurrency、Monitor は main 限定」。9/7〜9/8 のコミット（PR #7 の硬化を含む）で導入され、維持されてきた。
- Monitor は共有状態（Google Sheets）を持つので main に限定した。scan には同じ制約を入れておらず、ブランチでの動作確認ができる反面、本番の Slack に通知が行き、同じ日付の snapshot が別ブランチに作られ、main へ取り込むと衝突する。

### 証拠

| 仮説 | 判定 | 証拠 |
|------|------|------|
| 1. `scan` ジョブに main の限定が無い | 確認 | main 限定の `if` があるのは Monitor・Watchdog・各 `notify-failure` だけ。 |
| 2. 別ブランチから手動実行すると本番 secret・Slack・push が使われる | 確認 | `scan` の step が secret を使い、push 先は `ref_name`。 |
| 3. 意図した設計か | 意図あり | concurrency のコメントと `project-overview.md` の記述、導入時のコミット。→ 設計判断としてユーザーに確認し、「main に限定」を選択。 |

---

## 修正要件

### REQ-080: 日次 scan ジョブを main のみで実行する（ISSUE-10）

- **画面**: GitHub Actions（`inflection_shadow.yml`）
- **対象ファイル**: [.github/workflows/inflection_shadow.yml](../../.github/workflows/inflection_shadow.yml)、`tests/test_workflow_reliability.py`、[memo/project-overview.md](../project-overview.md)、[docs/playbooks.md](../../docs/playbooks.md)（該当箇所のみ）
- **Before（現状）**: 任意のブランチから手動実行すると、本番 secret で scan・Slack 通知・push が行われる。
- **After（期待）**:
  - `scan` ジョブに `if: github.ref == 'refs/heads/main'` を付ける。main 以外から実行すると、ジョブはスキップされ、secret の参照・Slack 通知・push は起きない。
  - `schedule` は常にデフォルトブランチ（main）で動くので、定時実行は変わらない。main の手動実行（`resend_digest` を含む）も変わらない。
  - スキップされた実行は `notify-failure` を起動しない（`scan` の結果が `skipped` で、`failure`/`cancelled` ではないため）。Watchdog は `head_branch == 'main'` の実行だけを数えるので影響を受けない。
  - concurrency のコメントを、実態（ブランチ実行は scan がスキップされる）に合わせる。concurrency 自体の定義は変えない。
  - ブランチでの動作確認が必要なときは、ローカル実行やテストで行う（本番の secret・Slack は使わない）。
- **修正方針**:
  - `scan` ジョブの `runs-on` の前に `if` を追加する。他のジョブ・step は変更しない。
  - 静的テストで「`scan` ジョブが main に限定されている」「`notify-failure` が main に限定され `scan` に依存している」を確認する。
  - 文書の「scan はブランチ別 concurrency」を、実態に合わせて更新する。
- **受入条件**:
  1. 静的テストで、`scan` ジョブの `if` が `github.ref == 'refs/heads/main'` であることを確認できる。修正前に失敗する回帰テストとして追加する。
  2. `notify-failure` が main 限定のまま、`scan` に依存している（スキップ時に起動しない前提）。
  3. 既存の workflow テスト（SHA 固定、権限、concurrency など）が無変更で PASS。
  4. 全テスト・ruff・mypy（既知 31 件のみ）が通る。
- **baseline への影響**: なし（投資判定・評価の数値に無関係。main の定時実行は不変）。
- **未確認（integration）**: 実際の GitHub Actions 上で、ブランチ実行がスキップされること、スキップが `notify-failure` を起動しないこと。ローカルでは静的確認までで、実機での確認は残る。

---

## 次の手順

- 修正は Phase 5 で実施する。原因と方針は確定済み。
- 続けて ISSUE-11（`test.yml` の token 権限が暗黙）に進む。
