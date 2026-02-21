# 運用レビュー修正点（GitHub Actions / Cloudflare Pages）

作成日: 2026-02-22
対象: `.github/workflows/weekly_run.yml` / `src/exporter.py` / `dashboard/`

---

## 1. GitHub Actions: 3つのAPIキーが workflow env に未設定

### 問題
`config.yaml` で `enabled: true` に設定されている 3 サービスが、
`.github/workflows/weekly_run.yml` の "Run stock analysis" ステップの `env` に含まれていない。

| 環境変数 | config.yaml | workflow env |
|---|---|---|
| `JQUANTS_API_KEY` | `jquants.enabled: true` | **未設定** |
| `FINNHUB_API_KEY` | `finnhub.enabled: true` | **未設定** |
| `FMP_API_KEY` | `fmp.enabled: true` | **未設定** |

各フェッチャーは `os.environ.get()` で取得し、未設定時は `{}` を返す graceful degradation
実装のためエラーにはならない。しかし **JP 株の PBR/ROE 補完・US 株センチメント・FMP
フォールバックが毎週 CI 実行時に必ず無効化される**状態となっており、設定と実態が乖離している。

### 修正方針
`weekly_run.yml` の "Run stock analysis" ステップに 3 変数を追加する。

```yaml
- name: Run stock analysis
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    GOOGLE_CREDENTIALS_JSON: ${{ secrets.GOOGLE_CREDENTIALS_JSON }}
    SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
    LINE_CHANNEL_ACCESS_TOKEN: ${{ secrets.LINE_CHANNEL_ACCESS_TOKEN }}
    LINE_USER_ID: ${{ secrets.LINE_USER_ID }}
    JQUANTS_API_KEY: ${{ secrets.JQUANTS_API_KEY }}      # 追加
    FINNHUB_API_KEY: ${{ secrets.FINNHUB_API_KEY }}      # 追加
    FMP_API_KEY: ${{ secrets.FMP_API_KEY }}              # 追加
  run: python -m src.main
```

GitHub リポジトリ Settings → Secrets and variables → Actions に対応するシークレットを登録すること。

### 変更対象
- `.github/workflows/weekly_run.yml`

---

## 2. Cloudflare Pages: JSON ファイルがキャッシュされて古いデータが表示される

### 問題
`dashboard/js/app.js:30` の `fetch()` はキャッシュバスティングなし:

```js
const resp = await fetch(DATA_BASE + filename);
```

かつ `dashboard/_headers` ファイルが存在しないため、Cloudflare CDN がデフォルト挙動で
JSON ファイルをキャッシュする可能性がある。GitHub Actions で毎週 JSON を更新・push しても、
**ユーザーのブラウザには Cloudflare にキャッシュされた古いデータが届く恐れがある**。

### 修正方針
`dashboard/_headers` を作成し、データ JSON に `Cache-Control: no-store` を付与する。

```
# Cloudflare Pages _headers
# データJSON は常に最新を配信する
/data/*
  Cache-Control: no-store, must-revalidate

# 静的アセット（JS/CSS）は長期キャッシュ
/js/*
  Cache-Control: public, max-age=3600
/css/*
  Cache-Control: public, max-age=3600
```

### 変更対象
- `dashboard/_headers`（新規作成）

---

## 3. exporter.py: Drive quota 超過を「成功」として返す

### 問題
`src/exporter.py:584-588` で Google Drive 保存容量超過エラーを `return True` で処理している。

```python
if _is_drive_quota_exceeded_error(exc):
    logger.warning("Google Drive の保存容量超過のため、今回のエクスポートをスキップします。")
    return True   # ← 失敗なのに True を返す
```

ダッシュボード更新が実質スキップされているのに呼び出し元が成功と判断する。
`continue-on-error: true` と組み合わさり、障害が完全に隠蔽される。

### 修正方針
quota 超過は「正常スキップ」ではなく「要注意の異常」として `False` を返し、
呼び出し元が `export_ok == False` として Slack 等で検知できるようにする。

```python
if _is_drive_quota_exceeded_error(exc):
    logger.error(
        "Google Drive の保存容量超過のため、今回のエクスポートをスキップします。"
        " Drive の空き容量を確認してください。"
    )
    return False   # False に変更
```

### 変更対象
- `src/exporter.py`（`_is_drive_quota_exceeded_error` を呼び出している箇所）

---

## 4. GitHub Actions タイムアウト 30 分が tight

### 問題
`timeout-minutes: 30` の中に下記が収まらない可能性がある。

- `pip install -r requirements.txt`（Prophet のビルドで 3〜5 分）
- Prophet 予測 × 最大 10 銘柄（`uncertainty_samples: 1000`、1 銘柄あたり数十秒）
- JQUANTS / Finnhub / FMP / FRED API 呼び出し（各 10 秒 timeout × リトライ）
- Google Sheets 読み書き

実測では 25〜35 分かかるケースがあり、timeout に引っかかると**データが中途半端な状態で
コミットされる**恐れがある。

### 修正方針
`timeout-minutes` を 60 に引き上げる。

```yaml
jobs:
  analyze:
    runs-on: ubuntu-latest
    timeout-minutes: 60   # 30 → 60
```

### 変更対象
- `.github/workflows/weekly_run.yml`

---

## 5. walkforward.json がダッシュボード JS から参照されていない

### 問題
`src/exporter.py` が `dashboard/data/walkforward.json` を生成し、
`git add dashboard/data/*.json` でリポジトリにコミットされる。
しかし `dashboard/js/` 配下のいずれのファイルも `walkforward.json` を `fetch` しておらず、
データが蓄積されるだけで**画面上に表示されない**。

### 修正方針
ウォークフォワード結果表示用の UI を実装するか、
対応するまでの間は `src/exporter.py` の walkforward 出力処理にコメントで未参照を明記する。

```python
# TODO: walkforward.json は dashboard JS 未参照。Phase 1 ダッシュボード対応時に表示を実装する
```

### 変更対象
- `src/exporter.py`（暫定コメント追加）または `dashboard/js/`（UI 実装）

---

## 実施順（推奨）

1. **修正点 1**（APIキー workflow 追加） — 設定と実態の乖離を即時解消
2. **修正点 2**（`_headers` 新規作成） — Cloudflare キャッシュ問題を解消
3. **修正点 3**（Drive quota を `False` で返す） — 障害の隠蔽を防ぐ
4. **修正点 4**（タイムアウト引き上げ） — CI 安定性向上
5. **修正点 5**（walkforward.json 参照） — Phase 1 ダッシュボード対応時に実施

---

## 受け入れ確認

- GitHub Actions の "Run stock analysis" ログに J-Quants / Finnhub / FMP の fetcher が
  「degraded mode」ではなく正常取得のログを出力している。
- Cloudflare Pages の Network タブで `data/*.json` の Response Header に
  `Cache-Control: no-store` が含まれている。
- Google Drive 容量超過時に `export_ok == False` → `main.py` が warning ログを出す。
- 週次 CI が 60 分以内に完了している。
