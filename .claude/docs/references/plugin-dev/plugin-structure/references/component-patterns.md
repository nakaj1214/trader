# コンポーネント組織化パターン

プラグインコンポーネントを効果的に組織化するための高度なパターンです。

## コンポーネントのライフサイクル

### 検出フェーズ

Claude Code が起動する際:

1. **有効なプラグインをスキャン**: 各プラグインの `.claude-plugin/plugin.json` を読み取る
2. **コンポーネントを検出**: デフォルトおよびカスタムパスを探索
3. **定義を解析**: YAML フロントマターと設定を読み取る
4. **コンポーネントを登録**: Claude Code で利用可能にする
5. **初期化**: MCP サーバーの起動、フックの登録

**タイミング**: コンポーネント登録は Claude Code の初期化時に行われ、継続的には行われません。

### 有効化フェーズ

コンポーネントが使用される際:

**コマンド**: ユーザーがスラッシュコマンドを入力 → Claude Code が検索 → 実行
**エージェント**: タスクが到着 → Claude Code が能力を評価 → エージェントを選択
**スキル**: タスクコンテキストが説明に一致 → Claude Code がスキルを読み込む
**フック**: イベント発生 → Claude Code がマッチするフックを呼び出す
**MCP サーバー**: ツール呼び出しがサーバー能力に一致 → サーバーに転送

## コマンド組織化パターン

### フラット構造

単一ディレクトリにすべてのコマンド:

```
commands/
├── build.md
├── test.md
├── deploy.md
├── review.md
└── docs.md
```

**使用する場面**:
- 合計 5〜15 コマンド
- すべてのコマンドが同じ抽象レベル
- 明確なカテゴリ分けがない

**利点**:
- シンプルでナビゲートしやすい
- 設定不要
- 高速な検出

### カテゴリ別構造

異なるコマンドタイプ用の複数ディレクトリ:

```
commands/              # コアコマンド
├── build.md
└── test.md

admin-commands/        # 管理用
├── configure.md
└── manage.md

workflow-commands/     # ワークフロー自動化
├── review.md
└── deploy.md
```

**マニフェスト設定**:
```json
{
  "commands": [
    "./commands",
    "./admin-commands",
    "./workflow-commands"
  ]
}
```

**使用する場面**:
- 15 以上のコマンド
- 明確な機能カテゴリ
- 異なる権限レベル

**利点**:
- 目的別に整理
- メンテナンスが容易
- ディレクトリごとにアクセスを制限可能

### 階層構造

複雑なプラグイン向けのネストされた組織化:

```
commands/
├── ci/
│   ├── build.md
│   ├── test.md
│   └── lint.md
├── deployment/
│   ├── staging.md
│   └── production.md
└── management/
    ├── config.md
    └── status.md
```

**注意**: Claude Code はネストされたコマンド検出を自動的にはサポートしません。カスタムパスを使用してください:

```json
{
  "commands": [
    "./commands/ci",
    "./commands/deployment",
    "./commands/management"
  ]
}
```

**使用する場面**:
- 20 以上のコマンド
- 多層的なカテゴリ分け
- 複雑なワークフロー

**利点**:
- 最大限の組織化
- 明確な境界
- スケーラブルな構造

## エージェント組織化パターン

### 役割ベースの組織化

主な役割でエージェントを整理:

```
agents/
├── code-reviewer.md        # コードをレビュー
├── test-generator.md       # テストを生成
├── documentation-writer.md # ドキュメントを作成
└── refactorer.md          # コードをリファクタリング
```

**使用する場面**:
- エージェントが重複しない明確な役割を持つ
- ユーザーが手動でエージェントを呼び出す
- 明確なエージェントの責務

### 能力ベースの組織化

特定の能力で整理:

```
agents/
├── python-expert.md        # Python 専門
├── typescript-expert.md    # TypeScript 専門
├── api-specialist.md       # API 設計
└── database-specialist.md  # データベース作業
```

**使用する場面**:
- テクノロジー固有のエージェント
- ドメイン専門知識にフォーカス
- 自動エージェント選択

### ワークフローベースの組織化

ワークフローの段階で整理:

```
agents/
├── planning-agent.md      # 計画フェーズ
├── implementation-agent.md # コーディングフェーズ
├── testing-agent.md       # テストフェーズ
└── deployment-agent.md    # デプロイフェーズ
```

**使用する場面**:
- 順序付きワークフロー
- 段階固有の専門知識
- パイプライン自動化

## スキル組織化パターン

### トピックベースの組織化

各スキルが特定のトピックをカバー:

```
skills/
├── api-design/
│   └── SKILL.md
├── error-handling/
│   └── SKILL.md
├── testing-strategies/
│   └── SKILL.md
└── performance-optimization/
    └── SKILL.md
```

**使用する場面**:
- ナレッジベースのスキル
- 教育的またはリファレンスコンテンツ
- 幅広い適用性

### ツールベースの組織化

特定のツールやテクノロジー向けのスキル:

```
skills/
├── docker/
│   ├── SKILL.md
│   └── references/
│       └── dockerfile-best-practices.md
├── kubernetes/
│   ├── SKILL.md
│   └── examples/
│       └── deployment.yaml
└── terraform/
    ├── SKILL.md
    └── scripts/
        └── validate-config.sh
```

**使用する場面**:
- ツール固有の専門知識
- 複雑なツール設定
- ツールのベストプラクティス

### ワークフローベースの組織化

完全なワークフロー向けのスキル:

```
skills/
├── code-review-workflow/
│   ├── SKILL.md
│   └── references/
│       ├── checklist.md
│       └── standards.md
├── deployment-workflow/
│   ├── SKILL.md
│   └── scripts/
│       ├── pre-deploy.sh
│       └── post-deploy.sh
└── testing-workflow/
    ├── SKILL.md
    └── examples/
        └── test-structure.md
```

**使用する場面**:
- マルチステッププロセス
- 企業固有のワークフロー
- プロセス自動化

### 充実したリソースを持つスキル

すべてのリソースタイプを含む包括的なスキル:

```
skills/
└── api-testing/
    ├── SKILL.md              # コアスキル（1500語）
    ├── references/
    │   ├── rest-api-guide.md
    │   ├── graphql-guide.md
    │   └── authentication.md
    ├── examples/
    │   ├── basic-test.js
    │   ├── authenticated-test.js
    │   └── integration-test.js
    ├── scripts/
    │   ├── run-tests.sh
    │   └── generate-report.py
    └── assets/
        └── test-template.json
```

**リソースの使い方**:
- **SKILL.md**: 概要とリソースの使用タイミング
- **references/**: 詳細ガイド（必要に応じて読み込み）
- **examples/**: コピー&ペースト可能なコードサンプル
- **scripts/**: 実行可能なテストランナー
- **assets/**: テンプレートと設定

## フック組織化パターン

### モノリシック設定

すべてのフックを含む単一の hooks.json:

```
hooks/
├── hooks.json     # すべてのフック定義
└── scripts/
    ├── validate-write.sh
    ├── validate-bash.sh
    └── load-context.sh
```

**hooks.json**:
```json
{
  "PreToolUse": [...],
  "PostToolUse": [...],
  "Stop": [...],
  "SessionStart": [...]
}
```

**使用する場面**:
- 合計 5〜10 フック
- シンプルなフックロジック
- 集中管理

### イベントベースの組織化

イベントタイプごとに個別ファイル:

```
hooks/
├── hooks.json              # すべてを統合
├── pre-tool-use.json      # PreToolUse フック
├── post-tool-use.json     # PostToolUse フック
├── stop.json              # Stop フック
└── scripts/
    ├── validate/
    │   ├── write.sh
    │   └── bash.sh
    └── context/
        └── load.sh
```

**hooks.json**（統合）:
```json
{
  "PreToolUse": ${file:./pre-tool-use.json},
  "PostToolUse": ${file:./post-tool-use.json},
  "Stop": ${file:./stop.json}
}
```

**注意**: ファイルの統合にはビルドスクリプトを使用してください。Claude Code はファイル参照をサポートしていません。

**使用する場面**:
- 10 以上のフック
- 異なるチームが異なるイベントを管理
- 複雑なフック設定

### 目的ベースの組織化

機能的な目的でグループ化:

```
hooks/
├── hooks.json
└── scripts/
    ├── security/
    │   ├── validate-paths.sh
    │   ├── check-credentials.sh
    │   └── scan-malware.sh
    ├── quality/
    │   ├── lint-code.sh
    │   ├── check-tests.sh
    │   └── verify-docs.sh
    └── workflow/
        ├── notify-team.sh
        └── update-status.sh
```

**使用する場面**:
- 多数のフックスクリプト
- 明確な機能的境界
- チームの専門化

## スクリプト組織化パターン

### フラットスクリプト

単一ディレクトリにすべてのスクリプト:

```
scripts/
├── build.sh
├── test.py
├── deploy.sh
├── validate.js
└── report.py
```

**使用する場面**:
- 5〜10 スクリプト
- すべてのスクリプトが関連
- シンプルなプラグイン

### カテゴリ別スクリプト

目的別にグループ化:

```
scripts/
├── build/
│   ├── compile.sh
│   └── package.sh
├── test/
│   ├── run-unit.sh
│   └── run-integration.sh
├── deploy/
│   ├── staging.sh
│   └── production.sh
└── utils/
    ├── log.sh
    └── notify.sh
```

**使用する場面**:
- 10 以上のスクリプト
- 明確なカテゴリ
- 再利用可能なユーティリティ

### 言語ベースの組織化

プログラミング言語別にグループ化:

```
scripts/
├── bash/
│   ├── build.sh
│   └── deploy.sh
├── python/
│   ├── analyze.py
│   └── report.py
└── javascript/
    ├── bundle.js
    └── optimize.js
```

**使用する場面**:
- 多言語のスクリプト
- 異なるランタイム要件
- 言語固有の依存関係

## クロスコンポーネントパターン

### 共有リソース

共通リソースを共有するコンポーネント:

```
plugin/
├── commands/
│   ├── test.md        # lib/test-utils.sh を使用
│   └── deploy.md      # lib/deploy-utils.sh を使用
├── agents/
│   └── tester.md      # lib/test-utils.sh を参照
├── hooks/
│   └── scripts/
│       └── pre-test.sh # lib/test-utils.sh を source
└── lib/
    ├── test-utils.sh
    └── deploy-utils.sh
```

**コンポーネントでの使い方**:
```bash
#!/bin/bash
source "${CLAUDE_PLUGIN_ROOT}/lib/test-utils.sh"
run_tests
```

**利点**:
- コードの再利用
- 一貫した動作
- メンテナンスの容易さ

### レイヤードアーキテクチャ

関心事をレイヤーに分離:

```
plugin/
├── commands/          # ユーザーインターフェース層
├── agents/            # オーケストレーション層
├── skills/            # ナレッジ層
└── lib/
    ├── core/         # コアビジネスロジック
    ├── integrations/ # 外部サービス
    └── utils/        # ヘルパー関数
```

**使用する場面**:
- 大規模プラグイン（100 以上のファイル）
- 複数の開発者
- 明確な関心の分離

### プラグイン内プラグイン

ネストされたプラグイン構造:

```
plugin/
├── .claude-plugin/
│   └── plugin.json
├── core/              # コア機能
│   ├── commands/
│   └── agents/
└── extensions/        # オプション拡張
    ├── extension-a/
    │   ├── commands/
    │   └── agents/
    └── extension-b/
        ├── commands/
        └── agents/
```

**マニフェスト**:
```json
{
  "commands": [
    "./core/commands",
    "./extensions/extension-a/commands",
    "./extensions/extension-b/commands"
  ]
}
```

**使用する場面**:
- モジュラーな機能
- オプション機能
- プラグインファミリー

## ベストプラクティス

### 命名

1. **一貫した命名**: ファイル名をコンポーネントの目的に一致させる
2. **説明的な名前**: コンポーネントの機能を示す
3. **略語を避ける**: 明確さのために完全な単語を使用する

### 組織化

1. **シンプルに始める**: フラット構造で始め、必要に応じて再編成
2. **関連アイテムをグループ化**: 関連するコンポーネントをまとめる
3. **関心を分離する**: 無関係な機能を混在させない

### スケーラビリティ

1. **成長を計画する**: スケールする構造を選択
2. **早期にリファクタリング**: 苦痛になる前に再編成する
3. **構造を文書化する**: README で組織化を説明する

### 保守性

1. **一貫したパターン**: 全体で同じ構造を使用
2. **ネストを最小限に**: ディレクトリの深さを管理可能に保つ
3. **規約を使用する**: コミュニティ標準に従う

### パフォーマンス

1. **深いネストを避ける**: 検出時間に影響
2. **カスタムパスを最小限に**: 可能な場合はデフォルトを使用
3. **設定を小さく保つ**: 大きな設定は読み込みを遅くする
