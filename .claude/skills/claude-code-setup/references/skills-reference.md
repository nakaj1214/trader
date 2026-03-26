# スキル推奨

スキルは、ワークフロー、リファレンス資料、ベストプラクティスをパッケージ化した専門知識です。`.claude/skills/<name>/SKILL.md` に作成します。スキルは関連する場面で Claude が自動的に呼び出すことも、ユーザーが `/skill-name` で直接呼び出すこともできます。

一部のビルド済みスキルは公式プラグインを通じて利用可能です（`/plugin install` でインストール）。

**注意**: これらは一般的なパターンです。コードベースのツールやフレームワークに特化したスキルのアイデアを見つけるには、Web 検索を使用してください。

---

## 公式プラグインから利用可能

### プラグイン開発 (plugin-dev)

| スキル | 最適な用途 |
|-------|----------|
| **skill-creator** | スキルの作成、テスト、改善 |
| **hook-development** | 自動化用フックの構築 |
| **command-development** | スラッシュコマンドの作成 |
| **agent-development** | 専門サブエージェントの構築 |
| **mcp-integration** | プラグインへの MCP サーバー統合 |
| **plugin-structure** | プラグインアーキテクチャの理解 |

### Git ワークフロー (commit-commands)

| スキル | 最適な用途 |
|-------|----------|
| **commit** | 適切なメッセージ付き git コミットの作成 |
| **commit-push-pr** | コミット、プッシュ、PR の完全なワークフロー |

### フロントエンド (frontend-design)

| スキル | 最適な用途 |
|-------|----------|
| **frontend-design** | 洗練された UI コンポーネントの作成 |

**価値**: 汎用的な AI 的美学ではなく、独自性のある高品質な UI を作成します。

### 自動化ルール (hookify)

| スキル | 最適な用途 |
|-------|----------|
| **writing-rules** | 自動化用 hookify ルールの作成 |

### 機能開発 (feature-dev)

| スキル | 最適な用途 |
|-------|----------|
| **feature-dev** | エンドツーエンドの機能開発ワークフロー |

---

## クイックリファレンス: 公式プラグインスキル

| コードベースのシグナル | スキル | プラグイン |
|-----------------|-------|--------|
| プラグインの構築 | skill-creator | - |
| Git コミット | commit | commit-commands |
| React/Vue/Angular | frontend-design | frontend-design |
| 自動化ルール | writing-rules | hookify |
| 機能計画 | feature-dev | feature-dev |

---

## カスタムプロジェクトスキル

プロジェクト固有のスキルは `.claude/skills/<name>/SKILL.md` に作成します。

### スキルの構造

```
.claude/skills/
└── my-skill/
    ├── SKILL.md           # メインの手順書（必須）
    ├── template.yaml      # 適用するテンプレート
    ├── scripts/
    │   └── validate.sh    # 実行するスクリプト
    └── examples/          # リファレンス例
```

### フロントマターリファレンス

```yaml
---
name: skill-name
description: このスキルの機能と使用するタイミング
disable-model-invocation: true  # ユーザーのみ呼び出し可能（副作用がある場合）
user-invocable: false           # Claude のみ呼び出し可能（バックグラウンド知識用）
allowed-tools: Read, Grep, Glob # ツールアクセスを制限
context: fork                   # 分離されたサブエージェントで実行
agent: Explore                  # フォーク時のエージェントタイプ
---
```

### 呼び出し制御

| 設定 | ユーザー | Claude | 用途 |
|---------|------|--------|---------|
| （デフォルト） | ✓ | ✓ | 汎用スキル |
| `disable-model-invocation: true` | ✓ | ✗ | 副作用あり（デプロイ、送信） |
| `user-invocable: false` | ✗ | ✓ | バックグラウンド知識 |

---

## カスタムスキルの例

### OpenAPI テンプレートによる API ドキュメント

YAML テンプレートを適用して一貫した API ドキュメントを生成:

```
.claude/skills/api-doc/
├── SKILL.md
└── openapi-template.yaml
```

**SKILL.md:**
```yaml
---
name: api-doc
description: Generate OpenAPI documentation for an endpoint. Use when documenting API routes.
---

Generate OpenAPI documentation for the endpoint at $ARGUMENTS.

Use the template in [openapi-template.yaml](openapi-template.yaml) as the structure.

1. Read the endpoint code
2. Extract path, method, parameters, request/response schemas
3. Fill in the template with actual values
4. Output the completed YAML
```

**openapi-template.yaml:**
```yaml
paths:
  /{path}:
    {method}:
      summary: ""
      description: ""
      parameters: []
      requestBody:
        content:
          application/json:
            schema: {}
      responses:
        "200":
          description: ""
          content:
            application/json:
              schema: {}
```

---

### スクリプト付きデータベースマイグレーションジェネレーター

バンドルされたスクリプトを使ってマイグレーションを生成・検証:

```
.claude/skills/create-migration/
├── SKILL.md
└── scripts/
    └── validate-migration.sh
```

**SKILL.md:**
```yaml
---
name: create-migration
description: Create a database migration file
disable-model-invocation: true
allowed-tools: Read, Write, Bash
---

Create a migration for: $ARGUMENTS

1. Generate migration file in `migrations/` with timestamp prefix
2. Include up and down functions
3. Run validation: `bash ~/.claude/skills/create-migration/scripts/validate-migration.sh`
4. Report any issues found
```

**scripts/validate-migration.sh:**
```bash
#!/bin/bash
# Validate migration syntax
npx prisma validate 2>&1 || echo "Validation failed"
```

---

### サンプル付きテストジェネレーター

プロジェクトのパターンに従ってテストを生成:

```
.claude/skills/gen-test/
├── SKILL.md
└── examples/
    ├── unit-test.ts
    └── integration-test.ts
```

**SKILL.md:**
```yaml
---
name: gen-test
description: Generate tests for a file following project conventions
disable-model-invocation: true
---

Generate tests for: $ARGUMENTS

Reference these examples for the expected patterns:
- Unit tests: [examples/unit-test.ts](examples/unit-test.ts)
- Integration tests: [examples/integration-test.ts](examples/integration-test.ts)

1. Analyze the source file
2. Identify functions/methods to test
3. Generate tests matching project conventions
4. Place in appropriate test directory
```

---

### テンプレート付きコンポーネントジェネレーター

テンプレートから新しいコンポーネントをスキャフォールド:

```
.claude/skills/new-component/
├── SKILL.md
└── templates/
    ├── component.tsx.template
    ├── component.test.tsx.template
    └── component.stories.tsx.template
```

**SKILL.md:**
```yaml
---
name: new-component
description: Scaffold a new React component with tests and stories
disable-model-invocation: true
---

Create component: $ARGUMENTS

Use templates in [templates/](templates/) directory:
1. Generate component from component.tsx.template
2. Generate tests from component.test.tsx.template
3. Generate Storybook story from component.stories.tsx.template

Replace {{ComponentName}} with the PascalCase name.
Replace {{component-name}} with the kebab-case name.
```

---

### チェックリスト付き PR レビュー

プロジェクト固有のチェックリストに対して PR をレビュー:

```
.claude/skills/pr-check/
├── SKILL.md
└── checklist.md
```

**SKILL.md:**
```yaml
---
name: pr-check
description: Review PR against project checklist
disable-model-invocation: true
context: fork
---

## PR Context
- Diff: !`gh pr diff`
- Description: !`gh pr view`

Review against [checklist.md](checklist.md).

For each item, mark ✅ or ❌ with explanation.
```

**checklist.md:**
```markdown
## PR チェックリスト

- [ ] 新機能にテストが追加されている
- [ ] console.log ステートメントがない
- [ ] エラーハンドリングにユーザー向けメッセージが含まれている
- [ ] API の変更が後方互換性を保っている
- [ ] データベースマイグレーションが元に戻せる
```

---

### リリースノートジェネレーター

git 履歴からリリースノートを生成:

**SKILL.md:**
```yaml
---
name: release-notes
description: Generate release notes from commits since last tag
disable-model-invocation: true
---

## Recent Changes
- Commits since last tag: !`git log $(git describe --tags --abbrev=0)..HEAD --oneline`
- Last tag: !`git describe --tags --abbrev=0`

Generate release notes:
1. Group commits by type (feat, fix, docs, etc.)
2. Write user-friendly descriptions
3. Highlight breaking changes
4. Format as markdown
```

---

### プロジェクト規約（Claude 専用）

Claude が自動的に適用するバックグラウンド知識:

**SKILL.md:**
```yaml
---
name: project-conventions
description: Code style and patterns for this project. Apply when writing or reviewing code.
user-invocable: false
---

## Naming Conventions
- React components: PascalCase
- Utilities: camelCase
- Constants: UPPER_SNAKE_CASE
- Files: kebab-case

## Patterns
- Use `Result<T, E>` for fallible operations, not exceptions
- Prefer composition over inheritance
- All API responses use `{ data, error, meta }` shape

## Forbidden
- No `any` types
- No `console.log` in production code
- No synchronous file I/O
```

---

### 環境セットアップ

セットアップスクリプトで新しい開発者をオンボーディング:

```
.claude/skills/setup-dev/
├── SKILL.md
└── scripts/
    └── check-prerequisites.sh
```

**SKILL.md:**
```yaml
---
name: setup-dev
description: Set up development environment for new contributors
disable-model-invocation: true
---

Set up development environment:

1. Check prerequisites: `bash scripts/check-prerequisites.sh`
2. Install dependencies: `npm install`
3. Copy environment template: `cp .env.example .env`
4. Set up database: `npm run db:setup`
5. Verify setup: `npm test`

Report any issues encountered.
```

---

## 引数パターン

| パターン | 意味 | 例 |
|---------|---------|---------|
| `$ARGUMENTS` | すべての引数を文字列として | `/deploy staging` → "staging" |

スキル内に `$ARGUMENTS` がない場合、引数は `ARGUMENTS: <value>` として追加されます。

## 動的コンテキスト注入

`!`command`` を使用してスキル実行前にライブデータを注入:

```yaml
## Current State
- Branch: !`git branch --show-current`
- Status: !`git status --short`
```

コマンドの出力がプレースホルダーを置換してから、Claude がスキルの内容を参照します。
