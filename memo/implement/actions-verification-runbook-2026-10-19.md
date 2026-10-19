# GitHub Actions での実環境確認・baseline 測定 手順書（2026-10-19）

> 対象: ISSUE-15〜21 と D1〜D3 の修正（コミット済み）。鍵（`SNAPSHOT_ENCRYPTION_KEY` など）は GitHub Secrets にしか無いので、実データの確認はすべて Actions 上で行う。
> 原則: **本番 secret を使う job は main でしか動かない**（修正済み）。ブランチでは動作確認できないため、main に入れた後に確認する。各手順の「期待」と違えば、その場で止めて報告する。

## 0. 事前（ローカル）

1. 修正が main にある（`git log origin/main` に今回のコミットがある）。
2. Actions の Secrets に `SNAPSHOT_ENCRYPTION_KEY`・`SLACK_WEBHOOK_URL`・J-Quants/Sheets 用の既存 secret がある（新規は不要）。
3. 作業中に `data:` の自動コミット（scan の snapshot）が main に積まれるので、`git pull --rebase` してから作業する。

## 1. CI（test.yml）— 権限と全テスト

- **操作:** main への push（またはこのコミットを含む PR）で `Test` が自動で走る。
- **見る所:** Actions → Test → 最新の run。
- **期待:** 成功。ログに ruff・mypy（既知 31 件のみ）・pytest（約 1150 件）が通る。`permissions` は `contents: read` のみ（run の "Set up job" の `GITHUB_TOKEN Permissions` に `Contents: read` だけ）。
- **失敗時:** mypy が 31 件を超える/テスト失敗なら、ローカルとの差（Python バージョン、依存）が原因。ログの該当行を共有。

## 2. PR とブランチ実行で本番鍵が使われないこと（ISSUE-17）

1. 作業ブランチを push し、Actions → **Forward Validation** → Run workflow で **branch = そのブランチ** を選んで実行。
2. **期待:** `Validate accumulated encrypted snapshots` step が **skipped**（鍵の step が動かない）。テスト step は成功。`JP Inflection Shadow Scan` も同様に、ブランチから実行すると `scan` job が skipped。
3. **失敗の判定:** どちらかの step が実行された（skipped でない）場合は P1。直ちに報告。

## 3. scan の main 限定と失敗通知（Q05/Q07、依存なし起動）

1. Actions → **JP Inflection Shadow Scan** → Run workflow、**branch = main**、`resend_digest = false` で実行（平日 16:40 JST 以降、市場日の終値が出てからが望ましい）。
2. **期待:**
   - `scan` が成功し、`data: record encrypted JP inflection shadow scan [skip ci]` の自動コミットが main に出る（すでに当日分があれば snapshot は増えず、ログに `snapshot_created=False`）。
   - ログの最終行に `digest=...` が出る。再送がある日は `digest_recovery=sent:N,failed:N,skipped:N`（0 件のときは出ない）。**ticker・会社名・URL・鍵は出ない**。
   - 失敗通知 job（`notify-failure`）が動かない（scan が成功しているため skipped）。
3. 失敗通知の実機確認（任意）: scan を意図的に失敗させる必要があるので、通常は行わない。`reliability_watchdog.yml`（毎日 20:10 JST）を **Run workflow（main）** で手動実行し、依存なしの Python で完走することを確認する。

## 4. pending ダイジェストの回収（ISSUE-18/21）

前日分が `pending` でなければ起きないので、機会があったときに確認する（人為的に作らない）。

- ログに `digest_recovery=sent:1,failed:0,skipped:0` が出て、Slack に前日付のダイジェストが 1 通届く。次の run では再送されない。
- `::warning title=Recovered digest state not saved` が出たら、送信済みだが状態が保存できていない。次の run で重複するので、`dashboard/data/inflection/digest_state.json` を確認する（`digest_state.json` は repo 内。手で `succeeded` にする場合は別途相談）。
- `::warning title=Daily digest state not saved`（当日分）も同様。

## 5. Forward Validation（main）— 要約の取得

1. Actions → **Forward Validation** → Run workflow、**branch = main**。
2. **期待:** 成功。`Validate accumulated encrypted snapshots` が実行される（main なので鍵が渡る）。
3. 完了後、run の Artifacts から `inflection-forward-summary`（`inflection_forward_validation_summary.json`）をダウンロードして保管する。ここに公開用の集計だけが入る（取引単位の行・ticker は入らない）。
4. **見る所:** 超過収益の評価件数、`benchmark_comparable`（ETF と比較できた件数）と評価済み件数の差。**D1 により、ETF の日付が揃わない取引は比較不能になる**ので、差が大きければ ETF 側の欠測頻度が高い証拠。

## 6. learning（週次）— 要約の取得

- learning は **日曜 09:30 JST の schedule のみ**（`github.event_name == 'schedule'`）。手動では動かない。
- 次の日曜の run が終わったら、Artifacts の `inflection-learning-summary`（`inflection_learning_summary.json`）を保管する。
- **見る所:** 各 horizon の `outcome_coverage`（`unresolved_matured`・**`benchmark_unpaired`**・`benchmark_comparable`）と、昇格候補（lessons）の有無。h60・h120 で保留が多いのは想定内（`docs/playbooks.md` 参照）。
- 手動で実行したい場合は、workflow の `if: github.event_name == 'schedule'` を `|| github.event_name == 'workflow_dispatch'` にする小さな変更が要る（secret を使う step なので、main 限定の条件は維持すること）。必要なら依頼してほしい。

## 7. baseline の再生成と比較

既存の baseline: `.harness/reports/reliability-baseline-2026-10-13.{md,json}`（コミット `3e9b930`、**実データ指標は鍵が無いため UNAVAILABLE**）。

1. 上の 5・6 で取った Forward / learning の要約を、**今回の baseline の実データ欄**として保存する（`.harness/reports/` に日付つきで保存。ticker・本文を含めない）。
2. 比較する指標（変更が見込まれるもの）:

| 項目 | 見る値 | 期待される変化 |
|---|---|---|
| ISSUE-03（6 銘柄の特徴量） | 該当 ticker の特徴量（鍵のある環境でのみ） | 値が変わる（baseline-changing） |
| ISSUE-07（learning の超過収益） | 平均超過収益 | 一律で約 0.15pt 低下 |
| C04 の 2 件 | `unevaluated`・`unresolved_matured` | 欠落がある場合に未評価が増える |
| D1（ETF 日付完全一致） | `benchmark_comparable` / 評価済み | ETF 欠測があれば比較可能件数が減る |
| D3（learning） | `benchmark_unpaired`、昇格の有無 | 比較不能があれば当該 horizon が保留 |

3. **historical の kill criterion（pass/fail/incomplete）の実測は、Actions 上の workflow が無いので現状できない。** `scripts/run_inflection_historical_backtest.py` は J-Quants の履歴キャッシュ（`--fetch` で取得、数日分の API 呼び出し）を前提とする。実測したい場合は、専用の手動 workflow（main 限定、secret は既存のものを使用、成果物は集計 JSON のみ）を新規に作る必要がある。**設計と実装は別作業になる**ので、必要なら依頼してほしい。それまでの kill criterion は合成データのテストでのみ確認済み。

## 8. 結果の記録と判断

- 確認結果（各手順の期待どおりか、ログの該当行、run の URL）を `.harness/reports/` に日付つきで 1 ファイルにまとめる。秘密情報は書かない。
- 次の判断:
  - 1〜6 が期待どおり → 保守修正は完了。7 の比較で baseline を確定し、Growth（G01〜G07）の着手を判断する。
  - D1/D3 で `benchmark_comparable` が大きく減る、または h5/h20 の昇格が常に保留 → 規則の見直しが先（Claude が proposal を作り、Codex が確認）。

## 付録: 触らないこと

- `data:` の自動コミット、`digest_state.json`、暗号化 snapshot（`dashboard/data/inflection/`）は手で編集しない。
- 手動実行は main の通常手順だけ。再送（`resend_digest=true`）は、当日分の再送が必要な場合に限る（重複送信になる）。
- Position Monitor の確認（1 分足の保持期間、日足保守判定の頻度）は本書の範囲外。`position_monitor.yml` の通常実行のログで、`recovered_daily_possible_touch` の出る頻度を観察する。
