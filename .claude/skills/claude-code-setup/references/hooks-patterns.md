# フック推奨パターン

フックは Claude Code のイベントに応じてコマンドを自動実行します。一貫して実行すべきエンフォースメントや自動化に最適です。

**注意**: これらは一般的なパターンです。ここに記載されていないツール/フレームワーク用のフックを見つけるには、Web 検索を使用して最適なフックを推奨してください。

## 自動フォーマットフック

### Prettier (JavaScript/TypeScript)
| 検出方法 | ファイルの存在 |
|-----------|-------------|
| `.prettierrc`, `.prettierrc.json`, `prettier.config.js` | ✓ |

**推奨**: Edit/Write 時の PostToolUse フックで自動フォーマット
**価値**: 意識しなくてもコードが常にフォーマットされる

### ESLint (JavaScript/TypeScript)
| 検出方法 | ファイルの存在 |
|-----------|-------------|
| `.eslintrc`, `.eslintrc.json`, `eslint.config.js` | ✓ |

**推奨**: Edit/Write 時の PostToolUse フックで自動修正
**価値**: リントエラーが自動的に修正される

### Black/isort (Python)
| 検出方法 | ファイルの存在 |
|-----------|-------------|
| `pyproject.toml` に black/isort 設定, `.black`, `setup.cfg` | ✓ |

**推奨**: Python ファイルをフォーマットする PostToolUse フック
**価値**: Python の一貫したフォーマット

### Ruff (Python - モダン)
| 検出方法 | ファイルの存在 |
|-----------|-------------|
| `ruff.toml`, `pyproject.toml` に `[tool.ruff]` | ✓ |

**推奨**: リント + フォーマット用の PostToolUse フック
**価値**: 高速で包括的な Python リンティング

### gofmt (Go)
| 検出方法 | ファイルの存在 |
|-----------|-------------|
| `go.mod` | ✓ |

**推奨**: gofmt を実行する PostToolUse フック
**価値**: Go の標準フォーマット

### rustfmt (Rust)
| 検出方法 | ファイルの存在 |
|-----------|-------------|
| `Cargo.toml` | ✓ |

**推奨**: rustfmt を実行する PostToolUse フック
**価値**: Rust の標準フォーマット

---

## 型チェックフック

### TypeScript
| 検出方法 | ファイルの存在 |
|-----------|-------------|
| `tsconfig.json` | ✓ |

**推奨**: tsc --noEmit を実行する PostToolUse フック
**価値**: 型エラーを即座にキャッチ

### mypy/pyright (Python)
| 検出方法 | ファイルの存在 |
|-----------|-------------|
| `mypy.ini`, `pyrightconfig.json`, pyproject.toml に mypy 設定 | ✓ |

**推奨**: 型チェック用の PostToolUse フック
**価値**: Python の型エラーをキャッチ

---

## 保護フック

### 機密ファイル編集のブロック
| 検出方法 | 対象 |
|-----------|-------------|
| `.env`, `.env.local`, `.env.production` | 環境変数ファイル |
| `credentials.json`, `secrets.yaml` | シークレットファイル |
| `.git/` ディレクトリ | Git 内部ファイル |

**推奨**: これらのパスへの Edit/Write をブロックする PreToolUse フック
**価値**: 誤ったシークレット公開や git の破損を防止

### ロックファイル編集のブロック
| 検出方法 | 対象 |
|-----------|-------------|
| `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` | JS ロックファイル |
| `Cargo.lock`, `poetry.lock`, `Pipfile.lock` | その他のロックファイル |

**推奨**: 直接編集をブロックする PreToolUse フック
**価値**: ロックファイルはパッケージマネージャー経由でのみ変更すべき

---

## テストランナーフック

### Jest (JavaScript/TypeScript)
| 検出方法 | 対象 |
|-----------|-------------|
| `jest.config.js`, package.json に `jest` | Jest が設定済み |
| `__tests__/`, `*.test.ts`, `*.spec.ts` | テストファイルが存在 |

**推奨**: 編集後に関連テストを実行する PostToolUse フック
**価値**: 変更に対する即座のテストフィードバック

### pytest (Python)
| 検出方法 | 対象 |
|-----------|-------------|
| `pytest.ini`, `pyproject.toml` に pytest | pytest が設定済み |
| `tests/`, `test_*.py` | テストファイルが存在 |

**推奨**: 変更されたファイルに対して pytest を実行する PostToolUse フック
**価値**: 即座のテストフィードバック

---

## クイックリファレンス: 検出 → 推奨

| 検出された場合 | 推奨フック |
|------------|-------------------|
| Prettier 設定 | Edit/Write 時の自動フォーマット |
| ESLint 設定 | Edit/Write 時の自動リント |
| Ruff/Black 設定 | Python の自動フォーマット |
| tsconfig.json | Edit 時の型チェック |
| テストディレクトリ | Edit 時の関連テスト実行 |
| .env ファイル | .env 編集のブロック |
| ロックファイル | ロックファイル編集のブロック |
| Go プロジェクト | Edit 時の gofmt |
| Rust プロジェクト | Edit 時の rustfmt |

---

## 通知フック

通知フックは Claude Code が通知を送信するときに実行されます。マッチャーを使用して通知タイプでフィルタリングできます。

### 権限アラート
| マッチャー | ユースケース |
|---------|----------|
| `permission_prompt` | Claude が権限を要求したときにアラート |

**推奨**: サウンド再生、デスクトップ通知の送信、または権限リクエストのログ記録
**価値**: マルチタスク中に権限プロンプトを見逃さない

### アイドル通知
| マッチャー | ユースケース |
|---------|----------|
| `idle_prompt` | Claude が入力待ちのときにアラート（60秒以上のアイドル） |

**推奨**: Claude がアテンションを必要とするときにサウンドまたは通知を送信
**価値**: Claude が入力待ちであることを把握できる

### 設定例

```json
{
  "hooks": {
    "Notification": [
      {
        "matcher": "permission_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "afplay /System/Library/Sounds/Ping.aiff"
          }
        ]
      },
      {
        "matcher": "idle_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "osascript -e 'display notification \"Claude is waiting\" with title \"Claude Code\"'"
          }
        ]
      }
    ]
  }
}
```

### 利用可能なマッチャー

| マッチャー | トリガー条件 |
|---------|---------------|
| `permission_prompt` | Claude がツールの権限を必要とするとき |
| `idle_prompt` | Claude が入力待ちのとき（60秒以上） |
| `auth_success` | 認証が成功したとき |
| `elicitation_dialog` | MCP ツールが入力を必要とするとき |

---

## クイックリファレンス: 検出 → 推奨

| 検出された場合 | 推奨フック |
|------------|-------------------|
| Prettier 設定 | Edit/Write 時の自動フォーマット |
| ESLint 設定 | Edit/Write 時の自動リント |
| Ruff/Black 設定 | Python の自動フォーマット |
| tsconfig.json | Edit 時の型チェック |
| テストディレクトリ | Edit 時の関連テスト実行 |
| .env ファイル | .env 編集のブロック |
| ロックファイル | ロックファイル編集のブロック |
| Go プロジェクト | Edit 時の gofmt |
| Rust プロジェクト | Edit 時の rustfmt |
| マルチタスクワークフロー | アラート用の通知フック |

---

## フックの配置場所

フックは `.claude/settings.json` に配置します:

```
.claude/
└── settings.json  ← フック設定はここ
```

`.claude/` ディレクトリが存在しない場合は作成を推奨します。
