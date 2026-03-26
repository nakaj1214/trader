---
paths:
  - "**/.git*"
  - "**/*.md"
---

# Git ワークフロールール

## コミットメッセージの形式

```
<type>: <description>

[optional body]
```

### 許可されるタイプ

| タイプ | 使用場面 |
|------|-------------|
| `feat` | 新機能 |
| `fix` | バグ修正 |
| `refactor` | 動作変更を伴わないコード変更 |
| `docs` | ドキュメントのみ |
| `test` | テストの追加・更新 |
| `chore` | ツール、依存関係、ビルドスクリプト |
| `perf` | パフォーマンス改善 |
| `ci` | CI/CD 設定 |

### 例

```
feat: add user authentication with JWT
fix: resolve race condition in cache invalidation
refactor: extract payment logic into service class
docs: update API endpoint documentation
test: add integration tests for auth flow
```

## プルリクエストのプロセス

1. **完全なコミット履歴** をレビューする（個別のコミットだけでなく）
2. `git diff [base-branch]...HEAD` を実行してすべての変更を確認する
3. 以下をカバーする詳細な PR 説明を書く:
   - 何を変更したか、なぜ変更したか
   - チェックリスト付きのテスト戦略
   - 破壊的変更（あれば）
4. 新しいブランチをプッシュするときは `-u` フラグを使用する: `git push -u origin branch-name`

## ブランチ命名

```
feat/short-description
fix/issue-number-description
refactor/module-name
```
