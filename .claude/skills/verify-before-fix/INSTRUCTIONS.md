# 証拠に基づく修正ゲート — 詳細手順

推測で修正してはならない。証拠を集めてから修正すること。
このスキルは **修正に着手する前のゲート** として機能する。

---

## 5フェーズプロセス

```
Phase 1: 現象の記録（事実のみ）
Phase 2: 仮説の列挙（最大3つ + 検証方法）
Phase 3: 証拠収集（レイヤー別の検証手段で実行）
Phase 4: 診断結果の報告（証拠付き）
Phase 5: 修正（原因確定後のみ着手可能）
```

**絶対ルール: Phase 3 を完了するまで Phase 5 に進んではならない。**

---

## Phase 1: 現象の記録

ユーザーの報告から **事実だけ** を抽出する。推測や解釈を含めない。

`tasks/verify-log.md` に以下のフォーマットで記録する:

```markdown
# 検証ログ: [問題の短い名前]
日時: YYYY-MM-DD

## Phase 1: 現象

### 報告された事実
- [ユーザーの報告をそのまま記述]

### 再現条件
- [いつ・どこで・どの操作で発生するか]

### 期待される動作
- [本来どう動くべきか]

### 実際の動作
- [何が起きているか]
```

**この段階では「なぜ」を考えない。「何が」だけ記録する。**

---

## Phase 2: 仮説の列挙

コードを読んで原因の仮説を **最大3つ** 列挙する。
各仮説に **検証方法** を必ずセットで記述する。

```markdown
## Phase 2: 仮説

| # | 仮説 | 可能性 | 検証方法 | 検証手段 |
|---|------|--------|----------|----------|
| 1 | [原因候補] | High/Med/Low | [何を確認すれば裏付けられるか] | [antigravity/ログ/テスト/DB] |
| 2 | [原因候補] | High/Med/Low | [何を確認すれば裏付けられるか] | [antigravity/ログ/テスト/DB] |
| 3 | [原因候補] | High/Med/Low | [何を確認すれば裏付けられるか] | [antigravity/ログ/テスト/DB] |
```

**検証方法のない仮説は無効。「たぶん○○だろう」は仮説ではない。**

---

## Phase 3: 証拠収集

### レイヤー判定

問題がどのレイヤーに属するかを判定し、対応する検証手段を選択する:

| レイヤー | 判定基準 | 検証手段 |
|---------|---------|---------|
| **フロントエンド** | UI表示・ユーザー操作・JS動作の問題 | antigravity IDE（[詳細](references/browser-verification.md)） |
| **バックエンド (PHP/Laravel)** | API・ビジネスロジック・ルーティングの問題 | docker compose exec + ログ |
| **Python** | スクリプト・データ処理の問題 | pytest + logging |
| **DB** | データ不整合・クエリの問題 | SQL直接実行 |
| **複合** | 複数レイヤーにまたがる | 各レイヤーの手段を組み合わせる |

---

### フロントエンド検証

詳細な手段・スクリプト・選択基準は **[references/browser-verification.md](references/browser-verification.md)** を参照。

**優先順位:**
1. **antigravity IDE** — スクリーンショット・DOM・コンソールログ・クリック・動画撮影
2. **ユーザーに依頼** — antigravity が使えない場合

**取得可能な証拠:** スクリーンショット、DOM キャプチャ（outerHTML + computed style）、コンソールログ、操作再現（クリック・ダブルクリック）

**検証結果が返ってくるまでコード修正を始めない。**

---

### バックエンド検証: PHP / Laravel

#### ログ確認
```bash
# Laravel ログ
docker compose exec laravel tail -f storage/logs/laravel.log

# 特定のエラーを検索
docker compose exec laravel grep -n "ERROR\|Exception" storage/logs/laravel.log | tail -20
```

#### デバッグ出力
```php
// 変数の値を確認（一時的に追加 → 確認後に削除）
Log::debug('変数確認', ['value' => $variable]);

// クエリログを有効化
DB::enableQueryLog();
// ... 処理 ...
Log::debug('実行SQL', DB::getQueryLog());
```

#### Tinker で手動実行
```bash
docker compose exec laravel php artisan tinker
>>> App\Models\Stock::where('department_id', 5)->count();
>>> DB::connection('blade_management')->select('SELECT * FROM 5_stock LIMIT 5');
```

---

### Python 検証

#### テストで入出力を確認
```bash
# 該当関数のテストを実行
uv run pytest tests/test_target.py -v -s

# 特定のテストケースのみ
uv run pytest tests/test_target.py::test_specific_case -v -s
```

#### ログで中間値を確認
```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

logger.debug(f"入力値: {input_value}")
logger.debug(f"処理結果: {result}")
```

---

### DB 検証

#### 実データの確認
```bash
# MariaDB に直接接続
docker compose exec mariadb mysql -u root -p

# テーブルの状態確認
SELECT COUNT(*) FROM 5_stock;
SELECT * FROM 5_stock WHERE product_number_id = 123 LIMIT 5;

# テーブル構造の確認
DESCRIBE 5_stock;
SHOW CREATE TABLE 5_stock;
```

#### Migration 状態の確認
```bash
docker compose exec laravel php artisan migrate:status
```

---

## Phase 4: 診断結果の報告

`tasks/verify-log.md` に検証結果を追記する:

```markdown
## Phase 3: 検証結果

### 仮説1: [仮説内容]
- 検証方法: [何をしたか]
- 結果: [観測した事実]
- 判定: **確認** / **棄却** / **要追加検証**
- 証拠: [スクリーンショット / ログ出力 / テスト結果]

### 仮説2: [仮説内容]
- ...

## Phase 4: 診断

### 確定した原因
[証拠に基づく原因の説明]

### 修正方針
[原因に対する修正案]
```

**原因が特定できない場合:**
- 「追加調査が必要」と報告する
- 推測で修正に進まない
- 追加の検証手段を提案する

---

## Phase 5: 修正（原因確定後のみ）

Phase 4 で原因が確定した場合のみ、修正に着手する。

修正後は再度 Phase 3 の検証手段で **問題が解消されたことを確認** する:
- フロントエンド → antigravity でスクリーンショット / DOM 確認
- バックエンド → ログで正常動作を確認
- Python → テストが通ることを確認
- DB → データが正しいことを確認

---

## 停止条件（強制ルール）

以下のパターンを検出したら **即座に停止** し、Phase 3 に戻る:

### 1. 同じ問題に2回修正を試みている
```
❌ 「前回は opacity を変えたが効かなかった。今度は z-index を変えてみる」
✅ 「前回の修正が効かなかったので、原因の理解が間違っている可能性がある。
    antigravity で [具体的な検証] を実行して確認する」
```

### 2. 微調整を繰り返している
以下のいずれかに該当したら停止:
- CSS 値（opacity, z-index, margin, padding）を2回以上変更
- setTimeout / sleep の ms を調整
- !important を追加
- try-catch / null チェックを追加し続ける
- `.env` / config の値を何度も変更

### 3. コードを読んだだけで断定している
```
❌ 「コードを読んだところ、このイベントハンドラーが原因です」
✅ 「コードからは X が原因の可能性がある。antigravity / ログ / テストで確認する」
```

---

## チェックリスト（各フェーズ完了時に確認）

### Phase 1 完了
- [ ] 現象を事実ベースで記述した（推測を含めていない）
- [ ] `tasks/verify-log.md` に記録した

### Phase 2 完了
- [ ] 仮説を最大3つ列挙した
- [ ] 各仮説に検証方法をセットで記述した

### Phase 3 完了
- [ ] 検証手段を実行した（antigravity / ログ / テスト / DB）
- [ ] 検証結果を `tasks/verify-log.md` に追記した
- [ ] 少なくとも1つの仮説が「確認」または「棄却」された

### Phase 4 完了
- [ ] 原因を証拠付きで特定した
- [ ] 原因が特定できない場合は「追加調査必要」と報告した

### Phase 5 完了
- [ ] 原因確定後に修正を実施した
- [ ] 修正後に再検証して問題解消を確認した
- [ ] 停止条件に該当していない
