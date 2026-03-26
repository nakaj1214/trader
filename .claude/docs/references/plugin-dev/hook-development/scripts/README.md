# フック開発ユーティリティスクリプト

これらのスクリプトは、デプロイ前にフック実装のバリデーション、テスト、リントを支援します。

## validate-hook-schema.sh

`hooks.json` 設定ファイルの構造と一般的な問題を検証します。

**使い方:**
```bash
./validate-hook-schema.sh path/to/hooks.json
```

**チェック項目:**
- 有効な JSON 構文
- 必須フィールドの存在
- 有効なフックイベント名
- 適切なフックタイプ（command/prompt）
- タイムアウト値の有効範囲
- ハードコードされたパスの検出
- プロンプトフックのイベント互換性

**例:**
```bash
cd my-plugin
./validate-hook-schema.sh hooks/hooks.json
```

## test-hook.sh

Claude Code にデプロイする前に、サンプル入力で個別のフックスクリプトをテストします。

**使い方:**
```bash
./test-hook.sh [options] <hook-script> <test-input.json>
```

**オプション:**
- `-v, --verbose` - 詳細な実行情報を表示
- `-t, --timeout N` - タイムアウトを秒単位で設定（デフォルト: 60）
- `--create-sample <event-type>` - サンプルテスト入力を生成

**例:**
```bash
# Create sample test input
./test-hook.sh --create-sample PreToolUse > test-input.json

# Test a hook script
./test-hook.sh my-hook.sh test-input.json

# Test with verbose output and custom timeout
./test-hook.sh -v -t 30 my-hook.sh test-input.json
```

**機能:**
- 適切な環境変数の設定（CLAUDE_PROJECT_DIR、CLAUDE_PLUGIN_ROOT）
- 実行時間の計測
- 出力 JSON のバリデーション
- 終了コードとその意味の表示
- 環境ファイル出力のキャプチャ

## hook-linter.sh

フックスクリプトの一般的な問題とベストプラクティス違反をチェックします。

**使い方:**
```bash
./hook-linter.sh <hook-script.sh> [hook-script2.sh ...]
```

**チェック項目:**
- shebang の存在
- `set -euo pipefail` の使用
- stdin 入力の読み取り
- 適切なエラーハンドリング
- 変数のクォート（インジェクション防止）
- 終了コードの使用
- ハードコードされたパス
- 長時間実行コードの検出
- stderr へのエラー出力
- 入力バリデーション

**例:**
```bash
# Lint single script
./hook-linter.sh ../examples/validate-write.sh

# Lint multiple scripts
./hook-linter.sh ../examples/*.sh
```

## 一般的なワークフロー

1. **フックスクリプトを書く**
   ```bash
   vim my-plugin/scripts/my-hook.sh
   ```

2. **スクリプトをリントする**
   ```bash
   ./hook-linter.sh my-plugin/scripts/my-hook.sh
   ```

3. **テスト入力を作成する**
   ```bash
   ./test-hook.sh --create-sample PreToolUse > test-input.json
   # Edit test-input.json as needed
   ```

4. **フックをテストする**
   ```bash
   ./test-hook.sh -v my-plugin/scripts/my-hook.sh test-input.json
   ```

5. **hooks.json に追加する**
   ```bash
   # Edit my-plugin/hooks/hooks.json
   ```

6. **設定をバリデーションする**
   ```bash
   ./validate-hook-schema.sh my-plugin/hooks/hooks.json
   ```

7. **Claude Code でテストする**
   ```bash
   claude --debug
   ```

## ヒント

- ユーザーワークフローの中断を避けるため、デプロイ前に必ずフックをテストする
- デバッグにはバーボスモード（`-v`）を使用する
- セキュリティとベストプラクティスの問題についてリンター出力を確認する
- 変更後は必ず hooks.json をバリデーションする
- さまざまなシナリオ（安全な操作、危険な操作、エッジケース）に対して異なるテスト入力を作成する

## よくある問題

### フックが実行されない

確認事項:
- スクリプトに shebang がある（`#!/bin/bash`）
- スクリプトが実行可能（`chmod +x`）
- hooks.json のパスが正しい（`${CLAUDE_PLUGIN_ROOT}` を使用）

### フックがタイムアウトする

- hooks.json のタイムアウトを短縮する
- フックスクリプトのパフォーマンスを最適化する
- 長時間実行される操作を削除する

### フックがサイレントに失敗する

- 終了コードを確認する（0 または 2 であるべき）
- エラーが stderr に出力されていることを確認する（`>&2`）
- JSON 出力構造をバリデーションする

### インジェクション脆弱性

- 変数を常にクォートする: `"$variable"`
- `set -euo pipefail` を使用する
- すべての入力フィールドをバリデーションする
- リンターを実行して問題を検出する
