# Weekly Stock Analysis（GitHub Actions）失敗原因と修正まとめ

## 背景
- GitHub Actions の `schedule` は **UTC 基準**です。
- 設定 `cron: '0 0 * * 0'` は **毎週日曜 00:00 UTC（= 日曜 09:00 JST）** にワークフローが開始されます。
- ただし、今回 Slack に通知が来ていなかった主因は **ワークフローが途中で失敗して終了していた**ことです。

---

## 1. 失敗していたポイント（ログから）
### 1) pytest が無い
- `Run tests` ステップで `No module named pytest` → exit code 1
- 結果：後続（分析・通知）が止まる / スキップされる

### 2) `predictions.json` の形式不一致で `KeyError: 0`
- `tests/test_exporter.py` で `predictions[0]` を参照した時に `KeyError: 0`
- 原因：`predictions` が **list ではなく dict** になっている可能性が高い

### 3) config に `screening` が無く `KeyError: 'screening'`
- `src/enricher.py` の `config["screening"]["lookback_days"]` が KeyError
- 原因：テストや最小構成の config で `screening` が省略されるケースを想定していない

### 4) zero std（標準偏差ゼロ）時に巨大値が出てテスト失敗
- `tests/test_baseline.py::test_portfolio_stats_zero_std`
- 期待：std が 0 のときは `None`
- 実際：ほぼ 0 で割った結果 `3.94e+16` のような巨大値

---

## 2. 修正方針（結論）
### 優先度 High（まずここでCIを通す）
1. **pytest を確実にインストール**
2. `predictions.json` を **list[dict]** で出力するよう統一
3. `config["screening"]` が無い場合でも落ちないよう **デフォルト値**を入れる
4. std が 0（または極小）なら **None を返す**（比率系の計算）

### 優先度 Medium（運用を安定させる）
5. **Slack 通知を常に飛ばす / 失敗時だけ飛ばす**のどちらかに揃える  
   - workflow 側で最終ステップを `if: always()` または `if: failure()` にする

---

## 3. GitHub Actions workflow の修正版（そのまま差し替え可）
> **ポイント**  
> - `pytest` を明示的にインストール  
> - `secrets` は `if:` の式で直接参照しない（job の `env:` に移して `env.` で参照）  
> - Slack 通知は「失敗しても必ず」送る（必要なら failure のみに変更）

```yml
name: Weekly Stock Analysis

on:
  schedule:
    - cron: '0 0 * * 0'  # 毎週日曜 UTC 00:00 (JST 09:00)
  workflow_dispatch:

concurrency:
  group: ${{ github.workflow }}
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  analyze:
    runs-on: ubuntu-latest
    timeout-minutes: 60

    # secrets は if 式で直接参照できないため env に移す
    env:
      SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -r requirements.txt
          # テスト依存が requirements に無いケースに備える
          python -m pip install pytest

      - name: Run tests
        run: python -m pytest tests/ -q

      - name: Run stock analysis
        env:
          GOOGLE_CREDENTIALS_JSON: ${{ secrets.GOOGLE_CREDENTIALS_JSON }}
          LINE_CHANNEL_ACCESS_TOKEN: ${{ secrets.LINE_CHANNEL_ACCESS_TOKEN }}
          LINE_USER_ID: ${{ secrets.LINE_USER_ID }}
          JQUANTS_API_KEY: ${{ secrets.JQUANTS_API_KEY }}
          FINNHUB_API_KEY: ${{ secrets.FINNHUB_API_KEY }}
          FMP_API_KEY: ${{ secrets.FMP_API_KEY }}
          FRED_API_KEY: ${{ secrets.FRED_API_KEY }}
        run: python -m src.main

      - name: Commit and push dashboard data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

          git add dashboard/data/
          git diff --staged --quiet || git commit -m "chore: update dashboard data [skip ci]"

          git pull --rebase origin "${{ github.ref_name }}"
          git push

      - name: Notify Slack (always)
        if: always() && env.SLACK_WEBHOOK_URL != ''
        run: |
          curl -sS -X POST -H 'Content-type: application/json'             --data "{\"text\":\"Weekly Stock Analysis: ${{ job.status }}\\nref=${{ github.ref_name }}\\nrun=https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }}\"}"             "${SLACK_WEBHOOK_URL}"
```

- 「失敗時だけ通知」にしたい場合は、最後の `if:` を以下に変更  
  - `if: failure() && env.SLACK_WEBHOOK_URL != ''`

---

## 4. アプリ側の修正（テストが期待する形に合わせる）

### 4-1) `predictions.json` を list に統一（`KeyError: 0` 対策）
**症状**
- `predictions[0]` が KeyError → dict 形式で出ている

**対応**
- export 前に **必ず list[dict] に正規化**してから保存する
- dict の場合は `{"predictions":[...]}` と `{ "AAPL": {...} }` の両方を吸収する

サンプル（export 直前の正規化関数）：

```python
def _normalize_predictions_for_export(predictions_obj):
    # predictions.json を list[dict] にそろえる

    normalized = []

    if isinstance(predictions_obj, list):
        normalized = predictions_obj

    elif isinstance(predictions_obj, dict):
        if "predictions" in predictions_obj:
            inner = predictions_obj.get("predictions")
            if isinstance(inner, list):
                normalized = inner
            else:
                normalized = []
        else:
            # ticker をキーにした dict を list に変換（順序を安定化）
            tickers = list(predictions_obj.keys())
            tickers.sort()

            for ticker in tickers:
                value = predictions_obj.get(ticker)
                if isinstance(value, dict):
                    item = dict(value)
                    if "ticker" not in item:
                        item["ticker"] = ticker
                    normalized.append(item)
                else:
                    normalized.append(
                        {
                            "ticker": ticker,
                            "value": value,
                        }
                    )
    else:
        normalized = []

    return normalized
```

---

### 4-2) `config["screening"]` が無いとき落とさない（`KeyError: 'screening'` 対策）
**症状**
- `config["screening"]["lookback_days"]` で KeyError

**対応**
- `config.get("screening", {})` で安全に取得し、無ければデフォルト値

```python
def compute_explanations(ticker, df, config):
    # screening が無いケースでも落ちないようにする

    screening_cfg = {}
    if isinstance(config, dict):
        screening_cfg = config.get("screening", {})

    # 例: 252 = 営業日ベースで約1年
    lookback_days = screening_cfg.get("lookback_days", 252)

    # 以降は lookback_days を使って処理する
```

---

### 4-3) std が 0（極小）なら None を返す（巨大値を防ぐ）
**症状**
- std ほぼ 0 で割って巨大値 → テストは None を期待

**対応**
- 分母が 0 / 極小なら None

```python
def _safe_ratio(numerator, denominator):
    eps = 1e-12

    if denominator is None:
        return None

    if abs(denominator) < eps:
        return None

    return numerator / denominator
```

---

## 5. 次にやること（最短手順）
1. workflow を修正版に差し替え（pytest + Slack always）
2. `predictions.json` の形式を list に統一（export 前に正規化）
3. `screening` をデフォルト対応
4. ratio 系の 0除算/極小値対応（None 返却）
5. Actions で再実行してテストが通ることを確認

---

## 参考メモ
- 「9時に通知が来ない」問題は、**9時に開始しても途中で失敗**すれば通知が来ない/到達しないことがある
- 最終ステップ通知（always/failure）を入れると、失敗時も Slack で把握しやすい
