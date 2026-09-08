# Trader 現行経路 再調査レビュー

調査日: 2026-09-08  
対象: `main` ブランチの JP inflection shadow scan / forward validation

## 結論

`master` の内容は PR #9 で `main` に反映済みで、ブランチ未反映問題は解決している。一方、候補スコアと売却評価の正確性に影響する未修正問題が4件、運用上の軽微な問題が1件残っている。

## 未修正の問題

### P1: 赤字予想の悪化を上方修正として加点する

- 対象: `src/screening/inflection_live.py::_fundamental_features()`
- 原因: 営業利益予想の修正率を常に `(new / old - 1) * 100` で計算している。
- 再現: `FOP: -100 -> -200` という悪化が `upward_revision_pct = 100.0` になる。
- 影響: 「業績予想上方修正」の理由と最大5点が誤って付与され、候補順位・分類が変わり得る。
- 修正方針: 黒字同士の増減率、赤字縮小、赤字拡大、赤字から黒字、黒字から赤字を符号別に扱う。少なくとも赤字拡大を正の上方修正率にしない。
- 必要な回帰テスト: `-100 -> -200`、`-100 -> -50`、`-100 -> 50`、`100 -> -50`。

### P1: 早期に成立した Trailing Stop が60営業日経過まで未完了になる

- 対象: `src/evaluation/inflection_backtest.py::simulate_signal()`
- 原因: Trailing Stopの走査前に、`len(future_closes) < holding_days` なら未完了として返している。
- 再現: エントリー翌日に10% Stopへ到達していても、60営業日分のデータがなければ `exit_date=None`、`exit_reason=None`、`net_return_pct=None` になる。
- 影響: 直近約3か月の成立済みTrailing取引が集計から落ち、固定保有との比較が遅延・偏重する。
- 修正方針: Trailing指定時は現在までのOHLCを先に走査し、Stop成立なら完了取引として返す。Stop未成立かつ最大保有日未到達の場合だけ未完了にする。
- 必要な回帰テスト: 最大保有期間未到達でも、途中の通常Stop・gap Stopを確定できること。

### P1: 配当調整係数で出来高を変形している

- 対象: `src/data/yfinance_prices.py::_normalize_for_scanner()`
- 原因: `raw Close / Adj Close` をVolumeへ掛けている。この係数はsplit専用ではなく、配当等によるAdj Closeの調整も含む。
- 再現: raw Volumeが `[1000, 1000]` でも、Close `[100, 100]`、Adj Close `[98, 100]` なら `[1020.408..., 1000]` になる。
- 影響: `volume_ratio_20d` と候補条件（1.25倍以上）が企業行動によって歪む。売買代金は保存できても、出来高増加シグナルとしては不正確になる。
- 修正方針: momentum用の価格、出来高比率用のVolume、売買代金用の価格×Volumeを分ける。Adj Close比をVolumeへ一律適用しない。
- 参考: [yfinance download API](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html)、[yfinanceのOHLC調整実装](https://github.com/ranaroussi/yfinance/blob/main/yfinance/utils.py)
- 必要な回帰テスト: 配当調整だけではVolume比率が変わらないことと、split前後の期待する扱いを明示すること。

### P2: 異なる戦略・schema versionのsnapshotを同じ成績へ混在できる

- 対象: `src/evaluation/inflection_forward.py::load_inflection_signals()`、`scripts/rebuild_inflection_forward_validation.py`
- 原因: `strategy_version` と `report_schema_version` の存在は確認するが、snapshot間の一致を検証せず、そのまま全signalを一括集計する。
- 再現: `strategy_version=v1` と `v2` のsnapshotが同時に読み込まれる。
- 影響: 戦略変更後の成績が旧戦略と混ざり、どのルールの性能か判断できなくなる。
- 修正方針: versionごとに集計を分けるか、単一reportでは同一versionだけを許可して不一致時にfail closedする。
- 併せて確認: `candidate.get("score") or 0.0` はscore欠損を0点として受理するため、欠損・非有限値を不正snapshotとして拒否する。
- 必要な回帰テスト: strategy/schema不一致、score欠損、`NaN`、`inf` を拒否すること。

## 軽微な問題

### P3: 取引終了前の手動scanが正常な前日データをstale扱いする

- 対象: `src/data/market_calendar.py::expected_tse_session_date()`、`.github/workflows/inflection_shadow.yml`
- 取引日であれば時刻に関係なく当日を期待する一方、workflowは任意時刻の`workflow_dispatch`を許可している。
- 定期実行は16:40 JSTなので通常影響しない。手動実行を市場終了後に限定するか、取引終了前は前営業日を期待値にする。

## 解決済みの運用問題

- GitHubの既定ブランチは`main`。
- `main`と`origin/main`は`a71ef87`で一致し、ahead/behindは`0/0`。
- `master`の`9e39546`はPR #9で`main`へmerge済み。
- worktreeは調査開始時点でclean。
- archive外の有効workflowは `test.yml`、`inflection_shadow.yml`、`forward_validation.yml` の3件。
- 以前発生したmissing hookによるローカルcommand blockは、`main`反映後には再現しない。

## 現在の検証結果

- `pytest`: 67 passed
- coverage: 90.75%
- `ruff check src scripts tests`: PASS
- CI対象の`mypy`: PASS
- 追跡ファイルから実値らしい秘密鍵は検出されず、`.env.example`はplaceholderのみ。

テスト成功は上記問題の不存在を意味しない。4件はいずれも既存テストにない入力で再現済みである。本番APIとGitHub Actionsの実行履歴は、認証情報を使用していないため今回の確認範囲外とする。
