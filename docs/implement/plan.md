# 修正計画書（nakaj1214/trader）

> 目的：検証の信頼性（データスヌーピング/過剰適合）を抑え、運用の安定性を上げ、誤解を生まない出力/表示に直す。

---

## 1. ゴール（達成状態）
- **検証がズルくならない**：スクリーニング条件・モデル設定を弄っても、同じ期間で"都合の良い採点"をしない構造になっている
- **運用で落ちにくい**：外部API失敗・欠損・休場があっても完走し、原因が追える
- **誤解を防ぐ**：簡略/参考値は明確に「参考」と分かる（UI/JSON/通知文言が統一）

---

## 2. 対象範囲（スコープ）
### 今回やる
- 期間分割（開発期間/評価期間）・ウォークフォワード（最小版）
- baseline（比較/品質指標）の扱い是正（正しく実装 or 参考として格下げ）
- データ品質（Close/Adj Close、欠損、評価日ルール）の固定
- JPもUSと同じパイプラインで回せるように統一（screen→predict→track→export/notify）
- レート制限/失敗時の共通処理（リトライ、バックオフ、タイムアウト、ログ）
- 設定変更の履歴・スナップショット出力（再現性）

### 今回やらない（別フェーズ）
- 自動売買
- 研究レベルの統計検定フル実装（PBO/Reality Check等を論文通りに完全再現するのは別案件）

---

## 3. 実行順（最重要→重要→整備）

> **注意:** フェーズ番号は内容の種別を示す識別子であり、実行順序と一致しない。
> Phase 1（ウォークフォワード）はデータ品質が固定されていないと結果がブレるため、
> Phase 3（データ品質固定）を先に完了させること。

1. Phase 0：再現性・CI・ログ（安全ネット）
2. Phase 3：データ品質＋評価日定義固定（ブレ除去） ← Phase 1 の前提
3. Phase 1：検証設計（データスヌーピング対策）
4. Phase 2：baseline是正（誤解防止）
5. Phase 4：JPパイプライン統一
6. Phase 5：外部API耐性強化
7. Phase 6：初心者向け誤解防止の表示/ドキュメント

---

## 4. 作業分解（フェーズ別）

### Phase 0：現状固定と安全ネット（最優先の土台）
**狙い**：修正で壊れても戻せる／差分比較できる

#### タスク
- [ ] 出力 JSON にメタ情報を必ず埋め込む
  - `run_timestamp`（ISO 8601 UTC）
  - `git_commit`（`git rev-parse --short HEAD` で取得）
  - `config_hash`（`config.yaml` の SHA-256 先頭8桁）
  - `data_source_flags`（使用した外部API の有効/無効フラグ）
- [ ] 実行時に `artifacts/config_snapshot.json` へ使用設定を保存
  - `artifacts/` は `.gitignore` に追加（シークレット混入防止）
  - 保存タイミング: `src/main.py` の先頭で `config` ロード直後
- [ ] 外部API無しで通るテストモードを強化（モック/フィクスチャ）
  - 全 `*_fetcher.py` が API キー未設定でも degraded mode で完走すること
- [ ] 各ステップでログを統一（開始/終了/件数/例外/対象ティッカー）

#### 受入条件（DoD）
- [ ] 同一 commit + 同一 config で「同じ件数・同じメタ情報」が再現できる
- [ ] APIキー無しでもテストが通る（CI でシークレット不要）
- [ ] `artifacts/` が `.gitignore` に追加されている

---

### Phase 1：検証設計の導入（データスヌーピング対策）
**狙い**：スクリーニングやProphet設定を触るほど当たって見える問題を抑える

> **前提:** Phase 3（評価日・価格系列の固定）完了後に実施すること。
> 評価日が確定していない状態でウォークフォワードを計算すると結果がブレる。

#### タスク
- [ ] 期間分割（train/test）を `config.yaml` で設定できるようにする
  ```yaml
  walkforward:
    train_weeks: 52   # ルール決定に使う期間（最低52週推奨）
    test_weeks: 13    # 評価期間（1クォーター）
    min_train_weeks: 26  # データ不足でスキップする閾値
  ```
- [ ] "ルール固定期間" の実装
  - 評価期間（`test_weeks`）中は `config.yaml` の重み・閾値・モデル設定を変更しない前提で集計
  - **実運用フロー:** ルール変更は「次のトレイン窓の開始時」のみ許可。本番 cron 実行中は config を編集しない。変更したい場合は `docs/implement/changelog.md`（未作成なら新規作成）に日付・理由を記録してから次週に適用する
  - ルール固定期間の概念を `docs/guide/USER_GUIDE.md` に明記する
- [ ] ウォークフォワード評価（最小版）を `src/walkforward.py` として実装
  - 計算フロー: `train_window` でルール決定 → `test_window` で評価 → 窓を `test_weeks` ずらして繰り返し
  - 最低必要データ: `train_weeks + test_weeks` 週分の確定済みレコード
- [ ] 評価指標の固定（的中率に加えて MAE / MAPE / ヒット率信頼区間も標準出力）
- [ ] ウォークフォワード結果を `dashboard/data/walkforward.json` へ出力
  ```json
  {
    "generated_at": "2025-01-01T00:00:00Z",
    "config": { "train_weeks": 52, "test_weeks": 13 },
    "windows": [
      {
        "train_start": "2023-01-01",
        "train_end":   "2023-12-31",
        "test_start":  "2024-01-01",
        "test_end":    "2024-03-31",
        "hit_rate_pct": 60.0,
        "mae": 1.23,
        "mape": 2.45,
        "n_predictions": 30
      }
    ]
  }
  ```

#### 受入条件
- [ ] `walkforward.json` が上記スキーマで出力される
- [ ] データ不足時は `windows: []` で出力され、エラー終了しない
- [ ] "ルール固定期間" の概念が `USER_GUIDE.md` に明記されている
- [ ] `config.yaml` に `walkforward` セクションが追加されている

---

### Phase 2：baseline（比較/品質指標）の扱い是正
**狙い**：簡略実装（プレースホルダ）を"本物っぽく"見せない

#### 現状
`baseline.py` の `build_backtest_hygiene()` は `hygiene_status = "computed"` を返すが、
`pbo` / `reality_check_pvalue` / `deflated_sharpe` の計算は明示的にプレースホルダ値。
`is_placeholder` フィールドが未実装のため、UIが誤解を招く可能性がある。

#### 方針（どちらか）
- A案（推奨：先に実施）：現状の簡略指標は **参考** と明記し、UI/JSONで警告 or 非表示
- B案：正しい実装へ置換（計算/依存/テストが増えるので後回しでもOK）

#### タスク（A案）
- [ ] `build_backtest_hygiene()` の返り値に `is_placeholder: true` を追加
  - `hygiene_status == "computed"` であっても簡略計算なら `is_placeholder: true`
  - `hygiene_status == "insufficient_trials"` は `is_placeholder: null`（算出不可）
- [ ] dashboard / 通知で `is_placeholder: true` の指標は警告ラベルまたは非表示にする
- [ ] `USER_GUIDE.md` に「baseline指標は参考値（簡略推定）であり、意思決定に使わない」旨を明記

#### 受入条件
- [ ] `backtest_hygiene` JSON に `is_placeholder` フィールドが常に含まれる
- [ ] `is_placeholder: true` の場合にダッシュボードで視覚的に区別されている
- [ ] `test_baseline.py` で `is_placeholder` の存在がアサートされている

---

### Phase 3：データ品質と評価日定義の固定（Close/Adj Close・欠損・休場）
**狙い**：データの揺れで結果がブレない

#### タスク

**Close vs Adj Close の設計決定（要確定）**
- [ ] **現状確認:** 現行コードは全ファイルで `df["Close"]` を使用（混在なし）
- [ ] `Close` を継続使用する場合: 日本株の配当落ちによる疑似的な価格下落を許容すると明記する
  - 影響範囲: 配当利回りの高い JP 銘柄のモメンタムスコアが一時的に下振れする
- [ ] `Adj Close` に切り替える場合: 全ファイル一括変更し、yfinance の `auto_adjust` 設定を確認する
- [ ] **どちらを選んだかを `config.yaml` に `price_column: "Close"` として明記し、コード内で参照する**（ハードコード禁止）

**評価日ルールの固定**
- [ ] 評価日を明文化: 「予測日から `forecast_days` 取引日後の `price_column` 終値で判定」
  - 現行 `tracker.py:fetch_close_at` はこのルールで実装済み——テストで固定する
  - 休場日（祝日）の扱い: 取引日カウントのみ（カレンダー日ではない）。現行実装と同じ
  - 週跨ぎ・連休の扱いをユニットテストで明示的にカバーする

**欠損の扱い統一**
- [ ] `marketCap が None` 等の欠損: 代替ソース（FMP → yfinance）で補完、それでも null なら除外してログに記録
- [ ] 欠損率が全銘柄の 30% 超の場合はサマリーに警告を出す
- [ ] 欠損処理のルールを `src/utils.py` または専用モジュールに集約する

#### 受入条件
- [ ] `price_column` が `config.yaml` に定義され、全モジュールで参照されている
- [ ] 評価日・欠損ルールが `USER_GUIDE.md` または `docs/` に明記されている
- [ ] 休場日/祝日/週跨ぎのケースをカバーするユニットテストが存在する
- [ ] 欠損時の挙動が全モジュールで一貫している

---

### Phase 4：日本株パイプラインの統一（US/JP共通フロー）
**狙い**：JPがscreenだけ/途中止まりにならない

#### 現状の課題
- `main.py` の JP フローは `screen()` のみで終了。predict/track/sheets/notify/export に進まない
- `tracker.py` は Google Sheets の単一ワークシートを前提とし、US/JP の区別がない
- `notifier.py` は米ドル建て（`$`）表記のみ

#### タスク
- [ ] `src/main.py` に `run_market_pipeline(market, config)` を実装し、JP/US 共通フローとして整理
- [ ] **Sheets 設計を決定する（要確定）**
  - 案A: 同一ワークシートに `market` 列を追加（`"US"` / `"JP"`）
  - 案B: ワークシートを市場ごとに分ける（`predictions_us` / `predictions_jp`）
  - どちらを選択したかを `config.yaml` と `docs/` に明記する
- [ ] `tracker.py` を市場対応に拡張
  - JP ティッカー（`.T` suffix）が `fetch_close_at` で正しく評価されることを確認・テスト化
  - `market` パラメータを受け取り、JP/US で取得ソース（yfinance/J-Quants）を切り替える
- [ ] `notifier.py` を市場対応に拡張
  - JP 銘柄は円建て表記（`¥`）、US 銘柄はドル建て（`$`）
- [ ] JP 固有差分（J-Quants/FMP 補完、決算警告等）は `enricher.py` または `jquants_fetcher.py` に閉じ込める
- [ ] JP の `exporter.py` 出力を `dashboard/jp/` 向けに分離する（現行は共通）

#### 受入条件
- [ ] JP も US と同等に `screen → predict → track → sheets → notify → export` まで動作する（モックテスト）
- [ ] `tracker.py` が JP ティッカー（`.T`）で正しい終値を取得できることをテストで確認済み
- [ ] Sheets の設計（同一/分割）が決定され、コード・ドキュメントに反映されている
- [ ] 市場差分が `enricher.py` / `notifier.py` の市場パラメータに集約されている

---

### Phase 5：外部API耐性（レート制限/失敗時の共通化）
**狙い**：運用で落ちない、落ちても原因が追える

#### タスク
- [ ] HTTP クライアントを `src/http_client.py` に共通化
  - ライブラリ: `requests` + `urllib3.util.retry.Retry`（または `tenacity`）
  - デフォルト設定: `timeout=10`秒、リトライ3回、指数バックオフ（1→2→4秒）
  - 429 レスポンスの `Retry-After` ヘッダーを尊重（ヘッダーがない場合は60秒待機）
  - 適用対象: `finnhub_fetcher.py`, `fmp_fetcher.py`, `jquants_fetcher.py`, `macro_fetcher.py`, `notifier.py`, `line_notifier.py`
- [ ] 通知失敗は非致命（全体停止しない）＋失敗ログ/サマリー必須
  - 現行は `try/except` で握りつぶしているが、失敗件数を最後にサマリー出力する
- [ ] yfinance の `download` 呼び出しをバッチ化・キャッシュ化
  - 同一実行内で同じティッカーを複数回取得しないようにセッション内キャッシュを追加

#### 受入条件
- [ ] 一時的な外部失敗でもバッチが完走し、失敗件数がサマリーに残る
- [ ] 429 / timeout の挙動が全 fetcher で統一されている
- [ ] `test_http_client.py` でリトライ・バックオフ・429 処理をモックテスト化している

---

### Phase 6：誤解防止（初心者向け表示/文言/ドキュメント）
**狙い**：「確実に儲かる」と誤解されない導線にする

#### タスク
- [ ] dashboard / 通知で「推定」「参考」「簡略」を強制表示
  - 予測価格には「AI推定値（参考）」ラベルを付与
  - `is_placeholder: true` の指標には「簡略推定・参考値」バッジを表示
- [ ] `USER_GUIDE.md` に以下を追記
  - 検証の読み方（期間分割/ウォークフォワード）
  - ルール固定期間の意味と変更手順
  - baseline/品質指標は参考（placeholder）である旨
  - Close vs Adj Close の選択理由と JP 株への影響
- [ ] JSON に `confidence_notes` / `data_quality_notes` を追加（欠損や注意点の明文化）
  - 例: `"confidence_notes": "Prophet 簡易モデル。外部要因は未考慮"`
  - 例: `"data_quality_notes": "PBR 欠損: FMP フォールバック使用"`

#### 受入条件
- [ ] UI / 通知 / 出力 JSON が "誤解しにくい" 文言に統一されている
- [ ] `USER_GUIDE.md` にウォークフォワード・ルール固定期間・placeholder の説明が追記されている
- [ ] `confidence_notes` / `data_quality_notes` フィールドが主要 JSON に存在する

---

## 5. 変更が入りやすい主要ポイント（ファイル目安）
- パイプライン：`src/main.py`
- スクリーニング：`src/screener.py`
- 予測：`src/predictor.py`
- 追跡（的中判定）：`src/tracker.py`
- 出力統合：`src/exporter.py`
- 補強：`src/enricher.py`
- baseline：`src/baseline.py`
- アノマリー検証：`src/alpha_survey.py`
- 外部API：`src/*_fetcher.py`, `src/notifier.py`, `src/line_notifier.py`
- HTTP共通クライアント（新規）：`src/http_client.py`
- ウォークフォワード（新規）：`src/walkforward.py`
- 設定：`config.yaml`
- ドキュメント：`docs/guide/USER_GUIDE.md`

---

## 6. テスト方針（最低限）
- [ ] 評価日ルール（休場/祝日/週跨ぎ）をユニットテスト化
- [ ] `price_column` 設定が全モジュールで参照されていること（`Close` がハードコードされていないこと）をテスト
- [ ] `is_placeholder` フィールドが `backtest_hygiene` JSON に常に含まれることをテスト
- [ ] JP ティッカー（`.T` suffix）が `fetch_close_at` で正しく評価されることをテスト
- [ ] JP/US パイプラインが同じ出口（export/notify）まで到達する統合テスト（モック）
- [ ] HTTP リトライ・バックオフ・429 処理を `test_http_client.py` でモックテスト化

---

## 7. 完了条件（Definition of Done）
- [ ] 検証が期間分割され、`walkforward.json`（期間別テーブル形式）が出力される
- [ ] `price_column` が `config.yaml` で固定され、評価日・欠損扱いがテストで守られている
- [ ] `baseline.py` の簡略指標に `is_placeholder: true` が付与され、UIで誤解されない表示になっている
- [ ] JP/US が `run_market_pipeline()` で同一パイプラインを完走する
- [ ] 外部API失敗があっても完走し、失敗件数がサマリーログに残る
- [ ] 実行メタ情報（commit hash / config hash）・config スナップショットで再現性が担保される
- [ ] `USER_GUIDE.md` にウォークフォワード・ルール固定期間・placeholder の説明が追記されている

---

## 8. 実装メモ（進め方）
- **Phase 3 を Phase 1 より先に完了させる**。評価日・価格系列が固定されていないとウォークフォワードの数字が信用できない
- `price_column` の Close/Adj Close 選択は JP 株の配当落ち影響を確認してから決定する（迷ったら `Close` のまま理由を明記）
- baseline の正確実装は後回しでも良いが、**`is_placeholder` の付与だけは Phase 2 で必ず入れる**
- `alpha_survey.py` は既に実装済み。このフェーズ計画の対象外だが、Phase 6 の誤解防止文言（アノマリー検証はスコアに含まれない旨）をダッシュボードに追加すること
- `artifacts/` ディレクトリは `.gitignore` に追加してからコードを書く（シークレットの誤コミット防止）
