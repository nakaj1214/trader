# Trader プロジェクト調査レポート（コード/運用の再検証 + 判断ロジックの文献照合）

調査日: 2026-09-08

対象: 現在の JP inflection shadow scan、Position Exit Monitor（`src/`, `scripts/`, `.github/workflows/`）

## 結論

既存レビュー（[`codex_review.md`](codex_review.md)、[`code_and_ops_review_2026-09-08.md`](code_and_ops_review_2026-09-08.md)、[`fix_verification_2026-09-08.md`](fix_verification_2026-09-08.md)）の指摘は実コードとの突き合わせで**全件修正済み**であることを確認した（`pytest` 119件全パス、カバレッジ91%、ruff/mypyクリーン）。今回はその上で、(1) 直近コミット（Position Exit Monitor / Slack通知）を含めた残存の問題点の再確認、(2) スコアリング・Exit戦略の判断根拠を金融文献・公式資料と照合する調査を行った。

## コード上の問題点（現状）

### モメンタムスコアが絶対リターン閾値方式（重要度: 中）

[`src/strategy/inflection.py:102-117`](../../src/strategy/inflection.py#L102-L117) の `return_20d` / `return_60d` は、市場全体との相対値ではなく絶対%閾値で加点する。強気相場では大半の銘柄が閾値を通過し、弱気相場ではほぼ誰も通過しない設計になっており、「銘柄固有の変化」と「市場全体のトレンド」を分離できない。詳細は下記「学術的妥当性チェック」を参照。

### 株式分割時のVolume歪みが未解決（重要度: 低、既知）

`fix_verification_2026-09-08.md` で既知の残存事項。`yf.download(..., actions=False)` のため分割イベントを検知できず、分割直後~20営業日は `volume_ratio_20d` が機械的に歪む可能性がある。頻度が低いイベントであり、優先度は低いままでよい。

### yfinance単独依存（重要度: 中、既知）

価格取得を非公式スクレイピング系ライブラリに全面依存している。障害検知の代替経路だった `compare_close_series` は死んでいたため削除済みで、現状は「yfinanceが部分的に壊れて古い/誤ったデータを返し続ける」ケースを検知する手段がない。

### `STRATEGY_VERSION` 変更時の運用手順が未整備（重要度: 低、既知）

バージョン間のsnapshotをfail closedにする実装（`inflection_forward.py`）はあるが、切替時に旧versionのsnapshotをどう退避するかのrunbookがない。

## 運用上の問題点

### forward validationの結果を確認する運用が定着していない

`.github/workflows/forward_validation.yml` は週次でsummaryを `actions/upload-artifact`（90日保持）にアップロードするようになったが、それを人が定期的に確認する運用フロー（カレンダーリマインダー等）は文書化されていない。仕組みはあるが、見る習慣が定着しなければ実質的に機能しない。

### Position Exit Monitorのアラート重複が未対策

[`scripts/run_position_monitor.py:160`](../../scripts/run_position_monitor.py#L160) に `ponytail:` コメントで明記されている通り、1日3回（09:03 / 12:35 / 15:35 JST）の各実行でTrailing Stop条件が継続して成立していると、毎回同じ銘柄でSlack通知が飛ぶ。現状「実行本数が少ないから許容」という判断だが、保有銘柄数が増えると通知疲れのリスクがある。永続的な重複排除（例: 状況シートに前回triggered状態を保存し、状態遷移時のみ通知）を検討する価値がある。

### Google Sheetsの書き込みが非原子的

[`src/data/sheets_client.py:55-56`](../../src/data/sheets_client.py#L55-L56) の `write_status()` は `clear()` → `update()` の2段階のため、実行途中でクラッシュすると台帳（状況シート）が空になる時間帯が発生し得る。これも `ponytail:` コメントで既知の簡易実装として明記されている。

### 寄り付き直後のTrailing Stop判定の質

09:03 JST実行は寄り付き直後で板が薄く/歪みやすい時間帯であり、この時点の「今日の始値」を使ったStop判定は他の2回（12:35・15:35）より信頼度が下がりうる。best-effort運用として明記済みだが、寄り付き直後のtriggeredはより慎重に扱う旨を通知文言に含めることを検討してもよい。

## 判断ロジックの学術的妥当性チェック

候補選定・スコアリング・Exit戦略の判断根拠を、信頼できる金融文献・公式資料と照合した。

| ロジック | 該当箇所 | 評価 |
|---|---|---|
| 52週高値ブレイクアウト加点 | `breakout_52w` | **整合**。George & Hwang (2004) *"The 52-Week High and Momentum Investing"* は52週高値からの近さが伝統的モメンタムより強い予測力を持つと報告しており、直接的な裏付けがある |
| 20日/60日モメンタム加点 | `return_20d` / `return_60d` | **一部不整合**。Jegadeesh & Titman (1993) の古典的モメンタム研究は「同業種内の相対順位（クロスセクショナル）」でモメンタムを測定する。本ロジックは**絶対リターン閾値**であり、市場全体の地合い（ベータ）と銘柄固有モメンタムを分離できていない。相対リターン化（TOPIX比較）がより文献に忠実 |
| 極端な急騰への減点（20日+80%以上、OVEREXTENDED判定） | `extreme_runup_penalty`, `_classify` | **整合**。Jegadeesh (1990) や Lehmann (1990) の短期リバーサル研究は、極端な短期急騰が部分的に反転する傾向を示しており、方向性は妥当。ただし50%/80%/100%という具体的閾値自体は学術的に較正されたものではなくヒューリスティック |
| 出来高急増への加点 | `volume_ratio` | **要注意**。Lee & Swaminathan (2000) の "momentum life cycle" 仮説では、出来高を伴う急騰銘柄はむしろ将来の反転（グラマー化）リスクが高いとされ、本ロジックの「出来高増加=常に加点」という単純な扱いとは緊張関係がある |
| 上方修正・黒字転換・営業利益加速への加点 | `_fundamental_features`, fundamental score | **整合**。PEAD（Bernard & Thomas 1989）や Piotroski F-score (2000) が示す「業績モメンタム・キャッシュフロー健全性の改善が将来リターンを予測する」という知見と方向性が一致する |
| Trailing Stop（HWM基準、確定High起点） | `position_exit.py`, `inflection_backtest.py` | **整合、かつ検証方針も妥当**。Kaminski & Lo (2014) *"When Do Stop-Loss Rules Stop Losses?"* は、トレイリングストップの有効性が資産のトレンド性/平均回帰性に強く依存し、レジームによって結果が反転しうることを示した。プロジェクト自身が「優位性確認までは検証用アラート」と位置付けている姿勢は、この文献の含意と整合的 |
| 流動性フィルタ（売買代金1億円以上） | `min_turnover_jpy` | **整合**。Amihud (2002) の非流動性指標研究などが示す通り、低流動性銘柄は価格インパクト・約定不能リスクが高く、フィルタ自体は標準的な実務 |
| 税率20.315%（税引前をデフォルト表示） | `tax_rate_pct` | **事実として正確**。日本の株式譲渡益課税（申告分離課税）の実際の税率（所得税15.315%+住民税5%）と一致 |
| Point-in-time設計全般（YoYを厳密に前年同期のみ、財務データの12週遅延明記、前日確定Highのみ使用） | 複数箇所 | **整合、良好な設計**。ルックアヘッドバイアス回避は定量分析の文献（López de Prado *Advances in Financial Machine Learning* 等）が繰り返し警告する最重要の落とし穴であり、本プロジェクトは意識的に対策している |
| 制限値幅・板厚を考慮しないExit検証 | [`trader_exit_strategy_research.md`](../trader_exit_strategy_research.md) §10 | 既にJPX公式資料（[制限値幅](https://www.jpx.co.jp/equities/trading/domestic/06.html)）を引用済みで対応方針が明記されており、追加指摘なし |

### 最も重要な指摘

**モメンタムスコアを絶対リターンではなく相対リターン（対TOPIXまたは業種平均）にすべき**という点が、学術的観点から見た最大のギャップである。現状の設計では、forward validationがTOPIX比較で「優位性」を測っているにもかかわらず、シグナル生成側は市場全体の上昇局面をそのまま銘柄固有シグナルとして拾ってしまう可能性があり、両者の整合性（市場ベータ由来の見かけ上の優位性ではないか）を切り分けられない。forward validationの結果を見る際は、対TOPIXの超過リターンだけでなく、**市場全体が上昇していた期間かどうか**を層別して確認することを推奨する。

## 優先度まとめ

1. モメンタムスコアの相対リターン化（対TOPIX/業種平均）を検討し、forward validation結果を市場地合い別に層別する
2. Position Exit Monitorのアラート重複排除（状態遷移時のみ通知）
3. yfinance単独依存のリスク軽減策（監視強化 or 代替ソース検討）
4. `STRATEGY_VERSION` 切替時のrunbook整備
5. 分割時のVolume歪み、Google Sheets書き込みの非原子性は優先度低のまま許容可能

## 検証

- `pytest tests/`: 119 passed、coverage 91.03%
- `ruff check src scripts tests`: PASS
- `mypy --ignore-missing-imports`: PASS（既存レビュー時点から変化なし）

## 参考文献・一次情報

- Jegadeesh, N., & Titman, S. (1993). *Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency.*
- Jegadeesh, N. (1990). *Evidence of Predictable Behavior of Security Returns.*
- Lehmann, B. (1990). *Fads, Martingales, and Market Efficiency.*
- George, T. J., & Hwang, C.-Y. (2004). *The 52-Week High and Momentum Investing.*
- Lee, C. M. C., & Swaminathan, B. (2000). *Price Momentum and Trading Volume.*
- Bernard, V., & Thomas, J. (1989). *Post-Earnings-Announcement Drift.*
- Piotroski, J. D. (2000). *Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers.*
- Kaminski, K., & Lo, A. W. (2014). *When Do Stop-Loss Rules Stop Losses?*
- Amihud, Y. (2002). *Illiquidity and Stock Returns: Cross-Section and Time-Series Effects.*
- López de Prado, M. (2018). *Advances in Financial Machine Learning.*
- [JPX 制限値幅](https://www.jpx.co.jp/equities/trading/domestic/06.html)
- 国税庁: 上場株式等の譲渡益に対する税率（申告分離課税 20.315%）

本レポートは技術的な調査と学術的な整合性チェックであり、投資助言や売買成果を保証するものではない。文献は方向性の裏付けとして参照しており、閾値そのもの（50%/80%/100%等）の最適性を検証したものではない。
