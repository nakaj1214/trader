## 実装計画: 価格取得の共通化と、自己学習の昇格判定の統計的補強 — REQ-042 / REQ-043 / REQ-044

> 入力: [proposal.md](proposal.md)
> 以前の plan.md（B1、REQ-039〜041、実装済み）は [plan_req039-041.md](plan_req039-041.md) に移した。

### 目的
週次 CI の価格取得を、forward と learning で共通の1回のバッチ取得にまとめ、データが増えても30分の制限に収まるようにする（REQ-042）。自己学習の昇格判定に、有意性検定と多重比較の補正を入れる（REQ-043）。「爆発」の定義を1か所に集約し、ボラティリティで正規化した定義を診断用に併記する（REQ-044）。戦略、snapshot、本番のスコアは変えない。

### 前提（Step 0 で満たす）
- A9 の修正は `d610dfa` でコミット済み（2026-10-01、別セッション）。REQ-042 は、このコミットの挙動（split only 基準 = `auto_adjust=False` の OHLC をそのまま使う）を基準にする。

### 提案からの変更点（調査で判明した事項）
1. **split only 基準の定義が A9 で変わった。** 提案は「`history(auto_adjust=False, actions=True)` → `split_adjust_ohlc`」の値と一致させるとしていた。しかし A9 で `split_adjust_ohlc` は削除され、split only 基準は「**`auto_adjust=False` の OHLC をそのまま使う**」になった（Yahoo の値はすでに分割調整済みであるため）。REQ-042 は、この**A9 修正後の挙動**と一致させる。
2. **total return 基準は、yfinance 自身の `yfinance.utils.auto_adjust()` で導出する。** これは `Adj Close / Close` の比を O/H/L に掛ける公開関数で、`history(auto_adjust=True)` が内部で使う処理と同じ。計算式をこちらで書き直さない。
3. **取得期間は、forward と learning で共通の1つの期間にする**（review #1）。開始は「**legacy（`dashboard/data/inflection/`）と v3 の両方の snapshot のうち、最も早い日付** − 100日」、終了は「今日 + 1日」とする（提案は −45日）。100日は、REQ-044 のボラティリティの計算に必要な、シグナル日より前の60営業日分のリターン（61本の終値）に、祝日と余裕を足した値である。snapshot の日付はファイル名（`YYYY-MM-DD.enc`）から取れるので、復号せずに計算できる。この計算は共通の関数 `shared_price_window(snapshot_dirs, today)` に置き、forward と learning の両方が使う。**引数には、CLI で解決した実際の入力ディレクトリを渡す**（既定のディレクトリを関数の中で決め打ちしない。再レビュー #1）。既定の実行では、両方の処理が同じ2つのディレクトリ（`dashboard/data/inflection/v3/` と `dashboard/data/inflection/`）を渡すので、期間が一致する。forward が評価する対象は、これまでどおり v3 だけである（期間を揃えるのは取得だけ）。
4. **Fisher の検定は両側にする**（提案は「方向別の片側」）。lift の向きを見てから片側検定の方向を選ぶと、事実上の検定数が倍になり、偽の昇格が増えるため。p 値は両側で計算し、方向は lift と超過リターンの符号で決める（現行の方向判定のまま）。
5. **既存の取得テストは書き直しが必要である。** `tests/test_inflection_forward.py`（14か所）と `tests/test_inflection_learning.py`（7か所）は `yfinance.Ticker` または `yfinance.download` を直接モックしている。取得の経路が変わるので、テストの観点（再試行、5%の許容、銘柄名の秘匿、ログの抑制、取得期間）は維持したまま、新しいモジュールに対するテストへ移す。
6. **価格ハッシュは、銘柄ごとに従来の取得期間で切り出したフレームから計算する**（review #2）。`_history_row_hashes` は、フレームの先頭行だけをその行自身の OHLC で正規化し、それ以外の行は前日の終値で正規化する。そのため、取得の開始を早めると、従来は先頭だった日付が途中の行になり、価格が同じでもハッシュが変わって、偽の「改訂」が記録される。そこで、評価やボラティリティには広い期間のフレームを使い、ハッシュの計算にだけ、従来と同じ開始日（その銘柄の最も早いシグナル日 − 10日、ベンチマークは − 45日）以降を切り出したフレームを渡す。`_changed_price_rows` は保存済みの日付と新しい日付の共通部分だけを比べるので、終了側が延びても改訂にはならない。
7. **未完了の horizon では、ボラティリティ正規化の爆発を `None` にする**（review #3）。直近の観測では、σ を計算できる61本の過去の終値があっても、h60 などの最大リターンはまだ `None` である。`is_vol_explosion` は、最大リターン・σ のどちらかが `None` なら `None` を返す。learning は、horizon が未完了（`completed=False`）なら関数を呼ばずに `vol_explosive=None` とする。

### スコープ
- 含むもの: REQ-042、REQ-043、REQ-044 と、それらのテスト
- 含まないもの: 昇格の「連続複数週」条件、Beta-Binomial、ボラティリティ正規化の爆発を昇格判定に採用すること、workflow の制限時間の変更、戦略・snapshot・本番スコアの変更

### 影響範囲（変更/追加予定ファイル）
- `src/data/forward_prices.py`（新規）: バッチ取得、2基準の導出、job 内キャッシュ、取得失敗の許容
- `scripts/rebuild_inflection_forward_validation.py`: `_fetch_adjusted_histories` を新モジュールに置き換える（3回の取得 → 1回）
- `scripts/rebuild_inflection_learning.py`: `_fetch_learning_histories` を新モジュールに置き換える（キャッシュを利用）
- `src/evaluation/explosion.py`（新規）: 爆発の定義の定数と、ボラティリティ正規化の判定関数
- `src/evaluation/inflection_learning.py`: Fisher 検定、BH 補正、Wilson 信頼区間、昇格条件、ボラティリティ正規化の爆発、定義の出力
- `src/evaluation/inflection_recall.py`、`src/evaluation/inflection_backtest.py`: 定数を `explosion.py` から import する（値は変えない）
- `tests/test_forward_prices.py`、`tests/test_explosion.py`（新規）、`tests/test_inflection_forward.py`、`tests/test_inflection_learning.py`（取得テストの移し替え、新しい判定のテスト）
- `.github/workflows/test.yml`: mypy 対象に新規ファイルを追加
- `.gitignore`: 変更不要（`artifacts/` は無視済み）

### 実装ステップ

#### Step 0: 前提を満たす
- [ ] 作業ツリーに、他のセッションの未コミットの変更（特に REQ-042 が変更するファイル）がないことを `git status` で確認する。あれば着手しない（ユーザーに報告して待つ）
- [ ] `pytest tests/` が PASS することを確認する（着手前の基準線）
**検証**: 作業ツリーに A9 の未コミット変更がない

#### Step 1: REQ-044 — 爆発の定義を集約する（値は変えない）
- [ ] `src/evaluation/explosion.py` を作り、次を名前付きの定数として置く。それぞれの意味をコメントで明記する
  - `HORIZON_MAX_RETURN_PCT = {5: 15.0, 20: 25.0, 60: 40.0, 120: 60.0}`（learning。horizon 別、保有期間中の最大リターン）
  - `FIXED_MAX_RETURN_PCT = 50.0`（backtest の `explosive_50pct`。保有期間中の最大リターン）
  - `TRACKED_POOL_THRESHOLD_PCT = 50.0` と `TRACKED_POOL_SEARCH_DAYS = 252`（recall。最初の観測日の終値から、252営業日以内に +50% の終値）
  - `VOL_EXPLOSION_K = 3.0`、`VOL_LOOKBACK_SESSIONS = 60`
- [ ] `explosion_definitions() -> dict` が、上記をレポートに出す形で返す
- [ ] learning（`EXPLOSION_MAX_RETURN_PCT` は `HORIZON_MAX_RETURN_PCT` の別名として残し、既存の import を壊さない）、backtest（`explosive_50pct` と `summarize_trades` の50.0）、recall（引数の既定値）を、この定数に置き換える
**検証**: 既存の learning・forward・recall・backtest のテストが変更なしで PASS する。`grep -nE "\b(15|25|40|60|50)\.0\b"` で、3つのモジュールに爆発の閾値が直書きで残っていないことを確かめる

#### Step 2: REQ-044 — ボラティリティ正規化の爆発（診断用）
- [ ] `explosion.py` に `realized_volatility(closes, signal_date, lookback=60) -> float | None` を置く。シグナル日**以前**の終値だけから、日次の対数リターンの標準偏差を計算する。終値が `lookback + 1` 本に満たなければ `None` を返す
- [ ] `is_vol_explosion(max_return_pct: float | None, sigma: float | None, horizon, k) -> bool | None` を置く。条件は `log(1 + max_return_pct/100) ≥ k × σ × √horizon`（リターンを対数に揃えて比較する）。**`max_return_pct` と `sigma` のどちらかが `None` なら `None` を返す**（変更点 7）
- [ ] learning の `evaluate_learning_observations` で、各 horizon の結果に `vol_explosive` を追加し、観測に `realized_volatility_60d` を追加する。**horizon が未完了（`completed=False`）なら、関数を呼ばずに `vol_explosive=None` とする。** 昇格判定と既存の `explosive` は変えない
- [ ] learning と forward のレポートに `explosion_definitions` を追加する。learning の公開サマリーにも含める
**検証**: 受入条件 REQ-044 の 3〜5

#### Step 3: REQ-043 — Fisher 検定、BH 補正、Wilson 信頼区間
- [ ] `inflection_learning.py` に、標準ライブラリだけで次の3つを実装する
  - `fisher_exact_two_sided(a, b, c, d) -> float`: 超幾何分布（`math.comb`）。観測した表以下の確率を持つ表の確率の合計を p 値とする。浮動小数の比較には相対誤差 1e-7 の許容を入れる（scipy と同じ扱い）
  - `benjamini_hochberg(p_values) -> list[float]`: 昇順に並べて `p × m / 順位` を計算し、後ろから累積最小を取り、1 で上限を切る。入力と同じ順序で返す
  - `wilson_interval(successes, n, z=1.96) -> tuple[float, float] | None`: n = 0 なら `None`
- [ ] `_factor_statistics` で、各 factor について「その factor を持つ観測」と「同じ horizon の独立観測のうち、その factor を持たない観測」の爆発の有無で2×2表を作り、`fisher_p_value` と `explosion_rate_ci95`（Wilson）を加える
- [ ] `build_learning_report` で、**昇格対象（`promotion_strategy_version` の行）の全 factor × 全 horizon** の p 値に BH 補正をかけ、各 factor の統計に `bh_q_value` を書き戻す。BH の family は、2×2表が作れたすべての検定とし、件数が30未満の factor も含める（少ないほうに寄せず、保守的にする）
- [ ] 昇格の条件に `bh_q_value ≤ PROMOTION_MAX_Q_VALUE`（0.10）を加える。件数、lift、超過リターンの符号の条件は現行どおり
- [ ] 累積統計（全 strategy version の `factor_statistics`）にも、`fisher_p_value` と Wilson 区間を付ける。BH 補正は昇格対象だけにかける（累積統計は昇格に使わないため）
- [ ] `promotion_gate` に、`test: "fisher_exact_two_sided"`、`correction: "benjamini_hochberg"`、`max_q_value`、`tests_in_family` を記録する
**検証**: 受入条件 REQ-043 の 1〜6。Fisher は、教科書の例（Fisher の紅茶の例 3,1,1,3 → 両側 p = 0.4857）と、手で計算した小さい表で値を確かめる。BH は既知の例（p = [0.01, 0.04, 0.03, 0.005] → q = [0.02, 0.04, 0.04, 0.02]）で確かめる

#### Step 4: REQ-042 — 共通のバッチ取得モジュール
- [ ] `src/data/forward_prices.py` に `fetch_price_histories(tickers, start, end, *, cache_path, ...) -> PriceHistories` を置く
  - `yf.download(tickers, start, end, group_by="ticker", auto_adjust=False, actions=True, progress=False, threads=True, timeout=15)` を50銘柄ずつ呼ぶ
  - 銘柄ごとのフレームの切り出しは、既存の `_extract_ticker_frame`（`src/data/yfinance_prices.py`）を再利用する
  - 再試行（最大2回、指数バックオフ）、yfinance のログ・stdout・stderr の抑制、例外メッセージに銘柄名を出さない処理は、learning の現行実装と同じにする
  - 取得失敗が5%を超えたら `RuntimeError` で止める（A3 の規則）
- [ ] `PriceHistories` は、生のフレームを持ち、2つの基準を返す
  - `split_only()`: `auto_adjust=False` の OHLC をそのまま返す（A9 後の挙動）
  - `total_return()`: `yfinance.utils.auto_adjust(frame)` の結果を返す
- [ ] **job 内キャッシュ**: 取得した生フレームと、その取得期間（start, end）を `artifacts/price_cache.pkl` に保存する。次の呼び出しでは、キャッシュの期間が要求期間を含む銘柄はキャッシュを使い、それ以外の銘柄だけを取得する。キャッシュは信頼できるローカルファイルとして pickle を使う（同じ runner の中でしか使わず、git にも artifact にも出さない）
**検証**: 受入条件 REQ-042 の 1〜5（モックの `yf.download` で確認する）

#### Step 5: REQ-042 — forward と learning を新モジュールに切り替える
- [ ] `src/data/forward_prices.py` に `shared_price_window(snapshot_dirs: list[Path], today) -> tuple[date, date] | None` を置く（変更点 3）。渡されたディレクトリの `YYYY-MM-DD.enc` のファイル名から最も早い日付を取り、「その日 − 100日」〜「今日 + 1日」を返す。存在しないディレクトリは無視し、どのディレクトリにも snapshot がなければ `None` を返す（呼び出し側は、従来どおり「snapshot がない」として終了する）
- [ ] forward の CLI に `--legacy-snapshot-dir`（既定 `dashboard/data/inflection`）を追加する。**取得期間の計算にだけ使い**、評価の対象は従来どおり `--snapshot-dir`（v3）だけにする。learning の CLI は、既存の `--snapshot-dir` と `--legacy-snapshot-dir` をそのまま使う
- [ ] forward: 観測（`all_observations`、v3 のみ）の全銘柄とベンチマークを、**1回の** `fetch_price_histories` で、`shared_price_window([解決済みの --snapshot-dir, 解決済みの --legacy-snapshot-dir])` の期間で取得する。`histories = total_return()`、`split_histories = split_only()`、`benchmark_history = total_return()[BENCHMARK_TICKER]` とする。ベンチマークの取得に失敗したら停止する
- [ ] learning: 同じ関数を、learning の観測（legacy を含む）の銘柄で、`shared_price_window([解決済みの --snapshot-dir, 解決済みの --legacy-snapshot-dir])` の期間で呼ぶ（既定の実行では forward と同じ期間になる）。期間が同じなので、forward で取得済みの銘柄はキャッシュの条件を満たし、再取得しない。legacy にしかない銘柄だけを取得する。`histories = total_return()` とする
- [ ] 旧関数 `_fetch_adjusted_histories` と `_fetch_learning_histories` は削除する。既存テストでそれらを使っていたテストを、新モジュールのテストに移す（変更点 5）
- [ ] 価格ハッシュの計算（`_price_hashes`）は、従来と同じく2つの基準とベンチマークについて行う。ただし、各銘柄のフレームを**従来の取得開始日以降に切り出してから**ハッシュを計算する（変更点 6）。開始日は、その銘柄の最も早いシグナル日 − 10日（ベンチマークは、全観測の最も早いシグナル日 − 10 − 35日）で、旧 `_fetch_adjusted_histories` の `start` の計算と同じ式にする。切り出しの関数 `legacy_hash_window(frame, start)` を置き、評価に使うフレームは切り出さない
**検証**: 既存の forward と learning の main のテスト（取得をモックしているもの）が、モックの対象を新モジュールに替えるだけで PASS する

#### Step 6: テスト・CI
- [ ] `tests/test_forward_prices.py`:
  - バッチ化: 100銘柄で `yf.download` が2回だけ呼ばれる
  - 2つの基準の値: split only は生の OHLC と一致し、total return は `history(auto_adjust=True)` 相当（`Adj Close / Close` の比を掛けた値）と一致する
  - 価格ハッシュ: 新旧の経路（旧: `history()` の生値と auto_adjust 済みの値を返すモック。新: 同じ生データを `download()` が返すモック）で `_history_row_hashes` が一致する
  - **取得範囲の違いによる偽の改訂がないこと**（review #2）: 旧の取得範囲（シグナル − 10日、ベンチマークは − 45日）で作ったハッシュを「保存済み」とし、新の取得範囲（− 100日）のフレームから `legacy_hash_window` で切り出して作ったハッシュと `_changed_price_rows` で比べ、改訂が0件になる。比較のため、切り出さずに新範囲のフレームからハッシュを作ると、旧の先頭日に改訂が出ることも確かめる（このテストが偽の改訂を検出できることの確認）
  - キャッシュ: 2回目の呼び出しで取得済みの銘柄を再取得しない。キャッシュの期間が要求より短い銘柄は再取得する
  - **forward → learning の共有**（review #1）: legacy（2026-09-09）と v3（2026-09-14）に共通の銘柄がある fixture で、`shared_price_window` が legacy の日付 − 100日から始まる。forward の次に learning を実行したとき、learning は共通銘柄を再取得せず、legacy にしかない銘柄だけを取得する。どちらのフレームにも、最も早い観測の前に61本以上の終値がある
  - **CLI で指定したディレクトリが期間に反映される**（再レビュー #1）: 既定のディレクトリを空にし、別のディレクトリにだけ既定より古い snapshot を置いて、`--snapshot-dir` と `--legacy-snapshot-dir` で指定する。forward と learning のどちらも、その最も古い日付 − 100日から取得することを確かめる（取得のモックに渡された start で検証する）
  - **同じ入力構成なら期間が一致する**: forward と learning に同じ2つのディレクトリを渡したとき、`shared_price_window` の戻り値が一致し、2回目（learning）は共通銘柄をキャッシュから使う。ディレクトリ構成が異なり、learning の要求期間がキャッシュの期間を超える場合は、その銘柄を取得し直す（キャッシュの期間の条件が守られる）
  - `shared_price_window`: 存在しないディレクトリを無視する、snapshot がなければ `None`、`.enc` 以外のファイルや日付でないファイル名は無視する
  - 5%の許容、ベンチマーク欠損での停止、再試行、銘柄名の秘匿、ログの抑制
- [ ] `tests/test_explosion.py`: 定数の値が以前と同じ、ボラティリティの先読み防止、履歴不足で `None`、穏やかな銘柄と荒い銘柄の判定の違い、`max_return_pct=None` または `sigma=None` で `None`（例外にならない）
- [ ] `tests/test_inflection_learning.py`（review #3）: シグナル日の前に61本以上の終値があり、h60・h120 がまだ未完了の観測で、learning レポートが最後まで生成され、未完了の horizon の `vol_explosive` が `None`、完了した horizon（h5 など）では bool になる
- [ ] `tests/test_inflection_learning.py`: Fisher の既知の値、BH の既知の値（単調性の補正を含む）、Wilson の区間、極端な表（爆発 0 件・全件爆発）で p = 1.0、160通りの中で1つだけ p ≈ 0.04 になる合成データでは補正後に昇格しない、件数の多い明確な factor は昇格する、`promotion_gate` と公開サマリーに新しい項目がある
- [ ] `test.yml` の mypy 対象に、`src/data/forward_prices.py` と `src/evaluation/explosion.py` を追加する
**検証**: `pytest tests/`、ruff、mypy がすべて PASS する

#### Step 7: 実データでの確認（ユーザーの確認後）
- [ ] 外部の API（yfinance）を呼ぶので、ユーザーに確認してから実行する。少数の銘柄（ベンチマークと、分割・配当のあった銘柄を含む5銘柄程度）について、旧経路（`history()`）と新経路（`download()` → 導出）の値を比べ、2つの基準とも一致することを確かめる。結果は memo に残す
**検証**: 新旧の値が一致する。一致しない場合は、差の原因（`download` の `ignore_tz` による index の違いなど）を調べ、ハッシュの日付キーに影響しないことを確かめる

### 例外・エラーハンドリング方針
- 取得: 5%以下の失敗は記録して続行し、超えたら停止する。ベンチマークの欠損は停止する。例外とログに銘柄名を出さない（現行の秘匿の方針を維持する）
- キャッシュ: 読み込みに失敗した場合（壊れたファイル、形式の違い）は、キャッシュを使わずに全銘柄を取得し直す（キャッシュは最適化であり、正しさには関わらない）
- 統計: 2×2表が作れない場合（factor を持つ観測、または持たない観測が0件）は p 値を `None` にし、BH の family から外して、昇格させない

### テスト/検証方針
- 自動テスト: `.venv/bin/python -m pytest tests/ -q`、`.venv/bin/ruff check src scripts tests`、`.venv/bin/mypy --ignore-missing-imports <test.yml の対象>`
- 手動確認観点:
  - [ ] Step 7 の新旧の値の比較
  - [ ] マージ後の最初の週次 forward validation（日曜 09:30 JST）が成功し、実行時間が短くなっている
  - [ ] その実行で、価格ハッシュの「改訂」が大量に記録されていない（`price_basis` ごとの `changed_count` のログを確認する）

### リスクと対策
1. リスク: `download()` と `history()` で値や index が微妙に異なり、価格ハッシュに大量の「改訂」が記録される → 対策: Step 7 で実データを比べてから CI に反映する。ハッシュは日付キーで比較し、比のスケール不変のハッシュなので、index のタイムゾーンの違いには影響されない
2. リスク: 昇格の条件が厳しくなり、昇格候補がほとんど出なくなる → 対策: これは意図した挙動である（偶然の昇格を防ぐ）。q 値は公開サマリーに出すので、「惜しい factor」も見える
3. リスク: 別のセッションの変更と、こちらの変更が衝突する（A9 は `d610dfa` でコミット済み） → 対策: Step 0 で、作業ツリーに他のセッションの未コミットの変更がないことを確かめてから着手する
4. リスク: pickle のキャッシュが、別のバージョンの pandas で読めない → 対策: 同じ runner の同じ job の中でしか使わない。読めなければ取り直す

### 完了条件
- [ ] REQ-042 の受入条件 1〜6、REQ-043 の 1〜6、REQ-044 の 1〜5 を満たすテストが PASS する（変更点 1〜5 を反映した内容で）
- [ ] 戦略、snapshot、本番のスコアの挙動が変わっていない（live と shadow health のテストが無変更で PASS する）
- [ ] `pytest`、`ruff`、`mypy` がすべて PASS する
- [ ] Step 7 は、ユーザーの確認後に実行する
