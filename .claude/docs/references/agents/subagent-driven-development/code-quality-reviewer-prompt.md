# コード品質レビュアー プロンプトテンプレート

コード品質レビュアーのサブエージェントをディスパッチする際にこのテンプレートを使用します。

**目的:** 実装が適切に構築されているか（クリーン、テスト済み、保守可能）を検証する

**仕様準拠レビューがパスした後にのみディスパッチすること。**

```
Task tool (superpowers:code-reviewer):
  Use template at requesting-code-review/code-reviewer.md

  WHAT_WAS_IMPLEMENTED: [実装者のレポートから]
  PLAN_OR_REQUIREMENTS: [計画ファイル]のタスク N
  BASE_SHA: [タスク前のコミット]
  HEAD_SHA: [現在のコミット]
  DESCRIPTION: [タスクの概要]
```

**コードレビュアーの返却内容:** 良い点、問題点（クリティカル/重要/軽微）、評価
