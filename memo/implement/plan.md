# Position Exit Monitor（保有銘柄の売却タイミング通知）

計画作成日: 2026-09-08

## Context

現在の `trader` は買い候補の発見（`scripts/run_inflection_shadow.py`）とバックテスト上の出口ルール検証（`scripts/rebuild_inflection_forward_validation.py`）はあるが、**実際に手動で購入した保有銘柄をリアルタイムに近い形で見張って「そろそろ売り時」と知らせる仕組み**が無い。

ユーザーは以下を決定済み:
- 証券会社は **SBI証券**。ただしSBIには個人向けリアルタイム/発注APIが無く、かつ**自動売買はしない**（売買は常にユーザーが手動でSBI証券上で行う）ため、証券会社側のAPI連携は一切不要。
- 保有銘柄の管理は **Excel/VBA不可（自宅PCで使えない）なのでGoogleスプレッドシート**を使いたい。
- 通知は **Slack**（このリポジトリに既にある `SLACK_WEBHOOK_URL` を流用）。
- チェック頻度は **GitHub Actionsの負荷を抑えることを優先**し、頻度を上げるより「重要なタイミングで確実に」を優先 → 平日 **9:00 / 12:35 / 15:35 JST** の3回（寄り付き・後場寄り・大引け）。

この機能は既存の本番scan/forward validationパイプラインとは完全に独立した追加機能であり、既存コードへの変更は最小限（既存ヘルパーの再利用のみ）にする。

## 全体構成

```
src/monitoring/__init__.py              (新規, 空)
src/monitoring/position_exit.py         (新規, 純粋ロジック)
src/data/live_quote.py                  (新規, Exit monitor専用の実勢価格・現在値取得)
src/data/sheets_client.py               (新規, Google Sheets I/O)
scripts/run_position_monitor.py         (新規, オーケストレーション)
.github/workflows/position_monitor.yml  (新規, スケジュール実行)

tests/test_position_exit.py             (新規)
tests/test_live_quote.py                (新規)
tests/test_sheets_client.py             (新規)
tests/test_run_position_monitor.py      (新規)

pyproject.toml                          (編集: 依存追加 gspread, google-auth)
.env.example                            (編集: 変数追加)
README.md                               (編集: セクション追加)
.github/workflows/test.yml              (編集: mypy対象ファイルに追加)
```

既存の本番scanパス（`src/screening/`, `src/strategy/`, `src/evaluation/`, `.github/workflows/inflection_shadow.yml` など）は一切変更しない。

## 1. `src/monitoring/position_exit.py`（純粋ロジック）

`src/evaluation/inflection_backtest.py` の `_true_max_drawdown_pct()`（51行目）を直接importして再利用する（内部関数だが同一リポジトリ内なので直接参照でよい、importの上に一行コメントで理由を残す）。`_series()` はスキャナー/バックテスト固有の調整型（Adj Close置換済み）を前提にしているため本モジュールでは使わず、`src/data/live_quote.py`（Section 2a）が実勢価格ベースの同等整形を行う。

**レビュー対応（P1: 実約定単価との尺度不一致／現在値の鮮度／backtestとの乖離）**: 既存 `simulate_signal()` が検証しているTrailing Stopは「前日までの確定済み日次HighをHWMとし、当日Openのgapと当日LowのStop到達で判定する」ルールである。本モジュールは無期限ポジション・単発チェック向けに**同じ判定式**を適用する（Closeの最大値・最新Closeだけで判定する簡易版は採用しない）。また `entry_price` とHigh/Low/Closeは、配当調整を含まない実勢価格ベースで揃え、分割のみを `src/data/live_quote.py` 側で補正済みの値を受け取る契約とする（本モジュール自身は補正しない）。

```python
@dataclass(frozen=True)
class PositionStatus:
    ticker: str
    entry_date: str
    entry_price: float           # 分割調整済み・配当調整なしの実勢価格スケール
    as_of_at: str                 # ISO8601 (JST) — 現在値（分足データ）の取得時刻
    quote_source: str             # 例: "yfinance_1m_bar"
    current_price: float
    high_water_mark: float        # entry_price と「前日までの確定済み日次High」の最大値
    stop_price: float
    trailing_stop_pct: float
    unrealized_pct: float
    distance_to_stop_pct: float
    max_drawdown_pct: float | None
    triggered: bool
    exit_reason: str | None       # "trailing_gap" | "trailing_stop" | None（未発動）

def evaluate_position(
    entry_price: float,
    entry_date: str,
    prior_confirmed_highs: pd.Series,   # entry日以降・JSTの当日より前だけ、分割調整済み日次High
    prior_confirmed_closes: pd.Series,  # drawdown計算用、同じ調整基準・同じ当日除外
    today_quote: TodayQuote,            # src/data/live_quote.py の型
    trailing_stop_pct: float,
    evaluated_at: datetime,             # 判定基準時刻（呼び出し側が渡す、システム時計を直接読まない）
    ticker: str,
) -> PositionStatus: ...
```

ロジック（`simulate_signal()` のTrailing Stop分岐と同じ判定式を単発チェックへ適用）:

1. `prior_confirmed_highs` が空なら `high_water_mark = entry_price`、非空なら `high_water_mark = max(entry_price, float(prior_confirmed_highs.max()))`（`pd.Series.max()` に `default` 引数は無く`TypeError`になるため、空判定を明示的に分岐する）
2. `stop_price = high_water_mark * (1 - trailing_stop_pct / 100)`
3. `today_quote.open <= stop_price` なら `triggered=True, exit_reason="trailing_gap"`（backtestのgap扱いと同じく当日始値で判定）
4. そうでなく `today_quote.low_so_far <= stop_price` なら `triggered=True, exit_reason="trailing_stop"`
5. どちらでもなければ `triggered=False, exit_reason=None`
6. `current_price = today_quote.last_price` を基準に `unrealized_pct`/`distance_to_stop_pct` を算出
7. `max_drawdown_pct` は `_true_max_drawdown_pct(entry_price, prior_confirmed_closes に today_quote.last_price を追加した系列)` で算出

**鮮度チェック（純粋関数として決定的にする）**: `today_quote` が取得できない、または `evaluated_at - today_quote.as_of_at` が `STALE_QUOTE_THRESHOLD_MINUTES`（`live_quote.py`で定義、既定60分）を超えている場合、`evaluate_position` は判定せず `StaleQuoteError`（`ValueError`のサブクラス）を送出する。`evaluated_at` は関数の外（オーケストレーション側）が生成して引数で渡し、関数内でシステム時計を直接読まない（純粋関数・テストの決定性を保つ）。呼び出し側はこれを監視エラーとして扱い、`triggered=False` へ黙ってフォールバックしない（見逃し防止）。

**検証根拠の明記（backtestとliveの価格基準の相違）**: `scripts/rebuild_inflection_forward_validation.py::_fetch_adjusted_histories()` は `yf.Ticker.history(auto_adjust=True)` を使い、配当調整と分割調整の両方を含むOHLCでbacktestする。一方live monitorは実約定単価と比較するため「配当調整なし・分割のみ補正」のOHLCを使う（Section 2a）。判定式（HWM・gap・Low到達）は同一でも**価格基準が異なる**ため、既存および将来のforward validationの10%/15%/20% Trailing Stop成績を**そのままlive monitorの根拠にはできない**（配当落ち付近で発動日・成績が変わり得るため）。したがって `DEFAULT_TRAILING_STOP_PCT = 15.0` は、配当調整なし基準での専用検証が別途行われるまで**「検証済みの売り時シグナル」ではなく「検証用アラート」**として扱う（配当調整なし基準でのforward validation追加は本計画のscope外とし、別途検討する）。この文言はSlackメッセージ・README（Section 3, 5）に明記する。

バリデーション: `entry_price`・`trailing_stop_pct`・`today_quote`の`open`/`high_so_far`/`low_so_far`/`last_price`はいずれも有限（`NaN`/`inf`でない）かつ正であることを要求し、満たさなければ `ValueError`。`trailing_stop_pct` は `(0,100)` 範囲外も `ValueError`。呼び出し側（オーケストレーション）が行単位でキャッチし、その行だけ `error`/`stale` 扱いにして他行の処理は続ける（forward validationのfail-closed方針とは違う寛容なダッシュボード用途だが、全行が失敗した場合はSection 3の通りスクリプト全体を失敗させる）。

`DEFAULT_TRAILING_STOP_PCT = 15.0` を既定値として定義。

## 2. `src/data/live_quote.py` と `src/data/sheets_client.py`（外部I/O）

### 2a. `src/data/live_quote.py`（新規）— Exit monitor専用の価格取得契約

スキャナー用 `src/data/yfinance_prices.py::fetch_price_data()` は再利用しない。この関数は `Close` を配当・分割調整込みの `Adj Close` に置換するため、SBI証券での実約定単価（配当調整を含まない）とそのまま比較すると `unrealized_pct`・HWM・Stop価格が誤る。

```python
@dataclass(frozen=True)
class TodayQuote:
    open: float
    high_so_far: float
    low_so_far: float
    last_price: float
    as_of_at: str   # ISO8601, JST — 分足データの最終barのtimestamp（実データ由来、リクエスト時刻の代用は禁止）
    source: str      # 例: "yfinance_1m_bar"

@dataclass(frozen=True)
class SplitAdjustedHistory:
    entry_price: float          # entry_date より後の分割だけで補正済み
    daily_highs: pd.Series      # 各行を「その行より後に発生した分割比率の累積」で補正済み（単一ratioを全行へ適用しない）
    daily_closes: pd.Series     # 同上、drawdown計算用

STALE_QUOTE_THRESHOLD_MINUTES = 60

def fetch_split_adjusted_history(ticker: str, entry_date: str, entry_price: float) -> SplitAdjustedHistory:
    """`Ticker(ticker).history(auto_adjust=False, actions=True)` 相当で日次OHLCと分割イベント（日付・比率）を
    一度に取得し、行ごとに「その行より後の分割比率の累積」で補正した日次High/Closeと、
    entry_date より後の分割だけで補正したentry_priceを返す。Adj Closeへの置換は行わない（配当を混ぜない）。
    `fetch_raw_daily_history`/`fetch_cumulative_split_ratio`/`adjust_entry_price_for_splits` に分割せず
    1関数にまとめることで、単一ratioを全行へ誤って適用する事故を防ぐ。
    `daily_highs`/`daily_closes` にはJSTの当日より前の行だけを含め、yfinanceが返す当日の進行中日足は
    （取得結果に含まれていても）除外する。ただし当日が分割日であれば、その分割は過去行とentry_priceの
    現在尺度への補正には反映する（当日足を除外することと、当日split eventを補正に使うことは独立）。
    entry_priceが有限かつ正であることを検証し、満たさなければ ValueError。"""

def fetch_today_quote(ticker: str) -> TodayQuote | None:
    """`Ticker(ticker).history(period="1d", interval="1m", auto_adjust=False)` の最終barから
    Open（当日最初のbarのOpen）/High・Low so far（当日barの最大・最小）/Last（最終barのClose）と、
    最終barのindexをJSTへ変換した `as_of_at` を組み立てる。`fast_info` は現在値取得APIとして
    quote時刻を公開していないため使わない（リクエスト実行時刻をas_of_atの代用にしない）。
    最終barの日付が当日でない、未来時刻、取得失敗、Open/High/Low/Lastが非有限・0以下、
    または `Low <= min(Open, Last) <= max(Open, Last) <= High` を満たさない（内部整合性が崩れている）
    のいずれかなら None を返し、呼び出し側で監視エラーとして扱う。"""
```

- `fetch_split_adjusted_history` の戻り値（`daily_highs`/`daily_closes`/補正済み`entry_price`）をそのまま `position_exit.evaluate_position()` に渡す。配当発生時は価格・High双方とも変更しない（配当はスケールに影響しない）。分割発生時は各日の行をその行より後の分割比率だけで補正し、単一の累積比率を全履歴へ一律適用しない。
- `fetch_today_quote` はtimestamp付きの分足データの最終indexをquote時刻として使う。データ提供元がtimestampを保証しない場合でも、リクエスト時刻で代用せずbest-effortである旨を明示する。
- いずれも新規のリトライ機構は作らない（対象は少数保有銘柄のみで、`fetch_price_data`のような大規模バッチ用の頑健性は過剰）。ただし全銘柄が失敗した場合はオーケストレーション側（Section 3）で実行全体を失敗させる。

### 2b. `src/data/sheets_client.py`（Google Sheets I/O）

`gspread` + `google-auth`（`google.oauth2.service_account.Credentials`）を使う薄いラッパー。

- 認証: `GOOGLE_SERVICE_ACCOUNT_JSON` 環境変数（サービスアカウントJSONキーの中身をそのまま文字列で）を `json.loads` → `Credentials.from_service_account_info(..., scopes=["https://www.googleapis.com/auth/spreadsheets"])`。Drive scopeは不要（`open_by_key`のみ使用）。
- `GOOGLE_SHEET_ID` 環境変数でスプレッドシートを特定。
- `read_holdings(worksheet_name="保有銘柄") -> list[dict]`: `get_all_records()` をそのまま返す。
- `write_status(rows: list[dict], worksheet_name="状況") -> None`: `worksheet.clear()` してから `STATUS_COLUMNS` の順に整形したヘッダー+データ行を `update()` で書き込む（毎回全上書き、履歴は持たない — シートは可変な「今の状態」を表すダッシュボードであり、暗号化snapshotのような不変監査ログではない）。
- 呼び出し2箇所（read/write）ごとに都度クライアントを作る。1日3回・呼び出し回数もごく少数なので、共有クライアントやリトライ機構は作らない（Sheets APIのデフォルトクォータ 60 req/min に対して桁違いに少ない。`# ponytail: リトライなし、1日数回のコールなのでクォータに余裕あり` の一言コメントで留める）。
- 対象ワークシート（「保有銘柄」「状況」タブ）は事前にユーザーが手動作成しておく前提（このコードはタブを作らない）。READMEに明記する。

**シートschemaの確定**:
- 「保有銘柄」（ユーザー手動編集）列: `ticker`（例 "7203.T"）, `entry_date`（`YYYY-MM-DD`）, `entry_price`（実約定単価、数値）, `trailing_stop_pct`（任意・数値・空欄なら15.0を既定値として使用）。`quantity` はどの計算にも使わないため今回のscopeから外す（必要になった時点で改めて追加する）。
- 「状況」（システムが毎回上書き）列: `ticker, entry_date, entry_price, current_price, high_water_mark, stop_price, trailing_stop_pct, unrealized_pct, distance_to_stop_pct, triggered, exit_reason, as_of_at, quote_source, status, error`。`status` は `ok` / `stale` / `error` のいずれか。`as_of_date`ではなく`as_of_at`（タイムゾーン付き時刻）にする（日中複数回チェックするため日付だけでは粒度不足）。

## 3. `scripts/run_position_monitor.py`（オーケストレーション）

`--dry-run` オプション（argparse、`rebuild_inflection_forward_validation.py`と同じargparse利用の流儀）を追加する。通常実行（本番workflow）では `SLACK_WEBHOOK_URL` を必須にし、未設定なら起動時に失敗させる。`--dry-run` を明示した場合のみ未設定を許容する（fail-open防止）。

流れ:
1. `read_holdings()` → 空なら `print(...); return 0`（`rebuild_inflection_forward_validation.py` と同じ「何もなければ正常終了」パターン）。
2. 既存の `exchange_calendars`（`src/data/market_calendar.py` と同じ `XTKS` カレンダー）で当日（JST）がTSE sessionか確認し、休場日なら `print(...); return 0` で正常終了する（祝日に「全銘柄stale」で毎回失敗扱いにしない）。
3. 各行を検証（ticker必須、entry_date parse可能かつ未来日でない・原則TSE session、entry_priceが有限かつ正、trailing_stop_pctは任意で指定時は有限かつ`(0,100)`）。失敗した行は即座に `error` 行としてためておき、残りを続行。
4. 行ごとに `fetch_split_adjusted_history(ticker, entry_date, entry_price)` で分割調整済みのentry_price・過去Highと `fetch_today_quote` を取得する。
5. `today_quote` が `None`、または `evaluated_at`（実行開始時刻、JST）から見て `as_of_at` が `STALE_QUOTE_THRESHOLD_MINUTES` を超えている銘柄は `status="stale"` の行にし、Trailing Stop判定はしない（黙って「未発動」にしない）。
6. 残りの行に、共通の `evaluated_at` を渡して `evaluate_position()` を適用し `triggered` を判定する（`evaluate_position`はシステム時計を直接読まない純粋関数のため、基準時刻は呼び出し側がここで1回だけ生成し全行で使い回す）。`ValueError`/`StaleQuoteError` は当該行のみ `error`/`stale` にする。
7. `write_status()` で「状況」シートを全行分書き込む。書込みに失敗した場合は例外を伝播させ、スクリプト全体を非ゼロ終了にする。
8. 評価対象（`status="ok"`）が0件、つまり全銘柄が `error`/`stale` の場合はスクリプトを非ゼロ終了にする（監視が実質停止しているのに正常終了して見えるfail-open状態を防ぐ）。休場日は手順2で既に正常終了しているため、営業日にこの条件へ達した場合のみ失敗になる。
9. `triggered=True` の行があれば、該当銘柄をまとめて1通のSlackメッセージとして `requests.post` で送信（1銘柄1通ではなく集約）。メッセージには「暫定の検証用アラートであり、確定した売買判断ではない」旨を含める。送信には `timeout` を設定し、HTTPステータスが4xx/5xxならスクリプトを非ゼロ終了にする（成功扱いにしない）。
10. `status="stale"` または `status="error"` の行が1件以上あれば、それらもまとめてSlackへ警告として通知する（一部銘柄の失敗は処理継続してよいが黙殺しない）。
11. サマリを1行print（`run_inflection_shadow.py` と同じ体裁、`ok`/`stale`/`error`/`triggered` の件数を含める）。

**重複抑制は行わない**（発動中は毎回通知する。1日3回までなので許容する簡略化 — コード中に一言コメントを残す）。

## 4. `.github/workflows/position_monitor.yml`

- `schedule`: 9:03/12:35/15:35 JST → UTC変換で `'3 0 * * 1-5'` / `'35 3 * * 1-5'` / `'35 6 * * 1-5'` の3エントリ + `workflow_dispatch`。**GitHub Actionsのscheduleは公式ドキュメント上、高負荷時に遅延・破棄されうるためbest-effortであり厳密な定刻実行を保証しない**。特に毎時0分は混雑しやすいため9:00ちょうどを避けて9:03にずらす。この制約はREADME（Section 5）とSlackメッセージ文言にも明記する。
- `concurrency`: `position-monitor-${{ github.ref_name }}`, `cancel-in-progress: true`。
- `permissions: contents: read`（gitに何も書き戻さないため `inflection_shadow.yml` と違い write権限不要）。
- `timeout-minutes: 15`（対象は少数銘柄のみなので45分は不要）。
- secrets: `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_SHEET_ID`（新規）, `SLACK_WEBHOOK_URL`（既存を流用、本番workflowでは必須。`--dry-run` は付けない）。
- 失敗時のみSlack通知するステップを既存ワークフローと同じcurlパターンで追加（Section 3のfail-closed化により、全銘柄失敗・シート書込失敗・Slack送信失敗時にここが確実に発火する）。

## 5. 既存ファイルの編集

- **`pyproject.toml`**: `dependencies` に `gspread`, `google-auth` を追加。既存の `==` 完全固定の慣習に合わせ、実装時に実際に `pip install` して解決されたバージョンをそのまま固定する（現時点のバージョン番号を推測で書かない）。
- **`.env.example`**: 既存の「# 説明（必須/任意）」形式で `GOOGLE_SERVICE_ACCOUNT_JSON`（必須）、`GOOGLE_SHEET_ID`（必須）を追加。
- **`README.md`**: 「## Forward Validation」の後、「## セットアップ」の前に新セクションを追加。目的・スケジュール（**best-effortであり厳密な定刻ではない**旨を明記）・シート構成（「保有銘柄」列: ticker/entry_date/entry_price/trailing_stop_pct、「状況」列: Section 2bの定義通り、ともにユーザー手動編集/システム上書きの別を明記）・必要secret・「この経路は暗号化/fail-closed方針とは独立した寛容なダッシュボードだが、全銘柄失敗・シート書込失敗・Slack送信失敗は監視停止とみなしworkflowを失敗させる」ことを明記。Trailing Stopの判定式は既存 `simulate_signal()` と同一である旨、および価格基準（配当調整なし・分割のみ補正）がforward validation（配当調整込み）と異なるため既存のTrailing Stop成績をそのまま根拠にできず、`DEFAULT_TRAILING_STOP_PCT=15.0` は配当調整なし基準での専用検証が別途行われるまで検証用の暫定値であることを明記する。
- **`.github/workflows/test.yml`**: `lint` job の `mypy --ignore-missing-imports` 対象リストに新規4ファイル（`src/monitoring/position_exit.py`, `src/data/live_quote.py`, `src/data/sheets_client.py`, `scripts/run_position_monitor.py`）を追加（このリストは手動列挙のため、追加しないと型チェックされないまま見過ごされる）。

## 6. テスト

- **`tests/test_position_exit.py`**: 純粋関数なのでモック不要。backtestと同じgap/低値タッチ判定（`trailing_gap`/`trailing_stop`）・未発動・HWMが前日までの確定High基準で正しく最大値を保持（`prior_confirmed_highs`が空の場合を含む）・含み損益計算・`ValueError`系（価格/quote/split ratioが非有限または0以下・trailing_stop_pct範囲外）・`evaluated_at`を明示的に渡した場合の鮮度判定（naive datetime、未来timestamp、ちょうど60分の境界を含む）・`today_quote`鮮度超過時の`StaleQuoteError`を網羅。`evaluated_at`は常に引数で渡し、関数内でシステム時計を読まないことをテストで担保する。
- **`tests/test_live_quote.py`**: `yf.Ticker`をモック（既存の「モジュールローカル参照をpatch」規約に従う）。`fetch_split_adjusted_history`がAdj Closeへ置換しないこと、「分割前High」「分割後High」「複数回分割」「配当のみ（補正されないこと）」を個別ケースとして網羅すること（単一ratioを全行へ誤適用しないことの回帰テスト）、`entry_price`がentry_dateより後の分割だけで補正されること、**yfinanceが当日の進行中日足を含めて返してもdaily_highs/daily_closesから当日分が除外されること（当日が分割日でも分割補正自体は反映されること）**、`fetch_today_quote`が分足データの最終barのtimestampを`as_of_at`に使うこと・最終barが当日でない/未来時刻/取得失敗/非有限値や`Low<=Open,Last<=High`を満たさない不整合な場合は例外ではなく`None`を返すことを確認。実ネットワーク呼び出しは一切行わない。
- **`tests/test_sheets_client.py`**: `gspread.authorize`と`Credentials.from_service_account_info`をモック（既存の「モジュールローカル参照をpatch」規約に従う）。`read_holdings`/`write_status`の正常系、環境変数未設定時の`RuntimeError`を確認。実ネットワーク呼び出しは一切行わない。
- **`tests/test_run_position_monitor.py`**: `read_holdings`/`write_status`/`live_quote`系関数/`requests.post`/カレンダー判定をモックし、以下を確認する。
  - 空保有時の早期終了、正常系での状況シート書き込み。
  - 当日がTSE休場日の場合は価格取得を行わず正常終了する（祝日に「全銘柄stale」で失敗にしない）。
  - 発動時のSlack送信（本番モードでwebhook未設定なら起動時に失敗、`--dry-run`時のみ許容）。
  - 不正行が混在しても他行は継続し、当該行のみ`error`になる。
  - `today_quote`が`None`または`stale`な銘柄は`status="stale"`になりTrailing Stop判定をしない。
  - **全銘柄が`error`/`stale`（`status="ok"`が0件）の場合はスクリプトが非ゼロ終了する。**
  - `write_status`が例外を送出した場合、非ゼロ終了で伝播する。
  - Slack送信がタイムアウト/4xx/5xxを返した場合、非ゼロ終了する。

全体テスト実行後、`pyproject.toml`の`--cov=src --cov-fail-under=80`ゲートを新規コードで満たすことを確認する。

## 検証手順

1. `ruff check src scripts tests`
2. `mypy --ignore-missing-imports src/monitoring/position_exit.py src/data/live_quote.py src/data/sheets_client.py scripts/run_position_monitor.py`（test.ymlに追加したのと同じ対象）
3. `pytest tests/test_position_exit.py tests/test_live_quote.py tests/test_sheets_client.py tests/test_run_position_monitor.py -q` → その後 `pytest tests/` でカバレッジ80%ゲートを含め全体確認
4. ローカルでの実シート疎通確認（CI外の手作業）:
   - Googleスプレッドシートに「保有銘柄」「状況」タブを作成し、「保有銘柄」にヘッダー+1行テストデータを入れる
   - GCPでサービスアカウントを作成しSheets APIを有効化、鍵JSONをダウンロード、そのシートをサービスアカウントのメールアドレスに編集者共有
   - `GOOGLE_SERVICE_ACCOUNT_JSON`/`GOOGLE_SHEET_ID` を環境変数にセットし、`python -c "from src.data.sheets_client import read_holdings; print(read_holdings())"` で疎通確認
   - `SLACK_WEBHOOK_URL` を設定せず `python scripts/run_position_monitor.py --dry-run` を実行し「状況」シートへの書き込みのみ確認する（通常実行はSlack必須のため未設定のまま`--dry-run`なしでは起動時に失敗する）→ 次に `SLACK_WEBHOOK_URL` を設定し、意図的にentry_priceを現在値より大幅に高くした行を入れて `--dry-run` なしで実行しTrailing Stopを発動させ、Slack通知が届くことを確認
5. secrets登録後、`workflow_dispatch` で手動実行し、cronに任せる前に一度確認する

## 既知の制約・意図的な簡略化

- 自動発注は行わない。売買は常にユーザーがSBI証券で手動実行する。
- Trailing Stop率は銘柄ごとに1つ（シートの列で上書き可、既定15%）。10/15/20%を並行比較する機能は持たない（バックテスト側の役割）。
- `DEFAULT_TRAILING_STOP_PCT=15.0`は、forward validationが配当調整込み・live monitorが配当調整なしという異なる価格基準を使うため、既存のTrailing Stop成績をそのまま根拠にできない。配当調整なし基準での専用検証が別途行われるまで「検証済みの売り時シグナル」ではなく「検証用アラート」として扱う。
- 通知の重複抑制はしない。発動が続く限り毎回（最大1日3回）Slackに通知する。
- GitHub Actionsのschedule時刻（9:03/12:35/15:35 JST）はbest-effortであり、高負荷時は遅延・省略されうる（公式仕様）。定刻性が必要になった場合はGitHub Actions以外の実行基盤を検討する。
- 日本の祝日をcronは認識しないが、`exchange_calendars`によるTSE session判定で休場日は価格取得前に正常終了する（祝日ごとに「全銘柄stale」でworkflowが失敗しないようにする）。
- 「状況」シートは毎回全上書きで、過去の履歴は残らない（暗号化snapshotのような不変記録ではなく、現在地を映すダッシュボード）。`clear()`後に`update()`が失敗すると直前の状態も失われる2段階更新のリスクは残存する既知の限界とし、今回のscopeでは対応しない（write失敗時にworkflowを失敗させることで、誤った状態が放置され続けることだけは防ぐ）。
- `quantity`（保有数量）列は現時点でどの計算にも使わないためscopeから外す。必要になった時点で改めて追加する。
- 全銘柄のprice/quote取得失敗、状況シート書込失敗、Slack送信失敗（webhook未設定含む、`--dry-run`時を除く）は実行全体を失敗させ、既存の失敗時Slack通知経路につなげる（fail-open防止）。一部銘柄のみの失敗は処理を継続するが、`stale`/`error`件数もあわせてSlackへ警告として通知する。
