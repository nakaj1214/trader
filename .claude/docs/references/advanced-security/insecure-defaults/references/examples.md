# 安全でないデフォルト: 例と反例

このドキュメントは、クイック検証チェックリストの各カテゴリについて、脆弱なパターン（報告すべき）と安全なパターン（スキップすべき）の詳細な例を提供します。

## フォールバックシークレット

### 脆弱 - 報告すべき

**Python: フォールバック付き環境変数**
```python
# File: src/auth/jwt.py
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-123')

# セキュリティコンテキストで使用
def create_token(user_id):
    return jwt.encode({'user_id': user_id}, SECRET_KEY, algorithm='HS256')
```
**脆弱な理由:** `SECRET_KEY` が欠落している場合、既知のシークレットでアプリが動作する。攻撃者がトークンを偽造可能。

**JavaScript: 論理 OR フォールバック**
```javascript
// File: config/database.js
const DB_PASSWORD = process.env.DB_PASSWORD || 'admin123';

const pool = new Pool({
  user: 'admin',
  password: DB_PASSWORD,
  database: 'production'
});
```
**脆弱な理由:** env 変数が欠落している場合、データベースがハードコードされたパスワードを受け入れる。

**Ruby: デフォルト付き fetch**
```ruby
# File: config/secrets.rb
Rails.application.credentials.secret_key_base =
  ENV.fetch('SECRET_KEY_BASE', 'fallback-secret-base')
```
**脆弱な理由:** Rails セッション暗号化がフォールバックとして弱い既知のキーを使用。

### 安全 - スキップすべき

**フェイルセキュア: 設定なしでクラッシュ**
```python
# File: src/auth/jwt.py
SECRET_KEY = os.environ['SECRET_KEY']  # 欠落時に KeyError を発生

# SECRET_KEY なしではアプリが起動しない - フェイルセキュア
```

**明示的なバリデーション**
```javascript
// File: config/database.js
if (!process.env.DB_PASSWORD) {
  throw new Error('DB_PASSWORD environment variable required');
}
const DB_PASSWORD = process.env.DB_PASSWORD;
```

**テストフィクスチャ（明確にスコープされている）**
```python
# File: tests/fixtures/auth.py
TEST_SECRET = 'test-secret-key-123'  # OK - テスト専用

# テストでの使用
def test_token_creation():
    token = create_token('user1', secret=TEST_SECRET)
```

---

## デフォルト認証情報

### 脆弱 - 報告すべき

**ハードコードされた管理者アカウント**
```python
# File: src/models/user.py
def bootstrap_admin():
    """管理者が存在しない場合、デフォルト管理者アカウントを作成"""
    if not User.query.filter_by(role='admin').first():
        admin = User(
            username='admin',
            password=hash_password('admin123'),
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
```
**脆弱な理由:** 初回起動時に既知の認証情報でデフォルト管理者アカウントが作成される。

**コード内の API キー**
```javascript
// File: src/integrations/payment.js
const STRIPE_API_KEY = process.env.STRIPE_KEY || 'sk_tes...';

const stripe = require('stripe')(STRIPE_API_KEY);
```
**脆弱な理由:** env 変数が欠落している場合、テスト API キーを使用。本番に到達する可能性あり。

**データベース接続文字列**
```java
// File: DatabaseConfig.java
private static final String DB_URL = System.getenv().getOrDefault(
    "DATABASE_URL",
    "postgresql://admin:password@localhost:5432/prod"
);
```
**脆弱な理由:** フォールバックとしてハードコードされたデータベース認証情報。

### 安全 - スキップすべき

**無効化されたデフォルトアカウント**
```python
# File: src/models/user.py
def bootstrap_admin():
    """管理者アカウントは環境変数で設定する必要あり"""
    username = os.environ['ADMIN_USERNAME']
    password = os.environ['ADMIN_PASSWORD']

    if not User.query.filter_by(username=username).first():
        admin = User(username=username, password=hash_password(password), role='admin')
        db.session.add(admin)
```

**例/ドキュメント用認証情報**
```bash
# File: README.md
## セットアップ

API キーを設定:
```bash
export STRIPE_KEY='sk_tes...'  # 例のみ
```
```

**テストフィクスチャ認証情報**
```python
# File: tests/conftest.py
@pytest.fixture
def test_user():
    return User(username='test_user', password='test_pass')  # OK - テストスコープ
```

---

## フェイルオープンセキュリティ

### 脆弱 - 報告すべき

**デフォルトで認証が無効**
```python
# File: config/security.py
REQUIRE_AUTH = os.getenv('REQUIRE_AUTH', 'false').lower() == 'true'

@app.before_request
def check_auth():
    if not REQUIRE_AUTH:
        return  # 認証チェックをスキップ
    # ... 認証ロジック
```
**脆弱な理由:** デフォルトが認証なし。env 変数が欠落している場合、アプリが安全でなく動作。

**CORS がすべてのオリジンを許可**
```javascript
// File: server.js
const allowedOrigins = process.env.ALLOWED_ORIGINS || '*';

app.use(cors({ origin: allowedOrigins }));
```
**脆弱な理由:** デフォルトが任意のオリジンからのリクエストを許可。XSS/CSRF リスク。

**デフォルトでデバッグモードが有効**
```python
# File: config.py
DEBUG = os.getenv('DEBUG', 'true').lower() != 'false'  # デフォルト: true

if DEBUG:
    app.config['DEBUG'] = True
    app.config['PROPAGATE_EXCEPTIONS'] = True
```
**脆弱な理由:** デバッグモードがデフォルト。スタックトレースが本番で機密情報を漏洩。

### 安全 - スキップすべき

**デフォルトで認証が必須**
```python
# File: config/security.py
REQUIRE_AUTH = os.getenv('REQUIRE_AUTH', 'true').lower() == 'true'  # デフォルト: true

# またはより良い方法 - 明示的に設定されていない場合クラッシュ
REQUIRE_AUTH = os.environ['REQUIRE_AUTH'].lower() == 'true'
```

**CORS が明示的な設定を必要とする**
```javascript
// File: server.js
if (!process.env.ALLOWED_ORIGINS) {
  throw new Error('ALLOWED_ORIGINS must be configured');
}
const allowedOrigins = process.env.ALLOWED_ORIGINS.split(',');

app.use(cors({ origin: allowedOrigins }));
```

**デフォルトでデバッグモードが無効**
```python
# File: config.py
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'  # デフォルト: false
```

---

## 弱い暗号

### 脆弱 - 報告すべき

**パスワードハッシュに MD5**
```python
# File: src/auth/passwords.py
import hashlib

def hash_password(password):
    """ユーザーパスワードをハッシュ化"""
    return hashlib.md5(password.encode()).hexdigest()
```
**脆弱な理由:** MD5 は暗号学的に破られている。レインボーテーブルが存在。bcrypt/Argon2 を使用すべき。

**機密データに DES 暗号化**
```java
// File: Encryption.java
public static byte[] encrypt(String data, byte[] key) {
    Cipher cipher = Cipher.getInstance("DES/ECB/PKCS5Padding");
    SecretKeySpec secretKey = new SecretKeySpec(key, "DES");
    cipher.init(Cipher.ENCRYPT_MODE, secretKey);
    return cipher.doFinal(data.getBytes());
}
```
**脆弱な理由:** DES は 56 ビット鍵（総当たり可能）。ECB モードはパターンを漏洩。

**署名検証に SHA1**
```javascript
// File: webhooks.js
function verifySignature(payload, signature) {
  const hmac = crypto.createHmac('sha1', WEBHOOK_SECRET);
  const computed = hmac.update(payload).digest('hex');
  return computed === signature;
}
```
**脆弱な理由:** SHA1 の衝突が存在。SHA256 以上を使用すべき。

### 安全 - スキップすべき

**セキュリティ以外のチェックサムに弱い暗号**
```python
# File: src/utils/cache.py
import hashlib

def cache_key(data):
    """キャッシュキーを生成 - セキュリティに関係しない"""
    return hashlib.md5(data.encode()).hexdigest()  # OK - キャッシュ検索用
```

**パスワードに現代の暗号**
```python
# File: src/auth/passwords.py
import bcrypt

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())
```

**強力な暗号化**
```java
// File: Encryption.java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
// 256 ビット鍵、認証付き暗号化
```

---

## 許容的なアクセス

### 脆弱 - 報告すべき

**ファイルパーミッションが全員書き込み可能**
```python
# File: src/storage/files.py
def create_secure_file(path):
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o666)  # rw-rw-rw-
    return fd
```
**脆弱な理由:** 任意のユーザーがファイルに書き込み可能。0o600 または 0o644 にすべき。

**S3 バケットがデフォルトで公開**
```python
# File: infrastructure/storage.py
def create_storage_bucket(name):
    bucket = s3.create_bucket(
        Bucket=name,
        ACL='public-read'  # デフォルトで公開読み取り
    )
```
**脆弱な理由:** 機密データが公開露出。明示的な設定を必要とすべき。

**API がすべてのオリジンを許可**
```python
# File: app.py
@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response
```
**脆弱な理由:** CORS の設定ミス。任意のサイトからの認証情報窃取を許可。

### 安全 - スキップすべき

**正当な理由を持って明示的に設定された許容性**
```python
# File: src/storage/public_assets.py
def create_public_asset(path):
    """CDN 配信用の全員読み取り可能アセットを作成"""
    # 意図的に公開 - 静的アセットのみ
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o644)
    return fd
```

**デフォルトで制限的**
```python
# File: infrastructure/storage.py
def create_storage_bucket(name, public=False):
    acl = 'public-read' if public else 'private'
    if public:
        logger.warning(f'Creating PUBLIC bucket: {name}')
    bucket = s3.create_bucket(Bucket=name, ACL=acl)
```

---

## デバッグ機能

### 脆弱 - 報告すべき

**API レスポンスにスタックトレース**
```python
# File: app.py
@app.errorhandler(Exception)
def handle_error(error):
    return jsonify({
        'error': str(error),
        'traceback': traceback.format_exc()  # 内部パス、ライブラリバージョンを漏洩
    }), 500
```
**脆弱な理由:** 内部実装の詳細を攻撃者に公開。

**GraphQL イントロスペクションが有効**
```javascript
// File: server.js
const server = new ApolloServer({
  typeDefs,
  resolvers,
  introspection: true,  // 本番で有効
  playground: true
});
```
**脆弱な理由:** 攻撃者が管理者専用フィールドを含む API スキーマ全体を発見可能。

**詳細なエラーメッセージ**
```java
// File: UserController.java
catch (SQLException e) {
    return ResponseEntity.status(500).body(
        "Database error: " + e.getMessage()  // テーブル名、制約を漏洩
    );
}
```
**脆弱な理由:** SQL エラーメッセージがデータベース構造を明らかにする。

### 安全 - スキップすべき

**ログのみのデバッグ機能**
```python
# File: app.py
@app.errorhandler(Exception)
def handle_error(error):
    logger.exception('Request failed', exc_info=error)  # 完全なトレースをログ
    return jsonify({'error': 'Internal server error'}), 500  # ユーザーには一般的なメッセージ
```

**環境対応のデバッグ設定**
```javascript
// File: server.js
const server = new ApolloServer({
  typeDefs,
  resolvers,
  introspection: process.env.NODE_ENV !== 'production',
  playground: process.env.NODE_ENV !== 'production'
});
```

**一般的なユーザー向けエラー**
```java
// File: UserController.java
catch (SQLException e) {
    logger.error("Database error", e);  // 完全な詳細はログへ
    return ResponseEntity.status(500).body("Unable to process request");  // 一般的
}
```
