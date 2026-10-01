## 実装計画: snapshot schema 5（生特徴量の保存＋対照群）— REQ-037 / REQ-038

> 入力: [proposal.md](proposal.md)
> 以前の plan.md（価格取得の再試行、実装済み）は [plan_price_retry.md](plan_price_retry.md) に移した。

### 目的
日次 scan の snapshot に、学習で必要な生特徴量・スコア内訳・開示日・業種（REQ-037）と、流動性フィルタ通過銘柄からの無作為な対照群（REQ-038）を保存する。スコア計算・分類・候補選定は変えず、v3 の蓄積データはそのまま評価に使い続ける。

### スコープ
- 含むもの:
  - `REPORT_SCHEMA_VERSION` を 4 → 5 に変更（`STRATEGY_VERSION` は v3 のまま）
  - candidate への `features`、`score_details`、`pre_score`、`sector33_code`、`sector33_name` の追加
  - report への `control_sample`、`control_sample_size`、`control_sample_seed` の追加、`scan_parameters.control_sample_size` の追加
  - forward loader（schema 4/5 の混在を許可）、learning loader（schema 5 の受け入れと新フィールドの読み込み）、`validate_report`（schema 5 の検査）の対応
  - 上記のテスト
- 含まないもの:
  - 対照群を使った学習・評価（learning のベースライン、forward の control グループ）
  - 新しい特徴量（最大日次リターンなど）の追加
  - スコア計算・分類の変更
  - workflow の変更（実行時間は直近 11.5〜15.3 分。最悪でも約31分で、45分の制限内）

### 影響範囲（変更/追加予定ファイル）
- `src/screening/inflection_live.py`: schema 5 の出力、candidate の評価処理の関数化、対照群の抽出
- `src/evaluation/inflection_forward.py`: schema 互換グループ {4, 5} の導入
- `src/evaluation/inflection_learning.py`: `SUPPORTED_SCHEMA_VERSIONS` に 5 を追加、新フィールドの検査と読み込み
- `scripts/run_inflection_shadow.py`: `validate_report` に schema 5 の検査を追加
- `tests/test_inflection_live.py`、`tests/test_inflection_forward.py`、`tests/test_inflection_learning.py`、`tests/test_shadow_health.py`: 既存アサーションの更新とテストの追加

### 実装ステップ

#### Step 1: candidate の評価処理を関数化する（挙動は変えない）
- [ ] **最初に**、受入条件 3b の期待値（Step 7 の forward テストの項）を、変更前のコードで固定する
- [ ] `scan_japan_inflection` のループ本体（[inflection_live.py:441-496](../../src/screening/inflection_live.py#L441-L496)）を、`_evaluate_candidate(ticker, tech, pre_score, *, client, ticker_meta, fundamental_limitation) -> LiveCandidate` に切り出す
- [ ] `preselected` を切り詰める前の一覧（流動性フィルタを通過した全銘柄の `(pre_score, ticker, tech)`）を `liquid` として残す
**検証**: この段階で `pytest tests/test_inflection_live.py` が無変更のまま PASS する（純粋なリファクタリング）

#### Step 2: REQ-037 — candidate に生特徴量などを追加する
- [ ] `LiveCandidate` に次のフィールドを追加する: `features: dict[str, Any]`、`score_details: dict[str, float]`、`pre_score: float`、`sector33_code: str | None`、`sector33_name: str | None`
- [ ] `features` のキーは次の8つに固定する: `revenue_growth_yoy_pct`、`operating_profit_growth_yoy_pct`、`operating_margin_change_pctpt`、`turned_profitable`、`upward_revision_pct`、`negative_operating_cashflow`、`latest_actual_disclosure_date`、`latest_disclosure_date`。`_fundamental_features()` の戻り値から取り、欠けている場合は数値と日付を `None`、真偽値を `False` にする（モジュール定数 `FEATURE_KEYS` で一覧化する）
- [ ] `score_details` = `raw.details` ＋ `{"fundamental": raw.fundamental, "momentum": raw.momentum, "risk_penalty": raw.risk_penalty}`
- [ ] `sector33_code` / `sector33_name` は master 行の `S33` / `S33Nm` から取る。空文字や欠損は `None` にする
- [ ] `REPORT_SCHEMA_VERSION = 5`
**検証**: fake client を使った scan で、candidate の `features` が `_fundamental_features()` と一致する。財務がない場合でも8キーがそろう

#### Step 3: REQ-038 — 対照群を抽出して保存する
- [ ] モジュール定数 `DEFAULT_CONTROL_SAMPLE_SIZE = 25` を置き、`scan_japan_inflection(..., control_sample_size: int = DEFAULT_CONTROL_SAMPLE_SIZE)` を追加する。`0` を許可し（負数は `ValueError`）、0 のときは抽出も財務取得も行わず `control_sample=[]` とする
- [ ] seed = `int.from_bytes(hashlib.sha256(expected_date.encode()).digest()[:8], "big")`
- [ ] `random.Random(seed).sample(sorted(liquid の ticker), k=min(control_sample_size, len(liquid)))` で抽出する。ticker をソートしてから抽出するのは、`prices` の dict の順序に結果が依存しないようにするため
- [ ] deep 側で評価済みの ticker は、`dict[str, LiveCandidate]` のキャッシュから再利用し、J-Quants を再度呼ばない
- [ ] report に `control_sample`（`as_dict()` の list、ticker 順）、`control_sample_size`（要求数）、`control_sample_seed` を追加し、`scan_parameters["control_sample_size"]` を追加する
- [ ] `candidates`、`deep_candidate_count`、`classification_counts` の計算は deep 側だけで行う（対照群を混ぜない）
**検証**: 同じ入力での2回の scan で `control_sample` が一致する。重複銘柄の `financial_summary` 呼び出しが1回になる

#### Step 4: forward loader の schema 互換性
- [ ] [inflection_forward.py](../../src/evaluation/inflection_forward.py) に `COMPATIBLE_SCHEMA_GROUPS = ({4, 5},)` を置き、`_schema_family(version) -> frozenset[int]`（グループに属すればそのグループ、属さなければ `{version}`）で比較する
- [ ] 混在の判定を `schema_version != expected_schema_version` から「family が異なる」に変える。strategy_version の不一致は従来どおり拒否する
- [ ] signal の `report_schema_version` には、各 snapshot の実際の値を入れる（従来どおり）
**検証**: 既存の `test_load_inflection_signals_rejects_mixed_versions`（strategy の不一致、schema 3↔4）は変更なしで PASS する。新規テストで 4↔5 の混在が成功する

#### Step 5: learning loader の schema 5 対応
- [ ] `CURRENT_SCHEMA_VERSION = 5`、`SUPPORTED_SCHEMA_VERSIONS = (3, 4, 5)` とし、`near_*` の bool 検査を schema 4 と 5 に適用する
- [ ] schema 5 では、`features` と `score_details` が dict、`pre_score` が **bool を除く有限の数値**（`isinstance(x, (int, float)) and not isinstance(x, bool) and isfinite(x)`）であることを検査し、違反時は `SnapshotLoadError`。Step 6 の保存前検査と同じ条件にする
- [ ] observation に `features`、`score_details`、`pre_score`、`sector33_code` を追加する（schema 3/4 では `None`）
- [ ] `control_sample` は読み込まない（スコープ外）
- [ ] `factor_labels` と集計は変更しない
**検証**: schema 3/4/5 の混在ディレクトリを読み込める。schema 5 の不正な `features` を拒否する

#### Step 6: validate_report の schema 5 検査
- [ ] `report_schema_version >= 5` のとき、**candidates と control_sample の両方の全行**について、次を同じ関数（`_validate_schema5_row`）で検査する:
  - 行が dict である
  - `ticker` が非空の文字列である
  - `features` と `score_details` が dict である
  - `pre_score` が bool を除く有限の数値である（NaN と inf は拒否。Step 5 の learning 側と同じ条件）
- [ ] 加えて、`control_sample` が list で、件数が `min(control_sample_size, liquid_candidate_count)` と一致し、ticker の重複がないことを検査する
- [ ] 違反時は `RuntimeError("DATA_HEALTH: ...")`
- [ ] schema 4 の report（既存の `_healthy_report`）は従来どおり通す
**検証**: `tests/test_shadow_health.py` で、正常な schema 5 report が通ることを確認する。また、次のそれぞれが拒否されることを確認する:
- candidate の `features` の欠落
- `pre_score` が `NaN` / `inf` / `True`
- control_sample の不正な行（`features=None`、`score_details` の欠落、`pre_score` の欠落、空の ticker）
- 件数の不一致
- ticker の重複

#### Step 7: テストの更新・追加
- [ ] `test_inflection_live.py`: `REPORT_SCHEMA_VERSION == 4` → `5` に変更
- [ ] `test_inflection_live.py`: `deep_candidates=0` で財務取得を避けている既存の scan 呼び出し**すべて**（現時点で L279、L316、L346、L381、L416）に `control_sample_size=0` を追加する。対象には `test_scan_retries_only_stale_tickers_and_recovers`、`test_scan_retries_missing_tickers_when_price_coverage_is_low`、`test_scan_recovers_on_second_retry` を含む。これを行わないと、既定の対照群が `FakeJQuantsClient.financial_summary` の `code == "11110"` という assert に当たり、既存テストが失敗する
- [ ] `test_inflection_live.py`: REQ-037 の受入条件 1・2、REQ-038 の受入条件 1〜4 のテストを追加する。対照群のテストでは、複数銘柄に対応し呼び出し回数を数える fake client（`MultiCodeFakeClient`）を新しく作って使う。`control_sample_size=0` のときに財務取得の回数が増えないこと（deep 側の分だけであること）も確認する
- [ ] `test_inflection_forward.py`: 4↔5 の混在が成功するテスト
- [ ] `test_inflection_forward.py`: **受入条件 3b**。実装に手を付ける前に、既存の `test_load_inflection_signals_accepts_v3_schema4_snapshot` を拡張し、固定の schema 4 入力に対して**現在の（変更前の）loader が返す signal の list 全体**を、リテラルの期待値として書き込む。この期待値をコミット前の現行コードで PASS させて固定する。その後の変更で、単独読み込みと schema 5 との混在読み込みの両方が、この期待値と一致することを確認する
- [ ] `test_inflection_learning.py`: `test_loader_rejects_unsupported_schema` の parametrize から `5` を除き `6` を加える。schema 5 の読み込み、不正な `features` の拒否のテストを追加する
- [ ] `test_shadow_health.py`: Step 6 のテスト
**検証**: `.venv/bin/python -m pytest tests/ -q`、`ruff check src scripts tests`、test.yml の mypy 対象がすべて PASS する

### 例外・エラーハンドリング方針
- 書き込み側（scan）: 財務の欠損は `None` / `False` で埋め、エラーにしない（従来の欠損時の挙動と同じ）。J-Quants の通信エラーは従来どおり scan を失敗させる（対照群の取得だけを黙って省くことはしない。部分的に欠けた snapshot を残さないため）
- 保存前（`validate_report`）: schema 5 の構造違反は `DATA_HEALTH` で fail closed にし、snapshot を書かない
- 読み込み側（forward / learning）: 構造違反は従来どおり `SnapshotLoadError` で fail closed にする

### テスト/検証方針
- 自動テスト: `.venv/bin/python -m pytest tests/ -q`、`.venv/bin/ruff check src scripts tests`、`.venv/bin/mypy --ignore-missing-imports <test.yml の対象>`
- 手動確認観点:
  - [ ] マージ後の最初の日次 scan が成功し、`dashboard/data/inflection/v3/` に新しい snapshot が追加される（GitHub Actions のログで `snapshot_created=True` を確認）
  - [ ] 実行時間が 45 分以内で、増分が約5分である
  - [ ] 直後の週次 forward validation（schedule 実行）が、schema 4/5 の混在で成功する
  - [ ] 【任意・鍵が必要】ローカルで最新の snapshot を復号し、`features` と `control_sample` が入っていることを確認する

### リスクと対策
1. リスク: 実データで master の `S33` が想定外の形式（数値型など）で返る → 対策: `str()` で文字列にし、空なら `None` とする。`validate_report` では業種を必須にしない
2. リスク: 対照群の J-Quants 呼び出しでレート制限（429）に当たり、scan 全体が失敗する → 対策: 既存の `min_interval=12.2s` と再試行を使う。初回の本番実行後に失敗が出たら、`control_sample_size` を下げて対応する（定数1か所の変更）
3. リスク: forward の schema 互換を緩めることで、本当に非互換な schema が混入する → 対策: 互換グループを {4, 5} に明示的に限定し、3↔4 の拒否テストは維持する。今後 schema を上げるときは、互換かどうかをこの定数で明示的に判断する
4. リスク: マージから最初の scan までの間に schema 4 と 5 の手動実行が交ざる → 対策: 同じ日の snapshot は上書きしない既存仕様のままで問題ない（どちらも読める）

### 完了条件
- [ ] REQ-037 の受入条件 1〜6（3b を含む）を満たすテストが PASS する
- [ ] REQ-038 の受入条件 1〜6 を満たすテストが PASS する
- [ ] `pytest`、`ruff`、`mypy` がすべて PASS する
- [ ] `STRATEGY_VERSION` が `jp-inflection-shadow-v3` のまま、保存先が `dashboard/data/inflection/v3/` のままである
