# データ拡張作成ワークフロー

プロジェクト固有の API に対する CodeQL のデータフローカバレッジを向上させるために、データ拡張 YAML ファイルを生成します。データベースビルド後、解析前に実行します。

## タスクシステム

ワークフロー開始時にこれらのタスクを作成:

```
TaskCreate: "既存のデータ拡張を確認" (ステップ 1)
TaskCreate: "既知のソースとシンクをクエリ" (ステップ 2) - blockedBy: ステップ 1
TaskCreate: "不足しているソースとシンクを特定" (ステップ 3) - blockedBy: ステップ 2
TaskCreate: "データ拡張ファイルを作成" (ステップ 4) - blockedBy: ステップ 3
TaskCreate: "再解析で検証" (ステップ 5) - blockedBy: ステップ 4
```

### 早期終了ポイント

| ステップ後 | 条件 | アクション |
|------------|-----------|--------|
| ステップ 1 | 拡張が既に存在 | 見つかったパック/ファイルを run-analysis ワークフローに返して終了 |
| ステップ 3 | 不足モデルが特定されなかった | カバレッジが十分であることを報告して終了 |

---

## ステップ

### ステップ 1: 既存のデータ拡張を確認

プロジェクト内の既存のデータ拡張とモデルパックを検索します。

**1. リポジトリ内モデルパック** — `dataExtensions` を持つ `qlpack.yml` または `codeql-pack.yml`:

```bash
fd '(qlpack|codeql-pack)\.yml$' . --exclude codeql_*.db | while read -r f; do
  if grep -q 'dataExtensions' "$f"; then
    echo "MODEL PACK: $(dirname "$f") - $(grep '^name:' "$f")"
  fi
done
```

**2. スタンドアロンデータ拡張ファイル** — `extensions:` キーを持つ `.yml` ファイル:

```bash
rg -l '^extensions:' --glob '*.yml' --glob '!codeql_*.db/**' | head -20
```

**3. インストール済みモデルパック:**

```bash
codeql resolve qlpacks 2>/dev/null | grep -iE 'model|extension'
```

**見つかった場合:** 見つかったものをユーザーに報告して終了します。これらは run-analysis ワークフローのモデルパック検出（ステップ 2b）で取得されます。

**見つからなかった場合:** ステップ 2 に進みます。

---

### ステップ 2: 既知のソースとシンクをクエリ

データベースに対してカスタム QL クエリを実行し、CodeQL が現在認識しているすべてのソースとシンクを列挙します。これにより、モデル化されているものとされていないものの直接的なインベントリが得られます。

#### 2a: データベースと言語の選択

```bash
DB_NAME=$(ls -dt codeql_*.db 2>/dev/null | head -1)
LANG=$(codeql resolve database --format=json -- "$DB_NAME" | jq -r '.languages[0]')
echo "Database: $DB_NAME, Language: $LANG"

DIAG_DIR="${DB_NAME%.db}-diagnostics"
mkdir -p "$DIAG_DIR"
```

#### 2b: ソース列挙クエリの作成

`Write` ツールを使用して、[diagnostic-query-templates.md](../references/diagnostic-query-templates.md#source-enumeration-query) のソーステンプレートから `$DIAG_DIR/list-sources.ql` を作成します。`$LANG` に正しいインポートブロックを選択してください。

#### 2c: シンク列挙クエリの作成

`Write` ツールを使用して、[diagnostic-query-templates.md](../references/diagnostic-query-templates.md#sink-enumeration-queries) の言語固有シンクテンプレートから `$DIAG_DIR/list-sinks.ql` を作成します。Concepts API は言語間で大きく異なります — 検出された言語の正確なテンプレートを使用してください。

**Java の場合:** `codeql/java-all` 依存関係を持つ `$DIAG_DIR/qlpack.yml` も作成し、クエリ実行前に `codeql pack install` を実行してください。テンプレートリファレンスの Java セクションを参照してください。

#### 2d: クエリの実行

```bash
# ソースクエリを実行
codeql query run \
  --database="$DB_NAME" \
  --output="$DIAG_DIR/sources.bqrs" \
  -- "$DIAG_DIR/list-sources.ql"

codeql bqrs decode \
  --format=csv \
  --output="$DIAG_DIR/sources.csv" \
  -- "$DIAG_DIR/sources.bqrs"

# シンククエリを実行
codeql query run \
  --database="$DB_NAME" \
  --output="$DIAG_DIR/sinks.bqrs" \
  -- "$DIAG_DIR/list-sinks.ql"

codeql bqrs decode \
  --format=csv \
  --output="$DIAG_DIR/sinks.csv" \
  -- "$DIAG_DIR/sinks.bqrs"
```

#### 2e: 結果のサマリー

```bash
echo "=== Known Sources ==="
wc -l < "$DIAG_DIR/sources.csv"
# ユニークなソースタイプを表示
cut -d',' -f2 "$DIAG_DIR/sources.csv" | sort -u

echo "=== Known Sinks ==="
wc -l < "$DIAG_DIR/sinks.csv"
# ユニークなシンク種別を表示
cut -d',' -f2 "$DIAG_DIR/sinks.csv" | sort -u
```

両方の CSV ファイルを読み取り、ユーザーにサマリーを提示:

```
## CodeQL 既知モデル

### ソース（合計 <N>）:
- remote: <count>（HTTP ハンドラー、リクエストパース）
- local: <count>（CLI 引数、ファイル読み取り）
- ...

### シンク（合計 <N>）:
- sql-execution: <count>
- command-execution: <count>
- file-access: <count>
- ...
```

---

### ステップ 3: 不足しているソースとシンクの特定

これはコア分析ステップです。プロジェクトの API サーフェスと CodeQL の既知モデルを照合します。

#### 3a: プロジェクトの API サーフェスのマッピング

ソースコードを読んで、セキュリティに関連するパターンを特定します。探すべきもの:

| パターン | 検索対象 | 想定されるモデルタイプ |
|---------|-------------|-------------------|
| HTTP/リクエストハンドラー | カスタムリクエストパース、パラメータアクセス | `sourceModel`（kind: `remote`） |
| データベース層 | カスタム ORM メソッド、生クエリラッパー | `sinkModel`（kind: `sql-injection`） |
| コマンド実行 | シェルラッパー、プロセス起動 | `sinkModel`（kind: `command-injection`） |
| ファイル操作 | カスタムファイル読み書き、パス構築 | `sinkModel`（kind: `path-injection`） |
| テンプレートレンダリング | HTML 出力、レスポンスビルダー | `sinkModel`（kind: `xss`） |
| デシリアライゼーション | カスタムデシリアライザー、データローダー | `sinkModel`（kind: `unsafe-deserialization`） |
| HTTP クライアント | URL 構築、リクエストビルダー | `sinkModel`（kind: `ssrf`） |
| サニタイザー | 入力バリデーション、エスケープ関数 | `neutralModel` |
| パススルーラッパー | ロギング、キャッシュ、エンコーディング | `summaryModel`（kind: `taint`） |

`Grep` を使用してソースコード内でこれらのパターンを検索:

```bash
# Python の例 - 言語に応じてパターンを調整
rg -n 'def (get_param|get_header|get_body|parse_request)' --type py
rg -n '(execute|query|raw_sql|cursor\.)' --type py
rg -n '(subprocess|os\.system|popen|exec)' --type py
rg -n '(open|read_file|write_file|path\.join)' --type py
rg -n '(render|template|html)' --type py
rg -n '(requests\.|urlopen|fetch|http_client)' --type py
```

#### 3b: 既知のソースとシンクとの照合

3a で見つかった各 API パターンについて、ステップ 2 のソース/シンク CSV に表示されているか確認:

```bash
# 特定のファイル/関数が既知ソースに表示されているか確認
grep -i "<function_or_file>" "$DIAG_DIR/sources.csv"

# 特定のファイル/関数が既知シンクに表示されているか確認
grep -i "<function_or_file>" "$DIAG_DIR/sinks.csv"
```

**API が「不足」している場合:**
- ユーザー入力を処理しているが `sources.csv` に表示されない
- 危険な操作を実行しているが `sinks.csv` に表示されない
- テイントされたデータをラップ/変換しているが CodeQL にサマリーモデルがない（どちらの CSV にも表示されない — 既知のソース/シンクの周りのラッパーパターンのコードを読んで特定）

#### 3c: ギャップの報告

ユーザーに発見を提示:

```
## データフローカバレッジのギャップ

### 不足しているソース（追跡されていないユーザー入力）:
- `myapp.http.Request.get_param()` — カスタムパラメータアクセス
- `myapp.auth.Token.decode()` — 信頼できないトークンデータ

### 不足しているシンク（チェックされていない危険な操作）:
- `myapp.db.Connection.raw_query()` — SQL 実行ラッパー
- `myapp.shell.Runner.execute()` — コマンド実行

### 不足しているサマリー（ラッパーでテイントが失われる）:
- `myapp.cache.Cache.get()` — テイントがキャッシュを通じて伝播しない
- `myapp.utils.encode_json()` — シリアライゼーションでテイントが失われる

データ拡張ファイルの作成に進みますか？
```

`AskUserQuestion` を使用:

```
header: "拡張"
question: "特定されたギャップに対するデータ拡張ファイルを作成しますか？"
options:
  - label: "すべて作成（推奨）"
    description: "特定されたすべてのギャップに対する拡張を生成"
  - label: "個別に選択"
    description: "モデル化するギャップを選択"
  - label: "スキップ"
    description: "拡張不要、解析に進む"
```

**「スキップ」の場合:** ワークフローを終了。

**「個別に選択」の場合:** `multiSelect: true` で各ギャップをリストした `AskUserQuestion` を使用。

---

### ステップ 4: データ拡張ファイルの作成

ユーザーが確認したギャップに対する YAML データ拡張ファイルを生成します。

#### ファイル構造

プロジェクトルートの `codeql-extensions/` ディレクトリにファイルを作成:

```
codeql-extensions/
  sources.yml       # sourceModel エントリ
  sinks.yml         # sinkModel エントリ
  summaries.yml     # summaryModel と neutralModel エントリ
```

#### YAML フォーマット

すべての拡張ファイルはこの構造に従います:

```yaml
extensions:
  - addsTo:
      pack: codeql/<language>-all  # ターゲットライブラリパック
      extensible: <model-type>      # sourceModel, sinkModel, summaryModel, neutralModel
    data:
      - [<columns>]
```

#### ソースモデル

カラム: `[package, type, subtypes, name, signature, ext, output, kind, provenance]`

| カラム | 説明 | 例 |
|--------|-------------|---------|
| package | モジュール/パッケージパス | `myapp.auth` |
| type | クラスまたはモジュール名 | `AuthManager` |
| subtypes | サブクラスを含める | `True`（Java: 大文字） / `true`（Python/JS/Go） |
| name | メソッド名 | `get_token` |
| signature | メソッドシグネチャ（オプション） | `""`（Python/JS）、`"(String,int)"`（Java） |
| ext | 拡張（オプション） | `""` |
| output | テイントされるもの | `ReturnValue`、`Parameter[0]`（Java） / `Argument[0]`（Python/JS/Go） |
| kind | ソースカテゴリ | `remote`, `local`, `file`, `environment`, `database` |
| provenance | モデルの作成方法 | `manual` |

**Java 固有のフォーマットの違い:**
- **subtypes**: `True` / `False`（大文字、Python スタイル）を使用、`true` / `false` ではない
- **パラメータの出力**: `Parameter[N]`（`Argument[N]` ではない）を使用してメソッドパラメータをソースとしてマーク
- **signature**: 曖昧さ解消のために必要 — Java 型構文を使用: `"(String)"`、`"(String,int)"`
- **パラメータ範囲**: 複数の連続パラメータをマークするには `Parameter[0..2]` を使用

例（Python）:

```yaml
# codeql-extensions/sources.yml
extensions:
  - addsTo:
      pack: codeql/python-all
      extensible: sourceModel
    data:
      - ["myapp.http", "Request", true, "get_param", "", "", "ReturnValue", "remote", "manual"]
      - ["myapp.http", "Request", true, "get_header", "", "", "ReturnValue", "remote", "manual"]
```

例（Java — `True`、`Parameter[N]`、signature に注意）:

```yaml
# codeql-extensions/sources.yml
extensions:
  - addsTo:
      pack: codeql/java-all
      extensible: sourceModel
    data:
      - ["com.myapp.controller", "ApiController", True, "search", "(String)", "", "Parameter[0]", "remote", "manual"]
      - ["com.myapp.service", "FileService", True, "upload", "(String,String)", "", "Parameter[0..1]", "remote", "manual"]
```

#### シンクモデル

カラム: `[package, type, subtypes, name, signature, ext, input, kind, provenance]`

注意: カラム 7 は `input`（テイントされたデータを受け取る引数）であり、`output` ではありません。

| 種類 | 脆弱性 |
|------|---------------|
| `sql-injection` | SQL インジェクション |
| `command-injection` | コマンドインジェクション |
| `path-injection` | パストラバーサル |
| `xss` | クロスサイトスクリプティング |
| `code-injection` | コードインジェクション |
| `ssrf` | サーバーサイドリクエストフォージェリ |
| `unsafe-deserialization` | 安全でないデシリアライゼーション |

例（Python）:

```yaml
# codeql-extensions/sinks.yml
extensions:
  - addsTo:
      pack: codeql/python-all
      extensible: sinkModel
    data:
      - ["myapp.db", "Connection", true, "raw_query", "", "", "Argument[0]", "sql-injection", "manual"]
      - ["myapp.shell", "Runner", false, "execute", "", "", "Argument[0]", "command-injection", "manual"]
```

例（Java — `True` とシンク入力の `Argument[N]` に注意）:

```yaml
extensions:
  - addsTo:
      pack: codeql/java-all
      extensible: sinkModel
    data:
      - ["com.myapp.db", "QueryRunner", True, "execute", "(String)", "", "Argument[0]", "sql-injection", "manual"]
```

#### サマリーモデル

カラム: `[package, type, subtypes, name, signature, ext, input, output, kind, provenance]`

| 種類 | 説明 |
|------|-------------|
| `taint` | データがフローを通過、まだテイント |
| `value` | データがフローを通過、正確な値が保持 |

例:

```yaml
# codeql-extensions/summaries.yml
extensions:
  # パススルー: テイントが伝播
  - addsTo:
      pack: codeql/python-all
      extensible: summaryModel
    data:
      - ["myapp.cache", "Cache", true, "get", "", "", "Argument[0]", "ReturnValue", "taint", "manual"]
      - ["myapp.utils", "JSON", false, "parse", "", "", "Argument[0]", "ReturnValue", "taint", "manual"]

  # サニタイザー: テイントがブロック
  - addsTo:
      pack: codeql/python-all
      extensible: neutralModel
    data:
      - ["myapp.security", "Sanitizer", "escape_html", "", "summary", "manual"]
```

**`neutralModel` とモデルなしの違い:** 関数にモデルがまったくない場合、CodeQL はそれを通じたフローを推測する可能性があります。既知の安全な関数を通じたテイント伝播を明示的にブロックするには `neutralModel` を使用してください。

#### 言語固有の注意事項

**Python:** `package` にはドット区切りのモジュールパスを使用（例: `myapp.db`）。

**JavaScript:** プロジェクトローカルコードの場合、`package` は多くの場合 `""` です。npm パッケージにはインポートパスを使用。

**Go:** 完全なインポートパスを使用（例: `myapp/internal/db`）。パッケージレベル関数の場合、`type` は多くの場合 `""` です。

**Java:** 完全修飾パッケージ名を使用（例: `com.myapp.db`）。

**C/C++:** `package` には `""` を使用し、名前空間を `type` に入れます。

#### ファイルの書き込み

`Write` ツールを使用して各ファイルを作成します。エントリのあるファイルのみ作成してください — 空のカテゴリはスキップしてください。

#### 拡張のデプロイ

**既知の制限:** `--additional-packs` と `--model-packs` フラグは、プリコンパイルされたクエリパック（`.codeql/libraries/` 内に `java-all` をキャッシュするバンドル CodeQL ディストリビューション）では機能しません。スタンドアロンモデルパックディレクトリに配置された拡張は `codeql resolve qlpacks` で解決されますが、`codeql database analyze` 中は暗黙的に無視されます。

**回避策 — ライブラリパックの `ext/` ディレクトリに拡張をコピー:**

> **警告:** `ext/` ディレクトリにコピーされたファイルは CodeQL の管理されたパックキャッシュ内にあります。`codeql pack download` やバージョンアップグレードでパックが更新されると**失われます**。パック更新後は、このデプロイステップを再実行して拡張を復元してください。

```bash
# クエリパックが使用する java-all ext ディレクトリを見つける
JAVA_ALL_EXT=$(find "$(codeql resolve qlpacks 2>/dev/null | grep 'java-queries' | awk '{print $NF}' | tr -d '()')" \
  -path '*/.codeql/libraries/codeql/java-all/*/ext' -type d 2>/dev/null | head -1)

if [ -n "$JAVA_ALL_EXT" ]; then
  PROJECT_NAME=$(basename "$(pwd)")
  cp codeql-extensions/sources.yml "$JAVA_ALL_EXT/${PROJECT_NAME}.sources.model.yml"
  [ -f codeql-extensions/sinks.yml ] && cp codeql-extensions/sinks.yml "$JAVA_ALL_EXT/${PROJECT_NAME}.sinks.model.yml"
  [ -f codeql-extensions/summaries.yml ] && cp codeql-extensions/summaries.yml "$JAVA_ALL_EXT/${PROJECT_NAME}.summaries.model.yml"

  # デプロイの検証 — ファイルが正しく配置されたことを確認
  DEPLOYED=$(ls "$JAVA_ALL_EXT/${PROJECT_NAME}".*.model.yml 2>/dev/null | wc -l)
  if [ "$DEPLOYED" -gt 0 ]; then
    echo "Extensions deployed to $JAVA_ALL_EXT ($DEPLOYED files):"
    ls -la "$JAVA_ALL_EXT/${PROJECT_NAME}".*.model.yml
  else
    echo "ERROR: Files were copied but verification failed. Check path: $JAVA_ALL_EXT"
  fi
else
  echo "WARNING: Could not find java-all ext directory. Extensions may not load."
  echo "Attempted path lookup from: codeql resolve qlpacks | grep java-queries"
  echo "Run 'codeql resolve qlpacks' manually to debug."
fi
```

**Python/JS/Go の場合:** 同じ制限が適用される可能性があります。`<lang>-all` パックの `ext/` ディレクトリを見つけて拡張をそこにコピーしてください。

**代替手段（クエリパックがプリコンパイルされていない場合）:** 適切なモデルパック `qlpack.yml` を持つ `--additional-packs=./codeql-extensions` を使用:

```yaml
# codeql-extensions/qlpack.yml
name: custom/<project>-extensions
version: 0.0.1
library: true
extensionTargets:
  codeql/<lang>-all: "*"
dataExtensions:
  - sources.yml
  - sinks.yml
  - summaries.yml
```

---

### ステップ 5: 再解析による検証

拡張の有無でフルセキュリティ解析を実行し、検出差分を測定します。これはソース/シンク列挙クエリを再実行するよりも信頼性が高く、テイント追跡クエリが使用する `sourceModel` extensible を反映しない場合があるためです。

#### 5a: ベースライン解析の実行（拡張なし）

```bash
RESULTS_DIR="${DB_NAME%.db}-results"
mkdir -p "$RESULTS_DIR"

# ベースライン実行（または以前のステップで既に実行済みならスキップ）
codeql database analyze "$DB_NAME" \
  --format=sarif-latest \
  --output="$RESULTS_DIR/baseline.sarif" \
  --threads=0 \
  -- codeql/<lang>-queries:codeql-suites/<lang>-security-extended.qls
```

#### 5b: 拡張付き解析の実行

```bash
# キャッシュをクリアして再評価を強制
codeql database cleanup "$DB_NAME"

codeql database analyze "$DB_NAME" \
  --format=sarif-latest \
  --output="$RESULTS_DIR/with-extensions.sarif" \
  --threads=0 \
  --rerun \
  -- codeql/<lang>-queries:codeql-suites/<lang>-security-extended.qls
```

`-vvv` フラグを使用して拡張がロードされていることを確認 — stderr で `Loading data extensions in ... <your-extension-file>.yml` を探してください。

#### 5c: 検出の比較

```bash
BASELINE=$(python3 -c "import json; print(sum(len(r.get('results',[])) for r in json.load(open('$RESULTS_DIR/baseline.sarif')).get('runs',[])))")
WITH_EXT=$(python3 -c "import json; print(sum(len(r.get('results',[])) for r in json.load(open('$RESULTS_DIR/with-extensions.sarif')).get('runs',[])))")
echo "Findings: $BASELINE → $WITH_EXT (+$((WITH_EXT - BASELINE)))"
```

**カウントが増加しなかった場合:** 拡張 YAML に構文エラーがあるか、コードと一致しないカラム値がある可能性があります。確認事項:

| 問題 | 解決策 |
|-------|----------|
| 拡張がロードされない | `-vvv` で実行し、出力で拡張ファイル名を検索 |
| プリコンパイルパックが拡張を無視 | 上記の `ext/` ディレクトリの回避策を使用 |
| Java: 新しい検出なし | subtypes の `True`/`False`（大文字）、ソースの `Parameter[N]` を確認 |
| 新しいソース/シンクなし | カラム値が実際のコードシグネチャと正確に一致することを確認 |
| 型が見つからない | CodeQL データベースに表示される正確な型名を使用 |
| 引数インデックスが間違い | 引数は 0 インデックス; `self` は `Argument[self]`（Python）、`Parameter[0]`（Java） |

拡張ファイルを修正し、`ext/` に再デプロイし、カウントが増加するまで 5b を再実行してください。

---

## 最終出力

```
## データ拡張を作成しました

**データベース:** $DB_NAME
**言語:** <LANG>

### 作成されたファイル:
- codeql-extensions/sources.yml — <N> ソースモデル
- codeql-extensions/sinks.yml — <N> シンクモデル
- codeql-extensions/summaries.yml — <N> サマリー/ニュートラルモデル

### モデルカバレッジ:
- ソース: <BEFORE> → <AFTER> (+<DELTA>)
- シンク: <BEFORE> → <AFTER> (+<DELTA>)

### 使用方法:
拡張が `<lang>-all` ext/ ディレクトリにデプロイ済み（自動ロード）。
バージョン管理用のソースファイルは `codeql-extensions/` にあります。
使用するには run-analysis ワークフローを実行してください。
```

## リファレンス

- [脅威モデルリファレンス](../references/threat-models.md) — 解析中にアクティブなソースカテゴリを制御
- [CodeQL データ拡張](https://codeql.github.com/docs/codeql-cli/using-custom-queries-with-the-codeql-cli/#using-extension-packs)
- [ライブラリモデルのカスタマイズ](https://codeql.github.com/docs/codeql-language-guides/customizing-library-models-for-python/)
