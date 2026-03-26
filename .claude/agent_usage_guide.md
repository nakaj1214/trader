# Claude エージェント使用ガイド

## 概要
Claude Code はタスクごとに特化したエージェントを提供しています。適切なエージェントを使用することで、パフォーマンスと精度が大幅に向上します。

## 利用可能なエージェント

### 1. Explore エージェント
**用途:** コードベースの探索と理解

**使用するタイミング:**
- 「エラー処理はどこで行われている？」
- 「認証はどのように動作する？」
- 「コードベースの構造は？」
- 「フックを使用しているすべてのコンポーネントを見つけて」
- 複数の検索が必要な探索全般

**例:**
```
User: クライアントからのエラーはどこで処理されている？
Assistant: [Task ツールを subagent_type=Explore で使用]
```

**徹底度レベル:**
- `quick`: 基本的な検索
- `medium`: 適度な探索（デフォルト）
- `very thorough`: 包括的な分析

### 2. Plan エージェント
**用途:** 実装戦略の設計

**使用するタイミング:**
- 複雑な機能の実装
- 複数の有効なアプローチが存在する場合
- アーキテクチャの判断が必要な場合
- 複数ファイルにまたがる変更が必要な場合

**動作内容:**
- コードベースを徹底的に探索する
- 重要なファイルを特定する
- トレードオフを検討する
- ステップバイステップの計画を作成する

### 3. Bash エージェント
**用途:** コマンドライン操作

**使用するタイミング:**
- Git 操作
- パッケージ管理（npm, pip など）
- Docker コマンド
- ビルドプロセス
- ターミナル操作全般

**使用しない場合:**
- ファイル読み込み（Read ツールを使用）
- ファイル編集（Edit ツールを使用）
- ファイル検索（Glob/Grep ツールを使用）

### 4. 汎用エージェント
**用途:** 複雑なマルチステップタスク

**使用するタイミング:**
- 複数のステップが必要なリサーチ
- いくつかの操作を組み合わせるタスク
- 自由度の高い検索
- 複雑なデータ収集

## エージェントのベストプラクティス

### 並列実行
可能な場合は複数のエージェントを同時に起動する:
```javascript
// Good: 単一メッセージで複数エージェント
Task(agent1), Task(agent2), Task(agent3)

// Bad: 逐次的なエージェント起動
Task(agent1) -> wait -> Task(agent2) -> wait -> Task(agent3)
```

### バックグラウンド実行
長時間実行タスクの場合:
```javascript
Task(subagent_type="Bash",
     prompt="Run comprehensive test suite",
     run_in_background=true)
```

### モデル選択
タスクの複雑さに応じて適切なモデルを選択する:
```javascript
// 簡単なタスク - Haiku を使用
Task(model="haiku", prompt="List all .ts files")

// 複雑な推論 - Opus を使用
Task(model="opus", prompt="Design authentication architecture")

// デフォルト - バランスの取れた Sonnet
Task(prompt="Implement feature X")
```

### エージェントの再開
以前のエージェントを再開して作業を続行する:
```javascript
// 最初の呼び出し
agent_id = Task(subagent_type="Explore", prompt="Find auth code")

// 後で、同じコンテキストで再開
Task(resume=agent_id, prompt="Now check error handling")
```

## よくあるパターン

### パターン 1: 探索してから実装
```
1. Task(Explore): "認証の実装を見つける"
2. 発見内容をレビュー
3. EnterPlanMode: 変更を設計
4. 変更を実装
```

### パターン 2: 並列リサーチ
```
Task(Explore, "ルーティングはどう処理されている？")
Task(Explore, "状態管理はどうなっている？")
Task(Explore, "API コールはどう行われている？")
// すべて並列で実行
```

### パターン 3: ビルドとテスト
```
1. コード変更を行う
2. Task(Bash): "npm run build"
3. Task(Bash): "npm test"
4. 発見された問題を修正
```

### パターン 4: 包括的な分析
```
Task(subagent_type="Explore",
     thoroughness="very thorough",
     prompt="Analyze entire authentication flow including error handling, session management, and security measures")
```

## アンチパターン

**ファイル操作に Bash を使用する**
```
// Bad
Task(Bash, "cat src/index.ts")
// Good
Read("src/index.ts")
```

**コードベースの質問に Explore を使わない**
```
// Bad
Grep + Glob + Read を手動で組み合わせ
// Good
Task(Explore, "Where is feature X implemented?")
```

**並列実行可能なのに逐次実行する**
```
// Bad
agent1 -> wait -> agent2 -> wait
// Good
agent1, agent2 を同じメッセージで
```

**タスクの複雑さに合わないモデルを使用する**
```
// Bad
Task(model="opus", "List files")
// Good
Task(model="haiku", "List files")
```

## 判断フロー

```
コードベースの探索？ → Explore エージェント
  ├─ 簡単なキーワード検索 → quick
  ├─ 中程度の調査 → medium
  └─ 包括的な分析 → very thorough

実装の計画？ → Plan エージェント

ターミナルコマンド？ → Bash エージェント
  └─ ただしファイル操作には使わない

マルチステップのリサーチ？ → 汎用エージェント

ファイル操作？
  ├─ 読み込み → Read ツール（エージェントではない）
  ├─ 編集 → Edit ツール（エージェントではない）
  └─ 検索 → Glob/Grep ツール（エージェントではない）
```

## パフォーマンスのコツ

1. **高コストな操作には Task ツールを使用する** ことでコンテキスト使用量を削減
2. **タスクが独立している場合はエージェントを並列起動する**
3. **長時間実行操作にはバックグラウンド実行を使用する**
4. **適切なモデルを選択する**: 簡単なタスクは Haiku、複雑なタスクは Opus
5. **作業を継続する場合は新規開始ではなくエージェントを再開する**
6. **エージェントが効率的に動けるよう、プロンプトは具体的にする**

## エージェントを使わない場合

- 特定の既知のファイルを読む → Read ツールを使用
- 特定の行を編集する → Edit ツールを使用
- 名前パターンでファイルを検索する → Glob ツールを使用
- 特定のテキストを検索する → Grep ツールを使用
- 単一コマンドを実行する → Bash ツールを直接使用
