# プラグイン推奨

プラグインは、スキル、コマンド、エージェント、フックのインストール可能なコレクションです。`/plugin install` でインストールできます。

**注意**: これらは公式リポジトリのプラグインです。追加のコミュニティプラグインを見つけるには、Web 検索を使用してください。

---

## 公式プラグイン

### 開発 & コード品質

| プラグイン | 最適な用途 | 主な機能 |
|--------|----------|--------------|
| **plugin-dev** | Claude Code プラグインの構築 | スキル、フック、コマンド、エージェントの作成スキル |
| **pr-review-toolkit** | PR レビューワークフロー | 専門レビューエージェント（コード、テスト、型） |
| **code-review** | 自動コードレビュー | 信頼度スコアリング付きマルチエージェントレビュー |
| **code-simplifier** | コードリファクタリング | 機能を保持しつつコードを簡素化 |
| **feature-dev** | 機能開発 | エージェントを使ったエンドツーエンドの機能ワークフロー |

### Git & ワークフロー

| プラグイン | 最適な用途 | 主な機能 |
|--------|----------|--------------|
| **commit-commands** | Git ワークフロー | /commit, /commit-push-pr コマンド |
| **hookify** | 自動化ルール | 会話パターンからフックを作成 |

### フロントエンド

| プラグイン | 最適な用途 | 主な機能 |
|--------|----------|--------------|
| **frontend-design** | UI 開発 | プロダクショングレードの UI、汎用的な美学を回避 |

### 学習 & ガイダンス

| プラグイン | 最適な用途 | 主な機能 |
|--------|----------|--------------|
| **explanatory-output-style** | 学習 | コード選択に関する教育的インサイト |
| **learning-output-style** | インタラクティブ学習 | 判断ポイントで貢献を要求 |
| **security-guidance** | セキュリティ意識 | 編集時にセキュリティ問題を警告 |

### 言語サーバー (LSP)

| プラグイン | 言語 |
|--------|----------|
| **typescript-lsp** | TypeScript/JavaScript |
| **pyright-lsp** | Python |
| **gopls-lsp** | Go |
| **rust-analyzer-lsp** | Rust |
| **clangd-lsp** | C/C++ |
| **jdtls-lsp** | Java |
| **kotlin-lsp** | Kotlin |
| **swift-lsp** | Swift |
| **csharp-lsp** | C# |
| **php-lsp** | PHP |
| **lua-lsp** | Lua |

---

## クイックリファレンス: コードベース → プラグイン

| コードベースのシグナル | 推奨プラグイン |
|-----------------|-------------------|
| プラグインの構築 | plugin-dev |
| PR ベースのワークフロー | pr-review-toolkit |
| Git コミット | commit-commands |
| React/Vue/Angular | frontend-design |
| 自動化ルールが必要 | hookify |
| TypeScript プロジェクト | typescript-lsp |
| Python プロジェクト | pyright-lsp |
| Go プロジェクト | gopls-lsp |
| セキュリティ重視のコード | security-guidance |
| 学習/オンボーディング | explanatory-output-style |

---

## プラグイン管理

```bash
# プラグインのインストール
/plugin install <plugin-name>

# インストール済みプラグインの一覧
/plugin list

# プラグインの詳細表示
/plugin info <plugin-name>
```

---

## プラグインを推奨する場面

**以下の場合にプラグインのインストールを推奨:**
- ユーザーが Anthropic の公式リポジトリまたは他の共有マーケットプレイスから Claude Code オートメーションをインストールしたい場合
- ユーザーが複数の関連機能を必要としている場合
- チームが標準化されたワークフローを求めている場合
- Claude Code の初期セットアップ時
