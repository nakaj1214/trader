# 標準プラグインの例

コマンド、エージェント、スキルを備えた適切に構造化されたプラグインです。

## ディレクトリ構造

```
code-quality/
├── .claude-plugin/
│   └── plugin.json
├── commands/
│   ├── lint.md
│   ├── test.md
│   └── review.md
├── agents/
│   ├── code-reviewer.md
│   └── test-generator.md
├── skills/
│   ├── code-standards/
│   │   ├── SKILL.md
│   │   └── references/
│   │       └── style-guide.md
│   └── testing-patterns/
│       ├── SKILL.md
│       └── examples/
│           ├── unit-test.js
│           └── integration-test.js
├── hooks/
│   ├── hooks.json
│   └── scripts/
│       └── validate-commit.sh
└── scripts/
    ├── run-linter.sh
    └── generate-report.py
```

## ファイルの内容

### .claude-plugin/plugin.json

```json
{
  "name": "code-quality",
  "version": "1.0.0",
  "description": "Comprehensive code quality tools including linting, testing, and review automation",
  "author": {
    "name": "Quality Team",
    "email": "quality@example.com"
  },
  "homepage": "https://docs.example.com/plugins/code-quality",
  "repository": "https://github.com/example/code-quality-plugin",
  "license": "MIT",
  "keywords": ["code-quality", "linting", "testing", "code-review", "automation"]
}
```

### commands/lint.md

```markdown
---
name: lint
description: コードベースに対してリントチェックを実行する
---

# Lint コマンド

プロジェクトのコードベースに対して包括的なリントチェックを実行します。

## プロセス

1. プロジェクトタイプとインストール済みリンターを検出
2. 適切なリンターを実行（ESLint、Pylint、RuboCop など）
3. 結果を収集しフォーマット
4. ファイル位置と重大度とともに問題を報告

## 実装

リンティングスクリプトを実行します:

\`\`\`bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/run-linter.sh
\`\`\`

出力を解析し、以下の分類で問題を提示します:
- 重大な問題（修正必須）
- 警告（修正推奨）
- スタイル提案（任意）

各問題について以下を表示:
- ファイルパスと行番号
- 問題の説明
- 修正提案（利用可能な場合）
```

### commands/test.md

```markdown
---
name: test
description: カバレッジレポート付きでテストスイートを実行する
---

# Test コマンド

プロジェクトのテストスイートを実行し、カバレッジレポートを生成します。

## プロセス

1. テストフレームワークを特定（Jest、pytest、RSpec など）
2. すべてのテストを実行
3. カバレッジレポートを生成
4. テストされていないコードを特定

## 出力

構造化されたフォーマットで結果を提示:
- テストサマリー（合格/失敗/スキップ）
- ファイル別カバレッジ率
- 重要なテスト未実施領域
- 失敗したテストの詳細

## 統合

テスト完了後、以下を提案:
- 失敗したテストの修正
- テストされていないコードのテスト生成（test-generator エージェントを使用）
- テスト変更に基づくドキュメントの更新
```

### agents/code-reviewer.md

```markdown
---
description: バグ、セキュリティ問題、改善機会の特定に特化したエキスパートコードレビューエージェント
capabilities:
  - 潜在的なバグとロジックエラーのコード分析
  - セキュリティ脆弱性の特定
  - パフォーマンス改善の提案
  - プロジェクト標準への準拠確認
  - テストカバレッジの妥当性レビュー
---

# コードレビューエージェント

包括的なコードレビューに特化したエージェントです。

## 専門領域

- **バグ検出**: ロジックエラー、エッジケース、エラーハンドリング
- **セキュリティ分析**: インジェクション脆弱性、認証問題、データ露出
- **パフォーマンス**: アルゴリズムの効率性、リソース使用、最適化の機会
- **標準準拠**: スタイルガイドの遵守、命名規則、ドキュメント
- **テストカバレッジ**: テストケースの妥当性、不足シナリオ

## レビュープロセス

1. **初期スキャン**: 明らかな問題の迅速なチェック
2. **深い分析**: 変更されたコードの行ごとのレビュー
3. **コンテキスト評価**: 関連コードへの影響チェック
4. **ベストプラクティス**: プロジェクトと言語の標準との比較
5. **推奨事項**: 優先度付きの改善リスト

## スキルとの統合

プロジェクト固有のガイドラインのために `code-standards` スキルを自動的に読み込みます。

## 出力フォーマット

レビューしたファイルごとに:
- 全体的な評価
- 重大な問題（マージ前に修正必須）
- 重要な問題（修正推奨）
- 提案（あると良い）
- ポジティブなフィードバック（良かった点）
```

### agents/test-generator.md

```markdown
---
description: コード分析から包括的なテストスイートを生成するエージェント
capabilities:
  - コード構造とロジックフローの分析
  - 関数とメソッドのユニットテスト生成
  - モジュールの統合テスト作成
  - エッジケースとエラー条件のテスト設計
  - テストフィクスチャとモックの提案
---

# テスト生成エージェント

包括的なテストスイートの生成に特化したエージェントです。

## 専門領域

- **ユニットテスト**: 個別の関数/メソッドのテスト
- **統合テスト**: モジュール間のインタラクションテスト
- **エッジケース**: 境界条件、エラーパス
- **テスト構成**: 適切なテスト構造と命名
- **モッキング**: モックとスタブの適切な使用

## 生成プロセス

1. **コード分析**: 関数の目的とロジックを理解
2. **パス特定**: すべての実行パスをマッピング
3. **入力設計**: すべてのパスをカバーするテスト入力を作成
4. **アサーション設計**: 期待される出力を定義
5. **テスト生成**: プロジェクトのフレームワークでテストを記述

## スキルとの統合

プロジェクト固有のテスト規約のために `testing-patterns` スキルを自動的に読み込みます。

## テスト品質

生成されるテストに含まれるもの:
- ハッピーパスのシナリオ
- エッジケースと境界条件
- エラーハンドリングの検証
- 外部依存関係のモックデータ
- 明確なテスト説明
```

### skills/code-standards/SKILL.md

```markdown
---
name: Code Standards
description: This skill should be used when reviewing code, enforcing style guidelines, checking naming conventions, or ensuring code quality standards. Provides project-specific coding standards and best practices.
version: 1.0.0
---

# コーディング標準

コード品質を維持するための包括的なコーディング標準とベストプラクティスです。

## 概要

以下のための標準化された規約による一貫したコード品質の強制:
- コードスタイルとフォーマット
- 命名規則
- ドキュメント要件
- エラーハンドリングパターン
- セキュリティプラクティス

## スタイルガイドライン

### フォーマット

- **インデント**: 2スペース（JavaScript/TypeScript）、4スペース（Python）
- **行の長さ**: 最大100文字
- **ブレース**: 開きブレースは同一行（K&R スタイル）
- **空白**: カンマの後、演算子の前後にスペース

### 命名規則

- **変数**: JavaScript は camelCase、Python は snake_case
- **関数**: camelCase、説明的な動詞-名詞ペア
- **クラス**: PascalCase
- **定数**: UPPER_SNAKE_CASE
- **ファイル**: モジュールは kebab-case

## ドキュメント要件

### 関数のドキュメント

すべての関数に含めるべき内容:
- 目的の説明
- 型付きのパラメータ説明
- 型付きの戻り値の説明
- 使用例（公開関数の場合）

### モジュールのドキュメント

すべてのモジュールに含めるべき内容:
- モジュールの目的
- 公開 API の概要
- 使用例
- 依存関係

## エラーハンドリング

### 必須プラクティス

- エラーを黙って飲み込まない
- 常にコンテキスト付きでエラーをログに記録
- 具体的なエラー型を使用する
- アクション可能なエラーメッセージを提供する
- finally ブロックでリソースをクリーンアップする

### パターン例

\`\`\`javascript
async function processData(data) {
  try {
    const result = await transform(data)
    return result
  } catch (error) {
    logger.error('Data processing failed', {
      data: sanitize(data),
      error: error.message,
      stack: error.stack
    })
    throw new DataProcessingError('Failed to process data', { cause: error })
  }
}
\`\`\`

## セキュリティプラクティス

- すべての外部入力をバリデーションする
- 出力前にデータをサニタイズする
- パラメータ化クエリを使用する
- 機密情報をログに記録しない
- 依存関係を最新に保つ

## 詳細ガイドライン

言語別の包括的なスタイルガイドについては:
- `references/style-guide.md`
```

### skills/code-standards/references/style-guide.md

```markdown
# 包括的スタイルガイド

サポートされるすべての言語の詳細なスタイルガイドラインです。

## JavaScript/TypeScript

### 変数宣言

デフォルトで `const` を使用し、再代入が必要な場合のみ `let`、`var` は使用しない:

\`\`\`javascript
// Good
const MAX_RETRIES = 3
let currentTry = 0

// Bad
var MAX_RETRIES = 3
\`\`\`

### 関数宣言

一貫性のために関数式を使用:

\`\`\`javascript
// Good
const calculateTotal = (items) => {
  return items.reduce((sum, item) => sum + item.price, 0)
}

// Bad (inconsistent style)
function calculateTotal(items) {
  return items.reduce((sum, item) => sum + item.price, 0)
}
\`\`\`

### Async/Await

Promise チェーンよりも async/await を優先:

\`\`\`javascript
// Good
async function fetchUserData(userId) {
  const user = await db.getUser(userId)
  const orders = await db.getOrders(user.id)
  return { user, orders }
}

// Bad
function fetchUserData(userId) {
  return db.getUser(userId)
    .then(user => db.getOrders(user.id)
      .then(orders => ({ user, orders })))
}
\`\`\`

## Python

### インポートの整理

インポートの順序: 標準ライブラリ、サードパーティ、ローカル:

\`\`\`python
# Good
import os
import sys

import numpy as np
import pandas as pd

from app.models import User
from app.utils import helper

# Bad - mixed order
from app.models import User
import numpy as np
import os
\`\`\`

### 型ヒント

すべての関数シグネチャに型ヒントを使用:

\`\`\`python
# Good
def calculate_average(numbers: list[float]) -> float:
    return sum(numbers) / len(numbers)

# Bad
def calculate_average(numbers):
    return sum(numbers) / len(numbers)
\`\`\`

## その他の言語

言語固有のガイドについては:
- Go: `references/go-style.md`
- Rust: `references/rust-style.md`
- Ruby: `references/ruby-style.md`
```

### hooks/hooks.json

```json
{
  "PreToolUse": [
    {
      "matcher": "Write|Edit",
      "hooks": [
        {
          "type": "prompt",
          "prompt": "Before modifying code, verify it meets our coding standards from the code-standards skill. Check formatting, naming conventions, and documentation. If standards aren't met, suggest improvements.",
          "timeout": 30
        }
      ]
    }
  ],
  "Stop": [
    {
      "matcher": ".*",
      "hooks": [
        {
          "type": "command",
          "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/validate-commit.sh",
          "timeout": 45
        }
      ]
    }
  ]
}
```

### hooks/scripts/validate-commit.sh

```bash
#!/bin/bash
# Validate code quality before task completion

set -e

# Check if there are any uncommitted changes
if [[ -z $(git status -s) ]]; then
  echo '{"systemMessage": "No changes to validate. Task complete."}'
  exit 0
fi

# Run linter on changed files
CHANGED_FILES=$(git diff --name-only --cached | grep -E '\.(js|ts|py)$' || true)

if [[ -z "$CHANGED_FILES" ]]; then
  echo '{"systemMessage": "No code files changed. Validation passed."}'
  exit 0
fi

# Run appropriate linters
ISSUES=0

for file in $CHANGED_FILES; do
  case "$file" in
    *.js|*.ts)
      if ! npx eslint "$file" --quiet; then
        ISSUES=$((ISSUES + 1))
      fi
      ;;
    *.py)
      if ! python -m pylint "$file" --errors-only; then
        ISSUES=$((ISSUES + 1))
      fi
      ;;
  esac
done

if [[ $ISSUES -gt 0 ]]; then
  echo "{\"systemMessage\": \"Found $ISSUES code quality issues. Please fix before completing.\"}"
  exit 1
fi

echo '{"systemMessage": "Code quality checks passed. Ready to commit."}'
exit 0
```

## 使用例

### コマンドの実行

```
$ claude
> /lint
リントチェックを実行中...

重大な問題 (2):
  src/api/users.js:45 - SQL インジェクション脆弱性
  src/utils/helpers.js:12 - 未処理の Promise rejection

警告 (5):
  src/components/Button.tsx:23 - PropTypes が未定義
  ...

スタイル提案 (8):
  src/index.js:1 - let の代わりに const を使用
  ...

> /test
テストスイートを実行中...

テスト結果:
  ✓ 245 合格
  ✗ 3 失敗
  ○ 2 スキップ

カバレッジ: 87.3%

テストされていないファイル:
  src/utils/cache.js - 0% カバレッジ
  src/api/webhooks.js - 23% カバレッジ

失敗したテスト:
  1. User API › GET /users › ページネーションを処理するべき
     期待値 200、実際値 500
  ...
```

### エージェントの使用

```
> src/api/users.js の変更をレビューしてください

[code-reviewer エージェントが自動選択]

コードレビュー: src/api/users.js

重大な問題:
  1. 45行目: SQL インジェクション脆弱性
     - SQL クエリに文字列連結を使用
     - パラメータ化クエリに置き換え
     - 優先度: 重大

  2. 67行目: エラーハンドリングの欠如
     - try/catch なしのデータベースクエリ
     - DB エラー時にサーバーがクラッシュする可能性
     - 優先度: 高

提案:
  1. 23行目: ユーザーデータのキャッシュを検討
     - 同じユーザーへの頻繁な DB クエリ
     - Redis キャッシュレイヤーを追加
     - 優先度: 中
```

## 主なポイント

1. **完全なマニフェスト**: すべての推奨メタデータフィールド
2. **複数のコンポーネント**: コマンド、エージェント、スキル、フック
3. **充実したスキル**: 詳細情報のためのリファレンスと例
4. **自動化**: フックが標準を自動的に強制
5. **統合**: コンポーネントが連携して動作

## このパターンを使用する場面

- 配布用の本番プラグイン
- チームコラボレーションツール
- 一貫性の強制が必要なプラグイン
- 複数のエントリポイントを持つ複雑なワークフロー
