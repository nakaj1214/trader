# CLAUDE.md 更新ガイドライン

## 基本原則

将来の Claude セッションに本当に役立つ情報のみを追加すること。コンテキストウィンドウは貴重であり、すべての行がその場所を正当化する必要があります。

## 追加すべきもの

### 1. 発見したコマンド/ワークフロー

```markdown
## Build

`npm run build:prod` - Full production build with optimization
`npm run build:dev` - Fast dev build (no minification)
```

理由: 将来のセッションがこれらを再発見する手間を省けます。

### 2. 落とし穴と非自明なパターン

```markdown
## Gotchas

- Tests must run sequentially (`--runInBand`) due to shared DB state
- `yarn.lock` is authoritative; delete `node_modules` if deps mismatch
```

理由: デバッグセッションの繰り返しを防止します。

### 3. パッケージの依存関係

```markdown
## Dependencies

The `auth` module depends on `crypto` being initialized first.
Import order matters in `src/bootstrap.ts`.
```

理由: コードからは明らかでないアーキテクチャの知識です。

### 4. 効果があったテストアプローチ

```markdown
## Testing

For API endpoints: Use `supertest` with the test helper in `tests/setup.ts`
Mocking: Factory functions in `tests/factories/` (not inline mocks)
```

理由: 効果のあるパターンを確立します。

### 5. 設定の特殊事項

```markdown
## Config

- `NEXT_PUBLIC_*` vars must be set at build time, not runtime
- Redis connection requires `?family=0` suffix for IPv6
```

理由: 環境固有の知識です。

## 追加すべきでないもの

### 1. 自明なコード情報

悪い例:
```markdown
The `UserService` class handles user operations.
```

クラス名から既にそれは分かります。

### 2. 汎用的なベストプラクティス

悪い例:
```markdown
Always write tests for new features.
Use meaningful variable names.
```

これはプロジェクト固有ではなく、普遍的なアドバイスです。

### 3. 一回限りの修正

悪い例:
```markdown
We fixed a bug in commit abc123 where the login button didn't work.
```

再発しないため、ファイルを散らかすだけです。

### 4. 冗長な説明

悪い例:
```markdown
The authentication system uses JWT tokens. JWT (JSON Web Tokens) are
an open standard (RFC 7519) that defines a compact and self-contained
way for securely transmitting information between parties as a JSON
object. In our implementation, we use the HS256 algorithm which...
```

良い例:
```markdown
Auth: JWT with HS256, tokens in `Authorization: Bearer <token>` header.
```

## 更新のための差分フォーマット

提案する各変更について:

### 1. ファイルの特定

```
File: ./CLAUDE.md
Section: Commands (new section after ## Architecture)
```

### 2. 変更内容の表示

```diff
 ## Architecture
 ...

+## Commands
+
+| Command | Purpose |
+|---------|---------|
+| `npm run dev` | Dev server with HMR |
+| `npm run build` | Production build |
+| `npm test` | Run test suite |
```

### 3. 理由の説明

> **これが役立つ理由:** ビルドコマンドがドキュメント化されておらず、
> プロジェクトの実行方法について混乱を招いていました。これにより
> 将来のセッションが `package.json` を調べる必要がなくなります。

## 検証チェックリスト

更新を確定する前に確認:

- [ ] 各追加がプロジェクト固有である
- [ ] 汎用的なアドバイスや自明な情報がない
- [ ] コマンドがテスト済みで動作する
- [ ] ファイルパスが正確
- [ ] 新しい Claude セッションがこれを役立つと感じるか？
- [ ] 情報を表現する最も簡潔な方法か？
