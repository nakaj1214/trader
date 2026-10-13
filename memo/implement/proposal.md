# 修正要件書（verify-before-fix）

> verify-before-fix スキルで生成。証拠に基づく診断結果と修正方針。
> 日時: 2026-10-13
> 対象: ISSUE-01（historical の市場カレンダーがベンチマーク依存、C04 の残存）
> 出典: [memo/implement/prompt.md](prompt.md)（問題一覧）、[Codex 最終監査](../../.harness/reports/reliability-final-audit-2026-10-13.md)
> 前の要件書: Stage 4C（REQ-068〜070、実装・コミット済み）は git 履歴（dev6）から復元できる。

---

## 診断結果

### 確認した現象

- 全市場日に存在する日が、対象銘柄とベンチマーク（1306.T）の両方で欠けていると、未評価になるべき取引が完了扱いになる。
- synthetic（80 営業日、対象銘柄とベンチマークが 2026-01-08 を欠き、別銘柄は取引している）で `_lag_report` を実行した結果:
  - h5: completed 1 / unevaluated 0、退出 2026-01-13、net +1.79%。
  - 同じ取引に全市場日のカレンダーを渡すと `incomplete_price_path`（欠落 `2026-01-08`）で未評価になる。

### 根本原因

historical の評価経路は、全市場日（`BarPanel.sessions`）を持っているのに、評価の市場カレンダーとしてベンチマーク 1306 の日付（`benchmark_history.index`）を使っている。ベンチマークと銘柄が同じ日を欠くと、その日が市場日として認識されず、欠損が検出されない。horizon が欠落日の分だけ延びて、完了として集計される。

カレンダーの出どころ:
- [inflection_historical.py:616](../../src/evaluation/inflection_historical.py#L616)（`_build_group_report` 経由。内部で [inflection_report.py:325](../../src/evaluation/inflection_report.py#L325) が `benchmark_history.index` を使用）
- [inflection_historical.py:622](../../src/evaluation/inflection_historical.py#L622)（`early_trades`）
- [inflection_historical.py:631](../../src/evaluation/inflection_historical.py#L631)（`simulate_portfolio`）
- [inflection_historical.py:478](../../src/evaluation/inflection_historical.py#L478)（`h60_excess_pairs`）

### 証拠

| 仮説 | 判定 | 証拠 |
|------|------|------|
| 1. historical がベンチマークの index を市場カレンダーにしている | 確認 | 上記 synthetic で、現行 `_lag_report` は完了、全市場日を渡すと `incomplete_price_path`。 |
| 2. 実データ（キャッシュ）でも 1306 に欠落日がある | 棄却（現時点） | 手元の J-Quants キャッシュ 422 営業日（2024-10-09〜2026-07-03）で、1306 の行欠落・OHLC 不完全はともに 0 件。現状の実害は無く、ベンチマークが 1 日でも欠けると誤る潜在的な不具合。 |
| 3. 修正が forward の結果を変える | 回避可能 | `_build_group_report` は共有関数。市場カレンダーを任意引数にし、省略時は従来どおり `benchmark_history.index` とすれば、forward・learning は変わらない（両経路は 1306.T を `required` で取得し、全 TSE 営業日の網羅を強制する。[forward_prices.py:233-235](../../src/data/forward_prices.py#L233-L235)）。 |

---

## 修正要件

### REQ-071: historical の評価に全市場日のカレンダーを使う（ISSUE-01 / C04）

- **画面**: historical backtest（`scripts/run_inflection_historical_backtest.py`、`build_backtest_report`）
- **対象ファイル**: [src/evaluation/inflection_historical.py](../../src/evaluation/inflection_historical.py)（`h60_excess_pairs`、`_lag_report`、`build_backtest_report`）、[src/evaluation/inflection_report.py](../../src/evaluation/inflection_report.py)（`_build_group_report` に任意の市場カレンダー引数）、`tests/test_inflection_historical.py`、`tests/test_inflection_backtest.py`
- **Before（現状）**: 評価の市場カレンダーが `pd.DatetimeIndex(benchmark_history.index)`。ベンチマークと銘柄が同じ日を欠くと、欠落が検出されず、完了扱いになる。
- **After（期待）**: historical の評価・ポートフォリオ・h60 の超過収益ペアが、全市場日（`data.panel.sessions`）を市場カレンダーにする。欠落日があれば `incomplete_price_path` で未評価になる。
- **修正方針**:
  - `build_backtest_report` で `data.panel.sessions` から市場カレンダー（`pd.DatetimeIndex`）を作り、`_lag_report` に渡す。
  - `_lag_report` が `h60_excess_pairs`・`early_trades`・`simulate_portfolio` にそのカレンダーを渡す。
  - `_build_group_report` に `market_calendar: pd.DatetimeIndex | None = None` を追加する。None のときは従来どおり `benchmark_history.index`（forward・learning は変わらない）。内部の `prepare_calendar` と `simulate_signals`/`simulate_exit_rule` に同じカレンダーを使う。
  - ベンチマーク価格のペアリング（`paired_benchmark_returns`）は変更しない（ベンチマークの値は 1306 の履歴から取る）。
  - 注意: `simulate_portfolio` は「カレンダーが取引のエントリー日・退出日をすべて含む」ことを要求する（[inflection_portfolio.py:114-115](../../src/evaluation/inflection_portfolio.py#L114-L115)）。全市場日は、ベンチマークの日付を含むため満たす。
  - ISSUE-02（kill criterion）・ISSUE-05（エントリー日のずれ）は別 REQ で扱う。本 REQ では触らない。
- **受入条件**:
  1. 上記 synthetic で、historical の `_lag_report` が h5 を `incomplete_price_path` の未評価にする（completed 0 / unevaluated 1）。回帰テストとして追加し、修正前に失敗することを確認する。
  2. forward（`rebuild_inflection_forward_validation.py` の経路）と learning の既存テストが無変更で PASS。
  3. ベンチマークが欠落しない正常入力では、historical の結果が修正前と完全一致（欠落が無い日付集合ではカレンダーが同じため）。キャッシュを使った比較は読み取りのみで行う。
  4. 全テスト・ruff・mypy（既知 31 件のみ）が通る。
  5. historical 評価の変化を baseline-changing として記録する（実キャッシュでは変化 0 の見込み）。

---

## 次の手順

- 修正は Phase 5 で実施する。原因は確定済み。
- 続けて ISSUE-02（kill criterion）、ISSUE-05（エントリー日）に進む。同じ `_evaluation_window` と historical 経路に関わるため、続けて扱うと手戻りが少ない。
