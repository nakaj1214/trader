# Antigravity × TradingView 記事 — 活用・差分実装計画

> 参考記事: https://note.com/xauxbt/n/n3b0a52b835ae
> 作成日: 2026-02-27
> 最終更新: 2026-02-27（review.md 指摘反映）

---

## 0. 調査サマリー

### 記事の主旨（公開部分から判断）

「Antigravity（Google AI エージェント）× TradingView」で銘柄選びを自動化する。
フロー: **探す → 絞る → 深掘りする** の 3 段階を AI が代行。

- Antigravity はブラウザ内蔵 AI エージェント。TradingView を自動操作し、チャート分析 HTML レポートを生成する
- 手動スクリーンショット不要で分析レポートを出力する点が差別化

### 現プロジェクトとの差分

| テーマ | 記事の手法 | 現プロジェクトの状態 | ギャップ |
|--------|-----------|---------------------|---------|
| **探す** | TradingView スクリーナー（150+指標）| yfinance + 5指標（RSI/MACD/volume/price/52wHigh）| 指標数・信号品質が少ない |
| **絞る** | Golden Cross・Bollinger 等の定番フィルター | スコア上位 N 件のみ | トレンド方向・レンジ判定が無い |
| **深掘り** | AI がチャート画像を読んで HTML レポート生成 | テキスト JSON + ダッシュボード | 視覚的チャートが通知・レポートに無い |
| **通知** | HTML レポートで画像込みのアウトプット | Slack テキスト通知 | 画像なし |

---

## 1. 実装フェーズ一覧

| Phase | 内容 | 優先度 | 難易度 |
|-------|------|--------|--------|
| A | スクリーナー強化（Golden Cross + Bollinger Band） | High | Low |
| B | Slack 通知にチャート画像を添付 | High | Medium |
| C | ADX でトレンド強度フィルターを追加 | Medium | Low |

---

## Phase A: スクリーナー強化

### 背景

現在のスクリーナーは RSI・MACD・出来高・騰落率・52 週高値の 5 指標のみ。
TradingView で最も広く使われる **Golden Cross** と **Bollinger Band** を追加し、選別精度を上げる。

### A-1 Golden Cross フィルター

**概要:** SMA50 > SMA200 の銘柄のみを通す。デス・クロス銘柄（下降トレンド）を排除する。

#### 前提: lookback_days の引き上げ（review 指摘 #1 対応）

現行 `config.yaml:14` の `lookback_days: 30` では SMA200 の計算に必要な 200 日分のデータが取得できない。
Golden Cross フィルターを有効にするには `lookback_days` を **252（約1年）** 以上に変更する必要がある。

**変更ファイル:** `config.yaml`

```yaml
screening:
  lookback_days: 252   # 30 → 252 に変更（SMA200 計算に必要）
```

> 注意: lookback_days を大きくすると yfinance のデータ取得量・実行時間が増加する。
> GitHub Actions の timeout-minutes: 60 の範囲内であれば問題ない。

**⚠️ yfinance 取得期間のカレンダー日補正（review 指摘対応）:**

現行 `fetch_stock_data()` は `period = f"{lookback_days}d"` で yfinance を呼ぶ（`src/screener.py:42`）。
`252d` は **カレンダー日 252 日** であり、土日・祝日を含むため実際に取得できる営業日数は約 180 日にとどまる。
SMA200 の計算には 200 本以上の営業日データが必要であり、このままでは `sma200 = NaN` → `golden_cross = None` が大量発生し、フィルターが機能しない。

**変更ファイル:** `src/screener.py`（`fetch_stock_data()`）

```python
# 変更前（252d = カレンダー日 → 約 180 営業日しか取れない）
period = f"{lookback_days}d"

# 変更後（× 1.5 補正 → 252 × 1.5 ≈ 378 カレンダー日 ≈ 270 営業日）
CALENDAR_DAY_FACTOR = 1.5
period = f"{int(lookback_days * CALENDAR_DAY_FACTOR)}d"
```

加えて `compute_indicators()` でも `len(close)` を事前確認し、上場直後等のデータ不足銘柄を安全に処理する（後述）。

**⚠️ 短期指標の計算窓の固定（review 指摘 対応）:**

現行の `compute_indicators()` は `price_change_1m = (close[-1] - close[0]) / close[0]` と
`volume_trend = 前半/後半の等分比較` を取得期間全体で計算している（`src/screener.py:151-159`）。
`lookback_days: 252` に変更するとこれらが **252 日窓ベースに変質**し、「1ヶ月騰落率」「短期出来高トレンド」の意味が崩れる。
`compute_indicators()` を以下のように修正し、**lookback_days に依存しない固定窓**に変更する:

```python
# 変更前（close[0] が 252 日前の値になり「1ヶ月騰落率」ではなくなる）
price_change_1m = (close[-1] - close[0]) / close[0]

# 変更後（直近 21 営業日固定 ≒ 1ヶ月 — lookback_days に依存しない）
price_change_1m = (
    (close.iloc[-1] - close.iloc[-22]) / close.iloc[-22]
    if len(close) >= 22 else (close.iloc[-1] - close.iloc[0]) / close.iloc[0]
)
```

```python
# 変更前（全取得期間を前半/後半に等分 — 252 日だと「126 日比較」になる）
mid = len(volume) // 2
vol_first = volume.iloc[:mid].mean()
vol_second = volume.iloc[mid:].mean()
volume_trend = (vol_second - vol_first) / vol_first if vol_first > 0 else 0.0

# 変更後（直近 42 営業日を固定窓として前半/後半 21 日ずつ比較 — lookback_days に依存しない）
VOL_WINDOW = 42
vol_data = volume.iloc[-VOL_WINDOW:] if len(volume) >= VOL_WINDOW else volume
mid = len(vol_data) // 2
vol_first = vol_data.iloc[:mid].mean()
vol_second = vol_data.iloc[mid:].mean()
volume_trend = (vol_second - vol_first) / vol_first if vol_first > 0 else 0.0
```

**変更ファイル:** `src/screener.py`

`compute_indicators()` の戻り値に追加:

```python
# SMA — len(close) >= 200 を事前確認（× 1.5 補正後も上場直後等でデータ不足の可能性あり）
if len(close) < 200:
    logger.warning("データ不足（%d本）: SMA200 計算不可。golden_cross=None。", len(close))
    golden_cross = None
else:
    sma50 = close.rolling(50).mean().iloc[-1]
    sma200 = close.rolling(200).mean().iloc[-1]
    # golden_cross は None（データ不足）/ 1.0（GC）/ 0.0（DC）の3値（review 指摘 #2 対応）
    if pd.isna(sma50) or pd.isna(sma200):
        golden_cross = None   # データ不足 → ハードフィルター対象外
    elif sma50 > sma200:
        golden_cross = 1.0    # ゴールデンクロス
    else:
        golden_cross = 0.0    # デス・クロス → ハードフィルター対象
```

`score_stock()` でのシグネチャ変更（review 指摘を受けて明示）:

現行は `score_stock(indicators: dict, weights: dict)` で呼ばれている（`src/screener.py:179`, `src/screener.py:295`）。
これを `config` 全体を受け取る設計に変更する:

```python
# 変更前
def score_stock(indicators: dict, weights: dict) -> float:
    ...

# 変更後（config を受け取り、内部で weights と golden_cross フラグを取得）
def score_stock(indicators: dict, config: dict) -> float:
    use_gc_filter = config.get("screening", {}).get("use_golden_cross_filter", True)
    weights = config.get("screening", {}).get("weights", {})
    gc = indicators.get("golden_cross")
    if use_gc_filter and gc is not None and gc == 0.0:
        # デス・クロス確定 かつ フィルター有効 → ハードフィルター（スコア強制 0）
        return 0.0
    # gc is None（データ不足）は除外しない
    # use_gc_filter=False の場合はフィルター全体をスキップ
    # gc == 1.0 は通常スコアリングへ
    ...
```

`screen()` 内の呼び出しも合わせて変更:

```python
# 変更前
score = score_stock(indicators, weights)

# 変更後
score = score_stock(indicators, config)
```

**既存テストの更新（review 指摘 対応 — 見落とし防止）:**

以下の既存テストは `score_stock(indicators, weights)` 形式で呼び出しているため、
新シグネチャ `score_stock(indicators, config)` に合わせて更新が必要:

| テスト | ファイル行 | 変更内容 |
|--------|-----------|---------|
| `test_score_stock_weights` | `tests/test_screener.py:54` | 第2引数を `weights` dict → `{"screening": {"weights": weights}}` 形式に変更 |
| `test_score_stock_with_fifty2w` | `tests/test_screener.py:139` | 同上 |
| `test_score_stock_fifty2w_none_skipped` | `tests/test_screener.py:152-153` | 同上（2箇所） |

`config.yaml` に追加:

```yaml
screening:
  use_golden_cross_filter: true   # false にすると無効化
```

**影響範囲:**
- `config.yaml`: `lookback_days` 30 → 252、`use_golden_cross_filter` 追加
- `src/screener.py`: `compute_indicators`（短期指標の固定窓化 + Golden Cross 追加）、`score_stock`
- `tests/test_screener.py`: Golden Cross ありなし・データ不足（None）のテストケース追加、`price_change_1m`/`volume_trend` の固定窓動作を確認するテスト追加

---

### A-2 Bollinger Band シグナル

**概要:** 価格が Bollinger Band（20日・2σ）の上限突破後の「スクイーズからのブレイクアウト」を検出する。

**変更ファイル:** `src/screener.py`

`compute_indicators()` の戻り値に追加:

```python
# Bollinger Band (20日, 2σ)
bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
bb_upper = bb.bollinger_hband().iloc[-1]
bb_lower = bb.bollinger_lband().iloc[-1]
bb_width = (bb_upper - bb_lower) / bb.bollinger_mavg().iloc[-1]  # バンド幅（スクイーズ検出用）
bb_pos = (current_price - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5
# 0=下限, 0.5=中央, 1.0=上限に位置
```

`score_stock()` でのスコアリング:

```python
# Bollinger Band スコア: 中央〜上限にいるほど高評価
bb_score = min(max(indicators.get("bb_pos", 0.5), 0.0), 1.0)
```

`config.yaml` に追加:

```yaml
screening:
  weights:
    bb_position: 0.10   # Bollinger Band スコアの重み（既存重みを調整して合計 1.0 に）
```

**既存重みの調整（合計 1.0 を維持 — review 指摘 #3 対応: 章間不整合を解消）:**

A-2 完了時点での重み（Phase C 適用前の中間状態）:

```yaml
weights:
  price_change_1m: 0.20   # 0.25 → 0.20
  volume_trend:   0.15   # 変更なし
  rsi_score:      0.20   # 変更なし（Phase C で adx_score 追加時に 0.15 へ再調整）
  macd_signal:    0.15   # 0.20 → 0.15
  fifty2w_score:  0.20   # 変更なし（Phase C で adx_score 追加時に 0.15 へ再調整）
  bb_position:    0.10   # 新規追加
# 合計: 0.20+0.15+0.20+0.15+0.20+0.10 = 1.00
```

> 最終的な全重みは「2. config.yaml 最終イメージ」の値（0.15/0.15）を正とする。

**影響範囲:**
- `src/screener.py`: `compute_indicators`, `score_stock`
- `config.yaml`: weights セクション
- `tests/test_screener.py`: Bollinger Band スコアのテスト追加

---

## Phase B: Slack 通知にチャート画像を添付

### 背景

Antigravity の差別化点は「チャート画像込みの HTML レポート生成」。
現行の Slack 通知はテキストのみ。週次の予測銘柄に価格チャート（終値 + SMA + BB）を添付することで、視覚的に確認しやすくする。

### 通知方式の決定（review 指摘 #6 対応）

**Slack Bot Token（files.upload）方式を正式採用する。**

- Webhook-only では `files.upload` が使えないため、画像添付には Bot Token が必須
- `SLACK_BOT_TOKEN=xoxb-...` を GitHub Actions Secrets および `.env` に追加する
- Webhook-only（`SLACK_WEBHOOK_URL`）は既存のテキスト通知に引き続き使用し、Bot Token は画像 upload にのみ追加で使用する

---

### B-1 チャート生成モジュール

**新規ファイル:** `src/chart_builder.py`

```python
def build_stock_chart(ticker: str, lookback_days: int, config: dict) -> bytes:
    """yfinance でデータを再取得し、OHLCV + SMA + BB チャートを PNG バイト列で返す。"""
```

#### データ取得設計（review 指摘 #4 対応）

`chart_builder.py` 内で yfinance からデータを直接再取得する。
これにより `screen()` の戻り値設計を変更せず、`main.py` への影響を最小化できる。

取得日数は以下のルールで決定する（review 指摘 #5 対応 + カレンダー日補正 — review 指摘対応）:

```python
# 描画は chart_lookback_days 分のみ（最終 N 行を使用）
chart_display_days = config.get("notifications", {}).get("chart_lookback_days", 60)

# SMA200 計算に必要な営業日数（200本）を確保する基準を決める
chart_fetch_days = max(chart_display_days, 252)

# A-1 の fetch_stock_data() と同じカレンダー日補正（× 1.5）を適用して yfinance に渡す
# （252 × 1.5 ≈ 378 カレンダー日 ≈ 270 営業日 → SMA200 安定計算可能 — review 指摘対応）
CALENDAR_DAY_FACTOR = 1.5
chart_fetch_period = f"{int(chart_fetch_days * CALENDAR_DAY_FACTOR)}d"
# yfinance 呼び出し例: yf.download(ticker, period=chart_fetch_period, ...)
```

使用ライブラリ: `matplotlib`（requirements.txt に追加）

> **注意（CI環境 — research6 指摘対応）:** Matplotlib はデフォルトで GUI バックエンドを使う場合があり、
> GitHub Actions 上でエラーとなる。`chart_builder.py` の先頭で非対話型バックエンドを明示的に設定すること:
>
> ```python
> import matplotlib
> matplotlib.use("Agg")  # 非対話型バックエンド（CI 環境必須、import前に設定）
> import matplotlib.pyplot as plt
> ```

チャート内容:
- 終値ライン
- SMA20（青）, SMA50（橙）, SMA200（赤）※ カレンダー日補正（× 1.5）適用で ≈ 270 営業日を確保するため安定計算可能
- Bollinger Band（塗りつぶし）
- 出来高バー（下部サブプロット）
- タイトル: `{ticker} — 直近 {chart_display_days} 日`

---

### B-2 notifier.py の更新

**変更ファイル:** `src/notifier.py`

現行の `notify()` シグネチャ（後方互換維持 — review 指摘 #3 対応）:

```python
# 変更前
def notify(
    predictions_df: pd.DataFrame,
    accuracy: dict | None = None,
    config: dict | None = None,
) -> bool:

# 変更後（stock_data を optional 引数として追加 → 既存呼び出し・テストはそのまま動く）
def notify(
    predictions_df: pd.DataFrame,
    accuracy: dict | None = None,
    config: dict | None = None,
    tickers_for_chart: list[str] | None = None,  # チャートを生成する銘柄リスト
) -> bool:
```

`tickers_for_chart` が渡された場合のみ `chart_builder.build_stock_chart()` を呼び出し、
Slack Bot Token を使って画像を upload する。

既存の `src/main.py` 呼び出し（`notify(predictions_df, accuracy, config)` 形式）は変更不要。
チャート添付を有効にするには `main.py` の呼び出しを拡張する。

**変更ファイル:** `src/main.py`

```python
# 変更前
notifier.notify(predictions_df, accuracy, config)

# 変更後（空予測 / ticker 列なしの場合も安全に処理 — review 指摘 #2 対応）
tickers = (
    predictions_df["ticker"].tolist()
    if not predictions_df.empty and "ticker" in predictions_df.columns
    else None
)
notifier.notify(predictions_df, accuracy, config, tickers_for_chart=tickers)
```

**影響範囲の確定:**
- `src/chart_builder.py`: 新規作成
- `src/notifier.py`: `notify()` に `tickers_for_chart` optional 引数追加
- `src/main.py`: `notify()` 呼び出しにティッカーリストを追加（空予測ガード込み）
- `requirements.txt`: matplotlib 追加
- `.github/workflows/weekly_run.yml`: job-level `env` に `SLACK_BOT_TOKEN` を追加（review 指摘対応 — 後述）
- `tests/test_notifier.py`: 新規分岐のテストを追加（review 指摘 #4 対応）
- `tests/test_chart_builder.py`: 新規作成
- `README.md`: GitHub Actions 必要 Secrets に `SLACK_BOT_TOKEN` を追記（research6 指摘対応）
- `.env.example`: `SLACK_BOT_TOKEN` を追記（review 指摘対応）

**`.github/workflows/weekly_run.yml` の変更内容（review 指摘対応 — 注入位置の明記）:**

`SLACK_BOT_TOKEN` は `src/main.py` から参照されるため、`SLACK_WEBHOOK_URL` と同じ **job-level `env`** に追加する:

```yaml
jobs:
  analyze:
    env:
      SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
      SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}   # 追加
```

---

**`tests/test_notifier.py` に追加するテストケース（review 指摘 #4 対応）:**

| テストケース | 確認内容 |
|---|---|
| `tickers_for_chart=None` | 既存動作と同一（chart_builder を呼ばない） |
| `slack_chart=false` かつ `tickers_for_chart` あり | upload が呼ばれない |
| `SLACK_BOT_TOKEN` 未設定 かつ `tickers_for_chart` あり | 例外を起こさず upload をスキップ |
| upload API が 5xx を返す | `notify()` が `False` を返す（Slack 送信失敗扱い） |

**環境変数の追加:**

```
SLACK_BOT_TOKEN=xoxb-...   # 画像アップロード用（Bot Token 方式）
```

**Slack チャンネル指定（research6・review 指摘対応）:**

`files.upload` API（および後継 `files.getUploadURLExternal`）にはチャンネル **ID** が必要。
現行 `config.yaml` の `slack.channel: "#stock-alerts"` はチャンネル名であり、ID ではない。

`config.yaml` にチャンネル ID 用のキーを追加し、名前→ID 解決を回避する:

```yaml
notifications:
  slack_channel_id: ""   # Bot Token 使用時の upload 先チャンネル ID（例: "C012AB3CD"）
                         # 空のままの場合は conversations.list API で slack.channel 名から自動解決
```

`notifier.py` での解決ロジック:

```python
channel_id = config.get("notifications", {}).get("slack_channel_id", "")
if not channel_id:
    # 名前から ID を解決（conversations.list API を使用）
    # 解決失敗時は upload をスキップして警告ログを出力
    channel_id = _resolve_channel_id(
        config.get("slack", {}).get("channel", "#stock-alerts"),
        bot_token,
    )
# requests を使って files.upload / files.getUploadURLExternal に POST
# （slack_sdk は使わず既存 requests で統一）
```

> 注意: Bot が当該チャンネルに参加している必要がある（Bot をチャンネルに招待すること）。
> `files.upload` が非推奨になる可能性があるため、
> 実装時は Slack API ドキュメントの最新仕様（`files.getUploadURLExternal` + `files.completeUploadExternal`）を確認すること。

`config.yaml` に追加:

```yaml
notifications:
  slack_chart: true          # チャート添付を有効にするか（false で従来のテキスト通知のみ）
  chart_lookback_days: 60    # チャートに表示する日数（取得は max(60, 252) 日分）
```

**依存ライブラリ追加（requirements.txt）:**

```
matplotlib>=3.8.0
```

---

## Phase C: ADX トレンド強度フィルター

### 背景

RSI・MACD・Golden Cross だけでは「弱いトレンドの銘柄」を誤選出することがある。
ADX（Average Directional Index）でトレンド強度を測り、スコアに反映する。

**変更ファイル:** `src/screener.py`

`compute_indicators()` の戻り値に追加:

```python
# ADX (14日) — ta ライブラリに実装済み
adx_ind = ta.trend.ADXIndicator(
    high=df["High"].squeeze(),
    low=df["Low"].squeeze(),
    close=close,
    window=14
)
adx_val = adx_ind.adx().iloc[-1]
# 25+ = トレンドあり, 50+ = 強いトレンド
adx_score = min(float(adx_val) / 50.0, 1.0) if not pd.isna(adx_val) else 0.5
```

`score_stock()` でのスコアリング:

```python
adx_score = indicators.get("adx_score", 0.5)
```

> **注意（research6 指摘対応）:** ADX はトレンドの「強さ」を示すが「方向」は示さない。
> 強い下降トレンド銘柄も ADX が高くなるため、高スコアになり得る。
> ただし A-1 の Golden Cross フィルター（`use_golden_cross_filter: true`）により
> デス・クロス銘柄はスコア 0 で除外されるため、実運用上の影響は限定的。
> 将来的に ADX + DI+/DI- を組み合わせてトレンド方向を加味する拡張も可能。

`config.yaml` に追加:

```yaml
screening:
  weights:
    adx_score: 0.10   # ADX スコアの重み（BB と合わせて既存重みを再調整）
```

**影響範囲:**
- `src/screener.py`: `compute_indicators`, `score_stock`
- `config.yaml`: weights セクション

---

## 2. config.yaml 最終イメージ（変更箇所のみ）

```yaml
screening:
  lookback_days: 252           # 30 → 252（SMA200 計算のため）
  use_golden_cross_filter: true
  weights:
    price_change_1m: 0.20
    volume_trend:    0.15
    rsi_score:       0.15
    macd_signal:     0.15
    fifty2w_score:   0.15
    bb_position:     0.10
    adx_score:       0.10

notifications:
  slack_chart: true
  chart_lookback_days: 60    # 表示日数。取得は max(60, 252) = 252 日分
  slack_channel_id: ""       # upload 先チャンネル ID（空なら slack.channel 名から自動解決）
```

---

## 3. 実装順序

```
Phase A-1 (Golden Cross フィルター + lookback_days 変更)
  → Phase A-2 (Bollinger Band スコア)
    → Phase C (ADX スコア)
      → Phase B (チャート画像生成・送信)
```

A → C は screener.py の修正のみで完結。B は新規モジュールを含むため後回し。

---

## 4. Verification Plan

### Phase A + C（screener 強化）

```powershell
python -m pytest tests/test_screener.py -v
```

確認ポイント:
- `compute_indicators()` の戻り値に `golden_cross`（None/1.0/0.0）, `bb_pos`, `adx_score` キーが追加されている
- Golden Cross フィルターが `use_golden_cross_filter: true` で機能する
- `golden_cross is None`（データ不足）の場合にハードフィルターが**適用されない**こと
- `golden_cross == 0.0`（デス・クロス）の場合にスコアが 0 になること
- `use_golden_cross_filter: false` の場合、デス・クロス銘柄でも**スコアが 0 にならない**こと（フィルター無効化の確認）

### Phase B（チャート生成 + notifier 分岐）

```powershell
python -m pytest tests/test_chart_builder.py tests/test_notifier.py -v
```

確認ポイント:
- `build_stock_chart()` が PNG バイト列を返す
- データ不足時（< 20 日）でもエラーにならない
- `tickers_for_chart=None` → 既存動作と同一（upload 未呼び出し）
- `slack_chart=false` → upload 未呼び出し
- `SLACK_BOT_TOKEN` 未設定 → スキップ（例外なし）
- `predictions_df` が空の場合 → `tickers=None` となり notify() が安全に終了する

### 統合確認

```powershell
python -m pytest tests/ -q
```

全テスト通過後、`workflow_dispatch` で手動実行して CI グリーンを確認。
