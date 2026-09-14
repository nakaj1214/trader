# 実装計画: REQ-036 — 自己改善学習（Inflection Self-Learning Postmortem）の移植

> 入力: `memo/implement/proposal.md` の REQ-036 のみを対象とする。
> 移植元: `origin/feat/self-learning-postmortem`（2026-09-08にmainから分岐、2026-09-09で開発停止、未マージ）。
> 単純な`git merge`/`cherry-pick`は使わない。分岐後にmain側がREQ-018（v3 snapshot分離、`near_52w_high`/`near_listing_high`分割）・REQ-014（ポートフォリオ評価追加）を独立に実装しており、双方の差分が大きい。

## 前提: 依存関数の存在確認（コードで確認済み）

移植元コード（`src/evaluation/inflection_learning.py`）が使う関数・定数は、現行mainに互換シグネチャで存在する。

| 依存 | 現行mainでの場所 | 状態 |
|---|---|---|
| `simulate_signal` | `src/evaluation/inflection_backtest.py:72` | 存在（シグネチャ互換） |
| `BENCHMARK_TICKER` | `src/evaluation/inflection_forward.py:19` | 存在（`"1306.T"`） |
| `paired_benchmark_returns` | `src/evaluation/inflection_forward.py:163` | 存在（**レビュー指摘によりこちらを採用**。移植元が使う`benchmark_returns_by_signal_date`は不採用、理由は実装ステップ1参照） |
| `SnapshotLoadError` | `src/evaluation/inflection_forward.py:22` | 存在 |
| `decrypt_json` | `src/data/snapshot_crypto.py` | 存在（`load_inflection_signals`が同じ関数を使用、`inflection_forward.py:1`付近でimport済み） |

したがって移植は「アルゴリズム自体の書き直し」ではなく、**現行mainのsnapshotスキーマに合わせた読み込み層の書き換え**が主作業になる。

## 現状（Before）の正確な把握

1. **`candidate.breakout_52w`は現行mainに存在しない。** 移植元の`factor_labels()`は`observation.get('breakout_52w')`を参照するが、現行mainの`LiveCandidate`（`src/screening/inflection_live.py:38-51`）はREQ-018で`near_52w_high`（新規上場銘柄以外の52週高値近接）と`near_listing_high`（**（レビュー指摘・3回目で訂正）** 252営業日未満（52週分の価格履歴が無い、`src/screening/inflection_live.py:101-102`の`len(close) < 252`が実際の条件）の上場来高値近接）に分割済みで、`breakout_52w`フィールドは存在しない。両フィールドともsnapshotの`candidates`配列に含まれている。
2. **snapshot保存先がv2/v3で分離されている。** `run_inflection_shadow.py:15`の`OUT_DIR`は`dashboard/data/inflection/v3`だが、**実際にはまだv3ディレクトリは1件も存在しない**（`ls dashboard/data/inflection/v3/` → No such file or directory を確認済み）。現状の`dashboard/data/inflection/`直下には`2026-09-09.enc`〜`2026-09-11.enc`の3件がありこれらはv2（REQ-018適用前）のsnapshotである。`rebuild_inflection_forward_validation.py:380`は`--snapshot-dir`の既定値を`dashboard/data/inflection/v3`にしており、v2は評価対象に含めていない（v2/v3非連続の既定方針、REQ-018のスコープ判断で確定済み）。
3. **CI配線が未確定。** `.github/workflows/forward_validation.yml`は`schedule`（毎週日曜09:30 JST）と対象pathへのPRで動く。移植元ブランチには専用workflowが無く、`scripts/rebuild_inflection_learning.py`は単体のCLIスクリプトとして存在するのみだった。
4. **`load_inflection_signals`（`inflection_forward.py:27-116`）の検証ロジックとフィールド抽出範囲。** **（レビュー指摘で訂正）** 当初「現行forward validationはEARLY_CANDIDATEのみを読む」と誤って記述していたが、実際は`rebuild_inflection_forward_validation.py:395`で`classifications=("EARLY_CANDIDATE", "WATCH", "NONE", "OVEREXTENDED")`を渡しており、**全区分を既に読んでいる**。独立loaderが必要な本当の理由は次の2点である。
   - `load_inflection_signals`が返す行は`ticker`/`score`/`classification`/`market`/`avg_turnover_20d_jpy`等に限られ、学習に必要な`raw_inflection_score`/`return_5d/20/60d_pct`/`volume_ratio_20d`/`near_52w_high`/`near_listing_high`/`reasons`を含まない。
   - `load_inflection_signals`は`strategy_version`/`schema_version`が1種類だけであることを強制する（`"Mixed strategy/schema versions"`で拒否）が、学習は`build_learning_report()`が複数`strategy_version`を横断して累積学習する設計（移植元コミット「Keep learning cumulative across strategy versions」）であり、単一バージョン強制はそのまま流用できない。
   - 一方で`load_inflection_signals`が行っている**それ以外の検証**（`source_commit_sha`必須、`storage.encrypted is True`、`storage.snapshot_date_basis == "latest_price_date"`、scoreの`isfinite`かつ`0.0 <= score <= 100.0`）は学習loaderにも同等に必要である。移植元の`load_learning_observations()`はこれらを検証しておらず、例えば`NaN`スコアが`_optional_float`を素通りして`_bucket()`の`score_band`で`ge85`に誤分類され、昇格統計を汚染する欠陥がある。
   - 対応方針: `inflection_forward.py`を改修して検証ロジックを共有関数に切り出すことはせず（既存の安定した本番コードへの変更・再テストコストを避けるため）、**同等の検証を`inflection_learning.py`側に複製する**。単一バージョン強制だけは意図的に行わない（複数バージョン許容が学習の設計そのものであるため）。この差分は`load_inflection_learning_observations()`のdocstringに明記する。

## スコープ判断（今回決定した既定値。着手前の要確認事項への回答）

proposal.mdのREQ-036には3つの`[要確認]`があった。移植の最小コストと既存パターンへの整合を優先し、以下を既定方針とする。ユーザーが異なる方針を希望する場合はここを修正すればよい。

1. **v2/v3混在の扱い**: forward validationと同じ方針に揃える。`load_inflection_learning_observations()`の既定`snapshot_dir`は`dashboard/data/inflection/v3`のみとし、v2は対象外とする（`rebuild_inflection_forward_validation.py`と同じ`--snapshot-dir`引数パターンを`rebuild_inflection_learning.py`にもそのまま用意する）。
2. **CI配線先**: 新規workflowファイルは作らず、**既存`forward_validation.yml`の`validate`ジョブに1ステップ追加**する。理由: 依存パッケージのセットアップ・checkoutを再利用でき、`SNAPSHOT_ENCRYPTION_KEY`等のsecrets設定も既に揃っているため。ただし学習ステップはyfinance呼び出しを伴い時間がかかるため、**`schedule`実行時のみ**実行する（PRごとの実行はしない。`if: github.event_name == 'schedule'`で分岐）。
3. **`public_learning_summary`の出力先**: 新規dashboardページは作らない。既存の`artifacts/inflection_forward_validation_summary.json`と同じ扱いで`artifacts/inflection_learning_summary.json`として`upload-artifact`する（dashboard UIへの表示はスコープ外、必要になれば別REQで扱う）。**（レビュー指摘で明確化）** フル`build_learning_report()`の結果（ticker単位の観測を含む）は別ファイル`artifacts/inflection_learning.json`としてローカルに生成するが、こちらはartifact化しない（詳細は実装ステップ2参照）。

## 変更対象

- `src/evaluation/inflection_learning.py`（新規: 移植元をベースに、`breakout_52w`依存を除去し`near_52w_high`/`near_listing_high`に対応させる）
- `scripts/rebuild_inflection_learning.py`（新規: 移植元をベースに、`--snapshot-dir`既定値を`dashboard/data/inflection/v3`にする）
- `tests/test_inflection_learning.py`（新規: 移植元のテストをベースに、現行のcandidateスキーマ（`near_52w_high`/`near_listing_high`）に合わせて書き換える）
- `.github/workflows/forward_validation.yml`（`validate`ジョブに学習ステップ追加、`schedule`時のみ実行、artifactアップロード追加）
- `memo/project-overview.md`（**レビュー指摘・3回目で追加、`変更対象`と`リスクと対策`5.の記載を一致させる**。自己改善学習の対象範囲（`report_schema_version == 4`限定、`strategy_version`は複数許容）とfail-closedの検証方針を追記する）

## 実装ステップ

### 1. `src/evaluation/inflection_learning.py`を移植する

対象: 移植元`src/evaluation/inflection_learning.py`（512行）をベースに以下を変更する。

- `load_learning_observations()`を`load_inflection_learning_observations()`にリネームし、以下を変更する。
  - `candidates`から読み取るフィールドに`near_52w_high`と`near_listing_high`を追加する（`breakout_52w`は読まない）。読み取り方の詳細は後述（レビュー指摘・2回目で型検証を追加）。
  - **（レビュー指摘で追加）** スナップショットヘッダ検証を`load_inflection_signals`と同等にする: `source_commit_sha`が非空文字列であること、`storage`が`dict`かつ`storage.get("encrypted") is True`かつ`storage.get("snapshot_date_basis") == "latest_price_date"`であることを検証し、いずれか欠けていれば`SnapshotLoadError`にする（移植元は`strategy_version`/`schema_version`/`market_date`しか検証していなかった）。
  - **（レビュー指摘・2回目で訂正）** 単一strategy versionの強制はしないが、**`report_schema_version`は`4`のみ受理し、それ以外（`None`・`1`〜`3`・`5`以上）は`SnapshotLoadError`で拒否する**（`report_schema_version != 4`）。理由: schema 3以前には`near_52w_high`/`near_listing_high`フィールド自体が存在せず、前回案の「正の整数なら無条件許可」では`bool(candidate.get(...))`が静かに`False`を返し、フィールド欠損が「両方近接していない」という有効な観測として学習に混入してしまう（誤学習）。現行`REPORT_SCHEMA_VERSION = 4`（`src/screening/inflection_live.py:32`）はv3 snapshot・`near_52w_high`/`near_listing_high`分割と対で導入されたバージョンであり、「v3ディレクトリのみ対象」という本計画のスコープ判断（`スコープ判断`1.）と`report_schema_version == 4`限定は一致する。将来schemaが変わり複数schemaを跨いだ累積学習が必要になった場合は、schema別のフィールド抽出adapterを追加してから対応範囲を広げる（今回のスコープ外）。**strategy_versionは複数許容のまま**（`build_learning_report()`の累積学習設計のため、こちらは変更しない）。
  - **（レビュー指摘で追加）** scoreの検証を`load_inflection_signals`と同等にする: `isinstance(raw_score, bool)`または`None`なら`SnapshotLoadError`、`float()`変換失敗なら`SnapshotLoadError`、`isfinite(score)`が`False`または`0.0 <= score <= 100.0`を満たさなければ`SnapshotLoadError`にする（移植元の`_optional_float`は変換失敗時に`None`を返すだけで、`NaN`はfloat変換に成功してしまうため`isfinite`チェックが必須）。
  - **（レビュー指摘・2回目で追加）** `_optional_float()`ヘルパーを、`isfinite`でない値（`NaN`・`inf`・`-inf`）を`None`へ正規化するよう修正する（`return_5d/20/60d_pct`・`volume_ratio_20d`・`avg_turnover_20d_jpy`等のoptional数値すべてに適用される共通ヘルパーのため、ここを直せば全項目に効く）。`_bucket()`は`value is None`を`"missing"`band に振り分ける既存ロジックがあるため、非finiteを`None`化するだけで最上位band誤分類を防げる。
  - **（レビュー指摘・3回目で訂正: fail-openをfail-closedに変更）** `near_52w_high`/`near_listing_high`の読み取りを`bool(candidate.get(...))`から、**厳密な`bool`型チェック＋拒否**に変更する: `raw = candidate.get("near_52w_high"); if not isinstance(raw, bool): raise SnapshotLoadError(...)`（`near_listing_high`も同様）。前回案（`isinstance`でなければ`False`にfallback）は、型検証を「拒否」ではなく「不正値を正規の`False`観測に静かに変換する」処理になっており、`report_schema_version == 4`限定で防いだはずの「フィールド欠損を`False`として学習に混入させる」問題がcandidate単位で再発していた（`None`・文字列・数値・キー欠損のいずれも`False`として学習された）。schema 4を要求している以上、両フィールドは`bool`として存在することが保証された前提であり、`bool`でなければcandidate行ではなく**snapshot全体を`SnapshotLoadError`で拒否する**（`load_inflection_signals`の他フィールド検証と同じfail-closed方針に揃える）。
- `factor_labels()`内の`"breakout_52w:true" if observation.get("breakout_52w") else "breakout_52w:false"`を、`f"near_52w_high:{bool(observation.get('near_52w_high'))}"`と`f"near_listing_high:{bool(observation.get('near_listing_high'))}"`の2ラベルに置き換える（新規上場銘柄と既存銘柄の52週/上場来高値近接を別factorとして扱えるようにする。1ラベルへ強制統合すると新規上場銘柄固有のシグナル精度が埋もれるため）。
- `_prediction_miss_reasons()`内の`if row.get("breakout_52w"):`を、**（レビュー指摘で訂正）** `near_52w_high`と`near_listing_high`で別々の理由名に分ける形に書き換える: `if row.get("near_52w_high"): reasons.append("near_52w_high_failed_to_outperform")`、`if row.get("near_listing_high"): reasons.append("near_listing_high_failed_to_outperform")`。252営業日未満（52週分）の価格履歴しかない銘柄には52週の値動き履歴自体が存在しないため、両者を`"52w_breakout_failed_to_outperform"`という1つの理由名にまとめると原因が誤って記録される。
- **（レビュー指摘で修正）** `evaluate_learning_observations()`のbenchmark比較を、`benchmark_returns_by_signal_date()`（signal_date起点の固定horizon）から`paired_benchmark_returns()`（各tradeの実際の`entry_date`/`exit_date`に合わせる、`scripts/rebuild_inflection_forward_validation.py:255-263`の`_paired_trade_rows`と同じパターン）に置き換える。個別銘柄がデータ欠損等で後日entryした場合、`signal_date`基準のbenchmark期間と実際のtrade期間がずれ、超過リターン・昇格判定が誤るため。horizonごとに`trades`のリストを作り、`paired_benchmark_returns(trades, benchmark_history, round_trip_cost_pct=round_trip_cost_pct)`を1回呼び出して`zip(trades, benchmarks, strict=True)`で対応付ける（`benchmark_returns_by_signal_date`は使わない）。
- **（レビュー指摘・2回目で修正）** `_independent_rows()`の重複排除を、`signal_date`基準から**実際の`entry_date`/`exit_date`基準**に書き換える。移植元は`if signal_date < occupied_until.get(ticker, ""): continue`（`signal_date`で判定）としているが、価格欠損等で実entryがsignal_dateより後にずれる観測がある場合、signal_date基準では誤って採用/除外される。`src/evaluation/inflection_backtest.py:255-274`の`select_non_overlapping_trades()`と同じ考え方に揃える: 各horizon outcomeの`entry_date`でソートし、`str(entry_date) <= occupied_until.get(ticker, "")`なら除外、採用したら`occupied_until[ticker] = str(exit_date)`を更新する（`exit_date`が無い＝`completed`でない観測はそもそも`_independent_rows`の対象外という既存フィルタは維持する）。
- それ以外のロジック（`_horizon_summary`、`_factor_statistics`、`_lessons`、`build_learning_report`、`public_learning_summary`）は移植元のまま流用する（`LEARNING_HORIZONS`、`EXPLOSION_MAX_RETURN_PCT`、`PROMOTION_MIN_OBSERVATIONS`等の定数も変更しない）。
- `promotion_gate.automatic_production_weight_update: False`は変更しない（本番反映しない設計を維持することが受入条件）。

検証:

- 新規テスト: `near_52w_high`/`near_listing_high`を含む合成candidateペイロードから、正しいfactor labelが生成されること。
- 新規テスト: 移植元と同じ昇格判定ロジック（`PROMOTION_MIN_OBSERVATIONS`・lift基準）が動作すること（合成データで`positive_candidate`/`negative_candidate`/`hold`の3パターンを再現する）。
- 新規テスト（レビュー指摘4への回帰）: 個別銘柄のentryがbenchmarkより遅れる合成ケース（例: 対象銘柄のデータが数日欠損しており`simulate_signal`のentry_dateがsignal_dateの翌営業日より後にずれる）で、excess returnが`entry_date`/`exit_date`基準で計算され、`signal_date`基準の値とは異なることを確認する。**同じ合成ケースで`_independent_rows()`のindependent observation数が`entry_date`/`exit_date`基準で正しくなることも確認する（2回目レビュー指摘3への回帰）。**
- 新規テスト（レビュー指摘3への回帰）: `NaN`score・`source_commit_sha`欠落・`storage.encrypted`が`False`または欠落のsnapshotが、それぞれ`SnapshotLoadError`で拒否されること。異なる`strategy_version`のsnapshotが2件（両方とも`report_schema_version == 4`）あっても拒否されず両方読み込まれること（学習はstrategy_versionの複数許容、schemaは`4`のみ）。
- 新規テスト（2回目レビュー指摘1への回帰）: `report_schema_version`が`3`（`near_52w_high`/`near_listing_high`が存在しない旧schema）・`5`（未対応の将来schema）・`None`のsnapshotが、いずれも`SnapshotLoadError`で拒否されること。
- 新規テスト（2回目レビュー指摘2への回帰）: `return_20d_pct`等に`float("nan")`/`float("inf")`/`float("-inf")`が入ったcandidateで、該当フィールドが`None`に正規化され`_bucket()`が`"missing"`bandに分類されること（最上位bandへの誤分類が起きないこと）。
- 新規テスト（**3回目レビュー指摘1への回帰、2回目時点のテスト方針を訂正**）: `near_52w_high`または`near_listing_high`に文字列`"false"`・`0`・`1`・`None`・キー欠損が入ったsnapshotが、**`False`へのfallbackではなく`SnapshotLoadError`で拒否される**こと（`bool("false") is True`という言語仕様による誤変換や、欠損の暗黙`False`化を許さないことの確認）。正しい`bool`型（`True`/`False`）が入っている場合のみ正常に読み込まれることも合わせて確認する。
- 新規テスト（レビュー指摘6への回帰）: `near_52w_high`のみ`True`の観測は`near_52w_high_failed_to_outperform`のみを、`near_listing_high`のみ`True`の観測は`near_listing_high_failed_to_outperform`のみを`prediction_miss_reasons`に含むこと。

### 2. `scripts/rebuild_inflection_learning.py`を移植する

対象: 移植元スクリプトをベースに以下を変更する。

- `argparse`に`--snapshot-dir`（既定値`dashboard/data/inflection/v3`）を追加する（`rebuild_inflection_forward_validation.py:380`と同じパターン）。
- **（レビュー指摘で出力契約を明記）** `--output`（既定値`artifacts/inflection_learning.json`。移植元の既定値を維持）でフル`build_learning_report()`の結果（ticker単位の`observations`・`postmortems`を含む）をローカルファイルへ書き出す。加えて新規に`--summary-output`（既定値`artifacts/inflection_learning_summary.json`）を追加し、`public_learning_summary(report)`の結果を別ファイルへ書き出す。**2つのファイルを両方生成する**（snapshot 0件時も同様に両方生成する）。CIワークフロー（ステップ4）は`--summary-output`のファイルだけを`upload-artifact`し、`--output`のフルレポートはephemeral runner上にのみ残す（`forward_validation.yml`の「Prediction-level trade rows remain on the ephemeral runner.」というコメント方針と揃える）。
- **（レビュー指摘で修正、2回目でさらに強化）** yfinanceバッチ取得ロジック（`_fetch_learning_histories`）は移植元をベースにするが、以下3点を`rebuild_inflection_forward_validation.py:90-124`の`_fetch_adjusted_histories`と同じ、またはそれ以上の秘匿境界に揃える。
  1. `yf.download(...)`呼び出しを`logging.getLogger("yfinance")`の`disabled`フラグでラップし、provider例外のログ出力を抑止する（移植元は抑止していなかった）。
  2. 失敗時に送出する`RuntimeError`から、tickerシンボルとprovider例外テキストを除去する。移植元の`raise RuntimeError(f"Learning price retrieval failed: {detail}")`（`detail`はticker名と例外文字列を連結したもの）を、`raise RuntimeError(f"Learning price retrieval failed for {len(failures)} ticker(s)")`という件数のみの形に変更する（`_fetch_adjusted_histories`と同じ形）。個別のticker・失敗理由はCIログ・例外メッセージへ出さない。
  3. **（2回目レビュー指摘4で追加）** `logging`のdisableだけでは、providerがticker名を直接`print()`やC拡張経由でstdout/stderrへ書くケースを防げない（`yfinance`はエラー時にloggerを経由せず直接出力することがある）。`yf.download(...)`呼び出しを`contextlib.redirect_stdout(io.StringIO())`と`contextlib.redirect_stderr(io.StringIO())`で二重に囲み、provider由来の出力を破棄する（stdlibのみで完結、新規依存なし）。この対策はロガー抑止の代替ではなく追加であり、両方を維持する。
- snapshot_dirが存在しない/`.enc`が0件の場合は例外を出さず、`observation_count: 0`の空レポートを（フル・summary両方）返す（現行`load_inflection_signals`が空ディレクトリでも空リストを返す挙動と揃える。v3ディレクトリが実際にまだ0件であるため、この分岐は導入直後に必ず通る）。

検証:

- 新規テスト: `dashboard/data/inflection/v3`が存在しない状態で実行しても例外にならず、フル・summary両方のファイルが`observation_count == 0`の内容で生成されること。
- 新規テスト（レビュー指摘1・2、および2回目レビュー指摘4への回帰）: yfinance取得が失敗するticker名や例外テキストが、送出される`RuntimeError`のメッセージ・標準出力・標準エラー・`logging`のいずれにも含まれないこと（件数のみが含まれること）を確認する。**loggerを使わず`print()`で直接tickerを標準出力へ書くfake providerをモックし、`redirect_stdout`/`redirect_stderr`によってテスト側の`capsys`/`capfd`にそのtickerが一切現れないことを確認する回帰テストを追加する（logger抑止だけでは検出できないケース）。**
- 手動確認観点（operator-run）: `python scripts/rebuild_inflection_learning.py`をローカル実行し、例外なく完了することを確認する（現状はv3 snapshotが0件のため空レポートになる想定）。

### 3. `tests/test_inflection_learning.py`を移植する

対象: 移植元のテストファイルをベースに、以下を現行スキーマに合わせて書き換える。

- fixtureペイロードの`breakout_52w`を`near_52w_high`/`near_listing_high`に置き換える。
- `tests/test_inflection_forward.py`と同じ流儀（`encrypt_json`/`decrypt_json`で合成snapshotを作り、実APIに接続しない、`SECRET = "test-snapshot-secret"`パターンを流用）に合わせる。
- 移植元のテストケース（cumulative learning across strategy upgrades、learning overlap boundary、batched price retrieval）はロジック変更がない部分なのでそのまま移植する。

検証:

- `pytest tests/test_inflection_learning.py -q`が全件成功すること。

### 4. `.github/workflows/forward_validation.yml`への配線

対象: `validate`ジョブに以下を追加する。

- 既存の`paths`トリガーに`src/evaluation/inflection_learning.py`・`scripts/rebuild_inflection_learning.py`・`tests/test_inflection_learning.py`を追加する。
- 既存の`Test forward-validation core`ステップの対象に`tests/test_inflection_learning.py`と`--cov=src.evaluation.inflection_learning`を追加する。
- 新規ステップ`Build inflection learning report`を`Validate accumulated encrypted snapshots`ステップの後に追加し、`if: github.event_name == 'schedule'`で`schedule`実行時のみ`python scripts/rebuild_inflection_learning.py`を実行する（PRごとのyfinance呼び出し増加を避ける）。**（レビュー指摘で追加）** このステップに`env: SNAPSHOT_ENCRYPTION_KEY: ${{ secrets.SNAPSHOT_ENCRYPTION_KEY }}`を明示的に設定する（GitHub Actionsの`env`はstep単位で、直前ステップの`Validate accumulated encrypted snapshots`に設定した値は後続ステップへ継承されないため。snapshotが1件でもあれば`snapshot_encryption_secret()`が鍵を要求し、未設定だと必ず失敗する）。
- 新規`upload-artifact`ステップで、**（レビュー指摘で訂正）** `--output`のフルレポート（`artifacts/inflection_learning.json`）ではなく`--summary-output`の`artifacts/inflection_learning_summary.json`だけを、既存の`inflection-forward-summary`と同様`if-no-files-found: ignore`・`retention-days: 90`でアップロードする。フルレポートはticker単位の観測を含むため、既存の「Prediction-level trade rows remain on the ephemeral runner」方針どおりartifact化しない。

検証:

- ローカルで`act`等は使わず、workflow YAMLの構文が既存パターン（`if`条件、`paths`配列の書式）と一致することを目視確認する。
- `python scripts/rebuild_inflection_learning.py`をローカル実行し、CIステップと同じコマンドが例外なく完了することを確認する。

## テスト/検証方針

- 自動テスト: `uv run pytest tests/test_inflection_learning.py -q`。移植元のテスト構成をそのまま踏襲し、現行スキーマ（`near_52w_high`/`near_listing_high`）に対応する箇所のみ書き換える。
- 既存テストへの影響確認: `uv run pytest tests/test_inflection_forward.py tests/test_inflection_strategy.py -q`で既存のforward validation・戦略ロジックに副作用がないことを確認する（`load_inflection_learning_observations`は独立関数として新規追加するため、既存`load_inflection_signals`は変更しない）。
- 手動確認観点（operator-run）: `python scripts/rebuild_inflection_learning.py`をローカル実行し、`artifacts/inflection_learning_summary.json`が例外なく出力されること（現状`observation_count`は0または極小になる想定。v3 snapshotがまだ蓄積されていないため）。

## リスクと対策

1. リスク: `near_52w_high`/`near_listing_high`への分割により、移植元の単一`breakout_52w`ラベルより粒度が細かくなり、`PROMOTION_MIN_OBSERVATIONS`（30件）に達するまでの期間が長くなる → 対策: これは既知の制約としてレポートの`limitations`に追記する（移植元も「small-sample overfitting防止のためmin observationsを設けている」という設計思想なので、粒度が増えること自体は方針と矛盾しない）。
2. リスク: v3 snapshotが現状0件のため、導入直後は学習レポートが空になり効果が確認しづらい → 対策: バグではなくデータ蓄積待ちであることを明記し、単体テストで「0件でも例外にならない」ことを保証する（REQ-014・REQ-017/020と同じ既知パターン）。
3. リスク: `forward_validation.yml`の`schedule`実行時間が学習ステップの追加でCI予算（`timeout-minutes: 30`）を圧迫する → 対策: yfinanceバッチ取得は移植元の`LEARNING_PRICE_BATCH_SIZE=50`をそのまま使い新規のAPI呼び出しパターンを増やさない。導入後に実測し、有意に超過する場合は別workflow・別timeout予算への分離を検討する。
4. リスク: `load_inflection_learning_observations()`と既存`load_inflection_signals()`のロジックが将来乖離し、片方だけ修正されるリスク（例: 将来の新フィールド追加時に一方だけ更新される） → 対策: 両関数のdocstringに互いを参照する形で「candidateスキーマが変わった場合は両方確認すること」を明記する（共通化は今回のスコープ外。読み込み対象範囲が異なる独立関数のままにする理由は「現状（Before）の把握」4.参照）。
5. リスク: `report_schema_version == 4`限定により、将来schema 5以降が出た際に学習が新schemaのsnapshotを一切読めなくなる（拒否され続ける） → 対策: これは意図した挙動（fail-closed）であり、schema 5対応時にadapterを追加してから対象を広げる設計とする。schema更新のたびに本モジュールの対応も見直す必要があることをdocstringと`memo/project-overview.md`に明記する。

## 完了条件

- [ ] `src/evaluation/inflection_learning.py`が現行mainのcandidateスキーマ（`near_52w_high`/`near_listing_high`、`breakout_52w`は参照しない）から観測を読み込み、`build_learning_report()`が例外なく学習レポートを生成する
- [ ] 昇格候補（`lessons`）が本番の`score_inflection()`等へ自動反映されないこと（`automatic_production_weight_update: False`が維持されること）をテストで保証する
- [ ] `scripts/rebuild_inflection_learning.py`が`--snapshot-dir`既定値`dashboard/data/inflection/v3`から読み込み、0件でも例外なく空レポートを返す
- [ ] `tests/test_inflection_learning.py`が現行スキーマに対応して移植され、`pytest`が成功する
- [ ] `.github/workflows/forward_validation.yml`の学習ステップに`SNAPSHOT_ENCRYPTION_KEY`が`env`で明示的に渡され、`schedule`実行時のみ動作し、既存のPRトリガー時の実行時間に影響しない
- [ ] `--summary-output`（`artifacts/inflection_learning_summary.json`）のみが`upload-artifact`され、`--output`のフルレポート（`artifacts/inflection_learning.json`）はephemeral runner上にのみ残る
- [ ] yfinance取得失敗時のticker名・provider例外テキストが、例外メッセージ・`logging`・標準出力・標準エラーのいずれにも含まれない（logger抑止と`redirect_stdout`/`redirect_stderr`の両方で保証する）
- [ ] `load_inflection_learning_observations()`が`source_commit_sha`・`storage`メタデータ・score（finite・0〜100）を`load_inflection_signals`と同等に検証し、`report_schema_version == 4`以外を拒否しつつ複数`strategy_version`の混在は許可する
- [ ] `return_5d/20/60d_pct`・`volume_ratio_20d`等のoptional数値がNaN/infのとき`None`に正規化される（**レビュー指摘・4回目でbooleanの記述を削除、fail-closed方針は次項に一本化**）
- [ ] `_independent_rows()`の重複排除が`signal_date`ではなく各horizon outcomeの実`entry_date`/`exit_date`で判定される
- [ ] `near_52w_high_failed_to_outperform`と`near_listing_high_failed_to_outperform`が別理由として記録される
- [ ] `near_52w_high`/`near_listing_high`が`bool`型でないcandidateを含むsnapshotが、`False`へのfallbackではなく`SnapshotLoadError`で拒否される
- [ ] `memo/project-overview.md`に自己改善学習の対象範囲（`report_schema_version == 4`限定・`strategy_version`複数許容）が明記される
- [ ] `evaluate_learning_observations()`が各tradeの実際の`entry_date`/`exit_date`に基づく`paired_benchmark_returns()`でbenchmark比較する（`signal_date`起点の固定horizonは使わない）
- [ ] `python scripts/rebuild_inflection_learning.py`をローカル実行し、`artifacts/inflection_learning.json`と`artifacts/inflection_learning_summary.json`の両方が例外なく出力されることを手動確認する
