# Trader プロジェクト関連文献・学術論文の概要まとめ (Literature Overview & Review)

日本株の短期変化点（Inflection）検知・ポジション管理を行う「**Trader**」の投資判断ロジックに関連する文献の要約と、2026-09-10時点でのリポジトリへの反映状況の評価。

`trader-enhancement-design.md` / `trader-enhancement-plan.md` はこの文献調査から派生した拡張案だったが、内容の大半が既存実装・既存計画（`memo/implement/roadmap.md`, `plan_req014.md`）と重複、またはリポジトリのデータ蓄積段階（shadow scan運用中、snapshot蓄積は1日分のみ）と整合しない時期尚早な提案だったため削除した。以下は各文献の要旨と、対応する現状のみを残す。

---

## 1. 日本市場における Post-Earnings Announcement Drift (PEAD) と流動性分析
* **文献:** 笠原 晃恭, Zhong Xin (2022)『日本市場における Post-Earnings Announcement Drift と流動性の分析』Osaka University Discussion Papers in Economics and Business, 21-25。
* **知見:** 決算サプライズ方向への株価ドリフトは流動性・サイズでは説明できない独立アノマリーとして存在。
* **現状:** ✅ 実装済み。`src/screening/inflection_live.py` のスコアリングが業績予想上方修正・営業利益成長・黒字転換・YoY比較（前年同期実績がある場合のみ）を既に評価している。

## 2. 株価モメンタムと出来高の関係
* **文献:** 三輪 宏太郎, 植田 一博 (2011)『株価モメンタムと出来高の関係と投資家の株価トレンド追随行為』人工知能学会 SIG-FIN。
* **知見:** 出来高急増を伴う値動きはトレンド追随行動によりモメンタムが持続しやすい。
* **現状:** ✅ 実装済み。`volume_ratio_20d`（閾値1.25/1.5）が既にスコアに統合されている。20日/250日窓への変更案は代替案の域を出ず、優先度は低い。

## 3. ベイズ分析による最適ストップロス閾値
* **文献:** Antoine E. Zambelli (2016) *Determining Optimal Stop-Loss Thresholds via Bayesian Analysis of Drawdown Distributions*, arXiv:1609.00869。
* **知見:** トレードの最大ドローダウン分布からベイズ法で最適ストップ幅を導出する「Rメソッド」。
* **現状:** ⚠️ 非推奨（時期尚早）。ベイズ推定には十分なトレード履歴が必要だが、snapshot蓄積は現状1日分のみ（`plan_req014.md`）。「評価ルールは結果を見る前に固定する」というリポジトリの原則（README）とも衝突するため、データが十分蓄積するまで着手しない。

## 4. トレイリングストップの効果（コモディティ市場）
* **文献:** Nam Nguyen / John Hua Fan, Tingxi Zhang (2023) *Fixed and Trailing Stop Losses in the Commodity Market*, Harbourfront Quantitative Finance。
* **知見:** ATR連動の動的トレイリングストップが固定ストップよりシャープレシオを改善。
* **現状:** 🟡 未実装・未計画。既存の10%/15%/20%固定ストップ比較（`scripts/rebuild_inflection_forward_validation.py`）に4つ目のバリアントとしてATRストップを加える形なら低リスクで筋が良い。ただしコモディティ市場の研究であり日本株個別銘柄への係数（k=2.5〜3.0）の直接転用は根拠薄弱な点に注意。優先度は`memo/implement/roadmap.md`のREQ-018/019/021・REQ-014より後。

## 5. 52週高値アノマリーとトレンドフォロー
* **文献:** Quantpedia / Cole Wilcox, Eric Crittenden (2005), Zarattini et al. (2024) *Does Trend-Following Still Work on Stocks?*
* **知見:** 52週高値付近の銘柄はアンカリング効果で情報織り込みが遅れ、超過リターンが持続。上位7%の「大化け株」が収益の大半を牽引。
* **現状:** ✅ 実装済み＋是正中。`near_52w_high`は実装済みで、命名・短期上場銘柄の扱い（上場来高値との混同）は`memo/implement/proposal.md`のREQ-018/030で是正作業中。Outlier寄与率などの追加集計は`plan_req014.md`のポートフォリオ指標（win_rate/profit_factor/median系）で概ねカバーされる。

---
*作成日: 2026-09-09 / 現状注記反映: 2026-09-10*
