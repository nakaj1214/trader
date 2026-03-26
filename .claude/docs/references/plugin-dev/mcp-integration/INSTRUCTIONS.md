# Claude CodeプラグインのMCP統合

## 概要

Model Context Protocol（MCP）はClaude Codeプラグインが外部サービスやAPIと統合することを可能にし、構造化されたツールアクセスを提供します。MCP統合を使用して外部サービスの機能をClaude Code内のツールとして公開します。

**主要機能:**
- 外部サービスへの接続（データベース、API、ファイルシステム）
- 単一サービスから10以上の関連ツールを提供
- OAuthと複雑な認証フローを処理
- プラグインとMCPサーバーをバンドルして自動セットアップ

## MCPサーバー設定方法

プラグインは2つの方法でMCPサーバーをバンドルできる:

### 方法1: 専用の.mcp.json（推奨）

プラグインルートに`.mcp.json`を作成する:

```json
{
  "database-tools": {
    "command": "${CLAUDE_PLUGIN_ROOT}/servers/db-server",
    "args": ["--config", "${CLAUDE_PLUGIN_ROOT}/config.json"],
    "env": {
      "DB_URL": "${DB_URL}"
    }
  }
}
```

**メリット:**
- 関心事の明確な分離
- 維持が容易
- 複数のサーバーに適している

### 方法2: plugin.jsonにインライン

plugin.jsonに`mcpServers`フィールドを追加する:

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "mcpServers": {
    "plugin-api": {
      "command": "${CLAUDE_PLUGIN_ROOT}/servers/api-server",
      "args": ["--port", "8080"]
    }
  }
}
```

**メリット:**
- 単一の設定ファイル
- シンプルな単一サーバープラグインに適している

## MCPサーバータイプ

### stdio（ローカルプロセス）

ローカルMCPサーバーを子プロセスとして実行する。ローカルツールとカスタムサーバーに最適。

**設定:**
```json
{
  "filesystem": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/allowed/path"],
    "env": {
      "LOG_LEVEL": "debug"
    }
  }
}
```

**ユースケース:**
- ファイルシステムアクセス
- ローカルデータベース接続
- カスタムMCPサーバー
- NPMパッケージのMCPサーバー

**プロセス管理:**
- Claude CodeがプロセスをSpawnして管理
- stdin/stdoutで通信
- Claude Code終了時に終了

### SSE（Server-Sent Events）

OAuthサポートを持つホストされたMCPサーバーに接続する。クラウドサービスに最適。

**設定:**
```json
{
  "asana": {
    "type": "sse",
    "url": "https://mcp.asana.com/sse"
  }
}
```

**ユースケース:**
- 公式ホスティングMCPサーバー（Asana、GitHubなど）
- MCPエンドポイントを持つクラウドサービス
- OAuthベースの認証
- ローカルインストール不要

**認証:**
- OAuthフローが自動的に処理される
- 初回使用時にユーザーがプロンプト
- トークンはClaude Codeが管理

### HTTP（REST API）

トークン認証を持つRESTful MCPサーバーに接続する。

**設定:**
```json
{
  "api-service": {
    "type": "http",
    "url": "https://api.example.com/mcp",
    "headers": {
      "Authorization": "Bearer ${API_TOKEN}",
      "X-Custom-Header": "value"
    }
  }
}
```

**ユースケース:**
- REST APIベースのMCPサーバー
- トークンベースの認証
- カスタムAPIバックエンド
- ステートレスなインタラクション

### WebSocket（リアルタイム）

リアルタイムの双方向通信のためにWebSocket MCPサーバーに接続する。

**設定:**
```json
{
  "realtime-service": {
    "type": "ws",
    "url": "wss://mcp.example.com/ws",
    "headers": {
      "Authorization": "Bearer ${TOKEN}"
    }
  }
}
```

**ユースケース:**
- リアルタイムデータストリーミング
- 永続接続
- サーバーからのプッシュ通知
- 低レイテンシの要件

## 環境変数の展開

全MCP設定は環境変数の置換をサポートする:

**${CLAUDE_PLUGIN_ROOT}** - プラグインディレクトリ（ポータビリティのために常に使用）:
```json
{
  "command": "${CLAUDE_PLUGIN_ROOT}/servers/my-server"
}
```

**ユーザー環境変数** - ユーザーのシェルから:
```json
{
  "env": {
    "API_KEY": "${MY_API_KEY}",
    "DATABASE_URL": "${DB_URL}"
  }
}
```

**ベストプラクティス:** プラグインREADMEに全ての必要な環境変数を文書化する。

## MCPツールの命名

MCPサーバーがツールを提供する場合、自動的にプレフィックスが付く:

**フォーマット:** `mcp__plugin_<plugin-name>_<server-name>__<tool-name>`

**例:**
- プラグイン: `asana`
- サーバー: `asana`
- ツール: `create_task`
- **完全名:** `mcp__plugin_asana_asana__asana_create_task`

### コマンドでMCPツールを使用する

コマンドのフロントマターで特定のMCPツールを事前許可する:

```markdown
---
allowed-tools: [
  "mcp__plugin_asana_asana__asana_create_task",
  "mcp__plugin_asana_asana__asana_search_tasks"
]
---
```

**ワイルドカード（慎重に使用）:**
```markdown
---
allowed-tools: ["mcp__plugin_asana_asana__*"]
---
```

**ベストプラクティス:** セキュリティのためにワイルドカードではなく特定のツールを事前許可する。

## ライフサイクル管理

**自動起動:**
- プラグインが有効になった時にMCPサーバーが起動
- 最初のツール使用前に接続が確立
- 設定変更には再起動が必要

**ライフサイクル:**
1. プラグインがロードされる
2. MCP設定が解析される
3. サーバープロセスが起動（stdio）または接続が確立（SSE/HTTP/WS）
4. ツールが検出・登録される
5. ツールが`mcp__plugin_...__...`として利用可能に

**サーバーの確認:**
`/mcp`コマンドを使用してプラグイン提供のサーバーを含む全サーバーを確認する。

## 認証パターン

### OAuth（SSE/HTTP）

OAuthはClaude Codeが自動的に処理する:

```json
{
  "type": "sse",
  "url": "https://mcp.example.com/sse"
}
```

初回使用時にユーザーがブラウザで認証する。追加設定は不要。

### トークンベース（ヘッダー）

静的または環境変数のトークン:

```json
{
  "type": "http",
  "url": "https://api.example.com",
  "headers": {
    "Authorization": "Bearer ${API_TOKEN}"
  }
}
```

READMEに必要な環境変数を文書化する。

### 環境変数（stdio）

MCPサーバーに設定を渡す:

```json
{
  "command": "python",
  "args": ["-m", "my_mcp_server"],
  "env": {
    "DATABASE_URL": "${DB_URL}",
    "API_KEY": "${API_KEY}",
    "LOG_LEVEL": "info"
  }
}
```

## 統合パターン

### パターン1: シンプルなツールラッパー

コマンドがユーザーインタラクションでMCPツールを使用する:

```markdown
# コマンド: create-item.md
---
allowed-tools: ["mcp__plugin_name_server__create_item"]
---

手順:
1. ユーザーからアイテムの詳細を収集する
2. mcp__plugin_name_server__create_itemを使用する
3. 作成を確認する
```

**用途:** MCPを呼び出す前の検証や前処理を追加する場合。

### パターン2: 自律エージェント

エージェントがMCPツールを自律的に使用する:

```markdown
# エージェント: data-analyzer.md

分析プロセス:
1. mcp__plugin_db_server__queryでデータをクエリ
2. 結果を処理・分析
3. 洞察レポートを生成
```

**用途:** ユーザーインタラクションなしの複数ステップMCPワークフロー。

### パターン3: マルチサーバープラグイン

複数のMCPサーバーを統合する:

```json
{
  "github": {
    "type": "sse",
    "url": "https://mcp.github.com/sse"
  },
  "jira": {
    "type": "sse",
    "url": "https://mcp.jira.com/sse"
  }
}
```

**用途:** 複数のサービスにまたがるワークフロー。

## セキュリティのベストプラクティス

### HTTPS/WSSを使用する

常にセキュアな接続を使用する:

```json
✅ "url": "https://mcp.example.com/sse"
❌ "url": "http://mcp.example.com/sse"
```

### トークン管理

**すること:**
- ✅ トークンに環境変数を使用
- ✅ READMEに必要な環境変数を文書化
- ✅ OAuthフローに認証を任せる

**しないこと:**
- ❌ 設定にトークンをハードコード
- ❌ gitにトークンをコミット
- ❌ ドキュメントでトークンを共有

### 権限のスコープ

必要なMCPツールのみを事前許可する:

```markdown
✅ allowed-tools: [
  "mcp__plugin_api_server__read_data",
  "mcp__plugin_api_server__create_item"
]

❌ allowed-tools: ["mcp__plugin_api_server__*"]
```

## エラーハンドリング

### 接続の失敗

MCPサーバーが利用できない場合の処理:
- コマンドにフォールバック動作を提供
- 接続の問題をユーザーに通知
- サーバーURLと設定を確認

### ツール呼び出しエラー

失敗したMCP操作の処理:
- MCPツールを呼び出す前に入力を検証
- 明確なエラーメッセージを提供
- レート制限とクォータを確認

## テスト

### ローカルテスト

1. `.mcp.json`にMCPサーバーを設定する
2. プラグインをローカルにインストール（`.claude-plugin/`）
3. `/mcp`を実行してサーバーが表示されることを確認
4. コマンドでツール呼び出しをテスト
5. 接続の問題は`claude --debug`ログを確認

### バリデーションチェックリスト

- [ ] MCP設定が有効なJSON
- [ ] サーバーURLが正しくアクセス可能
- [ ] 必要な環境変数が文書化されている
- [ ] `/mcp`出力にツールが表示される
- [ ] 認証が機能している（OAuthまたはトークン）
- [ ] コマンドからのツール呼び出しが成功する
- [ ] エラーケースが丁寧に処理される

## クイックリファレンス

### MCPサーバータイプ

| タイプ | トランスポート | 最適な用途 | 認証 |
|------|-----------|----------|------|
| stdio | プロセス | ローカルツール、カスタムサーバー | 環境変数 |
| SSE | HTTP | ホスティングサービス、クラウドAPI | OAuth |
| HTTP | REST | APIバックエンド、トークン認証 | トークン |
| ws | WebSocket | リアルタイム、ストリーミング | トークン |

### ベストプラクティス

**すること:**
- ✅ ポータブルなパスに${CLAUDE_PLUGIN_ROOT}を使用
- ✅ 必要な環境変数を文書化
- ✅ セキュアな接続（HTTPS/WSS）を使用
- ✅ コマンドで特定のMCPツールを事前許可
- ✅ 公開前にMCP統合をテスト
- ✅ 接続とツールのエラーを丁寧に処理

**しないこと:**
- ❌ 絶対パスをハードコード
- ❌ 認証情報をgitにコミット
- ❌ HTTPの代わりにHTTPSを使用しない
- ❌ ワイルドカードで全ツールを事前許可
- ❌ エラーハンドリングをスキップ
- ❌ セットアップの文書化を忘れる

## 追加リソース

### リファレンスファイル

詳細については以下を参照:

- **`references/server-types.md`** - 各サーバータイプの詳細解説
- **`references/authentication.md`** - 認証パターンとOAuth
- **`references/tool-usage.md`** - コマンドとエージェントでのMCPツールの使用

## 実装ワークフロー

プラグインにMCP統合を追加するには:

1. MCPサーバータイプを選択する（stdio、SSE、HTTP、ws）
2. プラグインルートに設定を含む`.mcp.json`を作成する
3. 全ファイル参照に${CLAUDE_PLUGIN_ROOT}を使用する
4. READMEに必要な環境変数を文書化する
5. `/mcp`コマンドでローカルテストする
6. 関連するコマンドでMCPツールを事前許可する
7. 認証を処理する（OAuthまたはトークン）
8. エラーケースをテストする（接続失敗、認証エラー）
9. プラグインREADMEにMCP統合を文書化する

カスタム/ローカルサーバーにはstdio、OAuthを持つホスティングサービスにはSSEを使用する。
