# コマンドテスト戦略

デプロイと配布前にスラッシュコマンドをテストするための包括的な戦略。

## 概要

コマンドのテストにより、正しく動作し、エッジケースを処理し、良好なユーザーエクスペリエンスを提供できることを確認する。体系的なテストアプローチにより、問題を早期に発見し、コマンドの信頼性への確信を築く。

## テストレベル

### レベル 1: 構文と構造の検証

**テスト対象:**
- YAML フロントマター構文
- Markdown フォーマット
- ファイルの場所と命名

**テスト方法:**

```bash
# YAML フロントマターの検証
head -n 20 .claude/commands/my-command.md | grep -A 10 "^---"

# 閉じフロントマターマーカーの確認
head -n 20 .claude/commands/my-command.md | grep -c "^---" # 2であるべき

# .md 拡張子の確認
ls .claude/commands/*.md

# 正しい場所にあるか確認
test -f .claude/commands/my-command.md && echo "Found" || echo "Missing"
```

**自動検証スクリプト:**

```bash
#!/bin/bash
# validate-command.sh

COMMAND_FILE="$1"

if [ ! -f "$COMMAND_FILE" ]; then
  echo "ERROR: File not found: $COMMAND_FILE"
  exit 1
fi

# .md 拡張子の確認
if [[ ! "$COMMAND_FILE" =~ \.md$ ]]; then
  echo "ERROR: File must have .md extension"
  exit 1
fi

# YAML フロントマターの検証（存在する場合）
if head -n 1 "$COMMAND_FILE" | grep -q "^---"; then
  # フロントマターマーカーのカウント
  MARKERS=$(head -n 50 "$COMMAND_FILE" | grep -c "^---")
  if [ "$MARKERS" -ne 2 ]; then
    echo "ERROR: Invalid YAML frontmatter (need exactly 2 '---' markers)"
    exit 1
  fi
  echo "✓ YAML frontmatter syntax valid"
fi

# 空ファイルの確認
if [ ! -s "$COMMAND_FILE" ]; then
  echo "ERROR: File is empty"
  exit 1
fi

echo "✓ Command file structure valid"
```

### レベル 2: フロントマターフィールドの検証

**テスト対象:**
- フィールドの型が正しいか
- 値が有効な範囲内か
- 必須フィールドが存在するか（ある場合）

**検証スクリプト:**

```bash
#!/bin/bash
# validate-frontmatter.sh

COMMAND_FILE="$1"

# YAML フロントマターの抽出
FRONTMATTER=$(sed -n '/^---$/,/^---$/p' "$COMMAND_FILE" | sed '1d;$d')

if [ -z "$FRONTMATTER" ]; then
  echo "No frontmatter to validate"
  exit 0
fi

# 'model' フィールドの確認（存在する場合）
if echo "$FRONTMATTER" | grep -q "^model:"; then
  MODEL=$(echo "$FRONTMATTER" | grep "^model:" | cut -d: -f2 | tr -d ' ')
  if ! echo "sonnet opus haiku" | grep -qw "$MODEL"; then
    echo "ERROR: Invalid model '$MODEL' (must be sonnet, opus, or haiku)"
    exit 1
  fi
  echo "✓ Model field valid: $MODEL"
fi

# 'allowed-tools' フィールドのフォーマット確認
if echo "$FRONTMATTER" | grep -q "^allowed-tools:"; then
  echo "✓ allowed-tools field present"
  # より詳細な検証をここに追加可能
fi

# 'description' の長さ確認
if echo "$FRONTMATTER" | grep -q "^description:"; then
  DESC=$(echo "$FRONTMATTER" | grep "^description:" | cut -d: -f2-)
  LENGTH=${#DESC}
  if [ "$LENGTH" -gt 80 ]; then
    echo "WARNING: Description length $LENGTH (recommend < 60 chars)"
  else
    echo "✓ Description length acceptable: $LENGTH chars"
  fi
fi

echo "✓ Frontmatter fields valid"
```

### レベル 3: 手動コマンド呼び出し

**テスト対象:**
- コマンドが `/help` に表示されるか
- コマンドがエラーなく実行されるか
- 出力が期待通りか

**テスト手順:**

```bash
# 1. Claude Code を起動
claude --debug

# 2. コマンドがヘルプに表示されるか確認
> /help
# リスト内のコマンドを探す

# 3. 引数なしでコマンドを呼び出す
> /my-command
# 適切なエラーまたは動作を確認

# 4. 有効な引数で呼び出す
> /my-command arg1 arg2
# 期待する動作を確認

# 5. デバッグログを確認
tail -f ~/.claude/debug-logs/latest
# エラーや警告を探す
```

### レベル 4: 引数テスト

**テスト対象:**
- 位置引数が機能するか ($1, $2 など)
- $ARGUMENTS がすべての引数をキャプチャするか
- 引数欠落が適切に処理されるか
- 無効な引数が検出されるか

**テストマトリクス:**

| テストケース | コマンド | 期待結果 |
|-----------|---------|-----------------|
| 引数なし | `/cmd` | 適切な処理またはメッセージ |
| 引数1つ | `/cmd arg1` | $1 が正しく置換される |
| 引数2つ | `/cmd arg1 arg2` | $1 と $2 が置換される |
| 余分な引数 | `/cmd a b c d` | すべてキャプチャまたは適切に無視 |
| 特殊文字 | `/cmd "arg with spaces"` | クォートが正しく処理される |
| 空引数 | `/cmd ""` | 空文字列が処理される |

**テストスクリプト:**

```bash
#!/bin/bash
# test-command-arguments.sh

COMMAND="$1"

echo "Testing argument handling for /$COMMAND"
echo

echo "Test 1: No arguments"
echo "  Command: /$COMMAND"
echo "  Expected: [期待する動作を記述]"
echo "  Manual test required"
echo

echo "Test 2: Single argument"
echo "  Command: /$COMMAND test-value"
echo "  Expected: 'test-value' appears in output"
echo "  Manual test required"
echo

echo "Test 3: Multiple arguments"
echo "  Command: /$COMMAND arg1 arg2 arg3"
echo "  Expected: All arguments used appropriately"
echo "  Manual test required"
echo

echo "Test 4: Special characters"
echo "  Command: /$COMMAND \"value with spaces\""
echo "  Expected: Entire phrase captured"
echo "  Manual test required"
```

### レベル 5: ファイル参照テスト

**テスト対象:**
- @ 構文でファイル内容が読み込まれるか
- 存在しないファイルが処理されるか
- 大きなファイルが適切に処理されるか
- 複数のファイル参照が機能するか

**テスト手順:**

```bash
# テストファイルの作成
echo "Test content" > /tmp/test-file.txt
echo "Second file" > /tmp/test-file-2.txt

# 単一ファイル参照のテスト
> /my-command /tmp/test-file.txt
# ファイル内容が読み込まれることを確認

# 存在しないファイルのテスト
> /my-command /tmp/nonexistent.txt
# 適切なエラーハンドリングを確認

# 複数ファイルのテスト
> /my-command /tmp/test-file.txt /tmp/test-file-2.txt
# 両方のファイルが処理されることを確認

# 大きなファイルのテスト
dd if=/dev/zero of=/tmp/large-file.bin bs=1M count=100
> /my-command /tmp/large-file.bin
# 適切な動作を確認（切り詰めまたは警告の可能性）

# クリーンアップ
rm /tmp/test-file*.txt /tmp/large-file.bin
```

### レベル 6: Bash 実行テスト

**テスト対象:**
- !` コマンドが正しく実行されるか
- コマンド出力がプロンプトに含まれるか
- コマンド失敗が処理されるか
- セキュリティ: 許可されたコマンドのみが実行されるか

**テスト手順:**

```bash
# bash 実行付きテストコマンドの作成
cat > .claude/commands/test-bash.md << 'EOF'
---
description: Test bash execution
allowed-tools: Bash(echo:*), Bash(date:*)
---

Current date: !`date`
Test output: !`echo "Hello from bash"`

Analysis of output above...
EOF

# Claude Code でテスト
> /test-bash
# 確認事項:
# 1. 日付が正しく表示される
# 2. echo 出力が表示される
# 3. デバッグログにエラーがない

# 許可されていないコマンドのテスト（失敗またはブロックされるべき）
cat > .claude/commands/test-forbidden.md << 'EOF'
---
description: Test forbidden command
allowed-tools: Bash(echo:*)
---

Trying forbidden: !`ls -la /`
EOF

> /test-forbidden
# 確認: 権限拒否または適切なエラー
```

### レベル 7: インテグレーションテスト

**テスト対象:**
- コマンドが他のプラグインコンポーネントと連携するか
- コマンド同士が正しく相互作用するか
- 呼び出し間の状態管理が機能するか
- ワークフローコマンドが順番に実行されるか

**テストシナリオ:**

**シナリオ 1: コマンド + フック統合**

```bash
# セットアップ: フックをトリガーするコマンド
# テスト: コマンドを呼び出し、フックが実行されることを確認

# コマンド: .claude/commands/risky-operation.md
# フック: 操作を検証する PreToolUse

> /risky-operation
# 確認: コマンド完了前にフックが実行され検証される
```

**シナリオ 2: コマンドシーケンス**

```bash
# セットアップ: マルチコマンドワークフロー
> /workflow-init
# 確認: 状態ファイルが作成される

> /workflow-step2
# 確認: 状態ファイルが読み込まれ、ステップ 2 が実行される

> /workflow-complete
# 確認: 状態ファイルがクリーンアップされる
```

**シナリオ 3: コマンド + MCP 統合**

```bash
# セットアップ: MCP ツールを使用するコマンド
# テスト: MCP サーバーにアクセスできることを確認

> /mcp-command
# 確認:
# 1. MCP サーバーが起動（stdio の場合）
# 2. ツール呼び出しが成功
# 3. 結果が出力に含まれる
```

## 自動テストアプローチ

### コマンドテストスイート

テストスイートスクリプトの作成:

```bash
#!/bin/bash
# test-commands.sh - コマンドテストスイート

TEST_DIR=".claude/commands"
FAILED_TESTS=0

echo "Command Test Suite"
echo "=================="
echo

for cmd_file in "$TEST_DIR"/*.md; do
  cmd_name=$(basename "$cmd_file" .md)
  echo "Testing: $cmd_name"

  # 構造の検証
  if ./validate-command.sh "$cmd_file"; then
    echo "  ✓ Structure valid"
  else
    echo "  ✗ Structure invalid"
    ((FAILED_TESTS++))
  fi

  # フロントマターの検証
  if ./validate-frontmatter.sh "$cmd_file"; then
    echo "  ✓ Frontmatter valid"
  else
    echo "  ✗ Frontmatter invalid"
    ((FAILED_TESTS++))
  fi

  echo
done

echo "=================="
echo "Tests complete"
echo "Failed: $FAILED_TESTS"

exit $FAILED_TESTS
```

### プリコミットフック

コミット前にコマンドを検証する:

```bash
#!/bin/bash
# .git/hooks/pre-commit

echo "Validating commands..."

COMMANDS_CHANGED=$(git diff --cached --name-only | grep "\.claude/commands/.*\.md")

if [ -z "$COMMANDS_CHANGED" ]; then
  echo "No commands changed"
  exit 0
fi

for cmd in $COMMANDS_CHANGED; do
  echo "Checking: $cmd"

  if ! ./scripts/validate-command.sh "$cmd"; then
    echo "ERROR: Command validation failed: $cmd"
    exit 1
  fi
done

echo "✓ All commands valid"
```

### 継続的テスト

CI/CD でコマンドをテストする:

```yaml
# .github/workflows/test-commands.yml
name: Test Commands

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Validate command structure
        run: |
          for cmd in .claude/commands/*.md; do
            echo "Testing: $cmd"
            ./scripts/validate-command.sh "$cmd"
          done

      - name: Validate frontmatter
        run: |
          for cmd in .claude/commands/*.md; do
            ./scripts/validate-frontmatter.sh "$cmd"
          done

      - name: Check for TODOs
        run: |
          if grep -r "TODO" .claude/commands/; then
            echo "ERROR: TODOs found in commands"
            exit 1
          fi
```

## エッジケーステスト

### エッジケースのテスト

**空引数:**
```bash
> /cmd ""
> /cmd '' ''
```

**特殊文字:**
```bash
> /cmd "arg with spaces"
> /cmd arg-with-dashes
> /cmd arg_with_underscores
> /cmd arg/with/slashes
> /cmd 'arg with "quotes"'
```

**長い引数:**
```bash
> /cmd $(python -c "print('a' * 10000)")
```

**特殊なファイルパス:**
```bash
> /cmd ./file
> /cmd ../file
> /cmd ~/file
> /cmd "/path with spaces/file"
```

**Bash コマンドのエッジケース:**
```markdown
# 失敗する可能性のあるコマンド
!`exit 1`
!`false`
!`command-that-does-not-exist`

# 特殊な出力のコマンド
!`echo ""`
!`cat /dev/null`
!`yes | head -n 1000000`
```

## パフォーマンステスト

### レスポンスタイムテスト

```bash
#!/bin/bash
# test-command-performance.sh

COMMAND="$1"

echo "Testing performance of /$COMMAND"
echo

for i in {1..5}; do
  echo "Run $i:"
  START=$(date +%s%N)

  # コマンドの呼び出し（手動ステップ — 時間を記録）
  echo "  Invoke: /$COMMAND"
  echo "  Start time: $START"
  echo "  (Record end time manually)"
  echo
done

echo "Analyze results:"
echo "  - Average response time"
echo "  - Variance"
echo "  - Acceptable threshold: < 3 seconds for fast commands"
```

### リソース使用量テスト

```bash
# コマンド実行中の Claude Code を監視
# ターミナル 1:
claude --debug

# ターミナル 2:
watch -n 1 'ps aux | grep claude'

# コマンドを実行して観察:
# - メモリ使用量
# - CPU 使用量
# - プロセス数
```

## ユーザーエクスペリエンステスト

### ユーザビリティチェックリスト

- [ ] コマンド名が直感的
- [ ] `/help` の説明が明確
- [ ] 引数がドキュメント化されている
- [ ] エラーメッセージがヘルプフル
- [ ] 出力が読みやすくフォーマットされている
- [ ] 長時間実行コマンドが進捗を表示
- [ ] 結果がアクション可能
- [ ] エッジケースの UX が良好

### ユーザー受け入れテスト

テスターの募集:

```markdown
# ベータテスター向けテストガイド

## コマンド: /my-new-command

### テストシナリオ

1. **基本的な使い方:**
   - 実行: `/my-new-command`
   - 期待: [記述]
   - 明確さを評価: 1-5

2. **引数付き:**
   - 実行: `/my-new-command arg1 arg2`
   - 期待: [記述]
   - 有用性を評価: 1-5

3. **エラーケース:**
   - 実行: `/my-new-command invalid-input`
   - 期待: ヘルプフルなエラーメッセージ
   - エラーメッセージを評価: 1-5

### フィードバック質問

1. コマンドは理解しやすかったですか？
2. 出力は期待通りでしたか？
3. 何を変更しますか？
4. このコマンドを定期的に使いますか？
```

## テストチェックリスト

コマンドをリリースする前に:

### 構造
- [ ] ファイルが正しい場所にある
- [ ] 正しい .md 拡張子
- [ ] 有効な YAML フロントマター（ある場合）
- [ ] Markdown 構文が正しい

### 機能
- [ ] コマンドが `/help` に表示される
- [ ] 説明が明確
- [ ] コマンドがエラーなく実行される
- [ ] 引数が期待通りに機能する
- [ ] ファイル参照が機能する
- [ ] Bash 実行が機能する（使用する場合）

### エッジケース
- [ ] 引数欠落が処理される
- [ ] 無効な引数が検出される
- [ ] 存在しないファイルが処理される
- [ ] 特殊文字が機能する
- [ ] 長い入力が処理される

### 統合
- [ ] 他のコマンドと連携する
- [ ] フックと連携する（該当する場合）
- [ ] MCP と連携する（該当する場合）
- [ ] 状態管理が機能する

### 品質
- [ ] パフォーマンスが許容範囲
- [ ] セキュリティ問題がない
- [ ] エラーメッセージがヘルプフル
- [ ] 出力が適切にフォーマットされている
- [ ] ドキュメントが完全

### 配布
- [ ] 他の人がテスト済み
- [ ] フィードバックを反映
- [ ] README が更新済み
- [ ] 例が提供されている

## 失敗したテストのデバッグ

### よくある問題と解決策

**問題: コマンドが /help に表示されない**

```bash
# ファイルの場所を確認
ls -la .claude/commands/my-command.md

# 権限を確認
chmod 644 .claude/commands/my-command.md

# 構文を確認
head -n 20 .claude/commands/my-command.md

# Claude Code を再起動
claude --debug
```

**問題: 引数が置換されない**

```bash
# 構文を確認
grep '\$1' .claude/commands/my-command.md
grep '\$ARGUMENTS' .claude/commands/my-command.md

# まずシンプルなコマンドでテスト
echo "Test: \$1 and \$2" > .claude/commands/test-args.md
```

**問題: Bash コマンドが実行されない**

```bash
# allowed-tools を確認
grep "allowed-tools" .claude/commands/my-command.md

# コマンド構文を確認
grep '!\`' .claude/commands/my-command.md

# コマンドを手動テスト
date
echo "test"
```

**問題: ファイル参照が機能しない**

```bash
# @ 構文を確認
grep '@' .claude/commands/my-command.md

# ファイルの存在を確認
ls -la /path/to/referenced/file

# 権限を確認
chmod 644 /path/to/referenced/file
```

## ベストプラクティス

1. **早期にテスト、頻繁にテスト**: 開発中にバリデーションする
2. **検証を自動化**: 繰り返し可能なチェックにスクリプトを使用
3. **エッジケースをテスト**: ハッピーパスだけテストしない
4. **フィードバックを得る**: 広く公開する前に他の人にテストしてもらう
5. **テストをドキュメント化**: 回帰テストのためにテストシナリオを保存
6. **本番環境を監視**: リリース後の問題を注視
7. **反復する**: 実際の使用データに基づいて改善
