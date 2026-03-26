# ルールセットカタログ

## 公式 CodeQL スイート

| スイート | 誤検知 | 用途 |
|-------|-----------------|----------|
| `security-extended` | 低 | **デフォルト** - セキュリティ監査 |
| `security-and-quality` | 中 | 包括的レビュー |
| `security-experimental` | 高め | 調査、脆弱性ハンティング |

**使用方法:** `codeql/<lang>-queries:codeql-suites/<lang>-security-extended.qls`

**言語:** `cpp`, `csharp`, `go`, `java`, `javascript`, `python`, `ruby`, `swift`

---

## Trail of Bits パック

| パック | 言語 | フォーカス |
|------|----------|-------|
| `trailofbits/cpp-queries` | C/C++ | メモリ安全性、整数オーバーフロー |
| `trailofbits/go-queries` | Go | 並行処理、エラーハンドリング |
| `trailofbits/java-queries` | Java | セキュリティ、コード品質 |

**インストール:**
```bash
codeql pack download trailofbits/cpp-queries
codeql pack download trailofbits/go-queries
codeql pack download trailofbits/java-queries
```

---

## CodeQL コミュニティパック

| パック | 言語 |
|------|----------|
| `GitHubSecurityLab/CodeQL-Community-Packs-JavaScript` | JavaScript/TypeScript |
| `GitHubSecurityLab/CodeQL-Community-Packs-Python` | Python |
| `GitHubSecurityLab/CodeQL-Community-Packs-Go` | Go |
| `GitHubSecurityLab/CodeQL-Community-Packs-Java` | Java |
| `GitHubSecurityLab/CodeQL-Community-Packs-CPP` | C/C++ |
| `GitHubSecurityLab/CodeQL-Community-Packs-CSharp` | C# |
| `GitHubSecurityLab/CodeQL-Community-Packs-Ruby` | Ruby |

**インストール:**
```bash
codeql pack download GitHubSecurityLab/CodeQL-Community-Packs-<Lang>
```

**ソース:** [github.com/GitHubSecurityLab/CodeQL-Community-Packs](https://github.com/GitHubSecurityLab/CodeQL-Community-Packs)

---

## インストールの確認

```bash
# インストール済みの全パックを一覧表示
codeql resolve qlpacks

# 特定のパックを確認
codeql resolve qlpacks | grep -E "(trailofbits|GitHubSecurityLab)"
```
