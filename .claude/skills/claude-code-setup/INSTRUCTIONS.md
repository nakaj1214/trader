# Claude Automationレコメンダー

コードベースのパターンを分析して、全ての拡張オプションにわたってClaude Codeのオートメーションを推奨する。

**このスキルは読み取り専用。** コードベースを分析して推奨事項を出力する。ファイルの作成や変更は行わない。ユーザーが自分で推奨事項を実装するか、Claudeに別途依頼する。

## 出力ガイドライン

- **各タイプで1〜2つを推奨する**: 圧倒しない - カテゴリごとに最も価値のある1〜2のオートメーションを表示する
- **ユーザーが特定のタイプを求めた場合**: そのタイプのみに集中してより多くのオプション（3〜5の推奨）を提供する
- **参照リストにとどまらない**: 参照ファイルには一般的なパターンが含まれているが、コードベースのツール、フレームワーク、ライブラリに固有の推奨事項をウェブ検索で見つける
- **より多くを求めることができると伝える**: 特定のカテゴリの推奨事項をもっと求めることができることを末尾に記す

## オートメーションタイプ概要

| タイプ | 最適な用途 |
|--------|-----------|
| **フック** | ツールイベントでの自動アクション（保存時フォーマット、リント、編集ブロック） |
| **サブエージェント** | 並行して実行する専門的なレビュアー/分析者 |
| **スキル** | パッケージ化された専門知識、ワークフロー、繰り返しタスク（`/skill-name`でClaudeまたはユーザーが呼び出す） |
| **プラグイン** | インストールできるスキルのコレクション |
| **MCPサーバー** | 外部ツール統合（データベース、API、ブラウザ、ドキュメント） |

## ワークフロー

### フェーズ1: コードベース分析

プロジェクトのコンテキストを収集する:

```bash
# プロジェクトタイプとツールを検出する
ls -la package.json pyproject.toml Cargo.toml go.mod pom.xml 2>/dev/null
cat package.json 2>/dev/null | head -50

# MCPサーバー推奨のために依存関係を確認する
cat package.json 2>/dev/null | grep -E '"(react|vue|angular|next|express|fastapi|django|prisma|supabase|stripe)"'

# 既存のClaude Code設定を確認する
ls -la .claude/ CLAUDE.md 2>/dev/null

# プロジェクト構造を分析する
ls -la src/ app/ lib/ tests/ components/ pages/ api/ 2>/dev/null
```

**把握すべき主要な指標:**

| カテゴリ | 確認する内容 | 推奨に役立つ情報 |
|--------|------------|--------------|
| 言語/フレームワーク | package.json、pyproject.toml、インポートパターン | フック、MCPサーバー |
| フロントエンドスタック | React、Vue、Angular、Next.js | Playwright MCP、フロントエンドスキル |
| バックエンドスタック | Express、FastAPI、Django | APIドキュメントツール |
| データベース | Prisma、Supabase、生SQL | データベースMCPサーバー |
| 外部API | Stripe、OpenAI、AWS SDK | ドキュメント向けcontext7 MCP |
| テスト | Jest、pytest、Playwright設定 | テストフック、サブエージェント |
| CI/CD | GitHub Actions、CircleCI | GitHub MCPサーバー |
| 課題追跡 | Linear、Jiraの参照 | 課題追跡MCP |
| ドキュメントパターン | OpenAPI、JSDoc、docstring | ドキュメントスキル |

### フェーズ2: 推奨事項を生成する

分析に基づいて、全カテゴリにわたって推奨事項を生成する:

#### A. MCPサーバーの推奨

詳細なパターンは [references/mcp-servers.md](references/mcp-servers.md) を参照。

| コードベースのシグナル | 推奨MCPサーバー |
|-----------------|----------------|
| 人気のライブラリを使用（React、Expressなど） | **context7** - ライブドキュメント参照 |
| UIテストが必要なフロントエンド | **Playwright** - ブラウザオートメーション/テスト |
| Supabaseを使用 | **Supabase MCP** - 直接データベース操作 |
| PostgreSQL/MySQLデータベース | **Database MCP** - クエリとスキーマツール |
| GitHubリポジトリ | **GitHub MCP** - Issues、PR、Actions |
| 課題管理にLinearを使用 | **Linear MCP** - 課題管理 |
| AWSインフラ | **AWS MCP** - クラウドリソース管理 |
| Slackワークスペース | **Slack MCP** - チーム通知 |
| メモリ/コンテキストの永続化 | **Memory MCP** - セッション間メモリ |
| Sentryエラー追跡 | **Sentry MCP** - エラー調査 |
| Dockerコンテナ | **Docker MCP** - コンテナ管理 |

#### B. スキルの推奨

詳細は [references/skills-reference.md](references/skills-reference.md) を参照。

`.claude/skills/<name>/SKILL.md` にスキルを作成する。一部はプラグイン経由でも利用可能:

| コードベースのシグナル | スキル | プラグイン |
|-----------------|-------|----------|
| プラグインを構築している | skill-creator | - |
| Gitコミット | commit | commit-commands |
| React/Vue/Angular | frontend-design | frontend-design |
| オートメーションルール | writing-rules | hookify |
| 機能計画 | feature-dev | feature-dev |

**作成すべきカスタムスキル**（テンプレート、スクリプト、例付き）:

| コードベースのシグナル | 作成するスキル | 呼び出し方 |
|-----------------|-------------|-----------|
| APIルート | **api-doc**（OpenAPIテンプレート付き） | 両方 |
| データベースプロジェクト | **create-migration**（バリデーションスクリプト付き） | ユーザーのみ |
| テストスイート | **gen-test**（テスト例付き） | ユーザーのみ |
| コンポーネントライブラリ | **new-component**（テンプレート付き） | ユーザーのみ |
| PRワークフロー | **pr-check**（チェックリスト付き） | ユーザーのみ |
| リリース | **release-notes**（gitコンテキスト付き） | ユーザーのみ |
| コードスタイル | **project-conventions** | Claudeのみ |
| オンボーディング | **setup-dev**（前提条件スクリプト付き） | ユーザーのみ |

#### C. フックの推奨

設定は [references/hooks-patterns.md](references/hooks-patterns.md) を参照。

| コードベースのシグナル | 推奨フック |
|-----------------|----------|
| Prettierが設定済み | PostToolUse: 編集時自動フォーマット |
| ESLint/Ruffが設定済み | PostToolUse: 編集時自動リント |
| TypeScriptプロジェクト | PostToolUse: 編集時型チェック |
| テストディレクトリが存在 | PostToolUse: 関連テストの実行 |
| `.env`ファイルが存在 | PreToolUse: `.env`編集のブロック |
| ロックファイルが存在 | PreToolUse: ロックファイル編集のブロック |
| セキュリティに敏感なコード | PreToolUse: 確認を要求 |

#### D. サブエージェントの推奨

テンプレートは [references/subagent-templates.md](references/subagent-templates.md) を参照。

| コードベースのシグナル | 推奨サブエージェント |
|-----------------|-----------------|
| 大規模コードベース（500ファイル超） | **code-reviewer** - 並行コードレビュー |
| 認証/決済コード | **security-reviewer** - セキュリティ監査 |
| APIプロジェクト | **api-documenter** - OpenAPI生成 |
| パフォーマンスが重要 | **performance-analyzer** - ボトルネック検出 |
| フロントエンドが多い | **ui-reviewer** - アクセシビリティレビュー |
| テストが不足 | **test-writer** - テスト生成 |

#### E. プラグインの推奨

利用可能なプラグインは [references/plugins-reference.md](references/plugins-reference.md) を参照。

| コードベースのシグナル | 推奨プラグイン |
|-----------------|-------------|
| 一般的な生産性 | **anthropic-agent-skills** - コアスキルバンドル |
| ドキュメントワークフロー | docx、xlsx、pdfスキルをインストール |
| フロントエンド開発 | **frontend-design** プラグイン |
| AIツールを構築 | MCP開発向け **mcp-builder** |

### フェーズ3: 推奨レポートを出力する

推奨事項を明確にフォーマットする。**カテゴリごとに1〜2の推奨のみ含める** - この特定のコードベースに最も価値のあるものを。関連性のないカテゴリはスキップする。

```markdown
## Claude Code Automation推奨事項

コードベースを分析し、各カテゴリのトップオートメーションを特定しました。タイプごとのトップ1〜2の推奨は以下の通りです:

### コードベースプロファイル
- **タイプ**: [検出した言語/ランタイム]
- **フレームワーク**: [検出したフレームワーク]
- **主要ライブラリ**: [検出した関連ライブラリ]

---

### 🔌 MCPサーバー

#### context7
**理由**: [検出したライブラリに基づく具体的な理由]
**インストール**: `claude mcp add context7`

---

### 🎯 スキル

#### [スキル名]
**理由**: [具体的な理由]
**作成**: `.claude/skills/[name]/SKILL.md`
**呼び出し方**: ユーザーのみ / 両方 / Claudeのみ
**プラグインでも利用可能**: [plugin-name] プラグイン（該当する場合）
```yaml
---
name: [skill-name]
description: [何をするか]
disable-model-invocation: true  # ユーザーのみの場合
---
```

---

### ⚡ フック

#### [フック名]
**理由**: [検出した設定に基づく具体的な理由]
**場所**: `.claude/settings.json`

---

### 🤖 サブエージェント

#### [エージェント名]
**理由**: [コードベースパターンに基づく具体的な理由]
**場所**: `.claude/agents/[category]/[name].md`

---

**もっと欲しい場合は？** 特定のカテゴリの追加推奨事項を求めることができます（例: 「MCPサーバーのオプションをもっと見せて」「他にどんなフックが役立つ？」）。

**実装を手伝ってほしい場合は？** 気軽に聞いてください。上記の推奨事項のいずれかのセットアップをお手伝いできます。
```

## 決定フレームワーク

### MCPサーバーを推奨するタイミング
- 外部サービス統合が必要（データベース、API）
- ライブラリ/SDKのドキュメント参照
- ブラウザオートメーションまたはテスト
- チームツール統合（GitHub、Linear、Slack）
- クラウドインフラ管理

### スキルを推奨するタイミング

- ドキュメント生成（docx、xlsx、pptx、pdf — プラグインにも含まれる）
- 頻繁に繰り返すプロンプトやワークフロー
- 引数を持つプロジェクト固有のタスク
- テンプレートやスクリプトをタスクに適用（スキルはサポートファイルをバンドルできる）
- `/skill-name` で起動するクイックアクション
- 分離して実行すべきワークフロー（`context: fork`）

**呼び出しの制御:**
- `disable-model-invocation: true` — ユーザーのみ（副作用のため: デプロイ、コミット、送信）
- `user-invocable: false` — Claudeのみ（バックグラウンドの知識として）
- デフォルト（両方省略）— 両方が呼び出せる

### フックを推奨するタイミング
- 繰り返す編集後アクション（フォーマット、リント）
- 保護ルール（機密ファイルの編集ブロック）
- バリデーションチェック（テスト、型チェック）

### サブエージェントを推奨するタイミング
- 専門的な知識が必要（セキュリティ、パフォーマンス）
- 並行レビューワークフロー
- バックグラウンド品質チェック

### プラグインを推奨するタイミング
- 複数の関連スキルが必要
- 事前パッケージ化されたオートメーションバンドルが欲しい
- チーム全体での標準化

---

## 設定のヒント

### MCPサーバーの設定

**チーム共有**: `.mcp.json` をリポジトリにコミットして、チーム全体が同じMCPサーバーを使えるようにする

**デバッグ**: `--mcp-debug` フラグを使って設定の問題を特定する

**推奨する前提条件:**
- GitHub CLI（`gh`）- ネイティブなGitHub操作を有効にする
- Puppeteer/Playwright CLI - ブラウザMCPサーバー向け

### ヘッドレスモード（CI/オートメーション向け）

オートメーションパイプライン向けにヘッドレスClaudeを推奨する:

```bash
# プリコミットフックの例
claude -p "fix lint errors in src/" --allowedTools Edit,Write

# 構造化出力付きCIパイプライン
claude -p "<prompt>" --output-format stream-json | your_command
```

### フックの権限

`.claude/settings.json` で許可ツールを設定する:

```json
{
  "permissions": {
    "allow": ["Edit", "Write", "Bash(npm test:*)", "Bash(git commit:*)"]
  }
}
```
