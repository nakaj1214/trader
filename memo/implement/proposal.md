# 実装要件書（REQ-068〜069: Stage 4C — 重複処理の削減と文書整合）

> このファイルは create-plan の入力です。
> 出典: [memo/local/tmp.md](../local/tmp.md)（Stage 4C 依頼文）、`.harness/reports/repository-audit-2026-10-08.md` の Q08/B09、`.harness/reports/reliability-stage4a-2026-10-09.md`、Stage 4B 報告（`.harness/reports/reliability-stage4b-2026-10-12.md` があれば参照）。
> 以前の要件書: REQ-001〜067 → それぞれ `proposal_req*.md`（直前の Stage 4B は `proposal_req062-067.md`）

## 背景・スコープ

- 対象は **Q08（重複取得・再計算の削減）と B09（運用・実装状態の文書整合）の 2 項目のみ**。Growth Opportunity（G01〜G07）には進まない。完了後は停止して報告する。
- Stage 4A（B05/B06/B10/Q06/Q10 外部通信禁止）と Stage 4B（Q03/Q04/Q05/Q07/Q09）、および第1〜第3段階（C01〜C07・B01〜B04・B07・B08・Q01・Q02）は現在の baseline として維持する。再設計しない。
- 目的は性能と保守性のみ。**同じ正常入力 → 同じ候補・スコア・評価結果・学習結果**。Q06 の閾値（ticker 10 / signal date 5 / 最大業種比率 50%）、スコア、閾値、重みは変更しない。
- 現在の作業ツリーには Stage 4B の変更が含まれる（`git status` で workflow・scripts・src の変更を確認済み）。baseline はこの作業ツリーとする。
- mypy 既知 31件（スタブ未導入）は baseline。件数ではなく内容の差分で新規 0 件を確認する。依存変更は想定せず、`uv.lock` は差分なしを期待する。
- 実装手順（Q08）: 監査の元指摘を再確認 → **最初に計測**（固定サイズの fake / synthetic データ）→ 計測で重複が確認できた箇所だけ最小修正 → 修正前後の結果完全一致を確認 → 対象テスト → Stage 4A/4B 回帰 → 第1〜第3段階回帰 → 全テスト → ruff → mypy → 外部通信・snapshot・archive・`uv.lock` 確認。効果がほとんど無い箇所は「変更不要」と判断してよい。

---

## 要件一覧

### REQ-068: run 内の重複取得・再計算の削減（Q08）

- **画面**: Position Monitor / 評価レポート（forward validation・backtest）
- **対象ファイル**: [scripts/run_position_monitor.py](../../scripts/run_position_monitor.py)（`run` の保有行ループ、`fetch_split_adjusted_history`・`fetch_today_bars` の呼出し）、[src/data/live_quote.py](../../src/data/live_quote.py)、[src/data/sheets_client.py](../../src/data/sheets_client.py)（`_worksheet`、`read_holdings`・`read_status`・`write_status`）、[src/evaluation/inflection_report.py](../../src/evaluation/inflection_report.py)（horizon・cost ごとの `simulate_signals` / `_paired_trade_rows`）、[src/evaluation/inflection_backtest.py](../../src/evaluation/inflection_backtest.py)
- **Before（現状）**:
  - Position Monitor は保有行ごとに `fetch_split_adjusted_history(ticker, …)` と `fetch_today_bars(ticker)` を呼ぶ。同一 ticker に複数の保有行があると、同じ run 内で同じ ticker の当日足を何度も取得し、気配時刻も行ごとに異なり得る。
  - Sheets は `read_status`・`read_holdings`・`write_status` ごとに `_worksheet()` が認証・`open_by_key` をやり直す（1 run で複数回接続）。
  - 評価レポートは 5 つの horizon × 通常/ストレス cost で `simulate_signals`・`_paired_trade_rows` を繰り返し、同じ価格系列の整形・index 調整・日付変換・共通統計を再計算する。
  - 上記の回数・時間・メモリは未計測 [要確認: 計測で重複の実在と規模を確認する]。
- **After（期待）**:
  1. **まず計測する**。固定サイズの fake / synthetic データで、provider call 数、同一 ticker の価格取得回数、Sheets connection / read / write 回数、同じ系列の整形回数、同一統計の再計算回数、実行時間、peak memory を before として記録する。実 API・実環境のベンチマークは行わない。
  2. 計測で重複が確認できた箇所に限り、**1 run 内だけ**の共有を入れる。
     - Position Monitor: 市場データ取得は ticker 単位で共有し、取引判定（購入日・entry price・stop・position 固有状態・取引固有の split 調整）は position 単位で独立のままにする。
     - Sheets: 1 run 内で worksheet / 接続を安全に共有できる範囲だけ削減する。retry 境界・認証エラー・batch 更新・Q04 通知状態・C07 writer 排他を壊さない。長寿命のグローバル接続や connection pool は導入しない。
     - 評価系列・統計: 安全に共有できる immutable な中間結果だけ共有する。可変 DataFrame を共有して後続処理が相互に影響する設計にしない（copy または immutable な表現を使う）。
  3. 最適化前後で正常入力に対する結果が**完全一致**する。浮動小数点の計算順序が変わる最適化はしない。
  4. 効果がほとんど無い、またはリスクが勝つ候補は変更せず、理由を報告する。
- **受入条件**:
  - before / after の provider call 数と Sheets connection 数を具体的な数値で報告できる（実行時間・peak memory は可能な範囲。ローカルの小さな時間差を根拠にしない。主な評価基準は重複処理回数が構造的に減ったか）。
  - 同一 ticker に複数 position があっても当日足の取得が 1 回であることを、fake provider の呼出し回数で確認する。
  - 同一 ticker・異なる購入日の position の結果（stop 判定・entry 調整・通知対象・warned 状態）が最適化前と一致する。
  - ある ticker の provider 失敗が他の ticker の position に誤伝播しない。同一 ticker の複数 position は同じ失敗を一貫して受け、他 position の固有計算を壊さない。
  - 共有された DataFrame 等を一方が変更しても他方に影響しない（cross contamination なし）。
  - Sheets を共有しても、既存の read / write の結果・書込み内容・retry・認証エラーの扱いが変わらない。
  - 最低限、candidate / EARLY_CANDIDATE / classification / score / feature 値 / stop 判定 / notification 対象 / outcome / portfolio / benchmark / learning 入力・出力が before / after で完全一致（既存仕様で順序が保証されているものは順序も一致）。
  - 永続 cache・外部 cache・新しい DB・multiprocessing・大規模 async・provider への並列大量アクセス・memoization framework・新しい依存 package・全面アーキテクチャ変更を導入していない。
- **備考**: Q08 は baseline-preserving でなければならない。正常入力の戦略結果が 1 件でも変わったら原因を調査する（性能改善を理由に結果差を許容しない）。

### REQ-069: 現行仕様を説明する文書の整合（B09）

- **画面**: 現行仕様を説明する文書（[memo/project-overview.md](../project-overview.md)、[docs/playbooks.md](../../docs/playbooks.md)、`.env.example`、必要に応じて AGENTS.md 以外の README 相当）
- **対象ファイル**: 上記の現行仕様文書。照合元は [.github/workflows/*.yml](../../.github/workflows/)、[.env.example](../../.env.example)、[scripts/](../../scripts/)・[src/](../../src/) の現行コード。
- **Before（現状）**: 監査時点で、概要が暗号鍵の API key fallback・最低限 secret は J-Quants のみ・Monitor 9:03 / 12:35 と記す一方、現行コードは専用暗号鍵必須・9:20 / 12:50。EDINET の状態も実装と食い違う。Stage 4A/4B で追加・変更された設定や運用（`JQUANTS_PLAN` / `JQUANTS_DATA_DELAY_WEEKS` の validation、Forward Validation の secret 分離、Q04 の通知状態と再送、uv.lock と Action SHA 固定、Q07 の障害分類、Q09 の atomic write）は未反映の可能性がある [要確認: 現行文書を照合して不一致を確定する]。
- **After（期待）**: 現行コードを正として、現行仕様を説明する文書だけを更新する。最低限、次を現在の実装と照合して反映する。
  - **セットアップ**: 必須環境変数、J-Quants 関連（`JQUANTS_PLAN`・`JQUANTS_DATA_DELAY_WEEKS` と設定 validation の挙動）、snapshot 暗号化 key、Slack、Google Sheets、その他 secret。
  - **GitHub Actions**: workflow 一覧、schedule、`workflow_dispatch`、concurrency、permissions、secret 利用、`uv.lock` 利用、Action SHA 固定。古い時刻・権限・依存導入方法を残さない。
  - **Forward Validation**: secret 不要の PR 検証、secret 必須の評価の分離、fork PR の扱い。
  - **Position Monitor**: 実行時間、stop 回収、checkpoint、incomplete 判定、branch / writer 制限、concurrency、通知状態。
  - **通知**: snapshot 生成・保存・Git 反映・Slack 通知・通知状態・明示再送が別状態であること。**Exactly-once を保証すると書かない**。runner 停止や Slack 受理後・状態保存前の停止で重複し得ることを必要な範囲で明記。
  - **Watchdog**: workflow 失敗・未起動・snapshot 欠落・一般障害通知の現在仕様。
  - **provider 障害**: timeout / 429 / HTTP 5xx / protocol 異常 / empty / validation / authentication / unexpected の分類を、運用者が理解する範囲だけ。実装詳細は過剰に書かない。
  - **atomic write**: snapshot・評価成果物が atomic に書かれること。複数成果物全体が transactional とは書かない。
  - **EDINET**: コード接続済み / test 済み / live 利用 / historical 利用 / learning 利用 / 実 API 確認済みか未確認かを実装に基づいて整理。「実装済み」と「本番で実証済み」を同一視しない。
  - 機能状態は、可能なら implemented / tested with fake・unit test / integration not verified / production enabled / production unverified（自然な日本語で可）を区別する。コードがあることと実サービスで確認済みであることを区別する。
- **変更してはいけないもの**: repository audit、Stage 1〜4 の実装報告、過去の分析メモ・研究メモ、過去の backtest 結果（`memo/analysis/`・`memo/research/`・`.harness/reports/` の過去レポート等）。判断に迷う文書は変更せず報告する。
- **受入条件**: 更新した各文書について「何が古かったか」「現在何に合わせたか」を整理して報告できる。文書記載の時刻・secret 名・環境変数・権限が workflow・`.env.example`・CLI 引数と一致する（自動照合が合理的な既存の仕組みがあれば利用。文書値を固定するだけの大量テストは追加しない）。過去記録は無変更（`git diff` で確認）。runtime baseline は変化しない（文書のみの変更）。意図的に変更しなかった文書を明記する。
- **備考**: コード・テスト・設定ファイルの値は変更しない（`.env.example` はコード上の事実に文書側を合わせるための照合対象で、不一致が見つかった場合は報告する。値を変えるかは別判断）。

### REQ-070: Stage 4C 分の境界回帰テスト（Q10）

- **画面**: テスト全般
- **対象ファイル**: [tests/conftest.py](../../tests/conftest.py)（Stage 4A の外部通信禁止 fixture を維持）、`tests/test_run_position_monitor.py`、`tests/test_live_quote.py`、`tests/test_sheets_client.py`、`tests/test_inflection_backtest.py`、`tests/test_inflection_forward.py`（必要な既存ファイルを拡張。新規ファイルは既存で検証できない場合のみ）
- **Before（現状）**: 同一 ticker 複数 position での取得回数、cross contamination、Sheets 共有後の結果維持、最適化前後の同等性を固定するテストが無い。
- **After（期待）**: 次を回帰テストとして固定する。同一 ticker 複数 position でも価格取得 1 回 / 異なる購入日の position 結果維持 / 共有 DataFrame による cross contamination なし / provider 失敗が他 position へ誤伝播しない / Sheets 共有後も既存結果維持 / 最適化前後の評価結果一致。B09 のために文書値を固定する大量のテストは追加しない。
- **受入条件**: 外部通信試行数 0。保存済み snapshot・archive の変更 0。最適化前の実装と同一入力で結果が一致する比較テスト（または保存した期待値）が存在する。

---

## 保護対象（Stage 4C で壊さない）

Stage 4A・Stage 4B の全項目、第1〜第3段階の全回帰（C01〜C07・B01〜B04・B07・B08・Q01・Q02）。特に Position Monitor の C02/C03、writer 排他 C07、Q02 公開ログ保護、Q04 通知状態、Q07 障害分類、Q09 atomic write、Q10 外部通信禁止。

## Harness 関連

Harness の正式入口が既存の `plan.md` / `proposal.md` の全面差替え判定で停止する問題は、Stage 4C 本体とは別問題として扱う。Harness infrastructure・installer は変更しない。今回の変更について、task 対象の minimal diff guard、`git diff --check`、レビューなど利用可能な既存検証を実施する。正式入口が同じ既存理由で停止する場合は事実だけ報告し、Stage 4C の失敗扱いにしない。新しい Blocking 原因が出たら別途報告する。

## 検証（Stage 4C 完了時）

Q08 対象テスト / Q10 Stage 4C 境界テスト / Stage 4A 回帰 / Stage 4B 回帰 / 第1〜第3段階回帰 / 全テスト / coverage / ruff / mypy（既知 31件・新規 0 件・内容差分で確認）/ 外部通信試行数 / `git diff --check` / task 対象 minimal diff guard / 保存済み snapshot 差分 / archive 差分 / `uv.lock` 差分（なし）。

## 完了報告

Stage 4C 終了後に停止（Growth へ進まない）。形式: 1 Q08（修正前の重複・修正内容・変更ファイル・追加テスト・baseline 一致結果）/ 2 性能比較（provider call 数・Sheets connection 数の before/after、可能なら実行時間・peak memory、変更しなかった候補とその理由）/ 3 B09（更新した文書ごとの「古かった点」と「合わせた先」、意図的に変更しなかった文書）/ 4 baseline（Q08: preserving / changing、B09: runtime への影響、正常入力の投資結果が完全一致したか）/ 5 検証結果（全テスト件数・failed・coverage・ruff・mypy 総件数と新規件数・最終対象回帰件数・外部通信試行数・snapshot / archive 変更数・`uv.lock` 差分・`git diff --check`・minimal diff guard）/ 6 未確認事項（実 GitHub Actions・実 Slack・実 provider・実 Google Sheets・実 Git push・runner 強制停止・Actions 基盤障害。コード上の未解決問題と混同しない）/ 7 Harness（正式入口の Blocking が既存の plan.md / proposal.md 問題と同一か、新規か）/ 8 第4段階最終状態（B05・B06・B09・B10・Q03〜Q10 の完了/未完了。監査の Critical / Bug / Quality に未対応が残っていないかの確認。見つかっても勝手に実装しない）/ 9 次フェーズへの引き継ぎ（保守フェーズ最終 baseline の確定・integration / production smoke test・Growth 候補評価で実施すべき事項のみ。Growth の実装は開始しない）。詳細は `.harness/reports/reliability-stage4c-2026-10-12.md` に記録。

---

## 繰り返し失敗している要件

なし。

---

## 完了済み・保留中

### 完了済み
- Stage 4A: B05 / B06 / B10 / Q06 / Q10（外部通信禁止 fixture）。
- Stage 4B: Q03 / Q04 / Q05 / Q07 / Q09（依頼文の記載による。実装・検証完了の確認はレポートを参照）。

### 保留中（今回のスコープ外）
- Growth Opportunity（G01〜G07）。Stage 4C 完了後も実装を開始せず、保守フェーズ全体の結果確認後に優先順位を決める。
- Q06 閾値の再評価（実データ利用可能になった段階）。
- mypy 既知 31件（スタブ未導入）の解消。
- Harness infrastructure / installer の修正（正式入口の既存停止問題）。
- 新特徴量・スコア・閾値・重み変更、ML framework、新 provider、自動売買・自動発注、永続 cache・大規模並列化、無関係な依存更新、archive 変更、過去 snapshot 変更、過去レポートの歴史修正、全面リファクタリング。
