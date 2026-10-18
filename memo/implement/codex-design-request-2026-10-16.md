# Codex への設計協議の依頼: 比較不能・未評価の結果を、判定にどう反映するか（2026-10-16）

> 目的: 設計判断が要る 3 項目について、**実装の前に**設計案を Codex と詰める。実装は決定後に Claude が `verify-before-fix` で行い、Codex が独立に検証する。
> 単独で直せる項目（ISSUE-15〜21）は [issues-2026-10-16.md](issues-2026-10-16.md) で `verify-before-fix` に渡すので、本書では扱わない。

## 0. 今回の依頼の範囲

- **やってほしいこと**: 下記の設計問題について、選択肢の比較・推奨案・受入条件（テストの観点）を、設計メモとして `.harness/reports/` に出す。**コードは変更しない。**
- **やらないこと**: 実装、新しい特徴量、スコア・重み・Q06 閾値（ticker 10 / signal date 5 / 最大業種比率 50%）の変更、Growth（G01〜G07）。
- 実 API・Slack・Sheets・保存済み snapshot・archive には触れない。実データの集計は、既存のローカルキャッシュ（`.data/jquants/`）の読み取りに限る。

## 1. 背景（なぜ設計が要るか）

元の監査（Codex、2026-10-13）の C04 は「欠測・未評価を、都合よく判定から除外してはならない」だった。これに応えて 2 つの修正をした。

- ISSUE-02: historical の kill criterion は、成熟した未評価が 1 件でもあれば `incomplete`（判定保留）にする（[kill_criterion](../../src/evaluation/inflection_historical.py#L513)、[unresolved_matured_h60](../../src/evaluation/inflection_historical.py#L478)）。
- learning の昇格判定も、成熟した未評価があれば昇格を保留する（[inflection_learning.py:737](../../src/evaluation/inflection_learning.py#L737)、Stage 3C で導入済み）。

その後の再調査で、**この「1 件でも保留」の規則が、実データでは判定を止めてしまう**ことと、**比較不能（ETF 側の欠測）が保留の数に入っていない**ことが分かった。両方を満たす設計が必要になった。

## 2. 設計問題（3 項目）

### D1（Codex #1・P1）ETF の欠測時に、比較期間が変わるのに超過収益を確定する

- **現象**: 株の価格は完備でも、TOPIX ETF（1306.T）がその取引の退出日を欠くと、ETF の退出日が前営業日にずれる。それでも超過収益を計算する。監査時点でも現在でも再現する（コードは無変更）。再現の例: 株の退出 2026-03-30、ETF が 3/30・3/31 を欠くと ETF は 3/27 を使い、`excess_return_pct` を返す。
- **コード**: [paired_benchmark_returns](../../src/evaluation/inflection_forward.py#L177)（行 204・205: entry 以降の最初の Open と、exit 以前の最後の Close を使う）。historical の `h60_excess_pairs` / `_lag_report` から呼ばれる。forward・learning も同じ関数を使う。
- **背景**: C05（Stage 1）で、「TOPIX 比較を、株の実際の entry / exit 日に合わせる」ようにした。しかし、ETF 側にその日の価格が無い場合の扱いは決めていなかった。

### D2（Codex #2・P1）ETF 不足で比較できない成熟結果が、kill 判定の保留に数えられない

- **現象**: 株は完備、ETF が 70 営業日で終了。異なる 3 銘柄で h60 が成熟し、ETF との比較ができるのは 2 件だけ。それでも `independent_trades=3 / valid_pairs=2 / unresolved_matured=0 / verdict=pass`。
- **コード**: `unresolved_matured_h60` は、株の `net_return_pct is None` だけを数える。`_valid_pairs` は、不明な超過収益を黙って除外する（[inflection_historical.py:509](../../src/evaluation/inflection_historical.py#L509)）。
- **ISSUE-02 との関係**: ISSUE-02 の修正は、株側の未評価だけを数えた（C04 の一部しか直していない）。

### D3（Claude 再調査 2-1）「1 件でも保留」だと、実データで判定が出なくなる

- **現象（実キャッシュで計測）**: 422 営業日（2024-10-09〜2026-07-03）の普通株のうち、売買代金 1 億円以上の（ticker, 日）で、**価格系列が horizon の途中で途切れる**確率:

  | horizon | 1 件あたり | 100 件中 1 件以上 | 625 件（learning 約 25 日分） | 2,500 件（約 100 日分） |
  |---|---|---|---|---|
  | h5 | 0.051% | 5.0% | 27.3% | 72.1% |
  | h20 | 0.188% | 17.2% | 69.2% | 99.1% |
  | h60 | 0.652% | 48.0% | 98.3% | 100% |
  | h120 | 1.483% | 77.6% | 100% | 100% |

  （集計は、売買代金 ≥ 1 億円の日の観測を対象に、価格系列の最終日が、その日 + horizon + 1 営業日より前である割合。上場廃止・TOB・合併を区別できない。キャッシュ内で価格系列が途切れた銘柄は 388。EARLY 候補に限った率は未測定。）
- **影響**: 
  - kill criterion: 有効な組が `min_independent`（既定 100）以上必要。EARLY が数百件なら、h60 で 1 件以上が途切れる確率は 85〜100% で、`pass`/`fail` が出ない（停止ルールとして機能しない）。
  - learning: 深掘り候補（1 日 25 件）の h60・h120 は、約 25 日分でほぼ確実に保留される。昇格候補（lessons）が出なくなる。
- **背景**: provider（J-Quants・yfinance）は、価格系列が途切れた理由（上場廃止・TOB・売買停止・データ欠損）のメタデータを提供しない。コード上は、`price_status` メタデータ（`permanent_termination` / `trading_halt`）があれば理由を区別するが、現在の provider はこれを供給しない（[inflection_backtest.py の `_price_diagnostics`](../../src/evaluation/inflection_backtest.py#L87)）。

## 3. 設計上の制約（守ること）

1. **未評価・比較不能を、黙って除外しない**（C04・C05・B06 の方針）。楽観方向への歪みを入れない。
2. 一方で、**判断が永久に出ない設計にもしない**（D3）。「保留」は、理由と規模が分かる形で出す。
3. forward・historical・learning で、同じ事象に対して**同じ規則**を使う（C01〜C08 以来の整合性）。共有の関数（`paired_benchmark_returns`、`_outcome_coverage`、`kill_criterion` など）の変更は、3 経路への影響を明示する。
4. 既存の出力のキー・数値を変える場合は、baseline-changing として列挙する（レポートは、プロジェクト完成時に再生成する前提。キーの追加は許容）。
5. スコア・閾値・重み・Q06 閾値は変更しない。`DEFAULT_MIN_INDEPENDENT`（100）も変更しない。
6. 新しい外部データ源・新 provider・新しい依存は導入しない。
7. 前回の教訓: 欠損・不正な型・複数日にまたがる境界を、受入条件（テスト）に含める。

## 4. 検討してほしい論点

### D1 / D2: 比較不能の扱い

- ETF の価格が、株の実 entry / exit と**同じ日**に無いとき、比較収益を「不明」とするか、最も近い日で代用するか（代用するなら許容する日数の上限と、その旨をレポートに記録するか）。
- 「不明」を、`excess_return_pct=None` で返すだけで足りるか。足りないなら、**比較不能の理由**（`benchmark_entry_missing` / `benchmark_exit_missing` など）を、診断に残すか。
- 比較不能な成熟結果を、kill criterion の保留の数（`unresolved_matured`）に含めるか。含めるなら、「株側の未評価」と「ETF 側の比較不能」を別に数えるか（原因が違うため）。
- 市場別ベンチマーク（グロースの 2516.T など、[_market_benchmark_excess](../../src/evaluation/inflection_report.py#L156)）にも同じ規則を適用するか。
- 代案: historical の入口で、必要な ETF 期間の完全性を保証し、不足なら**拒否**する（Codex #1 の最小修正案の後半）。この場合、実行が止まるのは許容できるか。

### D3: 「保留」の規則

候補（組み合わせも可）:

- (a) **割合の閾値**: 成熟した未評価の割合が閾値以下なら判定する。閾値は実データの終了率（h60 で約 0.65%）を踏まえて決める。ただし閾値は新しい「調整可能なパラメータ」になるので、恣意性をどう抑えるか。
- (b) **感度分析の併記**: 判定は出し、未評価を「最悪（損失）に置いた場合」「最良に置いた場合」の 2 通りで判定が覆るか（`robust` / `fragile`）を併記する。保留はしない。
- (c) **最悪ケースを仮定**: 未評価を、保守的な値（例: そこまでの最後の終値で退出、または -100%）に置いて判定する。楽観方向の歪みは出ないが、上場廃止以外（TOB の高値など）を悲観的に扱う歪みが出る。
- (d) **理由別の扱い**: 価格系列の終了を、`price_status` メタデータがあれば `permanent_termination`（損失扱い）と `trading_halt`（保留）に分け、メタデータが無い場合だけ保留とする。現在は provider がメタデータを出さないので、効果は限定的。
- (e) **現状維持**（1 件でも保留）＋ 保留の規模を、レポートの先頭に分かりやすく出す。判定は出ない前提を明示する。

kill criterion と learning で、同じ規則にするか、別の規則にするか（kill criterion は停止ルール、learning は昇格の提案で、誤りの費用が異なる）。

## 5. 依頼する成果物

`.harness/reports/reliability-design-unresolved-2026-10-16.md` に、次を出してください。

1. D1〜D3 それぞれの**推奨案**と、検討した選択肢の比較（長所・短所・楽観方向の歪みの有無）。
2. D3 について、実キャッシュで**影響を試算**した結果（読み取りのみ）。例: 各案で、h60・h120 の保留率・判定が出る割合、EARLY 候補での終了率（可能なら）。
3. 変更が必要な**関数・出力キー**の一覧（forward・historical・learning それぞれ）と、baseline-changing になる項目。
4. **受入条件（テストの観点）**: 欠損・不正な型・複数日・3 経路の整合を含める。修正前に失敗するテストの具体例。
5. 判断がユーザーに委ねられる点（閾値の値、拒否か代用か、など）を、選択肢と推奨つきで分けて列挙。
6. 実装の分割案（`verify-before-fix` で 1 件ずつ扱える単位）と、その順序。

## 6. このあとの流れ

1. Codex が設計メモを出す。
2. ユーザーが、設計メモの「判断が委ねられる点」を決める。
3. Claude が、決定に基づき要件書を作り、`verify-before-fix` で 1 件ずつ実装する。
4. Codex が、実装後に**独立に検証**する（今回の独立監査と同じ形式。特に、欠損・型・複数日の境界と、3 経路の整合）。
5. 鍵のある環境で baseline を再生成する（Growth の前に必須）。

## 7. 参考

- 元の監査: [reliability-final-audit-2026-10-13.md](../../.harness/reports/reliability-final-audit-2026-10-13.md)（C04・C05）
- Codex の独立監査: [reliability-independent-audit-2026-10-16.md](../../.harness/reports/reliability-independent-audit-2026-10-16.md)（#1・#2）
- Claude の再調査: [reliability-final-audit-recheck-2026-10-16.md](../../.harness/reports/reliability-final-audit-recheck-2026-10-16.md)（2-1）
- Codex の再現コード: `.harness/runtime/reliability-independent-2026-10-16/`（`test_evaluation_repro.py`、`evaluation_review.md`）
