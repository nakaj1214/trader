# 修正要件書（verify-before-fix）

> verify-before-fix スキルで生成。証拠に基づく診断結果と修正方針。
> 日時: 2026-10-14
> 対象: ISSUE-08（失敗通知ジョブが、依存を入れずに `requests` を import する）
> 出典: [memo/implement/prompt.md](prompt.md)（問題一覧）、[Codex 最終監査](../../.harness/reports/reliability-final-audit-2026-10-13.md)（Q01）
> 前の要件書: ISSUE-01〜07（REQ-071〜077）は実装済み。ISSUE-04・06・07 は未コミット。

---

## 診断結果

### 確認した現象

- site-packages を使えない Python で `scripts/check_workflow_health.py` を実行すると、起動前に `ModuleNotFoundError: No module named 'requests'`、終了コード 1 で落ちる。
- 4 つの workflow（`inflection_shadow` / `position_monitor` / `forward_validation` / `reliability_watchdog`）の `notify-failure` ジョブは、`setup-python` も `uv sync` も無く、`python scripts/check_workflow_health.py --notify-failure` を直接実行している。実行環境にたまたま入っている package に頼っている。

### 根本原因

[check_workflow_health.py:20](../../scripts/check_workflow_health.py#L20) が、出力を静かにする小さな関数 `suppress_provider_output` を `src/data/provider_output.py` から import する。そのモジュールは先頭で `import requests` する（[provider_output.py:13](../../src/data/provider_output.py#L13)）ため、関数自体は標準ライブラリしか使わないのに、`requests` が無いと import に失敗する。

失敗通知の経路（`failure_alert` と `notify_once`）は、標準ライブラリ（`json`・`os`・`re`・`urllib`）だけで書かれている。障害時に動くべき経路なので、依存は少ないほどよい。

### 証拠

| 仮説 | 判定 | 証拠 |
|------|------|------|
| 1. `requests` の import で起動前に落ちる | 確認 | site-packages なしの実行で `ModuleNotFoundError`、終了コード 1。 |
| 2. 4 つの `notify-failure` ジョブは依存を入れない | 確認 | 4 ファイルとも、`notify-failure` 内に `setup-python` / `uv sync` / `pip install` が無い。 |
| 3. 切り離しで他が壊れる | 棄却 | `src/__init__.py` は空、`src/data/__init__.py` は 72 バイトで重い import なし。重い依存を使うのは Watchdog の経路（`exchange_calendars`、遅延 import）だけで、そのジョブは依存を入れている。 |

---

## 修正要件

### REQ-078: 失敗通知スクリプトを標準ライブラリだけで起動できるようにする（ISSUE-08）

- **画面**: GitHub Actions の `notify-failure` ジョブ（`scripts/check_workflow_health.py --notify-failure`）
- **対象ファイル**: [src/data/provider_output.py](../../src/data/provider_output.py)、新規の小さなモジュール（`suppress_provider_output` の移設先）、[scripts/check_workflow_health.py](../../scripts/check_workflow_health.py)、`tests/test_workflow_health.py`
- **Before（現状）**: 失敗通知が `requests` に依存する import 連鎖を持つため、`requests` が無い環境では起動できない。
- **After（期待）**:
  - `suppress_provider_output` を、標準ライブラリだけを import する新しいモジュール（例 `src/data/quiet_output.py`）へ移す。`provider_output.py` は同名で再エクスポートし、既存の import（`from src.data.provider_output import suppress_provider_output`）と挙動を変えない。
  - `check_workflow_health.py` は新しいモジュールから import する。
  - site-packages を使えない環境（`python -B -S`）で、`--help` と `--notify-failure` が動く。
  - 重い依存を使う経路（Watchdog の期待実行の判定）は変更しない（そのジョブは依存を入れている）。
- **修正方針**:
  - 移すのは `suppress_provider_output` だけ。分類（`classify_provider_failure` など）は `requests` の型を使うので、`provider_output.py` に残す。
  - workflow（`notify-failure` ジョブ）は変更しない。依存を入れず、標準ライブラリだけで動く経路にするのが目的。
- **受入条件**:
  1. site-packages を使わない Python（`-B -S`）で `check_workflow_health.py --help` が終了コード 0。修正前に失敗する回帰テストとして追加する。
  2. 同じく site-packages なしで、`--notify-failure` が、ローカルの HTTP サーバー（`127.0.0.1`）に通知を送り、状態ファイルを書き、終了コード 0。通知の本文に secret・URL を含まない。
  3. `provider_output.suppress_provider_output` は従来どおり import でき、出力を抑える挙動は不変（既存のテストが無変更で PASS）。
  4. 全テスト・ruff・mypy（既知 31 件のみ）が通る。
- **baseline への影響**: なし（投資判定・評価の数値には無関係）。
- **未確認（integration）**: 実際の GitHub Actions 上でのジョブ実行は、ローカルでは確認できない。

---

## 次の手順

- 修正は Phase 5 で実施する。原因は確定済み。
- 続けて ISSUE-09（障害分類の消失）に進む。
