# MCP 認証パターン

Claude Code プラグインにおける MCP サーバーの認証方式の完全ガイドです。

## 概要

MCP サーバーは、サーバータイプとサービス要件に応じて複数の認証方式をサポートします。ユースケースとセキュリティ要件に最適な方式を選択してください。

## OAuth（自動）

### 仕組み

Claude Code は SSE および HTTP サーバーに対して完全な OAuth 2.0 フローを自動的に処理します:

1. ユーザーが MCP ツールを使用しようとする
2. Claude Code が認証の必要性を検出する
3. ブラウザで OAuth 同意画面を開く
4. ユーザーがブラウザで承認する
5. トークンが Claude Code によって安全に保存される
6. 自動トークンリフレッシュ

### 設定

```json
{
  "service": {
    "type": "sse",
    "url": "https://mcp.example.com/sse"
  }
}
```

追加の認証設定は不要です。Claude Code がすべてを処理します。

### サポートされるサービス

**OAuth 対応の既知の MCP サーバー:**
- Asana: `https://mcp.asana.com/sse`
- GitHub（利用可能な場合）
- Google サービス（利用可能な場合）
- カスタム OAuth サーバー

### OAuth スコープ

OAuth スコープは MCP サーバーによって決定されます。ユーザーは同意フロー中に必要なスコープを確認できます。

**README に必要なスコープを文書化してください:**
```markdown
## 認証

このプラグインには以下の Asana 権限が必要です:
- タスクとプロジェクトの読み取り
- タスクの作成と更新
- ワークスペースデータへのアクセス
```

### トークンの保存

トークンは Claude Code によって安全に保存されます:
- プラグインからはアクセスできない
- 暗号化されて保存
- 自動リフレッシュ
- サインアウト時にクリア

### OAuth のトラブルシューティング

**認証ループ:**
- キャッシュされたトークンをクリアする（サインアウトしてサインイン）
- OAuth リダイレクト URL を確認する
- サーバーの OAuth 設定を確認する

**スコープの問題:**
- 新しいスコープの場合、再承認が必要な場合がある
- 必要なスコープについてサーバーのドキュメントを確認する

**トークンの有効期限:**
- Claude Code が自動リフレッシュする
- リフレッシュに失敗した場合、再認証を求める

## トークンベースの認証

### Bearer トークン

HTTP および WebSocket サーバーで最も一般的です。

**設定:**
```json
{
  "api": {
    "type": "http",
    "url": "https://api.example.com/mcp",
    "headers": {
      "Authorization": "Bearer ${API_TOKEN}"
    }
  }
}
```

**環境変数:**
```bash
export API_TOKEN="your-secret-token-here"
```

### API キー

Bearer トークンの代替で、カスタムヘッダーに使用されることが多いです。

**設定:**
```json
{
  "api": {
    "type": "http",
    "url": "https://api.example.com/mcp",
    "headers": {
      "X-API-Key": "${API_KEY}",
      "X-API-Secret": "${API_SECRET}"
    }
  }
}
```

### カスタムヘッダー

サービスがカスタム認証ヘッダーを使用する場合があります。

**設定:**
```json
{
  "service": {
    "type": "sse",
    "url": "https://mcp.example.com/sse",
    "headers": {
      "X-Auth-Token": "${AUTH_TOKEN}",
      "X-User-ID": "${USER_ID}",
      "X-Tenant-ID": "${TENANT_ID}"
    }
  }
}
```

### トークン要件の文書化

README に必ず文書化してください:

```markdown
## セットアップ

### 必要な環境変数

プラグインを使用する前に以下の環境変数を設定してください:

\`\`\`bash
export API_TOKEN="your-token-here"
export API_SECRET="your-secret-here"
\`\`\`

### トークンの取得

1. https://api.example.com/tokens にアクセス
2. 新しい API トークンを作成
3. トークンとシークレットをコピー
4. 上記のように環境変数を設定

### トークンの権限

API トークンには以下の権限が必要です:
- リソースへの読み取りアクセス
- アイテム作成のための書き込みアクセス
- 削除アクセス（オプション、クリーンアップ操作用）
\`\`\`
```

## 環境変数認証（stdio）

### サーバーへの認証情報の受け渡し

stdio サーバーの場合、環境変数を通じて認証情報を渡します:

```json
{
  "database": {
    "command": "python",
    "args": ["-m", "mcp_server_db"],
    "env": {
      "DATABASE_URL": "${DATABASE_URL}",
      "DB_USER": "${DB_USER}",
      "DB_PASSWORD": "${DB_PASSWORD}"
    }
  }
}
```

### ユーザーの環境変数

```bash
# User sets these in their shell
export DATABASE_URL="postgresql://localhost/mydb"
export DB_USER="myuser"
export DB_PASSWORD="mypassword"
```

### ドキュメントテンプレート

```markdown
## データベース設定

以下の環境変数を設定してください:

\`\`\`bash
export DATABASE_URL="postgresql://host:port/database"
export DB_USER="username"
export DB_PASSWORD="password"
\`\`\`

または `.env` ファイルを作成してください（`.gitignore` に追加）:

\`\`\`
DATABASE_URL=postgresql://localhost:5432/mydb
DB_USER=myuser
DB_PASSWORD=mypassword
\`\`\`

読み込み方法: \`source .env\` または \`export $(cat .env | xargs)\`
\`\`\`
```

## 動的ヘッダー

### ヘッダーヘルパースクリプト

変更や有効期限があるトークンの場合、ヘルパースクリプトを使用します:

```json
{
  "api": {
    "type": "sse",
    "url": "https://api.example.com",
    "headersHelper": "${CLAUDE_PLUGIN_ROOT}/scripts/get-headers.sh"
  }
}
```

**スクリプト (get-headers.sh):**
```bash
#!/bin/bash
# Generate dynamic authentication headers

# Fetch fresh token
TOKEN=$(get-fresh-token-from-somewhere)

# Output JSON headers
cat <<EOF
{
  "Authorization": "Bearer $TOKEN",
  "X-Timestamp": "$(date -Iseconds)"
}
EOF
```

### 動的ヘッダーのユースケース

- 短命なトークンのリフレッシュが必要な場合
- HMAC 署名付きトークン
- 時間ベースの認証
- 動的なテナント/ワークスペース選択

## セキュリティのベストプラクティス

### 推奨事項

**環境変数を使用する:**
```json
{
  "headers": {
    "Authorization": "Bearer ${API_TOKEN}"
  }
}
```

**README に必要な変数を文書化する**

**常に HTTPS/WSS を使用する**

**トークンローテーションを実装する**

**トークンを安全に保存する（ファイルではなく環境変数）**

**利用可能な場合は OAuth に認証を任せる**

### 禁止事項

**トークンをハードコードしない:**
```json
{
  "headers": {
    "Authorization": "Bearer sk-abc123..."  // NEVER!
  }
}
```

**トークンを git にコミットしない**

**ドキュメントでトークンを共有しない**

**HTTPS の代わりに HTTP を使用しない**

**プラグインファイルにトークンを保存しない**

**トークンやセンシティブなヘッダーをログに出力しない**

## マルチテナンシーパターン

### ワークスペース/テナント選択

**環境変数経由:**
```json
{
  "api": {
    "type": "http",
    "url": "https://api.example.com/mcp",
    "headers": {
      "Authorization": "Bearer ${API_TOKEN}",
      "X-Workspace-ID": "${WORKSPACE_ID}"
    }
  }
}
```

**URL 経由:**
```json
{
  "api": {
    "type": "http",
    "url": "https://${TENANT_ID}.api.example.com/mcp"
  }
}
```

### ユーザーごとの設定

ユーザーが各自のワークスペースを設定します:

```bash
export WORKSPACE_ID="my-workspace-123"
export TENANT_ID="my-company"
```

## 認証のトラブルシューティング

### よくある問題

**401 Unauthorized:**
- トークンが正しく設定されているか確認
- トークンの有効期限が切れていないか確認
- トークンに必要な権限があるか確認
- ヘッダー形式が正しいか確認

**403 Forbidden:**
- トークンは有効だが権限が不足
- スコープ/権限を確認
- ワークスペース/テナント ID を確認
- 管理者の承認が必要な場合がある

**トークンが見つからない:**
```bash
# Check environment variable is set
echo $API_TOKEN

# If empty, set it
export API_TOKEN="your-token"
```

**トークンの形式が間違っている:**
```json
// Correct
"Authorization": "Bearer sk-abc123"

// Wrong
"Authorization": "sk-abc123"
```

### 認証のデバッグ

**デバッグモードを有効にする:**
```bash
claude --debug
```

確認事項:
- 認証ヘッダーの値（サニタイズ済み）
- OAuth フローの進行状況
- トークンリフレッシュの試行
- 認証エラー

**認証を個別にテストする:**
```bash
# Test HTTP endpoint
curl -H "Authorization: Bearer $API_TOKEN" \
     https://api.example.com/mcp/health

# Should return 200 OK
```

## 移行パターン

### ハードコードから環境変数への移行

**移行前:**
```json
{
  "headers": {
    "Authorization": "Bearer sk-hardcoded-token"
  }
}
```

**移行後:**
```json
{
  "headers": {
    "Authorization": "Bearer ${API_TOKEN}"
  }
}
```

**移行手順:**
1. プラグインの README に環境変数を追加
2. 設定を ${VAR} を使用するよう更新
3. 変数を設定してテスト
4. ハードコードされた値を削除
5. 変更をコミット

### Basic 認証から OAuth への移行

**移行前:**
```json
{
  "headers": {
    "Authorization": "Basic ${BASE64_CREDENTIALS}"
  }
}
```

**移行後:**
```json
{
  "type": "sse",
  "url": "https://mcp.example.com/sse"
}
```

**利点:**
- セキュリティの向上
- 認証情報管理が不要
- 自動トークンリフレッシュ
- スコープ付き権限

## 高度な認証

### 相互 TLS（mTLS）

一部のエンタープライズサービスではクライアント証明書が必要です。

**MCP 設定では直接サポートされていません。**

**回避策:** mTLS を処理する stdio サーバーでラップする:

```json
{
  "secure-api": {
    "command": "${CLAUDE_PLUGIN_ROOT}/servers/mtls-wrapper",
    "args": ["--cert", "${CLIENT_CERT}", "--key", "${CLIENT_KEY}"],
    "env": {
      "API_URL": "https://secure.example.com"
    }
  }
}
```

### JWT トークン

ヘッダーヘルパーで JWT トークンを動的に生成します:

```bash
#!/bin/bash
# generate-jwt.sh

# Generate JWT (using library or API call)
JWT=$(generate-jwt-token)

echo "{\"Authorization\": \"Bearer $JWT\"}"
```

```json
{
  "headersHelper": "${CLAUDE_PLUGIN_ROOT}/scripts/generate-jwt.sh"
}
```

### HMAC 署名

リクエスト署名が必要な API の場合:

```bash
#!/bin/bash
# generate-hmac.sh

TIMESTAMP=$(date -Iseconds)
SIGNATURE=$(echo -n "$TIMESTAMP" | openssl dgst -sha256 -hmac "$SECRET_KEY" | cut -d' ' -f2)

cat <<EOF
{
  "X-Timestamp": "$TIMESTAMP",
  "X-Signature": "$SIGNATURE",
  "X-API-Key": "$API_KEY"
}
EOF
```

## ベストプラクティスのまとめ

### プラグイン開発者向け

1. **サービスがサポートしている場合は OAuth を優先する**
2. **トークンには環境変数を使用する**
3. **必要なすべての変数を README に文書化する**
4. **例を含むセットアップ手順を提供する**
5. **認証情報をコミットしない**
6. **HTTPS/WSS のみを使用する**
7. **認証を徹底的にテストする**

### プラグインユーザー向け

1. **プラグイン使用前に環境変数を設定する**
2. **トークンを安全かつ非公開に保つ**
3. **定期的にトークンをローテーションする**
4. **開発/本番で異なるトークンを使用する**
5. **.env ファイルを git にコミットしない**
6. **承認前に OAuth スコープを確認する**

## まとめ

MCP サーバーの要件に合った認証方式を選択してください:
- **OAuth**: クラウドサービス向け（ユーザーにとって最も簡単）
- **Bearer トークン**: API サービス向け
- **環境変数**: stdio サーバー向け
- **動的ヘッダー**: 複雑な認証フロー向け

常にセキュリティを優先し、ユーザー向けの明確なセットアップドキュメントを提供してください。
