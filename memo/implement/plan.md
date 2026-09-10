# 実装計画: Phase 4A — Position Exit Monitor（REQ-023〜026）

> 入力: `memo/implement/proposal.md` のREQ-023〜026。
> REQ-027（Trade Ledger）は `memo/implement/plan_req027.md` へ分離し、今回は実装しない。
> REQ-028はREADMEと通知文で対応済みのため変更しない。

## 目的とスコープ

次の4点だけを修正する。

1. 当日の1分足を時系列処理し、日中のHWM更新後に発生したTrailing Stopを検知する（REQ-023）。
2. quoteのstale閾値をセッション中・大引け直後10分、それ以外60分に分ける（REQ-024）。
3. 同じトリガーが継続している間のSlack通知を1回にする（REQ-025）。
4. 「状況」シートの全件置換を1回のatomicな`spreadsheets.batchUpdate`にする（REQ-026）。

Trade Ledger、`position_id`、pending payload、tombstone、実現損益、MFE/MAE、workflow直列化は対象外とする。REQ-025の状態キーは既存入力だけで作れる`(ticker, entry_date)`とし、同じキーの複数保有はfail-closedにする。同日・同一tickerの複数positionを個別管理する必要が生じた時点で、REQ-027と一緒に`position_id`を導入する。

## 変更対象

- `src/data/live_quote.py`
- `src/monitoring/position_exit.py`
- `src/data/sheets_client.py`
- `scripts/run_position_monitor.py`
- `tests/test_live_quote.py`
- `tests/test_position_exit.py`
- `tests/test_sheets_client.py`
- `tests/test_run_position_monitor.py`
- `README.md`（状況シートの追加列だけを反映）

## 実装ステップ

### 1. 当日1分足を1回だけ取得して時系列評価する（REQ-023）

- `src/data/live_quote.py`に`fetch_today_bars(ticker) -> pd.DataFrame | None`を追加し、現行`fetch_today_quote()`の取得・JST変換・当日抽出を移す。
- 取得済みバーから`TodayQuote`を作る`build_today_quote(bars)`を追加する。`fetch_today_quote()`は互換性のため、その薄いラッパーとして残す。
- `run()`は`fetch_today_bars()`を1回だけ呼び、同じバーからquoteを作って`evaluate_position()`へ両方渡す。
- `evaluate_position()`はバーを時刻順に処理する前に、**全バーのOHLCを検証する**: finite・正値であること、`Low <= min(Open, Close) <= max(Open, Close) <= High`であること、indexがtimezone-aware・評価対象日と同日・重複なしであること、各バーの`timestamp`が`quote_at`以前かつ`evaluated_at`以前（未来のバーを含まない）であることを確認し、いずれか1件でも満たさなければ例外を送出してfail-closedにする（現行`fetch_today_quote()`は集約後の`TodayQuote`しか検証しておらず、個別バーのNaN・非正値・OHLC矛盾・タイムスタンプ異常は素通りしてしまうため）。検証を通過したバーだけを対象に、既存HWMからstopを計算し、`Open <= stop`、次に`Low <= stop`を判定し、未発火なら`High`でHWMを更新する。これにより同一バーのHighを先取りしない。
- 日足履歴は`(row_date > entry_date) & (row_date < current_date)`だけを確定履歴として返し、entry日と当日の未確定daily rowをHWM・drawdownから除外する。判定は2段階にする:
  - **生の取得結果（`history`/`frame`、日付フィルタ**前**）が空の場合**: 既存の分岐を維持する。`entry_date == current_date`（entry当日で、providerがまだ当日分のdaily rowを用意していないだけ）なら分割調整後entry priceと空Seriesを正常値として返す（Stop判定自体はこの後の当日バー処理でentry当日としてskipされる）。`entry_date < current_date`（entry日より後なのに生データが1件も無い）は従来どおり`ValueError`でfail-closedにする。
  - **生の取得結果は非空だが、日付フィルタ後の`prior`に欠落がある場合**: 単純に`prior.empty`かどうかでは判定しない。TSEカレンダー（既存の`market_calendar`/`exchange_calendars`）で`entry_date`と`current_date`の間（両端を含まない開区間）に**期待されるTSE session日の集合**を求め、`prior`に実際に含まれる日付の集合と比較する。**期待日の集合に対して1件でも不足があれば**（`prior`が完全に空の場合だけでなく、期待3セッションのうち1件しか無いような部分欠落も含む）、providerが確定日足を欠落させている実データ不整合とみなし`ValueError("prior confirmed daily history is missing")`をfail-closedで送出する。期待日集合と実際の日付集合が一致する場合（期待0件・実際0件を含む）のみ正常値として扱う（HWMがentry priceへ縮退してTrailing Stop水準が不当に低くなり、Exit alertを見逃すことを防ぐ）。
- entry時刻を持たないため、`entry_date == evaluated_at.date()`では当日バーによるStop判定を行わず、HWMは分割調整後entry priceのままとする。翌営業日から通常監視を始める。

検証:

- 「安値→高値→急落」と「高値→安値」の1分足で、未来Highを使わず正しいバーで発火する。
- 当日の未確定daily Highが初期HWMへ混入しない。
- entry当日は約定前バーで発火せず、翌日から評価される。
- run内のyfinance 1分足取得は銘柄ごとに1回だけである。
- entry当日（`entry_date == current_date`）で生の取得結果自体が空でも、fail-closedにならず正常評価に進み（Stop判定はskipされる）、分割調整後entry priceのみが返る。
- entry日より後なのに生の取得結果が空のケースは従来どおり`prior confirmed daily history is missing`でfail-closedになる。
- entry日の翌営業日（`(entry_date, current_date)`の間に期待されるTSE session数が0件のケース）で、確定履歴が空のまま正常に評価される（`prior confirmed daily history is missing`が誤って送出されない）。
- 期待session数と実際の日付集合が完全一致しないケース（例: 期待3セッションに対し実際は1セッションのみ返る部分欠落）で、`prior`が非空であってもfail-closedになる。生の取得結果自体が空のケースでも従来どおりerrorになる。
- NaN・非正値・`Low > min(Open, Close)`・`High < max(Open, Close)`を含む1分足、timezone-naiveなindex、評価対象日と異なる日付、重複timestamp、未来のtimestampを含む1分足が、それぞれ拒否されfail-closedになる。

### 2. stale閾値を取引時間に応じて切り替える（REQ-024）

- `STALE_QUOTE_THRESHOLD_MINUTES_IN_SESSION = 10`と`STALE_QUOTE_THRESHOLD_MINUTES_OUTSIDE_SESSION = 60`を定義する。
- `scripts/run_position_monitor.py`に`is_in_session(calendar, when)`を追加する。取引時間中、または当日session closeから30分以内なら`True`とする。昼休みは`False`とする。
- `evaluate_position()`へ`in_session: bool`を渡し、対応する閾値でquote ageを検証する。

検証:

- セッション中は11分でstale、9分で正常。
- 15:35時点の14:40 quoteはstale、15:30 quoteは正常。
- 16:05、寄付き前、昼休みは60分閾値を使う。

### 3. 「状況」シートをatomicに置換する（REQ-026）

- `write_status()`は`Worksheet.clear()`と`Worksheet.update()`を廃止し、`worksheet.spreadsheet.batch_update({"requests": [...]})`を1回だけ呼ぶ。
- 同じbatch内で、必要なら`updateSheetProperties`によりgridの行・列を拡張し、`repeatCell`で既存の`userEnteredValue`を消去してから、`updateCells`でheaderと全行を書き込む。全requestは1回の`spreadsheets.batchUpdate`としてatomicに適用する。
- 文字列は`stringValue`、数値は`numberValue`、真偽値は`boolValue`で明示し、`=`から始まるticker等を数式として解釈させない。

検証:

- `batch_update()`が1回だけ呼ばれ、`clear()`/`update()`は呼ばれない。
- 少ない行への置換で古い行が残らない。
- grid不足時の拡張と書込みが同じbatchに入り、batch失敗時は別API呼出しによる中間状態を作らない。
- `=`から始まる値は`stringValue`になる。

### 4. 通知を状態遷移ベースにする（REQ-025）

- `STATUS_COLUMNS`の末尾へ`triggered_at`と`last_notified_at`を追加し、既存の`exit_reason`をtrigger reasonとして使う。
- `read_status()`を追加し、前回行を`(ticker, entry_date)`で参照する。前回statusまたは今回holdingsに同じキーが複数あれば、曖昧な状態行を書き出さず全体をfail-closedにする。
- 正常評価が`False -> True`、または前回`triggered=True`かつ`last_notified_at`が空の場合だけ通知対象にする。Slack成功後だけ`last_notified_at=now`を設定する。
- 正常評価が`triggered=False`なら時刻をリセットする。stale/errorでは前回の`triggered`、`exit_reason`、`triggered_at`、`last_notified_at`を維持し、状態を解除しない。
- 処理順は「前回status読取 → holdings評価と状態反映 → Slack送信 → status atomic書込み」。Slack例外はいったん保持し、`last_notified_at`を空のままstatusへ保存してから再送出し、workflow失敗を維持する。
- Slack失敗後も同じtriggerが継続すれば次回再送する。trigger解除後やholding削除後まで通知キューを保持する機能はREQ-025の受入条件外であり、REQ-027の永続イベント設計へ延期する。
- Slack成功後・status保存失敗では次回通知が重複しうる。SheetsとSlackをまたぐtransactionは導入せず、at-least-onceの既知制約としてREADMEへ記載する。

検証:

- `True -> True`は初回だけ通知し、`True -> False -> True`は再通知する。
- stale/errorを挟んでも確定済みtriggerを解除しない。
- Slack失敗時は`last_notified_at`を設定せずstatus保存後に例外を再送出し、同じtriggerの次回runで再送する。
- dry-runは通知済み状態を作らない。
- 同一キーのholding/status重複はstatusを書き換える前にfail-closedになる。

## 副作用隔離と完了条件

- テストはGoogle Sheets、Slack、yfinanceをすべてmockし、外部HTTPや永続シートへ接続しない。
- `tests/test_live_quote.py`、`tests/test_position_exit.py`、`tests/test_sheets_client.py`、`tests/test_run_position_monitor.py`の対象テストが成功する。
- Ruff、mypy、Harnessの変更範囲検証が成功する。
- 実Google Sheetを使う確認はCodex検証では実行せず、必要な場合だけoperator-run手順としてREADMEに残す。
