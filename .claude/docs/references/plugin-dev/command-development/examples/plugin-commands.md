# プラグインコマンド例

Claude Codeプラグイン向けに設計されたコマンドの実践的な例。プラグイン固有のパターンと機能を示します。

## 目次

1. [シンプルなプラグインコマンド](#1-シンプルなプラグインコマンド)
2. [スクリプトベースの分析](#2-スクリプトベースの分析)
3. [テンプレートベースの生成](#3-テンプレートベースの生成)
4. [マルチスクリプトワークフロー](#4-マルチスクリプトワークフロー)
5. [設定駆動デプロイ](#5-設定駆動デプロイ)
6. [エージェント統合](#6-エージェント統合)
7. [スキル統合](#7-スキル統合)
8. [マルチコンポーネントワークフロー](#8-マルチコンポーネントワークフロー)
9. [入力バリデーション付きコマンド](#9-入力バリデーション付きコマンド)
10. [環境対応コマンド](#10-環境対応コマンド)

---

## 1. シンプルなプラグインコマンド

**ユースケース：** プラグインスクリプトを使用する基本的なコマンド

**ファイル：** `commands/analyze.md`

```markdown
---
description: Analyze code quality using plugin tools
argument-hint: [file-path]
allowed-tools: Bash(node:*), Read
---

Analyze @$1 using plugin's quality checker:

!`node ${CLAUDE_PLUGIN_ROOT}/scripts/quality-check.js $1`

Review the analysis output and provide:
1. Summary of findings
2. Priority issues to address
3. Suggested improvements
4. Code quality score interpretation
```

**主な特徴：**
- ポータブルなパスのために `${CLAUDE_PLUGIN_ROOT}` を使用
- ファイル参照とスクリプト実行を組み合わせ
- シンプルな単一目的のコマンド

---

## 2. スクリプトベースの分析

**ユースケース：** 複数のプラグインスクリプトを使用した包括的な分析の実行

**ファイル：** `commands/full-audit.md`

```markdown
---
description: Complete code audit using plugin suite
argument-hint: [directory]
allowed-tools: Bash(*)
model: sonnet
---

Running complete audit on $1:

**Security scan:**
!`bash ${CLAUDE_PLUGIN_ROOT}/scripts/security-scan.sh $1`

**Performance analysis:**
!`bash ${CLAUDE_PLUGIN_ROOT}/scripts/perf-analyze.sh $1`

**Best practices check:**
!`bash ${CLAUDE_PLUGIN_ROOT}/scripts/best-practices.sh $1`

Analyze all results and create comprehensive report including:
- Critical issues requiring immediate attention
- Performance optimization opportunities
- Security vulnerabilities and fixes
- Overall health score and recommendations
```

**主な特徴：**
- 複数のスクリプト実行
- 整理された出力セクション
- 包括的なワークフロー
- 明確なレポート構造

---

## 3. テンプレートベースの生成

**ユースケース：** プラグインテンプレートに従ったドキュメント生成

**ファイル：** `commands/gen-api-docs.md`

```markdown
---
description: Generate API documentation from template
argument-hint: [api-file]
---

Template structure: @${CLAUDE_PLUGIN_ROOT}/templates/api-documentation.md

API implementation: @$1

Generate complete API documentation following the template format above.

Ensure documentation includes:
- Endpoint descriptions with HTTP methods
- Request/response schemas
- Authentication requirements
- Error codes and handling
- Usage examples with curl commands
- Rate limiting information

Format output as markdown suitable for README or docs site.
```

**主な特徴：**
- プラグインテンプレートを使用
- テンプレートとソースファイルを組み合わせ
- 標準化された出力フォーマット
- 明確なドキュメント構造

---

## 4. マルチスクリプトワークフロー

**ユースケース：** ビルド、テスト、デプロイワークフローのオーケストレーション

**ファイル：** `commands/release.md`

```markdown
---
description: Execute complete release workflow
argument-hint: [version]
allowed-tools: Bash(*), Read
---

Executing release workflow for version $1:

**Step 1 - Pre-release validation:**
!`bash ${CLAUDE_PLUGIN_ROOT}/scripts/pre-release-check.sh $1`

**Step 2 - Build artifacts:**
!`bash ${CLAUDE_PLUGIN_ROOT}/scripts/build-release.sh $1`

**Step 3 - Run test suite:**
!`bash ${CLAUDE_PLUGIN_ROOT}/scripts/run-tests.sh`

**Step 4 - Package release:**
!`bash ${CLAUDE_PLUGIN_ROOT}/scripts/package.sh $1`

Review all step outputs and report:
1. Any failures or warnings
2. Build artifacts location
3. Test results summary
4. Next steps for deployment
5. Rollback plan if needed
```

**主な特徴：**
- マルチステップワークフロー
- 順次スクリプト実行
- 明確なステップ番号付け
- 包括的なレポーティング

---

## 5. 設定駆動デプロイ

**ユースケース：** 環境固有のプラグイン設定を使用したデプロイ

**ファイル：** `commands/deploy.md`

```markdown
---
description: Deploy application to environment
argument-hint: [environment]
allowed-tools: Read, Bash(*)
---

Deployment configuration for $1: @${CLAUDE_PLUGIN_ROOT}/config/$1-deploy.json

Current git state: !`git rev-parse --short HEAD`

Build info: !`cat package.json | grep -E '(name|version)'`

Execute deployment to $1 environment using configuration above.

Deployment checklist:
1. Validate configuration settings
2. Build application for $1
3. Run pre-deployment tests
4. Deploy to target environment
5. Run smoke tests
6. Verify deployment success
7. Update deployment log

Report deployment status and any issues encountered.
```

**主な特徴：**
- 環境固有の設定
- 動的な設定ファイル読み込み
- デプロイ前のバリデーション
- 構造化されたチェックリスト

---

## 6. エージェント統合

**ユースケース：** 複雑なタスクのためにプラグインエージェントを起動するコマンド

**ファイル：** `commands/deep-review.md`

```markdown
---
description: Deep code review using plugin agent
argument-hint: [file-or-directory]
---

Initiate comprehensive code review of @$1 using the code-reviewer agent.

The agent will perform:
1. **Static analysis** - Check for code smells and anti-patterns
2. **Security audit** - Identify potential vulnerabilities
3. **Performance review** - Find optimization opportunities
4. **Best practices** - Ensure code follows standards
5. **Documentation check** - Verify adequate documentation

The agent has access to:
- Plugin's linting rules: ${CLAUDE_PLUGIN_ROOT}/config/lint-rules.json
- Security checklist: ${CLAUDE_PLUGIN_ROOT}/checklists/security.md
- Performance guidelines: ${CLAUDE_PLUGIN_ROOT}/docs/performance.md

Note: This uses the Task tool to launch the plugin's code-reviewer agent for thorough analysis.
```

**主な特徴：**
- プラグインエージェントに委譲
- エージェントの機能を文書化
- プラグインリソースを参照
- 明確なスコープ定義

---

## 7. スキル統合

**ユースケース：** 専門知識のためにプラグインスキルを活用するコマンド

**ファイル：** `commands/document-api.md`

```markdown
---
description: Document API following plugin standards
argument-hint: [api-file]
---

API source code: @$1

Generate API documentation following the plugin's API documentation standards.

Use the api-documentation-standards skill to ensure:
- **OpenAPI compliance** - Follow OpenAPI 3.0 specification
- **Consistent formatting** - Use plugin's documentation style
- **Complete coverage** - Document all endpoints and schemas
- **Example quality** - Provide realistic usage examples
- **Error documentation** - Cover all error scenarios

The skill provides:
- Standard documentation templates
- API documentation best practices
- Common patterns for this codebase
- Quality validation criteria

Generate production-ready API documentation.
```

**主な特徴：**
- 名前でプラグインスキルを呼び出し
- スキルの目的を文書化
- 明確な期待値
- スキルの知識を活用

---

## 8. マルチコンポーネントワークフロー

**ユースケース：** エージェント、スキル、スクリプトを使用する複合ワークフロー

**ファイル：** `commands/complete-review.md`

```markdown
---
description: Comprehensive review using all plugin components
argument-hint: [file-path]
allowed-tools: Bash(node:*), Read
---

Target file: @$1

Execute comprehensive review workflow:

**Phase 1: Automated Analysis**
Run plugin analyzer: !`node ${CLAUDE_PLUGIN_ROOT}/scripts/analyze.js $1`

**Phase 2: Deep Review (Agent)**
Launch the code-quality-reviewer agent for detailed analysis.
Agent will examine:
- Code structure and organization
- Error handling patterns
- Testing coverage
- Documentation quality

**Phase 3: Standards Check (Skill)**
Use the coding-standards skill to validate:
- Naming conventions
- Code formatting
- Best practices adherence
- Framework-specific patterns

**Phase 4: Report Generation**
Template: @${CLAUDE_PLUGIN_ROOT}/templates/review-report.md

Compile all findings into comprehensive report following template.

**Phase 5: Recommendations**
Generate prioritized action items:
1. Critical issues (must fix)
2. Important improvements (should fix)
3. Nice-to-have enhancements (could fix)

Include specific file locations and suggested changes for each item.
```

**主な特徴：**
- マルチフェーズワークフロー
- スクリプト、エージェント、スキルを組み合わせ
- テンプレートベースのレポーティング
- 優先順位付きの出力

---

## 9. 入力バリデーション付きコマンド

**ユースケース：** 入力バリデーションとエラーハンドリング付きのコマンド

**ファイル：** `commands/build-env.md`

```markdown
---
description: Build for specific environment with validation
argument-hint: [environment]
allowed-tools: Bash(*)
---

Validate environment argument: !`echo "$1" | grep -E "^(dev|staging|prod)$" && echo "VALID" || echo "INVALID"`

Check build script exists: !`test -x ${CLAUDE_PLUGIN_ROOT}/scripts/build.sh && echo "EXISTS" || echo "MISSING"`

Verify configuration available: !`test -f ${CLAUDE_PLUGIN_ROOT}/config/$1.json && echo "FOUND" || echo "NOT_FOUND"`

If all validations pass:

**Configuration:** @${CLAUDE_PLUGIN_ROOT}/config/$1.json

**Execute build:** !`bash ${CLAUDE_PLUGIN_ROOT}/scripts/build.sh $1 2>&1`

**Validation results:** !`bash ${CLAUDE_PLUGIN_ROOT}/scripts/validate-build.sh $1 2>&1`

Report build status and any issues.

If validations fail:
- Explain which validation failed
- Provide expected values/locations
- Suggest corrective actions
- Document troubleshooting steps
```

**主な特徴：**
- 入力バリデーション
- リソース存在チェック
- エラーハンドリング
- 有用なエラーメッセージ
- グレースフルな失敗処理

---

## 10. 環境対応コマンド

**ユースケース：** 環境に基づいて動作を適応させるコマンド

**ファイル：** `commands/run-checks.md`

```markdown
---
description: Run environment-appropriate checks
argument-hint: [environment]
allowed-tools: Bash(*), Read
---

Environment: $1

Load environment configuration: @${CLAUDE_PLUGIN_ROOT}/config/$1-checks.json

Determine check level: !`echo "$1" | grep -E "^prod$" && echo "FULL" || echo "BASIC"`

**For production environment:**
- Full test suite: !`bash ${CLAUDE_PLUGIN_ROOT}/scripts/test-full.sh`
- Security scan: !`bash ${CLAUDE_PLUGIN_ROOT}/scripts/security-scan.sh`
- Performance audit: !`bash ${CLAUDE_PLUGIN_ROOT}/scripts/perf-check.sh`
- Compliance check: !`bash ${CLAUDE_PLUGIN_ROOT}/scripts/compliance.sh`

**For non-production environments:**
- Basic tests: !`bash ${CLAUDE_PLUGIN_ROOT}/scripts/test-basic.sh`
- Quick lint: !`bash ${CLAUDE_PLUGIN_ROOT}/scripts/lint.sh`

Analyze results based on environment requirements:

**Production:** All checks must pass with zero critical issues
**Staging:** No critical issues, warnings acceptable
**Development:** Focus on blocking issues only

Report status and recommend proceed/block decision.
```

**主な特徴：**
- 環境対応ロジック
- 条件付き実行
- 異なるバリデーションレベル
- 環境ごとの適切なレポーティング

---

## 共通パターンまとめ

### パターン：プラグインスクリプト実行
```markdown
!`node ${CLAUDE_PLUGIN_ROOT}/scripts/script-name.js $1`
```
用途：プラグイン提供のNode.jsスクリプトの実行

### パターン：プラグイン設定の読み込み
```markdown
@${CLAUDE_PLUGIN_ROOT}/config/config-name.json
```
用途：プラグイン設定ファイルの読み込み

### パターン：プラグインテンプレートの使用
```markdown
@${CLAUDE_PLUGIN_ROOT}/templates/template-name.md
```
用途：生成用のプラグインテンプレートの使用

### パターン：エージェント呼び出し
```markdown
Launch the [agent-name] agent for [task description].
```
用途：複雑なタスクのプラグインエージェントへの委譲

### パターン：スキル参照
```markdown
Use the [skill-name] skill to ensure [requirements].
```
用途：専門知識のためのプラグインスキルの活用

### パターン：入力バリデーション
```markdown
Validate input: !`echo "$1" | grep -E "^pattern$" && echo "OK" || echo "ERROR"`
```
用途：コマンド引数のバリデーション

### パターン：リソースバリデーション
```markdown
Check exists: !`test -f ${CLAUDE_PLUGIN_ROOT}/path/file && echo "YES" || echo "NO"`
```
用途：必要なプラグインファイルの存在確認

---

## 開発のヒント

### プラグインコマンドのテスト

1. **プラグインインストール済みの状態でテスト：**
   ```bash
   cd /path/to/plugin
   claude /command-name args
   ```

2. **${CLAUDE_PLUGIN_ROOT} の展開を確認：**
   ```bash
   # コマンドにデバッグ出力を追加
   !`echo "Plugin root: ${CLAUDE_PLUGIN_ROOT}"`
   ```

3. **異なる作業ディレクトリでテスト：**
   ```bash
   cd /tmp && claude /command-name
   cd /other/project && claude /command-name
   ```

4. **リソースの利用可能性を確認：**
   ```bash
   # すべてのプラグインリソースが存在するか確認
   !`ls -la ${CLAUDE_PLUGIN_ROOT}/scripts/`
   !`ls -la ${CLAUDE_PLUGIN_ROOT}/config/`
   ```

### 避けるべきよくある間違い

1. **${CLAUDE_PLUGIN_ROOT} の代わりに相対パスを使用する：**
   ```markdown
   # 間違い
   !`node ./scripts/analyze.js`

   # 正しい
   !`node ${CLAUDE_PLUGIN_ROOT}/scripts/analyze.js`
   ```

2. **必要なツールの許可を忘れる：**
   ```markdown
   # allowed-tools が不足
   !`bash script.sh`  # Bash権限なしでは失敗する

   # 正しい
   ---
   allowed-tools: Bash(*)
   ---
   !`bash ${CLAUDE_PLUGIN_ROOT}/scripts/script.sh`
   ```

3. **入力をバリデーションしない：**
   ```markdown
   # リスクあり - バリデーションなし
   Deploy to $1 environment

   # より良い - バリデーションあり
   Validate: !`echo "$1" | grep -E "^(dev|staging|prod)$" || echo "INVALID"`
   Deploy to $1 environment (if valid)
   ```

4. **プラグインパスをハードコードする：**
   ```markdown
   # 間違い - 異なるインストール先で動作しない
   @/home/user/.claude/plugins/my-plugin/config.json

   # 正しい - どこでも動作する
   @${CLAUDE_PLUGIN_ROOT}/config.json
   ```

---

プラグイン固有の機能の詳細は `references/plugin-features-reference.md` を参照してください。
一般的なコマンド開発については、メインの `SKILL.md` を参照してください。
