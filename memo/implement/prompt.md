Stage 4B の実装・検証が完了したので、Stage 4C を実施してください。

Stage 4A / 4B までの変更を現在のbaselineとして維持してください。

今回は以下の2項目だけを対象とします。

- Q08 重複取得・再計算の実行時間を抑える
- B09 運用・実装状態の文書に複数の不一致がある

**Growth Opportunityには進まないでください。**

また、Stage 4C完了後もGrowth実装は開始せず、一度停止して報告してください。

---

# Stage 4Cの目的

今回の目的は、

- 同一run内の不要な重複処理を削減する
- 現在の実装とドキュメントを一致させる

ことです。

投資戦略・検知ロジック・スコア・評価基準を改善または変更する段階ではありません。

原則として、

**同じ正常入力 → 同じ候補・同じスコア・同じ評価結果・同じ学習結果**

を維持してください。

Stage 4Cでは性能や保守性だけを改善してください。

---

# Stage 4A / 4B の保護

以下を現在のbaselineとして扱い、再設計しないでください。

Stage 4A:

- B05
- B06
- B10
- Q06
- Q10の外部通信禁止・境界テスト

Stage 4B:

- Q03 Forward PR / secret分離
- Q04 Slack通知状態・明示再送
- Q05 uv.lock / Action SHA / 最小権限
- Q07 provider障害分類
- Q09 atomic write

また、第1〜第3段階で修正済みの、

- C01〜C07
- B01〜B04
- B07
- B08
- Q01
- Q02

についても回帰させないでください。

---

# Q08 — 重複取得・再計算の削減

## 重要方針

**最適化する前に計測してください。**

推測だけでcache・並列処理・大規模な共通化を導入しないでください。

まず現在の処理について、固定サイズのfake / syntheticデータで可能な範囲で以下を計測してください。

- provider call数
- 同一tickerの価格取得回数
- Sheets connection / read / write回数
- 同じ価格系列の整形回数
- 同一統計計算の重複回数
- 実行時間
- peak memory

実環境・実APIを使ったベンチマークは不要です。

---

# Q08で優先して確認する箇所

精査レポートで指摘された以下を中心に確認してください。

## 1. Position Monitor の同一ticker取得

同じtickerについて複数の保有行がある場合、同じrun内で当日価格を何度も取得している場合は共有してください。

ただし、

- 購入日
- entry price
- stop
- position固有状態

などの取引固有計算は共有しないでください。

原則として、

**市場データ取得はticker単位で共有  
取引判定はposition単位で独立**

という境界にしてください。

異なる購入日のpositionが同じtickerに存在しても結果が変わらないことをテストしてください。

---

## 2. Sheets接続

同じrun内でread / writeごとに不要な再接続をしている場合は、安全に共有できる範囲で削減してください。

ただし、

- retry境界
- 認証エラー
- batch更新
- Q04通知状態
- C07 writer排他

を壊さないでください。

長寿命なグローバルconnectionや新しいconnection pool基盤は導入しないでください。

原則として1 run内だけで共有してください。

---

## 3. 評価系列・統計の再計算

複数の、

- horizon
- cost
- exit condition
- benchmark
- report

で同じ価格系列の、

- 正規化
- index調整
- 日付変換
- 共通統計

を繰り返している場合、安全に共有できるimmutableな中間結果だけ共有してください。

可変DataFrame等を共有して、後続処理が相互に影響する設計にはしないでください。

必要ならcopyやimmutable representationを使ってください。

---

# Q08で禁止する最適化

今回は以下を導入しないでください。

- 永続cacheの新設
- Redis等の外部cache
- 新しいDB
- multiprocessing
- 大規模なasync化
- providerへの並列大量アクセス
- 複雑なmemoization framework
- 新しい依存package
- 全面アーキテクチャ変更

Stage 4Cでは、

**低リスクなrun内共有**

に限定してください。

---

# Q08の結果同等性

最適化前後で、正常入力に対して最低限以下が完全一致することを確認してください。

- candidate
- EARLY_CANDIDATE
- classification
- score
- feature値
- stop判定
- notification対象
- outcome
- portfolio
- benchmark
- learning入力
- learning出力

順序について既存仕様上保証されているものは順序も維持してください。

浮動小数点計算順序を変えて結果が微妙に変化する最適化も避けてください。

---

# Q08の性能比較

可能な範囲で、修正前後を同一fakeデータで比較してください。

最低限、

- provider call数
- Sheets connection数

は具体的な数値を出してください。

可能なら、

- 実行時間
- peak memory

も比較してください。

ただし、ローカル実行時間の小さな差を性能改善の根拠として過度に解釈しないでください。

主な評価基準は、

**重複処理回数が構造的に減ったか**

としてください。

最適化効果がほとんどない箇所は、無理に変更せず「変更不要」と判断して構いません。

---

# B09 — 現在の実装と文書の整合

Q08完了後、現在のコードを正としてドキュメントを確認してください。

古い文書を機械的に全部書き換えるのではなく、

**現行仕様を説明する文書だけを更新してください。**

過去の、

- audit report
- analysis report
- implementation report
- research memo

は、その時点の記録として基本的に変更しないでください。

---

# B09で確認する項目

最低限以下を現在実装と照合してください。

## セットアップ

- 必須環境変数
- J-Quants関連設定
- 暗号化snapshot用key
- Slack
- Google Sheets
- その他secret

特にStage 4Aで追加した、

- `JQUANTS_PLAN`
- `JQUANTS_DATA_DELAY_WEEKS`
- 設定validation

を反映してください。

---

## GitHub Actions

現在の、

- workflow一覧
- schedule
- workflow_dispatch
- concurrency
- permissions
- secret利用
- uv.lock利用
- Action SHA固定

を反映してください。

古い時刻・古い権限・古い依存導入方法を残さないでください。

---

## Forward Validation

Stage 4Bで変更した、

- secret不要PR検証
- secret必須評価の分離
- fork PRの扱い

を反映してください。

---

## Position Monitor

現在の、

- 実行時間
- stop回収
- checkpoint
- incomplete判定
- branch / writer制限
- concurrency
- 通知状態

を反映してください。

---

## 通知

Stage 4BのQ04について、

- snapshot生成
- 保存
- Git反映
- Slack通知
- 通知状態
- 明示再送

が別状態であることを説明してください。

**Exactly-onceを保証すると記載しないでください。**

runner停止や、Slack受理後・状態保存前の停止などでは重複可能性が残ることを必要な範囲で明記してください。

---

## Watchdog

Q01で追加済みの、

- workflow失敗
- 未起動
- snapshot欠落
- 一般障害通知

の現在仕様を反映してください。

---

## provider障害

Q07で導入した安全な障害分類、

- timeout
- 429
- HTTP 5xx
- protocol異常
- empty
- validation
- authentication
- unexpected error

などについて、運用者が理解する必要がある範囲だけ記載してください。

実装詳細を過剰にドキュメント化する必要はありません。

---

## atomic write

snapshotや評価成果物がatomic writeされることを必要な範囲で反映してください。

ただし複数成果物全体がtransactionalであるとは記載しないでください。

---

## EDINET

現在のEDINETについて、

- コード接続済み
- test済み
- live利用
- historical利用
- learning利用
- 実API確認済み / 未確認

を実装に基づいて正確に整理してください。

「実装済み」と「本番で実証済み」を同一視しないでください。

---

# 状態表記

可能な場合、機能状態を以下のように区別してください。

- implemented
- tested with fake / unit test
- integration not verified
- production enabled
- production unverified

日本語文書なら自然な日本語表現にして構いません。

重要なのは、

**コードがあることと、実サービスで確認済みであることを区別すること**

です。

---

# B09で変更してはいけないもの

過去時点の事実を記録している、

- repository audit
- Stage 1〜4実装報告
- 過去の分析メモ
- 過去のbacktest結果

を現在仕様に合わせて書き換えないでください。

現行仕様を説明する、

- project overview
- setup
- operations
- README相当

の文書を中心に更新してください。

判断に迷う文書は変更せず報告してください。

---

# Harness関連

現在、

Harness正式入口が既存の `plan.md / proposal.md` の全面差替え判定で停止する問題があります。

これはStage 4C本体とは別問題として扱ってください。

Stage 4Cの「ついで修正」としてHarness infrastructureやinstallerを変更しないでください。

ただし今回の変更について、

- task対象minimal diff guard
- `git diff --check`
- review

など、利用可能な既存検証は実施してください。

Harness正式入口が同じ既存理由で停止する場合は、その事実だけ報告し、Stage 4C実装の失敗扱いにはしないでください。

新しいBlocking原因が発生した場合は別途報告してください。

---

# Q10 — Stage 4C分の境界テスト

Stage 4Aで導入した外部通信禁止fixtureを維持してください。

Stage 4Cでは特に以下を回帰テストとして固定してください。

- 同一ticker複数positionでも価格取得1回
- 異なる購入日のposition結果維持
- 共有DataFrame等によるcross contaminationがない
- provider失敗が他positionへ誤伝播しない
- Sheets共有後も既存結果維持
- 最適化前後の評価結果一致

B09については、文書だけの値を固定する目的で大量のテストを追加する必要はありません。

workflow時刻や重要設定など、自動照合が合理的な既存仕組みがあれば利用してください。

---

# baseline条件

Q08は原則として、

**baseline-preserving**

でなければなりません。

正常入力に対する戦略結果が1件でも変化した場合は、その原因を調査してください。

「性能改善のため」という理由だけで結果差を許容しないでください。

B09は文書変更のみなので、runtime baselineは変化しないことを期待します。

---

# 禁止事項

Stage 4Cでは以下を行わないでください。

- Growth Opportunity
- G01〜G07
- 新特徴量
- スコア変更
- 閾値変更
- 重み変更
- Q06の10件 / 5日 / 50%閾値変更
- ML framework導入
- 新provider
- 自動売買
- 自動発注
- 永続cache追加
- 大規模並列化
- 無関係な依存更新
- mypy既知31件のついで修正
- archive変更
- 過去snapshot変更
- 過去レポートの歴史修正
- Harness infrastructure修正
- 全面リファクタリング

---

# 最終検証

Stage 4C完了後、以下を実行してください。

- Q08対象テスト
- Q10 Stage 4C境界テスト
- Stage 4A回帰
- Stage 4B回帰
- 第1〜第3段階回帰
- 全テスト
- coverage
- ruff
- mypy
- 外部通信試行数
- `git diff --check`
- task対象minimal diff guard
- 保存済みsnapshot差分
- archive差分
- uv.lock差分

mypyについては、

- 既知baseline 31件
- 新規0件

を確認してください。

Stage 4Cでは依存変更を想定していないため、`uv.lock` は原則差分なしを期待します。

---

# Stage 4C完了報告

完了後はGrowthへ進まず停止してください。

以下を報告してください。

## 1. Q08

- 修正前の重複処理
- 修正内容
- 変更ファイル
- 追加テスト
- baseline一致結果

## 2. 性能比較

最低限、

- provider call数 before / after
- Sheets connection数 before / after

可能なら、

- 実行時間
- peak memory

も記載してください。

変更しなかった最適化候補があれば、その理由も書いてください。

## 3. B09

更新した文書ごとに、

- 何が古かったか
- 現在何に合わせたか

を整理してください。

過去記録として意図的に変更しなかった文書も明記してください。

## 4. baseline

Q08:

- baseline-preserving / changing

B09:

- runtime baselineへの影響

を報告してください。

正常入力の投資結果が完全一致したか明記してください。

## 5. 検証結果

- 全テスト件数
- failed
- coverage
- ruff
- mypy総件数
- mypy新規件数
- 最終対象回帰件数
- 外部通信試行数
- snapshot変更数
- archive変更数
- uv.lock差分
- `git diff --check`
- minimal diff guard

## 6. 未確認事項

以下をコード上の未解決問題と混同せず、integration / production未確認事項として整理してください。

- 実GitHub Actions
- 実Slack
- 実provider
- 実Google Sheets
- 実Git push
- runner強制停止
- GitHub Actions基盤障害

## 7. Harness

正式入口のBlockingが、

- 既存のplan.md / proposal.md問題と同一か
- 今回新しく発生した問題か

を区別してください。

既存問題だけなら、Stage 4CのBlockingとは扱わないでください。

## 8. 第4段階最終状態

以下について完了 / 未完了を整理してください。

- B05
- B06
- B09
- B10
- Q03
- Q04
- Q05
- Q06
- Q07
- Q08
- Q09
- Q10

そのうえで、監査で指摘されたCritical / Bug / Qualityについて、まだ未対応の項目が残っていないか確認してください。

ただし未対応が見つかっても、この依頼の範囲を超えて勝手に実装しないでください。

## 9. 次フェーズへの引き継ぎ

Growthへ進む前に必要な、

- 保守フェーズ最終baseline確定
- integration / production smoke test
- Growth候補評価

について、実施すべき事項だけ整理してください。

**Growth Opportunity自体の実装は開始しないでください。**

詳細レポートを、

`.harness/reports/reliability-stage4c-2026-10-12.md`

へ作成してください。