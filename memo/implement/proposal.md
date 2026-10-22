# 実装要件書: 一次選別の測定と評価の接続（Codex G01/G02 + Claude M1/M2）

> このファイルは create-plan の入力です。
> 番号の注意: 本書の REQ-001〜003 は、過去の [proposal_req001-036.md](proposal_req001-036.md) の REQ-001〜003 とは別物。
> 実装状況（2026-10-22）: REQ-001〜003 は実装済み。forward の OVEREXTENDED 群も追加した（[対応表](../../.harness/reports/trader-gap-verification-claude/implementation-trace.md)、[review.md](review.md)）。
> 日時: 2026-10-21 / 入力: ユーザー依頼「測定から始め、順序どおりに作る」（会話）。`memo/implement/prompt.md` は別件（2026-10-13 の保守課題）のため入力に使っていない。
> 根拠: [Codex 調査](../../.harness/reports/trader-gap-research/gap-analysis.md)（G01・G02）、[Claude 検証](../../.harness/reports/trader-gap-verification-claude/verification.md)（M1・M2）。
> 前の proposal.md（D1〜D3: 比較不能・未評価の扱い）は上書きした。内容は git 履歴（`da7b4f3` 時点）に残る。実装状況は今回確認していない。

---

## 目的と順序

目的: 「爆発的に伸びる株を初期に見つける」という理念に対し、今の一次選別が何を取り、何を取りこぼすかを、価格データだけで測れるようにする。重み・閾値を変える前の物差しを作る。

順序（上から。前が終わってから次へ。同時に直さない）:
1. REQ-001 全市場の急騰イベントに対する初期発見の評価
2. REQ-002 OVEREXTENDED 群を historical 評価に入れる
3. REQ-003 CONTROL を forward 評価へ別経路で接続する

データ蓄積（日次 scan・snapshot）は止めず、待たない。REQ-001/002 は既存のローカル日足キャッシュ（`.data/jquants`）で作れる。60/120 日成績の判定は標本が溜まってから（本スコープ外）。

## 全要件共通の制約

- スコア・閾値・重み・EARLY/WATCH の基準・Q06 閾値（ticker 10 / signal date 5 / 最大業種比率 50%）を変更しない。
- 外部 API・実 Slack・実 Sheets・暗号化 snapshot の復号・永続キャッシュへの書込みをしない。検証は fake / synthetic と一時ディレクトリ、およびローカル日足キャッシュの読取りのみ。
- 既存の出力キーは変えず、追加のみにする。正常入力の既存数値が変わる場合は、意図どおりかを説明して記録する。
- 既存テストを新実装に合わせて書き換えるだけの修正は禁止。

---

## 要件一覧

### REQ-001: 全市場の急騰イベントに対する初期発見の評価

- **画面**: なし（評価スクリプト・レポート）
- **対象ファイル**: 新規 `src/evaluation/inflection_event_recall.py`（既存 [inflection_recall.py](../../src/evaluation/inflection_recall.py) は変更しない）。一次選別は [inflection_live.py](../../src/screening/inflection_live.py) の `_technical_features`・`_pre_score`・流動性条件を再利用し、重複実装しない。入口は [run_inflection_historical_backtest.py](../../scripts/run_inflection_historical_backtest.py) に追加（既存出力は変えない）。試作: `.harness/reports/trader-gap-verification-claude/analysis/exemplar_funnel.py`（J-Quants 調整済み終値の近似。本番は yfinance Adj Close）。
- **Before（現状）**: Recall は deep_candidates に一度でも入った銘柄だけが分母（[inflection_recall.py:70](../../src/evaluation/inflection_recall.py#L70) の注記）。+50% 到達前に EARLY/WATCH が一度出れば検出扱いで、「何倍に上がってから見つけたか」が分からない。旧 summary では pool 内 Recall 25%（19/76）。
- **After（期待）**: 対象市場（Prime/Standard/Growth の普通株）全体から、日次ラベルを連続した上昇イベントにまとめ、イベントごとに次を出す。
  - 選別の段階別の到達: 価格あり → 流動性通過（20 日平均売買代金 ≥ 1 億円）→ pre_score 上位 25 → EARLY/WATCH（財務込みの分類は既存 historical の signal を使う）。
  - 初めて各段階に入った日の「イベント底からの上昇倍率」と、+50% 到達日との前後。
  - 1 日あたりの通知件数（EARLY+WATCH）。
  - 次に買える始値から一定保有（60 営業日）の純損益。
  - 起点の底は事後ラベルでよいが、選別側の入力には将来値を入れない。
- **受入条件**:
  1. 合成データで、「100→149 まで上がってから WATCH → 翌日 150」は、検出済みでも上昇倍率 1.49 として記録される（現行 Recall は 100% と表示するケース）。
  2. 観測一覧に無い急騰銘柄も分母に入る。
  3. 将来の価格を変えても、その日以前の段階判定は変わらない（先読みなしのテスト）。
  4. ローカル日足キャッシュの読取りだけで実行でき、例示 8 銘柄（キオクシア等）の段階別到達日を出力する。試作 `exemplar_funnel.py` の変形 B は**正解値ではなく比較資料**とする。変形 B は上場済み銘柄の 52 週高値加点を 60 本から判定するが、現行実装（`_technical_features`）は 252 本必須で、本要件は現行ロジックを変えず再利用する。到達日が変形 B と食い違う場合は、一致させず、差の理由（高値加点の判定本数・調整価格の違い）を出力に記録する。
  5. 既存の `tracked_pool_explosion_recall` と既存テストは不変。
- **備考**:
  - **イベント定義（確定）**:
    - 成立: ある日 H の終値が、H の直前 120 営業日の最安終値の 2 倍以上になった最初の日。
    - 底: その 120 営業日の窓の最安終値の日（同値なら最も早い日）。
    - 重複: 同一銘柄は、成立した底から 120 営業日が経つまで次のイベントを作らない（長く続く上昇は 1 件にまとめる）。
    - 初期: 底から終値 +50% に達する日の**前日まで**。+50% 到達当日は含めない（終値で判定して翌始値で買うので、当日は買えない。既存 Recall も `< explosion_date` と厳密に前で、揃える）。
    - 段階への到達は、その日の終値で判定し、買える価格は翌営業日の始値で測る。
  - **評価できる期間を分ける**:
    - 価格だけの段階（価格あり → 流動性 → 上位 25）は、日足が 21 本以上ある日から評価する。52 週高値の加点は 252 本が溜まるまで効かないため、`high_bonus_available=false` の期間を出力で区別する。
    - EARLY/WATCH の段階は、既存 historical の開始日（`default_signal_start`: 252 本の価格履歴と財務の準備期間 `FINS_WARMUP_DAYS` を満たす日、[inflection_historical.py:395](../../src/evaluation/inflection_historical.py#L395)）以降だけ評価する。
    - 開始日より前に起点があるイベントは、EARLY/WATCH の段階を「未評価」とし、検出にも未検出にも数えず、別の件数で出す。
  - [要確認: 受入の合否基準] 「初期」の上昇率の許容値、許容損失、通知上限の数値はプロジェクトの受入条件として別途決める（Codex G01 も同じ指摘）。本要件は測定までで、合否判定は含まない。
  - 注意: 試作は J-Quants の分割調整済み終値で、本番の yfinance Adj Close（配当込み）と異なる。historical の既存注記（[inflection_historical.py:379](../../src/evaluation/inflection_historical.py#L379)）と同様に限界として出力へ記す。
  - 受入条件 1 の例（100→149 で WATCH）は、上の定義では「+50% 到達の前日までに検出」となり、検出済みで記録される。そのうえで上昇倍率 1.49 が出力に残ることを確認する。

### REQ-002: OVEREXTENDED 群を historical 評価に入れる

- **画面**: なし（評価レポート）
- **対象ファイル**: [inflection_historical.py](../../src/evaluation/inflection_historical.py)（`GROUPS` は :376、群の評価は :733 付近）。forward 側は既に OVEREXTENDED を読む（[rebuild_inflection_forward_validation.py:208](../../scripts/rebuild_inflection_forward_validation.py#L208)）ので揃える。
- **Before（現状）**: `GROUPS = ("EARLY_CANDIDATE", "WATCH", "NONE", "CONTROL")`。旧 summary では signal 4,700 件のうち 152 件がどの群にも入らず、評価されていない。「+50% 超を除外する判断」（[inflection_live.py:461](../../src/screening/inflection_live.py#L461)）の妥当性が historical で測れない。
- **After（期待）**: historical レポートに `overextended` 群が追加され、他群と同じ指標（h5〜h252 の成績・+50% 到達率・MFE/MAE 等）が出る。
- **受入条件**:
  1. 群の件数の合計が signal 総数と一致する（欠けなし）。
  2. 既存 4 群の数値は変わらない（追加キーのみ）。変わる場合は理由を記録。
  3. 合成データで OVEREXTENDED が `overextended` 群に入るテストがある。
- **備考**: 評価の追加のみ。分類基準（r20 ≥ 50%・r60 ≥ 100%）は変えない。Monitor の「過熱」警告は対象外。

### REQ-003: CONTROL を forward 評価へ別経路で接続する

- **画面**: なし（forward 評価レポート）
- **対象ファイル**: [inflection_forward.py](../../src/evaluation/inflection_forward.py)（loader は :89 付近で `candidates` のみ読む）、[rebuild_inflection_forward_validation.py](../../scripts/rebuild_inflection_forward_validation.py)。learning への接続は含めない（[inflection_learning.py:139](../../src/evaluation/inflection_learning.py#L139) は現状維持）。
- **Before（現状）**: snapshot の `control_sample` は保存されているが、forward 評価は読まない。historical だけが CONTROL を評価している。
- **After（期待）**: forward レポートに、同じ日・保有期間・コスト条件の `control` 群が別キーで追加される。既存の candidate 系列には混ぜない。
- **受入条件**:
  1. `control_sample` を持つ snapshot（schema 5）で control 群が出る。持たない旧 schema では群が空で、エラーにならない。
  2. 既存の EARLY/WATCH/NONE/OVEREXTENDED の数値は変わらない（学習・評価の入力に混ぜない: [project-overview.md:66](../project-overview.md) の方針を維持）。
  3. fake の snapshot で、control 群が candidate 群と同じ entry/exit 規則で計算されるテストがある。
- **備考**: 実 snapshot は復号しない。検証は fake と一時ディレクトリで行う。

---

## 完了済み・保留中

### 完了済み
- なし（前の proposal の D1〜D3 は git 履歴を参照。今回は実装状況未確認）。

### 保留中（今回のスコープ外）
- 重み・閾値の変更、52 週高値の加点の見直し（M5）。REQ-001〜003 の結果が出てから判断する。
- 信用残・日々公表・空売りの取得（M3）。J-Quants スタンダード（月 3,300 円）が前提で、契約判断は REQ-001 の結果後。
- 売買単位 100 株・約定可否・ストップ高の扱い（G07）、出口別の資金推移（G06）、試行台帳と確認期間（G04）、依存を反映した区間（G05）。
- 爆発的価格の検定（PSY）・暴落確率の特徴量（M4）、注目・テーマ（M6）、新規上場銘柄の高値判定（M7）。いずれも測定結果を見てから。
- 60/120 日成績による EARLY の収益性判定（標本待ち）。
