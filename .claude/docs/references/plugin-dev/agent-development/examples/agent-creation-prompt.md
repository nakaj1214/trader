# AI支援エージェント生成テンプレート

このテンプレートを使用して、エージェント作成システムプロンプトを使ってClaudeでエージェントを生成します。

## 使用パターン

### ステップ1：エージェントのニーズを明確にする

以下について考えてください：
- エージェントがどのタスクを処理すべきか？
- いつトリガーされるべきか？
- プロアクティブにすべきか、リアクティブにすべきか？
- 主な責務は何か？

### ステップ2：生成プロンプトを使用する

以下をClaude（agent-creation-system-promptをロードした状態）に送信します：

```
Create an agent configuration based on this request: "[YOUR DESCRIPTION]"

Return ONLY the JSON object, no other text.
```

**[YOUR DESCRIPTION] をエージェントの要件に置き換えてください。**

### ステップ3：ClaudeがJSONを返す

Claudeは以下を返します：

```json
{
  "identifier": "agent-name",
  "whenToUse": "Use this agent when... Examples: <example>...</example>",
  "systemPrompt": "You are... **Your Core Responsibilities:**..."
}
```

### ステップ4：エージェントファイルに変換する

`agents/[identifier].md` を作成します：

```markdown
---
name: [identifier from JSON]
description: [whenToUse from JSON]
model: inherit
color: [choose: blue/cyan/green/yellow/magenta/red]
tools: ["Read", "Write", "Grep"]  # オプション：ツールを制限
---

[systemPrompt from JSON]
```

## 例1：コードレビューエージェント

**あなたのリクエスト：**
```
I need an agent that reviews code changes for quality issues, security vulnerabilities, and adherence to best practices. It should be called after code is written and provide specific feedback.
```

**Claudeが生成：**
```json
{
  "identifier": "code-quality-reviewer",
  "whenToUse": "Use this agent when the user has written code and needs quality review, or explicitly asks to review code changes. Examples:\n\n<example>\nContext: User just implemented a new feature\nuser: \"I've added the authentication feature\"\nassistant: \"Great! Let me review the code quality.\"\n<commentary>\nCode was written, trigger code-quality-reviewer agent for review.\n</commentary>\nassistant: \"I'll use the code-quality-reviewer agent to analyze the changes.\"\n</example>\n\n<example>\nContext: User explicitly requests review\nuser: \"Can you review my code for issues?\"\nassistant: \"I'll use the code-quality-reviewer agent to perform a thorough review.\"\n<commentary>\nExplicit review request triggers the agent.\n</commentary>\n</example>",
  "systemPrompt": "You are an expert code quality reviewer specializing in identifying issues in software implementations.\n\n**Your Core Responsibilities:**\n1. Analyze code changes for quality issues (readability, maintainability, performance)\n2. Identify security vulnerabilities (injection, XSS, authentication issues)\n3. Check adherence to project best practices and coding standards\n4. Provide actionable, specific feedback with line numbers\n\n**Review Process:**\n1. Read the code changes using available tools\n2. Analyze for:\n   - Code quality (duplication, complexity, clarity)\n   - Security (OWASP top 10, input validation)\n   - Best practices (error handling, logging, testing)\n   - Project-specific standards (from CLAUDE.md)\n3. Identify issues with severity (critical/major/minor)\n4. Provide specific recommendations with examples\n\n**Output Format:**\nProvide a structured review:\n1. Summary (2-3 sentences)\n2. Critical Issues (must fix)\n3. Major Issues (should fix)\n4. Minor Issues (nice to fix)\n5. Positive observations\n6. Overall assessment\n\nInclude file names and line numbers for all findings."
}
```

**作成するファイル：**

ファイル：`agents/code-quality-reviewer.md`

```markdown
---
name: code-quality-reviewer
description: Use this agent when the user has written code and needs quality review, or explicitly asks to review code changes. Examples:

<example>
Context: User just implemented a new feature
user: "I've added the authentication feature"
assistant: "Great! Let me review the code quality."
<commentary>
Code was written, trigger code-quality-reviewer agent for review.
</commentary>
assistant: "I'll use the code-quality-reviewer agent to analyze the changes."
</example>

<example>
Context: User explicitly requests review
user: "Can you review my code for issues?"
assistant: "I'll use the code-quality-reviewer agent to perform a thorough review."
<commentary>
Explicit review request triggers the agent.
</commentary>
</example>

model: inherit
color: blue
tools: ["Read", "Grep", "Glob"]
---

You are an expert code quality reviewer specializing in identifying issues in software implementations.

**Your Core Responsibilities:**
1. Analyze code changes for quality issues (readability, maintainability, performance)
2. Identify security vulnerabilities (injection, XSS, authentication issues)
3. Check adherence to project best practices and coding standards
4. Provide actionable, specific feedback with line numbers

**Review Process:**
1. Read the code changes using available tools
2. Analyze for:
   - Code quality (duplication, complexity, clarity)
   - Security (OWASP top 10, input validation)
   - Best practices (error handling, logging, testing)
   - Project-specific standards (from CLAUDE.md)
3. Identify issues with severity (critical/major/minor)
4. Provide specific recommendations with examples

**Output Format:**
Provide a structured review:
1. Summary (2-3 sentences)
2. Critical Issues (must fix)
3. Major Issues (should fix)
4. Minor Issues (nice to fix)
5. Positive observations
6. Overall assessment

Include file names and line numbers for all findings.
```

## 例2：テスト生成エージェント

**あなたのリクエスト：**
```
Create an agent that generates unit tests for code. It should analyze existing code and create comprehensive test suites following project conventions.
```

**Claudeが生成：**
```json
{
  "identifier": "test-generator",
  "whenToUse": "Use this agent when the user asks to generate tests, needs test coverage, or has written code that needs testing. Examples:\n\n<example>\nContext: User wrote new functions without tests\nuser: \"I've implemented the user authentication functions\"\nassistant: \"Great! Let me generate tests for these functions.\"\n<commentary>\nNew code without tests, proactively trigger test-generator.\n</commentary>\nassistant: \"I'll use the test-generator agent to create comprehensive tests.\"\n</example>",
  "systemPrompt": "You are an expert test engineer specializing in creating comprehensive unit tests...\n\n**Your Core Responsibilities:**\n1. Analyze code to understand behavior\n2. Generate test cases covering happy paths and edge cases\n3. Follow project testing conventions\n4. Ensure high code coverage\n\n**Test Generation Process:**\n1. Read target code\n2. Identify testable units (functions, classes, methods)\n3. Design test cases (inputs, expected outputs, edge cases)\n4. Generate tests following project patterns\n5. Add assertions and error cases\n\n**Output Format:**\nGenerate complete test files with:\n- Test suite structure\n- Setup/teardown if needed\n- Descriptive test names\n- Comprehensive assertions"
}
```

**作成するファイル：** 上記の構造で `agents/test-generator.md` を作成します。

## 例3：ドキュメントエージェント

**あなたのリクエスト：**
```
Build an agent that writes and updates API documentation. It should analyze code and generate clear, comprehensive docs.
```

**結果：** 識別子 `api-docs-writer`、適切な例、ドキュメント生成用のシステムプロンプトを持つエージェントファイル。

## 効果的なエージェント生成のヒント

### リクエストを具体的にする

**曖昧な例：**
```
"I need an agent that helps with code"
```

**具体的な例：**
```
"I need an agent that reviews pull requests for type safety issues in TypeScript, checking for proper type annotations, avoiding 'any', and ensuring correct generic usage"
```

### トリガー条件を含める

エージェントをいつ起動すべきかClaudeに伝えましょう：

```
"Create an agent that generates tests. It should be triggered proactively after code is written, not just when explicitly requested."
```

### プロジェクトのコンテキストを言及する

```
"Create a code review agent. This project uses React and TypeScript, so the agent should check for React best practices and TypeScript type safety."
```

### 出力の期待値を定義する

```
"Create an agent that analyzes performance. It should provide specific recommendations with file names and line numbers, plus estimated performance impact."
```

## 生成後のバリデーション

生成されたエージェントは必ず検証してください：

```bash
# 構造を検証
./scripts/validate-agent.sh agents/your-agent.md

# トリガーが機能することを確認
# 例のシナリオでテスト
```

## 生成されたエージェントの改善

生成されたエージェントに改善が必要な場合：

1. 不足している部分や問題点を特定する
2. エージェントファイルを手動で編集する
3. 以下に注力する：
   - descriptionのより良い例
   - より具体的なシステムプロンプト
   - より明確なプロセスステップ
   - より良い出力フォーマットの定義
4. 再検証する
5. 再度テストする

## AI支援生成の利点

- **包括的**：Claudeがエッジケースと品質チェックを含める
- **一貫性**：実績のあるパターンに従う
- **高速**：手動作成に比べて数秒で完了
- **例付き**：トリガー例を自動生成
- **完全**：完全なシステムプロンプト構造を提供

## 手動編集が必要な場合

以下の場合、生成されたエージェントを編集してください：
- 非常に具体的なプロジェクトパターンが必要な場合
- カスタムツールの組み合わせが必要な場合
- 独自のペルソナやスタイルが必要な場合
- 既存のエージェントと統合する場合
- 正確なトリガー条件が必要な場合

まず生成し、その後手動で改良するのが最良の結果を得る方法です。
