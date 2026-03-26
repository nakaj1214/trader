# コンテキスト管理ガイド

Claude のコンテキストウィンドウを効果的に管理することは、パフォーマンスとコストの最適化に不可欠です。

## コンテキストの理解

### コンテキストウィンドウサイズ
- **利用可能な合計**: 200,000 トークン
- **MCP 使用時の実効値**: 70,000 トークンまで低下する可能性あり
- **危険閾値**: 80,000 トークン未満 = パフォーマンス低下

### コンテキストを消費するもの

1. **システムプロンプト** (~5,000-15,000 トークン)
2. **会話履歴** (時間とともに増加)
3. **ファイル内容** (読み込み時)
4. **ツール定義** (MCP サーバー)
5. **エージェントコンテキスト** (特化エージェント)

## MCP サーバー管理

### 問題
各 MCP（Model Context Protocol）サーバーは Claude のコンテキストにツールを追加します。ツールが多すぎるとコンテキストウィンドウが圧迫されます。

### 推奨上限
- **合計 MCP 数**: 最大 20-30
- **プロジェクトごとの有効数**: 10 未満
- **アクティブツール数**: 80 未満

### MCP の管理方法

#### プロジェクトレベルの設定
プロジェクトに `.claude/config.json` を作成:

```json
{
  "disabledMcpServers": [
    "aws-mcp",
    "kubernetes-mcp",
    "terraform-mcp"
  ]
}
```

#### グローバル設定
`~/.claude/settings.json` を編集:

```json
{
  "mcpServers": {
    "filesystem": { "enabled": true },
    "github": { "enabled": true },
    "slack": { "enabled": false },
    "aws": { "enabled": false }
  }
}
```

#### スマートな MCP 戦略

**必要なものだけを有効にする:**
- Web 開発？有効にする: filesystem, github, npm
- クラウド作業？有効にする: aws, docker, kubernetes
- データサイエンス？有効にする: filesystem, python, jupyter

**使用しないときは無効にする:**
```bash
# MCP を一時的に無効化
/mcp disable aws-mcp

# 必要なときに再有効化
/mcp enable aws-mcp

# すべての MCP を一覧表示
/mcp list
```

## パッケージマネージャーの検出

### 設定の優先順位
Claude は以下の順序でパッケージマネージャーを検出します:

1. **環境変数**
   ```bash
   export CLAUDE_PACKAGE_MANAGER=pnpm
   ```

2. **プロジェクト設定**
   ```json
   // .claude/package-manager.json
   {
     "packageManager": "pnpm"
   }
   ```

3. **package.json**
   ```json
   {
     "packageManager": "pnpm@8.0.0"
   }
   ```

4. **ロックファイル検出**
   - `pnpm-lock.yaml` → pnpm
   - `yarn.lock` → yarn
   - `package-lock.json` → npm
   - `bun.lockb` → bun

5. **グローバル設定**
   ```json
   // ~/.claude/package-manager.json
   {
     "packageManager": "npm"
   }
   ```

6. **最初に見つかったもの**
   - チェック順: pnpm, yarn, bun, npm

### セットアップコマンド
```bash
# プロジェクトでこれを実行
/setup-pm

# または手動で設定ファイルを作成
echo '{"packageManager":"pnpm"}' > .claude/package-manager.json
```

## トークンコスト削減設定

出典: [everything-claude-code](https://github.com/affaan-m/everything-claude-code) `docs/token-optimization.md`

### 推奨設定値

`~/.claude/settings.json` に以下を設定:

| 設定 | 推奨値 | デフォルト | 効果 |
|------|--------|-----------|------|
| `MAX_THINKING_TOKENS` | 10,000 | 31,999 | 隠れコストを約70%削減 |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | 50% | 95% | 品質低下前に自動圧縮 |

```bash
# 環境変数で設定
export MAX_THINKING_TOKENS=10000
export CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50
```

### モデル別コスト戦略

- **メイン作業**: Sonnet（タスクの80%を処理、Opus 比60%コスト削減）
- **サブエージェント**: Haiku（約80%安価、探索・ファイル読み込み・テスト実行に十分）
- **複雑な推論**: Opus（セッション中に `/model opus` で切替）

### その他の最適化

- `/clear` で無関係なタスク間を切替
- `/compact` で論理的なブレークポイント（計画後、デバッグ後）に圧縮
- `/cost` で支出を監視
- MCP サーバーはプロジェクトあたり10未満に抑える

## コンテキスト最適化戦略

### 1. ファイル読み込みを最小化する

**悪いアプローチ:**
```typescript
// 大きなファイルを丸ごと読み込む
Read('src/components/LargeComponent.tsx')
Read('src/utils/helpers.ts')
Read('src/config/settings.ts')
```

**良いアプローチ:**
```typescript
// まず Grep で特定のコードを見つける
Grep('function targetFunction', { type: 'ts' })
// 次に関連ファイルのみ読み込む
Read('src/utils/helpers.ts', { offset: 100, limit: 50 })
```

### 2. エージェントを賢く使う

**問題**: エージェントを起動すると、そのコンテキストが自分のコンテキストに追加される

**解決策**: 高コストな操作にエージェントを使用する
```typescript
// Bad: メインコンテキストで50ファイルを読み込む
for (const file of allFiles) {
  Read(file);
}

// Good: Explore エージェントに委任する
Task({
  subagent_type: 'Explore',
  prompt: 'Find all authentication-related functions'
});
```

### 3. 不要な履歴をクリアする

**リセットするタイミング:**
- 無関係なタスクに切り替えるとき
- コンテキストが大きくなりすぎたとき
- パフォーマンスが低下したとき

**リセット方法:**
```bash
# 新しい会話を開始
/clear

# または重要なコンテキストのためにチェックポイント/保存を使用
/save checkpoint-before-refactor
```

### 4. システムプロンプトを最適化する

**カスタム指示を簡潔に保つ:**
```markdown
<!-- Bad: 5,000 トークンの指示 -->
- 常に X を行う
- Y は決してしない
- Z を考慮する
[... さらに 200 のルール ...]

<!-- Good: 500 トークンに集約 -->
# コアルール
1. セキュリティ: すべての入力をバリデーション
2. 品質: コミット前にテスト
3. スタイル: プロジェクトパターンに従う
```

### 5. 戦略的なファイルグルーピング

**Bad: 小さな読み込みを大量に**
```typescript
Read('types/user.ts')
Read('types/auth.ts')
Read('types/api.ts')
```

**Better: Glob を使用する**
```typescript
Glob('types/**/*.ts')
// 必要に応じて特定のファイルを読み込む
```

## トークンバジェット管理

### 使用量の監視
Claude は各レスポンスの後にトークン使用量を表示します:
```
Token usage: 25,000/200,000; 175,000 remaining
```

### バジェット内に収める

**目標範囲:**
- **健全**: 使用量 50,000 トークン未満
- **警告**: 50,000-100,000 トークン
- **危険**: 100,000 トークン超

**危険な場合:**
1. 現在のタスクを完了する
2. 新しい会話を開始する
3. コンテキストの簡単な要約を提供する
4. 新しい状態で続行する

## コンテキストに応じたモデル選択

### 各モデルの使い分け

**Haiku（高速、小さなコンテキスト）**
- シンプルなタスク
- 素早い操作
- ファイル検索
- コマンド実行

```typescript
Task({
  model: 'haiku',
  prompt: 'List all TypeScript files'
})
```

**Sonnet（バランス型）**
- 一般的な開発
- コードレビュー
- 実装
- デフォルトの選択肢

```typescript
Task({
  model: 'sonnet',
  prompt: 'Implement user authentication'
})
```

**Opus（大きなコンテキスト、深い推論）**
- 複雑なアーキテクチャ
- 重要な判断
- 大規模なリファクタリング
- システム設計

```typescript
Task({
  model: 'opus',
  prompt: 'Design microservices architecture'
})
```

## コンテキストを意識したワークフロー

### パターン 1: プログレッシブローディング
```
1. ハイレベルな検索から始める（Grep/Glob）
2. 関連ファイルを特定する
3. 必要なセクションのみ読み込む
4. 変更を実装する
```

### パターン 2: エージェント委任
```
1. リサーチを Explore エージェントに委任する
2. エージェントが要約を返す
3. 最小限のコンテキストで判断する
4. 焦点を絞った読み込みで実装する
```

### パターン 3: チェックポイント戦略
```
1. フェーズ 1 を完了する
2. チェックポイントを保存する
3. 会話をクリアする
4. 要約で再開する
5. フェーズ 2 を続行する
```

## メモリの永続化

### セッションフック
セッション間でコンテキストを保存・読み込みする:

```json
// ~/.claude/settings.json
{
  "hooks": {
    "session:end": "~/.claude/hooks/save-context.sh",
    "session:start": "~/.claude/hooks/load-context.sh"
  }
}
```

**save-context.sh:**
```bash
#!/bin/bash
# 重要なコンテキストをファイルに保存
echo "$CONVERSATION_SUMMARY" > ~/.claude/memory/last-session.txt
```

**load-context.sh:**
```bash
#!/bin/bash
# 関連する場合、前回のコンテキストを読み込む
if [ -f ~/.claude/memory/last-session.txt ]; then
  cat ~/.claude/memory/last-session.txt
fi
```

## ベストプラクティスまとめ

### すべきこと
- トークン使用量を定期的に監視する
- 使用していない MCP を無効にする
- 高コストな操作にはエージェントを使用する
- ファイルは選択的に読み込む
- タスク切り替え時にコンテキストをクリアする
- タスクに適したモデルを使用する
- カスタム指示を簡潔に保つ

### すべきでないこと
- すべての MCP を一度に有効にする
- 大きなファイルを不必要に丸ごと読み込む
- 無関係な履歴を残す
- シンプルなタスクに Opus を使用する
- コンテキストを際限なく増やす
- 不要なファイルを読み込む

## トラブルシューティング

### 症状: レスポンスが遅い
**原因**: コンテキストが大きすぎる
**解決策**:
1. トークン使用量を確認する
2. 不要な履歴をクリアする
3. 使用していない MCP を無効にする

### 症状: 「コンテキスト制限超過」
**原因**: コンテンツが多すぎる
**解決策**:
1. 新しい会話を開始する
2. MCP の数を減らす
3. 読み込むファイルを減らす

### 症状: Claude が以前の情報を「忘れる」
**原因**: コンテキストウィンドウが一杯
**解決策**:
1. メモリ永続化フックを使用する
2. チェックポイントを保存する
3. 再開時に簡潔な要約を提供する

## 上級テクニック: コンテキスト圧縮

### テクニック 1: 要約
```
# コンテキストチェックポイント時
「このセッションの主要な決定とコード変更を要約して」

# 要約を使って新しいセッションを開始
「続き: [要約]。次に機能 Y を実装しましょう。」
```

### テクニック 2: アーティファクトストレージ
```bash
# 重要な情報を外部に保存
echo "API endpoints: /api/users, /api/auth" > .claude/project-info.txt

# 必要なときに参照
「エンドポイントは .claude/project-info.txt を確認してください」
```

### テクニック 3: 継続的学習
セッション中にパターンを抽出してスキルとして保存する:

```markdown
# .claude/skills/project-patterns.md
---
name: project-patterns
description: Common patterns used in this project
---

- API ルートは /api ディレクトリ内
- コンポーネントはフックパターンを使用
- エラーハンドリングは ErrorBoundary 経由
```

## 追跡すべきメトリクス

以下を継続的に監視する:
- セッションあたりの平均トークン数
- アクティブな MCP 数
- タスクあたりの読み込みファイル数
- エージェント起動頻度
- リセットまでのセッション持続時間

ワークフローのパターンに基づいて最適化する。
