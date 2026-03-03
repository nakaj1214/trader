# _shared/ 構造ガイド

各プロジェクトの `.claude/` フォルダに重複していたファイルを集約した共有フォルダ。

---

```
_shared/
│
│  # ===== ドキュメント類 =====
│
├── README.md                # このテンプレートの概要・使い方
├── INSTALLATION.md          # 導入手順
├── CHANGELOG.md             # 変更履歴
├── LICENSE                  # ライセンス
├── STRUCTURE.md             # このファイル。フォルダ構造の説明
│
│  # ===== Claude Code の動作設定 =====
│
├── .claudeignore            # Claude に読ませないファイルのパターン (gitignore と同じ書式)
├── claude_settings.json     # Claude Code の推奨設定値 (モデル・権限・表示など)
├── custom_instructions.md   # Claude への恒久的な振る舞い指示 (「実装前に読め」「セキュリティ優先」等)
│
│  # ===== 参照ドキュメント =====
│
├── context-management.md    # コンテキストウィンドウの管理方法・注意事項
├── prompt_templates.md      # よく使うプロンプトのテンプレート集
├── quick_start.md           # Claude Code を使い始めるためのクイックガイド
├── agent_usage_guide.md     # サブエージェント (Task tool) の使い方ガイド
├── hooks_examples.sh        # フック (Pre/Post ToolUse 等) のサンプルスクリプト
│
│  # ===== agents/ =====
│  # Claude Code の /agent コマンドで呼び出せる専門エージェント定義
│  # 各ファイルが「役割・使い方・出力フォーマット」を定義する
│
├── agents/
│   ├── architect.md         # 設計・アーキテクチャ検討エージェント
│   ├── planner.md           # タスク分解・実装計画エージェント
│   ├── debugger.md          # デバッグ・原因調査エージェント
│   ├── tester.md            # テスト設計・TDD エージェント
│   ├── reviewer.md          # コードレビューエージェント
│   ├── refactorer.md        # リファクタリングエージェント
│   ├── performance.md       # パフォーマンス改善エージェント
│   └── documenter.md        # ドキュメント生成エージェント
│
│  # ===== commands/ =====
│  # /コマンド名 で呼び出せるカスタムスラッシュコマンドの定義
│
├── commands/
│   ├── plan.json            # /plan   → 機能実装計画の作成
│   ├── review.json          # /review → コードレビューの実行
│   └── tdd.json             # /tdd    → TDD サイクルの実行
│
│  # ===== mcp/ =====
│  # MCP (Model Context Protocol) サーバー設定のテンプレート集
│  # Claude Code に外部ツール連携を追加するための設定
│
├── mcp/
│   ├── mcp-guide.md             # MCP とは何か・導入方法のガイド
│   ├── mcp-by-technology.md     # 技術スタック別おすすめ MCP サーバー一覧
│   ├── universal-mcp-servers.md # 言語問わず汎用的に使える MCP サーバー
│   ├── context7-setup.md        # Context7 (ライブラリドキュメント取得) の設定手順
│   ├── mcp-settings-example.json    # settings.json への MCP 記述サンプル
│   ├── settings-javascript.json     # JS/TS プロジェクト向け MCP 設定
│   ├── settings-laravel-php.json    # Laravel/PHP プロジェクト向け MCP 設定
│   ├── settings-linux.json          # Linux サーバー向け MCP 設定
│   ├── settings-python.json         # Python プロジェクト向け MCP 設定
│   ├── settings-vba.json            # VBA プロジェクト向け MCP 設定
│   └── settings-universal.json      # 言語横断の汎用 MCP 設定
│
│  # ===== rules/ =====
│  # Claude が常に従うべきルール定義 (CLAUDE.md から参照される)
│
├── rules/
│   └── security-rules.md    # セキュリティルール (XSS・SQLi・認証等の禁止事項)
│
│  # ===== skills/ =====
│  # /スキル名 で呼び出せる作業手順書 (ワークフロー系・汎用)
│
└── skills/
    ├── brainstorming.md         # ソクラテス式ブレスト → 要件・設計を問いかけで整理
    ├── planning-with-files.md   # ファイルに計画を書きながら進める実装フロー
    ├── writing-plans.md         # 実装計画ドキュメントの書き方
    ├── executing-plans.md       # 計画を実行に移すときの手順
    ├── code-review.md           # コードレビューの進め方
    ├── tdd-workflow.md          # TDD (テスト駆動開発) のサイクル
    └── systematic-debugging.md  # 体系的なデバッグ手順
```

---

## 分類早見表

| フォルダ / ファイル | 役割 |
|---|---|
| `claude_settings.json` / `.claudeignore` | Claude Code の動作そのものを制御 |
| `custom_instructions.md` | Claude の思考・振る舞いの方針を指示 |
| `agents/` | 専門作業を担う名前付きエージェント |
| `commands/` | スラッシュコマンドのショートカット定義 |
| `mcp/` | 外部ツール連携 (DB・ブラウザ・ファイル等) の設定テンプレ |
| `rules/` | 常時適用されるルール (主にセキュリティ) |
| `skills/` | 作業手順のレシピ集 (呼び出して使う) |
| `*.md` (ルート直下) | 人間向けのドキュメント・参考資料 |
