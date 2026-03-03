# Claude Configuration Files

このディレクトリには、Claude Codeをより効果的に使用するための推奨設定とガイドが含まれています。

## ファイル一覧

### 1. claude_settings.json
Claude Codeの推奨設定をJSON形式でまとめたファイルです。

**主な設定項目:**
- 一般設定（自動保存、コンテキスト最適化など）
- コード生成ポリシー（セキュリティ優先、最小限の変更など）
- コミュニケーションスタイル（簡潔、専門的など）
- ツール使用の最適化
- Gitベストプラクティス

### 2. custom_instructions.md
Claudeをより賢く、強力にするためのカスタム指示書です。

**含まれる内容:**
- コア原則（読んでから行動、最小限の介入、セキュリティ優先など）
- タスク管理のベストプラクティス
- 効率的なツール使用方法
- Gitのベストプラクティス
- 避けるべきアンチパターン
- 最適化戦略

### 3. hooks_examples.sh
Claude Codeで使用できるフックの例を示すシェルスクリプトです。

**含まれるフック:**
- Pre-commit hook（コミット前のリント、テスト、フォーマット）
- Post-tool hook（ファイル編集後の自動フォーマット、型チェック）
- User prompt submit hook（プロンプトのログ記録）
- Bash execution hook（危険なコマンドの防止）
- File change hook（依存関係変更時のキャッシュクリア）

### 4. agent_usage_guide.md
Claude Codeの専門エージェントの使い方を詳しく説明したガイドです。

**含まれる内容:**
- 利用可能なエージェント（Explore、Plan、Bash、General-Purpose）
- 各エージェントの使用タイミング
- ベストプラクティス（並列実行、バックグラウンド実行など）
- 一般的なパターン
- 避けるべきアンチパターン
- パフォーマンスのヒント

## 使い方

### ステップ1: 設定の確認
`claude_settings.json`を確認し、プロジェクトに適した設定を理解します。

### ステップ2: カスタム指示の適用
`custom_instructions.md`の内容を参考に、Claudeとのやり取りを最適化します。

### ステップ3: フックの設定（オプション）
必要に応じて`hooks_examples.sh`を参考に、プロジェクト固有のフックを設定します。

### ステップ4: エージェントの活用
`agent_usage_guide.md`を参考に、適切なエージェントを使用してタスクを実行します。

## ベストプラクティスのクイックリファレンス

### ✅ すべきこと
- ファイルを変更する前に必ず読む
- 複雑なタスクにはTodoWriteツールを使用
- コードベースの探索にはExploreエージェントを使用
- 並列実行可能なツールは同時に実行
- セキュリティ脆弱性を常にチェック
- 具体的なファイルをステージング
- マークダウンリンクでコード参照を提供

### ❌ すべきでないこと
- 不要なファイルを作成しない
- 要求されていないリファクタリングをしない
- 時間の見積もりをしない
- Gitフックをスキップしない
- main/masterへの強制プッシュをしない
- ファイル操作にbashを使用しない
- 読んでいないコードを変更しない

## カスタマイズ

これらの設定ファイルは出発点として使用してください。プロジェクトやチームの要件に応じて、自由にカスタマイズできます。

## フィードバック

設定やガイドに関するフィードバックがある場合は、以下で報告してください:
https://github.com/anthropics/claude-code/issues

## バージョン

- Version: 1.0.0
- Last Updated: 2026-01-24
- Compatible with: Claude Code (all versions)

## ライセンス

これらの設定ファイルは自由に使用、変更、配布できます。


claude_code_tests/
├── 📄 README.md                    # 全体の説明とクイックリファレンス（日本語）
├── 📄 INSTALLATION.md              # インストール手順
├── 📄 CHANGELOG.md                 # 変更履歴
├── 📄 LICENSE                      # MITライセンス
├── 📄 quick_start.md              # 5分クイックスタート（日本語）
├── 📄 .claudeignore               # 無視するファイルパターン
│
├── ⚙️ 設定ファイル
│   ├── claude_settings.json       # 推奨設定
│   ├── custom_instructions.md     # カスタム指示書
│   └── hooks_examples.sh          # フック例
│
├── 📚 ガイド
│   ├── agent_usage_guide.md       # エージェント使用ガイド
│   ├── context-management.md      # コンテキスト管理ガイド
│   └── prompt_templates.md        # プロンプトテンプレート（日本語）
│
├── 🎯 skills/                     # Claudeスキル
│   ├── SKILL_TEMPLATE.md          # スキル作成テンプレート
│   ├── code-review.md             # コードレビュースキル
│   └── tdd-workflow.md            # TDDワークフロースキル
│
├── 🤖 agents/                     # 専門エージェント
│   └── planner.md                 # プランニングエージェント
│
├── 📜 rules/                      # ルール定義
│   └── security-rules.md          # セキュリティルール
│
└── ⚡ commands/                   # コマンド定義
    ├── tdd.json                   # /tdd コマンド
    ├── review.json                # /review コマンド
    └── plan.json                  # /plan コマンド
