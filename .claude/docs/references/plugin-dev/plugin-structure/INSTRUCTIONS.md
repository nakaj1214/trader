# Claude Codeのプラグイン構造

## 概要

Claude Codeプラグインは自動コンポーネント検出による標準化されたディレクトリ構造に従います。この構造を理解することで、Claude Codeにシームレスに統合する整理された維持可能なプラグインを作成できます。

**主要概念:**
- 自動検出のための慣習的なディレクトリレイアウト
- `.claude-plugin/plugin.json`でのマニフェスト駆動設定
- コンポーネントベースの整理（コマンド、エージェント、スキル、フック）
- `${CLAUDE_PLUGIN_ROOT}`を使用したポータブルなパス参照
- 明示的なvs.自動検出されたコンポーネントロード

## ディレクトリ構造

全Claude Codeプラグインは以下の組織パターンに従う:

```
plugin-name/
├── .claude-plugin/
│   └── plugin.json          # 必須: プラグインマニフェスト
├── commands/                 # スラッシュコマンド（.mdファイル）
├── agents/                   # サブエージェント定義（.mdファイル）
├── skills/                   # エージェントスキル（サブディレクトリ）
│   └── skill-name/
│       └── SKILL.md         # 各スキルに必須
├── hooks/
│   └── hooks.json           # イベントハンドラー設定
├── .mcp.json                # MCPサーバー定義
└── scripts/                 # ヘルパースクリプトとユーティリティ
```

**重要なルール:**

1. **マニフェストの場所**: `plugin.json`マニフェストは`.claude-plugin/`ディレクトリに**必ず**置く
2. **コンポーネントの場所**: 全コンポーネントディレクトリ（commands、agents、skills、hooks）はプラグインルートレベルに**必ず**置く（`.claude-plugin/`内にネストしない）
3. **オプションのコンポーネント**: プラグインが実際に使用するコンポーネントのみのディレクトリを作成する
4. **命名規則**: 全ディレクトリとファイル名にkebab-caseを使用する

## プラグインマニフェスト（plugin.json）

マニフェストはプラグインのメタデータと設定を定義する。`.claude-plugin/plugin.json`に配置:

### 必須フィールド

```json
{
  "name": "plugin-name"
}
```

**名前の要件:**
- kebab-caseフォーマットを使用（小文字とハイフン）
- インストール済みプラグイン間で一意
- スペースや特殊文字なし
- 例: `code-review-assistant`、`test-runner`、`api-docs`

### 推奨メタデータ

```json
{
  "name": "plugin-name",
  "version": "1.0.0",
  "description": "プラグインの目的の簡単な説明",
  "author": {
    "name": "著者名",
    "email": "author@example.com",
    "url": "https://example.com"
  },
  "homepage": "https://docs.example.com",
  "repository": "https://github.com/user/plugin-name",
  "license": "MIT",
  "keywords": ["testing", "automation", "ci-cd"]
}
```

**バージョンフォーマット**: セマンティックバージョニングに従う（MAJOR.MINOR.PATCH）
**キーワード**: プラグインの検出と分類のために使用

### コンポーネントパス設定

コンポーネントのカスタムパスを指定する（デフォルトディレクトリを補完）:

```json
{
  "name": "plugin-name",
  "commands": "./custom-commands",
  "agents": ["./agents", "./specialized-agents"],
  "hooks": "./config/hooks.json",
  "mcpServers": "./.mcp.json"
}
```

**重要**: カスタムパスはデフォルトを置き換えるのではなく補完する。デフォルトディレクトリとカスタムパスの両方のコンポーネントがロードされる。

**パスのルール:**
- プラグインルートからの相対パス
- `./`で始める
- 絶対パスは使用不可
- 複数の場所のための配列をサポート

## コンポーネントの整理

### コマンド

**場所**: `commands/`ディレクトリ
**フォーマット**: YAMLフロントマターを持つMarkdownファイル
**自動検出**: `commands/`内の全`.md`ファイルが自動的にロード

**構造の例**:
```
commands/
├── review.md        # /review コマンド
├── test.md          # /test コマンド
└── deploy.md        # /deploy コマンド
```

**ファイルフォーマット**:
```markdown
---
name: command-name
description: コマンドの説明
---

コマンド実装の指示...
```

**使用法**: コマンドはClaude Codeのネイティブスラッシュコマンドとして統合される

### エージェント

**場所**: `agents/`ディレクトリ
**フォーマット**: YAMLフロントマターを持つMarkdownファイル
**自動検出**: `agents/`内の全`.md`ファイルが自動的にロード

**構造の例**:
```
agents/
├── code-reviewer.md
├── test-generator.md
└── refactorer.md
```

**ファイルフォーマット**:
```markdown
---
description: エージェントの役割と専門知識
capabilities:
  - 特定のタスク1
  - 特定のタスク2
---

詳細なエージェントの指示と知識...
```

**使用法**: ユーザーがエージェントを手動で起動するか、Claude Codeがタスクコンテキストに基づいて自動的に選択する

### スキル

**場所**: スキルごとにサブディレクトリを持つ`skills/`ディレクトリ
**フォーマット**: 各スキルは`SKILL.md`ファイルを持つ独自のディレクトリ
**自動検出**: スキルサブディレクトリ内の全`SKILL.md`ファイルが自動的にロード

**構造の例**:
```
skills/
├── api-testing/
│   ├── SKILL.md
│   ├── scripts/
│   │   └── test-runner.py
│   └── references/
│       └── api-spec.md
└── database-migrations/
    ├── SKILL.md
    └── examples/
        └── migration-template.sql
```

**SKILL.mdフォーマット**:
```markdown
---
name: Skill Name
description: このスキルを使用するタイミング
version: 1.0.0
---

スキルの指示とガイダンス...
```

**サポートファイル**: スキルはサブディレクトリにスクリプト、リファレンス、例、アセットを含めることができる

**使用法**: Claude Codeはdescriptionに一致するタスクコンテキストに基づいてスキルを自律的にアクティベートする

### フック

**場所**: `hooks/hooks.json`またはplugin.jsonにインライン
**フォーマット**: イベントハンドラーを定義するJSON設定
**登録**: プラグインが有効になると自動的にフックが登録される

**構造の例**:
```
hooks/
├── hooks.json           # フック設定
└── scripts/
    ├── validate.sh      # フックスクリプト
    └── check-style.sh   # フックスクリプト
```

**設定フォーマット**:
```json
{
  "PreToolUse": [{
    "matcher": "Write|Edit",
    "hooks": [{
      "type": "command",
      "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/validate.sh",
      "timeout": 30
    }]
  }]
}
```

**利用可能なイベント**: PreToolUse、PostToolUse、Stop、SubagentStop、SessionStart、SessionEnd、UserPromptSubmit、PreCompact、Notification

### MCPサーバー

**場所**: プラグインルートの`.mcp.json`またはplugin.jsonにインライン
**フォーマット**: MCPサーバー定義のJSON設定
**自動起動**: プラグインが有効になると自動的にサーバーが起動

**フォーマット例**:
```json
{
  "mcpServers": {
    "server-name": {
      "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/servers/server.js"],
      "env": {
        "API_KEY": "${API_KEY}"
      }
    }
  }
}
```

**使用法**: MCPサーバーはClaude Codeのツールシステムとシームレスに統合される

## ポータブルなパス参照

### ${CLAUDE_PLUGIN_ROOT}

全プラグイン内パス参照に`${CLAUDE_PLUGIN_ROOT}`環境変数を使用する:

```json
{
  "command": "bash ${CLAUDE_PLUGIN_ROOT}/scripts/run.sh"
}
```

**重要な理由**: プラグインはインストール方法によって異なる場所にインストールされる:
- ユーザーのインストール方法（マーケットプレイス、ローカル、npm）
- OSの規則
- ユーザーの好み

**使用する場所**:
- フックコマンドパス
- MCPサーバーコマンド引数
- スクリプト実行の参照
- リソースファイルパス

**使用しないこと**:
- ハードコードされた絶対パス（`/Users/name/plugins/...`）
- 作業ディレクトリからの相対パス（コマンドの`./scripts/...`）
- ホームディレクトリのショートカット（`~/plugins/...`）

## ファイル命名規則

### コンポーネントファイル

**コマンド**: kebab-caseの`.md`ファイル
- `code-review.md` → `/code-review`
- `run-tests.md` → `/run-tests`
- `api-docs.md` → `/api-docs`

**エージェント**: 役割を説明するkebab-caseの`.md`ファイル
- `test-generator.md`
- `code-reviewer.md`
- `performance-analyzer.md`

**スキル**: kebab-caseのディレクトリ名
- `api-testing/`
- `database-migrations/`
- `error-handling/`

### サポートファイル

**スクリプト**: 適切な拡張子を持つ説明的なkebab-caseの名前
- `validate-input.sh`
- `generate-report.py`
- `process-data.js`

**ドキュメント**: kebab-caseのMarkdownファイル
- `api-reference.md`
- `migration-guide.md`
- `best-practices.md`

**設定**: 標準名を使用
- `hooks.json`
- `.mcp.json`
- `plugin.json`

## 自動検出メカニズム

Claude Codeはコンポーネントを自動的に検出してロードする:

1. **プラグインマニフェスト**: プラグインが有効になった時に`.claude-plugin/plugin.json`を読む
2. **コマンド**: `.md`ファイルの`commands/`ディレクトリをスキャン
3. **エージェント**: `.md`ファイルの`agents/`ディレクトリをスキャン
4. **スキル**: `SKILL.md`を含むサブディレクトリの`skills/`をスキャン
5. **フック**: `hooks/hooks.json`またはマニフェストから設定をロード
6. **MCPサーバー**: `.mcp.json`またはマニフェストから設定をロード

**検出のタイミング**:
- プラグインインストール: コンポーネントがClaude Codeに登録される
- プラグイン有効化: コンポーネントが使用可能になる
- 再起動不要: 変更は次のClaude Codeセッションで有効になる

## ベストプラクティス

### 整理

1. **論理的なグループ化**: 関連するコンポーネントをまとめる
   - テスト関連のコマンド、エージェント、スキルをまとめる
   - `scripts/`に異なる目的のためのサブディレクトリを作成

2. **最小限のマニフェスト**: `plugin.json`をリーンに保つ
   - 必要な時のみカスタムパスを指定
   - 標準レイアウトの自動検出に依存する

3. **ドキュメント**: READMEファイルを含める
   - プラグインルート: 全体的な目的と使用法
   - コンポーネントディレクトリ: 具体的なガイダンス
   - スクリプトディレクトリ: 使用法と要件

### 命名

1. **一貫性**: コンポーネント全体で一貫した命名を使用
   - コマンドが`test-runner`なら、関連エージェントは`test-runner-agent`
   - スキルディレクトリ名はその目的に一致させる

2. **明確性**: 目的を示す説明的な名前を使用
   - 良い: `api-integration-testing/`、`code-quality-checker.md`
   - 避ける: `utils/`、`misc.md`、`temp.sh`

### ポータビリティ

1. **常に${CLAUDE_PLUGIN_ROOT}を使用**: パスをハードコードしない
2. **複数のシステムでテスト**: macOS、Linux、Windowsで確認
3. **依存関係を文書化**: 必要なツールとバージョンを一覧表示
4. **システム固有の機能を避ける**: ポータブルなbash/Pythonの構造を使用

## 一般的なパターン

### 最小限プラグイン

依存関係のない単一コマンド:
```
my-plugin/
├── .claude-plugin/
│   └── plugin.json    # nameフィールドのみ
└── commands/
    └── hello.md       # 単一コマンド
```

### フル機能プラグイン

全コンポーネントタイプを持つ完全なプラグイン:
```
my-plugin/
├── .claude-plugin/
│   └── plugin.json
├── commands/          # ユーザー向けコマンド
├── agents/            # 特殊サブエージェント
├── skills/            # 自動アクティベートスキル
├── hooks/             # イベントハンドラー
│   ├── hooks.json
│   └── scripts/
├── .mcp.json          # 外部統合
└── scripts/           # 共有ユーティリティ
```

### スキル重視プラグイン

スキルのみを提供するプラグイン:
```
my-plugin/
├── .claude-plugin/
│   └── plugin.json
└── skills/
    ├── skill-one/
    │   └── SKILL.md
    └── skill-two/
        └── SKILL.md
```

## トラブルシューティング

**コンポーネントがロードされない**:
- ファイルが正しいディレクトリに正しい拡張子で存在するか確認
- YAMLフロントマターの構文を確認（コマンド、エージェント、スキル）
- スキルに`SKILL.md`があるか確認（`README.md`や他の名前ではなく）
- プラグインがClaude Code設定で有効になっているか確認

**パス解決エラー**:
- 全ハードコードされたパスを`${CLAUDE_PLUGIN_ROOT}`に置き換える
- マニフェストのパスが相対パスで`./`で始まるか確認
- 指定されたパスに参照ファイルが存在するか確認
- フックスクリプトで`echo $CLAUDE_PLUGIN_ROOT`でテスト

**自動検出が機能しない**:
- ディレクトリがプラグインルートにあることを確認（`.claude-plugin/`内にネストしない）
- ファイル命名が規則に従っているか確認（kebab-case、正しい拡張子）
- マニフェストのカスタムパスが正しいか確認
- プラグイン設定をリロードするためにClaude Codeを再起動

---

詳細な例と高度なパターンについては、`references/`と`examples/`ディレクトリのファイルを参照。
