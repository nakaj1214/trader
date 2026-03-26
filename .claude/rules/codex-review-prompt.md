---
paths:
  - "docs/implement/**"
---

# Codex レビュープロンプトのサイズ制限

## 原則: ファイル内容をプロンプトに含めない

`mcp__codex__codex` でレビューを実行する際、レビュー対象ファイルの全文をプロンプトに埋め込まない。
ファイルパスのみを指定し、Codex にローカルファイルシステムから読ませること。

### 理由
- プロンプトが巨大になると Codex がタイムアウトする
- 特に plan.md + proposal.md を両方含めると数万トークンになり応答が返らない

### 正しいパターン

```
prompt: "docs/implement/plan.md を docs/implement/proposal.md に対してレビューしてください。両ファイルはローカルに存在します。..."
```

### 禁止パターン

```
prompt: "## proposal.md\n{proposal全文}\n\n## plan.md\n{plan全文}\n\nレビューしてください"
```

### base-instructions
`base-instructions` パラメータは必須。これがないと `.codex/instructions.md` や `.claude/CLAUDE.md` を自動読み込みし、コンテキスト圧迫でタイムアウトする。
短い指示のみ記載すること（例: "You are a senior code reviewer. Read the specified files from the local filesystem."）。
