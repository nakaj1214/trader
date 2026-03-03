# 汎用MCPサーバー - 全言語・プロジェクト共通

どんなプログラミング言語、プロジェクトでも共通で使用できるMCPサーバーのガイド。

## 概要

MCPサーバーには2つのカテゴリがあります：

1. **汎用サーバー** - 言語・フレームワークに依存せず、すべての開発で使用可能
2. **特化型サーバー** - 特定の言語やサービスに特化（Python、PHP等）

このドキュメントでは**汎用サーバー**に焦点を当てます。

---

## 必須の汎用MCPサーバー TOP 10

### 1. Context7 - 最新ドキュメント取得

**最も推奨** - AIが最新のライブラリドキュメントを自動取得。

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

**機能:**
- 最新のライブラリドキュメント・コード例を自動取得
- バージョン指定可能（Next.js 15、React 19等）
- 古いAPIや存在しないAPIのハルシネーション防止
- **使い方**: プロンプトに `use context7` を追加

**対応言語:** 全言語（JavaScript、Python、PHP、Go、Rust等）

**使用例:**
```
Next.js 15でApp Routerを使ったプロジェクトを作成して。use context7
FastAPIでCRUD APIを作成して。use context7
```

**APIキー（推奨）:** [context7.com/dashboard](https://context7.com/dashboard) で無料キー取得（レート制限緩和）

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

---

### 2. Memory Server - 永続メモリ

セッション間で情報を保持するナレッジグラフ。

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
- プロジェクト情報の永続化
- エンティティ間の関係性管理
- 過去の決定事項の記憶
- チーム/プロジェクトの知識蓄積

**活用例:**
- 「このプロジェクトではTypeScriptを使う」を記憶
- コーディング規約の保存
- 過去のバグ修正履歴

---

### 3. Sequential Thinking - 複雑な問題解決

段階的な思考プロセスの可視化。

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
- 複雑な問題を段階的に分析
- 思考プロセスの分岐・修正
- デバッグや設計判断の補助

**活用シーン:**
- アーキテクチャ設計
- 複雑なバグの調査
- パフォーマンス最適化の計画

---

### 4. Filesystem Server - ファイル操作

安全なファイルシステムアクセス。

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
- **セキュリティ**: 指定ディレクトリのみアクセス可能

---

### 5. Git Server - バージョン管理

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

---

### 6. Brave Search - Web検索

プライバシー重視のWeb検索。

```json
{
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {
        "BRAVE_API_KEY": "your-brave-api-key"
      }
    }
  }
}
```

**機能:**
- Webページ検索
- ローカル検索（場所、ビジネス等）
- ニュース検索

**APIキー取得:** [brave.com/search/api](https://brave.com/search/api/)

---

### 7. Fetch Server - URLコンテンツ取得

Webコンテンツの取得・変換。

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

---

### 8. Puppeteer Server - ブラウザ自動化

ヘッドレスブラウザによる自動操作。

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
- E2Eテスト補助

---

### 9. GitHub Server - GitHub連携

GitHub APIとの統合。

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
- GitHub Actions操作

**トークン取得:** [github.com/settings/tokens](https://github.com/settings/tokens)

---

### 10. Time Server - 時刻・タイムゾーン

現在時刻とタイムゾーン情報。

```json
{
  "mcpServers": {
    "time": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-time"]
    }
  }
}
```

**機能:**
- 現在時刻の取得
- タイムゾーン変換
- 日付計算

---

## その他の有用な汎用サーバー

### Slack Server - チームコミュニケーション

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

### Notion Server - ドキュメント管理

```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_API_KEY": "ntn_xxxxxxxxxxxx"
      }
    }
  }
}
```

### Linear Server - プロジェクト管理

```json
{
  "mcpServers": {
    "linear": {
      "command": "npx",
      "args": ["-y", "@linear/linear-mcp-server"],
      "env": {
        "LINEAR_API_KEY": "lin_xxxxxxxxxxxx"
      }
    }
  }
}
```

### Firecrawl Server - 高度なWebスクレイピング

```json
{
  "mcpServers": {
    "firecrawl": {
      "command": "npx",
      "args": ["-y", "firecrawl-mcp"],
      "env": {
        "FIRECRAWL_API_KEY": "fc-xxxxxxxxxxxx"
      }
    }
  }
}
```

---

## 推奨構成パターン

### ミニマム構成（3サーバー）

最小限で最大効果を得る構成。

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp@latest"]
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    },
    "sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    }
  }
}
```

### スタンダード構成（6サーバー）

日常的な開発に最適。

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp@latest"]
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    },
    "sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
    },
    "git": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-git"]
    },
    "fetch": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-fetch"]
    }
  }
}
```

### フル構成（10サーバー）

全機能を活用する構成。

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp@latest"]
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    },
    "sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
    },
    "git": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-git"]
    },
    "fetch": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-fetch"]
    },
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {
        "BRAVE_API_KEY": "your-brave-api-key"
      }
    },
    "puppeteer": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-puppeteer"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "your-github-token"
      }
    },
    "time": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-time"]
    }
  }
}
```

---

## 設定ファイルの配置場所

| アプリケーション | パス |
|-----------------|------|
| Claude Code | `~/.claude/settings.json` |
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Cursor | Settings → Cursor Settings → MCP |
| VSCode | `.vscode/mcp.json` |

---

## セキュリティ考慮事項

### 推奨事項

1. **アクセス範囲の制限**: Filesystemサーバーは必要なディレクトリのみ指定
2. **読み取り専用モード**: データベースサーバーは読み取り専用で使用
3. **トークンの管理**: APIキーは環境変数で管理
4. **Docker分離**: 信頼性の低いサーバーはコンテナで実行

### Docker分離の例

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-v", "/path/to/allowed:/data:ro",
        "mcp/filesystem",
        "/data"
      ]
    }
  }
}
```

---

## 参考リンク

### 公式
- [MCP公式ドキュメント](https://modelcontextprotocol.io/)
- [MCP Servers GitHub](https://github.com/modelcontextprotocol/servers)
- [MCP仕様書 (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25)

### Context7
- [Context7 GitHub](https://github.com/upstash/context7)
- [Context7 Dashboard](https://context7.com/dashboard)
- [Context7 MCP紹介記事](https://upstash.com/blog/context7-mcp)

### サーバーディレクトリ
- [MCP.so](https://mcp.so/) - 3000+ サーバー検索
- [Awesome MCP Servers](https://mcp-awesome.com/) - 1200+ 品質検証済み
- [Smithery](https://smithery.ai/) - MCPサーバーカタログ

### 記事・ガイド
- [Top 10 MCP Servers for 2025](https://dev.to/fallon_jimmy/top-10-mcp-servers-for-2025-yes-githubs-included-15jg)
- [Best MCP Servers for Developers 2026](https://www.builder.io/blog/best-mcp-servers-2026)
- [MCP on Windows Setup](https://gist.github.com/feveromo/7a340d7795fca1ccd535a5802b976e1f)
