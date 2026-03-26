# コードレビューのリクエスト

コードレビュアーのサブエージェントを起動して、問題が連鎖する前に捕捉する。

**核心原則:** 早めにレビュー、頻繁にレビュー。

## レビューをリクエストする場面

**必須:**
- サブエージェント駆動開発の各タスク後
- 主要な機能を完了した後
- mainへのマージ前

**任意だが価値がある:**
- 行き詰まった時（新鮮な視点）
- リファクタリング前（ベースラインチェック）
- 複雑なバグ修正後

## リクエスト方法

**1. git SHAを取得:**
```bash
BASE_SHA=$(git rev-parse HEAD~1)  # または origin/main
HEAD_SHA=$(git rev-parse HEAD)
```

**2. code-reviewerサブエージェントを起動:**

`code-reviewer.md` のテンプレートを使ってTaskツールでサブエージェントを起動する

**プレースホルダー:**
- `{WHAT_WAS_IMPLEMENTED}` - 何を構築したか
- `{PLAN_OR_REQUIREMENTS}` - 何をすべきだったか
- `{BASE_SHA}` - 開始コミット
- `{HEAD_SHA}` - 終了コミット
- `{DESCRIPTION}` - 簡単なまとめ

**3. フィードバックに対応:**
- Critical問題は即座に修正
- Important問題は先に進む前に修正
- Minor問題は後で対処するメモ
- レビュアーが間違っている場合は（根拠を持って）反論

## 例

```
[タスク2完了: 検証関数を追加]

あなた: 先に進む前にコードレビューをリクエストします。

BASE_SHA=$(git log --oneline | grep "Task 1" | head -1 | awk '{print $1}')
HEAD_SHA=$(git rev-parse HEAD)

[code-reviewerサブエージェントを起動]
  WHAT_WAS_IMPLEMENTED: 会話インデックスの検証と修復関数
  PLAN_OR_REQUIREMENTS: docs/plans/deployment-plan.md のタスク2
  BASE_SHA: a7981ec
  HEAD_SHA: 3df7661
  DESCRIPTION: 4種類の問題タイプを持つverifyIndex()とrepairIndex()を追加

[サブエージェントが返す]:
  強み: クリーンなアーキテクチャ、実際のテスト
  問題:
    Important: 進捗インジケーターが不足
    Minor: レポート間隔のマジックナンバー（100）
  評価: 続行可能

あなた: [進捗インジケーターを修正]
[タスク3へ続く]
```

## ワークフローとの統合

**サブエージェント駆動開発:**
- 各タスク後にレビュー
- 問題が複合する前に捕捉
- 次のタスクに移る前に修正

**計画実行:**
- 各バッチ後にレビュー（3タスクごと）
- フィードバックを受けて適用、続行

**アドホック開発:**
- マージ前にレビュー
- 行き詰まった時にレビュー

## 危険サイン

**絶対にNG:**
- 「簡単だから」という理由でレビューをスキップする
- Critical問題を無視する
- 未修正のImportant問題で進む
- 有効な技術的フィードバックに反論する

**レビュアーが間違っている場合:**
- 技術的な根拠で反論する
- 動作するコード/テストを示す
- 明確化をリクエストする

テンプレートはこちら: requesting-code-review/code-reviewer.md
