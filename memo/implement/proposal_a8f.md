# 修正要件書（verify-before-fix）

> verify-before-fix スキルで生成。証拠に基づく診断結果と修正方針。
> 日時: 2026-10-01
> 対象: memo/analysis/improvement_report_2026-10-01.md A8-f

---

## 診断結果

### 確認した現象
- Position Exit Monitor（`position_monitor.yml`、09:03 / 12:35 / 15:35 JST）の場中の stale 閾値は10分（`STALE_QUOTE_THRESHOLD_MINUTES_IN_SESSION`）。
- 「状況」シートは毎回 `write_status(rows)` で全行を上書きするため、stale の履歴はシートに残らず、発生率を集計できない。そのため実測で検証した。

### 根本原因
yfinance の東証1分足は**約15分遅延**している（報告書の「約20分」ではなかった）。そのため、場中の閾値10分を常に超える。
- 09:03: 遅延のため当日の足がまだ1本もない → `fetch_today_bars` が None を返す → stale（"current quote is missing or invalid"）
- 12:35: 後場の足はまだ届いていない。最終足は前場引け 11:29 で、経過は約66分 → stale
- 15:35: 引け後30分の grace は場中扱い。最終足は約15:20 で、経過は約15分 → stale

### 証拠
| 仮説 | 判定 | 証拠 |
|------|------|------|
| yfinance 1分足の遅延が10分を超える | 確認 | 2026-10-01 09:53 JST に8銘柄（7203/6758/9984/8306/1306/4385/5253/3778）を `fetch_today_bars` で取得。全銘柄の最終足が 09:38 で、age は15.1〜16.0分。2回測定し再現した |
| 遅延が銘柄によって異なる | 棄却 | 大型株・ETF・グロース株で同じ 09:38 だった |

---

## 修正要件

### REQ-001: 場中の stale 閾値と監視時刻を、実際の遅延に合わせる

- **対象ファイル**: src/data/live_quote.py、.github/workflows/position_monitor.yml、tests/test_position_exit.py
- **Before（現状）**: 閾値は10分。実行は 09:03 / 12:35 / 15:35 で、場中の3回とも構造的に stale になる
- **After（期待）**: 閾値は20分（遅延15分＋足1本分と余裕）。実行は 09:20 / 12:50 / 15:35 で、当日の前場足・後場足・引け前の足が届いた後に評価する
- **修正方針**: `STALE_QUOTE_THRESHOLD_MINUTES_IN_SESSION = 20` に変更する。cron を `20 0` / `50 3` / `35 6` に変更する。閾値テストの境界値を更新する
- **受入条件**: tests/test_position_exit.py と tests/test_run_position_monitor.py が通ること。次の場中の実行で「状況」シートが `status=ok` になること
