---
description: hookify プラグインのヘルプを表示する
allowed-tools: ["Read"]
---

# Hookify プラグインヘルプ

hookify プラグインの仕組みと使い方を説明する。

## 概要

hookify プラグインは、望ましくない動作を防止するカスタムフックを簡単に作成できるようにする。`hooks.json` ファイルを編集する代わりに、監視するパターンを定義するシンプルな Markdown 設定ファイルを作成する。

## 仕組み

### 1. フックシステム

Hookify は以下のイベントで実行される汎用フックをインストールする:
- **PreToolUse**: ツール実行前（Bash、Edit、Write など）
- **PostToolUse**: ツール実行後
- **Stop**: Claude が作業を停止しようとするとき
- **UserPromptSubmit**: ユーザーがプロンプトを送信するとき

これらのフックは `.claude/hookify.*.local.md` の設定ファイルを読み取り、現在の操作に一致するルールがあるかチェックする。

### 2. 設定ファイル

ユーザーは `.claude/hookify.{rule-name}.local.md` ファイルでルールを作成する:

```markdown
---
name: warn-dangerous-rm
enabled: true
event: bash
pattern: rm\s+-rf
---

⚠️ **危険な rm コマンドを検出しました！**

このコマンドは重要なファイルを削除する可能性があります。パスを確認してください。
```

**主要フィールド:**
- `name`: ルールの一意な識別子
- `enabled`: true/false で有効化/無効化
- `event`: bash、file、stop、prompt、または all
- `pattern`: マッチさせる正規表現パターン

メッセージ本文は、ルールがトリガーされたときに Claude に表示される内容。

### 3. ルールの作成

**オプション A: /hookify コマンドを使用する**
```
/hookify Don't use console.log in production files
```

リクエストを分析し、適切なルールファイルを作成する。

**オプション B: 手動で作成する**
上記の形式で `.claude/hookify.my-rule.local.md` を作成する。

**オプション C: 会話を分析する**
```
/hookify
```

引数なしの場合、hookify は最近の会話を分析して防止したい動作を見つける。

## 利用可能なコマンド

- **`/hookify`** - 会話分析または明示的な指示からフックを作成する
- **`/hookify:help`** - このヘルプを表示する（今読んでいるもの）
- **`/hookify:list`** - 設定済みの全フックを一覧表示する
- **`/hookify:configure`** - 既存のフックをインタラクティブに有効化/無効化する

## ユースケース例

**危険なコマンドを防止する:**
```markdown
---
name: block-chmod-777
enabled: true
event: bash
pattern: chmod\s+777
---

chmod 777 は使わないでください。セキュリティリスクです。具体的なパーミッションを使用してください。
```

**デバッグコードについて警告する:**
```markdown
---
name: warn-console-log
enabled: true
event: file
pattern: console\.log\(
---

console.log を検出しました。コミット前にデバッグログを削除することを忘れないでください。
```

**停止前にテストを要求する:**
```markdown
---
name: require-tests
enabled: true
event: stop
pattern: .*
---

終了する前にテストを実行しましたか？`npm test` または同等のコマンドが実行されたことを確認してください。
```

## パターン構文

Python の正規表現構文を使用する:
- `\s` - 空白文字
- `\.` - リテラルのドット
- `|` - OR
- `+` - 1回以上
- `*` - 0回以上
- `\d` - 数字
- `[abc]` - 文字クラス

**例:**
- `rm\s+-rf` - "rm -rf" にマッチ
- `console\.log\(` - "console.log(" にマッチ
- `(eval|exec)\(` - "eval(" または "exec(" にマッチ
- `\.env$` - .env で終わるファイルにマッチ

## 重要な注意事項

**再起動不要**: Hookify ルール（`.local.md` ファイル）は次のツール使用時からすぐに有効になる。hookify フックは既にロードされており、ルールを動的に読み取る。

**ブロックまたは警告**: ルールは操作を `block`（実行を防止）するか `warn`（メッセージを表示するが許可）することができる。ルールのフロントマターで `action: block` または `action: warn` を設定する。

**ルールファイル**: ルールは `.claude/hookify.*.local.md` に保管する。git で無視すべき（必要に応じて .gitignore に追加）。

**ルールの無効化**: フロントマターで `enabled: false` に設定するか、ファイルを削除する。

## トラブルシューティング

**フックがトリガーされない場合:**
- ルールファイルが `.claude/` ディレクトリにあるか確認する
- フロントマターで `enabled: true` になっているか確認する
- パターンが有効な正規表現であることを確認する
- パターンをテストする: `python3 -c "import re; print(re.search('your_pattern', 'test_text'))"`
- ルールはすぐに有効になる - 再起動不要

**インポートエラー:**
- Python 3 が利用可能か確認する: `python3 --version`
- hookify プラグインが正しくインストールされているか確認する

**パターンがマッチしない場合:**
- 正規表現を単独でテストする
- エスケープの問題を確認する（YAML ではクォートなしのパターンを使用）
- まずシンプルなパターンを試してから精緻化する

## はじめに

1. 最初のルールを作成する:
   ```
   /hookify Warn me when I try to use rm -rf
   ```

2. トリガーを試す:
   - Claude に `rm -rf /tmp/test` の実行を依頼する
   - 警告が表示されるはず

4. `.claude/hookify.warn-rm.local.md` を編集してルールを精緻化する

5. 望ましくない動作に遭遇するたびにルールを追加する

その他の例については、`${CLAUDE_PLUGIN_ROOT}/examples/` ディレクトリを参照。
