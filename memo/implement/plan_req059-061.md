## 実装計画: EDINET の大量保有報告を、診断用の特徴量として記録する（REQ-059〜061）

### 目的
無料で point-in-time に取れる EDINET の大量保有報告書・変更報告書（`docTypeCode` 350/360）を取得・保存し（REQ-059）、日次 scan の `features` に診断用の3項目として記録し（REQ-060）、B1 の過去検証と learning でも使えるようにする（REQ-061）。スコア・分類・候補の選定・戦略は変えない。

### スコープ
- 含むもの: EDINET の取得クライアントとキャッシュ、確認用の `--probe`、EDINET コードリストによる銘柄の対応づけ、`features` の3項目、過去検証での再現、learning の factor ラベル
- 含まないもの: 保有目的・保有割合の解析（書類の中身）、TDnet・信用残・空売り・決算予定日、特徴量のスコアへの採用、`STRATEGY_VERSION`・`REPORT_SCHEMA_VERSION` の変更、戦略に影響する項目

### 実装の順序と関門
**Phase A（REQ-059）→ 関門 → Phase B（REQ-060・061）。** 関門は、実 API での確認（`--probe`）で、「大量保有報告で、発行会社をどの項目で特定できるか」を確かめること。前提が成り立たなければ、Phase B に進まず、結果を報告して判断を仰ぐ。関門より前の作業（取得・キャッシュ・テスト）は、API キーなしで完了できる。

### 事前に確認した事実
- 既存の B1 の取得は、日付ごとのファイル（`.data/<kind>/YYYY-MM-DD.json.gz`）に保存し、取得済みの日を飛ばして再開する。保存・読み出しの関数は [src/data/jquants_history.py](../../src/data/jquants_history.py) の `_write_day`（一時ファイルから `os.replace`）、`read_day`、`_path`。`KINDS = ("bars", "master", "fins")` は `fetch_range` の対象の限定にだけ使われ、`_path`・`_write_day`・`read_day` は `kind` の文字列を自由に渡せる。`.data/` は gitignore。
- B1 の取得の再試行は、`JQuantsV2Client(max_retries, retry_backoff)`（[jquants_v2_client.py](../../src/data/jquants_v2_client.py) の `_request`、`requests.get`、`_retry_delay`）と、スクリプト側の `PATIENT_MAX_RETRIES = 5`・`PATIENT_RETRY_BACKOFF_SECONDS = 15.0`。EDINET のクライアントも、同じ考え方（`requests`、待って再試行、上限で失敗）で作る。
- `select_and_evaluate(prices, ticker_meta, client, *, seed_date, deep_candidates, min_turnover_jpy, control_sample_size, fundamental_limitation)` は、ライブ（`scan_japan_inflection`）と過去検証（`reconstruct_scan`）の**両方から**呼ばれる。ここに任意の引数を足せば、同じコードで両方に特徴量が入る。
- 日次 scan の job は `timeout-minutes: 45`。`JQUANTS_API_KEY` は scan の step の `env` で渡される。
- `_evaluate_candidate` は `source`（辞書）から `FEATURE_DEFAULTS` のキーを `features` に書く。新しい項目は、`FEATURE_DEFAULTS` と `source` への追加だけで入る（REQ-050・053・054 と同じ方式）。
- **取下げ後の書類は、後日の一覧から消去される（レビューで確認。[EDINET API 仕様書 Version 2](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/download/ESE140206.pdf) の 3-1-3・3-1-5）。** 過去の日付を指定した一覧も更新され、取下げ後は元の `docTypeCode`・`submitDateTime`・`issuerEdinetCode` などが `null` になる。取下書の書類種別も `null`。したがって、**要件書の「提出日時があるので point-in-time で復元できる」は、そのままでは成り立たない**。後日取得した一覧から、当時は有効だった（のちに取り下げられた）提出が消えるため、過去の判定日の件数が実際より少なくなりうる。
- **本計画の方針（過去時点の保証を維持する）:** ①日ごとのキャッシュに、取得時刻（`captured_at`）と、種別が消去された記録（`docTypeCode` が `null` の記録）を、**捨てずに**保存する。②ある日の一覧が、判定の時刻 `cutoff`（`as_of` の16:40 JST）の評価に使えるのは、**次の2つを両方満たす場合だけ**とする（レビューの再指摘を受けて、条件を逆にした。「`cutoff` 以前に取得した一覧」は、取得後に追加された提出・取下げを含まないので、**使えない**）。**(a) その一覧を `cutoff` 以後に取得した（`captured_at` ≥ `cutoff`）**: `cutoff` までの提出と状態の変更が、すべて反映されている（取得が `cutoff` より前だと、取得後の同日の追加提出や、その後の取下げを反映できない）。**(b) 種別が消去された記録のうち、大量保有報告だった可能性を否定できないものが0件**: `cutoff` 以後の取下げで消えた提出、`cutoff` より前に取り下げられた提出（当時は取り下げ済み）の区別がつかないため、可能性が残るなら使わない。どちらかを満たさない日は**復元不能**とする。日別キャッシュは、取得済みの日を飛ばす再開のためだけに使い、**判定に使えるかの保証は、再開機能とは分けて、評価の時点の `day_usable` が決める**。③復元不能な日を、60日の窓に1日でも含む判定日は、全銘柄の3項目を `None`（0件にしない）にする。④ライブ scan は、実行時点の一覧を使う（取下げ済みの書類が消えているのは、その時点の実際の状態なので、point-in-time として正しい）。⑤`--probe` で、消去後も残る項目（`ordinanceCode`・`formCode` など）と、種別が消去された記録の頻度を測る。残る項目で「大量保有報告ではない」と判定できる記録は、(b) の否定に使ってよい（**どの項目が残るかは未確認。推測せず、`--probe` で確かめる**）。
- **未確認（Phase A の関門で確かめる）:** 350/360 の `secCode`・`issuerEdinetCode`・`subjectEdinetCode` の意味、EDINET コードリストの取得先 URL と形式（EDINET コード ↔ 証券コードの列）、取得できる過去の範囲、1日の書類数、応答時間、**取下げ後も残る項目と、種別が消去された記録の頻度（復元不能な日の割合）**。**取得先 URL や項目名を、記憶や二次情報から推測して実装しない。**

### 影響範囲（変更/追加予定ファイル）
- 新規 [src/data/edinet.py](../../src/data/edinet.py): 取得クライアント、350/360 の抽出、日付ごとのキャッシュ、EDINET コードリストの対応表、特徴量の計算
- 新規 [scripts/run_edinet_fetch.py](../../scripts/run_edinet_fetch.py): CLI（`--probe`、`--fetch`）
- [.env.example](../../.env.example): `EDINET_API_KEY` を追加（値は書かない）
- [src/screening/inflection_live.py](../../src/screening/inflection_live.py): `FEATURE_DEFAULTS`、`select_and_evaluate`・`_evaluate_candidate` の任意引数、`scan_japan_inflection` での取得（best-effort）
- [src/evaluation/inflection_historical.py](../../src/evaluation/inflection_historical.py): `reconstruct_scan` / `HistoricalData` への受け渡し
- [scripts/run_inflection_historical_backtest.py](../../scripts/run_inflection_historical_backtest.py): キャッシュの読み込み（任意）
- [src/evaluation/inflection_learning.py](../../src/evaluation/inflection_learning.py): `factor_labels`
- [.github/workflows/inflection_shadow.yml](../../.github/workflows/inflection_shadow.yml): scan の step の `env` に `EDINET_API_KEY`（GitHub Secrets）を追加
- `tests/test_edinet.py`（新規）、`tests/test_inflection_live.py`、`tests/test_inflection_historical.py`、`tests/test_inflection_learning.py`（既存に追記）
- `memo/analysis/`: `--probe` の結果の記録（受入条件）
- 変更しないもの: スコア・分類の計算、`STRATEGY_VERSION`、`REPORT_SCHEMA_VERSION`、forward・Monitor

### 実装ステップ

#### Phase A（REQ-059）

##### Step 1: 取得クライアントと抽出（API キー不要）
- [ ] `src/data/edinet.py` に、書類一覧（`documents.json`、`date` 指定）を取得するクライアントを作る。キーは環境変数 `EDINET_API_KEY` から読み、**例外のメッセージ・ログにキーを含めない**（URL やヘッダーをそのまま出さない）。
- [ ] リクエスト間隔は3秒以上（既定値を定数にし、`sleep` と時計を引数で差し替えられるようにして、テストで待たずに間隔を検証できるようにする）。HTTP 429・5xx・通信の失敗は、待って再試行する（上限を超えたら理由つきで失敗。B1 と同じ考え方で、回数と待ち時間は定数）。4xx（429 以外）は、再試行せずに失敗する。
- [ ] レスポンスの `results` から、`docTypeCode` が 350・360 のものを抽出し、必要な項目（`docID`、`submitDateTime`、`docTypeCode`、`secCode`、`issuerEdinetCode`、`subjectEdinetCode`、`filerName`、`withdrawalStatus` など。項目名は、`--probe` で実在を確認してから確定する）を保存する。**加えて、`docTypeCode` が `null` の記録（取下げ後に種別が消去された書類、取下書）も、捨てずに、残っている識別項目（`docID`、`ordinanceCode`、`formCode` など、`--probe` で残ると確認できたもの）だけを `erased_records` として保存する**（種別が消去された記録は、大量保有報告だった可能性を否定できないため、復元不能の判定に必要）。350・360 以外の種別の記録は、保存しない。
- [ ] 日付ごとのキャッシュ（`.data/edinet/filings/YYYY-MM-DD.json.gz`。要件書のパスに統一する）は、**辞書**で保存する: `{"captured_at": 取得時刻（JST、タイムゾーンつき）, "filings": [...], "erased_records": [...]}`。取得済みの日を飛ばす。**正常応答で書類がなかった日は、`filings` も `erased_records` も空で保存する**（API の失敗で取得できなかった日は保存しない。空の日と未取得の日を区別する）。保存・読み出しは、`jquants_history` の `_write_day`・`read_day` の考え方（一時ファイルから `os.replace`）に従う（読み出しは、リストではなく辞書を返すので、同等の小さな関数を `edinet.py` に置く。コピーが小さいなら、依存を避けてコピーする）。
- [ ] 日の評価に使えるかを返す関数 `day_usable(day_record, cutoff)` を作る: **`captured_at` ≥ `cutoff` かつ、`erased_records` のうち大量保有報告だった可能性を否定できないものが0件**のときだけ使える。それ以外（`captured_at` < `cutoff`、または消去記録が残る）は復元不能（使えない）。「否定できる」の条件は、`--probe` で残ると確認した項目に基づく（確認できるまでは、`erased_records` が1件でもあれば復元不能とする安全側の扱い）。
- [ ] 日別キャッシュは、**一度保存したら上書きしない**（取得済みの日を飛ばす再開のため。`captured_at` が最初の取得時刻のまま残る）。判定に使えるかは、再開の有無と関係なく、評価の時点の `day_usable` が決める。**取得を、評価したい期間の判定時刻（`cutoff`）より後に実行すること**が、過去検証で値が入るための前提になる（B1 の取得を今実行すれば、2026-07 以前の判定は条件 (a) を満たす）。
**検証**: 受入条件 1〜5（REQ-059）。合成のレスポンスでテストする。外部通信はしない。取下げ後の記録（種別が `null`）が `erased_records` に保存され、350/360 以外の種別は保存されないこと、空の日と未取得の日が区別されること、`day_usable` の3つの場合（取得時刻が当時以前、消去記録なし、消去記録あり）を確認する。

##### Step 2: CLI（`--probe`、`--fetch`）
- [ ] `scripts/run_edinet_fetch.py` に、`--probe DATE`（その日の 350/360 の件数と、各項目の値の例を表示する。**保有者名・会社名は表示しない**。項目が空かどうか、形式（桁数）だけを出す）と、`--fetch --start --end`（期間を取得する）を作る。
- [ ] キーがないときは、分かりやすいメッセージで終了コード1にする（キーの値は出さない）。
**検証**: キーなしのメッセージ、引数の検証をテストする。

##### Step 3: EDINET コードリストによる対応表
- [ ] **関門の結果（[edinet_probe_2026-10-07.md](../analysis/edinet_probe_2026-10-07.md)）: 発行会社は `issuerEdinetCode`（350/360 の 100% で6桁）で特定する。`secCode` は4〜12%しか入らず、使わない。** EDINET コードリスト（EDINET コード ↔ 証券コード）で対応表（EDINET コード → 4桁のティッカー）を作る関数を `edinet.py` に追加する。
  - 取得先（実 API の確認で、HTTP 200 を確認済み）: `https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip`（約570KB）。中の `EdinetcodeDlInfo.csv` は **Shift-JIS（cp932）**。1行目は「ダウンロード実行日…件数」の見出しで、2行目が列の見出し。使う列は `ＥＤＩＮＥＴコード`（全角）と `証券コード`（5桁。空の行は上場していない）。件数は 11,405 件、証券コードがあるのは 3,817 件。**列名は全角なので、文字列を正確に合わせる**（変化に備えて、列が見つからなければ明確なエラーにする）。
  - ティッカーへの変換: 5桁の証券コードの先頭4桁 + `.T`（既存の `_ticker_from_code` と同じ規則に合わせる。普通株は5桁目が `0`）。
  - 実測の対応率: 350/360 のうち 88%（1,792 / 2,027）が、上場会社の証券コードに対応づく。残りは非上場の発行会社などで、対象外（件数に数えない）。
  - 日次 scan では、実行のたびにコードリストを取得する（best-effort。失敗したら3項目を `None`）。保存は不要。
**検証**: 合成のコードリスト（cp932、全角の列名、見出し行つき）で、対応表が作られる。列が見つからない、証券コードが空の行、4桁への変換を確認する。

##### 関門: 実 API での確認（ユーザーの API キーが必要）
- [ ] ユーザーが EDINET で API キーを発行し、`.env` に `EDINET_API_KEY` として置く（キーを会話・ログ・Git に出さない）。
- [ ] `--probe` を、大量保有報告の提出が多い日（例: 直近の営業日と、数か月前の営業日）で実行し、①発行会社を特定する項目、②各項目の形式、③1日の応答時間と書類数、④取得できる過去の範囲を確認する。
- [ ] **取下げ後の記録を確認する:** 過去の数日分の一覧で、`docTypeCode` が `null` の記録の件数、その記録に残っている項目（`docID`、`ordinanceCode`、`formCode`、`withdrawalStatus` など）、種別が消去された記録がある日の割合を測る。残る項目で、大量保有報告ではないと判定できるかを確認する。
- [ ] 結果を `memo/analysis/edinet_probe_YYYY-MM-DD.md` に記録する（個人名・会社名は書かない）。復元不能な日の割合の見込みも書く。
- [ ] **発行会社を特定できない、または 350/360 が取得できない場合は、Phase B に進まず、結果を報告して判断を仰ぐ。** また、**復元不能な日の割合が高く、REQ-061 の過去検証がほとんど `None` になる見込みの場合も、REQ-061 の範囲（過去検証への適用）を、報告して判断を仰ぐ**（REQ-060 のライブの記録は、この影響を受けない）。
- **関門の結果（2026-10-07、実施済み）:** 発行会社は `issuerEdinetCode` で特定できる（上の Step 3）。一方、種別が消去された記録は、残る項目（`docID`・`parentDocID`・`withdrawalStatus` など）では大量保有報告だったかを判定できず、**1件以上ある日が 26 / 31（84%）**だった。厳密な条件では、過去検証の3項目は、ほぼすべて `None` になる。
- **REQ-061 の範囲（判断: ②過去検証への適用を見送る。レビューと本計画の推奨）:** 過去検証（`reconstruct_scan`・`HistoricalData`・`run_inflection_historical_backtest.py`）への適用は、**今回は実装しない**。ライブの記録（REQ-060）が溜まった後、forward と learning で評価する。近似（消去記録を数えない）で過去検証に入れる案は、検証・昇格判定への利用範囲を先に要件で決める必要があるため、今回は含めない（既存の検証経路に黙って入れない）。`day_usable`（Phase A で実装済み）は、将来の過去検証への適用に備えて残すが、Phase B では配線しない。
**検証**: 受入条件 6（REQ-059）。実施済み（[edinet_probe_2026-10-07.md](../analysis/edinet_probe_2026-10-07.md)）。

#### Phase B（REQ-060・061。関門を通過した場合だけ）

##### Step 4: 特徴量の計算関数
- [ ] `edinet.py` に、純粋関数 `holder_filing_features(day_records, ticker, as_of, cutoff, mode)` を作る。入力は、日付 → 日ごとの記録（`captured_at`・`filings`・`erased_records`）の対応（`mode="historical"` では、`day_usable` が真の日だけを使う）、対象のティッカー（発行会社の特定は Step 3・関門の結果に従う）、scan の市場日、提出日時の上限（`cutoff`）、`mode`（`"live"` か `"historical"`）。出力は、`major_holder_filings_60d`、`major_holder_new_filings_60d`（350 のみ）、`days_since_major_holder_filing`。
- [ ] 数える提出は、`submitDateTime` が `cutoff` 以下で、`as_of` から60暦日以内のもの。**`mode="live"`**: 実行時点の一覧をそのまま使う（取下げ済みで消去された書類は、その時点で存在しないので、数えない）。**`mode="historical"`**: 60日の窓の営業日のうち、**`day_usable` が偽の日（復元不能）、または記録がない日が1日でもあれば、3項目すべて `None`**（0件にしない。全銘柄に適用する）。提出がない場合は、件数 0・経過日数 `None`。**取得に失敗した（データがない）場合は、3項目すべて `None`**（0件と欠損を区別する）。
- [ ] タイムゾーンを明示して比較する（`submitDateTime` は JST。`cutoff` は JST の `as_of` の16:40 を使う）。
**検証**: 受入条件 1、2（REQ-060）。境界（ちょうど60日、`cutoff` ちょうど）、取り下げ、他の銘柄の提出を、合成データでテストする。加えて、レビューの再現ケースをテストにする。(1) 「10/1 に 350 が提出され、10/2 の判定時点では未取下げ、10/3 に取り下げられ、10/4 に 10/1 分を取得する（種別が `null` に消去されている）」とき、`mode="live"`（10/4 の実行）では0件、`mode="historical"` の 10/2 の判定では、消去記録が残るので、3項目が `None`（0件ではない）になること。(2) **「10/1 の 09:00 に空の一覧を取得し、同日の 10:00 に 350 が提出される」とき、16:40 の判定（`captured_at` < `cutoff`）は復元不能で、3項目が `None`（0件ではない）になること。** (3) **「10/1 分を同日 17:00 に保存し、10/2 に取り下げられる。10/5 の判定に、古い 10/1 分（`captured_at` 10/1 17:00）を渡す」とき、`captured_at` < `cutoff` なので `None` になり、古い記録の1件を数えないこと。** (4) `captured_at` ≥ `cutoff` で、消去記録がない日は、使えて、件数が数えられること。(5) `captured_at` ≥ `cutoff` でも、消去記録が残る日は、`None` になること。

##### Step 5: ライブ scan への組み込み（best-effort）
- [ ] `select_and_evaluate` と `_evaluate_candidate` に、任意の引数（`holder_filings`、既定は `None`）を追加する。`None` のとき、3項目は `None`。`FEATURE_DEFAULTS` に3項目（既定 `None`）を追加し、`source` に入れる。
- [ ] `scan_japan_inflection` で、`EDINET_API_KEY` があるとき、直近60暦日の営業日分の書類一覧を取得して `holder_filings` を作る。**例外は `Exception` 全般ではなく、取得クライアントが投げる失敗（通信・HTTP・解析）を捕捉し**、失敗したら `holder_filings = None` で scan を続行する。ログには、例外の型名と日数だけを出す。scan の終了コードは変えない。
- [ ] 取得の所要時間を測り（リクエスト間隔3秒 × 約43営業日 + 応答時間）、scan の job の `timeout-minutes: 45` に収まるかを確認する。収まらない場合は、取得の上限時間を設け、超えたら打ち切って `None` にする（日次 scan の完了を、診断用の特徴量より優先する）。
- [ ] `inflection_shadow.yml` の scan の step の `env` に `EDINET_API_KEY: ${{ secrets.EDINET_API_KEY }}` を追加する（Secrets の登録は、ユーザーが GitHub で行う）。
**検証**: 受入条件 3〜6（REQ-060）。取得が失敗しても scan が成功し、3項目が `None` になる。ログにキー・保有者名・銘柄名が出ない。

##### Step 6: learning への接続（REQ-061 の縮小した範囲）
- [ ] **過去検証への適用は、今回は実装しない**（上の関門の判断）。`reconstruct_scan`・`HistoricalData`・`run_inflection_historical_backtest.py` は変更しない。`holder_filing_features` の `mode="historical"` も、Phase B では実装しない（`mode="live"` だけ）。
- [ ] `factor_labels` に、`major_holder_filings_60d` の区分（0件、1件、2件以上）と `major_holder_new_filings_60d > 0` を、値がある（`None` でない）観測にだけ加える（REQ-055 と同じ方式。既存のラベルは変えない）。ライブの snapshot に溜まった値が、forward の learning で評価される。
**検証**: 受入条件 3、4（REQ-061）。learning の `factor_labels` が、値のある観測にだけラベルを付け、欠損（`None`）の観測にラベルが付かないこと。既存のラベルが変わらないこと。受入条件 1、2（過去検証）は、今回の範囲外（見送り）。

##### Step 7: 回帰と最終確認
- [ ] 新しい項目を足しても、スコア・分類・`candidates`・`classification_counts` が変わらないこと（REQ-050 のテストと同じ方式）。`validate_report`、forward・learning の loader が、項目がある snapshot とない snapshot の両方を読めること。
- [ ] ruff、mypy（CI の対象に `src/data/edinet.py` と `scripts/run_edinet_fetch.py` を加える。`.github/workflows/test.yml` の mypy の一覧）、`pytest tests/ -q`（カバレッジ 80% 以上）。
**検証**: 完了条件の全項目。

### 例外・エラーハンドリング方針
- EDINET の失敗は、日次 scan を止めない（特徴量を `None` にして続行）。ただし、`except Exception` で広く握りつぶさず、取得クライアントの失敗の型に限る。
- 4xx（429 以外）や認証の失敗（キーの誤り）は、再試行せず、理由（HTTP の状態）つきで失敗する。キーの値は、どこにも出さない。
- 規約: リクエスト間隔は3秒以上。短時間の大量アクセスをしない。`--fetch` の途中で止まっても、取得済みの日を飛ばして再開できる。
- ログと通知には、保有者名・会社名・銘柄名・キーを出さない（公開リポジトリのログ）。出すのは、日付・件数・例外の型名だけ。

### テスト/検証方針
- 自動テスト: `.venv/bin/python -m pytest tests/test_edinet.py tests/test_inflection_live.py tests/test_inflection_historical.py tests/test_inflection_learning.py -q`（対象）、最後に `.venv/bin/python -m pytest tests/ -q`。`ruff check src scripts tests`、CI と同じ対象の `mypy --ignore-missing-imports`。
- 受入条件のテストが、実装の誤りを検出できることを、一時的にバグを入れて確認する（例: 60日の境界を `<=` から `<` にする、`cutoff` を無視する、取り下げを数える、欠損を0件にする）。
- 手動確認観点: `--probe` の出力に個人名・会社名が出ないこと。実 API での確認の結果の記録。

### リスクと対策
1. リスク: 大量保有報告で発行会社を特定できず、対応づけが誤る → 対策: 関門（`--probe`）で実際の API の項目の意味を確認してから、Phase B に進む。確認できなければ、実装を止めて報告する。
2. リスク: scan の取得が遅く、job のタイムアウトや、日次 scan の完了時刻の遅れにつながる → 対策: 取得の上限時間を設け、超えたら打ち切って `None` にする。所要時間を、関門で測る。
3. リスク: EDINET の利用規約（短時間の大量アクセス）に触れ、API が停止される → 対策: リクエスト間隔は3秒以上、再試行の待ち時間を長くする、過去の取得は手元で1回だけ実行する。
4. リスク: API キーが公開ログや Git に漏れる → 対策: キーを例外・ログに出さない。`.env` と GitHub Secrets だけに置く。テストで、例外のメッセージにキーが含まれないことを確認する。
5. リスク: 提出日時の扱い（タイムゾーン、提出時刻と書類一覧の日付のずれ）で、先読みが起きる → 対策: `submitDateTime` を JST で比較し、`cutoff`（16:40 JST）以下だけを数える。境界のテストを追加する。書類一覧の日付と `submitDateTime` が異なる日付になりうる点を、関門で確認する。
5b. リスク: 後日取得した一覧では、取下げ後に消去された提出を復元できず、過去の件数が実際より少なくなる（過去検証の point-in-time が崩れる） → 対策: 日ごとのキャッシュに `captured_at` と `erased_records` を保存し、**`captured_at` ≥ `cutoff` かつ消去記録なし**の日だけを判定に使い（取得後の追加提出・取下げを反映できないキャッシュは使わない）、復元不能な日を窓に含む判定日は、0件にせず `None` にする。取得は、評価したい期間より後に1回実行すれば、その期間の判定は条件を満たす。ライブ scan は実行時点の状態を使うので影響を受けない。復元不能な日の割合を、関門で測り、高い場合は REQ-061 の範囲を判断を仰ぐ。将来の過去検証のために、ライブ scan の取得結果（当時の状態）を残す方式は、本計画の対象外とする（必要になれば別の要件にする）。
6. リスク: 日次 scan の snapshot の `features` に新しい項目が増えても、読む側を壊す → 対策: 追加のキーだけで、既存のキーは変えない。既存の loader のテストで、項目がある場合とない場合の両方を確認する。

### 完了条件
- [ ] REQ-059 の受入条件 1〜6 が、テストと実 API での確認で確認されている（6 は、API キーの用意後）
- [ ] REQ-060 の受入条件 1〜6 が、テストで確認されている（関門を通過した場合）
- [ ] REQ-061 の受入条件 3・4（learning への接続）が、テストで確認されている。受入条件 1・2（過去検証への適用）は、関門の判断により見送り（ライブの記録の蓄積後に再検討）
- [ ] スコア、分類、`candidates`、`classification_counts` が変わらない
- [ ] `STRATEGY_VERSION`（v3）と `REPORT_SCHEMA_VERSION`（5）が変わっていない
- [ ] ruff、mypy（CI の対象に新しいファイルを追加）、`pytest tests/ -q` が PASS（カバレッジ 80% 以上）
- [ ] API キーが、ログ・メモ・Git・テストの出力に含まれていない
