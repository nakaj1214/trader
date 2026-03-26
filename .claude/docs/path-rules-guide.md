# `.claude/rules/` パス指定ルール ガイド

> Claude Code 公式機能: `.claude/rules/` ディレクトリ内の `.md` ファイルはルールとして読み込まれる。
> YAML フロントマターで `paths:` を指定すると、**対象ファイルを開いたときだけ**ルールが注入される。

---

## なぜパス指定ルールを使うか

通常の `CLAUDE.md` はセッション開始時に全ルールを一括ロードする。
ファイル数が増えるとコンテキストが圧迫されるが、パス指定ルールを使えば
「TypeScript ファイルを開いたときだけ TypeScript のルールを読む」が実現できる。

---

## ディレクトリ構成

```
project/
├── CLAUDE.md                    # プロジェクト共通ルール（常に読み込まれる）
└── .claude/
    └── rules/
        ├── code-style.md        # paths なし → 常に読み込まれる
        ├── testing.md           # paths なし → 常に読み込まれる
        ├── api-design.md        # TypeScript API ファイル限定
        ├── security.md          # セキュリティ要件（全ファイル）
        └── frontend/
            ├── react.md         # React コンポーネント限定
            └── styles.md        # CSS/SCSS ファイル限定
```

---

## フロントマターの書き方

### パスなし（常にロード）

```markdown
# コーディングスタイル

- インデントは 2 スペース
- シングルクォートを使用
```

### パスあり（条件付きロード）

```markdown
---
paths:
  - "src/api/**/*.ts"
---

# API エンドポイント設計ルール

- 必ず入力バリデーションを行う
- 標準エラーレスポンス形式を使う
- OpenAPI コメントを含める
```

---

## よく使うパターン

| ルールファイル | `paths` の値 | 用途 |
|-------------|------------|------|
| `react.md` | `"src/**/*.{tsx,jsx}"` | React コンポーネント専用 |
| `api.md` | `"src/api/**/*.ts"` | API ハンドラー専用 |
| `tests.md` | `"**/*.test.{ts,js}"` | テストファイル専用 |
| `sql.md` | `"**/*.sql"` | SQL ファイル専用 |
| `styles.md` | `"**/*.{css,scss}"` | スタイルシート専用 |

複数パターンを指定する場合:

```yaml
---
paths:
  - "src/**/*.{ts,tsx}"
  - "lib/**/*.ts"
  - "tests/**/*.test.ts"
---
```

---

## シンボリックリンクで共有

`.claude/rules/` はシンボリックリンクをサポートしている。
`.claude/rules/` の内容を各プロジェクトにリンクできる:

```bash
# 共有ルールディレクトリをプロジェクトにリンク
ln -s /path/to/.claude/rules .claude/rules/shared

# 個別ファイルのリンク
ln -s /path/to/.claude/rules/security-rules.md .claude/rules/security.md
```

---

## ユーザーレベルルール

`~/.claude/rules/` に置いたルールは**すべてのプロジェクト**に適用される。
個人の好みを全プロジェクトで共有したい場合に使う。

```
~/.claude/rules/
├── preferences.md    # 個人コーディング好み
└── workflows.md      # 個人ワークフロー
```

プロジェクトルール > ユーザーレベルルールの優先順位。
