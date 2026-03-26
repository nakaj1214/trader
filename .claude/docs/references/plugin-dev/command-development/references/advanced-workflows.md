# 高度なワークフローパターン

複雑なワークフローのためのマルチステップコマンドシーケンスと構成パターン。

## 概要

高度なワークフローは複数のコマンドを組み合わせ、呼び出し間の状態を調整し、洗練された自動化シーケンスを作成する。これらのパターンにより、シンプルなコマンドの構成要素から複雑な機能を構築できる。

## マルチステップコマンドパターン

### シーケンシャルワークフローコマンド

マルチステッププロセスを通じてユーザーをガイドするコマンド:

```markdown
---
description: Complete PR review workflow
argument-hint: [pr-number]
allowed-tools: Bash(gh:*), Read, Grep
---

# PR Review Workflow for #$1

## Step 1: Fetch PR Details
!`gh pr view $1 --json title,body,author,files`

## Step 2: Review Files
Files changed: !`gh pr diff $1 --name-only`

For each file:
- Check code quality
- Verify tests exist
- Review documentation

## Step 3: Run Checks
Test status: !`gh pr checks $1`

Verify:
- All tests passing
- No merge conflicts
- CI/CD successful

## Step 4: Provide Feedback

Summarize:
- Issues found (critical/minor)
- Suggestions for improvement
- Approval recommendation

Would you like to:
1. Approve PR
2. Request changes
3. Leave comments only

Reply with your choice and I'll help complete the action.
```

**主な特徴:**
- 番号付きステップで明確さを確保
- コンテキストのための Bash 実行
- ユーザー入力のための判断ポイント
- 次のアクションの提案

### 状態保持ワークフロー

呼び出し間で状態を維持するコマンド:

```markdown
---
description: Initialize deployment workflow
allowed-tools: Write, Bash(git:*)
---

# Initialize Deployment

Creating deployment tracking file...

Current branch: !`git branch --show-current`
Latest commit: !`git log -1 --format=%H`

Deployment state saved to `.claude/deployment-state.local.md`:

\`\`\`markdown
---
initialized: true
branch: $(git branch --show-current)
commit: $(git log -1 --format=%H)
timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)
status: initialized
---

# Deployment Tracking

Branch: $(git branch --show-current)
Started: $(date)

Next steps:
1. Run tests: /deploy-test
2. Build: /deploy-build
3. Deploy: /deploy-execute
\`\`\`

State saved. Run `/deploy-test` to continue.
```

**次のコマンド** (`/deploy-test`):
```markdown
---
description: Run deployment tests
allowed-tools: Read, Bash(npm:*)
---

Reading deployment state from `.claude/deployment-state.local.md`...

Running tests: !`npm test`

Updating state to 'tested'...

Tests complete. Run `/deploy-build` to continue.
```

**パターンの利点:**
- コマンド間での永続的な状態
- 明確なワークフロー進行
- 安全なチェックポイント
- 再開機能

### 条件分岐ワークフロー

条件に基づいて適応するコマンド:

```markdown
---
description: Smart deployment workflow
argument-hint: [environment]
allowed-tools: Bash(git:*), Bash(npm:*), Read
---

# Deploy to $1

## Pre-flight Checks

Branch: !`git branch --show-current`
Status: !`git status --short`

**Checking conditions:**

1. Branch status:
   - If main/master: Require approval
   - If feature branch: Warning about target
   - If hotfix: Fast-track process

2. Tests:
   !`npm test`
   - If tests fail: STOP - fix tests first
   - If tests pass: Continue

3. Environment:
   - If $1 = 'production': Extra validation
   - If $1 = 'staging': Standard process
   - If $1 = 'dev': Minimal checks

**Workflow decision:**
Based on above, proceeding with: [determined workflow]

[Conditional steps based on environment and status]

Ready to deploy? (yes/no)
```

## コマンド構成パターン

### コマンドチェーン

連携して動作するように設計されたコマンド:

```markdown
---
description: Prepare for code review
---

# Prepare Code Review

Running preparation sequence:

1. Format code: /format-code
2. Run linter: /lint-code
3. Run tests: /test-all
4. Generate coverage: /coverage-report
5. Create review summary: /review-summary

This is a meta-command. After completing each step above,
I'll compile results and prepare comprehensive review materials.

Starting sequence...
```

**個別のコマンド** はシンプル:
- `/format-code` - フォーマットのみ
- `/lint-code` - リントのみ
- `/test-all` - テストのみ

**構成コマンド** がそれらを統合する。

### パイプラインパターン

前のコマンドの出力を処理するコマンド:

```markdown
---
description: Analyze test failures
---

# Analyze Test Failures

## Step 1: Get test results
(Run /test-all first if not done)

Reading test output...

## Step 2: Categorize failures
- Flaky tests (random failures)
- Consistent failures
- New failures vs existing

## Step 3: Prioritize
Rank by:
- Impact (critical path vs edge case)
- Frequency (always fails vs sometimes)
- Effort (quick fix vs major work)

## Step 4: Generate fix plan
For each failure:
- Root cause hypothesis
- Suggested fix approach
- Estimated effort

Would you like me to:
1. Fix highest priority failure
2. Generate detailed fix plans for all
3. Create GitHub issues for each
```

### 並列実行パターン

複数の同時操作を調整するコマンド:

```markdown
---
description: Run comprehensive validation
allowed-tools: Bash(*), Read
---

# Comprehensive Validation

Running validations in parallel...

Starting:
- Code quality checks
- Security scanning
- Dependency audit
- Performance profiling

This will take 2-3 minutes. I'll monitor all processes
and report when complete.

[Poll each process and report progress]

All validations complete. Summary:
- Quality: PASS (0 issues)
- Security: WARN (2 minor issues)
- Dependencies: PASS
- Performance: PASS (baseline met)

Details:
[Collated results from all checks]
```

## ワークフロー状態管理

### .local.md ファイルの使用

プラグイン固有のファイルにワークフロー状態を保存する:

```markdown
.claude/plugin-name-workflow.local.md:

---
workflow: deployment
stage: testing
started: 2025-01-15T10:30:00Z
environment: staging
branch: feature/new-api
commit: abc123def
tests_passed: false
build_complete: false
---

# Deployment Workflow State

Current stage: Testing
Started: 2025-01-15 10:30 UTC

Completed steps:
- ✅ Validation
- ✅ Branch check
- ⏳ Testing (in progress)

Pending steps:
- Build
- Deploy
- Smoke tests
```

**コマンドで状態を読み取る:**

```markdown
---
description: Continue deployment workflow
allowed-tools: Read, Write
---

Reading workflow state from .claude/plugin-name-workflow.local.md...

Current stage: @.claude/plugin-name-workflow.local.md

[Parse YAML frontmatter to determine next step]

Next action based on state: [determined action]
```

### ワークフロー復旧

中断されたワークフローを処理する:

```markdown
---
description: Resume deployment workflow
allowed-tools: Read
---

# Resume Deployment

Checking for interrupted workflow...

State file: @.claude/plugin-name-workflow.local.md

**Workflow found:**
- Started: [timestamp]
- Environment: [env]
- Last completed: [step]

**Recovery options:**
1. Resume from last step
2. Restart from beginning
3. Abort and clean up

Which would you like? (1/2/3)
```

## ワークフロー調整パターン

### コマンド間通信

相互にシグナルを送るコマンド:

```markdown
---
description: Mark feature complete
allowed-tools: Write
---

# Mark Feature Complete

Writing completion marker...

Creating: .claude/feature-complete.flag

This signals other commands that feature is ready for:
- Integration testing (/integration-test will auto-detect)
- Documentation generation (/docs-generate will include)
- Release notes (/release-notes will add)

Feature marked complete.
```

**他のコマンドがフラグをチェックする:**

```markdown
---
description: Generate release notes
allowed-tools: Read, Bash(git:*)
---

Checking for completed features...

if [ -f .claude/feature-complete.flag ]; then
  Feature ready for release notes
fi

[Include in release notes]
```

### ワークフローロック

ワークフローの同時実行を防止する:

```markdown
---
description: Start deployment
allowed-tools: Read, Write, Bash
---

# Start Deployment

Checking for active deployments...

if [ -f .claude/deployment.lock ]; then
  ERROR: Deployment already in progress
  Started: [timestamp from lock file]

  Cannot start concurrent deployment.
  Wait for completion or run /deployment-abort

  Exit.
fi

Creating deployment lock...

Deployment started. Lock created.
[Proceed with deployment]
```

**ロックのクリーンアップ:**

```markdown
---
description: Complete deployment
allowed-tools: Write, Bash
---

Deployment complete.

Removing deployment lock...
rm .claude/deployment.lock

Ready for next deployment.
```

## 高度な引数処理

### デフォルト付きオプション引数

```markdown
---
description: Deploy with optional version
argument-hint: [environment] [version]
---

Environment: ${1:-staging}
Version: ${2:-latest}

Deploying ${2:-latest} to ${1:-staging}...

Note: Using defaults for missing arguments:
- Environment defaults to 'staging'
- Version defaults to 'latest'
```

### 引数バリデーション

```markdown
---
description: Deploy to validated environment
argument-hint: [environment]
---

Environment: $1

Validating environment...

valid_envs="dev staging production"
if ! echo "$valid_envs" | grep -w "$1" > /dev/null; then
  ERROR: Invalid environment '$1'
  Valid options: dev, staging, production
  Exit.
fi

Environment validated. Proceeding...
```

### 引数変換

```markdown
---
description: Deploy with shorthand
argument-hint: [env-shorthand]
---

Input: $1

Expanding shorthand:
- d/dev → development
- s/stg → staging
- p/prod → production

case "$1" in
  d|dev) ENV="development";;
  s|stg) ENV="staging";;
  p|prod) ENV="production";;
  *) ENV="$1";;
esac

Deploying to: $ENV
```

## ワークフローのエラーハンドリング

### グレースフルフェイルオーバー

```markdown
---
description: Resilient deployment workflow
---

# Deployment Workflow

Running steps with error handling...

## Step 1: Tests
!`npm test`

if [ $? -ne 0 ]; then
  ERROR: Tests failed

  Options:
  1. Fix tests and retry
  2. Skip tests (NOT recommended)
  3. Abort deployment

  What would you like to do?

  [Wait for user input before continuing]
fi

## Step 2: Build
[Continue only if Step 1 succeeded]
```

### 失敗時のロールバック

```markdown
---
description: Deployment with rollback
---

# Deploy with Rollback

Saving current state for rollback...
Previous version: !`current-version.sh`

Deploying new version...

!`deploy.sh`

if [ $? -ne 0 ]; then
  DEPLOYMENT FAILED

  Initiating automatic rollback...
  !`rollback.sh`

  Rolled back to previous version.
  Check logs for failure details.
fi

Deployment complete.
```

### チェックポイント復旧

```markdown
---
description: Workflow with checkpoints
---

# Multi-Stage Deployment

## Checkpoint 1: Validation
!`validate.sh`
echo "checkpoint:validation" >> .claude/deployment-checkpoints.log

## Checkpoint 2: Build
!`build.sh`
echo "checkpoint:build" >> .claude/deployment-checkpoints.log

## Checkpoint 3: Deploy
!`deploy.sh`
echo "checkpoint:deploy" >> .claude/deployment-checkpoints.log

If any step fails, resume with:
/deployment-resume [last-successful-checkpoint]
```

## ベストプラクティス

### ワークフロー設計

1. **明確な進行:** ステップに番号を付け、現在の位置を表示
2. **明示的な状態:** 暗黙の状態に依存しない
3. **ユーザーコントロール:** 判断ポイントを提供
4. **エラー復旧:** 失敗を優雅に処理
5. **進捗表示:** 完了済みと保留中を表示

### コマンド構成

1. **単一責任:** 各コマンドは1つのことをうまく行う
2. **構成可能な設計:** コマンドが容易に連携
3. **標準インターフェース:** 一貫した入出力フォーマット
4. **疎結合:** コマンドが互いの内部に依存しない

### 状態管理

1. **永続的な状態:** .local.md ファイルを使用
2. **アトミック更新:** 完全な状態ファイルをアトミックに書き込む
3. **状態バリデーション:** 状態ファイルのフォーマット/完全性をチェック
4. **クリーンアップ:** 古い状態ファイルを削除
5. **ドキュメント化:** 状態ファイルフォーマットをドキュメント化

### エラーハンドリング

1. **早期失敗:** エラーを早期に検出
2. **明確なメッセージ:** 何が問題だったか説明
3. **復旧オプション:** 明確な次のステップを提供
4. **状態の保持:** 復旧のために状態を保持
5. **ロールバック機能:** 変更の取り消しをサポート

## 例: 完全なデプロイメントワークフロー

### 初期化コマンド

```markdown
---
description: Initialize deployment
argument-hint: [environment]
allowed-tools: Write, Bash(git:*)
---

# Initialize Deployment to $1

Creating workflow state...

\`\`\`yaml
---
workflow: deployment
environment: $1
branch: !`git branch --show-current`
commit: !`git rev-parse HEAD`
stage: initialized
timestamp: !`date -u +%Y-%m-%dT%H:%M:%SZ`
---
\`\`\`

Written to .claude/deployment-state.local.md

Next: Run /deployment-validate
```

### バリデーションコマンド

```markdown
---
description: Validate deployment
allowed-tools: Read, Bash
---

Reading state: @.claude/deployment-state.local.md

Running validation...
- Branch check: PASS
- Tests: PASS
- Build: PASS

Updating state to 'validated'...

Next: Run /deployment-execute
```

### 実行コマンド

```markdown
---
description: Execute deployment
allowed-tools: Read, Bash, Write
---

Reading state: @.claude/deployment-state.local.md

Executing deployment to [environment]...

!`deploy.sh [environment]`

Deployment complete.
Updating state to 'completed'...

Cleanup: /deployment-cleanup
```

### クリーンアップコマンド

```markdown
---
description: Clean up deployment
allowed-tools: Bash
---

Removing deployment state...
rm .claude/deployment-state.local.md

Deployment workflow complete.
```

この完全なワークフローは、状態管理、シーケンシャル実行、エラーハンドリング、および複数コマンド間での明確な関心の分離を示している。
