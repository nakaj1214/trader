# 証拠に基づく修正ゲート — 詳細手順

推測で修正してはならない。証拠を集めてから修正すること。
このスキルは **修正に着手する前のゲート** として機能する。

---

## 5フェーズプロセス

```
Phase 0: memo/implement/prompt.md を読む（毎回・キャッシュ不可）
Phase 1: 現象の記録（事実のみ）
Phase 2: 仮説の列挙（最大3つ + 検証方法）
Phase 3: 証拠収集（レイヤー別の検証手段で実行）
Phase 4: 診断結果を docs/implement/proposal.md に書き出す（確認あり）
Phase 5: 修正（原因確定後のみ着手可能）
```

**絶対ルール: Phase 3 を完了するまで Phase 4/5 に進んではならない。**

---

## Phase 0: docs/implement/prompt.md の読み込み

スキル開始時に **毎回** `memo/implement/prompt.md` を Read ツールで読み込む。キャッシュに頼らない。

ファイルが存在しない場合はそのまま Phase 1 に進む。

---

## Phase 1: 現象の記録

ユーザーの報告から **事実だけ** を抽出する。推測や解釈を含めない。
この段階ではファイルに書き出さず、Claude のコンテキスト内で記録する。

以下の形式で把握する:

```
【現象】
- 報告された事実: [ユーザーの報告をそのまま]
- 再現条件: [いつ・どこで・どの操作で発生するか]
- 期待される動作: [本来どう動くべきか]
- 実際の動作: [何が起きているか]
```

**この段階では「なぜ」を考えない。「何が」だけ記録する。**

---

## Phase 2: 仮説の列挙

コードを読んで原因の仮説を **最大3つ** 列挙する。
各仮説に **検証方法** を必ずセットで記述する。

| # | 仮説 | 可能性 | 検証方法 | 検証手段 |
|---|------|--------|----------|----------|
| 1 | [原因候補] | High/Med/Low | [何を確認すれば裏付けられるか] | [ログ/テスト/DB/ユーザー確認] |
| 2 | [原因候補] | High/Med/Low | [何を確認すれば裏付けられるか] | [ログ/テスト/DB/ユーザー確認] |
| 3 | [原因候補] | High/Med/Low | [何を確認すれば裏付けられるか] | [ログ/テスト/DB/ユーザー確認] |

**検証方法のない仮説は無効。「たぶん○○だろう」は仮説ではない。**

---

## Phase 3: 証拠収集

### レイヤー判定

問題がどのレイヤーに属するかを判定し、対応する検証手段を選択する:

| レイヤー | 判定基準 | 検証手段 |
|---------|---------|---------|
| **フロントエンド** | UI表示・ユーザー操作・JS動作の問題 | ユーザーへ確認依頼（[テンプレート](references/browser-verification.md)） |
| **バックエンド (PHP/Laravel)** | API・ビジネスロジック・ルーティングの問題 | docker compose exec + ログ |
| **Python** | スクリプト・データ処理の問題 | pytest + logging |
| **DB** | データ不整合・クエリの問題 | SQL直接実行 |
| **複合** | 複数レイヤーにまたがる | 各レイヤーの手段を組み合わせる |

---

### フロントエンド検証

確認依頼テンプレートは **[references/browser-verification.md](references/browser-verification.md)** を参照。

**方法: ユーザーへ確認依頼**

依頼する証拠の種類: スクリーンショット、DOM 構造（outerHTML）、コンソールログ、操作手順の再現

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

## Phase 4: memo/implement/proposal.md への書き出し

### 4-1. 上書き確認（必須）

`memo/implement/proposal.md` が存在する場合は **必ずユーザーに確認する**:

```
memo/implement/proposal.md が既に存在します。
上書きしてよいですか？（内容が失われます）
```

- **YES** → 4-2 に進む
- **NO** → 処理を停止し、ユーザーの指示を待つ

ファイルが存在しない場合は確認不要でそのまま 4-2 に進む。

### 4-2. proposal.md の生成

以下のテンプレートで `memo/implement/proposal.md` を生成する:

```markdown
# 修正要件書（verify-before-fix）

> verify-before-fix スキルで生成。証拠に基づく診断結果と修正方針。
> 日時: YYYY-MM-DD

---

## 診断結果

### 確認した現象
- [事実ベースの現象記述]

### 根本原因
[証拠に基づく原因の説明]

### 証拠
| 仮説 | 判定 | 証拠 |
|------|------|------|
| [仮説1] | 確認 / 棄却 | [観測した事実] |
| [仮説2] | 確認 / 棄却 | [観測した事実] |

---

## 修正要件

### REQ-001: {修正タイトル}

- **画面**: {画面名}
- **対象ファイル**: {ファイル名}
- **Before（現状）**: {現在の動作・状態}
- **After（期待）**: {修正後の動作・状態}
- **修正方針**: {具体的な変更内容}
- **受入条件**: {これを確認したら完了}
```

**原因が特定できない場合:**
- After を `[要確認: 追加調査が必要]` とする
- 追加の検証手段を修正方針に記載する
- 推測で修正に進まない

---

## Phase 5: 修正（原因確定後のみ）

Phase 4 で proposal.md に原因が確定した場合のみ、修正に着手する。

修正後は再度 Phase 3 の検証手段で **問題が解消されたことを確認** する:
- フロントエンド → ユーザーへスクリーンショット / DOM 確認を依頼
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
    ユーザーへ [具体的な確認] を依頼して証拠を集める」
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
✅ 「コードからは X が原因の可能性がある。ログ / テスト / ユーザー確認で証拠を集める」
```

---

## チェックリスト（各フェーズ完了時に確認）

### Phase 0 完了
- [ ] `memo/implement/prompt.md` を Read ツールで読み込んだ（または存在しないことを確認した）

### Phase 1 完了
- [ ] 現象を事実ベースで把握した（推測を含めていない）

### Phase 2 完了
- [ ] 仮説を最大3つ列挙した
- [ ] 各仮説に検証方法をセットで記述した

### Phase 3 完了
- [ ] 検証手段を実行した（ユーザー確認依頼 / ログ / テスト / DB）
- [ ] 少なくとも1つの仮説が「確認」または「棄却」された

### Phase 4 完了
- [ ] `memo/implement/proposal.md` の上書き確認をユーザーに取った（既存ファイルがある場合）
- [ ] proposal.md を生成した（診断結果 + REQ 形式の修正要件）
- [ ] 原因が特定できない場合は After を `[要確認]` とした

### Phase 5 完了
- [ ] 原因確定後に修正を実施した
- [ ] 修正後に再検証して問題解消を確認した
- [ ] 停止条件に該当していない
