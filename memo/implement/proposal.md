# 修正要件書（verify-before-fix）

> verify-before-fix スキルで生成。証拠に基づく診断結果と修正方針。
> 日時: 2026-10-15
> 対象: ISSUE-09（障害分類が最終結果に残らない）
> 出典: [memo/implement/prompt.md](prompt.md)（問題一覧）、[Codex 最終監査](../../.harness/reports/reliability-final-audit-2026-10-13.md)（Q07）
> 前の要件書: ISSUE-01〜08（REQ-071〜078）は実装済み・コミット済み（`debug 5` まで）。

---

## 診断結果

### 確認した現象

- **(a) Position Monitor**: timeout・HTTP 429・認証失敗（401）・サーバーエラー（500）のどれでも、状況の行は同じ `status='stale'`、`error='current quote is missing or invalid'` になる。運用者は原因を区別できない。
- **(b) forward**: 価格取得が失敗した後の終端例外は、`Required price history is unavailable` / `Price retrieval failed for 2 ticker(s)` だけ。関数は `{timeout: 2, empty: 2}` と分かっているのに、例外に含めない。

### 根本原因

- (a) [fetch_today_bars](../../src/data/live_quote.py#L209-L235) / [fetch_session_bars](../../src/data/live_quote.py#L238-L264) は、既知の失敗を `diagnostics` に数えて `None` を返す。しかし呼び出し側の [run_position_monitor.py](../../scripts/run_position_monitor.py) は `diagnostics` を渡さないため、分類が捨てられる。また、空の応答や構造異常で `None` を返す経路（行 216-219、249-252）は、`diagnostics` にも数えない。
- (b) [fetch_price_histories](../../src/data/forward_prices.py#L233-L237) の終端で、蓄積した `failures`（分類別の件数）を、汎用の `RuntimeError` に含めない。

### 証拠

| 仮説 | 判定 | 証拠 |
|------|------|------|
| (a) Monitor が失敗の種類を区別できない | 確認 | 4 種類の失敗すべてで、行が同一。 |
| (b) forward の終端例外が原因を失う | 確認 | 例外の文面に分類が無い（関数の `failures` には `timeout`・`empty` の件数がある）。 |
| (c) 自前のバグが validation として握られる | 棄却（対処しない） | `classify_provider_failure` が `ValueError`/`KeyError` を validation にするのは、yfinance 自体が解析失敗でこれらを投げるため。例外の型では、provider の失敗と自前のバグを区別できない。型を変えると、正当な provider の失敗が `unexpected` に変わって scan が止まる。区別する安全な手段が無いので、今回は変更しない。 |

---

## 修正要件

### REQ-079: provider 障害の分類を、Monitor の行と forward の終端例外に残す（ISSUE-09）

- **画面**: Position Monitor（Sheets の状況、Slack 警告）/ forward validation・learning の価格取得
- **対象ファイル**: [src/data/live_quote.py](../../src/data/live_quote.py)（`fetch_today_bars`、`fetch_session_bars`）、[scripts/run_position_monitor.py](../../scripts/run_position_monitor.py)、[src/data/forward_prices.py](../../src/data/forward_prices.py)（`fetch_price_histories`）、`tests/test_run_position_monitor.py`、`tests/test_live_quote.py`、`tests/test_forward_prices.py`
- **Before（現状）**: Monitor は失敗の種類を行に残さない。forward の終端例外は原因を含まない。
- **After（期待）**:
  - `fetch_today_bars` / `fetch_session_bars` は、空の応答を `empty`、構造異常（OHLC 列の欠落、タイムゾーンなし）を `protocol` として `diagnostics` に数える（既存の例外起因の分類に加える）。戻り値は変えない。
  - Monitor は `diagnostics` を渡し、`stale` / `incomplete` の行の `error` に分類を括弧書きで添える（例: `current quote is missing or invalid (timeout)`、`pending historical session data is unavailable (rate_limit)`）。分類が無ければ従来の文面のまま。
  - forward の終端例外は、蓄積した分類別の件数を文面に含める（例: `Price retrieval failed for 2 ticker(s) (timeout=2, empty=2)`）。文面の先頭部分（`Required price history is unavailable` / `Price retrieval failed for N ticker(s)`）は維持する。
  - 公開してよい情報は、分類名と件数だけ。ticker・URL・response body・生の例外本文は出さない（Q02/Q07 の保護を維持）。
  - 正常系の戻り値・取得結果・判定は不変。
- **修正方針**:
  - `live_quote.py`: 2 つの関数で、`None` を返す前に、該当する分類を `diagnostics` に加える小さな補助関数を使う。
  - `run_position_monitor.py`: ticker ごとの当日足の共有（Stage 4C の仕組み）で、`diagnostics` を一緒に保持し、同じ ticker の position に同じ分類を一貫して使う。`_recover_pending` の `fetch_session_bars` にも `diagnostics` を渡す。
  - `forward_prices.py`: 終端例外を作る箇所で、`failures`（引数 `diagnostics` を含む）を整形して文面に添える。
  - 既存テストのうち、`fetch_today_bars` の呼び出しの形（`assert_called_once_with("1111.T")`）を固定している 3 箇所は、診断を受け取る引数が加わるため、期待を `diagnostics=ANY` を許す形に更新する。契約の意図的な変更であり、他の期待は変えない。
- **受入条件**:
  1. timeout・429・401・500 の fake で、Monitor の行の `error` が、それぞれ別の分類を含む。修正前に失敗する回帰テストとして追加する。
  2. 空の応答と構造異常で、`diagnostics` に `empty` / `protocol` が数えられ、戻り値は従来どおり `None`。
  3. 同じ ticker の複数 position で、取得は 1 回のまま（Stage 4C）、同じ分類が全 position の行に付く。
  4. forward の終端例外が、分類別の件数を含み、文面の先頭部分は従来どおり（既存の `match=` が通る）。
  5. 行・例外・公開ログに、ticker・URL・response body・秘密が含まれない。
  6. 全テスト・ruff・mypy（既知 31 件のみ）が通る。
- **baseline への影響**: なし（失敗時の診断文面のみ。投資判定・評価の数値は不変）。

---

## 次の手順

- 修正は Phase 5 で実施する。原因は確定済み。
- 続けて ISSUE-10（日次 scan workflow に main ブランチの限定が無い）に進む。
