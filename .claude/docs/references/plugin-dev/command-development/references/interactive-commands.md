# インタラクティブコマンドパターン

AskUserQuestion ツールを通じてユーザーのフィードバックを収集し判断を行うコマンドの包括的ガイド。

## 概要

単純な引数ではうまくいかないユーザー入力を必要とするコマンドがある。例えば:
- トレードオフのある複数の複雑なオプションからの選択
- リストからの複数項目の選択
- 説明を必要とする判断
- インタラクティブな設定やプリファレンスの収集

これらのケースでは、コマンド引数に頼るのではなく、コマンド実行内で **AskUserQuestion ツール** を使用する。

## AskUserQuestion を使うタイミング

### AskUserQuestion を使う場合:

1. **説明が必要な複数選択肢の判断**
2. **選択にコンテキストが必要な複雑なオプション**
3. **複数選択シナリオ**（複数項目の選択）
4. **設定のためのプリファレンス収集**
5. **回答に基づいて適応するインタラクティブワークフロー**

### コマンド引数を使う場合:

1. **単純な値**（ファイルパス、数値、名前）
2. **ユーザーがすでに持っている既知の入力**
3. **自動化可能であるべきスクリプト可能なワークフロー**
4. **プロンプトが遅くなる高速呼び出し**

## AskUserQuestion の基本

### ツールパラメータ

```typescript
{
  questions: [
    {
      question: "Which authentication method should we use?",
      header: "Auth method",  // 短いラベル（最大12文字）
      multiSelect: false,     // 複数選択の場合は true
      options: [
        {
          label: "OAuth 2.0",
          description: "Industry standard, supports multiple providers"
        },
        {
          label: "JWT",
          description: "Stateless, good for APIs"
        },
        {
          label: "Session",
          description: "Traditional, server-side state"
        }
      ]
    }
  ]
}
```

**重要なポイント:**
- ユーザーは常に「Other」を選択してカスタム入力を提供できる（自動）
- `multiSelect: true` で複数のオプションを選択可能
- オプションは 2-4 個（それ以上は避ける）
- 1回のツールコールで 1-4 個の質問を聞ける

## ユーザーインタラクション用コマンドパターン

### 基本的なインタラクティブコマンド

```markdown
---
description: Interactive setup command
allowed-tools: AskUserQuestion, Write
---

# Interactive Plugin Setup

This command will guide you through configuring the plugin with a series of questions.

## Step 1: Gather Configuration

Use the AskUserQuestion tool to ask:

**Question 1 - Deployment target:**
- header: "Deploy to"
- question: "Which deployment platform will you use?"
- options:
  - AWS (Amazon Web Services with ECS/EKS)
  - GCP (Google Cloud with GKE)
  - Azure (Microsoft Azure with AKS)
  - Local (Docker on local machine)

**Question 2 - Environment strategy:**
- header: "Environments"
- question: "How many environments do you need?"
- options:
  - Single (Just production)
  - Standard (Dev, Staging, Production)
  - Complete (Dev, QA, Staging, Production)

**Question 3 - Features to enable:**
- header: "Features"
- question: "Which features do you want to enable?"
- multiSelect: true
- options:
  - Auto-scaling (Automatic resource scaling)
  - Monitoring (Health checks and metrics)
  - CI/CD (Automated deployment pipeline)
  - Backups (Automated database backups)

## Step 2: Process Answers

Based on the answers received from AskUserQuestion:

1. Parse the deployment target choice
2. Set up environment-specific configuration
3. Enable selected features
4. Generate configuration files

## Step 3: Generate Configuration

Create `.claude/plugin-name.local.md` with:

\`\`\`yaml
---
deployment_target: [answer from Q1]
environments: [answer from Q2]
features:
  auto_scaling: [true if selected in Q3]
  monitoring: [true if selected in Q3]
  ci_cd: [true if selected in Q3]
  backups: [true if selected in Q3]
---

# Plugin Configuration

Generated: [timestamp]
Target: [deployment_target]
Environments: [environments]
\`\`\`

## Step 4: Confirm and Next Steps

Confirm configuration created and guide user on next steps.
```

### マルチステージインタラクティブワークフロー

```markdown
---
description: Multi-stage interactive workflow
allowed-tools: AskUserQuestion, Read, Write, Bash
---

# Multi-Stage Deployment Setup

This command walks through deployment setup in stages, adapting based on your answers.

## Stage 1: Basic Configuration

Use AskUserQuestion to ask about deployment basics.

Based on answers, determine which additional questions to ask.

## Stage 2: Advanced Options (Conditional)

If user selected "Advanced" deployment in Stage 1:

Use AskUserQuestion to ask about:
- Load balancing strategy
- Caching configuration
- Security hardening options

If user selected "Simple" deployment:
- Skip advanced questions
- Use sensible defaults

## Stage 3: Confirmation

Show summary of all selections.

Use AskUserQuestion for final confirmation:
- header: "Confirm"
- question: "Does this configuration look correct?"
- options:
  - Yes (Proceed with setup)
  - No (Start over)
  - Modify (Let me adjust specific settings)

If "Modify", ask which specific setting to change.

## Stage 4: Execute Setup

Based on confirmed configuration, execute setup steps.
```

## インタラクティブ質問の設計

### 質問の構造

**良い質問:**
```markdown
Question: "Which database should we use for this project?"
Header: "Database"
Options:
  - PostgreSQL (Relational, ACID compliant, best for complex queries)
  - MongoDB (Document store, flexible schema, best for rapid iteration)
  - Redis (In-memory, fast, best for caching and sessions)
```

**悪い質問:**
```markdown
Question: "Database?"  // 曖昧すぎる
Header: "DB"  // 不明確な略語
Options:
  - Option 1  // 説明的でない
  - Option 2
```

### オプション設計のベストプラクティス

**明確なラベル:**
- 1-5 語を使用
- 具体的で説明的
- コンテキストなしの専門用語は避ける

**有用な説明:**
- オプションの意味を説明
- 主なメリットやトレードオフに言及
- ユーザーが情報に基づいた判断をできるよう支援
- 1-2 文に収める

**適切な数:**
- 1 つの質問に 2-4 個のオプション
- 選択肢が多すぎて圧倒しない
- 関連するオプションをグループ化
- 「Other」は自動的に提供される

### 複数選択の質問

**multiSelect を使う場合:**

```markdown
Use AskUserQuestion for enabling features:

Question: "Which features do you want to enable?"
Header: "Features"
multiSelect: true  // 複数選択を許可
Options:
  - Logging (Detailed operation logs)
  - Metrics (Performance monitoring)
  - Alerts (Error notifications)
  - Backups (Automatic backups)
```

ユーザーは任意の組み合わせを選択できる: なし、一部、またはすべて。

**multiSelect を使わない場合:**

```markdown
Question: "Which authentication method?"
multiSelect: false  // 認証方法は1つだけが妥当
```

相互排他的な選択肢には multiSelect を使わない。

## AskUserQuestion を使ったコマンドパターン

### パターン 1: シンプルな Yes/No 判断

```markdown
---
description: Command with confirmation
allowed-tools: AskUserQuestion, Bash
---

# Destructive Operation

This operation will delete all cached data.

Use AskUserQuestion to confirm:

Question: "This will delete all cached data. Are you sure?"
Header: "Confirm"
Options:
  - Yes (Proceed with deletion)
  - No (Cancel operation)

If user selects "Yes":
  Execute deletion
  Report completion

If user selects "No":
  Cancel operation
  Exit without changes
```

### パターン 2: 複数の設定質問

```markdown
---
description: Multi-question configuration
allowed-tools: AskUserQuestion, Write
---

# Project Configuration Setup

Gather configuration through multiple questions.

Use AskUserQuestion with multiple questions in one call:

**Question 1:**
- question: "Which programming language?"
- header: "Language"
- options: Python, TypeScript, Go, Rust

**Question 2:**
- question: "Which test framework?"
- header: "Testing"
- options: Jest, PyTest, Go Test, Cargo Test
  (Adapt based on language from Q1)

**Question 3:**
- question: "Which CI/CD platform?"
- header: "CI/CD"
- options: GitHub Actions, GitLab CI, CircleCI

**Question 4:**
- question: "Which features do you need?"
- header: "Features"
- multiSelect: true
- options: Linting, Type checking, Code coverage, Security scanning

Process all answers together to generate cohesive configuration.
```

### パターン 3: 条件付き質問フロー

```markdown
---
description: Conditional interactive workflow
allowed-tools: AskUserQuestion, Read, Write
---

# Adaptive Configuration

## Question 1: Deployment Complexity

Use AskUserQuestion:

Question: "How complex is your deployment?"
Header: "Complexity"
Options:
  - Simple (Single server, straightforward)
  - Standard (Multiple servers, load balancing)
  - Complex (Microservices, orchestration)

## Conditional Questions Based on Answer

If answer is "Simple":
  - No additional questions
  - Use minimal configuration

If answer is "Standard":
  - Ask about load balancing strategy
  - Ask about scaling policy

If answer is "Complex":
  - Ask about orchestration platform (Kubernetes, Docker Swarm)
  - Ask about service mesh (Istio, Linkerd, None)
  - Ask about monitoring (Prometheus, Datadog, CloudWatch)
  - Ask about logging aggregation

## Process Conditional Answers

Generate configuration appropriate for selected complexity level.
```

### パターン 4: 反復的な収集

```markdown
---
description: Collect multiple items iteratively
allowed-tools: AskUserQuestion, Write
---

# Collect Team Members

We'll collect team member information for the project.

## Question: How many team members?

Use AskUserQuestion:

Question: "How many team members should we set up?"
Header: "Team size"
Options:
  - 2 people
  - 3 people
  - 4 people
  - 6 people

## Iterate Through Team Members

For each team member (1 to N based on answer):

Use AskUserQuestion for member details:

Question: "What role for team member [number]?"
Header: "Role"
Options:
  - Frontend Developer
  - Backend Developer
  - DevOps Engineer
  - QA Engineer
  - Designer

Store each member's information.

## Generate Team Configuration

After collecting all N members, create team configuration file with all members and their roles.
```

### パターン 5: 依存関係の選択

```markdown
---
description: Select dependencies with multi-select
allowed-tools: AskUserQuestion
---

# Configure Project Dependencies

## Question: Required Libraries

Use AskUserQuestion with multiSelect:

Question: "Which libraries does your project need?"
Header: "Dependencies"
multiSelect: true
Options:
  - React (UI framework)
  - Express (Web server)
  - TypeORM (Database ORM)
  - Jest (Testing framework)
  - Axios (HTTP client)

User can select any combination.

## Process Selections

For each selected library:
- Add to package.json dependencies
- Generate sample configuration
- Create usage examples
- Update documentation
```

## インタラクティブコマンドのベストプラクティス

### 質問の設計

1. **明確で具体的に:** 質問は曖昧でないこと
2. **簡潔なヘッダー:** クリーンな表示のため最大12文字
3. **有用なオプション:** ラベルが明確で、説明がトレードオフを説明
4. **適切な数:** 1質問あたり 2-4 オプション、1コールあたり 1-4 質問
5. **論理的な順序:** 質問が自然に流れること

### エラーハンドリング

```markdown
# Handle AskUserQuestion Responses

After calling AskUserQuestion, verify answers received:

If answers are empty or invalid:
  Something went wrong gathering responses.

  Please try again or provide configuration manually:
  [Show alternative approach]

  Exit.

If answers look correct:
  Process as expected
```

### 段階的な開示

```markdown
# Start Simple, Get Detailed as Needed

## Question 1: Setup Type

Use AskUserQuestion:

Question: "How would you like to set up?"
Header: "Setup type"
Options:
  - Quick (Use recommended defaults)
  - Custom (Configure all options)
  - Guided (Step-by-step with explanations)

If "Quick":
  Apply defaults, minimal questions

If "Custom":
  Ask all available configuration questions

If "Guided":
  Ask questions with extra explanation
  Provide recommendations along the way
```

### 複数選択のガイドライン

**良い複数選択の使用:**
```markdown
Question: "Which features do you want to enable?"
multiSelect: true
Options:
  - Logging
  - Metrics
  - Alerts
  - Backups

理由: ユーザーは任意の組み合わせを選ぶ可能性がある
```

**悪い複数選択の使用:**
```markdown
Question: "Which database engine?"
multiSelect: true  // ❌ 単一選択であるべき

理由: データベースエンジンは1つしか使えない
```

## 高度なパターン

### バリデーションループ

```markdown
---
description: Interactive with validation
allowed-tools: AskUserQuestion, Bash
---

# Setup with Validation

## Gather Configuration

Use AskUserQuestion to collect settings.

## Validate Configuration

Check if configuration is valid:
- Required dependencies available?
- Settings compatible with each other?
- No conflicts detected?

If validation fails:
  Show validation errors

  Use AskUserQuestion to ask:

  Question: "Configuration has issues. What would you like to do?"
  Header: "Next step"
  Options:
    - Fix (Adjust settings to resolve issues)
    - Override (Proceed despite warnings)
    - Cancel (Abort setup)

  Based on answer, retry or proceed or exit.
```

### 段階的な設定構築

```markdown
---
description: Incremental configuration builder
allowed-tools: AskUserQuestion, Write, Read
---

# Incremental Setup

## Phase 1: Core Settings

Use AskUserQuestion for core settings.

Save to `.claude/config-partial.yml`

## Phase 2: Review Core Settings

Show user the core settings:

Based on these core settings, you need to configure:
- [Setting A] (because you chose [X])
- [Setting B] (because you chose [Y])

Ready to continue?

## Phase 3: Detailed Settings

Use AskUserQuestion for settings based on Phase 1 answers.

Merge with core settings.

## Phase 4: Final Review

Present complete configuration.

Use AskUserQuestion for confirmation:

Question: "Is this configuration correct?"
Options:
  - Yes (Save and apply)
  - No (Start over)
  - Modify (Edit specific settings)
```

### コンテキストに基づく動的オプション

```markdown
---
description: Context-aware questions
allowed-tools: AskUserQuestion, Bash, Read
---

# Context-Aware Setup

## Detect Current State

Check existing configuration:
- Current language: !`detect-language.sh`
- Existing frameworks: !`detect-frameworks.sh`
- Available tools: !`check-tools.sh`

## Ask Context-Appropriate Questions

Based on detected language, ask relevant questions.

If language is TypeScript:

  Use AskUserQuestion:

  Question: "Which TypeScript features should we enable?"
  Options:
    - Strict Mode (Maximum type safety)
    - Decorators (Experimental decorator support)
    - Path Mapping (Module path aliases)

If language is Python:

  Use AskUserQuestion:

  Question: "Which Python tools should we configure?"
  Options:
    - Type Hints (mypy for type checking)
    - Black (Code formatting)
    - Pylint (Linting and style)

Questions adapt to project context.
```

## 実例: マルチエージェントスワーム起動

**multi-agent-swarm プラグインからの例:**

```markdown
---
description: Launch multi-agent swarm
allowed-tools: AskUserQuestion, Read, Write, Bash
---

# Launch Multi-Agent Swarm

## Interactive Mode (No Task List Provided)

If user didn't provide task list file, help create one interactively.

### Question 1: Agent Count

Use AskUserQuestion:

Question: "How many agents should we launch?"
Header: "Agent count"
Options:
  - 2 agents (Best for simple projects)
  - 3 agents (Good for medium projects)
  - 4 agents (Standard team size)
  - 6 agents (Large projects)
  - 8 agents (Complex multi-component projects)

### Question 2: Task Definition Approach

Use AskUserQuestion:

Question: "How would you like to define tasks?"
Header: "Task setup"
Options:
  - File (I have a task list file ready)
  - Guided (Help me create tasks interactively)
  - Custom (Other approach)

If "File":
  Ask for file path
  Validate file exists and has correct format

If "Guided":
  Enter iterative task creation mode (see below)

### Question 3: Coordination Mode

Use AskUserQuestion:

Question: "How should agents coordinate?"
Header: "Coordination"
Options:
  - Team Leader (One agent coordinates others)
  - Collaborative (Agents coordinate as peers)
  - Autonomous (Independent work, minimal coordination)

### Iterative Task Creation (If "Guided" Selected)

For each agent (1 to N from Question 1):

**Question A: Agent Name**
Question: "What should we call agent [number]?"
Header: "Agent name"
Options:
  - auth-agent
  - api-agent
  - ui-agent
  - db-agent
  (Provide relevant suggestions based on common patterns)

**Question B: Task Type**
Question: "What task for [agent-name]?"
Header: "Task type"
Options:
  - Authentication (User auth, JWT, OAuth)
  - API Endpoints (REST/GraphQL APIs)
  - UI Components (Frontend components)
  - Database (Schema, migrations, queries)
  - Testing (Test suites and coverage)
  - Documentation (Docs, README, guides)

**Question C: Dependencies**
Question: "What does [agent-name] depend on?"
Header: "Dependencies"
multiSelect: true
Options:
  - [List of previously defined agents]
  - No dependencies

**Question D: Base Branch**
Question: "Which base branch for PR?"
Header: "PR base"
Options:
  - main
  - staging
  - develop

Store all task information for each agent.

### Generate Task List File

After collecting all agent task details:

1. Ask for project name
2. Generate task list in proper format
3. Save to `.daisy/swarm/tasks.md`
4. Show user the file path
5. Proceed with launch using generated task list
```

## ベストプラクティス

### 質問の書き方

1. **具体的に:** 「オプションを選んでください?」ではなく「どのデータベース?」
2. **トレードオフを説明:** オプションの説明で長所・短所を記述
3. **コンテキストを提供:** 質問のテキストだけで理解できるように
4. **判断をガイド:** ユーザーが情報に基づいた選択をできるよう支援
5. **簡潔に保つ:** ヘッダーは最大12文字、説明は1-2文

### オプションの設計

1. **意味のあるラベル:** 具体的で明確な名前
2. **情報量のある説明:** 各オプションが何をするか説明
3. **トレードオフの表示:** ユーザーが影響を理解できるよう支援
4. **一貫した詳細度:** すべてのオプションを同等に説明
5. **2-4 オプション:** 少なすぎず多すぎず

### フローの設計

1. **論理的な順序:** 質問が自然に流れること
2. **前の回答に基づく:** 後の質問が前の回答を活用
3. **質問を最小限に:** 必要なことだけを聞く
4. **関連をグループ化:** 関連する質問をまとめて聞く
5. **進捗を表示:** フロー内の現在位置を示す

### ユーザー体験

1. **期待値を設定:** ユーザーに何が起こるか伝える
2. **理由を説明:** ユーザーが目的を理解できるよう支援
3. **デフォルトを提供:** 推奨オプションを提案
4. **脱出を許可:** ユーザーがキャンセルまたはやり直しできるように
5. **アクションを確認:** 実行前にまとめを表示

## よくあるパターン

### パターン: 機能選択

```markdown
Use AskUserQuestion:

Question: "Which features do you need?"
Header: "Features"
multiSelect: true
Options:
  - Authentication
  - Authorization
  - Rate Limiting
  - Caching
```

### パターン: 環境設定

```markdown
Use AskUserQuestion:

Question: "Which environment is this?"
Header: "Environment"
Options:
  - Development (Local development)
  - Staging (Pre-production testing)
  - Production (Live environment)
```

### パターン: 優先度選択

```markdown
Use AskUserQuestion:

Question: "What's the priority for this task?"
Header: "Priority"
Options:
  - Critical (Must be done immediately)
  - High (Important, do soon)
  - Medium (Standard priority)
  - Low (Nice to have)
```

### パターン: スコープ選択

```markdown
Use AskUserQuestion:

Question: "What scope should we analyze?"
Header: "Scope"
Options:
  - Current file (Just this file)
  - Current directory (All files in directory)
  - Entire project (Full codebase scan)
```

## 引数と質問の組み合わせ

### 両方を適切に使用

**既知の値には引数:**
```markdown
---
argument-hint: [project-name]
allowed-tools: AskUserQuestion, Write
---

Setup for project: $1

Now gather additional configuration...

Use AskUserQuestion for options that require explanation.
```

**複雑な選択には質問:**
```markdown
Project name from argument: $1

Now use AskUserQuestion to choose:
- Architecture pattern
- Technology stack
- Deployment strategy

These require explanation, so questions work better than arguments.
```

## トラブルシューティング

**質問が表示されない場合:**
- allowed-tools に AskUserQuestion があるか確認
- 質問のフォーマットが正しいか確認
- オプション配列が 2-4 項目か確認

**ユーザーが選択できない場合:**
- オプションのラベルが明確か確認
- 説明が有用か確認
- オプションが多すぎないか検討
- multiSelect の設定が正しいか確認

**フローが分かりにくい場合:**
- 質問の数を減らす
- 関連する質問をグループ化
- ステージ間に説明を追加
- ワークフロー内の進捗を表示

AskUserQuestion を使えば、コマンドはインタラクティブなウィザードとなり、ユーザーを複雑な判断に導きつつ、単純な入力には引数の明確さを維持できる。
