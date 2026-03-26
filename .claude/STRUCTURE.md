# 構造ガイド

`.claude/` フォルダの構造と各コンポーネントの説明。

```
.claude/
│
│  # ===== ドキュメント類 =====
├── STRUCTURE.md             # フォルダ構造の説明（このファイル）
├── CLAUDE.md                # Claude Code に読み込ませるメインの指示ファイル
│
│  # ===== Claude Code の動作設定 =====
├── .claudeignore            # Claude に読ませないファイルのパターン (gitignore と同じ書式)
├── settings.json            # フック・パーミッション等の設定
│
│  # ===== 参照ドキュメント =====
├── context-management.md    # コンテキストウィンドウの管理方法・注意事項
├── prompt_templates.md      # よく使うプロンプトのテンプレート集
├── quick_start.md           # Claude Code を使い始めるためのクイックガイド
├── agent_usage_guide.md     # サブエージェント (Task tool) の使い方ガイド
│
│  # ===== agents/ (22 files) =====
│  # Claude Code の Task tool で呼び出せる専門エージェント定義
│  # 各ファイルに専門家としての役割を定義し、独自のコンテキストウィンドウで作業を行い結果を返す
├── agents/
│   ├── planning/                # 設計・計画
│   │   ├── planner.md           #   タスク分解・実装計画
│   │   └── architect.md         #   設計・アーキテクチャ検討 (+コードパターン分析)
│   ├── review/                  # コードレビュー・品質
│   │   ├── code-reviewer.md     #   コードレビュー
│   │   ├── python-reviewer.md   #   Python コードレビュー
│   │   ├── security-reviewer.md #   セキュリティレビュー
│   │   ├── database-reviewer.md #   DB 設計レビュー
│   │   ├── code-simplifier.md   #   コード簡素化
│   │   ├── type-design-analyzer.md  # 型設計分析
│   │   └── silent-failure-hunter.md # サイレント障害検出
│   ├── testing/                 # テスト
│   │   ├── tester.md            #   テスト設計・TDD
│   │   ├── tdd-guide.md         #   TDD ガイド
│   │   ├── e2e-runner.md        #   E2E テスト実行
│   │   └── pr-test-analyzer.md  #   PR テスト分析
│   ├── debugging/               # デバッグ・パフォーマンス
│   │   ├── debugger.md          #   デバッグ・原因調査
│   │   ├── performance.md       #   パフォーマンス改善
│   │   └── build-error-resolver.md # ビルドエラー解消
│   ├── refactoring/             # リファクタリング
│   │   └── refactorer.md        #   リファクタリング (+デッドコード除去)
│   ├── documentation/           # ドキュメント
│   │   └── documenter.md        #   ドキュメント生成 (+コードマップ・README同期)
│   ├── exploration/             # コード調査・分析
│   │   └── code-explorer.md     #   コードベース探索
│   └── tooling/                 # ツール・プラグイン管理
│       ├── agent-creator.md     #   エージェント定義作成
│       ├── plugin-validator.md  #   プラグイン検証
│       └── skill-reviewer.md    #   スキル定義レビュー
│
│  # ===== commands/ (26 files) =====
│  # /コマンド名 で呼び出せるカスタムスラッシュコマンドの定義
├── commands/
│   ├── build-fix.md         # /build-fix         → ビルドエラーの修正
│   ├── cancel-ralph.md      # /cancel-ralph      → ralphループのキャンセル
│   ├── checkpoint.md        # /checkpoint        → 作業チェックポイントの記録
│   ├── clean_gone.md        # /clean-gone        → 削除済みブランチの掃除
│   ├── code-review.md       # /code-review       → コードレビューの実行
│   ├── commit.md            # /commit            → コミットの作成
│   ├── commit-push-pr.md    # /commit-push-pr    → コミット・プッシュ・PR作成
│   ├── create-plugin.md     # /create-plugin     → プラグインの雛形生成
│   ├── e2e.md               # /e2e               → E2Eテストの実行
│   ├── feature-dev.md       # /feature-dev       → 機能開発フロー
│   ├── hookify.md           # /hookify           → フック設定の生成
│   ├── hookify-configure.md # /hookify-configure → フックの設定変更
│   ├── hookify-help.md      # /hookify-help      → フックのヘルプ
│   ├── hookify-list.md      # /hookify-list      → フック一覧表示
│   ├── learn-edits.md       # /learn-edits       → 編集パターンの学習
│   ├── materialize.md       # /materialize       → staging候補の生成
│   ├── orchestrate.md       # /orchestrate       → 複数エージェントの協調実行
│   ├── ralph-help.md        # /ralph-help        → ralphのヘルプ
│   ├── ralph-loop.md        # /ralph-loop        → ralphによる反復実行
│   ├── refactor-clean.md    # /refactor-clean    → リファクタリングと整理
│   ├── review-pr.md         # /review-pr         → PRのレビュー
│   ├── review-staged.md     # /review-staged     → staging候補のレビュー
│   ├── revise-claude-md.md  # /revise-claude-md  → CLAUDE.mdの改訂
│   ├── test-coverage.md     # /test-coverage     → テストカバレッジの確認
│   ├── update-docs.md       # /update-docs       → ドキュメントの更新
│   └── verify.md            # /verify            → 実装の検証
│
│  # ===== docs/ =====
│  # プロジェクト共通の設計ドキュメント・運用情報
├── docs/
│   ├── PROJECT-PROFILE.md       # プロジェクト全体像
│   ├── DESIGN.md                # システム設計ドキュメント（design-tracker が自動更新）
│   ├── user-preferences.md      # ユーザーの好み・スタイル設定
│   ├── workflow-guide.md        # ワークフロー設計の詳細ガイド
│   ├── playbooks.md             # トラブルシューティング手順集
│   ├── lessons.md               # 修正から学んだパターン（自己改善ループ）
│   ├── feedback-log.md          # フィードバック記録ログ
│   ├── improvement-tracker.md   # 改善トラッカー
│   ├── path-rules-guide.md      # パス指定ルールの使い方ガイド
│   ├── maintenance-cheatsheet.md # .claude メンテナンスチートシート
│   ├── libraries/               # ライブラリ調査ドキュメント
│   │   └── _TEMPLATE.md         #   調査テンプレート
│   ├── references/                # スキルから移動したリファレンス資料
│   │   ├── advanced-security/     #   CodeQL/Semgrep/SARIF
│   │   ├── agents/                #   サブエージェント活用パターン
│   │   ├── git/                   #   Git Worktree・ブランチ完了処理
│   │   ├── plugin-dev/            #   プラグイン開発ガイド
│   │   └── security/              #   OWASP・環境変数保護
│   └── memory/                    # コンテキスト圧縮時の引き継ぎ情報
│       ├── HANDOVER-*.md          #   セッション引き継ぎドキュメント
│       ├── SKILL-SUGGESTIONS-*.md #   スキル提案
│       ├── EDIT-PATTERNS-*.md     #   編集パターン記録
│       └── AUTO-MATERIALIZE-QUEUE.jsonl # 自動生成候補キュー
│
│  # ===== hooks/ =====
│  # 特定のイベントで自動実行されるフックスクリプト
├── hooks/
│   ├── fix-escalation-detector.py       # 失敗パターン検知フック（ルート配置）
│   ├── session/                         # セッション管理
│   │   └── pre-compact-handover.py      #   コンパクト前に HANDOVER + SKILL-SUGGESTIONS を生成
│   ├── quality/                         # コード品質
│   │   ├── edit-tracker.py              #   編集ログ蓄積フック
│   │   ├── lint-on-save.py              #   保存時の自動 Lint フック
│   │   ├── post-implementation-review.py #  実装後レビューフック
│   │   ├── post-test-analysis.py        #   テスト後分析フック
│   │   └── same-file-edit-warn.py       #   同一ファイル頻回編集の警告
│   ├── slack/                           # Slack 連携
│   │   ├── edit-approval.py             #   ファイル編集時の承認フック
│   │   ├── notify-slack.py              #   Slack通知フック
│   │   ├── slack_approval.py            #   Slack経由の承認フック
│   │   ├── slack_socket_daemon.py       #   Slackソケット接続デーモン
│   │   ├── stop-notify.py               #   停止通知フック
│   │   └── approval_skip_patterns.txt   #   承認スキップ対象パターン一覧
│   ├── lib/                             # フック共通ライブラリ（複数フックで再利用）
│   │   ├── transcript.py                #   JSONLトランスクリプト読み込み・テキスト変換
│   │   ├── claude_p.py                  #   claude -p 呼び出しユーティリティ
│   │   ├── env.py                       #   環境変数ユーティリティ
│   │   └── jsonl_io.py                  #   JSONL ファイル読み書きユーティリティ
│   └── tests/
│       └── test_slack_approval.py       # slack_approval.pyのテスト
│
│  # ===== meta/ =====
│  # .claude自体の品質管理や自動生成を行うスクリプト
├── meta/
│   ├── generate-registry.py         # 全スキルのSKILL.mdを読んで registry/skills.yaml を生成
│   └── health-check.py              # スキル品質監査（evals欠損・SKILL.md肥大化・未登録・重複検出）
│
│  # ===== registry/ =====
│  # スキルルーティングインデックス（meta/generate-registry.py で自動生成）
├── registry/
│   └── skills.yaml                  # 全スキルの name/path/description/tags/triggers 一覧
│
│  # ===== mcp/ =====
│  # MCP (Model Context Protocol) サーバー設定のテンプレート集
├── mcp/
│   ├── mcp-guide.md              # MCP とは何か・導入方法のガイド
│   ├── mcp-by-technology.md      # 技術スタック別おすすめ MCP サーバー一覧
│   ├── universal-mcp-servers.md  # 言語問わず汎用的に使える MCP サーバー
│   ├── context7-setup.md         # Context7 (ライブラリドキュメント取得) の設定手順
│   ├── mcp-settings-example.json # settings.json への MCP 記述サンプル
│   ├── settings-javascript.json  # JS/TS プロジェクト向け MCP 設定
│   ├── settings-laravel-php.json # Laravel/PHP プロジェクト向け MCP 設定
│   ├── settings-linux.json       # Linux サーバー向け MCP 設定
│   ├── settings-python.json      # Python プロジェクト向け MCP 設定
│   ├── settings-vba.json         # VBA プロジェクト向け MCP 設定
│   ├── settings-hardware.json    # ハードウェア開発向け MCP 設定
│   └── settings-universal.json   # 言語横断の汎用 MCP 設定
│
│  # ===== resources/ =====
│  # 外部参考資料・リンク集
├── resources/
│   └── awesome-claude-code.md   # Claude Code の便利ツール・リソース集
│
│  # ===== rules/ (26 files) =====
│  # Claudeが従うべきルール定義
│  # paths: フロントマターなし → 常時ロード（9ファイル・約430行）
│  # paths: フロントマターあり → 対象ファイル操作時のみロード（17ファイル）
├── rules/
│   ├── coding-principles.md      # [常時] コーディング原則 (汎用)
│   ├── language.md               # [常時] 言語・コミュニケーションルール
│   ├── security-rules.md         # [常時] セキュリティルール (XSS・SQLi・認証等)
│   ├── neutral-analysis.md       # [常時] 中立的分析ルール（迎合対策・三者構造）
│   ├── skill-execution.md        # [常時] スキル/フック実行ルール
│   ├── work-modes.md             # [常時] 作業モード切替（開発・調査・レビュー）
│   ├── _PATH_RULES_GUIDE.md      # [条件] パス指定ルールの書き方ガイド
│   ├── project-conventions.md    # [条件: **/*.php,*.js] プロジェクト固有規約
│   ├── ui-fix-verification.md    # [条件: *.js,*.css,*.html] UI修正検証ルール
│   ├── common/                   # [常時] 言語共通ルール
│   │   ├── coding-style.md       #   コーディングスタイル（不変性・ファイル構成・エラー処理）
│   │   ├── git-workflow.md       #   Git ワークフロー（コミット・PR・ブランチ命名）
│   │   └── testing.md            #   テストルール（TDD・カバレッジ80%+）
│   ├── python/                   # [条件: **/*.py] Python 固有ルール
│   │   ├── coding-style.md       #   Python コーディングスタイル（PEP 8・型注釈）
│   │   ├── dev-environment.md    #   Python 開発環境設定（uv・ruff・ty・marimo）
│   │   └── testing.md            #   Python テストルール（pytest・AAA・fixtures）
│   ├── php/                      # [条件: **/*.php] PHP 固有ルール
│   │   ├── coding-style.md       #   PHP コーディングスタイル（PHP 8.x・PSR-12）
│   │   └── comments.md           #   PHP コメント規約
│   ├── laravel/                  # [条件: **/*.php] Laravel 固有ルール
│   │   ├── conventions.md        #   Laravel 命名規則・Eloquent・Controller 規約
│   │   ├── architecture.md       #   Laravel アーキテクチャ設計
│   │   ├── database.md           #   Laravel データベース規約
│   │   └── frontend-integration.md # Laravel+jQuery フロントエンド統合
│   ├── javascript/               # [条件: **/*.js,*.ts] JavaScript 固有ルール
│   │   ├── jquery-style.md       #   jQuery コーディングスタイル
│   │   └── naming-and-comments.md #  JS 命名規則・コメント規約
│   └── hardware/                 # [条件: **/*.ino,*.c,*.cpp] ハードウェア開発ルール
│       ├── embedded-c-style.md   #   組み込み C/C++ スタイル
│       ├── raspberry-pi.md       #   Raspberry Pi 開発規約
│       └── esp32.md              #   ESP32 開発規約
│
│  # ===== skills/ (42 dirs) =====
│  # /スキル名 で呼び出せる作業手順書
│  # 構成: SKILL.md (概要+description) + INSTRUCTIONS.md (詳細手順)
│  # 高度なスキルは agents/, references/, scripts/ を持つ
│  #
│  # 設計原則:
│  #   - SKILL.md はフロー制御に徹する（専門処理は agents/ に分離）
│  #   - 確定的処理 → scripts/、判断・分析 → Agent
│  #   - スキーマ契約は references/schemas.md に定義
│  #   - description は押し強めに（トリガー判定に使われる唯一の情報）
│  #   - 並列性 → Sub-agent型、順序性 → Skill Chain型
└── skills/
    ├── SKILL_TEMPLATE.md            # スキル定義のテンプレート
    │
    │  # --- 計画・レビュー ---
    ├── create-proposal/             # 依頼文→構造化要件書（proposal.md）
    ├── create-plan/                 # 要件書→実装計画（plan.md）
    ├── proposal-quality-gate/       # 計画前の品質チェック
    ├── propose-one/                 # 1課題ずつ proposal→plan を実行
    ├── writing-plans/               # 実装計画ドキュメントの書き方
    ├── planning-with-files/         # ファイルに計画を書きながら進める実装フロー
    ├── implement-plans/             # 計画を実行に移すときの手順
    ├── code-review/                 # コードレビューの進め方
    ├── codex-review/                # Codex レビューループ
    │
    │  # --- 開発ワークフロー ---
    ├── analyze-project/             # プロジェクト分析 → ルール・スキル自動生成
    ├── brainstorming/               # ソクラテス式ブレスト → 要件・設計を問いかけで整理
    ├── claude-code-setup/           # Claude Code 環境セットアップ
    ├── claude-md-management/        # CLAUDE.md の管理・改訂
    ├── design-tracker/              # 設計変更の追跡
    ├── feedback-loop/               # フィードバック分類・記録・自動対策提案
    ├── fix-escalation/              # 2回失敗でエスカレーション調査を強制
    ├── verify-before-fix/           # 修正前の証拠収集ゲート
    ├── handover/                    # セッション引き継ぎドキュメントの手動生成
    ├── claude-template-sync/        # .claude_remote → .claude の安全な同期
    ├── init/                        # プロジェクト初期化
    ├── simplify/                    # コード簡素化
    ├── systematic-debugging/        # 体系的なデバッグ手順
    ├── tdd-workflow/                # テスト駆動開発 (+TDD の哲学と原則)
    │
    │  # --- スキル・プラグイン開発 ---
    ├── skill-creator/               # スキル定義の作成・評価・最適化
    ├── hookify/                     # フック設定の自動生成
    │
    │  # --- フロントエンド ---
    ├── accessibility/               # アクセシビリティ対応
    ├── frontend-design/             # フロントエンド設計 (+UI/UX 設計原則)
    ├── css-features/                # CSS モダン機能（ネスト・コンテナクエリ・:has()）
    ├── css-layout/                  # CSS レイアウト（Grid・Flexbox・レスポンシブ）
    ├── css-organization/            # CSS の整理・設計（BEM・変数・アニメーション）
    ├── jquery-interactions/         # jQuery インタラクション（AJAX・イベント・アニメーション）
    │
    │  # --- バックエンド・インフラ ---
    ├── docker-dev/                  # Docker Compose ベースの開発フロー
    ├── mcp-builder/                 # MCP サーバーの構築
    │
    │  # --- ハードウェア ---
    ├── esp32/                       # ESP32 開発ガイド（PlatformIO・WiFi・FreeRTOS・OTA）
    ├── raspberry-pi/                # Raspberry Pi 開発ガイド（GPIO・センサー・カメラ・systemd）
    │
    │  # --- ライブラリ・ツール ---
    ├── research-lib/                # ライブラリ調査
    ├── wolfram-foundation-tool/     # Wolfram 基盤ツール
    │
    │  # --- VBA ---
    ├── vba-core/                    # VBA コア機能（エラーハンドリング・変数宣言・メモリ管理）
    ├── vba-excel/                   # Excel VBA（ワークシートイベント・UserForm・セキュリティ）
    └── vba-patterns/                # VBA パターン集（最終行取得・配列ループ・ファイル操作）
```

---

## 分類早見表

| フォルダ / ファイル | 役割 |
|---|---|
| `CLAUDE.md`        | Claude Code に読み込ませるメイン指示ファイル |
| `agents/` (22)     | 専門作業を担う名前付きエージェント |
| `commands/` (26)   | スラッシュコマンドのショートカット定義 |
| `docs/`            | 設計ドキュメント・メモリ・運用情報 |
| `docs/references/` | スキルから移動したリファレンス資料（セキュリティ・Git・プラグイン等） |
| `hooks/`           | Pre/Post ToolUse 等で自動実行されるスクリプト |
| `hooks/lib/`       | フック共通ライブラリ（transcript 解析・claude -p 呼び出し） |
| `mcp/`             | 外部ツール連携 (DB・ブラウザ・ファイル等) の設定テンプレ |
| `meta/`            | .claude 自体の品質管理・自動生成スクリプト |
| `registry/`        | スキルルーティングインデックス（generate-registry.py が生成） |
| `resources/`       | 外部参考資料・便利ツール集 |
| `rules/` (26)      | 常時ロード(9)+条件付き(17)ルール (セキュリティ・コーディング規約等) |
| `skills/` (42)     | 作業手順のレシピ集 (呼び出して使う) |
| `settings.json`    | フック・パーミッション設定 |
| `.claudeignore`    | Claude に読ませないファイルのパターン |

---

## ルールのロード方式

| 方式 | ルール | 説明 |
|------|--------|------|
| **常時ロード** (9) | coding-principles, language, security-rules, neutral-analysis, skill-execution, work-modes, common/* | セッション開始時に必ず注入（約430行） |
| **条件付き** (17) | python/*, php/*, laravel/*, javascript/*, hardware/*, project-conventions, ui-fix-verification, _PATH_RULES_GUIDE | `paths:` フロントマターで対象ファイル操作時のみ注入 |

---

## スキル設計パターン

| パターン | 用途 | 例 |
|---------|------|-----|
| **Sub-agent 型** | 並列実行・文脈継承・Human-in-the-Loop | skill-creator（grader/comparator を並列 spawn） |
| **Skill Chain 型** | 順序実行・各スキル独立利用可 | create-proposal → create-plan → implement-plans |
| **シンプル型** | SKILL.md + INSTRUCTIONS.md のみ | tdd-workflow, brainstorming |

---

## ローカル CLAUDE.md

プロジェクト内のリスクが高いディレクトリに小さな CLAUDE.md を配置できる。
Claude がそのディレクトリ内のファイルを操作する時、自動的にローカル CLAUDE.md が読み込まれる。

```
src/auth/CLAUDE.md              # 認証・認可の落とし穴
database/migrations/CLAUDE.md   # マイグレーション規約
app/Services/Payment/CLAUDE.md  # 決済ロジック固有の制約
```

配置基準とテンプレートは GUIDE.md のセクション10を参照。
