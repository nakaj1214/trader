# CLAUDE.md テンプレート

## 主要原則

- **簡潔**: 密度が高く人間が読みやすい内容、可能な限り1行1コンセプト
- **実行可能**: コマンドはコピー＆ペーストで使えること
- **プロジェクト固有**: 汎用的なアドバイスではなく、このプロジェクト固有のパターンをドキュメント化
- **最新**: すべての情報が実際のコードベースの状態を反映していること

---

## 推奨セクション

プロジェクトに関連するセクションのみ使用してください。すべてのセクションが必要なわけではありません。

### コマンド

プロジェクトでの作業に必要な重要なコマンドをドキュメント化します。

```markdown
## Commands

| Command | Description |
|---------|-------------|
| `<install command>` | Install dependencies |
| `<dev command>` | Start development server |
| `<build command>` | Production build |
| `<test command>` | Run tests |
| `<lint command>` | Lint/format code |
```

### アーキテクチャ

Claude がファイルの場所を理解できるよう、プロジェクト構造を記述します。

```markdown
## Architecture

```
<root>/
  <dir>/    # <purpose>
  <dir>/    # <purpose>
  <dir>/    # <purpose>
```
```

### 重要なファイル

Claude が知っておくべき重要なファイルを一覧にします。

```markdown
## Key Files

- `<path>` - <purpose>
- `<path>` - <purpose>
```

### コードスタイル

プロジェクト固有のコーディング規約をドキュメント化します。

```markdown
## Code Style

- <convention>
- <convention>
- <preference over alternative>
```

### 環境

必要な環境変数とセットアップをドキュメント化します。

```markdown
## Environment

Required:
- `<VAR_NAME>` - <purpose>
- `<VAR_NAME>` - <purpose>

Setup:
- <setup step>
```

### テスト

テストのアプローチとコマンドをドキュメント化します。

```markdown
## Testing

- `<test command>` - <what it tests>
- <testing convention or pattern>
```

### 落とし穴

非自明なパターン、特殊な動作、注意事項をドキュメント化します。

```markdown
## Gotchas

- <non-obvious thing that causes issues>
- <ordering dependency or prerequisite>
- <common mistake to avoid>
```

### ワークフロー

開発ワークフローのパターンをドキュメント化します。

```markdown
## Workflow

- <when to do X>
- <preferred approach for Y>
```

---

## テンプレート: プロジェクトルート（最小構成）

```markdown
# <Project Name>

<One-line description>

## Commands

| Command | Description |
|---------|-------------|
| `<command>` | <description> |

## Architecture

```
<structure>
```

## Gotchas

- <gotcha>
```

---

## テンプレート: プロジェクトルート（包括的）

```markdown
# <Project Name>

<One-line description>

## Commands

| Command | Description |
|---------|-------------|
| `<command>` | <description> |

## Architecture

```
<structure with descriptions>
```

## Key Files

- `<path>` - <purpose>

## Code Style

- <convention>

## Environment

- `<VAR>` - <purpose>

## Testing

- `<command>` - <scope>

## Gotchas

- <gotcha>
```

---

## テンプレート: パッケージ/モジュール

モノレポ内のパッケージや独立したモジュール用。

```markdown
# <Package Name>

<Purpose of this package>

## Usage

```
<import/usage example>
```

## Key Exports

- `<export>` - <purpose>

## Dependencies

- `<dependency>` - <why needed>

## Notes

- <important note>
```

---

## テンプレート: モノレポルート

```markdown
# <Monorepo Name>

<Description>

## Packages

| Package | Description | Path |
|---------|-------------|------|
| `<name>` | <purpose> | `<path>` |

## Commands

| Command | Description |
|---------|-------------|
| `<command>` | <description> |

## Cross-Package Patterns

- <shared pattern>
- <generation/sync pattern>
```

---

## 更新の原則

CLAUDE.md を更新する際:

1. **具体的に**: このプロジェクトの実際のファイルパス、実際のコマンドを使用する
2. **最新に**: 実際のコードベースに対して情報を検証する
3. **簡潔に**: 可能な限り1行1コンセプト
4. **有用に**: 新しい Claude セッションがプロジェクトを理解するのに役立つか？
