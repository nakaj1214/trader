# trader 修正メモ（CI failing 対応・反映版）

## 1. `.github/workflows/weekly_run.yml`（反映内容）

- `Install dependencies` に `python -m pip install pytest` を追加
- `Slack 通知`は `if: always()` + `job env` 経由の `SLACK_WEBHOOK_URL` 参照へ統一
- `Commit and push` は **commit → pull --rebase → push** の順に修正
  - dirty tree での `git pull --rebase` 失敗を避けるため、`--autostash` を付与

```yml
- name: Commit and push dashboard data
  run: |
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"

    git add dashboard/data/
    git diff --staged --quiet || git commit -m "chore: update dashboard data [skip ci]"

    git pull --rebase --autostash origin "${{ github.ref_name }}"
    git push
```

## 2. `src/enricher.py`（KeyError: 'screening' 対応）

`compute_explanations()` の `screening` 参照を安全化する。

```python
# 変更前
lookback = config["screening"]["lookback_days"]
weights = config["screening"].get("weights", {})

# 変更後
lookback = config.get("screening", {}).get("lookback_days", 252)
weights = config.get("screening", {}).get("weights", {})
```

補足: `config.yaml` では `screening.lookback_days` が定義済みだが、テストや最小構成で欠落しても落ちないことを優先する。

## 3. `src/baseline.py`（zero std で Sharpe を `None`）

`_portfolio_stats()` に EPS ガードを入れる。

```python
std = returns.std()
eps = 1e-12
sharpe = round(float((returns.mean() / std) * (52 ** 0.5)), 2) if std > eps else None
```

## 4. テスト修正

### `tests/test_exporter.py`

`predictions.json` はトップレベル dict（`{"predictions": [...]}`）なので、統合テストは配列をキー経由で参照する。

```python
raw = json.loads((tmp_path / "predictions.json").read_text(encoding="utf-8"))
predictions = raw["predictions"]
assert len(predictions) == 3
assert predictions[0]["ticker"] == "AAPL"
```

### `tests/test_enricher.py`

`screening` キー欠落でも `compute_explanations()` が落ちない回帰テストを追加する。

```python
df = _make_price_df(list(range(100, 400)))
assert compute_explanations("AAPL", df, {}) is not None
assert compute_explanations("AAPL", df, {"sizing": {}}) is not None
```

## 5. 確認コマンド

```powershell
python -m pytest tests/test_baseline.py tests/test_exporter.py tests/test_enricher.py -v
```

workflow 構文チェック:

```powershell
actionlint .github/workflows/weekly_run.yml
# actionlint が無い場合
python -c "import yaml; yaml.safe_load(open('.github/workflows/weekly_run.yml'))"
```

## 6. rebase 継続時の最終手順

```powershell
git add .github/workflows/weekly_run.yml src/enricher.py src/baseline.py tests/test_exporter.py tests/test_enricher.py docs/error/fix_bundle.md
git rebase --continue
git push origin HEAD
```

コンフリクトが再発した場合は、修正 → `git add` → `git rebase --continue` を繰り返す。
