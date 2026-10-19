# Codex への独立検証の依頼: D1〜D3 と review.md 指摘の修正（2026-10-19）

> 範囲は**検証のみ**。コードは変更しない。実 API・Slack・Sheets・保存済み snapshot・archive・永続キャッシュには触れない。再現は合成データで、`.harness/runtime/` に置く。結果は `.harness/reports/reliability-verify-d1-d3-2026-10-19.md` に出す。

## 1. 検証してほしいこと

要件・設計判断（[proposal.md](proposal.md)）が**正しいか**、実装が要件を満たすか。特に次の 3 点。

1. **D1** `paired_benchmark_returns`（[inflection_forward.py](../../src/evaluation/inflection_forward.py)）: 銘柄の実 entry/exit 日と ETF の日付が完全一致しないと超過収益を `None` にする。forward・historical・learning・市場別ベンチマーク（2516.T）の 4 経路に、意図しない影響（過剰な `None`、休場日・上場初日・分割日の扱い）が無いか。
2. **D2** `unresolved_h60_outcomes`（[inflection_historical.py](../../src/evaluation/inflection_historical.py)）: 成熟した h60 で、銘柄は評価済みなのに ETF 比較不能な独立取引が、未解決に数えられているか。数えすぎ・数え漏れ（独立取引の選び方との整合）が無いか。
3. **D3** `kill_criterion` / `_excess_lower_bound`: 次の規則が数学的に妥当か。
   - 未解決があるとき、`pass` だけを確定する。各未解決を**証明できる下限**（銘柄 −100%−コスト、ETF は entry からの 62 営業日の窓の最高 Close）に置いても CI 下限 > 0 のときのみ。
   - 未解決は実シグナル日の同日クラスタに入れる。`fail` は確定しない。
   - 下限は、ETF の entry 日 Open と、市場カレンダー上の必要な全営業日の有効な Close が揃うときだけ返す（欠測・非有限値・後日の代用は `None`）。
   - 「真の下限か」（コスト項の符号、62 営業日が真の退出日を覆うか、ETF 側の未解決は下限なしで正しいか）を、反例を作って確認する。

## 2. 設計判断のうち、特に疑ってほしい点

- D1 を「代用・拒否」でなく「不明」にした点。
- D3 の learning を**変更しなかった**点（成熟した未評価があれば当該 horizon の昇格を保留）。kill criterion と規則が異なるが、許容できるか。
- 実データで未解決が多い場合（h60 で 1 件あたり約 0.65%）、`pass` がほぼ確定しなくなる。停止ルールとして実用になるか（過度に保守的でないか）。

## 3. 併せて確認してほしい修正（ISSUE-15〜21 と review.md 指摘）

- 古い保留日の日足検証（`_daily_session_is_valid`）、通知状態の値の型検証、Forward 復号 step の main 限定、過去 3 市場日の pending 再送（`unsaved:N` の警告を含む）、日足保守判定の `stop_price`。
- 受入条件は [issues-2026-10-16.md](issues-2026-10-16.md) の ISSUE-15〜21。

## 4. 検証の観点（前回の教訓）

欠損・不正な型・複数日にまたがる境界・3 経路の整合。既存テストは正常系中心なので、修正前に失敗する反例を作ること。

## 5. 既知の制限（指摘不要）

- 実データでの ETF 欠測頻度、暗号化 snapshot の baseline 再生成は未実施（鍵は GitHub 上のみ）。
- 実 Actions・実 Slack は未確認。
- 現行は全テスト 1150 件前後 PASS、ruff PASS、mypy は既知 31 件のみ。

## 6. 出力形式

指摘ごとに、重大度（P1/P2/低）・根拠箇所・合成データの再現・必要な結果・最小修正。設計判断（§2）は「妥当／要修正」と理由を書く。
