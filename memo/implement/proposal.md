# 実装要件書（REQ-039〜041: J-Quants 過去データによる point-in-time 過去検証）

> このファイルは create-plan の入力です。
> 出典: [memo/analysis/improvement_report_2026-10-01.md](../analysis/improvement_report_2026-10-01.md) の B1（propose-one で選択）。
> 以前の要件書: REQ-001〜036 → [proposal_req001-036.md](proposal_req001-036.md)、REQ-037〜038（schema 5、実装済み）→ [proposal_req037-038.md](proposal_req037-038.md)

## 背景

v3 戦略の有効性は forward shadow（日次 scan の記録）でしか測っておらず、有効なデータは 2026-09-14 以降の約10営業日分しかない。60営業日の成果が揃うのは早くても12月である。

J-Quants Free は、約2年前から12週前までの上場銘柄一覧・日足（上場廃止銘柄を含む）・財務サマリー（開示日時付き）を提供している。これを使えば、**現行 v3 のロジックを過去の各営業日に「その日に分かっていた情報だけで」適用**し、forward と同じ評価器で成績を出せる。

さらに、財務の取得可能時点を「開示当日」と「開示から12週後（現行 Free の状態）」の2通りで比較すれば、有料プラン（Light、月1,650円）に切り替える価値を数値で判断できる（レポート §8.4）。撤退条件（レポート §7.5）の一次判定にも使える。

## 共通の設計判断

- **評価専用。パラメータ探索はしない。** v3 の定数（`EARLY_CANDIDATE_SCORE`、`WATCH_SCORE`、`deep_candidates=25`、`min_turnover_jpy`、スコア配点）は現行コードの値をそのまま使い、本要件の中で変更・探索しない。過去データで閾値を合わせ始めると過剰最適化になり、forward の out-of-sample 性も失われるため。
- **戦略ロジックは現行コードを再利用する。** `src/screening/inflection_live.py` の `_technical_features`、`_pre_score`、`_classify`、`_evaluate_candidate`（REQ-037 で関数化済み）、`src/strategy/inflection.py` をそのまま呼ぶ。過去検証用にロジックを複製しない（複製すると live と乖離するため）。
- **評価器も現行コードを再利用する。** `simulate_signal`、`summarize_trades`、`paired_benchmark_returns`、`summarize_benchmark_excess`、`simulate_portfolio`、`compute_tracked_pool_explosion_recall` を使う。
- **ローカル実行のみ。CI では実行しない。** 呼び出しは約1,000〜1,500回で、Free の 5件/分の制限下では数時間かかるため。
- **J-Quants の取得データは公開リポジトリに保存しない。** このリポジトリは公開設定である。生データのキャッシュは gitignore 済みの `.data/jquants/`、結果は gitignore 済みの `artifacts/` に置く。銘柄名や trade 単位の行を含まない集計サマリーは、`memo/analysis/` に書き写してよい（2026-10-01 ユーザー判断）。

### 検証期間（Free プラン、2026-10-01 時点の試算）

| 項目 | 期間 | 根拠 |
|---|---|---|
| 取得できるデータ | 2024-10-01 頃 〜 2026-07-09 頃（約432営業日） | 「2年前から12週前まで」。実際の境界日は REQ-039 の取得時に API の応答で確定し、レポートに記録する |
| シグナル生成日（252日の履歴が揃う日以降） | 2025-10-14 〜 | `_technical_features` の `near_52w_high` は252営業日の履歴を要する。live と同じ条件にするため、履歴が揃う日から開始する |
| 60営業日の評価が完了するシグナル | 〜 2026-04-10（約120営業日） | データの最終日から60営業日を引いた日まで |
| 120営業日の評価が完了するシグナル | 〜 2026-01-13（約60営業日） | 同上 |

約120営業日 × 25銘柄 ≒ 3,000件の deep candidate と、同数の対照群（REQ-038 と同じ抽出）が得られる。forward の約10営業日分と比べて桁違いのサンプルになる。Light プランなら過去5年分に延びる。

---

## 要件一覧

### REQ-039: J-Quants 過去データの一括取得と、再開可能なローカルキャッシュ

- **画面**: なし（ローカル実行するデータ取得処理）
- **対象ファイル**:
  - 新規: `src/data/jquants_history.py`
  - 変更: [src/data/jquants_v2_client.py](../../src/data/jquants_v2_client.py)（日付指定の取得メソッドを追加）
  - 新規テスト: `tests/test_jquants_history.py`
- **Before（現状）**:
  - `JQuantsV2Client` は `listed_issues(date)` と `financial_summary(code)` の2つしか持たない。日足と、日付指定の財務取得がない。
  - 過去データを保存する仕組みがない。
- **After（期待）**:
  - `JQuantsV2Client` に `daily_bars(date)`（`GET /v2/equities/bars/daily?date=`）と `financial_summary_by_date(date)`（`GET /v2/fins/summary?date=`）を追加する。ページングは既存の `_get` の `pagination_key` 処理をそのまま使う。
  - `src/data/jquants_history.py` に、期間を指定して次の3種類を取得し、**1日1ファイル**でキャッシュする関数を置く。
    - 日足: TSE の全営業日（`exchange_calendars` の XTKS）について `daily_bars(date)`
    - 財務: 期間内の**全暦日**について `financial_summary_by_date(date)`（休日の開示も取りこぼさないため）
    - 上場銘柄一覧: 期間内の**各月の第1営業日**に `listed_issues(date)`（市場区分・業種の時点情報）
  - キャッシュの保存先は `.data/jquants/{bars,fins,master}/YYYY-MM-DD.json.gz`。既にファイルがある日は API を呼ばない（**中断後に再実行すると続きから再開できる**）。
  - 空の応答（休日の財務など）も、空のファイルとして保存し、再取得しない。
  - Free の範囲外の日付で API がエラー（範囲外を示す 4xx）を返した場合は、その日を「範囲外」として記録して処理を続け、最終的に実際に取得できた期間の先頭日と最終日を出力する。
  - 呼び出しの間隔は既存の `min_interval=12.2` 秒（5件/分）を守る。
- **受入条件**:
  1. fake HTTP（`requests.get` の差し替え）で、ページングのある日足が全ページ結合されて保存される。
  2. キャッシュ済みの日は API が呼ばれない（呼び出し回数で検証する）。
  3. 途中で例外が出ても、それまでに保存したファイルは残り、再実行で残りの日だけが取得される。
  4. 範囲外の応答は記録され、処理は止まらない。
  5. キャッシュの保存先が gitignore されている（`git check-ignore .data/jquants/x` が成功する）。
- **備考**: 実際の取得（数時間）はユーザーがローカルで実行する。テストは外部 API に接続しない。

### REQ-040: 過去の各営業日について v3 の scan を point-in-time で再現する

- **画面**: なし
- **対象ファイル**:
  - 新規: `src/evaluation/inflection_historical.py`
  - 変更（必要な場合のみ・挙動は変えない）: [src/screening/inflection_live.py](../../src/screening/inflection_live.py)（再利用のための関数の公開）
  - 新規テスト: `tests/test_inflection_historical.py`
- **Before（現状）**: `scan_japan_inflection()` は yfinance と J-Quants の「今日の」データを直接取得する。過去の日付を指定して実行する手段がない。
- **After（期待）**: `reconstruct_scan(as_of, cache, *, fundamental_lag) -> dict` を作る。指定日 `as_of` について、次の手順で live の scan と同じ形の report（schema 5 の candidate 形式、`control_sample` を含む）を返す。
  1. **ユニバース**: `as_of` 以前で最も近い月の master のうち、市場区分が Prime / Standard / Growth の銘柄で、かつ `as_of` に日足がある銘柄（上場廃止銘柄も、上場していた期間は含まれる。生存者バイアスを避ける）。
  2. **価格**: 各銘柄の `as_of` までの日足（最大252営業日）から、live と同じ列の DataFrame を作り、`_technical_features` に渡す。
     - `Close` = `AdjC`（分割調整済み。live の yfinance `Adj Close` に相当。ただし配当調整は含まない差異がある → 備考）
     - `Volume` = `Vo`（調整前。live と同じく生の出来高）
     - `Turnover` = `Va`（実際の売買代金）
  3. **一次選別と流動性**: live と同じ `min_turnover_jpy`、`_pre_score`、`deep_candidates=25`。
  4. **財務**: `financial_summary` を持つ**キャッシュ由来の client** を渡して `_evaluate_candidate` を呼ぶ。この client は、その銘柄の財務行のうち、**取得可能時点が `as_of` の scan 時刻（16:40 JST）以前の行だけ**を返す。
     - `fundamental_lag="disclosure"`: 取得可能時点 = `DiscDate` + `DiscTime`（`DiscTime` が空なら当日 23:59 とみなし、当日の scan には含めない）
     - `fundamental_lag="free_12w"`: 取得可能時点 = `DiscDate` + 84日（現行 Free の状態を再現）
  5. **対照群**: live と同じ関数・同じ seed 規則（`as_of` の日付から生成）で抽出する。
  - live 側の関数を呼ぶ際に、ロジックを複製しない。必要なら live 側の関数の引数を増やす（例: 財務の client を差し替え可能にする）が、live の出力は変えない。
- **受入条件**:
  1. **live との一致テスト**: 同じ価格・同じ財務を与えたとき、`reconstruct_scan` の `candidates` と `control_sample` が、`scan_japan_inflection`（fake の価格と client を使う）の出力と、`generated_at` などのメタデータを除いて一致する。
  2. **先読みがないこと**: `as_of` より後の日足、および取得可能時点が `as_of` 16:40 より後の財務行を、キャッシュに追加しても結果が変わらない。
  3. `fundamental_lag="free_12w"` では、開示から84日未満の財務行が使われない。
  4. 上場廃止銘柄が、上場していた日のユニバースに含まれる。
  5. 252営業日の履歴がない日は、`reconstruct_scan` を呼ぶ側（REQ-041）がシグナル期間から除外する（live の条件と揃えるため）。
- **備考**:
  - 価格の調整基準が live と少し異なる。live は yfinance の `Adj Close`（配当込み）、過去検証は J-Quants の `AdjC`（分割のみ）。20日・60日のモメンタムへの影響は配当利回り程度（年2〜3%の数分の1）と見込むが、結果の注記に明記する。
  - J-Quants の日足には `UL`/`LL`（ストップ高・安フラグ）がある。約定できない日の扱いは本要件では変えない（forward と同じ）。保留中の項目とする。

### REQ-041: 過去検証レポートの生成（2つの財務ラグの比較と撤退条件の一次判定）

- **画面**: なし（`artifacts/` に JSON を出力）
- **対象ファイル**:
  - 新規: `scripts/run_inflection_historical_backtest.py`
  - 新規テスト: `tests/test_inflection_historical.py`（REQ-040 と共有）
- **Before（現状）**: 過去検証の実行手段とレポートがない。
- **After（期待）**: ローカルで次のコマンドを実行すると、キャッシュから過去の scan を再現し、forward と同じ評価器で集計する。
  ```bash
  python scripts/run_inflection_historical_backtest.py --fetch      # REQ-039 の取得（再開可能）
  python scripts/run_inflection_historical_backtest.py             # キャッシュから評価のみ
  ```
  - シグナル期間: 252営業日の履歴が揃う日から、キャッシュの最終日まで。各 horizon の評価は、キャッシュ内で horizon が完了したものだけを `matured` として集計する。
  - 評価の価格: キャッシュの日足（`AdjO/AdjH/AdjL/AdjC`）を `simulate_signal` に渡す。ベンチマークは 1306.T（キャッシュの日足に含まれる）。
  - 2つの財務ラグ（`disclosure` と `free_12w`）それぞれについて、forward と同じ構成のレポートを作る。
    - 分類ごと（EARLY_CANDIDATE / WATCH / NONE / **CONTROL**）× horizon（5 / 20 / 60 / 120）の `summarize_trades` と `summarize_benchmark_excess`
    - EARLY_CANDIDATE の `simulate_portfolio`（forward と同じ設定）
    - `compute_tracked_pool_explosion_recall`
  - **ラグ比較**: 2つのラグについて、EARLY_CANDIDATE の h60 の平均超過リターン、その差、bootstrap 95% CI（signal_date クラスタ）を並べて出す。
  - **撤退条件の一次判定**: EARLY_CANDIDATE の h60 の対 TOPIX 超過リターンの 95% CI（signal_date クラスタ bootstrap）と、独立観測数（`select_non_overlapping_trades` 後）を出力する。CI が 0 をまたぐかどうかを `kill_criterion` として記録する。判定の閾値は §7.5 の例（独立観測 100件以上、h60、95% CI）を**暫定の既定値**とし、引数で変えられるようにする（2026-10-01 ユーザー判断: 根拠のある代替案がないため暫定採用。結果を見て基準を動かさないよう、変更する場合は結果を見る前に決める）。
  - 出力には `kill_criterion` として、判定（`pass` / `fail` / `insufficient_sample`）、使った閾値、独立観測数、CI を記録する。独立観測が閾値未満なら `insufficient_sample` とし、合否を出さない。閾値以上の場合は、CI の下限が 0 より大きければ `pass`、それ以外（0 をまたぐ、または全体が負）は `fail` とする。
  - 出力:
    - `artifacts/inflection_historical_backtest.json`（銘柄単位の trade を含む。ローカルのみ）
    - `artifacts/inflection_historical_backtest_summary.json`（`_summary_only` 相当で trade を除いた集計のみ）
  - レポートに必ず含める注記: 実際に使った期間、価格の調整基準の差、生存者バイアスへの対処、**パラメータ探索をしていないこと**、多重比較の注意。
- **受入条件**:
  1. 小さな合成キャッシュ（数銘柄 × 約300営業日）で、スクリプトが最後まで動き、2つのラグのレポートが出力される。
  2. `disclosure` のほうが財務を早く使えるケースを合成し、2つのラグで分類が変わることを確認する。
  3. summary 出力に、銘柄コードや trade の行が含まれない。
  4. `kill_criterion` が、CI が 0 をまたぐ合成データ（`fail`）、CI 全体が負の合成データ（`fail`）、CI の下限が正の合成データ（`pass`）、独立観測が閾値未満の合成データ（`insufficient_sample`）で、それぞれ正しく判定される。
  5. `pytest tests/`、ruff、mypy（新規ファイルを CI の mypy 対象に追加）が PASS する。

---

## 繰り返し失敗している要件

なし。

---

## 完了済み・保留中

### 完了済み
- REQ-037 / REQ-038（snapshot schema 5）: 実装済み。2026-10-01 時点で未コミット。

### 保留中（今回のスコープ外）
- **閾値・重みの探索**（REQ-017/020）。本要件の結果を見てから、期間を前後に分けて後半を holdout にする設計で、別の要件にする。
- **ストップ高・安で約定できない日の扱い**（`UL`/`LL` フラグの利用）。forward と同時に変える必要があるため別要件。
- **J-Quants Light への切り替え**。本要件のラグ比較の結果を見て、ユーザーが判断する（レポート §8.4）。
- **12週以降の評価価格の補完**（キャッシュの最終日以降を yfinance で補う）。価格ソースが混ざるため、今回は J-Quants の範囲内で完結させる。
- **TOB による上場廃止の成績の扱い**（最終取引日の終値で exit したとみなす）。キャッシュの日足で最終取引日が分かるので実装は容易だが、forward（A3）と方針を揃えるため別要件にする。
