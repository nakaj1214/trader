# OWASPセキュリティベストプラクティス スキル

コードを書く・レビューする際にこれらのセキュリティ標準を適用する。

## クイックリファレンス: OWASP Top 10:2025

| # | 脆弱性 | 主な対策 |
|---|---------------|----------------|
| A01 | アクセス制御の不備 | デフォルト拒否、サーバーサイドで強制、所有権を確認 |
| A02 | セキュリティの設定ミス | 設定を堅牢化、デフォルト無効化、機能を最小化 |
| A03 | サプライチェーンの失敗 | バージョンを固定、整合性を確認、依存関係を監査 |
| A04 | 暗号化の失敗 | TLS 1.2+、AES-256-GCM、パスワードにArgon2/bcrypt |
| A05 | インジェクション | パラメータ化クエリ、入力検証、安全なAPI |
| A06 | 不安全な設計 | 脅威モデリング、レート制限、セキュリティ制御の設計 |
| A07 | 認証の失敗 | MFA、漏洩パスワードチェック、セキュアなセッション |
| A08 | 整合性の失敗 | パッケージの署名、CDNにSRI、安全なデシリアライゼーション |
| A09 | ロギングの失敗 | セキュリティイベントのログ、構造化フォーマット、アラート |
| A10 | 例外処理の失敗 | フェイルクローズド、内部情報の隠蔽、コンテキスト付きログ |

## セキュリティコードレビューチェックリスト

コードをレビューする際に以下の問題をチェックする:

### 入力処理
- [ ] 全ユーザー入力をサーバーサイドで検証
- [ ] パラメータ化クエリを使用（文字列連結は不使用）
- [ ] 入力長制限を強制
- [ ] デニーリストよりアローリスト検証を優先

### 認証とセッション
- [ ] パスワードをArgon2/bcryptでハッシュ（MD5/SHA1は不使用）
- [ ] セッショントークンに十分なエントロピー（128ビット以上）
- [ ] ログアウト時にセッションを無効化
- [ ] センシティブな操作にMFAを利用可能

### アクセス制御
- [ ] 全リクエストで認可を確認
- [ ] ユーザーが操作できないオブジェクト参照を使用
- [ ] デフォルト拒否ポリシー
- [ ] 特権昇格パスを確認

### データ保護
- [ ] センシティブデータを静止時に暗号化
- [ ] 全データ転送にTLS
- [ ] URL/ログにセンシティブデータを含めない
- [ ] シークレットは環境/バルトに（コードには含めない）

### エラーハンドリング
- [ ] ユーザーにスタックトレースを露出しない
- [ ] エラー時はフェイルクローズド（拒否、許可しない）
- [ ] 全例外をコンテキスト付きでログ
- [ ] 一貫したエラーレスポンス（列挙なし）

## セキュアなコードパターン

### SQLインジェクション対策
```python
# 危険
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")

# 安全
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

### コマンドインジェクション対策
```python
# 危険
os.system(f"convert {filename} output.png")

# 安全
subprocess.run(["convert", filename, "output.png"], shell=False)
```

### パスワードの保存
```python
# 危険
hashlib.md5(password.encode()).hexdigest()

# 安全
from argon2 import PasswordHasher
PasswordHasher().hash(password)
```

### アクセス制御
```python
# 危険 - 認可チェックなし
@app.route('/api/user/<user_id>')
def get_user(user_id):
    return db.get_user(user_id)

# 安全 - 認可を強制
@app.route('/api/user/<user_id>')
@login_required
def get_user(user_id):
    if current_user.id != user_id and not current_user.is_admin:
        abort(403)
    return db.get_user(user_id)
```

### エラーハンドリング
```python
# 危険 - 内部情報を露出
@app.errorhandler(Exception)
def handle_error(e):
    return str(e), 500

# 安全 - フェイルクローズド、コンテキスト付きログ
@app.errorhandler(Exception)
def handle_error(e):
    error_id = uuid.uuid4()
    logger.exception(f"Error {error_id}: {e}")
    return {"error": "An error occurred", "id": str(error_id)}, 500
```

### フェイルクローズドパターン
```python
# 危険 - フェイルオープン
def check_permission(user, resource):
    try:
        return auth_service.check(user, resource)
    except Exception:
        return True  # 危険！

# 安全 - フェイルクローズド
def check_permission(user, resource):
    try:
        return auth_service.check(user, resource)
    except Exception as e:
        logger.error(f"Auth check failed: {e}")
        return False  # エラー時は拒否
```

## エージェントAIセキュリティ（OWASP 2026）

AIエージェントシステムを構築・レビューする際のチェック項目:

| リスク | 説明 | 軽減策 |
|------|-------------|------------|
| ASI01: ゴールハイジャック | プロンプトインジェクションがエージェントの目標を変更 | 入力サニタイズ、ゴール境界、行動監視 |
| ASI02: ツールの悪用 | ツールが意図しない方法で使用される | 最小権限、細粒度の権限、I/Oの検証 |
| ASI03: 特権の乱用 | エージェント間での認証情報のエスカレーション | 短命のスコープ付きトークン、ID検証 |
| ASI04: サプライチェーン | 侵害されたプラグイン/MCPサーバー | 署名を確認、サンドボックス、プラグインのアローリスト |
| ASI05: コード実行 | 安全でないコード生成/実行 | サンドボックス実行、静的解析、人間の承認 |
| ASI06: メモリ汚染 | 破損したRAG/コンテキストデータ | 保存コンテンツの検証、信頼レベルでセグメント化 |
| ASI07: エージェント通信 | エージェント間のなりすまし | 認証、暗号化、メッセージ整合性の確認 |
| ASI08: カスケード障害 | エラーがシステム間で伝播 | サーキットブレーカー、グレースフルデグラデーション、分離 |
| ASI09: 信頼の悪用 | AIを介したソーシャルエンジニアリング | AIコンテンツのラベル付け、ユーザー教育、確認ステップ |
| ASI10: 悪意のあるエージェント | 侵害されたエージェントが悪意を持って行動 | 行動監視、キルスイッチ、異常検知 |

### エージェントセキュリティチェックリスト

- [ ] 全エージェント入力がサニタイズ・検証されている
- [ ] ツールが最小必要権限で動作する
- [ ] 認証情報が短命でスコープ付き
- [ ] サードパーティプラグインが検証・サンドボックス化されている
- [ ] コード実行が隔離された環境で行われる
- [ ] エージェント通信が認証・暗号化されている
- [ ] エージェントコンポーネント間にサーキットブレーカーがある
- [ ] センシティブな操作に人間の承認が必要
- [ ] 異常検知のための行動監視がある
- [ ] エージェントシステムのキルスイッチが利用可能

## ASVS 5.0の主要要件

### レベル1（全アプリケーション）
- パスワードは最低12文字
- 漏洩パスワードリストとの照合
- 認証のレート制限
- セッショントークンは128ビット以上のエントロピー
- HTTPS必須

### レベル2（センシティブデータ）
- L1の全要件に加えて:
- センシティブな操作にMFA
- 暗号鍵の管理
- 包括的なセキュリティログ
- 全パラメータの入力検証

### レベル3（クリティカルなシステム）
- L1/L2の全要件に加えて:
- 鍵のためのハードウェアセキュリティモジュール
- 脅威モデリングの文書化
- 高度な監視とアラート
- ペネトレーションテストによる検証

## 言語別セキュリティの注意点

> **重要:** 以下の例は解説の出発点であり、包括的なリストではない。コードをレビューする際は、上級セキュリティ研究者のように考える: 言語のメモリモデル、型システム、標準ライブラリの落とし穴、エコシステム固有の攻撃ベクトル、過去のCVEパターンを考慮すること。各言語にはここに記載されている以上の深い注意点がある。

様々な言語には固有のセキュリティの落とし穴がある。以下は主要な20言語と主要なセキュリティ上の考慮事項。**作業中の特定の言語についてはより深く調べること:**

---

### JavaScript / TypeScript
**主なリスク:** プロトタイプ汚染、XSS、evalインジェクション
```javascript
// 危険: プロトタイプ汚染
Object.assign(target, userInput)
// 安全: nullプロトタイプを使用するか、キーを検証する
Object.assign(Object.create(null), validated)

// 危険: evalインジェクション
eval(userCode)
// 安全: ユーザー入力でevalを絶対に使わない
```
**注意点:** `eval()`、`innerHTML`、`document.write()`、プロトタイプチェーン操作、`__proto__`

---

### Python
**主なリスク:** Pickleデシリアライゼーション、フォーマット文字列インジェクション、シェルインジェクション
```python
# 危険: Pickle RCE
pickle.loads(user_data)
# 安全: JSONを使うかソースを検証する
json.loads(user_data)

# 危険: フォーマット文字列インジェクション
query = "SELECT * FROM users WHERE name = '%s'" % user_input
# 安全: パラメータ化
cursor.execute("SELECT * FROM users WHERE name = %s", (user_input,))
```
**注意点:** `pickle`、`eval()`、`exec()`、`os.system()`、`shell=True`の`subprocess`

---

### Java
**主なリスク:** デシリアライゼーションRCE、XXE、JNDIインジェクション
```java
// 危険: 任意のデシリアライゼーション
ObjectInputStream ois = new ObjectInputStream(userStream);
Object obj = ois.readObject();

// 安全: アローリストまたはJSONを使用
ObjectMapper mapper = new ObjectMapper();
mapper.readValue(json, SafeClass.class);
```
**注意点:** `ObjectInputStream`、`Runtime.exec()`、XXE保護なしのXMLパーサー、JNDIルックアップ

---

### C#
**主なリスク:** デシリアライゼーション、SQLインジェクション、パストラバーサル
```csharp
// 危険: BinaryFormatter RCE
BinaryFormatter bf = new BinaryFormatter();
object obj = bf.Deserialize(stream);

// 安全: System.Text.Jsonを使用
var obj = JsonSerializer.Deserialize<SafeType>(json);
```
**注意点:** `BinaryFormatter`、`JavaScriptSerializer`、`TypeNameHandling.All`、生SQLの文字列

---

### PHP
**主なリスク:** 型ジャグリング、ファイルインクルージョン、オブジェクトインジェクション
```php
// 危険: 型ジャグリングによる認証バイパス
if ($password == $stored_hash) { ... }
// 安全: 厳密な比較を使用
if (hash_equals($stored_hash, $password)) { ... }

// 危険: ファイルインクルージョン
include($_GET['page'] . '.php');
// 安全: アローリストでページを管理
$allowed = ['home', 'about']; include(in_array($page, $allowed) ? "$page.php" : 'home.php');
```
**注意点:** `==` vs `===`、`include/require`、`unserialize()`、`/e`付きの`preg_replace`、`extract()`

---

### Go
**主なリスク:** 競合状態、テンプレートインジェクション、スライス境界
```go
// 危険: 競合状態
go func() { counter++ }()
// 安全: sync プリミティブを使用
atomic.AddInt64(&counter, 1)

// 危険: テンプレートインジェクション
template.HTML(userInput)
// 安全: テンプレートにエスケープさせる
{{.UserInput}}
```
**注意点:** ゴルーチンのデータ競合、`template.HTML()`、`unsafe`パッケージ、未チェックのスライスアクセス

---

### Ruby
**主なリスク:** マスアサインメント、YAMLデシリアライゼーション、正規表現DoS
```ruby
# 危険: マスアサインメント
User.new(params[:user])
# 安全: ストロングパラメータ
User.new(params.require(:user).permit(:name, :email))

# 危険: YAML RCE
YAML.load(user_input)
# 安全: safe_loadを使用
YAML.safe_load(user_input)
```
**注意点:** YAML.load、Marshal.load、eval、ユーザー入力を使ったsend、.permit!

---

### Rust
**主なリスク:** unsafeブロック、FFI境界の問題、リリース時の整数オーバーフロー
```rust
// 注意: unsafeは安全性をバイパスする
unsafe { ptr::read(user_ptr) }

// 注意: リリースビルドの整数オーバーフロー
let x: u8 = 255;
let y = x + 1; // リリースビルドでは0にラップされる！
// 安全: チェックされた算術演算を使用
let y = x.checked_add(1).unwrap_or(255);
```
**注意点:** `unsafe`ブロック、FFI呼び出し、リリースビルドの整数オーバーフロー、信頼されない入力への`.unwrap()`

---

### Swift
**主なリスク:** 強制アンラップによるクラッシュ、Objective-Cの相互運用
```swift
// 危険: 信頼されないデータへの強制アンラップ
let value = jsonDict["key"]!
// 安全: 安全なアンラップ
guard let value = jsonDict["key"] else { return }

// 危険: フォーマット文字列
String(format: userInput, args)
// 安全: ユーザー入力をフォーマットとして使わない
```
**注意点:** 強制アンラップ(!)、try!、ObjCブリッジング、NSSecureCodingの誤用

---

### Kotlin
**主なリスク:** null安全性のバイパス、Java相互運用、シリアライゼーション
```kotlin
// 危険: JavaからのプラットフォームタイプによるNPE
val len = javaString.length // nullの場合にNPE
// 安全: 明示的なnullチェック
val len = javaString?.length ?: 0

// 危険: リフレクション
clazz.getDeclaredMethod(userInput)
// 安全: メソッドのアローリスト
```
**注意点:** Java相互運用のnull(!演算子)、リフレクション、シリアライゼーション、プラットフォームタイプ

---

### C / C++
**主なリスク:** バッファオーバーフロー、use-after-free、フォーマット文字列
```c
// 危険: バッファオーバーフロー
char buf[10]; strcpy(buf, userInput);
// 安全: 境界チェック
strncpy(buf, userInput, sizeof(buf) - 1);

// 危険: フォーマット文字列
printf(userInput);
// 安全: 常にフォーマット指定子を使用
printf("%s", userInput);
```
**注意点:** `strcpy`、`sprintf`、`gets`、ポインタ演算、手動メモリ管理、整数オーバーフロー

---

### Scala
**主なリスク:** XML外部エンティティ、シリアライゼーション、パターンマッチングの網羅性
```scala
// 危険: XXE
val xml = XML.loadString(userInput)
// 安全: 外部エンティティを無効化
val factory = SAXParserFactory.newInstance()
factory.setFeature("http://xml.org/sax/features/external-general-entities", false)
```
**注意点:** Java相互運用の問題、XMLパース、`Serializable`、網羅的なパターンマッチング

---

### R
**主なリスク:** コードインジェクション、ファイルパス操作
```r
# 危険: evalインジェクション
eval(parse(text = user_input))
# 安全: ユーザー入力をコードとして絶対にパースしない

# 危険: パストラバーサル
read.csv(paste0("data/", user_file))
# 安全: ファイル名を検証
if (grepl("^[a-zA-Z0-9]+\\.csv$", user_file)) read.csv(...)
```
**注意点:** `eval()`、`parse()`、`source()`、`system()`、ファイルパス操作

---

### Perl
**主なリスク:** 正規表現インジェクション、open()インジェクション、テイントモードのバイパス
```perl
# 危険: 正規表現DoS
$input =~ /$user_pattern/;
# 安全: quotemetaを使用
$input =~ /\Q$user_pattern\E/;

# 危険: open()コマンドインジェクション
open(FILE, $user_file);
# 安全: 3引数のopen
open(my $fh, '<', $user_file);
```
**注意点:** 2引数の`open()`、ユーザー入力からの正規表現、バッククォート、`eval`、テイントモード無効化

---

### Shell (Bash)
**主なリスク:** コマンドインジェクション、ワード分割、グロビング
```bash
# 危険: 引用符なしの変数
rm $user_file
# 安全: 常に引用符を使用
rm "$user_file"

# 危険: eval
eval "$user_command"
# 安全: ユーザー入力でevalを絶対に使わない
```
**注意点:** 引用符なしの変数、`eval`、バッククォート、ユーザー入力での`$(...)`、`set -euo pipefail`の欠如

---

### Lua
**主なリスク:** サンドボックスエスケープ、loadstringインジェクション
```lua
-- 危険: コードインジェクション
loadstring(user_code)()
-- 安全: 制限された関数を持つサンドボックス環境を使用
```
**注意点:** `loadstring`、`loadfile`、`dofile`、`os.execute`、`io`ライブラリ、debugライブラリ

---

### Elixir
**主なリスク:** アトム枯渇、コードインジェクション、ETSアクセス
```elixir
# 危険: アトム枯渇DoS
String.to_atom(user_input)
# 安全: 既存のアトムのみを使用
String.to_existing_atom(user_input)

# 危険: コードインジェクション
Code.eval_string(user_input)
# 安全: ユーザー入力でevalを絶対に使わない
```
**注意点:** `String.to_atom`、`Code.eval_string`、`:erlang.binary_to_term`、ETPパブリックテーブル

---

### Dart / Flutter
**主なリスク:** プラットフォームチャネルインジェクション、安全でないストレージ
```dart
// 危険: SharedPreferencesへのシークレット保存
prefs.setString('auth_token', token);
// 安全: flutter_secure_storageを使用
secureStorage.write(key: 'auth_token', value: token);
```
**注意点:** プラットフォームチャネルデータ、`dart:mirrors`、`Function.apply`、安全でないローカルストレージ

---

### PowerShell
**主なリスク:** コマンドインジェクション、実行ポリシーバイパス
```powershell
# 危険: インジェクション
Invoke-Expression $userInput
# 安全: ユーザーデータでInvoke-Expressionを避ける

# 危険: 未検証のパス
Get-Content $userPath
# 安全: パスが許可されたディレクトリ内であることを検証
```
**注意点:** `Invoke-Expression`、`& $userVar`、ユーザー引数を使った`Start-Process`、`-ExecutionPolicy Bypass`

---

### SQL（全方言）
**主なリスク:** インジェクション、特権エスカレーション、データ漏洩
```sql
-- 危険: 文字列連結
"SELECT * FROM users WHERE id = " + userId

-- 安全: パラメータ化クエリ（言語固有）
-- 全ケースでプリペアドステートメントを使用
```
**注意点:** 動的SQL、`EXECUTE IMMEDIATE`、動的クエリを使ったストアドプロシージャ、権限の付与

---

## 深いセキュリティ分析のマインドセット

任意の言語をレビューする際は、上級セキュリティ研究者のように考える:

1. **メモリモデル:** 言語はどのようにメモリを扱うか？ 管理されているか手動か？ GCの一時停止は悪用可能か？
2. **型システム:** 弱い型付け = 型混乱攻撃。強制の悪用を探す。
3. **シリアライゼーション:** 全言語にはPickle/Marshal相当のものがある。すべて危険。
4. **並行性:** スレッドモデル固有の競合状態、TOCTOU、アトミシティの失敗。
5. **FFI境界:** ネイティブ相互運用は型安全性が崩れる場所。
6. **標準ライブラリ:** 標準ライブラリの過去のCVE（Python urllib、Java XML、Ruby OpenSSL）。
7. **パッケージエコシステム:** タイポスクワッティング、依存関係の混乱、悪意のあるパッケージ。
8. **ビルドシステム:** ビルド中のMakefile/gradle/npmスクリプトインジェクション。
9. **ランタイムの動作:** デバッグとリリースの違い（Rustのオーバーフロー、C++のアサーション）。
10. **エラーハンドリング:** 言語はどのように失敗するか？ サイレントに？ スタックトレースで？ フェイルオープンで？

**リストにない言語の場合:** その言語固有のCWEパターン、CVE履歴、既知の落とし穴を調査する。上記の例は入口点であり、完全なカバレッジではない。

## このスキルをいつ適用するか

以下の場合にこのスキルを使用する:
- 認証または認可コードを書く
- ユーザー入力または外部データを処理する
- 暗号化またはパスワード保存を実装する
- コードのセキュリティ脆弱性をレビューする
- APIエンドポイントを設計する
- AIエージェントシステムを構築する
- アプリケーションのセキュリティ設定を構成する
- エラーと例外を処理する
- サードパーティの依存関係を扱う
- **任意の言語で作業する** - 上記の深い分析マインドセットを適用する
