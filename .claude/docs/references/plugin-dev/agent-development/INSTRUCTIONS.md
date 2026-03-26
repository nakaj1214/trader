# Claude Codeプラグインのエージェント開発

## 概要

エージェントは複雑な複数ステップのタスクを独立して処理する自律サブプロセスです。エージェント構造、トリガー条件、システムプロンプト設計を理解することで、強力な自律機能を作成できます。

**主要概念:**
- エージェントは自律的な作業のため、コマンドはユーザーが起動するアクションのため
- フロントマターを持つMarkdownファイル形式
- descriptionフィールドと例によるトリガー
- システムプロンプトがエージェントの動作を定義
- モデルと色のカスタマイズ

## エージェントファイル構造

### 完全なフォーマット

```markdown
---
name: agent-identifier
description: Use this agent when [triggering conditions]. Examples:

<example>
Context: [Situation description]
user: "[User request]"
assistant: "[How assistant should respond and use this agent]"
<commentary>
[Why this agent should be triggered]
</commentary>
</example>

<example>
[Additional example...]
</example>

model: inherit
color: blue
tools: ["Read", "Write", "Grep"]
---

You are [agent role description]...

**Your Core Responsibilities:**
1. [Responsibility 1]
2. [Responsibility 2]

**Analysis Process:**
[Step-by-step workflow]

**Output Format:**
[What to return]
```

## フロントマターフィールド

### name（必須）

名前空間と呼び出しに使用するエージェント識別子。

**フォーマット:** 小文字、数字、ハイフンのみ
**長さ:** 3〜50文字
**パターン:** 英数字で始まり終わること

**良い例:**
- `code-reviewer`
- `test-generator`
- `api-docs-writer`
- `security-analyzer`

**悪い例:**
- `helper`（汎用すぎる）
- `-agent-`（ハイフンで始まり/終わる）
- `my_agent`（アンダースコア不可）
- `ag`（短すぎる、3文字未満）

### description（必須）

Claudeがこのエージェントをトリガーすべき時を定義する。**最も重要なフィールド。**

**含める必要があるもの:**
1. トリガー条件（「このエージェントを使用するのは...」）
2. 使用方法を示す複数の`<example>`ブロック
3. 各例のコンテキスト、ユーザーリクエスト、アシスタントの応答
4. エージェントがトリガーされる理由を説明する`<commentary>`

**フォーマット:**
```
Use this agent when [conditions]. Examples:

<example>
Context: [Scenario description]
user: "[What user says]"
assistant: "[How Claude should respond]"
<commentary>
[Why this agent is appropriate]
</commentary>
</example>

[More examples...]
```

**ベストプラクティス:**
- 2〜4の具体的な例を含める
- プロアクティブおよびリアクティブなトリガーを示す
- 同じ意図の異なるフレーズをカバーする
- コメンタリーで理由を説明する
- エージェントを使用しない場合について具体的に記載する

### model（必須）

エージェントが使用するモデル。

**オプション:**
- `inherit` - 親と同じモデルを使用（推奨）
- `sonnet` - Claude Sonnet（バランス型）
- `opus` - Claude Opus（最も高性能、高コスト）
- `haiku` - Claude Haiku（高速、低コスト）

**推奨:** エージェントが特定のモデル機能を必要とする場合を除き、`inherit`を使用する。

### color（必須）

UIでのエージェントの視覚的識別子。

**オプション:** `blue`、`cyan`、`green`、`yellow`、`magenta`、`red`

**ガイドライン:**
- 同じプラグイン内の異なるエージェントには異なる色を選択
- 類似したエージェントタイプには一貫した色を使用
- Blue/cyan: 分析、レビュー
- Green: 成功指向のタスク
- Yellow: 注意、検証
- Red: クリティカル、セキュリティ
- Magenta: クリエイティブ、生成

### tools（オプション）

エージェントを特定のツールに制限する。

**フォーマット:** ツール名の配列

```yaml
tools: ["Read", "Write", "Grep", "Bash"]
```

**デフォルト:** 省略した場合、エージェントは全ツールにアクセス可能

**ベストプラクティス:** 最小限必要なツールに制限する（最小権限の原則）

**一般的なツールセット:**
- 読み取り専用分析: `["Read", "Grep", "Glob"]`
- コード生成: `["Read", "Write", "Grep"]`
- テスト: `["Read", "Bash", "Grep"]`
- フルアクセス: フィールドを省略するか`["*"]`を使用

## システムプロンプト設計

Markdownの本文がエージェントのシステムプロンプトになる。エージェントに直接話しかける2人称で書く。

### 構造

**標準テンプレート:**
```markdown
You are [role] specializing in [domain].

**Your Core Responsibilities:**
1. [Primary responsibility]
2. [Secondary responsibility]
3. [Additional responsibilities...]

**Analysis Process:**
1. [Step one]
2. [Step two]
3. [Step three]
[...]

**Quality Standards:**
- [Standard 1]
- [Standard 2]

**Output Format:**
Provide results in this format:
- [What to include]
- [How to structure]

**Edge Cases:**
Handle these situations:
- [Edge case 1]: [How to handle]
- [Edge case 2]: [How to handle]
```

### ベストプラクティス

✅ **すること:**
- 2人称で書く（"You are..."、"You will..."）
- 責任を具体的に記述する
- ステップバイステップのプロセスを提供する
- 出力フォーマットを定義する
- 品質基準を含める
- エッジケースに対処する
- 10,000文字以下に保つ

❌ **しないこと:**
- 1人称で書く（"I am..."、"I will..."）
- 曖昧または汎用的に書く
- プロセスステップを省略する
- 出力フォーマットを未定義のままにする
- 品質ガイダンスを省く
- エラーケースを無視する

## エージェントの作成

### 方法1: AI支援による生成

このプロンプトパターンを使用する（Claude Codeから抽出）:

```
Create an agent configuration based on this request: "[YOUR DESCRIPTION]"

Requirements:
1. Extract core intent and responsibilities
2. Design expert persona for the domain
3. Create comprehensive system prompt with:
   - Clear behavioral boundaries
   - Specific methodologies
   - Edge case handling
   - Output format
4. Create identifier (lowercase, hyphens, 3-50 chars)
5. Write description with triggering conditions
6. Include 2-3 <example> blocks showing when to use

Return JSON with:
{
  "identifier": "agent-name",
  "whenToUse": "Use this agent when... Examples: <example>...</example>",
  "systemPrompt": "You are..."
}
```

その後、フロントマターを持つエージェントファイル形式に変換する。

完全なテンプレートは`examples/agent-creation-prompt.md`を参照。

### 方法2: 手動作成

1. エージェント識別子を選ぶ（3〜50文字、小文字、ハイフン）
2. 例を含むdescriptionを書く
3. モデルを選択する（通常は`inherit`）
4. 視覚的識別のための色を選ぶ
5. ツールを定義する（アクセスを制限する場合）
6. 上記の構造でシステムプロンプトを書く
7. `agents/agent-name.md`として保存する

## バリデーションルール

### 識別子のバリデーション

```
✅ 有効: code-reviewer, test-gen, api-analyzer-v2
❌ 無効: ag（短すぎ）, -start（ハイフンで始まる）, my_agent（アンダースコア）
```

**ルール:**
- 3〜50文字
- 小文字、数字、ハイフンのみ
- 英数字で始まり終わること
- アンダースコア、スペース、特殊文字は不可

### descriptionのバリデーション

**長さ:** 10〜5,000文字
**含める必要があるもの:** トリガー条件と例
**推奨:** 2〜4の例を含む200〜1,000文字

### システムプロンプトのバリデーション

**長さ:** 20〜10,000文字
**推奨:** 500〜3,000文字
**構造:** 明確な責任、プロセス、出力フォーマット

## エージェントの整理

### プラグインエージェントディレクトリ

```
plugin-name/
└── agents/
    ├── analyzer.md
    ├── reviewer.md
    └── generator.md
```

`agents/`内のすべての`.md`ファイルが自動検出される。

### 名前空間

エージェントは自動的に名前空間が付けられる:
- 単一プラグイン: `agent-name`
- サブディレクトリあり: `plugin:subdir:agent-name`

## エージェントのテスト

### トリガーのテスト

エージェントが正しくトリガーされることを確認するためのテストシナリオを作成する:

1. 特定のトリガー例を持つエージェントを書く
2. テストで例と似たフレーズを使用する
3. ClaudeがエージェントをロードすることをVerify
4. エージェントが期待される機能を提供することを確認する

### システムプロンプトのテスト

システムプロンプトが完全であることを確認する:

1. エージェントに典型的なタスクを与える
2. プロセスステップに従っているかチェックする
3. 出力フォーマットが正しいか確認する
4. プロンプトで言及されているエッジケースをテストする
5. 品質基準が満たされているか確認する

## クイックリファレンス

### 最小エージェント

```markdown
---
name: simple-agent
description: Use this agent when... Examples: <example>...</example>
model: inherit
color: blue
---

You are an agent that [does X].

Process:
1. [Step 1]
2. [Step 2]

Output: [What to provide]
```

### フロントマターフィールドのまとめ

| フィールド | 必須 | フォーマット | 例 |
|-------|----------|--------|---------|
| name | Yes | lowercase-hyphens | code-reviewer |
| description | Yes | テキスト + 例 | Use when... <example>... |
| model | Yes | inherit/sonnet/opus/haiku | inherit |
| color | Yes | 色の名前 | blue |
| tools | No | ツール名の配列 | ["Read", "Grep"] |

### ベストプラクティス

**すること:**
- ✅ descriptionに2〜4の具体的な例を含める
- ✅ 具体的なトリガー条件を書く
- ✅ 特定の必要がなければモデルに`inherit`を使用
- ✅ 適切なツールを選択する（最小権限）
- ✅ 明確で構造化されたシステムプロンプトを書く
- ✅ エージェントのトリガーを徹底的にテストする

**しないこと:**
- ❌ 例のない汎用的なdescriptionを使用する
- ❌ トリガー条件を省略する
- ❌ 全エージェントに同じ色を使用する
- ❌ 不必要なツールアクセスを付与する
- ❌ 曖昧なシステムプロンプトを書く
- ❌ テストを省略する

## 追加リソース

### リファレンスファイル

詳細なガイダンスについては以下を参照:

- **`references/system-prompt-design.md`** - 完全なシステムプロンプトパターン
- **`references/triggering-examples.md`** - 例のフォーマットとベストプラクティス
- **`references/agent-creation-system-prompt.md`** - Claude Codeからの正確なプロンプト

### サンプルファイル

`examples/`内の動作例:

- **`agent-creation-prompt.md`** - AI支援エージェント生成テンプレート
- **`complete-agent-examples.md`** - 様々なユースケースの完全なエージェント例

### ユーティリティスクリプト

`scripts/`内の開発ツール:

- **`validate-agent.sh`** - エージェントファイル構造を検証
- **`test-agent-trigger.sh`** - エージェントが正しくトリガーされるかテスト

## 実装ワークフロー

プラグインのエージェントを作成するには:

1. エージェントの目的とトリガー条件を定義する
2. 作成方法を選択する（AI支援または手動）
3. `agents/agent-name.md`ファイルを作成する
4. 全必須フィールドを含むフロントマターを書く
5. ベストプラクティスに従ってシステムプロンプトを書く
6. descriptionに2〜4のトリガー例を含める
7. `scripts/validate-agent.sh`で検証する
8. 実際のシナリオでトリガーをテストする
9. プラグインREADMEにエージェントを文書化する

自律動作のために明確なトリガー条件と包括的なシステムプロンプトに集中すること。
