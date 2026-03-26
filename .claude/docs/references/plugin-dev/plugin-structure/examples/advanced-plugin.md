# 高度なプラグインの例

MCP 統合と高度な組織化を備えた、複雑なエンタープライズグレードのプラグインです。

## ディレクトリ構造

```
enterprise-devops/
├── .claude-plugin/
│   └── plugin.json
├── commands/
│   ├── ci/
│   │   ├── build.md
│   │   ├── test.md
│   │   └── deploy.md
│   ├── monitoring/
│   │   ├── status.md
│   │   └── logs.md
│   └── admin/
│       ├── configure.md
│       └── manage.md
├── agents/
│   ├── orchestration/
│   │   ├── deployment-orchestrator.md
│   │   └── rollback-manager.md
│   └── specialized/
│       ├── kubernetes-expert.md
│       ├── terraform-expert.md
│       └── security-auditor.md
├── skills/
│   ├── kubernetes-ops/
│   │   ├── SKILL.md
│   │   ├── references/
│   │   │   ├── deployment-patterns.md
│   │   │   ├── troubleshooting.md
│   │   │   └── security.md
│   │   ├── examples/
│   │   │   ├── basic-deployment.yaml
│   │   │   ├── stateful-set.yaml
│   │   │   └── ingress-config.yaml
│   │   └── scripts/
│   │       ├── validate-manifest.sh
│   │       └── health-check.sh
│   ├── terraform-iac/
│   │   ├── SKILL.md
│   │   ├── references/
│   │   │   └── best-practices.md
│   │   └── examples/
│   │       └── module-template/
│   └── ci-cd-pipelines/
│       ├── SKILL.md
│       └── references/
│           └── pipeline-patterns.md
├── hooks/
│   ├── hooks.json
│   └── scripts/
│       ├── security/
│       │   ├── scan-secrets.sh
│       │   ├── validate-permissions.sh
│       │   └── audit-changes.sh
│       ├── quality/
│       │   ├── check-config.sh
│       │   └── verify-tests.sh
│       └── workflow/
│           ├── notify-team.sh
│           └── update-status.sh
├── .mcp.json
├── servers/
│   ├── kubernetes-mcp/
│   │   ├── index.js
│   │   ├── package.json
│   │   └── lib/
│   ├── terraform-mcp/
│   │   ├── main.py
│   │   └── requirements.txt
│   └── github-actions-mcp/
│       ├── server.js
│       └── package.json
├── lib/
│   ├── core/
│   │   ├── logger.js
│   │   ├── config.js
│   │   └── auth.js
│   ├── integrations/
│   │   ├── slack.js
│   │   ├── pagerduty.js
│   │   └── datadog.js
│   └── utils/
│       ├── retry.js
│       └── validation.js
└── config/
    ├── environments/
    │   ├── production.json
    │   ├── staging.json
    │   └── development.json
    └── templates/
        ├── deployment.yaml
        └── service.yaml
```

## ファイルの内容

### .claude-plugin/plugin.json

```json
{
  "name": "enterprise-devops",
  "version": "2.3.1",
  "description": "Comprehensive DevOps automation for enterprise CI/CD pipelines, infrastructure management, and monitoring",
  "author": {
    "name": "DevOps Platform Team",
    "email": "devops-platform@company.com",
    "url": "https://company.com/teams/devops"
  },
  "homepage": "https://docs.company.com/plugins/devops",
  "repository": {
    "type": "git",
    "url": "https://github.com/company/devops-plugin.git"
  },
  "license": "Apache-2.0",
  "keywords": [
    "devops",
    "ci-cd",
    "kubernetes",
    "terraform",
    "automation",
    "infrastructure",
    "deployment",
    "monitoring"
  ],
  "commands": [
    "./commands/ci",
    "./commands/monitoring",
    "./commands/admin"
  ],
  "agents": [
    "./agents/orchestration",
    "./agents/specialized"
  ],
  "hooks": "./hooks/hooks.json",
  "mcpServers": "./.mcp.json"
}
```

### .mcp.json

```json
{
  "mcpServers": {
    "kubernetes": {
      "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/servers/kubernetes-mcp/index.js"],
      "env": {
        "KUBECONFIG": "${KUBECONFIG}",
        "K8S_NAMESPACE": "${K8S_NAMESPACE:-default}"
      }
    },
    "terraform": {
      "command": "python",
      "args": ["${CLAUDE_PLUGIN_ROOT}/servers/terraform-mcp/main.py"],
      "env": {
        "TF_STATE_BUCKET": "${TF_STATE_BUCKET}",
        "AWS_REGION": "${AWS_REGION}"
      }
    },
    "github-actions": {
      "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/servers/github-actions-mcp/server.js"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}",
        "GITHUB_ORG": "${GITHUB_ORG}"
      }
    }
  }
}
```

### hooks/hooks.json

```json
{
  "PreToolUse": [
    {
      "matcher": "Write|Edit",
      "hooks": [
        {
          "type": "command",
          "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/security/scan-secrets.sh",
          "timeout": 30
        }
      ]
    },
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "prompt",
          "prompt": "Evaluate if this bash command is safe for production environment. Check for destructive operations, missing safeguards, and potential security issues. Commands should be idempotent and reversible.",
          "timeout": 20
        }
      ]
    }
  ],
  "PostToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "command",
          "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/workflow/update-status.sh",
          "timeout": 15
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
          "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/quality/check-config.sh",
          "timeout": 45
        },
        {
          "type": "command",
          "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/workflow/notify-team.sh",
          "timeout": 30
        }
      ]
    }
  ],
  "SessionStart": [
    {
      "matcher": ".*",
      "hooks": [
        {
          "type": "command",
          "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/security/validate-permissions.sh",
          "timeout": 20
        }
      ]
    }
  ]
}
```

## 主な機能

### 多層的な組織化

**コマンド**: 機能別に整理（CI、モニタリング、管理）
**エージェント**: 役割別に分離（オーケストレーション vs. 専門）
**スキル**: 充実したリソース（リファレンス、例、スクリプト）

### MCP 統合

3つのカスタム MCP サーバー:
- **Kubernetes**: クラスター操作
- **Terraform**: インフラストラクチャのプロビジョニング
- **GitHub Actions**: CI/CD 自動化

### 共有ライブラリ

`lib/` 内の再利用可能なコード:
- **Core**: 共通ユーティリティ（ロギング、設定、認証）
- **Integrations**: 外部サービス（Slack、Datadog）
- **Utils**: ヘルパー関数（リトライ、バリデーション）

### 設定管理

`config/` 内の環境固有の設定:
- **Environments**: 環境ごとの設定
- **Templates**: 再利用可能なデプロイメントテンプレート

### セキュリティ自動化

複数のセキュリティフック:
- 書き込み前のシークレットスキャン
- セッション開始時の権限バリデーション
- 完了時の設定監査

### モニタリング統合

lib 統合による組み込みモニタリング:
- メトリクス用の Datadog
- アラート用の PagerDuty
- 通知用の Slack

## ユースケース

1. **マルチ環境デプロイメント**: dev/staging/prod 全体のオーケストレーションされたロールアウト
2. **Infrastructure as Code**: 状態管理付きの Terraform 自動化
3. **CI/CD 自動化**: ビルド、テスト、デプロイパイプライン
4. **モニタリングと可観測性**: 統合されたメトリクスとアラート
5. **セキュリティ強制**: 自動セキュリティスキャンとバリデーション
6. **チームコラボレーション**: Slack 通知とステータス更新

## このパターンを使用する場面

- 大規模なエンタープライズデプロイメント
- 複数環境の管理
- 複雑な CI/CD ワークフロー
- 統合モニタリング要件
- セキュリティが重要なインフラストラクチャ
- チームコラボレーションのニーズ

## スケーリングに関する考慮事項

- **パフォーマンス**: 並列操作のための個別 MCP サーバー
- **組織化**: スケーラビリティのための多層ディレクトリ
- **保守性**: 重複を減らす共有ライブラリ
- **柔軟性**: カスタマイズを可能にする環境設定
- **セキュリティ**: 階層化されたセキュリティフックとバリデーション
