# 実装要件書（memo/research 統合）

> このファイルは `memo/research/` 配下の3文書を統合・構造化したものです。
> `docs/implement/proposal.md` の代わりに `memo/implement/proposal.md` として作成しています。
> 各要件は「具体的な Before/After」「対象ファイル」「受入条件」を含みます。
> `/create-plan` を実行する場合は入力パスを `memo/implement/proposal.md` に読み替えてください。

## 入力元

| ファイル | 位置づけ |
|---|---|
| `memo/research/trader_remaining_issues_2026-09-09.md` | 現行実装の残存課題を P0〜P5 で整理した総合レビュー |
| `memo/research/deep-research-report.md` | `memo/analysis/literature_and_ops_review_2026-09-08.md` の妥当性検証・追加発見 |
| `memo/research/deep-research-report (1).md` | 上記の改訂版（ガバナンス・再現性を最優先に置いた `main` 反映実行計画） |

3文書は重複する指摘が多いため、本書では重複を統合し、3文書のいずれかが提示した固有の指摘も漏れなく要件化した。

---

## 要件一覧

### Phase 0: ガバナンス・実行基盤（他の全フェーズの前提）

### REQ-001: Shadow Scan が SNAPSHOT_ENCRYPTION_KEY 未設定で失敗している

- **画面/対象**: GitHub Actions `inflection_shadow.yml`
- **対象ファイル**: `.github/workflows/inflection_shadow.yml`（GitHub Secrets 設定）
- **Before（現状）**: `SNAPSHOT_ENCRYPTION_KEY` が Secrets 未設定のため `RuntimeError: SNAPSHOT_ENCRYPTION_KEY is required` で失敗し、`dashboard/data/inflection/` に `.gitkeep` しか存在せず実市場 snapshot が蓄積されていない。
- **After（期待）**: GitHub Secret 設定後、Shadow Scan が日次で成功し、`dashboard/data/inflection/YYYY-MM-DD.enc` が commit される。
- **受入条件**: 直近3営業日以上連続で Actions run が成功し、対応する `.enc` ファイルが増えていること。
- **備考**: Phase 2 以降の Forward Validation はすべてこのデータ蓄積が前提。

### REQ-002: main ブランチ無保護のまま Shadow Scan が直接 push している

- **画面/対象**: リポジトリ設定 + `.github/workflows/inflection_shadow.yml`
- **対象ファイル**: GitHub リポジトリ設定（Branch protection rules）、`.github/workflows/inflection_shadow.yml`
- **Before（現状）**: `main` にブランチ保護が無く、`contents: write` 権限の Shadow Scan workflow が `main` へ直接コミット・push（コミットメッセージに `[skip ci]` 付き）している。
- **After（期待）**: 生成データの push 経路を明確化する。少なくとも「なぜ直接 push が許容されるか（データのみでコードは変更しない等）」をrunbookに明記するか、専用ブランチ/PR経由に変更する。
- **受入条件**: 方針をドキュメント化し、直接 push を許容する場合はその理由と影響範囲（他PRとの衝突可能性、レビュー不能な変更が main に載る点）が明記されていること。
- **備考**: 優先度は高いが影響範囲の判断はユーザー確認が必要 `[要確認: 直接push運用を許容するか、PR経由に変更するか]`。

### REQ-003: GitHub Actions のバージョン固定が tag pin のみで supply-chain リスクがある

- **対象ファイル**: `.github/workflows/*.yml`
- **Before（現状）**: `actions/checkout@v7` 等、移動可能な tag で pin されている。transitive dependency の lock/hash、Dependabot も未設定。
- **After（期待）**: 少なくとも secrets を扱う workflow の Actions を full commit SHA pin に変更する。Dependabot を有効化する。
- **受入条件**: 対象 workflow 内の Actions 参照がすべて 40桁 SHA になっていること、`.github/dependabot.yml` が存在すること。
- **備考**: 優先度は中。個人プロジェクトでの費用対効果をユーザーと確認 `[要確認: 対応するかスキップするか]`。

---

### Phase 1: データ再現性・評価バイアスの是正（戦略変更より先に必須）

### REQ-004: Trailing Stop forward validation に右打切り（未成熟コホート）バイアスがある

- **対象ファイル**: `scripts/rebuild_inflection_forward_validation.py`、関連する trailing stop 集計ロジック
- **Before（現状）**: signal から60営業日未満でも早期 stop したケースは "completed trade" として集計されるが、stop せず保有継続中のケースは incomplete として除外される。そのため直近コホートは「早く損切りしたものだけ」が成績に反映され、下方に歪む。
- **After（期待）**: 共通の成熟日（例: signal_date から60営業日経過）を経たシグナル集合のみで trailing stop 成績を比較する。`eligible_count` / `censored_count` をレポートに出力する。
- **受入条件**: forward validation レポートに censoring 対応後の集計と対応前の集計が両方出力され、両者の差が説明可能であること。
- **備考**: 3文書中 `deep-research-report.md` が「最優先」と位置づける指摘。工数目安 4〜8時間。

### REQ-005: Forward validation とライブ Position Monitor の価格調整基準が不一致

- **対象ファイル**: forward validation 側の価格取得（`auto_adjust=True` 相当箇所）、`src/data/live_quote.py`（`auto_adjust=False` + split のみ手動補正）
- **Before（現状）**: forward validation は配当調整込み（`auto_adjust=True`）、本番 Position Monitor は分割のみ手動補正（`auto_adjust=False`）で、HWM/Stop 判定の基準系列が異なる。レポート上の "split_adjusted_ohlc" という記述も実態と不一致。
- **After（期待）**: `split_only` と `total_return_adjusted` を明示的な enum/定数として区別し、forward validation と Position Monitor で同一の価格基準（少なくとも意図を明示した上で意図的に別基準を使うなら文書化）に揃える。
- **受入条件**: 両パイプラインで使用する価格基準が定数/型として明示され、レポート内の表記が実装と一致すること。
- **備考**: `deep-research-report.md` が最優先級と評価。工数目安 6〜12時間。

### REQ-006: "immutable" が指すのは signal snapshot のみで、評価用の将来価格は再取得のたびに変わりうる

- **対象ファイル**: forward validation の価格取得ロジック全般
- **Before（現状）**: signal（買い候補）自体は暗号化 immutable snapshot として保存されるが、その後の評価に使う将来価格は rebuild のたびに yfinance から再取得しており、provider 側の事後訂正で過去の評価結果が変わりうる。
- **After（期待）**: 評価に使った OHLC 系列についても hash またはキャッシュを保存し、再計算結果が変化した場合に検知できるようにする。
- **受入条件**: 同一 signal 集合に対して2回 forward validation を実行した際、価格データが provider 側で変化していないことを検証するチェック（hash 比較）が存在すること。
- **備考**: `deep-research-report (1).md` の指摘。優先度「高」。

### REQ-007: yfinance 単独依存で cross-provider 検証がない

- **対象ファイル**: `src/data/`配下のデータ取得ロジック
- **Before（現状）**: coverage/staleness の fail-closed 検証はあるが、単一 provider が一貫して誤ったデータを返すケースを検出できない。
- **After（期待）**: J-Quants など別ソースとの突合（少なくとも定期サンプリングでの price diff チェック）を追加するか、当面は既知のリスクとして runbook に明記する。
- **受入条件**: cross-check の実装、またはリスク受容の方針をドキュメント化して合意すること。
- **備考**: 工数目安 8〜20時間（有償プラン検討含む）。`[要確認: 有償J-Quantsプランを導入するか]`。

---

### Phase 2: 評価設計の統計的強化

### REQ-008: 評価期間が 5/20/60 営業日までで短期に偏っている

- **対象ファイル**: `src/evaluation/inflection_forward.py`、`scripts/rebuild_inflection_forward_validation.py`
- **Before（現状）**: 主要評価が 5/20/60 営業日（約1週間〜3ヶ月）まで。
- **After（期待）**: 126営業日（約6ヶ月）・252営業日（約1年）を評価horizonに追加する。
- **受入条件**: forward validation レポートに 126日・252日列が追加され、値が算出されること。

### REQ-009: Trailing Stop の検証も60営業日で打ち切られ、実運用の無期限保有と乖離している

- **対象ファイル**: `scripts/rebuild_inflection_forward_validation.py`（trailing stop シミュレーション部）
- **Before（現状）**: Trailing Stop（10/15/20%）の評価が最大60営業日で打ち切られる。
- **After（期待）**: 60/126/252営業日で比較評価する（REQ-004 の成熟コホート対応と合わせて実施）。
- **受入条件**: 3horizon分のTrailing Stop成績（10/15/20% × 60/126/252日）がレポートに出力されること。

### REQ-010: Explosion Recall / Detection Lead Time が測定されていない

- **対象ファイル**: `src/evaluation/inflection_forward.py`（新規指標追加）
- **Before（現状）**: 「候補になった株がその後上がったか」は見ているが、「実際に爆発した株のうち何%を事前に検出できたか」を測っていない。
- **After（期待）**: `Explosion Recall = 事前検出できた爆発銘柄数 / 実際に爆発した銘柄数`、`Detection Lead Time = 初回candidate日から+50%到達日までの日数` を新規指標として追加する。
- **受入条件**: forward validation レポートに両指標が出力され、値が算出されること。

### REQ-011: WATCH 分類が対照群として使われていない

- **対象ファイル**: `src/evaluation/inflection_forward.py`
- **Before（現状）**: forward validation のデフォルト対象は `EARLY_CANDIDATE` のみ。
- **After（期待）**: `EARLY_CANDIDATE` / `WATCH` / `NONE からのサンプル` を分けて追跡し、EARLYがWATCHより優位かを比較できるようにする。
- **受入条件**: レポートに3群の成績が併記されること。

### REQ-012: 統計的信頼性（信頼区間・多重検定対応）が不足している

- **対象ファイル**: `src/evaluation/inflection_forward.py`
- **Before（現状）**: 平均・中央値・勝率・Profit Factor等のみで、サンプル数が少なくても高成績に見えうる。
- **After（期待）**: sample count、bootstrap confidence interval、日付/銘柄間の依存を考慮した集計、score band別・regime別のサンプル数を追加する。複数パラメータ比較（horizon×stop幅など）を行う場合は multiple-testing の注意書きを出力する。
- **受入条件**: レポートに「n=X, 95% CI = a%〜b%」の形式で少なくとも主要指標の信頼区間が出力されること。

### REQ-013: Peak Capture Ratio / Peak Giveback / Early Exit Return が測定されていない

- **対象ファイル**: `src/evaluation/inflection_forward.py` または `src/evaluation/inflection_backtest.py`
- **Before（現状）**: 最高値からどれだけ利益を残して売れたか、売却後にさらに上がったかを評価していない。
- **After（期待）**: `Peak Giveback = (Peak Price - Exit Price) / Peak Price`、`Peak Capture Ratio = Realized Profit / MFE`（MFE正の取引のみ）、Exit後5/20/60日Returnを追加する。
- **受入条件**: 各指標がレポートに出力されること。

### REQ-014: ポートフォリオレベルの評価がなく `portfolio_interpretation: False` のまま

- **対象ファイル**: `src/evaluation/inflection_backtest.py`、新規 portfolio simulator
- **Before（現状）**: 個別 trade の成績のみで、最大同時保有数・資金配分・セクター集中・Drawdown・Equity Curveが未実装。backtest自身が `portfolio_interpretation: False` と明記している。
- **After（期待）**: 初期資金・最大position数・position sizing・セクター上限・現金制約を考慮した portfolio simulation を追加し、CAGR・Max Drawdown・Equity Curve・Turnover・Win Rate・Profit Factorを算出する。
- **受入条件**: portfolio simulation の実行結果がレポート/dashboardに出力されること。
- **備考**: 工数目安 16〜40時間。3文書中で最も工数の大きい要件。

### REQ-015: TOPIX と個別株に同一の取引コストを適用しており excess return が歪む

- **対象ファイル**: `src/evaluation/inflection_backtest.py`（コスト計算部）
- **Before（現状）**: ベンチマーク（TOPIX ETF）と個別Growth株に同じ往復コストを適用している。
- **After（期待）**: `Benchmark cost` / `Individual stock normal cost` / `Individual stock stress cost` を分離する。
- **受入条件**: レポートに3種のコストシナリオ別の結果が出力されること。

### REQ-016: Trailing Stop 自体に paired benchmark 比較がない

- **対象ファイル**: `src/evaluation/inflection_backtest.py`
- **Before（現状）**: Trailing Stop（10/15/20%）は raw summary 中心で、同一 entry〜実際の exit 日までの TOPIX 超過リターンと比較していない。
- **After（期待）**: 各 trade について同一期間の TOPIX (1306.T) リターンとの差分を算出し、stop 幅ごとに paired 比較する。
- **受入条件**: レポートにstop幅別の paired benchmark excess が出力されること。

---

### Phase 3: 買い候補発見ロジックの改善

### REQ-017: Top25 のみ財務分析対象で、初動が小さい優良銘柄を取りこぼす可能性がある

- **対象ファイル**: `src/screening/inflection_live.py`（`deep_candidates: int = 25`, L271, `preselected[:deep_candidates]` L308）
- **Before（現状）**: 全市場を価格・出来高で一次選別後、デフォルト25銘柄のみ財務分析する。業績急改善でも値動きが小さい銘柄は上位に入らず財務分析すらされない可能性がある。
- **After（期待）**: `deep_candidates` を 25/50/100/200 で比較し、Explosion Recall と実行時間のトレードオフを検証した上で値を見直す。
- **受入条件**: 4パターンの比較結果（Recall・処理時間）がレポート化され、採用値が決定されること。

### REQ-018: 新規上場銘柄（65営業日未満）が完全に候補対象外になっている

- **対象ファイル**: `src/screening/inflection_live.py` の `_technical_features()`（`if len(close) < 65: return None`）
- **Before（現状）**: IPO後65営業日未満の銘柄は候補に入らず、上場初期の爆発的値動きを完全に取り逃す。また65〜251営業日の銘柄の `breakout_52w` は実際には「取得可能期間中の最高値（実質上場来高値）」であり「52週高値」ではない。
- **After（期待）**: 新規上場銘柄向けの別ルールを追加する。`near_52w_high` と `near_listing_high` を区別するフィールド/変数名に変更する。
- **受入条件**: 65営業日未満の銘柄が別ロジックで候補判定され、`near_listing_high` フラグが出力に含まれること。変数名 `breakout_52w` が実態に即した名称に変更されていること（呼び出し元含む）。

### REQ-019: スコアの意味が二重化しており閾値も汎用ロジックとライブで異なる

- **対象ファイル**: `src/strategy/inflection.py`（理論スコア）、`src/screening/inflection_live.py`（`EARLY_CANDIDATE_SCORE = 70.0` L25、正規化スコア）
- **Before（現状）**: 汎用側は `strong_candidate >= 75` / `watch >= 60`、ライブ側は `EARLY_CANDIDATE >= 70` / `WATCH >= 52`。ライブは利用可能項目のみ（最大58点）を100点換算しており、同じ `score=70` でも意味が異なる。
- **After（期待）**: `raw_inflection_score` と `live_normalized_score` を明確に区別する命名にし、classification関数を一本化するか名称を明示的に分ける。
- **受入条件**: 2つのスコアが型/フィールド名で区別可能になり、混同を防ぐコメント/docstringが付与されること。

### REQ-020: EARLY_CANDIDATE の閾値（70点）とスコア重みが未検証

- **対象ファイル**: `src/screening/inflection_live.py`、`src/strategy/inflection.py`
- **Before（現状）**: `EARLY_CANDIDATE_SCORE = 70.0` を含む閾値・配点（営業利益急増10点、黒字転換5点、出来高7点、52週高値6点等）はヒューリスティックで実証されていない。
- **After（期待）**: score band別（50-59/60-69/70-79/80-89/90+）の 20d/60d/126d/252d 成績・爆発率・TOPIX超過を評価する。Feature Ablation（Volumeなし/52週高値なし/業績成長なし/上方修正なし）で寄与度を検証する。
- **受入条件**: score band別テーブルと Feature Ablation の結果がレポート化されること。

### REQ-021: 市場区分別（Prime/Standard/Growth）のデータカバレッジが可視化されていない

- **対象ファイル**: shadow scan のデータ健全性チェック部分
- **Before（現状）**: 全市場合計でのみ price/technical/latest-date coverage を判定しており、市場区分別の欠損（例: Growth 30%）が閾値超過に隠れうる。
- **After（期待）**: Prime/Standard/Growth別に coverage を個別保存・health check する。
- **受入条件**: health check 出力に市場区分別の coverage 数値が含まれること。

### REQ-022: 絶対リターン型モメンタムの相対化（TOPIX/業種相対）を検証なしに採用すべきでない

- **対象ファイル**: `src/strategy/inflection.py`（モメンタムスコア算出部）
- **Before（現状）**: 現行は20日・60日の絶対リターン閾値（3/8/15%、5/15/30%）でモメンタムを加点している。`memo/analysis/literature_and_ops_review_2026-09-08.md` はTOPIX/業種相対化を最優先と結論しているが、日本市場では国際比較上モメンタムプレミアムが弱いという先行研究（Fama & French 2012）があり、米国研究のみを根拠に本番へ即反映するのは時期尚早。
- **After（期待）**: `absolute` / `TOPIX-relative` / `industry-relative rank` の3方式を別 `STRATEGY_VERSION` として同一 snapshot 上で shadow A/B/C 比較する。相対化は検証結果が出るまで本番反映しない。
- **受入条件**: 3方式が同一日付集合でshadow実行され、比較結果（forward validation指標）が出力されること。
- **備考**: 工数目安 12〜24時間。REQ-004/005（評価バイアス是正）の完了を前提とする。

---

### Phase 4: Exit Monitor（保有銘柄監視）の改善

### REQ-023: 当日の High がトレーリングストップの HWM に反映されず、日中の急騰後急落を捕捉できない

- **対象ファイル**: `src/monitoring/position_exit.py`、`src/data/live_quote.py`
- **Before（現状）**: HWM は `entry_price` または前日までの確定 High のみを使用し、当日の日中高値は無視される。例: 昨日までのHWM 1,000円、当日11:00に1,500円→14:00に1,200円 の場合、15% Trailingなら本来 1,275円付近が売却候補になるべきだが、現状は 850円のまま何も通知されない。
- **After（期待）**: 1分足を時系列順に処理し、各バーでHWM更新→次バーでStop判定、を行うことで未来情報を使わずに当日HWMを反映する。
- **受入条件**: 日中に高値を更新した銘柄で、その日のうちにHWM更新後のTrailing Stop水準に基づいた通知判定が行われること（テストで時系列データを与えて検証）。

### REQ-024: Exit Monitor の stale quote 許容が60分と長すぎる

- **対象ファイル**: `src/data/live_quote.py`（`STALE_QUOTE_THRESHOLD_MINUTES = 60`）
- **Before（現状）**: 15:35時点で14:40のデータでも正常扱いされ得る。
- **After（期待）**: セッション中（寄付き〜大引け）はより厳しい鮮度基準（例: 5〜10分）に見直す。実際のデータソースの遅延特性を確認した上で確定する。
- **受入条件**: `STALE_QUOTE_THRESHOLD_MINUTES` がセッション中/セッション外で分離され、セッション中の値が現行の60分より短く設定されること。
- **備考**: 具体的な分数は要検証 `[要確認: 5分か10分か、データ提供元の実測遅延を見て決定]`。

### REQ-025: 同一トリガーが1日に複数回（09:03/12:35/15:35）通知されうる

- **対象ファイル**: `src/monitoring/position_exit.py`、通知状態を保持するストア（新規 or 既存Sheets）
- **Before（現状）**: 各実行時点で条件が成立していれば毎回Slack通知される。永続的な「前回通知済み」状態を持たない。
- **After（期待）**: 状態遷移ベース（`false → true` になった時のみ通知）に変更する。`triggered_at` / `last_notified_at` / `trigger_reason` を台帳に保存する。
- **受入条件**: 同一トリガーが解除されないまま2回目の実行が走っても、2回目は通知されないこと（テストで検証）。

### REQ-026: Google Sheets の status 書き込みが非原子的（clear→update の2段階）

- **対象ファイル**: `src/data/sheets_client.py`（`write_status()` 相当）
- **Before（現状）**: `clear()` の後に別APIコールで `update()` するため、途中で失敗すると status sheet が一時的に空になる。
- **After（期待）**: Google Sheets API の `spreadsheets.batchUpdate`（atomic）またはstaging sheet経由のswap方式に変更する。
- **受入条件**: 書き込み中に例外を発生させても既存の status sheet 内容が失われないこと（テストで検証）。
- **備考**: 工数目安 2〜6時間、費用対効果が高い。

### REQ-027: 実売買の履歴（Trade Ledger）が残らない

- **対象ファイル**: `src/data/sheets_client.py`、`src/monitoring/position_exit.py`（新規台帳スキーマ）
- **Before（現状）**: 「状況」シートは現在値ダッシュボードのみで履歴を持たず、どの通知で買い/売りしたか、実際の約定価格、通知から約定までの時間を後から評価できない。
- **After（期待）**: `ticker, signal_id, candidate_date, notification_at, entry_order_at, entry_fill_at, entry_price, exit_signal_at, exit_fill_at, exit_price, exit_reason, realized_return, max_mfe, max_mae, peak_giveback` を持つ Trade Ledger を追加する。
- **受入条件**: 新規シート/テーブルにこれらのフィールドが記録され、少なくとも1件のダミートレードで読み書きが確認できること。

### REQ-028: GitHub Actions の schedule を Exit Monitor の定刻実行として扱っている

- **対象ファイル**: `.github/workflows/position_monitor.yml`、関連runbook
- **Before（現状）**: 2026-09-08 の Shadow Scan で予定16:40 JST に対し実行開始が約21:16 JSTと大幅遅延した実績があり、GitHub公式も高負荷時のschedule遅延・job drop の可能性を明記している。Exit Monitorを「必ずその時刻に動く売買安全装置」として扱うのは不適切。
- **After（期待）**: Exit Monitor は「best-effort alert」であり、注文タイミングの保証をしないことをrunbookに明記する。より定刻性が必要になった段階で常駐プロセス等への移行を検討する旨も記載する。
- **受入条件**: README/runbookに best-effort である旨の明記が追加されること。

---

## 繰り返し失敗している要件

該当なし（`memo/research/` 内に「改善されていない」「N回目」等の再試行失敗パターンの記述は見つからなかった）。

---

## Deep Research 文書内の記述修正（文献解釈・現状記述の誤り）

### REQ-029: Jegadeesh & Titman (1993) が「同業種内相対順位」として誤って引用されている

- **対象ファイル**: `memo/analysis/literature_and_ops_review_2026-09-08.md`（引用元）
- **Before（現状）**: 同論文を「同業種内の相対順位でモメンタムを測定する研究」と説明している。
- **After（期待）**: J&T (1993) は過去の個別株 winner/loser によるクロスセクショナル・モメンタム戦略であり、「業種モメンタム」を扱うのは Moskowitz & Grinblatt (1999) であると訂正する。
- **受入条件**: 該当箇所の文献引用が訂正され、TOPIX/業種相対化の論拠が「J&Tに忠実だから」ではなく「market-beta除去の実務的候補」という表現に修正されること。

### REQ-030: "52週高値ブレイクアウト" という表現・変数名が実装と不一致

- **対象ファイル**: `src/screening/inflection_live.py`（`breakout_52w`）、関連ドキュメント
- **Before（現状）**: コードは `current >= high52 * 0.99` であり「52週高値から1%以内」に近いが、"ブレイクアウト" と呼称している。
- **After（期待）**: 変数名・ドキュメント表記を `near_52w_high` に変更する（REQ-018 と連動）。George & Hwang (2004) は "52週高値への近さ" を扱う研究であり、直接的裏付けは "近さ" の部分のみである旨を明記する。
- **受入条件**: コード変数名とドキュメント記述が一致すること。

### REQ-031: 出来高研究が「反転リスク」として単純化されている

- **対象ファイル**: `memo/analysis/literature_and_ops_review_2026-09-08.md`
- **Before（現状）**: 出来高増加を反転リスクとしてのみ説明している。
- **After（期待）**: Lee & Swaminathan 等は turnover水準とモメンタム持続性/反転の両方を扱うとし、`Return × Volume × Holding Horizon` の相互作用として記述を改める。
- **受入条件**: 該当箇所が「単独で良い/悪いと決めつけない」表現に修正されること。

### REQ-032: Piotroski / PEAD の引用が Trader の実装を直接裏付けているかのように書かれている

- **対象ファイル**: `memo/analysis/literature_and_ops_review_2026-09-08.md`
- **Before（現状）**: 上方修正・黒字転換・営業利益改善がPEAD/Piotroskiに「整合」と表現されている。
- **After（期待）**: Piotroski F-score は高Book-to-Market銘柄のValue Investing研究でありTraderの「爆発前inflection」の直接的根拠ではない点、PEADはJ-Quants Freeの12週遅延により「決算発表直後のPEAD」とは言えない点を明記し、「方向性が近い／直接的根拠／参考程度」の3段階で整理し直す。
- **受入条件**: 該当引用が3段階のいずれかに分類され直され、過大な表現が修正されること。

### REQ-033: memo 文書が現行実装に追いついておらず「未実装」と誤記載している箇所がある

- **対象ファイル**: `memo/trader_exit_strategy_research.md`、`memo/project-overview.md`、`memo/analysis/*`
- **Before（現状）**: `memo/trader_exit_strategy_research.md` に「Position Exit Monitorは計画済み・未実装」という記述が残っているが、実際には `scripts/run_position_monitor.py` が実装済み。
- **After（期待）**: `未実装 / 実装済み / 検証中 / 本番採用` の4段階で状態表記を統一し、該当箇所を更新する。
- **受入条件**: 上記3ファイル内の実装状況記述が現状（`scripts/run_position_monitor.py` 実装済み含む）と一致すること。

### REQ-034: yfinance が「非公式スクレイピング系ライブラリ」と誤って説明されている

- **対象ファイル**: `memo/analysis/literature_and_ops_review_2026-09-08.md`
- **Before（現状）**: 「非公式スクレイピング系ライブラリ」と記述。
- **After（期待）**: yfinance公式説明に合わせ「Yahoo非公式・非保証のpublic API wrapper、personal use前提」と訂正する。合わせて、個人研究を超える用途を想定する場合は利用条件を確認する旨を追記する。
- **受入条件**: 該当箇所の表現が修正されること。

### REQ-035: 09:03 JST の板品質に関する記述の根拠が不十分

- **対象ファイル**: `memo/analysis/literature_and_ops_review_2026-09-08.md`
- **Before（現状）**: 「寄り付き直後は板が薄く/歪みやすいので始値が信頼できない」と記述。
- **After（期待）**: 東証は板寄せ方式で始値を決定するため「始値自体の品質が低い」という説明を修正し、「寄付き3分後で観測期間が短いこと、および1分足provider・freshnessへの依存が大きいこと」を問題の本質として記述し直す。
- **受入条件**: 該当箇所の記述が訂正されること。

---

## 完了済み・保留中

### 完了済み
- Position Exit Monitor（`scripts/run_position_monitor.py`）の実装自体（一部memoの記述が追いついていない: REQ-033で対応）
- Point-in-time設計、暗号化 immutable snapshot、strategy/schema version管理、benchmark比較、High/LowベースMFE/MAE、gap考慮のTrailing Stop、fail-closedなデータ検証（3文書とも高評価。追加改修は不要、現状維持）

### 保留中（今回のスコープ外・要ユーザー判断）
- J-Quants 有償プラン（Light/Standard/Premium）への切り替え検討（REQ-007関連）`[要確認]`
- 実売買のSlack通知からSBI証券への自動発注（本プロジェクトは手動売買前提のためスコープ外と想定）`[要確認: 引き続き手動売買前提でよいか]`
- Promotion条件（research candidate → validated buy candidate への昇格基準）の具体的数値の確定 — Phase 1〜4完了後に改めて検討

---

## 推奨する対応順（3文書の統合見解）

1. **Phase 0（ガバナンス・実行基盤）**: REQ-001〜003 — 特にREQ-001はREQ-008以降すべての前提
2. **Phase 1（評価バイアス是正・再現性）**: REQ-004〜007 — 戦略ロジック変更（REQ-022等）より必ず先に実施
3. **Phase 2（統計的評価強化）**: REQ-008〜016
4. **Phase 3（買い候補ロジック改善）**: REQ-017〜022
5. **Phase 4（Exit Monitor改善）**: REQ-023〜028
6. **文書修正（随時）**: REQ-029〜035 — コード変更を伴わないため他フェーズと並行実施可能

概算総工数（3文書中に工数記載があるもののみ合算、REQ-004,005,022,014,026,007等): 約24〜36 engineer-days（`deep-research-report (1).md` による見積り）。

---

## 次のステップ

`/create-plan` を実行する場合、本ファイル（`memo/implement/proposal.md`）を入力として渡してください（標準の `docs/implement/proposal.md` ではない点に注意）。要件数が多いため、Phase単位で分割して `/create-plan` を回すことを推奨します。
