# 実装要件書（REQ-062〜067: Stage 4B — CI・通知・保存・障害診断）

> このファイルは create-plan の入力です。
> 出典: [memo/local/tmp.md](../local/tmp.md)（Stage 4B 依頼文）、`.harness/reports/repository-audit-2026-10-08.md` の Q03/Q04/Q05/Q07/Q09/Q10、`.harness/reports/reliability-stage4a-2026-10-09.md`。
> 以前の要件書: REQ-001〜061 → それぞれ `proposal_req*.md`（直前の EDINET 要件は `proposal_req059-061.md`）

## 背景・スコープ

- Stage 4A（B05/B06/B10/Q06/Q10の外部通信拒否 fixture）は**確定済み baseline**。仕様の再設計・Q06 閾値（ticker 10 / signal date 5 / 最大業種比率 50%）の変更は禁止。
- 目的: CIの信頼性、secret/token 権限、通知状態の整合性、provider 障害の診断、保存の耐障害性、再現可能な実行環境。
- **投資戦略は変えない**。有効な同一入力に対し、候補・EARLY_CANDIDATE・スコア・閾値・重み・財務/出来高特徴量・benchmark 評価・outcome・portfolio・learning 入力は不変（変化したら原因調査）。障害時の失敗分類・retry・通知・保存状態・workflow 結果は変わってよい。
- 既知 mypy 31件（スタブ未導入）は変更前からの baseline。解消しない。件数ではなく**エラー内容の差分**で新規 0 件を確認する（入れ替わりも新規扱い）。
- 実装手順（各 REQ 共通）: 監査の元指摘を再確認 → Stage 4A 後コード確認 → 既存挙動の欠陥は修正前に失敗する最小テストを用意（Q04 の再送など新規機能は期待仕様テストのみ）→ 最小修正 → 対象テスト → 1〜4A 回帰 → 全テスト → ruff → mypy → 外部通信・保存済みデータ・archive 変更確認。既存テストを新実装に合わせて書き換えるだけは禁止。

---

## 要件一覧

### REQ-062: Forward Validation の PR 検証範囲と secret 条件の分離（Q03）

- **画面**: GitHub Actions（Forward Validation）
- **対象ファイル**: [.github/workflows/forward_validation.yml](../../.github/workflows/forward_validation.yml)、[.github/workflows/test.yml](../../.github/workflows/test.yml)、`tests/test_workflow_reliability.py`（静的検証）
- **Before（現状）**: `pull_request.paths` が 28 個の手列挙。`src/screening/**`、`src/evaluation/inflection_historical.py`、`src/evaluation/inflection_report.py`、`src/data/` の validation / 共通処理、`pyproject.toml`、`uv.lock` の変更は起動しない。`validate` ジョブは `SNAPSHOT_ENCRYPTION_KEY` を前提とした復号処理を含み、PR（特に fork）ではその secret が無い。
- **After（期待）**:
  - path filter が screening / evaluation / report / historical / forward / learning 共有コード / data validation / dependency 定義（`pyproject.toml`、`uv.lock`）/ workflow 自身の変更を漏らさない。手列挙の代わりに `src/**` 等のディレクトリ単位へ単純化できるなら採用（理由を報告）。
  - secret 不要の軽量検証（unit test・lint・型検査・静的 workflow 検証・fake データの Forward 関連テスト）は全 PR で実行してよい。復号を伴う重い検証（暗号化 snapshot の復号、信頼済み保存データによる評価）だけを path filter 等で絞り、secret が使える実行（schedule / workflow_dispatch / same-repo の信頼済み実行）に限定する。
  - secret 無しの PR（fork 含む）でも secret 不要の検証が正常完了する。
  - **fork PR に secret を渡す変更は禁止**（`pull_request_target` で PR コードを checkout して secret を使う構成も不可）。
- **受入条件**: workflow 静的テストで、同一リポジトリ PR / fork PR / push / schedule / workflow_dispatch × secret あり/なし の各組合せについて、(a) 上記の各変更カテゴリが検証ジョブを起動する、(b) secret を参照するステップは secret 必須ジョブ・ステップにのみ存在する、(c) fork 由来イベントで secret が渡らない、(d) `pull_request_target` を使っていない、を確認できる。
- **備考**: 無条件で全 PR に重い処理を回さない。変更する場合は必要性を説明する。

### REQ-063: 日次ダイジェストの成功状態の分離と安全な再送（Q04）

- **画面**: 日次 Slack ダイジェスト（Inflection Shadow）
- **対象ファイル**: [scripts/run_inflection_shadow.py](../../scripts/run_inflection_shadow.py)（`_deliver_digest`、`persist_report`）、[src/notify/inflection_digest.py](../../src/notify/inflection_digest.py)（`send_daily_digest`）、[src/notify/slack.py](../../src/notify/slack.py)、[.github/workflows/inflection_shadow.yml](../../.github/workflows/inflection_shadow.yml)
- **Before（現状）**: `snapshot_created=False`（同日再実行）だと `skipped:snapshot-existed` となり通知を送らない。つまり「snapshot が存在する」が「通知済み」の代用になっており、Slack 一時失敗や Git push 失敗後の再実行で通知が失われる。
- **After（期待）**:
  - snapshot created / persisted（runner 内保存）/ published（Git 反映）/ notification attempted / notification succeeded を区別して識別できる（log・Actions 出力・必要なら既存 snapshot のメタ情報で表現。新しい外部 DB・queue は導入しない）。
  - snapshot の存在だけで「通知済み」と判断しない。Slack 一時失敗に対し、明示的な再送経路（例: `workflow_dispatch` の入力、またはCLI フラグ）を持つ。
  - 同日の通常再実行・手動再送・再送後の通常実行で、可能な範囲で重複通知を抑制する。
  - **Exactly Once Delivery を保証したと表現しない**。Slack 受理後・状態保存前に停止するケース、状態保存後の Git push 失敗のケースなど、保証できない境界を文書化（コード内コメントまたは `docs/playbooks.md`）する。
  - 状態は既存 snapshot または Actions 出力で表現する。**新しい状態ファイルが必要な場合は理由を報告**する（REQ-066 の atomic write と Git push 失敗の境界が絡むため）。
- **受入条件**: fake Slack で次を確認する。(1) Slack 送信前に停止 → 通常再実行で通知される、(2) Slack 成功後に状態保存失敗 → 通常再実行で重複し得ることが分類・文書化されている、(3) 状態保存成功後に Git push 失敗、(4) 同日通常再実行は重複抑制、(5) 手動再送は送信され状態が更新される、(6) 再送後の通常実行は重複しない。実 Slack は使わない。公開ログに候補情報が出ない（既存仕様維持）。
- **備考**: 新規機能なので修正前の失敗確認は不要（期待仕様テストのみ）。Slack 通知失敗でスキャン全体を失敗させない既存仕様は維持。

### REQ-064: lockfile・Action SHA 固定・最小権限（Q05）

- **画面**: GitHub Actions（全 workflow）
- **対象ファイル**: `.github/workflows/*.yml`（forward_validation / inflection_shadow / position_monitor / reliability_watchdog / test）、[uv.lock](../../uv.lock)、[pyproject.toml](../../pyproject.toml)
- **Before（現状）**: 全 workflow が `python -m pip install -e .`（一部 `".[dev]"`）で依存を解決し、`uv.lock` が CI で使われていない。Action は `actions/checkout@v7`、`setup-python@v7`、`cache/restore@v4` 等のタグ指定で full SHA 固定ではない。`inflection_shadow.yml` は workflow 全体が `contents: write`。
- **After（期待）**:
  - CI / 定期実行は既存 `uv.lock` から同一依存を解決する（新しい依存管理基盤・不要な更新は導入しない）。lockfile と現行環境に差があれば機械的に更新せず内容と影響を確認・報告。
  - 現在使用中の各 Action の version を確認し、**そのタグに対応する検証済み full commit SHA** に固定する。最新版へ上げない。元タグをコメントで追跡可能にする。タグ→SHA の解決には GitHub への**読み取り専用の問い合わせ（`gh api` 等の GET）のみ**許可。
  - GitHub token permission と secret の必要箇所を workflow / job / step 単位で棚卸しし、最小化する（contents read/write、pull request、secret 利用、Git push）。secret・write 権限を要しない処理に与えない。PR 検証と本番更新処理を混同しない。
- **受入条件**: 静的テストで、(a) すべての `uses:` が 40 桁 SHA 固定かつ元タグのコメント付き、(b) `contents: write` と Git push は snapshot/hash 保存ジョブのみ、(c) secret は必要なジョブ・ステップのみ、(d) 不要な `pull-requests` 等の権限が無い、(e) 依存導入が lockfile ベース、を検証する。依存の version が変わっていないこと（`uv.lock` の diff が無い、または内容を説明済み）。
- **備考**: 実際の GitHub Actions 上の動作・Git push 権限はローカルで確認不能（未解決事項として報告）。

### REQ-065: provider 取得失敗の安全な分類（Q07）

- **画面**: provider 取得処理（yfinance / J-Quants / EDINET / Position Monitor）
- **対象ファイル**: [src/data/yfinance_prices.py](../../src/data/yfinance_prices.py)、[src/data/forward_prices.py](../../src/data/forward_prices.py)、[src/data/live_quote.py](../../src/data/live_quote.py)、[src/data/provider_output.py](../../src/data/provider_output.py)、[src/data/jquants_v2_client.py](../../src/data/jquants_v2_client.py)（Retry-After 処理）、[src/data/edinet.py](../../src/data/edinet.py)（Retry-After 処理）、[scripts/run_position_monitor.py](../../scripts/run_position_monitor.py)
- **Before（現状）**: `except Exception: # noqa: BLE001` が複数箇所（`yfinance_prices.py:112`、`forward_prices.py:158`、`live_quote.py:166,207` 等）で例外を握り、「データなし」/ coverage 不足に畳む。原因（timeout / 429 / 5xx / 空応答 / 不正 OHLCV / 想定外バグ）が失われる。EDINET の `Retry-After` は有限性のみ確認で上限・非負の検証が無く、J-Quants は非負のみ。
- **After（期待）**:
  - 最低限 timeout / HTTP 429 / HTTP 5xx / protocol・response 構造異常 / empty response / invalid OHLCV / validation failure / authentication・authorization / 想定外例外（programmer error）を区別できる安全な分類を残す。
  - 公開してよい情報は provider 分類・処理段階・安全な例外種別・HTTP status・retry 回数・対象件数・行番号など。ticker・購入日・URL query・API key・token・credential・response body・未加工例外本文は出さない。Stage 2 の Q02 公開ログ保護を維持。
  - 想定外バグ（TypeError 等）を「データなし」として握り潰さない。
  - 既存 retry を作り直さない。`Retry-After` を使う箇所は数値検証・有限・非負・上限を設ける（異常値で長時間停止しない）。
- **受入条件**: fake provider で timeout / 429 / 500 / malformed response / empty / invalid price / TypeError を発生させ、分類結果が区別され、公開出力（print・logger・例外文字列）に ticker・URL・秘密情報が含まれず、想定外バグは握り潰されず上位に伝わることを確認する。`Retry-After` が `inf`・`nan`・負数・巨大値でも待機が上限内であることを確認する。正常入力の取得結果は不変。
- **備考**: 既存の `noqa: BLE001` コメント付き箇所は、意図（ticker 非露出）を保ちつつ分類を残す。

### REQ-066: snapshot・結果ファイルの atomic write（Q09）

- **画面**: 保存処理（snapshot / JSON 結果 / summary / hash / evaluation・learning・historical 出力）
- **対象ファイル**: [scripts/run_inflection_shadow.py](../../scripts/run_inflection_shadow.py)（`snapshot.write_text`、`latest_path.write_text`）、[scripts/rebuild_inflection_forward_validation.py](../../scripts/rebuild_inflection_forward_validation.py)（`path.write_text`、`output.write_text`、`summary_output.write_text`）、[scripts/rebuild_inflection_learning.py](../../scripts/rebuild_inflection_learning.py)、[scripts/run_inflection_historical_backtest.py](../../scripts/run_inflection_historical_backtest.py)。再利用候補: [src/data/jquants_history.py](../../src/data/jquants_history.py)・[src/data/edinet.py](../../src/data/edinet.py)・[scripts/check_workflow_health.py](../../scripts/check_workflow_health.py) の既存「tmp→`os.replace`」パターン。
- **Before（現状）**: 上記の `write_text` / `open("w")` は最終パスへ直接 truncate して書き込むため、途中中断で壊れた JSON / 暗号化 snapshot が残り得る。既存の安全な書込みは一部（キャッシュ・状態ファイル）のみ。
- **After（期待）**:
  - 実際に破損リスクのある単一ファイル書込みを、temporary file → write → flush →（必要なら fsync）→ `os.replace` に統一する（既存パターンがあれば再利用。機械的な全箇所共通化はしない）。
  - 保護条件: immutable snapshot を上書きしない / 同日の既存正常 snapshot を壊さない / replace 前に失敗したら旧ファイル維持 / temp ファイルを正常成果物として認識しない（snapshot 列挙・読込側で除外）/ 出力親ディレクトリを安全に作成 / run ID のある成果物で世代を混同しない。
  - 複数ファイル間の完全 transaction は実装しない。「本当に atomic にできる単一ファイル」と「複数成果物間の整合性」を区別して報告する。
- **受入条件**: temp ディレクトリのみで次を確認する。write 途中失敗 / flush 失敗 / replace 前停止 / replace 失敗で旧ファイルが無傷、二重実行、既存 immutable snapshot が上書きされない、新規 output directory、temp ファイルが snapshot 列挙・読込に混入しない。保存済みの本番 snapshot・archive に触れない。保存内容（バイト列）は従来と同一。
- **備考**: 既存 snapshot の書換え・archive の整理は禁止。

### REQ-067: Stage 4B 分の境界回帰テスト（Q10）

- **画面**: テスト全般
- **対象ファイル**: [tests/conftest.py](../../tests/conftest.py)（Stage 4A の外部通信拒否 fixture を維持）、`tests/test_workflow_reliability.py`、`tests/test_inflection_digest.py`、`tests/test_yfinance_prices.py`、`tests/test_forward_prices.py`、`tests/test_live_quote.py`、`tests/test_inflection_forward.py`（必要な既存ファイルを拡張。新規ファイルは既存で検証できない場合のみ）
- **Before（現状）**: REQ-062〜066 の境界（secret なし PR、Slack 失敗と再送、通知成功・保存失敗、provider timeout/429/500、生ログ漏洩、atomic write 失敗、immutable file、workflow 権限）を固定するテストが無い。
- **After（期待）**: 上記の境界を、外部通信なし・実 Slack なし・temp 領域のみで固定するテストが存在する。coverage 目的だけのテストは追加しない。
- **受入条件**: 追加テストが REQ-062〜066 の各受入条件に対応し、外部通信試行数 0、保存済み snapshot 変更 0、archive 変更 0。

---

## 保護対象（Stage 4B で壊さない）

第1〜Stage 4A の全回帰テスト。特に C06 validation、B02 J-Quants 異常 response、B03 cache 回復、C02/C03 Monitor、C07 writer 排他、Q01 Watchdog、Q02 公開ログ保護、B10 configuration error、Q10 外部通信禁止。

## 検証（Stage 4B 完了時）

Stage 4B 対象テスト / Stage 4A 回帰 / 第1〜第3段階回帰 / 全テスト / coverage / ruff / mypy（既知 31件・新規エラー 0・内容差分で確認）/ workflow 静的確認 / 外部通信試行数 / 保存済み snapshot 変更数 / archive 変更数。

## 完了報告

Stage 4B 終了後に停止（Stage 4C へ進まない）。形式: 1 修正一覧（原因・修正・主なファイル・テスト）/ 2 baseline への影響 / 3 障害時挙動の変更（PR・secret 不足・通知失敗・Git 保存失敗・provider 障害・atomic write 失敗の前後）/ 4 検証結果 / 5 セキュリティ・権限（Action SHA・token permissions・secret scope・fork PR）/ 6 未解決事項（GitHub Actions 本番・Git push 権限・実 Slack・実 provider・runner 中断・基盤障害）/ 7 独立レビュー（secret 漏洩・ログ漏洩・二重通知・通知消失・ファイル破損・PR 検証漏れ・provider 障害の握り潰し・回帰。重大な問題のみ修正して再検証）/ 8 Stage 4C への引き継ぎ（Q08/B09 実施時の注意のみ）。詳細は `.harness/reports/reliability-stage4b-2026-10-12.md` に記録。

---

## 繰り返し失敗している要件

なし。

---

## 完了済み・保留中

### 完了済み
- Stage 4A: B05（第3段階-A で解消済み、回帰テスト追加）/ B06 / B10 / Q06 / Q10（外部通信拒否 fixture）。確定済み baseline。

### 保留中（今回のスコープ外）
- Stage 4C: Q08（重複取得・再計算の計測と 1 run 内共有）、B09（文書整合性）。
- Growth Opportunity（G01〜G07）。
- Q06 閾値（ticker 10 / signal date 5 / 最大業種比率 50%）の再評価 — 実データ利用可能になった段階で実施。
- mypy 既知 31件（スタブ未導入）の解消。
- 新しい特徴量・スコア変更・閾値最適化・重み調整・ML framework・新 provider・自動売買・自動発注・過去 snapshot 書換え・archive 変更・無関係な依存 version 更新・全面リファクタリング。
