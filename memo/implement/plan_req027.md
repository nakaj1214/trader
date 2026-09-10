# 実装計画: REQ-027 — Trade Ledger（現状範囲）

> `memo/implement/proposal.md` のREQ-027だけを対象とする。
> REQ-023〜026の実装（`memo/implement/plan.md`）から切り離す。

## 前提: 現在のプロジェクト段階

現状のリポジトリは「実売買」ではなく、以下を検証する段階にある。

- 株式情報（価格・出来高・財務）を安定して取得できるか
- 上昇/下降・値段の予測が当たっているか
- 分析ロジック（inflectionスコアリング）が妥当か

実際に手動で発注・約定する運用は、これらの検証が終わってから開始する。REQ-027の`entry_order_at`以降のフィールド（発注〜約定〜決済）は、実トレードという記録対象の事実そのものがまだ存在しないため、今は実装しない。

## 現状で必要な実装

**なし。** 理由:

- `candidate_date`相当は既存の暗号化snapshot（`dashboard/data/inflection/YYYY-MM-DD.enc`）と`inflection_forward.py`のforward validationで既に記録・評価されている。
- `exit_signal_at`/`notification_at`相当は、`memo/implement/plan.md`（REQ-023〜026、現在実装中）で「状況」シートに追加される`triggered_at`/`last_notified_at`でカバーされる予定。REQ-027側で重複実装しない（未実装のうちはREQ-027でも代替できないが、着手中のplan.mdが完了すれば満たされる）。
- `entry_date`/`entry_price`は「保有銘柄」シート（手動編集、`README.md`記載）に既にフィールドがある。
- 上記以外のフィールド（`entry_order_at`, `entry_fill_at`, `exit_fill_at`, `exit_price`, `realized_return_pct`, `max_mfe_pct`, `max_mae_pct`, `peak_giveback_pct`, `position_id`）は、実際の約定という入力がなければ記録も検証もできない。

よって、REQ-027として新たに着手するコードはない。今回のフェーズでは`memo/implement/plan.md`（REQ-023〜026）のみを実装する。

## 今後の展望（手動売買を開始する時点で着手）

以下は、検証が終わり実際の手動売買を開始する段になってから、統合Trade Ledgerとして再検討する。

### 想定フィールド

- `position_id`
- `signal_id`
- `ticker`
- `entry_date`
- `candidate_date`
- `notification_at`
- `entry_order_at`
- `entry_fill_at`
- `entry_price`
- `entry_price_split_adjusted`
- `exit_signal_at`
- `exit_fill_at`
- `exit_price`
- `exit_reason`
- `realized_return_pct`
- `max_mfe_pct`
- `max_mae_pct`
- `peak_giveback_pct`

証券会社APIを使わないため、注文・約定時刻と実約定価格は手入力とする。自動取得できる値だけをシステムが記録する。

### 着手前に決めること

1. `position_id`の入力・一意性・再利用禁止ルール。
2. 新規「取引履歴」worksheetの作成、header検証、既存シート（「保有銘柄」「状況」）からの移行方法。
3. 行追記と数式設定の部分失敗を再試行する最小の方法。
4. holding削除後も、Ledger記録またはSlack通知が未完了ならイベントを失わない状態モデル。
5. `entry_price_split_adjusted`を`exit_fill_at`時点の分割係数へ揃える方法。
6. MFE/MAE/peak givebackの観測期間と、entry日・exit日を含める境界。
7. 同時実行時の重複追記を防ぐwriter運用。

### 受入条件（着手時点で再確認）

- proposal REQ-027の全フィールドを持つ台帳が用意される。
- 自動項目と手入力項目の責任範囲がREADMEに明記される。
- 同じ取引は1回だけ記録され、部分失敗後も欠落・重複なく再試行できる。
- 分割をまたぐ実現損益が`exit_fill_at`時点の同一価格基準で計算される。
- 外部Google Sheet/Slackへ接続しないユニットテストで正常系と再試行を確認できる。

### 非目標（着手時点でも対象外）

- REQ-023〜026の実装へLedger用の`position_id`、pending payload、tombstone、数式修復、workflow直列化を持ち込まない。
- Phase 5の買い候補通知パイプラインを先行実装しない。
