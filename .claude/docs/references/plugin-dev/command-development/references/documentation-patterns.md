# コマンドドキュメントパターン

自己文書化型で保守しやすく、優れたユーザー体験を持つコマンドを作成するための戦略。

## 概要

よくドキュメント化されたコマンドは使いやすく、保守しやすく、配布しやすい。ドキュメントはコマンド自体に埋め込むべきであり、ユーザーと保守者が即座にアクセスできるようにする。

## 自己文書化型コマンド構造

### 完全なコマンドテンプレート

```markdown
---
description: Clear, actionable description under 60 chars
argument-hint: [arg1] [arg2] [optional-arg]
allowed-tools: Read, Bash(git:*)
model: sonnet
---

<!--
COMMAND: command-name
VERSION: 1.0.0
AUTHOR: Team Name
LAST UPDATED: 2025-01-15

PURPOSE:
Detailed explanation of what this command does and why it exists.

USAGE:
  /command-name arg1 arg2

ARGUMENTS:
  arg1: Description of first argument (required)
  arg2: Description of second argument (optional, defaults to X)

EXAMPLES:
  /command-name feature-branch main
    → Compares feature-branch with main

  /command-name my-branch
    → Compares my-branch with current branch

REQUIREMENTS:
  - Git repository
  - Branch must exist
  - Permissions to read repository

RELATED COMMANDS:
  /other-command - Related functionality
  /another-command - Alternative approach

TROUBLESHOOTING:
  - If branch not found: Check branch name spelling
  - If permission denied: Check repository access

CHANGELOG:
  v1.0.0 (2025-01-15): Initial release
  v0.9.0 (2025-01-10): Beta version
-->

# Command Implementation

[Command prompt content here...]

[Explain what will happen...]

[Guide user through steps...]

[Provide clear output...]
```

### ドキュメントコメントセクション

**PURPOSE**: コマンドが存在する理由
- 解決する問題
- ユースケース
- 使うべき場合と使うべきでない場合

**USAGE**: 基本的な構文
- コマンド呼び出しパターン
- 必須引数とオプション引数
- デフォルト値

**ARGUMENTS**: 詳細な引数ドキュメント
- 各引数の説明
- 型情報
- 有効な値・範囲
- デフォルト値

**EXAMPLES**: 具体的な使用例
- 一般的なユースケース
- エッジケース
- 期待される出力

**REQUIREMENTS**: 前提条件
- 依存関係
- 権限
- 環境セットアップ

**RELATED COMMANDS**: 関連性
- 類似コマンド
- 補完的なコマンド
- 代替アプローチ

**TROUBLESHOOTING**: よくある問題
- 既知の問題
- 解決策
- 回避策

**CHANGELOG**: バージョン履歴
- 何がいつ変更されたか
- 破壊的変更のハイライト
- 移行ガイダンス

## インラインドキュメントパターン

### コメント付きセクション

```markdown
---
description: Complex multi-step command
---

<!-- セクション1: バリデーション -->
<!-- このセクションは続行前に前提条件をチェックする -->

Checking prerequisites...
- Git repository: !`git rev-parse --git-dir 2>/dev/null`
- Branch exists: [validation logic]

<!-- セクション2: 分析 -->
<!-- ブランチ間の差分を分析する -->

Analyzing differences between $1 and $2...
[Analysis logic...]

<!-- セクション3: 推奨事項 -->
<!-- 実行可能な推奨事項を提供する -->

Based on analysis, recommend:
[Recommendations...]

<!-- 終了: ユーザーへの次のステップ -->
```

### インライン説明

```markdown
---
description: Deployment command with inline docs
---

# Deploy to $1

## Pre-flight Checks

<!-- 間違ったブランチからのデプロイを防ぐためにブランチ状態をチェック -->
Current branch: !`git branch --show-current`

<!-- 本番デプロイは main/master からでなければならない -->
if [ "$1" = "production" ] && [ "$(git branch --show-current)" != "main" ]; then
  ⚠️  WARNING: Not on main branch for production deploy
  This is unusual. Confirm this is intentional.
fi

<!-- テスト状態を確認して壊れたコードをデプロイしないようにする -->
Running tests: !`npm test`

✓ All checks passed

## Deployment

<!-- 実際のデプロイメントはここで行われる -->
<!-- ゼロダウンタイムのためにブルーグリーン戦略を使用 -->
Deploying to $1 environment...
[Deployment steps...]

<!-- デプロイ後の検証 -->
Verifying deployment health...
[Health checks...]

Deployment complete!

## Next Steps

<!-- デプロイ後にユーザーが行うべきことをガイド -->
1. Monitor logs: /logs $1
2. Run smoke tests: /smoke-test $1
3. Notify team: /notify-deployment $1
```

### 判断ポイントのドキュメント

```markdown
---
description: Interactive deployment command
---

# Interactive Deployment

## Configuration Review

Target: $1
Current version: !`cat version.txt`
New version: $2

<!-- 判断ポイント: ユーザーが設定を確認する -->
<!-- このポーズによりユーザーがすべてが正しいか確認できる -->
<!-- デプロイはリスクがあるため自動的に進行できない -->

Review the above configuration.

**Continue with deployment?**
- Reply "yes" to proceed
- Reply "no" to cancel
- Reply "edit" to modify configuration

[Await user input before continuing...]

<!-- ユーザー確認後にデプロイを進行する -->
<!-- 以降のステップはすべて自動化されている -->

Proceeding with deployment...
```

## ヘルプテキストパターン

### 組み込みヘルプコマンド

複雑なコマンドのためにヘルプサブコマンドを作成する:

```markdown
---
description: Main command with help
argument-hint: [subcommand] [args]
---

# Command Processor

if [ "$1" = "help" ] || [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
  **Command Help**

  USAGE:
    /command [subcommand] [args]

  SUBCOMMANDS:
    init [name]       Initialize new configuration
    deploy [env]      Deploy to environment
    status            Show current status
    rollback          Rollback last deployment
    help              Show this help

  EXAMPLES:
    /command init my-project
    /command deploy staging
    /command status
    /command rollback

  For detailed help on a subcommand:
    /command [subcommand] --help

  Exit.
fi

[Regular command processing...]
```

### コンテキストヘルプ

コンテキストに基づいたヘルプを提供する:

```markdown
---
description: Context-aware command
argument-hint: [operation] [target]
---

# Context-Aware Operation

if [ -z "$1" ]; then
  **No operation specified**

  Available operations:
  - analyze: Analyze target for issues
  - fix: Apply automatic fixes
  - report: Generate detailed report

  Usage: /command [operation] [target]

  Examples:
    /command analyze src/
    /command fix src/app.js
    /command report

  Run /command help for more details.

  Exit.
fi

[Command continues if operation provided...]
```

## エラーメッセージドキュメント

### 有用なエラーメッセージ

```markdown
---
description: Command with good error messages
---

# Validation Command

if [ -z "$1" ]; then
  ❌ ERROR: Missing required argument

  The 'file-path' argument is required.

  USAGE:
    /validate [file-path]

  EXAMPLE:
    /validate src/app.js

  Try again with a file path.

  Exit.
fi

if [ ! -f "$1" ]; then
  ❌ ERROR: File not found: $1

  The specified file does not exist or is not accessible.

  COMMON CAUSES:
  1. Typo in file path
  2. File was deleted or moved
  3. Insufficient permissions

  SUGGESTIONS:
  - Check spelling: $1
  - Verify file exists: ls -la $(dirname "$1")
  - Check permissions: ls -l "$1"

  Exit.
fi

[Command continues if validation passes...]
```

### エラー復旧ガイダンス

```markdown
---
description: Command with recovery guidance
---

# Operation Command

Running operation...

!`risky-operation.sh`

if [ $? -ne 0 ]; then
  ❌ OPERATION FAILED

  The operation encountered an error and could not complete.

  WHAT HAPPENED:
  The risky-operation.sh script returned a non-zero exit code.

  WHAT THIS MEANS:
  - Changes may be partially applied
  - System may be in inconsistent state
  - Manual intervention may be needed

  RECOVERY STEPS:
  1. Check operation logs: cat /tmp/operation.log
  2. Verify system state: /check-state
  3. If needed, rollback: /rollback-operation
  4. Fix underlying issue
  5. Retry operation: /retry-operation

  NEED HELP?
  - Check troubleshooting guide: /help troubleshooting
  - Contact support with error code: ERR_OP_FAILED_001

  Exit.
fi
```

## 使用例ドキュメント

### 埋め込み例

```markdown
---
description: Command with embedded examples
---

# Feature Command

This command performs feature analysis with multiple options.

## Basic Usage

\`\`\`
/feature analyze src/
\`\`\`

Analyzes all files in src/ directory for feature usage.

## Advanced Usage

\`\`\`
/feature analyze src/ --detailed
\`\`\`

Provides detailed analysis including:
- Feature breakdown by file
- Usage patterns
- Optimization suggestions

## Use Cases

**Use Case 1: Quick overview**
\`\`\`
/feature analyze .
\`\`\`
Get high-level feature summary of entire project.

**Use Case 2: Specific directory**
\`\`\`
/feature analyze src/components
\`\`\`
Focus analysis on components directory only.

**Use Case 3: Comparison**
\`\`\`
/feature analyze src/ --compare baseline.json
\`\`\`
Compare current features against baseline.

---

Now processing your request...

[Command implementation...]
```

### 例駆動型ドキュメント

```markdown
---
description: Example-heavy command
---

# Transformation Command

## What This Does

Transforms data from one format to another.

## Examples First

### Example 1: JSON to YAML
**Input:** `data.json`
\`\`\`json
{"name": "test", "value": 42}
\`\`\`

**Command:** `/transform data.json yaml`

**Output:** `data.yaml`
\`\`\`yaml
name: test
value: 42
\`\`\`

### Example 2: CSV to JSON
**Input:** `data.csv`
\`\`\`csv
name,value
test,42
\`\`\`

**Command:** `/transform data.csv json`

**Output:** `data.json`
\`\`\`json
[{"name": "test", "value": "42"}]
\`\`\`

### Example 3: With Options
**Command:** `/transform data.json yaml --pretty --sort-keys`

**Result:** Formatted YAML with sorted keys

---

## Your Transformation

File: $1
Format: $2

[Perform transformation...]
```

## メンテナンスドキュメント

### バージョンと変更ログ

```markdown
<!--
VERSION: 2.1.0
LAST UPDATED: 2025-01-15
AUTHOR: DevOps Team

CHANGELOG:
  v2.1.0 (2025-01-15):
    - YAML 設定のサポートを追加
    - エラーメッセージを改善
    - 引数の特殊文字に関するバグを修正

  v2.0.0 (2025-01-01):
    - 破壊的変更: 引数の順序を変更
    - 破壊的変更: 非推奨の --old-flag を削除
    - 新しいバリデーションチェックを追加
    - 移行ガイド: /migration-v2

  v1.5.0 (2024-12-15):
    - --verbose フラグを追加
    - パフォーマンスを50%改善

  v1.0.0 (2024-12-01):
    - 初回安定版リリース

MIGRATION NOTES:
  v1.x から v2.0 への移行:
    旧: /command arg1 arg2 --old-flag
    新: /command arg2 arg1

  --old-flag は削除されました。代わりに --new-flag を使用してください。

DEPRECATION WARNINGS:
  - --legacy-mode フラグは v2.1.0 で非推奨
  - v3.0.0 で削除予定（2025-06-01 予定）
  - 代わりに --modern-mode を使用してください

KNOWN ISSUES:
  - #123: 大きなファイルでのパフォーマンス低下（回避策: --stream フラグを使用）
  - #456: Windows での特殊文字（v2.2.0 で修正予定）
-->
```

### メンテナンスノート

```markdown
<!--
MAINTENANCE NOTES:

CODE STRUCTURE:
  - 行 1-50: 引数の解析とバリデーション
  - 行 51-100: メイン処理ロジック
  - 行 101-150: 出力フォーマット
  - 行 151-200: エラーハンドリング

DEPENDENCIES:
  - git 2.x 以降が必要
  - JSON 処理に jq を使用
  - 連想配列に bash 4.0+ が必要

PERFORMANCE:
  - 小さな入力（< 1MB）の高速パス
  - メモリ問題を避けるため大きなファイルをストリーム処理
  - /tmp に結果を1時間キャッシュ

SECURITY CONSIDERATIONS:
  - インジェクション防止のためすべての入力をバリデーション
  - allowed-tools で Bash アクセスを制限
  - コマンドファイルに認証情報なし

TESTING:
  - ユニットテスト: tests/command-test.sh
  - インテグレーションテスト: tests/integration/
  - 手動テストチェックリスト: tests/manual-checklist.md

FUTURE IMPROVEMENTS:
  - TODO: TOML フォーマットのサポートを追加
  - TODO: 並列処理を実装
  - TODO: 大きなファイル用のプログレスバーを追加

RELATED FILES:
  - lib/parser.sh: 共有解析ロジック
  - lib/formatter.sh: 出力フォーマット
  - config/defaults.yml: デフォルト設定
-->
```

## README ドキュメント

コマンドにはコンパニオン README ファイルを用意すべき:

```markdown
# Command Name

Brief description of what the command does.

## Installation

This command is part of the [plugin-name] plugin.

Install with:
\`\`\`
/plugin install plugin-name
\`\`\`

## Usage

Basic usage:
\`\`\`
/command-name [arg1] [arg2]
\`\`\`

## Arguments

- `arg1`: Description (required)
- `arg2`: Description (optional, defaults to X)

## Examples

### Example 1: Basic Usage
\`\`\`
/command-name value1 value2
\`\`\`

Description of what happens.

### Example 2: Advanced Usage
\`\`\`
/command-name value1 --option
\`\`\`

Description of advanced feature.

## Configuration

Optional configuration file: `.claude/command-name.local.md`

\`\`\`markdown
---
default_arg: value
enable_feature: true
---
\`\`\`

## Requirements

- Git 2.x or later
- jq (for JSON processing)
- Node.js 14+ (optional, for advanced features)

## Troubleshooting

### Issue: Command not found

**Solution:** Ensure plugin is installed and enabled.

### Issue: Permission denied

**Solution:** Check file permissions and allowed-tools setting.

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT License - See [LICENSE](LICENSE).

## Support

- Issues: https://github.com/user/plugin/issues
- Docs: https://docs.example.com
- Email: support@example.com
```

## ベストプラクティス

### ドキュメントの原則

1. **将来の自分のために書く:** 詳細を忘れることを前提にする
2. **説明の前に例を:** まず見せて、それから説明する
3. **段階的な開示:** 基本情報を先に、詳細は利用可能に
4. **最新の状態を保つ:** コードが変わったらドキュメントも更新
5. **ドキュメントをテストする:** 例が実際に動くか確認

### ドキュメントの配置場所

1. **コマンドファイル内:** コアの使い方、例、インライン説明
2. **README:** インストール、設定、トラブルシューティング
3. **別ドキュメント:** 詳細ガイド、チュートリアル、API リファレンス
4. **コメント:** メンテナー向けの実装詳細

### ドキュメントのスタイル

1. **明確で簡潔に:** 不要な言葉は省く
2. **能動態:** 「コマンドを実行できます」ではなく「コマンドを実行する」
3. **一貫した用語:** 全体を通じて同じ用語を使用
4. **適切なフォーマット:** 見出し、リスト、コードブロックを使用
5. **アクセシブルに:** 読者が初心者であることを前提にする

### ドキュメントのメンテナンス

1. **すべてバージョン管理:** 何がいつ変わったかを追跡
2. **優雅な非推奨化:** 機能削除前に警告する
3. **移行ガイド:** ユーザーのアップグレードを支援
4. **古いドキュメントのアーカイブ:** 旧バージョンをアクセス可能に保つ
5. **定期的にレビュー:** ドキュメントが現実と一致しているか確認

## ドキュメントチェックリスト

コマンドをリリースする前に:

- [ ] フロントマターの description が明確
- [ ] argument-hint がすべての引数を文書化
- [ ] コメント内の使用例
- [ ] 一般的なユースケースが示されている
- [ ] エラーメッセージが有用
- [ ] 要件が文書化されている
- [ ] 関連コマンドが列挙されている
- [ ] 変更ログが維持されている
- [ ] バージョン番号が更新されている
- [ ] README が作成/更新されている
- [ ] 例が実際に動作する
- [ ] トラブルシューティングセクションが完備

良いドキュメントがあれば、コマンドはセルフサービスとなり、サポート負荷を軽減しユーザー体験を向上させる。
