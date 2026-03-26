# Claude Codeプラグインのフック開発

## 概要

フックはClaude Codeのイベントに応答して実行されるイベント駆動の自動化スクリプトです。フックを使用して、操作の検証、ポリシーの強制、コンテキストの追加、外部ツールのワークフローへの統合を行います。

**主要機能:**
- 実行前のツール呼び出しの検証（PreToolUse）
- ツール結果への反応（PostToolUse）
- 完了基準の強制（Stop、SubagentStop）
- プロジェクトコンテキストのロード（SessionStart）
- 開発ライフサイクル全体のワークフロー自動化

## フックの種類

### プロンプトベースのフック（推奨）

コンテキスト対応の検証のためにLLM駆動の意思決定を使用する:

```json
{
  "type": "prompt",
  "prompt": "このツール使用が適切かどうかを評価する: $TOOL_INPUT",
  "timeout": 30
}
```

**対応イベント:** Stop、SubagentStop、UserPromptSubmit、PreToolUse

**メリット:**
- 自然言語推論に基づくコンテキスト対応の決定
- bashスクリプトなしの柔軟な評価ロジック
- エッジケースの処理が容易
- 維持・拡張が容易

### コマンドフック

決定論的チェックのためにbashコマンドを実行する:

```json
{
  "type": "command",
  "command": "bash ${CLAUDE_PLUGIN_ROOT}/scripts/validate.sh",
  "timeout": 60
}
```

**用途:**
- 高速な決定論的検証
- ファイルシステム操作
- 外部ツールの統合
- パフォーマンスが重要なチェック

## フック設定フォーマット

### プラグインのhooks.jsonフォーマット

`hooks/hooks.json`の**プラグインフック**には、ラッパーフォーマットを使用する:

```json
{
  "description": "フックの簡単な説明（オプション）",
  "hooks": {
    "PreToolUse": [...],
    "Stop": [...],
    "SessionStart": [...]
  }
}
```

**重要なポイント:**
- `description`フィールドはオプション
- `hooks`フィールドは実際のフックイベントを含む必須ラッパー
- これは**プラグイン固有のフォーマット**

**例:**
```json
{
  "description": "コード品質のための検証フック",
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/validate.sh"
          }
        ]
      }
    ]
  }
}
```

### 設定フォーマット（直接）

`.claude/settings.json`の**ユーザー設定**には、直接フォーマットを使用する:

```json
{
  "PreToolUse": [...],
  "Stop": [...],
  "SessionStart": [...]
}
```

**重要なポイント:**
- ラッパーなし — イベントをトップレベルに直接記述
- descriptionフィールドなし
- これは**設定フォーマット**

## フックイベント

### PreToolUse

ツールが実行される前に実行される。ツール呼び出しの承認、拒否、または変更に使用する。

**例（プロンプトベース）:**
```json
{
  "PreToolUse": [
    {
      "matcher": "Write|Edit",
      "hooks": [
        {
          "type": "prompt",
          "prompt": "ファイル書き込みの安全性を検証する。確認事項: システムパス、認証情報、パストラバーサル、センシティブなコンテンツ。'approve'または'deny'を返す。"
        }
      ]
    }
  ]
}
```

**PreToolUseの出力:**
```json
{
  "hookSpecificOutput": {
    "permissionDecision": "allow|deny|ask",
    "updatedInput": {"field": "modified_value"}
  },
  "systemMessage": "Claudeへの説明"
}
```

### PostToolUse

ツールが完了した後に実行される。結果への反応、フィードバックの提供、ログ記録に使用する。

**例:**
```json
{
  "PostToolUse": [
    {
      "matcher": "Edit",
      "hooks": [
        {
          "type": "prompt",
          "prompt": "編集結果の潜在的な問題を分析する: 構文エラー、セキュリティ脆弱性、破壊的変更。フィードバックを提供する。"
        }
      ]
    }
  ]
}
```

**出力の動作:**
- Exit 0: stdoutがトランスクリプトに表示
- Exit 2: stderrがClaudeにフィードバック
- systemMessageがコンテキストに含まれる

### Stop

メインエージェントが停止を検討する時に実行される。完了の検証に使用する。

**例:**
```json
{
  "Stop": [
    {
      "matcher": "*",
      "hooks": [
        {
          "type": "prompt",
          "prompt": "タスクの完了を確認する: テスト実行、ビルド成功、質問への回答。停止する場合は'approve'を、続けるべき理由とともに'block'を返す。"
        }
      ]
    }
  ]
}
```

**決定の出力:**
```json
{
  "decision": "approve|block",
  "reason": "説明",
  "systemMessage": "追加のコンテキスト"
}
```

### SubagentStop

サブエージェントが停止を検討する時に実行される。Stopフックと同様だが、サブエージェント用。

### UserPromptSubmit

ユーザーがプロンプトを送信する時に実行される。コンテキストの追加、検証、またはプロンプトのブロックに使用する。

**例:**
```json
{
  "UserPromptSubmit": [
    {
      "matcher": "*",
      "hooks": [
        {
          "type": "prompt",
          "prompt": "プロンプトにセキュリティガイダンスが必要かチェックする。認証、権限、またはAPIセキュリティについて議論している場合は、関連する警告を返す。"
        }
      ]
    }
  ]
}
```

### SessionStart

Claude Codeセッションが開始する時に実行される。コンテキストのロードと環境の設定に使用する。

**例:**
```json
{
  "SessionStart": [
    {
      "matcher": "*",
      "hooks": [
        {
          "type": "command",
          "command": "bash ${CLAUDE_PLUGIN_ROOT}/scripts/load-context.sh"
        }
      ]
    }
  ]
}
```

**特別な機能:** `$CLAUDE_ENV_FILE`を使用して環境変数を永続化:
```bash
echo "export PROJECT_TYPE=nodejs" >> "$CLAUDE_ENV_FILE"
```

完全な例は`examples/load-context.sh`を参照。

### SessionEnd

セッションが終了する時に実行される。クリーンアップ、ログ、状態の保存に使用する。

### PreCompact

コンテキストの圧縮前に実行される。保存すべき重要な情報を追加するために使用する。

### Notification

Claudeが通知を送る時に実行される。ユーザー通知への反応に使用する。

## フック出力フォーマット

### 標準出力（全フック）

```json
{
  "continue": true,
  "suppressOutput": false,
  "systemMessage": "Claudeへのメッセージ"
}
```

- `continue`: falseの場合、処理を停止（デフォルトtrue）
- `suppressOutput`: トランスクリプトから出力を非表示（デフォルトfalse）
- `systemMessage`: Claudeに表示されるメッセージ

### 終了コード

- `0` - 成功（stdoutがトランスクリプトに表示）
- `2` - ブロッキングエラー（stderrがClaudeにフィードバック）
- その他 - 非ブロッキングエラー

## フック入力フォーマット

全フックは共通フィールドを持つJSONをstdinで受け取る:

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.txt",
  "cwd": "/current/working/dir",
  "permission_mode": "ask|allow",
  "hook_event_name": "PreToolUse"
}
```

**イベント固有のフィールド:**

- **PreToolUse/PostToolUse:** `tool_name`、`tool_input`、`tool_result`
- **UserPromptSubmit:** `user_prompt`
- **Stop/SubagentStop:** `reason`

プロンプトでフィールドにアクセスするには`$TOOL_INPUT`、`$TOOL_RESULT`、`$USER_PROMPT`などを使用。

## 環境変数

全コマンドフックで利用可能:

- `$CLAUDE_PROJECT_DIR` - プロジェクトルートパス
- `$CLAUDE_PLUGIN_ROOT` - プラグインディレクトリ（ポータブルなパス用に使用）
- `$CLAUDE_ENV_FILE` - SessionStartのみ: 環境変数をここに永続化
- `$CLAUDE_CODE_REMOTE` - リモートコンテキストで実行中の場合に設定

**ポータビリティのためにフックコマンドで常に${CLAUDE_PLUGIN_ROOT}を使用する:**

```json
{
  "type": "command",
  "command": "bash ${CLAUDE_PLUGIN_ROOT}/scripts/validate.sh"
}
```

## プラグインフック設定

プラグインでは`hooks/hooks.json`でフックを定義する:

```json
{
  "PreToolUse": [
    {
      "matcher": "Write|Edit",
      "hooks": [
        {
          "type": "prompt",
          "prompt": "ファイル書き込みの安全性を検証する"
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
          "prompt": "タスクの完了を確認する"
        }
      ]
    }
  ],
  "SessionStart": [
    {
      "matcher": "*",
      "hooks": [
        {
          "type": "command",
          "command": "bash ${CLAUDE_PLUGIN_ROOT}/scripts/load-context.sh",
          "timeout": 10
        }
      ]
    }
  ]
}
```

プラグインフックはユーザーのフックとマージされ、並行して実行される。

## マッチャー

### ツール名のマッチング

**完全一致:**
```json
"matcher": "Write"
```

**複数のツール:**
```json
"matcher": "Read|Write|Edit"
```

**ワイルドカード（全ツール）:**
```json
"matcher": "*"
```

**正規表現パターン:**
```json
"matcher": "mcp__.*__delete.*"  // 全MCPのdeleteツール
```

**注意:** マッチャーは大文字小文字を区別する。

## セキュリティのベストプラクティス

### 入力バリデーション

コマンドフックでは常に入力を検証する:

```bash
#!/bin/bash
set -euo pipefail

input=$(cat)
tool_name=$(echo "$input" | jq -r '.tool_name')

# ツール名フォーマットを検証
if [[ ! "$tool_name" =~ ^[a-zA-Z0-9_]+$ ]]; then
  echo '{"decision": "deny", "reason": "無効なツール名"}' >&2
  exit 2
fi
```

### パスの安全性

パストラバーサルとセンシティブなファイルを確認する:

```bash
file_path=$(echo "$input" | jq -r '.tool_input.file_path')

# パストラバーサルを拒否
if [[ "$file_path" == *".."* ]]; then
  echo '{"decision": "deny", "reason": "パストラバーサルを検出"}' >&2
  exit 2
fi

# センシティブなファイルを拒否
if [[ "$file_path" == *".env"* ]]; then
  echo '{"decision": "deny", "reason": "センシティブなファイル"}' >&2
  exit 2
fi
```

完全な例は`examples/validate-write.sh`と`examples/validate-bash.sh`を参照。

### 全変数を引用符で囲む

```bash
# 良い: 引用符あり
echo "$file_path"
cd "$CLAUDE_PROJECT_DIR"

# 悪い: 引用符なし（インジェクションリスク）
echo $file_path
cd $CLAUDE_PROJECT_DIR
```

### 適切なタイムアウトを設定する

```json
{
  "type": "command",
  "command": "bash script.sh",
  "timeout": 10
}
```

**デフォルト:** コマンドフック（60秒）、プロンプトフック（30秒）

## パフォーマンスの考慮事項

### 並行実行

マッチングした全フックは**並行して**実行される:

```json
{
  "PreToolUse": [
    {
      "matcher": "Write",
      "hooks": [
        {"type": "command", "command": "check1.sh"},  // 並行
        {"type": "command", "command": "check2.sh"},  // 並行
        {"type": "prompt", "prompt": "検証する..."}   // 並行
      ]
    }
  ]
}
```

**設計上の意味:**
- フックはお互いの出力を見ない
- 非決定論的な順序
- 独立性を前提に設計する

### 最適化

1. 高速な決定論的チェックにはコマンドフックを使用
2. 複雑な推論にはプロンプトフックを使用
3. 一時ファイルに検証結果をキャッシュ
4. ホットパスでのI/Oを最小化

## 一時的にアクティブなフック

フラグファイルまたは設定を確認することで条件付きでアクティブになるフックを作成する:

**パターン: フラグファイルによるアクティベーション**
```bash
#!/bin/bash
# フラグファイルが存在する時のみアクティブ
FLAG_FILE="$CLAUDE_PROJECT_DIR/.enable-strict-validation"

if [ ! -f "$FLAG_FILE" ]; then
  # フラグなし、検証をスキップ
  exit 0
fi

# フラグあり、検証を実行
input=$(cat)
# ... 検証ロジック ...
```

**パターン: 設定ベースのアクティベーション**
```bash
#!/bin/bash
# アクティベーションのために設定を確認
CONFIG_FILE="$CLAUDE_PROJECT_DIR/.claude/plugin-config.json"

if [ -f "$CONFIG_FILE" ]; then
  enabled=$(jq -r '.strictMode // false' "$CONFIG_FILE")
  if [ "$enabled" != "true" ]; then
    exit 0  # 有効でない、スキップ
  fi
fi

# 有効、フックロジックを実行
input=$(cat)
# ... フックロジック ...
```

## フックのライフサイクルと制限

### フックはセッション開始時にロードされる

**重要:** フックはClaude Codeセッション開始時にロードされる。フック設定の変更はClaude Codeの再起動が必要。

**フックをホットスワップできない:**
- `hooks/hooks.json`の編集は現在のセッションに影響しない
- 新しいフックスクリプトは認識されない
- フックコマンド/プロンプトの変更は更新されない
- Claude Codeを再起動する必要がある: 終了して`claude`を再実行

**フック変更のテスト:**
1. フック設定またはスクリプトを編集する
2. Claude Codeセッションを終了する
3. 再起動: `claude`または`cc`
4. 新しいフック設定がロードされる
5. `claude --debug`でフックをテストする

## フックのデバッグ

### デバッグモードを有効にする

```bash
claude --debug
```

フック登録、実行ログ、入出力JSON、タイミング情報を確認する。

### フックスクリプトをテストする

コマンドフックを直接テストする:

```bash
echo '{"tool_name": "Write", "tool_input": {"file_path": "/test"}}' | \
  bash ${CLAUDE_PLUGIN_ROOT}/scripts/validate.sh

echo "終了コード: $?"
```

### JSON出力を検証する

フックが有効なJSONを出力することを確認する:

```bash
output=$(./your-hook.sh < test-input.json)
echo "$output" | jq .
```

## クイックリファレンス

### フックイベントのまとめ

| イベント | タイミング | 用途 |
|-------|------|---------|
| PreToolUse | ツール前 | 検証、変更 |
| PostToolUse | ツール後 | フィードバック、ログ |
| UserPromptSubmit | ユーザー入力 | コンテキスト、検証 |
| Stop | エージェント停止 | 完了チェック |
| SubagentStop | サブエージェント完了 | タスク検証 |
| SessionStart | セッション開始 | コンテキストロード |
| SessionEnd | セッション終了 | クリーンアップ、ログ |
| PreCompact | 圧縮前 | コンテキスト保存 |
| Notification | ユーザー通知 | ログ、反応 |

### ベストプラクティス

**すること:**
- ✅ 複雑なロジックにはプロンプトベースのフックを使用
- ✅ ポータビリティのために${CLAUDE_PLUGIN_ROOT}を使用
- ✅ コマンドフックで全入力を検証
- ✅ 全bash変数を引用符で囲む
- ✅ 適切なタイムアウトを設定
- ✅ 構造化されたJSON出力を返す
- ✅ フックを徹底的にテストする

**しないこと:**
- ❌ ハードコードされたパスを使用する
- ❌ ユーザー入力を検証なしで信頼する
- ❌ 長時間実行のフックを作成する
- ❌ フックの実行順序に依存する
- ❌ グローバル状態を予測不可能に変更する
- ❌ センシティブな情報をログに記録する

## 追加リソース

### リファレンスファイル

詳細なパターンと高度なテクニックについては以下を参照:

- **`references/patterns.md`** - 一般的なフックパターン（8以上の実績あるパターン）
- **`references/migration.md`** - 基本フックから高度なフックへの移行
- **`references/advanced.md`** - 高度なユースケースとテクニック

### サンプルフックスクリプト

`examples/`内の動作例:

- **`validate-write.sh`** - ファイル書き込み検証の例
- **`validate-bash.sh`** - Bashコマンド検証の例
- **`load-context.sh`** - SessionStartコンテキストロードの例

### ユーティリティスクリプト

`scripts/`内の開発ツール:

- **`validate-hook-schema.sh`** - hooks.jsonの構造と構文を検証
- **`test-hook.sh`** - デプロイ前にサンプル入力でフックをテスト
- **`hook-linter.sh`** - フックスクリプトの一般的な問題とベストプラクティスをチェック

## 実装ワークフロー

プラグインにフックを実装するには:

1. フックするイベントを特定する（PreToolUse、Stop、SessionStartなど）
2. プロンプトベース（柔軟）またはコマンド（決定論的）フックを決定する
3. `hooks/hooks.json`にフック設定を書く
4. コマンドフックの場合はフックスクリプトを作成する
5. 全ファイル参照に${CLAUDE_PLUGIN_ROOT}を使用する
6. `scripts/validate-hook-schema.sh hooks/hooks.json`で設定を検証する
7. デプロイ前に`scripts/test-hook.sh`でフックをテストする
8. `claude --debug`でClaude Codeでテストする
9. プラグインREADMEにフックを文書化する

ほとんどのユースケースにはプロンプトベースのフックに集中する。パフォーマンスが重要または決定論的なチェックのためにコマンドフックを予約する。
