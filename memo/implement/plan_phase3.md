# 実装計画: Phase 3（一部）— REQ-018, 019, 021, 022

> 入力: `memo/implement/proposal.md` のREQ-018, 019, 021, 022（Phase 3のうちデータ蓄積を待たずに着手できる項目）。
> REQ-017（`deep_candidates`比較）とREQ-020（スコア閾値検証）はforward validationデータの蓄積を待ってから別途計画する。
> `memo/implement/plan.md`（Phase 4A: REQ-023〜026）とは独立。同ファイルを上書きしないよう別名にしている。

## 目的とスコープ

対象:

1. 新規上場銘柄（65営業日未満）を候補から完全除外している問題を解消し、`breakout_52w`の変数名・意味を実態に合わせる（REQ-018, REQ-030の変数名部分）。
2. `raw_inflection_score`と正規化後スコアの命名・ドキュメントを明確に分離する（REQ-019）。
3. 市場区分別（Prime/Standard/Growth）のデータカバレッジを可視化する（REQ-021）。
4. モメンタムの絶対/TOPIX相対/業種相対をshadowで比較できるようにする（REQ-022）。

対象外: REQ-017（`deep_candidates`本数比較）、REQ-020（スコア閾値・重みのband別検証）— いずれも実データでの比較評価が前提のため、Shadow Scanのデータ蓄積後に別計画とする。

## 変更対象

- `src/screening/inflection_live.py`
- `src/strategy/inflection.py`
- `scripts/run_inflection_shadow.py`
- `tests/test_inflection_live.py`
- `tests/test_inflection_strategy.py`
- `README.md`（フィールド名・市場区分表記の変更を反映）

## 実装ステップ

### 1. 新規上場銘柄を候補対象に含め、`breakout_52w`を実態に合わせて改名する（REQ-018, REQ-030）

現状`_technical_features()`（`src/screening/inflection_live.py:71-97`）は`len(close) < 65`なら`None`を返し、上場65営業日未満の銘柄を`technical_usable_count`にすら含めない。また`high52 = close.tail(min(252, len(close))).max()`は、252営業日に満たない銘柄では実質「取得可能期間中の最高値（上場来高値）」を計算しており、`breakout_52w`という命名・「52週高値ブレイクアウト」という説明は不正確。

- `_technical_features()`の最低行数しきい値を65から**20**（`return_20d_pct`が計算可能な最小行数）へ下げる。20〜64行のデータしかない銘柄は「新規上場」として扱い、`return_60d_pct`は自動的に`None`になる（既存の`_pct_change`がそのまま処理する）。20行未満は引き続き`None`（技術指標が算出不能なため除外は妥当）。
- 高値近接フラグを2つに分離する: `len(close) >= 252`のときだけ`near_52w_high`（改名後の`breakout_52w`。真の252営業日高値からの近さ）を計算し、`len(close) < 252`のときは`near_listing_high`（取得可能期間中の高値＝実質上場来高値からの近さ）を計算する。計算式自体（`current >= high * 0.99`）は変えない。
- `breakout_52w`を`near_52w_high`へ全面改名する: `LiveCandidate.breakout_52w`（フィールド）、`InflectionFeatures.breakout_52w`、`_technical_features()`が返すキー、`score_inflection()`の`details["breakout_52w"]`、`_classify()`/`_pre_score()`の参照箇所、README、`tests/test_inflection_strategy.py`。**`near_listing_high`は`near_52w_high`とは別の新規フィールドとして追加する**（統合しない。252営業日未満の銘柄には`near_52w_high=False`固定、`near_listing_high`に実際の判定値を入れる）。
- `score_inflection()`・`_pre_score()`に`near_listing_high`のボーナス加点を追加する（`near_52w_high`と同じ配点で構わない。新規上場銘柄が`near_52w_high`加点を得られない代わりに`near_listing_high`で同等に評価されるようにする）。
- `_classify()`のOVEREXTENDED判定（`r20 >= 50.0 or r60 >= 100.0`）は、`r60`が`None`（新規上場で計算不能）の場合`0.0`扱いになり判定に寄与しない。新規上場銘柄はこの判定が`r20`だけに依存する点を`[要確認: 新規上場の急騰を見送ってよいか、r20だけでの過熱判定基準を別途設けるか]`としてコメントに残す。

検証:

- 上場20〜64営業日の合成データで、`_technical_features()`が`None`を返さず`near_listing_high`が計算されること、`near_52w_high`は`False`固定であることを確認する。
- 上場19営業日以下の合成データは引き続き`None`が返ることを確認する。
- 上場65〜251営業日の合成データで、`near_listing_high`が「取得可能期間中の高値」基準で正しく計算され、`near_52w_high`が計算されないことを確認する。
- 上場252営業日以上の合成データで、`near_52w_high`が従来の`breakout_52w`と同じ値になること（回帰）を確認する。
- `near_listing_high`が`score_inflection()`のmomentumスコアに`near_52w_high`と同等のボーナスを与えることを確認する。

### 2. スコアの命名を明確化する（REQ-019）

`LiveCandidate.raw_inflection_score`（`score_inflection()`の生スコア、汎用側`classify_signal()`の75/60閾値と対応）と`LiveCandidate.score`（`_normalize_available_score()`による正規化済みスコア、ライブ側`_classify()`の70/52閾値と対応）が、名前だけでは区別しづらい。

- `LiveCandidate.score`を`LiveCandidate.live_normalized_score`へ改名する（`raw_inflection_score`と対になる名前にする）。参照箇所: `scan_japan_inflection()`内の`score=round(score, 3)`引数名、ソートキー（`candidate.score`→`candidate.live_normalized_score`）、`_classify(score, tech)`呼び出しへ渡すローカル変数（`score`のままでよい。フィールド名だけの変更）、dashboard/README表示名、テスト。
- `_normalize_available_score()`と`LIVE_MEASURABLE_MAX_SCORE`の定義部に、「measurable_max_score=58点はcatalyst系（major_order等、ライブでは取得不可）を除いた場合の理論上限であり、汎用`score_inflection()`の100点満点とは意味が異なる」ことを説明するコメントを追加する。
- `src/strategy/inflection.py`の`classify_signal()`（75/60閾値、raw score用）と`src/screening/inflection_live.py`の`_classify()`（70/52閾値、live_normalized_score用）の両関数のdocstringに、対応するスコアの種類（raw/normalized）と閾値の意味を明記する。

検証:

- `LiveCandidate`に`raw_inflection_score`と`live_normalized_score`の両方が異なる値として存在し、`live_normalized_score`が引き続き0-100レンジで計算されることを確認する（既存のnormalize計算ロジック自体は変更しない）。
- 改名後も`tests/test_inflection_live.py`の既存アサーションが（フィールド名変更を反映した上で）通ること。

### 3. 市場区分別のデータカバレッジを可視化する（REQ-021）

現状`validate_report()`・`scan_japan_inflection()`のカバレッジ指標（`universe_count`, `price_data_count`, `technical_usable_count`, `latest_price_date_count`）は全市場合計のみで、Growth市場等の欠損がPrime/Standardに隠れて閾値超過しうる。

- `scan_japan_inflection()`内で`ticker_meta[ticker].get("MktNm")`から市場区分別（プライム/スタンダード/グロース）に`universe`・`price_data`・`technical_usable`・`latest_date一致`の件数を集計する`market_coverage: dict[str, dict[str, int]]`をレポートへ追加する。
- 既存の全市場合計指標（`universe_count`等）は変更しない（後方互換）。`market_coverage`は追加フィールドとする。
- `scripts/run_inflection_shadow.py`の`validate_report()`に、市場区分別のカバレッジ低下を**エラーにはしないが**ログ/レポートに残す診断出力を追加する（`[要確認: 市場区分別のfail-closed閾値を今回追加するか、可視化のみに留めるか。proposalのAfter記述は「個別保存・health check」だが、閾値超過の扱いまでは指定していない]`）。

検証:

- Prime/Standard/Growthそれぞれで異なるカバレッジ率になる合成データを用意し、`market_coverage`に正しい内訳が出力されることを確認する。
- 全市場合計のカバレッジは変更前と同じ値になること（既存指標への影響がないこと）を確認する。

### 4. モメンタムの絶対/TOPIX相対/業種相対をshadowで比較する（REQ-022）

**スコープ判断（`[要確認]`）**: proposalは「別`STRATEGY_VERSION`として同一snapshot上でshadow A/B/C比較する」としているが、これは3本の独立した本番相当パイプライン（3倍のJ-Quants/yfinance呼び出し、3種のsnapshotストレージ、`STRATEGY_VERSION`のネームスペース設計）を要求し、Phase 0-2で扱った複雑さに匹敵する規模になる。**本計画では軽量な代替案を採用する**: 3方式を独立パイプラインにはせず、**既存の1回のスキャンの中で3種の モメンタム値を追加フィールドとして計算し、同じcandidateレコードに併記する**（`return_20d_pct`等の絶対値は変更せず維持し、`return_20d_topix_relative_pct`等を追加する）。forward validation側（別途、REQ-008系で拡張済みの`scripts/rebuild_inflection_forward_validation.py`）で、どの基準が事後的に良い判別力を持ったかを比較する。**本番の`classification`・`score`計算には相対化を反映しない**（絶対値ベースのまま。proposalの「本番反映しない」という条件を満たす）。3本の独立パイプラインが将来的に必要になった場合は、この軽量版の比較結果を見てから改めて計画する。

- TOPIXの日次終値系列を`fetch_price_data`（既存の`src/data/yfinance_prices.py`）で`1306.T`について取得する（forward validationの`BENCHMARK_TICKER`と同じ銘柄）。
- 業種分類は`client.listed_issues()`（J-Quants `/equities/master`）のレスポンスに含まれる業種フィールド（`Sector17Code`/`Sector33Code`等、正確なフィールド名は`[要確認: 実際のレスポンスを確認してから実装する]`）を使う。業種平均リターンは、同一業種内の全銘柄の`return_20d_pct`/`return_60d_pct`の中央値（または平均）として計算する。
- `_technical_features()`または`scan_japan_inflection()`内で、`return_20d_topix_relative_pct = return_20d_pct - topix_return_20d_pct`、`return_20d_industry_relative_pct = return_20d_pct - industry_median_return_20d_pct`（60日版も同様）を計算し、`LiveCandidate`・レポートの`candidates`へ追加する。
- `score_inflection()`・`_classify()`・`_pre_score()`は**引き続き絶対値（`return_20d_pct`等）を使う**（変更しない）。追加フィールドは記録・比較用途に限定する。
- forward validation側で、`load_inflection_signals()`が読む`candidates`に上記relativeフィールドが含まれるようにし（forward validationは`memo/implement/proposal.md`のPhase 2で既に拡張済みのため、そちらの読み込み対象に追加フィールドを含める軽微な変更で済む）、絶対/TOPIX相対/業種相対のいずれのシグナル定義がforward validation上で優れていたかを比較できる集計を追加する`[要確認: Phase 2のforward validation実装（既にcommit済み）への追加変更が必要になるため、着手前に現状の`load_inflection_signals`の対応範囲を再確認する]`。

検証:

- TOPIXが+5%、業種平均が+2%、個別株が+8%のケースで、`return_20d_topix_relative_pct=+3pt`、`return_20d_industry_relative_pct=+6pt`が正しく計算されることを確認する。
- 業種分類が取得できない銘柄（データ欠損）で、industry-relative系フィールドが`None`になり例外を送出しないことを確認する。
- 追加フィールドの有無に関わらず、`classification`・`score`・`live_normalized_score`が既存の絶対値ロジックのままであること（本番判定に影響しないこと）を回帰確認する。

## テスト/検証方針

- 自動テスト: `pytest`（`tests/test_inflection_live.py`, `tests/test_inflection_strategy.py`に追記。TOPIX/業種データはfixtureまたはモックで与え、実際のyfinance/J-Quants APIへは接続しない）
- 手動確認観点（operator-run、自動テストの一部ではない）: `python scripts/run_inflection_shadow.py`を実行し、新規上場銘柄が候補に含まれること、`market_coverage`が出力されること、TOPIX/業種相対フィールドが`candidates`に含まれることを確認する

## リスクと対策

1. リスク: `breakout_52w`→`near_52w_high`の改名は複数ファイルにまたがる（`inflection_live.py`, `inflection.py`, テスト, README） → 対策: 影響範囲を`grep -rl breakout_52w`で事前に洗い出し済み（4ファイルのみ）。一括改名後にテストで回帰確認する。
2. リスク: J-Quants `/equities/master`の業種フィールド名が想定と異なる可能性がある → 対策: 実装着手前に実際のAPIレスポンス（テスト環境またはドキュメント）を確認し、フィールド名を確定してから着手する。
3. リスク: REQ-022の軽量版（本番判定へ反映しない）では、proposalが求める「別STRATEGY_VERSIONでのshadow比較」そのものではないため、後日フルパイプライン化が必要と判断された場合に手戻りが生じる → 対策: 軽量版の比較結果（forward validationでの判別力の違い）を先に見て、優位性が確認できた場合のみフルパイプライン化を別途計画する、という段階的アプローチを`[要確認]`として明記済み。
4. リスク: `_technical_features()`の最低行数を65→20に下げると、データ不足の銘柄が増え計算コストがわずかに増える → 対策: 影響は「新規上場銘柄が追加でtechnical_usable_countに入る」程度で、全体の銘柄数（約3600）に対して軽微。

## 完了条件

- [ ] 上場20〜251営業日の銘柄が候補判定の対象に含まれ、`near_listing_high`で高値近接が評価される（REQ-018）
- [ ] `breakout_52w`が`near_52w_high`に改名され、252営業日以上のデータがある銘柄にのみ適用される（REQ-018, REQ-030文書修正と対応）
- [ ] `LiveCandidate`に`raw_inflection_score`と`live_normalized_score`が明確に区別されたフィールドとして存在し、両者の意味の違いがdocstring/コメントで説明されている（REQ-019）
- [ ] レポートに市場区分別（プライム/スタンダード/グロース）のカバレッジ内訳（`market_coverage`）が出力される（REQ-021）
- [ ] `candidates`にTOPIX相対・業種相対のモメンタムフィールドが追加され、本番の`classification`/スコア計算には影響しないことが確認されている（REQ-022、軽量版）
- [ ] 上記すべてに対応するユニットテストが追加され、`pytest`が成功する
