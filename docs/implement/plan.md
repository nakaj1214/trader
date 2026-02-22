# Weekly Stock Analysis CI 失敗修正

`docs/error/weekly_stock_analysis_fixes.md` に記録された 4 つの失敗原因をコードに適用する。

## 各問題と現状の確認

| # | 問題 | 調査結果 |
|---|------|---------|
| 1 | `pytest` が無い | `weekly_run.yml` の Install ステップが `pip install -r requirements.txt` のみ |
| 2 | `predictions[0]` → KeyError | `test_export_integration` (l.356–357) が `predictions.json` を直接 `predictions[0]` で参照、かつ現行の `export()` は `{"meta...", "predictions": [...]}` 形式で書き出している → テストの `predictions` 変数が dict になるため `[0]` で KeyError |
| 3 | `config["screening"]` KeyError | `enricher.py` l.394: `lookback = config["screening"]["lookback_days"]` がキーの存在を前提としている |
| 4 | std=0 で巨大値 | `baseline.py` l.44: `sharpe = ... if std > 0 else None` — コードは **既に** `None` を返す実装になっている。ただし浮動小数精度の問題で失敗するケースを eps ガードで補強 |

> [!NOTE]
> `test_export_integration` の `predictions[0]` については、テスト自体が `predictions.json` の **トップレベルを list と仮定** している。現行コードは `{"predictions": [...]}` dict 形式で書き出すため、テストは `predictions["predictions"][0]` と書くべき。**テスト側を修正する**（本番コードの JSON 形式を崩さない方針）。

## Proposed Changes

---

### GitHub Actions Workflow

#### [MODIFY] `.github/workflows/weekly_run.yml`

- `Install dependencies` ステップに `python -m pip install pytest` を追加
- `Slack 通知 (always)` ステップを追加（`job env:` に `SLACK_WEBHOOK_URL` を移動）
- `git pull` コマンドのブランチ名をクォートで修正

---

### src/enricher.py

#### [MODIFY] `src/enricher.py`

- `compute_explanations()` (l.394) の `config["screening"]["lookback_days"]` を
  `config.get("screening", {}).get("lookback_days", 252)` に変更
- 同関数 l.413 の `config["screening"].get("weights", {})` も
  `config.get("screening", {}).get("weights", {})` に変更

---

### src/baseline.py

#### [MODIFY] `src/baseline.py`

- `_portfolio_stats()` (l.44) の Sharpe 計算を eps ガードに変更:
  ```python
  eps = 1e-12
  sharpe = round(float((returns.mean() / std) * (52 ** 0.5)), 2) if std > eps else None
  ```

---

### tests/test_enricher.py

#### [ADD] `tests/test_enricher.py`

- `compute_explanations()` に `screening` キーを持たない config を渡しても `KeyError` が発生しないことを確認するテストを追加する。
  対象ケース:
  - `config={}` （全キー欠落）
  - `config={"sizing": {...}}` （`screening` のみ欠落）

  ```python
  def test_compute_explanations_no_screening_key():
      """screening キーなし config で KeyError が出ないことを確認"""
      from src.enricher import compute_explanations
      df = _make_price_df(list(range(100, 400)))  # 300 日分
      # config={} (全キー欠落) でも KeyError が起きないことを確認
      result = compute_explanations("AAPL", df, {})
      assert result is not None
      # config に screening のみ欠落でも同様
      result2 = compute_explanations("AAPL", df, {"sizing": {}})
      assert result2 is not None
  ```

---

### tests/test_exporter.py

#### [MODIFY] `tests/test_exporter.py`

- `test_export_integration` の `predictions.json` 読み込み後の検証部分を修正。

  現行:
  ```python
  predictions = json.loads(...)
  assert len(predictions) == 3
  assert predictions[0]["ticker"] == "AAPL"
  ```
  修正後:
  ```python
  raw = json.loads(...)
  predictions = raw["predictions"]   # dict 形式 → predictions キーを取り出す
  assert len(predictions) == 3
  assert predictions[0]["ticker"] == "AAPL"
  ```

---

## Verification Plan

### Automated Tests

```powershell
python -m pytest tests/test_baseline.py tests/test_exporter.py tests/test_enricher.py -v
```

- `test_baseline.py::test_portfolio_stats_zero_std` → Sharpe が `None` になることを確認
- `test_exporter.py::test_export_integration` → `predictions[0]["ticker"] == "AAPL"` が通ることを確認
- `test_enricher.py::test_compute_explanations_no_screening_key` → `screening` キーなし config（`{}` および `{"sizing": {...}}`）で `KeyError` が出ないことを確認

### Workflow YAML 構文チェック

```powershell
# actionlint がインストール済みの場合（優先）
actionlint .github/workflows/weekly_run.yml

# actionlint 未インストールの場合（フォールバック）
python -c "import yaml; yaml.safe_load(open('.github/workflows/weekly_run.yml'))"
```

- YAML 構文ミスや `if` 条件式の誤りを push 前に検知する。
- 上記 2 つがローカル検証の手段。`gh workflow view weekly_run.yml` は GitHub 上の workflow 情報参照用であり、ローカルの未 push 変更の検証にはならないため使用しない。

全テスト通過 + workflow 構文チェック通過後、GitHub Actions で手動実行 (`workflow_dispatch`) して CI グリーンを確認する。
