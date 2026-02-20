# エビデンスベース投資意思決定支援 実装計画書（更新版）

## 目的
`docs/gpt_reseach/research3.md` の提案に基づき、未実装の拡張機能（フェーズ7〜10）を実装する。

本ファイルは「これから実装する内容」に限定する。
既に実装済みのフェーズ詳細（1〜6）は可読性のため削除し、要約のみ残す。

---

## 実装済みフェーズ（要約のみ）

| フェーズ | 内容 | 状態 |
|---------|------|------|
| 1 | リスク指標 + イベント注釈 | 実装済み |
| 2 | エビデンス指標（momentum/value/quality/low-risk） | 実装済み |
| 3 | 選出理由（スコア内訳）表示 | 実装済み |
| 4 | 予測誤差分析（MAE・帯別比較） | 実装済み |
| 5 | 予測ガードレール（WARN/CLIPPED） | 実装済み |
| 6 | ベースライン比較（AI vs 12-1モメンタム vs SPY） | 実装済み |

注記:
- 実装済みフェーズの詳細仕様は Git 履歴および実装コード（`src/`, `dashboard/js/`）を参照。

---

## 本計画の対象（未実装）

| フェーズ | 内容 | 工数 | 主な効果 | 状態 |
|---------|------|------|---------|------|
| 7 | 確率化 + 校正ダッシュボード（Brier/log-loss/reliability diagram） | 中 | 予測が「確率として妥当か」を可視化し誤用を抑制 | 未着手 |
| 8 | ポジションサイジング + 損切り規律 | 中 | 実行規律（サイズ上限・撤退基準）を提示 | 未着手 |
| 9 | バックテスト品質開示（過剰最適化対策メタデータ） | 中〜高 | バックテストの透明性を向上 | 未着手 |
| 10 | マクロ指標統合（FRED によるレジーム判定） | 中 | マクロ環境に応じたリスク調整根拠を追加 | 未着手 |

---

## フェーズ7: 確率化 + 校正ダッシュボード

### 概要
- `predicted_change_pct` と `ci_pct` から `prob_up`（上昇確率）を導出。
- `accuracy.json` に校正指標を追加し、確率の信頼性を公開。

### バックエンド変更
- `src/predictor.py`
  - `compute_prob_up(predicted_change_pct, ci_pct)` を追加。
  - 出力に `prob_up`（将来拡張で `prob_up_calibrated`）を追加。
- `src/exporter.py`
  - `build_calibration_metrics(records)` を追加。
  - `accuracy.json` に `calibration` セクションを追加。

### 出力スキーマ追加

> 注記: `as_of_utc` / `data_coverage_weeks` は共通仕様セクション準拠（予測/評価系成果物に統一付与。macro.jsonは対象外）。以下の例は各フェーズ固有の追加フィールドのみ示す。

- `predictions.json`
```json
{
  "prob_up": 0.62,
  "prob_up_calibrated": null
}
```

- `accuracy.json`
```json
{
  "calibration": {
    "overall": {
      "brier_score": 0.205,
      "log_loss": 0.623,
      "ece": 0.031,
      "reliability_bins": [
        {"p_bin": "0.5-0.6", "n": 45, "mean_pred": 0.54, "empirical": 0.56}
      ],
      "n_calibrated": 87
    },
    "recent_n_weeks": {
      "n_weeks": 12,
      "brier_score": 0.198,
      "log_loss": 0.610,
      "ece": 0.028,
      "n_calibrated": 24
    }
  }
}
```

### フロントエンド変更
- `dashboard/accuracy.html`
  - `#calibration-section` を追加。
- `dashboard/js/accuracy.js`
  - reliability diagram（Chart.js）描画（`overall` データを使用）。
  - 指標（Brier/log-loss/ECE）を「全期間」と「直近N週」で並列表示。
  - `n_calibrated < 30` は非表示または「データ蓄積中」を表示。
- `dashboard/css/style.css`
  - 校正セクションのスタイル追加。

### 対象ファイル
- `src/predictor.py`
- `src/exporter.py`
- `dashboard/accuracy.html`
- `dashboard/js/accuracy.js`
- `dashboard/css/style.css`
- `tests/test_predictor.py`

---

## フェーズ8: ポジションサイジング + 損切り規律

### 概要
- フェーズ1で算出済みのボラティリティを使い、
  - 最大保有比率（ボラターゲット）
  - 推奨損切り水準
  を算出して提示する。

### バックエンド変更
- `src/enricher.py`
  - `compute_sizing(vol_ann, config)` を追加。
  - `sizing` フィールドを `enrichment` に追加。
- `src/exporter.py`
  - `predictions.json` へ `sizing` を組み込み。
- `config.yaml`
```yaml
sizing:
  vol_target_ann: 0.10
  max_weight_cap: 0.20
  stop_loss_multiplier: 1.0
```

### 出力スキーマ追加
- `predictions.json`
```json
{
  "sizing": {
    "vol_target_ann": 0.10,
    "max_position_weight": 0.20,
    "stop_loss_pct": -0.087,
    "stop_loss_rationale": "20日ボラティリティに基づく月次リスク推定値"
  }
}
```

### フロントエンド変更
- `dashboard/js/stock.js`
  - リスクパネルに `max_position_weight` / `stop_loss_pct` を追記。
- `dashboard/js/index.js`
  - カードのリスク行にサイズ目安を追記。
- `dashboard/css/style.css`
  - `.sizing-panel`, `.sizing-note` を追加。

### 対象ファイル
- `src/enricher.py`
- `src/exporter.py`
- `config.yaml`
- `dashboard/js/stock.js`
- `dashboard/js/index.js`
- `dashboard/css/style.css`
- `tests/test_enricher.py`

---

## フェーズ9: バックテスト品質開示（過剰最適化対策）

### 概要
- フェーズ6の比較結果に、検証品質メタデータを追加。
- 「どれだけ試して、どう評価したか」を公開する。

### バックエンド変更
- `src/baseline.py`
  - `build_backtest_hygiene(config, oos_start)` を追加。
  - `comparison.json` に `backtest_hygiene` を追加。
  - `reality_check_pvalue`・`pbo`・`deflated_sharpe` の算出・格納を担当。
- `config.yaml`
```yaml
backtest:
  num_rules_tested: 1        # 推奨: 2以上。pbo/reality_check 算出には最低2、推奨10以上
  num_parameters_tuned: 4
  oos_start: "2025-01-01"
  min_rules_for_pbo: 2       # pbo / reality_check_pvalue を算出する最小 num_rules_tested
```

### 出力スキーマ追加
- `comparison.json`
```json
{
  "backtest_hygiene": {
    "num_rules_tested": 1,
    "num_parameters_tuned": 4,
    "oos_start": "2025-01-01",
    "data_coverage_weeks": 52,
    "transaction_cost_note": "取引コスト・税金は未考慮",
    "survivorship_bias_note": "上場廃止銘柄は評価対象外（サバイバーシップバイアスあり）",
    "hygiene_status": "insufficient_trials",
    "reality_check_pvalue": null,
    "pbo": null,
    "deflated_sharpe": null,
    "hygiene_note": "num_rules_tested が min_rules_for_pbo 未満のため品質指標は算出不可"
  }
}
```

備考:
- `hygiene_status`:
  - `"insufficient_trials"`: `num_rules_tested < min_rules_for_pbo` のため pbo / reality_check_pvalue が算出不可。
  - `"computed"`: 全品質指標が算出済み。
  - `"partial"`: deflated_sharpe のみ算出済み（単一戦略でも算出可能）。
- `reality_check_pvalue`: White's Reality Check（複数戦略の多重検定補正済みp値）。`num_rules_tested >= min_rules_for_pbo` で算出。
- `pbo`: Probability of Backtest Overfitting（CSCV法）。`num_rules_tested >= min_rules_for_pbo` で算出。
- `deflated_sharpe`: Deflated Sharpe Ratio（テスト回数・多重比較を考慮した調整済みSharpe）。`num_rules_tested` / `num_parameters_tuned` をもとに単独算出可能。

### フロントエンド変更
- `dashboard/accuracy.html`
  - `#backtest-hygiene-section` を追加。
- `dashboard/js/accuracy.js`
  - 品質情報パネル描画。
- `dashboard/css/style.css`
  - 品質情報パネルスタイル追加。

### 対象ファイル
- `src/baseline.py`
- `config.yaml`
- `dashboard/accuracy.html`
- `dashboard/js/accuracy.js`
- `dashboard/css/style.css`
- `tests/test_baseline.py`（以下を検証対象とする）
  - `num_rules_tested < min_rules_for_pbo` で `hygiene_status == "insufficient_trials"` となること
  - `num_rules_tested >= min_rules_for_pbo` で `reality_check_pvalue` / `pbo` の算出分岐へ進むこと

---

## フェーズ10: マクロ指標統合（FRED）

### 概要
- FRED API を使い主要系列を取得し、`macro.json` を生成。
- index にマクロ環境バナーを表示。

### スコープ明確化
- 本フェーズ初期版は **FRED のみ** を対象。
- BOJ/e-Stat/EDINET 連携は将来拡張（別フェーズ）とする。

### バックエンド変更
- 新規: `src/macro_fetcher.py`
  - `fetch_fred_series(...)`
  - `build_macro_json(api_key)`
- `src/exporter.py`
  - `FRED_API_KEY` がある場合のみ `macro.json` を生成。
- ワークフロー
  - `weekly_run.yml` で `secrets.FRED_API_KEY` を注入。

### 出力スキーマ追加
- `macro.json`
```json
{
  "as_of_utc": "2026-02-20T00:10:00Z",
  "data_as_of_utc": "2026-02-19T18:00:00Z",
  "series": {
    "FEDFUNDS": {"latest_value": 5.33, "unit": "%"},
    "T10Y2Y": {"latest_value": -0.12, "unit": "%"},
    "VIXCLS": {"latest_value": 18.5, "unit": "pts"}
  },
  "regime": {
    "is_risk_off": false,
    "note": "VIX > 25 またはイールドカーブ負転でリスクオフ"
  }
}
```

備考:
- `as_of_utc`: JSON 生成時刻（UTC）。全 JSON で統一された「生成時刻」の意味を持つ。
- `data_as_of_utc`: FRED から取得した最新系列の基準日時（UTC）。`as_of_utc` と区別するため別名で保持する。

### フロントエンド変更
- `dashboard/index.html`
  - マクロサマリーバナー領域を追加。
- 新規: `dashboard/js/macro.js`
  - `macro.json` を読み込み、存在時のみ描画。
- `dashboard/css/style.css`
  - `.macro-banner`, `.risk-off` を追加。

### 対象ファイル
- `src/macro_fetcher.py`
- `src/exporter.py`
- `.github/workflows/weekly_run.yml`
- `dashboard/index.html`
- `dashboard/js/macro.js`
- `dashboard/css/style.css`
- `tests/test_macro_fetcher.py`

---

## 共通仕様: 透明性メタデータ（予測/評価系JSON）

research3.md の最低要件として、予測・評価系成果物 JSON に `as_of_utc` と `data_coverage_weeks` を統一付与する。

**適用範囲の方針（方針B）**: 対象を「予測/評価系JSON（predictions.json / accuracy.json / comparison.json）」に限定する。
`macro.json` は外部データ（FRED）を取得して生成するため `data_coverage_weeks` は対象外とし、`as_of_utc` のみ付与する。

### 対象ファイルと付与フィールド

| ファイル | as_of_utc | data_coverage_weeks | 担当モジュール |
|---------|-----------|---------------------|--------------|
| `predictions.json` | ✓ | ✓ | `src/exporter.py` |
| `accuracy.json` | ✓ | ✓ | `src/exporter.py` |
| `comparison.json` | ✓ | ✓ | `src/baseline.py` |
| `macro.json` | ✓ | ✗（外部データのため対象外） | `src/macro_fetcher.py` |

### スキーマ例（予測/評価系）
```json
{
  "as_of_utc": "2026-02-20T00:10:00Z",
  "data_coverage_weeks": 52
}
```

### 実装方針
- `as_of_utc` の意味（方針A採用）: 全 JSON で「生成時刻（UTC現在時刻）」に統一。`datetime.utcnow().isoformat() + "Z"` を書き込み時に付与する。
- `macro.json` の FRED 系列基準日: `as_of_utc` とは別に `data_as_of_utc`（FRED の最新系列日時）を付与する。
- `data_coverage_weeks`: 確定済みレコード（`hit` が "的中" or "外れ"）の週数を集計。
- 共通関数配置: `src/meta.py` に `build_common_meta(records)` を新設し、`src/exporter.py` と `src/baseline.py` の両方から import して使用する。`macro.json` 生成時は `src/macro_fetcher.py` が直接 `as_of_utc` を付与する（`data_coverage_weeks` は不要）。

---

## 実装順序（research3）

1. フェーズ7: 確率化 + 校正ダッシュボード
2. フェーズ8: ポジションサイジング + 損切り規律
3. フェーズ9: バックテスト品質開示
4. フェーズ10: マクロ指標統合（FRED）

---

## 依存関係

- フェーズ7
  - 依存なし（単独着手可能）
  - 校正品質表示は `n_calibrated` の蓄積件数に依存
- フェーズ8
  - フェーズ1の `risk.vol_20d_ann` を再利用（実装済み）
- フェーズ9
  - フェーズ6の `comparison.json` を拡張（実装済み）
- フェーズ10
  - 他フェーズに依存せず独立実装可能

---

## レビュー結果（今回反映）

- 実装済みフェーズ（1〜6）の詳細記述を削除し、要約のみへ整理。
- 旧計画（research2）と新規計画（research3）が同一粒度で混在していた構成を解消。
- フェーズ10の対象を「FRED初期版」に明示し、BOJ等との差分を明確化。

### review.md 指摘事項の反映（2026-02-20 第1回）

- [x] 参照パス誤記修正: `docs/gpt_reseach.md/research3.md` → `docs/gpt_reseach/research3.md`
- [x] フェーズ9: `reality_check_pvalue` / `pbo` / `deflated_sharpe` を出力スキーマに追加、`src/baseline.py` の算出責務を明記
- [x] 共通メタデータ: 予測/評価系JSON（predictions.json / accuracy.json / comparison.json）に `as_of_utc` / `data_coverage_weeks` を統一追加
- [x] フェーズ7の校正指標を `overall` + `recent_n_weeks` の2ウィンドウ構成に分割、UI要件に「全期間と直近N週の並列表示」を追記

### review.md 指摘事項の反映（2026-02-20 第2回）

- [x] 透明性メタデータの適用範囲を方針B（予測/評価系のみ）に統一。`macro.json` は `as_of_utc` のみ・`data_coverage_weeks` は対象外と明記
- [x] フェーズ9: `config.yaml` に `min_rules_for_pbo` を追加し、品質指標の算出条件を明示
- [x] フェーズ9: `hygiene_status`（`insufficient_trials` / `computed` / `partial`）を `comparison.json` スキーマに追加し、`null` のまま固定化しないためのステータス管理を定義

### review.md 指摘事項の反映（2026-02-20 第3回）

- [x] `as_of_utc` の意味を全 JSON で「生成時刻（UTC現在時刻）」に統一（方針A採用）。`macro.json` の FRED 系列基準日は `data_as_of_utc` として別名で保持するよう明記
- [x] 共通メタ関数 `build_common_meta` を `src/meta.py` に分離し、`src/exporter.py` と `src/baseline.py` から import して使用する設計を明示

### review.md 指摘事項の反映（2026-02-20 第4回）

- [x] フェーズ7のスキーマ例冒頭に「共通メタデータは共通仕様セクション準拠」の注記を追加し、実装漏れを防止
- [x] フェーズ9の対象ファイルに `tests/test_baseline.py` を追加し、`hygiene_status` 分岐と `min_rules_for_pbo` 条件の検証対象を明記

### review.md 指摘事項の反映（2026-02-20 第6回）

- [x] フェーズ7注記の「全成果物に統一付与」を「予測/評価系成果物に統一付与（macro.jsonは対象外）」へ修正し、共通仕様セクションの適用範囲と文言を統一

### 受け入れ確認チェック

- `plan.md` の research3参照パスが実在パスと一致している。
- フェーズ9仕様に Reality Check / PBO / Deflated Sharpe が含まれている。
- `macro.json` の `data_coverage` 方針が計画全体で一貫している（`as_of_utc` のみ・`data_coverage_weeks` は対象外）。
- `predictions.json` / `accuracy.json` / `comparison.json` に `as_of_utc` / `data_coverage_weeks` が定義されている。
- 校正指標が「全期間（overall）+ 直近N週（recent_n_weeks）」で表示される。
- フェーズ9で品質指標が `null` のまま固定化しないための `hygiene_status` と最小試行数要件（`min_rules_for_pbo`）が定義されている。
- `as_of_utc` の意味が全成果物で「生成時刻」に統一され、FRED 系列基準日は `data_as_of_utc` として区別されている。
- 共通メタ生成ロジックが `src/meta.py` に分離され、`src/exporter.py` と `src/baseline.py` の依存関係が明示されている。
- フェーズ別スキーマ例と共通仕様の必須フィールド定義に齟齬がない（フェーズ7に共通仕様参照注記あり）。
- フェーズ9の品質指標ロジックに対するユニットテスト（`tests/test_baseline.py`）追加が計画に含まれている。
- フェーズ7注記と共通仕様セクションで、`data_coverage_weeks` の適用範囲が同一文言で定義されている（予測/評価系JSONのみ、macro.jsonは対象外）。
