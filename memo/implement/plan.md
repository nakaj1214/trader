# 実装計画: Phase 2 — 評価設計の統計的強化（ポートフォリオシミュレーション除く）

> 入力: `memo/implement/proposal.md` の REQ-008〜013, 015, 016（Phase 2: 評価設計の統計的強化。REQ-014ポートフォリオシミュレーションは別plan）。
> 出力先を標準の `docs/implement/plan.md` ではなく `memo/implement/plan.md` にしている点に注意。
> Phase 0+1（REQ-001〜007）は commit `e27ae08` で実装済み。本計画はその後の `src/evaluation/inflection_backtest.py`, `src/evaluation/inflection_forward.py`, `scripts/rebuild_inflection_forward_validation.py` の現状コードを前提に書いている。
> ユーザー決定（2026-09-09）: REQ-010は追跡対象プール内でのRecallに再定義。REQ-012はregime分類を簡易実装する。REQ-015のベンチマーク往復コストは0.05%をデフォルト採用（要検証）。

## 目的

Forward Validationの評価期間を6ヶ月・1年まで拡張し（REQ-008/009）、EARLY_CANDIDATE以外の分類も対照群として追跡し（REQ-011）、実際に爆発した銘柄をどれだけ事前検知できたかを測る指標を追加し（REQ-010）、統計的信頼性（信頼区間・score band・regime別サンプル数）を補強し（REQ-012）、利益確定の質を測る指標（Peak Capture/Giveback/Early Exit Return, REQ-013）とコスト・ベンチマークの精度（REQ-015/016）を改善する。これにより、「候補が上がったか」だけでなく「爆発をどれだけ事前に捉え、利益をどれだけ残せたか」を評価できるようにする。

## スコープ

- 含むもの: REQ-008, 009, 010, 011, 012, 013, 015, 016
- 含まないもの:
  - REQ-014（ポートフォリオシミュレーション。工数16〜40時間で性質が異なるため別plan）
  - Phase 3（買い候補ロジック改善）, Phase 4（Exit Monitor改善）, 文献修正
  - REQ-010の「全市場（約3600銘柄）に対するRecall」は対象外。追跡対象プール（EARLY_CANDIDATE/WATCH/NONE/OVEREXTENDEDとしてdeep_candidatesに一度でも入った銘柄）内でのRecallとして再定義する
  - REQ-012の厳密な多重検定補正（Bonferroni等）の導入は対象外。信頼区間とサンプル数の可視化、および「複数パラメータを比較している」旨の注意書き出力に留める

## 現状コードの前提（Phase 0+1実装後）

- `scripts/rebuild_inflection_forward_validation.py`: `main()`が`load_inflection_signals(snapshot_dir, encryption_secret=...)`をEARLY_CANDIDATEのみで1回呼び、`horizons`ループ（L293 `for holding_days in (5, 20, 60):`）と`exit_strategies`ループ（L341 `for trailing_stop_pct in (10.0, 15.0, 20.0):`、`holding_days=60`固定）を実行して単一レポートを生成する構造
- `load_inflection_signals()`（`src/evaluation/inflection_forward.py:21`）は`classifications`引数を既に受け付ける（デフォルト`("EARLY_CANDIDATE",)`）。`src/screening/inflection_live.py:340`の`_classify()`により、日次スキャンの`candidates`には`deep_candidates`（既定25銘柄）全件が`EARLY_CANDIDATE`/`WATCH`/`OVEREXTENDED`/`NONE`のいずれかで分類されて含まれている（`NONE`は候補から除外されず記録されている）。したがってREQ-011のWATCH/NONE取得は`classifications`引数を変えるだけで可能
- `TradeResult`（`src/evaluation/inflection_backtest.py:19`）は`entry_price`, `exit_price`, `mfe_pct`, `mae_pct`, `horizon_matured`等を保持。Peak Giveback/Peak Capture Ratioは`entry_price`・`exit_price`・`mfe_pct`から導出できるが、Early Exit Returnはexit後の価格系列が必要なため、Step 6ではいずれも`simulate_signal()`内部で計算し`TradeResult`のフィールドとして持たせる方針にする（`summarize_trades()`が`TradeResult`からしか値を読まないため、経路を統一する）
- ベンチマーク処理は`benchmark_returns_by_signal_date()`（`src/evaluation/inflection_forward.py:113`）が**固定`holding_days`**を前提にしており、可変exit_date（Trailing Stop）には対応していない

## 影響範囲（変更/追加予定ファイル）

| ファイル | 理由 |
|---|---|
| `scripts/rebuild_inflection_forward_validation.py` | REQ-008（horizons拡張）, REQ-009（exit_strategies拡張）, REQ-011（分類グループごとのレポート生成に構造変更）, REQ-015（ベンチマークコスト分離）, REQ-016（trailing stopのpaired benchmark呼び出し追加） |
| `src/evaluation/inflection_forward.py` | REQ-011（`load_inflection_signals`呼び出し側は変更不要、呼び出し方法のみ変わる）, REQ-012（`summarize_benchmark_excess`へのCI追加）, REQ-016（新規`paired_benchmark_returns`関数追加） |
| `src/evaluation/inflection_backtest.py` | REQ-012（`summarize_trades`へのcluster bootstrap CI・score band集計追加）, REQ-013（`TradeResult`へのpeak capture/giveback/early exit returnフィールド追加、`simulate_signal()`内での計算） |
| `src/evaluation/inflection_recall.py`（新規） | REQ-010（Explosion Recall / Detection Lead Time。`main`には未存在の`inflection_learning.py`（PR #10、未マージ）とは現時点で重複しないため新規作成する） |
| `tests/test_inflection_backtest.py`, `tests/test_inflection_forward.py` | 上記すべての新規関数のテスト追加 |
| `tests/test_inflection_recall.py`（新規、モジュール名に応じる） | REQ-010のテスト |
| `.github/workflows/forward_validation.yml` | REQ-010（`Test forward-validation core`ステップのpytest対象・`--cov`対象に`tests/test_inflection_recall.py`/`src.evaluation.inflection_recall`を追加しないとCIで実行されないため） |

## 実装ステップ

#### Step 1: 分類グループ（EARLY_CANDIDATE/WATCH/NONE）ごとにレポートを生成する構造へリファクタリング（REQ-011）

現状`main()`はEARLY_CANDIDATEのみを対象に1回だけhorizons/exit_strategies計算を行う。これをWATCH・NONEにも拡張する前提として、まず「シグナル集合を受け取ってhorizons+exit_strategiesレポートを返す」処理を関数として切り出す。

- [ ] `rebuild_inflection_forward_validation.py`に`_build_group_report(signals, histories, split_histories, benchmark_history, signal_dates) -> dict`を追加し、現行の`horizons`ループ（L291-338）と`exit_strategies`ループ（L340-378）のロジックをこの関数に移す
- [ ] `main()`で`load_inflection_signals(snapshot_dir, encryption_secret=..., classifications=("EARLY_CANDIDATE", "WATCH", "NONE", "OVEREXTENDED"))`を**1回だけ**呼び、4分類すべての観測を取得する。この結果から`("EARLY_CANDIDATE",)`, `("WATCH",)`, `("NONE",)`の3グループ分を分類フィールドでフィルタして`_build_group_report`に渡す（`OVEREXTENDED`はgroup reportの対象外だが、取得自体は共通化する）
- [ ] 4分類全体のticker集合で価格取得（`_fetch_adjusted_histories`, `split_histories`用の取得）を**1回にまとめて**行う（yfinance APIコールの重複を避ける。ponytail: 4回同じtickerを取りに行かない）。この共有済みの`histories`（total-return-adjusted）をStep 8のExplosion Recall計算にもそのまま渡す（Step 8のために別途価格取得を行わない）
- [ ] レポートのトップレベル構造を `{"groups": {"early_candidate": {...}, "watch": {...}, "none": {...}}, "tracked_pool_explosion_recall": {...}}` のように変更する（既存の`horizons`/`exit_strategies`トップレベルキーは`groups.early_candidate`配下に移動、Step 8の結果は`tracked_pool_explosion_recall`キーに格納）。**この構造変更は既存のforward validation artifactの読み手（人間の目視確認のみ、他コードからの参照なし）に影響するため、破壊的変更として許容する**

**検証**: 合成データで3分類それぞれにダミーsignalを用意し、`main()`相当の処理を呼び出して`groups`キー配下に3グループ分のレポートが生成されることを確認するテストを追加する。

#### Step 2: 評価horizonを126・252営業日に拡張する（REQ-008）

- [ ] `_build_group_report`内の`for holding_days in (5, 20, 60):`を`(5, 20, 60, 126, 252):`に変更する
- [ ] `_fetch_adjusted_histories`呼び出し（現在`max_horizon=60`固定、L235/238/245）を`max_horizon=252`に変更する（`end = max(dates) + timedelta(days=max_horizon*2+30)`により取得範囲が延びるだけで、直近シグナルは252営業日分のデータがまだ存在しないため`has_full_horizon=False`となり自動的に評価対象外になる。REQ-004のmatured判定と同じ考え方）

**検証**: `horizons`に`h126`, `h252`キーが追加され、値が算出されることを既存テストのパラメータ化で確認する。

#### Step 3: Trailing Stop評価を60/126/252営業日で比較する（REQ-009）

- [ ] `_build_group_report`内の`exit_strategies`ループを`for trailing_stop_pct in (10.0, 15.0, 20.0): for holding_days in (60, 126, 252):`の二重ループに変更し、キー名を`f"trailing_{int(trailing_stop_pct)}pct_h{holding_days}"`にする
- [ ] `simulate_signals(..., holding_days=holding_days, trailing_stop_pct=trailing_stop_pct)`と呼び出す（既存の`holding_days=60`ハードコードを置換）

**検証**: `exit_strategies`に9通り（3 stop幅 × 3 horizon）のキーが出力されることを確認する。

#### Step 4: ベンチマークの往復コストを個別株と分離する（REQ-015）

**採用値（2026-09-09合意）**: ベンチマーク（1306.T）往復コストは**0.05%固定**（base/stress共通、個別株のような0.2%/1.2%の切替は行わない）。`[要確認: 実測値ではなく目安値。将来実際のETFスプレッド・手数料データがあれば見直す]`

- [ ] `rebuild_inflection_forward_validation.py`に`BENCHMARK_ROUND_TRIP_COST_PCT = 0.05`を追加する
- [ ] `_build_group_report`内、stressパスで`benchmark_returns_by_signal_date(..., round_trip_cost_pct=STRESS_ROUND_TRIP_COST_PCT)`となっている箇所（現行L318-323相当）を`round_trip_cost_pct=BENCHMARK_ROUND_TRIP_COST_PCT`に修正する（baseパスは元々`ROUND_TRIP_COST_PCT`を使っており、これも`BENCHMARK_ROUND_TRIP_COST_PCT`に統一する）
- [ ] レポートの`benchmark`セクション（L280-285）に`"cost_rule": "same round-trip cost as candidate trades"`とあるのを`"cost_rule": f"fixed {BENCHMARK_ROUND_TRIP_COST_PCT}% round-trip regardless of base/stress scenario"`に修正する

**検証**: baseパスとstressパスで`benchmark_net_return_pct`の差が候補株側のコスト差（0.2%→1.2%）ではなく常に同一（0.05%コスト）になることをユニットテストで確認する。

#### Step 5: Trailing Stopにpaired benchmarkを追加する（REQ-016）

現行`exit_strategies`は`enrich_trades_with_benchmark`を呼んでおらず、TOPIX比較が無い。Trailing Stopは`exit_date`が可変（stopした日、または最大holding_daysに達した日）のため、固定`holding_days`前提の`benchmark_returns_by_signal_date`は使えない。

**レビュー指摘への対応**: 当初案は`signal_date`をキーにした辞書でベンチマークリターンを引く設計だったが、同一`signal_date`に複数銘柄のシグナルがあり、かつ各銘柄のTrailing Stop `exit_date`が異なる場合、1つの`signal_date`キーに複数の値が必要になり成立しない。また`trade.entry_date`はシグナル翌営業日と一致しない場合がある（銘柄固有の売買停止等）。したがって**`signal_date`単位の辞書をやめ、`trade`ごとに直接`entry_date`〜`exit_date`のベンチマークリターンを計算する**方式に変更する。

- [ ] `src/evaluation/inflection_forward.py`に`paired_benchmark_returns(trades: list[TradeResult], benchmark_history: pd.DataFrame, *, round_trip_cost_pct: float) -> list[dict[str, Any]]`を追加する。**`trades`と同じ順序・同じ長さのリストを返す**（`signal_date`キーの辞書にしない）。各tradeについて:
  - `trade.entry_date`/`trade.exit_date`が`None`の場合は`{"benchmark_ticker": ..., "benchmark_net_return_pct": None, "excess_return_pct": None, "beat_benchmark": None}`を返す
  - エントリー価格: ベンチマークの`Open`系列から`index >= trade.entry_date`を満たす最初の値（**trade自身のentry_dateが基準日で、"signal_date翌営業日"を再計算しない**。ベンチマーク側がその日休場等で値がなければ、直後の最初の取引可能日のOpenを使う）とその採用日`benchmark_entry_date`
  - イグジット価格: ベンチマークの`Close`系列から`index <= trade.exit_date`を満たす最後の値（ベンチマーク側にその日の値がなければ、**直前の**最後の取引可能日のCloseを使う。将来日を参照しないことを保証するため「以前」方向にのみ補完する）とその採用日`benchmark_exit_date`
  - **レビュー指摘への対応**: エントリーとイグジットを独立に（前方補完・後方補完それぞれ別方向で）決めているため、ベンチマーク行の欠損が多い短期tradeでは`benchmark_entry_date > benchmark_exit_date`という逆転が起こり得る。**`benchmark_entry_date <= benchmark_exit_date`を必須条件とし、成立しない場合は`benchmark_net_return_pct`等を全て`None`にする**（無効な期間でリターンを計算しない）
  - 上記条件を満たす場合のみ2値から`gross`→`net`（`round_trip_cost_pct`控除）を計算し、`trade.net_return_pct`との差分を`excess_return_pct`とする
  - どちらの価格も見つからない、または日付が逆転する場合は全項目`None`
- [ ] `_build_group_report`の`exit_strategies`生成時、各stop幅・各holding_daysの`trades`に対して`paired_benchmark_returns`を呼び、各trade行へ結果をマージしたうえで`summarize_benchmark_excess`をレポートに追加する
- [ ] このベンチマーク比較にはStep 4の`BENCHMARK_ROUND_TRIP_COST_PCT`を使う

**検証**: 同一`signal_date`に2銘柄のシグナルがあり、片方は早期stop・もう片方は満期closeという、**exit_dateが異なる2trade**を用意し、それぞれの`benchmark_net_return_pct`が個別のexit_dateに対応した異なる値になることを確認するテストを必須で追加する。加えて、`trade.entry_date`がsignal翌営業日と一致しないケース（銘柄側の売買停止を模したデータ）でもベンチマーク側が`trade.entry_date`基準で計算されることを確認する。**ベンチマーク行の欠損により補完後の`benchmark_entry_date`が`benchmark_exit_date`より後になる合成データケースを用意し、`benchmark_net_return_pct`等が`None`になることを確認するテストを追加する。**

#### Step 6: Peak Capture Ratio / Peak Giveback / Early Exit Return を追加する（REQ-013）

**レビュー指摘への対応**: 当初案はPeak系指標を「trade行（dict化後）」に追加する一方、`summarize_trades()`（`Iterable[TradeResult]`を受け取る）にその中央値を追加するとしており、TradeResultの外で計算した値をTradeResultベースの集計関数が参照できないという矛盾があった。Early Exit Returnはexit後の価格データが必要だが、`simulate_signal()`は元々`history`（closes等）にアクセスできる関数であり、exit_dateが決まった時点でまだ`closes`系列がスコープ内にある。したがって**新指標はすべて`TradeResult`のフィールドとして`simulate_signal()`内部で計算し、`summarize_trades()`は既存の`mfe_pct`/`mae_pct`と同じ経路（`trade.xxx`から直接読む）で集計する**方式に統一する。post-hocな別関数は作らない。

- [ ] `TradeResult`（`src/evaluation/inflection_backtest.py:19`）に`peak_giveback_pct: float | None = None`, `peak_capture_ratio: float | None = None`, `early_exit_return_5d_pct: float | None = None`, `early_exit_return_20d_pct: float | None = None`, `early_exit_return_60d_pct: float | None = None`を追加する
- [ ] `simulate_signal()`内、`exit_date`/`exit_price`/`mfe_pct`が確定した後（現行の`return TradeResult(...)`の直前、L192-209付近）で以下を計算する。**Peak GivebackとPeak Capture Ratioで`mfe_pct`の要件が異なる点に注意**（proposal REQ-013はPeak Capture RatioのみMFE正を要求しており、Peak Giveback自体はMFE=0（下落のみでentry_priceがpeakのまま終わったtrade）でも定義可能な値のため、両方を一律`None`にしない）:
  - `mfe_pct is None`の場合のみ`peak_giveback_pct`・`peak_capture_ratio`とも`None`
  - `mfe_pct is not None`なら常に`peak_price = entry_price * (1 + mfe_pct / 100)`、`peak_giveback_pct = (peak_price - exit_price) / peak_price * 100`を計算する（`mfe_pct == 0`即ちPeak Price=Entry Priceの下落オンリーtradeでも計算する）
  - `peak_capture_ratio`は`mfe_pct > 0`の場合のみ`net_return_pct / mfe_pct`、それ以外（`mfe_pct`が`None`または`<= 0`）は`None`
  - Early Exit Return: `closes`系列（関数内で既に取得済み）から`closes.index > exit_date`のうち`N`番目（5/20/60）の値と`exit_price`を比較して算出する。`closes`にその営業日数分のデータがまだ無い場合は`None`（未来のデータを待つのではなく、その時点で計算不能として扱う。REQ-004の`horizon_matured`とは独立に、それぞれのN日ごとに個別に`None`判定する）
- [ ] `summarize_trades()`（`src/evaluation/inflection_backtest.py:249`）に、既存の`mfe`/`mae`収集と同じパターンで`peak_giveback_pct`/`peak_capture_ratio`/`early_exit_return_5d/20d/60d_pct`のリストを`trade.xxx is not None`のtradeから集め、`median_peak_giveback_pct`, `median_peak_capture_ratio`, `median_early_exit_return_5d/20d/60d_pct`として出力する

**検証**: `TradeResult`の新フィールドと`summarize_trades()`の中央値が、同一のtrade集合から一貫して計算されること（明細値の中央値を手計算した値とsummary出力が一致すること）を確認する結合テストを追加する。MFEが正のtradeでpeak_giveback/peak_capture_ratioが期待通り計算されること、**MFE=0（下落のみで終値がentry未満のtrade）でpeak_giveback_pctは数値になりpeak_capture_ratioは`None`になること**、MFEが`None`のtradeで両方とも`None`になることを確認する。Early Exit Returnは、exit後に価格が上昇する合成データ・下落する合成データの両方でテストする。

#### Step 7: 統計的信頼性（bootstrap CI・score band・簡易regime）を追加する（REQ-012）

**regime分類（2026-09-09合意: 簡易実装する）**: TOPIXベンチマーク自身の直近20営業日リターンの符号で「上昇regime」「下落regime」の2値に分類する。厳密なregime判定モデルではなく、サンプル数を分けて見るための簡易ラベルである旨をレポートに明記する。

**レビュー指摘への対応（20営業日分の過去データ不足）**: 現行`_fetch_adjusted_histories()`は`start = min(dates) - timedelta(days=10)`（L78相当）で、最古のsignal dateの10暦日前からしか価格を取得しない。10暦日は営業日換算で高々7日程度のため、20営業日リターンの計算に必要な過去データが最古のsignal付近では不足し、正常なデータでも`regime_label`が`None`（データ不足による`unknown`）になってしまう。ベンチマーク取得だけ開始日を延長する。

**レビュー指摘への対応**: 当初案の「`random.choices`でtradeを1件ずつIID再標本化する」方式は、同一`signal_date`に複数銘柄が同時に上下する市場共通ショックや、同一tickerが複数日に渡って観測される反復依存を無視するため、CIが実際より過度に狭くなる。加えて乱数seedが未固定で、同じ入力でも実行のたびにレポート値が変わってしまう。したがって**個別リターンではなく「クラスタ」単位でリサンプリングするcluster bootstrap**に変更し、seedを固定する。

- [ ] `src/evaluation/inflection_backtest.py`に`BOOTSTRAP_SEED = 1234`（固定seed定数）を追加する
- [ ] `cluster_bootstrap_ci(values: list[float], cluster_keys: list[str], *, n_resamples: int = 2000, confidence: float = 0.95, seed: int = BOOTSTRAP_SEED) -> tuple[float, float] | None`を追加する。`values`と`cluster_keys`（同じ長さ）を受け取り、`cluster_keys`ごとに値をグルーピングしてクラスタ単位でリサンプリング（`random.Random(seed).choices(list(clusters.values()), k=len(clusters))`のように、クラスタという単位で復元抽出し、抽出したクラスタ内の値を展開して平均を取る、を`n_resamples`回繰り返しパーセンタイルを取る）。標準ライブラリのみで実装し、numpyの新規依存は追加しない。**レビュー指摘への対応**: 有効なクラスタ数（ユニークな`cluster_keys`の数）が**2未満の場合は`None`を返す**（クラスタが1つしかないと毎回同じクラスタしか引けず、必ず幅ゼロのCIになり「不確実性がない」という誤ったシグナルになるため。データ蓄積初期でsignal_dateのクラスタが1日分しか無い場合等に該当する）
- [ ] `summarize_trades()`に`sample_count`（既存の`completed`と同義だが明示名として追加）、`mean_net_return_ci95_by_signal_date`（`cluster_keys`に`trade.signal_date`を使用、同日の市場共通ショックへの依存を考慮）と対になる`signal_date_cluster_count`、`mean_net_return_ci95_by_ticker`（`cluster_keys`に`trade.ticker`を使用、同一銘柄の反復観測への依存を考慮）と対になる`ticker_cluster_count`を追加する。どちらか一方に絞らず両方出す（レビュー指摘の「双方のCIを別々に表示」に対応）。クラスタ数を併記することで、CIが`None`の場合に「データ不足で推定不能」と「幅ゼロで真に不確実性が無い」を混同しないようにする
- [ ] `summarize_benchmark_excess()`（`src/evaluation/inflection_forward.py:156`）にも同様に`mean_excess_return_ci95_by_signal_date`と`signal_date_cluster_count`を追加する（excess returnは銘柄跨ぎの日次比較が主目的のため、date単位のみでよい。ticker単位は`summarize_trades`側でカバー済み）
- [ ] 同一入力に対して2回`cluster_bootstrap_ci`を呼び出し、常に同一の結果になることを確認するテスト（固定seedの効果を確認）、クラスタ数0/1/2それぞれでの挙動（0/1件なら`None`、2件以上なら計算される）を確認するテストを追加する
- [ ] score band別サンプル数集計として、`src/evaluation/inflection_backtest.py`に`score_band(score: float) -> str`を追加する。**レビュー指摘への対応**: `load_inflection_signals()`は0〜100の値を許容し、特にNONE分類は50点未満も含まれうるため、`"50-59"`始まりのバケットでは0〜49点と100点ちょうどの所属先が未定義になっていた。`0-9`, `10-19`, ..., `90-99`, `100`（境界含む）で0〜100を完全に覆うバケットにする（`score == 100.0`は専用の`"100"`バケット、それ以外は`int(score // 10) * 10`から`f"{floor}-{floor+9}"`を生成する）
- [ ] `rebuild_inflection_forward_validation.py`で各horizon/exit_strategyのtrade集合をscore bandごとにグループ化してtrade件数を出力する（`score_band_sample_counts: {"0-9": N, ..., "90-99": N, "100": N}`）。**集計対象の母集団は、それぞれの数値が実際に集計されている母集団と一致させる**（`horizons`の各horizonは`completed`なtrade、Trailing Stopは`matured_summary`に対応する`matured`なtradeのみを対象にし、未完了(`net_return_pct is None`)や`horizon_matured is False`のcensored tradeはband集計にも含めない。CIやwin rateのsample countとband件数の合計が一致することを前提とする）。band別の詳細な成績（勝率等）まではこのステップでは出さず件数のみとする
- [ ] `_fetch_adjusted_histories()`（`rebuild_inflection_forward_validation.py`）に`extra_lookback_days: int = 0`引数を追加し、`start = min(dates) - timedelta(days=10 + extra_lookback_days)`に変更する（デフォルト0なら既存呼び出しの挙動を変えない）。`main()`のbenchmark取得呼び出し（`benchmark_rows`に対する`_fetch_adjusted_histories`呼び出し）だけ`extra_lookback_days=35`を指定する（20営業日 ≈ 暦日28〜30日に安全マージンを加えた値。土日・祝日を考慮した概算であり、正確な営業日カレンダー計算はしない）
- [ ] regime定義を明確化する: `regime_label(benchmark_history, signal_date) -> str`を追加し、`"up"` / `"down"` / `"unknown"`のいずれかを返す（`None`ではなく`"unknown"`という明示的な値にして、件数集計で欠落させない）。**20営業日リターンの定義**: `signal_date`以前（`signal_date`を含む）のCloseを新しい順に21本取得できる場合、`return = latest_close / close_20_bars_before - 1`（21本目が20営業日前の基準値）で計算する。21本未満しか取得できない場合は`"unknown"`を返す。**0%の扱い**: `return >= 0` を `"up"`、`return < 0` を `"down"`に分類する（0%ちょうどは`"up"`側に含める、と明記する）
- [ ] 各horizon/exit_strategyのtrade集合をregime別に件数集計する（`regime_sample_counts: {"up": N, "down": N, "unknown": N}`）。**score band集計と同様、対象母集団は各summaryに対応するcompleted/matured tradeのみとし、`up`+`down`+`unknown`の合計がsummaryのsample countと一致するようにする**
- [ ] レポートの適当な箇所（`report`トップレベルまたは各groupの中）に、パラメータ数（5horizon×2分類×3グループ等）が多いため個別の「ベストな組み合わせ」を過信しないよう注意する`multiple_comparisons_caveat`という固定文言フィールドを追加する

**検証**: 既知の分布（例: 全て同じ値のリスト）で`cluster_bootstrap_ci`が有効クラスタ2未満のとき`None`を返すこと、固定seedにより同一入力で同一出力になることを確認する統計的テストを追加する。`score_band`は境界値（0, 9.999, 10, 49.999, 50, 99.999, 100）で期待するバケットに入ることを確認する。`regime_label`は**20営業日リターンが負・ゼロ・正の3パターン**（`"down"`/`"up"`/`"up"`になること）、**21本未満しかCloseが無いケース**（`"unknown"`になること）、および**最古のsignal dateに対して延長後のlookbackで実際に21本分のベンチマークCloseが取得できること**をテストする。score band・regimeいずれの集計もcensored/未完了tradeを含まない母集団になっており、各カテゴリ件数の合計がsummaryのsample countと一致することも確認する。

#### Step 8: 追跡対象プール内でのExplosion Recall / Detection Lead Timeを追加する（REQ-010）

**再定義（2026-09-09合意）**: 全市場に対するRecallではなく、日次スキャンで`deep_candidates`に一度でも入った銘柄（`EARLY_CANDIDATE`/`WATCH`/`NONE`/`OVEREXTENDED`のいずれか）の集合を「追跡対象プール」とし、そのプール内で「爆発した銘柄のうち、爆発前にEARLY_CANDIDATEまたはWATCHとして検知できていた比率」を計算する。レポート上は`explosion_recall_pct`ではなく`tracked_pool_explosion_recall_pct`のように、全市場Recallではないことが分かる名前にする。

**レビュー指摘への対応**: 当初案は計算ロジックのみを記述しており、`rebuild_inflection_forward_validation.py`から呼び出して最終レポートに格納する手順、および価格取得の共有設計（Step 1参照）が欠けていた。以下で明示する。

- [ ] `src/evaluation/inflection_learning.py`は現在`main`ブランチには存在せず、未マージのPR #10（`feat/self-learning-postmortem`）にのみ存在することを確認済み（2026-09-09時点）。したがって本Phaseでは重複を気にせず新規に`src/evaluation/inflection_recall.py`を作成する。**ただしPR #10が本Phase完了前にmainへマージされた場合は、マージ後に`inflection_learning.py`とのロジック重複（スナップショット読み込み・銘柄タイムライン構築等）を再確認し、必要なら統合すること**
- [ ] `inflection_recall.py`に`compute_tracked_pool_explosion_recall(observations: list[dict[str, Any]], histories: dict[str, pd.DataFrame], *, explosion_threshold_pct: float = 50.0, search_horizon_days: int = 252) -> dict[str, Any]`を追加する。引数の`observations`はStep 1で`main()`が取得した4分類ぶんの`signals`（ticker×date×classification×score）、`histories`はStep 1で共有取得済みの`total_return_adjusted`価格系列をそのまま渡す（**この関数の内部では価格取得を行わない**）
- [ ] 関数内部: tickerごとに観測を日付順に並べ、`baseline_date`（そのtickerの最初の観測日、＝スナップショットの`latest_price_date`であり必ずしもそのticker自身の最終取引価格日ではない点に注意）を求める。**レビュー指摘への対応**: `baseline_date`当日にそのtickerのCloseが存在するとは限らない（`latest_price_date`は全銘柄の最大日付であり、個別tickerの実際の価格系列がその日まで届いていないケースがある）。したがって`baseline_price`は`histories[ticker]`のClose系列から`index <= baseline_date`を満たす**直近のClose**を採用し、実際に使った日付を`effective_baseline_date`として保持する。該当するCloseが1件も無い（`baseline_date`より前のデータが無い）tickerは、Recallの分母・分子いずれからも除外し、除外件数を`excluded_no_price_count`として戻り値に含める（fail-closedにはしない。データの疎さを可視化する）
- [ ] `effective_baseline_date`以降`search_horizon_days`営業日以内で`baseline_price`比+50%以上に初めて到達した日を`explosion_date`とする（到達しなければ分母に含めない）。`explosion_date`より前に`EARLY_CANDIDATE`または`WATCH`として観測された日があれば「事前検知」とし、最も早い観測日を`first_detected_date`として`Detection Lead Time = explosion_date - first_detected_date`（**カレンダー日数**。営業日数への変換は行わない。`[要確認: 営業日ベースが望ましければ後日変更]`）を計算する
- [ ] 戻り値のschemaを固定する: `{"tracked_pool_explosion_recall_pct": float | None, "exploded_ticker_count": int, "detected_ticker_count": int, "detection_lead_time_median_days": float | None, "excluded_no_price_count": int, "definition_note": "全市場ではなく、日次スキャンでdeep_candidatesに一度でも入った銘柄プール内でのRecall"}`。**空集合時（`observations`が空、または`exploded_ticker_count == 0`）でも例外を送出せず、`tracked_pool_explosion_recall_pct: None`, `exploded_ticker_count: 0`, `detected_ticker_count: 0`, `detection_lead_time_median_days: None`を返す**
- [ ] `rebuild_inflection_forward_validation.py`の`main()`で、Step 1完了後（`histories`取得後、`report`構築前）に`compute_tracked_pool_explosion_recall(all_observations, histories)`を呼び出し、結果を`report["tracked_pool_explosion_recall"]`に格納する
- [ ] `tests/test_inflection_recall.py`を新規作成し、`.github/workflows/forward_validation.yml`の`Test forward-validation core`ステップ（現行L47-58）の`pytest`対象ファイル一覧と`--cov`対象に本テストファイルと`src.evaluation.inflection_recall`を追加する（追加しないと通常のCIで実行されない）

**検証**: 合成データで (a) 爆発前にEARLY_CANDIDATE観測がある銘柄、(b) 爆発後にしかEARLY_CANDIDATE観測がない銘柄、(c) 一度もEARLY_CANDIDATE/WATCHにならずNONEのみだった銘柄、(d) 爆発しなかった銘柄、(e) **`baseline_date`当日にそのtickerのCloseが欠損している銘柄**（直近の利用可能Closeが`effective_baseline_date`として使われ、`excluded_no_price_count`には計上されないこと）、(f) **`baseline_date`より前に一切価格データが無い銘柄**（`excluded_no_price_count`に計上され分母・分子から除外されること）、の6パターンを用意し、Recallと分母・分子が期待通りになることを確認する。`observations`が空のケースで例外にならず既定のNone/0が返ることも確認する。`main()`から呼んだ結果が`report["tracked_pool_explosion_recall"]`に実際に格納されることを結合テストで確認する。

## 例外・エラーハンドリング方針

- Step 1〜8とも既存のfail-closed方針を踏襲し、価格データ不備時は`RuntimeError`で停止する（Phase 0+1の`_fetch_adjusted_histories`が既に持つリトライ・失敗集約の仕組みをそのまま使う）。
- `cluster_bootstrap_ci`・`compute_tracked_pool_explosion_recall`等の新規統計関数は、入力不足（サンプル数0等）の場合は例外を送出せず`None`または既定値（0件）を返す（既存の`summarize_trades`の"値が無ければNone"という一貫した設計に合わせる）。REQ-013の新規指標は`simulate_signal()`内部に組み込むため、既存のfail-closed方針をそのまま継承する。

## テスト/検証方針

- 自動テスト: `pytest`（`tests/test_inflection_backtest.py`, `tests/test_inflection_forward.py`に追記。REQ-010用に新規テストファイルを追加）
- 手動確認観点: `python scripts/rebuild_inflection_forward_validation.py`を実データ（Phase 0+1完了後、`.enc`スナップショットが蓄積された状態）で実行し、`groups.early_candidate/watch/none`それぞれにhorizons(5/20/60/126/252)・exit_strategies(3stop×3horizon)・CI・score band・regime・peak系指標・tracked_pool_explosion_recall_pctが期待通り出力されることを確認する

## リスクと対策

1. リスク: REQ-011で4分類（EARLY/WATCH/NONE/OVEREXTENDED）分の観測を扱うため、`rebuild_inflection_forward_validation.py`の実行時間・yfinance API呼び出し数が増える → 対策: Step 1でticker集合を事前に和集合化し、価格取得を1回にまとめることで増加を抑える。現行の`.github/workflows/forward_validation.yml`の`validate` jobの`timeout-minutes`は**30分**（45分ではない、訂正済み）。実装後にローカルまたは1回のActions実行で実測し、30分に収まらない場合はtimeout延長を検討する。
2. リスク: REQ-008でhorizonを252日に伸ばすと、Shadow Scanのデータ蓄積が始まったばかり（2026-09-09時点）のため、当面ほとんどのsignalが`horizon_matured=False`となり126/252日の集計はほぼ空になる → 対策: `eligible_count`/`censored_count`（Phase 0+1で追加済み）でサンプル不足を可視化する。空でもエラーにはしない。
3. リスク: REQ-010のExplosion Recallが「全市場」ではなく「追跡対象プール内」であることが将来誤読される可能性がある → 対策: フィールド名を`tracked_pool_explosion_recall_pct`とし、レポート内に定義の注記文字列を追加する。
4. リスク: REQ-010着手時点では`main`に`inflection_learning.py`は存在しない（PR #10は未マージ）が、本Phase実装中にPR #10がマージされると新規作成する`inflection_recall.py`と機能重複する可能性がある → 対策: 実装直前に`git log --all -- src/evaluation/inflection_learning.py`等でマージ状況を再確認し、マージ済みなら統合を検討してからStep 8に着手する。

## 完了条件

- [ ] `groups.early_candidate/watch/none`の3グループ構造でレポートが生成される（REQ-011）
- [ ] `horizons`に`h5/h20/h60/h126/h252`が出力される（REQ-008）
- [ ] `exit_strategies`に3stop幅×3holding_days（60/126/252）=9通りが出力される（REQ-009）
- [ ] ベンチマーク往復コストが個別株のbase/stressと独立した固定値（0.05%）になっている（REQ-015）
- [ ] `exit_strategies`の各tradeにpaired benchmark excessが付与されている（REQ-016）
- [ ] 各tradeに`peak_giveback_pct`, `peak_capture_ratio`, Early Exit Return（5/20/60日）が付与され、`summarize_trades`にmedianが出力される（REQ-013）
- [ ] `summarize_trades`/`summarize_benchmark_excess`にbootstrap CIが出力され、score band別・regime別のサンプル数集計が出力される（REQ-012）
- [ ] `report["tracked_pool_explosion_recall"]`に`tracked_pool_explosion_recall_pct`とDetection Lead Timeの中央値が`main()`から実際に呼び出されて格納される（REQ-010）。`tests/test_inflection_recall.py`がCI（`forward_validation.yml`）で実行される
- [ ] 上記すべてに対応するユニットテストが追加され、`pytest`が成功する
