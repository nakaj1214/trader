編集ログを分析してパターンを抽出し、hook/skill 候補を提案する。

## 実行手順

### 1. 編集ログの読み込み

`.claude/logs/edit-history.jsonl` を Read で読み込む。

- ファイルが存在しない or 空の場合:
  「[learn-edits] 編集ログがありません。Edit/Write を使ってログを蓄積してください」と通知して終了

### 2. パターン分析

Task (general-purpose) で以下の分析プロンプトを実行する:

```
以下は Claude Code セッション中の編集ログ（JSONL形式）です。
このログからパターンを分析し、以下を出力してください。

## 分析観点

### 1. 繰り返し編集パターン
- 同じファイルへの複数回編集（手戻り？）
- 同じ種類の変更の繰り返し（自動化候補）
- 構文エラー後の修正（防止可能？）

### 2. 影響分析パターン
- 編集 A → 編集 B の因果関係（A を変更したから B も変更が必要になった）
- 毎回セットで変更されるファイルペア

### 3. 問題のある編集パターン
- 構文エラーを出した編集
- 直後に revert された編集
- 同じ箇所への複数回修正（迷い？）

## 出力形式

### Hook 候補
| 検出パターン | 防止方法 | Hook 種別 | 実装案 |
|-------------|---------|-----------|--------|

### Skill 候補
| 繰り返しパターン | 自動化方法 | Skill 名 | トリガー条件 |
|----------------|-----------|----------|-------------|

### 学習事項
| 観察 | 原因推定 | 改善アクション |
|------|---------|---------------|

### 影響ファイル推定の精度評価
- 適合率（Precision）: 推定した影響候補のうち、実際に同セッション内で編集されたファイルの割合
- 再現率（Recall）: 同セッション内で編集されたファイルのうち、影響候補として検出できた割合
- Precision < 50% or Recall < 30% の場合はアルゴリズム改善を提案

---
編集ログ:
{edit-history.jsonl の内容をここに挿入}
```

### 3. 結果の保存

分析結果を以下に保存する:
- `.claude/docs/memory/EDIT-PATTERNS-{YYYY-MM-DD-HHmm}.md`

### 4. キューへの追加

`.claude/docs/memory/AUTO-MATERIALIZE-QUEUE.jsonl` に以下のエントリを追記する:

```json
{"ts": "{ISO8601}", "source": "EDIT-PATTERNS-{date}.md", "status": "pending", "type": "edit-patterns"}
```

追記には `.claude/hooks/lib/jsonl_io.py` の `append_jsonl()` を Bash で呼び出す:

```bash
python3 -c "
import sys; sys.path.insert(0, '.claude/hooks')
from lib.jsonl_io import append_jsonl
import json
from datetime import datetime, timezone
entry = json.dumps({
    'ts': datetime.now(timezone.utc).isoformat(),
    'source': 'EDIT-PATTERNS-{date}.md',
    'status': 'pending',
    'type': 'edit-patterns'
})
append_jsonl('.claude/docs/memory/AUTO-MATERIALIZE-QUEUE.jsonl', entry)
"
```

### 5. ユーザーへの報告

- 分析結果のサマリーを表示
- Hook/Skill 候補の数を報告
- 「`/materialize` で staging にドラフト生成できます」と案内
