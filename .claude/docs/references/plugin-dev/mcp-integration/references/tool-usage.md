# コマンドとエージェントでの MCP ツールの使用

Claude Code プラグインのコマンドとエージェントで MCP ツールを効果的に使用するための完全ガイドです。

## 概要

MCP サーバーを設定すると、そのツールはプレフィックス `mcp__plugin_<plugin-name>_<server-name>__<tool-name>` で利用可能になります。これらのツールは、Claude Code の組み込みツールと同様にコマンドやエージェントで使用できます。

## ツールの命名規則

### フォーマット

```
mcp__plugin_<plugin-name>_<server-name>__<tool-name>
```

### 例

**Asana プラグインの asana サーバー:**
- `mcp__plugin_asana_asana__asana_create_task`
- `mcp__plugin_asana_asana__asana_search_tasks`
- `mcp__plugin_asana_asana__asana_get_project`

**カスタムプラグインの database サーバー:**
- `mcp__plugin_myplug_database__query`
- `mcp__plugin_myplug_database__execute`
- `mcp__plugin_myplug_database__list_tables`

### ツール名の確認

**`/mcp` コマンドを使用:**
```bash
/mcp
```

表示される内容:
- 利用可能なすべての MCP サーバー
- 各サーバーが提供するツール
- ツールのスキーマと説明
- 設定で使用する完全なツール名

## コマンドでのツール使用

### ツールの事前許可

コマンドのフロントマターで MCP ツールを指定します:

```markdown
---
description: 新しい Asana タスクを作成する
allowed-tools: [
  "mcp__plugin_asana_asana__asana_create_task"
]
---

# タスク作成コマンド

タスクを作成するには:
1. ユーザーからタスクの詳細を収集
2. mcp__plugin_asana_asana__asana_create_task を使用して詳細を指定
3. 作成をユーザーに確認
```

### 複数ツール

```markdown
---
allowed-tools: [
  "mcp__plugin_asana_asana__asana_create_task",
  "mcp__plugin_asana_asana__asana_search_tasks",
  "mcp__plugin_asana_asana__asana_get_project"
]
---
```

### ワイルドカード（慎重に使用）

```markdown
---
allowed-tools: ["mcp__plugin_asana_asana__*"]
---
```

**注意:** コマンドがサーバーのすべてのツールに本当にアクセスする必要がある場合のみワイルドカードを使用してください。

### コマンド手順でのツール使用

**コマンドの例:**
```markdown
---
description: Asana タスクの検索と作成
allowed-tools: [
  "mcp__plugin_asana_asana__asana_search_tasks",
  "mcp__plugin_asana_asana__asana_create_task"
]
---

# Asana タスク管理

## タスクの検索

タスクを検索するには:
1. mcp__plugin_asana_asana__asana_search_tasks を使用
2. 検索フィルター（担当者、プロジェクトなど）を指定
3. 結果をユーザーに表示

## タスクの作成

タスクを作成するには:
1. タスクの詳細を収集:
   - タイトル（必須）
   - 説明
   - プロジェクト
   - 担当者
   - 期限
2. mcp__plugin_asana_asana__asana_create_task を使用
3. タスクリンク付きの確認を表示
```

## エージェントでのツール使用

### エージェントの設定

エージェントは事前許可なしで MCP ツールを自律的に使用できます:

```markdown
---
name: asana-status-updater
description: ユーザーが「Asana のステータスを更新」「プロジェクトレポートを生成」「Asana タスクを同期」と依頼した場合に使用するエージェント
model: inherit
color: blue
---

## 役割

Asana プロジェクトステータスレポートを生成する自律エージェント。

## プロセス

1. **タスクの照会**: mcp__plugin_asana_asana__asana_search_tasks ですべてのタスクを取得
2. **進捗の分析**: 完了率の計算とブロッカーの特定
3. **レポートの生成**: フォーマットされたステータス更新を作成
4. **Asana の更新**: mcp__plugin_asana_asana__asana_create_comment でレポートを投稿

## 利用可能なツール

エージェントは事前承認なしですべての Asana MCP ツールにアクセスできます。
```

### エージェントのツールアクセス

エージェントはコマンドよりも広いツールアクセスを持ちます:
- Claude が必要と判断した任意のツールを使用可能
- 事前許可リストが不要
- 通常使用するツールを文書化すべき

## ツール呼び出しパターン

### パターン 1: シンプルなツール呼び出し

バリデーション付きの単一ツール呼び出し:

```markdown
手順:
1. ユーザーが必要なフィールドを提供したかバリデーション
2. バリデーション済みデータで mcp__plugin_api_server__create_item を呼び出し
3. エラーを確認
4. 確認を表示
```

### パターン 2: 順次ツール呼び出し

複数のツール呼び出しをチェーン:

```markdown
手順:
1. 既存アイテムを検索: mcp__plugin_api_server__search
2. 見つからない場合、新規作成: mcp__plugin_api_server__create
3. メタデータを追加: mcp__plugin_api_server__update_metadata
4. 最終アイテム ID を返す
```

### パターン 3: バッチ操作

同じツールで複数の呼び出し:

```markdown
手順:
1. 処理するアイテムのリストを取得
2. 各アイテムに対して:
   - mcp__plugin_api_server__update_item を呼び出し
   - 成功/失敗を追跡
3. 結果のサマリーを報告
```

### パターン 4: エラーハンドリング

適切なエラーハンドリング:

```markdown
手順:
1. mcp__plugin_api_server__get_data を呼び出し試行
2. エラーの場合（レート制限、ネットワーク等）:
   - 待機してリトライ（最大3回）
   - それでも失敗する場合、ユーザーに通知
   - 設定の確認を提案
3. 成功時、データを処理
```

## ツールパラメータ

### ツールスキーマの理解

各 MCP ツールにはパラメータを定義するスキーマがあります。`/mcp` で確認できます。

**スキーマの例:**
```json
{
  "name": "asana_create_task",
  "description": "Create a new Asana task",
  "inputSchema": {
    "type": "object",
    "properties": {
      "name": {
        "type": "string",
        "description": "Task title"
      },
      "notes": {
        "type": "string",
        "description": "Task description"
      },
      "workspace": {
        "type": "string",
        "description": "Workspace GID"
      }
    },
    "required": ["name", "workspace"]
  }
}
```

### パラメータ付きのツール呼び出し

Claude はスキーマに基づいてツール呼び出しを自動的に構成します:

```typescript
// Claude generates this internally
{
  toolName: "mcp__plugin_asana_asana__asana_create_task",
  input: {
    name: "Review PR #123",
    notes: "Code review for new feature",
    workspace: "12345",
    assignee: "67890",
    due_on: "2025-01-15"
  }
}
```

### パラメータのバリデーション

**コマンドでは呼び出し前にバリデーション:**

```markdown
手順:
1. 必須パラメータを確認:
   - タイトルが空でない
   - ワークスペース ID が提供されている
   - 期限が有効な形式（YYYY-MM-DD）
2. バリデーション失敗時、不足データの提供をユーザーに要求
3. バリデーション成功時、MCP ツールを呼び出し
4. ツールエラーを適切に処理
```

## レスポンスの処理

### 成功レスポンス

```markdown
手順:
1. MCP ツールを呼び出し
2. 成功時:
   - レスポンスから関連データを抽出
   - ユーザー表示用にフォーマット
   - 確認メッセージを提供
   - 関連リンクまたは ID を含める
```

### エラーレスポンス

```markdown
手順:
1. MCP ツールを呼び出し
2. エラー時:
   - エラータイプを確認（認証、レート制限、バリデーション等）
   - 有用なエラーメッセージを提供
   - 対処手順を提案
   - 内部エラーの詳細をユーザーに公開しない
```

### 部分的な成功

```markdown
手順:
1. 複数の MCP 呼び出しによるバッチ操作
2. 成功と失敗を個別に追跡
3. サマリーを報告:
   - 「10件中8件を正常に処理しました」
   - 「失敗したアイテム: [item1, item2] 理由: [reason]」
   - リトライまたは手動介入を提案
```

## パフォーマンス最適化

### リクエストのバッチ処理

**良い例: フィルター付きの単一クエリ**
```markdown
手順:
1. フィルター付きで mcp__plugin_api_server__search を呼び出し:
   - project_id: "123"
   - status: "active"
   - limit: 100
2. すべての結果を処理
```

**避けるべき例: 多数の個別クエリ**
```markdown
手順:
1. 各アイテム ID に対して:
   - mcp__plugin_api_server__get_item を呼び出し
   - アイテムを処理
```

### 結果のキャッシュ

```markdown
手順:
1. コストの高い MCP 操作を呼び出し: mcp__plugin_api_server__analyze
2. 再利用のために結果を変数に保存
3. 後続の操作にキャッシュされた結果を使用
4. データが変更された場合のみ再取得
```

### 並列ツール呼び出し

ツール間に依存関係がない場合、並列で呼び出します:

```markdown
手順:
1. 並列呼び出しを実行（Claude が自動処理）:
   - mcp__plugin_api_server__get_project
   - mcp__plugin_api_server__get_users
   - mcp__plugin_api_server__get_tags
2. すべての完了を待機
3. 結果を統合
```

## 統合のベストプラクティス

### ユーザーエクスペリエンス

**フィードバックを提供:**
```markdown
手順:
1. ユーザーに通知: 「Asana タスクを検索中...」
2. mcp__plugin_asana_asana__asana_search_tasks を呼び出し
3. 進行状況を表示: 「15件のタスクが見つかりました、分析中...」
4. 結果を提示
```

**長時間操作の処理:**
```markdown
手順:
1. ユーザーに警告: 「これには1分ほどかかる場合があります...」
2. 更新付きの小さなステップに分割
3. 段階的な進捗を表示
4. 完了時に最終サマリー
```

### エラーメッセージ

**良いエラーメッセージ:**
```
タスクを作成できませんでした。以下を確認してください:
   1. Asana にログインしていること
   2. ワークスペース 'Engineering' へのアクセス権があること
   3. プロジェクト 'Q1 Goals' が存在すること
```

**悪いエラーメッセージ:**
```
エラー: MCP ツールが 403 を返しました
```

### ドキュメント

**コマンドでの MCP ツール使用を文書化:**
```markdown
## 使用する MCP ツール

このコマンドは以下の Asana MCP ツールを使用します:
- **asana_search_tasks**: 条件に一致するタスクを検索
- **asana_create_task**: 詳細を指定して新しいタスクを作成
- **asana_update_task**: 既存のタスクプロパティを更新

このコマンドを実行する前に Asana に認証されていることを確認してください。
```

## ツール使用のテスト

### ローカルテスト

1. `.mcp.json` に **MCP サーバーを設定**
2. `.claude-plugin/` に**プラグインをローカルインストール**
3. `/mcp` で**ツールの利用可能性を確認**
4. ツールを使用する**コマンドをテスト**
5. **デバッグ出力を確認**: `claude --debug`

### テストシナリオ

**成功呼び出しのテスト:**
```markdown
手順:
1. 外部サービスにテストデータを作成
2. このデータを照会するコマンドを実行
3. 正しい結果が返されることを確認
```

**エラーケースのテスト:**
```markdown
手順:
1. 認証なしでテスト
2. 無効なパラメータでテスト
3. 存在しないリソースでテスト
4. 適切なエラーハンドリングを確認
```

**エッジケースのテスト:**
```markdown
手順:
1. 空の結果でテスト
2. 最大結果数でテスト
3. 特殊文字でテスト
4. 同時アクセスでテスト
```

## よくあるパターン

### パターン: CRUD 操作

```markdown
---
allowed-tools: [
  "mcp__plugin_api_server__create_item",
  "mcp__plugin_api_server__read_item",
  "mcp__plugin_api_server__update_item",
  "mcp__plugin_api_server__delete_item"
]
---

# アイテム管理

## 作成
必須フィールドで create_item を使用...

## 読み取り
アイテム ID で read_item を使用...

## 更新
アイテム ID と変更内容で update_item を使用...

## 削除
アイテム ID で delete_item を使用（先に確認を求める）...
```

### パターン: 検索して処理

```markdown
手順:
1. **検索**: フィルター付きで mcp__plugin_api_server__search
2. **フィルタリング**: 必要に応じて追加のローカルフィルタリングを適用
3. **変換**: 各結果を処理
4. **提示**: フォーマットしてユーザーに表示
```

### パターン: マルチステップワークフロー

```markdown
手順:
1. **セットアップ**: 必要な情報をすべて収集
2. **バリデーション**: データの完全性を確認
3. **実行**: MCP ツール呼び出しのチェーン:
   - 親リソースを作成
   - 子リソースを作成
   - リソースを関連付け
   - メタデータを追加
4. **検証**: すべてのステップが成功したことを確認
5. **報告**: ユーザーにサマリーを提供
```

## トラブルシューティング

### ツールが利用できない

**確認事項:**
- MCP サーバーが正しく設定されている
- サーバーが接続されている（`/mcp` で確認）
- ツール名が完全に一致する（大文字小文字を区別）
- 設定変更後に Claude Code を再起動

### ツール呼び出しが失敗する

**確認事項:**
- 認証が有効
- パラメータがツールスキーマに一致
- 必須パラメータが提供されている
- `claude --debug` のログを確認

### パフォーマンスの問題

**確認事項:**
- 個別の呼び出しではなくバッチクエリを使用
- 適切な場合に結果をキャッシュ
- 不必要なツール呼び出しをしていない
- 可能な場合は並列呼び出し

## まとめ

効果的な MCP ツールの使用には以下が必要です:
1. `/mcp` による**ツールスキーマの理解**
2. コマンドでの適切な**ツールの事前許可**
3. **適切なエラーハンドリング**
4. バッチ処理とキャッシュによる**パフォーマンスの最適化**
5. フィードバックと明確なエラーによる**良い UX の提供**
6. デプロイ前の**徹底的なテスト**

プラグインのコマンドとエージェントで堅牢な MCP ツール統合を実現するために、これらのパターンに従ってください。
