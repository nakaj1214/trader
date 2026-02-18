---
name: pwf
description: ファイルで計画管理 - 3つのMarkdownファイル（task_plan/findings/progress）で文脈を保持し、セッションをまたいで作業を継続する。
---

# ファイルで計画管理 スキル

永続Markdownファイルで計画と文脈を管理する。セッションが切れても作業を継続できる。

## 使う場面

1. 長時間タスクがセッション制限を超えそうなとき
2. 作業が複数セッションにまたがるとき
3. 調査結果を蓄積したいとき
4. 進捗を可視化したいとき
5. チームと状況を共有したいとき

## 3ファイル・パターン

### 1. task_plan.md - 計画とフェーズ管理

```markdown
# Task Plan

## Overview
- Task: [Task name]
- Purpose: [1文で説明]
- Start: [Date/time]

## Phases

### Phase 1: Research [完了]
- [x] 要件確認
- [x] 既存コード調査
- [x] 制約の特定

### Phase 2: Design [進行中]
- [x] アーキテクチャ判断
- [ ] インターフェース設計
- [ ] テスト計画

### Phase 3: Implementation [未着手]
- [ ] コア機能実装
- [ ] テスト作成
- [ ] リファクタ

### Phase 4: Review [未着手]
- [ ] コードレビュー
- [ ] ドキュメント更新
- [ ] PR作成

## Decisions
- [Decision 1]: [Reason]
- [Decision 2]: [Reason]

## Open Questions
- [ ] [Question 1]
- [ ] [Question 2]
```

### 2. findings.md - 調査結果の蓄積

```markdown
# Findings

## Codebase Research

### Authentication Module
- Location: `src/auth/`
- Method: JWT + Refresh tokens
- Related files:
  - `auth.service.ts` - Auth logic
  - `auth.guard.ts` - Guards
  - `auth.dto.ts` - Data structures

### Database Structure
```sql
-- Users table
CREATE TABLE users (
  id UUID PRIMARY KEY,
  email VARCHAR UNIQUE,
  ...
);
```

## External Research

### Reference Documentation
- [Official docs](url): [Summary]
- [Blog article](url): [Summary]

### Similar Implementations
- [Project A]: [What we can learn]

## Important Discoveries
1. [Discovery 1]: [Impact]
2. [Discovery 2]: [Impact]

## Notes
- [Note 1]
- [Note 2]
```

### 3. progress.md - セッションログ

```markdown
# Progress Log

## Current Status
- Last updated: [Date/time]
- Current phase: Phase 2
- Next action: [Specific next step]

---

## Session 3 (2024-01-25 14:00-16:00)

### Completed
- Phase 2のインターフェース設計を完了
- テスト計画のドラフト作成

### Issues Encountered
- [Issue]: [Resolution/Unresolved]

### Next Session TODO
1. [ ] 残りのPhase 2タスク
2. [ ] Phase 3開始

---

## Session 2 (2024-01-25 10:00-12:00)

### Completed
- Phase 1完了
- アーキテクチャ判断

### Notes
- [Observations]

---

## Session 1 (2024-01-24 15:00-17:00)

### Completed
- 初期調査を開始
- 要件を確認
```

## 初期化テンプレート

### セッション開始

```bash
# ファイルがなければ作成
if [ ! -f task_plan.md ]; then
  cat > task_plan.md << 'EOF'
# Task Plan

## Overview
- Task:
- Purpose:
- Start:

## Phases

### Phase 1: Research [進行中]
- [ ] 要件確認
- [ ] 既存コード調査

### Phase 2: Design [未着手]
- [ ] 設計判断

### Phase 3: Implementation [未着手]
- [ ] 実装

## Decisions

## Open Questions
EOF
fi
```

## ワークフロー

### セッション開始

```markdown
## Session Start Checklist

1. [ ] progress.mdを確認して前回の状態を把握
2. [ ] task_plan.mdで現在フェーズを確認
3. [ ] findings.mdで蓄積情報を思い出す
4. [ ] 次のアクションを特定
5. [ ] 作業開始
```

### 作業中

```markdown
## Working Rules

### 発見があったら
- findings.mdに追記

### タスク完了時
- task_plan.mdのチェックを更新

### 判断をしたら
- task_plan.mdのDecisionsに追記

### 問題が起きたら
- progress.mdに記録
```

### セッション終了

```markdown
## Session End Checklist

1. [ ] progress.mdにサマリー追加
2. [ ] task_plan.mdの進捗更新
3. [ ] 次のアクションを明確化
4. [ ] 未解決の質問を記録
```

## 実践例

### 例: API開発プロジェクト

**task_plan.md**
```markdown
# REST API Development Plan

## Overview
- Task: ユーザー管理API開発
- Purpose: CRUD操作APIを提供
- Start: 2024-01-25

## Phases

### Phase 1: Research [完了]
- [x] 既存APIパターン確認
- [x] 認証方式の確認
- [x] DB構造の確認

### Phase 2: Design [完了]
- [x] エンドポイント設計
- [x] レスポンス形式決定
- [x] エラーハンドリング設計

### Phase 3: Implementation [進行中]
- [x] GET /users
- [x] GET /users/:id
- [ ] POST /users
- [ ] PUT /users/:id
- [ ] DELETE /users/:id

## Decisions
- Response format: JSON API specification compliant
- Authentication: Bearer token required
- Pagination: Cursor-based
```

**findings.md**
```markdown
# Findings

## Existing API Patterns

### Endpoint Naming Rules
- Resource names are plural: `/users`, `/posts`
- Nesting limited to 2 levels: `/users/:id/posts`

### Response Format
```json
{
  "data": { ... },
  "meta": { "total": 100, "page": 1 }
}
```

### Error Format
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input",
    "details": [...]
  }
}
```

## Authentication

- Method: JWT
- Header: `Authorization: Bearer <token>`
- Expiration: 1 hour
- Refresh: `/auth/refresh`
```

**progress.md**
```markdown
# Progress Log

## Current Status
- Last updated: 2024-01-25 15:30
- Current phase: Phase 3 Implementation
- Next action: Implement POST /users

---

## Session 2 (2024-01-25 14:00-15:30)

### Completed
- GET /users実装とテスト完了
- GET /users/:id実装とテスト完了

### Next Session TODO
1. [ ] POST /users実装
2. [ ] バリデーション追加
```

## 復旧手順

### セッションが切れたとき

```markdown
## Recovery Checklist

1. progress.mdの「Current Status」を確認
2. 「Next action」を読む
3. task_plan.mdで全体進捗を確認
4. findings.mdで必要情報を確認
5. 作業再開
```

### 再開プロンプト例

```
前回のセッションから再開します。

progress.mdによると:
- Current: Phase 3 Implementation
- Next action: Implement POST /users

task_plan.mdによると:
- GET /users 完了
- GET /users/:id 完了
- POST /users ここから開始

POST /usersの実装を開始します。
```

## 注意点

- ファイルは必ずコミットする（gitで管理）
- 冗長でも明確に書く
- 略語を避け、未来の自分が理解できるようにする
- 定期的にバックアップ

## 関連スキル

- [writing-plans](writing-plans.md): 詳細な計画作成
- [executing-plans](executing-plans.md): 計画実行
- [systematic-debugging](systematic-debugging.md): 問題の記録
