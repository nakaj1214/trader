---
description: 設定済みの hookify ルールを一覧表示する
allowed-tools: ["Glob", "Read", "Skill"]
---

# Hookify ルール一覧

**まず hookify:writing-rules スキルをロード**してルール形式を理解してください。

プロジェクトに設定されているすべての hookify ルールを表示します。

## 手順

1. Glob ツールを使って全ての hookify ルールファイルを検索:
   ```
   pattern: ".claude/hookify.*.local.md"
   ```

2. 見つかった各ファイルに対して:
   - Read ツールでファイルを読み込む
   - フロントマターのフィールドを抽出: name, enabled, event, pattern
   - メッセージのプレビューを抽出（先頭100文字）

3. 結果をテーブルで表示:

```
## 設定済み Hookify ルール

| 名前 | 有効 | イベント | パターン | ファイル |
|------|------|----------|----------|----------|
| warn-dangerous-rm | ✅ はい | bash | rm\s+-rf | hookify.dangerous-rm.local.md |
| warn-console-log | ✅ はい | file | console\.log\( | hookify.console-log.local.md |
| check-tests | ❌ いいえ | stop | .* | hookify.require-tests.local.md |

**合計**: 3 ルール（2 有効、1 無効）
```

4. 各ルールの概要を表示:
```
### warn-dangerous-rm
**イベント**: bash
**パターン**: `rm\s+-rf`
**メッセージ**: "⚠️ **危険な rm コマンドを検出しました！** このコマンドは削除する可能性があります..."

**ステータス**: ✅ アクティブ
**ファイル**: .claude/hookify.dangerous-rm.local.md
```

5. フッターを追加:
```
---

ルールを変更するには: .local.md ファイルを直接編集してください
ルールを無効にするには: フロントマターで `enabled: false` を設定
ルールを有効にするには: フロントマターで `enabled: true` を設定
ルールを削除するには: .local.md ファイルを削除
ルールを作成するには: `/hookify` コマンドを使用

**注意**: 変更は即座に反映されます。再起動は不要です
```

## ルールが見つからない場合

hookify ルールが存在しない場合:

```
## Hookify ルールが設定されていません

まだ hookify ルールを作成していません。

開始するには:
1. `/hookify` を使って会話を分析してルールを作成
2. または `.claude/hookify.my-rule.local.md` ファイルを手動で作成
3. `/hookify:help` でドキュメントを確認

例:
```
/hookify console.log を使ったときに警告して
```

`${CLAUDE_PLUGIN_ROOT}/examples/` でルールファイルの例を確認できます。
```
