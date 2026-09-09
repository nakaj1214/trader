# PR #10 レビュー結果

- 対象: nakaj1214/trader PR #10 「Add cumulative self-learning postmortems for inflection signals」
- ブランチ: `feat/self-learning-postmortem` → `main`
- 変更規模: 5ファイル / +1018 / -2
- レビュー日: 2026-09-09
- レビュー方式: 8アングル並列調査（正確性3・再利用/簡潔化/効率3・高度性1・規約1）+ 個別検証

## 概要

JP inflectionシグナルの累積自己学習・ポストモーテム機能を追加するPR。暗号化スナップショットからシグナル観測を読み込み、将来の株価推移と比較して「予測ミス」「爆発的値動きの見逃し」を検出し、統計的根拠のある要因のみを次期戦略への昇格候補として提案する（本番の戦略重みは自動更新しない設計）。

新規追加ファイル:
- `scripts/rebuild_inflection_learning.py`
- `src/evaluation/inflection_learning.py`
- `tests/test_inflection_learning.py`

既存ファイルへの軽微な変更:
- `.github/workflows/forward_validation.yml`
- `.github/workflows/test.yml`

## 指摘事項（重要度順）

### 1. `load_learning_observations` が兄弟モジュールより検証が緩い（CONFIRMED）
- 場所: `src/evaluation/inflection_learning.py:44-84`
- 既存の `load_inflection_signals`（`src/evaluation/inflection_forward.py:20-63`）は `source_commit_sha`、`storage.encrypted is True`、`storage.snapshot_date_basis`、スコアの `isfinite`/`0-100`範囲チェックを必須としているが、新設の `load_learning_observations` はこれらを一切チェックしない。
- 失敗シナリオ: 改ざん済み・出所不明のスナップショット（`source_commit_sha`欠落や`storage.encrypted != True`）が forward-validation では拒否されるのに、自己学習パイプラインには無検証で取り込まれてしまう。学習データの信頼性を担保する検証層が抜け落ちている。

### 2. baseline爆発率が0だと昇格判定がその水平線全体で無音停止する（CONFIRMED）
- 場所: `src/evaluation/inflection_learning.py:325-332`
```python
lift = None
if baseline_explosion_rate is not None and baseline_explosion_rate > 0:
    lift = rate / baseline_explosion_rate
```
- 失敗シナリオ: `baseline_explosion_rate` が `None` ではなく厳密に `0.0`（ベースライン群に爆発的値動きが一件もない）の場合、`lift` は常に `None` のままとなり `direction` は必ず `"hold"`。特定要因が100%の爆発率を持っていても、ベースラインが0なら昇格候補として検出されない。データ初期段階や `h120`（閾値60%）のような達成困難な水平線で起きやすく、エラーも警告も出ないため気づきにくい。

### 3. `_extract_ticker_frame` が「要求ティッカー数」と「実際に返る列形状」を混同（PLAUSIBLE）
- 場所: `scripts/rebuild_inflection_learning.py:33-44`
```python
if not isinstance(raw.columns, pd.MultiIndex):
    return raw.copy() if batch_size == 1 else pd.DataFrame()
```
- 失敗シナリオ: `batch_size` は「バッチで要求したティッカー数」であり、yfinanceが実際に返す列構造（MultiIndexか否か）を保証しない。複数ティッカーをリクエストしても一部が上場廃止等でデータなしの場合、yfinanceの挙動によっては列がフラット化することがあり、その場合バッチ内の成功したティッカーまで巻き添えで空扱いになり、無駄なリトライ後に偽の `RuntimeError` で失敗する可能性がある。yfinanceの実挙動依存のため確定はできないが、要求数ではなく実際の `raw.columns` 形状で分岐すべきロジック上の弱点。

### 4. `_prediction_miss_reasons` が `h20` のみを見て判定（PLAUSIBLE）
- 場所: `src/evaluation/inflection_learning.py:162-186`
- 4つの評価水平線（5/20/60/120日）を計算しているにもかかわらず、「予測ミス」ラベルは20日時点の結果のみで固定的に決まる。
- 失敗シナリオ: 20日で損失でも120日で大きく上振れした（あるいはその逆の）シグナルが、恒久的に誤ってミス/非ミスに分類される。意図的な設計かもしれないが、ポストモーテムの説明力が特定の1水平線に偏る点は要検討。

### 5. `build_learning_report` が同一処理を2回繰り返す（CONFIRMED、簡潔化・効率の2アングルが独立指摘）
- 場所: `src/evaluation/inflection_learning.py:391-434`
- 全体ベースライン(`baselines`/`factors`)と昇格用ベースライン(`promotion_baselines`/`promotion_factors`)を、ほぼ同じ3行シーケンスで水平線ごとに2回実行。
- 失敗シナリオ: 戦略バージョンが1つしかない通常運用時は `latest_rows == evaluated` となり完全に同じ計算を2回行うだけの無駄。加えて将来の統計ロジック変更時に2箇所を同期更新し忘れるリスクがある。共通処理を関数化して2回呼ぶ形に整理すべき。

### 6. CI coverageゲートが新モジュールの低カバレッジを覆い隠しうる（PLAUSIBLE）
- 場所: `.github/workflows/forward_validation.yml:57-62`
- `inflection_learning` を既存の充実したカバレッジ対象群と同じ `--cov-fail-under=80` の一括判定に混ぜたため、`pytest-cov` はブレンド後の合算値でしか判定しない。
- 失敗シナリオ: 将来 `inflection_learning.py` の変更がテスト追加なしでマージされても、他モジュールの高カバレッジに埋もれてゲートを通過しうる。なお `scripts/rebuild_inflection_learning.py` 自体は `--cov` 対象に含まれていない。

### 7. 既存モジュールとのロジック重複（CONFIRMED）
- 場所: `src/evaluation/inflection_learning.py` / `scripts/rebuild_inflection_learning.py`
- スナップショット読み込み・検証ループ（指摘1と根は同じ）、価格取得のリトライ/バックオフ/失敗集約ロジック、レポート出力の書き込みボイラープレートが、いずれも `inflection_forward.py` / `rebuild_inflection_forward_validation.py` とほぼ同一構造で個別に再実装されている。
- 失敗シナリオ: 今後どちらか一方だけ修正されて仕様が乖離するリスクが高い（実際に指摘1で既に乖離が発生済み）。

### 8. `public_learning_summary` が許可リスト方式（CONFIRMED、cleanup）
- 場所: `src/evaluation/inflection_learning.py:490-512`
- 公開すべきでないのは実質 `observations`/`postmortems` の2キーだけなのに、15個のキーを列挙する許可リストで管理している。
- 失敗シナリオ: 将来レポートに新しい集計キーを追加した際、この許可リストへの追加を忘れると新フィールドが黙って公開サマリから消える。除外リスト方式（`{"observations", "postmortems"}` を弾く）の方が意図（ティッカー単位情報を出さない）に合致し安全。

## その他の確認事項

- CI設定変更（ワークフロー2ファイル）自体は配線ミスなし、ステップ順序も正しく、`SNAPSHOT_ENCRYPTION_KEY` の受け渡しも妥当。
- ティッカー単位のポストモーテム（`postmortems`/`observations`）が公開アーティファクトに漏れていないことは確認済み（`public_learning_summary` の許可リストで除外されており、`artifacts/` も `.gitignore` 対象）。
- CLAUDE.md はこのリポジトリに存在しないため規約違反の指摘なし（`AGENTS.md` はあるが対象外）。

## 優先度

最も優先度が高いのは **指摘1（検証漏れ）** と **指摘2（昇格判定の無音停止）**。いずれも自己学習パイプラインの信頼性・正確性に直結する。
