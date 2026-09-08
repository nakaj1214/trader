# Trader プロジェクトレビュー

レビュー日: 2026-09-08

対象: 現在の JP inflection shadow 経路

## 結論

旧週次予測、旧 GUI、Docker、設定、データ、テストは `archive/legacy/` に隔離され、現行の package・CI・実行経路から外れました。今回までに、現行経路で判明した6件を修正しました。下記の構成上の制約は引き続き残ります。

## 修正済み

### P1: 欠損年度があると複数年の変化率を YoY として採用する — 修正済み

- `_previous_comparable_actual()` は同じ期間種別かつちょうど1年前の `CurFYEn` だけを比較対象にするよう変更しました。
- 欠損年度または決算期変更で比較可能性を確認できない場合は、YoY と営業利益率変化を `None` にします。
- 2年空いたデータを拒否する回帰テストを追加しました。

### P2: forward validation の約定コストが固定値だけ — 修正済み

- 既存の通常シナリオ（総往復コスト0.2%）を維持し、悲観シナリオ（1.2%）を各5・20・60日評価へ追加しました。
- report に両シナリオの前提と、板厚・売買停止・制限値幅による約定確率を未モデル化であることを明記します。

### P2: Close ベース指標では日中のピーク捕捉を評価できない — 修正済み

- 既存の Close ベース指標を維持し、調整済み `High / Low` から `mfe_pct` / `mae_pct` を追加しました。
- forward validation の取得データは調整済み OHLC を必須とし、summary に中央値を追加しました。
- High/Low と Close の差を確認する回帰テストを追加しました。

### P2: APIキー変更で過去snapshotを復号できなくなる — 修正済み

- scanner と forward validation は共通の `snapshot_encryption_secret()` を使い、専用の `SNAPSHOT_ENCRYPTION_KEY` がなければ失敗するよう変更しました。
- GitHub Actions から `JQUANTS_API_KEY` へのフォールバックを削除しました。
- 暗号鍵のローテーションには既存snapshotの再暗号化が必要です。

### P1: 売却戦略が文書だけで固定保有しか評価できない — 修正済み

- 最大60営業日の10% / 15% / 20% Trailing Stopをforward validationへ追加しました。
- 売却線は前日までのHigh Water Markだけで計算し、当日High/Lowの順序を仮定しません。
- Stopを下回るgapでは実際の当日始値を使い、`exit_reason` を保存します。

### P2: 同一銘柄の重複signalを独立取引としてしか集計できない — 修正済み

- 従来のsignal単位集計は比較用に維持し、同一銘柄を同時に一つだけ保有する `position_summary` を追加しました。
- 銘柄間の資金配分までは扱わないため、portfolio解釈は引き続き無効です。

## Archive へ移した既知の問題

以下は修正せず、実行経路ごと `archive/legacy/` に移しました。

- 起動できない Docker exporter と重複した `requirements.txt`
- 削除済み module を import する Google Sheets 移行スクリプト
- 同日再実行で予測を重複保存する旧 SQLite pipeline
- 通知失敗を成功として返す旧 orchestrator

## 既知の制約

- 現行 shadow snapshot を表示・通知する consumer はありません。現在はデータ蓄積フェーズです。
- forward validation のraw集計は独立した日次signalです。`position_summary` は同一銘柄の重複保有を除きますが、銘柄間の同時保有数、資金制約、portfolio drawdown は表しません。
- 保有ポジション、数量、High Water Mark、売却履歴を保持する ledger はありません。現行 scanner は Exit monitor として利用できません。
- 日次 GitHub Actions は高負荷時の遅延・欠落があり得るため、リアルタイムの売却監視基盤にはできません。
- `dashboard/data/inflection/` は現在空で、forward validation は評価対象がない間は正常終了する設計です。

## 検証

- `pytest`: 67 passed、coverage 90.75%
- `ruff check src scripts tests`: PASS
- `mypy --ignore-missing-imports src scripts`: PASS
