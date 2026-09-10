# Trader リポジトリ機能拡張・基本システム設計書 (System & Strategy Enhancement Design Document)

本設計書は、日本株の短期変化点（Inflection）検知および自動監視を行う Python プロジェクト「**Trader**」に対し、最新のクオンツ・ファイナンス理論および学術研究の知見を反映するためのシステム拡張設計仕様を定義します。

---

## 1. 全体アーキテクチャと基本方針

### 1.1 システム拡張の目標
1. **シグナル精度の向上**: PEAD（決算発表後ドリフト）、出来高急増（Volume Surge）、52週高値アンカリング効果を定量的スコアに統合し、偽シグナル（Noise）を削減する [13, 28, 84, 105]。
2. **リスク調整後リターンの最大化**: 従来の固定15%トレイリングストップから、銘柄別ボラティリティ（ATR）に連動する動的トレイリングストップへ拡張し、シャープレシオ向上と最大ドローダウン抑制を実現する [2, 17, 32]。
3. **Point-in-Time データの厳格性維持**: 暗号化スナップショット、J-Quants Free遅延データの扱い、実行コストモデル（0.2%/1.2%）などの現行データ健全性規約を完全に維持・拡張する [10, 11, 12, 16, 17]。

### 1.2 アーキテクチャ構成図（コンポーネント拡張）

```
[ J-Quants API V2 ] + [ yfinance ]
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│ Module A: Enhanced Inflection Scanner (日次スクリーナー) │
│  ├─ Fundamental & PEAD Engine (業績修正/成長率/YoY比較)  │
│  ├─ Volume Surge Engine (1M/12M 出来高変化率)            │
│  └─ 52-Week High Proximity & Momentum Engine             │
└────────────────────────┬─────────────────────────────────┘
                         │ Candidates Score
                         ▼
┌──────────────────────────────────────────────────────────┐
│ Encrypted Snapshot Storage (dashboard/data/inflection/)  │
│  └─ Schema v2.1 (新スコア・ATR・メタデータ格納)          │
└────────────┬─────────────────────────────┬───────────────┘
             │                               │
             ▼                               ▼
┌─────────────────────────────┐ ┌───────────────────────────┐
│ Module B: Dynamic Exit      │ │ Module C: Advanced        │
│ Monitor                     │ │ Forward Validation Engine │
│  ├─ High Water Mark 追跡    │ │  ├─ ATR-based Trailing Stop│
│  ├─ ATR Dynamic Stop        │ │  ├─ Bayesian Stop (T/R)   │
│  └─ Google Sheets / Slack   │ │  └─ Sharpe/MDD/Turnover   │
└─────────────────────────────┘ └───────────────────────────┘
```

---

## 2. モジュール別詳細設計仕様

### 2.1 Module A: スクリーニング（Inflection Scanner）の強化仕様

#### (1) PEAD（決算発表後ドリフト）＆ファンダメンタル・エンジン
* **概要:** 大阪大学の研究 (2022) [105] に基づき、J-Quants 財務データを用いた決算サプライズの抽出ロジックを強化します。
* **計算式・判定ルール:**
  * **売上・営業利益成長率:** 同一年度の訂正値を考慮し、前年同期実績が存在する場合のみ YoY 比較を実行（既存原則遵守）[13]。
  * **業績予想上方修正フラグ ($Surprise_{Rev}$):** 直近四半期における営業利益予想の修正率が $+5\%$ 以上かつ前年比増益。
  * **流動性スコアフィルタ:** Amihud の非流動性指標または売買代金下位銘柄を排除し、実効コストを担保できる上位流動性ユニバースに制限 [85, 105]。

#### (2) Volume Surge（出来高急増）エンジン
* **概要:** 人工知能学会 SIG-FIN 研究 (2011) [80, 84] に基づき、出来高の異常増加によるトレンド持続性をスコア化します。
* **計算式:**
  $$\text{Volume Ratio (VR)} = \frac{\text{直近20営業日の平均出来高}}{\text{過去250営業日（12ヶ月）の平均出来高}}$$
* **判定閾値:**
  * $VR \ge 1.5$: 出来高急増フラグ付与（加点スコア $+1.5$）
  * $VR < 0.8$: 出来高低迷（減点ペナルティ $-1.0$）

#### (3) 52週高値アンカリング・ブレイクアウトエンジン
* **概要:** Quantpedia / Wilcox & Crittenden 研究 [32, 35] に基づき、52週高値（250日高値）への近接度を評価します。
* **計算式:**
  $$\text{Proximity Ratio (PR)} = \frac{\text{現在株価（Close）}}{\text{過去250営業日における最高値（High}_{250}\text{)}}$$
* **判定閾値:**
  * $PR \ge 0.95$（52週高値から5%以内）: 高度モメンタム候補（加点スコア $+2.0$）
  * $PR = 1.00$（新高値ブレイクアウト）: 超優先候補（`EARLY_CANDIDATE` 昇格フラグ）[10, 32]。

---

### 2.2 Module B: 動的リスク管理（Dynamic Trailing Stop）の拡張仕様

#### (1) ATR（Average True Range）連動型トレイリングストップ
* **概要:** 従来の固定 $15\%$ トレイリングストップ [20] から、銘柄ごとのボラティリティに自動適応する ATR トレイリングストップへ拡張します [2, 32]。
* **計算アルゴリズム:**
  1. 直近14日間の True Range (TR) を計算:
     $$TR = \max(High - Low, |High - Close_{prev}|, |Low - Close_{prev}|)$$
  2. $ATR_{14} = \text{EMA}_{14}(TR)$ を算出。
  3. ストップ価格（$StopPrice_t$）の動的更新ルール:
     $$\text{StopPrice}_t = \max\left(\text{StopPrice}_{t-1}, \text{HighWaterMark}_t - k \times ATR_{14,t}\right)$$
     ※ 通常ボラティリティ銘柄では $k = 2.5 \sim 3.0$ を標準パラメータとします。
* **メリット:** 高ボラティリティ銘柄（成長株等）でのノイズによる損切りを回避しつつ、低ボラティリティ銘柄では利益を速やかに保全します [2, 32, 57]。

#### (2) ベイズ分析に基づく最大ドローダウン最適化（Rメソッド）
* **概要:** Zambelli (2016) [52, 70, 75] の Rメソッドを参考とし、Forward Validation の蓄積データから過去の最大ドローダウン分布 $P(D \in B_i)$ を集計。
* **実装仕様:**
  * 直近 $m=250$ トレードのドローダウン履歴をビン（Bin）分割し、期待リターンが最大化される累積確率カットオフ $T$ を算出 [62, 63, 70]。
  * ベイズ最適ストップ値 $T$ を補助的なエグジットパラメータとして記録 [74]。

---

### 2.3 Module C: 検証エンジン（Forward Validation Engine）の強化仕様

#### (1) 評価メトリクスの拡張
* 現行の「TOPIX比過剰収益率（Excess Return）」および「10%/15%/20%固定トレイリングストップ評価」[17] に加え、以下の定量的リスク指標を生成レポートに追加出力します。
  1. **Sharpe Ratio (シャープレシオ)**: Risk-Free Rate = 0% と仮定した年率化リスク調整後リターン [2, 35]。
  2. **Max Drawdown (最大ドローダウン)**: 保有期間中および決済後の最大下落率 [17, 35]。
  3. **Outlier Contribution Rate (大化け株寄与率)**: Zarattini et al. (2024) [44] の知見に基づき、全トレード中上位7%の銘柄が総利益に占める割合を計測。
  4. **Turnover (売買回転率)**: 1ヶ月あたりの平均売買回数および取引コスト浸食率 [44]。

#### (2) 取引コスト＆約定制限モデル
* 既存の「通常コスト 0.2% / 悲観コスト 1.2%」の二段階評価を維持しつつ [17]、高Turnover戦略に対するコストペナルティをシミュレーションに導入します [44]。

---

## 3. データ構造・暗号化スキーマ変更仕様

スナップショットの暗号化フォーマット（Fernet）および可逆性を維持したまま、スキーマバージョンを `report_schema_version = "2.1"` に更新します [11, 14]。

### 暗号化 JSON データ構造追加フィールド (Schema v2.1)

```json
{
  "strategy_version": "2.1.0",
  "report_schema_version": "2.1",
  "source_commit_sha": "b5a269987511a095cbfc18c93b6ff1f9b0a9a507",
  "scan_parameters": {
    "volume_surge_window_short": 20,
    "volume_surge_window_long": 250,
    "atr_period": 14,
    "atr_multiplier": 2.5
  },
  "candidates": [
    {
      "ticker": "XXXX.T",
      "classification": "EARLY_CANDIDATE",
      "scores": {
        "fundamental_score": 4.5,
        "volume_surge_ratio": 1.82,
        "proximity_to_52w_high": 0.98,
        "composite_score": 8.3
      },
      "indicators": {
        "atr_14": 125.5,
        "dynamic_stop_price_initial": 2350.0,
        "historical_max_drawdown_p90": 0.082
      }
    }
  ]
}
```

---
*作成日: 2026-09-09*
