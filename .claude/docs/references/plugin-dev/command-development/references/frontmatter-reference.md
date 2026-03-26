# コマンドフロントマターリファレンス

スラッシュコマンドの YAML フロントマターフィールドの完全なリファレンス。

## フロントマター概要

YAML フロントマターはコマンドファイルの先頭にあるオプションのメタデータ:

```markdown
---
description: Brief description
allowed-tools: Read, Write
model: sonnet
argument-hint: [arg1] [arg2]
---

Command prompt content here...
```

すべてのフィールドはオプション。フロントマターなしでもコマンドは動作する。

## フィールド仕様

### description

**型:** String
**必須:** いいえ
**デフォルト:** コマンドプロンプトの最初の行
**最大長:** `/help` 表示のため 約60文字推奨

**目的:** コマンドの動作を説明し、`/help` の出力に表示される

**例:**
```yaml
description: Review code for security issues
```
```yaml
description: Deploy to staging environment
```
```yaml
description: Generate API documentation
```

**ベストプラクティス:**
- 60文字以内で表示をクリーンに保つ
- 動詞で始める（Review, Deploy, Generate）
- コマンドの動作を具体的に記述
- "command" や "slash command" の冗長な記述を避ける

**良い例:**
- ✅ "Review PR for code quality and security"
- ✅ "Deploy application to specified environment"
- ✅ "Generate comprehensive API documentation"

**悪い例:**
- ❌ "This command reviews PRs"（不要な "This command"）
- ❌ "Review"（曖昧すぎる）
- ❌ "A command that reviews pull requests for code quality, security issues, and best practices"（長すぎる）

### allowed-tools

**型:** String または String の配列
**必須:** いいえ
**デフォルト:** 会話の権限を継承

**目的:** コマンドが使用できるツールを制限または指定する

**フォーマット:**

**単一ツール:**
```yaml
allowed-tools: Read
```

**複数ツール（カンマ区切り）:**
```yaml
allowed-tools: Read, Write, Edit
```

**複数ツール（配列）:**
```yaml
allowed-tools:
  - Read
  - Write
  - Bash(git:*)
```

**ツールパターン:**

**特定のツール:**
```yaml
allowed-tools: Read, Grep, Edit
```

**Bash コマンドフィルター付き:**
```yaml
allowed-tools: Bash(git:*)           # git コマンドのみ
allowed-tools: Bash(npm:*)           # npm コマンドのみ
allowed-tools: Bash(docker:*)        # docker コマンドのみ
```

**すべてのツール（非推奨）:**
```yaml
allowed-tools: "*"
```

**使用タイミング:**

1. **セキュリティ:** コマンドを安全な操作に制限
   ```yaml
   allowed-tools: Read, Grep  # 読み取り専用コマンド
   ```

2. **明確さ:** 必要なツールをドキュメント化
   ```yaml
   allowed-tools: Bash(git:*), Read
   ```

3. **Bash 実行:** bash コマンド出力を有効化
   ```yaml
   allowed-tools: Bash(git status:*), Bash(git diff:*)
   ```

**ベストプラクティス:**
- できるだけ制限的にする
- Bash にはコマンドフィルターを使用（例: `*` ではなく `git:*`）
- 会話の権限と異なる場合のみ指定
- 特定のツールが必要な理由をドキュメント化

### model

**型:** String
**必須:** いいえ
**デフォルト:** 会話から継承
**値:** `sonnet`, `opus`, `haiku`

**目的:** コマンドを実行する Claude モデルを指定する

**例:**
```yaml
model: haiku    # 高速、シンプルなタスクに効率的
```
```yaml
model: sonnet   # バランスの取れたパフォーマンス（デフォルト）
```
```yaml
model: opus     # 複雑なタスクに最大の能力
```

**使用タイミング:**

**`haiku` を使う場合:**
- シンプルで定型的なコマンド
- 高速実行が必要
- 低複雑度タスク
- 頻繁な呼び出し

```yaml
---
description: Format code file
model: haiku
---
```

**`sonnet` を使う場合:**
- 標準的なコマンド（デフォルト）
- 速度と品質のバランス
- 最も一般的なユースケース

```yaml
---
description: Review code changes
model: sonnet
---
```

**`opus` を使う場合:**
- 複雑な分析
- アーキテクチャの判断
- 深いコード理解
- 重要なタスク

```yaml
---
description: Analyze system architecture
model: opus
---
```

**ベストプラクティス:**
- 特定の必要がない限り省略
- 速度が必要な場合は `haiku` を使用
- `opus` は本当に複雑なタスクに限定
- 異なるモデルでテストして適切なバランスを見つける

### argument-hint

**型:** String
**必須:** いいえ
**デフォルト:** なし

**目的:** ユーザーとオートコンプリートのために期待される引数をドキュメント化

**フォーマット:**
```yaml
argument-hint: [arg1] [arg2] [optional-arg]
```

**例:**

**単一引数:**
```yaml
argument-hint: [pr-number]
```

**複数の必須引数:**
```yaml
argument-hint: [environment] [version]
```

**オプション引数:**
```yaml
argument-hint: [file-path] [options]
```

**説明的な名前:**
```yaml
argument-hint: [source-branch] [target-branch] [commit-message]
```

**ベストプラクティス:**
- 各引数に角括弧 `[]` を使用
- 説明的な名前を使用（`arg1`, `arg2` ではなく）
- 説明でオプションか必須かを示す
- コマンド内の位置引数と順序を合わせる
- 簡潔だが明確に保つ

**パターン別の例:**

**シンプルなコマンド:**
```yaml
---
description: Fix issue by number
argument-hint: [issue-number]
---

Fix issue #$1...
```

**複数引数:**
```yaml
---
description: Deploy to environment
argument-hint: [app-name] [environment] [version]
---

Deploy $1 to $2 using version $3...
```

**オプション付き:**
```yaml
---
description: Run tests with options
argument-hint: [test-pattern] [options]
---

Run tests matching $1 with options: $2
```

### disable-model-invocation

**型:** Boolean
**必須:** いいえ
**デフォルト:** false

**目的:** SlashCommand ツールによるプログラム的なコマンド呼び出しを防止する

**例:**
```yaml
disable-model-invocation: true
```

**使用タイミング:**

1. **手動専用コマンド:** ユーザーの判断が必要なコマンド
   ```yaml
   ---
   description: Approve deployment to production
   disable-model-invocation: true
   ---
   ```

2. **破壊的操作:** 不可逆的な影響を持つコマンド
   ```yaml
   ---
   description: Delete all test data
   disable-model-invocation: true
   ---
   ```

3. **インタラクティブワークフロー:** ユーザー入力が必要なコマンド
   ```yaml
   ---
   description: Walk through setup wizard
   disable-model-invocation: true
   ---
   ```

**デフォルト動作 (false):**
- コマンドは SlashCommand ツールから利用可能
- Claude がプログラム的に呼び出し可能
- 手動呼び出しも引き続き可能

**true の場合:**
- ユーザーが `/command` と入力した場合のみ呼び出し可能
- SlashCommand ツールからは利用不可
- センシティブな操作により安全

**ベストプラクティス:**
- 控えめに使用（Claude の自律性を制限する）
- コマンドコメントに理由をドキュメント化
- 常に手動であるべきならコマンドとして存在すべきか検討

## 完全な例

### 最小限のコマンド

フロントマター不要:

```markdown
Review this code for common issues and suggest improvements.
```

### シンプルなコマンド

description のみ:

```markdown
---
description: Review code for issues
---

Review this code for common issues and suggest improvements.
```

### 標準的なコマンド

description とツール:

```markdown
---
description: Review Git changes
allowed-tools: Bash(git:*), Read
---

Current changes: !`git diff --name-only`

Review each changed file for:
- Code quality
- Potential bugs
- Best practices
```

### 複雑なコマンド

すべてのよく使うフィールド:

```markdown
---
description: Deploy application to environment
argument-hint: [app-name] [environment] [version]
allowed-tools: Bash(kubectl:*), Bash(helm:*), Read
model: sonnet
---

Deploy $1 to $2 environment using version $3

Pre-deployment checks:
- Verify $2 configuration
- Check cluster status: !`kubectl cluster-info`
- Validate version $3 exists

Proceed with deployment following deployment runbook.
```

### 手動専用コマンド

呼び出し制限付き:

```markdown
---
description: Approve production deployment
argument-hint: [deployment-id]
disable-model-invocation: true
allowed-tools: Bash(gh:*)
---

<!--
手動承認が必要
このコマンドは人間の判断が必要で、自動化できない。
-->

Review deployment $1 for production approval:

Deployment details: !`gh api /deployments/$1`

Verify:
- All tests passed
- Security scan clean
- Stakeholder approval
- Rollback plan ready

Type "APPROVED" to confirm deployment.
```

## バリデーション

### よくあるエラー

**無効な YAML 構文:**
```yaml
---
description: Missing quote
allowed-tools: Read, Write
model: sonnet
---  # ❌ 上のクォートが欠落
```

**修正:** YAML 構文を検証

**不正なツール指定:**
```yaml
allowed-tools: Bash  # ❌ コマンドフィルターが欠落
```

**修正:** `Bash(git:*)` フォーマットを使用

**無効なモデル名:**
```yaml
model: gpt4  # ❌ 有効な Claude モデルではない
```

**修正:** `sonnet`, `opus`, または `haiku` を使用

### バリデーションチェックリスト

コマンドをコミットする前に:
- [ ] YAML 構文が有効（エラーなし）
- [ ] description が 60 文字以内
- [ ] allowed-tools が適切なフォーマットを使用
- [ ] model が指定されている場合は有効な値
- [ ] argument-hint が位置引数と一致
- [ ] disable-model-invocation が適切に使用されている

## ベストプラクティスのまとめ

1. **最小限から始める:** 必要な場合のみフロントマターを追加
2. **引数をドキュメント化:** 引数がある場合は常に argument-hint を使用
3. **ツールを制限:** 動作する最も制限的な allowed-tools を使用
4. **適切なモデルを選択:** 速度には haiku、複雑さには opus
5. **手動専用は控えめに:** disable-model-invocation は必要な場合のみ
6. **明確な説明:** `/help` でコマンドを見つけやすくする
7. **徹底的にテスト:** フロントマターが期待通り動作するか確認
