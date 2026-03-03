# Context7 MCP セットアップガイド

Context7は、AIが最新のライブラリドキュメントを自動取得するMCPサーバー。

## なぜContext7が必要か

| 問題 | Context7の解決策 |
|------|-----------------|
| AIが古いAPIを提案する | 最新バージョンのドキュメントを自動取得 |
| 存在しないAPIをハルシネーション | 実際のドキュメントから回答 |
| 毎回ドキュメントを手動で検索 | プロンプトに `use context7` を追加するだけ |
| バージョン違いによるエラー | バージョン指定でドキュメント取得 |

## クイックスタート

### 1. 設定を追加

**Claude Code / Claude Desktop:**

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp@latest"]
    }
  }
}
```

**Cursor:**
Settings → Cursor Settings → MCP → Add new global MCP server

**VSCode:**
`.vscode/mcp.json` に追加:
```json
{
  "servers": {
    "context7": {
      "type": "http",
      "url": "https://mcp.context7.com/mcp"
    }
  }
}
```

### 2. 使い方

プロンプトに `use context7` を追加するだけ：

```
Next.js 15でApp Routerを使ったプロジェクトを作成して。use context7

FastAPIでCRUD APIを認証付きで作成して。use context7

Reactで状態管理をZustandで実装して。use context7
```

## 高度な設定

### APIキーの取得（推奨）

無料プランでもレート制限が緩和されます。

1. [context7.com/dashboard](https://context7.com/dashboard) にアクセス
2. GitHubアカウントでサインイン
3. APIキーを生成

### APIキー付き設定

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp@latest"],
      "env": {
        "CONTEXT7_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

### 環境変数で管理

```bash
# .bashrc / .zshrc / .profile
export CONTEXT7_API_KEY="your-api-key-here"
```

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp@latest"],
      "env": {
        "CONTEXT7_API_KEY": "${CONTEXT7_API_KEY}"
      }
    }
  }
}
```

## 提供されるツール

Context7は2つのMCPツールを提供：

### 1. resolve-library-id

ライブラリ名からContext7 IDを解決。

**入力:** `next.js`
**出力:** `/vercel/next.js/v15.0.0`

### 2. get-library-docs

ライブラリのドキュメントとコード例を取得。

**パラメータ:**
- `libraryId`: Context7 ID（例: `/vercel/next.js/v15.0.0`）
- `topic`: トピックフィルター（オプション）
- `tokens`: 最大トークン数（デフォルト: 5000）

## 対応ライブラリ例

| カテゴリ | ライブラリ |
|---------|-----------|
| フロントエンド | React, Vue, Angular, Svelte, Next.js, Nuxt |
| バックエンド | Express, FastAPI, Django, Laravel, Spring Boot |
| データベース | Prisma, Drizzle, TypeORM, SQLAlchemy |
| 状態管理 | Redux, Zustand, Pinia, MobX |
| テスト | Jest, Vitest, Playwright, Cypress |
| UI | Tailwind CSS, Chakra UI, Material UI, shadcn/ui |
| API | tRPC, GraphQL, OpenAPI |

## 使用例

### フロントエンド開発

```
React 19のServer Componentsの使い方を教えて。use context7

TailwindCSS v4でダークモードを実装して。use context7

shadcn/uiでフォームコンポーネントを作成して。use context7
```

### バックエンド開発

```
FastAPI 0.115でWebSocket実装して。use context7

Laravel 12のミドルウェアの書き方を教えて。use context7

Express.jsでJWT認証を実装して。use context7
```

### データベース

```
Prisma 6のマイグレーション方法を教えて。use context7

TypeORMでリレーションを定義して。use context7
```

## トラブルシューティング

### サーバーが起動しない

1. Node.js v18以上がインストールされているか確認
```bash
node --version  # v18.0.0以上が必要
```

2. npxが使えるか確認
```bash
npx --version
```

3. 手動でインストール
```bash
npm install -g @upstash/context7-mcp
```

### ドキュメントが取得できない

1. ライブラリ名が正しいか確認
2. インターネット接続を確認
3. APIキーを設定してレート制限を回避

### 古いドキュメントが返される

Context7はバージョン指定が可能：
```
Next.js 15.1.0のルーティングについて教えて。use context7
```

## 代替ランタイム

### Bun

```json
{
  "mcpServers": {
    "context7": {
      "command": "bunx",
      "args": ["-y", "@upstash/context7-mcp@latest"]
    }
  }
}
```

### Deno

```json
{
  "mcpServers": {
    "context7": {
      "command": "deno",
      "args": ["run", "-A", "npm:@upstash/context7-mcp@latest"]
    }
  }
}
```

## 参考リンク

- [Context7 GitHub](https://github.com/upstash/context7)
- [Context7 Dashboard](https://context7.com/dashboard)
- [Context7 公式ブログ](https://upstash.com/blog/context7-mcp)
- [Smithery - Context7](https://smithery.ai/server/@upstash/context7-mcp)
- [Context7 MCP Tutorial](https://dev.to/mehmetakar/context7-mcp-tutorial-3he2)
