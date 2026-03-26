# マーケットプレイスのためのコマンド設計

配布とマーケットプレイスでの成功を目的としたコマンド作成のガイドライン。

## 概要

マーケットプレイスを通じて配布されるコマンドは、個人使用のコマンド以上の考慮が必要。異なる環境で動作し、多様なユースケースを処理し、未知のユーザーに優れたユーザー体験を提供しなければならない。

## 配布のための設計

### ユニバーサル互換性

**クロスプラットフォームの考慮事項:**

```markdown
---
description: Cross-platform command
allowed-tools: Bash(*)
---

# Platform-Aware Command

Detecting platform...

case "$(uname)" in
  Darwin*)  PLATFORM="macOS" ;;
  Linux*)   PLATFORM="Linux" ;;
  MINGW*|MSYS*|CYGWIN*) PLATFORM="Windows" ;;
  *)        PLATFORM="Unknown" ;;
esac

Platform: $PLATFORM

<!-- プラットフォームに基づいて動作を調整 -->
if [ "$PLATFORM" = "Windows" ]; then
  # Windows 固有の処理
  PATH_SEP="\\"
  NULL_DEVICE="NUL"
else
  # Unix 系の処理
  PATH_SEP="/"
  NULL_DEVICE="/dev/null"
fi

[Platform-appropriate implementation...]
```

**プラットフォーム固有のコマンドを避ける:**

```markdown
<!-- 悪い例: macOS 固有 -->
!`pbcopy < file.txt`

<!-- 良い例: プラットフォーム検出 -->
if command -v pbcopy > /dev/null; then
  pbcopy < file.txt
elif command -v xclip > /dev/null; then
  xclip -selection clipboard < file.txt
elif command -v clip.exe > /dev/null; then
  cat file.txt | clip.exe
else
  echo "Clipboard not available on this platform"
fi
```

### 最小限の依存関係

**必要なツールのチェック:**

```markdown
---
description: Dependency-aware command
allowed-tools: Bash(*)
---

# Check Dependencies

Required tools:
- git
- jq
- node

Checking availability...

MISSING_DEPS=""

for tool in git jq node; do
  if ! command -v $tool > /dev/null; then
    MISSING_DEPS="$MISSING_DEPS $tool"
  fi
done

if [ -n "$MISSING_DEPS" ]; then
  ❌ ERROR: Missing required dependencies:$MISSING_DEPS

  INSTALLATION:
  - git: https://git-scm.com/downloads
  - jq: https://stedolan.github.io/jq/download/
  - node: https://nodejs.org/

  Install missing tools and try again.

  Exit.
fi

✓ All dependencies available

[Continue with command...]
```

**オプション依存関係のドキュメント:**

```markdown
<!--
DEPENDENCIES:
  必須:
  - git 2.0+: バージョン管理
  - jq 1.6+: JSON 処理

  オプション:
  - gh: GitHub CLI（PR 操作用）
  - docker: コンテナ操作（コンテナ化テスト用）

  機能の利用可能性はインストール済みツールに依存する。
-->
```

### グレースフルデグラデーション

**機能の欠如を処理する:**

```markdown
---
description: Feature-aware command
---

# Feature Detection

Detecting available features...

FEATURES=""

if command -v gh > /dev/null; then
  FEATURES="$FEATURES github"
fi

if command -v docker > /dev/null; then
  FEATURES="$FEATURES docker"
fi

Available features: $FEATURES

if echo "$FEATURES" | grep -q "github"; then
  # GitHub 統合付きのフル機能
  echo "✓ GitHub integration available"
else
  # GitHub なしの縮小機能
  echo "⚠ Limited functionality: GitHub CLI not installed"
  echo "  Install 'gh' for full features"
fi

[Adapt behavior based on available features...]
```

## 未知のユーザーのためのユーザー体験

### 明確なオンボーディング

**初回実行体験:**

```markdown
---
description: Command with onboarding
allowed-tools: Read, Write
---

# First Run Check

if [ ! -f ".claude/command-initialized" ]; then
  **Welcome to Command Name!**

  This appears to be your first time using this command.

  WHAT THIS COMMAND DOES:
  [Brief explanation of purpose and benefits]

  QUICK START:
  1. Basic usage: /command [arg]
  2. For help: /command help
  3. Examples: /command examples

  SETUP:
  No additional setup required. You're ready to go!

  ✓ Initialization complete

  [Create initialization marker]

  Ready to proceed with your request...
fi

[Normal command execution...]
```

**段階的な機能の発見:**

```markdown
---
description: Command with tips
---

# Command Execution

[Main functionality...]

---

💡 TIP: Did you know?

You can speed up this command with the --fast flag:
  /command --fast [args]

For more tips: /command tips
```

### 包括的なエラーハンドリング

**ユーザーのミスを予測する:**

```markdown
---
description: Forgiving command
---

# User Input Handling

Argument: "$1"

<!-- よくあるタイプミスのチェック -->
if [ "$1" = "hlep" ] || [ "$1" = "hepl" ]; then
  Did you mean: help?

  Showing help instead...
  [Display help]

  Exit.
fi

<!-- 見つからない場合に類似コマンドを提案 -->
if [ "$1" != "valid-option1" ] && [ "$1" != "valid-option2" ]; then
  ❌ Unknown option: $1

  Did you mean:
  - valid-option1 (most similar)
  - valid-option2

  For all options: /command help

  Exit.
fi

[Command continues...]
```

**有用な診断情報:**

```markdown
---
description: Diagnostic command
---

# Operation Failed

The operation could not complete.

**Diagnostic Information:**

Environment:
- Platform: $(uname)
- Shell: $SHELL
- Working directory: $(pwd)
- Command: /command $@

Checking common issues:
- Git repository: $(git rev-parse --git-dir 2>&1)
- Write permissions: $(test -w . && echo "OK" || echo "DENIED")
- Required files: $(test -f config.yml && echo "Found" || echo "Missing")

This information helps debug the issue.

For support, include the above diagnostics.
```

## 配布のベストプラクティス

### 名前空間の意識

**名前の衝突を避ける:**

```markdown
---
description: Namespaced command
---

<!--
COMMAND NAME: plugin-name-command

このコマンドはプラグイン名で名前空間化されており、
他のプラグインのコマンドとの衝突を避けている。

代替の命名アプローチ:
- プラグインプレフィックス: /plugin-command
- カテゴリ: /category-command
- 動詞-名詞: /verb-noun

選択したアプローチ: plugin-name プレフィックス
理由: 所有権が最も明確で、衝突の可能性が最も低い
-->

# Plugin Name Command

[Implementation...]
```

**命名の根拠をドキュメント化:**

```markdown
<!--
NAMING DECISION:

コマンド名: /deploy-app

検討した代替案:
- /deploy: 汎用すぎる、衝突の可能性が高い
- /app-deploy: 直感的でない順序
- /my-plugin-deploy: 冗長すぎる

最終選択のバランス:
- 発見しやすさ（目的が明確）
- 簡潔さ（入力しやすい）
- 一意性（衝突の可能性が低い）
-->
```

### 設定可能性

**ユーザープリファレンス:**

```markdown
---
description: Configurable command
allowed-tools: Read
---

# Load User Configuration

Default configuration:
- verbose: false
- color: true
- max_results: 10

Checking for user config: .claude/plugin-name.local.md

if [ -f ".claude/plugin-name.local.md" ]; then
  # YAML フロントマターから設定を解析
  VERBOSE=$(grep "^verbose:" .claude/plugin-name.local.md | cut -d: -f2 | tr -d ' ')
  COLOR=$(grep "^color:" .claude/plugin-name.local.md | cut -d: -f2 | tr -d ' ')
  MAX_RESULTS=$(grep "^max_results:" .claude/plugin-name.local.md | cut -d: -f2 | tr -d ' ')

  echo "✓ Using user configuration"
else
  echo "Using default configuration"
  echo "Create .claude/plugin-name.local.md to customize"
fi

[Use configuration in command...]
```

**賢いデフォルト値:**

```markdown
---
description: Command with smart defaults
---

# Smart Defaults

Configuration:
- Format: ${FORMAT:-json}  # デフォルトは json
- Output: ${OUTPUT:-stdout}  # デフォルトは stdout
- Verbose: ${VERBOSE:-false}  # デフォルトは false

These defaults work for 80% of use cases.

Override with arguments:
  /command --format yaml --output file.txt --verbose

Or set in .claude/plugin-name.local.md:
\`\`\`yaml
---
format: yaml
output: custom.txt
verbose: true
---
\`\`\`
```

### バージョン互換性

**バージョンチェック:**

```markdown
---
description: Version-aware command
---

<!--
COMMAND VERSION: 2.1.0

COMPATIBILITY:
- プラグインバージョン >= 2.0.0 が必要
- v1.x からの破壊的変更は MIGRATION.md に記載

VERSION HISTORY:
- v2.1.0: --new-feature フラグを追加
- v2.0.0: 破壊的変更: 引数の順序を変更
- v1.0.0: 初回リリース
-->

# Version Check

Command version: 2.1.0
Plugin version: [detect from plugin.json]

if [  "$PLUGIN_VERSION" < "2.0.0" ]; then
  ❌ ERROR: Incompatible plugin version

  This command requires plugin version >= 2.0.0
  Current version: $PLUGIN_VERSION

  Update plugin:
    /plugin update plugin-name

  Exit.
fi

✓ Version compatible

[Command continues...]
```

**非推奨警告:**

```markdown
---
description: Command with deprecation warnings
---

# Deprecation Check

if [ "$1" = "--old-flag" ]; then
  ⚠️  DEPRECATION WARNING

  The --old-flag option is deprecated as of v2.0.0
  It will be removed in v3.0.0 (est. June 2025)

  Use instead: --new-flag

  Example:
    Old: /command --old-flag value
    New: /command --new-flag value

  See migration guide: /command migrate

  Continuing with deprecated behavior for now...
fi

[Handle both old and new flags during deprecation period...]
```

## マーケットプレイスでの表示

### コマンドの発見

**説明的な命名:**

```markdown
---
description: Review pull request with security and quality checks
---

<!-- 良い例: 説明的な名前と description -->
```

```markdown
---
description: Do the thing
---

<!-- 悪い例: 曖昧な description -->
```

**検索可能なキーワード:**

```markdown
<!--
KEYWORDS: security, code-review, quality, validation, audit

これらのキーワードは、ユーザーがマーケットプレイスで
関連機能を検索する際にこのコマンドを発見するのに役立つ。
-->
```

### ショーケース例

**説得力のあるデモンストレーション:**

```markdown
---
description: Advanced code analysis command
---

# Code Analysis Command

This command performs deep code analysis with actionable insights.

## Demo: Quick Security Audit

Try it now:
\`\`\`
/analyze-code src/ --security
\`\`\`

**What you'll get:**
- Security vulnerability detection
- Code quality metrics
- Performance bottleneck identification
- Actionable recommendations

**Sample output:**
\`\`\`
Security Analysis Results
=========================

🔴 Critical (2):
  - SQL injection risk in users.js:45
  - XSS vulnerability in display.js:23

🟡 Warnings (5):
  - Unvalidated input in api.js:67
  ...

Recommendations:
1. Fix critical issues immediately
2. Review warnings before next release
3. Run /analyze-code --fix for auto-fixes
\`\`\`

---

Ready to analyze your code...

[Command implementation...]
```

### ユーザーレビューとフィードバック

**フィードバックメカニズム:**

```markdown
---
description: Command with feedback
---

# Command Complete

[Command results...]

---

**How was your experience?**

This helps improve the command for everyone.

Rate this command:
- 👍 Helpful
- 👎 Not helpful
- 🐛 Found a bug
- 💡 Have a suggestion

Reply with an emoji or:
- /command feedback

Your feedback matters!
```

**使用分析の準備:**

```markdown
<!--
ANALYTICS NOTES:

改善のために追跡するもの:
- よく使われる引数
- 失敗率
- 平均実行時間
- ユーザー満足度スコア

プライバシー保護:
- 個人を特定できる情報なし
- 集計統計のみ
- ユーザーのオプトアウトを尊重
-->
```

## 品質基準

### プロフェッショナルな仕上げ

**一貫したブランディング:**

```markdown
---
description: Branded command
---

# ✨ Command Name

Part of the [Plugin Name] suite

[Command functionality...]

---

**Need Help?**
- Documentation: https://docs.example.com
- Support: support@example.com
- Community: https://community.example.com

Powered by Plugin Name v2.1.0
```

**ディテールへの注意:**

```markdown
<!-- 重要なディテール -->

✓ 絵文字/記号を一貫して使用
✓ 出力カラムを整列
✓ 数値に桁区切りを使用
✓ カラー/フォーマットを適切に使用
✓ 進捗インジケーターを提供
✓ 推定残り時間を表示
✓ 成功した操作を確認
```

### 信頼性

**冪等性:**

```markdown
---
description: Idempotent command
---

# Safe Repeated Execution

Checking if operation already completed...

if [ -f ".claude/operation-completed.flag" ]; then
  ℹ️  Operation already completed

  Completed at: $(cat .claude/operation-completed.flag)

  To re-run:
  1. Remove flag: rm .claude/operation-completed.flag
  2. Run command again

  Otherwise, no action needed.

  Exit.
fi

Performing operation...

[Safe, repeatable operation...]

Marking complete...
echo "$(date)" > .claude/operation-completed.flag
```

**アトミック操作:**

```markdown
---
description: Atomic command
---

# Atomic Operation

This operation is atomic - either fully succeeds or fully fails.

Creating temporary workspace...
TEMP_DIR=$(mktemp -d)

Performing changes in isolated environment...
[Make changes in $TEMP_DIR]

if [ $? -eq 0 ]; then
  ✓ Changes validated

  Applying changes atomically...
  mv $TEMP_DIR/* ./target/

  ✓ Operation complete
else
  ❌ Changes failed validation

  Rolling back...
  rm -rf $TEMP_DIR

  No changes applied. Safe to retry.
fi
```

## 配布のためのテスト

### リリース前チェックリスト

```markdown
<!--
PRE-RELEASE CHECKLIST:

機能:
- [ ] macOS で動作する
- [ ] Linux で動作する
- [ ] Windows (WSL) で動作する
- [ ] すべての引数がテスト済み
- [ ] エラーケースが処理されている
- [ ] エッジケースがカバーされている

ユーザー体験:
- [ ] 明確な description
- [ ] 有用なエラーメッセージ
- [ ] 例が提供されている
- [ ] 初回実行体験が良い
- [ ] ドキュメントが完備

配布:
- [ ] ハードコードされたパスがない
- [ ] 依存関係がドキュメント化されている
- [ ] 設定オプションが明確
- [ ] バージョン番号が設定済み
- [ ] 変更ログが更新済み

品質:
- [ ] TODO コメントがない
- [ ] デバッグコードがない
- [ ] パフォーマンスが許容範囲
- [ ] セキュリティがレビュー済み
- [ ] プライバシーが考慮されている

サポート:
- [ ] README が完備
- [ ] トラブルシューティングガイド
- [ ] サポート連絡先が提供されている
- [ ] フィードバックメカニズム
- [ ] ライセンスが指定されている
-->
```

### ベータテスト

**ベータリリースアプローチ:**

```markdown
---
description: Beta command (v0.9.0)
---

# 🧪 Beta Command

**This is a beta release**

Features may change based on feedback.

BETA STATUS:
- Version: 0.9.0
- Stability: Experimental
- Support: Limited
- Feedback: Encouraged

Known limitations:
- Performance not optimized
- Some edge cases not handled
- Documentation incomplete

Help improve this command:
- Report issues: /command report-issue
- Suggest features: /command suggest
- Join beta testers: /command join-beta

---

[Command implementation...]

---

**Thank you for beta testing!**

Your feedback helps make this command better.
```

## メンテナンスと更新

### 更新戦略

**バージョン管理されたコマンド:**

```markdown
<!--
VERSION STRATEGY:

メジャー (X.0.0): 破壊的変更
- すべての破壊的変更をドキュメント化
- 移行ガイドを提供
- 旧バージョンを短期間サポート

マイナー (x.Y.0): 新機能
- 後方互換
- 新機能をアナウンス
- 例を更新

パッチ (x.y.Z): バグ修正
- ユーザー向けの変更なし
- 変更ログを更新
- セキュリティ修正を優先

リリーススケジュール:
- パッチ: 必要に応じて
- マイナー: 月次
- メジャー: 年次または必要に応じて
-->
```

**更新通知:**

```markdown
---
description: Update-aware command
---

# Check for Updates

Current version: 2.1.0
Latest version: [check if available]

if [ "$CURRENT_VERSION" != "$LATEST_VERSION" ]; then
  📢 UPDATE AVAILABLE

  New version: $LATEST_VERSION
  Current: $CURRENT_VERSION

  What's new:
  - Feature improvements
  - Bug fixes
  - Performance enhancements

  Update with:
    /plugin update plugin-name

  Release notes: https://releases.example.com/v$LATEST_VERSION
fi

[Command continues...]
```

## ベストプラクティスのまとめ

### 配布設計

1. **ユニバーサル:** プラットフォームや環境を問わず動作
2. **自己完結:** 最小限の依存関係、明確な要件
3. **グレースフル:** 機能が利用できない場合も優雅に劣化
4. **寛容:** ユーザーのミスを予測して処理
5. **有用:** 明確なエラー、良いデフォルト、優れたドキュメント

### マーケットプレイスでの成功

1. **発見しやすい:** 明確な名前、良い description、検索可能なキーワード
2. **プロフェッショナル:** 洗練された表示、一貫したブランディング
3. **信頼できる:** 徹底的にテスト、エッジケースを処理
4. **保守しやすい:** バージョン管理、定期的に更新、サポート付き
5. **ユーザー中心:** 優れた UX、フィードバックに応答

### 品質基準

1. **完全:** 完全にドキュメント化、すべての機能が動作
2. **テスト済み:** 実環境で動作、エッジケースを処理
3. **安全:** 脆弱性なし、安全な操作
4. **高パフォーマンス:** 合理的な速度、リソース効率的
5. **倫理的:** プライバシーを尊重、ユーザーの同意

これらの考慮事項により、コマンドはマーケットプレイス対応となり、多様な環境とユースケースのユーザーを満足させる。
