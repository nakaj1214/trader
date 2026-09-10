# 実装計画: REQ-014 — ポートフォリオレベル評価（Portfolio Simulation）

> 入力: `memo/implement/proposal.md` の REQ-014（132-138行目）のみを対象とする。
> `memo/implement/plan.md`（REQ-023〜026）、`plan_phase3.md`（REQ-018,019,021,022）、`plan_req027.md`（REQ-027）とは独立。いずれも上書きしないよう別名にしている。
> 3文書中で最も工数見積りが大きい要件（proposal記載: 16〜40時間）であり、依存関係とスコープの検討に特に時間をかけている。

## 前提: 依存要件の状態確認

REQ-014は個別trade評価の上に成り立つため、着手前に前提REQの実装状況をコードで確認した。

| 前提REQ | 内容 | 状態 |
|---|---|---|
| REQ-008/009 | 126/252営業日horizonの追加 | 実装済み（`scripts/rebuild_inflection_forward_validation.py:271,314`で`h126`/`h252`と`trailing_*_h126`/`h252`が存在） |
| REQ-012 | 信頼区間・クラスタ集計 | 実装済み（`cluster_bootstrap_ci`, `src/evaluation/inflection_backtest.py:281-318`） |
| REQ-013 | Peak Capture / Peak Giveback / Early Exit Return | 実装済み（`TradeResult`のフィールド, `src/evaluation/inflection_backtest.py:39-43,199-241`） |
| REQ-015 | ベンチマークと個別株のコスト分離 | 実装済み（`ROUND_TRIP_COST_PCT` / `STRESS_ROUND_TRIP_COST_PCT` / `BENCHMARK_ROUND_TRIP_COST_PCT`） |
| REQ-016 | Trailing Stopのpaired benchmark比較 | 実装済み（`_paired_trade_rows`, `paired_benchmark_returns`） |

したがってREQ-014は前提待ちではなく、既存の`_build_group_report`が生成する`TradeResult`群の上に新しい集計レイヤーを追加すればよい状態にある。

## 現状（Before）の正確な把握

- `src/evaluation/inflection_backtest.py`の`simulate_signal`は、**1シグナル=1取引**を資金制約なしで独立にシミュレートする（資金・同時保有数を考慮しない）。
- `select_non_overlapping_trades`（同ファイル255-274行目）は「同一tickerの重複保有を1つに絞る」だけで、tickerをまたいだ同時保有数・現金制約は扱っていない。
- `scripts/rebuild_inflection_forward_validation.py:430`で`"portfolio_interpretation": False`を明記しており、レポート自身が「これはポートフォリオ全体の収益ではない」と宣言している。
- ポートフォリオ視点の指標（最大同時保有数、資金配分、セクター集中、Portfolio Drawdown、Equity Curve、Cash utilization、Exposure、Turnover、CAGR）は一切実装されていない。

## データ面の事前調査（着手前に必須の確認）

1. **セクター（業種）データは現状どこにも存在しない。**
   - `src/screening/inflection_live.py`が`client.listed_issues()`（J-Quants `/equities/master`）から使っているのは`Code`, `Mkt`, `MktNm`, `CoName`のみ（`ticker_meta`構築部, 280-285行目）。
   - テストfixture（`tests/test_inflection_live.py:24-30`）にも業種フィールドは存在しない。
   - `plan_phase3.md`のREQ-022実装ステップでも「業種分類のフィールド名は`[要確認: 実際のレスポンスを確認してから実装する]`」として**未解決のまま**になっている（`plan_phase3.md:78`）。
   - → **結論: 「同業種集中」の上限判定は本計画のスコープ外とする。** 業種データの取得元が確定していない状態でセクター上限だけ先行実装すると、REQ-022の業種取得実装とデータ構造が重複・不整合になるリスクが高い。詳細は下記「スコープ判断」参照。
2. **市場区分（Prime/Standard/Growth）とavg_turnover_20d_jpyは既にsnapshotに保存されている。**
   - `LiveCandidate`（`src/screening/inflection_live.py:34-50`）は`market`と`avg_turnover_20d_jpy`を保持し、`scan_japan_inflection()`の戻り値`candidates`（同ファイル414行目`[candidate.as_dict() for candidate in candidates]`）経由でそのまま暗号化snapshotに書き込まれている（`scripts/run_inflection_shadow.py`の`persist_report`は`report`を素通しするだけ）。
   - しかし`load_inflection_signals`（`src/evaluation/inflection_forward.py:99-113`）はこの2フィールドを**読み捨てている**（ticker/score/classification等しか抽出しない）。データ移行なしに読み出し側を拡張するだけで使えるようになる。
3. **現状のsnapshot蓄積数は1日分のみ**（`dashboard/data/inflection/`に`.enc`が1件）。ポートフォリオ指標（CAGR・Max Drawdown等）は複数日・複数銘柄が重なって初めて意味を持つため、実装直後の出力はほぼ空または退化した値になる。これはバグではなくデータ蓄積待ちであることをレポート内に明記する（完了条件参照）。

## スコープ判断（簡略化した点と理由）

proposalの Before/After（132-138行目）が要求する要素のうち、以下は意図的に簡略化・対象外とする。各項目に理由と拡張時の入口を記す。

1. **セクター上限は対象外。** 理由: 上記の通り業種データが存在しない。市場区分別（Prime/Standard/Growth）のexposure内訳は診断情報として出力するが、上限として強制はしない（proposalが求めるのは「同業種」であり市場区分の代用は意味が異なるため、代用ではなく別カテゴリの診断値として明示する）。拡張時: REQ-022で業種フィールドが確定した後、`同一業種の保有比率が閾値を超える新規entryをスキップする`ロジックを追加する。
2. **Position sizingは「初期資金に対する固定比率」とし、複利（時価評価額に対する比率）にはしない。** 理由: 時価ベースの比率にすると含み益・含み損でポジションサイズが動的に変わり、検証ロジックが複雑化する。固定比率は「毎回同じ金額の枠を使う」という最も単純で説明可能なルールであり、proposalの「position sizing」という要求を満たす最小実装。拡張時: `position_size_mode: "fixed_fraction_of_initial" | "fixed_fraction_of_equity"`のような切替を追加する。
3. **ポートフォリオシミュレーションは1つの既定構成（EARLY_CANDIDATE群・保有60営業日・通常コスト0.2%）のみに対して実行する。** 現行の`_build_group_report`は5horizon×3群＋3stop幅×3horizon×3群のすべての組み合わせを生成しており、これら全てにポートフォリオシミュレーション（日次時価評価ループ）を重ねるとCI予算（`forward_validation.yml:33`の`timeout-minutes: 30`）を圧迫するリスクがある。拡張時: 既定構成での実装・検証が安定してから、他のhorizon/exit_strategy組み合わせへ展開するかを別途判断する。
4. **銘柄の売買単位（100株単位）・板厚/ADVに対する参加比率制限はモデル化しない。** 既存の`simulate_signal`も端株を許容する金額ベースのシミュレーションであり、この抽象度に合わせる。`avg_turnover_20d_jpy`は診断情報（新規entry時点のADVに対するposition sizeの比率）としてのみ記録し、発注のブロック条件にはしない。既存の`execution_limitations`（`scripts/rebuild_inflection_forward_validation.py:442-446`）に`position_capacity_not_modeled`を追記して明示する。
5. **資金・スロット不足で入れなかったsignalは「先送り」せず「その日は機会損失」として扱う。** 理由: entry価格は「シグナル翌営業日の始値」に固定されており、後日改めてentryする設計にすると、どの価格で入るかの恣意性が生まれ、他の評価ロジック（point-in-time原則）と矛盾する。`[要確認: この機会損失方式でよいか。後日再挑戦する設計が必要な場合は別途要件化する]`

## 変更対象

- `src/evaluation/inflection_forward.py`（`load_inflection_signals`の拡張のみ）
- `src/evaluation/inflection_portfolio.py`（新規: ポートフォリオシミュレーション本体）
- `scripts/rebuild_inflection_forward_validation.py`（レポートへの配線、`portfolio_interpretation`の更新）
- `tests/test_inflection_forward.py`（`load_inflection_signals`拡張分のテスト追記、`main()`のテストへ`portfolio_summary`の検証追加）
- `tests/test_inflection_portfolio.py`（新規: シミュレーション本体の単体テスト）
- `README.md`（Forward Validationセクションへポートフォリオ指標の説明を追記）

## 実装ステップ

### 1. `load_inflection_signals`が`market`と`avg_turnover_20d_jpy`を保持するようにする

対象: `src/evaluation/inflection_forward.py:99-113`

- `signals[key] = {...}`の辞書に`"market": candidate.get("market")`と`"avg_turnover_20d_jpy": candidate.get("avg_turnover_20d_jpy")`を追加する。両方とも欠損時は`None`許容とし、スキーマ検証（`SnapshotLoadError`）の対象にはしない（既存の`jquants_plan`等と同じ「あれば使う」方針に合わせる。理由: 過去snapshotとの後方互換のため必須項目にはできない）。
- 既存の型チェック関数は変更しない。追加フィールドは診断・ポートフォリオ集計専用。

検証:

- 新規テスト: `market`/`avg_turnover_20d_jpy`を含むcandidateペイロードから復号したsignalに両フィールドが正しく含まれること。
- 既存テスト（`test_load_inflection_signals_filters_to_early_candidates`等）は、フィールドが存在しないfixtureでも`None`のまま失敗しないことを確認する回帰チェックとして流用する。

### 2. `src/evaluation/inflection_portfolio.py`を新規作成する

`src/evaluation/inflection_recall.py`と同じ構成（フリー関数＋辞書を返す、副作用なし、`histories`は呼び出し側が用意した`dict[str, pd.DataFrame]`を受け取るだけ）に合わせる。`src/evaluation/inflection_backtest.py`の`_series`・`_true_max_drawdown_pct`をそのまま再利用する。

#### 2-1. 入力・パラメータ

```python
def simulate_portfolio(
    signals: list[dict[str, Any]],
    trades: list[TradeResult],
    histories: dict[str, pd.DataFrame],
    calendar: pd.DatetimeIndex,
    *,
    initial_capital_jpy: float,
    max_positions: int,
    position_size_pct: float,
) -> dict[str, Any]:
```

- `signals`と`trades`は`simulate_signals(signals, histories, holding_days=60, round_trip_cost_pct=ROUND_TRIP_COST_PCT, apply_tax=False)`の呼び出し元・戻り値をそのまま**同じ順序で**渡す（zip前提。長さ不一致は`ValueError`）。
- `calendar`には、呼び出し側（`rebuild_inflection_forward_validation.py`）が既に取得済みの`benchmark_history`（`1306.T`, TOPIX ETF）の日付indexをそのまま渡す。TOPIX ETFは全営業日で取引されるため、TSE営業日カレンダーの代用として使う（新規のカレンダー取得コードを増やさない）。
- 入力検証: `initial_capital_jpy > 0`, `max_positions >= 1`, `0 < position_size_pct <= 1.0`, `max_positions * position_size_pct <= 1.0 + 1e-9`（スロット数×比率が資金を超える設定は構成ミスとして拒否する）。

既定値（呼び出し側の定数として定義。**`[要確認: 以下は仮値。実運用を想定した妥当な初期資金・最大保有数か確認が必要]`**）:

- `initial_capital_jpy = 3_000_000`
- `max_positions = 8`
- `position_size_pct = 1 / 8`（均等配分）

#### 2-2. 実行可能trade抽出とイベントスケジューリング

- `trades`のうち`trade.entry_date is not None and trade.exit_date is not None`のものだけを対象にする（価格データ欠損・horizon未成熟は除外。h60固定horizonでは`exit_date is not None`は`horizon_matured is True`と等価であることを`simulate_signal`のロジックから確認済み — `trailing_stop_pct=None`の分岐では`has_full_horizon`を満たさない限りexit自体が発生しない）。
- 各対象tradeを`(entry_date, -score, ticker)`でソートし、同一entry_dateの中ではスコア降順・ticker昇順（決定的タイブレーク）で処理順を決める。
- 日付ごとに次の順でイベントを処理する（同日内で**exit → entry**の順にすることで、同日退出した資金を同日entryに再利用できるようにする。これは非現実的な先読みではなく、「引ける現金は使える」という単純な会計上の順序）。
  1. その日が`exit_date`のポジションを閉じる: 実現損益を計算して現金に反映し、保有スロットを1つ空ける。
  2. その日が`entry_date`のtradeを、ソート順（スコア降順）に評価する。次の条件をすべて満たせば実行する。
     - 対象tickerに現在オープン中のポジションがない（`same_ticker_overlap_policy: one_open_position_per_ticker`と同じ制約をここでも適用）。
     - オープン中ポジション数 `< max_positions`。
     - 現金 `>= initial_capital_jpy * position_size_pct`。
     条件を満たさない場合はスキップし、理由別（`skipped_ticker_conflict` / `skipped_slot_full` / `skipped_insufficient_cash`）にカウントする。実行された場合は`entry_price`で`shares = (initial_capital_jpy * position_size_pct) / entry_price`分を購入したとみなし、現金から差し引く。
- 全対象tradeを処理し終えた後も残る「一度も実行されなかったtrade」は`executed_trades`に含めない。

#### 2-3. 日次Equity Curve

- `calendar`のうち、最初のentry_dateから最後のexit_dateまでの範囲でループする（それ以前・以後は現金のみで変動がないため計算不要）。
- 各日の評価額 = 現金 + Σ(オープン中ポジションの`shares × その日のClose`)。オープン中ポジションのCloseは`_series(histories[ticker], "Close")`を`calendar`にreindexし前方補完（`ffill`）した値を使う（個別銘柄の休場日ズレに対する近似であることをdocstringに明記する）。
- 得られた`equity_series: pd.Series`から:
  - `final_equity_jpy = float(equity_series.iloc[-1])`
  - `max_drawdown_pct = _true_max_drawdown_pct(initial_capital_jpy, equity_series)`（既存関数をそのまま再利用）
  - `elapsed_calendar_days = (equity_series.index[-1] - equity_series.index[0]).days`
  - `cagr_pct`: `elapsed_calendar_days > 0`かつ`final_equity_jpy > 0`のとき`((final_equity_jpy / initial_capital_jpy) ** (365.25 / elapsed_calendar_days) - 1) * 100`、それ以外は`None`。
  - `mean_open_position_count` / `max_open_position_count`: 日次のオープン数の平均・最大。
  - `mean_cash_utilization_pct`: 日次の`(initial_capital_jpy - cash) / initial_capital_jpy`の平均。

#### 2-4. 既存集計の再利用（新規実装しない部分）

- 勝率・Profit Factor・平均/中央値リターン・信頼区間は、`executed_trades`（`TradeResult`のリスト）に対して既存の`summarize_trades()`（`src/evaluation/inflection_backtest.py:330-392`）をそのまま呼び出して`"trade_summary"`として埋め込む。**この部分は新規ロジックを書かない。**
- `turnover_ratio = 総entry想定元本(=len(executed_trades) * initial_capital_jpy * position_size_pct) / mean(equity_series)`として定義する（期間全体のturnoverであり年率換算はしない。単位・定義をdocstringと出力キー名`turnover_ratio_period_total`に明記する）。

#### 2-5. 診断情報（exposure・skip理由）

- `exposure_by_market_pct`: `executed_trades`に対応する`signals`の`market`フィールドで集計した、実行済みtrade件数に対する構成比（Prime/Standard/Growth/不明）。上限を強制しない診断値であることを明記する。
- `avg_turnover_capacity_ratio_median`: 各`executed_trade`について`(initial_capital_jpy * position_size_pct) / signal["avg_turnover_20d_jpy"]`（=そのポジションが20日平均売買代金の何%を占めるか）の中央値。`avg_turnover_20d_jpy`が`None`または0の場合は除外する。診断値であり発注可否には使わない。
- `skipped_ticker_conflict_count` / `skipped_slot_full_count` / `skipped_insufficient_cash_count`: 上記2-2のスキップ理由別件数。

#### 2-6. 戻り値の例

```json
{
  "config": {
    "initial_capital_jpy": 3000000,
    "max_positions": 8,
    "position_size_pct": 0.125,
    "source_horizon": "h60",
    "source_cost_scenario": "base"
  },
  "executed_trade_count": 0,
  "skipped_ticker_conflict_count": 0,
  "skipped_slot_full_count": 0,
  "skipped_insufficient_cash_count": 0,
  "final_equity_jpy": null,
  "cagr_pct": null,
  "max_drawdown_pct": null,
  "elapsed_calendar_days": 0,
  "mean_open_position_count": null,
  "max_open_position_count": 0,
  "mean_cash_utilization_pct": null,
  "turnover_ratio_period_total": null,
  "exposure_by_market_pct": {},
  "avg_turnover_capacity_ratio_median": null,
  "trade_summary": { "...": "summarize_trades()の出力" },
  "caveat": "..."
}
```

`executed_trade_count == 0`（現状の1日分snapshotでは確実に発生する）の場合、`final_equity_jpy`等は`None`または空集計を返し、例外は送出しない（既存の`summarize_trades`が空リストに対して`None`を返す挙動と揃える）。

### 3. `scripts/rebuild_inflection_forward_validation.py`への配線

対象: `_build_group_report`は変更せず、`main()`内で以下を追加する。

- `groups`の構築ループ（469-481行目）の**後**に、`early_candidate`用の`signals`（既にループ内で`classification == "EARLY_CANDIDATE"`に絞ったもの。ループ変数を保持するよう軽微にリファクタする）に対して`simulate_signals(signals, histories, holding_days=60, round_trip_cost_pct=ROUND_TRIP_COST_PCT, apply_tax=False)`をもう一度呼び出す。
  - **これは新規のネットワーク取得やAPI呼び出しを伴わない**（`histories`は既に397行目で取得済みのものを再利用するだけの、メモリ内のpandas演算）。CI時間予算への影響は無視できる想定。`_build_group_report`内で既に同じ呼び出しをしているため計算の重複はあるが、re-run costはCPUのみで軽微。`[要確認: 実測でCI実行時間が有意に増える場合は、_build_group_reportの戻り値からh60 tradesを再利用する形にリファクタする]`
  - 得られた`trades`と対応する`signals`を`simulate_portfolio(...)`へ渡し、`portfolio_summary`を得る。
- `report`辞書に`"portfolio_summary": portfolio_summary`を追加する（`"groups"`と同階層）。
- `"portfolio_interpretation": False`（430行目）を`True`に変更し、直後に`"portfolio_interpretation_note"`として次の趣旨の文字列を追加する:「`portfolio_summary`はEARLY_CANDIDATE群・60営業日保有・通常コストのみを対象とした単一構成のシミュレーションである。他のhorizon/exit_strategyの組み合わせはtrade単位の評価のみで、ポートフォリオ集計はまだ提供していない。CAGR/Max Drawdownはsnapshot蓄積日数が少ないうちは統計的に意味を持たない。」
- `execution_limitations`（442-446行目）に`"position_capacity_not_modeled"`（ADV参加比率・板厚を無視している）と`"lot_size_not_modeled"`（100株単位を無視している）を追記する。

検証:

- `tests/test_inflection_forward.py`の`test_main_writes_three_groups_and_tracked_pool_recall`に、`report["portfolio_summary"]`が存在し`executed_trade_count`等の主要キーを含むことのアサーションを追加する。
- `test_group_report_has_all_horizons_stops_and_aligned_breakdowns`は変更不要（`_build_group_report`自体は無変更のため）。

### 4. README更新

対象: `README.md`のForward Validationセクション（103-124行目付近）。

- 「ポートフォリオレベルの評価」として、対象範囲（EARLY_CANDIDATE・60営業日・通常コストのみ）、初期資金・最大保有数・配分比率の既定値、セクター上限は未実装であること、CAGR/Max Drawdownは十分なsnapshot蓄積後にのみ意味を持つことを明記する。

## テスト/検証方針

- 自動テスト: `pytest`。`tests/test_inflection_portfolio.py`を新規作成し、`tests/test_inflection_backtest.py`と同じ流儀（`_history()`ヘルパーで合成OHLCFデータを作り、実APIに接続しない）で以下を検証する。
  1. 資金・スロットに余裕がある場合、全executable tradeが実行され`executed_trade_count`が一致すること。
  2. 同一entry_dateで資金/スロットが不足するケースで、スコアが高い方が優先されスコアが低い方が`skipped_slot_full_count`または`skipped_insufficient_cash_count`にカウントされること（先送りされず「その回は不参加」であることも確認する＝後続日で再度entryされていないこと）。
  3. 同一tickerに未決済ポジションがある間、新規entryが`skipped_ticker_conflict_count`としてスキップされること。
  4. 既知の価格パスから手計算した`final_equity_jpy`・`max_drawdown_pct`・`cagr_pct`が一致すること（トレード期間中に含み損の谷があるケースを含め、日次mark-to-marketでdrawdownが検出されることを確認する＝trade境界だけでなく日次で評価していることの回帰テスト）。
  5. `executed_trades`が0件のとき例外を送出せず、`None`/空の集計を返すこと（現状のsnapshot1件シナリオを模したケース）。
  6. `max_positions * position_size_pct > 1.0`等の不正な構成で`ValueError`になること。
  7. `exposure_by_market_pct`が`signals`の`market`フィールドから正しく集計されること（`market`が欠損した信号は「不明」区分に入ること）。
- `tests/test_inflection_forward.py`: `load_inflection_signals`が`market`/`avg_turnover_20d_jpy`を保持することのテストを追加。`main()`のテストに`portfolio_summary`存在確認を追加。
- 手動確認観点（operator-run）: `python scripts/rebuild_inflection_forward_validation.py`を実行し、`artifacts/inflection_forward_validation.json`の`portfolio_summary`が例外なく出力されること、`executed_trade_count`が現状のsnapshot件数に対して妥当な値（現状は0または極小）になることを目視確認する。

## リスクと対策

1. リスク: セクター上限を実装しないため、proposalのAfter記述（「セクター上限を考慮した」）を字面通りには満たさない → 対策: 「スコープ判断」節に理由（業種データ未取得、REQ-022が同じ理由で保留中）を明記し、`[要確認]`としてユーザー判断を仰ぐ。市場区分の診断値で部分的に代替する。
2. リスク: 初期資金・最大保有数・配分比率が実運用と乖離した仮値になる → 対策: 定数化してコード1箇所（`inflection_portfolio.py`の呼び出し引数）を変えるだけで調整できる設計にし、README/plan双方に`[要確認]`として明記する。
3. リスク: 日次mark-to-marketのために`histories`を`calendar`へreindex+ffillする際、個別銘柄の出来高停止・データ欠損期間があると評価額が実態とずれる → 対策: 既存の`_fetch_adjusted_histories`は「価格データが空/不足なら丸ごと失敗させる」fail-closed設計（`scripts/rebuild_inflection_forward_validation.py:123-124`）のため、対象期間中に大穴が開いたヒストリーはそもそも上流で弾かれる。ffillは数日程度の休場ズレの吸収にとどまる想定であることをdocstringに明記する。
4. リスク: CI実行時間（30分予算）への影響 → 対策: 新規のAPI呼び出しを増やさず、既取得の`histories`に対するメモリ内シミュレーションのみで完結させる設計にした（実装ステップ3参照）。導入後に実測し、有意な増加があれば`_build_group_report`からのtrade再利用へリファクタする。
5. リスク: 現状snapshotが1日分のみで`executed_trade_count=0`になり、機能追加の効果が当面レポート上で確認しづらい → 対策: これはバグではなくデータ不足であることを`portfolio_interpretation_note`に明記し、単体テストで「0件でも例外にならない」ことを保証する。実データでの意味のある検証は、snapshotが複数日・複数銘柄蓄積してから改めて行う。
6. リスク: 「同日中にexitした資金を同日entryに再利用する」処理順序が、時刻情報のない日次シミュレーションにおいて楽観的すぎる（実際は寄り付き成行決済と寄り付き新規発注が同時刻に処理可能とは限らない） → 対策: この前提を実装ステップ2-2とdocstringに明記し、保守的に倒したい場合は処理順序を「entry優先」に変える1行の変更で切替可能な設計にする（`[要確認: 同日再利用を許可する前提でよいか]`）。

## 完了条件

- [ ] `load_inflection_signals`が`market`/`avg_turnover_20d_jpy`を保持し、欠損時も例外を送出しない（後方互換）
- [ ] `src/evaluation/inflection_portfolio.py`が、現金制約・最大同時保有数・均等配分position sizing・同一ticker重複禁止を考慮したポートフォリオシミュレーションを提供し、CAGR・Max Drawdown・Equity Curve由来の指標・Turnover・Cash Utilization・Exposure内訳・勝率/Profit Factor（既存`summarize_trades`再利用）を算出する
- [ ] `artifacts/inflection_forward_validation.json`に`portfolio_summary`が追加され、`portfolio_interpretation`が`True`になり、対象範囲（EARLY_CANDIDATE・h60・通常コストのみ）が`portfolio_interpretation_note`で明示される
- [ ] `execution_limitations`に`position_capacity_not_modeled`・`lot_size_not_modeled`が追記される
- [ ] セクター上限が未実装であることと、市場区分別exposureが診断目的の代替値であることがREADME/レポートの両方に明記される
- [ ] 上記すべてに対応するユニットテスト（`tests/test_inflection_portfolio.py`新規、`tests/test_inflection_forward.py`追記）が追加され、`pytest`が成功する
- [ ] `python scripts/rebuild_inflection_forward_validation.py`をローカル実行し、`portfolio_summary`が例外なく出力されることを手動確認する
