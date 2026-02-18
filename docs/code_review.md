# 実装コード再レビュー（2026-02-18, 再確認2）

対象:
- `src/main.py`
- `src/screener.py`
- `src/predictor.py`
- `src/sheets.py`
- `src/tracker.py`
- `src/notifier.py`
- `src/glossary.py`
- `src/utils.py`

## 旧指摘の再確認

- 解消: 営業日基準の予測 (`src/predictor.py:60`)
- 解消: 更新対象日の終値取得に `target_date` を反映 (`src/tracker.py:36`, `src/tracker.py:236`)
- 解消: 終値未取得で週が詰まる問題への対処 (`src/tracker.py:167`)
- 解消: `min_market_cap` 取得失敗時の0扱い除外 (`src/screener.py:79`, `src/screener.py:195`)
- 解消: `評価不能` 行を的中率分母から除外 (`src/tracker.py:134-137`)
- 解消: 終値取得窓を14日に拡大 (`src/tracker.py:48`)
- 解消: 祝日対応 — 実取引日データベースの評価日カウントに変更 (`src/tracker.py:35-77`)

## Findings（重大度順）

現時点で未解消の指摘事項はなし（静的レビュー範囲）。

## テスト観点

1. 主要ユニットテストは追加済み
- `tests/test_predictor.py`
- `tests/test_screener.py`
- `tests/test_sheets_tracker.py`

2. 追加テスト → 追加済み
- `test_calculate_accuracy_excludes_unevaluable`: `評価不能` を的中率分母から除外できること
- `test_fetch_close_at_handles_holiday`: 祝日がある週で実取引日ベースの評価が正しいこと
- `test_fetch_close_at_insufficient_trading_days`: 取引日不足時に価格を返さないこと

## 実行確認メモ

- この環境では `python` / `py` 実行が不可で、実行テストは未実施（静的レビューのみ）。
