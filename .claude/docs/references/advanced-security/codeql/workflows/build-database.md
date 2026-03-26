# データベース構築ワークフロー

ビルド方法を順番に試して、高品質な CodeQL データベースを作成します。

## タスクシステム

ワークフロー開始時にこれらのタスクを作成:

```
TaskCreate: "言語の検出と設定" (ステップ 1)
TaskCreate: "データベースのビルド" (ステップ 2) - blockedBy: ステップ 1
TaskCreate: "必要に応じて修正を適用" (ステップ 3) - blockedBy: ステップ 2
TaskCreate: "品質の評価" (ステップ 4) - blockedBy: ステップ 3
TaskCreate: "必要に応じて品質を改善" (ステップ 5) - blockedBy: ステップ 4
TaskCreate: "最終レポートの生成" (ステップ 6) - blockedBy: ステップ 5
```

---

## 概要

データベース作成は言語タイプによって異なります:

### インタープリタ言語（Python, JavaScript, Go, Ruby）
- **ビルド不要** - CodeQL がソースを直接抽出
- **除外設定サポート** - `--codescanning-config` で無関係なファイルをスキップ

### コンパイル言語（C/C++, Java, C#, Rust, Swift）
- **ビルド必要** - CodeQL がコンパイルをトレースする必要あり
- **除外設定非サポート** - すべてのコンパイルされたコードをトレースする必要あり
- 成功するまでビルド方法を順番に試行:
  1. **オートビルド** - CodeQL がビルドを自動検出して実行
  2. **カスタムコマンド** - 検出されたビルドシステム用の明示的ビルドコマンド
  3. **マルチステップ** - init → trace-command → finalize による細かい制御
  4. **ノービルドフォールバック** - `--build-mode=none`（部分的解析、最終手段）

---

## データベース命名

以前のデータベースを上書きしないように、一意の連番データベース名を生成:

```bash
# 次に利用可能なデータベース番号を見つける
get_next_db_name() {
  local prefix="${1:-codeql}"
  local max=0
  for db in ${prefix}_*.db; do
    if [[ -d "$db" ]]; then
      num="${db#${prefix}_}"
      num="${num%.db}"
      if [[ "$num" =~ ^[0-9]+$ ]] && (( num > max )); then
        max=$num
      fi
    fi
  done
  echo "${prefix}_$((max + 1)).db"
}

DB_NAME=$(get_next_db_name)
echo "Database name: $DB_NAME"
```

以下のすべてのコマンドで `$DB_NAME` を使用してください。

---

## ビルドログ

ワークフロー全体を通して詳細なログファイルを維持します。重要なすべてのアクションをログに記録してください。

**開始時の初期化:**
```bash
LOG_FILE="${DB_NAME%.db}-build.log"
echo "=== CodeQL Database Build Log ===" > "$LOG_FILE"
echo "Started: $(date -Iseconds)" >> "$LOG_FILE"
echo "Working directory: $(pwd)" >> "$LOG_FILE"
echo "Database: $DB_NAME" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
```

**ログヘルパー関数:**
```bash
log_step() {
  echo "[$(date -Iseconds)] $1" >> "$LOG_FILE"
}

log_cmd() {
  echo "[$(date -Iseconds)] COMMAND: $1" >> "$LOG_FILE"
}

log_result() {
  echo "[$(date -Iseconds)] RESULT: $1" >> "$LOG_FILE"
  echo "" >> "$LOG_FILE"
}
```

**記録すべき内容:**
- 検出された言語とビルドシステム
- 各ビルド試行の正確なコマンド
- 修正の試行とその結果:
  - クリーンされたキャッシュ/アーティファクト
  - インストールされた依存関係（パッケージ名、バージョン）
  - ダウンロードされた JAR、npm パッケージ、Python ホイール
  - 設定されたレジストリ認証
- 適用された品質改善:
  - ソースルートの調整
  - 設定されたエクストラクタオプション
  - インストールされた型スタブ
- 品質評価結果（ファイル数、エラー）
- すべての環境変数を含む最終的な成功コマンド

---

## ステップ 1: 言語の検出と設定

### 1a. 言語の検出

```bash
# ファイル数で主要言語を検出
fd -t f -e py -e js -e ts -e go -e rb -e java -e c -e cpp -e h -e hpp -e rs -e cs | \
  sed 's/.*\.//' | sort | uniq -c | sort -rn | head -5

# ビルドファイルを確認（コンパイル言語）
ls -la Makefile CMakeLists.txt build.gradle pom.xml Cargo.toml *.sln 2>/dev/null || true

# 既存の CodeQL データベースを確認
ls -la "$DB_NAME" 2>/dev/null && echo "WARNING: existing database found"
```

| 言語 | `--language=` | タイプ |
|----------|---------------|------|
| Python | `python` | インタープリタ |
| JavaScript/TypeScript | `javascript` | インタープリタ |
| Go | `go` | インタープリタ |
| Ruby | `ruby` | インタープリタ |
| Java/Kotlin | `java` | コンパイル |
| C/C++ | `cpp` | コンパイル |
| C# | `csharp` | コンパイル |
| Rust | `rust` | コンパイル |
| Swift | `swift` | コンパイル（macOS） |

### 1b. 除外設定の作成（インタープリタ言語のみ）

> **コンパイル言語ではこのサブステップをスキップ** - ビルドトレースが必要な場合、除外設定はサポートされません。

無関係なファイルをスキャンし、`codeql-config.yml` を作成:

```bash
# よくある除外可能なディレクトリを見つける
ls -d node_modules vendor third_party external deps 2>/dev/null || true

# テストディレクトリを見つける
fd -t d -E node_modules "test|tests|spec|__tests__|fixtures" .

# 生成/縮小されたファイルを見つける
fd -t f -E node_modules "\.min\.js$|\.bundle\.js$|\.generated\." . | head -20

# ファイル数を推定
echo "Total source files:"
fd -t f -e py -e js -e ts -e go -e rb | wc -l
echo "In node_modules:"
fd -t f -e js -e ts node_modules 2>/dev/null | wc -l
```

**除外設定の作成:**

```yaml
# codeql-config.yml
paths-ignore:
  # パッケージマネージャ
  - node_modules
  - vendor
  - venv
  - .venv
  # サードパーティコード
  - third_party
  - external
  - deps
  # 生成/縮小
  - "**/*.min.js"
  - "**/*.bundle.js"
  - "**/generated/**"
  - "**/dist/**"
  # テスト（オプション）
  # - "**/test/**"
  # - "**/tests/**"
```

```bash
log_step "Created codeql-config.yml"
log_result "Exclusions: $(grep -c '^  -' codeql-config.yml) patterns"
```

---

## ステップ 2: データベースのビルド

### インタープリタ言語の場合（Python, JavaScript, Go, Ruby）

単一コマンド、ビルド不要:

```bash
log_step "Building database for interpreted language: <LANG>"
CMD="codeql database create $DB_NAME --language=<LANG> --source-root=. --codescanning-config=codeql-config.yml --overwrite"
log_cmd "$CMD"

$CMD 2>&1 | tee -a "$LOG_FILE"

if codeql resolve database -- "$DB_NAME" >/dev/null 2>&1; then
  log_result "SUCCESS"
else
  log_result "FAILED"
fi
```

**成功後はステップ 4（品質の評価）にスキップしてください。**

---

### コンパイル言語の場合（Java, C/C++, C#, Rust, Swift）

成功するまでビルド方法を順番に試行:

#### 方法 1: オートビルド

```bash
log_step "METHOD 1: Autobuild"
CMD="codeql database create $DB_NAME --language=<LANG> --source-root=. --overwrite"
log_cmd "$CMD"

$CMD 2>&1 | tee -a "$LOG_FILE"

if codeql resolve database -- "$DB_NAME" >/dev/null 2>&1; then
  log_result "SUCCESS"
else
  log_result "FAILED"
fi
```

#### 方法 2: カスタムコマンド

ビルドシステムを検出し、明示的なコマンドを使用:

| ビルドシステム | 検出 | コマンド |
|--------------|-----------|---------|
| Make | `Makefile` | `make clean && make -j$(nproc)` |
| CMake | `CMakeLists.txt` | `cmake -B build && cmake --build build` |
| Gradle | `build.gradle` | `./gradlew clean build -x test` |
| Maven | `pom.xml` | `mvn clean compile -DskipTests` |
| Cargo | `Cargo.toml` | `cargo clean && cargo build` |
| .NET | `*.sln` | `dotnet clean && dotnet build` |
| Meson | `meson.build` | `meson setup build && ninja -C build` |
| Bazel | `BUILD`/`WORKSPACE` | `bazel build //...` |

**プロジェクト固有のビルドスクリプトを探す:**
```bash
# カスタムビルドスクリプトを探す
fd -t f -e sh -e bash -e py "build|compile|make|setup" .
ls -la build.sh compile.sh Makefile.custom configure 2>/dev/null || true

# README のビルド手順を確認
grep -i -A5 "build\|compile\|install" README* 2>/dev/null | head -20
```

プロジェクトにはカスタムスクリプト（`build.sh`、`compile.sh`）や README に記載された非標準のビルドステップがある場合があります。見つかった場合はこれらを一般的なコマンドの代わりに使用してください。

```bash
log_step "METHOD 2: Custom command"
log_step "Detected build system: <BUILD_SYSTEM>"
BUILD_CMD="<BUILD_CMD>"
CMD="codeql database create $DB_NAME --language=<LANG> --source-root=. --command='$BUILD_CMD' --overwrite"
log_cmd "$CMD"

$CMD 2>&1 | tee -a "$LOG_FILE"

if codeql resolve database -- "$DB_NAME" >/dev/null 2>&1; then
  log_result "SUCCESS"
else
  log_result "FAILED"
fi
```

#### 方法 3: マルチステップビルド

細かい制御が必要な複雑なビルド向け:

```bash
log_step "METHOD 3: Multi-step build"

# 1. 初期化
log_cmd "codeql database init $DB_NAME --language=<LANG> --source-root=. --overwrite"
codeql database init $DB_NAME --language=<LANG> --source-root=. --overwrite

# 2. 各ビルドステップをトレース
log_cmd "codeql database trace-command $DB_NAME -- <build step 1>"
codeql database trace-command $DB_NAME -- <build step 1>

log_cmd "codeql database trace-command $DB_NAME -- <build step 2>"
codeql database trace-command $DB_NAME -- <build step 2>
# ... 必要に応じて追加ステップ

# 3. 完了処理
log_cmd "codeql database finalize $DB_NAME"
codeql database finalize $DB_NAME

if codeql resolve database -- "$DB_NAME" >/dev/null 2>&1; then
  log_result "SUCCESS"
else
  log_result "FAILED"
fi
```

#### 方法 4: ノービルドフォールバック（最終手段）

すべてのビルド方法が失敗した場合、部分的解析に `--build-mode=none` を使用:

> **警告:** これはビルドトレースなしでデータベースを作成します。解析は不完全になります — ソースレベルのパターンのみが検出され、コンパイルされたコードを通じたデータフローは追跡されません。

```bash
log_step "METHOD 4: No-build fallback (partial analysis)"
CMD="codeql database create $DB_NAME --language=<LANG> --source-root=. --build-mode=none --overwrite"
log_cmd "$CMD"

$CMD 2>&1 | tee -a "$LOG_FILE"

if codeql resolve database -- "$DB_NAME" >/dev/null 2>&1; then
  log_result "SUCCESS (partial - no build tracing)"
else
  log_result "FAILED"
fi
```

---

## ステップ 3: 修正の適用（ビルドが失敗した場合）

以下を順番に試行し、現在のビルド方法を再試行します。**各修正の試行をログに記録:**

### 1. 既存状態のクリーン
```bash
log_step "Applying fix: clean existing state"
rm -rf "$DB_NAME"
log_result "Removed $DB_NAME"
```

### 2. ビルドキャッシュのクリーン
```bash
log_step "Applying fix: clean build cache"
CLEANED=""
make clean 2>/dev/null && CLEANED="$CLEANED make"
rm -rf build CMakeCache.txt CMakeFiles 2>/dev/null && CLEANED="$CLEANED cmake-artifacts"
./gradlew clean 2>/dev/null && CLEANED="$CLEANED gradle"
mvn clean 2>/dev/null && CLEANED="$CLEANED maven"
cargo clean 2>/dev/null && CLEANED="$CLEANED cargo"
log_result "Cleaned: $CLEANED"
```

### 3. 不足している依存関係のインストール

> **注意:** 以下のコマンドは、CodeQL がビルドをトレースできるように*対象プロジェクトの*依存関係をインストールします。対象プロジェクトが期待するパッケージマネージャ（`pip`、`npm`、`go mod` 等）を使用してください — これはスキル自体のツール設定ではありません。

```bash
log_step "Applying fix: install dependencies"

# Python — 対象プロジェクトのパッケージマネージャ（pip/uv/poetry）を使用
if [ -f requirements.txt ]; then
  log_cmd "pip install -r requirements.txt"
  pip install -r requirements.txt 2>&1 | tee -a "$LOG_FILE"
fi
if [ -f setup.py ] || [ -f pyproject.toml ]; then
  log_cmd "pip install -e ."
  pip install -e . 2>&1 | tee -a "$LOG_FILE"
fi

# Node - インストールされたパッケージをログに記録
if [ -f package.json ]; then
  log_cmd "npm install"
  npm install 2>&1 | tee -a "$LOG_FILE"
fi

# Go
if [ -f go.mod ]; then
  log_cmd "go mod download"
  go mod download 2>&1 | tee -a "$LOG_FILE"
fi

# Java - ダウンロードされた依存関係をログに記録
if [ -f build.gradle ] || [ -f build.gradle.kts ]; then
  log_cmd "./gradlew dependencies --refresh-dependencies"
  ./gradlew dependencies --refresh-dependencies 2>&1 | tee -a "$LOG_FILE"
fi
if [ -f pom.xml ]; then
  log_cmd "mvn dependency:resolve"
  mvn dependency:resolve 2>&1 | tee -a "$LOG_FILE"
fi

# Rust
if [ -f Cargo.toml ]; then
  log_cmd "cargo fetch"
  cargo fetch 2>&1 | tee -a "$LOG_FILE"
fi

log_result "Dependencies installed - see above for details"
```

### 4. プライベートレジストリの処理

依存関係が認証を必要とする場合、ユーザーに確認:
```
AskUserQuestion: "ビルドにはプライベートレジストリへのアクセスが必要です。オプション:"
  1. "認証を設定してリトライ"
  2. "これらの依存関係をスキップ"
  3. "必要なものを表示"
```

```bash
# 認証設定が行われた場合ログに記録
log_step "Private registry authentication configured"
log_result "Registry: <REGISTRY_URL>, Method: <AUTH_METHOD>"
```

**修正後:** 現在のビルド方法をリトライ。それでも失敗する場合は次の方法に移行。

---

## ステップ 4: 品質の評価

すべての品質チェックを実行し、プロジェクトの期待されるソースファイルと比較します。

### 4a. メトリクスの収集

```bash
log_step "Assessing database quality"

# 1. ベースラインのコード行数とファイルリスト（最も信頼性の高い指標）
codeql database print-baseline -- "$DB_NAME"
BASELINE_LOC=$(python3 -c "
import json
with open('$DB_NAME/baseline-info.json') as f:
    d = json.load(f)
for lang, info in d['languages'].items():
    print(f'{lang}: {info[\"linesOfCode\"]} LoC, {len(info[\"files\"])} files')
")
echo "$BASELINE_LOC"
log_result "Baseline: $BASELINE_LOC"

# 2. ソースアーカイブのファイル数
SRC_FILE_COUNT=$(unzip -Z1 "$DB_NAME/src.zip" 2>/dev/null | wc -l)
echo "Files in source archive: $SRC_FILE_COUNT"

# 3. エクストラクタ診断からの抽出エラー
EXTRACTOR_ERRORS=$(find "$DB_NAME/diagnostic/extractors" -name '*.jsonl' \
  -exec cat {} + 2>/dev/null | grep -c '^{' 2>/dev/null || true)
EXTRACTOR_ERRORS=${EXTRACTOR_ERRORS:-0}
echo "Extractor errors: $EXTRACTOR_ERRORS"

# 4. 診断サマリーのエクスポート（実験的だが有用）
DIAG_TEXT=$(codeql database export-diagnostics --format=text -- "$DB_NAME" 2>/dev/null || true)
if [ -n "$DIAG_TEXT" ]; then
  echo "Diagnostics: $DIAG_TEXT"
fi

# 5. データベースが完了処理済みか確認
FINALIZED=$(grep '^finalised:' "$DB_NAME/codeql-database.yml" 2>/dev/null \
  | awk '{print $2}')
echo "Finalized: $FINALIZED"
```

### 4b. 期待されるソースとの比較

作業ディレクトリから期待されるソースファイル数を推定して比較:

```bash
# プロジェクト内のソースファイルを数える（言語に応じて拡張子を調整）
EXPECTED=$(fd -t f -e java -e kt --exclude 'codeql_*.db' \
  --exclude node_modules --exclude vendor --exclude .git . | wc -l)
echo "Expected source files: $EXPECTED"
echo "Extracted source files: $SRC_FILE_COUNT"

# データベースメタデータからのベースライン LoC
DB_LOC=$(grep '^baselineLinesOfCode:' "$DB_NAME/codeql-database.yml" \
  | awk '{print $2}')
echo "Baseline LoC: $DB_LOC"

# エラー率
if [ "$SRC_FILE_COUNT" -gt 0 ]; then
  ERROR_RATIO=$(python3 -c "print(f'{$EXTRACTOR_ERRORS/$SRC_FILE_COUNT*100:.1f}%')")
else
  ERROR_RATIO="N/A (no files)"
fi
echo "Error ratio: $ERROR_RATIO ($EXTRACTOR_ERRORS errors / $SRC_FILE_COUNT files)"
```

### 4c. 評価のログ記録

```bash
log_step "Quality assessment results"
log_result "Baseline LoC: $DB_LOC"
log_result "Source archive files: $SRC_FILE_COUNT (expected: ~$EXPECTED)"
log_result "Extractor errors: $EXTRACTOR_ERRORS (ratio: $ERROR_RATIO)"
log_result "Finalized: $FINALIZED"

# 抽出されたファイルのサンプル
unzip -Z1 "$DB_NAME/src.zip" 2>/dev/null | head -20 >> "$LOG_FILE"
```

### 品質基準

| 指標 | ソース | 良好 | 不良 |
|--------|--------|------|------|
| ベースライン LoC | `print-baseline` / `baseline-info.json` | > 0、プロジェクトサイズに比例 | 0 または期待値を大幅に下回る |
| ソースアーカイブファイル | `src.zip` | 期待されるソースファイル数に近い | 0 または期待値の 50% 未満 |
| エクストラクタエラー | `diagnostic/extractors/*.jsonl` | 0 またはファイルの 5% 未満 | ファイルの 5% 以上 |
| 完了処理済み | `codeql-database.yml` | `true` | `false`（不完全なビルド） |
| 主要ディレクトリ | `src.zip` リスト | アプリケーションコードディレクトリが存在 | `src/main`、`lib/`、`app/` 等が不足 |
| "No source code seen" | ビルドログ | 不在 | 存在（キャッシュされたビルド — コンパイル言語） |

**ベースライン LoC の解釈:** 少数のエクストラクタエラーは正常であり、解析に大きな影響を与えません。ただし、`baselineLinesOfCode` が 0 またはソースアーカイブにファイルが含まれていない場合、データベースは空です — おそらくキャッシュされたビルド（コンパイル言語）または誤った `--source-root` です。

---

## ステップ 5: 品質の改善（不良の場合）

以下の改善を試み、各改善後に再評価します。**すべての改善をログに記録:**

### 1. ソースルートの調整
```bash
log_step "Quality improvement: adjust source root"
NEW_ROOT="./src"  # または検出されたサブディレクトリ
# インタープリタ言語: --codescanning-config=codeql-config.yml を追加
# コンパイル言語: config フラグを省略
log_cmd "codeql database create $DB_NAME --language=<LANG> --source-root=$NEW_ROOT --overwrite"
codeql database create $DB_NAME --language=<LANG> --source-root=$NEW_ROOT --overwrite
log_result "Changed source-root to: $NEW_ROOT"
```

### 2. "no source code seen" の修正（キャッシュされたビルド - コンパイル言語のみ）
```bash
log_step "Quality improvement: force rebuild (cached build detected)"
log_cmd "make clean && rebuild"
make clean && codeql database create $DB_NAME --language=<LANG> --overwrite
log_result "Forced clean rebuild"
```

### 3. 型スタブ / 依存関係のインストール

> **注意:** これらは CodeQL 抽出品質を向上させるために*対象プロジェクトの*環境にインストールします。

```bash
log_step "Quality improvement: install type stubs/additional deps"

# Python 型スタブ — 対象プロジェクトの環境にインストール
STUBS_INSTALLED=""
for stub in types-requests types-PyYAML types-redis; do
  if pip install "$stub" 2>/dev/null; then
    STUBS_INSTALLED="$STUBS_INSTALLED $stub"
  fi
done
log_result "Installed type stubs:$STUBS_INSTALLED"

# 追加のプロジェクト依存関係
log_cmd "pip install -e ."
pip install -e . 2>&1 | tee -a "$LOG_FILE"
```

### 4. エクストラクタオプションの調整
```bash
log_step "Quality improvement: adjust extractor options"

# C/C++: ヘッダーを含める
export CODEQL_EXTRACTOR_CPP_OPTION_TRAP_HEADERS=true
log_result "Set CODEQL_EXTRACTOR_CPP_OPTION_TRAP_HEADERS=true"

# Java: 特定の JDK バージョン
export CODEQL_EXTRACTOR_JAVA_OPTION_JDK_VERSION=17
log_result "Set CODEQL_EXTRACTOR_JAVA_OPTION_JDK_VERSION=17"

# 次に現在の方法で再ビルド
```

**各改善後:** 品質を再評価。改善が不可能な場合は次のビルド方法に移行。

---

## 終了条件

**成功:**
- 品質評価が「良好」を示す
- ユーザーが現在のデータベース状態を受け入れる

**失敗（すべての方法を使い切った場合）:**
```
AskUserQuestion: "すべてのビルド方法が失敗しました。オプション:"
  1. "現在の状態を受け入れる"（何らかのデータベースが存在する場合）
  2. "ビルドを手動で修正してリトライ"
  3. "中止"
```

---

## 最終レポート

**ログファイルの最終処理:**
```bash
echo "=== Build Complete ===" >> "$LOG_FILE"
echo "Finished: $(date -Iseconds)" >> "$LOG_FILE"
echo "Final database: $DB_NAME" >> "$LOG_FILE"
echo "Successful method: <METHOD>" >> "$LOG_FILE"
echo "Final command: <EXACT_COMMAND>" >> "$LOG_FILE"
codeql resolve database -- "$DB_NAME" >> "$LOG_FILE" 2>&1
```

**ユーザーへの報告:**
```
## データベースビルド完了

**データベース:** $DB_NAME
**言語:** <LANG>
**ビルド方法:** autobuild | custom | multi-step
**抽出されたファイル:** <COUNT>

### 品質:
- エラー: <N>
- カバレッジ: <good/partial/poor>

### ビルドログ:
以下を含む完全な詳細は `$LOG_FILE` を参照:
- 試行されたすべてのコマンド
- 適用された修正
- 品質評価

**使用された最終コマンド:**
<EXACT_COMMAND>

**解析の準備ができました。**
```

---

## パフォーマンス: 並列抽出

`--threads` を使用してデータベース作成を並列化:

```bash
# コンパイル言語（除外設定なし）
codeql database create $DB_NAME --language=cpp --threads=0 --command='make -j$(nproc)'

# インタープリタ言語（除外設定あり）
codeql database create $DB_NAME --language=python --threads=0 \
  --codescanning-config=codeql-config.yml
```

**注意:** `--threads=0` は利用可能なコアを自動検出します。共有マシンでは明示的な数を使用してください。

---

## クイックリファレンス

| 言語 | ビルドシステム | カスタムコマンド |
|----------|--------------|----------------|
| C/C++ | Make | `make clean && make -j$(nproc)` |
| C/C++ | CMake | `cmake -B build && cmake --build build` |
| Java | Gradle | `./gradlew clean build -x test` |
| Java | Maven | `mvn clean compile -DskipTests` |
| Rust | Cargo | `cargo clean && cargo build` |
| C# | .NET | `dotnet clean && dotnet build` |

詳細は [language-details.md](../references/language-details.md) を参照。
