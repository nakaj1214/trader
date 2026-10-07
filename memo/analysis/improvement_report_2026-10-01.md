# Trader 改善提案レポート（コード・機能・理論）

調査日: 2026-10-01
対象: `main`（`f3678c2`）の現行経路。対象は JP inflection shadow scan、forward validation、自己学習、ポートフォリオ評価、Position Exit Monitor。
依頼元: [memo/implement/prompt.md](../implement/prompt.md) 3行目

## 0. 結論

1. **前回レビューで出た P1/P2 はすべて修正済み**（詳細は §1）。`pytest` 264件がすべて通り、カバレッジは 91.93%。`ruff` も PASS。コードの品質は高く、point-in-time 設計（先読みを防ぐ設計）も徹底されている。
2. 一方で、**プロジェクトの目的（予測とタイミングをユーザに伝える）と現状との間に大きな欠落が2つ**ある。
   - 候補は暗号化 snapshot に保存されるだけで、**ユーザが候補を見る手段も通知もない**（§2-A1）。
   - 売却側は **固定 15% の Trailing Stop だけ**で、「利益を最大化する手放し時」を支援する仕組みがない（§3-B3）。
3. **データ蓄積の設計には、今すぐ直さないと取り返せない損失が1つある**。snapshot には財務の数値特徴量、スコア内訳、開示日が保存されていない。そのため、後から「どの財務要因が効いたか」を学習できない（§2-A2）。1日遅れるごとに学習材料が失われるため、最優先で直すべき。
4. 「蓄積待ち」を短縮できる。J-Quants Free の過去データ（約2年分、12週遅延）を使えば、**戦略全体の point-in-time 過去検証を今すぐ実行できる**（§3-B1）。forward shadow（実運用と並行した記録）は、その検証に対する out-of-sample（検証に使っていないデータでの）確認として位置付け直すのがよい。

優先度の凡例: **P0** = 目的達成や学習データの取得に直結するため即対応。**P1** = 近いうちに壊れる、または結論を誤らせる。**P2** = 改善推奨。**P3** = 軽微。

---

## 1. 既知指摘の現状確認（修正済みのもの）

| 既知指摘（出典） | 現状 |
|---|---|
| 赤字予想の悪化を上方修正として加点（codex_review P1） | 修正済み。[inflection_live.py:228](../../src/screening/inflection_live.py#L228) で `(new-old)/abs(old)` を使用 |
| Trailing Stop が最大保有日前に確定しない（同 P1） | 修正済み。[inflection_backtest.py:132-173](../../src/evaluation/inflection_backtest.py#L132-L173) |
| 配当調整係数で Volume を変形（同 P1） | 修正済み。Volume は生値のまま、`Turnover` を別列に分離（[yfinance_prices.py](../../src/data/yfinance_prices.py) `_normalize_for_scanner`） |
| strategy/schema の混在集計（同 P2） | 修正済み。forward は fail closed、learning は schema 3/4 を区別して読み込む |
| 当日 High の HWM 反映・stale 閾値の分岐・通知重複・Sheets 原子化（REQ-023〜026） | 実装済み |
| Explosion Recall、Early Exit、Peak Capture/Giveback、クラスタ bootstrap CI、portfolio 評価 | 実装済み |

以下の §2〜§4 は、上記以外の**新規指摘**である。

---

## 2. 修正すべき部分（コード・設計）

### A1 [P0] 候補をユーザが見る手段がない（目的との乖離）

- 対象: [scripts/run_inflection_shadow.py](../../scripts/run_inflection_shadow.py)、[.github/workflows/inflection_shadow.yml](../../.github/workflows/inflection_shadow.yml)
- 事実: 日次 scan の結果は `inflection_candidates.enc`（暗号化）にしか出力されない。Slack 通知は失敗時だけである。リポジトリ内で `decrypt_json` を呼ぶのは評価系だけで、候補を表示する CLI や通知はない。
- 影響: 「予測とタイミングをユーザに促す」という目的の出口が存在しない。検証期間中であっても、ユーザが候補を目で見て「なぜこの銘柄か」を確認できないと、定性的なフィードバック（明らかなノイズ銘柄の混入など）も得られない。
- 修正案（最小）: scan の成功後に、EARLY_CANDIDATE と WATCH の上位数件を Slack へ日次ダイジェストとして送る。文言には「検証用・売買推奨ではない」と明記する。銘柄、分類、スコア、reasons、20日リターン、出来高比を含める。あわせて `scripts/show_candidates.py`（ローカルで復号して表形式で表示する数十行のスクリプト）を置く。
- 注意: Slack は外部送信になるため、公開範囲（個人 workspace かどうか）を確認してから有効化すること。

### A2 [P0] snapshot に学習用の生特徴量が保存されていない（後から取り戻せない）

- 対象: [inflection_live.py:53-75](../../src/screening/inflection_live.py#L53-L75)（`LiveCandidate`）
- 事実: `_fundamental_features` が計算した `revenue_growth_yoy_pct`、`operating_profit_growth_yoy_pct`、`operating_margin_change_pctpt`、`upward_revision_pct`、`turned_profitable`、`negative_operating_cashflow`、`latest_actual_disclosure_date`、`latest_disclosure_date` は、**snapshot に保存されていない**。残るのは閾値で丸めた `reasons` 文字列だけである。スコア内訳（`InflectionScore.details`、fundamental/momentum/risk の小計）、一次選別の `pre_score`、業種コードも保存されていない。
- 影響:
  - 自己学習（[inflection_learning.py:170-211](../../src/evaluation/inflection_learning.py#L170-L211)）の factor は、価格系の帯と reasons しか使えない。そのため「売上成長 15% と 40% のどちらが効いたか」「開示から何日経過した上方修正が効くか」を検証できない。
  - REQ-020（スコア閾値・重みの band 別検証）と REQ-022（業種相対）は、これらの値がないと実施できない。
  - 財務値は「その日に取得可能だった値」を再現するのが難しい（J-Quants の遅延と訂正開示があるため）。**保存しなかった日の値は後から正確に復元できない**。
- 修正案: `LiveCandidate` に `features: dict`（上記の数値と開示日）、`score_details: dict`、`pre_score: float`、`sector33_code`（master に存在すれば）を追加する。`REPORT_SCHEMA_VERSION=5` とし、learning loader の `SUPPORTED_SCHEMA_VERSIONS` に 5 を加える。戦略ロジックは変えないため `STRATEGY_VERSION` は v3 のままでよい。ただし forward 側は schema 混在を fail closed で拒否するので、「同一 strategy 内では schema 4→5 を許可する」ように [inflection_forward.py:69-73](../../src/evaluation/inflection_forward.py#L69-L73) を緩める必要がある。

### A3 [P1・2026-10-01 対応済み] 上場廃止（TOB/MBO）銘柄が1つでもあると週次検証が全体で失敗する

- 対象: [rebuild_inflection_forward_validation.py:127-128](../../scripts/rebuild_inflection_forward_validation.py#L127-L128)、[rebuild_inflection_learning.py:135-136](../../scripts/rebuild_inflection_learning.py#L135-L136)
- 事実: 価格取得に1銘柄でも失敗すると `RuntimeError` になり、レポート全体が生成されない。yfinance は上場廃止後の JP 銘柄に対して空データを返すことが多い。
- 影響: 2025〜26年の日本市場では TOB・MBO・親子上場解消による上場廃止が多い。deep_candidates に入った銘柄が1つ上場廃止になった時点で、**以後の週次 forward validation と learning は恒久的に失敗し続ける**。しかも TOB は「プレミアム付きで強制的に exit した」という重要な成果であり、欠損扱いにすべきではない。
- 修正案: 取得失敗を致命的エラーにせず、`price_unavailable` として件数と銘柄をレポートに記録して継続する。失敗率が閾値（例: 5%）を超えた場合だけ fail させる。可能なら上場廃止銘柄は J-Quants の日足（上場廃止銘柄の履歴も含む。後述 B1）で補完し、最終取引日の終値で exit したとみなす。回帰テストとして「1銘柄の取得失敗ではレポートが生成される」ケースを追加する。

### A4 [P1] forward validation の価格取得がスケールせず、30分の制限を超える見込み

- 対象: [rebuild_inflection_forward_validation.py:59-129](../../scripts/rebuild_inflection_forward_validation.py#L59-L129)、[forward_validation.yml:38](../../.github/workflows/forward_validation.yml#L38)
- 事実: 1銘柄ずつ `yf.Ticker().history()` を呼び、各呼び出しの間に 0.5 秒待つ。これを価格基準2種類（total return と split only）で2回行う。同じ job 内で learning も価格を再取得する（こちらは50銘柄単位のバッチ）。job の制限時間は30分。
- 影響: deep_candidates は1日25銘柄で、新規銘柄が毎日数件ずつ加わる。数か月で対象銘柄は数百〜千を超え、「1リクエスト約1〜1.5秒 × 2基準」で制限時間に達する。
- 修正案: learning 側の `_fetch_learning_histories`（バッチ取得）と共通化する。split only 基準は `actions=True` で1回だけ取得し、total return 基準は取得データから `Adj Close` 比で導出すれば、取得を1回にできる。forward と learning で同じ価格データを使い回す（1回の実行でデータを渡す）。

### A5 [P1] 自己学習の昇格判定が多重比較に対して無防備で、「爆発」の定義がモジュールごとに異なる

- 対象: [inflection_learning.py:29-34, 369-429](../../src/evaluation/inflection_learning.py#L369-L429)、[inflection_recall.py:17](../../src/evaluation/inflection_recall.py#L17)、[inflection_backtest.py:225](../../src/evaluation/inflection_backtest.py#L225)
- 事実:
  - 昇格の基準は「n≥30、lift≥1.35、平均超過リターン>0」だけである。factor ラベルは約40種類あり、それを4つの horizon で見るので、約160通りの比較になる。有意性の検定も多重比較の補正もないため、**偶然だけで毎週いくつかの「positive_candidate」が出る**。
  - 「爆発」の定義が3つある。learning は horizon 別の閾値（15/25/40/60%）、backtest の `explosive_50pct` は保有期間内の最大リターン≥50%、recall は252日以内に終値+50%。同じ「爆発」という言葉で集計値の意味がずれている。
- 修正案:
  - 爆発率の差は Fisher 正確検定、または Beta-Binomial（経験ベイズ）で縮小した lift の下側信頼限界で判定する。factor×horizon の全体に Benjamini–Hochberg の FDR 補正（偽発見率の制御）をかける。昇格には「連続する複数週で同じ方向」を条件に加える。
  - 爆発の定義を1か所の定数に集約し、ボラティリティで正規化した定義（例: 事前60日の日次ボラティリティ σ に対して +kσ√h）を併記する。値動きの荒い小型株ほど「爆発」と判定されやすい偏りを除くためである。

### A6 [P2] scan を実行できなかった日が記録されない

- 事実: v3 の対象期間（2026-09-14〜09-30）に TSE の営業日は10日あるが、snapshot は9件で、**09-28 が欠けている**。09-29 の自動再実行導入より前の失敗とみられる。欠けた日を記録する台帳や補完の仕組みはない。
- 影響: 欠損日が特定の相場状況（データ遅延が起きやすい急変日など）に偏ると、評価にバイアスが入る。
- 修正案: 失敗日を `dashboard/data/inflection/v3/_gaps.json`（暗号化は不要なメタデータ）に追記し、forward レポートに「期待営業日数と snapshot 数」を出す。後から補完する場合は、price only の特徴量だけを `backfilled: true` 付きで保存し、本来の評価系列とは分ける。

### A7 [P2] 上方修正が「いつの修正か」を考慮していない

- 対象: [inflection_live.py:217-228](../../src/screening/inflection_live.py#L217-L228)
- 事実: 同じ会計年度の直近2つの FOP を比較するだけなので、数か月前の修正でも、次の開示まで「業績予想上方修正」として加点され続ける。さらに Free プランの12週遅延が加わる。本決算の開示後は、終了した会計年度の古い修正を見ることになり、新年度の予想（`NxFOP`）は評価されない。
- 修正案: まず A2 で開示日を保存し、開示からの経過日数を factor として学習させる。そのうえで、経過日数に応じた減衰（例: 60営業日で0にする）を次期 strategy の候補とする。

### A8 [P3] 軽微な指摘

| # | 内容 | 場所 |
|---|---|---|
| a | `extreme_runup_penalty`（20日+80%で減点）は、live では r20≥50% の時点で OVEREXTENDED に分類されるため、分類に影響しない死に設定である | [inflection.py:122-126](../../src/strategy/inflection.py#L122-L126)、[inflection_live.py:260](../../src/screening/inflection_live.py#L260) |
| b | 株式分割の直後20営業日は `volume_ratio_20d` が歪む（既知、未対応） | [inflection_live.py:97-103](../../src/screening/inflection_live.py#L97-L103) |
| c | 【対応済み】main 上で手動 dispatch すると、実行中の定期 scan がキャンセルされる（`cancel-in-progress: true`。コメントの意図は「branch 実行が main を止めない」こと） | [inflection_shadow.yml:11-12](../../.github/workflows/inflection_shadow.yml#L11-L12) |
| d | benchmark が全銘柄共通の TOPIX ETF `1306.T` である。Growth の小型株には size 要因の差が混入するため、市場区分別の benchmark（例: グロース250連動 ETF）を併記するとよい | [inflection_forward.py:19](../../src/evaluation/inflection_forward.py#L19) |
| e | 【対応済み】CI の mypy 対象に `inflection_backtest/portfolio/learning/recall` と rebuild 系 scripts が含まれていない（`pyproject` は `strict = true`） | [test.yml:42-53](../../.github/workflows/test.yml#L42-L53) |
| f | 【対応済み】yfinance の東証1分足は実測約15分遅延（2026-10-01 09:53 JST、8銘柄で age 15〜16分）。場中閾値10分では 09:03 / 12:35 / 15:35 の全実行が構造的に stale だったため、閾値を20分に、cron を 09:20 / 12:50 / 15:35 に変更（詳細: [proposal_a8f.md](../implement/proposal_a8f.md)） | [live_quote.py:19-20](../../src/data/live_quote.py#L19-L20) |

### A9 [P1・対応済み] 分割のみの価格基準で、分割を二重に調整していた（2026-10-01 追記・同日に実データで確認して修正）

- 対象: [live_quote.py](../../src/data/live_quote.py) の `split_adjust_ohlc` と `fetch_split_adjusted_history`（本番の Position Exit Monitor）、forward の trailing stop 評価（`SPLIT_ONLY` 基準）
- 根拠: yfinance 1.7.0 の `_fix_bad_stock_splits`（`scrapers/history.py` L2953〜）のコメントは、Yahoo が過去の価格に分割調整を**適用して**返す前提で、その調整の欠落や二重適用を修復している。そのため、`history(auto_adjust=False)` の OHLC はすでに分割調整済みである可能性が高い。その上で `split_adjust_ohlc` が分割比で割るのは二重の調整になる。
- 影響: 分割前に買って分割後も保有している銘柄について、「分割後の基準での買値」と HWM（保有中の最高値）が実際より低くなる。すると stop 価格も低くなり、**売却アラートが出るべきときに出ない**可能性がある。forward では、分割をまたぐ trade の trailing stop の成績がずれる。
- 状態: ライブラリのソースからの推定で、実データでは未確認である。REQ-042（A4）では挙動を変えない。**verify-before-fix で、分割のあった銘柄の実データを使って確かめる**ことを推奨する。B1 の J-Quants キャッシュ（`AdjFactor`）を、独立した照合データとして使える。
- 実データ確認（2026-10-01、yfinance 1.7.0、`history(auto_adjust=False, actions=True)`）:
  - 7203.T（2021-09-29 に 1:5 分割）: 分割前日 2021-09-28 の Close は **2077**（実際の取引値は約1万円台なので、すでに ÷5 されている）。`split_adjust_ohlc(h, 2021-10-05)` を通すと **415.4** になり、分割後の 2000 前後と比べて5分の1になる。
  - 8058.T（2023-12-28 に 1:3 分割）: 分割前の Close は 2217.33 のような端数（= 6652 ÷ 3）で、分割後の 2245〜2287 と連続している。つまり Yahoo の値はすでに分割調整済みである。
  - J-Quants キャッシュ（`.data/jquants`）は手元に存在しないため、照合はしていない。2銘柄・2時期で同じ結果なので、結論は変わらないと判断した。
- 結論と影響の内訳:
  - `fetch_split_adjusted_history`: `entry_price ÷ 分割比` は**正しい**（ユーザが入力する買値は分割前の実際の値であるため）。誤っているのは、購入日の翌日から分割前日までの行を `split_adjust_ohlc` がもう一度割っている部分である。その結果、分割前の HWM が 1/分割比 に縮み、stop 価格が低くなって、**売却アラートが出ない**。
  - forward（`SPLIT_ONLY`）: 分割前の行だけが二重に割られ、分割日に価格が分割比の倍率で跳ね上がる。分割をまたぐ trade は trailing stop がずれるだけでなく、**見かけ上 ×分割比 の利益**になる。直近の forward 期間に分割をまたいだ trade があるかどうかは未確認である。
  - 既存のテスト（`tests/test_live_quote.py` の分割ケース、`tests/test_inflection_forward.py:304`）は、未調整の raw 値という誤った前提で作った fixture で、二重調整を正しい挙動として固定している。
- 修正（2026-10-01）: `split_adjust_ohlc` を削除し、Monitor と forward（`SPLIT_ONLY`）は yfinance の OHLC をそのまま「取得時点の分割基準」として使うようにした。`entry_price ÷ 分割比` は残している。テスト fixture は、分割前の行もすでに調整済みという実データの形に直した。7203.T の実データで、買値 9820 を分割比で割った値が 1964 になり、同じ日の Yahoo の Close（1964）と一致することを確かめた。分割当日の基準は 2026-10-01 に事後確認した。8035.T と 5805.T（いずれも 2026-09-29 に 1:5 分割）で、分割当日の1分足（8035.T は 11430〜11440）と日足（Open 11355、Close 11505）は同じ分割後の基準で、分割前の日足とも連続していた。ただし、分割当日の朝の時点で Yahoo の日足がすでに調整されていたかどうかは、後からは確かめられない。もし調整が遅れていた場合、HWM が過大になり、早めの誤った売却アラートが出る側にずれる（アラートが出ない側にはずれない）。

---

## 3. 実装したほうが良い機能

### B1 [P0] J-Quants の過去データによる point-in-time 過去検証（「蓄積待ち」の短縮）

- 背景: 現在は forward shadow の蓄積を待っている段階だが、有効なのは v3 の9営業日分だけである。60営業日の成果が出揃うのは早くても12月で、REQ-017/020/022 の判断材料が揃うのは来年以降になる。
- 提案: J-Quants Free は「約2年前から12週前まで」の上場銘柄一覧、日足（**上場廃止銘柄を含む**）、財務サマリー（`DiscDate` 付き）を提供している。これを使えば `scan_japan_inflection` と同じロジックを過去の各営業日に適用できる。
  1. その日の上場銘柄一覧（生存者バイアスなし）
  2. その日までの日足でテクニカル特徴量を計算
  3. `DiscDate` がその日以前の財務だけでスコアを計算
  4. 既存の `simulate_signal`、`simulate_portfolio`、learning にそのまま流す
- さらに、財務の取得可能日を「`DiscDate` 当日」と「`DiscDate` + 12週」の2通りで検証すれば、**有料プラン（遅延なし）に切り替える価値を金額で見積もれる**。PEAD は開示後の数十日に集中するため、差が大きい可能性が高い。
- 注意:
  - 過去検証で閾値を調整し始めると過剰最適化になる。**過去検証は「現行 v3 ルールの固定評価」に使い、パラメータ探索はしない**か、行うなら期間を前後に分けて後半を holdout にする。forward shadow は引き続き真の out-of-sample として扱う。
  - 【要確認】J-Quants V2 の日付指定エンドポイント（`/equities/bars/daily?date=`、`/fins/summary?date=` 相当）の有無と Free プランのレート制限。日付指定で全銘柄を一括取得できるなら、2年分でも約500回×2の呼び出しで済む。
- 副次効果: 日次 scan でも `/fins/summary?date=` で「その日の全開示」を1回で取得しローカルに蓄積すれば、**25銘柄に限らず全流動銘柄の財務を評価できる**（現状は一次選別の上位25銘柄しか財務を見ていないため、「財務は強いがモメンタムが中程度」の銘柄を原理的に拾えない）。

### B2 [P1] 対照群（ランダムサンプル）の記録

- 背景: WATCH と NONE も「モメンタム上位25銘柄」の中での分類なので、真の対照群ではない。learning と recall は、deep_candidates の中しか見えない（`limitations` に明記されている）。
- 提案: 毎日、流動性フィルタを通過した銘柄から固定 seed で無作為に25銘柄を抽出し、同じ特徴量（価格系＋可能なら財務）を `control_sample` として snapshot に保存する。これで「EARLY_CANDIDATE は市場の平均的な銘柄より爆発率が何倍高いか」を偏りなく推定できる。追加コストは J-Quants の呼び出し25回（約5分）だけである。

### B3 [P1] 売却タイミング支援の拡張（Exit Monitor）

目的の後半（「上昇が止まる直前に手放す」）に対して、現状は固定 %の Trailing Stop だけである。天井を事前に当てることは原理的にできない。現実的な目標は「トレンドの大部分を取り、天井からの反落で出る」ことで、そのための Peak Capture の計測は既にある。以下を **forward validation の exit_strategies に並べて比較し、優位だったものだけを Monitor に採用する**。

| 候補 | 内容 | 根拠 |
|---|---|---|
| ATR / Chandelier Exit | stop = HWM − k × ATR(14 or 22)、k = 2.5〜3.5。銘柄ごとのボラティリティに合わせて幅を自動調整する | LeBeau（Chandelier）、既存メモ [trader_exit_strategy_research.md §8.1](../trader_exit_strategy_research.md) |
| 移動平均割れ | 利益が +X% 以上になった後、終値が 10EMA / 20EMA を下回ったら exit | トレンドフォローの実務 |
| 時間 stop | N 営業日（例: 10〜15日）で +R に届かなければ exit する。「爆発しなかった候補」の資金拘束を減らす | Kaminski & Lo (2014) の含意 |
| 段階利確 | +2R や +50% で半分を利確し、残りを trailing で保有する | R-multiple 管理（Van Tharp） |
| 決算跨ぎの警告 | 決算発表予定日の N 日前に通知する。J-Quants の決算発表予定日は Free プランでも取得できる（§8） | ギャップリスクの管理 |
| 過熱・出来高クライマックスの警告 | 20日で +50% 超、または出来高が平常の5倍以上の大陽線・長い上ヒゲで警告だけ出す（自動判定ではなく注意喚起） | Bali, Cakici & Whitelaw (2011)（MAX 効果） |

加えて、Monitor に「stop まで残り3%以内」の**事前警告**を追加すると、ユーザが判断する余裕ができる（`distance_to_stop_pct` は計算済みで、通知に使っていないだけである）。

### B4 [P1] 相場環境（regime）ゲートと、その層別評価

- 背景: モメンタム系の戦略は、下落相場からの急反発局面で大きく負ける（momentum crash）。現状の regime は forward レポートの件数集計（TOPIX の20日リターンが正か負か）だけである。
- 提案: regime（例: TOPIX が200日線より上か、20日の実現ボラティリティが閾値を超えているか）を learning の factor ラベルに加える。優位性が確認できれば、次期 strategy で「下落 regime では EARLY_CANDIDATE を WATCH に格下げ」または「ポジション数を半分にする」。
- 根拠: Daniel & Moskowitz (2016) *Momentum Crashes*、Barroso & Santa-Clara (2015) *Momentum Has Its Moments*（ボラティリティ管理）

### B5 [P2] ポジションサイズ設計（リスク基準）

- 現状の portfolio 評価は、1銘柄 12.5% の固定配分である（ユーザ未確認の既定値）。
- 提案: 「1トレードの許容損失を資金の x%」とし、株数 = 許容損失 ÷ (entry − stop) で決める（リスク均等配分）。ATR stop と組み合わせると、値動きの荒い小型株は自動的に小さく持つことになる。100株単位の丸めと ADV 比の上限（例: 20日平均売買代金の 1% 以下）も同時に入れる（REQ-014b と統合する）。

### B6 [P2] 追加データソース（point-in-time で取得できるもの）

| データ | 用途 | 取得元 | 備考 |
|---|---|---|---|
| TDnet 適時開示（上方修正・大型受注・提携） | catalyst の点数（現状は常に0点で、`LIVE_MEASURABLE_MAX_SCORE=58` の原因） | TDnet（公開）／J-Quants 有料 | 開示時刻がわかるので point-in-time が保証できる |
| EDINET 大量保有報告（5%ルール） | 機関投資家・アクティビストの参入を catalyst として使う | EDINET API（無料・公式） | 提出日時あり |
| 信用残・貸借倍率、空売り残高 | 需給（踏み上げ余地、過熱） | J-Quants（信用残は Standard 以上）／JPX 公表 | 週次、公表ラグあり |
| 業種コード（33業種） | REQ-022 の業種相対モメンタム、REQ-014b のセクター上限 | J-Quants master | A2 で snapshot に保存 |

特に TDnet は、「材料が point-in-time で取れないので本番スコアから除外」（[inflection_live.py:548](../../src/screening/inflection_live.py#L548)）という現状の制約を解消できる、最も直接的な経路である。

---

## 4. 既存機能に反映・追加したほうが良い論文・理論

既存メモ（[literature_and_ops_review_2026-09-08.md](literature_and_ops_review_2026-09-08.md)、[literature-summary.md](../notebook/literature-summary.md)）で既に扱っている J&T (1993)、George & Hwang (2004)、Lee & Swaminathan (2000)、PEAD、Kaminski & Lo (2014)、Amihud (2002) などは除き、**新規のものだけ**を挙げる。

### 4.1 シグナル（買い側）

| 文献 | 要点 | 反映先 |
|---|---|---|
| Chordia & Shivakumar (2006) *Earnings and Price Momentum* | 価格モメンタムの大部分は業績モメンタム（SUE）で説明される | 財務点を「前年比」だけでなく「前四半期からの変化（加速）」でも測る。現状の `revenue_acceleration` は live で未計測だが、J-Quants の累計値の差分から単独四半期を作れば計算できる |
| Da, Gurun & Warachka (2014) *Frog in the Pan* | 同じリターンでも、小さな上昇が積み重なった（連続的な）上昇のほうがモメンタムが持続する。急騰1回で稼いだリターンは持続しにくい | 20日間の上昇日比率、または「最大日次リターン ÷ 20日リターン」を特徴量に追加し、learning で検証する |
| Bali, Cakici & Whitelaw (2011) *Maxing Out* | 直近の最大日次リターンが極端な「宝くじ型」銘柄は、その後のリターンが低い | 「爆発を探す」戦略とは逆向きの証拠なので、OVEREXTENDED の判定や exit の警告に使う |
| Moskowitz & Grinblatt (1999)、Hou (2007) *Industry Information Diffusion* | 業種モメンタムと、業種内での情報伝播の遅れ（先行株 → 追随株） | REQ-022 の業種相対化の根拠。Kioxia → 半導体関連のような「テーマ波及」を捉える唯一の定量的な経路 |
| Daniel & Moskowitz (2016)、Barroso & Santa-Clara (2015) | momentum crash と、ボラティリティ管理による改善 | B4 の regime ゲート、B5 のサイズ設計 |

### 4.2 評価・自己学習（統計）

| 文献・手法 | 要点 | 反映先 |
|---|---|---|
| Harvey, Liu & Zhu (2016) *…and the Cross-Section of Expected Returns* | 多数の factor を試す場合は、t 統計量の基準を大幅に引き上げるべき | A5 の昇格ゲート |
| Benjamini & Hochberg (1995) FDR | 多重比較で偽発見率を制御する標準手法 | A5：factor × horizon 全体に適用する |
| Bailey & López de Prado (2014) *Deflated Sharpe Ratio*、Bailey et al. (2017) PBO | 多数の exit/horizon の組み合わせから最良の結果を選ぶと、成績を過大評価する（backtest overfitting） | forward レポートの `multiple_comparisons_caveat` を定量化する（exit 戦略9通り × コスト2通りの中で最良のものの DSR を出す） |
| López de Prado (2018) Triple-Barrier / Meta-Labeling / Purged CV | 上限・下限・時間の3つの障壁でラベルを付ける。一次シグナルに「乗るか」を二次モデルで判定する。重なりのある観測はパージして検証する | A5 の爆発定義の統一（上限＝爆発、下限＝stop、時間＝horizon）。自己学習の最終形は、EARLY_CANDIDATE に対する meta-label（採否）モデルとし、重みの直接更新はしない現設計と整合する |
| Beta-Binomial（経験ベイズ）による縮小推定 | 少数サンプルの率（爆発率）を全体平均に向けて縮めることで、偶然の高 lift を抑える | A5 |

### 4.3 売却・資金管理

| 文献・手法 | 要点 | 反映先 |
|---|---|---|
| Han, Zhou & Zhu (2016) *Taming Momentum Crashes: A Simple Stop-Loss Strategy* | モメンタム銘柄に stop-loss を入れると、crash リスクが大きく下がる | 現行 Trailing Stop の根拠を補強。B3 で stop 幅を比較する |
| LeBeau（Chandelier Exit）、Wilder（ATR） | ボラティリティに比例した trailing 幅 | B3 |
| Van Tharp（R-multiple）、Thorp / fractional Kelly | 損失単位（R）で損益を管理し、資金の成長率を最大化するサイズの上限を決める | B5。Kelly は推定誤差に弱いので、使うなら 1/4〜1/2 Kelly を上限の参考にする程度にとどめる |

---

## 5. 推奨する実施順

| 順 | 項目 | 理由 |
|---|---|---|
| 1 | **A2** snapshot schema 5（生特徴量・開示日・スコア内訳・pre_score・業種の保存） | 1日遅れるごとに学習材料が失われる。戦略ロジックは変わらない |
| 2 | **A3** 上場廃止銘柄で検証全体が失敗しないようにする | 最初の TOB が起きた時点で週次の検証が止まる |
| 3 | **A1** 日次ダイジェスト通知と候補表示スクリプト | 目的の出口。数十行で済む |
| 4 | **B2** 対照群のランダムサンプル | A2 と同じ schema 変更にまとめられる |
| 5 | **B1** J-Quants による過去 point-in-time 検証 | 「蓄積待ち」を短縮し、有料プランの価値も見積もれる。規模は中程度なので、proposal → plan の手順で進める |
| 6 | **A4、A5** 価格取得の共通化と、昇格ゲートの統計的補強 | データが増える前に直す |
| 7 | **B3、B4** exit 候補と regime を検証系に追加 → 優位なものだけ Monitor に反映 | 検証してから本番に入れる、という現行方針を守る |
| 8 | A6、A7、A8、B5、B6 | 余力に応じて |

roadmap との関係: A2 は REQ-020/022/014b の前提条件なので、roadmap の「蓄積待ち」より先に入れるべきである。B1 の過去検証は REQ-017/020 を先行して検討する材料になる（ただし、判断は forward の結果で確認してから行う）。

## 7. プロジェクトの方向性・妥当性

### 7.1 結論

検証の進め方は正しい。ただし、**目的の言い方に、達成できない部分が2つある**。

### 7.2 妥当な点

- **自動売買をせず、shadow で記録して forward validation する方針。** 個人の株式予測で最も多い失敗は「検証前に実資金を入れる」ことで、このプロジェクトはそれを構造的に避けている。
- **先読みの防止（point-in-time）、暗号化した変更不能な snapshot、TOPIX との比較、ストレスコスト、多重比較への注意。** 個人プロジェクトとしては非常に丁寧である。
- **旧パイプライン（Prophet / LightGBM）の廃止。** 復元検証で損失を確認したうえで方針を変えた判断は健全である。

### 7.3 無理がある点

**(1) 「爆発する銘柄を事前に見つける」の出発点に後知恵バイアスがある**

- [memo/prompt.md](../prompt.md) の例（キオクシア、QDレーザ、Terra Drone など）は、結果を知ってから選んだ銘柄である。同じ時期に似た兆候があったのに上がらなかった銘柄が、その何十倍もある。
- 大きく上がる銘柄は全体のごく一部なので、どんな条件で絞っても候補の大半は外れる。
- 目標は「当てる」ではなく、「**外れも含めた全体の成績が、TOPIX やグロース指数を買うより良いか**」とすべきである。現行の評価設計は既にこの形になっているので、直すべきなのは目的の書き方である。なお、過去に上がった銘柄を特別扱いしない方針（`notes` に明記）は正しい。

**(2) 「一番利益が出るタイミングで手放す」は原理的に達成できない**

- 天井は事後にしか分からない。現実的な目標は「上昇の大部分を取り、天井からの反落で降りる」ことである。Peak Capture Ratio（上昇幅のうち取れた割合）が 0.5〜0.6 程度でも上出来といえる。§3-B3 はこの前提で書いている。

### 7.4 勝てる根拠（エッジ）の源泉が弱い

現状の構成で「市場に勝てる理由」を検討すると、根拠は薄い。

| 要素 | 懸念 |
|---|---|
| 財務データ | J-Quants Free は12週間遅延する。決算後のドリフト（PEAD）は開示後の数十日に集中するため、12週後にはほぼ織り込まれている |
| 価格モメンタム | 日本市場はモメンタム効果が国際的に見て弱い（Fama & French 2012） |
| 執行 | 小型・グロース株は板が薄く、ストップ高で約定できないこともあるため、実際のコストは大きい |

つまり、現状は「遅延した財務データ＋弱いモメンタム」の組み合わせで、**勝てなくても不思議ではない構成**である。だからこそ検証が必要であり、その検証の仕組み自体はよくできている。財務データの遅延をなくす方法は §8 にまとめた。

### 7.5 提案: 撤退条件を事前に決める

結果を見てから基準を動かさないように、撤退条件を今のうちに文書化する。

- 例: 「EARLY_CANDIDATE の独立観測が100件以上になった時点で、60日の対TOPIX超過リターンの95%信頼区間（signal_date クラスタ bootstrap）が0をまたぐ場合、v3 戦略は打ち切って方針を見直す」
- §3-B1 の過去 point-in-time 検証を使えば、この判定を数か月待たずに一度試せる。そこで明確に負けていれば、shadow を続ける前に方針を見直す。

### 7.6 位置付けの言い換え

「爆発株を当てて天井で売る」を目的にすると、必ず期待を下回る。**「規律ある候補の絞り込みと損切りで、指数に勝てるかを検証する仕組み」**と捉え直せば、現行の設計はそのまま妥当である。検証の結果が「勝てない」だった場合でも、実資金を失う前にそれが判明したことになるので、プロジェクトの価値は残る。

---

## 8. 当日データの取得とコスト

### 8.1 現状

| データ | 取得元 | 鮮度 | 費用 |
|---|---|---|---|
| 株価・出来高 | yfinance | **当日の終値まで取得済み**（16:40 JST に実行） | 無料 |
| 財務（決算短信サマリー） | J-Quants Free | **12週間遅延** | 無料 |

価格は既に当日のデータを無料で取得している。遅延しているのは財務データだけである。

### 8.2 J-Quants の料金プラン（2026-10-01 に公式サイトで確認）

| プラン | 月額（税込） | 遅延 | 過去データ | API 制限 | 本プロジェクトに関係する差分 |
|---|---|---|---|---|---|
| Free | 0円 | 12週間 | 2年 | 5件/分 | 現状 |
| **Light** | **1,650円** | **なし** | 5年 | 60件/分 | 財務の遅延がなくなる。過去検証（B1）を5年分で実行できる |
| Standard | 3,300円 | なし | 10年 | 120件/分 | 信用取引残高が使える（B6） |
| Premium | 16,500円 | なし | 20年 | 500件/分 | 財務諸表の詳細、売買内訳。現段階では不要 |

決算発表予定日は Free プランでも取得できる（B3 の決算跨ぎ警告は無料で実装可能）。

### 8.3 無料で当日の財務データを得る方法

- **TDnet（JPX の適時開示閲覧サービス）**: 決算短信と業績予想修正が開示と同時に公開され、決算短信には XBRL が付く。閲覧は無料だが、公式の配信 API は有料である。サイトを機械的に取得する場合は利用規約の確認が必要で、XBRL を解析する実装の手間もかかる。
- **EDINET API**: 無料の公式 API である。ただし有価証券報告書・半期報告書は決算短信より遅く提出されるため、当日の決算データの代わりにはならない（大量保有報告の取得には有用）。
- **yfinance の財務データ**: 日本株では欠損が多く、いつ取得可能になったかの記録（point-in-time）もないため、スコアには使えない。

### 8.4 推奨

1. **まずは料金を払わずに、遅延の影響を測る。** B1 の過去検証（Free の2年分）で「財務を `DiscDate` 当日から使える場合」と「12週間後から使える場合」を比較する。
2. 差が明確なら、**J-Quants Light（月額1,650円）に切り替える**のが最も手間が少なく、規約上も安全である。過去検証の期間も5年に延びる。`JQUANTS_PLAN=light`、`JQUANTS_DATA_DELAY_WEEKS=0` に設定し、データの性質が変わるので `STRATEGY_VERSION` も上げる。
3. 差がなければ、Free のまま続け、価格系のシグナルと TDnet 由来の材料（B6）に注力する。

出典: [J-Quants API 公式サイト](https://jpx-jquants.com/)

---

## 9. 検証したこと・していないこと

- 実行したこと: `pytest tests/`（264 passed、coverage 91.93%）、`ruff check src scripts tests`（PASS）、snapshot ファイル一覧と TSE 営業日の突き合わせ（09-28 の欠損を確認）。
- していないこと: snapshot の復号（鍵を使用していないため、候補の中身・件数・分類の比率は未確認）、外部 API の呼び出し、GitHub Actions の実行履歴の確認。「【要確認】」を付けた項目は仕様・実挙動の確認が必要である。
- 本レポートは技術的な調査と文献の照合であり、投資助言や売買成果の保証ではない。

---

## 10. 実装状況（2026-10-07 更新、コードとの突き合わせ）

> 2026-10-01 夜の版を置き換えた。「本番で動いているか」ではなく、「コードとテストが main にあるか」の状態である。push・コミットの状態は含めない。

### 実装済み（コードとテストで確認）

| 項目 | 内容 | 要件 |
|---|---|---|
| A1 | 候補のローカル表示（`scripts/show_candidates.py`）、日次の Slack ダイジェスト | REQ-048・049 |
| A2、B2 | snapshot schema 5（生特徴量、スコア内訳、業種、対照群） | — |
| A3、A8-c・e・f、A9 | 上場廃止で検証が止まる問題、手動実行による scan の中止、mypy の対象、1分足の遅延、分割の二重調整 | 対応済み |
| A4、A5 | 価格取得の一括化、Fisher 検定と BH 補正、爆発の定義の集約 | REQ-042〜044 |
| A6 | 実行できなかった営業日の検出（forward のレポートの `session_coverage`、ダイジェストの警告） | REQ-051 |
| A7（入力のみ） | 開示・予想修正からの経過日数を `features` に記録（減衰は未実装） | REQ-050 |
| A8-d | 市場区分別のベンチマーク（グロース → `2516.T`）を forward のレポートに併記 | REQ-058 |
| B1 | J-Quants の過去データによる point-in-time 検証（取得・評価・メモリの修正）。**結果: 標本不足で判定不能**（[historical_backtest_2026-10-06.md](historical_backtest_2026-10-06.md)） | REQ-039〜041 |
| B3（一部） | 売却ルール4種の比較、stop 接近と過熱の事前警告、DSR（売却ルールの多重比較補正） | REQ-045・047・056・057 |
| B4（一部） | 相場環境の判定、learning の factor、成績の層別集計 | REQ-046 |
| §4.1（一部） | 価格系の診断値、四半期の業績の加速、業種の相対モメンタムを `features` に記録（スコアには使わない）。learning の factor ラベルに接続 | REQ-050・053〜055 |
| 日次 scan の耐性 | 期待日より後の足の除去、失敗時の最新日付の分布を Slack に出力 | REQ-052 |
| B6（Phase A） | EDINET の大量保有報告の取得クライアント、キャッシュ、`--probe`（**実 API での確認は、API キーの用意待ち**） | REQ-059 |

### 計画済み・未実装
- **B6 Phase B（REQ-060・061）:** 大量保有報告を、日次 scan の `features` と過去検証・learning に記録する。**実 API での確認（`--probe`）が関門**で、API キー（EDINET）の発行が前提。

### 意図して保留しているもの
- 優位だった売却ルールを Monitor に採用すること、相場環境による戦略の切り替え、A7 の減衰、A8-a・b、B5（ポジションサイズ）: **B1 の標本が不足**（独立取引 18件と10件、必要は100件）。forward の標本が溜まってから判断する。
- 昇格に「連続する複数週」の条件を加える件、Beta-Binomial による縮小推定。
- 特徴量の、スコアへの採用（記録のみ。forward と過去検証で効果を確認してから）。

### 調査済みで、判断待ちのもの
- **決算発表日の警告:** Free プランでは、将来の予定日がほぼ取れない（直近12週に公表された分が見えない）。有料プラン（Light 以上）の判断、または保有銘柄だけ yfinance を使う案の取得率の実測が先（[earnings_date_availability_2026-10-07.md](earnings_date_availability_2026-10-07.md)）。
- **B6 の他のデータ:** TDnet（J-Quants のアドオン月5,500円 + Light 以上）、信用残・空売り（Standard 以上、月3,300円）。有料プランの判断が先（[b6_additional_data_sources_2026-10-07.md](b6_additional_data_sources_2026-10-07.md)）。Light（月1,650円）は、12週間の遅延がなくなる。

### まだ答えが出ていない問い
- §7.5 の撤退判定（60営業日の対 TOPIX 超過リターンの信頼区間）: B1 の結果は `insufficient_sample`（独立取引 18件と10件）。**forward の標本の蓄積を待つ。**
- §8 の財務ラグの比較（有料プランに切り替える価値）: B1 の lag の差は、平均 −4.1%、95%CI −34〜+22（共通のシグナル日7）で、判定できない。
