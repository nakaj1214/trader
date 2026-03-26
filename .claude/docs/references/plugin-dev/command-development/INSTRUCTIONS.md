# Claude Codeのコマンド開発

## 概要

スラッシュコマンドは、インタラクティブセッション中にClaudeが実行するMarkdownファイルとして定義された頻繁に使用されるプロンプトです。コマンド構造、フロントマターオプション、動的機能を理解することで、強力で再利用可能なワークフローを作成できます。

**主要概念:**
- コマンド用のMarkdownファイル形式
- 設定用のYAMLフロントマター
- 動的引数とファイル参照
- コンテキストのためのBash実行
- コマンドの整理と名前空間

## コマンドの基礎

### スラッシュコマンドとは？

スラッシュコマンドは、起動時にClaudeが実行するプロンプトを含むMarkdownファイルです。コマンドは以下を提供します:
- **再利用性**: 一度定義して繰り返し使用
- **一貫性**: 共通ワークフローの標準化
- **共有**: チームやプロジェクト全体への配布
- **効率性**: 複雑なプロンプトへの素早いアクセス

### 重要: コマンドはClaudeへの指示

**コマンドはエージェントが消費するために書かれており、人間が消費するためではない。**

ユーザーが`/command-name`を起動すると、コマンドの内容がClaudeの指示になる。コマンドはClaudeに何をすべきかの指示として書く。ユーザーへのメッセージとして書かない。

**正しいアプローチ（Claudeへの指示）:**
```markdown
以下を含むセキュリティ脆弱性についてこのコードをレビューする:
- SQLインジェクション
- XSS攻撃
- 認証の問題

具体的な行番号と重大度評価を提供する。
```

**間違ったアプローチ（ユーザーへのメッセージ）:**
```markdown
このコマンドはセキュリティの問題についてコードをレビューします。
脆弱性の詳細を含むレポートを受け取ります。
```

最初の例はClaudeに何をすべきかを伝えている。2番目はユーザーに何が起こるかを伝えるがClaudeに指示していない。常に最初のアプローチを使用すること。

### コマンドの場所

**プロジェクトコマンド**（チームと共有）:
- 場所: `.claude/commands/`
- スコープ: 特定のプロジェクトで利用可能
- ラベル: `/help`で「(project)」と表示
- 用途: チームワークフロー、プロジェクト固有のタスク

**個人コマンド**（どこでも利用可能）:
- 場所: `~/.claude/commands/`
- スコープ: 全プロジェクトで利用可能
- ラベル: `/help`で「(user)」と表示
- 用途: 個人ワークフロー、クロスプロジェクトのユーティリティ

**プラグインコマンド**（プラグインにバンドル）:
- 場所: `plugin-name/commands/`
- スコープ: プラグインインストール時に利用可能
- ラベル: `/help`で「(plugin-name)」と表示
- 用途: プラグイン固有の機能

## ファイル形式

### 基本構造

コマンドは`.md`拡張子を持つMarkdownファイルです:

```
.claude/commands/
├── review.md           # /review コマンド
├── test.md             # /test コマンド
└── deploy.md           # /deploy コマンド
```

**シンプルなコマンド:**
```markdown
以下を含むセキュリティ脆弱性についてこのコードをレビューする:
- SQLインジェクション
- XSS攻撃
- 認証バイパス
- 安全でないデータ処理
```

基本的なコマンドにはフロントマターは不要。

### YAMLフロントマターあり

YAMLフロントマターを使用して設定を追加する:

```markdown
---
description: コードのセキュリティ問題をレビュー
allowed-tools: Read, Grep, Bash(git:*)
model: sonnet
---

このコードのセキュリティ脆弱性をレビューする...
```

## YAMLフロントマターフィールド

### description

**目的:** `/help`に表示される簡単な説明
**型:** 文字列
**デフォルト:** コマンドプロンプトの最初の行

```yaml
---
description: コードレビューのPRを確認
---
```

**ベストプラクティス:** 明確で実用的な説明（60文字以下）

### allowed-tools

**目的:** コマンドが使用できるツールを指定
**型:** 文字列または配列
**デフォルト:** 会話から継承

```yaml
---
allowed-tools: Read, Write, Edit, Bash(git:*)
---
```

**パターン:**
- `Read, Write, Edit` - 特定のツール
- `Bash(git:*)` - gitコマンドのみのBash
- `*` - 全ツール（まれに必要）

**使用時:** コマンドに特定のツールアクセスが必要な場合

### model

**目的:** コマンド実行のモデルを指定
**型:** 文字列（sonnet、opus、haiku）
**デフォルト:** 会話から継承

```yaml
---
model: haiku
---
```

**ユースケース:**
- `haiku` - 高速、シンプルなコマンド
- `sonnet` - 標準ワークフロー
- `opus` - 複雑な分析

### argument-hint

**目的:** オートコンプリート用の期待される引数を文書化
**型:** 文字列
**デフォルト:** なし

```yaml
---
argument-hint: [pr-number] [priority] [assignee]
---
```

**メリット:**
- ユーザーがコマンド引数を理解するのに役立つ
- コマンドの発見性を向上させる
- コマンドインターフェースを文書化する

### disable-model-invocation

**目的:** SlashCommandツールがコマンドをプログラムで呼び出すことを防ぐ
**型:** ブール値
**デフォルト:** false

```yaml
---
disable-model-invocation: true
---
```

**使用時:** コマンドが手動でのみ起動されるべき場合

## 動的引数

### $ARGUMENTSの使用

全引数を単一文字列として取得:

```markdown
---
description: 番号で問題を修正
argument-hint: [issue-number]
---

コーディング標準とベストプラクティスに従って問題 #$ARGUMENTS を修正する。
```

**使用例:**
```
> /fix-issue 123
> /fix-issue 456
```

### 位置引数の使用

`$1`、`$2`、`$3`などで個々の引数を取得:

```markdown
---
description: 優先度と担当者でPRをレビュー
argument-hint: [pr-number] [priority] [assignee]
---

優先度レベル $2 でプルリクエスト #$1 をレビューする。
レビュー後、フォローアップのために $3 に割り当てる。
```

**使用例:**
```
> /review-pr 123 high alice
```

**展開後:**
```
優先度レベル high でプルリクエスト #123 をレビューする。
レビュー後、フォローアップのために alice に割り当てる。
```

### 引数の組み合わせ

位置引数と残りの引数を混ぜる:

```markdown
$1 を $2 環境にオプション付きでデプロイする: $3
```

**使用例:**
```
> /deploy api staging --force --skip-tests
```

**展開後:**
```
api を staging 環境にオプション付きでデプロイする: --force --skip-tests
```

## ファイル参照

### @構文の使用

コマンドにファイルの内容を含める:

```markdown
---
description: 特定のファイルをレビュー
argument-hint: [file-path]
---

@$1 を以下の観点でレビューする:
- コード品質
- ベストプラクティス
- 潜在的なバグ
```

**使用例:**
```
> /review-file src/api/users.ts
```

**効果:** コマンドを処理する前にClaudeが`src/api/users.ts`を読む

### 複数のファイル参照

複数のファイルを参照する:

```markdown
@src/old-version.js と @src/new-version.js を比較する

識別する:
- 破壊的変更
- 新機能
- バグ修正
```

### 静的ファイル参照

引数なしで既知のファイルを参照する:

```markdown
@package.json と @tsconfig.json の一貫性をレビューする

確認する:
- TypeScriptのバージョンが一致しているか
- 依存関係が整合しているか
- ビルド設定が正しいか
```

## コマンドでのBash実行

コマンドはインラインでbashコマンドを実行して、Claudeがコマンドを処理する前に動的にコンテキストを収集できます。これはリポジトリの状態、環境情報、またはプロジェクト固有のコンテキストを含めるのに役立ちます。

**使用時:**
- 動的なコンテキストを含める（git状態、環境変数など）
- プロジェクト/リポジトリの状態を収集する
- コンテキスト対応のワークフローを構築する

**実装の詳細:**
完全な構文、例、ベストプラクティスについては、`references/plugin-features-reference.md`のbash実行セクションを参照。

## コマンドの整理

### フラット構造

小さなコマンドセット用の単純な整理:

```
.claude/commands/
├── build.md
├── test.md
├── deploy.md
├── review.md
└── docs.md
```

**使用時:** 5〜15のコマンド、明確なカテゴリなし

### 名前空間構造

サブディレクトリでコマンドを整理する:

```
.claude/commands/
├── ci/
│   ├── build.md        # /build (project:ci)
│   ├── test.md         # /test (project:ci)
│   └── lint.md         # /lint (project:ci)
├── git/
│   ├── commit.md       # /commit (project:git)
│   └── pr.md           # /pr (project:git)
└── docs/
    ├── generate.md     # /generate (project:docs)
    └── publish.md      # /publish (project:docs)
```

**メリット:**
- カテゴリ別の論理的なグループ
- `/help`に名前空間が表示
- 関連コマンドを見つけやすい

**使用時:** 15以上のコマンド、明確なカテゴリあり

## ベストプラクティス

### コマンド設計

1. **単一責任:** 1つのコマンド、1つのタスク
2. **明確な説明:** `/help`で自己説明的
3. **明示的な依存関係:** 必要な時は`allowed-tools`を使用
4. **引数を文書化:** 常に`argument-hint`を提供
5. **一貫した命名:** 動詞-名詞パターンを使用（review-pr、fix-issue）

### 引数処理

1. **引数を検証する:** プロンプトで必須引数を確認する
2. **デフォルトを提供する:** 引数がない場合のデフォルトを提案
3. **フォーマットを文書化:** 期待される引数フォーマットを説明
4. **エッジケースを処理:** 欠落または無効な引数を考慮

### ファイル参照

1. **明示的なパス:** 明確なファイルパスを使用
2. **存在を確認:** 欠落ファイルを丁寧に処理
3. **相対パス:** プロジェクト相対パスを使用
4. **Globサポート:** パターンにGlobツールの使用を検討

### Bashコマンド

1. **スコープを制限:** `Bash(*)`ではなく`Bash(git:*)`を使用
2. **安全なコマンド:** 破壊的な操作を避ける
3. **エラーを処理:** コマンド失敗を考慮
4. **高速に保つ:** 長時間実行コマンドは起動を遅くする

### ドキュメント

1. **コメントを追加:** 複雑なロジックを説明
2. **例を提供:** コメントに使用例を示す
3. **要件を一覧表示:** 依存関係を文書化
4. **コマンドをバージョン管理:** 破壊的変更を記録

```markdown
---
description: アプリケーションを環境にデプロイ
argument-hint: [environment] [version]
---

<!--
使用法: /deploy [staging|production] [version]
必要条件: AWSの認証情報が設定されていること
例: /deploy staging v1.2.3
-->

バージョン $2 を使用してアプリケーションを $1 環境にデプロイする...
```

## 一般的なパターン

### レビューパターン

```markdown
---
description: コード変更をレビュー
allowed-tools: Read, Bash(git:*)
---

変更されたファイル: !`git diff --name-only`

各ファイルを以下の観点でレビューする:
1. コード品質とスタイル
2. 潜在的なバグや問題
3. テストカバレッジ
4. ドキュメントの必要性

各ファイルに対して具体的なフィードバックを提供する。
```

### テストパターン

```markdown
---
description: 特定のファイルのテストを実行
argument-hint: [test-file]
allowed-tools: Bash(npm:*)
---

テストを実行: !`npm test $1`

結果を分析し、失敗の修正を提案する。
```

### ドキュメントパターン

```markdown
---
description: ファイルのドキュメントを生成
argument-hint: [source-file]
---

@$1 の包括的なドキュメントを生成する（以下を含む）:
- 関数/クラスの説明
- パラメータのドキュメント
- 戻り値の説明
- 使用例
- エッジケースとエラー
```

### ワークフローパターン

```markdown
---
description: 完全なPRワークフロー
argument-hint: [pr-number]
allowed-tools: Bash(gh:*), Read
---

PR #$1 ワークフロー:

1. PRを取得: !`gh pr view $1`
2. 変更をレビュー
3. チェックを実行
4. 承認または変更リクエスト
```

## トラブルシューティング

**コマンドが表示されない:**
- ファイルが正しいディレクトリにあるか確認
- `.md`拡張子があるか確認
- 有効なMarkdown形式を確認
- Claude Codeを再起動

**引数が機能しない:**
- `$1`、`$2`の構文が正しいか確認
- `argument-hint`が使用法と一致しているか確認
- 余分なスペースがないか確認

**Bash実行が失敗する:**
- `allowed-tools`にBashが含まれているか確認
- バッククォート内のコマンド構文を確認
- ターミナルでコマンドを最初にテスト
- 必要な権限を確認

**ファイル参照が機能しない:**
- `@`構文が正しいか確認
- ファイルパスが有効か確認
- Readツールが許可されているか確認
- 絶対パスまたはプロジェクト相対パスを使用

## プラグイン固有の機能

### CLAUDE_PLUGIN_ROOT変数

プラグインコマンドは`${CLAUDE_PLUGIN_ROOT}`にアクセスでき、プラグインの絶対パスに解決される環境変数。

**目的:**
- プラグインファイルをポータブルに参照
- プラグインスクリプトを実行
- プラグイン設定をロード
- プラグインテンプレートにアクセス

**基本的な使用法:**

```markdown
---
description: プラグインスクリプトを使用して分析
allowed-tools: Bash(node:*)
---

分析を実行: !`node ${CLAUDE_PLUGIN_ROOT}/scripts/analyze.js $1`

結果をレビューして発見事項を報告する。
```

**一般的なパターン:**

```markdown
# プラグインスクリプトを実行
!`bash ${CLAUDE_PLUGIN_ROOT}/scripts/script.sh`

# プラグイン設定をロード
@${CLAUDE_PLUGIN_ROOT}/config/settings.json

# プラグインテンプレートを使用
@${CLAUDE_PLUGIN_ROOT}/templates/report.md

# プラグインリソースにアクセス
@${CLAUDE_PLUGIN_ROOT}/docs/reference.md
```

**使用する理由:**
- 全インストールで機能する
- システム間でポータブル
- ハードコードされたパス不要
- マルチファイルプラグインに必須

### プラグインコマンドの整理

プラグインコマンドは`commands/`ディレクトリから自動的に検出される:

```
plugin-name/
├── commands/
│   ├── foo.md              # /foo (plugin:plugin-name)
│   ├── bar.md              # /bar (plugin:plugin-name)
│   └── utils/
│       └── helper.md       # /helper (plugin:plugin-name:utils)
└── plugin.json
```

## プラグインコンポーネントとの統合

### エージェント統合

複雑なタスクのためにプラグインエージェントを起動する:

```markdown
---
description: 詳細なコードレビュー
argument-hint: [file-path]
---

code-reviewerエージェントを使用して @$1 の包括的なレビューを開始する。

エージェントは以下を分析する:
- コード構造
- セキュリティの問題
- パフォーマンス
- ベストプラクティス

エージェントはプラグインリソースを使用する:
- ${CLAUDE_PLUGIN_ROOT}/config/rules.json
- ${CLAUDE_PLUGIN_ROOT}/checklists/review.md
```

### スキル統合

特殊な知識のためにプラグインスキルを活用する:

```markdown
---
description: 標準でAPIをドキュメント化
argument-hint: [api-file]
---

プラグイン標準に従って @$1 のAPIをドキュメント化する。

api-docs-standardsスキルを使用して以下を確認する:
- 完全なエンドポイントドキュメント
- 一貫したフォーマット
- サンプルの品質
- エラードキュメント

本番対応のAPIドキュメントを生成する。
```

### マルチコンポーネントワークフロー

エージェント、スキル、スクリプトを組み合わせる:

```markdown
---
description: 包括的なレビューワークフロー
argument-hint: [file]
allowed-tools: Bash(node:*), Read
---

対象: @$1

フェーズ1 - 静的分析:
!`node ${CLAUDE_PLUGIN_ROOT}/scripts/lint.js $1`

フェーズ2 - 詳細レビュー:
詳細な分析のためにcode-reviewerエージェントを起動する。

フェーズ3 - 標準チェック:
検証のためにcoding-standardsスキルを使用する。

フェーズ4 - レポート:
テンプレート: @${CLAUDE_PLUGIN_ROOT}/templates/review.md

テンプレートに従って発見事項をレポートにまとめる。
```

## バリデーションパターン

### 引数バリデーション

```markdown
---
description: 検証付きでデプロイ
argument-hint: [environment]
---

環境を検証: !`echo "$1" | grep -E "^(dev|staging|prod)$" || echo "INVALID"`

$1 が有効な環境の場合:
  $1 にデプロイ
そうでない場合:
  有効な環境を説明: dev、staging、prod
  使用法を表示: /deploy [environment]
```

### ファイル存在チェック

```markdown
---
description: 設定を処理
argument-hint: [config-file]
---

ファイルの存在を確認: !`test -f $1 && echo "EXISTS" || echo "MISSING"`

ファイルが存在する場合:
  設定を処理: @$1
そうでない場合:
  設定ファイルの配置場所を説明
  期待されるフォーマットを表示
  設定例を提供
```

---

詳細なフロントマターフィールドの仕様については`references/frontmatter-reference.md`を参照。
プラグイン固有の機能とパターンについては`references/plugin-features-reference.md`を参照。
コマンドパターンの例については`examples/`ディレクトリを参照。
