# レビュー対象
- docs/implement/plan.md (iteration 2)
- レビュー日: 2026-03-07
- レビュアー: Claude Opus 4.6
- 前回レビュー: iteration 1 (CHANGES_REQUIRED, 3 blocking issues)

---

# まず結論
- 判定: **APPROVED**
- 要点:
  1. 前回指摘した3件のBlocking issues (B1, B2, B3) はすべて適切に修正されている。`_VALID_ANALYSIS_TYPES` の更新が Step 1 と影響範囲テーブルに明記され、`collect_pair()` は `model_dump()` パターンに修正され、CLI の `TICKER_OPTIONAL_TYPES` 分岐ロジックが Step 6 にコード例付きで追加された。
  2. 前回の Non-blocking 推奨事項も大部分が反映済み: NB-1 (自己参照型検証) は Step 1 の検証項目に追加、NB-2 (`params` 型) は `dict[str, Any]` に変更、NB-4 (`--sector` オプション) は Step 6 のオプション一覧に追加、NB-7 (ファイルサイズ管理) はリスク4に800行超過時の分割ゲート条件として追加。
  3. リスクが4件から5件に増え、設定バリデーション不整合リスクが明示的に追加された。各リスクの対策も具体的で実行可能。
  4. 実装順序は依存関係に沿っており、各ステップに明確なゲート条件と検証基準がある。
  5. 新たなBlocking issues は発見されなかった。以下に Non-blocking の推奨事項を記載する。

---

# 前回Blocking修正の確認
- B1: **RESOLVED** -- `src/core/config.py` が影響範囲テーブルの変更ファイルに追加され（L63）、Step 1 に `_VALID_ANALYSIS_TYPES` へ7種追加するコード例が明記された（L93-104）。さらにリスク5（L285）でバリデーション不整合の早期検出を対策として記載。実際の `config.py` L260-264 の `_VALID_ANALYSIS_TYPES` セットと照合し、追加される7種がバリデータ `analyses_must_be_valid`（L306-315）を通過することを確認済み。
- B2: **RESOLVED** -- Step 1 の `collect_pair()` コード例（L116-123）が `primary.model_dump(exclude={"comparison_data"})` パターンに修正された。L124 に `frozen=True` Pydantic モデルとの互換性確保の注記あり。さらに L105-113 で `from __future__ import annotations` の確認と `model_dump()` / `model_validate()` の往復テスト、JSON シリアライズ/デシリアライズテストが検証項目に追加された。実際の `models.py` L83 で `AnalysisInput(BaseModel, frozen=True)` を確認し、`model_dump()` パターンが正しいことを検証済み。
- B3: **RESOLVED** -- Step 6（L218-229）に `TICKER_OPTIONAL_TYPES` セットと分岐ロジックのコード例が追加された。`stock_screener` / `portfolio_builder` 指定時は `--ticker` 省略可能で、ダミーティッカー `"MARKET"` を生成する仕組みが明確。混合タイプ指定時（`all(t in TICKER_OPTIONAL_TYPES for t in types)`）の挙動も正しく、カテゴリA/B のタイプが混在する場合は従来通りエラーになる。実際の `cli.py` L192-195 のコードと照合し、置換箇所が正確であることを確認済み。

---

# 必須修正（Blocking）

なし。

---

# 推奨（Non-blocking）

- [ ] **NB-1: カテゴリC テンプレートの `{financials_summary}` 処理**: カテゴリC（`stock_screener`, `portfolio_builder`）はダミーティッカー "MARKET" を使用するため、`_format_financials_summary()` は `Company: Market Overview (MARKET)` + 空の financials を出力する。テンプレート設計（Step 2）において、カテゴリC のテンプレートでは `{financials_summary}` の使用を最小限にし、代わりに `_user_prompt()` 内で `data.params` を直接フォーマットする設計を推奨。これは前回 NB-3 で指摘した点であり、実装フェーズで対応可能。

- [ ] **NB-2: `run_single()` のカテゴリB 分岐の将来的拡張性**: Step 6 で `run_single()` に `stock_comparison` の特殊分岐を追加するが、将来的に他の特殊データ収集パターンが増えた場合のスケーラビリティが懸念される（前回 NB-5）。`Analyzer` ABC に `collect_data(collector, ticker, **kwargs) -> AnalysisInput` のようなフックメソッドを追加するリファクタリングを、次回イテレーションの検討事項として記録を推奨。現時点では1種のみの特殊分岐なので、YAGNI 原則によりこのままで問題なし。

- [ ] **NB-3: テンプレート定数名と `name` フィールドの対応表**: 既存テンプレートでは `MA_ANALYSIS` -> `name="ma"`、`THREE_STATEMENT` -> `name="financial_statement"` のように定数名と name が異なるケースがある（前回 NB-6）。新規7種の定数名（`STOCK_ANALYSIS`, `STOCK_SCREENER` 等）と name フィールドの対応をコメントまたは表で Step 2 に追記すると、実装時の混乱を防げる。

- [ ] **NB-4: `--style` オプションの許容値バリデーション**: Step 6 の CLI オプション `--style TEXT` は自由テキストだが、例外・エラーハンドリング方針（L258）では「許容値（growth/dividend/value）をエラーメッセージに含めて表示」と記載されている。CLI レベルで `typer.Option(..., help="Investment style (growth/dividend/value)")` のヘルプ文を追加し、不正値の場合のバリデーションを `click.Choice` または手動チェックで実装することを推奨。

- [ ] **NB-5: `tests/conftest.py` の変更内容の具体化**: 影響範囲テーブル（L67）に `tests/conftest.py` が追加されているが、具体的にどのフィクスチャを追加するかの詳細がない。最低限 `comparison_data` 付き `AnalysisInput`、空 financials の `AnalysisInput`（カテゴリC用）、モック `LLMClient` のフィクスチャ名と概要を Step 7 に追記すると、テスト実装がスムーズになる。

- [ ] **NB-6: `analysis_exporter.py` のダミーティッカー対応**: `export_json()` はティッカーベースでファイルをグルーピングするため（L39: `output_dir / f"{ticker}.json"`）、カテゴリC の結果は `MARKET.json` として出力される。これは技術的に問題ないが、ダッシュボードの `index.json` に `"MARKET"` キーが含まれることになる。ダッシュボード側でこのキーを適切に表示するか、フィルタリングするかの方針を「含まないもの」セクションに明記するか、Step 6 の検証項目に追加を推奨。

---

# 影響範囲の追加提案

- 影響範囲テーブルは iteration 2 で十分に網羅されている。前回指摘した `src/core/config.py` と `tests/conftest.py` が追加済み。
- `src/export/analysis_exporter.py` は変更不要（ダミーティッカー "MARKET" でそのまま動作する）だが、NB-6 の通り出力結果の確認は検証フェーズで行うべき。

---

# テスト追加/修正提案

- Step 7 のテスト計画は包括的。前回提案した以下の項目がすべて反映済み:
  - `_VALID_ANALYSIS_TYPES` バリデーションテスト（Step 1 の検証項目に含まれる）
  - `AnalysisInput` 自己参照テスト（Step 1 の検証項目に `model_dump()` / `model_validate()` 往復テスト含む）
  - CLI 統合テスト（Step 6 の検証項目に `--ticker` 未指定 + `--type stock_screener` テスト含む）
  - `collect_pair()` エラーケース（例外・エラーハンドリング方針 L259 に記載）
  - 既存12種非影響テスト（Step 1 ゲート条件: `pytest tests/ -v` 全PASS）

- 追加推奨:
  - [ ] `--type stock_comparison` で `--compare` 未指定時のエラーメッセージに比較対象銘柄の指定方法が含まれることを確認するテスト（Step 6 L231 に記載はあるが、Step 7 のテスト項目に明示的に含まれていない）
  - [ ] `TICKER_OPTIONAL_TYPES` 以外のタイプで `--ticker` 未指定時に従来通りエラーになることを確認するネガティブテスト

---

# リスク再評価

1. **リスク 1 (`AnalysisInput` モデル変更) -- 適切**: 新フィールドは Optional/デフォルト値付きで後方互換性を保持。自己参照型の技術検証が Step 1 に追加され、リスク軽減策が具体的。`from __future__ import annotations` が `models.py` L9 で既に使用されていることを確認済み。リスクレベル: 中（前回から変更なし、妥当）。

2. **リスク 2 (API レート制限) -- 妥当**: `collect_pair()` の順次実行と `max_concurrent` 制限の組み合わせは適切。追加対策不要。

3. **リスク 3 (銘柄不要フロー) -- 解決済み**: `TICKER_OPTIONAL_TYPES` 分岐ロジックとダミーティッカー生成の仕組みが Step 6 に明記され、前回指摘した CLI との矛盾が解消。

4. **リスク 4 (テンプレート肥大化) -- 妥当**: 800行超過時のファイル分割ゲート条件が追加された。現在の `templates.py` は329行（実測値）であり、7テンプレート追加後も600-700行程度で800行以内に収まる見込み。

5. **リスク 5 (設定バリデーション不整合) -- 新規追加・妥当**: Step 1 の最初のタスクとして `_VALID_ANALYSIS_TYPES` 更新を配置し、ゲート条件で早期検出する設計は正しい。

6. **追加リスク評価**: 新たな重大リスクは発見されなかった。

---

# 次アクション

1. **実装着手可能**: 全 Blocking issues が解決済みのため、Step 1 から実装を開始する。
2. **NB-1〜NB-6 は実装フェーズで順次対応**: 特に NB-1（カテゴリC テンプレート設計）は Step 2 実装時、NB-4（`--style` バリデーション）は Step 6 実装時に対応。
3. **各ステップのゲート条件を厳守**: 特に Step 1 完了時の `pytest tests/ -v` 全PASS と `AnalysisInput` 自己参照型の検証を必ず実施。
4. **Step 2 完了時に `templates.py` の行数を確認**: 800行を超える場合は即座にファイル分割を実施。

---

**APPROVED**
