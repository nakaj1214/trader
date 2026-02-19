# エビデンスベース投資意思決定支援 実装計画書

## 背景

`docs/implement/research.md` の調査結果をもとに、現在の AI Stock Predictions ダッシュボードに **投資判断の質を上げるための意思決定支援機能** を段階的に追加する。

## 現状のアーキテクチャ

```
yfinance (株価) + ta (テクニカル指標)
  → screener.py (トップ10銘柄を選出)
  → predictor.py (Prophet で5営業日先を予測)
  → tracker.py (的中率追跡)
  → sheets.py (Google Sheets 永続化)
  → exporter.py (JSON出力 → dashboard/data/)
  → 静的サイト (Vanilla JS + Chart.js)
```

**既存のデータフィールド (predictions.json):**
`date`, `ticker`, `current_price`, `predicted_price`, `predicted_change_pct`, `ci_pct`, `actual_price`, `status`, `hit`

**利用可能だが未活用のデータ:**
- yfinance: 過去株価 (ボラティリティ・β・最大DD算出可)、`.info` (P/E, P/B, 配当利回り, ROE, 利益率, セクター, 決算日)
- ta ライブラリ: ボリンジャーバンド, ATR, ADX 等の追加テクニカル指標
- screener.py のスコア内訳: `price_change_1m`, `volume_trend`, `rsi`, `macd_bullish`, `score`

**`lookback_days` の意味:**
`config.yaml` の `screening.lookback_days`（現行: 30）は **カレンダー日** を意味する。screener は `yf.download(period=f"{lookback_days}d")` でカレンダー日指定で取得しており、結果の DataFrame 行数（営業日数）は通常20〜22日程度となる。enricher で同一条件を再現する際は `df.tail()` ではなく日付ベース切り出し（`pd.Timedelta(days=lookback_days)`）を使用する。

---

## フェーズ構成

| フェーズ | 内容 | 工数 | 主な効果 |
|---------|------|------|---------|
| 1 | リスク指標 + イベント注釈 | 低〜中 | アップサイドだけでなく"想定下振れ"を同時提示 |
| 2 | エビデンス指標（モメンタム/バリュー/クオリティ/低リスク） | 中 | AI予測が"どのタイプの上昇"かを説明 |
| 3 | 予測根拠の表示（スコア内訳） | 低〜中 | "なぜこの銘柄？"を短文で説明 |
| 4 | 予測誤差分析（帯別精度・MAE） | 中 | 予測上昇率と実績のずれを定量化し過信を防止 |

---

## フェーズ1: リスク指標 + イベント注釈

### 概要
research.md「期待リターン×リスク表示」「イベント注釈」に対応。
現在のダッシュボードは予測上昇率のみ表示しており、リスク（下振れ）の情報がない。各銘柄にボラティリティ・β・最大ドローダウンおよび直近イベント（決算日・配当落ち日）を付与する。

### バックエンド変更

**新規ファイル: `src/enricher.py`**

各予測銘柄について yfinance からリスク指標とイベント情報を算出する。

```python
# 主要関数
def enrich(predictions_df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """予測結果にリスク指標・イベント情報を付与して返す。"""

def compute_risk_metrics(df: pd.DataFrame, spy_df: pd.DataFrame,
                         lookback_days: int = 90) -> dict:
    """1銘柄のリスク指標を算出する。

    呼び出し元（exporter）が事前に取得した株価 DataFrame を受け取る。
    関数内部では yfinance を呼び出さない。

    Args:
        df: 対象銘柄の株価 DataFrame（Close 列を含む、252営業日分以上）
            ※ 呼び出し元が十分なカレンダー日数で取得済みであること
        spy_df: SPY の株価 DataFrame（beta 算出用、df と同期間）
        lookback_days: beta の計算窓（デフォルト90営業日）

    各指標は df の末尾から所定の窓で算出する:
      - vol_20d_ann:      末尾 20営業日
      - vol_60d_ann:      末尾 60営業日
      - beta:             末尾 lookback_days 営業日（デフォルト90）
      - max_drawdown_1y:  末尾 252営業日（1年分）
    ※ df の営業日数が不足する場合は利用可能な範囲で算出する

    Returns:
        {
            "vol_20d_ann": float,   # 20日ボラティリティ（年率換算）
            "vol_60d_ann": float,   # 60日ボラティリティ（年率換算）
            "beta": float,          # S&P500に対するβ
            "max_drawdown_1y": float,  # 過去1年の最大ドローダウン (負値)
        }
    """

def fetch_events(ticker: str) -> list[dict]:
    """決算日・配当落ち日をyfinance .infoから取得する。
    Returns:
        [
            {"type": "earnings", "date": "2026-03-05", "days_to": 14},
            {"type": "dividend_ex", "date": "2026-03-20", "days_to": 29},
        ]
    """
```

**計算ロジック:**

呼び出し元（exporter）が `yf.download` で取得済みの DataFrame (`df`, `spy_df`) を受け取り、各指標を算出する。関数内部では yfinance を呼び出さない。

**データ取得期間の換算（営業日 vs カレンダー日）:**
`yf.download` の `period` パラメータはカレンダー日数を指定する。252営業日 ≈ 365カレンダー日だが、祝日等を考慮して **`period="400d"`** を使用する。取得後の DataFrame 行数が実際の営業日数となる。

```
取得: yf.download(tickers, period="400d")  — 252営業日を確実に含むため余裕を持ったカレンダー日数
前提: df は 252営業日分以上を含むこと（最大DDが252営業日を要するため）
不足時: df の営業日数が 252 に満たない場合は利用可能な範囲で算出する

ボラティリティ(20日年率) = df 末尾20営業日の日次リターンの標準偏差 × √252
ボラティリティ(60日年率) = df 末尾60営業日の日次リターンの標準偏差 × √252
β = Cov(df リターン, spy_df リターン) / Var(spy_df リターン)  ※末尾 lookback_days(90)営業日
最大DD(1年) = df 末尾252営業日の最大ドローダウン（ピークからの最大下落率）
```

**イベント取得:**
```python
info = yf.Ticker(ticker).info
# 決算日: info.get("earningsDate") → Timestampのリスト
# 配当落ち日: info.get("exDividendDate") → Timestamp
# セクター: info.get("sector") → 文字列 (フェーズ2で使用)
```

**`src/exporter.py` 変更:**

`build_predictions_json` で enricher の出力を predictions.json に統合する。

```json
// predictions.json の各レコードに追加されるフィールド
{
  "date": "2026-02-19",
  "ticker": "CBRE",
  "current_price": 152.01,
  "predicted_price": 425.23,
  "predicted_change_pct": 179.74,
  "ci_pct": 2.89,
  "actual_price": null,
  "status": "予測済み",
  "hit": null,
  // ↓ 新規追加フィールド
  "risk": {
    "vol_20d_ann": 0.28,
    "vol_60d_ann": 0.25,
    "beta": 1.10,
    "max_drawdown_1y": -0.18
  },
  "events": [
    {"type": "earnings", "date": "2026-03-05", "days_to": 14},
    {"type": "dividend_ex", "date": "2026-03-20", "days_to": 29}
  ]
}
```

**`src/main.py` は変更しない。**

enricher の実行責務は **exporter のみに統一** する。理由:
- `python -m src.exporter` の単体実行でも enrichment が動作する必要がある（GitHub Actions ワークフローで exporter は独立ステップとして実行される）
- main.py に enricher を入れると、main 経由と exporter 単体実行で enrichment の有無が分岐し、データ欠落のリスクがある
- Google Sheets のスキーマ変更を避ける（既存の9列ヘッダーを維持）

**実装詳細（exporter の変更）:**

```python
# exporter.py に追加
def build_predictions_json(records: list[dict], enrichment: dict) -> list[dict]:
    """records: Sheetsの全レコード, enrichment: {(date, ticker): {risk: ..., events: ...}}"""
    results = []
    for r in records:
        item = {
            "date": r["日付"],
            "ticker": r["ティッカー"],
            # ... 既存フィールド ...
        }
        # enrichment は (date, ticker) キーで最新週のみ存在
        key = (r["日付"], r["ティッカー"])
        ticker_data = enrichment.get(key, {})
        if ticker_data:
            item["risk"] = ticker_data.get("risk")
            item["events"] = ticker_data.get("events")
        results.append(item)
    return results
```

**enrichment のスコープ制限:**
- enrichment の辞書キーは `(date, ticker)` のタプルとする
- exporter は最新週の予測済みレコードのみを enricher に渡し、結果を `(date, ticker)` キーで格納する
- 過去週のレコードにはキーが一致しないため enrichment フィールドが付与されない
- これにより、最新時点で算出したリスク指標が過去レコードに混入する時点整合性の問題を防止する

**export 関数の変更フロー:**
1. Google Sheets からレコード取得（既存）
2. 最新週の日付を特定し、最新週の予測済みティッカーを抽出
3. 最新週のティッカー + SPY に対して `yf.download(tickers, period="400d")` で長期株価データを一括取得（252営業日を確実に含むためカレンダー日数に余裕を持たせる）
4. 各銘柄の DataFrame と SPY DataFrame を `enricher.compute_risk_metrics(df, spy_df)` に渡しリスク指標を算出
5. `enricher.fetch_events(ticker)` でイベント情報を取得（ticker 文字列を渡す。内部で `.info` を呼ぶ）
6. （フェーズ3追加）`enricher.compute_explanations(ticker, df, config)` に長期 DataFrame をそのまま渡してスコア内訳を算出。日付ベースの期間切り出しは関数内部で行う（呼び出し側では切り出さない）
7. 結果を `{(date, ticker): {...}}` 形式で格納
8. enrichment データと records を `build_predictions_json` に渡す
9. JSON出力（既存）

### フロントエンド変更

**`dashboard/js/stock.js` 変更:**

銘柄詳細ページにリスクパネルとイベントバッジを追加する。

```
価格推移チャートの上に:
┌──────────────────────────────────────────────┐
│ CBRE                                         │
│ 予測: +12.5% (4週)                            │
│                                               │
│ ボラ(20日): 28%年率  β: 1.10  最大DD: -18%     │
│                                               │
│ [決算まで14日] [配当落ちまで29日]                │
└──────────────────────────────────────────────┘
```

- `risk` フィールドが存在する最新レコードからリスク指標を表示
- `events` フィールドからイベントバッジを生成
- リスク指標がない過去レコードは表示をスキップ

**`dashboard/js/index.js` 変更:**

予測カードにリスク情報を1行追加する。

```
┌─────────────────────────────┐
│ CBRE                        │
│ $152.01 → $425.23  +179.7%  │
│ 実績: -           未確定     │
│ ボラ28% | β1.10 | DD-18%    │  ← 新規追加行
│ [決算14日後]                 │  ← 新規追加行
└─────────────────────────────┘
```

**`dashboard/css/style.css` 変更:**

- `.risk-row` スタイル追加（薄いグレー背景、小フォント）
- `.event-badge` スタイル追加（ピル型バッジ、オレンジ系）

### 対象ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `src/enricher.py` | **新規作成**: リスク指標算出 + イベント取得 |
| `src/exporter.py` | enricher 呼び出し + 結果を predictions.json に統合 |
| `dashboard/js/stock.js` | リスクパネル + イベントバッジ描画 |
| `dashboard/js/index.js` | カードにリスク情報行追加 |
| `dashboard/css/style.css` | リスク行・イベントバッジのスタイル |
| `tests/test_enricher.py` | **新規作成**: enricher のユニットテスト |

---

## フェーズ2: エビデンス指標（モメンタム/バリュー/クオリティ/低リスク）

### 概要
research.md「エビデンス指標スナップショット」に対応。
AI予測が"どのタイプの上昇"かを実証研究で裏づけのある因子（ファクター）で分解表示する。

### バックエンド変更

**`src/enricher.py` に追加:**

```python
def compute_evidence_signals(ticker: str, peer_tickers: list[str]) -> dict:
    """銘柄のエビデンス指標を対象銘柄群内の z-score で算出する。
    Returns:
        {
            "momentum_z": float,    # 12ヶ月モメンタム (直近1ヶ月除外) の z-score
            "value_z": float,       # バリュー指標 (P/B逆数) の z-score
            "quality_z": float,     # 収益性 (ROE or 利益率) の z-score
            "low_risk_z": float,    # 低リスク (ボラティリティ逆数) の z-score
            "composite": float,     # 合成スコア (0〜100)
        }
    """
```

**各指標の算出方法:**

| 指標 | 算出元 | 計算方法 |
|------|--------|---------|
| momentum_z | yfinance 過去株価 | 過去12ヶ月リターン（直近1ヶ月除外）→ 対象銘柄群内z-score |
| value_z | yfinance `.info["priceToBook"]` | P/B の逆数 → 対象銘柄群内z-score（高いほどバリュー） |
| quality_z | yfinance `.info["returnOnEquity"]` | ROE → 対象銘柄群内z-score |
| low_risk_z | フェーズ1の vol_20d_ann | ボラティリティの逆数 → 対象銘柄群内z-score（低ボラほど高スコア） |
| composite | 上記4指標 | `0.3*momentum + 0.25*value + 0.25*quality + 0.2*low_risk` → 0〜100に正規化 |

**z-score の計算:**
```
z = (銘柄の値 - 対象銘柄群平均) / 対象銘柄群標準偏差
```
対象銘柄群 = 最新週の予測対象銘柄（topN）。

**サンプルサイズに関する注意:**
- topN（現行設定: 10銘柄）は統計的に十分な母集団とは言えないため、z-score は市場全体に対する絶対的な位置づけではなく、**選出銘柄間の相対比較** として解釈する
- フロントエンドの表示ラベルも「市場平均比」ではなく「選出銘柄内の相対位置」とする
- 将来的に母集団を拡大する場合は、screener が中間結果（全銘柄の指標値）をファイルに保存し enricher が参照する方式を検討する

**データ取得の最適化:**
- `yf.Ticker(ticker).info` の呼び出しはフェーズ1の `fetch_events` と共通化する
- 1回の `.info` 呼び出しでリスク・イベント・ファンダメンタルデータを一括取得
- レート制限対策: バッチ間に1秒のスリープ（既存 screener と同じパターン）

### フロントエンド変更

**`dashboard/js/stock.js` 変更:**

銘柄詳細ページに「根拠パネル」を追加する。

```
┌──────────────────────────────────────────────┐
│ エビデンス指標                                 │
│                                               │
│ モメンタム  ████████░░  +1.25  ▲ 支持          │
│ バリュー    ███░░░░░░░  -0.40  ▼ 反対          │
│ 収益性      ██████░░░░  +0.70  ▲ 支持          │
│ 低リスク    ████░░░░░░  +0.30  ▲ 支持          │
│                                               │
│ 合成スコア: 63 / 100                           │
└──────────────────────────────────────────────┘
```

- z-score の絶対値でバーの長さを決定
- z > 0 → 緑「▲ 支持」、z < 0 → 赤「▼ 反対」
- z-score が null の場合は「データなし」と表示

**`dashboard/css/style.css` 変更:**

- `.evidence-panel` コンテナスタイル
- `.evidence-bar` 横棒グラフスタイル（CSS のみで描画、Chart.js 不要）
- `.evidence-support` / `.evidence-oppose` 色分け

### predictions.json への追加フィールド

```json
{
  "evidence": {
    "momentum_z": 1.25,
    "value_z": -0.40,
    "quality_z": 0.70,
    "low_risk_z": 0.30,
    "composite": 63
  }
}
```

### 対象ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `src/enricher.py` | `compute_evidence_signals` 関数追加、`.info` 取得の共通化 |
| `src/exporter.py` | evidence フィールドを predictions.json に追加 |
| `dashboard/js/stock.js` | 根拠パネル描画 |
| `dashboard/css/style.css` | エビデンスバー・パネルのスタイル |
| `tests/test_enricher.py` | エビデンス指標のテスト追加 |

---

## フェーズ3: 予測根拠の表示（スコア内訳）

### 概要
research.md「局所説明（SHAP風）」に対応。
完全なSHAPは本プロジェクトのモデル構成（Prophet + ルールベーススコアリング）には不向きなため、スクリーニングスコアの内訳をそのまま「なぜこの銘柄が選ばれたか」の根拠として表示する。

**再計算タイミングに関する注意:**
explanations は exporter 実行時に株価データを再取得し、日付ベースで切り出した `sliced_df` を `screener.compute_indicators(sliced_df)` に渡して算出する。予測自体は `src.main` 実行時点で確定済みであり、GitHub Actions ワークフロー上 main と exporter は別ステップ（数分〜数十分の時間差）で実行される。そのため、exporter 時点の指標値が main 実行時と微妙に異なる可能性がある（市場クローズ後の実行を前提とするため通常は同一だが、API レスポンスのタイミング差は排除できない）。この仕様を明示するため、JSON 出力と UI に「エクスポート時点の再計算値」である旨を記載する。

### バックエンド変更

**`src/screener.py` は変更しない。**

screener の戻り値（`current_price`, `price_change_1m`, `volume_trend`, `rsi`, `macd_bullish`）は既存のまま維持する。スコア内訳の算出は enricher が単独で行う。

**`src/enricher.py` に追加:**

enricher が screener の `compute_indicators` 関数をインポートし、最新週のティッカーに対してスコア内訳を再計算する。Google Sheets にはスコア内訳を保存しない。

**因子名 → 重みキー → スコア変換の対応表:**

`compute_indicators` が返す指標キーと `config.yaml` の重みキーは一致しないものがある。enricher はこの対応を正しくマッピングする必要がある。

| `compute_indicators` の返却キー | `config.yaml` の重みキー | スコア変換ロジック（`score_stock` 準拠） |
|------|------|------|
| `price_change_1m` | `price_change_1m` (0.3) | `max(0.0, raw)` |
| `volume_trend` | `volume_trend` (0.2) | `max(0.0, raw)` |
| `rsi` | `rsi_score` (0.25) | 40-60 → 1.0 / 30-70 → 0.5 / else → 0.0 |
| `macd_bullish` | `macd_signal` (0.25) | そのまま (0.0 or 1.0) |

各ファクターの寄与度 (impact) = 変換後スコア × 重み

```python
def compute_explanations(ticker: str, df: pd.DataFrame, config: dict) -> list[dict]:
    """screener の関数を再利用してスコア内訳を算出する。
    screener.py 自体は変更せず、enricher 内で内訳を組み立てる。

    注意: screener.compute_indicators のシグネチャは
    compute_indicators(df: pd.DataFrame) -> dict であり、
    ticker 文字列ではなく株価 DataFrame を受け取る。

    重要: compute_indicators は df の先頭と末尾で price_change_1m を
    計算する（close.iloc[-1] - close.iloc[0]）。フェーズ1のリスク指標用
    DataFrame は最大252日分を含むため、そのまま渡すと price_change_1m が
    「1年間の変動率」になり、screener が使う30日間の値と乖離する。
    必ず日付ベースで screener と同一のカレンダー日数に切り出してから渡すこと。

    期間切り出しの注意（営業日 vs カレンダー日）:
    - config["screening"]["lookback_days"] はカレンダー日を意味する
    - screener は yf.download(period=f"{lookback_days}d") でカレンダー日指定
    - df.tail(lookback_days) は営業日数（行数）指定のため不一致になる
    - 日付ベース切り出し（pd.Timedelta）を使うことで screener と同条件になる

    手順:
    1. フェーズ1で取得済みの長期 DataFrame を受け取る
    2. 日付ベースで切り出す:
       cutoff = df.index.max() - pd.Timedelta(days=config["screening"]["lookback_days"])
       sliced_df = df.loc[df.index >= cutoff]
       ※ tail() ではなく Timedelta を使い、screener の period=f"{lookback_days}d" と同じカレンダー日数で切り出す
    3. screener.compute_indicators(sliced_df) で生指標を取得
    4. score_stock と同じ変換ロジックを適用し、config.yaml の重みで寄与度を算出
    5. 寄与度降順で上位3項目を返す

    Args:
        ticker: ティッカーシンボル（表示用）
        df: yf.download で取得済みの株価 DataFrame（Close, Volume 列を含む）
            ※ フェーズ1のリスク指標用に取得した長期データを想定
        config: config.yaml の設定辞書

    Returns:
        [{"factor": "macd_bullish", "impact": 0.25, "text": "MACD買いシグナル"}, ...]
    """
    lookback = config["screening"]["lookback_days"]  # 現行: 30（カレンダー日）
    cutoff = df.index.max() - pd.Timedelta(days=lookback)
    sliced_df = df.loc[df.index >= cutoff]
    indicators = screener.compute_indicators(sliced_df)
    # ... 以降、score_stock と同じ変換ロジックで寄与度を算出 ...
```

**実装方針:**
- exporter が最新週のティッカーリストを enricher に渡す（フェーズ1・2 と同じフロー）
- enricher はフェーズ1のリスク指標算出時に取得済みの長期株価 DataFrame を再利用する（重複取得を避ける）
- **DataFrame の期間切り出し（重要）:** `compute_indicators` は `df` の先頭行と末尾行で `price_change_1m` を計算する（`screener.py:105-107`）。フェーズ1 のリスク指標用 DataFrame は最大252日分を含むため、日付ベースで screener と同一のカレンダー日数に切り出してから渡す（`cutoff = df.index.max() - pd.Timedelta(days=lookback_days)` / `df.loc[df.index >= cutoff]`）。`tail()` は営業日数（行数）指定であり、screener の `period=f"{lookback_days}d"`（カレンダー日）と一致しないため使用しない。これにより explanations の指標値が実際の銘柄選出時と整合する
- `screener.compute_indicators(sliced_df)` に切り出し後の DataFrame を渡して生指標を取得する
- `score_stock` と同じスコア変換ロジック（RSI の帯判定、max(0, x) 等）を enricher 内で再現し、`config.yaml` の重みを掛けて各ファクターの寄与度を算出する
- 結果を `(date, ticker)` キーの enrichment 辞書に `explanations` として格納

### フロントエンド変更

**`dashboard/js/stock.js` 変更:**

銘柄詳細ページに「選出理由」セクションを追加する。

```
┌──────────────────────────────────────────────┐
│ 選出理由                                      │
│                                               │
│ この銘柄がトップ10に入った主因:                  │
│ ① MACD買いシグナルが出ている (+0.25)            │
│ ② RSIが安定圏にある (+0.25)                     │
│ ③ 1ヶ月株価上昇率が高い (+0.045)                │
│                                               │
│ ※ エクスポート時点の指標値に基づく再計算結果です  │
└──────────────────────────────────────────────┘
```

- 寄与度（weighted）降順で上位3項目を表示
- 短い日本語の説明テンプレートを付与
- 再計算値である旨の注記を末尾に表示

### predictions.json への追加フィールド

```json
{
  "explanations": {
    "factors": [
      {"factor": "macd_bullish", "weight_key": "macd_signal", "impact": 0.25, "text": "MACD買いシグナル"},
      {"factor": "rsi",          "weight_key": "rsi_score",    "impact": 0.25, "text": "RSI安定圏"},
      {"factor": "price_change_1m", "weight_key": "price_change_1m", "impact": 0.045, "text": "1ヶ月株価上昇率が高い"}
    ],
    "recalculated_at": "2026-02-19T06:15:00Z",
    "note": "エクスポート時点の指標値に基づく再計算結果"
  }
}
```

### 対象ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `src/enricher.py` | screener の関数を再利用してスコア内訳を算出・explanations 形式に変換 |
| `src/exporter.py` | explanations フィールドを predictions.json に追加 |
| `dashboard/js/stock.js` | 選出理由セクション描画 |
| `dashboard/css/style.css` | 選出理由セクションのスタイル |

---

## フェーズ4: 予測誤差分析（帯別精度・MAE）

### 概要
research.md「予測の校正ダッシュボード」の方向性を踏まえつつ、現状のモデル出力に適合した形で実装する。

**現状のモデルは確率を出力しない**（上昇予測のみをフィルタした予測上昇率%を出力）。そのため research.md が前提とする「確率予測の校正（calibration）」（Brier Score、reliability diagram 等）は適用できない。確率出力（例: `prob_positive`）を導入するまでは「校正」を名乗らず、**「予測誤差分析」** として予測上昇率と実績上昇率のずれを定量化する。

### バックエンド変更

**`src/exporter.py` 変更:**

accuracy.json に予測誤差分析データを追加する。

```python
def build_accuracy_json(records: list[dict]) -> dict:
    # 既存の weekly + cumulative に加えて:
    accuracy["error_analysis"] = build_error_analysis(records)
    return accuracy

def build_error_analysis(records: list[dict]) -> dict:
    """予測上昇率 vs 実際変動率の誤差分析データを構築する。"""
    # 確定済み + 実績あり (actual_price が数値) のレコードのみ対象
    # predicted_change_pct をビン分割（0-5%, 5-10%, 10-20%, 20%+）
    # 各ビンの平均予測上昇率 vs 平均実際変動率 を算出
    # MAE (Mean Absolute Error) を算出
```

**accuracy.json への追加フィールド:**

```json
{
  "updated_at": "2026-02-19T...",
  "weekly": [...],
  "cumulative": {...},
  "error_analysis": {
    "mae_pct": 5.3,
    "bins": [
      {
        "range": "0-5%",
        "avg_predicted_pct": 3.2,
        "avg_actual_pct": 2.8,
        "hit_rate_pct": 72.0,
        "count": 45
      },
      {
        "range": "5-10%",
        "avg_predicted_pct": 7.1,
        "avg_actual_pct": 4.5,
        "hit_rate_pct": 65.0,
        "count": 30
      }
    ],
    "notes": "予測上昇率の帯ごとに実績変動率を比較。MAEは予測と実績の平均絶対誤差。"
  }
}
```

**MAE の計算:**
```
actual_change_pct = (actual_price - current_price) / current_price * 100
MAE = mean(|predicted_change_pct - actual_change_pct|)
```

**将来の拡張（確率出力導入後）:**
- predictor がクラス確率（例: `prob_positive: 0.72`）を出力するようになった段階で、Brier Score・reliability diagram・ECE 等の校正指標を追加する
- その際に `error_analysis` を `calibration` に昇格させる

### フロントエンド変更

**`dashboard/js/accuracy.js` 変更:**

的中率ページに「予測誤差分析」セクションを追加する。

```
┌──────────────────────────────────────────────┐
│ 予測誤差分析                                   │
│                                               │
│ 平均予測誤差 (MAE): 5.3%                       │
│                                               │
│ [予測上昇率 vs 実際変動率 のバーチャート]        │
│                                               │
│ 予測帯     予測平均  実績平均  的中率  件数      │
│ 0-5%      +3.2%    +2.8%   72%    45         │
│ 5-10%     +7.1%    +4.5%   65%    30         │
│ 10-20%    +14.2%   +8.1%   58%    20         │
│ 20%+      +35.0%   +12.3%  50%    10         │
└──────────────────────────────────────────────┘
```

- Chart.js でグループ化バーチャート（予測 vs 実績）
- テーブルで詳細数値

### 対象ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `src/exporter.py` | `build_error_analysis` 関数追加、accuracy.json 拡張 |
| `dashboard/js/accuracy.js` | 予測誤差分析セクション + チャート + テーブル描画 |
| `dashboard/accuracy.html` | 予測誤差分析セクション用 HTML 追加 |
| `dashboard/css/style.css` | 誤差分析テーブル・チャートのスタイル |

---

## 実装順序

| 順番 | フェーズ | 理由 |
|------|---------|------|
| 1 | フェーズ1: リスク指標 + イベント | yfinance の既存データのみで実装可能。最も少ない工数で最大のユーザー価値 |
| 2 | フェーズ3: 予測根拠 | screener.py の既存スコアを再利用するため低工数。フェーズ2の前に仕組みを作る |
| 3 | フェーズ2: エビデンス指標 | `.info` API呼び出しの共通化が必要。フェーズ1の enricher を拡張 |
| 4 | フェーズ4: 予測誤差分析 | 十分な確定済みデータが蓄積されてから意味を持つ。exporter の変更のみ |

---

## 技術的制約と設計判断

### enricher の実行タイミング（責務の一本化）

enricher は **exporter からのみ呼び出される** 設計とする。main.py は enricher を呼び出さない。理由:
- `python -m src.exporter` の単体実行（GitHub Actions の独立ステップ）でも enrichment が正しく動作する
- main.py と exporter の両方から呼び出すと、実行経路によって enrichment の有無が分岐し、データ欠落や重複実行のリスクがある
- Google Sheets のスキーマ変更を避ける（既存の9列ヘッダーを維持）
- リスク指標は「その時点の最新データ」で計算すべき（1週間前のボラティリティは古い）

**フェーズ3（スコア内訳）も同じフロー:** enricher がフェーズ1で取得済みの長期株価 DataFrame を日付ベースで screener と同一のカレンダー日数に切り出し（`cutoff = df.index.max() - pd.Timedelta(days=config["screening"]["lookback_days"])` / `df.loc[df.index >= cutoff]`）、`screener.compute_indicators(sliced_df)` に渡して生指標を取得する。`lookback_days` はカレンダー日であり `tail()` による営業日数切り出しとは異なる点に注意。`config.yaml` の重み定義を参照して寄与度を enricher 内で算出する。screener.py 自体は一切変更しない（戻り値・インターフェースとも既存のまま維持）。

### explanations の再計算タイミング（仕様）

explanations（選出理由）は **exporter 実行時に再計算** する設計とする。予測自体は `src.main` 実行時点で確定しているが、explanations は exporter ステップで株価データを再取得し、日付ベースで切り出した `sliced_df` を `screener.compute_indicators(sliced_df)` に渡して算出する。

**タイミングのずれに関する仕様:**
- GitHub Actions ワークフローでは main と exporter は別ステップで実行される（`weekly_run.yml:36`, `weekly_run.yml:41`）
- 市場クローズ後の日曜 00:00 UTC 実行を前提とするため、通常は main 時点と exporter 時点で株価データは同一
- ただし API レスポンスのタイミング差（キャッシュ更新等）により微差が生じる可能性は排除できない
- この仕様を明示するため、JSON 出力に `recalculated_at` タイムスタンプを付与し、フロントエンドに注記を表示する

**main.py に explanation 元データを保存しない理由:**
- main.py の責務を増やさない（enricher の責務は exporter に一本化する設計方針に準拠）
- Google Sheets のスキーマ変更を避ける
- 市場クローズ後の実行であれば実質的な差異は無視できる

### yfinance API 呼び出しの最適化

```
対象銘柄数: 最新週の予測対象銘柄（topN = 最大10銘柄）
フェーズ1で必要な .info 呼び出し: 最大10銘柄 × 1回 = 10回
フェーズ2で追加される .info 呼び出し: 0回（フェーズ1と共通化済み）
  → P/B, ROE 等のファンダメンタルデータもフェーズ1の .info 呼び出しで一括取得
株価データ取得: yf.download でバッチ取得（既存パターン）
ベンチマーク (SPY): 1回の追加取得
```

合計: 約11回の API 呼び出し追加。対象が topN に限定されているため yfinance のレート制限内で十分。
全銘柄ユニバースに拡大する場合は数百回の `.info` 呼び出しが必要となり、キャッシュ戦略と実行時間予算の再設計が必要。

### 既存テストへの影響

- `tests/test_exporter.py`: `build_predictions_json` のシグネチャ変更に伴うテスト修正が必要
- `tests/test_enricher.py`: 新規テスト作成。yfinance 呼び出しはモックで対応
- 既存の `test_screener.py`, `test_predictor.py` は変更不要

### フロントエンドの互換性

- `risk`, `evidence`, `explanations` フィールドは **オプショナル**（存在しない場合は表示しない）
- 既存の predictions.json にフィールドがない過去データでも正常動作する
- ES5互換を維持（既存コードに合わせる）

---

## 参考: research.md との対応表

| research.md の提案 | 本計画での対応 | 備考 |
|-------------------|--------------|------|
| 期待リターン×リスク表示 | フェーズ1 | ボラ・β・最大DDを実装 |
| イベント注釈 | フェーズ1 | 決算日・配当落ち日 |
| エビデンス指標スナップショット | フェーズ2 | momentum/value/quality/low-risk のz-score |
| シグナル集約とランキング分解 | フェーズ2 (composite) | 合成スコアとして実装 |
| 局所説明（SHAP風） | フェーズ3 | スクリーニングスコアの内訳で代替 |
| 予測の校正ダッシュボード | フェーズ4 | 現段階は予測誤差分析（MAE + 帯別精度）。確率出力導入後に校正指標へ昇格 |
| セクター/市場中立ランキング | 対象外 | 工数に対して効果が限定的。将来検討 |
| バックテスト強化 | 対象外 | 既存シミュレータの延長で将来対応可能 |
| 過学習警告 | 対象外 | 現時点でバックテストデータが不足 |
| アラート（RSS） | 対象外 | 週次更新では効果が薄い |
