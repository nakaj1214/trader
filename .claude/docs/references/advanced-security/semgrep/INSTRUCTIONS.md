# Semgrep セキュリティスキャン

自動言語検出、Task サブエージェントによる並列実行、並列トリアージで完全な Semgrep スキャンを実行する。利用可能な場合は自動的に Semgrep Pro を使用してクロスファイルテイント解析を行う。

## 前提条件

**必須:** Semgrep CLI

```bash
semgrep --version
```

未インストールの場合は [Semgrep インストールドキュメント](https://semgrep.dev/docs/getting-started/) を参照。

**オプション:** Semgrep Pro（クロスファイル解析と Pro 言語用）

```bash
# Semgrep Pro エンジンがインストールされているか確認
semgrep --pro --validate --config p/default 2>/dev/null && echo "Pro available" || echo "OSS only"

# ログイン済みの場合、Pro Engine をインストール/更新
semgrep install-semgrep-pro
```

Pro で有効になる機能: クロスファイルテイント追跡、手続き間解析、追加言語（Apex, C#, Elixir）。

## 使用する場面

- コードベースのセキュリティ監査
- コードレビュー前の脆弱性検出
- 既知のバグパターンのスキャン
- 静的解析の初回パス

## 使用しない場面

- バイナリ解析 → バイナリ解析ツールを使用
- Semgrep CI が既に設定済み → 既存パイプラインを使用
- クロスファイル解析が必要だが Pro ライセンスがない → 代替として CodeQL を検討
- カスタム Semgrep ルールの作成 → `semgrep-rule-creator` スキルを使用
- 既存ルールの他言語への移植 → `semgrep-rule-variant-creator` スキルを使用

---

## オーケストレーションアーキテクチャ

このスキルは最大効率のため **並列 Task サブエージェント** を使用する:

```
┌─────────────────────────────────────────────────────────────────┐
│ メインエージェント                                                │
│ 1. 言語検出 + Pro 利用可否の確認                                  │
│ 2. 検出結果に基づくルールセット選択（参照: rulesets.md）            │
│ 3. 計画 + ルールセットを提示し承認を取得 [⛔ ハードゲート]         │
│ 4. 承認済みルールセットで並列スキャン Task を起動                   │
│ 5. 並列トリアージ Task を起動                                     │
│ 6. 結果を収集して報告                                             │
└─────────────────────────────────────────────────────────────────┘
          │ Step 4                           │ Step 5
          ▼                                  ▼
┌─────────────────┐              ┌─────────────────┐
│ スキャン Task    │              │ トリアージ Task  │
│ （並列実行）     │              │ （並列実行）     │
├─────────────────┤              ├─────────────────┤
│ Python scanner  │              │ Python triager  │
│ JS/TS scanner   │              │ JS/TS triager   │
│ Go scanner      │              │ Go triager      │
│ Docker scanner  │              │ Docker triager  │
└─────────────────┘              └─────────────────┘
```

---

## Task システムによるワークフロー強制

このスキルは **Task システム** を使用してワークフロー準拠を強制する。起動時に以下のタスクを作成する:

```
TaskCreate: "言語と Pro 利用可否の検出" (Step 1)
TaskCreate: "検出結果に基づくルールセット選択" (Step 2) - blockedBy: Step 1
TaskCreate: "ルールセット付き計画を提示し承認を取得" (Step 3) - blockedBy: Step 2
TaskCreate: "承認済みルールセットでスキャンを実行" (Step 4) - blockedBy: Step 3
TaskCreate: "検出結果のトリアージ" (Step 5) - blockedBy: Step 4
TaskCreate: "結果の報告" (Step 6) - blockedBy: Step 5
```

### 必須ゲート

| タスク | ゲートタイプ | 次に進めない条件 |
|--------|------------|----------------|
| Step 3: 承認取得 | **ハードゲート** | ユーザーがルールセット＋計画を明示的に承認するまで |
| Step 5: トリアージ | **ソフトゲート** | すべてのスキャン JSON ファイルが存在するまで |

**Step 3 はハードゲート**: ユーザーが "yes"、"proceed"、"approved" 等で承認した後にのみ `completed` にマークする。

### Task フローの例

```
1. 依存関係付きで全6タスクを作成
2. TaskUpdate Step 1 → in_progress、検出を実行
3. TaskUpdate Step 1 → completed
4. TaskUpdate Step 2 → in_progress、ルールセットを選択
5. TaskUpdate Step 2 → completed
6. TaskUpdate Step 3 → in_progress、ルールセット付き計画を提示
7. 停止: ユーザーの応答を待つ（ルールセットの変更の可能性あり）
8. ユーザー承認 → TaskUpdate Step 3 → completed
9. TaskUpdate Step 4 → in_progress（ブロック解除）
... ワークフロー続行
```

---

## ワークフロー

### Step 1: 言語と Pro 利用可否の検出（メインエージェント）

```bash
# Semgrep Pro が利用可能か確認（非破壊的チェック）
SEMGREP_PRO=false
if semgrep --pro --validate --config p/default 2>/dev/null; then
  SEMGREP_PRO=true
  echo "Semgrep Pro: 利用可能（クロスファイル解析有効）"
else
  echo "Semgrep Pro: 利用不可（OSS モード、単一ファイル解析）"
fi

# ファイル拡張子で言語を検出
fd -t f -e py -e js -e ts -e jsx -e tsx -e go -e rb -e java -e php -e c -e cpp -e rs | \
  sed 's/.*\.//' | sort | uniq -c | sort -rn

# フレームワーク/テクノロジーの確認
ls -la package.json pyproject.toml Gemfile go.mod Cargo.toml pom.xml 2>/dev/null
fd -t f "Dockerfile" "docker-compose" ".tf" "*.yaml" "*.yml" | head -20
```

検出結果のカテゴリマッピング:

| 検出内容 | カテゴリ |
|---------|---------|
| `.py`, `pyproject.toml` | Python |
| `.js`, `.ts`, `package.json` | JavaScript/TypeScript |
| `.go`, `go.mod` | Go |
| `.rb`, `Gemfile` | Ruby |
| `.java`, `pom.xml` | Java |
| `.php` | PHP |
| `.c`, `.cpp` | C/C++ |
| `.rs`, `Cargo.toml` | Rust |
| `Dockerfile` | Docker |
| `.tf` | Terraform |
| k8s マニフェスト | Kubernetes |

### Step 2: 検出結果に基づくルールセット選択

Step 1 で検出した言語とフレームワークを使用し、[rulesets.md]({baseDir}/references/rulesets.md) の **ルールセット選択アルゴリズム** に従ってルールセットを選択する。

アルゴリズムの内容:
1. セキュリティベースライン（常に含む）
2. 言語固有のルールセット
3. フレームワークルールセット（検出された場合）
4. インフラストラクチャルールセット
5. **必須** サードパーティルールセット（Trail of Bits, 0xdea, Decurity — オプションではない）
6. レジストリの検証

**出力:** Step 3 でユーザーレビュー用に渡す構造化 JSON:

```json
{
  "baseline": ["p/security-audit", "p/secrets"],
  "python": ["p/python", "p/django"],
  "javascript": ["p/javascript", "p/react", "p/nodejs"],
  "docker": ["p/dockerfile"],
  "third_party": ["https://github.com/trailofbits/semgrep-rules"]
}
```

### Step 3: 重要ゲート - 計画を提示し承認を取得

> **⛔ 必須チェックポイント — スキップ禁止**
>
> このステップではユーザーの明示的な承認が必要。
> ユーザーは承認前にルールセットを変更する可能性がある。

**明示的なルールセットリスト** 付きで計画をユーザーに提示する:

```
## Semgrep スキャン計画

**対象:** /path/to/codebase
**出力ディレクトリ:** ./semgrep-results-001/
**エンジン:** Semgrep Pro（クロスファイル解析） | Semgrep OSS（単一ファイル）

### 検出された言語/テクノロジー:
- Python (1,234 ファイル) - Django フレームワーク検出
- JavaScript (567 ファイル) - React 検出
- Dockerfile (3 ファイル)

### 実行するルールセット:

**セキュリティベースライン（常に含む）:**
- [x] `p/security-audit` - 包括的なセキュリティルール
- [x] `p/secrets` - ハードコードされた認証情報、API キー

**Python (1,234 ファイル):**
- [x] `p/python` - Python セキュリティパターン
- [x] `p/django` - Django 固有の脆弱性

**JavaScript (567 ファイル):**
- [x] `p/javascript` - JavaScript セキュリティパターン
- [x] `p/react` - React 固有の問題
- [x] `p/nodejs` - Node.js サーバーサイドパターン

**Docker (3 ファイル):**
- [x] `p/dockerfile` - Dockerfile ベストプラクティス

**サードパーティ（検出言語に対して自動追加）:**
- [x] Trail of Bits ルール - https://github.com/trailofbits/semgrep-rules

**利用可能だが未選択:**
- [ ] `p/owasp-top-ten` - OWASP Top 10（security-audit と重複）

### 実行戦略:
- 3つの並列スキャン Task を起動（Python, JavaScript, Docker）
- 合計ルールセット: 9
- [Pro の場合] クロスファイルテイント追跡有効

**ルールセットを変更しますか？** 追加・削除するものを教えてください。
**スキャンを開始しますか？** "proceed" または "yes" と回答してください。
```

**⛔ 停止: ユーザーの明示的な承認を待つ**

計画提示後:

1. **ユーザーがルールセットの変更を希望する場合:**
   - 要求されたルールセットを適切なカテゴリに追加
   - 要求されたルールセットを削除
   - 更新した計画を再提示
   - 承認待ちに戻る

2. **ユーザーが応答しない場合は AskUserQuestion を使用:**
   ```
   "9つのルールセット（Trail of Bits を含む）でスキャン計画を準備しました。スキャンを実行しますか？"
   選択肢: ["はい、スキャンを実行", "先にルールセットを変更"]
   ```

3. **有効な承認応答:**
   - "yes", "proceed", "approved", "go ahead", "looks good", "run it"

4. **最終ルールセットが確認された後にのみ** タスクを完了にマーク

5. **承認として扱ってはならないもの:**
   - ユーザーの元のリクエスト（「このコードベースをスキャンして」）
   - 沈黙 / 応答なし
   - 計画に関する質問

### スキャン前チェックリスト

Step 3 を完了にマークする前に確認:
- [ ] 対象ディレクトリをユーザーに表示
- [ ] エンジンタイプ（Pro/OSS）を表示
- [ ] 検出された言語を一覧表示
- [ ] **すべてのルールセットをチェックボックス付きで明示的に一覧表示**
- [ ] ユーザーにルールセットの変更機会を提供
- [ ] ユーザーが明示的に承認（確認の引用を記載）
- [ ] **Step 4 用に最終ルールセットリストを記録**

### Step 4: 並列スキャン Task の起動

衝突を避けるため実行番号付きの出力ディレクトリを作成し、**Step 3 で承認されたルールセット** で Task を起動:

```bash
# 次の利用可能な実行番号を検索
LAST=$(ls -d semgrep-results-[0-9][0-9][0-9] 2>/dev/null | sort | tail -1 | grep -o '[0-9]*$' || true)
NEXT_NUM=$(printf "%03d" $(( ${LAST:-0} + 1 )))
OUTPUT_DIR="semgrep-results-${NEXT_NUM}"
mkdir -p "$OUTPUT_DIR"
echo "出力ディレクトリ: $OUTPUT_DIR"
```

**1つのメッセージで N 個の Task を同時起動**（言語カテゴリごとに1つ）、`subagent_type: Bash` を使用。

スキャナー Task のプロンプトテンプレートは [scanner-task-prompt.md]({baseDir}/references/scanner-task-prompt.md) を参照。

**例 - 3言語スキャン（承認済みルールセット使用）:**

以下の3つの Task を1つのメッセージで同時起動:

1. **Task: Python スキャナー**
   - 承認済みルールセット: p/python, p/django, p/security-audit, p/secrets, https://github.com/trailofbits/semgrep-rules
   - 出力: semgrep-results-001/python-*.json

2. **Task: JavaScript スキャナー**
   - 承認済みルールセット: p/javascript, p/react, p/nodejs, p/security-audit, p/secrets, https://github.com/trailofbits/semgrep-rules
   - 出力: semgrep-results-001/js-*.json

3. **Task: Docker スキャナー**
   - 承認済みルールセット: p/dockerfile
   - 出力: semgrep-results-001/docker-*.json

### Step 5: 並列トリアージ Task の起動

スキャン Task 完了後、`subagent_type: general-purpose` でトリアージ Task を起動（トリアージにはコードコンテキストの読み取りが必要で、コマンド実行だけでは不十分）。

トリアージ Task のプロンプトテンプレートは [triage-task-prompt.md]({baseDir}/references/triage-task-prompt.md) を参照。

### Step 6: 結果の収集（メインエージェント）

すべての Task 完了後、マージされた SARIF とレポートを生成:

**トリアージ済み真陽性のみのマージ SARIF を生成:**

```bash
uv run {baseDir}/scripts/merge_triaged_sarif.py [OUTPUT_DIR]
```

このスクリプトの処理:
1. マージに [SARIF Multitool](https://www.npmjs.com/package/@microsoft/sarif-multitool) の使用を試みる（`npx` が利用可能な場合）
2. Multitool が利用不可の場合は純粋な Python マージにフォールバック
3. すべての `*-triage.json` ファイルを読み取り、真陽性の検出結果を抽出
4. マージされた SARIF をフィルタリングし、トリアージ済み真陽性のみを含める
5. `[OUTPUT_DIR]/findings-triaged.sarif` に出力

**オプション: より良いマージ品質のため SARIF Multitool をインストール:**

```bash
npm install -g @microsoft/sarif-multitool
```

**ユーザーへの報告:**

```
## Semgrep スキャン完了

**スキャン対象:** 1,804 ファイル
**使用ルールセット:** 9（Trail of Bits を含む）
**総生検出数:** 156
**トリアージ後:** 32 真陽性

### 深刻度別:
- ERROR: 5
- WARNING: 18
- INFO: 9

### カテゴリ別:
- SQL インジェクション: 3
- XSS: 7
- ハードコードされたシークレット: 2
- セキュアでない設定: 12
- コード品質: 8

結果の出力先:
- semgrep-results-001/findings-triaged.sarif (SARIF, 真陽性のみ)
- semgrep-results-001/*-triage.json (言語別トリアージ詳細)
- semgrep-results-001/*.json (生スキャン結果)
- semgrep-results-001/*.sarif (ルールセット別生 SARIF)
```

---

## よくある間違い

| 間違い | 正しいアプローチ |
|--------|----------------|
| `--metrics=off` なしで実行 | テレメトリを防ぐため常に `--metrics=off` を使用 |
| ルールセットを順次実行 | `&` と `wait` で並列実行 |
| ルールセットを言語に限定しない | 言語固有ルールには `--include="*.py"` を使用 |
| トリアージなしで生検出を報告 | 常にトリアージして偽陽性を除去 |
| 多言語でシングルスレッド | 言語ごとに並列 Task を起動 |
| Task を順次実行 | 並列化のため1つのメッセージですべての Task を起動 |
| Pro が利用可能なのに OSS を使用 | ログイン状態を確認し、より深い解析のため `--pro` を使用 |
| Pro が利用不可と仮定 | スキャン前に常にログイン検出で確認 |

## 制限事項

1. **OSS モード:** ファイル間のデータフロー追跡不可（`semgrep login` でログインし `semgrep install-semgrep-pro` を実行して有効化）
2. **Pro モード:** クロスファイル解析は `-j 1`（シングルジョブ）で遅いが、並列ルールセットで補う
3. トリアージにはコードコンテキストの読み取りが必要 — Task で並列化
4. 一部の偽陽性パターンは人間の判断が必要

## 拒否すべき合理化

| ショートカット | なぜ間違いか |
|--------------|------------|
| 「ユーザーがスキャンを依頼したので承認済み」 | 元のリクエスト ≠ 計画の承認。計画を提示し AskUserQuestion を使い明示的な "yes" を待つ |
| 「Step 3 がブロックしているので完了にマーク」 | タスク状態の偽装は強制を無効化する。実際の承認後にのみ完了にマーク |
| 「ユーザーの意図はわかっている」 | 仮定は間違ったディレクトリ/ルールセットのスキャンを引き起こす。検証のためすべてのパラメータ付き計画を提示 |
| 「デフォルトルールセットを使用」 | ユーザーはスキャン前に正確なルールセットを確認・承認する必要がある |
| 「確認なしで追加ルールセットを追加」 | 承認リストを同意なく変更すると信頼を損なう |
| 「ルールセットリストの表示をスキップ」 | 何が実行されるか見えなければユーザーは判断できない |
| 「サードパーティルールセットはオプション」 | Trail of Bits, 0xdea, Decurity ルールは公式レジストリにない脆弱性を検出する — 言語が一致する場合は必須 |
| 「トリアージをスキップしてすべて報告」 | ノイズでユーザーを圧倒する。真の問題が埋もれる |
| 「1つずつルールセットを実行」 | 時間の無駄。並列実行の方が速い |
| 「--config auto を使用」 | メトリクスが送信される。ルールセットの制御が低下 |
| 「トリアージは後で」 | コンテキストなしの検出は評価が困難 |
| 「Task を1つずつ」 | 並列性が失われる。すべての Task を一緒に起動 |
| 「Pro は遅いので --pro をスキップ」 | クロスファイル解析は真陽性を 250% 多く検出する。時間をかける価値がある |
| 「Pro の確認は不要」 | Pro を見逃す = 重要なクロスファイル脆弱性を見逃す |
| 「OSS で十分」 | OSS はファイル間テイントフローを検出できない。利用可能な場合は常に Pro を優先 |
