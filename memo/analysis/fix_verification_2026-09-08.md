# 修正反映の再検証レポート

調査日: 2026-09-08

対象: [`code_and_ops_review_2026-09-08.md`](code_and_ops_review_2026-09-08.md) と [`codex_review.md`](codex_review.md) の指摘に対する修正差分（作業ツリー、未コミット）

## 結論

両レビューで指摘した全7件（Codex側P1×3・P2×1、自分側3件）が正しく修正されていることを、diffの個別確認とテスト追加内容の突き合わせで確認した。`pytest`は67件→**89件**に増加し全パス、カバレッジ91.11%、`ruff`/`mypy`ともにクリーン。修正漏れ・新規リグレッションは検出されなかった。

## 修正内容の検証

| # | 指摘元 | 指摘内容 | 修正内容 | 検証方法 |
|---|---|---|---|---|
| 1 | Codex P1 | 赤字予想の悪化（`FOP: -100→-200`）を上方修正として加点 | `src/screening/inflection_live.py::_fundamental_features()` の計算式を `(new-old)/abs(old)*100` に変更し符号を保持 | `-100→-200`が`-100%`になる回帰テスト（`test_forecast_revision_preserves_improvement_direction`、4パターン）を確認 |
| 2 | Codex P1 | Trailing Stopが早期成立しても60営業日分のデータがないと未完了扱い | `src/evaluation/inflection_backtest.py::simulate_signal()` に `has_full_horizon` を導入。Trailing指定時は部分窓でもStop走査を先に行い、成立すれば完了取引として返す。不成立時のみ未完了 | 4日分のデータでgap Stopが完了取引になるテスト、Stop不成立時は未完了のままのテストを確認。あわせて `select_non_overlapping_trades` も未完了(open)ポジションでティッカーを塞ぐよう修正されており、回帰テストも追加済み |
| 3 | Codex P1 | 配当調整係数(`raw_close/adj_close`)をVolumeにも適用し出来高比率を歪めていた | `src/data/yfinance_prices.py::_normalize_for_scanner()` でVolumeは生値のまま保持し、`raw_close*raw_volume` を新設の `Turnover` 列に分離。Closeのみ調整値を使用 | 配当のみのケースでVolumeが変化しないテスト、Turnover列を使う`_technical_features`側のテストを確認 |
| 4 | Codex P2 | 異なる`strategy_version`/`report_schema_version`のsnapshotを同一集計に混在できる。score欠損は0点として受理 | `src/evaluation/inflection_forward.py::load_inflection_signals()` で最初に読んだversionを基準にfail closed。scoreは欠損/bool/NaN/inf/範囲外(0-100)を拒否 | version不一致、score異常系（NaN, inf, -1, 101, 欠損）の回帰テストを個別に確認 |
| 5 | Codex P3 | 取引時間中の手動scanで、まだ引けていない当日を期待し前営業日の正常データをstale扱いする | `src/data/market_calendar.py::expected_tse_session_date()` で `session_close` と比較し、閉場前なら前営業日を期待値にする | 閉場前の`generated_at`で前日データを受理するテスト(`test_validate_report_accepts_previous_session_before_tse_close`)を確認 |
| 6 | 自分 | forward validationの結果（TOPIX対比・Trailing Stop成績）がどこにも残らない | `scripts/rebuild_inflection_forward_validation.py` に `_summary_only()` を追加し、銘柄別trade行を除いた集計を `inflection_forward_validation_summary.json` として出力。`.github/workflows/forward_validation.yml` で `actions/upload-artifact`（90日保持）にアップロード。READMEにも追記 | ワークフロー差分、summary生成ロジックの単体テスト(`test_forward_summary_removes_prediction_rows`)を確認 |
| 7 | 自分 | forward validationの価格取得(`_fetch_adjusted_histories`)にリトライ/レート制御が一切ない | 再試行(`max_retries`)・指数バックオフ・リクエスト間隔(`request_interval_seconds`)を追加 | 一時的失敗から2回目で成功するテスト(`test_forward_price_fetch_retries_transient_failure`)を確認 |
| 8 | 自分 | `compare_close_series`（`src/data/validation.py`）が本番経路から一切呼ばれていない死んだコード | 関数を削除 | コードベース全体で参照ゼロを確認 |

## 新たに見つかった残存事項（軽微、ブロッカーではない）

### 1. 株式分割時のVolume歪みが再発する可能性
配当由来のVolume歪み（頻発）は正しく除去されたが、`yf.download(..., actions=False)` で分割イベント自体を取得していないため、純粋な株数調整ができない。分割直後の約20営業日は `volume_ratio_20d` が機械的に跳ね、`EARLY_CANDIDATE`条件（出来高比1.25倍以上）に影響し得る。分割はレアイベントであり、常時発生していた配当由来の誤りに比べれば実害は小さいため、現時点では妥当なトレードオフと判断する。将来的に分割検知を別途行うなら改善余地がある。

### 2. `STRATEGY_VERSION` の運用手順が未整備
今回 `jp-inflection-shadow-v1 → v2` へ上げると同時に、異なるversionのsnapshot混在をfail closedにする変更が入った。組み合わせとしては正しいが、今後version変更のたびに「旧versionのsnapshotをどう退避するか」という運用手順が必要になる。現状 `dashboard/data/inflection/` は空でまだ実データが無いため影響はないが、実データ蓄積後に同様の変更をする際はrunbook化をおすすめする。

### 3. 設計判断寄りで対象外のまま残っている項目
- yfinance単独依存（公式APIではない価格ソースへの一本足打法）
- J-Quantsのページネーション+レート制御と、GitHub Actionsの45分タイムアウトとの余裕度が未実測

いずれも今回のバグ修正の範囲外であり、次に手を入れる際の検討事項として残す。

## 検証コマンド

```
pytest tests/        # 89 passed, coverage 91.11%
ruff check src scripts tests   # All checks passed
mypy --ignore-missing-imports <production path files>   # Success
```