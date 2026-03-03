# MCP (Model Context Protocol) ガイド

MCPサーバーを使用して、Skillsではできない開発を便利にする機能を追加する方法。

## 技術スタック別ガイド

各技術スタックに特化したMCP設定は以下のファイルを参照:

| 技術 | ガイド | 設定ファイル |
|------|--------|-------------|
| Laravel / PHP | [mcp-by-technology.md](mcp-by-technology.md#laravel--php) | [settings-laravel-php.json](settings-laravel-php.json) |
| Python | [mcp-by-technology.md](mcp-by-technology.md#python) | [settings-python.json](settings-python.json) |
| JavaScript / Node.js | [mcp-by-technology.md](mcp-by-technology.md#javascript--nodejs) | [settings-javascript.json](settings-javascript.json) |
| VBA / Excel | [mcp-by-technology.md](mcp-by-technology.md#vba--excel) | [settings-vba.json](settings-vba.json) |
| Linux (Ubuntu) | [mcp-by-technology.md](mcp-by-technology.md#linux-ubuntu) | [settings-linux.json](settings-linux.json) |

## Skills vs MCP の違い

| 機能 | Skills | MCP |
|------|--------|-----|
| 定義 | マークダウンベースの指示・知識 | 実行可能なサーバープロセス |
| 実行 | Claude内で解釈 | 外部プロセスとして実行 |
| データアクセス | なし（知識のみ） | リアルタイムでデータ取得可能 |
| API連携 | 不可 | 可能（認証含む） |
| ファイル操作 | 不可 | 可能（読み書き） |
| データベース | 不可 | 可能（クエリ実行） |
| ブラウザ操作 | 不可 | 可能（Puppeteer等） |
| 永続化 | 不可 | 可能（メモリサーバー） |

## MCPでしかできないこと

### 1. 外部サービスとの認証付き連携
- GitHub API（Issue作成、PR操作）
- Slack（メッセージ送信、チャンネル操作）
- Jira/Linear（チケット管理）
- Google Drive（ファイルアクセス）

### 2. データベース操作
- PostgreSQL/MySQL/SQLiteクエリ実行
- スキーマ情報の取得
- データの読み書き

### 3. ブラウザ自動化
- Webページのスクレイピング
- スクリーンショット取得
- フォーム操作
- E2Eテスト補助

### 4. 永続的なメモリ
- セッション間での情報保持
- ナレッジグラフの構築
- プロジェクト固有の知識管理

### 5. リアルタイム情報取得
- 現在時刻・タイムゾーン
- 外部APIからのデータフェッチ
- システム情報の取得

## 推奨MCPサーバー

### 開発必須

#### 1. Filesystem Server
ファイルシステムへの安全なアクセス。

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "C:/Users/nakashima/Desktop/claude"
      ]
    }
  }
}
```

**機能:**
- ファイルの読み書き
- ディレクトリ一覧
- ファイル検索
- アクセス制御（指定ディレクトリのみ）

#### 2. Git Server
Gitリポジトリの操作。

```json
{
  "mcpServers": {
    "git": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-git"]
    }
  }
}
```

**機能:**
- コミット履歴の取得
- diff表示
- ブランチ情報
- ファイル変更の追跡

#### 3. Memory Server
永続的なメモリ・ナレッジグラフ。

```json
{
  "mcpServers": {
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
```

**機能:**
- セッション間での情報保持
- エンティティの関係性管理
- プロジェクト知識の蓄積

### データベース連携

#### 4. PostgreSQL Server
PostgreSQLデータベースへの接続。

```json
{
  "mcpServers": {
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "POSTGRES_CONNECTION_STRING": "postgresql://user:password@localhost:5432/dbname"
      }
    }
  }
}
```

**機能:**
- SQLクエリ実行（読み取り専用推奨）
- スキーマ情報の取得
- テーブル構造の確認

#### 5. SQLite Server
ローカルSQLiteデータベース。

```json
{
  "mcpServers": {
    "sqlite": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-sqlite",
        "--db-path",
        "C:/path/to/database.db"
      ]
    }
  }
}
```

### 外部サービス連携

#### 6. GitHub Server
GitHub APIとの連携。

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "ghp_xxxxxxxxxxxx"
      }
    }
  }
}
```

**機能:**
- Issue/PRの作成・更新
- リポジトリ情報の取得
- コードレビュー補助

#### 7. Slack Server
Slackとの連携。

```json
{
  "mcpServers": {
    "slack": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-slack"],
      "env": {
        "SLACK_BOT_TOKEN": "xoxb-xxxxxxxxxxxx"
      }
    }
  }
}
```

**機能:**
- メッセージの送信
- チャンネル一覧取得
- 検索

### ブラウザ自動化

#### 8. Puppeteer Server
ブラウザ自動化・スクレイピング。

```json
{
  "mcpServers": {
    "puppeteer": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-puppeteer"]
    }
  }
}
```

**機能:**
- Webページのスクレイピング
- スクリーンショット取得
- PDF生成
- フォーム操作

#### 9. Fetch Server
Webコンテンツの取得。

```json
{
  "mcpServers": {
    "fetch": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-fetch"]
    }
  }
}
```

**機能:**
- URLからコンテンツ取得
- HTMLをマークダウンに変換
- robots.txt準拠

### 高度な開発ツール

#### 10. Sequential Thinking Server
複雑な問題解決のための思考プロセス。

```json
{
  "mcpServers": {
    "sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    }
  }
}
```

**機能:**
- 段階的な問題分析
- 思考の可視化
- 複雑なタスクの分解

#### 11. Claude Context (Semantic Code Search)
コードベース全体のセマンティック検索。

```json
{
  "mcpServers": {
    "claude-context": {
      "command": "npx",
      "args": ["-y", "@anthropic/claude-context"]
    }
  }
}
```

**機能:**
- コード全体の意味検索
- 関連コードの発見
- 大規模コードベースの理解

## 設定ファイルの場所

### Claude Code
```
~/.claude/settings.json
```

### Claude Desktop (Windows)
```
%APPDATA%\Claude\claude_desktop_config.json
```

### Claude Desktop (macOS)
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

## 完全な設定例

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "C:/Users/nakashima/Desktop/claude"
      ]
    },
    "git": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-git"]
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    },
    "fetch": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-fetch"]
    },
    "sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    }
  }
}
```

## コンテキストウィンドウの注意

### MCPサーバーの制限
- **推奨**: プロジェクトあたり10個以下のMCPを有効化
- **最大ツール数**: 80個以下を推奨
- **理由**: MCPのツール定義がコンテキストを消費

### 未使用MCPの無効化

プロジェクト設定（`.claude/config.json`）で未使用MCPを無効化:

```json
{
  "disabledMcpServers": [
    "slack",
    "puppeteer",
    "postgres"
  ]
}
```

## MCPサーバーの開発

### TypeScript SDK
```bash
npm install @modelcontextprotocol/sdk
```

### 基本構造
```typescript
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const server = new Server({
  name: "my-mcp-server",
  version: "1.0.0"
}, {
  capabilities: {
    tools: {}
  }
});

// ツールを定義
server.setRequestHandler("tools/list", async () => ({
  tools: [{
    name: "my_tool",
    description: "My custom tool",
    inputSchema: {
      type: "object",
      properties: {
        param1: { type: "string", description: "First parameter" }
      },
      required: ["param1"]
    }
  }]
}));

// ツール実行を処理
server.setRequestHandler("tools/call", async (request) => {
  if (request.params.name === "my_tool") {
    const { param1 } = request.params.arguments;
    // ツールのロジック
    return { content: [{ type: "text", text: `Result: ${param1}` }] };
  }
});

// サーバー起動
const transport = new StdioServerTransport();
await server.connect(transport);
```

## トラブルシューティング

### MCPサーバーが起動しない
1. Node.jsがインストールされているか確認
2. `npx` コマンドが使えるか確認
3. ファイアウォール設定を確認

### 接続エラー
1. 設定ファイルのJSON構文を確認
2. パスが正しいか確認（Windows: バックスラッシュをエスケープ）
3. Claude Codeを再起動

### パフォーマンス問題
1. 不要なMCPサーバーを無効化
2. コンテキストウィンドウの使用量を確認
3. 大きなデータを返すツールの使用を制限

## 参考リンク

### 公式リソース
- [MCP公式ドキュメント](https://modelcontextprotocol.io/)
- [MCP Servers GitHub](https://github.com/modelcontextprotocol/servers)
- [MCP仕様書 (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25)
- [Claude Code MCP設定](https://docs.anthropic.com/en/docs/claude-code/mcp)
- [Anthropic MCP発表](https://www.anthropic.com/news/model-context-protocol)

### コミュニティリソース（1200+サーバー）
- [Awesome MCP Servers](https://mcp-awesome.com/) - 1200+ 品質検証済みサーバーディレクトリ
- [MCP.so](https://mcp.so/) - 3000+ サーバー検索プラットフォーム
- [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) - キュレーションリスト
- [wong2/awesome-mcp-servers](https://github.com/wong2/awesome-mcp-servers) - キュレーションリスト
- [mcpservers.org](https://mcpservers.org/) - MCPサーバーディレクトリ
- [MCP Market](https://mcpmarket.com/) - MCPマーケットプレイス

### 言語別SDK
- [TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)
- [Python SDK](https://github.com/modelcontextprotocol/python-sdk) - v1.x推奨（v2は2026年Q1予定）
- [PHP SDK](https://github.com/php-mcp/server) - PHP 8.1+
- [Laravel MCP](https://github.com/laravel/mcp) - Laravel 12.x公式

### セキュリティ
- [Docker MCP Toolkit](https://www.docker.com/blog/top-mcp-servers-2025/) - コンテナ分離でセキュア実行

## まとめ

MCPサーバーは、Skillsでは実現できない以下の機能を提供します：

1. **外部サービス連携** - GitHub, Slack, Jira等
2. **データベース操作** - SQL実行、スキーマ取得
3. **ブラウザ自動化** - スクレイピング、スクリーンショット
4. **永続メモリ** - セッション間の情報保持
5. **リアルタイムデータ** - API、システム情報

開発効率を最大化するために、必要なMCPサーバーを選択して設定してください。
