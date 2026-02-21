# フェーズ17〜19の深掘り調査と追加設定提案レポート

## エグゼクティブサマリ

本レポートは、提示いただいた「自動AI株式分析 & 追跡ワークフロー」の設定（スクリーニング→予測→追跡→通知→JSON出力）を前提に、計画中の **フェーズ17〜19（J-Quants API / Finnhub / Financial Modeling Prep）** を「何が強化でき、どこに落とし穴があり、どう設定・統合すると堅牢になるか」を深掘りする。現行実装（GitHub: nakaj1214/trader）では **価格・企業情報・一部ファンダが yfinance に強く依存**しており、安定運用と精度（特に JP 銘柄の情報欠損、ニュース由来のイベント影響、グローバル財務の穴埋め）の観点から、データソースの多重化は合理的である。特に **J-Quants API V2 のAPIキー認証化**と、**CSV一括提供**・**分足/Tick提供**など提供形態が強化されており、JP側の基礎データの信頼性・再現性向上に寄与し得る。citeturn6search1turn0search7turn8search7

結論としての推奨は以下。

- **JP（nikkei225）ファンダ・銘柄マスタは J-Quants API を第一優先**にし、yfinance は補助（欠損時のフォールバック）に寄せる。J-Quants API は上場銘柄一覧、株価（調整/非調整）、財務（四半期）、配当、決算予定などを提供し、JPの“情報欠落”を構造的に減らせる。citeturn0search7turn6search1  
- **USのニュース・センチメントは Finnhub を“信号生成専用”にして導入**し、重いNLP（要約/分類）は必要になってから OpenAI 等に拡張する（現行repoには OpenAI設定があるがコード上は未使用）。Finnhubの `company_news` / `news_sentiment` はUS企業向けとしてクライアント実装上も明示されているため、S&P500/NASDAQ100用途と相性が良い。citeturn5search0turn10search5turn0search10  
- **グローバル財務の最終フォールバック（FMP）は “stable” エンドポイントとレート制御・キャッシュが必須**。FMP公式はベースURL `https://financialmodelingprep.com/stable/` とAPIキー付与方法・429への対処を案内している。citeturn1search4turn0search5  
- 設定としては単なる `enabled: true/false` だけでは運用が不安定になりやすい。**APIキー/レート/キャッシュTTL/シンボル変換/優先順位/データ鮮度**を設定可能にし、「どのデータが、いつ、どのソースから来たか」をメタに残すのが、後から精度・障害分析を回すうえで決定的に効く（特に“ニュース・決算・配当”はデータ整合性が崩れやすい）。

---

## 現行ワークフローにおける追加データの“刺さりどころ”

現行repoは、(a) 静的ユニバースCSV（sp500/nasdaq100/nikkei225）→(b) yfinanceでOHLCV取得→(c) テクニカル指標でスコアリング→(d) Prophetで5営業日先予測→(e) Sheetsに記録→(f) 追跡・校正・比較をJSON出力、というパイプラインである（README および `screener.py`/`predictor.py`/`exporter.py` の構造から確認）。ここにフェーズ17〜19を入れる場合、主な“刺さりどころ”は次の3つ。

- **スクリーニングの入力特徴量を増やす**（技術指標中心 → 価格＋ファンダ＋センチメントへ）  
- **エンリッチ（説明・根拠・イベント）を強化する**（決算予定、配当、ニュース、投資家売買など）  
- **yfinance依存を減らす**（欠損・仕様変更・取得失敗の影響を抑える）

特に現行 `predictor.py` では Prophet の不確実性区間を「95% CI」として扱い `1.96` で正規近似しているが、Prophetの `interval_width` はデフォルト `0.8`（80%予測区間）であり、**確率化ロジックは現状のままだと系統的にズレる**可能性が高い。新しいデータを足しても、確率や校正を意思決定に使うならまずここを整合させる価値が高い。citeturn7search0

---

## サービス別深掘り調査

### J-Quants API 日本株ファンダメンタルデータ強化

**何が取れるか（JP銘柄での価値）**  
entity["organization","日本取引所グループ","exchange group japan"]が案内する J-Quants API は、個人向けに **株価（調整/非調整のOHLC）、四半期財務、上場銘柄一覧、配当、決算発表予定**などを提供する。特に「調整済株価」「過去日の上場銘柄一覧」などは、バックテストや特徴量生成の“再現性”に効く。citeturn0search7

**V2の重要点（実装・運用目線）**  
2025年12月の更新として **J-Quants API V2** が開始され、認証がトークン方式から **APIキー方式**へ移行し、レスポンスの列名最適化（短縮）も行われた。V1は移行期間として継続提供されるが、廃止予定である旨は複数の公式資料で示唆されているため、新規実装はV2前提が安全である。citeturn6search1turn6search0turn8search7turn8search12

**2026年1月の追加（CSV/高頻度）**  
2026-01-19 の公式発表で、Lightプラン以上向けに **CSV形式による一括取得**、および **株式の分足・Tickデータ（アドオン、月額5,500円）**が追加されている。分析用途（特徴量の検証、再学習）ではCSVが運用負荷を下げる一方、現行の「週次×Top10」用途だけならまず日足＋財務で十分なことが多い（高頻度は“やること”と“やる意味”が急増する）。citeturn6search1turn6search0

**導入時の落とし穴（JP特有）**  
- シンボル体系：現行は yfinance ティッカー（例 `7203.T`）だが、J-Quants側は4桁コード主体の設計が多い。V2のベースURLが `https://api.jquants.com/v2` とされるクライアント実装も存在する。どのIDを正として内部キーにするか（4桁コード/ISIN/yfinance ticker）を最初に固定しないと、後でデータ統合が破綻しやすい。citeturn8search5turn0search7  
- 大容量時のページング：レスポンスに `pagination_key` が付く場合がある（旧仕様書上の共通注意）。V2でも大量データ取得では同様の概念が残る可能性が高いため、バルク/日次取得ジョブには「ページング前提」の実装が必要。citeturn6search3  
- 財務データの欠損・不一致：EDINET XBRL由来の制約で、PDF開示と一致しない/企業独自タクソノミ項目が欠ける場合がある（これはPro側FAQだが、XBRLベースの提供である以上、同種の注意は一般に重要）。ファンダ特徴量は「欠損に強い集約（TTMや前年同期比など）」を設計し、欠損率をモニタするのが実務的。citeturn6search12

---

### Finnhub ニュース・センチメントシグナル追加

**何が取れるか（US銘柄×短期予測で効きやすい）**  
Finnhub は株価・企業情報・財務に加え、**企業ニュース**や **ニュース・センチメント**系のデータを提供する。公式クライアント実装（例：Python/JS/PHPなど）では `company_news` や `news_sentiment` が代表的エンドポイントとして扱われている。citeturn10search5turn10search3turn5search14

特に「週次5営業日先」の方向性予測では、テクニカルだけでなく  
- 決算・ガイダンス  
- 製品発表  
- 訴訟・規制  
- M&A  
などのニュース駆動イベントが外れ要因になりやすいため、「ニュース量」「センチメント」「直近のネガ/ポジ比率」をガードレールや説明要因として加えるのは合理的である。

**US限定の注意**  
いくつかのクライアント実装上、企業ニュース/ニュースセンチメントは **US企業のみ**対応と明記されている。提示設定の `markets: sp500/nasdaq100` には合致するが、`nikkei225` には基本的に適用しない設計が妥当。citeturn5search0turn0search10

**実装で重要なポイント**  
- レート制御：無料・有料プランの呼び出し上限はプランごとに異なる（60 req/min などの記述が複数の統合資料に見られる）。ここは契約プランで変動し得るため、**設定で rpm を持つ**のが安全。citeturn2search0turn2search4  
- “センチメント”の扱い：  
  - 使い方を「ランキングの微調整」なのか「弾くガードレール」なのかで設計が変わる  
  - 遅延評価（翌週実績）と整合させるなら、ニュース特徴量は **予測時点まで**の情報に限定（リーク防止）  
- データ権利：ニュース本文の全文取得・再配布は契約上NGのことが多い。システムは「リンク＋要点（自前要約）」程度までに留める設計が安全（要約も元記事のコピーにならないよう注意）。

---

### Financial Modeling Prep グローバル財務データ補完

**何が取れるか（グローバルの“穴埋め”としての価値）**  
Financial Modeling Prep（以下FMP）は、株価・企業プロフィール・財務諸表など多数のエンドポイントを提供しており、**yfinanceの欠損や取得失敗のフォールバック**として有用になり得る。公式のQuickstartでは、ベースURLとして `https://financialmodelingprep.com/stable/` を提示し、APIキーはクエリ `apikey=...` で付与する。citeturn1search4

**レガシー罠と“stable”固定の重要性**  
FMPのドキュメントには「レガシーAPIエンドポイントを閲覧中、最新はこちら」といった注意が複数存在し、実運用では **stable系に寄せる**ほうが安全。citeturn1search1turn1search4

**料金・レート制限（運用設計に直結）**  
公式Pricingでは、Free は 250 calls/day、上位プランは calls/min が増える等が示されている。Top10銘柄でも、財務・株価・指標を個別に叩くと上限に近づくため、**キャッシュとバッチ設計**（必要最小限の取得・更新頻度の分離）が必須。citeturn0search5

**財務データ：as-reportedの扱い**  
FMPは「as reported（提出資料どおり）」の財務ステートメント取得も案内している。会計項目の定義揺れを吸収するには、まずは “少数の頑健な特徴量（売上成長、粗利率、営業利益率、FCFマージン等）” に絞り、後から項目を増やすのが現実的。citeturn1search3

---

## 統合設計と推奨データモデル

### 推奨アーキテクチャ

現行repoはモジュールごとに yfinance を直接呼ぶ構造が多いため、フェーズ17〜19を足すと「どこでどのプロバイダを使うか」が散らかりやすい。そこで **Provider層（データ取得）を切り出して、機能単位で優先順位とフォールバックを統制**するのが最も効果的である。

```mermaid
flowchart LR
  subgraph Pipeline[既存パイプライン]
    A[Screening] --> B[Prediction]
    B --> C[Tracking]
    C --> D[Exporter/JSON]
  end

  subgraph Providers[データプロバイダ]
    YF[yfinance]
    JQ[J-Quants API]
    FH[Finnhub]
    FMP[FMP]
  end

  subgraph Cache[キャッシュ/スナップショット]
    K[(Local cache)]
  end

  A -->|価格/出来高| Providers
  A -->|ファンダ(必要なら)| Providers
  D -->|イベント/エビデンス/ニュース| Providers
  Providers <--> K
```

### 統合時に決めるべき“正規化ルール”

- **シンボル正規化（内部キー）**：  
  - US: `AAPL` のようなティッカー  
  - JP: yfinance は `7203.T` だが、J-Quantsは4桁コードが中心になりやすいので、内部キーを「4桁」か「.T」かで統一し、相互変換テーブルを必ず持つ（上場銘柄一覧データセットが使える可能性がある）。citeturn0search7turn8search8  
- **データ鮮度（as of）**：財務は発表日・対象期間が重要。予測時点以後の情報を混ぜるとリークになるため、取得データに `as_of_date` / `source_timestamp` を付けて保存する。  
- **通貨・単位**：JPはJPY、USはUSDが混在しやすい。比率（マージン、ROE等）中心に寄せるか、為替で統一するかを明示する。

---

## 追加するとよい設定項目

提示の `enabled` フラグだけだと、トラブル時に「どこで詰まったか」「なぜ欠損したか」「レート制限か、認証か」が追えない。そこで、最低限下記のような設定ブロックを追加することを推奨する（値は例）。

### 推奨追加設定（YAML例）

```yaml
data_sources:
  # 市場ごとの優先順位
  priority:
    us:
      prices: ["yfinance", "fmp"]
      fundamentals: ["fmp", "yfinance"]
      news: ["finnhub"]
    jp:
      prices: ["jquants", "yfinance"]
      fundamentals: ["jquants", "yfinance"]
      events: ["jquants", "yfinance"]

  # API共通
  http:
    timeout_sec: 20
    max_retries: 3
    backoff_sec: 2
    jitter: true
  cache:
    enabled: true
    backend: "file"          # file / sqlite / redis など
    dir: ".cache"
    ttl_hours:
      prices_daily: 24
      fundamentals: 168      # 週1更新前提
      news: 3                # 数時間〜半日
  snapshot:
    enabled: true
    dir: "data_snapshots"    # 取得データの再現性確保

jquants:
  enabled: true
  api_version: "v2"
  api_key_env: "JQUANTS_API_KEY"
  base_url: "https://api.jquants.com/v2"  # クライアント実装例
  rate_limit_rpm: 60                      # 契約プランに合わせる
  pagination:
    enabled: true
    max_pages: 50
  datasets:
    prices_daily: true
    financials_quarterly: true
    dividends: true
    earnings_calendar: true
  symbol_mapping:
    jp_code_to_yfinance_suffix: ".T"

finnhub:
  enabled: true
  api_key_env: "FINNHUB_API_KEY"
  base_url: "https://finnhub.io/api/v1"
  rate_limit_rpm: 60
  sentiment:
    lookback_days: 7
    min_articles: 5
    decay_half_life_days: 2
    output_fields:
      - "sentiment_score"
      - "buzz"
      - "bearish_percent"
      - "bullish_percent"

fmp:
  enabled: true
  api_key_env: "FMP_API_KEY"
  base_url: "https://financialmodelingprep.com/stable/"
  rate_limit:
    calls_per_day: 250       # Free想定。プランで変更
  endpoints:
    use_stable_only: true
  fundamentals:
    period: "annual"         # freeでも成立しやすい範囲から
    limit: 5
```

上のうち、FMPの `base_url` やAPIキー付与、429（Too many requests）への対処は公式Quickstartが明示しているため、実装はこの仕様に合わせるのが良い。citeturn1search4  
J-QuantsはV2でAPIキー方式に移行しているため、設定面でも “V2前提” を明確化するのが安全。citeturn6search1turn8search7

### 追加設定として有効なもの（機能面）

- **流動性フィルタ**：min_market_cap だけだと、出来高が薄い銘柄・価格が飛ぶ銘柄を拾う可能性が残る。`min_avg_dollar_volume`（平均出来高×価格）を入れると、実務上のノイズが減りやすい。  
- **イベント禁則**：決算直前（n日前）や配当落ち直前は値動きが特殊になることがあるため、`exclude_days_to_earnings <= N` のようなルールを設定で切替可能にする（J-Quants APIは決算発表予定データセットを提供している）。citeturn0search7  
- **Prophet設定の露出**：`interval_width`、`uncertainty_samples`、`holidays` の有無などをconfigに出す。とくに `interval_width` はデフォルト80%で、ここが確率化ロジックに直結する。citeturn7search0turn7search6

---

## 導入時の検証観点と最小テスト

フェーズ17〜19は「データの追加」だが、実際には **ロジックと評価の変更**でもある。最小限、次を導入前後で必ず確認すると、後戻りコストが大きく下がる。

- **データ完全性テスト**：Top10銘柄に対し、(a) 財務指標欠損率、(b) ニュース取得件数、(c) 企業マスタ一致率（JPコード↔.T）を日次でログ化。  
- **リーク防止テスト**：財務・ニュース特徴量が「予測日より後の情報」を含まないことを機械的に検査（`as_of` を比較）。  
- **モデル・信頼区間整合**：Prophetの `interval_width` が80%なら、`compute_prob_up` の `1.96` 前提は成立しない。  
  - 対応案A：Prophetを `interval_width=0.95` に変更して 1.96 と整合させる  
  - 対応案B：`interval_width` から対応する z 値で逆算する（例：80%なら z≈1.2816）  
  Prophetドキュメントは `interval_width` が予測分布の分位点であり、デフォルト0.8で80%予測区間であることを明示している。citeturn7search0  

---

## 参照リンク集（実装時にすぐ使うもの）

```text
J-Quants API（JPX公式概要）:
https://www.jpx.co.jp/english/markets/other-data-services/j-quants-api/

J-Quants API 機能拡充（V2/APIキー/CSV/分足・Tick）公式リリース:
https://www.jpx.co.jp/corporate/news/news-releases/6020/20260119.html

J-Quants 公式Quick Start（V2ノートブックあり）:
https://github.com/J-Quants/jquants-api-quick-start

FMP 公式Quickstart（stable URLとapikey付与、429含む）:
https://site.financialmodelingprep.com/developer/docs/quickstart
FMP 公式Pricing:
https://site.financialmodelingprep.com/developer/docs/pricing

Prophet interval_width（デフォルト0.8=80%）:
https://facebook.github.io/prophet/docs/diagnostics.html
```

