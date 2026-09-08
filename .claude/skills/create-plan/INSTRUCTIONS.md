# Create Plan — 詳細手順

## Fixed Files

| File | Role |
|------|------|
| `docs/implement/proposal.md` | Input: ユーザーが書いた要件書（読み取り専用） |
| `docs/implement/plan.md` | Output: 実装計画書（Claude が作成・更新） |
| `docs/tests/{feature}.test.js` または `docs/tests/{feature}.test.html` | Output: 挙動確認テストファイル |

---

## Step 0-pre: 調査型タスク判定

proposal.md を読み、課題が**調査型**（原因不明のバグ・動作不良）かを判定する:

- 「〜が動かない」「〜が表示されない」「アラートが出る」「原因不明」などのキーワード
- 修正方針が「まず原因を調べる」になっている

**調査型と判定した場合**: ユーザーに以下を提案して確認を取る:
> この課題は原因不明のバグです。テスト作成より verify-before-fix で証拠を集めて直接修正する方が速い可能性があります。
> 1. verify-before-fix で進める（推奨）— plan 作成とテスト作成をスキップ
> 2. 通常の create-plan で進める

ユーザーが「1」を選んだ場合: plan.md に「verify-before-fix による調査 → 最小修正」の簡易テンプレートを生成して完了する。

**実装型と判定した場合**: 通常通り Step 0 に進む。

---

## Step 0: Proposal Quality Gate（前提チェック）

**plan 作成の前に、必ず `proposal-quality-gate` スキルの INSTRUCTIONS.md を読み、品質チェックを実行すること。**

品質チェックの結果:
- **PASS** → Step 1 に進む
- **FAIL** → proposal.md のリライトを実施し、ユーザー承認後に Step 1 に進む

詳細: [proposal-quality-gate INSTRUCTIONS.md](../proposal-quality-gate/INSTRUCTIONS.md)

---

## Step 1: Read Proposal

Read `docs/implement/proposal.md`.

If the file does not exist, stop and tell the user:
> `docs/implement/proposal.md` が見つかりません。先にファイルを作成してください。

---

## Step 2: Investigate Codebase (Claude)

Investigate the codebase based on the scope described in proposal.md:

- Related existing code (classes, functions, modules)
- Files likely to be affected
- Libraries and patterns already in use
- Existing tests relevant to the scope

Use this investigation to inform the plan in the next step.

### 調査の落とし穴（必ず守ること）

#### ファイルの存在 ≠ 実行済み・動作確認済み

「ファイルがある」は出発点にすぎない。計画の中で「〜が完了している」「〜が適用済み」と書く場合は、**必ず実際の状態をコマンドで確認する**。

| 確認したいこと | 確認方法（例） |
|-------------|-------------|
| Migration が適用済みか | `php artisan migrate:status` または `SELECT migration FROM migrations` |
| テーブルが存在するか | `SHOW TABLES` in the target DB |
| データが存在するか | `SELECT COUNT(*) FROM table` |
| 接続設定が有効か | `.env` を Read する（ファイルが存在するだけでは不十分） |

確認していない状態は **`[未確認]`** タグを付け、推測を事実として書かない。

#### 同種ファイルが複数ある場合は複数読む

代表として1件だけ読むと、残りのファイルでパターンが違う可能性を見落とす。

- 同種ファイルが5件以下: **全件読む**
- 同種ファイルが6件以上: **少なくとも5件サンプリングして差異がないか確認する**

特に「グループ内の差異」に注意する（例: 一部のMigrationだけデータコピーがある、一部のModelだけ接続名が違うなど）。

#### スキーマ変更を含む場合は旧新カラム名を対照する

テーブル名・接続名の変更だけでなく、**カラム名の差異**が既存コードを壊す最大の原因になる。  
Model の `$fillable`、Repository の `select/where/join`、FormRequest を含めて旧新カラム名を対照し、影響範囲に含める。

---

## Step 3: Create plan.md (Claude)

### 計画書を書く前のセルフチェック

plan.md に書く前に、以下を自問する:

1. **「〜が完了している」「〜が存在する」と書く場合**: Step 2 で実際に確認したか？ → していなければ `[未確認]` タグを付ける
2. **「〜を変更する」と書く場合**: 変更前後の具体的な値（カラム名・設定値・関数名）は調べたか？ → 調べていなければ実装で必ず詰まる
3. **「〜はリスクが低い」と書く場合**: 過去に同種の変更で問題が起きていないか review.md や lessons.md を確認したか？
4. **テーブル数・件数・行数を書く場合**: 実際に COUNT したか？ → していなければ `[未確認]` タグを付ける

**`[未確認]` タグの使い方:**
```
# ❌ 確認せずに断定する
- ams DB に roles、departments が作成済み（Migration済み）

# ✅ 未確認を明示する
- ams DB に roles、departments が Migration済み [未確認: migrate:status で要確認]
```

`[未確認]` タグが多い場合は、plan.md を書く前に調査に戻る。

---

Based on proposal.md, create `docs/implement/plan.md` using the format below.

```markdown
## 実装計画: {Title}

### 目的
{1-2 sentences from proposal}

### スコープ
- 含むもの: {list}
- 含まないもの: {list}

### 影響範囲（変更/追加予定ファイル）
- {file path}: {reason}

### 実装ステップ

#### Step 1: {Title}
- [ ] {Specific task}
- [ ] {Specific task}
**検証**: {Completion criteria}

#### Step 2: {Title}
...

### 例外・エラーハンドリング方針
{policy}

### テスト/検証方針
- 自動テスト: {command or N/A}
- 手動確認観点: {specific checklist}

### リスクと対策
1. リスク: {description} → 対策: {mitigation}
2. リスク: {description} → 対策: {mitigation}
3. リスク: {description} → 対策: {mitigation}

### 完了条件
- [ ] {Acceptance criterion}
```

---

## Step 3.5: plan.md 完了報告——ここで必ず停止する

plan.md を作成したら、**必ずここで停止してユーザーに報告する**。
Step 4（テストファイル作成）はユーザーの明示的な指示があるまで開始しない。

```
## plan.md 作成完了

- docs/implement/plan.md を作成しました。

内容を確認後、続けてテストファイルの作成を行う場合はその旨お伝えください。
```

---

## Step 4: テストファイル作成と挙動確認

plan.md の実装ステップと proposal.md の受入条件をもとに、テストファイルを作成して挙動を確認する。

### 4-1. テスト環境の確認

```bash
cat src/package.json 2>/dev/null | grep -E '"jest|"mocha|"vitest|"jasmine'
cat package.json 2>/dev/null | grep -E '"jest|"mocha|"vitest|"jasmine'
```

### 4-2. テストファイルの作成

`docs/tests/` ディレクトリ（なければ作成）にテストファイルを配置する。

#### A. 既存テストフレームワーク（Jest / Mocha 等）がある場合

フレームワークの規約に従い `docs/tests/{feature}.test.js` を作成する。

#### B. ブラウザ向けコード（jQuery / DOM 操作）でフレームワークがない場合

`docs/tests/{feature}.test.html` を作成する:

```html
<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"><title>{feature} テスト</title></head>
<body>
<!-- テスト用の最小 DOM -->
...

<script src="/path/to/jquery.min.js"></script>
<script src="/path/to/target-module.js"></script>
<script>
var results = [];

function assert(label, condition) {
    results.push({ label: label, pass: condition });
    console.log((condition ? '✅ PASS' : '❌ FAIL') + ': ' + label);
}

// --- テストケース（proposal.md の受入条件ごとに記述）---

var passed = results.filter(function(r) { return r.pass; }).length;
console.log('結果: ' + passed + '/' + results.length + ' PASS');
</script>
</body>
</html>
```

#### C. DOM 不要なロジックの場合（Node.js 実行可能）

`docs/tests/{feature}.test.js` を作成し、`node docs/tests/{feature}.test.js` で実行する:

```js
function assert(label, condition) {
    console.log((condition ? '✅ PASS' : '❌ FAIL') + ': ' + label);
    if (!condition) process.exitCode = 1;
}

// テストケース...
```

### 4-3. テストの実行・確認

- **C の場合（Node.js 実行）**: `node docs/tests/{feature}.test.js` を実行し、全行の出力を確認する
- **A の場合（既存フレームワーク）**: フレームワークのコマンドで実行する
- **B の場合（HTML）**: ファイルを読み返し、テストロジックが proposal.md の受入条件を網羅していることを目視で確認する

### 4-4. 修正

- **C/A で FAIL が出た場合**: テストが通るよう plan.md の該当ステップを修正し、テストも修正する。最大 3 回まで修正を試みる

---

## Step 5: Done

ユーザーに以下を報告して**停止する**（実装は自動開始しない）:

```
## 計画作成完了

### 作成ファイル
- docs/implement/plan.md
- docs/tests/{feature}.test.*（挙動確認）

### テスト結果
{PASS / FAIL サマリ または HTML 確認済み}

### 次のステップ
内容を確認後、`/implement-plans` で実装を開始してください。
```

**`implement-plans` は自動発火しない。ユーザーの明示的な指示を待つこと。**

---

## Notes

- テストファイルは `docs/tests/` ディレクトリに配置する（存在しない場合は作成する）
- テストは proposal.md の受入条件を1つ以上カバーすること
- ブラウザ向けコードで Node.js 実行が難しい場合は HTML テストページで代替する（目視確認）
- Codex レビューループを使いたい場合は `/codex-loop-create-plan` スキルを使うこと
