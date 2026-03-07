# Cloudflare Pages / GitHub Actions 前提の調査結果

- 調査日: 2026-03-07
- 対象: 現在のワークツリー
- 前提:
  - GitHub Actions がテスト、週次データ生成、Cloudflare Pages デプロイを担当する
  - Cloudflare Pages は静的成果物と `dashboard/data/*.json` を配信する

---

## 結論

Cloudflare Pages への静的デプロイ経路自体は大きく壊れていない。一方で、GitHub Actions で継続運用する前提では、Python 側の旧実装と新しい CI 定義の間に整合性崩れがあり、そのままでは CI が安定しない。

特に問題なのは、`src.predictor` / `src.exporter` の旧系が `prophet` を import 時に必須化している点と、追加予定の `test.yml` が `.[dev]` しか入れない点である。これにより、Cloudflare Pages 用データの生成以前にテスト段階で落ちる構成になっている。

---

## Pages / Actions 観点の整理

### 1. Cloudflare Pages 側

- `deploy_dashboard.yml` は `dashboard-v2` を build し、`dashboard/data/*.json` を `dashboard-v2/static/data/` にコピーして Pages へ deploy する構成になっている
- 静的配信の前提自体は妥当
- `tests/test_dashboard_html.py` と `tests/test_json_exporter.py` は通っており、ダッシュボード HTML と新しい JSON exporter 側には致命的な破綻は見えなかった

### 2. GitHub Actions 側

- `weekly_run_v2.yml` は `python -m src.cli run --market all` を実行し、生成済み `dashboard/data/` を commit/push する
- この経路を正とするなら、Pages は GitHub push を契機に継続的に更新できる
- ただし、別途追加されている `test.yml` は現状のコードベースと噛み合っておらず、CI の安定運用を阻害する

---

## 主要な発見事項

### F1. 旧予測/旧エクスポート系が `prophet` 未導入環境で即死する

- `src/predictor.py` が module import 時に `from prophet import Prophet` を実行する
- `src/exporter.py` は `src.predictor` から `compute_prob_up` を import している
- そのため `prophet` がない環境では、予測だけでなく export 関連テストまで巻き込んで失敗する
- GitHub Actions の `test.yml` は `python -m pip install -e ".[dev]"` しか実行しないが、`pyproject.toml` では `prophet` は `ml` extra にある
- つまり、Actions 上の test job は構成上ほぼ確実に失敗する

Cloudflare Pages への影響:

- Pages 自体は落ちない
- ただし upstream の test / data generation が落ちると `dashboard/data/*.json` が更新されず、Pages には古いデータまたは欠損データが残る

### F2. 新規 `test.yml` はこのままだと常時 red

- lint job は `ruff check src/ tests/` を実行するが、現ワークツリーでは 46 件の違反が出る
- test job は `.[dev]` のみを入れるため、F1 の import 問題を踏む
- この workflow を commit すると、Cloudflare Pages に行く前段の CI が安定しない

### F3. 新旧 2 系統の実行経路が並存している

- 新系:
  - `src.cli`
  - `src.orchestrator`
  - `src.export.json_exporter`
  - `config/default.yaml`
  - `weekly_run_v2.yml`
- 旧系:
  - `src.main`
  - `src.predictor`
  - `src.exporter`
  - `config.yaml`
  - `README.md`
  - `weekly_run.yml`

この状態だと、どの workflow / install 方法 / entrypoint を使うかで成立条件が変わる。Cloudflare Pages と GitHub Actions を安定運用するなら、どちらを正系にするかを明確に固定した方がよい。

---

## 実行した確認

### 全体テスト

実行:

```bash
python -m pytest -q -p no:cacheprovider --no-cov
```

結果:

- 465 tests collected
- 429 passed
- 36 failed
- 失敗は `src.predictor` / `src.exporter` 起点に集中

### 新系の主要テスト

実行:

```bash
python -m pytest tests/test_json_exporter.py tests/test_prediction_new.py tests/test_orchestrator.py tests/test_config.py -q -p no:cacheprovider --no-cov
```

結果:

- 53 passed

解釈:

- 新系の `json_exporter` / `prediction` / `orchestrator` / `config` は少なくとも単体テスト上は成立している
- 現在の大きな破綻は旧系と CI 定義の組み合わせにある

### Ruff

実行:

```bash
python -m ruff check src tests
```

結果:

- 46 errors
- 大半は unused import だが、`test.yml` を lint gate にするなら未解消では通らない

---

## Cloudflare Pages 運用への示唆

Cloudflare Pages は静的配信なので、問題の中心は Pages ではなく「GitHub Actions が正しい JSON を安定生成して push できるか」にある。今回の調査では、Pages 用フロントと新しい JSON exporter には大きな阻害要因は見えず、ボトルネックは以下の 2 点だった。

1. CI/test 経路が旧 `src.predictor` / `src.exporter` を踏んで落ちること
2. 新旧 2 系統が混在し、workflow ごとに別の前提で動いていること

---

## 推奨対応

### 優先度高

1. GitHub Actions の正系を `weekly_run_v2.yml` + `deploy_dashboard.yml` + `src.cli` に寄せる
2. `src.predictor` と `src.exporter` を残すなら、`prophet` を import 時ではなく実行時に読む形へ変更する
3. もしくは旧系を廃止するなら、`README.md`、`weekly_run.yml`、旧系テストを新系へ整理する

### 優先度中

1. `test.yml` を commit する前に、少なくとも以下を揃える
   - `ml` extra を入れる
   - 既存 ruff 違反を解消するか、lint 対象/ルールを一時的に絞る
2. Cloudflare Pages 側の deploy は、`dashboard/data/*.json` 更新を前提にしているため、週次生成 workflow の失敗時に stale data になることを運用上明記する

---

## 現時点の判断

- Cloudflare Pages への静的配信方式: 継続可能
- GitHub Actions による自動運用: そのままでは不安定
- 安定化の近道: 新系 workflow / 新系 entrypoint に一本化し、旧系の依存条件を CI から切り離す
