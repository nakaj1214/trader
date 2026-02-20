# 実装計画書

---

## 実装済みフェーズ一覧

| フェーズ | 内容 | 状態 |
|---------|------|------|
| 11 | ショートインタレスト補助情報（バックエンド完了・UI接続完了） | **実装済み** |
| 12 | 機関投資家保有状況（バックエンド完了・UI接続完了） | **実装済み** |
| 13 | 52-Week High Momentum ファクター追加 | **実装済み** |
| 14 | 買い時・売り時ガイド（ダッシュボード） | **実装済み** |
| 15 | 日本株データ収集バックエンド | **実装済み** |
| 16 | ダッシュボード分離（米国株・日本株） | **実装済み** |

---

## フェーズ11: ショートインタレスト補助情報（実装済み・UI接続修正済み）

### 実装内容

**`src/enricher.py`**
- `enrich_short_interest(ticker, info)` を追加
- `yf.Ticker(t).info` から `shortRatio`, `shortPercentOfFloat` を取得
- signal 判定: `short_pct_float > 0.20` → `high_short`, `> 0.10` → `moderate_short`, それ以外 → `neutral`
- 取得失敗時は `None` を返す

**`src/exporter.py`**
- `build_predictions_json()` 内で `short_interest` キーを出力
- `if ticker_data.get("short_interest")` で存在チェック

**`dashboard/stock.html`**
- `id="short-interest-panel"` のコンテナ `<div>` を追加（`sizing-panel` 直下）
- 欠落していたDOMにより `renderShortInterestPanel` が即 return していた問題を修正済み

**`dashboard/js/stock.js`**
- `renderShortInterestPanel(prediction)` を追加
- `#short-interest-panel` に Short Ratio・空売り比率・シグナルを表示

**`tests/test_enricher.py`** — TestEnrichShortInterest（4テスト）追加

### 出力スキーマ（`predictions.json`）

```json
{
  "short_interest": {
    "short_ratio": 3.2,
    "short_pct_float": 0.052,
    "signal": "neutral",
    "data_note": "月次更新・参考値（yfinance）"
  }
}
```

---

## フェーズ12: 機関投資家保有状況（実装済み・UI接続修正済み）

### 実装内容

**`src/enricher.py`**
- `enrich_institutional_holders(ticker)` を追加
- `yf.Ticker(ticker).institutional_holders` から上位5機関を取得
- カラム名を動的検出（`holder`/`name` を含む列名）
- `institutional_pct` を合計保有比率として計算
- `data_note` に45〜75日遅延の注記を付与

**`src/exporter.py`**
- `if ticker_data.get("institutional")` で `institutional` キーを出力

**`dashboard/stock.html`**
- `id="institutional-panel"` のコンテナ `<div>` を追加（`short-interest-panel` 直下）
- 欠落していたDOMにより `renderInstitutionalPanel` が即 return していた問題を修正済み

**`dashboard/js/stock.js`**
- `renderInstitutionalPanel(prediction)` を追加
- `#institutional-panel` に機関保有率・上位5機関を表示

**`tests/test_enricher.py`** — TestEnrichInstitutionalHolders（3テスト）追加

### 出力スキーマ（`predictions.json`）

```json
{
  "institutional": {
    "institutional_pct": 0.78,
    "top5_holders": ["Vanguard", "BlackRock", "State Street"],
    "data_note": "四半期報告（45〜75日遅延）・参考値"
  }
}
```

---

## フェーズ13: 52-Week High Momentum ファクター追加（実装済み）

### 実装内容

**`src/screener.py`**
- `compute_52w_high_score(info)`: `min(currentPrice / fiftyTwoWeekHigh, 1.0)` を計算
- `_fetch_52w_data(tickers)`: ティッカーごとに `.info` を取得
- `score_stock()` に `fifty2w_score` 寄与を追加（None 時はスキップ）
- `screen()` 内で市場キャップフィルタ後に `_fetch_52w_data()` を呼び出し

**`config.yaml`**

```yaml
screening:
  weights:
    price_change_1m: 0.25
    volume_trend: 0.15
    rsi_score: 0.20
    macd_signal: 0.20
    fifty2w_score: 0.20   # Phase 13 追加（合計 1.0）
```

**`src/enricher.py`**
- `enrich_52w_high(ticker, info)` を追加
- `fifty2w_score = min(current/high52, 1.0)`, `fifty2w_pct_from_high = ratio - 1.0`

**`src/exporter.py`**
- `if "fifty2w_score" in ticker_data` で存在チェック（`0.0` 保持のため `in` 演算子使用）
- `fifty2w_score` / `fifty2w_pct_from_high` を出力

**`src/alpha_survey.py`**（新規）
- `run_anomaly_test(anomaly_name, lookback_weeks)`: 現時点は `insufficient_data` を返すスタブ
- `build_alpha_survey_json(results)`: `n_observations < 52` → `insufficient_data` 強制
- `run_and_export()`: `dashboard/data/alpha_survey.json` を原子的書き込み

**`src/main.py`**
- Step 7 として `run_alpha_survey()` を呼び出し

**`dashboard/accuracy.html`**
- `#alpha-survey-section` を追加

**`dashboard/js/accuracy.js`**
- `renderAlphaSurvey(survey)` を追加（アノマリー統計検証テーブル）

**`tests/test_screener.py`** — 7テスト追加
**`tests/test_enricher.py`** — TestEnrich52wHigh（5テスト）追加
**`tests/test_alpha_survey.py`**（新規）— 7テスト

### 設計決定事項

- `fifty2w_*` は Google Sheets に保存しない（Sheets 非永続化）
- `sheets.py` の `HEADERS` / `append_predictions` は変更しない
- Enrichment は最新週の `予測済み` 銘柄のみ対象

---

## フェーズ14: 買い時・売り時ガイド（実装済み）

### 背景・目的

株の知識が少ないユーザー向けに、「いつ買うか」「いつ売るか」の判断基準をダッシュボード上で視覚的に提示する。

### 実装内容

**`dashboard/index.html`**

予測一覧セクションの上部に常時表示パネルを追加：

```html
<div class="timing-guide">
  <div class="timing-guide-cols">
    <div class="timing-col-buy">  <!-- 買い時のサイン（緑系）-->
      <ul>
        <li>予測上昇率がプラス（+）の銘柄</li>
        <li>累計的中率が55%以上</li>
        <li>VIX が25以下・逆イールドなし</li>
      </ul>
    </div>
    <div class="timing-col-sell">  <!-- 売り時のサイン（オレンジ系）-->
      <ul>
        <li>損切り価格を下回ったら即売り</li>
        <li>1週間後の予測期間終了で確認</li>
        <li>VIX が25超・逆イールド時はポジション縮小</li>
      </ul>
    </div>
  </div>
</div>
```

**`dashboard/js/index.js`**

各予測カードの末尾に「アクション行」を追加：

```js
// 予測済み銘柄のみ表示
if (p.status === "予測済み") {
  if (displayPct > 0) {
    // 緑系バッジ: "▲ 今週の推奨行動: 購入を検討（予測 +X.X%）"
  } else {
    // グレーバッジ: "– 今週は見送り推奨（予測 -X.X%）"
  }
  // 損切り価格計算: current_price * (1 + stop_loss_pct)
  // "損切り目安: $XXX.XX を下回ったら売り"
}
```

**`dashboard/js/stock.js`**

`renderSizingPanel()` を拡張：

```js
// 損切り価格を実金額で強調表示（赤枠ハイライト）
var stopPrice = prediction.current_price * (1 + s.stop_loss_pct);
// → "損切り価格（この価格を下回ったら売り）: $XXX.XX"
// → "現在価格 $XXX.XX から -X.X% 下落した水準"

// 目標価格を緑枠で表示
// → "目標価格（予測）: $XXX.XX"
```

**`dashboard/css/style.css`**

追加クラス：

| クラス | 用途 |
|-------|------|
| `.timing-guide` | ガイドパネル全体（水色背景） |
| `.timing-col-buy` | 買いサイン列（緑系） |
| `.timing-col-sell` | 売りサイン列（オレンジ系） |
| `.action-row.action-buy` | 予測カードの買い推奨行（緑） |
| `.action-row.action-neutral` | 見送り推奨行（グレー） |
| `.action-stop` | 損切り目安価格行（赤テキスト） |
| `.stop-loss-highlight` | 損切り価格の強調ボックス（赤枠） |
| `.target-price-row` | 目標価格行（緑枠） |

---

---

## フェーズ15: 日本株データ収集バックエンド（実装済み）

### 概要

現在は S&P500・NASDAQ100 の米国株のみを対象としている。
日本株（日経225構成銘柄）のデータ収集を並行して行い、将来の運用に備える。

### バックエンド変更

**`config.yaml`**

```yaml
screening:
  markets:
    - "sp500"
    - "nasdaq100"
    - "nikkei225"   # 有効化（コメントアウト解除）
```

> **注意:** `src/screener.py` は `config["screening"]["markets"]` を参照しているため、`markets` は必ず `screening` 配下に置く。トップレベルに移動すると設定破壊になるため変更しない。

**`src/screener.py`**

- `screen()` を市場別に実行できるよう引数 `market` を追加
- 日本株ティッカーは yfinance 形式（例: `7203.T`）で扱う
- 市場別の出力ファイルを分離:
  - 米国株: `dashboard/data/predictions_us.json`
  - 日本株: `dashboard/data/predictions_jp.json`

**`src/enricher.py`**

- 市場を判定する `is_jp_ticker(ticker)` ヘルパー追加（`.T` サフィックスで判定）
- 日本株は円建てのため `current_price` / `predicted_price` 表示を円に変換

**`src/main.py`**

- 米国株・日本株それぞれの `screen()` → `enrich()` → `export()` を順次実行
- 日本株が失敗しても米国株のフローに影響しないよう独立した try/except で囲む

**`src/sheets.py`**

- `worksheet_name` を市場別に分ける（例: `predictions_us`, `predictions_jp`）

### 実装済み変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `config.yaml` | `nikkei225` を `screening.markets` に追加（有効化） |
| `src/screener.py` | `screen(config, market=None)` — market 引数追加 |
| `src/enricher.py` | `is_jp_ticker(ticker)` ヘルパー追加（`.T` サフィックス判定） |
| `src/exporter.py` | `_split_records_by_market()` / `predictions_us.json` + `predictions_jp.json` 出力 / `predictions.json` 後方互換維持 |
| `src/main.py` | 日本株スクリーニングを独立 try/except ブロックで追加 |
| `src/sheets.py` | `append_predictions(..., market=None)` — 市場別 worksheet 名対応 |

### 後方互換ポリシー

- `predictions.json` は Phase 16 移行完了まで米国株データを引き続き出力（`predictions_us.json` のコピー）
- Phase 16 ページ (`us/`) に完全移行後は `predictions.json` を廃止可能

---

## フェーズ16: ダッシュボード分離（米国株・日本株）（実装済み）

### 概要

現在の `index.html` / `accuracy.html` / `stock.html` を米国株と日本株で分離する。
ランディングページ（`index.html`）で市場を選択し、それぞれ独立したページへ遷移する。

### 新規ページ構成

```
dashboard/
├── index.html              ← ランディングページ（市場選択）
├── us/
│   ├── index.html          ← 米国株サマリー（現 index.html の移植）
│   ├── accuracy.html       ← 米国株的中率
│   └── stock.html          ← 米国株銘柄詳細
├── jp/
│   ├── index.html          ← 日本株サマリー
│   ├── accuracy.html       ← 日本株的中率
│   └── stock.html          ← 日本株銘柄詳細
├── data/
│   ├── predictions_us.json ← 米国株予測データ
│   ├── predictions_jp.json ← 日本株予測データ
│   ├── accuracy_us.json    ← 米国株的中率
│   └── accuracy_jp.json    ← 日本株的中率
├── js/
│   ├── app.js              ← 共通ユーティリティ（変更なし）
│   ├── index_us.js         ← 米国株サマリー描画
│   ├── index_jp.js         ← 日本株サマリー描画（円建て表示）
│   ├── accuracy.js         ← 共通（データパス切り替えで対応）
│   └── stock.js            ← 共通（データパス切り替えで対応）
└── css/
    └── style.css           ← 共通（変更最小限）
```

### ランディングページ（`index.html`）

```html
<!-- 市場選択ページ -->
<div class="market-select">
  <a href="us/index.html" class="market-card">
    <div class="market-flag">🇺🇸</div>
    <div>米国株（S&P500・NASDAQ100）</div>
  </a>
  <a href="jp/index.html" class="market-card">
    <div class="market-flag">🇯🇵</div>
    <div>日本株（日経225）</div>
  </a>
</div>
```

### 日本株表示の差異

| 項目 | 米国株 | 日本株 |
|------|-------|-------|
| 通貨表示 | `$` | `¥`（円） |
| 価格フォーマット | `$250.00` | `¥3,500` |
| データファイル | `predictions_us.json` | `predictions_jp.json` |
| 単元株表示 | なし | 「1単元=100株 / 最低X万円」を表示 |

### フロントエンド変更

**`dashboard/js/app.js`**
- `formatPrice(value, currency)` に `currency` 引数を追加（`"USD"` / `"JPY"`）
- JPY の場合は小数点なし・千区切りで表示

**`dashboard/us/index.html`** / **`dashboard/jp/index.html`**
- 現在の `index.html` をベースに市場別パスを設定
- ヘッダーに「米国株」/「日本株」ラベルを追加

**`dashboard/js/index_jp.js`**
- `loadJSON("../data/predictions_jp.json")` を参照
- 円建て表示ロジック

### 実装済み変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `dashboard/index.html` | 市場選択ランディングページに変更 |
| `dashboard/us/index.html` | 米国株サマリー（新規） |
| `dashboard/us/accuracy.html` | 米国株的中率（新規） |
| `dashboard/us/stock.html` | 米国株銘柄詳細（新規） |
| `dashboard/jp/index.html` | 日本株サマリー（新規） |
| `dashboard/jp/accuracy.html` | 日本株的中率（新規） |
| `dashboard/jp/stock.html` | 日本株銘柄詳細（新規） |
| `dashboard/js/app.js` | `MARKET` / `DATA_BASE` / `predictionsFile()` 自動検出を追加；`formatPrice(price, currency)` JPY 対応 |
| `dashboard/js/index_us.js` | 米国株サマリー描画（新規）— `predictions_us.json` 参照 |
| `dashboard/js/index_jp.js` | 日本株サマリー描画（新規）— 円建て・単元株表示 |
| `dashboard/js/accuracy.js` | `predictionsFile()` を使用して市場別 JSON を参照 |
| `dashboard/js/stock.js` | `predictionsFile()` を使用して市場別 JSON を参照 |
| `dashboard/css/style.css` | `.market-select` / `.market-card` / `.market-label` スタイル追加 |

### 市場検出メカニズム（app.js）

```js
// URL パスから自動判定（サーバーなしでもファイルパスで動作）
var MARKET = path.indexOf("/jp/") !== -1 ? "jp" : "us";
var DATA_BASE = (path includes /us/ or /jp/) ? "../data/" : "data/";
```

- `us/` 下のページ → `../data/predictions_us.json`
- `jp/` 下のページ → `../data/predictions_jp.json`
- ルート（後方互換）→ `data/predictions.json`

### 受け入れ確認チェック

- [x] `dashboard/index.html` が市場選択ページとして機能する
- [x] `us/index.html` が米国株サマリーを USD 表示で描画する
- [x] `jp/index.html` が日本株データを円建てで表示する（JPY / 単元株情報付き）
- [x] 米国株フローの障害が日本株フローに影響しない（独立した try/except）
- [x] `predictions_us.json` と `predictions_jp.json` が別ファイルとして出力される
- [x] `predictions.json` が後方互換として継続出力される
