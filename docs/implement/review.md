# ヘルプ機能レビュー（USER_GUIDE.md 準拠）

## 結論
- `index.html` / `accuracy.html` / `simulator.html` / `stock.html` にヘルプ導線（`?`ボタン）は実装されています。
- ただし、ユーザー向けヘルプ文言に不整合があり、修正が必要です。

## 指摘事項と修正案

### 1. HELP_CONTENT の誤字（優先度: 高）
- 対象: `dashboard/js/app.js:95`, `dashboard/js/app.js:97`, `dashboard/js/app.js:103`, `dashboard/js/app.js:104`, `dashboard/js/app.js:108`, `dashboard/js/app.js:132`
- 事象: Unicodeエスケープ文字列に誤りがあり、表示文言が不自然（例: 「銅柄4」「銃柄」「倉想」）。
- 修正案:
  - `\u9283\u67c4` を `\u9298\u67c4`（銘柄）へ統一
  - `\u4ed3\u60f3` を `\u4eee\u60f3`（仮想）へ修正
  - `\u6bce\u9031\u306e\u4e0a\u6607\u4e88\u6e2c\u9285\u67c04\u3092` を `\u6bce\u9031\u306e\u4e0a\u6607\u4e88\u6e2c\u9298\u67c4\u3092` へ修正
- 備考: 文字列を Unicode エスケープで保持する場合は、同種文字列（銘柄/仮想）を一括置換すると取りこぼしを防げます。

### 2. USER_GUIDE の LINE 補助通知説明がヘルプに未反映（優先度: 中）
- 根拠: `docs/guide/USER_GUIDE.md:8`, `docs/guide/USER_GUIDE.md:36`, `docs/guide/USER_GUIDE.md:37`, `docs/guide/USER_GUIDE.md:38`
- 事象: ヘルプモーダル（`dashboard/js/app.js` の `HELP_CONTENT`）に LINE 補助通知の説明がない。
- 修正案:
  - 「このシステムでできること」に以下を追加:
    - `必要に応じて LINE で「Slack確認リマインド」を受け取る`
  - 追記（短文）:
    - `LINEは補助通知です（Slack確認の促進）`
    - `LINE失敗時でも Slack が届いていれば運用は継続されます`

### 3. simulator ページ見出しの用語不一致（優先度: 低）
- 対象: `dashboard/simulator.html:34`
- 事象: 見出しが「料金シミュレータ」になっており、ガイドの「投資シミュレータ」と不一致。
- 修正案:
  - `料金シミュレータ` → `投資シミュレータ`

## 受け入れ確認チェック
- ヘルプモーダル内で「銘柄」「仮想」が正しく表示される
- ヘルプモーダル内に LINE 補助通知の説明が表示される
- `simulator.html` の見出しが「投資シミュレータ」になっている

---

## plan.md 再レビュー（research3整合性） 2026-02-20

### 結論
- フェーズ7〜10の骨子は概ね整合しています。
- ただし、research3の必須要件に対して以下4点の不足があります。

### 指摘事項と修正案

### 1. 参照パス誤記（優先度: 高）
- 対象: `docs/implement/plan.md:4`
- 事象: `docs/gpt_reseach.md/research3.md` と記載されており、実ファイルパスと不一致です（正: `docs/gpt_reseach/research3.md`）。
- 修正案: 目的セクションの参照先を正しいパスへ修正する。

### 2. バックテスト品質開示の要件不足（優先度: 高）
- 根拠: `docs/gpt_reseach/research3.md:12`, `docs/gpt_reseach/research3.md:157`, `docs/gpt_reseach/research3.md:196`
- 事象: research3は Reality Check / PBO / Deflated Sharpe の開示を求めていますが、planは `num_rules_tested` などのメタデータ中心で、当該指標の算出・公開要件が明記されていません。
- 修正案: フェーズ9に `reality_check_pvalue`, `pbo`, `deflated_sharpe` の出力項目と算出責務（`src/baseline.py`）を追加する。

### 3. 透明性メタデータの適用範囲が不足（優先度: 中）
- 根拠: `docs/gpt_reseach/research3.md:193`
- 事象: research3は成果物JSONに `as_of` と `data_coverage` の明示を最低要件としています。planでは `macro.json` の `as_of_utc` と `comparison.json` の `data_coverage_weeks` はありますが、`predictions.json` / `accuracy.json` への適用が計画化されていません。
- 修正案: 共通仕様として `predictions.json`, `accuracy.json`, `comparison.json`, `macro.json` に `as_of` / `data_coverage` を統一追加する。

### 4. 校正ダッシュボードの集計粒度不足（優先度: 中）
- 根拠: `docs/gpt_reseach/research3.md:82`
- 事象: research3は Brier/log-loss を「全期間」と「直近N週」で併記することを推奨しています。planは指標表示までで、2ウィンドウ併記が仕様化されていません。
- 修正案: フェーズ7の `accuracy.json.calibration` を `overall` と `recent_n_weeks` に分割し、UI表示要件にも追記する。

### 受け入れ確認チェック（追記）
- `plan.md` の research3参照パスが実在パスと一致している。
- フェーズ9仕様に Reality Check / PBO / Deflated Sharpe が含まれている。
- `predictions.json` / `accuracy.json` を含む主要成果物に `as_of` / `data_coverage` が定義されている。
- 校正指標が「全期間 + 直近N週」で表示される。

---

## plan.md レビュー（2026-02-20 追加）

### 結論
- 前回指摘の反映は概ね完了しています。
- ただし、実装時に仕様解釈が分かれる点が2件あります。

### 指摘事項と修正案

### 1. 透明性メタデータ仕様の自己矛盾（優先度: 高）
- 対象: `docs/implement/plan.md:276`, `docs/implement/plan.md:280`, `docs/implement/plan.md:285`, `docs/implement/plan.md:342`
- 事象: 「全成果物 JSON に `as_of` と `data_coverage` を統一付与」と記載がある一方、`macro.json` の `data_coverage` は「-（なし）」になっており、受け入れ確認とも矛盾しています。
- 修正案:
  - 方針A: `macro.json` にも `data_coverage`（例: `data_coverage_latest_date` など）を定義して統一する。
  - 方針B: 対象を「予測/評価系JSONのみ」に明示的に限定し、該当の受け入れ確認文言を合わせて修正する。

### 2. フェーズ9の初期設定と品質指標算出要件の不整合（優先度: 中）
- 対象: `docs/implement/plan.md:169`, `docs/implement/plan.md:173`, `docs/implement/plan.md:189`, `docs/implement/plan.md:200`
- 事象: `reality_check_pvalue` / `pbo` / `deflated_sharpe` の算出責務は明記されていますが、初期設定が `num_rules_tested: 1` のため、指標が恒常的に `null` になりやすく、フェーズ9の目的（品質開示）を満たしにくい構成です。
- 修正案:
  - `num_rules_tested` の最小要件（例: 2以上、推奨は10以上）を計画に追加する。
  - 算出条件未達時の明示ステータス（例: `hygiene_status: "insufficient_trials"`）を `comparison.json` 仕様に追加する。

### 受け入れ確認チェック（追加）
- `macro.json` の `data_coverage` 方針が計画全体で一貫している。
- フェーズ9で、品質指標が `null` のまま固定化しないための条件（最小試行数または未達ステータス）が定義されている。

---

## plan.md レビュー（2026-02-20 第3回）

### 結論
- これまでの指摘反映は進んでいます。
- 追加で、実装時に解釈ブレを起こす仕様不整合が2点あります。

### 指摘事項と修正案

### 1. `as_of_utc` の意味がセクション内で不一致（優先度: 中）
- 対象: `docs/implement/plan.md:305`, `docs/implement/plan.md:308`
- 事象: `as_of_utc` を「書き込み時のUTC現在時刻」と定義する一方、`macro.json` では「FREDの最新系列日時を使用」と記載されており、同名フィールドの意味がファイル間で異なっています。
- 修正案:
  - 方針A: `as_of_utc` を全JSONで「生成時刻」に統一し、系列基準日は別名（例: `data_as_of_utc`）で保持する。
  - 方針B: `as_of_utc` を「データ基準時刻」に統一し、生成時刻は `generated_at_utc` を追加する。

### 2. 共通メタ関数の配置責務が曖昧（優先度: 中）
- 対象: `docs/implement/plan.md:289`, `docs/implement/plan.md:293`, `docs/implement/plan.md:307`
- 事象: `build_common_meta(records)` を `src/exporter.py` に置くと記載されていますが、`comparison.json` の担当は `src/baseline.py` とされており、どのモジュールが共通メタ生成を担うかが不明瞭です。
- 修正案:
  - 共通処理を `src/meta.py`（または `src/common_meta.py`）へ分離し、`exporter.py` と `baseline.py` から利用する方針を明記する。
  - もしくは `baseline.py` が `exporter.py` の関数を利用する設計であることを明示し、依存方針を固定する。

### 受け入れ確認チェック（追加）
- `as_of_utc` の意味が全成果物で一意に定義されている（生成時刻 or データ基準時刻）。
- 共通メタ生成ロジックの配置モジュールと呼び出し元（`exporter.py` / `baseline.py`）が明示されている。

---

## plan.md レビュー（2026-02-20 第4回）

### 結論
- 重大な方針矛盾は解消済みです。
- 実装時の取りこぼし防止の観点で、以下2点を追加修正するのが安全です。

### 指摘事項と修正案

### 1. フェーズ別スキーマ例に共通メタデータが未反映（優先度: 中）
- 対象: `docs/implement/plan.md:53`, `docs/implement/plan.md:61`, `docs/implement/plan.md:287`, `docs/implement/plan.md:369`
- 事象: 共通仕様では `predictions.json` / `accuracy.json` に `as_of_utc` / `data_coverage_weeks` を付与すると定義されていますが、フェーズ7のスキーマ例には当該項目が出ていません。
- 修正案:
  - フェーズ7の `predictions.json` / `accuracy.json` 例に `as_of_utc` / `data_coverage_weeks` を明示追加する。
  - もしくは各フェーズ例の直下に「共通メタデータは共通仕様セクション準拠」と明記して実装漏れを防ぐ。

### 2. フェーズ9のテスト計画が不足（優先度: 中）
- 対象: `docs/implement/plan.md:216`
- 事象: フェーズ7/8/10にはテストファイルが明記されていますが、フェーズ9の対象ファイルにテスト追加がありません。`hygiene_status` 分岐や `min_rules_for_pbo` 条件は回帰しやすく、テスト計画が必要です。
- 修正案:
  - 対象ファイルに `tests/test_baseline.py`（または同等）を追加し、少なくとも以下を検証対象にする。
  - `num_rules_tested < min_rules_for_pbo` で `hygiene_status = insufficient_trials` となること。
  - 条件充足時に `reality_check_pvalue` / `pbo` の算出分岐へ進むこと。

### 受け入れ確認チェック（追加）
- フェーズ別スキーマ例と共通仕様の必須フィールド定義に齟齬がない。
- フェーズ9の品質指標ロジックに対するユニットテスト追加が計画に含まれている。

---

## plan.md レビュー（2026-02-20 第5回）

### 結論
- 新規の指摘事項はありません。
- 直近レビュー（第4回）の未反映項目が継続している状態です。

### 継続確認事項（第4回から変更なし）
- フェーズ7のスキーマ例に `as_of_utc` / `data_coverage_weeks` が未記載（共通仕様との対応明記が必要）。
- フェーズ9の対象ファイルにテスト計画（`tests/test_baseline.py` など）が未記載。

---

## plan.md レビュー（2026-02-20 第6回）

### 結論
- 第4回で指摘した2点（フェーズ7の共通メタ注記、フェーズ9のテスト計画）は反映済みです。
- ただし、文言整合に軽微な不一致が1件あります。

### 指摘事項と修正案

### 1. 共通仕様の適用範囲と注記文言の不一致（優先度: 低）
- 対象: `docs/implement/plan.md:54`, `docs/implement/plan.md:293`, `docs/implement/plan.md:296`
- 事象: フェーズ7注記で `as_of_utc` / `data_coverage_weeks` を「全成果物に統一付与」としていますが、共通仕様セクションでは適用範囲を「予測/評価系JSON」に限定し、`macro.json` は `data_coverage_weeks` 対象外と定義しています。
- 修正案:
  - フェーズ7注記の「全成果物に統一付与」を「予測/評価系成果物に統一付与（macro.jsonは対象外）」へ修正する。

### 受け入れ確認チェック（追加）
- フェーズ7注記と共通仕様セクションで、`data_coverage_weeks` の適用範囲が同一文言で定義されている。

---

## plan.md レビュー（2026-02-20 第7回）

### 結論
- 新規の指摘事項はありません。
- 第6回で指摘した文言不整合は `docs/implement/plan.md:54` で解消され、共通仕様（`docs/implement/plan.md:293`, `docs/implement/plan.md:296`）と整合しています。

### 補足
- 現時点の `plan.md` は、review.md の第1回〜第6回で挙げた主要指摘を反映済みと判断します。

---

## plan.md レビュー（2026-02-20 第8回）

### 結論
- 新規の指摘事項はありません。
- `plan.md` は第7回レビュー時点の整合状態を維持しています。

### 補足
- 本レビュー時点で、追加修正が必要な不備は確認されませんでした。
