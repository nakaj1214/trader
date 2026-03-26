# Semgrep ルールセットリファレンス

## 全ルールセットカタログ

### セキュリティ重視のルールセット

| ルールセット | 説明 | 使用ケース |
|---------|-------------|----------|
| `p/security-audit` | 包括的な脆弱性検出、偽陽性が多め | 手動監査、セキュリティレビュー |
| `p/secrets` | ハードコードされた認証情報、API キー、トークン | 常に含める |
| `p/owasp-top-ten` | OWASP Top 10 Web アプリケーション脆弱性 | Web アプリセキュリティ |
| `p/cwe-top-25` | CWE Top 25 最も危険なソフトウェア脆弱性 | 一般的なセキュリティ |
| `p/sql-injection` | SQL インジェクションパターンと汚染データフロー | データベースセキュリティ |
| `p/insecure-transport` | コードが暗号化チャネルを使用しているか確認 | ネットワークセキュリティ |
| `p/gitleaks` | ハードコードされた認証情報の検出（gitleaks 移植版） | シークレットスキャン |
| `p/findsecbugs` | Java 向け FindSecBugs ルールパック | Java セキュリティ |
| `p/phpcs-security-audit` | PHP セキュリティ監査ルール | PHP セキュリティ |

### CI/CD ルールセット

| ルールセット | 説明 | 使用ケース |
|---------|-------------|----------|
| `p/default` | デフォルトルールセット、バランスの取れたカバレッジ | 初回ユーザー |
| `p/ci` | 高信頼性のセキュリティ + ロジックバグ、低偽陽性 | CI パイプライン |
| `p/r2c-ci` | 低偽陽性、CI セーフ | CI/CD ブロッキング |
| `p/r2c` | コミュニティ人気、Semgrep キュレーション（618k+ ダウンロード） | 一般的なスキャン |
| `p/auto` | 検出された言語/フレームワークに基づいてルールを自動選択 | クイックスキャン |
| `p/comment` | コメント関連ルール | コードレビュー |

### サードパーティルールセット

| ルールセット | 説明 | メンテナー |
|---------|-------------|------------|
| `p/gitlab` | GitLab メンテナンスのセキュリティルール | GitLab |

---

## ルールセット選択アルゴリズム

検出された言語とフレームワークに基づいてルールセットを選択するアルゴリズム。

### ステップ 1: セキュリティベースラインを常に含める

```json
{
  "baseline": ["p/security-audit", "p/secrets"]
}
```

- `p/security-audit` - 包括的な脆弱性検出（常に含める）
- `p/secrets` - ハードコードされた認証情報、API キー、トークン（常に含める）

### ステップ 2: 言語固有のルールセットを追加

検出された各言語に対してプライマリルールセットを追加する。フレームワークが検出された場合は、そのルールセットも追加する。

**GA 言語（本番対応済み）:**

| 検出条件 | プライマリルールセット | フレームワークルールセット | Pro ルール数 |
|-----------|-----------------|-------------------|----------------|
| `.py` | `p/python` | `p/django`, `p/flask`, `p/fastapi` | 710+ |
| `.js`, `.jsx` | `p/javascript` | `p/react`, `p/nodejs`, `p/express`, `p/nextjs`, `p/angular` | 250+ (JS), 70+ (JSX) |
| `.ts`, `.tsx` | `p/typescript` | `p/react`, `p/nodejs`, `p/express`, `p/nextjs`, `p/angular` | 230+ |
| `.go` | `p/golang` | `p/go` (エイリアス) | 80+ |
| `.java` | `p/java` | `p/spring`, `p/findsecbugs` | 190+ |
| `.kt` | `p/kotlin` | `p/spring` | 60+ |
| `.rb` | `p/ruby` | `p/rails` | 40+ |
| `.php` | `p/php` | `p/symfony`, `p/laravel`, `p/phpcs-security-audit` | 50+ |
| `.c`, `.cpp`, `.h` | `p/c` | - | 150+ |
| `.rs` | `p/rust` | - | 40+ |
| `.cs` | `p/csharp` | - | 170+ |
| `.scala` | `p/scala` | - | コミュニティ |
| `.swift` | `p/swift` | - | 60+ |

**ベータ言語（Pro 推奨）:**

| 検出条件 | プライマリルールセット | 備考 |
|-----------|-----------------|-------|
| `.ex`, `.exs` | `p/elixir` | 最適なカバレッジには Pro が必要 |
| `.cls`, `.trigger` | `p/apex` | Salesforce; Pro が必要 |

**実験的言語:**

| 検出条件 | プライマリルールセット | 備考 |
|-----------|-----------------|-------|
| `.sol` | 公式ルールセットなし | Decurity サードパーティルールを使用 |
| `Dockerfile` | `p/dockerfile` | ルール数が限定的 |
| `.yaml`, `.yml` | `p/yaml` | K8s、GitHub Actions、docker-compose パターン |
| `.json` | `r/json.aws` | AWS IAM ポリシー; 特定ルールには `r/json.*` を使用 |
| Bash スクリプト | - | コミュニティサポート |
| Cairo, Circom | - | 実験的、スマートコントラクト |

**フレームワーク検出のヒント:**

| フレームワーク | 検出シグナル | ルールセット |
|-----------|------------------|---------|
| Django | `settings.py`, `urls.py`, requirements 内の `django` | `p/django` |
| Flask | requirements 内の `flask`, `@app.route` | `p/flask` |
| FastAPI | requirements 内の `fastapi`, `@app.get/post` | `p/fastapi` |
| React | react 依存の `package.json`, `.jsx`/`.tsx` ファイル | `p/react` |
| Next.js | `next.config.js`, `pages/` または `app/` ディレクトリ | `p/nextjs` |
| Angular | `angular.json`, `@angular/` 依存 | `p/angular` |
| Express | package.json 内の `express`, `app.use()` パターン | `p/express` |
| NestJS | `@nestjs/` 依存, `@Controller` デコレーター | `p/nodejs` |
| Spring | spring 含む `pom.xml`, `@SpringBootApplication` | `p/spring` |
| Rails | rails 含む `Gemfile`, `config/routes.rb` | `p/rails` |
| Laravel | laravel 含む `composer.json`, `artisan` | `p/laravel` |
| Symfony | symfony 含む `composer.json`, `config/packages/` | `p/symfony` |

### ステップ 3: インフラストラクチャルールセットを追加

| 検出条件 | ルールセット | 説明 |
|-----------|---------|-------------|
| `Dockerfile` | `p/dockerfile` | コンテナセキュリティ、ベストプラクティス |
| `.tf`, `.hcl` | `p/terraform` | IaC 設定ミス、CIS ベンチマーク、AWS/Azure/GCP |
| k8s マニフェスト | `p/kubernetes` | K8s セキュリティ、RBAC 問題 |
| CloudFormation | `p/cloudformation` | AWS インフラセキュリティ |
| GitHub Actions | `p/github-actions` | CI/CD セキュリティ、シークレット漏洩 |
| `.yaml`, `.yml` | `p/yaml` | 汎用 YAML パターン（K8s、docker-compose） |
| AWS IAM JSON | `r/json.aws` | IAM ポリシー設定ミス（`--config r/json.aws` を使用） |

### ステップ 4: サードパーティルールセットを追加

これらは**オプションではない**。言語が一致した場合は自動的に含める:

| 言語 | ソース | 必須の理由 |
|-----------|--------|--------------|
| Python, Go, Ruby, JS/TS, Terraform, HCL | [Trail of Bits](https://github.com/trailofbits/semgrep-rules) | 実際のエンゲージメントに基づくセキュリティ監査パターン（AGPLv3） |
| C, C++ | [0xdea](https://github.com/0xdea/semgrep-rules) | メモリ安全性、低レベル脆弱性 |
| Solidity, Cairo, Rust | [Decurity](https://github.com/Decurity/semgrep-smart-contracts) | スマートコントラクト脆弱性、DeFi エクスプロイト |
| Go | [dgryski](https://github.com/dgryski/semgrep-go) | 追加の Go 固有パターン |
| Android (Java/Kotlin) | [MindedSecurity](https://github.com/mindedsecurity/semgrep-rules-android-security) | OWASP MASTG 由来のモバイルセキュリティルール |
| Java, Go, JS/TS, C#, Python, PHP | [elttam](https://github.com/elttam/semgrep-rules) | セキュリティコンサルティングパターン |
| Dockerfile, PHP, Go, Java | [kondukto](https://github.com/kondukto-io/semgrep-rules) | コンテナと Web アプリセキュリティ |
| PHP, Kotlin, Java | [dotta](https://github.com/federicodotta/semgrep-rules) | ペンテスト由来の Web/モバイルアプリルール |
| Terraform, HCL | [HashiCorp](https://github.com/hashicorp-forge/semgrep-rules) | HashiCorp インフラパターン |
| Swift, Java, Cobol | [akabe1](https://github.com/akabe1/akabe1-semgrep-rules) | iOS とレガシーシステムパターン |
| Java | [Atlassian Labs](https://github.com/atlassian-labs/atlassian-sast-ruleset) | Atlassian メンテナンスの Java ルール |
| Python, JS/TS, Java, Ruby, Go, PHP | [Apiiro](https://github.com/apiiro/malicious-code-ruleset) | 悪意のあるコード検出、サプライチェーン |

### ステップ 5: ルールセットの検証

最終決定前に、公式ルールセットが読み込まれるか検証する:

```bash
# クイックバリデーション（有効なら exit 0）
semgrep --config p/python --validate --metrics=off 2>&1 | head -3
```

または [Semgrep Registry](https://semgrep.dev/explore) を参照。

### 出力形式

```json
{
  "baseline": ["p/security-audit", "p/secrets"],
  "python": ["p/python", "p/django"],
  "javascript": ["p/javascript", "p/react", "p/nodejs"],
  "docker": ["p/dockerfile"],
  "third_party": ["https://github.com/trailofbits/semgrep-rules"]
}
```
