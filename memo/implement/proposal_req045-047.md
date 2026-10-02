# 実装要件書（REQ-045〜047: 売却ルールの比較検証、相場環境の層別評価、stop 接近の事前警告）

> このファイルは create-plan の入力です。
> 出典: [memo/analysis/improvement_report_2026-10-01.md](../analysis/improvement_report_2026-10-01.md) の B3・B4（propose-one で選択）。
> 以前の要件書: REQ-001〜036、037〜038、039〜041、042〜044 → それぞれ `proposal_req*.md`

## 背景

- **B3:** プロジェクトの目的の後半は「上昇が止まる直前に手放す」ことだが、売却の仕組みは固定 %の Trailing Stop だけである。天井は事後にしか分からないので、現実的な目標は「上昇の大部分を取り、天井からの反落で降りる」ことになる。候補となる売却ルールを、**forward validation（と B1 の過去検証）で同じ条件のもとに比較し、優位だったものだけを、別の要件で Monitor に採用する**。
- **B4:** モメンタム系の戦略は、下落相場からの急反発の局面で大きく負けやすい（momentum crash）。今の相場環境の扱いは、forward レポートで「TOPIX の20日リターンが正か負か」の件数を数えるだけで、成績の層別も、自己学習の factor にもなっていない。

## 共通の設計判断

- **戦略・snapshot・本番の Monitor の売却判定は変えない。** REQ-045 と REQ-046 は評価側だけの変更である。REQ-047 は、Monitor に「警告」を足すだけで、売却の条件（trailing stop）は変えない。
- **パラメータは事前に固定し、探索しない。** 各売却ルールのパラメータは下表の1組だけで比較する。結果を見て調整すると、比較が過大評価になるため（レポート §4.2 の多重比較の注意）。
- **約定の仮定は既存の trailing stop と揃える。** 判断に使えるのは、その日の時点で確定している情報だけとする（先読みしない）。

---

## 要件一覧

### REQ-045: 売却ルールの候補を、forward と過去検証の exit 比較に追加する（B3）

- **画面**: なし（forward のレポート `exit_strategies`、B1 の過去検証のレポート）
- **対象ファイル**:
  - 新規: `src/evaluation/exit_rules.py`
  - 変更: [src/evaluation/inflection_report.py](../../src/evaluation/inflection_report.py)（`_build_group_report` の `exit_strategies`）
  - テスト: 新規 `tests/test_exit_rules.py`、既存 `tests/test_inflection_forward.py`
- **Before（現状）**: `exit_strategies` は、固定 %の trailing stop（10% / 15% / 20%）× 最大保有日数（60 / 126 / 252）の9通りだけである（`inflection_report.py` L133〜）。
- **After（期待）**: `exit_rules.py` に、売却ルールを日足（OHLC）で1日ずつ判定するシミュレーターを作り、次の4つのルールを `exit_strategies` に追加する。最大保有日数は 126 営業日とする（既存の trailing と比べやすくするため）。

  | ルール | 内容（パラメータは固定） | 約定の仮定 |
  |---|---|---|
  | Chandelier（ATR） | stop = 前日までの HWM（保有中の最高値）− 3.0 × ATR(22)。ATR は前日までの22営業日で計算する | 既存の trailing と同じ: 寄付が stop 以下なら寄付で、日中の安値が stop 以下なら stop 価格で約定 |
  | 移動平均割れ | 保有中の最大含み益が +20% 以上になった後、終値が 10日 EMA を下回ったら、**翌営業日の寄付**で売る | 終値で判断し、翌日の寄付で約定（同じ日の終値で売ると先読みになるため） |
  | 時間 stop | 15 営業日目の終値で含み益が +5% 未満なら、翌営業日の寄付で売る。そうでなければ trailing 15% に切り替えて保有を続ける | 同上 |
  | 段階利確 | 日中の高値が entry の +50% に達したら、半分を +50% の価格で利確する。残りの半分は trailing 15% で保有する | 利確の約定は +50% の価格（指値を想定）。寄付が +50% を超えていれば寄付の価格 |

  - 4つのルールとも、どの売却条件にも当たらなければ、最大保有日数の終値で売る。
  - 結果は既存の `TradeResult` に揃えて返し、既存の集計（`summarize_trades`、`paired_benchmark_returns`、未完了の除外、stress コスト）をそのまま使う。段階利確の損益は、2つの売買の加重平均とする。
  - 新しいルールの結果は、既存の9通りと同じ形で `exit_strategies` に並べる（キー例: `chandelier_3atr22_h126`、`ma10_break_after20_h126`、`time15d_5pct_then_trail15_h126`、`partial50_half_then_trail15_h126`）。
  - 既存の9通りの結果は変えない。
- **受入条件**:
  1. 新しいシミュレーターで、固定 %の trailing（例: 15%）を表した場合の結果が、既存の `simulate_signal(trailing_stop_pct=15)` と一致する（シミュレーターの約定の仮定が既存と同じであることの確認）。
  2. 各ルールについて、手で計算できる合成の価格系列で、売却日・売却価格・損益が期待どおりになる（ギャップダウン、日中の stop 到達、保有期間の満了、条件に当たらない場合を含む）。
  3. ATR、EMA、含み益の判定に、判定日より後の価格を使っていない（判定日より後の価格を変えても、その日までの判定が変わらない）。
  4. 段階利確の損益が、2つの売買の加重平均と一致する。
  5. 既存の `exit_strategies` の9通りの値が変わらない。
  6. 価格データに欠損（O/H/L のいずれかが NaN）がある場合は、既存の trailing と同じく例外を出す。
- **備考**: B1 の過去検証は `_build_group_report` を使っているので、追加のルールは過去検証のレポートにも自動で入る。

### REQ-046: 相場環境（regime）を判定し、自己学習の factor と forward の層別集計に加える（B4）

- **画面**: なし
- **対象ファイル**:
  - 新規: `src/evaluation/regime.py`
  - 変更: [src/evaluation/inflection_learning.py](../../src/evaluation/inflection_learning.py)（factor ラベル）、[src/evaluation/inflection_report.py](../../src/evaluation/inflection_report.py)（層別集計）、[src/data/forward_prices.py](../../src/data/forward_prices.py)（取得期間）
  - テスト: 新規 `tests/test_regime.py`、既存テスト
- **Before（現状）**: regime は `regime_label`（TOPIX ETF の20日リターンが正か負か）で件数を数えるだけである。自己学習の factor にも、成績の層別にも使われていない。
- **After（期待）**:
  - `regime.py` に、シグナル日**以前**のベンチマーク（1306.T）の終値だけを使う、2つの判定を置く。
    - **トレンド**: 終値が200営業日の移動平均より上なら `up`、下なら `down`。200本に満たなければ `unknown`
    - **ボラティリティ**: 20営業日の実現ボラティリティ（年率）が、過去252営業日の20日ボラティリティの中央値より高ければ `high`、それ以外は `normal`。履歴が足りなければ `unknown`
  - 自己学習の factor ラベルに `regime_trend:{up|down|unknown}` と `regime_vol:{high|normal|unknown}` を追加する（REQ-043 の Fisher 検定と BH 補正の対象になる）。
  - forward（と過去検証）のレポートで、各グループ・各 horizon の成績を、トレンドとボラティリティの regime 別にも集計する（件数、平均超過リターン、勝率）。既存の `regime_sample_counts`（20日リターン）は互換のため残す。
  - 上の判定には、シグナル日の前に約272営業日分（252 + 20）のベンチマークの履歴が必要である。共通の取得期間（REQ-042 の `PRIOR_HISTORY_DAYS`）を、100日から **420日** に延ばす。増えるのは各銘柄の行数で、API の呼び出し回数は変わらない。
- **受入条件**:
  1. 合成の価格系列で、トレンドとボラティリティの判定が期待どおりになる（境界、履歴不足で `unknown`）。
  2. シグナル日より後の価格を変えても、判定が変わらない。
  3. 自己学習の factor ラベルに regime が含まれ、Fisher 検定と BH 補正の対象になる。
  4. forward のレポートに regime 別の成績が出る。既存のキーと値は変わらない。
  5. 取得期間の延長後も、価格ハッシュが変わらない（REQ-042 の `legacy_hash_window` で従来の期間に切り出しているため）。既存の回帰テストが PASS する。

### REQ-047: Position Monitor に「stop まで残りわずか」の事前警告を追加する（B3 の補足）

- **画面**: Slack 通知、Google スプレッドシートの「状況」シート
- **対象ファイル**:
  - 変更: [scripts/run_position_monitor.py](../../scripts/run_position_monitor.py)、[src/data/sheets_client.py](../../src/data/sheets_client.py)（`STATUS_COLUMNS`）
  - テスト: `tests/test_run_position_monitor.py`、`tests/test_sheets_client.py`
- **Before（現状）**: `distance_to_stop_pct`（現在値が stop 価格から何%上にあるか）は計算して状況シートに書くが、通知には使っていない。通知は stop に到達した時（triggered）だけである。
- **After（期待）**:
  - stop に未到達で、`distance_to_stop_pct` が **3.0% 以下**になった銘柄を、「[検証用アラート] stop まで残り x%」として Slack に通知する（`WARNING_DISTANCE_PCT = 3.0` として定数化する）。
  - 同じ銘柄・同じ日には1回だけ通知する。状況シートに `last_warned_at` 列を追加して、重複を防ぐ（既存の `last_notified_at` と同じ方式）。
  - 売却の判定（triggered の条件）と、triggered の通知は変えない。triggered になった銘柄には、事前警告を出さない。
  - 通知の文言には、既存のアラートと同じく「確定した売買判断ではない」ことを明記する。
- **受入条件**:
  1. 残り 3.0% 以下で未到達の銘柄に、1回だけ警告が出る。同じ日の2回目の実行では出ない。翌日は再び出る。
  2. 残り 3.0% より大きい銘柄、triggered の銘柄、stale や error の銘柄には、警告が出ない。
  3. `--dry-run` では Slack に送らない。
  4. 状況シートに `last_warned_at` 列が追加され、既存の列の値は変わらない。
  5. 既存の Monitor のテストがすべて PASS する。

---

## 繰り返し失敗している要件

なし。

---

## 完了済み・保留中

### 完了済み
- REQ-042〜044（価格取得の共通化、昇格判定の統計的補強）: コミット済み（`324a765`）、未 push

### 保留中（今回のスコープ外）
- **優位だった売却ルールを Monitor に採用すること。** REQ-045 の比較結果（十分な件数）を見てから、別要件で判断する。
- **regime による戦略の切り替え**（下落 regime で EARLY_CANDIDATE を WATCH に下げる、ポジション数を減らす）。REQ-046 の診断結果を見てから、次期 strategy version として判断する。
- **決算発表日をまたぐ前の警告**。J-Quants の決算発表予定 API を Monitor の workflow から呼ぶ必要があり、秘密情報の扱いを含めて別要件にする。
- **過熱・出来高クライマックスの警告**。判定条件の設計が必要なため別要件にする。
- **多重比較を考慮した exit ルールの評価**（Deflated Sharpe Ratio など、レポート §4.2）。ルールの数が増えたので、比較結果を読むときの注意として、別要件で検討する。
