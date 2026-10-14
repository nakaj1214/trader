# 修正要件書（verify-before-fix）

> verify-before-fix スキルで生成。証拠に基づく診断結果と修正方針。
> 日時: 2026-10-14
> 対象: ISSUE-03（live scan で優先株が普通株のメタデータを上書き）
> 出典: [memo/implement/prompt.md](prompt.md)（問題一覧）
> 前の要件書: ISSUE-01（REQ-071）、ISSUE-02（REQ-072）は実装済み。ISSUE-05（REQ-073、遅延エントリーの記録）は実装済み・未コミット。

---

## 診断結果

### 確認した現象

- 普通株の ticker に、優先株の master 行が紐づくことがある。
- fake（普通株 `25930` 伊藤園と優先株 `25935` 伊藤園（優先株式）、いずれもプライム）で `scan_japan_inflection` を実行:
  - 普通株を先に並べた場合: 社名「伊藤園」、`financial_summary` は `25930`。
  - 優先株を先に並べた場合: 社名「伊藤園（優先株式）」、`financial_summary` は `25935`。
  - いずれも universe は 1（同じ ticker に畳まれる）。並び順で結果が変わる。
- 実 master（`.data/jquants/master/2026-07-01.json.gz`）: 対象 3 市場の 3,723 行のうち、普通株 3,716、非普通株 7。優先株が後に来るため、伊藤園・インフロニア・ゼンショー・JAL・ANA・ソフトバンクの 6 銘柄で優先株が勝つ。

### 根本原因

[scan_japan_inflection](../../src/screening/inflection_live.py#L781-L787) が、コードの先頭 4 桁だけで ticker を作る（[_ticker_from_code](../../src/screening/inflection_live.py#L127-L129)）。優先株の行（コード末尾が 0 以外）が、同じ ticker の普通株の行を上書きし、`ticker_meta` に優先株の社名・コードが入る。財務は `ticker_meta` のコード（[_evaluate_candidate](../../src/screening/inflection_live.py#L546-L547)）で取得されるため、優先株コードには財務行が無く、ファンダメンタルが全欠損になる。

historical は `_is_ordinary_code`（5 桁で末尾 0）で普通株だけを対象にしており（[inflection_historical.py:71-73](../../src/evaluation/inflection_historical.py#L71-L73)、[同:232](../../src/evaluation/inflection_historical.py#L232)）、live だけに無い。

### 証拠

| 仮説 | 判定 | 証拠 |
|------|------|------|
| 1. live だけ普通株のフィルタが無い | 確認 | 上記 fake。historical は除外済み。 |
| 2. 衝突は master の並び順に依存する | 確認 | 並びを逆にすると結果が変わる。実 master では優先株が後に来て、6 銘柄で優先株が勝つ。 |
| 3. 修正で ticker が消える | 棄却 | 実 master で、ticker は修正前後とも 3,716 個。普通株が無く優先株だけの ticker は 0 件。universe 件数は変わらない（初期の「6 件減る」という見込みは誤り）。 |

---

## 修正要件

### REQ-074: live scan は普通株の master 行だけを universe にする（ISSUE-03）

- **画面**: 日次 scan（`scripts/run_inflection_shadow.py`、`scan_japan_inflection`）
- **対象ファイル**: [src/screening/inflection_live.py](../../src/screening/inflection_live.py)（`scan_japan_inflection`）、[src/evaluation/inflection_historical.py](../../src/evaluation/inflection_historical.py)（`_is_ordinary_code` の参照元を共通化する場合のみ）、`tests/test_inflection_live.py`
- **Before（現状）**: master の行を先頭 4 桁で ticker 化して、後から来た行で上書きする。優先株（末尾 0 以外）が普通株の社名・コード・財務取得を置き換える。
- **After（期待）**:
  - live の universe は、コードが 5 桁で末尾 0 の行（普通株）だけで作る。historical と同じ規則にする。
  - 優先株の行があっても、普通株の `ticker_meta`（社名・市場・業種）と普通株コードの財務が使われる。master の並び順に依存しない。
  - 普通株の行は従来どおり ticker 化され、これまでの結果（universe 件数、候補、スコア）は、優先株が絡まない銘柄では不変。
- **修正方針**:
  - `scan_japan_inflection` の master 絞り込み（`JP_MARKET_CODES` の判定）に、普通株の判定を加える。判定関数は `_is_ordinary_code` を live 側へ移して historical から参照する形にするか、live に同じ小関数を置く（import の循環を避ける。historical は live を import している）。
  - `FEATURE_DEFAULTS` やスコア・分類・閾値は変更しない。
  - 優先株の価格は取得しない（ticker が普通株のものなので、従来から価格は普通株の ticker で取得済み）。
- **受入条件**:
  1. 上記 fake で、普通株を先に並べても優先株を先に並べても、社名は普通株、`financial_summary` は普通株コード、universe は 1 になる。修正前に失敗する回帰テストとして追加する。
  2. 優先株が絡まない既存ケースは、結果が完全に不変（既存テストが無変更で PASS）。
  3. 実 master で、修正前後の universe 件数（3,716）が変わらないことを記録する。6 銘柄（伊藤園・インフロニア・ゼンショー・JAL・ANA・ソフトバンク）の `ticker_meta` が普通株になることを確認する。
  4. 全テスト・ruff・mypy（既知 31 件のみ）が通る。
- **baseline への影響**: 6 銘柄（上記）の社名・財務由来の特徴量が変わる（優先株コード由来の全欠損 → 普通株の実財務）。スコア・分類が変わり得るため、baseline-changing として記録する。

---

## 次の手順

- 修正は Phase 5 で実施する。原因は確定済み。
- 続けて ISSUE-04（Position Monitor が古い保有銘柄を永久に評価できない）に進む。
