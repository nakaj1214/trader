# プラグインマニフェストリファレンス

`plugin.json` 設定の完全なリファレンスです。

## ファイルの場所

**必須パス**: `.claude-plugin/plugin.json`

マニフェストはプラグインルートの `.claude-plugin/` ディレクトリに配置する必要があります。正しい場所にこのファイルがないと、Claude Code はプラグインを認識しません。

## 完全なフィールドリファレンス

### コアフィールド

#### name（必須）

**型**: String
**フォーマット**: kebab-case
**例**: `"test-automation-suite"`

プラグインの一意の識別子。以下に使用されます:
- Claude Code でのプラグイン識別
- 他のプラグインとの競合検出
- コマンドの名前空間（オプション）

**要件**:
- インストールされたすべてのプラグイン間で一意
- 小文字、数字、ハイフンのみ使用
- スペースや特殊文字なし
- 文字で始まる
- 文字または数字で終わる

**バリデーション**:
```javascript
/^[a-z][a-z0-9]*(-[a-z0-9]+)*$/
```

**例**:
- 良い例: `api-tester`, `code-review`, `git-workflow-automation`
- 悪い例: `API Tester`, `code_review`, `-git-workflow`, `test-`

#### version

**型**: String
**フォーマット**: セマンティックバージョニング（MAJOR.MINOR.PATCH）
**例**: `"2.1.0"`
**デフォルト**: 未指定の場合 `"0.1.0"`

セマンティックバージョニングのガイドライン:
- **MAJOR**: 互換性のない API 変更、破壊的変更
- **MINOR**: 新機能、後方互換性あり
- **PATCH**: バグ修正、後方互換性あり

**プレリリースバージョン**:
- `"1.0.0-alpha.1"` - アルファリリース
- `"1.0.0-beta.2"` - ベータリリース
- `"1.0.0-rc.1"` - リリース候補

**例**:
- `"0.1.0"` - 初期開発
- `"1.0.0"` - 最初の安定リリース
- `"1.2.3"` - 1.2 へのパッチ更新
- `"2.0.0"` - 破壊的変更を含むメジャーバージョン

#### description

**型**: String
**長さ**: 50〜200文字推奨
**例**: `"Automates code review workflows with style checks and automated feedback"`

プラグインの目的と機能の簡潔な説明。

**ベストプラクティス**:
- プラグインの「何をするか」に焦点を当て、「どうやるか」ではない
- 能動態を使用
- 主な機能やメリットに言及
- マーケットプレイス表示のため200文字以内に抑える

**例**:
- 良い例: "Generates comprehensive test suites from code analysis and coverage reports"
- 良い例: "Integrates with Jira for automatic issue tracking and sprint management"
- 悪い例: "A plugin that helps you do testing stuff"
- 悪い例: "This is a very long description that goes on and on about every single feature..."

### メタデータフィールド

#### author

**型**: Object
**フィールド**: name（必須）、email（オプション）、url（オプション）

```json
{
  "author": {
    "name": "Jane Developer",
    "email": "jane@example.com",
    "url": "https://janedeveloper.com"
  }
}
```

**代替フォーマット**（文字列のみ）:
```json
{
  "author": "Jane Developer <jane@example.com> (https://janedeveloper.com)"
}
```

**ユースケース**:
- クレジットと帰属
- サポートや質問の連絡先
- マーケットプレイスでの表示
- コミュニティでの認知

#### homepage

**型**: String（URL）
**例**: `"https://docs.example.com/plugins/my-plugin"`

プラグインのドキュメントまたはランディングページへのリンク。

**リンク先**:
- プラグインドキュメントサイト
- プロジェクトホームページ
- 詳細な使用ガイド
- インストール手順

**リンクしないもの**:
- ソースコード（`repository` フィールドを使用）
- イシュートラッカー（ドキュメントに含める）
- 個人ウェブサイト（`author.url` を使用）

#### repository

**型**: String（URL）または Object
**例**: `"https://github.com/user/plugin-name"`

ソースコードリポジトリの場所。

**文字列フォーマット**:
```json
{
  "repository": "https://github.com/user/plugin-name"
}
```

**オブジェクトフォーマット**（詳細）:
```json
{
  "repository": {
    "type": "git",
    "url": "https://github.com/user/plugin-name.git",
    "directory": "packages/plugin-name"
  }
}
```

**ユースケース**:
- ソースコードへのアクセス
- イシューの報告
- コミュニティへの貢献
- 透明性と信頼

#### license

**型**: String
**フォーマット**: SPDX 識別子
**例**: `"MIT"`

ソフトウェアライセンスの識別子。

**一般的なライセンス**:
- `"MIT"` - 寛容、人気のある選択肢
- `"Apache-2.0"` - 特許許諾付きの寛容ライセンス
- `"GPL-3.0"` - コピーレフト
- `"BSD-3-Clause"` - 寛容
- `"ISC"` - 寛容、MIT に類似
- `"UNLICENSED"` - プロプライエタリ、非オープンソース

**完全なリスト**: https://spdx.org/licenses/

**複数ライセンス**:
```json
{
  "license": "(MIT OR Apache-2.0)"
}
```

#### keywords

**型**: 文字列の配列
**例**: `["testing", "automation", "ci-cd", "quality-assurance"]`

プラグインの発見とカテゴリ分けのためのタグ。

**ベストプラクティス**:
- 5〜10 キーワードを使用
- 機能カテゴリを含める
- テクノロジー名を追加
- 一般的な検索用語を使用
- プラグイン名の重複を避ける

**考慮するカテゴリ**:
- 機能: `testing`, `debugging`, `documentation`, `deployment`
- テクノロジー: `typescript`, `python`, `docker`, `aws`
- ワークフロー: `ci-cd`, `code-review`, `git-workflow`
- ドメイン: `web-development`, `data-science`, `devops`

### コンポーネントパスフィールド

#### commands

**型**: String または文字列の配列
**デフォルト**: `["./commands"]`
**例**: `"./cli-commands"`

コマンド定義を含む追加のディレクトリまたはファイル。

**単一パス**:
```json
{
  "commands": "./custom-commands"
}
```

**複数パス**:
```json
{
  "commands": [
    "./commands",
    "./admin-commands",
    "./experimental-commands"
  ]
}
```

**動作**: デフォルトの `commands/` ディレクトリを補完する（置き換えではない）

**ユースケース**:
- カテゴリ別のコマンド整理
- 安定版と実験版のコマンド分離
- 共有場所からのコマンド読み込み

#### agents

**型**: String または文字列の配列
**デフォルト**: `["./agents"]`
**例**: `"./specialized-agents"`

エージェント定義を含む追加のディレクトリまたはファイル。

**フォーマット**: `commands` フィールドと同じ

**ユースケース**:
- 専門分野ごとのエージェントグループ化
- 汎用エージェントとタスク固有エージェントの分離
- プラグイン依存関係からのエージェント読み込み

#### hooks

**型**: String（JSON ファイルへのパス）または Object（インライン設定）
**デフォルト**: `"./hooks/hooks.json"`

フック設定の場所またはインライン定義。

**ファイルパス**:
```json
{
  "hooks": "./config/hooks.json"
}
```

**インライン設定**:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/scripts/validate.sh",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

**ユースケース**:
- シンプルなプラグイン: インライン設定（50行未満）
- 複雑なプラグイン: 外部 JSON ファイル
- 複数のフックセット: 異なるコンテキスト用の個別ファイル

#### mcpServers

**型**: String（JSON ファイルへのパス）または Object（インライン設定）
**デフォルト**: `./.mcp.json`

MCP サーバー設定の場所またはインライン定義。

**ファイルパス**:
```json
{
  "mcpServers": "./.mcp.json"
}
```

**インライン設定**:
```json
{
  "mcpServers": {
    "github": {
      "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/servers/github-mcp.js"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    }
  }
}
```

**ユースケース**:
- シンプルなプラグイン: 単一のインラインサーバー（20行未満）
- 複雑なプラグイン: 外部 `.mcp.json` ファイル
- 複数サーバー: 常に外部ファイルを使用

## パス解決

### 相対パスルール

コンポーネントフィールドのすべてのパスは以下のルールに従う必要があります:

1. **相対パスでなければならない**: 絶対パスは不可
2. **`./` で始まる必要がある**: プラグインルートからの相対を示す
3. **`../` は使用不可**: 親ディレクトリへのナビゲーション不可
4. **スラッシュのみ**: Windows でもフォワードスラッシュ

**例**:
- 良い例: `"./commands"`
- 良い例: `"./src/commands"`
- 良い例: `"./configs/hooks.json"`
- 悪い例: `"/Users/name/plugin/commands"`
- 悪い例: `"commands"`（`./` がない）
- 悪い例: `"../shared/commands"`
- 悪い例: `".\\commands"`（バックスラッシュ）

### 解決順序

Claude Code がコンポーネントを読み込む際:

1. **デフォルトディレクトリ**: まず標準の場所をスキャン
   - `./commands/`
   - `./agents/`
   - `./skills/`
   - `./hooks/hooks.json`
   - `./.mcp.json`

2. **カスタムパス**: マニフェストで指定されたパスをスキャン
   - `commands` フィールドのパス
   - `agents` フィールドのパス
   - `hooks` と `mcpServers` フィールドのファイル

3. **マージ動作**: すべての場所のコンポーネントが読み込まれる
   - 上書きなし
   - 検出されたすべてのコンポーネントが登録
   - 名前の競合はエラーになる

## バリデーション

### マニフェストのバリデーション

Claude Code はプラグイン読み込み時にマニフェストをバリデーションします:

**構文バリデーション**:
- 有効な JSON フォーマット
- 構文エラーなし
- 正しいフィールド型

**フィールドバリデーション**:
- `name` フィールドが存在し有効なフォーマット
- `version` がセマンティックバージョニングに従う（存在する場合）
- パスが `./` プレフィックス付きの相対パス
- URL が有効（存在する場合）

**コンポーネントバリデーション**:
- 参照されたパスが存在
- フックと MCP の設定が有効
- 循環依存関係がない

### よくあるバリデーションエラー

**無効な名前フォーマット**:
```json
{
  "name": "My Plugin"  // スペースを含む
}
```
修正: kebab-case を使用
```json
{
  "name": "my-plugin"  // 正しい
}
```

**絶対パス**:
```json
{
  "commands": "/Users/name/commands"  // 絶対パス
}
```
修正: 相対パスを使用
```json
{
  "commands": "./commands"  // 正しい
}
```

**`./` プレフィックスの欠落**:
```json
{
  "hooks": "hooks/hooks.json"  // ./ がない
}
```
修正: ./ プレフィックスを追加
```json
{
  "hooks": "./hooks/hooks.json"  // 正しい
}
```

**無効なバージョン**:
```json
{
  "version": "1.0"  // セマンティックバージョニングではない
}
```
修正: MAJOR.MINOR.PATCH を使用
```json
{
  "version": "1.0.0"  // 正しい
}
```

## 最小限 vs. 完全な例

### 最小限のプラグイン

動作するプラグインの最低限:

```json
{
  "name": "hello-world"
}
```

完全にデフォルトのディレクトリ検出に依存します。

### 推奨プラグイン

配布用の良いメタデータ:

```json
{
  "name": "code-review-assistant",
  "version": "1.0.0",
  "description": "Automates code review with style checks and suggestions",
  "author": {
    "name": "Jane Developer",
    "email": "jane@example.com"
  },
  "homepage": "https://docs.example.com/code-review",
  "repository": "https://github.com/janedev/code-review-assistant",
  "license": "MIT",
  "keywords": ["code-review", "automation", "quality", "ci-cd"]
}
```

### 完全なプラグイン

すべての機能を備えた完全な設定:

```json
{
  "name": "enterprise-devops",
  "version": "2.3.1",
  "description": "Comprehensive DevOps automation for enterprise CI/CD pipelines",
  "author": {
    "name": "DevOps Team",
    "email": "devops@company.com",
    "url": "https://company.com/devops"
  },
  "homepage": "https://docs.company.com/plugins/devops",
  "repository": {
    "type": "git",
    "url": "https://github.com/company/devops-plugin.git"
  },
  "license": "Apache-2.0",
  "keywords": [
    "devops",
    "ci-cd",
    "automation",
    "kubernetes",
    "docker",
    "deployment"
  ],
  "commands": [
    "./commands",
    "./admin-commands"
  ],
  "agents": "./specialized-agents",
  "hooks": "./config/hooks.json",
  "mcpServers": "./.mcp.json"
}
```

## ベストプラクティス

### メタデータ

1. **常にバージョンを含める**: 変更と更新を追跡
2. **明確な説明を書く**: ユーザーがプラグインの目的を理解できるように
3. **連絡先情報を提供**: ユーザーサポートを可能にする
4. **ドキュメントへのリンク**: サポート負担を軽減
5. **適切なライセンスを選択**: プロジェクトの目標に合致

### パス

1. **可能な場合はデフォルトを使用**: 設定を最小限に
2. **論理的に整理**: 関連コンポーネントをグループ化
3. **カスタムパスを文書化**: 非標準レイアウトの理由を説明
4. **パス解決をテスト**: 複数のシステムで検証

### メンテナンス

1. **変更時にバージョンを上げる**: セマンティックバージョニングに従う
2. **キーワードを更新**: 新機能を反映
3. **説明を最新に保つ**: 実際の能力に一致
4. **変更履歴を維持**: バージョン履歴を追跡
5. **リポジトリリンクを更新**: URL を最新に保つ

### 配布

1. **公開前にメタデータを完了**: すべてのフィールドを記入
2. **クリーンインストールでテスト**: 開発環境なしでプラグインが動作するか確認
3. **マニフェストをバリデーション**: バリデーションツールを使用
4. **README を含める**: インストールと使用方法を文書化
5. **ライセンスファイルを指定**: プラグインルートに LICENSE ファイルを含める
