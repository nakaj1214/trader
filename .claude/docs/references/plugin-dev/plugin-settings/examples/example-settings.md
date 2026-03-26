# プラグイン設定ファイルの例

## テンプレート: 基本設定

**.claude/my-plugin.local.md:**

```markdown
---
enabled: true
mode: standard
---

# My Plugin 設定

プラグインは standard モードで有効です。
```

## テンプレート: 高度な設定

**.claude/my-plugin.local.md:**

```markdown
---
enabled: true
strict_mode: false
max_file_size: 1000000
allowed_extensions: [".js", ".ts", ".tsx"]
enable_logging: true
notification_level: info
retry_attempts: 3
timeout_seconds: 60
custom_path: "/path/to/data"
---

# My Plugin 高度な設定

このプロジェクトはカスタムプラグイン設定を使用しています:
- standard バリデーションモード
- 1MB ファイルサイズ制限
- JavaScript/TypeScript ファイルが対象
- info レベルのロギング
- 3回のリトライ

## 追加メモ

この設定に関する質問は @team-lead にお問い合わせください。
```

## テンプレート: エージェント状態ファイル

**.claude/multi-agent-swarm.local.md:**

```markdown
---
agent_name: database-implementation
task_number: 4.2
pr_number: 5678
coordinator_session: team-leader
enabled: true
dependencies: ["Task 3.5", "Task 4.1"]
additional_instructions: "Use PostgreSQL, not MySQL"
---

# タスク割り当て: データベーススキーマ実装

新機能モジュールのデータベーススキーマを実装します。

## 要件

- マイグレーションファイルの作成
- パフォーマンスのためのインデックス追加
- 制約のテスト作成
- README にスキーマを文書化

## 成功基準

- マイグレーションが正常に実行される
- すべてのテストが合格
- CI がグリーンの状態で PR を作成
- スキーマが文書化されている

## 連携

依存するタスク:
- Task 3.5: API エンドポイント定義
- Task 4.1: データモデル設計

コーディネーターセッション 'team-leader' にステータスを報告してください。
```

## テンプレート: フィーチャーフラグパターン

**.claude/experimental-features.local.md:**

```markdown
---
enabled: true
features:
  - ai_suggestions
  - auto_formatting
  - advanced_refactoring
experimental_mode: false
---

# 実験的機能の設定

現在有効な機能:
- AI を活用したコード提案
- 自動コードフォーマット
- 高度なリファクタリングツール

実験モードは OFF です（安定版機能のみ）。
```

## フックでの使用

これらのテンプレートはフックから読み取ることができます:

```bash
# Check if plugin is configured
if [[ ! -f ".claude/my-plugin.local.md" ]]; then
  exit 0  # Not configured, skip hook
fi

# Read settings
FRONTMATTER=$(sed -n '/^---$/,/^---$/{ /^---$/d; p; }' ".claude/my-plugin.local.md")
ENABLED=$(echo "$FRONTMATTER" | grep '^enabled:' | sed 's/enabled: *//')

# Apply settings
if [[ "$ENABLED" == "true" ]]; then
  # Hook is active
  # ...
fi
```

## Gitignore

プロジェクトの `.gitignore` に必ず追加してください:

```gitignore
# Plugin settings (user-local, not committed)
.claude/*.local.md
.claude/*.local.json
```

## 設定の編集

ユーザーは設定ファイルを手動で編集できます:

```bash
# Edit settings
vim .claude/my-plugin.local.md

# Changes take effect after restart
exit  # Exit Claude Code
claude  # Restart
```

変更には Claude Code の再起動が必要です - フックはホットスワップできません。
