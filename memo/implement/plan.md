# JP Inflection Shadow Scan 再試行機能 実装計画書

## 1. 目的

現在の `JP Inflection Shadow Scan` は、Yahoo Finance から最新営業日の株価が十分取得できなかった場合、

```text
DATA_HEALTH: latest market-date coverage too low
```

として失敗します。

安全装置そのものは正しいため、`MIN_LATEST_DATE_COVERAGE = 0.80` は変更しません。

今回追加するのは、一時的な外部データ遅延に対して自動再試行を行い、それでも回復しない場合だけ Slack 通知する仕組みです。

```text
初回取得
  ↓
最新データ不足
  ↓
対象銘柄だけ再取得
  ↓
まだ不足
  ↓
もう一度再取得
  ↓
それでも不足
  ↓
失敗確定 → Slack通知
```

---

## 2. 基本方針

| 項目 | 方針 |
|---|---|
| 最大試行回数 | 3回（初回 + 再試行2回） |
| 再試行対象 | 全銘柄ではなく未取得銘柄・stale銘柄（最終日が期待営業日と不一致）のみ |
| 待機時間 | 1回目 3分、2回目 7分 |
| 最新判定 | 東証の期待営業日と比較（scan開始時に一度だけ確定した基準時刻を使用） |
| 合格条件 | 価格取得率 70%以上 かつ 最新日カバレッジ 80%以上（既存の二つの health gate を両方満たす） |
| Slack通知 | 3回すべて失敗した場合のみ |
| 不完全データ保存 | しない |
| Snapshot commit | 正常時のみ |
| 想定外エラー | 原則として即失敗。外部データ由来の一時障害のみ再試行 |

GitHub Actions 自体を複数回 Re-run するのではなく、1回の Workflow 内部で回復処理まで完結させます。

---

## 3. 処理フロー

```text
GitHub Actions
        │
        ▼
JP Inflection Shadow Scan開始
        │
        ▼
J-Quantsから対象銘柄一覧取得
        │
        ▼
Yahoo Financeから株価取得
        │
        ▼
期待する東証営業日を算出（scan開始時に一度だけ確定）
        │
        ▼
価格取得率・最新日カバレッジ確認
        │
        ├── 両閾値OK（70%以上 かつ 80%以上）
        │      │
        │      ▼
        │   通常分析へ
        │
        └── いずれか未達
               │
               ▼
          3分待機
               │
               ▼
     未取得・stale銘柄だけ再取得
               │
               ▼
          カバレッジ再確認
               │
        ┌──────┴──────┐
     両閾値OK       いずれか未達
        │              │
        ▼              ▼
      続行          7分待機
                       │
                       ▼
             未取得・stale銘柄再取得
                       │
                       ▼
                  最終確認
                       │
              ┌────────┴────────┐
           両閾値OK           いずれか未達
              │                  │
              ▼                  ▼
            続行              FAILURE
                                  │
                                  ▼
                              Slack通知
```

---

## 4. 最重要の変更点

現在の `fetch_price_data()` は、

- 銘柄データそのものが取得できなかった場合は再試行する
- データは取得できたが最終日が古い場合は取得成功として扱う

という動作です。

今回のように、

```text
データは取得できた
↓
ただし最終行が前営業日のまま
↓
最新営業日のデータが未反映
```

というケースも再試行対象にします。

加えて、そもそも取得できなかった銘柄（未取得銘柄）も再試行対象に含めます。現行の最新日カバレッジは `latest_date_count / price_data_count` で計算され、分母の `price_data_count` は取得できた銘柄数のみです。そのため未取得銘柄は分母に含まれず、例えば3,700銘柄中2,500銘柄しか取得できなくてもその全てが最新営業日なら最新日カバレッジは100%となり、再試行されずに後段の `validate_report()` が価格取得率70%未満で失敗します。これを防ぐため、価格取得率（`price_data_count / universe_count`）が70%未満の場合も再試行対象とし、再取得対象は「未取得銘柄 + stale銘柄」とします。

例:

```text
expected_date = 2026-09-28

2026-09-28 : 3
2026-09-25 : 3686
```

この場合は、

```text
fresh = 3
stale = 3686
coverage = 0.1%
```

として、`stale_tickers` のみ再取得します。

再取得は `src/screening/inflection_live.py` から既存の `fetch_price_data(retry_tickers, lookback_days)` を呼び出し、`prices.update(fetch_price_data(retry_tickers, lookback_days))` で結果を置き換えるだけで実現します。`fetch_price_data()` は任意の ticker subset 取得と missing/invalid ticker の短時間 retry を既に持っているため、`src/data/yfinance_prices.py` 自体は変更しません。

---

## 5. 再試行を行う位置

現状は概ね以下です。

```text
Yahoo Finance取得
↓
テクニカル計算
↓
候補25銘柄抽出
↓
J-Quants財務情報取得
↓
report生成
↓
validate_report()
↓
失敗
```

これを以下に変更します。

```text
Yahoo Finance取得
↓
株価日付チェック
↓
必要なら再取得
↓
正常になったことを確認
↓
テクニカル計算
↓
J-Quants
↓
report生成
↓
validate_report()
```

Yahoo Finance 側の一時障害が明らかな場合、不要な後続処理を実行せず早い段階で回復を試みます。

期待営業日の判定に使う基準時刻（`generated_at`）は scan 開始時に timezone 付きで一度だけ確定し、以下の両方で同じ値を使用します。東証引け時刻をまたぐ手動実行などで、早期の再試行判定と終了時の最終判定が矛盾しないようにするためです。

- 再試行前後の `expected_tse_session_date()`
- report の `generated_at` と最終 `validate_report()`

再試行枯渇時は、価格データ取得の失敗だけを表す専用例外（`attempts`（総試行回数）を含む診断値を持つ、例: `PriceDataRetryExhausted`）を送出します。`run_inflection_shadow.py` はこの例外だけを捕捉し、環境変数 `GITHUB_OUTPUT` が設定されている場合のみ診断情報を追記してから再送出します。`GITHUB_OUTPUT` が未設定（ローカル実行など）の場合は output への書き込みを行わず、専用例外をそのまま再送出します。APIキー未設定やコード例外など他の失敗はこの例外を経由せず、即座に失敗として扱われます（`$GITHUB_OUTPUT` は書かれません）。

---

## 6. 修正対象

| ファイル | 変更内容 |
|---|---|
| `src/screening/inflection_live.py` | `MIN_PRICE_COVERAGE`・`MIN_LATEST_DATE_COVERAGE` を定義（single source of truth）。期待営業日判定、coverage計算（`universe`, `missing`, `price_coverage`, `latest_coverage`）、再試行制御、起動時の retry環境変数検証（不正なら即Failure、`PriceDataRetryExhausted`にしない）、再試行枯渇時に総試行回数 `attempts` を含む診断値を持つ専用例外（例: `PriceDataRetryExhausted`）の送出 |
| `scripts/run_inflection_shadow.py` | `MIN_PRICE_COVERAGE`・`MIN_LATEST_DATE_COVERAGE` は `inflection_live` から import して使用（重複定義しない）。`PriceDataRetryExhausted` のみを捕捉し、`GITHUB_OUTPUT` が設定されている場合だけ診断情報（`expected_date`, `universe`, `missing`, `price_data`, `price_coverage`, `latest_coverage`, 未達gate, `attempts`）を書き出して再送出する（未設定なら書かずそのまま再送出）。それ以外の例外は output を書かず即失敗させる |
| `.github/workflows/inflection_shadow.yml` | scan step に `id: scan` を付与。Slack通知 step の条件を `failure() && steps.scan.outputs.retry_exhausted == 'true' && env.SLACK_WEBHOOK_URL != ''` に限定し、本文に `$GITHUB_OUTPUT` の診断情報（`steps.scan.outputs.attempts` を含む）を含める |
| `tests/test_inflection_live.py` | coverage回復テスト追加、`PriceDataRetryExhausted` の送出条件テスト追加、stale/未取得銘柄の再取得に既存 `fetch_price_data()` を使うテスト追加 |
| `tests/test_shadow_health.py` | 最終的に異常データを拒否することを確認 |

---

## 7. 再試行設定

再試行回数と待機時間は環境変数化します。

```text
INFLECTION_PRICE_RETRY_COUNT=2
INFLECTION_PRICE_RETRY_WAIT_SECONDS=180,420
```

意味:

```text
初回
↓
180秒（3分）
↓
Retry #1
↓
420秒（7分）
↓
Retry #2
```

コード内に固定値で埋め込まず、将来調整できるようにします。

起動時に以下を検証し、不正なら待機せず設定エラーとして即 Failure とします。この失敗は `PriceDataRetryExhausted` にせず、Slack 通知対象にも含めません（外部データ障害と区別するため）。

- retry count は 0 以上の整数
- wait は retry count と同数
- 各 wait は 0 以上の数値

---

## 8. ログ改善

### 初回異常時

```text
DATA_HEALTH_RETRY:
attempt=1/2
expected_date=2026-09-28
universe=3704
missing=1200
price_data=2504
price_coverage=67.6%
fresh=3
latest_coverage=0.1%
failed_gate=price_coverage,latest_coverage
wait=180s
```

### Retry #1 後

```text
DATA_HEALTH_RETRY:
attempt=2/2
expected_date=2026-09-28
universe=3704
missing=54
price_data=3650
price_coverage=98.5%
fresh=2450
latest_coverage=67.1%
failed_gate=latest_coverage
wait=420s
```

### 回復時

```text
DATA_HEALTH_RECOVERED:
attempt=2
universe=3704
missing=14
price_data=3690
price_coverage=99.6%
fresh=3690
latest_coverage=100.0%
```

GitHub Actions のログだけで、どの段階でどこまで回復したか、どの gate（`price_coverage` / `latest_coverage`）が未達だったか確認できるようにします。

---

## 9. Slack 通知方針

途中の失敗では通知しません。

```text
初回失敗
→ 通知なし

Retry #1失敗
→ 通知なし

Retry #2成功
→ 通知なし
→ Workflow Success
```

価格データの再試行が3回とも枯渇した場合（`retry_exhausted == 'true'`）のみ、

```text
Workflow Failure (retry_exhausted=true)
↓
Slack通知
```

とします。APIキー未設定・schema不整合・コード例外など他の failure では通知しません。Workflow step の条件を `failure() && steps.scan.outputs.retry_exhausted == 'true' && env.SLACK_WEBHOOK_URL != ''` に限定することで実現します。

### 通知例

```text
⚠️ JP Inflection Shadow Scan FAILED

株価データの取得が回復しませんでした。

expected: 2026-09-28
universe: 3704
missing: 1200
price_data: 2504
price_coverage: 67.6% (< 70%)
latest_coverage: 99.6% (>= 80%)
failed_gate: price_coverage
attempts: 3  ({{ steps.scan.outputs.attempts }} を参照。固定値ではなく `INFLECTION_PRICE_RETRY_COUNT` に応じて可変)

GitHub Actions:
https://github.com/.../actions/runs/...
```

未達だった gate（`price_coverage` / `latest_coverage`）を明示し、最新日カバレッジが正常でも価格取得率不足で失敗した場合に誤った理由を通知しないようにします。

---

## 10. エラー種別ごとの扱い

| エラー | 処理 |
|---|---|
| Yahoo 最新日不足 | 自動再試行 |
| Yahoo 一時通信失敗 | 自動再試行 |
| 一部 ticker 取得失敗 | 現在の ticker 単位 retry |
| J-Quants 一時通信エラー | 今回の対象外。現状どおり即 Failure（回数・待機・対象例外が未定義のため、必要になれば別計画で対応） |
| APIキー未設定 | 即 Failure |
| 暗号化キー未設定 | 即 Failure |
| Schema不整合 | 即 Failure |
| コード例外 | 即 Failure |
| retry設定（環境変数）不正 | 即 Failure（設定エラー、`PriceDataRetryExhausted`にせずSlack通知対象外） |

「待てば直る可能性がある外部データ障害」だけを再試行対象にします。

---

## 11. 安全装置

以下の閾値は維持します。`MIN_PRICE_COVERAGE` と `MIN_LATEST_DATE_COVERAGE` は `src/screening/inflection_live.py` に定義し、`scripts/run_inflection_shadow.py` はそこから import して使う single source of truth とします（値を複製しません）。

```python
MIN_UNIVERSE_COUNT = 3000
MIN_PRICE_COVERAGE = 0.70
MIN_TECHNICAL_COVERAGE = 0.60
MIN_LATEST_DATE_COVERAGE = 0.80
```

また、再試行中の不完全データについては以下を行いません。

```text
inflection_candidates.enc 更新
snapshot 作成
Git commit
```

正常性確認後にのみ保存します。

---

## 12. 必須テスト

### 1. 初回正常

```text
99% coverage
→ retryなし
→ success
```

### 2. 1回目で回復

```text
0.1%
→ Retry #1
→ 99%
→ success
```

### 3. 2回目で回復

```text
0.1%
→ 60%
→ 99%
→ success
```

### 4. 最後まで回復しない

```text
0.1%
→ 5%
→ 10%
→ failure
→ Slack通知対象
```

### 5. stale銘柄のみ再取得

```text
3704銘柄中100銘柄だけ stale
→ 100銘柄だけ再取得
```

### 6. 保存防止

最終 Failure の場合、

```text
snapshot
latest
```

を更新しないこと。

### 7. 休日

土日・東証休場日は直前営業日を正常な最新日として扱うこと。

### 8. 設定ミス

APIキーや暗号化キーの異常は待機せず即 Failure とすること。`INFLECTION_PRICE_RETRY_COUNT` / `INFLECTION_PRICE_RETRY_WAIT_SECONDS` が不正（負数・非整数・個数不一致）な場合も同様に、待機・再試行せず即 Failure とし、`PriceDataRetryExhausted` にせず Slack 通知対象にも含めないこと。

### 9. 未取得銘柄を含むカバレッジ回復

```text
3704銘柄中1200銘柄が未取得（price_dataに含まれない）
→ price_coverage = 2504 / 3704 = 67.6%（< 70%）のため最新日カバレッジが100%でも再試行される
→ 未取得銘柄を再取得
→ price_coverage 70%以上・latest_coverage 80%以上で success
```

### 10. 想定外エラーでは通知しない

```text
APIキー未設定などscan前に失敗
→ retry_exhausted は書き込まれない
→ Slack通知されない（Workflow Failureのみ）
```

### 11. GITHUB_OUTPUT 未設定環境

```text
ローカル実行など GITHUB_OUTPUT 未設定
→ 再試行枯渇時、output書き込みをスキップ
→ PriceDataRetryExhausted をそのまま再送出（元の例外を握り潰さない）
```

---

## 13. 完成後の動作イメージ

```text
初回取得
latest coverage = 0.1%

↓ 自動判断

3分待機

↓

Retry #1
latest coverageを再確認

↓ まだ不足

7分待機

↓

Retry #2

├─ 回復
│   → 通常処理
│   → snapshot保存
│   → Success
│   → Slackなし
│
└─ 回復しない
    → snapshot保存しない
    → Workflow Failure
    → Slack通知
```

---

## 14. 完了条件

以下をすべて満たしたら実装完了とします。

- 価格取得率または最新日カバレッジが閾値未満のとき自動再試行される（未取得銘柄が多い場合を含む）
- 未取得銘柄・stale銘柄のみ再取得される
- 期待営業日の基準時刻（`generated_at`）が scan開始時に一度だけ確定され、再試行判定と最終reportで同一の値が使われる
- 初回の一時的な外部データ遅延では Slack 通知されない
- 価格データの再試行が3回とも枯渇した場合（`retry_exhausted == 'true'`）のみ Slack 通知される。APIキー未設定・schema不整合・コード例外など他の failure では通知されない
- Slack通知・ログの診断情報に `universe`, `missing`, `price_coverage`, `latest_coverage`, 未達 gate が含まれ、最新日カバレッジが正常でも価格取得率不足で失敗した場合に誤った理由が通知されない
- 価格データ再試行枯渇のみを表す専用例外で失敗詳細が `run_inflection_shadow.py` へ伝搬し、他の例外はこの経路を通らない（終了コードは維持される）
- `GITHUB_OUTPUT` が未設定（ローカル実行など）でも `PriceDataRetryExhausted` が握り潰されずそのまま再送出される
- `price_coverage = price_data / universe`・`latest_coverage = fresh / price_data` の定義と閾値（70%・80%）が計画・ログ・Slack通知例・テストで統一されている
- Slack通知の `attempts` は `PriceDataRetryExhausted` → `$GITHUB_OUTPUT` → `steps.scan.outputs.attempts` を経由した実際の総試行回数であり、`INFLECTION_PRICE_RETRY_COUNT` の変更時も固定値化・誤報しない
- retry環境変数（`INFLECTION_PRICE_RETRY_COUNT` / `INFLECTION_PRICE_RETRY_WAIT_SECONDS`）が不正な場合は起動時に即Failureとなり、`PriceDataRetryExhausted` にもSlack通知対象にもならない
- 不完全な snapshot が保存されない
- `MIN_LATEST_DATE_COVERAGE = 0.80` と `MIN_PRICE_COVERAGE = 0.70` は `src/screening/inflection_live.py` に単一定義され、`scripts/run_inflection_shadow.py` はそれを import して使う
- 既存テストと追加テストがすべて通る
- 正常時の既存 Workflow の挙動を壊さない
