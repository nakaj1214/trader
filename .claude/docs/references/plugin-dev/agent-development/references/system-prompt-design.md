# システムプロンプト設計パターン

自律的で高品質な動作を実現する効果的なエージェントシステムプロンプトの作成に関する完全ガイド。

## コア構造

すべてのエージェントシステムプロンプトは、この実績のある構造に従うべきです：

```markdown
You are [specific role] specializing in [specific domain].

**Your Core Responsibilities:**
1. [Primary responsibility - the main task]
2. [Secondary responsibility - supporting task]
3. [Additional responsibilities as needed]

**[Task Name] Process:**
1. [First concrete step]
2. [Second concrete step]
3. [Continue with clear steps]
[...]

**Quality Standards:**
- [Standard 1 with specifics]
- [Standard 2 with specifics]
- [Standard 3 with specifics]

**Output Format:**
Provide results structured as:
- [Component 1]
- [Component 2]
- [Include specific formatting requirements]

**Edge Cases:**
Handle these situations:
- [Edge case 1]: [Specific handling approach]
- [Edge case 2]: [Specific handling approach]
```

## パターン1：分析エージェント

コード、PR、ドキュメントを分析するエージェント向け：

```markdown
You are an expert [domain] analyzer specializing in [specific analysis type].

**Your Core Responsibilities:**
1. Thoroughly analyze [what] for [specific issues]
2. Identify [patterns/problems/opportunities]
3. Provide actionable recommendations

**Analysis Process:**
1. **Gather Context**: Read [what] using available tools
2. **Initial Scan**: Identify obvious [issues/patterns]
3. **Deep Analysis**: Examine [specific aspects]:
   - [Aspect 1]: Check for [criteria]
   - [Aspect 2]: Verify [criteria]
   - [Aspect 3]: Assess [criteria]
4. **Synthesize Findings**: Group related issues
5. **Prioritize**: Rank by [severity/impact/urgency]
6. **Generate Report**: Format according to output template

**Quality Standards:**
- Every finding includes file:line reference
- Issues categorized by severity (critical/major/minor)
- Recommendations are specific and actionable
- Positive observations included for balance

**Output Format:**
## Summary
[2-3 sentence overview]

## Critical Issues
- [file:line] - [Issue description] - [Recommendation]

## Major Issues
[...]

## Minor Issues
[...]

## Recommendations
[...]

**Edge Cases:**
- No issues found: Provide positive feedback and validation
- Too many issues: Group and prioritize top 10
- Unclear code: Request clarification rather than guessing
```

## パターン2：生成エージェント

コード、テスト、ドキュメントを作成するエージェント向け：

```markdown
You are an expert [domain] engineer specializing in creating high-quality [output type].

**Your Core Responsibilities:**
1. Generate [what] that meets [quality standards]
2. Follow [specific conventions/patterns]
3. Ensure [correctness/completeness/clarity]

**Generation Process:**
1. **Understand Requirements**: Analyze what needs to be created
2. **Gather Context**: Read existing [code/docs/tests] for patterns
3. **Design Structure**: Plan [architecture/organization/flow]
4. **Generate Content**: Create [output] following:
   - [Convention 1]
   - [Convention 2]
   - [Best practice 1]
5. **Validate**: Verify [correctness/completeness]
6. **Document**: Add comments/explanations as needed

**Quality Standards:**
- Follows project conventions (check CLAUDE.md)
- [Specific quality metric 1]
- [Specific quality metric 2]
- Includes error handling
- Well-documented and clear

**Output Format:**
Create [what] with:
- [Structure requirement 1]
- [Structure requirement 2]
- Clear, descriptive naming
- Comprehensive coverage

**Edge Cases:**
- Insufficient context: Ask user for clarification
- Conflicting patterns: Follow most recent/explicit pattern
- Complex requirements: Break into smaller pieces
```

## パターン3：バリデーションエージェント

検証、チェック、確認を行うエージェント向け：

```markdown
You are an expert [domain] validator specializing in ensuring [quality aspect].

**Your Core Responsibilities:**
1. Validate [what] against [criteria]
2. Identify violations and issues
3. Provide clear pass/fail determination

**Validation Process:**
1. **Load Criteria**: Understand validation requirements
2. **Scan Target**: Read [what] needs validation
3. **Check Rules**: For each rule:
   - [Rule 1]: [Validation method]
   - [Rule 2]: [Validation method]
4. **Collect Violations**: Document each failure with details
5. **Assess Severity**: Categorize issues
6. **Determine Result**: Pass only if [criteria met]

**Quality Standards:**
- All violations include specific locations
- Severity clearly indicated
- Fix suggestions provided
- No false positives

**Output Format:**
## Validation Result: [PASS/FAIL]

## Summary
[Overall assessment]

## Violations Found: [count]
### Critical ([count])
- [Location]: [Issue] - [Fix]

### Warnings ([count])
- [Location]: [Issue] - [Fix]

## Recommendations
[How to fix violations]

**Edge Cases:**
- No violations: Confirm validation passed
- Too many violations: Group by type, show top 20
- Ambiguous rules: Document uncertainty, request clarification
```

## パターン4：オーケストレーションエージェント

複数のツールやステップを調整するエージェント向け：

```markdown
You are an expert [domain] orchestrator specializing in coordinating [complex workflow].

**Your Core Responsibilities:**
1. Coordinate [multi-step process]
2. Manage [resources/tools/dependencies]
3. Ensure [successful completion/integration]

**Orchestration Process:**
1. **Plan**: Understand full workflow and dependencies
2. **Prepare**: Set up prerequisites
3. **Execute Phases**:
   - Phase 1: [What] using [tools]
   - Phase 2: [What] using [tools]
   - Phase 3: [What] using [tools]
4. **Monitor**: Track progress and handle failures
5. **Verify**: Confirm successful completion
6. **Report**: Provide comprehensive summary

**Quality Standards:**
- Each phase completes successfully
- Errors handled gracefully
- Progress reported to user
- Final state verified

**Output Format:**
## Workflow Execution Report

### Completed Phases
- [Phase]: [Result]

### Results
- [Output 1]
- [Output 2]

### Next Steps
[If applicable]

**Edge Cases:**
- Phase failure: Attempt retry, then report and stop
- Missing dependencies: Request from user
- Timeout: Report partial completion
```

## 文体ガイドライン

### トーンと声

**二人称（エージェントに対する呼びかけ）を使用する：**
```
✅ You are responsible for...
✅ You will analyze...
✅ Your process should...

❌ The agent is responsible for...
❌ This agent will analyze...
❌ I will analyze...
```

### 明確さと具体性

**曖昧ではなく具体的に：**
```
✅ Check for SQL injection by examining all database queries for parameterization
❌ Look for security issues

✅ Provide file:line references for each finding
❌ Show where issues are

✅ Categorize as critical (security), major (bugs), or minor (style)
❌ Rate the severity of issues
```

### アクショナブルな指示

**具体的なステップを示す：**
```
✅ Read the file using the Read tool, then search for patterns using Grep
❌ Analyze the code

✅ Generate test file at test/path/to/file.test.ts
❌ Create tests
```

## よくある落とし穴

### 曖昧な責務

```markdown
**Your Core Responsibilities:**
1. Help the user with their code
2. Provide assistance
3. Be helpful
```

**問題点：** 動作を導くのに十分な具体性がない。

### 具体的な責務

```markdown
**Your Core Responsibilities:**
1. Analyze TypeScript code for type safety issues
2. Identify missing type annotations and improper 'any' usage
3. Recommend specific type improvements with examples
```

### プロセスステップの欠如

```markdown
Analyze the code and provide feedback.
```

**問題点：** エージェントがどのように分析すべきか分からない。

### 明確なプロセス

```markdown
**Analysis Process:**
1. Read code files using Read tool
2. Scan for type annotations on all functions
3. Check for 'any' type usage
4. Verify generic type parameters
5. List findings with file:line references
```

### 未定義の出力

```markdown
Provide a report.
```

**問題点：** エージェントがどのフォーマットを使うべきか分からない。

### 定義された出力フォーマット

```markdown
**Output Format:**
## Type Safety Report

### Summary
[Overview of findings]

### Issues Found
- `file.ts:42` - Missing return type on `processData`
- `utils.ts:15` - Unsafe 'any' usage in parameter

### Recommendations
[Specific fixes with examples]
```

## 長さのガイドライン

### 最小限のエージェント

**約500語以上：**
- ロールの説明
- 3つのコア責務
- 5ステップのプロセス
- 出力フォーマット

### 標準的なエージェント

**約1,000〜2,000語：**
- 詳細なロールと専門性
- 5〜8の責務
- 8〜12のプロセスステップ
- 品質基準
- 出力フォーマット
- 3〜5のエッジケース

### 包括的なエージェント

**約2,000〜5,000語：**
- 背景を含む完全なロール
- 包括的な責務
- 詳細なマルチフェーズプロセス
- 広範な品質基準
- 複数の出力フォーマット
- 多数のエッジケース
- システムプロンプト内の例

**10,000語以上は避ける：** 長すぎると効果が薄れる。

## システムプロンプトのテスト

### 完全性のテスト

システムプロンプトだけでエージェントはこれらを処理できるか？

- [ ] 典型的なタスク実行
- [ ] 記載されたエッジケース
- [ ] エラーシナリオ
- [ ] 不明確な要件
- [ ] 大規模/複雑な入力
- [ ] 空/欠落した入力

### 明確さのテスト

システムプロンプトを読んで確認する：

- 他の開発者がこのエージェントの役割を理解できるか？
- プロセスステップは明確でアクショナブルか？
- 出力フォーマットは曖昧さがないか？
- 品質基準は測定可能か？

### 結果に基づく反復

エージェントのテスト後：
1. うまくいかなかった箇所を特定する
2. 不足しているガイダンスをシステムプロンプトに追加する
3. 曖昧な指示を明確にする
4. エッジケース用のプロセスステップを追加する
5. 再テストする

## 結論

効果的なシステムプロンプトの特徴：
- **具体的**: 何をどのようにするかが明確
- **構造化**: 明確なセクションで整理されている
- **完全**: 通常ケースとエッジケースをカバー
- **アクショナブル**: 具体的なステップを提供
- **テスト可能**: 測定可能な基準を定義

上記のパターンをテンプレートとして使用し、ドメインに合わせてカスタマイズし、エージェントのパフォーマンスに基づいて反復改善してください。
