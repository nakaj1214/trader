---
description: hookify ルールをインタラクティブに有効化/無効化する
allowed-tools: ["Glob", "Read", "Edit", "AskUserQuestion", "Skill"]
---

# Hookify ルールの設定

**まず hookify:writing-rules スキルをロードして**ルールの形式を理解する。

インタラクティブなインターフェースを使って既存の hookify ルールを有効化/無効化する。

## ステップ

### 1. 既存ルールの検索

Glob ツールを使ってすべての hookify ルールファイルを検索する:
```
pattern: ".claude/hookify.*.local.md"
```

ルールが見つからない場合、ユーザーに通知する:
```
hookify ルールはまだ設定されていません。`/hookify` を使って最初のルールを作成してください。
```

### 2. 現在の状態を読み取る

各ルールファイルに対して:
- ファイルを読み取る
- フロントマターから `name` と `enabled` フィールドを抽出する
- 現在の状態付きのルールリストを構築する

### 3. 切り替えるルールをユーザーに選択してもらう

AskUserQuestion を使ってユーザーにルールを選択させる:

```json
{
  "questions": [
    {
      "question": "Which rules would you like to enable or disable?",
      "header": "Configure",
      "multiSelect": true,
      "options": [
        {
          "label": "warn-dangerous-rm (currently enabled)",
          "description": "Warns about rm -rf commands"
        },
        {
          "label": "warn-console-log (currently disabled)",
          "description": "Warns about console.log in code"
        },
        {
          "label": "require-tests (currently enabled)",
          "description": "Requires tests before stopping"
        }
      ]
    }
  ]
}
```

**オプションの形式:**
- ラベル: `{rule-name} (currently {enabled|disabled})`
- 説明: ルールの message または pattern からの簡潔な説明

### 4. ユーザー選択の解析

選択された各ルールに対して:
- ラベルから現在の状態を判定する（enabled/disabled）
- 状態を切り替える: enabled → disabled、disabled → enabled

### 5. ルールファイルの更新

切り替える各ルールに対して:
- Read ツールで現在の内容を読み取る
- Edit ツールで `enabled: true` を `enabled: false` に変更する（またはその逆）
- 引用符の有無両方に対応する

**有効化の編集パターン:**
```
old_string: "enabled: false"
new_string: "enabled: true"
```

**無効化の編集パターン:**
```
old_string: "enabled: true"
new_string: "enabled: false"
```

### 6. 変更の確認

ユーザーに変更内容を表示する:

```
## Hookify ルール更新完了

**有効化:**
- warn-console-log

**無効化:**
- warn-dangerous-rm

**変更なし:**
- require-tests

変更はすぐに適用されます - 再起動は不要
```

## 重要な注意事項

- 変更は次のツール使用時からすぐに有効になる
- .claude/hookify.*.local.md ファイルを手動で編集することもできる
- ルールを完全に削除するには、.local.md ファイルを削除する
- 設定済みのすべてのルールを確認するには `/hookify:list` を使用する

## エッジケース

**設定するルールがない場合:**
- `/hookify` を使ってルールを作成するようメッセージを表示する

**ユーザーがルールを選択しなかった場合:**
- 変更が行われなかったことを通知する

**ファイルの読み取り/書き込みエラー:**
- 具体的なエラーをユーザーに通知する
- フォールバックとして手動編集を提案する
