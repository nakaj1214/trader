# Trader プロジェクト調査レポート（コード品質 / 運用）

調査日: 2026-09-08

対象: 現在の JP inflection shadow 経路（`src/`, `scripts/`, `.github/workflows/`）

## 結論

出口戦略に特化した [`trader_exit_strategy_research.md`](../trader_exit_strategy_research.md) とは別に、コード全体のバグ・堅牢性、および運用/サービス選定の妥当性を調査した。テストは67件全パス、カバレッジ90.75%、ruff/mypy(CI相当設定)もクリーンで、point-in-time汚染を避ける設計は随所に行き届いている。その上で、実運用に影響し得る問題点を以下の通り確認した。

## コード上の問題点

### forward validation の価格取得にリトライ/レート制御が一切ない（重要度: 中〜高）

`scripts/rebuild_inflection_forward_validation.py` の `_fetch_adjusted_histories`（35-72行目）は銘柄ごとに `yf.Ticker(ticker).history()` を逐次呼び出すだけである。

- 本番経路の `src/data/yfinance_prices.py` はbatch化・指数バックオフ・再試行・呼び出し間隔スリープを実装済みだが、forward validation側は1回失敗したら即座にそのtickerを失敗扱いにし、`RuntimeError` で全体を中断する。リトライも呼び出し間隔の制御もない。
- EARLY_CANDIDATE の蓄積が進むほど対象tickerが増え、Yahoo側のレート制限(429)を受けやすくなる。一過性のネットワークエラー1件で、毎週の forward validation が丸ごと失敗し続ける可能性がある。
- 本番用の堅牢な fetch ロジックが既にあるので、同等の再試行・ペーシングをこちらにも適用するのが直し方として妥当。

### `compare_close_series` が本番経路のどこからも呼ばれていない（重要度: 低）

`src/data/validation.py`（57行目）の2ソース比較関数は、テスト(`tests/test_data_validation.py`)以外どこからも参照されていない。本番の価格ソースはyfinance単独（J-Quants Freeは価格を提供しない）で、比較対象となる「もう一つのソース」自体が存在せず、実質的に死んでいる安全機構になっている。「クロス検証している」という誤解を招くため、使う予定がなければ削除、使うなら実際に配線すべき。

### 同じ機能（yfinance取得）が2箇所に別実装で存在

本番スキャン用 `fetch_price_data`（`yf.download`、バッチ、再試行）と forward validation 用 `_fetch_adjusted_histories`（`yf.Ticker().history`、個別、再試行なし）が別ロジックになっている。上記のリトライ欠如もこの重複が一因で、将来yfinance側の仕様変更に対応する際に片方だけ直して不整合になるリスクがある。

## 運用上の問題点

### forward validation の結果がどこにも残らない（重要度: 高）

`.github/workflows/forward_validation.yml` は週次で `scripts/rebuild_inflection_forward_validation.py` を実行するが、出力先の `artifacts/inflection_forward_validation.json` は `.gitignore` 対象かつ `actions/upload-artifact` も行っていない。ログに出るのは `signal_count` と保存パスのみ。

戦略がTOPIXに勝っているか、Trailing Stopが固定期間より優れているかを計算しているのに、その結果を人間が一度も確認できない設計になっている。データ健全性の合否だけがCI結果として残り、肝心の予測精度・超過リターンは毎回捨てられる。ここが埋まらない限り、README/memoが掲げる「out-of-sample検証で優位性を確認してから次に進む」という手順自体が実行不能である。暗号化したまま要約だけをSlack等に送る、または暗号化JSONをprivateな場所に保存するなど、結果を継続的に確認できる経路が必要。

### 唯一の価格ソースが非公式APIのyfinance（重要度: 中）

本番の日次スキャンは価格・出来高を100% yfinanceに依存している。yfinanceは非公式スクレイピング系ライブラリで、仕様変更・遮断のリスクが常にある。J-Quants Freeは価格を提供しないため、代替ソースが用意されていない。データ健全性チェック（カバレッジ率など）はあるが、「yfinanceが部分的に壊れて古い/誤ったデータを返し続ける」ケースの検知は薄い。前述の死んでいる `compare_close_series` はまさにこの穴を埋めるためのものに見えるため、優先的に配線するか、J-Quants側で価格が取れるプランへの切替を検討する価値がある。

### J-Quants呼び出し回数とCIタイムアウトの余裕度が未検証（重要度: 低）

`min_interval=12.2秒` のペーシングで、universe取得（ページネーション）+ `deep_candidates=25` 件の財務取得を直列実行する。universeが3000銘柄超で複数ページに分かれる場合、ページ取得もペーシング対象になるため、yfinance側のバッチ取得時間と合わせて `.github/workflows/inflection_shadow.yml` の `timeout-minutes: 45` にどれだけ余裕があるか、実測ログで確認しておくとよい。

### 分析手法そのものについて

- スコアリング・OVEREXTENDED判定・データ健全性チェックのロジック自体は妥当で、将来情報混入を避ける設計（前年同期のみYoY比較、財務は約12週遅延を明記、Trailing Stopは確定HWMベース）がきちんと実装されている。
- Exit戦略（ATR/Chandelier、段階利確など）が未実装なのは既知の通りで、「固定Trailing Stopの優位性が確認できてから拡張する」という優先順位付けは妥当。
- ただし「forward validationの結果が残らない」問題が解決されない限り、そもそも「Trailing Stopが優位か」の検証結果を誰も見られないため、実装順序上の「out-of-sample / forward validation」は表面上「進行中」でも実質的に進捗が測れない。

## 優先度まとめ

1. forward validationの結果を人間が確認できる経路を作る — 検証の目的そのものが達成できていない
2. forward validationの価格取得にリトライ/ペーシングを追加する — 毎週の検証が壊れやすい
3. `compare_close_series` を配線するか削除する
4. yfinance単独依存のリスクを認識し、監視かフォールバックを検討する

## 検証

- `pytest`: 67 passed、coverage 90.75%
- `ruff check src scripts tests`: PASS
- `mypy`: 型スタブ未導入の警告のみ（CI実行時は `--ignore-missing-imports` で対応済みのため問題なし）
