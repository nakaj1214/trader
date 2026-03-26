# Varlockセキュリティスキル

Claudeコードセッションのためのセキュアバイデフォルト環境変数管理。

> **リポジトリ**: https://github.com/dmno-dev/varlock
> **ドキュメント**: https://varlock.dev

## 基本原則: シークレットは絶対に露出させない

Claudeと作業する際、シークレットは以下のいずれにも現れてはならない:
- ターミナル出力
- Claudeの入出力コンテキスト
- ログファイルやトレース
- Gitコミットやdiff
- エラーメッセージ

このスキルはすべてのセンシティブデータを適切に保護する。

---

## 重要: Claudeのセキュリティルール

### ルール1: シークレットをechoしない

```bash
# ❌ 絶対にしてはいけない - Claudeのコンテキストにシークレットが露出する
echo $CLERK_SECRET_KEY
cat .env | grep SECRET
printenv | grep API

# ✅ これをする - 露出せずに検証する
varlock load --quiet && echo "✓ シークレット検証済み"
```

### ルール2: .envを直接読まない

```bash
# ❌ 絶対にしてはいけない - 全シークレットが露出する
cat .env
less .env
Read tool on .env file

# ✅ これをする - 値ではなくスキーマを読む（安全）
cat .env.schema
varlock load  # マスクされた値を表示
```

### ルール3: 検証にVarlockを使う

```bash
# ❌ 絶対にしてはいけない - エラーでシークレットが露出する
test -n "$API_KEY" && echo "Key: $API_KEY"

# ✅ これをする - Varlockが検証してマスクする
varlock load
# 出力: API_KEY 🔐sensitive └ ▒▒▒▒▒
```

### ルール4: コマンドにシークレットを含めない

```bash
# ❌ 絶対にしてはいけない - コマンド履歴にシークレットが残る
curl -H "Authorization: Bearer sk_live_xxx" https://api.example.com

# ✅ これをする - 環境変数を使う
curl -H "Authorization: Bearer $API_KEY" https://api.example.com
# より良い方法: varlock run -- curl ...
```

---

## クイックスタート

### インストール

```bash
# Varlock CLIをインストール
curl -sSfL https://varlock.dev/install.sh | sh -s -- --force-no-brew

# PATHに追加（~/.zshrcまたは~/.bashrcに追加）
export PATH="$HOME/.varlock/bin:$PATH"

# 確認
varlock --version
```

### プロジェクトの初期化

```bash
# 既存の.envから.env.schemaを作成
varlock init

# または手動で作成
touch .env.schema
```

---

## スキーマファイル: .env.schema

スキーマは各変数の型、バリデーション、センシティビティを定義する。

### 基本構造

```bash
# グローバルデフォルト
# @defaultSensitive=true @defaultRequired=infer

# アプリケーション
# @type=enum(development,staging,production) @sensitive=false
NODE_ENV=development

# @type=port @sensitive=false
PORT=3000

# データベース - センシティブ
# @type=url @required
DATABASE_URL=

# @type=string @required @sensitive
DATABASE_PASSWORD=

# APIキー - センシティブ
# @type=string(startsWith=sk_) @required @sensitive
STRIPE_SECRET_KEY=

# @type=string(startsWith=pk_) @sensitive=false
STRIPE_PUBLISHABLE_KEY=
```

### セキュリティアノテーション

| アノテーション | 効果 | 用途 |
|------------|--------|---------|
| `@sensitive` | 全出力でマスク | APIキー、パスワード、トークン |
| `@sensitive=false` | ログに表示 | 公開鍵、シークレットでない設定 |
| `@defaultSensitive=true` | 全変数をデフォルトでセンシティブに | セキュリティ重視プロジェクト |

### 型アノテーション

| 型 | バリデーション | 例 |
|------|-----------|---------|
| `string` | 任意文字列 | `@type=string` |
| `string(startsWith=X)` | プレフィックス検証 | `@type=string(startsWith=sk_)` |
| `string(contains=X)` | 部分文字列検証 | `@type=string(contains=+clerk_test)` |
| `url` | 有効なURL | `@type=url` |
| `port` | 1-65535 | `@type=port` |
| `boolean` | true/false | `@type=boolean` |
| `enum(a,b,c)` | 指定値のいずれか | `@type=enum(dev,prod)` |

---

## Claudeが安全に使えるコマンド

### 環境の検証

```bash
# 全変数を確認（安全 - センシティブな値はマスクされる）
varlock load

# クワイエットモード（成功時は出力なし）
varlock load --quiet

# 特定の環境を確認
varlock load --env=production
```

### シークレットを使ったコマンドの実行

```bash
# 検証済み環境をコマンドに注入
varlock run -- npm start
varlock run -- node script.js
varlock run -- pytest

# シークレットはコマンドから利用できるが、表示はされない
```

### スキーマの確認（安全）

```bash
# スキーマは安全に読める - 値を含まない
cat .env.schema

# 期待される変数を一覧表示
grep "^[A-Z]" .env.schema
```

---

## 一般的なパターン

### パターン1: 操作前に検証する

```bash
# 常に最初に環境を検証する
varlock load --quiet || {
  echo "❌ 環境検証失敗"
  exit 1
}

# その後、操作を進める
npm run build
```

### パターン2: 安全なシークレットローテーション

```bash
# 1. 外部ソース（1Password、AWSなど）でシークレットを更新
# 2. .envファイルを手動で更新（Claudeには頼まない）
# 3. 新しい値が機能するか検証
varlock load

# 4. GitHub Secretsを使っている場合は同期（値は表示されない）
./scripts/update-github-secrets.sh
```

### パターン3: CI/CD統合

```yaml
# GitHub Actions - GitHub Secretsからのシークレット
- name: 環境を検証
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}
    API_KEY: ${{ secrets.API_KEY }}
  run: varlock load --quiet
```

### パターン4: Docker統合

```dockerfile
# コンテナにVarlockをインストール
RUN curl -sSfL https://varlock.dev/install.sh | sh -s -- --force-no-brew \
    && ln -s /root/.varlock/bin/varlock /usr/local/bin/varlock

# コンテナ起動時に検証
CMD ["varlock", "run", "--", "npm", "start"]
```

---

## シークレット関連タスクの対応

### ユーザーが「APIキーが設定されているか確認して」と求めた場合

```bash
# ✅ 安全なアプローチ
varlock load 2>&1 | grep "API_KEY"
# 表示: ✅ API_KEY 🔐sensitive └ ▒▒▒▒▒

# ❌ 絶対にしない
echo $API_KEY
```

### ユーザーが「認証のデバッグをして」と求めた場合

```bash
# ✅ 安全なアプローチ - 存在と形式を確認
varlock load  # 型と必須フィールドを検証

# 値を表示せずにキーの正しいプレフィックスを確認
varlock load 2>&1 | grep -E "(CLERK|AUTH)"

# ❌ 絶対にしない
printenv | grep KEY
```

### ユーザーが「シークレットを更新して」と求めた場合

```
Claudeはこう応答すべき:
「セキュリティ上の理由から、シークレットを直接変更することはできません。以下の手順をお願いします:
1. .envファイルの値を手動で更新する
2. またはシークレットマネージャー（1Password、AWSなど）で更新する
3. その後、`varlock load`を実行して検証する

新しい変数を追加する必要がある場合は、.env.schemaの更新をお手伝いできます。」
```

### ユーザーが「.envファイルを見せて」と求めた場合

```
Claudeはこう応答すべき:
「シークレットを含むため、.envファイルを直接読むことはしません。代わりに:
- `varlock load`を実行してマスクされた値を確認
- `cat .env.schema`を実行してスキーマを確認（安全）
- 必要であれば.env.schemaの変更をお手伝いできます」
```

---

## 外部シークレットソース

### 1Password統合

```bash
# .env.schemaで
# @type=string @sensitive
API_KEY=exec('op read "op://vault/item/field"')
```

### AWS Secrets Manager

```bash
# .env.schemaで
# @type=string @sensitive
DB_PASSWORD=exec('aws secretsmanager get-secret-value --secret-id prod/db')
```

### 環境別の値

```bash
# .env.schemaで
# @type=url
API_URL=env('API_URL_${NODE_ENV}', 'http://localhost:3000')
```

---

## トラブルシューティング

### "varlock: command not found"

```bash
# インストールを確認
ls ~/.varlock/bin/varlock

# PATHに追加
export PATH="$HOME/.varlock/bin:$PATH"

# またはフルパスを使用
~/.varlock/bin/varlock load
```

### "Schema validation failed"

```bash
# どの変数が欠落/無効かを確認
varlock load  # 詳細なエラーを表示

# よくある修正:
# - 必須変数を.envに追加する
# - 型の不一致を修正する（portは数値である必要がある）
# - スキーマのプレフィックスが一致しているか確認する
```

### "Sensitive value exposed in logs"

```bash
# 1. 露出したシークレットをすぐにローテーションする
# 2. .env.schemaに@sensitiveアノテーションがあるか確認する
# 3. echo/catではなくvarlockコマンドを使っているか確認する

# センシティビティを追加:
# 変更前: API_KEY=
# 変更後:  # @type=string @sensitive
#         API_KEY=
```

---

## npmスクリプト

package.jsonに以下を追加:

```json
{
  "scripts": {
    "env:validate": "varlock load",
    "env:check": "varlock load --quiet || echo 'Environment validation failed'",
    "prestart": "varlock load --quiet",
    "start": "varlock run -- node server.js"
  }
}
```

---

## 新規プロジェクトのセキュリティチェックリスト

- [ ] Varlock CLIをインストール
- [ ] すべての変数を定義した`.env.schema`を作成
- [ ] すべてのシークレットに`@sensitive`アノテーションを付ける
- [ ] スキーマヘッダーに`@defaultSensitive=true`を追加
- [ ] `.env`を`.gitignore`に追加
- [ ] `.env.schema`をバージョン管理にコミット
- [ ] CI/CDに`npm run env:validate`を追加
- [ ] シークレットローテーション手順を文書化
- [ ] Claudeセッションでは`cat .env`や`echo $SECRET`を絶対に使わない

---

## クイックリファレンスカード

| タスク | 安全なコマンド |
|------|-------------|
| 全環境変数を検証 | `varlock load` |
| クワイエット検証 | `varlock load --quiet` |
| 環境付きで実行 | `varlock run -- <cmd>` |
| スキーマを表示 | `cat .env.schema` |
| 特定の変数を確認 | `varlock load \| grep VAR_NAME` |

| してはいけないこと | 理由 |
|----------|-----|
| `cat .env` | 全シークレットが露出する |
| `echo $SECRET` | Claudeのコンテキストに露出する |
| `printenv \| grep` | 一致するシークレットが露出する |
| ツールで.envを読む | Claudeのコンテキストにシークレットが入る |
| コマンドにハードコード | シェル履歴に残る |

---

## 他のスキルとの連携

### Clerkスキル
- テストユーザーのパスワードは`@sensitive`
- テストメールは`@sensitive=false`（+clerk_testを含むが、シークレットではない）
- 参照: `~/.claude/skills/clerk/SKILL.md`

### Dockerスキル
- `.env`ファイルをマウントし、シークレットをイメージにコピーしない
- `varlock run`をエントリポイントとして使用
- 参照: `~/.claude/skills/docker/SKILL.md`

---

*最終更新: 2025年12月22日*
*Claudeコードのためのセキュアバイデフォルト環境管理*
