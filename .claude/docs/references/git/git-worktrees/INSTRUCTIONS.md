# Git Worktrees スキル

Git worktreesを使って、複数のブランチを並行で作業し、切り替えコストを下げる。

## 使う場面

1. 複数ブランチを同時に進めたいとき
2. レビュー中のPRと別作業を並行したいとき
3. サブエージェント並行作業を分離したいとき
4. 緊急バグ修正と新機能を同時に進めたいとき
5. 実験的変更を安全に隔離したいとき

## Git Worktreesとは

1つのGitリポジトリに対して、複数の作業ツリー（worktree）を作成できる仕組み。別ディレクトリで異なるブランチを同時に開ける。

```
my-project/           # メインworktree (main)
my-project-feature/   # 別worktree (feature-x)
my-project-hotfix/    # 別worktree (hotfix-123)
```

## 基本コマンド

### Worktreeの追加

```bash
# 既存ブランチを追加してworktree作成
git worktree add ../project-feature feature-branch

# 新しいブランチでworktree作成
git worktree add ../project-hotfix hotfix-branch

# 一時的な作業（ブランチを切らない）
git worktree add --detach ../project-temp
```

### Worktree一覧

```bash
git worktree list
# /path/to/project          abc1234 [main]
# /path/to/project-feature  def5678 [feature-x]
# /path/to/project-hotfix   ghi9012 [hotfix-123]
```

### Worktreeの削除

```bash
# worktreeを削除
git worktree remove ../project-feature

# 強制削除（作業中でも削除）
git worktree remove --force ../project-feature

# 参照が残ったworktreeを掃除
git worktree prune
```

## ディレクトリ構成パターン

### パターン1: 兄弟ディレクトリ

```
workspace/
  project/            # メイン (main)
  project-feature/    # 機能A
  project-bugfix/     # バグ修正
  project-experiment/ # 実験
```

### パターン2: サブディレクトリ

```
project/
  .git/              # 元のGit
  main/              # メインworktree
  feature/           # 機能worktree
  hotfix/            # 修正worktree
```

### パターン3: タスク別

```
project/
  .git/
  current/           # 現在作業中
  review/            # レビュー対応
  staging/           # ステージング用
```

## 実践例

### Example 1: 複数機能の並行開発

```bash
# メインリポジトリで開始
cd my-project

# 機能Aのworktree作成
git worktree add ../my-project-feature-a feature-a

# 機能Bのworktree作成
git worktree add ../my-project-feature-b feature-b

# それぞれのディレクトリで開発
# Terminal 1: cd ../my-project-feature-a && code .
# Terminal 2: cd ../my-project-feature-b && code .
```

### Example 2: 緊急バグ修正

```bash
# 進行中の作業を止めずにhotfix用worktree作成
git worktree add ../my-project-hotfix -b hotfix-urgent main

# hotfix作業
cd ../my-project-hotfix
# ... 修正作業 ...
git commit -m "Fix urgent bug"
git push origin hotfix-urgent

# メイン作業に戻る
cd ../my-project
```

### Example 3: サブエージェント並行開発

```bash
# バックエンド用worktree
git worktree add ../project-backend -b feature/backend main

# フロントエンド用worktree
git worktree add ../project-frontend -b feature/frontend main

# 各worktreeで作業
# Agent A: cd ../project-backend
# Agent B: cd ../project-frontend

# 作業完了後に統合
cd ../project
git merge feature/backend
git merge feature/frontend
```

## サブエージェント連携のルール

### 割り当てテンプレート

```markdown
## Worktree割り当て

### Agent A: Claude Code
- Worktree: ../project-backend
- ブランチ: feature/backend
- タスク: Task 1.1, 1.2, 1.3
- 担当: API実装

### Agent B: Codex CLI
- Worktree: ../project-frontend
- ブランチ: feature/frontend
- タスク: Task 2.1, 2.2, 2.3
- 担当: UI実装

### 同期ルール
1. 各worktreeでコミット
2. メインブランチへの直接pushは禁止
3. 作業完了後にPR作成
```

### 実行コマンド例

```bash
# Agent Aの作業
cd ../project-backend
codex exec --full-auto --sandbox write --cd . "Task 1.1を実装"

# Agent Bの作業
cd ../project-frontend
gemini "Task 2.1を実装"

# 統合（メインで実施）
cd ../project
git merge feature/backend
git merge feature/frontend
```

## 注意点

### やってはいけないこと

| NG | 理由 |
|-----|------|
| 同じブランチを複数worktreeで開く | Gitが混乱する |
| worktreeのディレクトリを手動削除 | 参照が残る |
| 長期間放置 | マージコンフリクトが増える |

### ベストプラクティス

| ルール | 理由 |
|------|------|
| 目的別に1worktree | 切り替えが楽 |
| 作業完了後は削除 | ディスク節約 |
| 定期的にprune | 参照の掃除 |
| 変更の多いworktreeは短命に | コンフリクト防止 |

## トラブルシューティング

### Worktreeが削除できない

```bash
# 強制削除
git worktree remove --force ../project-feature

# 残った参照を掃除
git worktree prune
```

### "already checked out" エラー

```bash
# どこで使用中か確認
git worktree list

# 使用中のworktreeを削除するか、別ブランチで追加する
```

### マージコンフリクト

```bash
# worktree内でコンフリクト解消
cd ../project-feature
git fetch origin
git rebase origin/main
# コンフリクト解消
git add .
git rebase --continue
```

## ワークフロー例

```
1. 計画作成（writing-plans）
2. タスクを分割し並行可能性を判断
3. Worktreeを作成（タスク/担当ごと）
4. 各worktreeで作業
5. レビューとテスト
6. メインブランチへ統合
7. Worktree削除と掃除
```

## 関連スキル

- [writing-plans](writing-plans.md): 進行計画の作成
- [implement-plans](implement-plans.md): 実行と検証
- [ai-cli-selector](ai-cli-selector.md): ツール選定
