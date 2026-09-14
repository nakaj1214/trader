<!-- 別ブランチ origin/feat/self-learning-postmortem にある自己改善学習機能（inflection self-learning postmortem）が
mainブランチに実装されているか調査した結果、未実装だと判明した。この機能をmainに統合したい。

機能の概要（ブランチのコミット・コードから確認済み）:
- src/evaluation/inflection_learning.py: 暗号化snapshot群から過去の deep-scan candidate（EARLY_CANDIDATE以外も含む）を読み込み、
  5/20/60/120営業日後の実績（TOPIX相対の超過リターン、爆発的上昇の有無、予測ミス理由）を事後評価する。
  factor（classification/market/score帯/リターン帯/出来高帯/reasonsなど）ごとに統計を取り、
  最新strategy_versionのデータだけを対象に「昇格候補」を判定するが、本番の戦略重み・スコアリングは自動更新しない
  （次期strategy versionへの提案としてのみ記録する設計）。
- scripts/rebuild_inflection_learning.py: yfinanceからバッチで価格を取得し、上記の学習レポートを生成してartifact/dashboardへ出力する。
- 週次のCIから呼び出す想定（forward_validationと同様の運用）。

ブランチは2026-09-08にmainから分岐し2026-09-09で開発が止まっており、以降のmainの変更（REQ-018でのv3 snapshot分離、
near_52w_high/near_listing_highへのフィールド分割、REQ-014のポートフォリオ評価など）を反映していない。
そのままマージはできないため、現行mainの構造に合わせて機能を移植する形で要件化してほしい。

依存関係の事前調査結果:
- simulate_signal, BENCHMARK_TICKER, benchmark_returns_by_signal_date, SnapshotLoadError は現行mainの
  src/evaluation/inflection_backtest.py, inflection_forward.py にそのまま存在する（互換）。
- ただしブランチのコードは candidate に breakout_52w フィールドがある前提だが、現行mainは
  near_52w_high / near_listing_high に分割済みで breakout_52w は存在しない（要修正）。
- ブランチのコードは snapshot を dashboard/data/inflection/*.enc 直下から読む前提だが、現行mainは
  REQ-018以降 dashboard/data/inflection/v3/ 配下に保存している（v2との非連続性も既知）。パス・バージョン対応の修正が必要。
- CIワークフローへの新規配線（forward_validation.ymlに相乗りするか専用workflowにするか）は未確定。
-->