# Installation Guide

このガイドでは、Claude Code設定ファイルをシステムにインストールする方法を説明します。

## 前提条件

- Claude Code CLI がインストールされている
- Node.js (v16以上) がインストールされている（一部の機能で必要）
- Git がインストールされている

## インストール方法

### 方法1: プラグインとしてインストール（推奨）

このリポジトリをClaudeのマーケットプレイスに追加します：

```bash
# マーケットプレイスに追加
/plugin marketplace add <your-github-username>/claude-config

# プラグインをインストール
/plugin install claude-config@<your-github-username>
```

### 方法2: 手動インストール

#### ステップ1: 設定ディレクトリを作成

```bash
# Windowsの場合
mkdir -p %USERPROFILE%\.claude\skills
mkdir -p %USERPROFILE%\.claude\agents
mkdir -p %USERPROFILE%\.claude\rules
mkdir -p %USERPROFILE%\.claude\commands
mkdir -p %USERPROFILE%\.claude\hooks

# macOS/Linuxの場合
mkdir -p ~/.claude/skills
mkdir -p ~/.claude/agents
mkdir -p ~/.claude/rules
mkdir -p ~/.claude/commands
mkdir -p ~/.claude/hooks
```

#### ステップ2: ファイルをコピー

```bash
# Windowsの場合
xcopy /E /I claude_code_tests\skills %USERPROFILE%\.claude\skills
xcopy /E /I claude_code_tests\agents %USERPROFILE%\.claude\agents
xcopy /E /I claude_code_tests\rules %USERPROFILE%\.claude\rules
xcopy /E /I claude_code_tests\commands %USERPROFILE%\.claude\commands

# macOS/Linuxの場合
cp -r claude_code_tests/skills/* ~/.claude/skills/
cp -r claude_code_tests/agents/* ~/.claude/agents/
cp -r claude_code_tests/rules/* ~/.claude/rules/
cp -r claude_code_tests/commands/* ~/.claude/commands/
```

#### ステップ3: フックを設定（オプション）

`hooks_examples.sh`を参考にして、必要なフックを作成します。

```bash
# Windowsの場合
copy claude_code_tests\hooks_examples.sh %USERPROFILE%\.claude\hooks\

# macOS/Linuxの場合
cp claude_code_tests/hooks_examples.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/hooks_examples.sh
```

Claude設定ファイル（`~/.claude/settings.json`）にフックを追加：

```json
{
  "hooks": {
    "pre-commit": "~/.claude/hooks/hooks_examples.sh",
    "post-tool": "~/.claude/hooks/hooks_examples.sh"
  }
}
```

### 方法3: プロジェクト固有の設定

特定のプロジェクトにのみ設定を適用する場合：

```bash
# プロジェクトルートに.claudeディレクトリを作成
mkdir .claude

# 設定ファイルをコピー
cp -r claude_code_tests/skills .claude/
cp -r claude_code_tests/agents .claude/
cp -r claude_code_tests/rules .claude/

# プロジェクト設定を作成
cat > .claude/config.json << EOF
{
  "skills": ["code-review", "tdd-workflow"],
  "agents": ["planner"],
  "rules": ["security-rules"]
}
EOF
```

## 設定のカスタマイズ

### スキルの選択

すべてのスキルを有効にする必要はありません。プロジェクトに必要なものだけを選択してください：

```json
// .claude/config.json
{
  "enabledSkills": [
    "code-review",
    "tdd-workflow"
  ]
}
```

### MCPサーバーの制限

コンテキストウィンドウを最適化するため、使用するMCPサーバーを制限します：

```json
// ~/.claude/settings.json
{
  "mcpServers": {
    "filesystem": { "enabled": true },
    "github": { "enabled": true },
    "aws": { "enabled": false },
    "kubernetes": { "enabled": false }
  }
}
```

### パッケージマネージャーの設定

プロジェクトで使用するパッケージマネージャーを指定：

```json
// .claude/package-manager.json
{
  "packageManager": "pnpm"
}
```

または環境変数で設定：

```bash
# .env または .bashrc/.zshrc
export CLAUDE_PACKAGE_MANAGER=pnpm
```

## インストールの確認

### スキルのテスト

```bash
# Claude Codeを起動
claude

# スキルを使用してみる
/review src/index.ts
```

### エージェントのテスト

```bash
# プランエージェントを使用
/plan
```

### 設定の確認

```bash
# 有効なスキルを確認
/skills list

# 有効なコマンドを確認
/commands list
```

## トラブルシューティング

### 問題: スキルが読み込まれない

**原因**: ファイルパスが正しくない

**解決策**:
```bash
# スキルディレクトリを確認
ls ~/.claude/skills

# スキルファイルの形式を確認
cat ~/.claude/skills/code-review.md
```

### 問題: フックが実行されない

**原因**: 実行権限がない（macOS/Linux）

**解決策**:
```bash
# 実行権限を付与
chmod +x ~/.claude/hooks/*.sh

# フック設定を確認
cat ~/.claude/settings.json
```

### 問題: コマンドが見つからない

**原因**: コマンドファイルの形式が正しくない

**解決策**:
```bash
# コマンドファイルの形式を確認
cat ~/.claude/commands/tdd.json

# JSONの妥当性を確認
node -e "console.log(require('./.claude/commands/tdd.json'))"
```

## アップグレード

### プラグインの更新

```bash
/plugin update claude-config
```

### 手動更新

```bash
# 最新版をダウンロード
git pull origin main

# ファイルを再コピー
cp -r claude_code_tests/skills/* ~/.claude/skills/
cp -r claude_code_tests/agents/* ~/.claude/agents/
cp -r claude_code_tests/rules/* ~/.claude/rules/
```

## アンインストール

### プラグインのアンインストール

```bash
/plugin uninstall claude-config
```

### 手動アンインストール

```bash
# Windowsの場合
rmdir /S /Q %USERPROFILE%\.claude

# macOS/Linuxの場合
rm -rf ~/.claude
```

## 次のステップ

1. [quick_start.md](quick_start.md)を読んで基本的な使い方を学ぶ
2. [custom_instructions.md](custom_instructions.md)でベストプラクティスを確認
3. [agent_usage_guide.md](agent_usage_guide.md)でエージェントの使い方を学ぶ
4. [context-management.md](context-management.md)でパフォーマンス最適化を理解

## サポート

- **ドキュメント**: このディレクトリ内のMarkdownファイル
- **Issues**: https://github.com/anthropics/claude-code/issues
- **Discussion**: https://github.com/anthropics/claude-code/discussions
