# エージェントトリガー例：ベストプラクティス

信頼性の高いトリガーのための効果的な `<example>` ブロックの書き方に関する完全ガイド。

## Exampleブロックのフォーマット

トリガー例の標準フォーマット：

```markdown
<example>
Context: [状況を説明 - このインタラクションに至った経緯]
user: "[正確なユーザーメッセージまたはリクエスト]"
assistant: "[トリガー前のClaudeの応答]"
<commentary>
[このシナリオでこのエージェントがトリガーされるべき理由の説明]
</commentary>
assistant: "[Claudeがエージェントを起動する方法 - 通常は 'I'll use the [agent-name] agent...']"
</example>
```

## 良いExampleの構造

### Context

**目的：** シーンを設定する - ユーザーのメッセージの前に何が起きたか

**良いContext：**
```
Context: User just implemented a new authentication feature
Context: User has created a PR and wants it reviewed
Context: User is debugging a test failure
Context: After writing several functions without documentation
```

**悪いContext：**
```
Context: User needs help (曖昧すぎる)
Context: Normal usage (具体的でない)
```

### ユーザーメッセージ

**目的：** エージェントをトリガーすべき正確なフレーズを示す

**良いユーザーメッセージ：**
```
user: "I've added the OAuth flow, can you check it?"
user: "Review PR #123"
user: "Why is this test failing?"
user: "Add docs for these functions"
```

**フレーズを変える：**
同じ意図に対して異なるフレーズの例を複数含めます：
```
Example 1: user: "Review my code"
Example 2: user: "Can you check this implementation?"
Example 3: user: "Look over my changes"
```

### アシスタントの応答（トリガー前）

**目的：** エージェントを起動する前にClaudeが何を言うかを示す

**良い応答：**
```
assistant: "I'll analyze your OAuth implementation."
assistant: "Let me review that PR for you."
assistant: "I'll investigate the test failure."
```

**プロアクティブな例：**
```
assistant: "Great! Now let me review the code quality."
<commentary>
Code was just written, proactively trigger review agent.
</commentary>
```

### Commentary

**目的：** 理由を説明する - このエージェントがなぜトリガーされるべきか

**良いCommentary：**
```
<commentary>
User explicitly requested code review, trigger the code-reviewer agent.
</commentary>

<commentary>
After code implementation, proactively use review agent to check quality.
</commentary>

<commentary>
PR analysis request matches pr-analyzer agent's expertise.
</commentary>
```

**判断ロジックを含める：**
```
<commentary>
User wrote tests (Test tool used). The test-analyzer agent should check
test quality and coverage before continuing.
</commentary>
```

### アシスタントの応答（トリガー時）

**目的：** Claudeがどのようにエージェントを呼び出すかを示す

**標準パターン：**
```
assistant: "I'll use the [agent-name] agent to [what it will do]."
```

**例：**
```
assistant: "I'll use the code-reviewer agent to analyze the changes."
assistant: "Let me use the test-generator agent to create comprehensive tests."
assistant: "I'll use the security-analyzer agent to check for vulnerabilities."
```

## Exampleの種類

### タイプ1：明示的なリクエスト

ユーザーがエージェントの機能を直接要求する場合：

```markdown
<example>
Context: User explicitly requests security analysis
user: "Check my code for security vulnerabilities"
assistant: "I'll use the security-analyzer agent to perform a thorough security review."
<commentary>
Direct security analysis request triggers the security-analyzer agent.
</commentary>
</example>
```

### タイプ2：プロアクティブなトリガー

明示的なリクエストなしに、関連する作業の後にエージェントがトリガーされる場合：

```markdown
<example>
Context: User just implemented database queries
user: "I've added the user search functionality"
assistant: "Great! Let me review it for security."
<commentary>
Database code written. Proactively trigger security-analyzer to check
for SQL injection and other database security issues.
</commentary>
assistant: "I'll use the security-analyzer agent to check the database code."
</example>
```

### タイプ3：暗黙的なリクエスト

ユーザーが直接述べずにニーズを暗示する場合：

```markdown
<example>
Context: User mentions code is hard to understand
user: "This code is confusing and hard to follow"
assistant: "I can help improve the code clarity."
<commentary>
User indicates complexity issues. Trigger code-simplifier agent to refactor
for better readability.
</commentary>
assistant: "I'll use the code-simplifier agent to suggest improvements."
</example>
```

### タイプ4：ツール使用パターン

以前のツール使用に基づいてエージェントがトリガーされる場合：

```markdown
<example>
Context: User made multiple edits to test files
user: "I've updated all the tests"
assistant: "Great! Let me verify test quality."
<commentary>
Multiple Edit tools used on test files. Proactively trigger test-quality-analyzer
to ensure tests follow best practices.
</commentary>
assistant: "I'll use the test-quality-analyzer agent to review the tests."
</example>
```

## 複数のExample戦略

### 異なるフレーズをカバーする

```markdown
<example>
user: "Review my code"
[...]
</example>

<example>
user: "Can you check my implementation?"
[...]
</example>

<example>
user: "Look over these changes"
[...]
</example>
```

### プロアクティブとリアクティブの両方をカバーする

```markdown
<example>
Context: User explicitly requests review
user: "Review my code for issues"
[...]
</example>

<example>
Context: After user writes code
user: "I've implemented the feature"
assistant: "Great! Now let me review it."
<commentary>
Code written, proactively review.
</commentary>
[...]
</example>
```

### エッジケースをカバーする

```markdown
<example>
Context: Typical usage
user: "Check my PR"
[...]
</example>

<example>
Context: Large PR that needs thorough analysis
user: "This is a big PR, can you do a deep review?"
[...]
<commentary>
Large PR mentioned, use thorough analysis mode.
</commentary>
</example>
```

## よくある間違い

### Contextの欠如

```markdown
<example>
user: "Review my code"
assistant: "I'll use the code-reviewer agent."
</example>
```

**問題点：** このリクエストに至った経緯のコンテキストがない。

### Contextあり

```markdown
<example>
Context: User just finished implementing authentication
user: "Review my code"
assistant: "I'll use the code-reviewer agent to analyze the auth implementation."
<commentary>
Auth code written, review for security and best practices.
</commentary>
</example>
```

### Commentaryの欠如

```markdown
<example>
Context: User requests review
user: "Check my changes"
assistant: "I'll use the reviewer agent."
</example>
```

**問題点：** エージェントがなぜトリガーされるのかの説明がない。

### Commentaryあり

```markdown
<example>
Context: User requests review after making changes
user: "Check my changes"
assistant: "I'll use the code-reviewer agent to analyze the modifications."
<commentary>
Code review request triggers agent to check quality, security, and adherence to standards.
</commentary>
</example>
```

### エージェントが直接応答している

```markdown
<example>
user: "Review my code"
assistant: "I found the following issues: [lists issues]"
</example>
```

**問題点：** トリガーではなく、エージェントの出力を示している。

### トリガーを示している

```markdown
<example>
user: "Review my code"
assistant: "I'll use the code-reviewer agent to perform the review."
<commentary>
Review request triggers the agent.
</commentary>
</example>
```

## Exampleの数は？

### 最低：2つのExample

少なくとも以下をカバーする：
1. 明示的なリクエスト
2. 1つのバリエーションまたはプロアクティブトリガー

### 推奨：3〜4つのExample

以下をカバーする：
1. 明示的なリクエスト（直接の要求）
2. 暗黙的なリクエスト（ユーザーがニーズを暗示）
3. プロアクティブトリガー（関連する作業の後）
4. エッジケースまたは特定のシナリオ

### 最大：6つのExample

6つ以上はdescriptionが長くなりすぎます。最も重要なシナリオに焦点を当ててください。

## テンプレートライブラリ

### コードレビューエージェント

```markdown
<example>
Context: User just implemented a new feature
user: "I've added the user registration feature"
assistant: "Great! Let me review the code quality."
<commentary>
Code written, proactively trigger code-reviewer agent.
</commentary>
assistant: "I'll use the code-reviewer agent to analyze the implementation."
</example>

<example>
Context: User explicitly requests review
user: "Can you review my changes for issues?"
assistant: "I'll use the code-reviewer agent to perform a thorough review."
<commentary>
Explicit review request triggers the agent.
</commentary>
</example>
```

### テスト生成エージェント

```markdown
<example>
Context: User implemented functions without tests
user: "I've added the data processing functions"
assistant: "Great! Let me generate tests for these."
<commentary>
New code without tests, proactively trigger test-generator agent.
</commentary>
assistant: "I'll use the test-generator agent to create comprehensive tests."
</example>

<example>
Context: User explicitly asks for tests
user: "Generate tests for my code"
assistant: "I'll use the test-generator agent to create a complete test suite."
<commentary>
Direct test generation request triggers the agent.
</commentary>
</example>
```

### ドキュメントエージェント

```markdown
<example>
Context: User added new API endpoints
user: "I've implemented the REST API endpoints"
assistant: "I'll document these endpoints."
<commentary>
New API code, proactively generate documentation.
</commentary>
assistant: "I'll use the api-docs-writer agent to create comprehensive documentation."
</example>

<example>
Context: User requests documentation
user: "Write docs for this API"
assistant: "I'll use the api-docs-writer agent to generate clear documentation."
<commentary>
Documentation request triggers the agent.
</commentary>
</example>
```

### バリデーションエージェント

```markdown
<example>
Context: User ready to commit changes
user: "I'm ready to commit this code"
assistant: "Let me validate it first."
<commentary>
Before commit, proactively validate with validation-agent.
</commentary>
assistant: "I'll use the code-validator agent to check for issues."
</example>

<example>
Context: User asks for validation
user: "Validate my implementation"
assistant: "I'll use the code-validator agent to verify correctness."
<commentary>
Explicit validation request triggers the agent.
</commentary>
</example>
```

## トリガー問題のデバッグ

### エージェントがトリガーされない

**確認事項：**
1. ユーザーメッセージからの関連キーワードがExampleに含まれているか
2. Contextが実際の使用シナリオと一致しているか
3. Commentaryがトリガーロジックを明確に説明しているか
4. アシスタントがExampleでAgent toolの使用を示しているか

**修正方法：**
異なるフレーズをカバーするExampleを追加する。

### エージェントが頻繁にトリガーされすぎる

**確認事項：**
1. Exampleが広すぎるまたは一般的すぎないか
2. トリガー条件が他のエージェントと重複していないか
3. Commentaryがいつ使用しないべきかを区別していないか

**修正方法：**
Exampleをより具体的にし、ネガティブな例を追加する。

### エージェントが誤ったシナリオでトリガーされる

**確認事項：**
1. Exampleが実際の意図された使用と一致していないか
2. Commentaryが不適切なトリガーを示唆していないか

**修正方法：**
正しいトリガーシナリオのみを示すようにExampleを修正する。

## ベストプラクティスまとめ

**すべきこと：**
- 2〜4つの具体的で詳細なExampleを含める
- 明示的とプロアクティブの両方のトリガーを示す
- 各Exampleに明確なContextを提供する
- Commentaryで理由を説明する
- ユーザーメッセージのフレーズを変える
- ClaudeがAgent toolを使用する様子を示す

**すべきでないこと：**
- 一般的で曖昧なExampleを使用する
- ContextやCommentaryを省略する
- 1種類のトリガーのみを示す
- エージェント起動ステップをスキップする
- Exampleを類似させすぎる
- エージェントがトリガーされる理由の説明を忘れる

## 結論

よく作り込まれたExampleは、信頼性の高いエージェントトリガーに不可欠です。エージェントがいつ、なぜ使用されるべきかを明確に示す多様で具体的なExampleの作成に時間を投資してください。
