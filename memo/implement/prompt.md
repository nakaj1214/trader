# 保守フェーズ最終監査後の未解決問題一覧（2026-10-13）

> 出典:
> - Codex 最終監査 [.harness/reports/reliability-final-audit-2026-10-13.md](../../.harness/reports/reliability-final-audit-2026-10-13.md)（判定 BLOCKED。PARTIALLY FIXED 6件）
> - Claude 追加調査（2026-10-13。Codex が挙げていない問題）
>
> 対象コード: commit `3e9b930`（dev6）。各項目は `verify-before-fix` で 1 件ずつ扱う前提。
> 本ファイルは「現象と仮説の材料」であり、原因・修正方針の確定ではない。修正前に必ず証拠を取り直すこと。

---

## 使い方

1. 下の「推奨順」から 1 件選び、`verify-before-fix` に ID を指定して渡す（例: 「ISSUE-01 を verify-before-fix で」）。
2. スキルの Phase 1 は各項目の「現象」、Phase 2 は「仮説と検証方法」を出発点にする。記載の再現は過去の結果なので、Phase 3 で再実行して確認する。
3. 1 件の修正・検証が終わってから次へ進む。複数件を同時に直さない。

## 全項目共通の制約

- 外部 API・実 Slack・実 Sheets・永続キャッシュ・保存済み snapshot・archive に触れない。検証は fake / synthetic と一時ディレクトリで行う。
- スコア・閾値・重み・Q06 閾値（ticker 10 / signal date 5 / 最大業種比率 50%）を変更しない。Growth（G01〜G07）に進まない。
- 修正で正常入力の候補・スコア・評価結果が変わる場合は、変化が修正の意図どおりか説明する（baseline-changing として記録）。
- 既存テストを新実装に合わせて書き換えるだけの修正は禁止。修正前に失敗するテストを先に用意する。

## 一覧

| ID | 出典 | 重大度 | 概要 | 再現状況 | baseline 影響の見込み |
|---|---|---|---|---|---|
| ISSUE-01 | Codex (C04) | 高（BLOCKED 要因） | historical がベンチマークの index を市場カレンダーにし、欠落日を隠す | Codex が synthetic で再現 | changing（historical 評価） |
| ISSUE-02 | Codex (C04) | 高（BLOCKED 要因） | 成熟した未評価取引が kill criterion の判定から落ちる | Codex が synthetic で再現 | changing（kill criterion） |
| ISSUE-03 | Claude | 中 | live scan で優先株が普通株のメタデータを上書き（6 銘柄） | 実 master で確認 | changing（該当 6 銘柄の特徴量） |
| ISSUE-04 | Claude | 中 | Position Monitor が古い保有銘柄を永久に評価できない | fake で再現 | preserving（正常系） |
| ISSUE-05 | Claude | 中〜低 | 翌営業日の始値が欠けるとエントリー日が黙ってずれる | synthetic で再現 | changing（該当取引が未評価に） |
| ISSUE-06 | Codex (Q04) + Claude | 中〜低 | 日次 scan の snapshot と通知状態の境界（通知取りこぼし／snapshot 未 commit） | Codex が fake で再現（前半）。後半はコードと workflow で確認 | preserving |
| ISSUE-07 | Claude | 低〜中 | learning の超過収益だけベンチマークコストが 0.2%（forward・historical は 0.05%） | コードで確認 | changing（learning の超過収益 −0.15pt） |
| ISSUE-08 | Codex (Q01) | 低〜中 | 失敗通知ジョブが依存未導入で `requests` を import する | Codex が no-site 実行で確認 | preserving |
| ISSUE-09 | Codex (Q07) | 低 | Monitor・forward の障害分類が最終結果に残らない／自前バグが validation に分類される | コードで確認 | preserving |
| ISSUE-10 | Claude | 低 | 日次 scan workflow に main ブランチの限定が無い | workflow で確認 | preserving |
| ISSUE-11 | Codex (Q05) | 低 | `test.yml` に `permissions` 指定が無い | workflow で確認 | preserving |
| ISSUE-12 | Codex (Q10) | 低 | 外部通信拒否 fixture が yfinance の curl_cffi 経路を止めない | Codex が確認 | preserving |
| ISSUE-13 | Claude | 低 | 価格キャッシュ `artifacts/price_cache.pkl` が直書き（Q09 の取り残し） | コードで確認 | preserving |
| ISSUE-14 | Claude | 低 | レポート内で「up/down」が 20 日騰落と 200 日移動平均の 2 定義で使われる | コードで確認 | preserving（表示のみ） |

**推奨順:** ISSUE-01 → 02（BLOCKED 解除。修正後に baseline を取り直す）→ 03 → 04 → 05 → 06 → 07 → 08 以降。
05 は 01 と同じ `_evaluation_window` に関わるため、01 の直後に扱うと手戻りが少ない。

**対象外（誤りとして取り下げ）:** 「C04 のカレンダー欠落が forward・learning にもある」という Claude の初回指摘は誤り。両経路は 1306.T を `required` で取得し全 TSE 営業日の網羅を強制する（[forward_prices.py:233-235](../../src/data/forward_prices.py#L233-L235)）ため、本番では欠落が起きない。

---

## ISSUE-01: historical の市場カレンダーがベンチマーク依存（C04）

- **出典 / 重大度:** Codex 最終監査 / 高（最終判定 BLOCKED の要因）
- **現象:** 全銘柄の市場日には存在する日が、対象銘柄とベンチマーク（TOPIX ETF）の両方で欠けていると、未評価になるべき取引が完了扱いになる。
- **再現条件（Codex）:** 8 市場日の synthetic。対象銘柄と TOPIX に 1/22 が無く、別銘柄には有る。
- **期待:** `incomplete_price_path` で未評価。**実際:** 完了・net −0.2%・1/27 退出（horizon が欠落分延びる）。
- **根拠箇所:** `market_calendar=pd.DatetimeIndex(benchmark_history.index)` を渡している [inflection_historical.py:478](../../src/evaluation/inflection_historical.py#L478)、[同:622](../../src/evaluation/inflection_historical.py#L622)、[同:631](../../src/evaluation/inflection_historical.py#L631)、および `_build_group_report` 内 [inflection_report.py:325](../../src/evaluation/inflection_report.py#L325)（historical から呼ばれる場合）。`BarPanel.sessions` は全市場日を持つ。
- **仮説と検証方法:**
  1. historical 経路のカレンダーがベンチマーク依存（High）→ 上の synthetic を `_lag_report` 経由で実行し、`BarPanel.sessions` を渡した場合と結果を比較。
  2. `_build_group_report` は forward と共有のため、カレンダー引数の追加が forward の結果を変える（Med）→ forward の既存テストが無変更で通るか確認。
- **修正方針の候補（未確定）:** historical では `BarPanel.sessions`（または TSE カレンダー）を市場カレンダーとして渡す。forward・learning は現状のままでよい（上記「対象外」参照）。
- **受入条件:** synthetic で `incomplete_price_path` になる。forward の既存テストが無変更で PASS。historical 評価の変化を baseline-changing として記録。

## ISSUE-02: 成熟した未評価取引が kill criterion から落ちる（C04）

- **出典 / 重大度:** Codex 最終監査 / 高（最終判定 BLOCKED の要因）
- **現象:** 集計には未評価 1 件が残るのに、kill criterion の判定は `pass` になる。
- **再現条件（Codex）:** 完了 2 件と、十分古い価格終了 1 件。`min_independent=2` の bounded fixture（本番既定 100 は変えない）。
- **期待:** 成熟した未評価がある間は判定を保留（learning と同じ扱い）。**実際:** `pass`。
- **根拠箇所:** [h60_excess_pairs](../../src/evaluation/inflection_historical.py#L470-L487) → `select_non_overlapping_trades`（`exit_date` の無い取引を除外。[inflection_backtest.py:416-435](../../src/evaluation/inflection_backtest.py#L416-L435)）→ [kill_criterion](../../src/evaluation/inflection_historical.py#L494-L520)。learning は `unresolved_matured` で昇格を保留する（[inflection_learning.py:734-738](../../src/evaluation/inflection_learning.py#L734-L738)）。
- **仮説と検証方法:**
  1. kill criterion に成熟未評価の件数が渡っていない（High）→ 上の fixture で `kill_criterion` の入力件数と verdict を確認。
  2. 成熟判定（`horizon_matured`）と未評価理由の組合せで、保留すべき条件の定義が曖昧（Med）→ learning の `_outcome_coverage` の条件と比較。
- **修正方針の候補（未確定）:** 成熟済みで未評価の取引を数え、1 件以上なら verdict を保留（例: `incomplete`）にする。learning の扱いと揃える。
- **受入条件:** 上の fixture で `pass` にならない。未評価ゼロの既存ケースは不変。

## ISSUE-03: live scan で優先株が普通株のメタデータを上書き

- **出典 / 重大度:** Claude 追加調査 / 中
- **現象:** 普通株の ticker（例 `2593.T` 伊藤園）に、優先株の master 行（コード `25935`、社名「伊藤園（優先株式）」）が紐づく。財務は優先株コードで取得され、全欠損になる。
- **再現条件:** 手元の J-Quants master（`.data/jquants/master/2026-07-01.json.gz`）で、プライム・スタンダード・グロースの 3,723 行中 6 件が衝突。伊藤園・インフロニア・ゼンショー・JAL・ANA・ソフトバンク。上書き後は全件が優先株コードになった。手元の fins キャッシュでは優先株コードの財務行は 0 件、普通株コードは有り。
- **期待:** 普通株（コード末尾 0）のメタデータと財務を使う。**実際:** 後から来た優先株行が上書き。
- **根拠箇所:** [_ticker_from_code](../../src/screening/inflection_live.py#L127-L129)（先頭 4 桁で ticker 化）、[ticker_meta の構築](../../src/screening/inflection_live.py#L781-L787)、[_evaluate_candidate のコード取得](../../src/screening/inflection_live.py#L546-L547)。historical は `_is_ordinary_code` で除外済み（[inflection_historical.py:70-73](../../src/evaluation/inflection_historical.py#L70-L73)、[同:231](../../src/evaluation/inflection_historical.py#L231)）。
- **仮説と検証方法:**
  1. live だけ普通株フィルタが無い（High）→ fake の `listed_issues` に普通株と優先株を並べ、`scan_japan_inflection` の `ticker_meta` と `financial_summary` の呼出しコードを確認。
  2. 衝突は master の並び順に依存（Med）→ 並びを逆にした fake で結果が変わるか確認。
- **修正方針の候補（未確定）:** live でも `_is_ordinary_code` 相当で普通株だけを残す（historical と共通化）。universe 件数は 6 件減る見込み。
- **受入条件:** 衝突ケースで普通株コードの財務が使われる。universe 件数の変化を記録。

## ISSUE-04: Position Monitor が古い保有銘柄を永久に評価できない

- **出典 / 重大度:** Claude 追加調査 / 中（Codex は「過去 1 分足の保持期間」を integration 未確認として扱い、C02 を FIXED とした）
- **現象:** 前回の状態行が無い position（新規追加、または状況シートのリセット後）で、購入翌日〜前日のうち 1 日でも 1 分足が取れないと `incomplete` になり、チェックポイント（`as_of_at`）が空のまま進まない。次回も同じ全区間を再生して失敗し続ける。
- **再現条件（Claude）:** fake。購入日 2026-07-01、評価 2026-10-09、2026-09-10 より前の 1 分足が取得不可。3 回連続で `incomplete`、`as_of_at=''`。provider の 1 分足保持が約 30 日という前提は未確認（integration）。
- **期待:** 取得できない古い区間があっても、何らかの明示的な扱いで評価が先へ進む（または利用者がそれと分かる状態になる）。**実際:** 永久に `incomplete`。毎回「一部銘柄を評価できませんでした」の Slack 警告。全銘柄がこの状態なら毎回 workflow 失敗。
- **根拠箇所:** [_recover_pending](../../scripts/run_position_monitor.py#L136-L184)（[行 167-168](../../scripts/run_position_monitor.py#L167-L168) で例外）、[_preserve_previous_state](../../scripts/run_position_monitor.py#L127-L133)（失敗時に前回 `as_of_at` を引き継ぐだけ）。
- **仮説と検証方法:**
  1. 再生できない日があるとチェックポイントが進まない（High）→ 上の fake を `run()` 全体で実行し、`write_status` に渡る行と Slack 警告を確認。
  2. 実際の 1 分足保持期間（Med、integration）→ fake では確認不能。修正方針は保持期間に依存しない形にする。
- **修正方針の候補（未確定）:** 1 分足の無い古い営業日は日足で保守的に判定する（安値が stop 以下なら接触として扱う等）、または「評価不能区間あり」を明示して以降の評価を進める。C02（stop 回収）・C03（incomplete）の保証を壊さないこと。
- **受入条件:** 上の fake で、2 回目以降に評価が先へ進む、または明示的な状態になり警告が繰り返されない。既存の C02/C03 回帰テストが無変更で PASS。

## ISSUE-05: 翌営業日の始値が欠けるとエントリー日が黙ってずれる

- **出典 / 重大度:** Claude 追加調査 / 中〜低
- **現象:** シグナル翌営業日の始値が無いと、その次の始値がある日にエントリーし、欠損として記録されない。
- **再現条件（Claude）:** synthetic。市場カレンダーは 2026-01-05 から 12 営業日、銘柄は 2026-01-06 だけ欠落。`simulate_signal(holding_days=5)` で entry 2026-01-07、net +18.8%、`missing_sessions=[]`、`unevaluated_reason=None`。
- **期待:** 「翌営業日始値で entry」から外れた取引は未評価、または欠損として記録。**実際:** 黙って 1 営業日後にエントリーして完了扱い。
- **根拠箇所:** [_evaluation_window](../../src/evaluation/inflection_backtest.py#L133-L136)（`after_open` の最初の日をエントリーにし、`required` をエントリー日から数える）。forward・learning・historical・exit rule のすべてが通る共通関数。
- **仮説と検証方法:**
  1. エントリー日を市場カレンダー上の翌営業日と照合していない（High）→ 上の synthetic を再実行。
  2. 実データで頻度が低い（Med）→ historical キャッシュで「翌営業日に始値が無い EARLY_CANDIDATE」の件数を数える（読み取りのみ）。
- **修正方針の候補（未確定）:** エントリー日が市場カレンダー上の翌営業日でない場合、`missing_sessions` に含めるか専用の未評価理由（例 `entry_session_missing`）にする。売買停止の扱い（`price_status` メタデータ）とも整合させる。ISSUE-01 と同じ関数のため続けて扱う。
- **受入条件:** synthetic が未評価（または欠損記録あり）になる。欠損の無い既存ケースは不変。

## ISSUE-06: 日次 scan の snapshot と通知状態の境界（Q04 の残り + 追加）

- **出典 / 重大度:** Codex（Q04）+ Claude 追加調査 / 中〜低
- **現象 A（Codex）:** snapshot 保存後、`pending` 状態を作る前に latest 保存の失敗やプロセス停止が起きると、次の通常実行は新 snapshot を「旧 snapshot（状態なし）」として扱い、通知を `skipped:legacy-no-state` にする。明示再送でしか回復できない。
- **現象 B（Claude）:** `_deliver_digest` は try の外で呼ばれ、通知状態ファイルの読み書き（JSON 不正、値不正、OSError）で例外が出ると scan ステップ全体が失敗する。Commit ステップに `if: always()` が無いため、作成済み snapshot が commit されない。状態ファイルが壊れたまま残ると毎日同じ失敗になり、snapshot が蓄積されない。「ダイジェストの失敗で scan を失敗させない」という docstring の契約に反する。
- **再現条件:** A は Codex が実関数の fake で再現（snapshot 有り・state 無し・再試行 send 0 件）。B はコードと workflow で確認（未実行）。
- **根拠箇所:** [persist_report](../../scripts/run_inflection_shadow.py#L191-L220)（snapshot → latest の順）、[_deliver_digest](../../scripts/run_inflection_shadow.py#L238-L259)、[main の呼出し](../../scripts/run_inflection_shadow.py#L278-L287)、[inflection_shadow.yml の Commit ステップ](../../.github/workflows/inflection_shadow.yml#L77-L86)。
- **仮説と検証方法:**
  1. A: `pending` の作成が snapshot 作成より後（High）→ `persist_report` の latest 書込みを失敗させる fake で、次回 `_deliver_digest` の結果を確認。
  2. B: 状態ファイル不正で `main` が例外終了する（High）→ 不正な `digest_state.json` を置いた一時ディレクトリで `_deliver_digest` を呼び、例外の伝播を確認。
  3. B: snapshot が commit されないのは workflow 側の条件（High）→ Commit ステップの `if` を静的確認。
- **修正方針の候補（未確定）:** A は snapshot 作成と同時（前）に `pending` を確定する順序の見直し。B は通知状態の例外を scan の成否から切り離す（ステータスとして記録）、または Commit ステップを scan 失敗時も snapshot があれば実行する。exactly-once は保証しない前提を維持。
- **受入条件:** A の fake で次回の通常実行が通知する。B の不正状態でも snapshot が保存・commit 対象になり、状態の異常はステータスで分かる。

## ISSUE-07: learning の超過収益だけベンチマークコストが異なる

- **出典 / 重大度:** Claude 追加調査 / 低〜中
- **現象:** learning は `paired_benchmark_returns(..., round_trip_cost_pct=0.2)` でベンチマーク側にも 0.2% を課す。forward と historical は 0.05%（`BENCHMARK_ROUND_TRIP_COST_PCT`）で、文書（project-overview）にも 0.05% と記載。
- **影響:** 同じ取引でも learning の超過収益が 0.15pt 高い。B06 の外れ率（超過収益 ≤ 0 を外れとする）と、昇格判定の「平均超過収益の符号」が楽観側にずれる。
- **根拠箇所:** [inflection_learning.py:40](../../src/evaluation/inflection_learning.py#L40)、[同:340-344](../../src/evaluation/inflection_learning.py#L340-L344)、[inflection_report.py:45](../../src/evaluation/inflection_report.py#L45)、[inflection_historical.py:482](../../src/evaluation/inflection_historical.py#L482)。
- **仮説と検証方法:**
  1. 意図しない不一致（Med）→ git 履歴・過去の要件書（REQ の learning 移植時）で、ベンチマークコストを意図して分けた記録があるか確認。
  2. 意図した差（Low）→ 記録があれば文書に明記するだけで済む。
- **修正方針の候補（未確定）:** 意図しない差なら learning も `BENCHMARK_ROUND_TRIP_COST_PCT` を使う。意図した差なら文書化。
- **受入条件:** 同一取引で learning と forward の超過収益の定義が一致する（または差が文書化されている）。learning 指標の変化を記録。

## ISSUE-08: 失敗通知ジョブの依存前提（Q01）

- **出典 / 重大度:** Codex 最終監査（Q01）/ 低〜中
- **現象:** `check_workflow_health.py` は `provider_output.py` 経由で `requests` に依存するが、4 つの `notify-failure` ジョブは依存を導入しない。no-site の Python では起動前に `ModuleNotFoundError: requests` で exit 1。hosted runner に偶然入っている package に依存している。
- **根拠箇所:** [check_workflow_health.py:19-20](../../scripts/check_workflow_health.py#L19-L20)、[provider_output.py:13](../../src/data/provider_output.py#L13)、各 workflow の `notify-failure` ジョブ。
- **仮説と検証方法:** `python -B -S scripts/check_workflow_health.py --help` の終了コードを確認（Codex は exit 1）。
- **修正方針の候補（未確定）:** 失敗通知の経路を標準ライブラリだけで動かす（`suppress_provider_output` の依存を切り離す）、またはジョブで依存を導入する。障害時に動く経路なので依存は少ない方がよい。
- **受入条件:** no-site 実行で起動できる。実 Actions 上の確認は integration 未確認として残す。

## ISSUE-09: 障害分類の消失（Q07）

- **出典 / 重大度:** Codex 最終監査（Q07）+ Claude 補足 / 低
- **現象:**
  - Monitor の `fetch_today_bars` / `fetch_session_bars` は既知の失敗（timeout・429・認証）を `None` にし、呼出し側が diagnostics を渡さないため区別できない（stale / incomplete に畳まれる）。
  - forward の必須価格・coverage の終端は、蓄積した原因を返す前に汎用の `RuntimeError` になる。
  - （Claude 補足）`classify_provider_failure` は `KeyError` / `ValueError` を一律 validation に分類するため、自前コードのバグも「データの問題」として握られ得る。
- **根拠箇所:** [live_quote.py:209-264](../../src/data/live_quote.py#L209-L264)、[run_position_monitor.py:367-374](../../scripts/run_position_monitor.py#L367-L374)、[forward_prices.py:233-237](../../src/data/forward_prices.py#L233-L237)、[provider_output.py:30-48](../../src/data/provider_output.py#L30-L48)。
- **仮説と検証方法:** fake provider で timeout / 429 / 認証失敗を起こし、Monitor の最終行・公開ログに分類が残るか確認。
- **修正方針の候補（未確定）:** Monitor の呼出しで diagnostics を渡し、行の `error` に安全な分類だけを残す。forward の終端例外に分類件数を含める。公開ログの保護（Q02）を維持。
- **受入条件:** 分類が最終結果または公開ログで区別できる。ticker・URL・本文は出ない。

## ISSUE-10: 日次 scan workflow に main ブランチの限定が無い

- **出典 / 重大度:** Claude 追加調査 / 低
- **現象:** Monitor・Watchdog は `if: github.ref == 'refs/heads/main'` で限定しているが、日次 scan の `scan` ジョブには無い。別ブランチから手動実行すると、本番 secret で scan を回して Slack に通知し、そのブランチへ snapshot を push する。通知状態はブランチごとなので同日の通知が重複する。同じ日付の snapshot を後で main に取り込むと衝突する。
- **根拠箇所:** [inflection_shadow.yml:14-28](../../.github/workflows/inflection_shadow.yml#L14-L28)。
- **仮説と検証方法:** workflow の静的確認（既存の `tests/test_workflow_reliability.py` の仕組みで照合可能）。
- **修正方針の候補（未確定）:** `scan` ジョブを main に限定する。ブランチでの動作確認が必要なら dry-run 相当の別経路を用意する。
- **受入条件:** 静的テストで main 以外では scan ジョブが実行されない。

## ISSUE-11: `test.yml` の token 権限が暗黙（Q05）

- **出典 / 重大度:** Codex 最終監査（Q05）/ 低
- **現象:** `test.yml` に workflow / job の `permissions` 指定が無く、実効権限がリポジトリ既定値に依存する。既存の静的テストは明示的な write 付与しか検出できない。
- **根拠箇所:** [.github/workflows/test.yml](../../.github/workflows/test.yml)、`tests/test_workflow_reliability.py`。
- **修正方針の候補（未確定）:** `permissions: contents: read` を明示し、静的テストで「全 workflow に明示的な permissions がある」ことを確認する。
- **受入条件:** 静的テストが PASS。

## ISSUE-12: 外部通信拒否 fixture の範囲（Q10）

- **出典 / 重大度:** Codex 最終監査（Q10）/ 低
- **現象:** `tests/conftest.py` は Python の socket（connect / getaddrinfo）だけを止める。yfinance が使う curl_cffi のネイティブ通信（`Curl.perform`）は止まらない。今回、実通信は観測されていない。
- **根拠箇所:** [tests/conftest.py](../../tests/conftest.py)。
- **修正方針の候補（未確定）:** curl_cffi の送信関数（または yfinance のセッション生成）もテスト時に拒否する。拒否試行の計数は既存の仕組みに合わせる。
- **受入条件:** curl_cffi 経由の送信試行がテストで拒否・計数される。全テストが PASS。

## ISSUE-13: 価格キャッシュの直書き（Q09 の取り残し）

- **出典 / 重大度:** Claude 追加調査 / 低
- **現象:** `artifacts/price_cache.pkl` を `path.write_bytes(pickle.dumps(...))` で直接書く。中断すると壊れたファイルが残る。読込側は例外時に全件取得へ戻るので安全側だが、Q09（atomic write）を FIXED とした記述とは食い違う。
- **根拠箇所:** [forward_prices.py:138-142](../../src/data/forward_prices.py#L138-L142)。
- **修正方針の候補（未確定）:** 既存の `atomic_write` を使う（バイナリ対応が必要なら最小限の拡張）。
- **受入条件:** 書込み途中の失敗で旧ファイルが残る。

## ISSUE-14: レポート内の「up/down」の二重定義

- **出典 / 重大度:** Claude 追加調査 / 低
- **現象:** 同じ group report 内で、`regime_sample_counts` は 20 日騰落で up/down を判定し（[inflection_report.py:72-79](../../src/evaluation/inflection_report.py#L72-L79)）、`regime_breakdown.trend` は 200 日移動平均で判定する（[regime.py](../../src/evaluation/regime.py)）。同じラベルで意味が違う。
- **修正方針の候補（未確定）:** 値は変えず、キー名または説明文で定義の違いを明示する（例 `regime_sample_counts` に定義を併記）。
- **受入条件:** レポート上で定義の違いが分かる。数値は不変。

---

## 確認して問題が無かった主な領域（参考）

historical の as_of 時点の split 補正と財務の締切（look-ahead なし）、exit rule とポートフォリオの約定順序、atomic write と snapshot 暗号化、forward の snapshot 読込、Watchdog の期待実行判定、Sheets の run 内共有、市場別ベンチマーク名と実データ `MktNm` の一致。
