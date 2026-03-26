# シンプルなコマンド例

一般的なユースケース向けの基本的なスラッシュコマンドパターン。

**重要：** 以下のすべての例はClaude（エージェント）向けの指示として書かれており、ユーザーへのメッセージではありません。コマンドはClaudeに何をすべきかを伝えるものであり、ユーザーに何が起こるかを伝えるものではありません。

## 例1：コードレビューコマンド

**ファイル：** `.claude/commands/review.md`

```markdown
---
description: Review code for quality and issues
allowed-tools: Read, Bash(git:*)
---

Review the code in this repository for:

1. **Code Quality:**
   - Readability and maintainability
   - Consistent style and formatting
   - Appropriate abstraction levels

2. **Potential Issues:**
   - Logic errors or bugs
   - Edge cases not handled
   - Performance concerns

3. **Best Practices:**
   - Design patterns used correctly
   - Error handling present
   - Documentation adequate

Provide specific feedback with file and line references.
```

**使い方：**
```
> /review
```

---

## 例2：セキュリティレビューコマンド

**ファイル：** `.claude/commands/security-review.md`

```markdown
---
description: Review code for security vulnerabilities
allowed-tools: Read, Grep
model: sonnet
---

Perform comprehensive security review checking for:

**Common Vulnerabilities:**
- SQL injection risks
- Cross-site scripting (XSS)
- Authentication/authorization issues
- Insecure data handling
- Hardcoded secrets or credentials

**Security Best Practices:**
- Input validation present
- Output encoding correct
- Secure defaults used
- Error messages safe
- Logging appropriate (no sensitive data)

For each issue found:
- File and line number
- Severity (Critical/High/Medium/Low)
- Description of vulnerability
- Recommended fix

Prioritize issues by severity.
```

**使い方：**
```
> /security-review
```

---

## 例3：ファイル引数付きテストコマンド

**ファイル：** `.claude/commands/test-file.md`

```markdown
---
description: Run tests for specific file
argument-hint: [test-file]
allowed-tools: Bash(npm:*), Bash(jest:*)
---

Run tests for $1:

Test execution: !`npm test $1`

Analyze results:
- Tests passed/failed
- Code coverage
- Performance issues
- Flaky tests

If failures found, suggest fixes based on error messages.
```

**使い方：**
```
> /test-file src/utils/helpers.test.ts
```

---

## 例4：ドキュメント生成

**ファイル：** `.claude/commands/document.md`

```markdown
---
description: Generate documentation for file
argument-hint: [source-file]
---

Generate comprehensive documentation for @$1

Include:

**Overview:**
- Purpose and responsibility
- Main functionality
- Dependencies

**API Documentation:**
- Function/method signatures
- Parameter descriptions with types
- Return values with types
- Exceptions/errors thrown

**Usage Examples:**
- Basic usage
- Common patterns
- Edge cases

**Implementation Notes:**
- Algorithm complexity
- Performance considerations
- Known limitations

Format as Markdown suitable for project documentation.
```

**使い方：**
```
> /document src/api/users.ts
```

---

## 例5：Gitステータスサマリー

**ファイル：** `.claude/commands/git-status.md`

```markdown
---
description: Summarize Git repository status
allowed-tools: Bash(git:*)
---

Repository Status Summary:

**Current Branch:** !`git branch --show-current`

**Status:** !`git status --short`

**Recent Commits:** !`git log --oneline -5`

**Remote Status:** !`git fetch && git status -sb`

Provide:
- Summary of changes
- Suggested next actions
- Any warnings or issues
```

**使い方：**
```
> /git-status
```

---

## 例6：デプロイコマンド

**ファイル：** `.claude/commands/deploy.md`

```markdown
---
description: Deploy to specified environment
argument-hint: [environment] [version]
allowed-tools: Bash(kubectl:*), Read
---

Deploy to $1 environment using version $2

**Pre-deployment Checks:**
1. Verify $1 configuration exists
2. Check version $2 is valid
3. Verify cluster accessibility: !`kubectl cluster-info`

**Deployment Steps:**
1. Update deployment manifest with version $2
2. Apply configuration to $1
3. Monitor rollout status
4. Verify pod health
5. Run smoke tests

**Rollback Plan:**
Document current version for rollback if issues occur.

Proceed with deployment? (yes/no)
```

**使い方：**
```
> /deploy staging v1.2.3
```

---

## 例7：比較コマンド

**ファイル：** `.claude/commands/compare-files.md`

```markdown
---
description: Compare two files
argument-hint: [file1] [file2]
---

Compare @$1 with @$2

**Analysis:**

1. **Differences:**
   - Lines added
   - Lines removed
   - Lines modified

2. **Functional Changes:**
   - Breaking changes
   - New features
   - Bug fixes
   - Refactoring

3. **Impact:**
   - Affected components
   - Required updates elsewhere
   - Migration requirements

4. **Recommendations:**
   - Code review focus areas
   - Testing requirements
   - Documentation updates needed

Present as structured comparison report.
```

**使い方：**
```
> /compare-files src/old-api.ts src/new-api.ts
```

---

## 例8：クイックフィックスコマンド

**ファイル：** `.claude/commands/quick-fix.md`

```markdown
---
description: Quick fix for common issues
argument-hint: [issue-description]
model: haiku
---

Quickly fix: $ARGUMENTS

**Approach:**
1. Identify the issue
2. Find relevant code
3. Propose fix
4. Explain solution

Focus on:
- Simple, direct solution
- Minimal changes
- Following existing patterns
- No breaking changes

Provide code changes with file paths and line numbers.
```

**使い方：**
```
> /quick-fix button not responding to clicks
> /quick-fix typo in error message
```

---

## 例9：リサーチコマンド

**ファイル：** `.claude/commands/research.md`

```markdown
---
description: Research best practices for topic
argument-hint: [topic]
model: sonnet
---

Research best practices for: $ARGUMENTS

**Coverage:**

1. **Current State:**
   - How we currently handle this
   - Existing implementations

2. **Industry Standards:**
   - Common patterns
   - Recommended approaches
   - Tools and libraries

3. **Comparison:**
   - Our approach vs standards
   - Gaps or improvements needed
   - Migration considerations

4. **Recommendations:**
   - Concrete action items
   - Priority and effort estimates
   - Resources for implementation

Provide actionable guidance based on research.
```

**使い方：**
```
> /research error handling in async operations
> /research API authentication patterns
```

---

## 例10：コード解説コマンド

**ファイル：** `.claude/commands/explain.md`

```markdown
---
description: Explain how code works
argument-hint: [file-or-function]
---

Explain @$1 in detail

**Explanation Structure:**

1. **Overview:**
   - What it does
   - Why it exists
   - How it fits in system

2. **Step-by-Step:**
   - Line-by-line walkthrough
   - Key algorithms or logic
   - Important details

3. **Inputs and Outputs:**
   - Parameters and types
   - Return values
   - Side effects

4. **Edge Cases:**
   - Error handling
   - Special cases
   - Limitations

5. **Usage Examples:**
   - How to call it
   - Common patterns
   - Integration points

Explain at level appropriate for junior engineer.
```

**使い方：**
```
> /explain src/utils/cache.ts
> /explain AuthService.login
```

---

## 主要パターン

### パターン1：読み取り専用分析

```markdown
---
allowed-tools: Read, Grep
---

Analyze but don't modify...
```

**用途：** コードレビュー、ドキュメント、分析

### パターン2：Git操作

```markdown
---
allowed-tools: Bash(git:*)
---

!`git status`
Analyze and suggest...
```

**用途：** リポジトリステータス、コミット分析

### パターン3：単一引数

```markdown
---
argument-hint: [target]
---

Process $1...
```

**用途：** ファイル操作、対象を絞ったアクション

### パターン4：複数引数

```markdown
---
argument-hint: [source] [target] [options]
---

Process $1 to $2 with $3...
```

**用途：** ワークフロー、デプロイ、比較

### パターン5：高速実行

```markdown
---
model: haiku
---

Quick simple task...
```

**用途：** シンプルで繰り返しのコマンド

### パターン6：ファイル比較

```markdown
Compare @$1 with @$2...
```

**用途：** 差分分析、マイグレーション計画

### パターン7：コンテキスト収集

```markdown
---
allowed-tools: Bash(git:*), Read
---

Context: !`git status`
Files: @file1 @file2

Analyze...
```

**用途：** 情報に基づいた意思決定

## シンプルなコマンドを書くためのヒント

1. **基本から始める：** 単一責務、明確な目的
2. **段階的に複雑さを追加：** フロントマターなしから始める
3. **段階的にテスト：** 各機能が動作することを確認
4. **わかりやすい名前：** コマンド名で目的がわかるようにする
5. **引数を文書化：** 常にargument-hintを使用する
6. **例を提供：** コメントに使い方を記載する
7. **エラーを処理：** 引数やファイルの欠落を考慮する
