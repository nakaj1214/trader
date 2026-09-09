# 実装計画: Phase 0+1 — ガバナンス基盤の復旧と評価バイアスの是正

> 入力: `memo/implement/proposal.md` の REQ-001〜REQ-007（Phase 0: ガバナンス・実行基盤 / Phase 1: データ再現性・評価バイアスの是正）。
> 出力先を標準の `docs/implement/plan.md` ではなく `memo/implement/plan.md` にしている点に注意。
> REQ-002/003/007のユーザー決定は2026-09-09に確定済み（詳細はStep 2/3/7）。

## 目的

Shadow Scan が実データを一度も蓄積できていない状態（REQ-001）と、main の無保護運用（REQ-002）・Actions の tag pin（REQ-003）というガバナンス上の欠落を解消したうえで、Forward Validation に存在する2つの評価バイアス — Trailing Stop の右打切り（REQ-004）と backtest/live 間の価格調整基準の不一致（REQ-005） — を是正する。あわせて評価用価格データの再現性チェック（REQ-006）を追加し、単一プロバイダ依存のデータ品質リスク（REQ-007）を文書化してユーザー合意を得る。これらは Phase 2 以降（評価指標拡張・戦略ロジック改善）を実施する前提となる。

## スコープ

- 含むもの: REQ-001〜REQ-007（proposal.md 記載の Phase 0 + Phase 1）
- 含まないもの:
  - Phase 2（126/252日評価、Explosion Recall、ポートフォリオ評価等）
  - Phase 3（買い候補ロジック改善、`deep_candidates` 比較、スコア閾値検証等）
  - Phase 4（Exit Monitor の当日HWM反映、Trade Ledger等）
  - 文献・記述修正（REQ-029〜035）
  - J-Quants有償プラン導入、cross-provider の本格実装、単一provider内の異常値検知コード（REQ-007はリスクの文書化とユーザー合意のみ。詳細はStep 7参照）

## 影響範囲（変更/追加予定ファイル）

| ファイル | 理由 |
|---|---|
| GitHub リポジトリ設定（Secrets, Branch protection） | REQ-001（運用確認。Secret自体は登録済み）, REQ-002（保護方針の決定） — コード変更ではなくユーザー操作 |
| `scripts/run_inflection_shadow.py` | REQ-001（coverage不足の根本原因調査のための診断出力追加。`validate_report()` L54付近）、原因判明後の対応（マスタのフィルタ追加等、別途追記のうえ実装） |
| `src/screening/inflection_live.py` | REQ-001（`scan_japan_inflection()`の戻り値に日付別件数・stale ticker一覧を追加。原因調査結果に応じて上場廃止/取引停止銘柄の除外フィルタを追加する可能性は調査結果次第で別途追記） |
| `tests/test_inflection_live.py` | REQ-001（日付別件数・stale ticker一覧の計算に対するテスト追加） |
| `tests/test_shadow_health.py` | REQ-001（`validate_report()`の例外メッセージに診断情報が含まれることのテスト追加） |
| `.github/workflows/inflection_shadow.yml` | REQ-002（direct push運用方針の確定後に対応。方針未確定のため本計画では変更を保留） |
| `.github/workflows/forward_validation.yml` | REQ-002（Forward Validationのdirect push可否もREQ-002の確認事項に含める。方針未確定のため保留）, REQ-003（方針確定後にActions SHA pin。方針未確定のため保留）, REQ-006（`validate` job（read-only）と`persist-price-hashes` job（`contents: write`、scheduled限定）への分割） |
| `.github/workflows/position_monitor.yml`, `.github/workflows/test.yml` | REQ-003（方針確定後にActions SHA pin。方針未確定のため保留） |
| `.github/dependabot.yml`（新規） | REQ-003（方針確定後にDependabot有効化。方針未確定のため保留） |
| `README.md` または新規 `docs/runbook.md`（`memo/analysis/` 配下でも可、要確認） | REQ-002/003の方針決定結果の明記, REQ-007（単一プロバイダリスクの受容方針とユーザー合意の明記） |
| `src/evaluation/inflection_backtest.py` | REQ-004（`TradeResult` に `horizon_matured` フィールド追加、matured-only集計関数追加） |
| `scripts/rebuild_inflection_forward_validation.py` | REQ-004（`exit_strategies` に `eligible_count`/`censored_count` 出力を追加）, REQ-005（trailing stop用にsplit-only価格を`actions=True`で取得する経路を追加し`price_adjustment`表記を区別）, REQ-006（価格基準ごと・日付行ごとのOHLCハッシュを算出し、暗号化永続化ファイルとの共通日付比較・更新を行う） |
| `src/data/live_quote.py` | REQ-005（`fetch_split_adjusted_history` の split-only 調整ロジックを forward validation から再利用できるよう関数を切り出し） |
| `dashboard/data/inflection_forward_price_hashes.enc`（新規） | REQ-006（価格再現性ハッシュ（日付行単位）の永続化先。ticker等を平文で残さないよう既存の `snapshot_encryption_secret()` で暗号化してgit commitする） |
| `tests/test_inflection_backtest.py` | REQ-004のテスト、REQ-005のTrailing Stop基準差分のテスト（既存ファイルに追記） |
| `tests/test_live_quote.py` | REQ-005（分割調整関数の切り出しに対するテスト、既存ファイルに追記） |
| `tests/test_inflection_forward.py` | REQ-005（`actions=True`/`False`取得モード分岐）, REQ-006（日付行ハッシュの安定性・共通日付比較ロジック）のテスト（既存ファイルに追記） |
| `tests/test_data_validation.py` | REQ-007の異常値検知を将来実施する場合の追加先（本計画では実装しない。既存ファイル名を誤って `tests/test_validation.py` としないよう明記） |

## 実装ステップ

#### Step 1: Shadow Scan の稼働復旧（REQ-001）

**訂正**: 「本ステップにコード変更は無い」としていたのは誤り。下記「coverage不足の根本原因調査」で`scripts/run_inflection_shadow.py`（`validate_report()`）と`src/screening/inflection_live.py`（`scan_japan_inflection()`）に診断出力を追加するコード変更を伴う。ユーザーが行う運用タスク（Secret登録・workflow_dispatch実行・3営業日確認）と、診断コードの実装・テストは分けて管理する。

**状況更新（2026-09-09 実行ログ `memo/tmp.md` により判明）**: `SNAPSHOT_ENCRYPTION_KEY` は登録済みで、`snapshot_encryption_secret()` は正常に通過し `persist_report()` まで到達している。したがって Secret未設定はもはや現在のblockerではない。現在の実際の失敗原因は `validate_report()`（`scripts/run_inflection_shadow.py:54`）の以下のチェックである。

```
RuntimeError: DATA_HEALTH: latest market-date coverage too low: date=2026-09-09, 2855/3656 (78.1%)
```

`MIN_LATEST_DATE_COVERAGE = 0.80`（同ファイルL22）に対し78.1%で不足。これは`universe`（J-Quants `listed_issues()` から取得した現在の上場銘柄マスタ、L278）に対する価格カバレッジ（70%基準、こちらは通過）ではなく、価格取得に成功した銘柄（`price_data_count`）のうち「最新日付のバーを持つ銘柄」の比率が基準を満たさないというチェックである。ログには個別に404となった13銘柄（`2540.T`等、"No data found, symbol may be delisted"）が見えるが、これらは`price_data`に含まれないため`latest_date_coverage`の分母にすら入らない別問題であり、78.1%不足の主因ではない。**真因は未特定**。

**運用チェックリスト（ユーザー実施・Secret値とGitHub操作権限が必要）**:
- [x] GitHub リポジトリの Settings → Secrets and variables → Actions に `SNAPSHOT_ENCRYPTION_KEY` を設定する（値は `src/data/snapshot_crypto.py` の `snapshot_encryption_secret()` が要求する形式に合わせる）— **2026-09-09 登録済み・動作確認済み（Secret起因のエラーは解消）**
- [ ] 下記「coverage不足の根本原因調査」を完了する
- [ ] 原因調査の結果に基づく対応（下記参照）を適用したうえで `workflow_dispatch` を再実行し、成功することを確認する
- [ ] 翌営業日以降、scheduled run（毎日 07:40 UTC）が成功し `dashboard/data/inflection/YYYY-MM-DD.enc` が commit されることを3営業日以上連続で確認する（経過日数が必要なため即日には完了しない）

**coverage不足の根本原因調査（`systematic-debugging`方針に準拠。閾値は根拠なく変更しない）**:
- [ ] `scan_japan_inflection()`（`src/screening/inflection_live.py:293-296`）の戻り値に、`latest_dates`の日付別件数（例: 直近5営業日分の件数）と、最新日付でない銘柄のticker一覧（先頭20件程度）を新しいキー（例: `latest_date_histogram`, `stale_tickers_sample`）として追加する
- [ ] `validate_report()`（`scripts/run_inflection_shadow.py:54`）が`DATA_HEALTH: latest market-date coverage too low`で失敗する際、上記2つの値を例外メッセージに含める
- [ ] `tests/test_inflection_live.py` に `scan_japan_inflection()` が日付別件数とstale ticker一覧を正しく計算することを確認する最小テストを追加する
- [ ] `tests/test_shadow_health.py` に、`validate_report()` がcoverage不足時に例外メッセージへ日付別件数を含めることを確認するテストを追加する（既存の `test_validate_report_rejects_*` 系テストの構造に合わせる）
- [ ] `workflow_dispatch`を再実行し、上記診断出力を取得する
- [ ] 診断結果を次の観点で評価する: (a) stale銘柄が特定の古い日付に集中しているか（J-Quantsマスタに残る上場廃止・取引停止銘柄の可能性）、(b) 日付がランダムに分散しているか（yfinanceのバッチ取得タイミング起因の一時的遅延の可能性）、(c) 78.1%程度が実際の全市場スキャンで恒常的に生じる値かどうか
- [ ] **診断結果が出るまで、フィルタ追加・リトライ変更・閾値変更のいずれも実装しない。** 診断結果に基づき対応を決定した後、対応候補（J-Quantsマスタから上場廃止/取引停止銘柄を除外するフィルタ追加／yfinance取得のリトライ・タイミング見直し／実測データに基づく`MIN_LATEST_DATE_COVERAGE`の変更をユーザーに提示し合意）から選び、別途この計画に追記してから実装する

**注意**: Secret登録前の段階では、Phase 1（REQ-004〜007）の「実データでの検証」は実施不能だったが、Secret自体は解消済み。現在は上記coverage問題により実データ蓄積が引き続きブロックされている。REQ-004〜007のコード変更自体は実データ蓄積を待たずに合成データのユニットテストで検証を進めてよいが、本Phase全体の完了条件からは運用チェックリストを分離し、それが未完了の間は「Phase 1実データ検証: 未完了」として扱う。

**検証**: `git log --oneline -- dashboard/data/inflection/` に `.gitkeep` 以外の `.enc` ファイル追加コミットが3件以上並ぶこと（運用チェックリスト側の受入条件。コード変更の完了条件には含めない）。

#### Step 2: main ブランチのガバナンス方針を決定・明記する（REQ-002）— **決定済み**

**ユーザー決定（2026-09-09）**: Shadow ScanおよびForward Validation（Step 6で新設する`persist-price-hashes` job）のいずれもmainへのdirect push（`contents: write`での直接commit）を**継続する**。専用ブランチ+PRへの変更は行わない。

**対応**:
- [ ] `.github/workflows/inflection_shadow.yml`の"Commit encrypted immutable market-day snapshot"ステップの直前に、direct pushが許容されている理由（生成物のみでソースコード変更を含まない、レビュー不要なデータ更新である）を1行コメントで残す
- [ ] `.github/workflows/forward_validation.yml`の`persist-price-hashes` job（Step 6）にも同様の理由コメントを残す
- [ ] README または runbook に「`main`はブランチ保護が無効。Shadow Scan workflowおよびForward Validationの`persist-price-hashes` jobが`contents: write`で直接pushする設計であり、意図的な運用である」旨を明記する

**検証**: 上記コメント・README/runbook記述が追加されていること。

#### Step 3: GitHub Actions の SHA pin 化と Dependabot 導入（REQ-003）— **決定済み**

**ユーザー決定（2026-09-09）**: 個人プロジェクトの規模ではメンテナンス負荷に見合わないため、SHA pin化・Dependabot導入は**実施しない**。既存のtag pin（`actions/checkout@v7`等）を継続する。

**対応**: コード変更なし。この決定をplan.md（本項）に記録することをもって本ステップは完了とする。

#### Step 4: Trailing Stop の右打切りバイアスを是正する（REQ-004）

現状 `simulate_signal()`（`src/evaluation/inflection_backtest.py:63`）は、`trailing_stop_pct` 指定時、stop が発動した場合は `has_full_horizon`（60営業日ぶんのデータが既に存在するか）を無視して常に "completed" として返す一方、stop が発動せず `has_full_horizon=False` の場合のみ incomplete（`exit_date=None`）として除外する（L148-162）。この非対称性により、直近シグナルのうち「早く損切りされたもの」だけが集計に残り、「まだ確定していない（stopしていない）もの」が消えるため、直近コホートの成績が下方に歪む。

- [ ] `TradeResult` dataclass（L18-37）に `horizon_matured: bool | None = None` フィールドを追加する
- [ ] `simulate_signal()`内で、trailing_stop_pct指定の有無・exit_reasonに関わらず、常に `has_full_horizon` の値を `horizon_matured` として設定して返す（早期stopでもimmatureならその旨を記録する。データ欠如で trade自体が作れない場合は `horizon_matured=None` のまま）
- [ ] `src/evaluation/inflection_backtest.py` に `filter_matured(trades: Iterable[TradeResult]) -> list[TradeResult]` を追加し、`horizon_matured is True` の trade のみを返す
- [ ] `summarize_trades()` の呼び出し元（`rebuild_inflection_forward_validation.py` の `exit_strategies` 生成部, L212-244）で、`filter_matured()` を通した trade 集合に対する summary（`matured_summary`）と、未フィルタの summary（`raw_summary`、参考値として維持）の両方を出力する
- [ ] `exit_strategies[f"trailing_{...}pct"]` に `eligible_count`（matured件数）と `censored_count`（immature件数）を追加する

**検証**: `entry_date` から60営業日分の未来データが存在しない signal で trailing stop が早期発動したケースを用意したユニットテストを作成し、`horizon_matured=False` かつ `filter_matured()` 適用後に除外されることを確認する。同時に60営業日分のデータが揃っている signal は `horizon_matured=True` となり残ることを確認する。

#### Step 5: Forward Validation と Position Monitor の価格調整基準を統一する（REQ-005）

現状、`scripts/rebuild_inflection_forward_validation.py:73` は `auto_adjust=True`（配当・分割調整済み＝total-return adjusted）で価格を取得しているが、本番の `src/data/live_quote.py` の `fetch_split_adjusted_history()`（L54-129）は `auto_adjust=False` + 分割のみ手動補正（配当調整なし）である。Trailing Stop の HWM/Stop 判定はこの2つの基準の違いにより、配当銘柄で backtest と実運用の水準がずれうる。

- [ ] `src/data/live_quote.py` の分割調整ロジック（L78-129の分割ファクター計算部分）を再利用可能な関数として切り出す（例: `split_adjust_ohlc(history: pd.DataFrame, as_of: date) -> pd.DataFrame` のように、`SplitAdjustedHistory` 生成の中核ロジックを独立させる。既存の `fetch_split_adjusted_history` はこれを呼び出す形にリファクタリングする）
- [ ] `rebuild_inflection_forward_validation.py` の `_fetch_adjusted_histories()`（L40-93）は現状 `actions=False`（L74）で取得しており分割情報（`Stock Splits`列）を含まない。`exit_strategies` 生成用に別途 `auto_adjust=False, actions=True` で取得する経路を追加し、そのデータを上記の分割調整関数に通す（`horizons` 用は既存どおり `auto_adjust=True, actions=False` のまま維持し、両者の取得方法の違いを関数名またはパラメータで明示する）
- [ ] レポートの `price_adjustment` フィールド（現状 `"split_adjusted_ohlc"` という誤記、L140）を `{"horizons": "total_return_adjusted", "exit_strategies": "split_only"}` のような区別可能な形式に修正する

**検証**: 過去に配当を実施した銘柄（テストでは合成データで模擬）に対し、`auto_adjust=True` 系列と split-only 系列で Trailing Stop の exit_date/exit_price が異なりうることを `tests/test_inflection_backtest.py` のユニットテストで示す。分割調整関数の切り出し自体は `tests/test_live_quote.py` に、`_fetch_adjusted_histories()` の取得モード分岐（`actions=True`/`False`の使い分け）は `tests/test_inflection_forward.py` にテストを追加する。

#### Step 6: 評価用価格データの再現性チェックを追加する（REQ-006）

forward validation は signal（買い候補）自体は immutable snapshot だが、評価に使う将来価格は rebuild のたびに yfinance から再取得しており、provider側の事後訂正で結果が変わりうる。

**レビュー指摘への対応（2回目）**: 1回目の改訂で「`artifacts/`はephemeralなので永続化する」という方向には修正したが、`{ticker, price_basis, date_range, sha256}`という**全期間まとめてのハッシュ**は、履歴が毎日1行ずつ伸びる通常運用では機能しない。次回実行時に新しい日付の行が増えれば`date_range`（開始〜終了日）自体が変わるため、「同じ`date_range`同士を比較する」というロジックは実質毎回スキップされ、逆に「取得範囲の終端を固定して比較する」ようにすると新規行が増えただけで毎回差分警告になり、provider側の事後訂正なのか正常な履歴追加なのかを区別できない。したがって**日次の行単位でハッシュを取り、共通する日付部分だけを前回と比較する**方式に変更する。

- [ ] `rebuild_inflection_forward_validation.py` の `_fetch_adjusted_histories()` が返す各ティッカーのOHLC系列について、**日付ごと**に `(Open, High, Low, Close)` を固定の数値表現（例: 小数点以下6桁に丸めた`float`、またはそれを文字列化したもの）にそろえた上で1行ずつSHA256ハッシュを計算する。インデックスはタイムゾーンなしの`date`に正規化してから使う（`_series()`と同様の正規化）。**価格基準ごと**（`total_return_adjusted`用の horizons 取得と、Step 5 で split-only に切り替える exit_strategies 取得）に分けて保持する: `{ticker: {"total_return_adjusted": {date: sha256, ...}, "split_only": {date: sha256, ...}}}`
- [ ] 同一OHLC入力に対して常に同じハッシュ値になることを保証するテストを追加する（NaN混入時の扱い、列の順序、dtype違いなどによってハッシュがぶれないことを確認する）
- [ ] このハッシュ辞書をJSON化し、既存の`dashboard/data/inflection/`配下の暗号化スナップショットと同じ`snapshot_encryption_secret()`を使って暗号化し、`dashboard/data/inflection_forward_price_hashes.enc`として保存する（tickerを平文でリポジトリに残さないため）
- [ ] スクリプト側は実行開始時に前回の`.enc`ファイルが存在すれば復号して読み込み、**前回と今回の両方に存在する日付キーのみ**を突き合わせてハッシュを比較する（新しい日付の追加はスキップ対象であり差分警告にしない。既存日付のハッシュが変化した場合のみproviderの事後訂正とみなし警告する）。比較後、最新のハッシュ辞書（新しい日付を含む）で`.enc`ファイルを更新する
- [ ] **標準出力（公開リポジトリのActionsログ）への警告はticker名を含めない。** 警告メッセージは `{"price_basis": "...", "changed_count": N}` のように、変化した価格基準と件数のみを出す。どのticker・どの日付が変化したかの詳細は、暗号化された`.enc`ファイル自身の中に埋め込む（例えば更新後のハッシュ辞書に`revision_detected_at`のようなメタ情報を持たせる）か、暗号化されたartifactとしてのみ保持し、平文ログには出さない

**ワークフロー権限の分離**（`contents: write`がPRの検証ジョブ全体に及ぶ問題への対応。責務は比較・生成側と書き込み側で重複させない）:
- [ ] `.github/workflows/forward_validation.yml`を**2つのjob**に分割する。
  - (1) `validate`: `permissions.contents: read`のまま変更しない。PR・schedule・workflow_dispatchいずれのトリガーでも実行する。既存のpytest・`rebuild_inflection_forward_validation.py`実行に加え、**前回`.enc`の復号・新規ハッシュとの比較・警告出力・更新後ハッシュ辞書の暗号化までをすべてこのjob内で完結させる**（リポジトリ内の既存`.enc`をcheckoutで読み取り、比較後の新しい暗号化済みペイロードを生成する）。生成した暗号化ペイロードのみを`actions/upload-artifact`で後続jobに渡す
  - (2) `persist-price-hashes`: `permissions.contents: write`を持ち、`if: github.event_name == 'schedule'`でjobレベルに限定する。行うのは **checkout → `validate` jobが生成した暗号化artifactを`download-artifact`で取得 → `dashboard/data/inflection_forward_price_hashes.enc`として配置 → commit・push** のみ。復号・比較・ハッシュ計算などのロジックはこのjobに置かない
- [ ] 上記の分担により、書き込み権限を持つjobはgitの読み書きだけを行い、価格データや比較ロジックに一切触れない構成にする

**REQ-002との関係の明確化**: 本Step 6により、Forward Validation側にも新たなmain直接push経路が追加される。これはREQ-002で確認する「main directpush方針」の対象に含める（Shadow Scanのdirect push可否とForward Validationのdirect push可否は同じガバナンス判断の一部として、まとめてユーザーに確認する。Forward Validation側だけ先に既定で書き込み権限を追加することはしない）。

**検証**: ローカルで`SNAPSHOT_ENCRYPTION_KEY`を設定した状態で forward validation を2回連続実行し、1回目で生成された`dashboard/data/inflection_forward_price_hashes.enc`を2回目が読み込み、共通日付部分で警告が出ないことを確認する（プロセスをまたいだ永続化ファイル経由の比較）。新しい日付が1行増えただけでは警告が出ないこと、既存日付のOHLC値を1件改変した場合は警告が出ることの両方をテストで確認する。

#### Step 7: 単一プロバイダのデータ品質リスクを明記し、ユーザー合意を得る（REQ-007）— **決定済み**

**ユーザー決定（2026-09-09）**: 当面cross-provider照合（J-Quants価格との突合等）は行わず、yfinance単一プロバイダのデータ品質リスクを**受容する**。

**レビュー指摘への対応**: 当初案の「前日比±80%の単一provider内チェック」は、系列全体が一貫して100倍になる誤りや通常幅に収まる誤価格を検出できず、proposal.mdの受入条件（cross-provider照合、またはリスク受容方針の文書化と合意）のどちらも満たさない。また現行の`fetch_price_data()`（`src/data/yfinance_prices.py`）は`actions=False`で取得しており分割情報を`validate_ohlcv()`に渡していないため、「分割イベント発生日を除外する」という当初の実装は前提となるデータ取得ができておらず実装不能だった。本Phaseでは異常値検知の実装は行わず、proposal.mdの受入条件どおりリスクの文書化とユーザー合意のみを行う。

- [ ] README または runbook に、yfinance単一プロバイダ依存によるデータ品質リスク（分割調整漏れ、配当調整漏れ、100倍誤り等、yfinance公式のPrice Repair文書が言及する既知の問題）と、当面リスクを受容する旨を明記する
- [ ] 将来的に異常値検知（例: 前日比リターンの閾値チェック）を追加する場合は、`fetch_price_data()`側で`actions=True`に変更し分割情報を`validate_ohlcv()`まで伝搬させる設計が別途必要であることをrunbookに書き残す（実装は本Phaseの範囲外）

**検証**: README/runbookに上記リスク説明とリスク受容の記録が追加されていること。異常値検知コードの追加・テストは本Phaseの完了条件に含めない。

## 例外・エラーハンドリング方針

- REQ-004/005 はいずれも既存の fail-closed 方針（データ不備時は例外を送出し処理を止める）を踏襲する。新規追加する検証は既存の `RuntimeError` ベースの失敗経路に統合し、新しい例外階層は増やさない。
- **REQ-006は意図的にfail-closedにしない。** 価格改訂検知は「標準出力への警告」のみとし、forward validationレポート自体の生成・commitは継続する。理由: providerの事後訂正は珍しくなく、検知のたびにレポート生成全体を失敗させると週次運用が頻繁に止まる。したがってREQ-006はfail-closed方針の対象外として明示的に切り分ける。受入テストも「警告は出るがプロセスは正常終了する（exit code 0）」ことを確認する形にする。
- REQ-007は原則としてコード実装を行わないため対象外。REQ-001〜003はコードではなく運用・設定変更のため、実装上の例外処理は発生しない。

## テスト/検証方針

- 自動テスト: `pytest`（既存の `tests/test_inflection_backtest.py`, `tests/test_live_quote.py`, `tests/test_inflection_forward.py`, `tests/test_inflection_live.py`, `tests/test_shadow_health.py` に追記。REQ-007の異常値検知は本Phaseでは実装しないため`tests/test_data_validation.py`への追加は無し）
- 手動確認観点:
  - Step 1: GitHub Actions の実行ログ、coverage不足の診断出力、dashboard/data/inflection/への commit 履歴（ユーザーの運用確認）
  - Step 2/3: ユーザーとの決定事項の記録（Shadow ScanとForward Validation両方のdirect push可否を含む）、決定に応じたREADME/runbookの記述またはworkflow YAMLのdiff
  - Step 4〜6: `python scripts/rebuild_inflection_forward_validation.py` を実データ（Step1完了後）で実行し、出力JSONに `eligible_count`/`censored_count`/`price_adjustment`区別、および`dashboard/data/inflection_forward_price_hashes.enc`が期待通り出力・更新されることを確認。`forward_validation.yml`の2job構成がPRトリガーでは書き込みを行わないことをActionsのpermissions表示で確認
  - Step 7: README/runbookのリスク記述とユーザー合意の記録

## リスクと対策

1. リスク: REQ-004の変更でmatured判定を厳格化すると、直近数ヶ月分のsignalがtrailing-stop評価から一時的にほぼ全滅する可能性がある（そもそもshadow scanが2026-09-09時点でデータ蓄積を始めたばかりのため） → 対策: `eligible_count`/`censored_count`を出力し、サンプル不足の場合はレポート上で明示する（Phase 2のREQ-012統計的信頼性強化と合わせて評価）。
2. リスク: REQ-005でexit_strategiesの価格基準をsplit-onlyに切り替えると、既存のforward validation結果（過去に生成済みのartifacts）と数値が変わり、比較不能になる → 対策: 変更後の初回実行結果をベースラインとして扱う旨をコミットメッセージ/PRに明記する。過去結果は「total-return adjusted基準だった」ことをレポート内の`price_adjustment`フィールドの違いで判別可能にする。
3. リスク: （解消）REQ-003のSHA pin/Dependabotは「実施しない」と決定済みのため、メンテナンス負荷増のリスクは発生しない。
4. リスク: REQ-006でforward_validation.ymlに書き込み権限を持たせると、PRトリガー実行時に意図しない書き込みが発生しうる → 対策: commitステップの条件分岐ではなく、`contents: write`を持つjob自体を`validate`（read-only、PR/schedule/dispatch共通）から分離し、`persist-price-hashes`job（scheduled限定）にのみ付与する。
5. リスク: （解消）REQ-002/003/007のユーザー決定は2026-09-09に取得済み（Step 2/3/7参照）。REQ-006の`persist-price-hashes`job追加はREQ-002の「継続する」決定に基づき実施してよい。
6. リスク: REQ-001のcoverage不足の根本原因が「J-Quantsマスタの上場廃止銘柄残存」以外（例: yfinanceバッチ取得の一時的な問題）だった場合、フィルタ追加では解決しない → 対策: 診断出力（日付ヒストグラム・stale ticker一覧）を先に取得し、原因を分類してから対応方針を決める。原因不明のまま実装を進めない。

## 完了条件

**ユーザー決定（2026-09-09、すべて確定済み）**:
- REQ-002: main directpushを**継続する**（Shadow Scan・Forward Validation双方）
- REQ-003: Actions SHA pin + Dependabot導入は**実施しない**
- REQ-007: yfinance単一プロバイダのデータ品質リスクを**受容する**

**コード変更の完了条件（合成データ・ユニットテストで検証可能）**:
- [ ] `TradeResult`に`horizon_matured`が追加され、`filter_matured()`によるmatured-only集計が`exit_strategies`に`eligible_count`/`censored_count`とともに出力される（REQ-004）
- [ ] Trailing Stop評価（`exit_strategies`）が`actions=True`で取得したsplit-only価格基準を使用し、レポートの`price_adjustment`表記が実態と一致する（REQ-005）
- [ ] 評価用価格データのハッシュが価格基準ごと・日付行ごとに算出され、同一入力に対し安定したハッシュ値になることがテストで確認されている。警告出力にticker名が含まれない（REQ-006）
- [ ] `.github/workflows/forward_validation.yml`が`validate`（read-only、復号・比較・暗号化artifact生成まで担当）と`persist-price-hashes`（`contents: write`、schedule限定、checkout・commit・pushのみ担当）の2job構成になっており、`dashboard/data/inflection_forward_price_hashes.enc`への暗号化commitがscheduled実行でのみ行われる（REQ-006。REQ-002の決定により実施可）
- [ ] `.github/workflows/inflection_shadow.yml`と`persist-price-hashes` jobにdirect push許容理由のコメントが追加され、README/runbookにREQ-002〜003・007の決定内容が明記されている
- [ ] `scan_japan_inflection()`の戻り値に日付別件数・stale ticker一覧が追加され、`validate_report()`の例外メッセージに含まれる（REQ-001診断コード）
- [ ] 上記に対応するユニットテストが `tests/test_inflection_backtest.py`, `tests/test_live_quote.py`, `tests/test_inflection_forward.py`, `tests/test_inflection_live.py`, `tests/test_shadow_health.py` に追加され、`pytest`が成功する

**運用確認が必要な完了条件（コード変更とは別に管理。ユーザー実施）**:
- [ ] REQ-001: coverage不足（`DATA_HEALTH: latest market-date coverage too low`）の根本原因が診断出力（上記コード変更後に`workflow_dispatch`を再実行して取得）により特定され、対応が適用されたうえで、Shadow Scanが3営業日以上連続で成功し`.enc`ファイルが蓄積されている

**Phase 1完了の前提**: 上記「運用確認」が完了するまで、Phase 2以降（proposal.mdのREQ-008〜）の着手根拠となる実データでの検証は「未完了」として扱う。
