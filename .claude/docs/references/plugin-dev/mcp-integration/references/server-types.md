# MCP サーバータイプ: 詳細ガイド

Claude Code プラグインでサポートされるすべての MCP サーバータイプの完全なリファレンスです。

## stdio（標準入出力）

### 概要

ローカル MCP サーバーを子プロセスとして実行し、stdin/stdout 経由で通信します。ローカルツール、カスタムサーバー、NPM パッケージに最適な選択肢です。

### 設定

**基本:**
```json
{
  "my-server": {
    "command": "npx",
    "args": ["-y", "my-mcp-server"]
  }
}
```

**環境変数付き:**
```json
{
  "my-server": {
    "command": "${CLAUDE_PLUGIN_ROOT}/servers/custom-server",
    "args": ["--config", "${CLAUDE_PLUGIN_ROOT}/config.json"],
    "env": {
      "API_KEY": "${MY_API_KEY}",
      "LOG_LEVEL": "debug",
      "DATABASE_URL": "${DB_URL}"
    }
  }
}
```

### プロセスのライフサイクル

1. **起動**: Claude Code が `command` と `args` でプロセスを生成
2. **通信**: stdin/stdout 経由の JSON-RPC メッセージ
3. **ライフサイクル**: プロセスは Claude Code セッション全体で実行
4. **シャットダウン**: Claude Code 終了時にプロセスが終了

### ユースケース

**NPM パッケージ:**
```json
{
  "filesystem": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
  }
}
```

**カスタムスクリプト:**
```json
{
  "custom": {
    "command": "${CLAUDE_PLUGIN_ROOT}/servers/my-server.js",
    "args": ["--verbose"]
  }
}
```

**Python サーバー:**
```json
{
  "python-server": {
    "command": "python",
    "args": ["-m", "my_mcp_server"],
    "env": {
      "PYTHONUNBUFFERED": "1"
    }
  }
}
```

### ベストプラクティス

1. **絶対パスまたは ${CLAUDE_PLUGIN_ROOT} を使用する**
2. **Python サーバーには PYTHONUNBUFFERED を設定する**
3. **設定は stdin ではなく args または env で渡す**
4. **サーバークラッシュを適切に処理する**
5. **ログは stdout ではなく stderr に出力する（stdout は MCP プロトコル用）**

### トラブルシューティング

**サーバーが起動しない:**
- コマンドが存在し実行可能か確認
- ファイルパスが正しいか確認
- 権限を確認
- `claude --debug` のログを確認

**通信が失敗する:**
- サーバーが stdin/stdout を正しく使用しているか確認
- 余分な print/console.log 文がないか確認
- JSON-RPC フォーマットを確認

## SSE（Server-Sent Events）

### 概要

Server-Sent Events によるストリーミングで、ホストされた MCP サーバーに HTTP 接続します。クラウドサービスと OAuth 認証に最適です。

### 設定

**基本:**
```json
{
  "hosted-service": {
    "type": "sse",
    "url": "https://mcp.example.com/sse"
  }
}
```

**ヘッダー付き:**
```json
{
  "service": {
    "type": "sse",
    "url": "https://mcp.example.com/sse",
    "headers": {
      "X-API-Version": "v1",
      "X-Client-ID": "${CLIENT_ID}"
    }
  }
}
```

### 接続のライフサイクル

1. **初期化**: URL への HTTP 接続を確立
2. **ハンドシェイク**: MCP プロトコルのネゴシエーション
3. **ストリーミング**: サーバーが SSE 経由でイベントを送信
4. **リクエスト**: クライアントがツール呼び出しのために HTTP POST を送信
5. **再接続**: 切断時の自動再接続

### 認証

**OAuth（自動）:**
```json
{
  "asana": {
    "type": "sse",
    "url": "https://mcp.asana.com/sse"
  }
}
```

Claude Code が OAuth フローを処理します:
1. 初回使用時にユーザーに認証を求める
2. ブラウザで OAuth フローを開く
3. トークンを安全に保存
4. 自動トークンリフレッシュ

**カスタムヘッダー:**
```json
{
  "service": {
    "type": "sse",
    "url": "https://mcp.example.com/sse",
    "headers": {
      "Authorization": "Bearer ${API_TOKEN}"
    }
  }
}
```

### ユースケース

**公式サービス:**
- Asana: `https://mcp.asana.com/sse`
- GitHub: `https://mcp.github.com/sse`
- その他のホスト型 MCP サーバー

**カスタムホストサーバー:**
独自の MCP サーバーをデプロイして HTTPS + SSE で公開します。

### ベストプラクティス

1. **常に HTTPS を使用し、HTTP は使用しない**
2. **利用可能な場合は OAuth に認証を任せる**
3. **トークンには環境変数を使用する**
4. **接続障害を適切に処理する**
5. **必要な OAuth スコープを文書化する**

### トラブルシューティング

**接続拒否:**
- URL が正しくアクセス可能か確認
- HTTPS 証明書が有効か確認
- ネットワーク接続を確認
- ファイアウォール設定を確認

**OAuth の失敗:**
- キャッシュされたトークンをクリア
- OAuth スコープを確認
- リダイレクト URL を確認
- 再認証する

## HTTP（REST API）

### 概要

標準的な HTTP リクエストで RESTful MCP サーバーに接続します。トークンベースの認証とステートレスなインタラクションに最適です。

### 設定

**基本:**
```json
{
  "api": {
    "type": "http",
    "url": "https://api.example.com/mcp"
  }
}
```

**認証付き:**
```json
{
  "api": {
    "type": "http",
    "url": "https://api.example.com/mcp",
    "headers": {
      "Authorization": "Bearer ${API_TOKEN}",
      "Content-Type": "application/json",
      "X-API-Version": "2024-01-01"
    }
  }
}
```

### リクエスト/レスポンスフロー

1. **ツール検出**: 利用可能なツールを発見するための GET
2. **ツール呼び出し**: ツール名とパラメータを含む POST
3. **レスポンス**: 結果またはエラーを含む JSON レスポンス
4. **ステートレス**: 各リクエストが独立

### 認証

**トークンベース:**
```json
{
  "headers": {
    "Authorization": "Bearer ${API_TOKEN}"
  }
}
```

**API キー:**
```json
{
  "headers": {
    "X-API-Key": "${API_KEY}"
  }
}
```

**カスタム認証:**
```json
{
  "headers": {
    "X-Auth-Token": "${AUTH_TOKEN}",
    "X-User-ID": "${USER_ID}"
  }
}
```

### ユースケース

- REST API バックエンド
- 内部サービス
- マイクロサービス
- サーバーレス関数

### ベストプラクティス

1. **すべての接続に HTTPS を使用する**
2. **トークンを環境変数に保存する**
3. **一時的な障害に対するリトライロジックを実装する**
4. **レート制限に対応する**
5. **適切なタイムアウトを設定する**

### トラブルシューティング

**HTTP エラー:**
- 401: 認証ヘッダーを確認
- 403: 権限を確認
- 429: レート制限を実装
- 500: サーバーログを確認

**タイムアウトの問題:**
- 必要に応じてタイムアウトを延長
- サーバーのパフォーマンスを確認
- ツールの実装を最適化

## WebSocket（リアルタイム）

### 概要

WebSocket を介して MCP サーバーに接続し、リアルタイムの双方向通信を実現します。ストリーミングと低レイテンシのアプリケーションに最適です。

### 設定

**基本:**
```json
{
  "realtime": {
    "type": "ws",
    "url": "wss://mcp.example.com/ws"
  }
}
```

**認証付き:**
```json
{
  "realtime": {
    "type": "ws",
    "url": "wss://mcp.example.com/ws",
    "headers": {
      "Authorization": "Bearer ${TOKEN}",
      "X-Client-ID": "${CLIENT_ID}"
    }
  }
}
```

### 接続のライフサイクル

1. **ハンドシェイク**: WebSocket アップグレードリクエスト
2. **接続**: 永続的な双方向チャネル
3. **メッセージ**: WebSocket 上の JSON-RPC
4. **ハートビート**: キープアライブメッセージ
5. **再接続**: 切断時の自動再接続

### ユースケース

- リアルタイムデータストリーミング
- ライブ更新と通知
- コラボレーティブ編集
- 低レイテンシのツール呼び出し
- サーバーからのプッシュ通知

### ベストプラクティス

1. **WSS（セキュア WebSocket）を使用し、WS は使用しない**
2. **ハートビート/ping-pong を実装する**
3. **再接続ロジックを処理する**
4. **切断中のメッセージをバッファリングする**
5. **接続タイムアウトを設定する**

### トラブルシューティング

**接続の切断:**
- 再接続ロジックを実装
- ネットワークの安定性を確認
- サーバーが WebSocket をサポートしているか確認
- ファイアウォール設定を確認

**メッセージの配信:**
- メッセージの確認応答を実装
- 順序外のメッセージに対応
- 切断中のバッファリング

## 比較マトリクス

| 機能 | stdio | SSE | HTTP | WebSocket |
|------|-------|-----|------|-----------|
| **トランスポート** | プロセス | HTTP/SSE | HTTP | WebSocket |
| **方向** | 双方向 | サーバー→クライアント | リクエスト/レスポンス | 双方向 |
| **状態** | ステートフル | ステートフル | ステートレス | ステートフル |
| **認証** | 環境変数 | OAuth/ヘッダー | ヘッダー | ヘッダー |
| **ユースケース** | ローカルツール | クラウドサービス | REST API | リアルタイム |
| **レイテンシ** | 最小 | 中程度 | 中程度 | 低い |
| **セットアップ** | 簡単 | 中程度 | 簡単 | 中程度 |
| **再接続** | プロセス再生成 | 自動 | 該当なし | 自動 |

## 適切なタイプの選択

**stdio を使用する場合:**
- ローカルツールやカスタムサーバーを実行する
- 最小レイテンシが必要
- ファイルシステムやローカルデータベースを操作する
- サーバーをプラグインと一緒に配布する

**SSE を使用する場合:**
- ホストサービスに接続する
- OAuth 認証が必要
- 公式 MCP サーバー（Asana、GitHub）を使用する
- 自動再接続が必要

**HTTP を使用する場合:**
- REST API と統合する
- ステートレスなインタラクションが必要
- トークンベースの認証を使用する
- シンプルなリクエスト/レスポンスパターン

**WebSocket を使用する場合:**
- リアルタイム更新が必要
- コラボレーティブ機能を構築する
- 低レイテンシが重要
- 双方向ストリーミングが必要

## タイプ間の移行

### stdio から SSE への移行

**移行前（stdio）:**
```json
{
  "local-server": {
    "command": "node",
    "args": ["server.js"]
  }
}
```

**移行後（SSE - サーバーをデプロイ）:**
```json
{
  "hosted-server": {
    "type": "sse",
    "url": "https://mcp.example.com/sse"
  }
}
```

### HTTP から WebSocket への移行

**移行前（HTTP）:**
```json
{
  "api": {
    "type": "http",
    "url": "https://api.example.com/mcp"
  }
}
```

**移行後（WebSocket）:**
```json
{
  "realtime": {
    "type": "ws",
    "url": "wss://api.example.com/ws"
  }
}
```

利点: リアルタイム更新、低レイテンシ、双方向通信。

## 高度な設定

### 複数サーバー

異なるタイプを組み合わせる:

```json
{
  "local-db": {
    "command": "npx",
    "args": ["-y", "mcp-server-sqlite", "./data.db"]
  },
  "cloud-api": {
    "type": "sse",
    "url": "https://mcp.example.com/sse"
  },
  "internal-service": {
    "type": "http",
    "url": "https://api.example.com/mcp",
    "headers": {
      "Authorization": "Bearer ${API_TOKEN}"
    }
  }
}
```

### 条件付き設定

環境変数を使ってサーバーを切り替える:

```json
{
  "api": {
    "type": "http",
    "url": "${API_URL}",
    "headers": {
      "Authorization": "Bearer ${API_TOKEN}"
    }
  }
}
```

開発/本番で異なる値を設定:
- 開発: `API_URL=http://localhost:8080/mcp`
- 本番: `API_URL=https://api.production.com/mcp`

## セキュリティに関する考慮事項

### stdio のセキュリティ

- コマンドパスをバリデーションする
- ユーザー提供のコマンドを実行しない
- 環境変数のアクセスを制限する
- ファイルシステムへのアクセスを制限する

### ネットワークセキュリティ

- 常に HTTPS/WSS を使用する
- SSL 証明書をバリデーションする
- 証明書の検証をスキップしない
- セキュアなトークン保存を使用する

### トークン管理

- トークンをハードコードしない
- 環境変数を使用する
- 定期的にトークンをローテーションする
- トークンリフレッシュを実装する
- 必要なスコープを文書化する

## まとめ

ユースケースに基づいて MCP サーバータイプを選択してください:
- **stdio**: ローカル、カスタム、または NPM パッケージのサーバー向け
- **SSE**: OAuth 付きのホストサービス向け
- **HTTP**: トークン認証の REST API 向け
- **WebSocket**: リアルタイム双方向通信向け

堅牢な MCP 統合のために、徹底的にテストし、エラーを適切に処理してください。
