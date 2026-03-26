# プラグイン固有のコマンド機能リファレンス

このリファレンスでは、Claude Code プラグインにバンドルされるコマンド固有の機能とパターンを扱う。

## 目次

- [プラグインコマンドのディスカバリー](#プラグインコマンドのディスカバリー)
- [CLAUDE_PLUGIN_ROOT 環境変数](#claude_plugin_root-環境変数)
- [プラグインコマンドパターン](#プラグインコマンドパターン)
- [プラグインコンポーネントとの統合](#プラグインコンポーネントとの統合)
- [バリデーションパターン](#バリデーションパターン)

## プラグインコマンドのディスカバリー

### 自動検出

Claude Code はプラグイン内のコマンドを以下のロケーションから自動検出する:

```
plugin-name/
├── commands/              # 自動検出されるコマンド
│   ├── foo.md            # /foo (plugin:plugin-name)
│   └── bar.md            # /bar (plugin:plugin-name)
└── plugin.json           # プラグインマニフェスト
```

**重要なポイント:**
- コマンドはプラグインロード時に検出される
- 手動登録は不要
- コマンドは `/help` で "(plugin:plugin-name)" ラベル付きで表示される
- サブディレクトリが名前空間を作成する

### 名前空間付きプラグインコマンド

論理的なグループ化のためにサブディレクトリでコマンドを整理する:

```
plugin-name/
└── commands/
    ├── review/
    │   ├── security.md    # /security (plugin:plugin-name:review)
    │   └── style.md       # /style (plugin:plugin-name:review)
    └── deploy/
        ├── staging.md     # /staging (plugin:plugin-name:deploy)
        └── prod.md        # /prod (plugin:plugin-name:deploy)
```

**名前空間の動作:**
- サブディレクトリ名が名前空間になる
- `/help` で "(plugin:plugin-name:namespace)" として表示
- 関連コマンドの整理に便利
- プラグインに 5 つ以上のコマンドがある場合に使用

### コマンドの命名規則

**プラグインコマンド名は以下を満たすべき:**
1. 説明的でアクション指向
2. よくあるコマンド名との競合を避ける
3. 複数語の名前にはハイフンを使用
4. 一意性のためにプラグイン名のプレフィックスを検討

**例:**
```
良い例:
- /mylyn-sync          (プラグイン固有のプレフィックス)
- /analyze-performance (説明的なアクション)
- /docker-compose-up   (明確な目的)

避けるべき例:
- /test               (よくある名前と競合)
- /run                (汎用的すぎる)
- /do-stuff           (説明的でない)
```

## CLAUDE_PLUGIN_ROOT 環境変数

### 目的

`${CLAUDE_PLUGIN_ROOT}` はプラグインコマンドで利用可能な特別な環境変数で、プラグインディレクトリの絶対パスに解決される。

**重要な理由:**
- プラグイン内のポータブルなパスを実現
- プラグインのファイルやスクリプトを参照可能
- 異なるインストール先でも動作
- マルチファイルプラグイン操作に不可欠

### 基本的な使い方

プラグイン内のファイルを参照する:

```markdown
---
description: Analyze using plugin script
allowed-tools: Bash(node:*), Read
---

Run analysis: !`node ${CLAUDE_PLUGIN_ROOT}/scripts/analyze.js`

Read template: @${CLAUDE_PLUGIN_ROOT}/templates/report.md
```

**展開結果:**
```
Run analysis: !`node /path/to/plugins/plugin-name/scripts/analyze.js`

Read template: @/path/to/plugins/plugin-name/templates/report.md
```

### よくあるパターン

#### 1. プラグインスクリプトの実行

```markdown
---
description: Run custom linter from plugin
allowed-tools: Bash(node:*)
---

Lint results: !`node ${CLAUDE_PLUGIN_ROOT}/bin/lint.js $1`

Review the linting output and suggest fixes.
```

#### 2. 設定ファイルの読み込み

```markdown
---
description: Deploy using plugin configuration
allowed-tools: Read, Bash(*)
---

Configuration: @${CLAUDE_PLUGIN_ROOT}/config/deploy-config.json

Deploy application using the configuration above for $1 environment.
```

#### 3. プラグインリソースへのアクセス

```markdown
---
description: Generate report from template
---

Use this template: @${CLAUDE_PLUGIN_ROOT}/templates/api-report.md

Generate a report for @$1 following the template format.
```

#### 4. マルチステッププラグインワークフロー

```markdown
---
description: Complete plugin workflow
allowed-tools: Bash(*), Read
---

Step 1 - Prepare: !`bash ${CLAUDE_PLUGIN_ROOT}/scripts/prepare.sh $1`
Step 2 - Config: @${CLAUDE_PLUGIN_ROOT}/config/$1.json
Step 3 - Execute: !`${CLAUDE_PLUGIN_ROOT}/bin/execute $1`

Review results and report status.
```

### ベストプラクティス

1. **プラグイン内部パスには常に使用する:**
   ```markdown
   # 良い例
   @${CLAUDE_PLUGIN_ROOT}/templates/foo.md

   # 悪い例
   @./templates/foo.md  # カレントディレクトリからの相対パス（プラグインからではない）
   ```

2. **ファイルの存在を検証する:**
   ```markdown
   ---
   description: Use plugin config if exists
   allowed-tools: Bash(test:*), Read
   ---

   !`test -f ${CLAUDE_PLUGIN_ROOT}/config.json && echo "exists" || echo "missing"`

   If config exists, load it: @${CLAUDE_PLUGIN_ROOT}/config.json
   Otherwise, use defaults...
   ```

3. **プラグインのファイル構造をドキュメント化する:**
   ```markdown
   <!--
   プラグイン構造:
   ${CLAUDE_PLUGIN_ROOT}/
   ├── scripts/analyze.js  (解析スクリプト)
   ├── templates/          (レポートテンプレート)
   └── config/             (設定ファイル)
   -->
   ```

4. **引数と組み合わせる:**
   ```markdown
   Run: !`${CLAUDE_PLUGIN_ROOT}/bin/process.sh $1 $2`
   ```

### トラブルシューティング

**変数が展開されない場合:**
- コマンドがプラグインから読み込まれていることを確認
- bash 実行が許可されていることを確認
- 構文が正確であることを確認: `${CLAUDE_PLUGIN_ROOT}`

**ファイルが見つからないエラー:**
- プラグインディレクトリにファイルが存在するか確認
- プラグインルートからの相対パスが正しいか確認
- ファイルの読み取り/実行権限を確認

**スペースを含むパス:**
- Bash コマンドは自動的にスペースを処理
- ファイル参照もスペース付きパスで動作
- 特別なクォーティングは不要

## プラグインコマンドパターン

### パターン 1: 設定ベースのコマンド

プラグイン固有の設定を読み込むコマンド:

```markdown
---
description: Deploy using plugin settings
allowed-tools: Read, Bash(*)
---

Load configuration: @${CLAUDE_PLUGIN_ROOT}/deploy-config.json

Deploy to $1 environment using:
1. Configuration settings above
2. Current git branch: !`git branch --show-current`
3. Application version: !`cat package.json | grep version`

Execute deployment and monitor progress.
```

**使用場面:** 呼び出し間で一貫した設定が必要なコマンド

### パターン 2: テンプレートベースの生成

プラグインテンプレートを使用するコマンド:

```markdown
---
description: Generate documentation from template
argument-hint: [component-name]
---

Template: @${CLAUDE_PLUGIN_ROOT}/templates/component-docs.md

Generate documentation for $1 component following the template structure.
Include:
- Component purpose and usage
- API reference
- Examples
- Testing guidelines
```

**使用場面:** 標準化された出力の生成

### パターン 3: マルチスクリプトワークフロー

複数のプラグインスクリプトを連携させるコマンド:

```markdown
---
description: Complete build and test workflow
allowed-tools: Bash(*)
---

Build: !`bash ${CLAUDE_PLUGIN_ROOT}/scripts/build.sh`
Validate: !`bash ${CLAUDE_PLUGIN_ROOT}/scripts/validate.sh`
Test: !`bash ${CLAUDE_PLUGIN_ROOT}/scripts/test.sh`

Review all outputs and report:
1. Build status
2. Validation results
3. Test results
4. Recommended next steps
```

**使用場面:** 複数ステップを持つ複雑なプラグインワークフロー

### パターン 4: 環境対応コマンド

環境に応じて動作を変えるコマンド:

```markdown
---
description: Deploy based on environment
argument-hint: [dev|staging|prod]
---

Environment config: @${CLAUDE_PLUGIN_ROOT}/config/$1.json

Environment check: !`echo "Deploying to: $1"`

Deploy application using $1 environment configuration.
Verify deployment and run smoke tests.
```

**使用場面:** 環境ごとに動作が異なるコマンド

### パターン 5: プラグインデータ管理

プラグイン固有のデータを管理するコマンド:

```markdown
---
description: Save analysis results to plugin cache
allowed-tools: Bash(*), Read, Write
---

Cache directory: ${CLAUDE_PLUGIN_ROOT}/cache/

Analyze @$1 and save results to cache:
!`mkdir -p ${CLAUDE_PLUGIN_ROOT}/cache && date > ${CLAUDE_PLUGIN_ROOT}/cache/last-run.txt`

Store analysis for future reference and comparison.
```

**使用場面:** 永続的なデータストレージが必要なコマンド

## プラグインコンポーネントとの統合

### プラグインエージェントの呼び出し

コマンドから Task ツールを使ってプラグインエージェントをトリガーできる:

```markdown
---
description: Deep analysis using plugin agent
argument-hint: [file-path]
---

Initiate deep code analysis of @$1 using the code-analyzer agent.

The agent will:
1. Analyze code structure
2. Identify patterns
3. Suggest improvements
4. Generate detailed report

Note: This uses the Task tool to launch the plugin's code-analyzer agent.
```

**重要なポイント:**
- エージェントはプラグインの `agents/` ディレクトリに定義されている必要がある
- Claude は自動的に Task ツールを使ってエージェントを起動する
- エージェントは同じプラグインリソースにアクセスできる

### プラグインスキルの呼び出し

コマンドから専門知識のためにプラグインスキルを参照できる:

```markdown
---
description: API documentation with best practices
argument-hint: [api-file]
---

Document the API in @$1 following our API documentation standards.

Use the api-docs-standards skill to ensure documentation includes:
- Endpoint descriptions
- Parameter specifications
- Response formats
- Error codes
- Usage examples

Note: This leverages the plugin's api-docs-standards skill for consistency.
```

**重要なポイント:**
- スキルはプラグインの `skills/` ディレクトリに定義されている必要がある
- スキル名を言及して Claude にスキル呼び出しのヒントを与える
- スキルは専門的なドメイン知識を提供する

### プラグインフックとの連携

コマンドをプラグインフックと連携して設計できる:

```markdown
---
description: Commit with pre-commit validation
allowed-tools: Bash(git:*)
---

Stage changes: !\`git add $1\`

Commit changes: !\`git commit -m "$2"\`

Note: This commit will trigger the plugin's pre-commit hook for validation.
Review hook output for any issues.
```

**重要なポイント:**
- フックはイベントに応じて自動的に実行される
- コマンドはフックのための状態を準備できる
- コマンド内にフックとの連携をドキュメント化する

### マルチコンポーネントプラグインコマンド

複数のプラグインコンポーネントを連携させるコマンド:

```markdown
---
description: Comprehensive code review workflow
argument-hint: [file-path]
---

File to review: @$1

Execute comprehensive review:

1. **静的解析** (プラグインスクリプト経由)
   !`node ${CLAUDE_PLUGIN_ROOT}/scripts/lint.js $1`

2. **詳細レビュー** (プラグインエージェント経由)
   Launch the code-reviewer agent for detailed analysis.

3. **ベストプラクティス** (プラグインスキル経由)
   Use the code-standards skill to ensure compliance.

4. **ドキュメント** (プラグインテンプレート経由)
   Template: @${CLAUDE_PLUGIN_ROOT}/templates/review-report.md

Generate final report combining all outputs.
```

**使用場面:** 複数のプラグイン機能を活用する複雑なワークフロー

## バリデーションパターン

### 入力バリデーション

コマンドは処理前に入力をバリデーションすべき:

```markdown
---
description: Deploy to environment with validation
argument-hint: [environment]
---

Validate environment: !`echo "$1" | grep -E "^(dev|staging|prod)$" || echo "INVALID"`

$IF($1 in [dev, staging, prod],
  Deploy to $1 environment using validated configuration,
  ERROR: Invalid environment '$1'. Must be one of: dev, staging, prod
)
```

**バリデーションアプローチ:**
1. grep/test を使った Bash バリデーション
2. プロンプト内のインラインバリデーション
3. スクリプトベースのバリデーション

### ファイル存在チェック

必要なファイルが存在するか確認する:

```markdown
---
description: Process configuration file
argument-hint: [config-file]
---

Check file: !`test -f $1 && echo "EXISTS" || echo "MISSING"`

Process configuration if file exists: @$1

If file doesn't exist, explain:
- Expected location
- Required format
- How to create it
```

### 必須引数

必須引数が提供されているかバリデーションする:

```markdown
---
description: Create deployment with version
argument-hint: [environment] [version]
---

Validate inputs: !`test -n "$1" -a -n "$2" && echo "OK" || echo "MISSING"`

$IF($1 AND $2,
  Deploy version $2 to $1 environment,
  ERROR: Both environment and version required. Usage: /deploy [env] [version]
)
```

### プラグインリソースバリデーション

プラグインリソースが利用可能か確認する:

```markdown
---
description: Run analysis with plugin tools
allowed-tools: Bash(test:*)
---

Validate plugin setup:
- Config exists: !`test -f ${CLAUDE_PLUGIN_ROOT}/config.json && echo "✓" || echo "✗"`
- Scripts exist: !`test -d ${CLAUDE_PLUGIN_ROOT}/scripts && echo "✓" || echo "✗"`
- Tools available: !`test -x ${CLAUDE_PLUGIN_ROOT}/bin/analyze && echo "✓" || echo "✗"`

If all checks pass, proceed with analysis.
Otherwise, report missing components and installation steps.
```

### 出力バリデーション

コマンド実行結果をバリデーションする:

```markdown
---
description: Build and validate output
allowed-tools: Bash(*)
---

Build: !`bash ${CLAUDE_PLUGIN_ROOT}/scripts/build.sh`

Validate output:
- Exit code: !`echo $?`
- Output exists: !`test -d dist && echo "✓" || echo "✗"`
- File count: !`find dist -type f | wc -l`

Report build status and any validation failures.
```

### グレースフルなエラーハンドリング

ヘルプフルなメッセージでエラーを優雅に処理する:

```markdown
---
description: Process file with error handling
argument-hint: [file-path]
---

Try processing: !`node ${CLAUDE_PLUGIN_ROOT}/scripts/process.js $1 2>&1 || echo "ERROR: $?"`

If processing succeeded:
- Report results
- Suggest next steps

If processing failed:
- Explain likely causes
- Provide troubleshooting steps
- Suggest alternative approaches
```

## ベストプラクティスのまとめ

### プラグインコマンドは以下を満たすべき:

1. **プラグイン内部パスには常に ${CLAUDE_PLUGIN_ROOT} を使用する**
   - スクリプト、テンプレート、設定、リソース

2. **入力を早期にバリデーションする**
   - 必須引数のチェック
   - ファイル存在の確認
   - 引数フォーマットのバリデーション

3. **プラグイン構造をドキュメント化する**
   - 必要なファイルの説明
   - スクリプトの目的のドキュメント化
   - 依存関係の明確化

4. **プラグインコンポーネントと統合する**
   - 複雑なタスクにはエージェントを参照
   - 専門知識にはスキルを使用
   - 関連する場合はフックと連携

5. **ヘルプフルなエラーメッセージを提供する**
   - 何が問題だったかを説明
   - 修正方法を提案
   - 代替案を提示

6. **エッジケースを処理する**
   - ファイルの欠落
   - 無効な引数
   - スクリプト実行の失敗
   - 依存関係の欠落

7. **コマンドを焦点を絞って保つ**
   - 1 コマンドに 1 つの明確な目的
   - 複雑なロジックはスクリプトに委譲
   - マルチステップワークフローにはエージェントを使用

8. **インストール間でテストする**
   - パスがどこでも動作することを確認
   - 異なる引数でテスト
   - エラーケースを検証

---

一般的なコマンド開発については、メインの SKILL.md を参照。
コマンドの例については、examples/ ディレクトリを参照。
