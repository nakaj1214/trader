---
paths:
  - "**/*.php"
  - "**/*.js"
  - "**/*.py"
---

# セキュリティルール

コードの記述・レビュー時に常に従うこと。

## 1. シークレットのハードコード禁止

シークレット・API キー・認証情報をコードに直書きしない。環境変数を使用する。

```typescript
// ❌ const API_KEY = "sk_live_abc123xyz789";
// ✅ const API_KEY = process.env.API_KEY;
```

検出: `password`, `secret`, `key`, `token` パターンをスキャン。`.env` を `.gitignore` に含める。

## 2. 入力バリデーション

すべてのユーザー入力を処理前にバリデーション: 型・フォーマット・長さ・範囲・特殊文字サニタイズ。
スキーマベースのバリデーション（Zod、Pydantic 等）を推奨。

## 3. SQL インジェクション防止

パラメータ化クエリまたは ORM を使用。ユーザー入力を SQL に結合しない。

```typescript
// ❌ db.query(`SELECT * FROM users WHERE id = ${userId}`);
// ✅ db.query('SELECT * FROM users WHERE id = ?', [userId]);
```

## 4. XSS 防止

HTML レンダリング前にユーザー生成コンテンツをエスケープ。フレームワーク組み込み機能を使用。

```typescript
// ❌ return `<div>${comment}</div>`;
// ✅ return `<div>${escapeHtml(comment)}</div>`;
```

## 5. 認証と認可

- パスワード: bcrypt/argon2 でハッシュ化（md5/sha1 禁止）
- セッション: `crypto.randomBytes(32)`, cookie に `secure`, `httpOnly`, `sameSite: 'strict'`
- 認可: すべての保護ルートでチェック。レート制限を実装

## 6. コマンドインジェクション防止

ユーザー入力でシェルコマンドを実行しない。`spawn` の配列引数またはライブラリを使用。

```typescript
// ❌ exec(`convert ${userFileName} output.jpg`);
// ✅ spawn('convert', [userFileName, 'output.jpg']);
```

## 7. パストラバーサル防止

ファイルパスをバリデーション。`path.resolve()` + `startsWith()` で許可ディレクトリ内を確認。

## 8. CSRF 保護

状態変更操作に CSRF トークンを実装。Laravel: `<meta name="csrf-token">` + `$.ajaxSetup`。

## 9. セキュアヘッダー

`helmet.js` または手動で設定: `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security`, `Content-Security-Policy`。

## 10. エラーハンドリング

エラーメッセージで機密情報を公開しない。サーバーに詳細ログ、クライアントには汎用エラー。

## セキュリティチェックリスト

- [ ] シークレットがハードコードされていない
- [ ] ユーザー入力がバリデーションされている
- [ ] SQL がパラメータ化されている
- [ ] HTML 出力がエスケープされている
- [ ] パスワードが bcrypt/argon2 でハッシュ化されている
- [ ] 認証・認可チェックが実施されている
- [ ] コマンドインジェクション脆弱性がない
- [ ] ファイルパスがバリデーションされている
- [ ] CSRF 保護が実装されている
- [ ] セキュリティヘッダーが設定されている
- [ ] エラーメッセージが情報を漏洩していない
- [ ] 本番で HTTPS が強制されている

## インシデント対応

脆弱性発見時: 停止 → エスカレーション → 修正 → 認証情報ローテーション → コードベース全体監査。
データ漏洩・認証バイパス・権限昇格・シークレット漏洩は直ちにセキュリティチームにエスカレーション。
