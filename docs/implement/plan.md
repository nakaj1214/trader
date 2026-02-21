# 実装計画書

---

## フェーズ一覧

| フェーズ | 内容 | 状態 |
|---------|------|------|
| 17 | J-Quants API 日本株ファンダメンタルデータ強化 | **実装済み** |
| 18 | Finnhub ニュース・センチメントシグナル追加 | **実装済み** |
| 19 | Financial Modeling Prep グローバル財務データ補完 | **実装済み** |
| 20 | Prophet interval_width と prob_up 変換の整合修正 | **実装済み** |
| 21 | prob_up 確率校正（Platt scaling / isotonic）実装 | **Step 0 実装済み（Step 1 以降は 50 件蓄積後）** |
| 22 | J-Quants V2 APIキー方式への移行 | **実装済み** |
| 23 | 流動性フィルタ強化（min_avg_dollar_volume_us / _jp） | **実装済み** |
| 24 | 決算禁則フィルタ（J-Quants 決算カレンダー連携） | **実装済み** |
| 25 | Prophet 設定の config 露出 | **実装済み** |

---

## フェーズ17: J-Quants API 日本株ファンダメンタルデータ強化（実装済み）

### 背景と精度向上の見込み

#### 現状の問題

`src/enricher.py` の `compute_evidence_signals()` は evidence スコアを 4 ファクターで算出する：

| ファクター | 重み | 使用フィールド | JP株での問題 |
|-----------|------|---------------|-------------|
| momentum_z | 30% | 株価履歴（Close） | ✅ 問題なし |
| value_z | 25% | `info["priceToBook"]` | ❌ yfinance が **頻繁に null** |
| quality_z | 25% | `info["returnOnEquity"]` | ❌ yfinance が **頻繁に null** |
| low_risk_z | 20% | vol_20d_ann（株価から計算） | ✅ 問題なし |

日本株（.T サフィックス）では `yf.Ticker(t).info` の `priceToBook` / `returnOnEquity` が
取得できないケースが多い。この場合 value_z と quality_z が両方 `None` になり、
**composite スコアは momentum + low_risk の 2 ファクター（計 50%重み）でしか計算されない**。

#### J-Quants API で解決できること

[J-Quants API](https://jpx-jquants.com/)（日本取引所グループ公式）の `fins/statements` エンドポイントは
四半期財務データ（PBR・ROE・EPS 等）を提供する。これを補完データとして使うことで：

- `value_z`（P/B逆数）：null → **常に算出可能**
- `quality_z`（ROE）：null → **常に算出可能**
- evidence composite カバレッジ：~50% → **~100%**

**JP 銘柄のエビデンスランキング精度が大幅に向上し、スクリーニングの銘柄選択品質が改善する。**

> **米国株には影響しない**（J-Quants は日本株専用。US 株は yfinance 継続）

#### 無料プランで利用可能なデータ

| エンドポイント | 用途 | 取得フィールド |
|--------------|------|--------------|
| `fins/statements` | 四半期財務 | `PBR`, `ROEAfterTax`, `EPS`, `DividendPayableDate` |
| `listed/info` | 銘柄属性 | `Sector17Code`, `Sector33Code`, `ScaleCategory` |
| `prices/daily_quotes` | OHLCV | `Open`, `High`, `Low`, `Close`, `Volume` |

---

### 実装方針

#### 方針: J-Quants を「補完データソース」として使う

- JP ティッカーの enrichment 時のみ J-Quants API を呼び出す
- yfinance で取得できた値があれば尊重し、null の場合だけ J-Quants で補完
- JQUANTS_MAIL_ADDRESS / JQUANTS_PASSWORD が未設定なら従来どおり（degraded mode）
- 米国株フローには一切影響しない

```
JP ticker enrichment フロー（Phase 17 後）:

_fetch_info(ticker)
  ├─ yf.Ticker(ticker).info  →  base info dict
  └─ is_jp_ticker(ticker) かつ J-Quants 設定あり?
       YES → _supplement_jp_info(info, ticker)
               ├─ fins/statements で PBR・ROE 取得
               ├─ info["priceToBook"] が None → J-Quants PBR で上書き
               └─ info["returnOnEquity"] が None → J-Quants ROE で上書き
       NO  → info をそのまま返す（従来動作）
```

---

### 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| `src/jquants_fetcher.py` | **新規** | J-Quants API クライアント（認証・財務データ取得・キャッシュ） |
| `src/enricher.py` | **修正** | `_fetch_info()` に JP 補完ロジック追加 |
| `.env.example` | **修正** | `JQUANTS_MAIL_ADDRESS` / `JQUANTS_PASSWORD` を追記 |
| `requirements.txt` | **修正** | `jquantsapi` を追加 |
| `config.yaml` | **修正** | `jquants:` セクション追加（enabled フラグ） |
| `tests/test_jquants_fetcher.py` | **新規** | モックを使った単体テスト |

---

### 実装詳細

#### `src/jquants_fetcher.py`（新規）

```python
"""J-Quants API クライアント

日本株の財務データ（PBR・ROE）を取得し、yfinance の null を補完する。
JQUANTS_MAIL_ADDRESS / JQUANTS_PASSWORD が未設定の場合は全関数が {} を返す。

認証フロー:
  1. POST /token/auth_user (mail + password) → refresh_token
  2. POST /token/auth_refresh (refresh_token) → id_token
  3. GET /fins/statements?code=<4桁コード> (Authorization: Bearer <id_token>)
"""

import logging
import os
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.jquants.com/v1"

# セッション内キャッシュ（再実行時の重複取得を防ぐ）
_id_token_cache: str | None = None
_financial_cache: dict[str, dict] = {}


def _get_id_token() -> str | None:
    """J-Quants id_token を取得する（セッション内キャッシュあり）。"""
    global _id_token_cache
    if _id_token_cache:
        return _id_token_cache
    mail = os.environ.get("JQUANTS_MAIL_ADDRESS")
    password = os.environ.get("JQUANTS_PASSWORD")
    if not mail or not password:
        return None
    try:
        # Step 1: refresh_token
        r = requests.post(f"{BASE_URL}/token/auth_user",
                          json={"mailaddress": mail, "password": password}, timeout=10)
        r.raise_for_status()
        refresh_token = r.json()["refreshToken"]
        # Step 2: id_token
        r2 = requests.post(f"{BASE_URL}/token/auth_refresh",
                           params={"refreshtoken": refresh_token}, timeout=10)
        r2.raise_for_status()
        _id_token_cache = r2.json()["idToken"]
        return _id_token_cache
    except Exception:
        logger.warning("J-Quants 認証失敗（JQUANTS_MAIL_ADDRESS / JQUANTS_PASSWORD を確認）")
        return None


def fetch_financial_data(ticker: str) -> dict:
    """ticker（例: "7203.T"）の最新四半期財務データを取得する。

    Returns:
        {"priceToBook": float, "returnOnEquity": float} or {}
    """
    if ticker in _financial_cache:
        return _financial_cache[ticker]

    id_token = _get_id_token()
    if not id_token:
        return {}

    # yfinance の "7203.T" → J-Quants は "72030"（5桁、末尾 0 補完）
    code = ticker.replace(".T", "").zfill(4) + "0"
    try:
        r = requests.get(
            f"{BASE_URL}/fins/statements",
            params={"code": code},
            headers={"Authorization": f"Bearer {id_token}"},
            timeout=15,
        )
        r.raise_for_status()
        statements = r.json().get("statements", [])
        if not statements:
            _financial_cache[ticker] = {}
            return {}
        # 最新レコードを使用
        latest = statements[-1]
        result = {}
        if (pbr := latest.get("PBR")) is not None:
            try:
                result["priceToBook"] = float(pbr)
            except (ValueError, TypeError):
                pass
        if (roe := latest.get("ROEAfterTax")) is not None:
            try:
                result["returnOnEquity"] = float(roe) / 100.0  # % → 小数
            except (ValueError, TypeError):
                pass
        _financial_cache[ticker] = result
        return result
    except Exception:
        logger.warning("J-Quants fins/statements 取得失敗: %s", ticker)
        _financial_cache[ticker] = {}
        return {}
```

#### `src/enricher.py` 変更箇所

```python
# 変更前
def _fetch_info(ticker: str) -> dict:
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}

# 変更後
def _fetch_info(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}
    # Phase 17: JP 株は J-Quants で null フィールドを補完
    if is_jp_ticker(ticker):
        info = _supplement_jp_info(info, ticker)
    return info


def _supplement_jp_info(info: dict, ticker: str) -> dict:
    """J-Quants API で priceToBook / returnOnEquity の null を補完する。"""
    try:
        from src.jquants_fetcher import fetch_financial_data
        jq = fetch_financial_data(ticker)
        if not jq:
            return info
        info = dict(info)  # コピーして変更
        if info.get("priceToBook") is None and "priceToBook" in jq:
            info["priceToBook"] = jq["priceToBook"]
            logger.debug("J-Quants PBR 補完: %s → %.2f", ticker, jq["priceToBook"])
        if info.get("returnOnEquity") is None and "returnOnEquity" in jq:
            info["returnOnEquity"] = jq["returnOnEquity"]
            logger.debug("J-Quants ROE 補完: %s → %.4f", ticker, jq["returnOnEquity"])
    except Exception:
        logger.warning("J-Quants 補完失敗: %s（従来の info を使用）", ticker)
    return info
```

#### `.env.example` 追記

```bash
# J-Quants API（日本株ファンダメンタルデータ補完）
# https://jpx-jquants.com/ で無料登録後に取得
JQUANTS_MAIL_ADDRESS=your-email@example.com
JQUANTS_PASSWORD=your-jquants-password
```

#### `config.yaml` 追加セクション

```yaml
jquants:
  enabled: true          # false にすると yfinance のみで動作（Phase 17 以前と同じ）
```

> **`enabled` フラグの実装ポリシー（Phase 17/18/19 共通）**: API キー未設定の場合と同様に、`enabled: false` でも API 呼び出しをスキップする。fetcher を呼び出す前（`_supplement_jp_info` 等）で `load_config()["jquants"]["enabled"]` を確認し、`false` ならスキップ。これにより APIキーが設定済みでも強制無効化できる。

#### `requirements.txt` 追加

```
jquantsapi>=0.5.0   # オプション（なくても degraded mode で動作）
```

---

### テスト方針

`tests/test_jquants_fetcher.py`（新規）:

```python
# モックを使い、API キー不要でテスト可能にする
class TestFetchFinancialData:
    def test_returns_empty_when_no_credentials(self):
        # JQUANTS_MAIL_ADDRESS 未設定 → {} を返す
        ...

    def test_supplements_pbr_from_jquants(self, mock_requests):
        # PBR null の info を渡すと J-Quants 値で補完される
        ...

    def test_does_not_overwrite_existing_value(self, mock_requests):
        # yfinance で取れた PBR は上書きしない
        ...

    def test_us_ticker_not_supplemented(self):
        # US 銘柄（AAPL 等）は J-Quants を呼ばない
        ...
```

---

### 段階的な実装ステップ

```
Step 1: src/jquants_fetcher.py 作成 + tests/test_jquants_fetcher.py
Step 2: src/enricher.py に _supplement_jp_info() を追加
Step 3: .env.example / requirements.txt / config.yaml 更新
Step 4: 手動で python -m src.main を実行し、JP 銘柄のエビデンス composite が
        value_z / quality_z を含むようになったことをログで確認
Step 5: plan.md を 実装済み に更新
```

---

### 受け入れ確認チェック

- [ ] `JQUANTS_MAIL_ADDRESS` 未設定時は従来動作（JP 銘柄の value_z / quality_z が null のまま）
- [ ] `JQUANTS_MAIL_ADDRESS` 設定時、JP 銘柄の `evidence.value_z` が non-null になる
- [ ] `JQUANTS_MAIL_ADDRESS` 設定時、JP 銘柄の `evidence.quality_z` が non-null になる
- [ ] US 銘柄の enrichment は一切変化しない
- [ ] J-Quants API タイムアウト・エラー時でも処理が継続する（try/except）
- [ ] テストが全件パスする（API モック使用）

---

## フェーズ18: Finnhub ニュース・センチメントシグナル追加（実装済み）

### 背景と精度向上の見込み

#### 現状の問題

現在のシグナル群は株価・財務データのみで構成されており、**ニュース・市場心理（センチメント）**は一切考慮されていない。
proposal.md の「② OpenAI API でニュースを活用」という目的を、**Finnhub の無料 API で OpenAI APIキー不要かつ低コストに実現できる**。

| 現状 | 問題 |
|------|------|
| evidence composite | momentum / value / quality / low_risk の 4 ファクターのみ |
| ニュース効果 | 未組み込み（決算・リコール・M&A 等のイベントを検知できない） |
| センチメント | 未組み込み（強気・弱気の偏りを定量化できない） |

#### Finnhub API で解決できること

[Finnhub](https://finnhub.io/)（無料 60 req/分）の `news-sentiment` エンドポイントは
直近ニュースの強気・弱気比率とバズ量を返す。これを新たなシグナルとして追加することで：

- **センチメントシグナル**：強気割合・弱気割合・バズ量を `news_sentiment` フィールドとして出力
- **ランキング補助**：evidence composite の高い銘柄の中で、ニュースが強気のものを優先提示
- **リスクフィルタ**：強気割合が低い（`bearishPercent > 0.65`）銘柄に警告フラグを付与

> **対象: US 株のみ（S&P500 / NASDAQ100）**
> Finnhub の日本株ニュース対応は無料プランでは限定的なため、JP 株は対象外。

#### 無料プランで利用可能なデータ

| エンドポイント | レート制限 | 取得フィールド |
|--------------|-----------|--------------|
| `GET /api/v1/news-sentiment` | 60 req/分 | `companyNewsScore`, `sentiment.bullishPercent`, `sentiment.bearishPercent`, `buzz.weeklyAverage` |

---

### 実装方針

#### 方針: センチメントを「独立した enrichment フィールド」として追加する

- evidence composite のウェイトは変更しない（既存スコアへの破壊的変更を避ける）
- `news_sentiment` というネストオブジェクトを出力 JSON に追加する
- `FINNHUB_API_KEY` が未設定なら `news_sentiment: null`（degraded mode）
- US 株のみ対象。JP 株フローには一切影響しない

```
US ticker enrichment フロー（Phase 18 後）:

enrich(ticker)
  ├─ 既存: evidence / risk / short / institutional / events
  └─ Phase 18: enrich_news_sentiment(ticker)
       ├─ FINNHUB_API_KEY 未設定? → news_sentiment: null でスキップ
       └─ GET /api/v1/news-sentiment?symbol={ticker}
            → news_sentiment: {
                "score": 0.72,           # companyNewsScore (0〜1)
                "bullish_pct": 0.72,     # bullishPercent
                "bearish_pct": 0.28,     # bearishPercent
                "weekly_buzz": 5.2,      # buzz.weeklyAverage
                "signal": "bullish"      # bullish / neutral / bearish
              }
```

**signal 判定基準:**

| signal | 条件 |
|--------|------|
| `"bullish"` | `bullishPercent >= 0.60` |
| `"bearish"` | `bearishPercent >= 0.60` |
| `"neutral"` | それ以外 |

---

### 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| `src/finnhub_fetcher.py` | **新規** | Finnhub API クライアント（センチメント取得・キャッシュ） |
| `src/enricher.py` | **修正** | `_enrich_news_sentiment()` 追加、`enrich()` ループ内で呼び出し dict に格納 |
| `src/exporter.py` | **修正** | `news_sentiment` キーを出力 JSON に含める処理を追加 |
| `.env.example` | **修正** | `FINNHUB_API_KEY` を追記 |
| `requirements.txt` | **修正** | `finnhub-python>=2.4.0` を追加 |
| `config.yaml` | **修正** | `finnhub:` セクション追加（enabled フラグ） |
| `tests/test_finnhub_fetcher.py` | **新規** | モックを使った単体テスト |

---

### 実装詳細

#### `src/finnhub_fetcher.py`（新規）

```python
"""Finnhub API クライアント

US 株のニュース・センチメントデータを取得する。
FINNHUB_API_KEY が未設定の場合は全関数が {} を返す（degraded mode）。
"""

import logging
import os
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://finnhub.io/api/v1"

_sentiment_cache: dict[str, dict] = {}


def fetch_news_sentiment(ticker: str) -> dict:
    """ticker（例: "AAPL"）のニュース・センチメントを取得する。

    Returns:
        {
            "score": float,         # companyNewsScore (0〜1)
            "bullish_pct": float,   # bullishPercent
            "bearish_pct": float,   # bearishPercent
            "weekly_buzz": float,   # buzz.weeklyAverage
            "signal": str           # "bullish" / "neutral" / "bearish"
        }
        or {} （APIキー未設定・エラー時）
    """
    if ticker in _sentiment_cache:
        return _sentiment_cache[ticker]

    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        return {}

    try:
        r = requests.get(
            f"{BASE_URL}/news-sentiment",
            params={"symbol": ticker, "token": api_key},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

        sentiment = data.get("sentiment", {})
        buzz = data.get("buzz", {})
        bullish = sentiment.get("bullishPercent", 0.5)
        bearish = sentiment.get("bearishPercent", 0.5)

        if bullish >= 0.60:
            signal = "bullish"
        elif bearish >= 0.60:
            signal = "bearish"
        else:
            signal = "neutral"

        result = {
            "score": data.get("companyNewsScore"),
            "bullish_pct": bullish,
            "bearish_pct": bearish,
            "weekly_buzz": buzz.get("weeklyAverage"),
            "signal": signal,
        }
        _sentiment_cache[ticker] = result
        return result
    except Exception:
        logger.warning("Finnhub センチメント取得失敗: %s", ticker)
        _sentiment_cache[ticker] = {}
        return {}
```

#### `src/enricher.py` 変更箇所

> **I/F 注意**: `enrich()` は `{(date, ticker): {...}}` 形式の dict を返す。
> `news_sentiment` は `records` を直接更新するのではなく、この dict に追加する。
> `exporter.py` の `ticker_data.get("news_sentiment")` で読み取り、出力 JSON に含める。

```python
def _enrich_news_sentiment(ticker: str, config: dict) -> dict | None:
    """US 銘柄のニュース・センチメントを返す。JP 株・API キー未設定・enabled=false 時は None。"""
    cfg = config.get("finnhub", {})
    if not cfg.get("enabled", True):
        return None
    if is_jp_ticker(ticker):
        return None
    from src.finnhub_fetcher import fetch_news_sentiment
    return fetch_news_sentiment(ticker) or None

# enrich() の各 ticker 処理後に enrichment dict へ追加:
#   enrichment[(date, ticker)]["news_sentiment"] = _enrich_news_sentiment(ticker, config)
```

#### `.env.example` 追記

```bash
# Finnhub API（US 株ニュース・センチメント）
# https://finnhub.io/register で無料登録後に取得
FINNHUB_API_KEY=your-finnhub-api-key
```

#### `config.yaml` 追加セクション

```yaml
finnhub:
  enabled: true   # false にすると従来動作（news_sentiment: null）
```

> **`enabled` フラグ**: `_enrich_news_sentiment()` 内で `config["finnhub"]["enabled"]` を確認し、`false` の場合は API キーが設定済みでもスキップ（Phase 17 の `enabled` ポリシーと同じ）。

---

### テスト方針

`tests/test_finnhub_fetcher.py`（新規）:

```python
class TestFetchNewsSentiment:
    def test_returns_empty_when_no_api_key(self):
        # FINNHUB_API_KEY 未設定 → {} を返す
        ...

    def test_bullish_signal_when_bullish_pct_high(self, mock_requests):
        # bullishPercent=0.75 → signal="bullish"
        ...

    def test_bearish_signal_when_bearish_pct_high(self, mock_requests):
        # bearishPercent=0.65 → signal="bearish"
        ...

    def test_jp_ticker_skipped(self):
        # JP 銘柄（7203.T 等）は Finnhub を呼ばない
        ...
```

---

### 段階的な実装ステップ

```
Step 1: src/finnhub_fetcher.py 作成 + tests/test_finnhub_fetcher.py
Step 2: src/enricher.py に _enrich_news_sentiment() 追加、enrich() ループで enrichment dict に格納
Step 3: src/exporter.py で news_sentiment キーを出力 JSON に反映
Step 4: .env.example / requirements.txt / config.yaml 更新
Step 5: FINNHUB_API_KEY をセットして python -m src.main を実行し
        US 銘柄の news_sentiment フィールドが出力 JSON に含まれることを確認
Step 6: plan.md を 実装済み に更新
```

---

### 受け入れ確認チェック

- [ ] `FINNHUB_API_KEY` 未設定時は `news_sentiment: null`（従来動作）
- [ ] `FINNHUB_API_KEY` 設定時、US 銘柄の出力 JSON に `news_sentiment.signal` が含まれる
- [ ] `bullishPercent >= 0.60` → `signal: "bullish"` になる
- [ ] JP 銘柄の `news_sentiment` は常に `null`
- [ ] API エラー・タイムアウト時でも処理が継続する（try/except）
- [ ] テストが全件パスする（API モック使用）

---

## フェーズ19: Financial Modeling Prep グローバル財務データ補完（実装済み）

### 背景と精度向上の見込み

#### 現状の問題

| データソース | US株 | JP株 |
|-------------|------|------|
| yfinance `.info` | P/B・ROE が稀に null | P/B・ROE が頻繁に null |
| J-Quants (Phase 17) | 対象外 | PBR・ROE を補完 |
| **FMP（本フェーズ）** | **P/B・ROE の null を補完** | **J-Quants で取れない銘柄を補完** |

Phase 17 で JP 株の財務データ補完は大幅に改善されるが、以下のケースが残る：

- **US 株**：yfinance の `.info` で `priceToBook` / `returnOnEquity` が null になる銘柄が存在する
- **JP 株**：J-Quants の `fins/statements` にデータがない銘柄（上場間もない等）

[Financial Modeling Prep (FMP)](https://site.financialmodelingprep.com/) は無料プランで
**250 req/日・46 カ国 70,000+ 銘柄**の財務データを提供する。
東証（TSE）対応済みで、US 株・JP 株両方のバックアップソースとして機能する。

#### FMP 無料プランで利用可能なデータ

| エンドポイント | 用途 | 取得フィールド |
|--------------|------|--------------|
| `GET /api/v3/key-metrics/{symbol}` | 財務指標 | `pbRatio`, `roe`, `eps`, `debtToEquity` |
| `GET /api/v3/ratios/{symbol}` | 財務比率 | `priceToBookRatio`, `returnOnEquity`, `currentRatio` |

---

### 実装方針

#### 方針: FMP を「最終フォールバック」として使う

- **US 株**: yfinance → （null なら）FMP で補完
- **JP 株**: yfinance → J-Quants（Phase 17）→ （まだ null なら）FMP で補完
- `FMP_API_KEY` が未設定なら従来どおり（degraded mode）
- 1 日 250 req の上限を考慮し、**null のフィールドがある銘柄のみ FMP を呼び出す**

```
_fetch_info(ticker) フロー（Phase 19 後）:

_fetch_info(ticker)
  ├─ yf.Ticker(ticker).info → base info
  ├─ is_jp_ticker? → J-Quants 補完（Phase 17）
  └─ priceToBook or returnOnEquity が null かつ FMP_API_KEY あり?
       YES → _supplement_fmp_info(info, ticker)
               ├─ GET /api/v3/key-metrics/{ticker}?period=quarter
               ├─ info["priceToBook"] が None → FMP pbRatio で上書き
               └─ info["returnOnEquity"] が None → FMP roe で上書き
       NO  → info をそのまま返す
```

---

### 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| `src/fmp_fetcher.py` | **新規** | FMP API クライアント（財務指標取得・キャッシュ・レート管理） |
| `src/enricher.py` | **修正** | `_fetch_info()` に FMP フォールバックロジック追加 |
| `.env.example` | **修正** | `FMP_API_KEY` を追記 |
| `config.yaml` | **修正** | `fmp:` セクション追加（enabled フラグ） |
| `tests/test_fmp_fetcher.py` | **新規** | モックを使った単体テスト |

---

### 実装詳細

#### `src/fmp_fetcher.py`（新規）

```python
"""Financial Modeling Prep API クライアント

US 株・JP 株の財務データ（PBR・ROE）を取得し、yfinance / J-Quants の
null を最終フォールバックとして補完する。
FMP_API_KEY が未設定の場合は全関数が {} を返す（degraded mode）。

無料プラン制限: 250 req/日
"""

import logging
import os
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://financialmodelingprep.com/api/v3"

_metrics_cache: dict[str, dict] = {}


def fetch_key_metrics(ticker: str) -> dict:
    """ticker（例: "AAPL" または "7203.T"）の最新四半期財務指標を取得する。

    JP 株の場合は ticker をそのまま渡す（FMP は "7203.T" 形式に対応）。

    Returns:
        {"priceToBook": float, "returnOnEquity": float} or {}
    """
    if ticker in _metrics_cache:
        return _metrics_cache[ticker]

    api_key = os.environ.get("FMP_API_KEY")
    if not api_key:
        return {}

    try:
        r = requests.get(
            f"{BASE_URL}/key-metrics/{ticker}",
            params={"period": "quarter", "limit": 1, "apikey": api_key},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            _metrics_cache[ticker] = {}
            return {}

        latest = data[0]
        result = {}
        if (pb := latest.get("pbRatio")) is not None:
            try:
                result["priceToBook"] = float(pb)
            except (ValueError, TypeError):
                pass
        if (roe := latest.get("roe")) is not None:
            try:
                result["returnOnEquity"] = float(roe)  # FMP は小数（0.12 = 12%）
            except (ValueError, TypeError):
                pass
        _metrics_cache[ticker] = result
        return result
    except Exception:
        logger.warning("FMP key-metrics 取得失敗: %s", ticker)
        _metrics_cache[ticker] = {}
        return {}
```

#### `src/enricher.py` 変更箇所

```python
def _fetch_info(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}
    # Phase 17: JP 株は J-Quants で補完
    if is_jp_ticker(ticker):
        info = _supplement_jp_info(info, ticker)
    # Phase 19: null が残っていれば FMP で最終補完（US/JP 両対応）
    if info.get("priceToBook") is None or info.get("returnOnEquity") is None:
        info = _supplement_fmp_info(info, ticker)
    return info


def _supplement_fmp_info(info: dict, ticker: str) -> dict:
    """FMP API で priceToBook / returnOnEquity の null を最終補完する。"""
    try:
        from src.fmp_fetcher import fetch_key_metrics
        fmp = fetch_key_metrics(ticker)
        if not fmp:
            return info
        info = dict(info)
        if info.get("priceToBook") is None and "priceToBook" in fmp:
            info["priceToBook"] = fmp["priceToBook"]
            logger.debug("FMP PBR 補完: %s → %.2f", ticker, fmp["priceToBook"])
        if info.get("returnOnEquity") is None and "returnOnEquity" in fmp:
            info["returnOnEquity"] = fmp["returnOnEquity"]
            logger.debug("FMP ROE 補完: %s → %.4f", ticker, fmp["returnOnEquity"])
    except Exception:
        logger.warning("FMP 補完失敗: %s（従来の info を使用）", ticker)
    return info
```

#### `.env.example` 追記

```bash
# Financial Modeling Prep API（グローバル財務データ補完）
# https://site.financialmodelingprep.com/ で無料登録後に取得（250 req/日）
FMP_API_KEY=your-fmp-api-key
```

#### `config.yaml` 追加セクション

```yaml
fmp:
  enabled: true   # false にすると FMP 補完を無効化
```

> **`enabled` フラグ**: `_supplement_fmp_info()` 内で `config["fmp"]["enabled"]` を確認し、`false` の場合はスキップ（Phase 17 の `enabled` ポリシーと同じ）。

---

### テスト方針

`tests/test_fmp_fetcher.py`（新規）:

```python
class TestFetchKeyMetrics:
    def test_returns_empty_when_no_api_key(self):
        # FMP_API_KEY 未設定 → {} を返す
        ...

    def test_supplements_pbr_for_us_stock(self, mock_requests):
        # AAPL の priceToBook null → FMP pbRatio で補完
        ...

    def test_supplements_roe_for_jp_stock(self, mock_requests):
        # 7203.T の returnOnEquity null → FMP roe で補完
        ...

    def test_does_not_overwrite_existing_value(self, mock_requests):
        # yfinance / J-Quants で取れた値は上書きしない
        ...
```

---

### 段階的な実装ステップ

```
Step 1: src/fmp_fetcher.py 作成 + tests/test_fmp_fetcher.py
Step 2: src/enricher.py の _fetch_info() に FMP フォールバックを追加
Step 3: .env.example / config.yaml 更新
Step 4: FMP_API_KEY をセットして python -m src.main を実行し、
        yfinance で null だった P/B・ROE が補完されることをログで確認
Step 5: plan.md を 実装済み に更新
```

---

### 受け入れ確認チェック

- [ ] `FMP_API_KEY` 未設定時は従来動作（FMP は一切呼ばれない）
- [ ] US 株で yfinance が null を返した場合に FMP 値が補完される
- [ ] JP 株で J-Quants が null を返した場合に FMP 値が補完される
- [ ] yfinance / J-Quants で取得済みの値は FMP で上書きされない
- [ ] FMP API エラー・タイムアウト時でも処理が継続する（try/except）
- [ ] テストが全件パスする（API モック使用）

---

## フェーズ20: Prophet interval_width と prob_up 変換の整合修正（実装済み）

> **出典**: `docs/gpt_reseach/research4.md` の「不確実性区間→確率変換の整合」（優先度: 最優先、概算工数: 3〜7人日）

### 背景と精度向上の見込み

#### 現状のバグ

`src/predictor.py` に **系統的な確率過大推定バグ** が存在する。

```python
# src/predictor.py:72〜78
model = Prophet(
    daily_seasonality=False,
    weekly_seasonality=True,
    yearly_seasonality=True,
    changepoint_prior_scale=0.05,
    # ← interval_width 未指定 → デフォルト 0.80（80% 予測区間）
)

# src/predictor.py:35
sigma = ci_pct / 1.96  # ← 1.96 は 95% CI の z 値
```

| 項目 | 現状 | 問題 |
|------|------|------|
| Prophet の `interval_width` | 未指定（デフォルト 0.80） | 80% 予測区間 → z = **1.28** |
| `compute_prob_up` の z 値 | `1.96`（95% CI 想定） | **ミスマッチ** |
| σ の計算 | `ci_pct / 1.96`（過小） | σ が実際より小さくなる |
| `prob_up` の結果 | `μ / σ` が過大 | **上昇確率が系統的に水増し** |

80% 予測区間の半幅を 95% の z (1.96) で割っているため、σ が約 35% 過小評価され、
`prob_up` が全銘柄で過大になっている。これは確率を意思決定に使う設計では致命的。

#### 修正後の期待効果

- `prob_up` が「正規分布として整合した」真の上昇確率になる
- 過大推定が是正され、閾値フィルタ（例: `prob_up > 0.6`）の意味が正確になる
- Phase 21 の校正処理の前提条件として必須

---

### 修正方針

**方針 A（推奨）**: `interval_width=0.95` を Prophet に明示し、z=1.96 と整合させる

```python
# 修正後
model = Prophet(
    daily_seasonality=False,
    weekly_seasonality=True,
    yearly_seasonality=True,
    changepoint_prior_scale=0.05,
    interval_width=0.95,   # ← 追加: z=1.96 と整合させる
)
```

`compute_prob_up` のコメントは「95% CI の半幅」であることを明記するのみで、
計算ロジックの変更は不要。

**方針 B（代替）**: `interval_width` から z を動的に計算する

```python
from scipy.stats import norm

INTERVAL_WIDTH = 0.80  # Prophet のデフォルト
Z = norm.ppf((1 + INTERVAL_WIDTH) / 2)  # → 1.2816

sigma = ci_pct / Z  # 正確な σ
```

方針 A の方が変更箇所が最小かつ意図が明確なため推奨。

---

### 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| `src/predictor.py` | **修正** | `Prophet()` に `interval_width=0.95` を追加 |
| `src/predictor.py` | **修正** | `compute_prob_up()` のドキュメントに 95% CI 前提を明記 |
| `tests/test_predictor.py` | **修正** | interval_width=0.95 前提のテストケース更新 |

---

### 段階的な実装ステップ

```
Step 1: src/predictor.py の Prophet() に interval_width=0.95 を追加
Step 2: compute_prob_up() のドキュメントコメントを更新
Step 3: テストを更新（期待値が変わるため）
Step 4: python -m src.main を実行し、prob_up の分布が是正されたことをログで確認
        （是正前より prob_up の平均値が下がることを確認）
Step 5: plan.md を 実装済み に更新
```

---

### 受け入れ確認チェック

- [ ] `Prophet(interval_width=0.95)` が明示されている
- [ ] `compute_prob_up(ci_pct=10.0)` 内の σ = 10.0 / 1.96 が意味的に正しい
- [ ] 修正前後で prob_up の平均値が下がる（過大推定の是正を確認）
- [ ] テストが全件パスする

---

## フェーズ21: prob_up 確率校正（Platt scaling / isotonic）実装（Step 0 実装済み）

> **出典**: `docs/gpt_reseach/research4.md` の「確率校正の実装（温度/Platt/isotonic）」（優先度: 最優先、概算工数: 5〜12人日）

### 背景と精度向上の見込み

#### 現状の問題

`src/predictor.py:102` に `"prob_up_calibrated": None,` があり、
**校正処理のプレースホルダが未実装**のまま残っている。

現在の `prob_up` は Prophet の正規分布近似から計算されるが、
正規分布仮定は株価の実態（厚い裾・非対称）と乖離があるため、
**「prob_up=0.70 の銘柄の実際の的中率が 0.55」という状態が常態化し得る**。

`docs/gpt_reseach/research4.md` は次の校正手法を推奨：

| 手法 | 特性 | 必要サンプル |
|------|------|-------------|
| **Platt scaling** | ロジスティック回帰で校正。少サンプルでも安定 | 50〜200件 |
| **Isotonic regression** | ノンパラメトリック。精度高いがサンプル多めに必要 | 200件以上 |
| **Temperature scaling** | ニューラルネット向け（本プロジェクトでは非主力） | — |

現行の Google Sheets は `predictions` シートのみを持ち、`prob_up` は記録されていない。
Phase 21 では先に `predictions` シートへ `prob_up` を追記する改修を行い（Step 0）、
50 件以上の実績が蓄積した後に **Platt scaling から始めるのが現実的**。

#### 実装後の期待効果

- `prob_up_calibrated` フィールドが実データに基づく真の確率になる
- Reliability diagram / ECE（Expected Calibration Error）で品質を可視化
- 「確率0.7なら実際に7割当たる」という意思決定品質を実現

---

### 実装方針

```
校正フロー:

1. 過去実績データを Google Sheets の predictions シートから取得
   → (prob_up, 的中) のペアを収集（的中="的中"→1, "外れ"→0 に変換）
   ※ predictions シートへの prob_up 記録は Step 0 で先行実施（50 件以上蓄積が必要）

2. Platt scaling を fit する
   from sklearn.linear_model import LogisticRegression
   calibrator = LogisticRegression()
   calibrator.fit(prob_up_array.reshape(-1,1), actual_up_array)

3. 新しい prob_up に対して calibrator.predict_proba() を適用
   → prob_up_calibrated を生成

4. 校正品質を評価
   - ECE（Expected Calibration Error）: 校正のズレを定量化
   - Brier score: 確率予測の総合精度
   - Reliability diagram: 信頼度 vs 正解率のグラフ
```

---

### 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| `src/sheets.py` | **修正** | ① HEADERS 末尾（列10）に `prob_up` 追加、② `migrate_headers()` 追加（既存シート移行）、③ `append_predictions()` で `prob_up` を記録（`prob_up_calibrated` は Sheets に保存しない） |
| `src/calibrator.py` | **新規** | Platt scaling / isotonic の fit・transform・保存 |
| `src/predictor.py` | **修正** | `prob_up_calibrated` を校正値で埋める |
| `src/exporter.py` | **修正** | `prob_up_calibrated` を出力 JSON に含める（Sheets 保存なし：毎実行で再計算されるため不要） |
| `tests/test_sheets_tracker.py` | **修正** | `prob_up` 列追加後の `update_cell` 列番号回帰テストを追加 |
| `requirements.txt` | **修正** | `scikit-learn>=1.4.0` のコメントアウトを解除（`# Phase 2` 行を有効化） |
| `data/calibration_model.pkl` | **新規** | fit 済み校正モデルのスナップショット（CI では毎実行時に fit し直す） |
| `tests/test_calibrator.py` | **新規** | 校正ロジックの単体テスト |

> **`calibration_model.pkl` の永続化方針**: CI/本番（`weekly_run.yml`）では `dashboard/data/*.json` のみ commit 対象のため、pkl は毎実行時に `predictions` シートのデータで再 fit する設計を基本とする。pkl はローカルキャッシュ扱い（`.gitignore` 対象にするか、再 fit コストが高い場合のみ Artifacts として保存する）。

---

### 段階的な実装ステップ

```
Step 0a: HEADERS 末尾（9列目「ステータス」の後）に "prob_up" を追加（列10）
         → update_actuals() の update_cell(row, 7/8/9) はそのまま維持（列番号ずれなし）
Step 0b: 既存シートへのヘッダー移行関数 migrate_headers() を src/sheets.py に追加
         → 実装: ws.row_values(1) でヘッダー行を取得し "prob_up" が未存在なら末尾に追記
         → 既存データ行の prob_up 欄は空欄のまま（遡及再計算はしない）
         → prob_up_calibrated 列は追加しない（JSON 出力専用、Sheets スキーマ対象外）
Step 0c: append_predictions() に prob_up 値を渡せるよう引数を追加し記録開始
         ※ 記録が 50 件以上蓄積するまで Step 1 以降は延期
Step 1: predictions シートから (prob_up, 的中) ペアを 50 件以上収集できたことを確認
Step 2: requirements.txt の scikit-learn>=1.4.0 コメントアウトを解除
Step 3: src/calibrator.py を作成し、Platt scaling を実装
Step 4: src/predictor.py の prob_up_calibrated を校正値で埋める
Step 5: Reliability diagram（校正前後）を可視化して ECE 改善を確認
Step 6: src/exporter.py で prob_up_calibrated を出力に含める
Step 7: plan.md を 実装済み に更新
```

---

### 受け入れ確認チェック

- [ ] `prob_up` は HEADERS の末尾（列10）に追加されており、列7〜9（翌週実績価格・的中・ステータス）の `update_cell` が壊れていない
- [ ] `migrate_headers()` が既存シートに `prob_up` 列を追加できる（新規作成シートと同一ヘッダーになる）
- [ ] `append_predictions()` で `prob_up` が記録される（Step 0c）
- [ ] `predictions` シートに最低 50 件の (prob_up, 的中) ペアが蓄積されている
- [ ] `prob_up_calibrated` は出力 JSON（`exporter.py`）に含まれる（Sheets への保存はしない：毎実行で再計算するため）
- [ ] `tests/test_sheets_tracker.py` が `prob_up` 列追加後も列番号更新テストをパスする
- [ ] `requirements.txt` の `scikit-learn>=1.4.0` が有効化されている
- [ ] `prob_up_calibrated` フィールドが `null` でなくなる
- [ ] 校正後の ECE が校正前より低下する
- [ ] Reliability diagram で calibrated が uncalibrated より対角線に近くなる
- [ ] `calibration_model.pkl` が生成・保存される（CI では毎実行 fit し直す設計）
- [ ] テストが全件パスする

---

## フェーズ22: J-Quants V2 APIキー方式への移行（計画中）

> **出典**: `docs/gpt_reseach/research5.md` 「J-Quants API V2 の重要点（実装・運用目線）」

### 背景と必要性

#### 現状の問題

`src/jquants_fetcher.py`（Phase 17 実装）は J-Quants API **V1** を使用している。

```
現在の認証フロー（V1）:
  POST /v1/token/auth_user  (mailaddress + password) → refreshToken
  POST /v1/token/auth_refresh (refreshToken)          → idToken
  GET  /v1/fins/statements   (Bearer idToken)         → 財務データ
```

2025年12月に **J-Quants API V2** が開始され、認証がトークン方式から **APIキー方式（JQUANTS_API_KEY）** に移行した。V1は移行期間として継続提供されるが、廃止予定であることが公式資料で示唆されており、**新規実装は V2 前提が安全**（research5.md より）。

| 項目 | V1（現状） | V2（移行後） |
|------|-----------|------------|
| 認証 | メール + パスワード → トークン2段階 | APIキー直接（シンプル） |
| 環境変数 | `JQUANTS_MAIL_ADDRESS` + `JQUANTS_PASSWORD` | `JQUANTS_API_KEY` |
| ベースURL | `https://api.jquants.com/v1` | `https://api.jquants.com/v2` |
| 列名 | 旧表記 | 最適化（短縮）済み |
| 将来性 | 廃止予定 | **推奨** |

#### 移行後の期待効果

- 認証フローが 2 ステップ → **1 ステップ**に簡略化（コード削減・信頼性向上）
- V1 廃止後も継続稼働（運用リスク排除）
- V2 限定の新機能（CSV一括取得・分足Tick等）への対応準備

---

### 実装方針

#### 方針: V2 優先 → V1 フォールバック（移行期間中）

`JQUANTS_API_KEY` が設定されていれば V2 を使用。
設定なしで `JQUANTS_MAIL_ADDRESS` + `JQUANTS_PASSWORD` が設定されていれば V1 を使用（後方互換）。

```
_get_auth_header() の判定ロジック:
  JQUANTS_API_KEY 設定済み?
    YES → {"Authorization": "Bearer {JQUANTS_API_KEY}"}  (V2)
     NO → _get_id_token() で V1 トークンフロー実行 → {"Authorization": "Bearer {idToken}"}
```

V2 のエンドポイント・列名変更への対応:
- `BASE_URL` を V2 ベースに切り替え（`JQUANTS_API_KEY` の有無で自動判定、config では制御しない）
- 列名マッピング: V2 で短縮された場合も対応（`PBR` → V2 での列名を要確認）

---

### 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| `src/jquants_fetcher.py` | **修正** | V2 APIキー認証を追加、`_get_auth_header()` に認証方式の自動判定を実装 |
| `.env.example` | **修正** | `JQUANTS_API_KEY` を追記（`JQUANTS_MAIL_ADDRESS` / `JQUANTS_PASSWORD` はコメントで非推奨を明示） |
| `tests/test_jquants_fetcher.py` | **修正** | V2 APIキー認証パスのテストを追加 |

---

### 実装詳細

#### `src/jquants_fetcher.py` 変更箇所

```python
BASE_URL_V2 = "https://api.jquants.com/v2"
BASE_URL_V1 = "https://api.jquants.com/v1"


def _get_auth_header() -> dict | None:
    """V2（APIキー）または V1（トークンフロー）の認証ヘッダーを返す。

    V2 優先: JQUANTS_API_KEY が設定されていれば直接 Bearer で使用。
    V1 フォールバック: JQUANTS_MAIL_ADDRESS + JQUANTS_PASSWORD から idToken を取得。
    どちらも未設定 → None を返す（degraded mode）。
    """
    api_key = os.environ.get("JQUANTS_API_KEY")
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}
    # V1 フォールバック（後方互換）
    id_token = _get_id_token()  # 既存の V1 トークンフロー
    if id_token:
        return {"Authorization": f"Bearer {id_token}"}
    return None


def fetch_financial_data(ticker: str) -> dict:
    """ticker の最新四半期財務データを取得する（V2/V1 自動選択）。"""
    if ticker in _financial_cache:
        return _financial_cache[ticker]

    auth_header = _get_auth_header()
    if not auth_header:
        return {}

    base_url = BASE_URL_V2 if os.environ.get("JQUANTS_API_KEY") else BASE_URL_V1
    code = ticker.replace(".T", "").zfill(4) + "0"
    try:
        r = requests.get(
            f"{base_url}/fins/statements",
            params={"code": code},
            headers=auth_header,
            timeout=15,
        )
        r.raise_for_status()
        ...
    except Exception:
        ...
```

---

### 段階的な実装ステップ

```
Step 1: src/jquants_fetcher.py に _get_auth_header() を追加し、V2 APIキー認証を実装
Step 2: fetch_financial_data() を _get_auth_header() 使用に切り替え
Step 3: .env.example に JQUANTS_API_KEY を追記（V1 変数は非推奨コメント付きで残す）
Step 4: tests/test_jquants_fetcher.py に V2 パスのテストを追加
Step 5: JQUANTS_API_KEY をセットして動作確認（JP 銘柄の財務データが取得できること）
Step 6: plan.md を 実装済み に更新
```

---

### 受け入れ確認チェック

- [ ] `JQUANTS_API_KEY` 設定時、V2 エンドポイントで財務データが取得できる
- [ ] `JQUANTS_MAIL_ADDRESS` + `JQUANTS_PASSWORD` 設定時（V1）も引き続き動作する（後方互換）
- [ ] 両方未設定の場合、従来どおり `{}` を返す（degraded mode）
- [ ] V2 で列名が変更されていても正しくマッピングされる
- [ ] テストが全件パスする（V2・V1 それぞれのモックテスト）

---

## フェーズ23: 流動性フィルタ強化（min_avg_dollar_volume_us / _jp）（計画中）

> **出典**: `docs/gpt_reseach/research5.md` 「追加設定として有効なもの（機能面）」流動性フィルタ

### 背景と精度向上の見込み

#### 現状の問題

`src/screener.py` の `screen()` 関数は `min_market_cap` フィルタのみを持つ。

```python
# 現状（screener.py:240〜256）
min_market_cap = screening_cfg.get("min_market_cap", 0)
if min_market_cap > 0:
    # 時価総額が閾値未満の銘柄を除外
    ...
```

**時価総額が大きくても、出来高が薄い銘柄が通過する**ケースが存在する。

| 問題 | 結果 |
|------|------|
| 時価総額は大きいが出来高が少ない銘柄 | スプレッドが広く実際には売買困難 |
| 出来高の急変（一時的なスパイク）| 価格が大きく飛び、予測外れの要因になる |
| 日本株の流動性の低い銘柄 | JP 銘柄で特に問題（日次出来高が薄い） |

**平均出来高×価格（Average Daily Dollar Volume = ADDV）** フィルタを追加することで、**実際に売買可能な流動性のある銘柄のみをスクリーニング対象にできる**。

---

### 実装方針

#### 方針: 時価総額フィルタの後に ADDV フィルタを追加する

`fetch_stock_data()` で取得済みの OHLCV データから `avg(Volume × Close)` を計算し、閾値未満の銘柄を除外する。

```
ADDV = mean(daily Volume × daily Close price) over lookback period
```

- US 株: `min_avg_dollar_volume_us`（ドル建て、例: $1,000,000 /日 = 100万ドル/日）
- JP 株: `min_avg_dollar_volume_jp`（円建て、例: ¥500,000,000 /日 = 5億円/日）
- ティッカーが `.T` で終わる場合は JP 閾値を使用し、それ以外は US 閾値を使用する

```
screen() の流れ（Phase 23 後）:
  ① 時価総額フィルタ（既存: min_market_cap）
  ② 流動性フィルタ（新規: US/JP 通貨別 ADDV フィルタ）
     is_jp = ticker.endswith(".T")
     threshold = min_avg_dollar_volume_jp if is_jp else min_avg_dollar_volume_us
     ADDV = stock_data[ticker]["Volume"].mean() × stock_data[ticker]["Close"].mean()
     ADDV < threshold → 除外
  ③ テクニカル指標算出 + スコアリング
```

OHLCV データは `fetch_stock_data()` で既に取得済みのため、**追加 API コールなし**でフィルタ適用できる。

---

### 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| `src/screener.py` | **修正** | `screen()` 内に US/JP 別 ADDV フィルタを追加 |
| `config.yaml` | **修正** | `screening.min_avg_dollar_volume_us` / `screening.min_avg_dollar_volume_jp` を追加 |
| `tests/test_screener.py` | **修正** | ADDV フィルタの単体テストを追加（US・JP それぞれ） |

---

### 実装詳細

#### `config.yaml` 追加設定

```yaml
screening:
  markets:
    - "sp500"
    - "nasdaq100"
    - "nikkei225"
  top_n: 10
  min_market_cap: 10_000_000_000
  min_avg_dollar_volume_us: 1_000_000    # Phase 23: US株 日次平均売買代金の下限（ドル建て、0で無効化）
  min_avg_dollar_volume_jp: 500_000_000  # Phase 23: JP株 日次平均売買代金の下限（円建て、0で無効化）
  lookback_days: 30
  weights:
    ...
```

> **設定値の目安**:
> - US 株 (`min_avg_dollar_volume_us`): `1_000_000`（100万ドル/日）
> - JP 株 (`min_avg_dollar_volume_jp`): `500_000_000`（5億円/日）
> - どちらも `0` に設定するとフィルタ無効（従来動作）

#### `src/screener.py` 変更箇所

```python
# 時価総額フィルタの直後に追加
min_addv_us = screening_cfg.get("min_avg_dollar_volume_us", 0)
min_addv_jp = screening_cfg.get("min_avg_dollar_volume_jp", 0)
if min_addv_us > 0 or min_addv_jp > 0:
    before = len(stock_data)
    for ticker in list(stock_data.keys()):
        is_jp = ticker.endswith(".T")
        threshold = min_addv_jp if is_jp else min_addv_us
        if threshold <= 0:
            continue
        df = stock_data[ticker]
        # 日次売買代金の平均: Volume × Close の平均
        close = df["Close"].squeeze()
        volume = df["Volume"].squeeze()
        addv = float((volume * close).mean())
        if addv < threshold:
            stock_data.pop(ticker, None)
    logger.info(
        "流動性フィルタ後: %d → %d 銘柄 (ADDV 閾値未満を除外)",
        before, len(stock_data),
    )
```

---

### 段階的な実装ステップ

```
Step 1: config.yaml に min_avg_dollar_volume_us: 1_000_000 / min_avg_dollar_volume_jp: 500_000_000 を追加
Step 2: src/screener.py の screen() に US/JP 別 ADDV フィルタブロックを追加
Step 3: tests/test_screener.py にフィルタのテストを追加
        （US 閾値で US 株を除外、JP 閾値で JP 株を除外、閾値 0 では無効化されること）
Step 4: python -m src.main を実行し、流動性の低い銘柄が除外されることをログで確認
Step 5: plan.md を 実装済み に更新
```

---

### 受け入れ確認チェック

- [ ] `min_avg_dollar_volume_us: 0` かつ `min_avg_dollar_volume_jp: 0` で従来動作（フィルタ無効）
- [ ] US 株は `min_avg_dollar_volume_us` 閾値で除外される
- [ ] JP 株（`.T` 末尾）は `min_avg_dollar_volume_jp` 閾値で除外される
- [ ] OHLCV データが取得済みのため、追加 API コールが発生しない
- [ ] テストが全件パスする（US / JP それぞれのケースをモックで検証）

---

## フェーズ24: 決算禁則フィルタ（J-Quants 決算カレンダー連携）（計画中）

> **出典**: `docs/gpt_reseach/research5.md` 「追加設定として有効なもの（機能面）」イベント禁則

### 背景と精度向上の見込み

#### 現状の問題

決算発表（Earnings Announcement）は、事前予測が困難な **株価の大幅変動イベント**である。

| 現状 | 問題 |
|------|------|
| 決算日前後の銘柄がスクリーニングで選出される | 予測精度の低下：決算後に方向が大きく変わる |
| JP 株の決算カレンダーを利用していない | J-Quants が無料で決算発表予定を提供しているのに未利用 |

**「予測日から N 日以内に決算発表がある JP 銘柄」を除外**することで：
- 予測の方向性が決算発表で覆される銘柄を事前に除外
- `prob_up` の期待校正精度が向上（ノイズイベントを回避）

> **対象: JP 株のみ（Phase 1）**
> US 株の決算カレンダーは別途 API（yfinance の `calendar` / Finnhub の `earnings` 等）が必要。
> Phase 24 では J-Quants を持つ JP 株から開始し、US 株は次フェーズで検討する。

---

### 実装方針

#### 方針: J-Quants 決算カレンダーを取得し、enricher でフィルタを適用する

```
JP ticker enrichment フロー（Phase 24 後）:

screen() → [JP銘柄リスト]
  │
  └─ enricher.enrich() 内で決算禁則チェック:
       for ticker in jp_tickers:
         days_to_earnings = _fetch_days_to_earnings(ticker)
         if days_to_earnings is not None and days_to_earnings <= exclude_threshold:
             enrichment[(date, ticker)]["earnings_warning"] = {
                 "days_to_earnings": days_to_earnings,
                 "exclude": True,
             }
```

J-Quants の決算カレンダーエンドポイント（`/fins/announcement`）から
対象銘柄の次回決算発表日を取得し、今日からの日数を算出する。

---

### 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| `src/jquants_fetcher.py` | **修正** | `fetch_earnings_calendar(ticker)` 関数を追加 |
| `src/enricher.py` | **修正** | `_fetch_earnings_warning()` 追加、`enrich()` で JP 銘柄に適用 |
| `src/exporter.py` | **修正** | `earnings_warning` フィールドを出力 JSON に含める |
| `config.yaml` | **修正** | `screening.exclude_days_to_earnings` を追加 |
| `tests/test_jquants_fetcher.py` | **修正** | `fetch_earnings_calendar` のモックテストを追加 |

---

### 実装詳細

#### `src/jquants_fetcher.py` 追加関数

```python
_earnings_cache: dict[str, dict | None] = {}


def fetch_earnings_calendar(ticker: str) -> dict | None:
    """ticker（例: "7203.T"）の次回決算発表予定を取得する。

    Returns:
        {"announcement_date": "2026-05-10", "days_to_earnings": 78} or None（未取得・エラー）
    """
    if ticker in _earnings_cache:
        return _earnings_cache[ticker]

    auth_header = _get_auth_header()
    if not auth_header:
        _earnings_cache[ticker] = None
        return None

    base_url = BASE_URL_V2 if os.environ.get("JQUANTS_API_KEY") else BASE_URL_V1
    code = ticker.replace(".T", "").zfill(4) + "0"
    try:
        r = requests.get(
            f"{base_url}/fins/announcement",
            params={"code": code},
            headers=auth_header,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json().get("announcement", [])
        if not data:
            _earnings_cache[ticker] = None
            return None

        # 最も近い未来の決算日を取得
        today = datetime.now().date()
        future = [
            d for d in data
            if d.get("Date") and datetime.strptime(d["Date"], "%Y-%m-%d").date() >= today
        ]
        if not future:
            _earnings_cache[ticker] = None
            return None

        next_date = min(future, key=lambda d: d["Date"])
        days = (datetime.strptime(next_date["Date"], "%Y-%m-%d").date() - today).days
        result = {"announcement_date": next_date["Date"], "days_to_earnings": days}
        _earnings_cache[ticker] = result
        return result
    except Exception:
        logger.warning("J-Quants 決算カレンダー取得失敗: %s", ticker)
        _earnings_cache[ticker] = None
        return None
```

#### `config.yaml` 追加設定

```yaml
screening:
  exclude_days_to_earnings: 5  # Phase 24: 決算発表 N 日前の JP 銘柄を警告（0で無効化）
```

> **設定値の考え方**:
> `5`: 5営業日以内（翌週の予測期間内）に決算があれば警告・除外候補
> `0`: 無効化（従来動作）
> 警告フラグ（`earnings_warning.exclude: true`）のみ付けて最終判断はユーザーに委ねる設計も可。

#### `src/enricher.py` 追加関数

```python
def _fetch_earnings_warning(ticker: str, config: dict | None = None) -> dict | None:
    """JP 銘柄の決算禁則警告を取得する。

    決算発表が exclude_days_to_earnings 日以内なら警告情報を返す。
    JP 株以外・設定なし・API 未設定 → None。
    """
    if not is_jp_ticker(ticker):
        return None
    if config is None:
        return None
    threshold = config.get("screening", {}).get("exclude_days_to_earnings", 0)
    if threshold <= 0:
        return None

    from src.jquants_fetcher import fetch_earnings_calendar
    cal = fetch_earnings_calendar(ticker)
    if cal is None:
        return None

    days = cal["days_to_earnings"]
    return {
        "announcement_date": cal["announcement_date"],
        "days_to_earnings": days,
        "exclude": days <= threshold,  # True: 除外推奨
    }
```

---

### 段階的な実装ステップ

```
Step 1: src/jquants_fetcher.py に fetch_earnings_calendar() を追加
        → Phase 22 の _get_auth_header() を先に実装しておくこと
Step 2: config.yaml に screening.exclude_days_to_earnings: 5 を追加
Step 3: src/enricher.py に _fetch_earnings_warning() を追加し、enrich() 内で JP 銘柄に適用
Step 4: src/exporter.py で earnings_warning フィールドを出力 JSON に含める
Step 5: tests/test_jquants_fetcher.py に fetch_earnings_calendar のテストを追加
Step 6: JP 銘柄を対象に python -m src.main を実行し、
        決算が近い銘柄に earnings_warning が付与されることを確認
Step 7: plan.md を 実装済み に更新
```

> **前提条件**: Phase 22（J-Quants V2 移行）を先に完了させること（`_get_auth_header()` が必要）。

---

### 受け入れ確認チェック

- [ ] `exclude_days_to_earnings: 0` では決算フィルタが無効（従来動作）
- [ ] 決算 N 日以内の JP 銘柄に `earnings_warning.exclude: true` が付与される
- [ ] 決算が遠い JP 銘柄や US 銘柄には `earnings_warning` が `null` になる
- [ ] J-Quants APIキー未設定時でも処理が継続する（try/except）
- [ ] テストが全件パスする（モック使用）

---

## フェーズ25: Prophet 設定の config 露出（計画中）

> **出典**: `docs/gpt_reseach/research5.md` 「追加するとよい設定項目」Prophet設定

### 背景と精度向上の見込み

#### 現状の問題

`src/predictor.py` の Prophet パラメータが **ハードコード**されている。

```python
# 現状（Phase 20 で interval_width=0.95 を追加済み）
model = Prophet(
    daily_seasonality=False,
    weekly_seasonality=True,
    yearly_seasonality=True,
    changepoint_prior_scale=0.05,
    interval_width=0.95,
)
```

| パラメータ | 現状 | 問題 |
|-----------|------|------|
| `interval_width` | 0.95（ハードコード） | config から変更できない |
| `changepoint_prior_scale` | 0.05（ハードコード） | トレンドの強さを調整できない |
| `uncertainty_samples` | デフォルト（1000） | 精度 vs 速度のトレードオフを設定できない |

`interval_width` は Phase 20 で `prob_up` 計算と整合させたため**変更は慎重に**行う必要があるが、
`config.yaml` 経由で制御可能にしておくことで、将来の実験・チューニングが容易になる。

---

### 実装方針

#### 方針: config.yaml に `prophet:` セクションを追加し、predictor.py で読み込む

```yaml
# config.yaml に追加（Phase 25）
prophet:
  interval_width: 0.95               # 95% 予測区間（z=1.96、prob_up 計算と整合）
  changepoint_prior_scale: 0.05      # トレンド変化点の柔軟性（大きいほど過学習しやすい）
  uncertainty_samples: 1000          # 不確実性推定のサンプル数（多いほど精度高・遅い）
```

```python
# src/predictor.py での読み込み
prophet_cfg = config.get("prophet", {})
model = Prophet(
    daily_seasonality=False,
    weekly_seasonality=True,
    yearly_seasonality=True,
    changepoint_prior_scale=prophet_cfg.get("changepoint_prior_scale", 0.05),
    interval_width=prophet_cfg.get("interval_width", 0.95),
    uncertainty_samples=prophet_cfg.get("uncertainty_samples", 1000),
)
```

> **重要**: `interval_width` のデフォルトは **必ず 0.95** に設定すること。
> Phase 20 で `compute_prob_up()` の `sigma = ci_pct / 1.96` と整合させており、
> `interval_width` を 0.95 以外に変更すると `prob_up` が系統的にずれる。
> config で `interval_width` を変更する場合は、`compute_prob_up()` の z 値も合わせて変更が必要。

---

### 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| `config.yaml` | **修正** | `prophet:` セクションを追加（interval_width / changepoint_prior_scale / uncertainty_samples） |
| `src/predictor.py` | **修正** | `predict()` 内で config から Prophet パラメータを読み込む |
| `tests/test_predictor.py` | **修正** | config 経由でパラメータが渡されることのテストを追加 |

---

### 実装詳細

#### `config.yaml` 追加セクション

```yaml
# フェーズ25: Prophet 設定（予測モデルのパラメータ）
prophet:
  interval_width: 0.95           # ⚠️ 変更する場合は compute_prob_up の z 値も要修正
  changepoint_prior_scale: 0.05  # トレンド変化点の感度（0.001〜0.5）
  uncertainty_samples: 1000      # 確率予測のサンプル数（精度 vs 速度）
```

#### `src/predictor.py` 変更箇所

```python
# 変更前
model = Prophet(
    daily_seasonality=False,
    weekly_seasonality=True,
    yearly_seasonality=True,
    changepoint_prior_scale=0.05,
    interval_width=0.95,
)

# 変更後
prophet_cfg = config.get("prophet", {})
interval_width = prophet_cfg.get("interval_width", 0.95)
model = Prophet(
    daily_seasonality=False,
    weekly_seasonality=True,
    yearly_seasonality=True,
    changepoint_prior_scale=prophet_cfg.get("changepoint_prior_scale", 0.05),
    interval_width=interval_width,
    uncertainty_samples=int(prophet_cfg.get("uncertainty_samples", 1000)),
)
```

> **`predict_stock()` への受け渡し**: `predict()` は既に `config: dict | None = None` を引数に持ち、
> `predict()` が `predict_stock()` を呼ぶ際に prophet 設定を渡す必要がある。
> `predict_stock()` に `prophet_cfg: dict` 引数を追加し、`predict()` 側から渡すこと。

---

### 段階的な実装ステップ

```
Step 1: config.yaml に prophet: セクションを追加
Step 2: src/predictor.py の predict_stock() に prophet_cfg 引数を追加し Prophet 初期化に適用。
        predict() → predict_stock() 呼び出し時に prophet_cfg を渡すよう修正
Step 3: interval_width の扱いを確認:
        compute_prob_up() の z 値（1.96）と整合していることをコメントで明記
Step 4: tests/test_predictor.py に prophet config 読み込みのテストを追加
Step 5: python -m src.main を実行し、config の値が Prophet に渡されることをログで確認
Step 6: plan.md を 実装済み に更新
```

---

### 受け入れ確認チェック

- [ ] `config.yaml` の `prophet.interval_width` が Prophet に反映される
- [ ] `prophet:` セクションが未設定の場合、デフォルト値（interval_width=0.95 等）で動作する
- [ ] `interval_width: 0.95` がデフォルトであり、prob_up 計算と整合している旨がコメントで明記されている
- [ ] `changepoint_prior_scale` / `uncertainty_samples` も config から変更できる
- [ ] テストが全件パスする
