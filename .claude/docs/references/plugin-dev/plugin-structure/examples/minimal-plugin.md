# 最小限のプラグインの例

単一コマンドを持つ最もシンプルなプラグインです。

## ディレクトリ構造

```
hello-world/
├── .claude-plugin/
│   └── plugin.json
└── commands/
    └── hello.md
```

## ファイルの内容

### .claude-plugin/plugin.json

```json
{
  "name": "hello-world"
}
```

### commands/hello.md

```markdown
---
name: hello
description: Prints a friendly greeting message
---

# Hello コマンド

ユーザーに親しみのある挨拶を表示します。

## 実装

ユーザーに以下のメッセージを出力します:

> Hello! This is a simple command from the hello-world plugin.
>
> Use this as a starting point for building more complex plugins.

コマンドが正常に実行されたことを示すために、現在のタイムスタンプを挨拶に含めます。
```

## 使い方

プラグインをインストール後:

```
$ claude
> /hello
Hello! This is a simple command from the hello-world plugin.

Use this as a starting point for building more complex plugins.

Executed at: 2025-01-15 14:30:22 UTC
```

## 主なポイント

1. **最小限のマニフェスト**: 必須の `name` フィールドのみ
2. **単一コマンド**: `commands/` ディレクトリに1つの Markdown ファイル
3. **自動検出**: Claude Code がコマンドを自動的に検出
4. **依存関係なし**: スクリプト、フック、外部リソースなし

## このパターンを使用する場面

- クイックプロトタイプ
- 単一目的のユーティリティ
- プラグイン開発の学習
- 特定の機能を持つ内部チームツール

## このプラグインの拡張

より多くの機能を追加するには:

1. **コマンドを追加**: `commands/` に `.md` ファイルを追加
2. **メタデータを追加**: `plugin.json` にバージョン、説明、著者を追加
3. **エージェントを追加**: `agents/` ディレクトリにエージェント定義を作成
4. **フックを追加**: `hooks/hooks.json` でイベント処理を作成
