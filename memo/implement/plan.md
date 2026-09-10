# 実装計画: Phase 3（一部）— REQ-018, 019, 021

> 入力: `memo/implement/proposal.md` のREQ-018, 019, 021（Phase 3のうちデータ蓄積を待たずに着手できる項目）。
> REQ-017（`deep_candidates`比較）とREQ-020（スコア閾値検証）はforward validationデータの蓄積を待ってから別途計画する。
> REQ-022（モメンタム相対化のshadow A/B/C比較）は`memo/implement/plan_req022.md`へ切り離した（軽量案では選択バイアスが生じ受入条件を満たせないため、REQ-027と同様に方針確定を先に行う）。
> Phase 4Aの計画は`memo/implement/phase_4A.md`にあり、本ファイルとは独立。

## 目的とスコープ

対象:

1. 新規上場銘柄（65営業日未満）を候補から完全除外している問題を解消し、`breakout_52w`の変数名・意味を実態に合わせる（REQ-018, REQ-030の変数名部分）。
2. `raw_inflection_score`と正規化後スコアの命名・ドキュメントを明確に分離する（REQ-019）。
3. 市場区分別（Prime/Standard/Growth）のデータカバレッジを可視化する（REQ-021）。

対象外:
- REQ-017（`deep_candidates`本数比較）、REQ-020（スコア閾値・重みのband別検証）— いずれも実データでの比較評価が前提のため、Shadow Scanのデータ蓄積後に別計画とする。
- REQ-022（モメンタム相対化のshadow A/B/C比較）— `memo/implement/plan_req022.md`参照。

## 変更対象

- `src/screening/inflection_live.py`（`STRATEGY_VERSION`更新を含む）
- `src/strategy/inflection.py`
- `src/evaluation/inflection_forward.py`（`load_inflection_signals()`のスコアフィールド互換性）
- `scripts/run_inflection_shadow.py`（`OUT_DIR`をv3サブディレクトリへ変更、スコアフィールド参照箇所があれば追随）
- `scripts/rebuild_inflection_forward_validation.py`（`--snapshot-dir`デフォルトの変更、スコアフィールド参照箇所があれば追随）
- `tests/test_inflection_live.py`
- `tests/test_inflection_strategy.py`
- `tests/test_inflection_forward.py`
- `tests/test_shadow_health.py`（`validate_report()`の`market_coverage`検証追加に伴う`_healthy_report()`フィクスチャ更新・新規テスト）
- `README.md`, `memo/project-overview.md`（フィールド名・市場区分表記・`STRATEGY_VERSION`更新とforward validation断絶の変更を反映）

## 実装ステップ

### 1. 新規上場銘柄を候補対象に含め、`breakout_52w`を実態に合わせて改名する（REQ-018, REQ-030）

現状`_technical_features()`（`src/screening/inflection_live.py:71-97`）は`len(close) < 65`なら`None`を返し、上場65営業日未満の銘柄を`technical_usable_count`にすら含めない。また`high52 = close.tail(min(252, len(close))).max()`は、252営業日に満たない銘柄では実質「取得可能期間中の最高値（上場来高値）」を計算しており、`breakout_52w`という命名・「52週高値ブレイクアウト」という説明は不正確。

- `_technical_features()`の最低行数しきい値を65から**21**（`return_20d_pct`が計算可能な最小行数）へ下げる。**レビュー指摘への対応**: `_pct_change(close, 20)`は`close.iloc[-21]`（20営業日前の終値）と最新終値を比較するため、`len(close) <= 20`では`None`を返す（`len(close) == 20`ちょうどでは計算できない）。当初案は20を境界にしていたが、正しい境界は21である。21〜64行のデータしかない銘柄は「新規上場」として扱い、`return_60d_pct`は自動的に`None`になる（既存の`_pct_change`がそのまま処理する）。20行以下は引き続き`None`（技術指標が算出不能なため除外は妥当）。
- 高値近接フラグを2つに分離する: `len(close) >= 252`のときだけ`near_52w_high`（改名後の`breakout_52w`。真の252営業日高値からの近さ）を計算し、`len(close) < 252`のときは`near_listing_high`（取得可能期間中の高値＝実質上場来高値からの近さ）を計算する。計算式自体（`current >= high * 0.99`）は変えない。
- `breakout_52w`を`near_52w_high`へ全面改名する: `LiveCandidate.breakout_52w`（フィールド）、`InflectionFeatures.breakout_52w`、`_technical_features()`が返すキー、`score_inflection()`の`details["breakout_52w"]`、`_classify()`/`_pre_score()`の参照箇所、README、`tests/test_inflection_strategy.py`。**`near_listing_high`は`near_52w_high`とは別の新規フィールドとして追加する**（統合しない。252営業日未満の銘柄には`near_52w_high=False`固定、`near_listing_high`に実際の判定値を入れる）。
- `score_inflection()`・`_pre_score()`に`near_listing_high`のボーナス加点を追加する（`near_52w_high`と同じ配点で構わない。新規上場銘柄が`near_52w_high`加点を得られない代わりに`near_listing_high`で同等に評価されるようにする）。
- `_classify()`のOVEREXTENDED判定（`r20 >= 50.0 or r60 >= 100.0`）は、`r60`が`None`（新規上場で計算不能）の場合`0.0`扱いになり判定に寄与しない。新規上場銘柄はこの判定が`r20`だけに依存する点を`[要確認: 新規上場の急騰を見送ってよいか、r20だけでの過熱判定基準を別途設けるか]`としてコメントに残す。
- **レビュー指摘への対応（P1、3回目: REQ-018の戦略変更を既存`STRATEGY_VERSION`へ混在させる）**: 上記の変更は候補母集団（新規上場銘柄の追加）とスコア挙動（`near_listing_high`加点）を変えるため、`src/screening/inflection_live.py:28`の`STRATEGY_VERSION = "jp-inflection-shadow-v2"`を据え置くと、`load_inflection_signals()`（`src/evaluation/inflection_forward.py`）が変更前v2と変更後v2のsnapshotを同一戦略として黙って結合し、forward validationの比較結果の再現性を損なう。さらに`load_inflection_signals()`は`snapshot_dir`配下の全`.enc`を単一ディレクトリとしてglobし、strategy versionが1つでも混在すると`SnapshotLoadError`で全体を停止する仕様（`inflection_forward.py:69-73`）であるため、versionだけ上げてディレクトリを分けないと、次回scan後の最初のforward validation実行が既存v2 snapshotとの混在で即座に失敗する。
  - `STRATEGY_VERSION`を`"jp-inflection-shadow-v3"`へ更新する。
  - `scripts/run_inflection_shadow.py`の`OUT_DIR`（現行`dashboard/data/inflection`）を`dashboard/data/inflection/v3`に変更し、v3以降のsnapshotは新しいサブディレクトリへ保存する。既存のv2 snapshot（`dashboard/data/inflection/*.enc`）は削除・移動せずそのまま残す（過去記録として保持、gitの`inflection_shadow.yml`の`git add dashboard/data/inflection/`は再帰的なので変更不要）。
  - `scripts/rebuild_inflection_forward_validation.py`の`--snapshot-dir`デフォルトを`dashboard/data/inflection/v3`に変更し、今後のforward validationはv3 snapshotのみを対象にする。`.github/workflows/forward_validation.yml`のパストリガー（`dashboard/data/inflection/**`）はサブディレクトリも含む再帰パターンのため変更不要。
  - この結果、REQ-018適用前（v2）とREQ-018適用後（v3）のforward validation結果は意図的に非連続になる（過去のv2集計はv2 snapshotのみで完結し、今後のv3集計はv3 snapshotが十分蓄積してから別途評価する）。README/`memo/project-overview.md`にこの断絶を一文で明記する。

検証:

- 上場21〜64営業日の合成データで、`_technical_features()`が`None`を返さず`near_listing_high`が計算されること、`near_52w_high`は`False`固定であることを確認する。
- 上場20営業日ちょうど、および19営業日以下の合成データで、`return_20d_pct`が計算不能なため引き続き`None`が返ることを確認する（境界テスト）。
- 上場65〜251営業日の合成データで、`near_listing_high`が「取得可能期間中の高値」基準で正しく計算され、`near_52w_high`が計算されないことを確認する。
- 上場252営業日以上の合成データで、`near_52w_high`が従来の`breakout_52w`と同じ値になること（回帰）を確認する。
- `near_listing_high`が`score_inflection()`のmomentumスコアに`near_52w_high`と同等のボーナスを与えることを確認する。
- `scripts/run_inflection_shadow.py`実行後、snapshotが`dashboard/data/inflection/v3/YYYY-MM-DD.enc`に保存され、`strategy_version`が`"jp-inflection-shadow-v3"`であることを確認する。
- `dashboard/data/inflection/v3`のみを対象に`load_inflection_signals()`を呼び出し、v3 snapshotのみでは`SnapshotLoadError`（混在エラー）が発生しないことを確認する（既存v2 snapshotとの混在テストではなく、新ディレクトリ単体での正常系）。

### 2. スコアの命名を明確化する（REQ-019）

`LiveCandidate.raw_inflection_score`（`score_inflection()`の生スコア、汎用側`classify_signal()`の75/60閾値と対応）と`LiveCandidate.score`（`_normalize_available_score()`による正規化済みスコア、ライブ側`_classify()`の70/52閾値と対応）が、名前だけでは区別しづらい。

- **レビュー指摘への対応（P1、2回目: `as_dict()`でキーを削除すると永続化境界でREQ-019の目的を満たさない）**: 当初案は`LiveCandidate.score`を単純に`live_normalized_score`へ改名するだけだったが、`src/evaluation/inflection_forward.py`の`load_inflection_signals()`は暗号化snapshotの`candidate["score"]`を必須キーとして読んでおり、欠落時は`SnapshotLoadError`を送出する（`inflection_forward.py:90-98`）。さらに、既に本番commit済みのsnapshot（`dashboard/data/inflection/2026-09-09.enc`）は旧`score`キーで暗号化保存されているため、キー名を変更するとforward validationがこれらすべてのsnapshotを読めなくなる。**前回の修正案は`as_dict()`で`live_normalized_score`キーを`score`へ`pop`して置き換えるものだったが、これでは永続化されるcandidateデータに`live_normalized_score`という明示名が結局残らず、「raw_inflection_scoreとlive_normalized_scoreをフィールド名で区別する」というREQ-019の目的を蓄積・forward validation側で達成できない。**修正: `as_dict()`は`live_normalized_score`キーを**削除せず残したまま**、後方互換のため同値の`score`キーを**追加**する（`result["score"] = result["live_normalized_score"]`。popしない）。これにより新規snapshotには`raw_inflection_score`・`live_normalized_score`・`score`（後方互換alias）の3キーが並び、既存loaderは引き続き`score`を読めて壊れず、明示名も新たに永続化される。**レビュー指摘への対応（P1、4回目: snapshot構造を変えるのに`REPORT_SCHEMA_VERSION`を据え置いている）**: 当初案は「`REPORT_SCHEMA_VERSION`は変更不要」としていたが、`strategy_version`（計算ロジックの識別）と`report_schema_version`（永続化形式の識別）は別契約であり、本計画はcandidateから`breakout_52w`を削除して`near_52w_high`/`near_listing_high`を追加し、トップレベルに`market_coverage`（`validate_report()`が必須検証）を追加するため、snapshotのフィールド契約自体が変わる。据え置くとschema識別が機能しないため、`src/screening/inflection_live.py:29`の`REPORT_SCHEMA_VERSION`を3から**4**へ更新する。v3保存先（`dashboard/data/inflection/v3/`）には新schema 4のsnapshotのみが置かれるため混在問題は増えない。dashboard/README等、Python側の内部コードで`.score`を参照している箇所は`.live_normalized_score`に更新する。参照箇所: `scan_japan_inflection()`内の`score=round(score, 3)`引数名、ソートキー（`candidate.score`→`candidate.live_normalized_score`）、`_classify(score, tech)`呼び出しへ渡すローカル変数（`score`のままでよい。フィールド名だけの変更）、dashboard/README表示名、テスト。
- `_normalize_available_score()`と`LIVE_MEASURABLE_MAX_SCORE`の定義部に、「measurable_max_score=58点はcatalyst系（major_order等、ライブでは取得不可）を除いた場合の理論上限であり、汎用`score_inflection()`の100点満点とは意味が異なる」ことを説明するコメントを追加する。
- `src/strategy/inflection.py`の`classify_signal()`（75/60閾値、raw score用）と`src/screening/inflection_live.py`の`_classify()`（70/52閾値、live_normalized_score用）の両関数のdocstringに、対応するスコアの種類（raw/normalized）と閾値の意味を明記する。

検証:

- `LiveCandidate`に`raw_inflection_score`と`live_normalized_score`の両方が異なる値として存在し、`live_normalized_score`が引き続き0-100レンジで計算されることを確認する（既存のnormalize計算ロジック自体は変更しない）。
- 改名後も`tests/test_inflection_live.py`の既存アサーションが（フィールド名変更を反映した上で）通ること。
- `LiveCandidate.as_dict()`の出力に`live_normalized_score`キーと`score`キーの**両方**が含まれ、両者の値が一致することを確認する（新規snapshotで明示名が実際に永続化されることのテスト）。
- 既存の暗号化snapshot（`dashboard/data/inflection/2026-09-09.enc`相当の、`score`キーのみ・`live_normalized_score`キーを持たない・`report_schema_version=3`の合成データ）を`load_inflection_signals()`が変更なしで読み込めることを`tests/test_inflection_forward.py`に追加する（後方互換性の回帰テスト。schema 3のfixtureはそのまま残し、新規に書き換えない）。
- `scan_japan_inflection()`の出力・`tests/test_inflection_live.py`・`tests/test_shadow_health.py`の新形式fixtureが`report_schema_version=4`を期待するように更新されていることを確認する。

### 3. 市場区分別のデータカバレッジを可視化する（REQ-021）

現状`validate_report()`・`scan_japan_inflection()`のカバレッジ指標（`universe_count`, `price_data_count`, `technical_usable_count`, `latest_price_date_count`）は全市場合計のみで、Growth市場等の欠損がPrime/Standardに隠れて閾値超過しうる。

- `scan_japan_inflection()`内で`ticker_meta[ticker].get("Mkt")`（安定コード）から市場区分別（Prime/Standard/Growth）に`universe`・`price_data`・`technical_usable`・`latest_date一致`の件数を集計する`market_coverage: dict[str, dict[str, int]]`をレポートへ追加する。
- 既存の全市場合計指標（`universe_count`等）は変更しない（後方互換）。`market_coverage`は追加フィールドとする。
- **レビュー指摘への対応（P2、2回目: 市場キーの「固定」と生成元が矛盾している）**: 当初案は`market_coverage`のキーを日本語の固定3種としつつ、生成元には`MktNm`（表示用テキスト。安定性が保証されず、現行テストfixtureでは`"Prime"`/`"Standard"`という別の表記になっている）を使い、想定外の値は`"その他"`へ集約するとしていた。これでは「固定契約」と言いながら実際には可変テキストに依存しており矛盾する。修正: 既に対象銘柄の絞り込みに使っている安定コード`Mkt`（`JP_MARKET_CODES = {"0111", "0112", "0113"}`）から`{"0111": "Prime", "0112": "Standard", "0113": "Growth"}`という固定マッピングでキーを導出する。対象銘柄は`JP_MARKET_CODES`で既に3コードに絞り込み済みのため、想定外コードが`market_coverage`集計に混入することは契約違反であり、`"その他"`へ集約せず、検出した時点で即座にエラー（fail-closed）とする。
  - `market_coverage`のキーは固定3種（`"Prime"`, `"Standard"`, `"Growth"`）。各値は`{"universe": int, "price_data": int, "technical_usable": int, "latest_date_count": int}`の固定フィールドを持つ。`Mkt`が上記3コード以外の銘柄が`market_coverage`集計対象に含まれていた場合は契約違反として`DATA_HEALTH`エラーで即座にfail-closedにする（`JP_MARKET_CODES`によるuniverse絞り込みが正しく機能していれば発生しないはずのガード）。
  - `scripts/run_inflection_shadow.py`の`validate_report()`に、**エラーにはしないが**次の整合性検証を追加する: `market_coverage`の各フィールドの市場別合計が、レポートの全市場合計値（`universe_count`, `price_data_count`, `technical_usable_count`, `latest_price_date_count`）と一致することを確認し、不一致なら`DATA_HEALTH`エラーとしてfail-closedにする（件数の集計漏れ・二重集計を検知するため。市場別の**低さ**自体はエラーにしない）。
  - `main()`の既存の結果出力（標準出力のサマリ行）に、市場区分別のカバレッジ率（`price_data/universe`等）を追加で出力する。
  - `[要確認: 市場区分別カバレッジの絶対的な低さに対するfail-closed閾値を将来追加するかは今回のスコープ外。可視化と整合性検証のみを行う]`。

検証:

- Prime/Standard/Growthそれぞれで異なるカバレッジ率になる合成データ（`Mkt`コードで区別）を用意し、`market_coverage`に固定4フィールドの内訳が`Mkt`コードから正しくマッピングされて出力されることを確認する。
- 全市場合計のカバレッジは変更前と同じ値になること（既存指標への影響がないこと）を確認する。
- `market_coverage`の市場別合計と全市場合計値が意図的に不一致になる合成データ（集計漏れを模したもの）で、`validate_report()`が`DATA_HEALTH`エラーをfail-closedで送出することを確認する。
- 市場別のカバレッジが低い（例: Growthだけ30%）が市場別合計と全体合計が一致している場合はエラーにならないことを確認する（低さ自体は今回fail-closedの対象外であることの回帰テスト）。

**レビュー指摘への対応（P2、2回目: `validate_report()`変更の既存テストファイルが計画対象から漏れている）**: 上記の市場別合計整合性検証（fail-closed）と低カバレッジ許容の2テストは`tests/test_shadow_health.py`に追加する（`validate_report()`の専用テストは同ファイルに集約されており、既存の`_healthy_report()`フィクスチャがこの変更の直接の影響を受けるため）。同ファイルの`_healthy_report()`フィクスチャに、上記3コード分の整合した`market_coverage`を追加する（現状は`market_coverage`を持たないため、`validate_report()`側で必須化すると既存テストが軒並み失敗する）。既存snapshotの`score`キーのみでの読み込み確認は引き続き`tests/test_inflection_forward.py`側のテストで担保し、重複させない。

## テスト/検証方針

- 自動テスト: `pytest`（`tests/test_inflection_live.py`, `tests/test_inflection_strategy.py`, `tests/test_inflection_forward.py`, `tests/test_shadow_health.py`に追記。実際のyfinance/J-Quants APIへは接続しない）
- 手動確認観点（operator-run、自動テストの一部ではない）: `python scripts/run_inflection_shadow.py`を実行し、新規上場銘柄が候補に含まれること、`market_coverage`が出力されること、既存の暗号化snapshotの読み込み（forward validation）に影響が無いことを確認する

## リスクと対策

1. リスク: `breakout_52w`→`near_52w_high`の改名は複数ファイルにまたがる（`inflection_live.py`, `inflection.py`, テスト, README） → 対策: 影響範囲を`grep -rl breakout_52w`で事前に洗い出し済み（4ファイルのみ）。一括改名後にテストで回帰確認する。
2. リスク: `LiveCandidate.score`→`live_normalized_score`の改名で、シリアライズ側は`live_normalized_score`に加え後方互換aliasの`score`キーも出力する変換ロジック（`as_dict()`のオーバーライド）を入れるため、将来的にこのalias追加自体を書き忘れて`score`キーが消え旧loaderを壊す変更が入りうる → 対策: `tests/test_inflection_forward.py`に既存snapshot形式（`score`キーのみ）の読み込みテストを追加し、この互換性が壊れたら即座にテスト失敗で検知できるようにする。
3. リスク: `_technical_features()`の最低行数を65→21に下げると、データ不足の銘柄が増え計算コストがわずかに増える → 対策: 影響は「新規上場銘柄が追加でtechnical_usable_countに入る」程度で、全体の銘柄数（約3600）に対して軽微。
4. リスク: `STRATEGY_VERSION`更新とsnapshot保存先のv3サブディレクトリ分離により、REQ-018適用前後のforward validation結果が非連続になり、v3 snapshotが十分蓄積するまでは統計的に意味のある検証ができない → 対策: これは意図した挙動（異なる戦略挙動を黙って混ぜないためのfail-closed設計）であり、既存のv2 snapshotは削除せず保持する。README/`memo/project-overview.md`に断絶を明記し、運用担当者が「なぜ検証結果がリセットされたか」を追えるようにする。
5. リスク: `REPORT_SCHEMA_VERSION`を3から4へ更新すると、`report_schema_version`に依存する既存fixture（`tests/test_inflection_live.py`, `tests/test_shadow_health.py`）が期待値不一致で一斉に失敗しうる → 対策: 新形式のfixtureは4を期待するよう更新し、後方互換テスト（旧schema 3・旧`score`キーのみのsnapshot読み込み確認）はfixtureを分離して3のまま残す（`tests/test_inflection_forward.py`側）。

## 完了条件

- [ ] 上場21〜251営業日の銘柄が候補判定の対象に含まれ、`near_listing_high`で高値近接が評価される（REQ-018）
- [ ] `breakout_52w`が`near_52w_high`に改名され、252営業日以上のデータがある銘柄にのみ適用される（REQ-018, REQ-030文書修正と対応）
- [ ] `STRATEGY_VERSION`が`jp-inflection-shadow-v3`へ更新され、新snapshotは`dashboard/data/inflection/v3/`へ保存される。既存v2 snapshotは保持されたまま今後のforward validation対象から外れ、この断絶がREADME/project-overviewに明記されている
- [ ] `REPORT_SCHEMA_VERSION`が3から4へ更新され、新形式snapshotのフィールド契約変更（`near_52w_high`/`near_listing_high`/`market_coverage`追加）とschema versionが対応している。旧schema 3・旧`score`キーのみのsnapshot読み込みテストは引き続き3のfixtureで検証される
- [ ] `LiveCandidate`に`raw_inflection_score`と`live_normalized_score`が明確に区別されたフィールドとして存在し、両者の意味の違いがdocstring/コメントで説明されている。`as_dict()`出力は`live_normalized_score`キーに加え後方互換aliasの`score`キー（同値）も持ち、既存の暗号化snapshot（`score`キーのみ）がforward validationで変更なしに読み込めることが確認されている（REQ-019）
- [ ] レポートに市場区分別（Prime/Standard/Growth、`Mkt`コードから固定マッピング）のカバレッジ内訳（`market_coverage`、固定4フィールド）が出力され、市場別合計と全体合計の不一致がfail-closedで検知される（REQ-021）
- [ ] 上記すべてに対応するユニットテストが追加され、`pytest`が成功する
