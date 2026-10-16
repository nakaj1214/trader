# 修正要件書（verify-before-fix）

> verify-before-fix スキルで生成。証拠に基づく診断結果と修正方針。
> 日時: 2026-10-16
> 対象: ISSUE-14（レポート内の「up/down」の二重定義）
> 出典: [memo/implement/prompt.md](prompt.md)（問題一覧）
> 前の要件書: ISSUE-01〜13（REQ-071〜083）は実装済み。ISSUE-12・13 は未コミット。

---

## 診断結果

### 確認した現象

- 同じ group report のブロックが、同じラベル `up`/`down` を、別の意味で出力する。
- 実測（長い上昇のあとに 4 週間の押し目がある相場。最後の終値 221.5、200 営業日平均 207.8）:
  - `regime_sample_counts`: `{'up': 0, 'down': 1, 'unknown': 0}`（20 営業日の騰落で `down`）。
  - `regime_breakdown['trend']`: `{'up': 1, 'down': 0, 'unknown': 0}`（200 営業日移動平均との比較で `up`）。

### 根本原因

- `regime_sample_counts` は [regime_label](../../src/evaluation/inflection_report.py#L72-L79) で、**直近 20 営業日の騰落**（20 営業日前以上の終値なら `up`）。
- `regime_breakdown` は [regime.py](../../src/evaluation/regime.py) の `regime_labels` で、**200 営業日移動平均との比較**（以上なら `up`）。
- 前者は 9/9、後者は 10/1 に別の目的（市場環境の層別）で追加された。同じ語が別の定義のまま並んで出力され、レポートからはどちらが何を指すか分からない。統一する指示や記録は無い。

### 証拠

| 仮説 | 判定 | 証拠 |
|------|------|------|
| 1. 同じレポート内で同じラベルが別の意味で使われる | 確認 | 上記の実測（`down` と `up` が同時に出る）。 |
| 2. 意図的な差か | 経緯あり | 導入時期・目的が異なる（9/9 の件数表示、10/1 の層別）。統一の指示は無い。 |
| 3. 利用者は限定的 | 確認 | `regime_sample_counts` はコード内で `_report_breakdowns` が作るだけで、読むのは出力 JSON。数値を変えると過去との比較が崩れる。 |

---

## 修正要件

### REQ-084: up/down の定義をレポートに明示する（数値は変えない）（ISSUE-14）

- **画面**: forward / historical のレポート（各 group report の horizon・exit_strategy ブロック）
- **対象ファイル**: [src/evaluation/inflection_report.py](../../src/evaluation/inflection_report.py)（`_report_breakdowns`）、`tests/test_inflection_forward.py`（既存の report 形状のテストがある場所。必要なら）
- **Before（現状）**: 同じ `up`/`down` が、20 営業日の騰落と 200 営業日移動平均で別の意味を持つのに、レポートに定義が無い。
- **After（期待）**:
  - `_report_breakdowns` の出力に、定義を説明するキー `regime_definitions` を追加する。内容は固定の短い文字列で、`regime_sample_counts` は「直近 20 営業日の終値の騰落（20 営業日前以上で up）」、`regime_breakdown` の `trend` は「終値と 200 営業日単純移動平均の比較（以上で up）」、`volatility` は「20 営業日実現ボラティリティと、過去 252 営業日の値の中央値との比較」。
  - 既存のキー（`score_band_sample_counts`・`regime_sample_counts`・`regime_breakdown`）と、その数値は一切変えない（キー名の変更もしない）。
  - 追加するのは固定の文字列だけ（個別の取引情報・ticker を含まない）ので、公開用の要約にも含めてよい。
- **修正方針**:
  - `inflection_report.py` に定数 `REGIME_DEFINITIONS`（dict）を置き、`_report_breakdowns` の戻り値に `"regime_definitions": REGIME_DEFINITIONS` を足す。
  - 定義の文面は、`regime.py` の閾値（`TREND_WINDOW`・`VOLATILITY_WINDOW`・`VOLATILITY_BASELINE_SESSIONS`）と `regime_label` の 20 営業日の定数（コード内の `21` 本目＝20 営業日前）から生成し、数値がずれないようにする。
  - 新しいキーは、`_report_breakdowns` を使う全ブロック（horizon、stress、exit_strategy）に付く。レポートは再生成される前提で、キーが増えることは許容する（過去レポートとの比較は、既存キーで可能）。
- **受入条件**:
  1. レポートの各ブロックに `regime_definitions` があり、`regime_sample_counts` と `trend` の定義が、20 営業日の騰落と 200 営業日移動平均として区別されている。修正前に失敗する回帰テストとして追加する。
  2. 既存のキーと数値が不変（既存のテストが無変更で PASS。上の実測の相場で `regime_sample_counts` と `trend` の値が従来どおり）。
  3. 定義の文面に含まれる窓の数値が、コードの定数と一致する（定数を変えると文面も変わる）。
  4. 全テスト・ruff・mypy（既知 31 件のみ）が通る。
- **baseline への影響**: なし（既存の数値は不変。レポートにキーが増えるのみ）。

---

## 次の手順

- 修正は Phase 5 で実施する。原因と方針は確定済み。
- これで ISSUE-01〜14 のすべてに着手済み。
