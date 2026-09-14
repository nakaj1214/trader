# REQ-014 実装修正計画レビュー（5回目）

確認日: 2026-09-14

対象: `memo/implement/plan_req014.md`

## 判定

**VERDICT: PASS**

blocking issueはない。前回までの指摘に対し、計画は以下を整合させている。

- `exit_date`の有無をentry選択に使わず、未成熟positionを評価基準日まで資金・slotへ反映するpoint-in-time設計
- `entered_positions`と`completed_trades`を分離し、Equity Curve・Turnover・exposure・trade summaryの母集団を明確化
- 未決済positionの仮想清算価値を、既存の完了tradeと同じentry元本基準の往復cost控除へ統一
- costのfinite/range検証、config出力、値上がり・値下がりを含む回帰テスト4b〜4e
- `memo/project-overview.md`と`forward_validation.yml`を具体的な変更対象に確定
- 既知の`ffill`制約、未確認パラメータ、限定されたportfolio対象範囲をレポートへ明記

## 実装後確認

- point-in-time・cost・未決済positionの修正と、回帰テスト4b〜4e、レポート・文書・CI配線を反映済み。
- 本計画に沿った実装依頼をもって、セクター上限・dashboard配線をREQ-014bへ分離する方針を承認済みとする。
- forward-validation対象テスト88件、coverage 91.95%、Ruff、mypy（`--ignore-missing-imports`）はPASS。
- 外部価格取得と生成物更新を伴う実データoperator-runは未実施。
