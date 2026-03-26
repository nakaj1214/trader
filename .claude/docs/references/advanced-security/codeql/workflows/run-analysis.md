# 解析実行ワークフロー

ルールセットの選択と結果のフォーマッティングを伴い、既存のデータベースに対して CodeQL セキュリティクエリを実行します。

## タスクシステム

ワークフロー開始時にこれらのタスクを作成:

```
TaskCreate: "データベースの選択と言語の検出" (ステップ 1)
TaskCreate: "追加クエリパックの確認とモデルパックの検出" (ステップ 2) - blockedBy: ステップ 1
TaskCreate: "クエリパック、モデルパック、脅威モデルの選択" (ステップ 3) - blockedBy: ステップ 2
TaskCreate: "解析の実行" (ステップ 4) - blockedBy: ステップ 3
TaskCreate: "結果の処理と報告" (ステップ 5) - blockedBy: ステップ 4
```

### 必須ゲート

| タスク | ゲートタイプ | 次に進む条件 |
|------|-----------|---------------------|
| ステップ 2 | **ソフトゲート** | 各不足パックについてユーザーがインストール/無視を確認 |
| ステップ 3 | **ハードゲート** | クエリパック、モデルパック、脅威モデルの選択をユーザーが承認 |

---

## ステップ

### ステップ 1: データベースの選択と言語の検出

**利用可能なデータベースを探す:**

```bash
# すべての CodeQL データベースを一覧表示
ls -dt codeql_*.db 2>/dev/null | head -10

# 最新のデータベースを取得
get_latest_db() {
  ls -dt codeql_*.db 2>/dev/null | head -1
}

DB_NAME=$(get_latest_db)
if [[ -z "$DB_NAME" ]]; then
  echo "ERROR: No CodeQL database found. Run build-database workflow first."
  exit 1
fi
echo "Using database: $DB_NAME"
```

**複数のデータベースが存在する場合**、`AskUserQuestion` を使用してユーザーに選択させます:

```
header: "データベース"
question: "複数のデータベースが見つかりました。どれを解析しますか？"
options:
  - label: "codeql_3.db（最新）"
    description: "作成日: <timestamp>"
  - label: "codeql_2.db"
    description: "作成日: <timestamp>"
  - label: "codeql_1.db"
    description: "作成日: <timestamp>"
```

**確認と言語の検出:**

```bash
# データベースが存在することを確認し、言語を取得
codeql resolve database -- "$DB_NAME"

# データベースから主要言語を取得
LANG=$(codeql resolve database --format=json -- "$DB_NAME" \
  | jq -r '.languages[0]')
LANG_COUNT=$(codeql resolve database --format=json -- "$DB_NAME" \
  | jq '.languages | length')
echo "Primary language: $LANG"
if [ "$LANG_COUNT" -gt 1 ]; then
  echo "WARNING: Multi-language database ($LANG_COUNT languages)"
  codeql resolve database --format=json -- "$DB_NAME" \
    | jq -r '.languages[]'
fi
```

**多言語データベース:** 複数の言語が検出された場合、どの言語を解析するかユーザーに確認するか、各言語について個別に解析を実行します。

---

### ステップ 2: 追加クエリパックの確認とモデルパックの検出

推奨されるサードパーティクエリパックがインストールされているか確認し、利用可能なモデルパックを検出します。各不足パックについて、インストールまたは無視するようユーザーに確認します。

#### 2a: クエリパック

**言語別の利用可能パック**（[ruleset-catalog.md](../references/ruleset-catalog.md) を参照）:

| 言語 | Trail of Bits | コミュニティパック |
|----------|---------------|----------------|
| C/C++ | `trailofbits/cpp-queries` | `GitHubSecurityLab/CodeQL-Community-Packs-CPP` |
| Go | `trailofbits/go-queries` | `GitHubSecurityLab/CodeQL-Community-Packs-Go` |
| Java | `trailofbits/java-queries` | `GitHubSecurityLab/CodeQL-Community-Packs-Java` |
| JavaScript | - | `GitHubSecurityLab/CodeQL-Community-Packs-JavaScript` |
| Python | - | `GitHubSecurityLab/CodeQL-Community-Packs-Python` |
| C# | - | `GitHubSecurityLab/CodeQL-Community-Packs-CSharp` |
| Ruby | - | `GitHubSecurityLab/CodeQL-Community-Packs-Ruby` |

**検出された言語で利用可能な各パックについて:**

```bash
# パックがインストールされているか確認
codeql resolve qlpacks | grep -i "<PACK_NAME>"
```

**インストールされていない場合**、`AskUserQuestion` を使用:

```
header: "<PACK_TYPE>"
question: "<LANG> 用の <PACK_NAME> がインストールされていません。インストールしますか？"
options:
  - label: "インストール（推奨）"
    description: "実行: codeql pack download <PACK_NAME>"
  - label: "無視"
    description: "この解析ではこのパックをスキップ"
```

**「インストール」の場合:**
```bash
codeql pack download <PACK_NAME>
```

**「無視」の場合:** パックをスキップとしてマークし、次のパックに進みます。

#### 2b: モデルパックの検出

モデルパックには、プロジェクト固有またはフレームワーク固有の API に対する CodeQL のデータフロー解析を向上させるデータ拡張（カスタムソース、シンク、フローサマリー）が含まれています。新しい拡張を作成するには、まず [create-data-extensions](create-data-extensions.md) ワークフローを実行してください。

**3つの場所を検索:**

**1. リポジトリ内モデルパック** — `dataExtensions` を持つ `qlpack.yml` または `codeql-pack.yml`:

```bash
# コードベース内の CodeQL パック定義を見つける
fd '(qlpack|codeql-pack)\.yml$' . --exclude codeql_*.db | while read -r f; do
  if grep -q 'dataExtensions' "$f"; then
    echo "MODEL PACK: $(dirname "$f") - $(grep '^name:' "$f")"
  fi
done
```

**2. リポジトリ内スタンドアロンデータ拡張** — `extensions:` キーを持つ `.yml` ファイル（CodeQL が自動検出）:

```bash
# コードベース内のデータ拡張 YAML ファイルを見つける
rg -l '^extensions:' --glob '*.yml' --glob '!codeql_*.db/**' | head -20
```

**3. インストール済みモデルパック** — CodeQL が解決するモデルを含むライブラリパック:

```bash
# すべての解決済みパックをリストし、モデル/ライブラリパックをフィルタ
# モデルパックは通常、名前に "model" があるか、ライブラリパック
codeql resolve qlpacks 2>/dev/null | grep -iE 'model|extension'
```

**検出されたすべてのモデルパックをステップ 3 での提示用に記録します。** モデルパックが見つからない場合は記録して進みます — モデルパックはオプションです。

---

### ステップ 3: 重要なゲート - クエリパックとモデルパックの選択

> **必須チェックポイント - スキップ不可**
>
> すべての利用可能なパックをチェックリストとして提示します。クエリパックが先、次にモデルパック。

#### 3a: クエリパックの選択

`AskUserQuestion` ツールを `multiSelect: true` で使用:

```
header: "クエリパック"
question: "実行するクエリパックを選択してください:"
multiSelect: false
options:
  - label: "すべて使用（推奨）"
    description: "最大カバレッジのためにインストール済みの全クエリパックを実行"
  - label: "security-extended"
    description: "codeql/<lang>-queries - コアセキュリティクエリ、低誤検知"
  - label: "security-and-quality"
    description: "コード品質チェックを含む - より多い検出、より多いノイズ"
  - label: "個別に選択"
    description: "全リストから特定のパックを選択"
```

**「すべて使用」の場合:** インストール済みのすべてのクエリパックを含める: `security-extended` + Trail of Bits + コミュニティパック（インストール済みのもの）。

**「個別に選択」の場合:** インストール済みのすべてのパックをリストした `multiSelect: true` の質問でフォローアップ:

```
header: "クエリパック"
question: "実行するクエリパックを選択してください:"
multiSelect: true
options:
  - label: "security-extended"
    description: "codeql/<lang>-queries - コアセキュリティクエリ、低誤検知"
  - label: "security-and-quality"
    description: "コード品質チェックを含む - より多い検出、より多いノイズ"
  - label: "security-experimental"
    description: "最先端クエリ - 誤検知が多い場合あり"
  - label: "Trail of Bits"
    description: "trailofbits/<lang>-queries - メモリ安全性、ドメイン専門知識"
  - label: "コミュニティパック"
    description: "GitHubSecurityLab/CodeQL-Community-Packs-<Lang> - 追加セキュリティクエリ"
```

**ステップ 2a でインストール済みの組み込みおよびサードパーティパックのみを表示**

**停止: ユーザーの選択を待機**

#### 3b: モデルパックの選択（検出された場合）

**ステップ 2b でモデルパックが検出されなかった場合、このサブステップをスキップ。**

ステップ 2b で検出されたモデルパックを提示します。ソース別に分類:

`AskUserQuestion` ツールを使用:

```
header: "モデルパック"
question: "モデルパックはカスタムデータフローモデル（ソース、シンク、サマリー）を追加します。含めるものを選択してください:"
multiSelect: false
options:
  - label: "すべて使用（推奨）"
    description: "検出されたすべてのモデルパックとデータ拡張を含める"
  - label: "個別に選択"
    description: "リストから特定のモデルパックを選択"
  - label: "スキップ"
    description: "モデルパックなしで実行"
```

**「すべて使用」の場合:** ステップ 2b で検出されたすべてのモデルパックとデータ拡張を含めます。

**「個別に選択」の場合:** `multiSelect: true` の質問でフォローアップ:

```
header: "モデルパック"
question: "含めるモデルパックを選択してください:"
multiSelect: true
options:
  # 2b で見つかった各リポジトリ内モデルパック:
  - label: "<pack-name>"
    description: "<path> のリポジトリ内モデルパック - カスタムデータフローモデル"
  # 2b で見つかった各スタンドアロンデータ拡張:
  - label: "リポジトリ内拡張"
    description: "コードベースで <N> データ拡張ファイルが見つかりました（自動検出）"
  # 2b で見つかった各インストール済みモデルパック:
  - label: "<pack-name>"
    description: "インストール済みモデルパック - <利用可能な場合の説明>"
```

**注意:**
- リポジトリ内スタンドアロンデータ拡張（`extensions:` キーを持つ `.yml` ファイル）は解析中に CodeQL が自動検出します — ここで選択すると、ソースディレクトリが `--additional-packs` 経由で渡されます
- リポジトリ内モデルパック（`qlpack.yml` を持つもの）は親ディレクトリを `--additional-packs` 経由で渡す必要があります
- インストール済みモデルパックは `--model-packs` 経由で渡されます

**停止: ユーザーの選択を待機**

---

### ステップ 3c: 脅威モデルの選択

脅威モデルは、CodeQL がテイントとして扱う入力ソースを制御します。デフォルト（`remote`）は HTTP/ネットワーク入力のみをカバーします。脅威モデルを拡張すると、より多くの脆弱性が見つかりますが、誤検知が増加する可能性があります。各モデルの詳細は [threat-models.md](../references/threat-models.md) を参照してください。

`AskUserQuestion` を使用:

```
header: "脅威モデル"
question: "CodeQL がテイントとして扱うべき入力ソースはどれですか？"
multiSelect: false
options:
  - label: "リモートのみ（推奨）"
    description: "デフォルト — HTTP リクエスト、ネットワーク入力。Web サービスと API に最適。"
  - label: "リモート + ローカル"
    description: "CLI 引数、ローカルファイルを追加。CLI ツールやデスクトップアプリ向け。"
  - label: "すべてのソース"
    description: "リモート、ローカル、環境変数、データベース、ファイル。最大カバレッジ、より多いノイズ。"
  - label: "カスタム"
    description: "個別に特定の脅威モデルを選択"
```

**「カスタム」の場合:** `multiSelect: true` でフォローアップ:

```
header: "脅威モデル"
question: "有効にする脅威モデルを選択してください:"
multiSelect: true
options:
  - label: "remote"
    description: "HTTP リクエスト、ネットワーク入力（常に含まれる）"
  - label: "local"
    description: "CLI 引数、ローカルファイル — CLI ツール、バッチプロセッサ向け"
  - label: "environment"
    description: "環境変数 — 12-Factor/コンテナアプリ向け"
  - label: "database"
    description: "データベース結果 — セカンドオーダーインジェクション監査向け"
```

**脅威モデルフラグの構築:**

```bash
# デフォルト以外のモデルが選択された場合のみ --threat-models を追加
# デフォルト（remote のみ）はフラグ不要
THREAT_MODEL_FLAG=""  # または "--threat-models=remote,local" 等
```

---

### ステップ 4: 解析の実行

ステップ 3 でユーザーが選択したパック**のみ**で解析を実行します。

```bash
# 結果ディレクトリはデータベース名に対応
RESULTS_DIR="${DB_NAME%.db}-results"
mkdir -p "$RESULTS_DIR"

# ステップ 3a のユーザー選択からパックリストを構築
PACKS="<USER_SELECTED_QUERY_PACKS>"

# ステップ 3b のユーザー選択からモデルパックフラグを構築
# --model-packs はインストール済みモデルパック用
# --additional-packs はリポジトリ内モデルパックとデータ拡張用
MODEL_PACK_FLAGS=""
ADDITIONAL_PACK_FLAGS=""

# ステップ 3c の脅威モデルフラグ（デフォルト/remote のみの場合は空文字列）
# THREAT_MODEL_FLAG=""

codeql database analyze $DB_NAME \
  --format=sarif-latest \
  --output="$RESULTS_DIR/results.sarif" \
  --threads=0 \
  $THREAT_MODEL_FLAG \
  $MODEL_PACK_FLAGS \
  $ADDITIONAL_PACK_FLAGS \
  -- $PACKS
```

**モデルパック用のフラグリファレンス:**

| ソース | フラグ | 例 |
|--------|------|---------|
| インストール済みモデルパック | `--model-packs` | `--model-packs=myorg/java-models` |
| リポジトリ内モデルパック（`qlpack.yml` 付き） | `--additional-packs` | `--additional-packs=./lib/codeql-models` |
| リポジトリ内スタンドアロン拡張（`.yml`） | `--additional-packs` | `--additional-packs=.` |

**例（C++ クエリパックとモデルパック付き）:**

```bash
codeql database analyze codeql_1.db \
  --format=sarif-latest \
  --output=codeql_1-results/results.sarif \
  --threads=0 \
  --additional-packs=./codeql-models \
  -- codeql/cpp-queries:codeql-suites/cpp-security-extended.qls \
     trailofbits/cpp-queries \
     GitHubSecurityLab/CodeQL-Community-Packs-CPP
```

**例（Python インストール済みモデルパック付き）:**

```bash
codeql database analyze codeql_1.db \
  --format=sarif-latest \
  --output=codeql_1-results/results.sarif \
  --threads=0 \
  --model-packs=myorg/python-models \
  -- codeql/python-queries:codeql-suites/python-security-extended.qls
```

### パフォーマンスフラグ

コードベースが大規模な場合は [../references/performance-tuning.md](../references/performance-tuning.md) を読み、関連する最適化を適用してください。

### ステップ 5: 結果の処理と報告

**検出数のカウント:**

```bash
jq '.runs[].results | length' "$RESULTS_DIR/results.sarif"
```

**SARIF レベル別サマリー:**

```bash
jq -r '.runs[].results[] | .level' "$RESULTS_DIR/results.sarif" \
  | sort | uniq -c | sort -rn
```

**セキュリティ深刻度別サマリー**（トリアージにより有用）:

```bash
jq -r '
  .runs[].results[] |
  (.properties["security-severity"] // "none") + " " +
  (.message.text // "no message" | .[0:80])
' "$RESULTS_DIR/results.sarif" | sort -rn | head -20
```

**ルール別サマリー:**

```bash
jq -r '.runs[].results[] | .ruleId' "$RESULTS_DIR/results.sarif" \
  | sort | uniq -c | sort -rn
```

---

## 最終出力

ユーザーへの報告:

```
## CodeQL 解析完了

**データベース:** $DB_NAME
**言語:** <LANG>
**クエリパック:** <使用されたクエリパックのリスト>
**モデルパック:** <使用されたモデルパックのリスト、または "なし">
**脅威モデル:** <脅威モデルのリスト、または "デフォルト（remote）">

### 結果サマリー:
- 合計検出: <N>
- Error: <N>
- Warning: <N>
- Note: <N>

### 出力ファイル:
- SARIF: $RESULTS_DIR/results.sarif
```
