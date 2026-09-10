# Trader リポジトリ機能拡張・実装計画書 (Implementation Roadmap & Action Plan)

本計画書は、設計書（`trader-enhancement-design.md`）に基づき、「**Trader**」リポジトリへ学術論文・クオンツ理論の成果を段階的かつ安全に組み込むための工程・マイルストーン・リスク管理計画を策定したものです。

---

## 1. プロジェクト目標と成功指標 (KPI)

### 1.1 目標 (Objectives)
1. **超過収益率（Excess Return）の向上**: ベンチマーク（1306.T TOPIX ETF）に対する年間超過収益率の増大 [17]。
2. **リスク調整後リターンの最適化**: シャープレシオ $1.0$ 以上を目指し、トレイリングストップ最適化により最大ドローダウン（Max Drawdown）を $15\%$ 未満に抑制 [2, 35]。
3. **運用・再現性の維持**: 暗号化スナップショット、GitHub Actions 自動化、J-Quants Free API制約の完全遵守 [9, 10, 11, 12, 17]。

### 1.2 成功判定 KPI
| 指標 | 現行ベースライン（推定） | 目標値（機能拡張後） | 根拠論文 |
| :--- | :--- | :--- | :--- |
| **Sharpe Ratio** | 0.5 〜 0.7 | **1.1 〜 1.3** | Harbourfront Quant (2023) [2], Quantpedia [35] |
| **Max Drawdown** | -25% 〜 -35% | **-15% 未満** | Zambelli (2016) [52], Fan & Zhang (2023) [2] |
| **Outlier 捕捉率** | 未計測 | **上位7%の大化け株保持率 80%以上** | Zarattini et al. (2024) [44] |
| **TOPIX 勝率** | 50% 前後 | **60% 以上** | Osaka Univ (2022) [105], SIG-FIN (2011) [80] |

---

## 2. フェーズ別実装ロードマップ (Phased Roadmap)

```
[ Phase 1: 動的リスク管理 & ATR ストップ ] ──────────┐ (1〜2週間)
                                                      │
[ Phase 2: スクリーニング・シグナル拡張 ] ────────────┼─► [ Forward Validation ]
  (PEAD / Volume Surge / 52W High)                    │   (検証＆比較レポート)
                                                      │
[ Phase 3: Validation Engine & メトリクス拡張 ] ──────┘
                                                      │
                                                      ▼
[ Phase 4: ベイズ最適化 & Position Monitor 連動 ] ─────── (3〜4週間)
```

---

### Phase 1: 動的リスク管理 & ATR ストップの実装 (工数目安: 1〜2週間)
* **目的:** 固定15%トレイリングストップから、ボラティリティ比例型（ATR）トレイリングストップへの移行 [2, 32]。
* **作業項目:**
  1. `src/trader/indicators/atr.py`: 14日 EMA ベースの ATR 計算モジュールの追加。
  2. `scripts/forward_validation.py`: 固定 10%/15%/20% ストップロジックに加え、$k \times ATR$ ($k=2.5, 3.0$) の動的ストップ検証分岐を追加 [17, 32]。
  3. テスト作成: pytest による ATR 計算および動的ストップトリガー条件の単体テスト実装 [24]。
* **成果物:** ATR対応版 `forward_validation.py` & テストグリーン確認。

---

### Phase 2: スクリーニング・シグナルの多角化 (工数目安: 2週間)
* **目的:** PEAD、出来高急増、52週高値アンカリングの3大シグナルを統合 [28, 80, 105]。
* **作業項目:**
  1. `src/trader/scanner/volume_surge.py`: 直近20日出来高 / 250日平均出来高の比率（Volume Ratio）判定ロジックの実装 [84, 86]。
  2. `src/trader/scanner/pead.py`: J-Quants 財務データから営業利益予想の上方修正率・YoY 変化率のスコア化ロジックの強化 [13, 105]。
  3. `src/trader/scanner/high_proximity.py`: 52週高値（250日高値）からの近接率 $PR$ の算出とスコア加算 [32, 35]。
  4. `scripts/run_inflection_shadow.py`: 新スコアロジックを反映し、スナップショットスキーマ `2.1` への対応 [10, 14, 24]。
* **成果物:** 新判定ロジック搭載の Shadow Scanner とスキーマ v2.1 スナップショット。

---

### Phase 3: Validation Engine & 詳細メトリクス出力 (工数目安: 1週間)
* **目的:** 戦略成果の定量的評価（Sharpe Ratio, Max Drawdown, Outlier Contribution）の自動化 [17, 35, 44]。
* **作業項目:**
  1. `src/trader/validation/metrics.py`: シャープレシオ、最大ドローダウン、勝率、売買回転率の計算ユーティリティ作成 [17, 35]。
  2. `scripts/forward_validation.py`: 週次バックテスト実行時に追加メトリクスを計算し、GitHub Actions Artifact `inflection-forward-summary` に要約データを出力 [18]。
* **成果物:** 詳細定量メトリクス出力機能付き Forward Validation パイプライン。

---

### Phase 4: ベイズドローダウン最適化 & Position Monitor 連携 (工数目安: 2週間)
* **目的:** Live Monitor（Google Sheets / Slack）への動的ストップ通知の適用とベイズ最適化の実証 [19, 20, 52, 70]。
* **作業項目:**
  1. `scripts/run_position_monitor.py`: Google スプレッドシート「保有銘柄」タブの `trailing_stop_pct` 項目において、`ATR_2.5` などの動的表記をサポート [20]。
  2. `src/trader/risk/bayesian_stop.py`: Zambelli (2016) の Rメソッド（ローリングウィンドウ内最大ドローダウン分布のベイズ推定）による最適カットオフ算出モジュールのプロトタイプ作成 [70, 75]。
* **成果物:** Google Sheets / Slack 動的アラート連携 & ベイズストップモジュール。

---

## 3. マイルストーン & 担当・実行スケジュール

| マイルストーン | 主要納入物 | 目標完了時期 | 判定基準 |
| :--- | :--- | :--- | :--- |
| **M1: ATR Dynamic Stop** | ATR算出・Forward Validation 統合 | 第1週終了時 | pytest 通過、既存固定ストップとの比較データ出力 [17, 24] |
| **M2: Signal Multi-Factor** | PEAD/Volume Surge/52W High Scanner | 第3週終了時 | スナップショット Schema v2.1 の暗号化保存成功 [10, 14] |
| **M3: Validation Metrics** | Sharpe Ratio / MDD / Turnover ログ出力 | 第4週終了時 | 週次 GitHub Actions artifact に新指標が含まれること [18] |
| **M4: Live Monitor Sync** | Dynamic Stop 対応 Live Monitor | 第6週終了時 | Google Sheets 状況タブへの動的ストップ価格正常上書き [20] |

---

## 4. リスク管理とシステム制約事項

### 4.1 データプロバイダ制約への配慮
* **J-Quants API Free プラン制限:**
  5 calls/min のレート制限および指数バックオフ（429/5xx リトライ）処理を既存クライアントから継承し、超過呼び出しを防止 [12, 17]。
* **yfinance データ品質リスク:**
  分割・配当調整漏れや欠損値に対し、既存のデータ健全性検証（Coverage 65営業日以上、ticker重複チェック等）を厳守 [15, 16]。

### 4.2 バックテストオーバーフィッティング（過剰適合）リスク
* **対策:** Forward Validation の評価ルール（翌営業日始値エントリー、1306.T TOPIX ベンチマーク同条件比較）は結果を見る前に固定し、Future Look-Ahead Bias（先回りバイアス）を排除する原則を継続 [17]。

---
*作成日: 2026-09-09*
