# 静的サイト向けエビデンス基盤の投資意思決定支援機能の設計レポート

## エグゼクティブサマリー

あなたの静的（DBなし）日本語サイトに「週次のAI株価上昇予測」を載せるだけだと、利用者の意思決定としては **(a) 予測の不確かさが“どれくらい当てになるのか”、(b) リスクと見合うのか、(c) 代替（ベンチマーク／単純ルール）より良いのか** が判断できません。実務・研究の観点では、ここを埋めるのが“エビデンスベースの意思決定支援”の核です（予測の校正・検証、リスク調整、過剰最適化の抑止）。citeturn10search0turn10search4turn31search0turn35search5

本レポートでは、まず GitHub コネクタで **nakaj1214/trader** を読み取り、現状のパイプライン（週次バッチ実行→Sheets/JSON→静的ダッシュボード）を前提に、**追加すべき機能を「データ要件・実装難易度・期待効果」で優先順位付け**します（利用コネクタ：GitHub）。その上で、学術・業界一次資料に基づき、次の方針を推奨します。

- **“予測の見せ方”を「点予測」中心から「期待リターン×リスク×確率（校正済み）」へ移す**：確率予測の評価は Brier / log-loss 等の適切なスコアリングと、Platt/温度スケーリング等の校正が中核です。citeturn11search0turn4search7turn35search5turn36search0  
- **因子（モメンタム／バリュー／低ボラ／クオリティ）・イベント（決算など）を“予測の補助根拠”として同一画面に統合**：研究ではモメンタムやバリュー等の因子プレミアムが繰り返し議論され、指数方法論も公開されています。citeturn4search2turn5search5turn6search1turn30search46turn30search3  
- **バックテストを「週次シミュレータ」から、実運用に耐える“ウォークフォワード＋手数料・スリッページ＋ベンチマーク比較”へ拡張**：データスヌーピングやバックテスト過剰適合対策を組み込むべきです。citeturn10search0turn10search4turn9search0  
- **日本株を本気でやるなら、価格・財務・イベントの取得基盤を yfinance 依存から J-Quants / EDINET へ段階的に移行**：更新時刻が明示され、運用設計（何時に何を更新するか）を固められます。citeturn13search1turn16view0turn20search6  
- **静的サイト運用に最適化した CI/CD（GitHub Actions）で、データ取得→特徴量→検証→JSON生成→公開を自動化**（現状リポジトリ方針と整合）。

以下、根拠と具体案を示します。なお、未指定事項（例：AIモデルが「確率」も出すのか／対象市場・ユニバース／売買コスト前提／投資助言の位置づけ）は **仮定**として明示します。

## 現状（GitHub repo nakaj1214/trader）分析とギャップ

### 既に実装されている強み（静的サイト適性が高い）
GitHub コネクタで確認した範囲で、現状のリポジトリは「DBなし・静的ホスティング」に非常に相性が良い設計です。

- **週次バッチ**：スクリーニング→予測→結果を Google Sheets に蓄積→JSONを書き出し→ダッシュボードが読む（CI で完結）。  
- **予測モデル**：yfinance の時系列を Prophet で予測し、予測価格と上下区間を保持（`yhat_lower/upper` 相当の幅を `ci_pct` として出力）。Prophet の区間は仮定付きで、将来の変化点が過去と同程度に起きる等の前提があり、**校正保証はない**点が重要です。citeturn36search0  
- **“根拠”の芽**：リスク（ボラ、ベータ、最大DD等）や、簡易な因子っぽい指標（モメンタム、バリュー、クオリティ、低リスク）をダッシュボードに表示する作りが既にあります。  
- **評価の入口**：accuracy 用 JSON、誤差分析の枠、週次投資シミュレータ（簡易バックテスト）ページが既に存在。

### 重大ギャップ（「当てになり度」を証明できない）
現状の JSON サンプル（`predictions.json`）を見ると、**短期（週次）としては非現実的に大きい上昇率**が出るケースがあり、利用者にとっては“当たる／外れる”以前に、モデルが破綻しているかどうかが判断できません（Prophet の外れ値・変化点推定の影響はドキュメントでも注意されます）。citeturn36search0turn36search5  
また `accuracy.json` は現時点で集計母数がゼロで、評価・校正がまだ始まっていない状態に見えます（＝「データ収集中」段階）。

この段階で最優先すべきは UI の派手さではなく、**(1) 予測の暴走を抑えるガードレール、(2) ベースライン比較、(3) 確率化＋校正＋検証**です。これがないまま機能を増やすと、バックテスト過剰適合や見かけ倒しの説明が増えます。データスヌーピング問題は金融では特に深刻で、統計的検定枠組みも提案されています。citeturn10search0turn10search4

> 使用したコネクタ：GitHub（nakaj1214/trader）

## エビデンスベースと「採用すべき指標」整理

ここでは、あなたのサイトの意思決定支援に直結する研究・方法論を、**「何を測ると良いか」→「なぜか」→「どう実装するか」**の順で要約します。

### モメンタム（価格モメンタム／収益モメンタム）
- **価格モメンタム**：過去3–12か月で勝っている銘柄が、短期的に勝ち続けやすいという古典結果が報告されています。citeturn4search2  
- **収益（earnings）ニュースを伴うモメンタム**：価格モメンタムと過去の収益サプライズが、それぞれ将来リターンのドリフトと関連するという議論もあります。citeturn8search1turn33search0  
- ただし、モメンタムは局面で反転やクラッシュが起こり得るため、**単独で“買い推奨”の根拠にしない**のが実務的です（後述のリスク管理・分散とセット）。

実装上は、あなたの repo ですでに「1か月変化」「RSI」「MACD」などテクニカルが入っていますが、研究系モメンタムとしては **(a) 6–12か月、(b) 直近1か月を除外（短期反転回避）**のような定義がよく使われます（MSCI の因子インデックス方法論でも 6か月＋12か月等の組み合わせとリスク調整の考え方が説明されています）。citeturn30search46turn4search2

### バリュー／クオリティ／投資（企業要因）
バリュー（簿価時価比など）、サイズ等を説明変数として横断面の平均リターンを説明するアプローチは長い研究史があり、三因子・五因子などの枠組みが提案されています。citeturn4search0turn5search5turn6search6  
五因子は「収益性（profitability）」「投資（investment）」を追加し、三因子より説明力が上がるとされますが、地域により効き方が異なり、日本では収益性・投資の関係が弱い可能性が指摘されています（国際テスト）。citeturn7search7

あなたのサイトに落とす際は、学術モデルをそのまま推定するより、**“説明支援”としての要約指標（例：ROE、D/E、利益の安定性、B/P、投資成長率）**を示し、予測と併記して意思決定補助にするのが安全です（指数方法論側でも品質要因に ROE 等を使う例が説明されています）。citeturn30search6turn30search46

### 低ボラティリティ／低リスク（Low-risk anomaly）
低ボラ・低ベータが、理論的直観に反してリスク調整後で良い成績になり得る（あるいは高ボラが低リターンになり得る）という議論があります。citeturn6search1turn6search0  
指数・業界研究でも、最小分散（minimum volatility）型の考え方や制約付き最適化の形が整理されています。citeturn30search1turn30search4turn30search46

サイト機能としては、「この予測は“高リターン候補”だが、過去ボラや最大DDが大きい」など、**予測とリスクを同じ視線で比較**できる形が価値になります。

### アナリスト推奨・決算反応・リビジョン
アナリスト推奨には即時反応だけでなく、その後のドリフトが観測されるという研究があり、コンセンサス推奨の変化に反応する戦略が研究されています。citeturn8search0turn8search3  
また、アナリストの予測改定が市場効率性や PEAD（決算後ドリフト）に影響するという示唆もあります。citeturn5search7turn33search3  

ただし、**アナリストデータは無料での取得・再配布が難しい**場合が多く、実装コスト・ライセンスリスクが高い領域です。あなたの制約（DBなし／公開サイト）では、まずは **決算日（イベント）注釈と、決算跨ぎの成績・ボラ上昇**など、公開データでできる代替から入るのが現実的です。

### マクロシグナル（配当利回り、金利、インフレ等）
配当利回り（D/P）などが将来の割引率やリターンと関係し得るという古典研究があります。citeturn9search1turn9search5  
一方で、“株式プレミアム予測”の多くはアウト・オブ・サンプルでうまくいかず不安定だった、という包括的検証もあります。citeturn9search0turn9search3  

結論として、マクロは「当てに行く」より **レジーム判定（低金利局面／高インフレ局面など）**としてリスク管理・配分に使う方が、サイトの意思決定支援として堅いです。

### リスク調整リターン（Sharpe など）
リターン単体でなく、リスク当たりの期待収益を比較する指標（Sharpe 比など）は、実務で広く使われています。citeturn31search0  
ただし Sharpe も推定誤差・期間依存があるので、**複数指標（Sharpe、最大DD、勝率、損益比、回転率）をセット**で提示するのが良いです。

### 確率予測の校正（Calibration）
あなたの「AI上昇予測」を意思決定に使うなら、**確率が“当たる確率”になっているか**（校正）が中核です。確率予測の評価に Brier（確率予報の検証）や、適切なスコアリングルールの枠組みが古くからあります。citeturn11search0turn11search1  
校正手法としては、Platt（SVM 出力をシグモイドで確率化）citeturn34search1、温度スケーリング（ニューラルネット等の校正に有効）citeturn4search7 が広く参照されます。scikit-learn でも Platt（sigmoid）や校正曲線の方法論が整理されています。citeturn35search5turn35search0  

重要：現状 repo の Prophet 区間は、仮定（将来の変化点が過去と同程度など）に依存し、**そのまま“80%信頼”と見なすのは危険**です。Prophet 自身がこの点を明示しています。citeturn36search0

## 推奨機能セット（入力・出力・更新頻度・UX案）

前提：あなたは **DBなし**だが **JSON と Google Sheets** は保存可能。予測生成や検証は **オフライン（GitHub Actions / ローカル）で実行**し、静的サイトは JSON を読むだけにします（現状 repo と整合）。

### 機能比較テーブル（優先度設計）
まず「どれから作るべきか」を、実装難易度・必要データ・期待効果で整理します（**静的サイトでの“意思決定支援価値”**を基準）。

| 機能 | 目的（意思決定価値） | 実装難易度 | データ要件 | 期待効果 |
|---|---|---:|---|---:|
| 予測ガードレール（上昇率クリップ／対数化／異常検知） | 破綻予測の排除、信頼性向上 | 低 | 価格のみ | 高 |
| ベースライン比較（単純モメンタム等） | 「AIが本当に上か？」を示す | 低 | 価格のみ | 高 |
| 確率化（P(up)）＋校正（Platt/温度）＋信頼性図 | 確率を意思決定に使える形へ | 中 | 予測＋実現 | 高 |
| リスク推定（年率ボラ、最大DD、β）＋リスク調整指標 | 同じ“上昇”でも危険度が違う | 低 | 価格＋指数 | 中〜高 |
| 因子集約スコア（モメンタム/バリュー/クオリティ/低ボラ） | 予測の補助根拠、説明 | 中 | 価格＋財務 | 中 |
| セクター／市場ニュートラル順位 | 偏り（同業種だらけ）を抑える | 中 | セクター分類＋指数 | 中 |
| イベント注釈（決算・配当・開示）強化 | “いつ危ない/動く”を明示 | 中 | カレンダー/開示 | 中 |
| バックテスト（手数料・再現可能性・WF） | 実運用に近い検証 | 中〜高 | 価格＋ルール | 高 |
| SHAP風ローカル説明（寄与度） | なぜその順位かを定量化 | 中 | 特徴量＋スコア | 中 |
| アラート（RSS/JSON差分→Slack/LINE） | 行動へ繋げる | 低〜中 | 予測差分 | 中 |

以降、各機能の **required inputs / outputs / update frequency / UX 案**を具体化します。

### 予測ガードレール（最優先）
- **Inputs**：各銘柄の価格系列、現行モデルの予測（予測価格・区間）。  
- **Outputs**：  
  - `predicted_change_pct_clipped`（例：±X%にクリップ）  
  - `sanity_flags`（例：短期で +100% を超えたら赤旗、区間幅が極端なら黄旗）  
- **更新頻度**：週次（予測生成時に同時生成）。  
- **UX案**：カードに「⚠️予測が不安定（外れ値の可能性）」を表示し、詳細に「なぜ旗が立ったか」を1–2行で説明。Prophet は外れ値が不確実性区間を不自然に広げ得る点を明示しているため、“区間幅の異常”は旗として合理的です。citeturn36search5turn36search0  

### ベースライン比較（AIの価値を証明する柱）
- **Inputs**：価格系列、（可能なら）指数ベンチマーク（TOPIX、S&P 500等）。  
- **Outputs**：同じ週次リバランス条件での  
  - AI戦略 vs. 単純モメンタム（例：12-1モメンタム） vs. ランダム vs. ベンチマーク の成績 JSON  
- **更新頻度**：週次（または月次）  
- **UX案**：  
  - 「累積リターン」  
  - 「月次/週次の勝率」  
  - 「最大DD」  
  - 「回転率」  
  を同一セクションに。  
研究的には、単純予測はアウト・オブ・サンプルで崩れやすいことが知られ、比較枠を作るのは必須です。citeturn9search0turn10search0  

### 確率化（P(up)）＋校正ダッシュボード
現状は回帰（価格予測）ですが、意思決定支援としては **「上がる確率」**が扱いやすいので、回帰出力を確率に落とします。

- **Inputs**：  
  - 予測分布の近似（例：Prophet の `yhat_lower/upper` を正規近似のσに変換）  
  - 実現結果（予測後 N営業日の実現リターン符号）  
- **Outputs**：  
  - `p_up_raw`（未校正）  
  - `p_up_calibrated`（校正後：Platt/温度）  
  - 指標：Brier、log-loss、ECE、信頼性図（reliability diagram）用ビン別集計  
- **更新頻度**：週次（実現が揃うのは遅れるため、常に「確定分だけ更新」）  
- **UX案**：  
  - 上部：全体の Brier/log-loss と “過去○件の確定データで計測”表示  
  - 下部：信頼性図（予測0.6のとき実際に何%上がったか）＋ヒストグラム  
- **根拠**：Brier は確率予報の検証として古典、適切スコアリングの枠組みもあります。citeturn11search0turn11search1  
  Platt（シグモイド）や温度スケーリングは校正の代表手法です。citeturn34search1turn4search7turn35search5  
  さらに scikit-learn には校正曲線・Platt（sigmoid）の実装整理があります。citeturn35search0turn35search5  

> 重要：Prophet の区間は“正しい被覆率を保証しない”前提が明記されています。従って、サイトで「80%信頼区間」と断言せず、「Prophet仮定に基づく区間」＋ **実測被覆率（Calibration of intervals）**の両方を出すのが筋です。citeturn36search0  

### リスク推定とリスク調整（Sharpe等）
- **Inputs**：価格系列、無リスク金利（簡易なら短期金利系列、なければ0近似＋注記）。  
- **Outputs**：  
  - 年率ボラ（例：20日/60日）  
  - 最大DD  
  - β（市場指数に対する回帰）  
  - リスク調整（Sharpe、Sortino風、情報比）  
- **更新頻度**：日次〜週次（J-Quants の株価更新は概ね 16:30 目安）。citeturn13search1  
- **UX案**：  
  - 「予測上昇率」だけではなく、「予測上昇率 / 過去ボラ（≒期待Sharpeの簡易代理）」を並べて表示。  
Sharpe比は実務で広く使われる指標として Sharpe 本人の解説があります。citeturn31search0  

### 因子集約（モメンタム／バリュー／クオリティ／低ボラ）
- **Inputs**：  
  - 価格（モメンタム、ボラ）  
  - 財務（B/P、ROE、利益安定性、投資成長 など）  
- **Outputs**：  
  - 因子別 z-score（市場orセクター内で標準化）  
  - 合成スコア（0–100）  
  - “根拠テキスト”テンプレ（後述）  
- **更新頻度**：  
  - 価格：日次  
  - 財務：四半期〜日次（データ源次第）  
- **UX案**：  
  - “AI予測”と“因子スコア”を同じカード内で並置し、「予測が強いがバリューが弱い」などトレードオフを可視化。  
研究的背景として、モメンタムやバリューが広く検証されてきたこと、また価値とモメンタムが広い資産で観測されることが報告されています。citeturn4search2turn7search1turn29search0  
指数方法論としても、品質・モメンタム等の定義の一例が公開されています。citeturn30search46turn30search3  

### セクター／市場ニュートラル順位（偏り対策）
- **Inputs**：セクター分類（GICS/JPX業種等）、市場指数、銘柄リターン。  
- **Outputs**：  
  - セクター内順位  
  - 市場中立スコア（例：市場β調整後の期待収益）  
- **更新頻度**：週次  
- **UX案**：  
  - ランキングに「セクター内Top」「市場ニュートラルTop」を切替タブで提供。  
最小ボラなどは制約付き最適化で構築されることが説明されており、偏り制御は方法論として自然です。citeturn30search1turn30search4  

### バックテストエンジン（JSON/Sheets出力）
- **Inputs**：予測履歴（あなたの Sheets/JSON）、価格、手数料・スリッページ仮定。  
- **Outputs**：バックテスト結果 JSON（累積リターン、DD、回転率、ヒット率、確率校正指標、サンプル数）。  
- **更新頻度**：週次（新しい予測が出るたびに更新）  
- **UX案**：  
  - 「戦略の定義（ルール）」を必ず明記（例：毎週木曜終値で上位N等）。  
  - ベンチマーク比較と、アウト・オブ・サンプルの区切り表示。  
過剰最適化・データスヌーピングの危険性は古典的に指摘され、検定手続きも提案されています。citeturn10search0turn10search4  

### SHAP風ローカル説明（寄与度）を“静的に配信”
- **Inputs**：特徴量ベクトル（因子、テクニカル、イベントフラグなど）とスコアリングモデル（線形/木/ルール）。  
- **Outputs**：銘柄×週の「寄与度」JSON（上位5特徴と符号・寄与値）。  
- **更新頻度**：週次  
- **UX案**：  
  - 銘柄詳細に「今回の順位が高い理由（上位3要因）」を棒グラフ＋文章で。  
SHAP は予測の説明フレームワークとして整理されています。citeturn35search7turn35search2  
ただし静的サイトでは計算をクライアントでやらず、**オフラインで計算→JSON配信**が現実的です。

## データソースと取り込み（DBなし前提：JSON / Google Sheets）

ここは“実装できること”が価値を決めるので、**公式・一次の仕様**を中心に整理します。あなたの優先指定（J-Quants, EDINET, BOJ, e-Stat, FRED, Alpha Vantage, Stooq, SEC EDGAR）に沿います。

### 日本株：J-Quants（価格・財務・イベント）
- **強み**：更新タイミングが公開され、運用スケジュールを固定できる（株価 16:30頃、財務 18:00速報/24:30確報など）。citeturn13search1turn13search0  
- **留意点**：Version2への移行が進んでおり、旧版ドキュメントがレガシー扱い。レートリミットは存在し基準は調整され得る。citeturn21search3turn21search1  
- **プラン差**：JPXの案内で、無料は12週間遅延・過去2年等の制約が明記されています（データ要件に直結）。citeturn20search1turn20search6  
- **推奨リフレッシュ**：日次（16:40以降に当日分OHLC取得、財務は確報に合わせて翌日更新でも良い）。

> 【レート上限（数値）】は公式ドキュメントで明示されない場合があるため、実装では「429/制限応答を前提に指数バックオフ＋キャッシュ」で設計し、プラン別の目安値は“非公式情報”として注記するのが安全です。citeturn21search3turn20search2  

### 日本開示：EDINET API（金融庁）
- **公式仕様書（Version2, 2026年1月）**がPDFで公開され、書類一覧API・書類取得API・更新タイミング等が整理されています。citeturn16view0turn15view0  
- **推奨リフレッシュ**：日次（提出書類の取得は“提出当日”の取りこぼしがあるので、当日＋翌日朝の二段階などにする）。

### 日本マクロ：日本銀行（BOJ）時系列API（2026年開始）
- 2026年2月18日に、BOJ時系列検索サイトのAPI提供開始が告知され、JSON/CSV取得ができるとされています。citeturn13search6turn17search1  
- **利用マニュアル（2026年2月18日）**で、エンドポイント（`/getDataCode`, `/getDataLayer`, `/getMetadata`）やパラメータが明示されています。citeturn19view0turn19view1  
- **推奨リフレッシュ**：日次（マニュアルでは検索サイトのデータ公開が概ね 8:50頃と記載）。citeturn19view0turn17search8  

### 日本統計：e-Stat API
- e-Stat API はユーザー登録とアプリケーションIDが必要で、仕様書が公開されています。citeturn12search2turn12search4turn12search3  
- **推奨リフレッシュ**：統計の更新頻度に依存（CPI等は月次）。サイト上では “系列更新に合わせて自動取得可能”の趣旨が説明されています。citeturn12search6  

### 米国マクロ：FRED API
- FRED API は利用規約で、第三者著作権データの取扱い、表示義務、API制限の可能性などが明示されています。citeturn28search0  
- **推奨リフレッシュ**：系列ごとの更新頻度に依存（月次/週次/日次）。

### 米国開示：SEC EDGAR
- SEC はEDGARへの自動アクセスに対し **10リクエスト/秒**のレート制御等を告知しています（公平アクセス目的）。citeturn22search0  
- **推奨リフレッシュ**：日次〜週次（ファイリングの有無により差分取得）。

### 価格データの補助：Alpha Vantage / Stooq
- **Alpha Vantage**：公式のプレミアム案内では「標準API使用上限（例：25/日）」が言及されており、無料枠の細部は変動し得ます（実装では必ず最新を確認）。citeturn23search5turn22search9  
- **Stooq**：利用規約で、サイト上データの再配布禁止、免責、またS&P指数データ等のライセンス制約が明記されています（公開サイトでの再配布は特に注意）。citeturn27view0  

> 結論：公開静的サイトの“裏側取得”は自由でも、**再配布（あなたがJSONとして公開すること）**が禁止・制限されるデータがあるため、必ず各ソースのToS/ライセンスに合わせて「公開してよい加工物」を定義してください。citeturn27view0turn28search0turn16view0  

### 取得→保存（JSON/Sheets）の擬似コード例

#### Python（J-Quants → JSONに保存）
```python
import json
from datetime import date, timedelta

def fetch_prices_jquants(code: str, start: str, end: str) -> list[dict]:
    # 実装はJ-Quants公式SDK/HTTPに合わせて差し替え
    # 返り値: [{"date":"2026-02-19","open":..,"high":..,"low":..,"close":..,"volume":..}, ...]
    raise NotImplementedError

def save_json(path: str, obj: object) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

today = date.today()
start = (today - timedelta(days=400)).strftime("%Y-%m-%d")
end = today.strftime("%Y-%m-%d")

prices = fetch_prices_jquants("7203", start, end)  # 例：トヨタ
save_json("dashboard/data/prices/7203.json", prices)
```

#### Python（EDINET：書類一覧→重要書類だけJSON化）
```python
import requests
import json
from datetime import date

EDINET_API_KEY = "YOUR_KEY"  # GitHub Secretsに入れる
BASE = "https://api.edinet-fsa.go.jp/api/v2"

def get_doc_list(on_date: str) -> dict:
    # 仕様書に従ってパラメータ指定（例：type=2など）
    params = {"date": on_date, "type": 2}
    headers = {"Authorization": f"Bearer {EDINET_API_KEY}"}
    r = requests.get(f"{BASE}/documents.json", params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()

doc_list = get_doc_list(date.today().strftime("%Y-%m-%d"))
with open("dashboard/data/edinet/doclist.json", "w", encoding="utf-8") as f:
    json.dump(doc_list, f, ensure_ascii=False, indent=2)
```
（EDINET APIの構成・更新タイミング等は金融庁仕様書に従うことが前提）。citeturn16view0

#### Python（BOJ API：マクロ系列→JSON）
```python
import requests, json

# 例：/getDataCode は series code 指定でデータ取得（詳細はマニュアル）
url = "https://www.stat-search.boj.or.jp/api/v1/getDataCode"
params = {
  "format": "json",
  "lang": "en",
  "db": "CO",
  "startDate": "202401",
  "endDate": "202504",
  "code": "TK99F1000601GCQ01000"
}
r = requests.get(url, params=params, headers={"Accept-Encoding": "gzip"}, timeout=30)
r.raise_for_status()
data = r.json()

with open("dashboard/data/macro/boj_CO.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
```
（エンドポイント・パラメータは BOJ マニュアル参照）。citeturn19view0  

## 軽量モデリングとバックテスト（静的サイト前提の“オフライン実行”設計）

ここは「モデルを賢くする」より、**検証可能性**を最大化するのが勝ち筋です。特に、予測が不安定な段階では “高度モデル”より “壊れないベースライン＋校正と評価”が重要です。citeturn9search0turn10search0  

### 推奨モデル（軽量・説明可能）
- **ルールベース**：  
  - 例：12-1モメンタム上位、低ボラ上位、クオリティ上位等（因子研究・指数方法論を参考に定義）。citeturn30search46turn30search4  
- **ロジスティック回帰（分類）**：  
  - “来週上がるか”を目的にし、特徴量は因子＋イベントフラグ＋市場レジーム。  
  - 出力確率を Platt/温度で校正し、Brier/log-lossで評価。citeturn35search5turn4search7turn11search0  
- **ヒューリスティック・アンサンブル**：  
  - AI予測（回帰）＋因子スコア＋リスク（罰則）を加重平均し、最終順位を作る。  
  - “なぜそうなったか”を寄与度で説明しやすい。

### 評価指標（最低限そろえるセット）
- **リターン系**：累積リターン、年率、最大DD、回転率、手数料控除後。  
- **リスク調整**：Sharpe（ただし推定誤差に注意）。citeturn31search0  
- **分類（上がる確率）**：Brier、log-loss、信頼性図、ECE。citeturn11search0turn35search5  
- **過剰適合対策**：ウォークフォワード、ホールドアウト、必要なら Reality Check/バックテスト過剰適合に関する考え方を注記。citeturn10search0turn10search4  

### パイプライン（Mermaid：静的サイト向け）
```mermaid
flowchart LR
  A[データ取得<br/>J-Quants/EDINET/BOJ/e-Stat/FRED] --> B[特徴量生成<br/>因子・イベント・リスク]
  B --> C[予測生成<br/>AI(回帰) + ルール/分類]
  C --> D[ガードレール<br/>外れ値・安定性フラグ]
  D --> E[バックテスト/検証<br/>WF・コスト・ベンチマーク]
  E --> F[確率校正<br/>Platt/温度]
  F --> G[成果物出力<br/>JSON/Sheets]
  G --> H[静的サイト表示<br/>Charts + 説明文]
  E --> I[通知/差分<br/>Slack/LINE/RSS]
```

### バックテスト擬似コード（週次リバランス）
```python
def backtest_weekly(signal, prices, rebalance_day="THU", top_n=10, fee_bp=10):
    """
    signal: {(date, ticker): score}  # 予測週の順位スコア
    prices: {(date, ticker): close}  # 終値
    fee_bp: 取引コスト（bps）
    """
    equity = 1.0
    holdings = {}  # ticker -> weight
    history = []

    for reb_date in weekly_rebalance_dates(prices, rebalance_day):
        # 1) その週の候補を取り、上位Nを等金額
        picks = top_tickers(signal, reb_date, top_n)
        target = {t: 1.0/top_n for t in picks}

        # 2) 取引コスト（簡易）：回転率×fee
        turnover = turnover_from(holdings, target)
        equity *= (1 - turnover * fee_bp / 10000.0)

        # 3) 次リバランス日までのリターン
        next_date = next_rebalance_date(reb_date)
        port_ret = portfolio_return(target, prices, reb_date, next_date)
        equity *= (1 + port_ret)

        holdings = target
        history.append({"date": str(reb_date), "equity": equity, "turnover": turnover, "port_ret": port_ret})

    return history
```

### 校正擬似コード（Platt／温度の“最低限”）
```python
# Platt（シグモイド）例：モデルのスコア→確率にロジスティック回帰を当てる
# 温度スケーリング例：logits/T を最小 log-loss になるTで最適化（多クラスはsoftmax）。
```
（実装は scikit-learn の calibration を参照すると堅い）。citeturn35search5turn35search0  

## 説明可能性とUI（静的サイトで成立する要素）

UIは後で変えられる前提でも、**「何を説明するか」**の設計は先に固めた方が、データ設計がブレません。

### 静的サイトで実現しやすい可視化（推奨配置）
- トップ（ランキング）  
  - 予測：`期待リターン`、`P(up)`（校正済み）、`リスク（ボラ/最大DD）`、`イベント（決算/配当）`  
  - “バッジ”：外れ値警告、データ遅延、決算跨ぎ注意  
- 銘柄詳細  
  - 価格チャート＋予測点（ただし“未来線”を強調しすぎない）  
  - 因子スコア（セクター内相対）  
  - ローカル説明（寄与度Top3〜5）  
- 精度ページ  
  - 信頼性図（reliability diagram）  
  - 予測確率分布ヒストグラム  
  - 週次成績（累積、DD、Sharpe）  
- バックテストページ  
  - 戦略定義（ルール）を固定表示（隠さない）

### 例：日本語ツールチップ文（そのまま使えるテンプレ）
- **P(up)（校正済み）**  
  「この確率は、過去の確定データに基づき“当たりやすさ”が一致するよう補正しています（例：0.60と表示された銘柄群が、平均で約60%上昇する状態を目標）。」  
- **予測区間（Prophet）**  
  「Prophetの仮定（将来のトレンド変化が過去と同程度起きる等）に基づく区間です。実測での被覆率（どれくらい区間内に収まったか）も併記しています。」citeturn36search0  
- **最大ドローダウン**  
  「一定期間における“高値からの最大下落率”です。リターンが高くても、DDが大きい戦略は資金管理が難しくなります。」  
- **Sharpe比**  
  「リスク（変動）1あたりの超過リターン指標です。期間や推定誤差に依存するため、他の指標と併せて確認してください。」citeturn31search0  

### SHAP風寄与度をオフラインで計算して配信する方法
- スコアが線形（例：`score = Σ w_i x_i`）なら、寄与度は単に `w_i x_i` を保存すればよい（最速）。  
- 木モデル等を使うなら、SHAPの考え方に沿って寄与度を計算し JSONに格納（クライアント計算不要）。citeturn35search7turn35search2  

クライアント側（JS）は JSON を読むだけにして、表示は Chart.js 等で十分（現状 repo と同じ方針で拡張可能）。

## 実装ロードマップ（現状：データ収集段階を前提）

### ステップ別計画（労力：低/中/高）
1) **予測ガードレール導入**（低）  
   - クリップ、異常フラグ、対数変換検討、外れ値説明。citeturn36search5  

2) **ベースライン比較の常設**（低）  
   - 12-1モメンタム等の単純戦略、ベンチマーク比較。citeturn4search2turn9search0  

3) **確率化（P(up)）と校正ダッシュボード**（中）  
   - Brier/log-loss、信頼性図、Platt/温度。citeturn11search0turn4search7turn35search5  

4) **バックテストを“実運用想定”へ**（中）  
   - 手数料・スリッページ、WF、取引制約、ベンチマーク。  
   - 過剰適合の注意喚起（Reality Check等の概念を用語集に）。citeturn10search0turn10search4  

5) **データ基盤の段階移行（日本株→J-Quants/EDINET）**（中〜高）  
   - 取得時刻に合わせた Actions スケジュール設計。citeturn13search1turn16view0turn20search6  

6) **因子統合とセクター中立**（中）  
   - 指数方法論（MSCI/S&P）を参考に定義を固定。citeturn30search46turn30search3  

7) **説明（寄与度）を標準化**（中）  
   - 線形寄与度→必要ならSHAPへ。citeturn35search7  

### 必要ライブラリ・ツール（現行 repo からの差分中心）
- Python：pandas / numpy / requests / statsmodels or scikit-learn（校正・分類）citeturn35search0turn35search5  
- データ：J-Quants API、EDINET API、BOJ API、e-Stat API、FRED API citeturn13search1turn16view0turn19view0turn12search4turn28search0  
- CI：GitHub Actions（現状踏襲）  
- 可視化：Chart.js等（現状踏襲）

### セキュリティ・プライバシー・法務（重要）
- **APIキー管理**：GitHub Secretsに格納し、リポジトリには入れない。  
- **利用規約・再配布**：Stooq は再配布禁止が明記。FRED も第三者著作権や表示義務に言及。EDINET/BOJ/e-Statも規約遵守が前提。citeturn27view0turn28search0turn16view0turn19view0turn12search4  
- **投資助言規制への配慮**：日本では投資助言・代理業に登録要件があり、個別具体的な売買助言かどうか等で扱いが変わり得ます。金融庁のガイドブックやFAQで枠組みが説明されています。citeturn32search2turn32search1turn32search4turn32search6  
  - 実装上は、サイト上で **「情報提供であり投資助言ではない」「不確実性」「過去成績は将来を保証しない」**等を明確化し、モデルの限界（校正・検証範囲）も表示するのが安全です。

### 本番リリース前チェックリスト（抜粋）
- データ更新時刻と遅延表示（J-Quants/BOJ等の更新タイミングに整合）citeturn13search1turn19view0  
- 予測の外れ値フラグが機能している  
- ベースラインとベンチマーク比較が常に表示される  
- 校正・評価は「確定データ数」とセットで出る（母数ゼロなら“未評価”と明記）  
- 取引コスト仮定が表示される  
- データ再配布・ライセンス違反がない（特にStooq）citeturn27view0  

## 参考例・JSONスキーマ案（予測／評価／特徴量）

最後に、静的サイト運用に向いた「差分更新しやすい」スキーマ例を提示します。現状 repo の `predictions.json` を拡張する想定です（未指定事項は仮定：対象は株式、予測ホライズンはN営業日、通貨は銘柄市場に依存）。

### predictions.schema.json（例）
```json
{
  "as_of": "2026-02-20",
  "horizon_trading_days": 5,
  "universe": "nikkei225|sp500|custom",
  "items": [
    {
      "date": "2026-02-19",
      "ticker": "7203.T",
      "price_close": 2875.0,
      "pred": {
        "expected_return": 0.012,
        "expected_price": 2909.5,
        "interval": { "level": 0.8, "lower_price": 2830.0, "upper_price": 2990.0 },
        "p_up_raw": 0.62,
        "p_up_calibrated": 0.58,
        "sanity_flags": ["OK"]
      },
      "risk": {
        "vol_20d_ann": 0.22,
        "max_drawdown_252d": -0.34,
        "beta_252d": 1.05
      },
      "signals": {
        "momentum_12_1_z": 0.7,
        "value_z": -0.2,
        "quality_z": 0.4,
        "low_vol_z": 0.5,
        "composite_score_0_100": 72
      },
      "events": {
        "earnings_date": "2026-02-05",
        "ex_dividend_date": null,
        "sec_filing_recent": false
      },
      "explain": {
        "top_factors": [
          { "name": "12-1モメンタム", "contrib": 0.31 },
          { "name": "低ボラ", "contrib": 0.18 },
          { "name": "決算後日数", "contrib": -0.05 }
        ],
        "template_id": "jp_v1"
      }
    }
  ]
}
```

### backtest.schema.json（例）
```json
{
  "strategy_id": "weekly_top10_equalweight_v1",
  "rules": {
    "rebalance": "weekly",
    "top_n": 10,
    "weighting": "equal",
    "fee_bp": 10,
    "slippage_bp": 5
  },
  "period": { "start": "2025-01-01", "end": "2026-02-19" },
  "benchmark": "TOPIX|SPY",
  "results": {
    "cagr": 0.08,
    "max_drawdown": -0.22,
    "sharpe": 0.62,
    "turnover_avg": 0.85
  },
  "equity_curve": [
    { "date": "2025-01-09", "equity": 1.00 },
    { "date": "2025-01-16", "equity": 1.01 }
  ]
}
```

### calibration.schema.json（例）
```json
{
  "target": "p_up",
  "method": "platt|temperature",
  "fit_window": { "start": "2025-01-01", "end": "2026-02-19" },
  "metrics": {
    "brier": 0.23,
    "logloss": 0.66,
    "ece": 0.04,
    "n": 420
  },
  "reliability_bins": [
    { "bin": "0.5-0.6", "p_mean": 0.55, "freq_pos": 0.52, "n": 80 }
  ]
}
```

## 主要参考文献・一次資料（抜粋）

- モメンタム：Jegadeesh & Titman (1993) citeturn4search2  
- 因子（3因子/5因子）：Fama & French (1993, 2015) citeturn5search5turn6search6  
- 低リスク：Frazzini & Pedersen “Betting Against Beta” (NBER) citeturn6search1  
- ボラと期待リターン：Ang et al. (NBER) citeturn6search0  
- アナリスト推奨：Womack (1996)、Barber et al. (2001) citeturn8search0turn8search3  
- PEAD：Bernard & Thomas (1989) citeturn5search7  
- マクロ予測の不安定性：Welch & Goyal (2008) citeturn9search0  
- Sharpe比：Sharpe (1994) citeturn31search0  
- 校正：Brier (1950) citeturn11search0、Guo et al. (2017) citeturn4search7、Platt (1999) citeturn34search1、scikit-learn calibration citeturn35search5  
- バックテスト過剰適合：White (2000) citeturn10search0、Bailey et al. (2016) citeturn10search4  
- SHAP：Lundberg & Lee (2017) citeturn35search7  
- データソース一次資料：J-Quants更新時刻 citeturn13search1、EDINET API仕様書(2026/1) citeturn16view0、BOJ APIマニュアル(2026/2) citeturn19view0、e-Stat API仕様 citeturn12search4、FRED Terms citeturn28search0、SEC EDGAR rate control citeturn22search0、Stooq ToS citeturn27view0