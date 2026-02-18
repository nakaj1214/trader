---
name: writing-plans
description: 実装計画の作成 - タスクを2〜5分の具体的手順に分解し、チェックポイント付きの実行可能な計画を作る。
---

# 計画作成スキル

大きなタスクを小さな実行単位に分解し、明確な計画を作るプロセス。

## 使う場面

1. 新機能実装を始めるとき
2. リファクタの計画を立てるとき
3. 複数ファイルにまたがる変更
4. チームで作業分担するとき

## 計画の原則

### 良い計画の特徴

| 特徴 | 説明 |
|----------------|-------------|
| 具体的 | 「UI改善」ではなく「ボタン色を#3B82F6に変更」 |
| 測定可能 | 完了判定が明確 |
| 独立実行 | 各タスクを単独で実行・検証できる |
| 適切な粒度 | 2〜5分で完了 |
| 順序が明確 | 依存関係が整理されている |

### 悪い計画の兆候

- 「〜を考える」「〜を検討する」が多い
- 1タスクが30分以上
- 完了条件が曖昧
- 依存関係が複雑すぎる

## 計画テンプレート

### 基本形式

```markdown
# [Feature Name] Implementation Plan

## Overview
- Purpose: [1文で説明]
- Estimate: [合計時間]
- Scope: [変更するファイル/モジュール]

## Prerequisites
- [ ] [準備1]
- [ ] [準備2]

## Task List

### Phase 1: [Phase Name]

#### Task 1.1: [Task Name]
- Description: [具体的な作業内容]
- File: [対象ファイルパス]
- Completion condition: [完了判定]
- Estimate: [時間]

#### Task 1.2: [Task Name]
...

### Phase 2: [Phase Name]
...

## Checkpoints
- [ ] Phase 1 complete: [検証方法]
- [ ] Phase 2 complete: [検証方法]
- [ ] All complete: [最終検証]

## Risks and Mitigations
| Risk | Mitigation |
|------|------------|
| [Risk 1] | [Mitigation 1] |

## Rollback Plan
[問題発生時の復旧手順]
```

## 分解テクニック

### 1. 機能分解

```
Feature: User Registration
  Backend
    Create API endpoint
    Implement validation
    DB save processing
  Frontend
    Form component
    Input validation
    API call
  Tests
    Unit tests
    E2E tests
```

### 2. 影響範囲分解

```
Change: Switch auth to JWT
  Identify affected files
  Modify auth middleware
  Update existing endpoints
  Frontend token management
  Migrate existing sessions
```

### 3. リスクベース分解

```
Priority: 高リスクを先に実施
1. [High risk] DBスキーマ変更 -> 先に検証
2. [Medium risk] API変更 -> 互換性確認
3. [Low risk] UI調整 -> 最後に実施
```

## 実践例

### 例: 検索機能追加

```markdown
# Search Feature Implementation Plan

## Overview
- Purpose: 記事のキーワード検索を可能にする
- Estimate: 2 hours
- Scope: api/, components/, pages/

## Task List

### Phase 1: Backend (45 min)

#### Task 1.1: 検索APIエンドポイント作成
- File: api/search.ts
- Content: GET /api/search?q=keyword
- Completion condition: curlでレスポンスが返る
- Estimate: 15 min

#### Task 1.2: 検索ロジック実装
- File: lib/search.ts
- Content: タイトル/本文の部分一致検索
- Completion condition: Unit testsが通る
- Estimate: 20 min

#### Task 1.3: APIテスト作成
- File: tests/api/search.test.ts
- Completion condition: npm testが通る
- Estimate: 10 min

### Phase 2: Frontend (45 min)

#### Task 2.1: 検索バーコンポーネント作成
- File: components/SearchBar.tsx
- Content: 入力欄と検索ボタン
- Completion condition: Storybookで表示確認
- Estimate: 15 min

#### Task 2.2: 検索結果表示
- File: components/SearchResults.tsx
- Content: 結果一覧とハイライト
- Completion condition: モックデータで表示確認
- Estimate: 15 min

#### Task 2.3: ページ統合
- File: pages/search.tsx
- Content: 検索バーと結果を統合
- Completion condition: /searchでアクセス可能
- Estimate: 15 min

### Phase 3: 統合テスト (30 min)

#### Task 3.1: E2Eテスト作成
- File: e2e/search.spec.ts
- Completion condition: npm run e2eが通る
- Estimate: 20 min

#### Task 3.2: パフォーマンス検証
- Content: 1000件で応答時間測定
- Completion condition: 200ms以下
- Estimate: 10 min

## Checkpoints
- [ ] Phase 1完了: API単体の動作確認
- [ ] Phase 2完了: モックデータでUI確認
- [ ] All complete: 本番データで検索実行

## Risks and Mitigations
| Risk | Mitigation |
|------|------------|
| 大量データで遅い | インデックス追加検討 |
| 文字エンコード問題 | UTF-8を検証 |

## Rollback Plan
- APIエンドポイント削除
- UI変更を戻す
- DBインデックスは残してもよい
```

## タスク見積もり

### 見積もりの目安

| タスク種別 | 目安時間 |
|-----------|--------------|
| 単純なファイル追加 | 2〜5分 |
| 既存コード修正 | 5〜10分 |
| 新規ロジック実装 | 10〜20分 |
| テスト作成 | 5〜15分 |
| 統合/調整 | 10〜20分 |

### バッファの考え方

```
実見積もり * 1.5 = 計画上の見積もり

理由:
- 想定外の問題
- 割り込み
- レビュー/確認時間
```

## 計画の更新

計画は生きたドキュメント。実装中に更新する:

```markdown
## Change History

### [Date/time] Changed by: [Name]
- Task 1.3を分割（想定より複雑）
- Task 2.2の見積を15分 -> 25分に変更
- Task 3.3を追加（性能改善が必要）
```

## 関連スキル

- [brainstorming](brainstorming.md): 計画前に要件を明確化
- [executing-plans](executing-plans.md): 作成した計画を実行
- [tdd-workflow](tdd-workflow.md): テスト駆動で実装
