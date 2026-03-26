主要なマイルストーンでの進捗を追跡するため、ワークフロースナップショットを管理する。

## 使い方

```
/checkpoint create <name>   - 現在の状態を名前付きチェックポイントとして保存
/checkpoint verify <name>   - 現在の状態と保存されたチェックポイントを比較
/checkpoint list            - 保存済みの全チェックポイントを表示
/checkpoint clear           - 古いチェックポイントを削除（最新5件を保持）
```

## 作成モード

1. クリーンな作業状態を確認する
2. チェックポイント名で git stash またはコミットを作成する
3. `.claude/checkpoints.log` に記録する:
   ```
   [timestamp] [name] [sha]
   ```

## 検証モード

保存されたチェックポイントと比較し、以下の変更を報告する:
- チェックポイント以降に変更されたファイル
- テスト結果（前後の比較）
- コードカバレッジメトリクス
- ビルドステータス

## 一覧モード

全チェックポイントを表示する:
```
CHECKPOINT          TIMESTAMP           SHA       STATUS
feature-start       2026-02-27 10:00   abc123    behind
auth-complete       2026-02-27 14:00   def456    current
```

## 典型的なチェックポイントフロー

```
/checkpoint create feature-start
# ... 認証を実装 ...
/checkpoint create auth-complete
/checkpoint verify feature-start    # 何が変わったかを表示
# ... UI を実装 ...
/checkpoint create ui-complete
# PR の準備完了
```

チェックポイントは git と統合されており、実装方針が変わった場合に戻ることができる回復可能な状態を作成する。
