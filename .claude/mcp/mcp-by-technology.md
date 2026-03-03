# 技術スタック別 MCP サーバーガイド

各開発言語・フレームワークに最適なMCPサーバーの設定例。

## 目次

1. [Laravel / PHP](#laravel--php)
2. [Python](#python)
3. [JavaScript / Node.js](#javascript--nodejs)
4. [VBA / Excel](#vba--excel)
5. [Linux (Ubuntu)](#linux-ubuntu)
6. [共通推奨MCP](#共通推奨mcp)

---

## Laravel / PHP

### 公式 Laravel MCP サーバー

Laravel 12.x から公式MCPパッケージが提供されています。

**インストール:**
```bash
composer require laravel/mcp
```

**参考リンク:**
- [Laravel MCP 公式ドキュメント](https://laravel.com/docs/12.x/mcp)
- [laravel/mcp GitHub](https://github.com/laravel/mcp)
- [php-mcp/laravel GitHub](https://github.com/php-mcp/laravel)

### PHP MCP SDK

2025年9月にAnthropicとSymfonyチームが公式PHP SDKを発表。

**特徴:**
- PHP 8.1+ サポート
- WebSocketトランスポート
- Laravel/Symfonyアダプター

**インストール:**
```bash
composer require php-mcp/server
# Laravel用
composer require php-mcp/laravel
```

### Laravel開発向けMCP設定

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "C:/path/to/laravel/project"
      ]
    },
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "POSTGRES_CONNECTION_STRING": "postgresql://user:password@localhost:5432/laravel_db"
      }
    },
    "mysql": {
      "command": "uvx",
      "args": ["mcp-server-mysql"],
      "env": {
        "MYSQL_HOST": "localhost",
        "MYSQL_USER": "root",
        "MYSQL_PASSWORD": "password",
        "MYSQL_DATABASE": "laravel_db"
      }
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

### Laravel特有のMCPユースケース

| ユースケース | MCP | 機能 |
|------------|-----|------|
| DBマイグレーション確認 | postgres/mysql | スキーマ情報取得 |
| Eloquentモデル生成補助 | filesystem + memory | ファイル構造記憶 |
| API開発 | fetch | エンドポイントテスト |
| Artisanコマンド実行 | shell-mcp | コマンド実行 |

---

## Python

### 公式 Python MCP SDK

```bash
pip install mcp
# または
uv add mcp
```

**注意:** 2026年Q1まではv1.xが本番環境推奨。v2は開発中。

**参考リンク:**
- [Python SDK GitHub](https://github.com/modelcontextprotocol/python-sdk)
- [PyPI - mcp](https://pypi.org/project/mcp/)
- [Real Python MCP チュートリアル](https://realpython.com/python-mcp/)

### Python開発向けMCP設定

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "C:/path/to/python/project"
      ]
    },
    "sqlite": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-sqlite",
        "--db-path",
        "C:/path/to/database.db"
      ]
    },
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "POSTGRES_CONNECTION_STRING": "postgresql://user:password@localhost:5432/python_db"
      }
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

### Python用カスタムMCPサーバー作成

FastMCPを使用した簡単な例:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-python-server")

@mcp.tool()
def run_pytest(test_path: str) -> str:
    """指定パスのpytestを実行"""
    import subprocess
    result = subprocess.run(
        ["pytest", test_path, "-v"],
        capture_output=True,
        text=True
    )
    return result.stdout + result.stderr

@mcp.resource("file:///{path}")
def read_python_file(path: str) -> str:
    """Pythonファイルを読み込み"""
    with open(path) as f:
        return f.read()
```

### Python特有のMCPユースケース

| ユースケース | MCP | 機能 |
|------------|-----|------|
| データ分析 | sqlite/postgres | データクエリ |
| 機械学習 | memory | モデル情報保持 |
| Jupyter連携 | filesystem | ノートブックアクセス |
| テスト実行 | shell-mcp | pytest実行 |

---

## JavaScript / Node.js

### TypeScript MCP SDK

```bash
npm install @modelcontextprotocol/sdk
```

**参考リンク:**
- [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)
- [公式MCPサーバー一覧](https://github.com/modelcontextprotocol/servers)

### JavaScript開発向けMCP設定

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "C:/path/to/js/project"
      ]
    },
    "git": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-git"]
    },
    "puppeteer": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-puppeteer"]
    },
    "fetch": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-fetch"]
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

### フロントエンド開発向け追加MCP

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-playwright"]
    },
    "browserbase": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-browserbase"],
      "env": {
        "BROWSERBASE_API_KEY": "your-api-key"
      }
    }
  }
}
```

### JavaScript特有のMCPユースケース

| ユースケース | MCP | 機能 |
|------------|-----|------|
| E2Eテスト | puppeteer/playwright | ブラウザ自動化 |
| React開発 | filesystem + memory | コンポーネント構造記憶 |
| API開発 | fetch | エンドポイントテスト |
| パッケージ管理 | shell-mcp | npm/yarn実行 |

---

## VBA / Excel

VBA専用のMCPサーバーは現時点で公式には存在しませんが、以下の組み合わせで開発効率を向上できます。

### VBA開発向けMCP設定

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "C:/path/to/excel/projects"
      ]
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

### VBA開発のワークフロー

1. **ファイルシステムMCP**: xlsm/xlsb ファイルの管理
2. **メモリMCP**: VBAモジュール構造・変数定義の記憶
3. **Sequential Thinking**: 複雑なVBAロジックの段階的設計

### VBA用カスタムMCPサーバー案

Python + win32comを使用したカスタムMCPサーバー:

```python
# vba_mcp_server.py
from mcp.server.fastmcp import FastMCP
import win32com.client

mcp = FastMCP("vba-server")

@mcp.tool()
def list_vba_modules(file_path: str) -> str:
    """ExcelファイルのVBAモジュール一覧を取得"""
    excel = win32com.client.Dispatch("Excel.Application")
    excel.Visible = False
    try:
        wb = excel.Workbooks.Open(file_path)
        modules = []
        for component in wb.VBProject.VBComponents:
            modules.append({
                "name": component.Name,
                "type": component.Type
            })
        wb.Close(False)
        return str(modules)
    finally:
        excel.Quit()

@mcp.tool()
def export_vba_module(file_path: str, module_name: str, output_path: str) -> str:
    """VBAモジュールをファイルにエクスポート"""
    excel = win32com.client.Dispatch("Excel.Application")
    excel.Visible = False
    try:
        wb = excel.Workbooks.Open(file_path)
        for component in wb.VBProject.VBComponents:
            if component.Name == module_name:
                component.Export(output_path)
                wb.Close(False)
                return f"Exported {module_name} to {output_path}"
        wb.Close(False)
        return f"Module {module_name} not found"
    finally:
        excel.Quit()
```

### VBA特有のMCPユースケース

| ユースケース | MCP | 機能 |
|------------|-----|------|
| モジュール管理 | filesystem | .bas/.cls ファイル管理 |
| 複雑なロジック設計 | sequential-thinking | 段階的設計 |
| プロジェクト情報記憶 | memory | 変数・関数定義の保持 |

---

## Linux (Ubuntu)

### シェルコマンド実行MCP

**注意:** シェル実行MCPはセキュリティリスクがあります。必ずホワイトリスト制限を設定してください。

**参考リンク:**
- [mcp-shell-server](https://github.com/tumf/mcp-shell-server)
- [cli-mcp-server](https://github.com/MladenSU/cli-mcp-server)
- [linux-mcp-server ガイド](https://skywork.ai/skypage/en/Mastering-linux-mcp-server-A-Comprehensive-Guide-for-AI-Engineers/1971398124258062336)

### Linux開発向けMCP設定

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/home/user/projects"
      ]
    },
    "git": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-git"]
    },
    "shell": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-shell"],
      "env": {
        "ALLOWED_COMMANDS": "ls,cat,grep,find,pwd,echo,head,tail,wc,sort,uniq",
        "ALLOWED_DIRECTORIES": "/home/user/projects"
      }
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    },
    "docker": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-docker"]
    }
  }
}
```

### セキュアなシェルMCP設定（推奨）

```json
{
  "mcpServers": {
    "cli-mcp": {
      "command": "uvx",
      "args": ["cli-mcp-server"],
      "env": {
        "ALLOWED_COMMANDS": "git,npm,yarn,python,pip,docker,kubectl",
        "ALLOWED_DIRECTORIES": "/home/user/projects,/tmp",
        "COMMAND_TIMEOUT": "30",
        "ALLOW_SHELL_OPERATORS": "false"
      }
    }
  }
}
```

### Linux特有のMCPユースケース

| ユースケース | MCP | 機能 |
|------------|-----|------|
| サーバー管理 | shell | systemctlコマンド |
| Docker操作 | docker-mcp | コンテナ管理 |
| ログ分析 | filesystem + shell | ログファイル解析 |
| パッケージ管理 | shell | apt/yum実行 |

---

## 共通推奨MCP

すべての技術スタックで有用なMCPサーバー:

### 基本セット

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

### 追加推奨MCP

| MCP | 用途 | コマンド |
|-----|------|---------|
| GitHub | Issue/PR管理 | `@modelcontextprotocol/server-github` |
| Slack | チーム通知 | `@modelcontextprotocol/server-slack` |
| Puppeteer | ブラウザ自動化 | `@modelcontextprotocol/server-puppeteer` |
| Time | 時刻情報 | `@modelcontextprotocol/server-time` |
| SQLite | ローカルDB | `@modelcontextprotocol/server-sqlite` |
| PostgreSQL | DB連携 | `@modelcontextprotocol/server-postgres` |

---

## MCP発見リソース

### 公式リソース
- [MCP公式サーバー](https://github.com/modelcontextprotocol/servers)
- [MCP仕様書](https://modelcontextprotocol.io/specification/2025-11-25)

### コミュニティリソース
- [Awesome MCP Servers](https://mcp-awesome.com/) - 1200+ サーバーディレクトリ
- [MCP.so](https://mcp.so/) - 3000+ サーバー検索
- [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers)
- [wong2/awesome-mcp-servers](https://github.com/wong2/awesome-mcp-servers)
- [mcpservers.org](https://mcpservers.org/)

### セキュリティ
- Docker MCP Toolkit（コンテナ分離）
- [Docker MCP ブログ](https://www.docker.com/blog/top-mcp-servers-2025/)

---

## 設定のベストプラクティス

### 1. 必要なMCPのみ有効化
- プロジェクトあたり10個以下を推奨
- 最大ツール数: 80個以下

### 2. プロジェクト固有の設定
`.claude/config.json` で不要MCPを無効化:

```json
{
  "disabledMcpServers": ["slack", "puppeteer"]
}
```

### 3. 環境変数の管理
機密情報は環境変数で管理:

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    }
  }
}
```

### 4. セキュリティ考慮事項
- シェル実行MCPは必ずホワイトリスト制限
- データベースMCPは読み取り専用推奨
- ファイルシステムMCPはアクセスディレクトリを制限
