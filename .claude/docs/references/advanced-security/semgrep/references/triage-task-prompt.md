# トリアージサブエージェント タスクプロンプト

ステップ 5 でトリアージ Task を生成する際に、このプロンプトテンプレートを使用する。`subagent_type: general-purpose` を使用。

## テンプレート

```
You are a security finding triager for [LANGUAGE_CATEGORY].

## Input Files
[LIST OF JSON FILES TO TRIAGE]

## Output Directory
[OUTPUT_DIR]

## Task
For each finding:
1. Read the JSON finding
2. Read source code context (5 lines before/after)
3. Classify as TRUE_POSITIVE or FALSE_POSITIVE

## False Positive Criteria
- Test files (should add to .semgrepignore)
- Sanitized inputs (context shows validation)
- Dead code paths
- Example/documentation code
- Already has nosemgrep comment

## Output Format
Create: [OUTPUT_DIR]/[lang]-triage.json

```json
{
  "file": "[lang]-[ruleset].json",
  "total": 45,
  "true_positives": [
    {"rule": "...", "file": "...", "line": N, "reason": "..."}
  ],
  "false_positives": [
    {"rule": "...", "file": "...", "line": N, "reason": "..."}
  ]
}
```

## Report
Return summary:
- Total findings: N
- True positives: N
- False positives: N (with breakdown by reason)
```

## 変数の置換

| 変数 | 説明 | 例 |
|----------|-------------|---------|
| `[LANGUAGE_CATEGORY]` | トリアージ対象の言語グループ | Python, JavaScript, Docker |
| `[OUTPUT_DIR]` | 実行番号付きの結果ディレクトリ | semgrep-results-001 |

## 使用例: Python トリアージタスク

```
You are a security finding triager for Python.

## Input Files
- semgrep-results-001/python-python.json
- semgrep-results-001/python-django.json
- semgrep-results-001/python-security-audit.json
- semgrep-results-001/python-secrets.json
- semgrep-results-001/python-trailofbits.json

## Output Directory
semgrep-results-001

## Task
For each finding:
1. Read the JSON finding
2. Read source code context (5 lines before/after)
3. Classify as TRUE_POSITIVE or FALSE_POSITIVE

## False Positive Criteria
- Test files (should add to .semgrepignore)
- Sanitized inputs (context shows validation)
- Dead code paths
- Example/documentation code
- Already has nosemgrep comment

## Output Format
Create: semgrep-results-001/python-triage.json

```json
{
  "file": "python-django.json",
  "total": 45,
  "true_positives": [
    {"rule": "python.django.security.injection.sql-injection", "file": "views.py", "line": 42, "reason": "User input directly in raw SQL query"}
  ],
  "false_positives": [
    {"rule": "python.django.security.injection.sql-injection", "file": "tests/test_views.py", "line": 15, "reason": "Test file with mock data"}
  ]
}
```

## Report
Return summary:
- Total findings: 45
- True positives: 12
- False positives: 33 (18 test files, 10 sanitized inputs, 5 dead code)
```

## トリアージ判定ツリー

```
検出結果
├── テストファイルか？ → FALSE_POSITIVE（.semgrepignore に追加）
├── サンプル/ドキュメントのコードか？ → FALSE_POSITIVE
├── nosemgrep コメントがあるか？ → FALSE_POSITIVE（既に確認済み）
├── 入力が上流でサニタイズ/バリデーションされているか？
│   └── 10〜20行前にバリデーションがあるか確認 → バリデーション済みなら FALSE_POSITIVE
├── コードパスに到達可能か？
│   └── 関数が呼び出し/エクスポートされているか確認 → デッドコードなら FALSE_POSITIVE
└── 上記のいずれにも該当しない → TRUE_POSITIVE
```
