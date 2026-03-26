---
description: "ユーザー設定でプラグイン設定ファイルを作成する"
allowed-tools: ["Write", "AskUserQuestion"]
---

# プラグイン設定の作成

このコマンドは、ユーザーが `.claude/my-plugin.local.md` 設定ファイルを作成するのを支援します。

## 手順

### ステップ 1: ユーザーの設定を確認する

AskUserQuestion を使って設定を収集します:

```json
{
  "questions": [
    {
      "question": "Enable plugin for this project?",
      "header": "Enable Plugin",
      "multiSelect": false,
      "options": [
        {
          "label": "Yes",
          "description": "Plugin will be active"
        },
        {
          "label": "No",
          "description": "Plugin will be disabled"
        }
      ]
    },
    {
      "question": "Validation mode?",
      "header": "Mode",
      "multiSelect": false,
      "options": [
        {
          "label": "Strict",
          "description": "Maximum validation and security checks"
        },
        {
          "label": "Standard",
          "description": "Balanced validation (recommended)"
        },
        {
          "label": "Lenient",
          "description": "Minimal validation only"
        }
      ]
    }
  ]
}
```

### ステップ 2: 回答を解析する

AskUserQuestion の結果から回答を抽出します:

- answers["0"]: 有効/無効（Yes/No）
- answers["1"]: モード（Strict/Standard/Lenient）

### ステップ 3: 設定ファイルを作成する

Write ツールを使って `.claude/my-plugin.local.md` を作成します:

```markdown
---
enabled: <Yes の場合 true、No の場合 false>
validation_mode: <strict、standard、または lenient>
max_file_size: 1000000
notify_on_errors: true
---

# プラグイン設定

プラグインは <mode> バリデーションモードで設定されています。

設定を変更するには、このファイルを編集して Claude Code を再起動してください。
```

### ステップ 4: ユーザーに通知する

ユーザーに伝える内容:
- `.claude/my-plugin.local.md` に設定ファイルが作成された
- 現在の設定のサマリー
- 必要に応じて手動で編集する方法
- リマインダー: 変更を反映するには Claude Code の再起動が必要
- 設定ファイルは gitignore される（コミットされない）

## 実装上の注意

書き込み前に必ずユーザー入力をバリデーションしてください:
- モードが有効か確認
- 数値フィールドが数値か確認
- パスにディレクトリトラバーサルの試みがないか確認
- フリーテキストフィールドをサニタイズ
