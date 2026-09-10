# 実装計画: REQ-022 — モメンタム相対化のshadow A/B/C比較（現状範囲）

> `memo/implement/proposal.md` のREQ-022だけを対象とする。
> `memo/implement/plan.md`（Phase 3の一部: REQ-018, 019, 021）から切り離す。

## 切り離した理由

`memo/implement/plan.md`の当初案は、既存の絶対リターン一次選別（`_pre_score()`→上位`deep_candidates`）で候補を確定させた**後**に、TOPIX相対・業種相対の値を追加フィールドとして付記するだけの軽量案だった。レビューで次の欠陥が指摘された。

- 一次選別が絶対リターンだけで行われるため、TOPIX相対または業種相対でなら上位に入るはずの銘柄が、絶対リターン基準で先に脱落し候補にすら残らない（選択バイアス）。
- proposalの受入条件（`absolute` / `TOPIX-relative` / `industry-relative rank`を**別`STRATEGY_VERSION`として同一日付集合でshadow実行**し、方式別のforward validation指標を比較する）を満たすには、3方式それぞれが独立に一次選別・スコアリング・classificationを行う必要がある。軽量な値の付記では代替できない。

したがって、REQ-022はproposalの受入条件どおり実装するなら3本の独立パイプラインが必要であり、これはREQ-027と同程度の設計・実装規模になる。**未確定事項が多いまま実装に着手せず、方針を確定してから着手する。**

## 着手前に決めること

1. **共有と分岐の境界**: 価格・出来高・財務データの取得（J-Quants/yfinance呼び出し）は3方式で共有し、一次選別（`_pre_score()`相当）とスコアリング（`score_inflection()`相当）以降だけを方式ごとに分岐させる。3倍のAPI呼び出しにはしない。
2. **`STRATEGY_VERSION`のネームスペース**: 3方式を`jp-inflection-shadow-v2-absolute` / `-topix-relative` / `-industry-relative`のように区別し、snapshot保存先（`dashboard/data/inflection/`配下）も方式ごとに分離するか、同一ファイル内に3方式分の`candidates`を持たせるかを決める。後者は`load_inflection_signals()`の`classifications`フィルタと同様に`strategy_variant`フィールドでの絞り込みが必要になる。
3. **業種分類の実データ確認**: J-Quants `/equities/master`の実際のレスポンス（テスト環境または公式ドキュメント）を確認し、業種を表すフィールド名（`Sector17Code`/`Sector33Code`等、正式名称未確認）を確定する。
4. **業種平均リターンの母集団・集計方法**: 同一業種内の対象銘柄集合（全上場銘柄か、流動性フィルタ後か）、集計値（中央値か平均か）、同順位・欠損時の扱いを一意に決める（再現性のため）。
5. **相対リターンの計算式**: `TOPIX-relative = stock_return - topix_return`のような差分方式か、`industry-relative rank`という名称が示すとおり業種内の順位（パーセンタイル等）にするかを決める。proposalの文言は「rank」だが、後続のforward validation比較のしやすさから差分方式の方が扱いやすい可能性があり、要検討。
6. **既存本番パイプラインへの影響分離**: 3方式のうち`absolute`は現行本番ロジックと同一のはずだが、コード共通化のためにリファクタリングした結果、既存の`inflection_shadow.yml`（本番）が想定外に変わらないことを保証する設計にする（例: 既存の`scan_japan_inflection()`はそのまま本番用に残し、3方式比較は別スクリプト/別workflowから、共通ヘルパーだけを呼び出す）。
7. **forward validationの拡張**: 3方式分のsnapshotを`rebuild_inflection_forward_validation.py`がどう読み分け、方式別に集計・比較するかを設計する（Phase 2で実装済みの`groups`構造とは別軸になる可能性が高い）。

## 受入条件（着手時点で再確認）

- `absolute` / `TOPIX-relative` / `industry-relative`の3方式が、同一日付・同一universeに対して独立に一次選別・スコアリング・classificationを行い、それぞれの候補集合が異なりうることを確認できる。
- forward validationが3方式を区別して集計し、方式間の優劣を比較できる。
- 既存の本番`inflection_shadow.yml`パイプラインの出力（`EARLY_CANDIDATE`等）が、この変更によって一切変化しない。
- 業種分類が取得できない銘柄でもfail-closedにならず、`industry-relative`方式でのみ除外されるなど影響範囲が閉じている。

## 非目標（着手時点でも対象外）

- 相対化を本番の`classification`・`score`へ反映すること（proposal自身が「相対化は検証結果が出るまで本番反映しない」としている）。
- Phase 5相当の買い候補通知パイプラインとの統合。
