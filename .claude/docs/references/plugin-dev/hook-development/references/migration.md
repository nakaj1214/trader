# 基本フックから高度なフックへの移行

このガイドでは、基本的なコマンドフックから高度なプロンプトベースのフックに移行して、保守性と柔軟性を向上させる方法を説明します。

## なぜ移行するのか？

プロンプトベースのフックにはいくつかの利点があります:

- **自然言語による推論**: LLM がコンテキストと意図を理解する
- **エッジケースへの対応力向上**: 予期しないシナリオに適応する
- **bash スクリプティング不要**: 記述と保守がシンプル
- **より柔軟なバリデーション**: コーディングなしで複雑なロジックを処理できる

## 移行例: Bash コマンドのバリデーション

### 移行前（基本コマンドフック）

**設定:**
```json
{
  "PreToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "command",
          "command": "bash validate-bash.sh"
        }
      ]
    }
  ]
}
```

**スクリプト (validate-bash.sh):**
```bash
#!/bin/bash
input=$(cat)
command=$(echo "$input" | jq -r '.tool_input.command')

# Hard-coded validation logic
if [[ "$command" == *"rm -rf"* ]]; then
  echo "Dangerous command detected" >&2
  exit 2
fi
```

**問題点:**
- 正確な "rm -rf" パターンのみチェック
- `rm -fr` や `rm -r -f` のようなバリエーションを検出できない
- 他の危険なコマンド（`dd`、`mkfs` など）を見逃す
- コンテキスト認識がない
- bash スクリプティングの知識が必要

### 移行後（高度なプロンプトフック）

**設定:**
```json
{
  "PreToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "prompt",
          "prompt": "Command: $TOOL_INPUT.command. Analyze for: 1) Destructive operations (rm -rf, dd, mkfs, etc) 2) Privilege escalation (sudo) 3) Network operations without user consent. Return 'approve' or 'deny' with explanation.",
          "timeout": 15
        }
      ]
    }
  ]
}
```

**利点:**
- すべてのバリエーションとパターンを検出
- 文字列のリテラルではなく意図を理解
- スクリプトファイルが不要
- 新しい基準の追加が容易
- コンテキストに基づいた判断
- 拒否時に自然言語で説明

## 移行例: ファイル書き込みのバリデーション

### 移行前（基本コマンドフック）

**設定:**
```json
{
  "PreToolUse": [
    {
      "matcher": "Write",
      "hooks": [
        {
          "type": "command",
          "command": "bash validate-write.sh"
        }
      ]
    }
  ]
}
```

**スクリプト (validate-write.sh):**
```bash
#!/bin/bash
input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path')

# Check for path traversal
if [[ "$file_path" == *".."* ]]; then
  echo '{"decision": "deny", "reason": "Path traversal detected"}' >&2
  exit 2
fi

# Check for system paths
if [[ "$file_path" == "/etc/"* ]] || [[ "$file_path" == "/sys/"* ]]; then
  echo '{"decision": "deny", "reason": "System file"}' >&2
  exit 2
fi
```

**問題点:**
- ハードコードされたパスパターン
- シンボリックリンクを理解しない
- エッジケースの欠落（例: `/etc` と `/etc/`）
- ファイル内容の考慮なし

### 移行後（高度なプロンプトフック）

**設定:**
```json
{
  "PreToolUse": [
    {
      "matcher": "Write|Edit",
      "hooks": [
        {
          "type": "prompt",
          "prompt": "File path: $TOOL_INPUT.file_path. Content preview: $TOOL_INPUT.content (first 200 chars). Verify: 1) Not system directories (/etc, /sys, /usr) 2) Not credentials (.env, tokens, secrets) 3) No path traversal 4) Content doesn't expose secrets. Return 'approve' or 'deny'."
        }
      ]
    }
  ]
}
```

**利点:**
- コンテキスト認識（内容も考慮）
- シンボリックリンクやエッジケースに対応
- 「システムディレクトリ」を自然に理解
- 内容内のシークレットを検出可能
- 基準の拡張が容易

## コマンドフックを維持すべき場面

コマンドフックにもまだ適切な用途があります:

### 1. 決定論的なパフォーマンスチェック

```bash
#!/bin/bash
# Check file size quickly
file_path=$(echo "$input" | jq -r '.tool_input.file_path')
size=$(stat -f%z "$file_path" 2>/dev/null || stat -c%s "$file_path" 2>/dev/null)

if [ "$size" -gt 10000000 ]; then
  echo '{"decision": "deny", "reason": "File too large"}' >&2
  exit 2
fi
```

**コマンドフックを使う場面:** バリデーションが純粋に数学的または決定論的な場合。

### 2. 外部ツールとの統合

```bash
#!/bin/bash
# Run security scanner
file_path=$(echo "$input" | jq -r '.tool_input.file_path')
scan_result=$(security-scanner "$file_path")

if [ "$?" -ne 0 ]; then
  echo "Security scan failed: $scan_result" >&2
  exit 2
fi
```

**コマンドフックを使う場面:** はい/いいえの回答を提供する外部ツールと統合する場合。

### 3. 非常に高速なチェック（50ms 未満）

```bash
#!/bin/bash
# Quick regex check
command=$(echo "$input" | jq -r '.tool_input.command')

if [[ "$command" =~ ^(ls|pwd|echo)$ ]]; then
  exit 0  # Safe commands
fi
```

**コマンドフックを使う場面:** パフォーマンスが重要でロジックがシンプルな場合。

## ハイブリッドアプローチ

多段階バリデーションのために両方を組み合わせます:

```json
{
  "PreToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "command",
          "command": "bash ${CLAUDE_PLUGIN_ROOT}/scripts/quick-check.sh",
          "timeout": 5
        },
        {
          "type": "prompt",
          "prompt": "Deep analysis of bash command: $TOOL_INPUT",
          "timeout": 15
        }
      ]
    }
  ]
}
```

コマンドフックが高速な決定論的チェックを行い、プロンプトフックが複雑な推論を処理します。

## 移行チェックリスト

フックを移行する際:

- [ ] コマンドフック内のバリデーションロジックを特定する
- [ ] ハードコードされたパターンを自然言語の基準に変換する
- [ ] 古いフックで見逃していたエッジケースでテストする
- [ ] LLM が意図を理解していることを確認する
- [ ] 適切なタイムアウトを設定する（プロンプトフックでは通常 15〜30 秒）
- [ ] 新しいフックを README に文書化する
- [ ] 古いスクリプトファイルを削除またはアーカイブする

## 移行のコツ

1. **1つのフックから始める**: すべてを一度に移行しない
2. **徹底的にテストする**: プロンプトフックがコマンドフックで検出していたものを検出するか確認する
3. **改善を探す**: 移行をバリデーション強化の機会として活用する
4. **参照用にスクリプトを保持する**: ロジックを参照する必要がある場合に備えて古いスクリプトをアーカイブする
5. **理由を文書化する**: プロンプトフックの方が優れている理由を README で説明する

## 完全な移行例

### 元のプラグイン構造

```
my-plugin/
├── .claude-plugin/plugin.json
├── hooks/hooks.json
└── scripts/
    ├── validate-bash.sh
    ├── validate-write.sh
    └── check-tests.sh
```

### 移行後

```
my-plugin/
├── .claude-plugin/plugin.json
├── hooks/hooks.json      # Now uses prompt hooks
└── scripts/              # Archive or delete
    └── archive/
        ├── validate-bash.sh
        ├── validate-write.sh
        └── check-tests.sh
```

### 更新された hooks.json

```json
{
  "PreToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "prompt",
          "prompt": "Validate bash command safety: destructive ops, privilege escalation, network access"
        }
      ]
    },
    {
      "matcher": "Write|Edit",
      "hooks": [
        {
          "type": "prompt",
          "prompt": "Validate file write safety: system paths, credentials, path traversal, content secrets"
        }
      ]
    }
  ],
  "Stop": [
    {
      "matcher": "*",
      "hooks": [
        {
          "type": "prompt",
          "prompt": "Verify tests were run if code was modified"
        }
      ]
    }
  ]
}
```

**結果:** よりシンプルで、より保守しやすく、より強力。

## よくある移行パターン

### パターン: 文字列含有チェック → 自然言語

**移行前:**
```bash
if [[ "$command" == *"sudo"* ]]; then
  echo "Privilege escalation" >&2
  exit 2
fi
```

**移行後:**
```
"Check for privilege escalation (sudo, su, etc)"
```

### パターン: 正規表現 → 意図

**移行前:**
```bash
if [[ "$file" =~ \.(env|secret|key|token)$ ]]; then
  echo "Credential file" >&2
  exit 2
fi
```

**移行後:**
```
"Verify not writing to credential files (.env, secrets, keys, tokens)"
```

### パターン: 複数条件 → 基準リスト

**移行前:**
```bash
if [ condition1 ] || [ condition2 ] || [ condition3 ]; then
  echo "Invalid" >&2
  exit 2
fi
```

**移行後:**
```
"Check: 1) condition1 2) condition2 3) condition3. Deny if any fail."
```

## まとめ

プロンプトベースのフックへの移行により、プラグインはより保守しやすく、柔軟で、強力になります。コマンドフックは決定論的なチェックと外部ツール統合のために残しておきましょう。
