# 実装要件書（REQ-059〜061: EDINET の大量保有報告を、診断用の特徴量として記録する）

> このファイルは create-plan の入力です。
> 出典: [memo/analysis/improvement_report_2026-10-01.md](../analysis/improvement_report_2026-10-01.md) の B6、[memo/analysis/b6_additional_data_sources_2026-10-07.md](../analysis/b6_additional_data_sources_2026-10-07.md)（2026-10-07 の調査）。
> 以前の要件書: REQ-001〜058 → それぞれ `proposal_req*.md`

## 背景

- catalyst（材料）の点数は、本番では常に0点で、`LIVE_MEASURABLE_MAX_SCORE=58` の原因になっている。材料を point-in-time で取れるデータがないためである。
- **EDINET の大量保有報告書・変更報告書（5%ルール、`docTypeCode` 350/360）は、無料で取得でき、提出日時があるので point-in-time で復元できる。** 機関投資家やアクティビストの参入を示す材料になりうる。有料の J-Quants（Standard 以上、月3,300円）を使わずに済む。
- 効果は未検証なので、**スコアには使わず、診断用の特徴量として記録する**。効果は forward と B1 の過去検証で確認する。

## 決定済みの事項

- **戦略・スコア・分類・候補の選定は変えない。** `STRATEGY_VERSION`（v3）と `REPORT_SCHEMA_VERSION`（5）は変えない。snapshot に足すのは `features`（辞書）の項目だけ（REQ-050・053・054 と同じ方式）。
- **EDINET の取得の失敗で、日次 scan を止めない。** 失敗したら特徴量を `None` にして続行する（best-effort）。
- 取得の頻度は、規約（短時間の大量アクセスの禁止）に従い、**1リクエストあたり3秒以上の間隔**を空ける。
- EDINET の API キーは、`.env`（gitignore）と GitHub の Secrets にだけ置く。ログ・メモ・Git に出さない。**キーの発行は、ユーザーが EDINET の公式サイトで行う**（メールアドレスの登録が必要）。

## 事実確認の状況（2026-10-07）

確認済み（公式または複数の出典）:
- EDINET API v2 の書類一覧: `GET https://api.edinet-fsa.go.jp/api/v2/documents.json`（`date`、`type`、`Subscription-Key`）。日付の指定のみで、銘柄での絞り込みはできない。提出日時（`submitDateTime`）、`docTypeCode`、`secCode`、`issuerEdinetCode`、`subjectEdinetCode`、`filerName` を返す。
- API キーの取得は無料。商用利用も可。短時間の大量アクセスは、予告なく停止されうる。

**未確認（実装の前に、実際の API で確かめる。REQ-059 の確認の段階）:**
- 大量保有報告書（350/360）で、`secCode`・`issuerEdinetCode`・`subjectEdinetCode` が、それぞれ**保有者**と**発行会社（対象の銘柄）**のどちらを指すか。**発行会社の証券コードを得るには、EDINET コードリスト（EDINET コード ↔ 証券コードの対応表）が必要になる可能性が高い。**
- 取得できる過去の範囲（出典により 2016 年以降、2021 年3月以降と食い違う）。
- 1日の書類数、取得に必要なリクエスト数、応答時間。
- 保有目的（純投資・重要提案行為など）が、一覧のメタデータにあるか。ない場合は、今回は記録しない（書類の中身の解析は対象外）。

---

## 要件一覧

### REQ-059: EDINET の大量保有報告のメタデータを取得し、ローカルに保存する（確認の段階を含む）

- **画面**: なし（取得スクリプト、ローカルのキャッシュ）
- **対象ファイル**: 新規 `src/data/edinet.py`（取得とキャッシュ）、新規 `scripts/run_edinet_fetch.py`（CLI）、`.env.example`（キー名の追加）、新規 `tests/test_edinet.py`
- **Before（現状）**: EDINET のデータを取得する仕組みがない。
- **After（期待）**:
  1. **確認（`--probe`）:** 指定した日付1日分の書類一覧から、`docTypeCode` が 350・360 の件数と、各項目の値の例（個人・企業名を除く）を表示する。保有者と発行会社のどちらがどの項目に入るかを、人が確認できる。
  2. **取得（`--fetch`）:** 指定した期間の各日について、書類一覧を取得し、350・360 のメタデータ（`docID`、`submitDateTime`、`docTypeCode`、`secCode`、`issuerEdinetCode`、`subjectEdinetCode`、`filerName`、`withdrawalStatus` など必要な項目だけ）を、日付ごとのファイル（`.data/edinet/filings/YYYY-MM-DD.json.gz`）に保存する。
     - 取得済みの日は飛ばす（途中から再開できる）。1リクエストごとに3秒以上の間隔を空ける。HTTP 429 や一時的な失敗は、B1 の取得（`PATIENT_MAX_RETRIES`）と同じ方式で待って再試行する。
     - 休日・開示のない日は、空のリストとして保存する（再取得を避ける）。
  3. **対応表:** EDINET コードリストを取得して保存し、EDINET コード → 証券コード（4桁のティッカー）の対応を作る。取得できない場合は、`secCode` だけで対応づけられる項目だけを使う（判断は確認の段階の結果による）。
  4. API キーは環境変数 `EDINET_API_KEY` から読む。ログ・例外のメッセージにキーを含めない。
- **受入条件**:
  1. 合成のレスポンスで、350・360 だけが抽出され、必要な項目が保存される（他の書類種別は保存しない）。
  2. 取得済みの日を飛ばして再開できる。空の日が空のリストとして保存される。
  3. 429 や一時的な失敗で、待って再試行し、上限を超えたら理由つきで失敗する。リクエスト間隔が3秒以上である（時計を差し替えたテストで確認する）。
  4. キーが、ログ・例外のメッセージ・保存ファイルに含まれない。
  5. 外部通信は、テストでは行わない（取得関数を差し替える）。
  6. **実 API での確認（`--probe`）の結果が、`memo/analysis/` に記録され、REQ-060・061 の前提（発行会社の特定方法）が確認されている。** 前提が成り立たない場合は、REQ-060・061 に進まず、結果を報告して判断を仰ぐ。
- **備考**: キーの発行は、ユーザーが行う。キーが用意されるまで、実 API での確認（受入条件 6）はできない。それ以外はキーなしで実装・テストできる。

### REQ-060: 日次 scan で、大量保有報告の提出を診断用の特徴量として記録する

- **画面**: なし（snapshot の `features`）
- **対象ファイル**: [src/screening/inflection_live.py](../../src/screening/inflection_live.py)（`FEATURE_DEFAULTS`、`_evaluate_candidate`、`scan_japan_inflection`）、`src/data/edinet.py`、[.github/workflows/inflection_shadow.yml](../../.github/workflows/inflection_shadow.yml)（キーの受け渡し）、`tests/test_inflection_live.py`
- **Before（現状）**: `features` に、大量保有報告の情報がない。
- **After（期待）**: `features` に、次の項目を追加する（すべて**スコアには使わない**）。計算できなければ `None`。
  - `major_holder_filings_60d`: 直近60暦日に、その銘柄（発行会社）を対象にした大量保有報告書・変更報告書（350・360）の提出件数
  - `major_holder_new_filings_60d`: 同、新規の大量保有報告書（350）の件数
  - `days_since_major_holder_filing`: 直近の提出からの経過日数（scan の市場日 − 提出日）
  - 提出は、scan の実行時刻（16:40 JST）までに提出されたもの（`submitDateTime` が scan 時刻以前）だけを数える（point-in-time）。取り下げられた書類は数えない。
  - scan は、直近60暦日分の書類一覧を取得する（リクエスト数は営業日数ぶん。間隔を3秒以上空けるので、数分かかる）。
  - **EDINET の取得に失敗した場合（キーなし、通信の失敗、規約による停止など）は、3項目を `None` にして scan を続行する。** scan の終了コードを失敗にしない。ログには、例外の型名と件数だけを出す（銘柄名・キーは出さない）。
  - `EDINET_API_KEY` が設定されていなければ、取得せず、3項目を `None` にする。
- **受入条件**:
  1. 合成の提出データで、対象銘柄の件数・新規の件数・経過日数が期待どおりになる。scan 時刻より後の提出、取り下げ、他の銘柄の提出は数えない。
  2. 提出が60日より前の銘柄、提出のない銘柄は、件数が0、経過日数が `None`（あるいは要件のとおり）になる（欠損と「0件」を区別する）。
  3. EDINET の取得が失敗しても、scan が成功し、3項目が `None` になる。キーがないときも同じ。
  4. 新しい項目を足しても、スコア、分類、`candidates`、`classification_counts` が変わらない。
  5. `validate_report`、forward の loader、learning の loader が、新しい項目がある snapshot と、ない snapshot の両方を読める。
  6. ログと標準出力に、API キー、保有者名、銘柄名が含まれない。
- **備考**: 取得にかかる時間（数分）を、日次 scan のタイムアウト内に収められるかを、REQ-059 の確認で測る。収まらない場合は、取得を差分（前日までのキャッシュ + 当日）にする方式を、計画で検討する。

### REQ-061: B1 の過去検証と learning で、大量保有報告の特徴量を使えるようにする

- **画面**: なし（過去検証のレポート、learning のレポート）
- **対象ファイル**: [src/evaluation/inflection_historical.py](../../src/evaluation/inflection_historical.py)（`reconstruct_scan`）、[scripts/run_inflection_historical_backtest.py](../../scripts/run_inflection_historical_backtest.py)、[src/evaluation/inflection_learning.py](../../src/evaluation/inflection_learning.py)（`factor_labels`）、`tests/`
- **Before（現状）**: 過去検証は、大量保有報告を知らない。learning も、この特徴量を factor にしていない。
- **After（期待）**:
  - 過去検証の各判定日で、キャッシュ（`.data/edinet/filings/`）から、REQ-060 と同じ関数で3項目を計算する（同じコードを通る）。キャッシュがない日は `None`。
  - learning の `factor_labels` に、`major_holder_filings_60d` の区分（0件、1件、2件以上）と `major_holder_new_filings_60d > 0` を、値がある観測にだけ加える（REQ-055 と同じ方式。既存のラベルは変えない）。
- **受入条件**:
  1. 過去検証で、判定日より後の提出を変えても、その日の3項目が変わらない（先読みしない）。
  2. キャッシュがない期間で、例外にならず `None` になる。
  3. learning の `factor_labels` が、値のある観測にだけラベルを付け、既存のラベルが変わらない。新しいラベルは、既存の昇格判定（Fisher 検定と BH 補正）の対象になる。
  4. 既存の過去検証・learning のテストが PASS する。
- **備考**: 過去の取得（2024-10 以降の約500営業日）は、3秒間隔で30分ほどかかる見込み。取得は、ユーザーが手元で実行する（B1 の取得と同じ運用）。

---

## 繰り返し失敗している要件

なし。

---

## 完了済み・保留中

### 完了済み
- REQ-048〜058（候補の見える化、診断用の特徴量、日次 scan の耐性、learning への接続、過熱警告、DSR、市場別ベンチマーク）

### 保留中（今回のスコープ外）
- **保有目的・保有割合の解析。** 書類の中身（XBRL・CSV）の解析が必要。メタデータだけで効果を確認してから判断する。
- **TDnet（適時開示）、信用残・空売り、決算発表予定日。** 有料プランの判断が先（[調査メモ](../analysis/b6_additional_data_sources_2026-10-07.md)）。
- **大量保有報告の特徴量のスコアへの採用。** 記録だけを行う。採用は、forward と過去検証で効果を確認してから。
- **戦略に影響する項目**（A7 の減衰、A8-a・b、相場環境による切り替え、売却ルールの採用、B5）。
