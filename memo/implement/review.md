# 未来日足・四半期・業種相対診断値 実装計画レビュー

レビュー日: 2026-10-07

対象: [plan.md](plan.md)（REQ-052 / REQ-053 / REQ-054）。[proposal.md](proposal.md) と現行の取得・候補評価・履歴財務参照経路を確認した。

## 結論

VERDICT: PASS

計画は実装開始可能（READY）。Blockingに該当する指摘はなく、REQ-052〜054を実装した。最終差分の独立レビューもPASS。

初回取得・再取得後の未来日足を除外し、失敗診断とSlack通知に最新日分布・除外銘柄数を追加した。四半期と業種相対の8特徴量は診断値として記録し、既存のスコア・候補選定・戦略には使用しない。

## Implementation notes

- ライブの財務取得元は判定日で行を絞らないため、新しい四半期診断値にだけ開示日の上限を適用した。既存の財務スコアの扱いは維持した。
- 保存済みキャッシュを読み取り、[取得率の測定メモ](../analysis/quarterly_feature_coverage_2026-10-07.md) に集計した。1月・4月の加速は履歴不足で過半数が欠損する。過去履歴の拡充は別作業の判断事項であり、今回の実装には含めない。

## 検証

- 全テスト568件PASS、カバレッジ95.50%。ruffとCI対象30ファイルのmypyもPASS。
- 未来日足の境界、累計からの四半期差分、中央値の計算を壊すと追加テストが失敗することを確認。既存のスコア・選定結果の回帰検証もPASS。
- `minimal_diff_guard.py` と `git diff --check` はPASS。Harnessのfullプロファイルは未初期化のため、既存CIの検証コマンドで確認した。
- 外部API呼び出し・実通知・キャッシュ更新は行っていない。

---

## REQ-055〜057 実装計画・実装レビュー

レビュー日: 2026-10-07

対象: 現在の [plan.md](plan.md) と [proposal.md](proposal.md)。上記の REQ-052〜054 は前回のレビュー記録。

### 結論

VERDICT: PASS / READY

実装を妨げる指摘はない。REQ-055〜057を実装し、今回の8ファイルの差分に対する独立レビューもPASS。

- learning に10特徴量の区分と業種ラベルを追加した。既存ラベルの順序・値を維持し、欠損・不正な値は追加しない。新しいラベルは既存の Fisher 検定・BH 補正に入る。
- Monitor に20営業日で+50%以上の過熱警告を追加した。stop接近と重なる場合も1銘柄1通にまとめ、既存の `last_warned_at` で同日の再送を抑止する。売却判定とstopの計算は変更していない。
- グループの `deflated_sharpe` を追加した。ベースコスト・満期済み・銘柄ごとの重複除外後に30取引以上あるルールを対象とし、計算不能なら `None` と理由を返す。計算は [Bailey & López de Prado (2014) の原論文](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) の式(2)と照合した。

### Implementation notes

- Monitor の `fetch_split_adjusted_history` は購入日から取得し、返す確定終値は購入日の翌営業日以降だけ。今回も取得範囲を維持したため、購入後の確定終値が20営業日分ない銘柄は、要件の履歴不足時の扱いに従って過熱警告を出さない。取得回数・取得範囲・通信量は増えていない。
- 計画の要件書リンク `proposal_req055-057.md` は存在しないが、同じ要件が現在の `proposal.md` にあるため、こちらをレビューの根拠とした。
- 経過日数は現行の `_age_days` が返す整数日。30日・60日・90日を各区分の上限に含めるため、既存の `<` 比較の `_bucket` に31・61・91日の境界を渡している。
- Harness の既存タスク範囲には前回作業が残っており、全体の差分ガードは作業開始時から存在した `plan.md` / `proposal.md` の置換を検出する。これらは編集せず、今回のコード・テスト8ファイルを指定した差分ガードはPASS。登録済み検証コマンドも未初期化のため、既存CIのコマンドを使用した。

### 検証

- ruff、CI対象30ファイルのmypy、今回の差分チェックはPASS。
- ラベル境界を `<=`、過熱閾値を51%、DSRの試行数を常に2にする変更をメモリ内で加え、それぞれ受入テストが失敗することを確認した。作業ツリーに一時的なバグは書き込んでいない。
- 全テスト611件PASS、カバレッジ95.58%（80%以上）。今回のコード・テスト・レビュー追記を指定した `minimal_diff_guard.py` と `git diff --check` もPASS。
- 本番scan、戦略・スキーマのバージョン、売却ルールの採用は変更していない。外部API呼び出し・実通知・キャッシュ更新は行っていない。

---

## REQ-058 市場区分別ベンチマーク 実装計画レビュー

レビュー日: 2026-10-07

対象: 現在の [plan.md](plan.md) と [proposal.md](proposal.md)。上記のREQ-052〜057は過去のレビュー記録。

### 結論

VERDICT: PASS / READY

前回のBlockingは、追加ETFを別に取得する計画への修正で解消済み。計画指定の `2516.T` でREQ-058のコードと自動テストを実装した。今回の4ファイルの差分に対する独立レビューもPASS。計画にあるETF採用の確認と実データ検証の実行確認は未回答であり、実データ検証は実行していない。

### 初回のBlocking（解消済み・参考）

**指摘1: `required` から外すだけでは `2516.T` の取得失敗を任意扱いにできない。**

状態: 解消済み。既存の取得は維持し、追加ETFを別の取得に分離した。以下は初回の計画に対する指摘記録。

- 対象: 計画の「事前に確認した事実」1項目目とStep 3。`fetch_price_histories` の同じ取得対象に `2516.T` を加え、`required` に入れなければ続行できるという前提が誤っている。
- 根拠: [forward_prices.py](../../src/data/forward_prices.py) は、必須銘柄の欠損とは別に、全取得対象の欠損率が `MAX_FAILURE_RATIO = 0.05` を超えると `RuntimeError` を送出する。
- 再現: 観測銘柄1件と `1306.T` の取得は成功する。同じ取得対象に `2516.T` を追加し、その銘柄だけ欠損させると、欠損率 `1 / 3 > 5%` により `RuntimeError: Price retrieval failed for 1 ticker(s)` になる。既存の `FakeDownload` を使用し、外部通信・キャッシュ書き込みなしで確認した。
- 影響: 既存の候補・TOPIX価格がすべて取得できても、新しいETFの欠損だけでレポート生成が止まる。REQ-058受入条件3「2516.Tの価格が取得できないときもレポートを生成する」を満たせない。
- 必要な修正: `2516.T` の失敗を既存の必須価格取得・失敗率判定から分離する方針を計画に明記する。例えば、既存の取得は維持し、追加ETFを別に取得してその失敗だけを理由付きの欠損として扱う。既存銘柄の5%ガードを緩めたり、既存取得の例外をまとめて握りつぶしたりしない。
- Blocking Qualification Gate: 条件1=NO、2=NO、3=YES（既存のレポート生成経路を追加ETFの欠損で停止させる）、4=YES（受入条件3を満たせない）、5=NO。分類根拠は条件3・4。

### Implementation notes（非Blocking）

- `paired_benchmark_returns` の行には `signal_date` がない一方、`summarize_benchmark_excess` は評価可能な行の `signal_date` を参照する。新しい市場別集計でも、既存の `_paired_trade_rows` と同様に取引情報とペアリング結果を合わせてから要約する。
- 市場の参照キーはStep 3の方針どおり、シグナル日と銘柄の組とする。銘柄だけの対応表にすると市場変更前後の観測を区別できない。具体的な引数の型は実装時に決めればよい。
- `2516` が東証グロース市場250指数に連動するETFであることは [JPXの公式銘柄一覧](https://www.jpx.co.jp/equities/products/etfs/issues/01-01.html) で確認できた。計画にあるユーザーの採用確認と実データ実行の確認を、この事実確認で代替した扱いにはしていない。

### 初回の検証（参考）

- 現行の取得・市場保存・ペアリング・レポート組立・価格ハッシュの経路を確認した。
- 上記の取得失敗を既存のテスト用取得モックで再現し、確認スクリプトの終了コード0を確認した。
- コード・テスト・計画は変更していない。実データでの再構築・外部の価格取得・実通知は実行していない。

### 再レビュー・実装の検証

- 市場とベンチマークの対応を追加し、売却ルールごとに満期済み取引の `market_benchmark_excess` を併記した。市場はシグナル日と銘柄の組で参照する。引数を省略する学習・過去検証の出力は維持する。
- `2516.T` は既存取得とは別に取得し、その取得の `RuntimeError` だけを捕捉する。失敗時は追加の集計に `value: None` と例外の種類・理由を記録する。TOPIXの必須取得と既存銘柄の5%ガードは維持した。
- 追加ETFは候補銘柄の履歴に混ぜず、価格ハッシュはTOPIXと同じ期間で追加する。共有キャッシュの読込・保存は既存エントリを維持することを確認した。
- 対象83テスト、ruff、CI対象30ファイルのmypyはPASS。合成価格の手計算、市場変更前後の参照、満期前の除外、既存レポートのキー順・値の一致、取得失敗時の続行と既存ガード、既存ハッシュとキャッシュの維持を確認した。
- 市場の対応をTOPIXに置き換える変更と、全市場にTOPIXの価格を使う変更をメモリ内で加え、受入テストがそれぞれ失敗することを確認した。作業ツリーに一時的なバグは書き込んでいない。
- 全テスト621件PASS、カバレッジ95.61%（80%以上）。今回のコード・テスト・レビュー更新の `minimal_diff_guard.py` と `git diff --check` はPASS。Harnessの登録済みコマンドは従来どおり未初期化のため、既存CIのコマンドで検証した。
- 採用確認と実データ検証は計画の確認待ち。実データ検証を行う場合は、既存snapshotを読んで `.harness/runtime/req058-live/` を `--repo-root` に指定し、価格キャッシュ・ハッシュ・出力をその隔離先へ保存する。

---

## REQ-059〜061 EDINET 実装計画レビュー

レビュー日: 2026-10-07

対象: 現在の [plan.md](plan.md) と [proposal.md](proposal.md)。上記は過去のレビュー記録。

### 結論

VERDICT: PASS / READY（REQ-059・REQ-060・REQ-061のlearning接続を実装済み）

前回のBlockingと関門の判断待ちは解消済み。更新された計画の「②過去検証への適用を見送る」に従い、発行会社対応表・ライブの診断値・learningへの接続を実装した。過去検証への接続は今回の対象外。最終差分の独立レビューもPASS。

### 初回のBlocking（解消済み・参考）

**指摘1: 後から取得した書類一覧と提出日時だけでは、取下げ前の過去時点を復元できない。**

- 対象: [plan.md](plan.md:41)のStep 1（350/360のみ保存）、Step 4（現在の取下区分で除外）、Step 6（後から取得したキャッシュで過去検証）。[proposal.md](proposal.md:10)の「提出日時があるので point-in-time で復元できる」という前提。
- 根拠: [金融庁 EDINET API仕様書 Version 2（2026年6月）](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/download/ESE140206.pdf)の3-1-3・3-1-5（本文55〜61ページ）。過去日を指定した一覧も更新され、取下げ後は元の `docTypeCode`、`submitDateTime`、`issuerEdinetCode` などが `null` になる。取下書も書類種別は `null` のため、350/360のみの抽出では取下げイベントを保存できない。
- 再現: 10月1日に350の書類が提出され、10月2日の判定時点では未取下げ、10月3日に取下げられたとする。10月4日に10月1日分を取得すると元の書類種別が消去されており、Step 1で除外される。10月2日の特徴量は本来1件なのに0件となる。`cutoff` を比較しても、失われた書類種別・提出日時・対象銘柄は戻らない。
- 影響: REQ-061の「判定時点で利用可能だった情報による過去検証」と、REQ-060と同じ意味の特徴量を保証できない。APIが正常応答した空リストと、後日の消去で復元不能になったデータも区別できず、欠損を0件としてlearningに入れる恐れがある。現行の [reconstruct_scan](../../src/evaluation/inflection_historical.py:320) は当時利用可能なデータだけでの復元を契約としている。
- 必要な修正: 後日取得した一覧で保証できる範囲と、当時の状態を復元できない期間の扱いを要件・計画で決める。厳密な過去時点の保証を維持するなら、復元不能な期間は `None` / 評価対象外とし、当時の状態を確認できるデータだけを用いる。Phase Aの保存対象とPhase Bへの関門も、その方針に合わせる。発行会社の特定だけでは、この問題は解消しない。
- Blocking Qualification Gate: 条件1=NO、2=YES（取下げ前の必要情報を予定の取得元から回収できない）、3=NO、4=YES（計画の方法では過去時点保証を満たせない）、5=NO。分類根拠は条件2・4。

### Implementation notes（非Blocking）

- 保存先の不一致は解消済み。計画の取得CLI・過去検証とも、要件書の `.data/edinet/filings/` に統一された。

### 検証

- 公式仕様、現行のキャッシュ読書き関数、過去検証の共通評価経路を確認した。
- 公式仕様の取下げ後の項目消去を合成データで再現し、同じ過去の `cutoff` に対して計画どおりの抽出・除外が取下げ前1件／後日の取得0件になることを確認した（終了コード0）。外部API・実通知・永続キャッシュへの書込みは行っていない。
- 変更はこのレビューへの追記のみ。コード・テスト・要件書・計画は変更していない。

### 第2回レビュー（2026-10-07。当時の指摘・現在は解消済み）

**指摘1は未解消: `captured_at ≤ cutoff` は、その判定時刻までの情報が揃っている保証にならない。**

- 修正済みの部分: `erased_records` と取得時刻を保存し、後日取得した消去記録を含む窓を `None` にする方針。初回の「10/3に取下げ、10/4に取得して10/2を評価」のケースは、この修正で0件にしない扱いになった。
- 残る問題: [plan.md](plan.md:45)の `day_usable` は、取得時刻が判定時刻以前なら無条件に利用可能とする。消去記録がない場合の分岐も、取得後の追加提出を検出しない。日別キャッシュは取得済みなら再取得しないため、途中時点の一覧がそのまま使われる。
- 再現1: 10/1の09:00に空の一覧を取得し、同日の10:00に350の書類が提出される。16:40の評価では `09:00 ≤ 16:40` により利用可能と判定され、件数は0。本来は1件であり、情報不足を `None` にする経路にも入らない。
- 再現2: 10/1の提出を同日17:00に保存し、10/2に取り下げられる。10/5の判定に古い10/1分と取下書の記録を渡しても、両方とも取得時刻が `cutoff` 以前なので利用可能となる。Step 4の提出日時・元の取下区分による集計では、古い記録の1件が残る。日別の取得時刻の比較だけでは、判定時点までの取下げを元の提出に反映できない。
- 根拠: [金融庁公式仕様](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/download/ESE140206.pdf)の3-1-3・3-1-5では、一覧の更新と別日の取下書を説明している。日付が同じでも、取得時点と判定時点の一覧は同一とは限らない。修正で追加された利用可能条件が、前回指摘の過去時点保証を十分に満たしていない。
- 必要な修正: 「その時刻までに取得した」ではなく、対象日の提出と判定時刻までの状態変更を反映できることを、利用可能条件にする。反映を保証できないキャッシュは `None` とする。取得済みの日を飛ばす再開機能と、判定に使える期間の保証を分け、上の2ケースを検証条件に加える。具体的な保存・更新方法は実装時に決めてよく、新しい履歴保存基盤を要求する指摘ではない。
- Blocking Qualification Gate: 条件1=NO、2=NO、3=NO、4=YES（不完全・古い記録を確定件数として返し、REQ-060の件数・取下げ除外とREQ-061の過去時点保証を満たせない）、5=NO。分類根拠は条件4。新しいBlocking分類ではなく、前回指摘に対する修正の未解消部分。
- 非Blockingの整合メモ: 要件書のREQ-059は「350/360だけ」「空のリスト」の旧形式のままなので、計画で決めた辞書形式・消去記録の保存に合わせる。修正の意図は明確なため、これ自体は実装方向の不明点ではない。
- 検証: 計画の `day_usable` 条件を合成データに適用し、再現1の0件／本来1件と、再現2の1件／本来0件を確認した（終了コード0）。外部API・実通知・永続キャッシュへの書込みは行っていない。今回もレビューのみ更新した。

### 第3回レビュー・Phase A実装（2026-10-07）

- 前回の2ケースは、取得時刻が判定時刻より古いため利用不可になる。取得時刻が同時刻・後の場合も、消去記録があれば利用不可になることを自動テストで確認した。前回のBlockingは解消済み。Phase Bの計算・接続は実APIの関門を通過してから行う。
- [edinet.py](../../src/data/edinet.py) に取得クライアント、辞書形式のキャッシュ、`day_usable`、匿名化したprobeを追加した。HTTP 429・全5xx・通信失敗は有限回で再試行し、その他の4xxは即時失敗する。3秒以上の間隔は差し替えた時計で確認した。エラーには状態コード・通信例外の種類を残し、元の例外文・URL・レスポンス本文は表示しない。
- [run_edinet_fetch.py](../../scripts/run_edinet_fetch.py) は `--probe DATE` と `--fetch --start --end` を提供する。取得は休日を含む全暦日が対象で、成功した空の日も保存し、失敗した日は保存しない。取得済みファイルは上書きせず、途中から再開できる。probeは日付・件数・所要時間・項目の有無／型／桁数だけを表示し、キャッシュを書かない。
- `.env.example` に値が空のキー名を追加し、CIのmypy対象に新しいソースとCLIを追加した。既存のscan・スコア・候補選定・バージョンは変更していない。
- Implementation note: [公式仕様](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/download/ESE140206.pdf)の4-1では350は大量保有報告書、360は訂正大量保有報告書。Phase Bで「新規」を350の全件と同一視せず、様式コードなどによる変更報告との識別を実APIの関門で確認する。Phase Aはその確認用に `formCode`・`ordinanceCode`・状態変更の識別項目も保存する。APIの更新時刻や状態変更行の扱いも、Phase Bで過去時点保証を実装する際の確認対象とする。
- 対象48テスト、ruff、CI対象32ファイルのmypyはPASS。取得時刻の比較を逆にする変更と消去記録を無視する変更をメモリ内で加え、追加テストがそれぞれ失敗することを確認した。作業ツリーに一時的なバグは書き込んでいない。今回の5ファイルに対する独立差分レビューもPASS。
- 全テスト669件PASS、カバレッジ95.73%（80%以上）。今回のコード・テスト・設定・レビュー6ファイルを指定した `minimal_diff_guard.py` と `git diff --check` もPASS。Harness共通検証入口は作業開始前からの `plan.md` / `proposal.md` の置換を検出して停止するため、それらは変更せず、今回の差分ガードと既存CIのコマンドで検証した。
- テストのHTTPはモックで遮断し、キャッシュはpytestの一時ディレクトリだけに書いた。実API・実通知・既存の永続キャッシュへの書込みは行っていない。実APIの受入確認結果は未取得なので、probe結果のメモは作成していない。

### 第4回レビュー・実API確認後の関門（2026-10-07）

**判断事項1: REQ-061の過去検証を、厳密な欠損のまま実装するか、対象外にするかを決める必要がある。**

- 新しい根拠: [実API確認メモ](../analysis/edinet_probe_2026-10-07.md)では、`issuerEdinetCode` と公式コードリストによる銘柄対応を確認済み。一方、消去記録がある日は26 / 31（84%）で、残存項目から大量保有報告だった可能性を否定できないと記録されている。この集計はメモの調査結果として参照し、今回APIで再取得した結果とはしていない。
- 現行実装との照合: [day_usable](../../src/data/edinet.py:133)は、消去記録が1件でもあれば利用不可を返す。計画のStep 4では、その日を60日の窓に1日でも含む判定日の全銘柄を `None` にする。このため、厳密な条件を実装しても過去検証で効果を測れない見込みというメモの判断は、現行コード・計画と整合する。
- 計画上の扱い: [plan.md](plan.md:63)は、この状況で「REQ-061の範囲（過去検証への適用）を、報告して判断を仰ぐ」と明記している。実装の一般的な依頼だけから、過去検証の見送りや近似への変更を選択した扱いにはしない。新しい設計上のBlockingは追加せず、計画で定めた関門の判断待ちとする。
- 選択肢: ①厳密な条件のまま実装し、欠損が多いことを取得率に明示する。②過去検証への適用を見送り、ライブの記録とlearningへの接続を進める。③近似として別扱いにする場合は、検証・昇格判定への利用範囲を先に要件で決める。近似を既存の検証経路へ黙って入れない。推奨は②で、当時のライブsnapshotを蓄積してから評価する。
- REQ-060のライブ記録は、この過去データの消去問題による判断待ちではない。REQ-061の方針を計画に反映すれば、確認済みの発行会社対応を使って次の実装を進められる。銘柄対応表とPhase Bは、現在の作業ツリーでは未実装であることを確認した。
- APIキーは現在 `.env` に存在する（値は表示・保存していない）。以前の「キー未用意」は解消済み。
- 検証: 合成データを現行の `day_usable` に渡し、後日取得した消去記録なしの日は利用可、消去記録が1件ある日は利用不可になること、窓に1日でも利用不可があると計画の利用条件を満たさないことを確認した（終了コード0）。今回はレビューのみ更新し、実API・実通知・永続キャッシュの変更は行っていない。

### 第5回レビュー・Phase B実装（2026-10-07）

- 計画の関門に②の選択が明記されたため、READY。過去検証の接続を見送っても、対象要件・境界・対応箇所・互換性・受入条件の確認方法が揃っており、追加の計画Blockingはない。`HistoricalData`・`reconstruct_scan`・過去検証CLIは変更していない。
- [edinet.py](../../src/data/edinet.py) で、公式ZIPのcp932 CSVから `issuerEdinetCode` → 証券コード → tickerを対応づける。提出者の `secCode` は使わない。ライブは毎回、対応表と60暦日の営業日一覧を新規取得し、古い日別キャッシュを使わない。取得の全体予算は300秒で、失敗・時間切れは3項目を `None` にしてscanを継続する。
- Implementation note: [公式様式コード一覧（別紙1）](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/download/ESE140327.xlsx)では、350に変更報告書も含まれる。新規件数は `010000`・`030000` のみ。変更は `010002`・`020002`・`030002`、360は訂正報告書として総件数に含める。未知の350の様式では新規件数を `None` とし、0件にしない。
- [inflection_live.py](../../src/screening/inflection_live.py) の候補と対照群に3診断値を記録する。提出は市場日から60日以内・16:40 JST以下に限定し、取下げは計画どおり実行時点の状態を使う。同じ `docID` の更新を重複計上せず、取下書が参照する元書類と子書類も除外する。正常取得の空窓は件数0・経過日数 `None`。スコア・分類・選定・戦略／schemaバージョンは維持する。
- [inflection_learning.py](../../src/evaluation/inflection_learning.py) に件数帯0／1／2以上と新規提出の有無のラベルを追加し、既存のFisher検定・BH補正へ接続した。欠損・非有限値はラベル化しない。workflowのscan stepにGitHub Secretsの `EDINET_API_KEY` を渡す設定を追加した。
- 独立レビューで見つかった実装上のずれは修正済み。提出日時と違い、状態変更日時はライブの取下げ除外の締切ではない。16:40後の取下書を無視せず、16:40以前に提出済みの書類を後の状態変更日時だけで落とさない。修正後のEDINET・ライブ133テストはPASS。
- 60日境界・提出の締切・取下げ除外・欠損の0件化・締切後の状態変更・締切後の取下げを壊す6通りの変更をメモリ内で加え、追加テストがすべて失敗することを確認した。合成6,000件・300銘柄の集計は約3秒。キー・個人名・会社名をログに出さず、テストのHTTPはすべて置換している。今回、実APIの再取得・実通知・永続キャッシュ更新は行っていない（公式の公開様式コード一覧のみ確認した）。
- 最終検証: 全体697テストPASS、カバレッジ95.86%。ruff・CI対象32ファイルのmypy・タスク対象13ファイルの `minimal_diff_guard.py`・`git diff --check` はすべてPASS。`validate_report`、forward／learning loaderは追加キーの有無の両方を読み込める。レビュー修正後の最終コードで全体テストを再実行し、終了コード0を確認した。

## REQ-062〜067 Stage 4B 実装計画レビュー

レビュー日: 2026-10-12

対象: 現在の [plan.md](plan.md) と [proposal.md](proposal.md)。以下は今回のレビュー結果。

### 結論

VERDICT: CHANGES REQUIRED（実装未着手）

### Blocking

**指摘1: Actions 出力だけでは、次の通常実行が前回の通知状態を判定できない。**

- 対象: [plan.md](plan.md:61) の「Actions 出力を第一候補」、[plan.md](plan.md:62) の「通常実行は snapshot 新規作成時のみ送信」、[plan.md](plan.md:65) の障害境界テスト。
- 根拠: `GITHUB_OUTPUT` と stdout は同じ workflow run 内の情報であり、次の通常実行へ通知成功・失敗を永続化しない。現行コードも既存 snapshot では `snapshot_created=False` となり、通知を `skipped:snapshot-existed` にする。
- 影響: Slack 送信前に停止して snapshot だけ残った場合、通常再実行は通知を送れず受入条件 (1) を満たさない。一方、既存 snapshot でも常に送る変更では、通知成功済みの通常再実行を抑止できず受入条件 (4)(6) を満たさない。手動再送だけでは「通常再実行で通知される」という要件の代替にならない。
- 必要な修正: 次回 run から読める通知状態をどこに永続化するか決め、通常実行の判定を計画に明記する。要件が許す既存 snapshot のメタ情報を使うか、理由を記した小さな状態ファイルを REQ-066 の atomic write 対象として使える。少なくとも `pending / succeeded` を区別し、状態の保存と Git push の順序、push 失敗時の再実行挙動を受入条件 (1)〜(6) に対応づける。
- Blocking Qualification Gate: 条件1=NO、2=YES（run 間で参照できる通知状態の保存先が未決定）、3=NO、4=YES（第一候補の方式では受入条件 (1)(4)(6) を同時に満たせない）、5=YES（状態の永続化境界が実装方式と変更ファイルを左右する）。分類根拠は条件2・4・5。

### 確認

- `plan_scope_guard.py` は READY-GATE / SCOPE-WARN 0 だったが、これは構造検査であり上記の実行間状態の矛盾は判定しない。
- 現行の `persist_report`、`_deliver_digest`、`inflection_shadow.yml` の scan→commit 順序を確認した。コード・workflow・テストは変更していない。

### 第2回レビュー・実装（2026-10-12）

VERDICT: PASS

- 前回Blockingは解消済み。通知状態を `dashboard/data/inflection/digest_state.json` の `pending` / `succeeded` としてrun間で保持し、通常再実行、明示再送、旧snapshot、状態保存・Git push失敗の境界を実装した。
- 最終差分を、権限・secret、通知消失／重複、atomic write、provider例外の伝播、テストの外部副作用の順に限定レビューした。追加のBlockingはない。
- 全1016テストPASS、coverage 95.77%、ruff PASS、mypyは既知31件のみ（新規0）。対象回帰200件も最終のprovider診断接続後にPASSし、外部通信試行は0。Action 5リポジトリのタグSHAは公式 `git ls-remote --tags` で再確認した。

## 現行 plan / proposal の整合レビュー（2026-10-12）

VERDICT: CHANGES REQUIRED（今回の実装は未着手）

### Blocking

**指摘1: plan は実装済みの Stage 4B、proposal は未実装の Stage 4C を対象としており、実装範囲が一致しない。**

- 対象: [plan.md](plan.md:1) のタイトル・スコープ・完了条件と、[proposal.md](proposal.md:1) の REQ-068〜070。
- 根拠: plan は REQ-062〜067 の実装を指示し、Stage 4C（Q08/B09）を明示的に対象外としている。proposal は Q08 の重複処理削減、B09 の文書整合、REQ-070 の境界テストを要求している。Stage 4B は [完了報告](../../.harness/reports/reliability-stage4b-2026-10-12.md) に完了と記録され、現行コードでも `scripts/run_inflection_shadow.py` の通知状態・再送、`src/data/atomic_write.py`、workflow の SHA 固定・lockfile 導入・PR secret 分離を確認した。
- 未実装側の証拠: `scripts/run_position_monitor.py:329,336` は保有行ループ内で価格履歴・当日足を取得し、`src/data/sheets_client.py:37-49` は `_worksheet()` 呼出しごとに認証・接続する。Stage 4C の計測・共有範囲・変更順序・同等性検証は現行 plan に含まれていない。
- 影響: plan に従っても proposal の受入条件を満たせず、proposal に従えば plan が除外した別フェーズを実装することになる。
- 必要な修正: plan を現在の proposal（REQ-068〜070）に合わせ、計測を先に行う順序、run 内だけの共有、position 固有処理の維持、文書更新範囲、baseline 完全一致と対象回帰の検証方針を示す。Stage 4B は完了済みの baseline として扱う。コードレベルの設計詳細は実装時に決めてよい。
- Blocking Qualification Gate: 条件1=YES（対象フェーズと実装範囲が相反する）、2=NO、3=NO、4=YES（現行 plan では REQ-068〜070 を満たせない）、5=YES（性能改善・文書更新と CI・通知・保存では変更範囲と進め方が異なる）。分類根拠は条件1・4・5。

### 今回の確認範囲

- 現行 plan / proposal、Stage 4B 完了報告、上記の実装と既存テストを照合した。過去の PASS・テスト件数は既存報告の記録であり、今回の再実行結果ではない。
- 今回の変更は本レビューへの追記のみ。計画・要件書・コード・workflow・テストは変更せず、実サービスへの接続・通知・永続データ更新も行っていない。

### 第2回レビュー（Stage 4C、2026-10-12）

VERDICT: READY（実装開始）

- 前回のBlockingは解消済み。plan / proposal とも REQ-068〜070 を対象とし、計測先行、run 内だけの共有、position 固有処理の維持、現行文書だけの更新、baseline 完全一致・外部通信禁止の検証方針が揃っている。Stage 4A/4B は完了済みの baseline として扱われている。
- 現行の取得・Sheets 接続・評価関数を照合し、追加の計画Blockingはない。実装詳細は対象コードと計測結果に基づいて決める。
- Implementation note: Step 6 の通知順序の記述は現行コードに合わせて文書化する。実際の `run_inflection_shadow.main()` は snapshot/latest 保存→通知状態保存・Slack→workflow の commit/push。文書側の修正で解決できるため、計画Blockingではない。
- Harness 正式入口は `verification commands are not initialized`、終了コード2で停止した。今回観測した原因は文書の全面差替え判定ではない。Harness設定は変更せず、CIの既存コマンドで本タスクを検証する。要件の実装・検証方法を変更する必要はないため非Blocking。

### Stage 4C 実装・最終レビュー（2026-10-12）

VERDICT: PASS（REQ-068〜070 実装完了）

- fake/syntheticのbeforeを保存してから、Monitorのticker単位の生履歴・当日足、Sheetsのrun内接続、評価レポートの整形済み系列・カレンダーを共有した。position別の分割補正・回収・stop・通知と可変copy、失敗分離、scope終了時の破棄を維持した。
- provider取得は4 position / 2 tickerで日次4→2・当日足4→2、Sheets認証／openは3→1。評価50 signalでは系列整形9,206→1,708、カレンダー正規化1,800→401。全report・portfolio・learningは値とキー順まで一致（learningの生成時計だけbefore時刻に固定）。準備済みデータ保持で計測peak memoryは約1.66MB増える。
- 現行仕様文書の暗号鍵・設定・Monitor時刻・通知状態／再送／Git反映順序・EDINETの確認段階等を現行コードに合わせた。過去記録・workflow・設定値は変更していない。
- 独立差分レビューはPASS。共有データの書換え、障害伝播、購入日別履歴、Sheetsの認証／retry／writer制限、文書の過剰主張を確認し、Blockingなし。最後に購入日前後の分割と独立取得の完全一致テストを強化し、同じreviewerの限定再確認もPASS。
- 全1032テストPASS、coverage95.74%、外部通信試行0。対象回帰はMonitor78・評価112・Sheets13件、最後の分割同等性テスト再実行もPASS。ruff PASS、mypyはpath/message単位で既知31件と一致し新規0。snapshot・archive・uv.lockの今回差分0、diff-check／minimal diff guard PASS。
- 詳細・変更不要候補・実環境未確認事項は [Stage 4C完了報告](../../.harness/reports/reliability-stage4c-2026-10-12.md) に記録した。Growthには進まず停止する。

---

## 修正コード再レビュー（2026-10-19、最新結果）

What this change does: ISSUE-15〜21の修正を、[issues-2026-10-16.md](issues-2026-10-16.md) の受入条件と現行コード・関連テストで照合した。前回指摘への未コミット修正も再確認した。以下が今回の最新判定であり、上の過去レビューとは区別する。

対象: `3f42da1..7b8ddad` のISSUE関連修正と現在の作業ツリー。実装コードは変更していない。全文上書きはHarnessフックが大量削除として拒否したため、過去記録を保持し、前回のISSUEレビュー節を今回の結果で上書きした。

### ISSUE-15〜21の確認結果

| ID | 結果 | 実装・検証根拠 |
|---|---|---|
| ISSUE-15 | 追加指摘なし | `_daily_session_is_valid` がHigh/Low/Closeの有限性・正値・整合を確認。不正な古い日足は `incomplete` とし、以前のcheckpointを維持。正常日・確認済み無取引日は従来の経路を維持。 |
| ISSUE-16 | 追加指摘なし | `_digest_states` が集合判定の前に値の文字列型を確認。配列・オブジェクト・数値・null等で通知だけを止め、snapshot保存は継続し、不正状態ファイルを変更しない。 |
| ISSUE-17 | 静的確認で追加指摘なし | Forward復号stepは「非PRかつmain」、learningの鍵利用はschedule条件。PRのsecret不要テストは維持。実Actions・GitHub側設定は未確認。 |
| ISSUE-18 | 現行の(a)、過去3市場日の回収を確認 | 保存済みsnapshotからpendingを再送し、成功を保存して次の実行での再送を抑止。休日・範囲外・snapshot欠損／復号不能を扱う。exactly-onceを保証しない前提を維持。 |
| ISSUE-19 | 追加指摘なし | High=120、従前最高値=100、stop=10%では判定・保存値ともstop=108。既存列を増やしていない。 |
| ISSUE-20 | 追加指摘なし | playbooksの「初期通知状態の保存失敗はrunを失敗させる」という旧説明を修正。現行docs・project-overviewに同じ旧主張は見つからない。 |
| ISSUE-21 | 前回の再送経路の指摘も解消 | 当日分の `sent:state-save-failed` に加え、過去分の保存失敗を `unsaved:N` で区別しmainで警告する。追加Slack送信をしない回帰テストあり。 |

ISSUE-18の(a)/N=3は現行実装・運用文書の方針として確認した。承認履歴はコードから証明できず、今回その方針は変更していない。

### Must fix — 前回D3指摘の残件

以下はISSUE-15〜21の未対応項目ではない。元のISSUE一覧が明示的に除外しているD1〜D3のうち、[proposal.md](proposal.md) の「証明できる下限だけで合格を確定する」という修正の再確認結果。

1. **[P1] ETFの欠測があっても下限を確定し、誤って合格する**（[inflection_historical.py:486](../../src/evaluation/inflection_historical.py#L486)）
   - **What this is:** `_excess_lower_bound` は銘柄側の未評価について、ETFのOpenと窓内の最高Closeから超過収益の下限を計算する。前回の実日付クラスタへの修正と、未評価がある場合に不合格を確定しない修正は反映済み。
   - **Problem:** `index >= entry_date` の先頭62行を使うため、ETFの実entry日が欠けても翌日のOpenで代用する。62行あることは必要な市場日の完備を証明せず、期間内の欠測も見逃すため、「欠測なら下限不明」とする現行方針に反する。
   - **再現:** 合成140営業日、シグナル2026-01-05、銘柄履歴は最初の10営業日だけとしてh60を未評価にした。ETFはOpen/Close=1000、実entry日2026-01-06の行だけ欠測。有効組120件の超過収益を+5%とすると、`unresolved_h60_outcomes → kill_criterion` は下限 **−100.15%**、感度分析CI下限 **+2.256957%** で `pass`。欠測行をOpen=100・Close=1000で補うと、下限 **−1000.15%**、CI下限 **−21.221304%** で `incomplete` になる。下限を証明できない欠測時点で保留が必要。
   - **Fix:** 実entry日の有効なETF Openと、既存の市場カレンダーに基づく必要期間の有効なCloseが揃うときだけ下限を返す。欠測・非有限値があれば `None` とし、後の日付で代用しない。既存historicalテストに開始日欠測・期間内欠測と集計元から合否までの回帰ケースを追加する。
   - **If we skip it:** データが欠けたことで下限が楽観的になり、完全なデータなら保留となる戦略を合格させる。

これは前回指摘2「超過収益の下限を保証できない」の残件。新しい特徴量・閾値・依存関係・別の設計項目は要求しない。

### 検証・変更範囲

- 上記の独立再現はfake/syntheticだけで行い、終了コード0と、欠測時の `pass`／補完時の `incomplete` を確認した。
- 関連7ファイル（Monitor、digest、workflow reliability、session gaps、historical、forward、learning）のテストは **455件PASS**、終了コード0、外部通信試行0。`.venv/bin/python -m pytest` に `-q -o addopts=` と一時 `--basetemp` を指定した。全体カバレッジは測定していない。
- 実API・実Slack・実Sheets、保存済みsnapshot・archive・永続キャッシュには接続・更新していない。スコア・重み・Q06閾値・Growthの変更もない。
- 全体のminimal diff guardは開始時から `proposal.md` の既存全面差替えで終了コード2。ガードや許可設定は変更していない。
- 更新した `review.md` を指定したminimal diff guardと `git diff --check` はPASS。

Verdict: ISSUE-15〜21に追加指摘なし。関連D3は指摘1を修正してから合否判定を利用する。

Not checked: 実Actions・実データ再生成・実配信。D3にはETF欠測時の誤合格リスクが残る。

---

## REQ-001〜003 計画レビュー（2026-10-21）

判定: **READY**。現行の一次選別、historical の群集計、forward の loader・価格取得・hash の開始日を計画と照合し、計画上のBlockingはない。REQ-001 → 002 → 003の順序と、スコア・閾値・分類基準を変更しない範囲を維持する。

### Implementation notes

- Step 7の「既存ケースは無修正」は、`tests/test_inflection_forward.py` のfixtureと群キー集合の期待値に限り調整が必要。現在のCLIテストは暗号文の代わりに `placeholder` を置き、旧candidate loaderだけをmockしている。別control loaderには空を返すmockを追加し、3群だけという期待値はcontrolを含む4群へ更新する。既存群の数値・hash・価格取得失敗の検証は維持し、別途controlあり／なしの同値性を検証する。これは検証方法の調整であり、要件・実装方向・既存データ保護を変更しないため非Blocking。
- 実キャッシュで、アイズ（5242.T）は2025-06-03の直前120市場営業日の終値が119本しかなく、底を確定できないためラベル未確定として除外される。弁護士ドットコム（6027.T）は最大約1.655倍で2倍の条件未達。この差は比較レポートに明記する。独立レビューでも「欠測を推測で埋めない」という計画と整合すると確認し、実装変更は不要と判断した。根拠: `.harness/reports/trader-implementation/focus-window-check.json`。

### REQ-001 実装時の指摘と修正（2026-10-22）

- 重複抑制が成立日だけを検査し、前イベントの底から120営業日以内にある底を再利用していた。受入条件の重複抑制を満たせないためBlocking（資格条件4）。底の位置も検査する2行の修正を加え、再交差で2件となる回帰テストが修正前FAIL・修正後PASSとなることを確認した。関連22テストPASS、外部通信試行0。
- 修正前の1490件は採用せず実キャッシュを再測定した。終了コード0、141.008秒、peak RSS 1,194,104 KiB、業務入力変更なし、外部通信試行0。入力と依存コードの同一性を確認した一次選別・既存集計キャッシュを再利用しており、時間はコールド実行の性能値ではない。8銘柄の出力・集計整合性を確認し、試作との差を [比較結果](../../.harness/reports/trader-implementation/prototype-comparison.md) に記録した。実行根拠: `.harness/reports/trader-implementation/req001-runtime.json`。

### REQ-002・003 実装確認

- historicalに`overextended`を追加。既存4群の全値不変と5群の件数合計を確認し、関連85テストPASS。
- forwardはcontrolを別loader・別群で評価する。候補価格取得の5%失敗ガードを維持し、control専用銘柄だけ別取得する。controlの取得失敗は原因と欠損件数を出し、候補群を継続する。旧snapshot・不正行・暗号/metadata検証、controls-only、同日同tickerの両cohort、既存群・recall・portfolio・価格hashの不変性の回帰18テストPASS。実snapshotは復号していない。
- 価格取得の事前見積もりはローカルv3の18ファイル×既定25行で最大450 control行、専用銘柄数はその以下。50銘柄/batchで最大9 batch（再試行を除く）、batch間待機は計4秒。既存の30分timeoutは維持するが、実APIと実snapshotでの総所要時間は未測定。
- 独立レビューはREQ-001の重複修正とREQ-003の最終差分を限定再確認してPASS。スコア・閾値・分類基準は変更していない。ruffとCI指定のmypy（33ファイル）PASS。
- 最終全体テストは1178件PASS、2件はsandboxがlocalhostサーバー用socket作成を拒否して失敗（`PermissionError: Operation not permitted`）。この2件だけ承認付きで制限外再実行し、2件PASS・終了コード0を確認した。合計1180ケース確認、coverage 96.33%、外部通信試行0。全体ログ: `.harness/runtime/trader-implementation/final-pytest.log`、再実行ログ: `.harness/runtime/trader-implementation/localhost-recheck.log`。

## REQ-001〜003 再点検と全体整合性（2026-10-22）

要件・現在の実装・本番scan・historical/forward・学習・workflow・出力文書を照合し、以下の2件を修正した。

1. **CONTROLの価格取得失敗で既存hashが消える（B3: 保護データ）**。取得できた銘柄だけで暗号化hash一覧を上書きしていたため、次回の取得成功時にCONTROLの価格改定を比較できなかった。保存時に取得できない銘柄の旧hashを残す1行へ修正。失敗中の保持と、復旧後の改定検出を回帰テストで確認した（修正前FAIL、修正後PASS）。候補のhash値・開始日、失敗割合のガードは変更していない。
2. **財務準備期間未達で価格評価まで中止する（B4: 受入条件）**。CLIの旧`days=[]`早期終了を削除し、既存report関数へ渡す。価格イベントを測定し、EARLY/WATCHは全件未評価とする。旧「No scan daysはエラー」のテストは新要件と衝突するため、終了コードだけでなく、イベントの存在・価格段階の評価件数・財務の未評価件数・summary保存を検証するテストへ変更した（修正前FAIL、修正後PASS）。bars自体が無いときのエラーは維持する。

CLI・forwardの関連103テストPASS（73.87秒、外部通信試行0）。スコア・分類・学習入力は変更していない。実API・実snapshot・本番workflowは実行していない。

修正後の全1181テストPASS（終了コード0、490.10秒、coverage 96.33%、外部通信試行0）。localhostテストを含め、承認付きでsandbox外実行した。ruff・CI指定mypy 33ファイル・独立再レビュー・minimal diff guard・diff checkもPASS。全体ログは `.harness/runtime/followup-review/full-tests.log`。本番scanの候補選別、暗号化snapshotと通知、forwardの候補群・recall・portfolio、candidateだけを読む学習、週次workflowの暗号化hash保存とsummary出力の接続を確認し、追加の不整合は認めなかった。

## Claude 確認: 漏れの点検と全体整合性（2026-10-22）

- 調査結果（Codex G01〜G12、Claude M1〜M7）と実装を1件ずつ対応づけた。表は [implementation-trace.md](../../.harness/reports/trader-gap-verification-claude/implementation-trace.md)。範囲内の漏れは1件だった。
- **漏れ: forward に OVEREXTENDED 群が無かった**。historical には REQ-002 で追加済みだったが、forward の群ループは EARLY/WATCH/NONE のままで、OVEREXTENDED の観測は読み込まれても recall にしか使われていなかった。除外判断の妥当性（M2）を本番の蓄積データで測れないため、群ループに追加した。先にテストへ期待値（群の存在と、候補4群の件数の合計＝signal 総数）を足し、修正前 FAIL・修正後 PASS を確認した。portfolio・recall・価格 hash の入力は変えていない。
- 独立に再実行: 全 1181 テスト PASS（Claude の補完前の状態、431.5 秒、coverage 96.33%、外部通信の試行 0）。補完後は forward 関連 143 テスト PASS。ruff PASS、CI 指定の mypy 33 ファイル PASS。
- スコア・閾値・分類基準・学習の差分なし（`src/strategy`・`explosion.py`・`inflection_learning.py` は無変更、`inflection_live.py` は一次選別の抽出だけ）。
- `project-overview.md` の記述（各 workflow の実行時刻、選別の既定値、コスト、保有期間、学習の期間、`show_candidates.py` のオプション）を実装と照合し、一致した。forward の群の説明に OVEREXTENDED を追記した。
- 番号の衝突: 今回の REQ-001〜003 は過去の `proposal_req001-036.md` と番号が重なるため、proposal・roadmap に注記した。
- 既存の状態として記録: `src/evaluation/inflection_forward.py` は HEAD の時点で CRLF と LF が混在している。追加行も CRLF のため `git diff --check` が行末の空白を報告するが、動作には影響しない。正規化は差分が大きくなるので行っていない。
- 未検証: forward workflow の実行時間（control 専用銘柄の取得が増える）、実 snapshot の `control_sample` の件数。いずれも実 API と復号鍵が要る。
