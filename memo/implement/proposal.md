# 修正要件書（verify-before-fix）

> verify-before-fix スキルで生成。証拠に基づく診断結果と修正方針。
> 日時: 2026-10-16
> 対象: ISSUE-18（前日分の pending 通知が、翌市場日の通常実行で再送されない）。方針は「直近 3 営業日まで自動回収」（ユーザー判断、2026-10-16）。
> 出典: [memo/implement/issues-2026-10-16.md](issues-2026-10-16.md)（Codex 独立監査 #5、分類 A・P2）
> 前の要件書: ISSUE-01〜17（REQ-071〜087）は実装済み。ISSUE-15〜17 は未コミット。

---

## 診断結果

### 確認した現象

- `_deliver_digest` は、その実行の `latest_price_date`（当日）だけを確認・送信する。9/30 の送信が失敗して `pending` のまま残っても、10/1 の通常実行は 10/1 分だけを送信し、状態は `9/30=pending, 10/1=succeeded` になる。過去の pending 日を処理する呼び出しは無い。
- 監査時点（`3e9b930`）でも現在でも、同じ結果（再現済み）。`playbooks.md` の「pending 日は次の通常実行で再試行」と食い違う（Stage 4B 以来）。
- 状態は 30 件で切り捨てられる。明示再送（`resend_digest`）も最新日を使うので、前日の回収にならない。

### 根本原因

pending 日の再送が、同じ市場日の再実行にしか存在しない。過去日の pending を拾う処理が無い。

### 証拠

| 仮説 | 判定 | 証拠 |
|------|------|------|
| 1. 過去の pending 日を処理する経路が無い | 確認 | 再現（監査時点・現在とも）。 |
| 2. 過去日のダイジェストを再構築できる | 確認（実現可能） | `build_digest(report, warnings=...)` は `report` の辞書（`classification_counts`・`data_policy`・`candidates`・`latest_price_date`）だけから本文を作る。保存済みの snapshot（`dashboard/data/inflection/v3/<日付>.enc`）は `decrypt_json` で同じ形の辞書に戻せる。scan ジョブは鍵を持つ。実際に `2026-10-15.enc` までの snapshot が存在する。 |
| 3. 何日前まで回収するか | 要判断 → 決定 | ユーザー判断: 直近 3 営業日まで。 |

---

## 修正要件

### REQ-088: 通常実行で、直近 3 営業日の pending ダイジェストを、保存済み snapshot から再送する（ISSUE-18）

- **画面**: 日次 scan（`scripts/run_inflection_shadow.py`、Slack ダイジェスト）
- **対象ファイル**: [scripts/run_inflection_shadow.py](../../scripts/run_inflection_shadow.py)、`tests/test_inflection_digest.py`、[docs/playbooks.md](../../docs/playbooks.md)（該当箇所のみ）
- **Before（現状）**: 当日分だけを送る。送信失敗日は、同じ市場日の再実行か、手動再送でしか回収されない。
- **After（期待）**:
  - 通常実行の最後に、当日より前の直近 3 つの TSE 営業日のうち、状態が `pending` の日を、その日の保存済み snapshot から本文を再構築して再送する。成功したら `succeeded` に更新する（状態は 1 件ごとに原子的に書く）。
  - 失敗（Slack の失敗など）・snapshot が無い・復号できない・日付が合わない日は、`pending` のまま残し、次の実行で再試行する（3 営業日を過ぎたら回収しない）。
  - 直近 3 営業日より古い pending、`succeeded`、状態に無い日（旧 snapshot）は対象外。
  - webhook が無い、通知状態ファイルが不正・読めない、の場合は回収を試みない（当日分と同じ扱い）。
  - 回収の例外は握らず状態として報告し、scan と snapshot の保存は成功のまま（ダイジェストは scan を失敗させない）。
  - ログには回収の結果を件数だけで出す（例 `digest_recovery=sent:1,failed:0,skipped:0`）。ticker・本文・URL は出さない。
  - 当日分の送信、手動再送、重複抑制（`succeeded`）の挙動は変えない。exactly-once は保証しない前提を維持する。
- **修正方針**:
  - `_recover_pending_digests(market_date, *, state_path, snapshot_dir, secret, webhook)` を追加し、`main` の当日ダイジェストの後に呼ぶ（`try/except` で囲む）。
  - 対象日は、TSE カレンダー（`exchange_calendars`）で、当日の直前の営業日 3 つを求める（休日・週末をまたいでも「3 営業日」）。
  - 本文は、`decrypt_json` で snapshot を読み、`send_daily_digest` を再利用する（本文の組み立てを新設しない）。`latest_price_date` が対象日と一致しない場合は回収しない。
  - 回収で `pending` を再び書く必要は無い（すでに `pending`）。成功時だけ `succeeded` を書く。
  - `docs/playbooks.md` に、回収の範囲（直近 3 営業日）と、回収されない場合（snapshot が無い、4 営業日以上前）の手動対処を明記する。
- **受入条件**:
  1. 前日が `pending` のとき、次の通常実行で、当日分と前日分の 2 通が送られ、両方 `succeeded` になる。前日分の本文は前日の日付と候補を含む。修正前に失敗する回帰テストとして追加する。
  2. 2 回目の通常実行で、再送されない（`succeeded`）。
  3. 直近 3 営業日より古い pending は回収されず、`pending` のまま。
  4. snapshot が無い日・日付が合わない日・復号できない日は、`pending` のまま（送らず、例外なし）。
  5. Slack の失敗で、回収の日は `pending` のまま。scan は成功。
  6. webhook が無い・状態が不正のとき、回収を試みない。
  7. 当日分の送信・手動再送・`legacy-no-state` の既存の挙動が不変（既存のテストが無変更で PASS）。
  8. 全テスト・ruff・mypy（既知 31 件のみ）が通る。
- **baseline への影響**: なし（通知のみ）。
- **未確認（integration）**: 実 Slack・実 snapshot（鍵が必要）での再構築。ローカルは fake Slack と、テスト用に暗号化した snapshot で確認する。

---

## 次の手順

- 修正は Phase 5 で実施する。原因と方針は確定済み。
- 続けて ISSUE-19〜21（小さい項目）に進む。
