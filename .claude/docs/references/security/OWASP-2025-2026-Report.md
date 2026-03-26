# OWASP セキュリティベストプラクティス 2025-2026

安全なアプリケーションを構築する開発者のための、最新 OWASP セキュリティ基準の包括的ガイド。

---

## 目次

1. [OWASP Top 10:2025](#owasp-top-102025)
2. [OWASP ASVS 5.0.0](#owasp-asvs-500)
3. [OWASP Top 10 for Agentic Applications 2026](#owasp-top-10-for-agentic-applications-2026)
4. [主要なセキュリティ原則](#主要なセキュリティ原則)
5. [出典と参考資料](#出典と参考資料)

---

## OWASP Top 10:2025

OWASP Global AppSec EU Barcelona 2025 で発表。175,000 以上の CVE と 280 万のテスト済みアプリケーションの分析に基づく。

### サマリーテーブル

| ランク | カテゴリ | 2021 からの変更 |
|------|----------|------------------|
| A01 | Broken Access Control | #1 のまま |
| A02 | Security Misconfiguration | #5 から上昇 |
| A03 | Software Supply Chain Failures | **新規**（A06:2021 から拡張） |
| A04 | Cryptographic Failures | #2 から下降 |
| A05 | Injection | #3 から下降 |
| A06 | Insecure Design | #4 から下降 |
| A07 | Identification and Authentication Failures | #7 のまま |
| A08 | Software and Data Integrity Failures | #8 のまま |
| A09 | Security Logging and Monitoring Failures | #9 のまま |
| A10 | Mishandling of Exceptional Conditions | **新規** |

---

### A01:2025 – Broken Access Control（アクセス制御の不備）

**説明:** アクセス制御は、ユーザーが意図された権限の範囲外で行動することを防ぐポリシーを強制する。失敗すると、不正なデータの開示、変更、または破壊につながる。

**よくある脆弱性:**
- URL、アプリケーション状態、HTML ページの改変によるアクセス制御のバイパス
- 主キーの変更による他者のレコードへのアクセス（IDOR）
- 権限昇格（ユーザーとしてログインしたまま管理者として行動）
- POST, PUT, DELETE API のアクセス制御の欠如
- CORS の設定ミスによる不正な API アクセスの許可

**防止策:**
```python
# 悪い例: 認可チェックなし
@app.route('/api/user/<user_id>')
def get_user(user_id):
    return db.get_user(user_id)

# 良い例: 認可を強制
@app.route('/api/user/<user_id>')
@login_required
def get_user(user_id):
    if current_user.id != user_id and not current_user.is_admin:
        abort(403)
    return db.get_user(user_id)
```

**緩和策:**
1. デフォルトでアクセスを拒否（許可リストアプローチ）
2. アクセス制御を一度実装し、アプリケーション全体で再利用
3. ユーザー提供の ID を受け入れる代わりにレコードの所有権を強制
4. ディレクトリリスティングを無効化し、Web ルートから機密ファイルを削除
5. アクセス制御の失敗をログに記録し、繰り返しの試行を警告
6. API アクセスにレート制限を適用して自動化攻撃の被害を最小化

---

### A02:2025 – Security Misconfiguration（セキュリティの設定ミス）

**説明:** セキュリティの強化が不足している、クラウド権限が不適切に設定されている、不要な機能が有効になっている、またはデフォルトアカウントが残っている場合にアプリケーションが脆弱になる。

**よくある脆弱性:**
- アプリケーションスタック全体でのセキュリティ強化の欠如
- 不要な機能の有効化（ポート、サービス、ページ、アカウント）
- デフォルト認証情報が未変更
- スタックトレースを露出するエラーハンドリング
- 古いまたは脆弱なソフトウェアコンポーネント
- 安全でないクラウドストレージ権限（S3 バケットの公開）

**防止策:**
```yaml
# 悪い例: 本番環境でデバッグモード
DEBUG=True
SECRET_KEY="development-key"

# 良い例: 本番環境で強化
DEBUG=False
SECRET_KEY="${RANDOM_SECRET_FROM_VAULT}"
ALLOWED_HOSTS=["app.example.com"]
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

**緩和策:**
1. 環境全体で自動化された再現可能な強化プロセス
2. 不要な機能やフレームワークを含まない最小限のプラットフォーム
3. 設定の定期的なレビューと更新（クラウド権限、パッチ）
4. 安全な分離によるセグメント化されたアプリケーションアーキテクチャ
5. セキュリティディレクティブの送信（CSP, HSTS, X-Frame-Options）
6. すべての環境での設定の自動検証

---

### A03:2025 – Software Supply Chain Failures（ソフトウェアサプライチェーンの障害）

**説明:** サードパーティ依存関係、侵害されたビルドパイプライン、安全でないパッケージ管理のリスクを強調する新カテゴリ。2021年のコンポーネント脆弱性フォーカスから拡張。

**よくある脆弱性:**
- 既知の脆弱性を持つコンポーネントの使用
- 依存関係の混同攻撃
- パッケージレジストリでのタイポスクワッティング
- 侵害された CI/CD パイプライン
- 署名されていないまたは未検証のパッケージ
- ソフトウェア部品表（SBOM）の欠如

**防止策:**
```bash
# 悪い例: 検証なしでインストール
npm install some-package

# 良い例: バージョンをロック、整合性を検証、監査
npm install some-package@1.2.3 --save-exact
npm audit
npm audit signatures
```

```json
// 整合性ハッシュ付き package-lock.json
{
  "dependencies": {
    "lodash": {
      "version": "4.17.21",
      "integrity": "sha512-v2kDEe57lecT..."
    }
  }
}
```

**緩和策:**
1. すべてのコンポーネントのインベントリを維持（SBOM）
2. 未使用の依存関係と機能を削除
3. 脆弱性の継続的な監視（Dependabot, Snyk）
4. 安全なリンクを通じて公式ソースからコンポーネントを取得
5. パッケージに署名し、署名を検証
6. CI/CD パイプラインに適切なアクセス制御と監査ログを確保
7. ロックファイルを使用し、整合性ハッシュを検証

---

### A04:2025 – Cryptographic Failures（暗号化の失敗）

**説明:** 機密データの露出につながる暗号化に関する失敗。弱いアルゴリズム、不適切な鍵管理、暗号化の欠如を含む。

**よくある脆弱性:**
- 平文でのデータ転送（HTTP, SMTP, FTP）
- 非推奨アルゴリズムの使用（MD5, SHA1, DES）
- 弱いまたはデフォルトの暗号鍵
- 証明書検証の欠如
- 認証モードなしの暗号化の使用
- 乱数生成のエントロピー不足

**防止策:**
```python
# 悪い例: 弱いハッシュ
import hashlib
password_hash = hashlib.md5(password.encode()).hexdigest()

# 良い例: モダンなパスワードハッシュ
from argon2 import PasswordHasher
ph = PasswordHasher()
password_hash = ph.hash(password)

# 悪い例: ECB モード
from Crypto.Cipher import AES
cipher = AES.new(key, AES.MODE_ECB)

# 良い例: 認証付き暗号化
from cryptography.fernet import Fernet
cipher = Fernet(key)
```

**緩和策:**
1. データを機密性でクラス分けし、それに応じたコントロールを適用
2. 不必要に機密データを保存しない
3. すべてのデータを転送中（TLS 1.2+）および保存時に暗号化
4. 強力で最新のアルゴリズムを使用（AES-256-GCM, Argon2, bcrypt）
5. 認証モード（GCM, CCM）で暗号化
6. 鍵をランダムに生成し、安全に保管（HSM, vault）
7. 機密レスポンスのキャッシュを無効化

---

### A05:2025 – Injection（インジェクション）

**説明:** 信頼できないデータがコマンドやクエリの一部としてインタープリターに送信されるときに発生。SQL, NoSQL, OS, LDAP, 式言語インジェクションを含む。

**よくある脆弱性:**
- ユーザー入力のバリデーション、フィルタリング、サニタイズの欠如
- パラメータ化されていない動的クエリ
- ORM 検索パラメータでの敵対的データの使用
- コマンド内でのユーザー入力の直接結合

**防止策:**
```python
# 悪い例: SQL インジェクション脆弱性
query = f"SELECT * FROM users WHERE id = {user_id}"
cursor.execute(query)

# 良い例: パラメータ化クエリ
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))

# 悪い例: コマンドインジェクション
os.system(f"convert {filename} output.png")

# 良い例: 安全な API を使用、シェルを避ける
subprocess.run(["convert", filename, "output.png"], shell=False)
```

```javascript
// 悪い例: NoSQL インジェクション
db.users.find({ username: req.body.username })

// 良い例: 型をバリデーション
if (typeof req.body.username !== 'string') throw new Error();
db.users.find({ username: req.body.username })
```

**緩和策:**
1. パラメータ化されたインターフェースを持つ安全な API を使用
2. 許可リストですべての入力をバリデーション
3. 特定のインタープリター用に特殊文字をエスケープ
4. LIMIT とページネーションで大量開示を防止
5. サーバーサイドでの正（ポジティブ）入力バリデーションを実装

---

### A06:2025 – Insecure Design（安全でない設計）

**説明:** 完璧な実装では修正できない設計とアーキテクチャの欠陥。設計フェーズでのセキュリティコントロールの欠如または非効果を示す。

**よくある脆弱性:**
- 機密操作のレート制限の欠如
- 認証失敗時のアカウントロックアウトなし
- マルチテナントシステムのテナント分離の欠如
- 不正検知コントロールの欠如
- 信頼境界の不足

**防止策:**
```python
# 悪い例: パスワードリセットにレート制限なし
@app.route('/password-reset', methods=['POST'])
def password_reset():
    send_reset_email(request.form['email'])
    return "Email sent"

# 良い例: レート制限と検証
from flask_limiter import Limiter
limiter = Limiter(app)

@app.route('/password-reset', methods=['POST'])
@limiter.limit("3 per hour")
def password_reset():
    email = request.form['email']
    if not is_valid_email_format(email):
        abort(400)
    # 列挙を防ぐために一貫したタイミングを使用
    send_reset_email_async(email)
    return "If account exists, email was sent"
```

**緩和策:**
1. セキュリティ専門家を含む安全な開発ライフサイクルの確立
2. 安全な設計パターンライブラリの作成と使用
3. 認証、アクセス制御、ビジネスロジックの脅威モデリング
4. ユーザーストーリーにセキュリティ言語を統合
5. テナント分離とリソース制限の実装
6. ユーザー/サービスごとのリソース消費制限

---

### A07:2025 – Identification and Authentication Failures（識別と認証の失敗）

**説明:** ユーザーの身元確認、認証、セッション管理は重要。弱点があると攻撃者がパスワード、鍵、セッショントークンを侵害できる。

**よくある脆弱性:**
- 弱いまたはよく知られたパスワードの許可
- 弱い資格情報回復（知識ベースの質問）
- 平文または弱くハッシュ化されたパスワード
- MFA の欠如または非効果
- URL でのセッション ID の露出
- ログアウト時のセッションの適切な無効化の欠如

**防止策:**
```python
# パスワード強度要件
import re
def validate_password(password):
    if len(password) < 12:
        return False
    if password in COMMON_PASSWORDS:  # 漏洩リストに対してチェック
        return False
    return True

# セッション管理
@app.route('/logout')
@login_required
def logout():
    session.clear()  # サーバーサイドセッションをクリア
    response = redirect('/')
    response.delete_cookie('session')
    return response
```

**緩和策:**
1. 自動化攻撃を防ぐ MFA の実装
2. デフォルト認証情報を含めない
3. 漏洩パスワードリストに対してパスワードをチェック
4. NIST 800-63b に沿ったパスワードポリシー
5. 列挙攻撃への対策（一貫したレスポンス）
6. 指数バックオフによるログイン試行回数の制限
7. サーバーサイドの安全なセッションマネージャーの使用; ログイン後に ID を再生成

---

### A08:2025 – Software and Data Integrity Failures（ソフトウェアとデータの完全性の障害）

**説明:** 完全性違反から保護しないコードとインフラストラクチャ。安全でないデシリアライゼーション、署名されていない更新、検証なしの CI/CD を含む。

**よくある脆弱性:**
- 信頼できない CDN やリポジトリに依存するアプリケーション
- 整合性検証なしの自動更新
- 信頼できないデータの安全でないデシリアライゼーション
- 適切なアクセス制御のない CI/CD パイプライン
- 署名されていないまたは未検証のコードデプロイ

**防止策:**
```html
<!-- 悪い例: 整合性なしの CDN -->
<script src="https://cdn.example.com/lib.js"></script>

<!-- 良い例: サブリソース整合性 -->
<script src="https://cdn.example.com/lib.js"
        integrity="sha384-abc123..."
        crossorigin="anonymous"></script>
```

```python
# 悪い例: 安全でないデシリアライゼーション
import pickle
data = pickle.loads(user_input)

# 良い例: バリデーション付き安全なシリアライゼーション
import json
data = json.loads(user_input)
validate_schema(data)
```

**緩和策:**
1. デジタル署名でソフトウェア/データが期待されるソースからであることを検証
2. 信頼できるリポジトリからの依存関係を確保
3. ソフトウェアサプライチェーンセキュリティツールの使用（OWASP Dependency-Check）
4. コードと設定の変更をレビュー
5. CI/CD に適切な分離、設定、アクセス制御を確保
6. 信頼できないクライアントに署名/暗号化されていないシリアライズデータを送信しない

---

### A09:2025 – Security Logging and Monitoring Failures（セキュリティログとモニタリングの不備）

**説明:** ログとモニタリングがなければ、侵害を検出できない。不十分なログ、検出、モニタリング、レスポンスにより攻撃者が潜伏し続ける。

**よくある脆弱性:**
- 監査可能なイベントがログに記録されない（ログイン、ログイン失敗、トランザクション）
- 警告とエラーが不明確なログメッセージを生成
- ログがローカルにのみ保存
- アラート閾値が設定されていないまたは非効果
- ペネトレーションテストがアラートをトリガーしない
- アプリケーションがリアルタイムでアクティブな攻撃を検出できない

**防止策:**
```python
import logging
from datetime import datetime

# 構造化ログの設定
logging.basicConfig(
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('security')

@app.route('/login', methods=['POST'])
def login():
    user = authenticate(request.form['username'], request.form['password'])
    if user:
        logger.info(f"LOGIN_SUCCESS user={user.id} ip={request.remote_addr}")
        return redirect('/dashboard')
    else:
        logger.warning(f"LOGIN_FAILURE username={request.form['username']} ip={request.remote_addr}")
        return "Invalid credentials", 401
```

**緩和策:**
1. すべてのログイン、アクセス制御、サーバーサイドバリデーション失敗をログ記録
2. ログ管理ソリューションで消費可能な形式でログを生成
3. インジェクション攻撃を防ぐためにログデータを正しくエンコード
4. 高価値トランザクションに整合性管理付き監査証跡を確保
5. 効果的なモニタリングとアラートを確立
6. インシデント対応と復旧計画を作成（NIST 800-61r2）

---

### A10:2025 – Mishandling of Exceptional Conditions（例外的条件の不適切な処理）

**説明:** エラー、エッジケース、予期しない状態の処理の失敗に対処する新カテゴリ。不適切な例外処理は情報漏洩やセキュリティ障害を引き起こす可能性がある。

**よくある脆弱性:**
- ユーザーへのスタックトレースの露出
- コンポーネント間の一貫性のないエラーハンドリング
- フェイルオープン動作（エラー時のアクセス許可）
- 優雅な劣化なしのリソース枯渇
- エラーパスでの競合状態
- 不完全なトランザクションロールバック

**防止策:**
```python
# 悪い例: 情報漏洩
@app.errorhandler(Exception)
def handle_error(e):
    return str(e), 500  # 内部詳細を露出

# 良い例: 安全なエラーハンドリング
@app.errorhandler(Exception)
def handle_error(e):
    error_id = uuid.uuid4()
    logger.exception(f"Error {error_id}: {e}")
    return {"error": "An error occurred", "id": str(error_id)}, 500
```

```python
# 悪い例: フェイルオープン
def check_permission(user, resource):
    try:
        return authorization_service.check(user, resource)
    except Exception:
        return True  # フェイルオープン！

# 良い例: フェイルクローズド
def check_permission(user, resource):
    try:
        return authorization_service.check(user, resource)
    except Exception as e:
        logger.error(f"Auth check failed: {e}")
        return False  # フェイルクローズド
```

**緩和策:**
1. 障害を前提に設計: すべてのエラー条件を予測し処理
2. エラー時のフェイルクローズド（デフォルトで拒否）を実装
3. 適切な粒度で構造化された例外処理を使用
4. エンドユーザーに内部エラーを決して露出しない
5. デバッグ用のコンテキスト付きですべての例外をログ記録
6. 正常パスと同じ徹底度でエラーハンドリングパスをテスト
7. 外部依存関係のサーキットブレーカーを実装

---

## OWASP ASVS 5.0.0

Application Security Verification Standard (ASVS) 5.0.0 は 2025年5月30日にリリース。17 カテゴリにわたる約 350 のセキュリティ要件を 3 つの検証レベルで提供。

### 検証レベル

| レベル | ユースケース | 説明 |
|-------|----------|-------------|
| L1 | すべてのアプリケーション | 低リスクアプリケーション向けの基本的なセキュリティコントロール |
| L2 | ほとんどのアプリケーション | 機密データを扱うアプリケーション向けの標準セキュリティ |
| L3 | 高価値ターゲット | 重要インフラ、医療、金融向けの高度なセキュリティ |

### ASVS カテゴリ

1. **V1: アーキテクチャ、設計、脅威モデリング**
2. **V2: 認証**
3. **V3: セッション管理**
4. **V4: アクセス制御**
5. **V5: 入力バリデーション**
6. **V6: 保存時の暗号化**
7. **V7: エラーハンドリングとログ**
8. **V8: データ保護**
9. **V9: 通信**
10. **V10: 悪意のあるコード**
11. **V11: ビジネスロジック**
12. **V12: ファイルとリソース**
13. **V13: API と Web サービス**
14. **V14: 設定**
15. **V15: OAuth と OIDC**（5.0 の新規）
16. **V16: 自己完結型トークン**（5.0 の新規）
17. **V17: WebSockets**（5.0 の新規）

### 主要な要件の例

**認証 (V2):**
- V2.1.1: ユーザーパスワードは最低 12 文字でなければならない（SHALL）
- V2.1.6: パスワードは漏洩パスワードリストに対してチェックされなければならない（SHALL）
- V2.2.1: クレデンシャルスタッフィングを防ぐアンチオートメーションコントロールが必要（SHALL）
- V2.5.2: パスワード回復はアカウントの存在を明かしてはならない（SHALL NOT）

**セッション管理 (V3):**
- V3.2.1: セッショントークンは最低 128 ビットのエントロピーを持つこと（SHALL）
- V3.3.1: ログアウト時にセッションを無効化すること（SHALL）
- V3.4.1: Cookie ベースのトークンは Secure 属性を設定すること（SHALL）

**アクセス制御 (V4):**
- V4.1.1: アクセス制御はサーバーサイドで強制すること（SHALL）
- V4.2.1: 機密データは認可されたユーザーのみがアクセス可能であること（SHALL）
- V4.3.1: ディレクトリブラウジングを無効化すること（SHALL）

**暗号化 (V6):**
- V6.2.1: すべての暗号モジュールは安全に失敗すること（SHALL）
- V6.4.1: 鍵は承認された乱数生成器を使用して生成すること（SHALL）
- V6.4.2: 鍵は安全に保管すること（HSM, vault）（SHALL）

---

## OWASP Top 10 for Agentic Applications 2026

2025年12月にリリース。AI エージェント、マルチエージェントシステム、自律型アプリケーションに特有のセキュリティリスクに対処するフレームワーク。

### サマリーテーブル

| ID | リスク | 説明 |
|----|------|-------------|
| ASI01 | Agent Goal Hijack | プロンプトインジェクションがエージェントの中核目標を変更 |
| ASI02 | Tool Misuse | 正当なツールが意図しない/安全でない方法で使用される |
| ASI03 | Identity & Privilege Abuse | エージェント間インタラクションでの資格情報のエスカレーション |
| ASI04 | Supply Chain Vulnerabilities | 侵害されたプラグイン、MCP サーバー、または依存関係 |
| ASI05 | Unexpected Code Execution | エージェントによる安全でないコード生成または実行 |
| ASI06 | Memory & Context Poisoning | RAG システムやエージェントメモリの操作 |
| ASI07 | Insecure Inter-Agent Communication | エージェントシステム間のなりすましや改ざん |
| ASI08 | Cascading Failures | 相互接続されたシステム全体へのエラー伝播 |
| ASI09 | Human-Agent Trust Exploitation | AI 生成コンテンツによるソーシャルエンジニアリング |
| ASI10 | Rogue Agents | システム内の侵害された/悪意のあるエージェント |

---

### ASI01: Agent Goal Hijack（エージェント目標のハイジャック）

**説明:** 攻撃者がプロンプトインジェクションを使用してエージェントの意図された目標を変更し、正常に機能しているように見せながら悪意のある目的に利用する。

**攻撃ベクター:**
- ユーザー入力での直接プロンプトインジェクション
- 侵害されたデータソースを通じた間接インジェクション
- ドキュメント、Web サイト、メールに隠された指示
- マルチターン会話の操作

**防止策:**
- 厳格な入力サニタイゼーションとフィルタリングの実装
- エージェントの応答を制限する構造化出力形式の使用
- システムプロンプトで明確な目標境界を確立
- 行動分析による目標逸脱の監視
- 機密操作での Human-in-the-loop の実装

---

### ASI02: Tool Misuse（ツールの悪用）

**説明:** ツール（API、データベース、ファイルシステム）にアクセスできるエージェントが、悪意のある指示や欠陥のある推論により意図しない方法でそれらを使用する可能性がある。

**攻撃ベクター:**
- エージェントをだまして有害なコマンドを実行させる
- 昇格された権限でのツール使用
- 不正な結果を達成するためのツールコールの連鎖
- 曖昧なツール説明の悪用

**防止策:**
- すべてのツールアクセスに最小権限の原則を適用
- ツールごとの細粒度権限の実装
- すべてのツール入出力のバリデーション
- ツール使用ポリシーの作成と強制
- 監査のためのすべてのツール呼び出しのログ記録

---

### ASI03: Identity & Privilege Abuse（ID と権限の悪用）

**説明:** エージェントが、特にマルチエージェントや長時間実行のコンテキストで、適切な範囲を超えて権限を継承、蓄積、またはエスカレーションする可能性がある。

**攻撃ベクター:**
- プロンプトインジェクションによる資格情報の窃取
- セッショントークンの露出
- ツールチェーンによる権限昇格
- マルチエージェントシステムでの ID 混乱

**防止策:**
- 短期間の、スコープ付き資格情報の使用
- エージェント間の ID 検証の実装
- エージェントコンテキストを通じた生の資格情報の受け渡しをしない
- 権限使用パターンの監査
- 資格情報のローテーションの実装

---

### ASI04: Supply Chain Vulnerabilities（サプライチェーンの脆弱性）

**説明:** 侵害されたプラグイン、MCP サーバー、またはサードパーティ統合がエージェントシステムに脆弱性を導入する。

**攻撃ベクター:**
- 悪意のある MCP サーバー実装
- プラグインレジストリでのタイポスクワッティング
- 侵害された更新メカニズム
- バックドア付きエージェントフレームワーク

**防止策:**
- プラグイン/サーバーの信頼性と署名の検証
- すべての統合のインベントリ維持
- サードパーティコンポーネントのサンドボックス化
- 統合からの異常な動作の監視
- 許可されたプラグインの許可リストの使用

---

### ASI05: Unexpected Code Execution（予期しないコード実行）

**説明:** コードを生成または実行するエージェントが、悪意のあるコードの実行にだまされる可能性がある。

**攻撃ベクター:**
- プロンプトを通じたコードインジェクション
- 取得されたコンテキスト内の悪意のあるコード
- 安全でないコード実行環境
- 難読化によるコードレビューのバイパス

**防止策:**
- サンドボックス環境で生成されたコードを実行
- 実行前の静的分析の実装
- コード実行機能の制限
- 機密操作の人間による承認の要求
- 許可された操作の許可リストの使用

---

### ASI06: Memory & Context Poisoning（メモリとコンテキストの汚染）

**説明:** 攻撃者がエージェントのメモリ、RAG データベース、またはコンテキストを破壊し、将来の動作に影響を与える。

**攻撃ベクター:**
- ベクターデータベースへの悪意のあるコンテンツの注入
- 会話履歴の操作
- ナレッジベースの汚染
- コンテキストウィンドウの制限の悪用

**防止策:**
- すべての保存コンテンツのバリデーションとサニタイズ
- コンテンツ整合性検証の実装
- 信頼レベルによるメモリのセグメント化
- 保存された知識の定期的な監査
- メモリの減衰/有効期限の実装

---

### ASI07: Insecure Inter-Agent Communication（安全でないエージェント間通信）

**説明:** エージェント間の通信が傍受、なりすまし、または改ざんに対して脆弱である可能性がある。

**攻撃ベクター:**
- エージェント通信への中間者攻撃
- エージェント ID のなりすまし
- メッセージの改ざん
- リプレイ攻撃

**防止策:**
- すべてのエージェント通信の認証
- エージェント間メッセージの暗号化
- メッセージ整合性検証の実装
- エージェントオーケストレーション用の安全なチャネルの使用
- 暗号的なエージェント ID の検証

---

### ASI08: Cascading Failures（カスケード障害）

**説明:** 1 つのエージェントまたはコンポーネントのエラーが、相互接続されたシステム全体に伝播し、広範な障害を引き起こす。

**攻撃ベクター:**
- エージェントチェーン全体にカスケードするエラーのトリガー
- 1 つのエージェントのリソース枯渇が他に影響
- 機密情報を露出するエラーハンドリング
- 失敗した操作からのリトライストーム

**防止策:**
- エージェント間のサーキットブレーカーの実装
- 優雅な劣化の設計
- エージェント障害の分離
- エージェント間コールのレート制限
- カスケードパターンの監視

---

### ASI09: Human-Agent Trust Exploitation（人間-エージェント間の信頼の悪用）

**説明:** 攻撃者が人間が AI エージェントに寄せる信頼を利用してソーシャルエンジニアリング攻撃を行う。

**攻撃ベクター:**
- AI 生成フィッシングコンテンツ
- エージェント応答を通じたなりすまし
- 有用に見えるエージェントを通じた信頼の悪用
- 欺瞞的なマルチターン会話

**防止策:**
- AI 生成コンテンツの明確なラベリング
- AI の限界に関するユーザー教育
- 機密アクションの検証ステップ
- 重要な判断に対する人間の監視の維持
- 不審な動作の検出の実装

---

### ASI10: Rogue Agents（ローグエージェント）

**説明:** 外部攻撃または欠陥のある設計により、侵害されたまたは悪意を持って行動するエージェント。

**攻撃ベクター:**
- インジェクション攻撃によるエージェントの侵害
- 悪意のあるエージェントのデプロイ
- エージェント動作の変更
- エージェントシステムを通じたインサイダー脅威

**防止策:**
- 異常に対するエージェント動作の監視
- エージェントの認証と認可の実装
- エージェントシステムの定期的なセキュリティ監査
- エージェント操作のキルスイッチ
- 動作ベースラインと逸脱検出

---

## 主要なセキュリティ原則

### 多層防御（Defense in Depth）
複数のセキュリティコントロールを重層化し、1 つが失敗しても他が保護を提供するようにする。

### 最小権限（Least Privilege）
機能に必要な最小限の権限を付与する。不要なアクセスを定期的にレビューし取り消す。

### フェイルセキュア（Fail Secure）
エラーが発生した場合、安全な状態をデフォルトとする。不確実な場合はアクセスを許可するのではなく拒否する。

### ゼロトラスト（Zero Trust）
信頼せず、常に検証する。ソースに関係なく、すべてのリクエストを認証・認可する。

### デフォルトで安全（Secure by Default）
安全なデフォルトで製品を出荷する。セキュリティを低下させるには明示的なアクションを要求する。

### 入力バリデーション（Input Validation）
すべての入力をサーバーサイドでバリデーションする。拒否リストよりも許可リストを使用する。

### 出力エンコーディング（Output Encoding）
コンテキスト（HTML, JavaScript, SQL など）に基づいて出力をエンコードし、インジェクションを防止する。

### セキュリティをシンプルに（Keep Security Simple）
複雑なセキュリティはしばしばバイパスされる。シンプルで理解しやすいコントロールを優先する。

---

## 出典と参考資料

### 公式 OWASP リソース
- [OWASP Top 10:2025](https://owasp.org/Top10/)
- [OWASP ASVS 5.0](https://github.com/OWASP/ASVS)
- [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/)
- [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/)

### 業界分析
- [GitLab: OWASP Top 10 2025 - What's Changed and Why It Matters](https://about.gitlab.com/blog/)
- [Aikido: OWASP Top 10 for Agentic Applications Guide](https://www.aikido.dev/blog/)
- [Security Boulevard: OWASP 2025 Analysis](https://securityboulevard.com/)

### 標準とガイドライン
- [NIST SP 800-63b: Digital Identity Guidelines](https://pages.nist.gov/800-63-3/)
- [NIST SP 800-61r2: Incident Handling Guide](https://csrc.nist.gov/publications/detail/sp/800-61/rev-2/final)
- [CWE/SANS Top 25 Software Errors](https://cwe.mitre.org/top25/)

---

*最終更新: 2026年1月*
