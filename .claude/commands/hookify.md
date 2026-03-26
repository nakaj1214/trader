---
description: 会話分析または明示的な指示から、望ましくない動作を防止するフックを作成する
argument-hint: 対処する特定の動作（任意）
allowed-tools: ["Read", "Write", "AskUserQuestion", "Task", "Grep", "TodoWrite", "Skill"]
---

# Hookify - 望ましくない動作からフックを作成

**まず: Skill ツールを使って hookify:writing-rules スキルをロード**し、ルールファイルの形式と構文を理解してください。

会話の分析やユーザーの明示的な指示に基づいて、問題のある動作を防止するフックルールを作成します。

## タスク

望ましくない動作を防止する hookify ルールの作成をサポートします。以下の手順に従ってください:

### ステップ 1: 動作情報の収集

**$ARGUMENTS が指定されている場合:**
- ユーザーが具体的な指示を提供: `$ARGUMENTS`
- 追加のコンテキストのため、最近の会話（直近10〜15件のユーザーメッセージ）も分析する
- その動作が発生している例を探す

**$ARGUMENTS が空の場合:**
- conversation-analyzer エージェントを起動して問題のある動作を検出
- エージェントがユーザーのプロンプトからフラストレーションの兆候をスキャン
- エージェントが構造化された結果を返す

**会話を分析するには:**
Task ツールを使って conversation-analyzer エージェントを起動:
```
{
  "subagent_type": "general-purpose",
  "description": "Analyze conversation for unwanted behaviors",
  "prompt": "You are analyzing a Claude Code conversation to find behaviors the user wants to prevent.

Read user messages in the current conversation and identify:
1. Explicit requests to avoid something (\"don't do X\", \"stop doing Y\")
2. Corrections or reversions (user fixing Claude's actions)
3. Frustrated reactions (\"why did you do X?\", \"I didn't ask for that\")
4. Repeated issues (same problem multiple times)

For each issue found, extract:
- What tool was used (Bash, Edit, Write, etc.)
- Specific pattern or command
- Why it was problematic
- User's stated reason

Return findings as a structured list with:
- category: Type of issue
- tool: Which tool was involved
- pattern: Regex or literal pattern to match
- context: What happened
- severity: high/medium/low

Focus on the most recent issues (last 20-30 messages). Don't go back further unless explicitly asked."
}
```

### ステップ 2: 検出結果をユーザーに提示

動作の収集後（引数またはエージェントから）、AskUserQuestion を使ってユーザーに提示:

**質問 1: どの動作を hookify するか？**
- ヘッダー: "ルール作成"
- multiSelect: true
- オプション: 検出された各動作を一覧表示（最大4件）
  - ラベル: 短い説明（例: "rm -rf をブロック"）
  - 説明: なぜ問題なのか

**質問 2: 選択された各動作に対して、アクションを確認:**
- 「操作をブロックしますか、それとも警告のみにしますか？」
- オプション:
  - "警告のみ"（action: warn - メッセージを表示するが許可する）
  - "操作をブロック"（action: block - 実行を防止する）

**質問 3: パターン例を確認:**
- 「このルールをトリガーするパターンは？」
- 検出されたパターンを表示
- ユーザーが修正または追加できるようにする

### ステップ 3: ルールファイルの生成

確認された各動作に対して `.claude/hookify.{rule-name}.local.md` ファイルを作成:

**ルール命名規則:**
- ケバブケースを使用
- 説明的に: `block-dangerous-rm`, `warn-console-log`, `require-tests-before-stop`
- アクション動詞で始める: block, warn, prevent, require

**ファイル形式:**
```markdown
---
name: {rule-name}
enabled: true
event: {bash|file|stop|prompt|all}
pattern: {regex pattern}
action: {warn|block}
---

{ルールがトリガーされたときに Claude に表示するメッセージ}
```

**アクション値:**
- `warn`: メッセージを表示するが操作は許可する（デフォルト）
- `block`: 操作を防止するかセッションを停止する

**より複雑なルール（複数条件）の場合:**
```markdown
---
name: {rule-name}
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: \.env$
  - field: new_text
    operator: contains
    pattern: API_KEY
---

{警告メッセージ}
```

### ステップ 4: ファイルの作成と確認

**重要**: ルールファイルはカレントワーキングディレクトリの `.claude/` フォルダに作成する必要があります。プラグインディレクトリではありません。

カレントワーキングディレクトリ（Claude Code を起動した場所）をベースパスとして使用します。

1. カレントワーキングディレクトリに `.claude/` ディレクトリが存在するか確認
   - 存在しない場合は、まず作成: `mkdir -p .claude`

2. Write ツールで各 `.claude/hookify.{name}.local.md` ファイルを作成
   - カレントワーキングディレクトリからの相対パスを使用: `.claude/hookify.{name}.local.md`
   - パスはプラグインの .claude ディレクトリではなく、プロジェクトの .claude ディレクトリに解決されること

3. 作成された内容をユーザーに表示:
   ```
   3つの hookify ルールを作成しました:
   - .claude/hookify.dangerous-rm.local.md
   - .claude/hookify.console-log.local.md
   - .claude/hookify.sensitive-files.local.md

   これらのルールは以下でトリガーされます:
   - dangerous-rm: "rm -rf" にマッチする Bash コマンド
   - console-log: console.log 文を追加する編集
   - sensitive-files: .env やクレデンシャルファイルの編集
   ```

4. ファイルが正しい場所に作成されたことをリストで確認

5. ユーザーに通知: **「ルールは即座にアクティブになります。再起動は不要です！」**

   hookify フックは既にロードされており、次のツール使用時に新しいルールを読み込みます。

## イベントタイプリファレンス

- **bash**: Bash ツールのコマンドにマッチ
- **file**: Edit, Write, MultiEdit ツールにマッチ
- **stop**: エージェントが停止しようとしたときにマッチ（完了チェックに使用）
- **prompt**: ユーザーがプロンプトを送信したときにマッチ
- **all**: すべてのイベントにマッチ

## パターン記述のヒント

**Bash パターン:**
- 危険なコマンドにマッチ: `rm\s+-rf|chmod\s+777|dd\s+if=`
- 特定のツールにマッチ: `npm\s+install\s+|pip\s+install`

**ファイルパターン:**
- コードパターンにマッチ: `console\.log\(|eval\(|innerHTML\s*=`
- ファイルパスにマッチ: `\.env$|\.git/|node_modules/`

**停止パターン:**
- 欠落したステップをチェック:（トランスクリプトまたは完了基準を確認）

## ワークフロー例

**ユーザーの発言**: "/hookify 確認なしに rm -rf を使わないで"

**あなたの対応**:
1. 分析: ユーザーは rm -rf コマンドを防止したい
2. 確認: 「このコマンドをブロックしますか、警告だけにしますか？」
3. ユーザーが選択: "警告のみ"
4. `.claude/hookify.dangerous-rm.local.md` を作成:
   ```markdown
   ---
   name: warn-dangerous-rm
   enabled: true
   event: bash
   pattern: rm\s+-rf
   ---

   ⚠️ **危険な rm コマンドを検出しました**

   rm -rf を使用する前に警告するよう要求されました。
   パスが正しいか確認してください。
   ```
5. 確認: 「hookify ルールを作成しました。即座にアクティブです。トリガーしてみてください！」

## 重要な注意事項

- **再起動不要**: ルールは次のツール使用時に即座に有効になります
- **ファイルの場所**: プロジェクトの `.claude/` ディレクトリ（カレントワーキングディレクトリ）にファイルを作成。プラグインの .claude/ ではありません
- **正規表現構文**: Python 正規表現構文を使用（生の文字列、YAML でのエスケープ不要）
- **アクションタイプ**: ルールは操作を `warn`（デフォルト）または `block` できます
- **テスト**: ルール作成後すぐにテストしてください

## トラブルシューティング

**ルールファイルの作成に失敗した場合:**
1. pwd でカレントワーキングディレクトリを確認
2. `.claude/` ディレクトリの存在を確認（必要なら mkdir で作成）
3. 必要に応じて絶対パスを使用: `{cwd}/.claude/hookify.{name}.local.md`
4. Glob または ls でファイルの作成を確認

**ルールが作成後にトリガーされない場合:**
1. ファイルがプラグインの `.claude/` ではなくプロジェクトの `.claude/` にあるか確認
2. Read ツールでファイルを確認し、パターンが正しいか検証
3. パターンをテスト: `python3 -c "import re; print(re.search(r'pattern', 'test text'))"`
4. フロントマターに `enabled: true` があるか確認
5. ルールは即座に機能します。再起動は不要です

**ブロックが厳しすぎる場合:**
1. ルールファイルで `action: block` を `action: warn` に変更
2. またはパターンをより具体的に調整
3. 変更は次のツール使用時に有効になります

TodoWrite を使って手順の進捗を管理してください。
