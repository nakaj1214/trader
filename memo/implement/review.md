# Phase 2 実装計画レビュー（最終）

確認日: 2026-09-09
対象: `memo/implement/proposal.md` REQ-008〜013, 015, 016 / 更新後の `memo/implement/plan.md`

## 判定

**実装可。追加指摘なし。**

## 確認結果

- REQ-008〜013, 015, 016の要件と受入条件が実装ステップ・テスト・完了条件へ対応している。
- Paired benchmarkはtrade単位で実entry/exit日を使い、欠損補完後の日付逆転も拒否する設計になっている。
- Peak Giveback、Peak Capture Ratio、Early Exit Returnは`TradeResult`から明細・集計まで一貫して扱える。
- Cluster bootstrapはdate/ticker依存、固定seed、クラスタ不足を扱い、score bandとregimeの件数は評価母集団と一致する。
- 20営業日regime用の過去価格取得、21本のClose定義、0%・データ不足時の分類が明記されている。
- Explosion Recallは4分類の共有価格取得、baseline価格欠損、空集合、最終report接続、CI実行まで定義されている。
- 既存artifactの`groups`配下への構造変更に本番コード上のconsumerはなく、計画記載どおり許容可能。

## 実装時の留意事項

- `src/evaluation/inflection_learning.py`が実装着手前にmainへ入っていないことを計画どおり再確認する。
- 実データ実行時間を測定し、現行30分のActions timeoutを超える場合だけ延長する。
