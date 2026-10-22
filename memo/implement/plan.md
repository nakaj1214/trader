## 実装計画: 一次選別の測定と評価の接続（REQ-001〜003）

> 入力: [proposal.md](proposal.md)。前の plan.md（Stage 4C）は上書きした。内容は git 履歴に残る。
> 順序は REQ-001 → REQ-002 → REQ-003。前のステップの検証が終わってから次へ進む。同時に直さない。

### 目的
「爆発的に伸びる株を初期に見つける」理念に対し、今の一次選別が何を取り、何を取りこぼすかを、既存のローカル日足キャッシュだけで測れるようにする（REQ-001）。あわせて、historical で評価されていない OVEREXTENDED（REQ-002）と、forward で読まれていない CONTROL（REQ-003）を評価に接続する。**スコア・閾値・重み・分類基準は変えない**。

### スコープ
- 含むもの: 急騰イベントの定義と段階別到達の測定、historical への OVEREXTENDED 群の追加、forward への control 群の追加（別経路）。
- 含まないもの: proposal の「保留中」の全項目（重み・閾値の見直し、信用残の取得、約定モデル、試行台帳、PSY など）。合否判定の数値（「初期」の許容値・通知上限）。`inflection_learning.py` への CONTROL 接続。
- 追記（2026-10-22）: 当初はスコープ外とした forward 側の OVEREXTENDED 群は、M2（除外判断の妥当性）を本番の蓄積データで測るために必要と判断し、群ループへ追加した（portfolio・recall・hash は不変）。

### 確認した現状（調査結果）
- `select_and_evaluate`（[inflection_live.py:660](../../src/screening/inflection_live.py#L660)）の一次選別（流動性 → `_pre_score` 順位）は関数の内側の局所変数で、順位を外に出していない。段階別の判定には抽出が要る（Step 1）。
- historical は `reconstruct_scan` → `collect_signals` → `_lag_report` の流れで、群は `GROUPS`（[:376](../../src/evaluation/inflection_historical.py#L376)）を回して作る。OVEREXTENDED は `collect_signals` で signal に入るが、`_lag_report` の群ループに無く評価されない（[:733](../../src/evaluation/inflection_historical.py#L733)）。
- 評価開始日は `default_signal_start`（[:397](../../src/evaluation/inflection_historical.py#L397)）。旧 summary では 2026-02-16 から 94 日。ローカルキャッシュの日足は 2024-10-09〜2026-07-03（約 422 営業日）。
- forward の loader `load_inflection_signals`（[inflection_forward.py:40](../../src/evaluation/inflection_forward.py#L40)）は `candidates` だけを読む。snapshot の `control_sample` は schema 5 以降にある。rebuild script は観測銘柄の価格取得・価格 hash・市場別ベンチマークを `all_observations` から作る（[:206-258](../../scripts/rebuild_inflection_forward_validation.py#L206)）。
- 既存の評価機構は再利用する: 売買は `simulate_signals`、群の指標は `_build_group_report`（[inflection_report.py:334](../../src/evaluation/inflection_report.py#L334)）。新規の損益計算は書かない。
- ローカルに `SNAPSHOT_ENCRYPTION_KEY` が無く、実 snapshot は復号していない [未確認: 実 snapshot の `control_sample` の件数]。

### 影響範囲（変更/追加予定ファイル）
- `src/screening/inflection_live.py`: 一次選別の抽出（挙動不変の純リファクタ）。
- `src/evaluation/inflection_event_recall.py`（新規）: イベント抽出・段階判定・集計。
- `src/evaluation/inflection_historical.py`: `GROUPS` に OVEREXTENDED を追加。`build_backtest_report` に `event_recall` キーを追加（追加のみ）。
- `scripts/run_inflection_historical_backtest.py`: 例示銘柄の指定オプション（既定は空）。
- `src/evaluation/inflection_forward.py`: control 用の別 loader を追加。
- `scripts/rebuild_inflection_forward_validation.py`: control 群の評価を追加（別キー）。
- テスト: `tests/test_inflection_live.py`（抽出の同値性）、`tests/test_inflection_event_recall.py`（新規）、`tests/test_inflection_historical.py`、`tests/test_inflection_forward.py`、必要なら `tests/test_run_historical_backtest.py`。
- `memo/project-overview.md`: 評価節に新しい出力キーを 1 段落で追記。

### 実装ステップ

#### Step 1: 一次選別の抽出（REQ-001 の前提・挙動不変）
- [ ] `select_and_evaluate` の「技術特徴 → 流動性 → pre_score 順位」の部分を関数に切り出し、順位つきの流動性通過リストと `technical_usable`・業種別リターンを返す。`select_and_evaluate` はそれを呼ぶだけにする。
- [ ] 引数・戻り値・並び順（同点の扱いを含む）を変えない。
**検証**: 既存の `tests/test_inflection_live.py` が無修正で通る。切り出す前後で同じ合成データの `Selection` が一致する同値性テストを 1 件追加する。

#### Step 2: 急騰イベントの抽出（REQ-001）
- [ ] 新規 `inflection_event_recall.py` に、終値の系列からイベントを返す純関数を作る。定義は proposal の確定どおり（直前 120 営業日の最安終値の 2 倍以上になった最初の日を成立日、窓の最安終値の日を底（同値は最も早い日）、底から 120 営業日は同一銘柄の新イベントを作らない、初期は底から終値 +50% 到達日の前日まで）。
- [ ] 入力は `data.panel.evaluation_histories()` の Close（split 調整済み）。
**検証**: 合成系列のテストで、(a) 2 倍に届かない系列はイベントなし、(b) 長く続く上昇は 1 件、(c) +50% 到達日当日は初期に含めない、(d) 底の同値は最も早い日、(e) 将来の値を変えても過去日の判定が変わらない。

#### Step 3: 段階別到達と集計（REQ-001）
- [ ] 日ごとに Step 1 の関数で、価格あり → 流動性通過 → 上位 25 を判定し、イベントごとに「初めて各段階に入った日」「その日の底からの上昇倍率」「+50% 到達日との前後」を記録する。日足が 21 本未満の日は評価しない。`near_52w_high` が効かない期間（上場済み・新規とも 252 本未満）は `high_bonus_available=false` を付ける。
- [ ] EARLY/WATCH の段階は `collect_signals` の signal から取る。底が `default_signal_start` より前のイベントは「未評価」とし、検出にも未検出にも数えず別の件数で出す。
- [ ] 損益は、各段階の初到達日を signal として既存の `simulate_signals`（保有 60 営業日、通常コスト、次の始値で entry）に渡す。1 日あたりの通知件数（EARLY+WATCH）も集計する。
- [ ] 出力に、価格が J-Quants の分割調整済み終値で本番（yfinance の Adj Close）と異なること、変形 B（60 本判定）は比較資料であり現行ロジック（252 本必須）を変えていないことを注記する。
**検証**: 合成データで「100→149 まで上がってから WATCH → 翌日 150」が、検出済み・上昇倍率 1.49 として記録される。観測一覧に無い急騰銘柄が分母に入る。底が開始日より前のイベントが「未評価」になる。既存の `tracked_pool_explosion_recall` と `tests/test_inflection_recall.py` は無修正。

#### Step 4: レポートへの統合と CLI（REQ-001）
- [ ] `build_backtest_report` に `event_recall` キーを追加する（価格だけの段階は lag に依らず 1 回、EARLY/WATCH の段階は lag ごと）。既存キーは変えない。`summary_report`・`_summary_only` が新キーを落とさず、イベント行の全件は full 出力だけに入るようにする。
- [ ] CLI に `--event-focus`（銘柄のカンマ区切り、既定は空）を足し、指定銘柄のイベントの段階別到達日を summary に出す。
**検証**: `tests/test_run_historical_backtest.py` の既存ケースが通り、`event_recall` が summary に入る。

#### Step 5: 実キャッシュでの確認（REQ-001・手動）
- [ ] 実キャッシュ（読み取りのみ）で `--event-focus` に例示 8 銘柄を指定して実行し、結果を `.harness/reports/` に記録する。外部 API・暗号化 snapshot は使わない。
- [ ] 試作（`.harness/reports/trader-gap-verification-claude/analysis/funnel_variantB.json`）と比べ、食い違う到達日は一致させず、理由（高値加点の判定本数・調整価格の差）を記録する。
**検証**: 実行が終了コード 0 で完了し、ピークメモリと所要時間を記録する（旧 historical は約 1.1GB）。

#### Step 6: OVEREXTENDED 群を historical に追加（REQ-002）
- [ ] `GROUPS` に `"OVEREXTENDED"` を足す（群キーは `overextended`）。
- [ ] 既存テストの群キー集合の期待値（[test_inflection_historical.py:845](../../tests/test_inflection_historical.py#L845)）は、意図した追加として更新する（他は書き換えない）。
**検証**: 群ごとの signal_count の合計が signal 総数と一致するテストを追加する。既存 4 群の数値が変わらないことを同じ合成データで確認する。OVEREXTENDED が `overextended` 群に入るテストを追加する。

#### Step 7: CONTROL を forward 評価に別経路で接続（REQ-003）
- [ ] `inflection_forward.py` に、`control_sample` を読む別 loader を追加する（復号・メタデータ・schema の検証は既存と同じ基準。schema 5 未満など `control_sample` が無い snapshot は空を返し、エラーにしない）。既存 loader の戻り値・挙動は変えない。
- [ ] rebuild script で control 群を `groups["control"]` として別キーで評価する。`all_observations` には混ぜない（recall・portfolio の入力を変えない）。
- [ ] 価格取得の対象に control の銘柄を加える。**価格 hash の `starts` は、既存どおり `all_observations` だけから計算し、control だけの銘柄の分は別に足す**（候補にも control にも出る銘柄の起点が動くと、保存済みの hash の窓がずれて改ざん検知が壊れるため）。
- [ ] `ticker_markets` と市場別ベンチマークも control の行で補う。
**検証**: fake の snapshot で、control 群が candidate 群と同じ entry/exit 規則で計算される。`control_sample` の無い旧 schema では群が空でエラーにならない。既存群と既存の price hash の値が、control を足す前後で一致する。`tests/test_inflection_forward.py` の既存ケースは無修正で通る。

#### Step 8: 文書と最終確認
- [ ] `memo/project-overview.md` の評価節に、`event_recall`・`overextended` 群・`control` 群を各 1〜2 行で追記する。
- [ ] 下記のテスト/検証方針を実行する。

### 例外・エラーハンドリング方針
- 入力が足りないときは推測で埋めない。日足が不足する日・価格のない銘柄は段階判定から外し、件数を別に出す（`excluded_no_price` と同じ考え方）。
- control の復号失敗・不正な行は既存と同じく fail closed（`SnapshotLoadError`）。`control_sample` が無いだけなら空として扱う。
- 分類基準・スコアの数値を変えない。既存の出力キーを削除・改名しない。

### テスト/検証方針
- 自動テスト（対象を絞る。全体は最後に 1 回）:
  - `.venv/bin/python -m pytest tests/test_inflection_live.py tests/test_inflection_event_recall.py tests/test_inflection_recall.py tests/test_inflection_historical.py tests/test_run_historical_backtest.py tests/test_inflection_forward.py -q`
  - `.venv/bin/ruff check src scripts tests`、現行経路の mypy（`.github/workflows/test.yml` の設定どおり）
- 手動確認観点: Step 5 の実キャッシュ実行（外部通信なし）で、例示 8 銘柄の到達日と、イベント件数（2 倍イベント 927 件前後）が試作と大きく矛盾しないこと。矛盾する場合は定義の差を記録する。
- 既存の snapshot・`artifacts/`・`.data/`・archive は書き換えない。

### リスクと対策
1. リスク: 約 400 日 × 約 4,400 銘柄の価格だけの段階判定が重い（旧 historical は 94 日 × 2 lag で約 1.1GB）→ 対策: 日足から日ごとにフレームを作る既存の `frames_as_of` を使い、価格だけの段階は lag に依らず 1 回にする。実測値を Step 5 で記録し、重すぎれば期間を絞るオプションを足す。
2. リスク: 抽出（Step 1）で並び順や同点の扱いが変わり、本番の候補が変わる → 対策: 同値性テストと既存テスト無修正を必須にする。差が出たら抽出をやめ、新モジュール側で同じ式を呼ぶ形に切り替える。
3. リスク: control の銘柄を価格取得・hash に足すことで、保存済み hash の窓が動く、または yfinance の取得件数が増えて forward workflow が遅くなる → 対策: 既存銘柄の `starts` は `all_observations` だけから計算する（Step 7）。取得件数の増加（1 日 25 銘柄 × snapshot 日数）を実行前に見積もり、`forward_validation.yml` のタイムアウト内か確認する [未確認]。
4. リスク: イベント定義（2 倍・120 営業日・底・重複）の細部で件数が大きく変わる → 対策: 定義は proposal で確定済み。パラメータは定数で 1 か所に置き、レポートの `definition` に出力する。
5. リスク: キャッシュが約 1.7 年で、52 週高値の加点が効かない期間が長い → 対策: `high_bonus_available` で区別して出し、結論に混ぜない。

### 完了条件
- [ ] REQ-001: 受入条件 1〜5 を満たす（合成データのテストと、実キャッシュでの例示 8 銘柄の出力）。
- [ ] REQ-002: historical レポートに `overextended` 群が出て、群の件数の合計が signal 総数と一致し、既存 4 群の数値が不変。
- [ ] REQ-003: forward レポートに `control` 群が別キーで出て、既存群と価格 hash の値が不変。旧 schema でエラーにならない。
- [ ] 対象テストと ruff・mypy が通る。スコア・閾値・分類基準の差分がない（`git diff` で確認）。
