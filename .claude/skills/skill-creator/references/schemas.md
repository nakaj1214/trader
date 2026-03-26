# JSON スキーマ

このドキュメントは skill-creator が使用する JSON スキーマを定義する。

---

## evals.json

スキルの eval を定義する。スキルディレクトリ内の `evals/evals.json` に配置する。

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "User's example prompt",
      "expected_output": "Description of expected result",
      "files": ["evals/files/sample1.pdf"],
      "expectations": [
        "The output includes X",
        "The skill used script Y"
      ]
    }
  ]
}
```

**フィールド：**
- `skill_name`: スキルのフロントマターと一致する名前
- `evals[].id`: 一意の整数識別子
- `evals[].prompt`: 実行するタスク
- `evals[].expected_output`: 成功の人間向け説明
- `evals[].files`: 入力ファイルパスのオプションリスト（スキルルートからの相対パス）
- `evals[].expectations`: 検証可能な記述のリスト

---

## history.json

改善モードでのバージョン進行を追跡する。ワークスペースルートに配置する。

```json
{
  "started_at": "2026-01-15T10:30:00Z",
  "skill_name": "pdf",
  "current_best": "v2",
  "iterations": [
    {
      "version": "v0",
      "parent": null,
      "expectation_pass_rate": 0.65,
      "grading_result": "baseline",
      "is_current_best": false
    },
    {
      "version": "v1",
      "parent": "v0",
      "expectation_pass_rate": 0.75,
      "grading_result": "won",
      "is_current_best": false
    },
    {
      "version": "v2",
      "parent": "v1",
      "expectation_pass_rate": 0.85,
      "grading_result": "won",
      "is_current_best": true
    }
  ]
}
```

**フィールド：**
- `started_at`: 改善を開始した ISO タイムスタンプ
- `skill_name`: 改善対象のスキル名
- `current_best`: 最高パフォーマンスのバージョン識別子
- `iterations[].version`: バージョン識別子（v0、v1、...）
- `iterations[].parent`: 派生元の親バージョン
- `iterations[].expectation_pass_rate`: 採点結果のパス率
- `iterations[].grading_result`: "baseline"、"won"、"lost"、または "tie"
- `iterations[].is_current_best`: 現在の最良バージョンかどうか

---

## grading.json

採点エージェントの出力。`<run-dir>/grading.json` に配置する。

```json
{
  "expectations": [
    {
      "text": "The output includes the name 'John Smith'",
      "passed": true,
      "evidence": "Found in transcript Step 3: 'Extracted names: John Smith, Sarah Johnson'"
    },
    {
      "text": "The spreadsheet has a SUM formula in cell B10",
      "passed": false,
      "evidence": "No spreadsheet was created. The output was a text file."
    }
  ],
  "summary": {
    "passed": 2,
    "failed": 1,
    "total": 3,
    "pass_rate": 0.67
  },
  "execution_metrics": {
    "tool_calls": {
      "Read": 5,
      "Write": 2,
      "Bash": 8
    },
    "total_tool_calls": 15,
    "total_steps": 6,
    "errors_encountered": 0,
    "output_chars": 12450,
    "transcript_chars": 3200
  },
  "timing": {
    "executor_duration_seconds": 165.0,
    "grader_duration_seconds": 26.0,
    "total_duration_seconds": 191.0
  },
  "claims": [
    {
      "claim": "The form has 12 fillable fields",
      "type": "factual",
      "verified": true,
      "evidence": "Counted 12 fields in field_info.json"
    }
  ],
  "user_notes_summary": {
    "uncertainties": ["Used 2023 data, may be stale"],
    "needs_review": [],
    "workarounds": ["Fell back to text overlay for non-fillable fields"]
  },
  "eval_feedback": {
    "suggestions": [
      {
        "assertion": "The output includes the name 'John Smith'",
        "reason": "A hallucinated document that mentions the name would also pass"
      }
    ],
    "overall": "Assertions check presence but not correctness."
  }
}
```

**フィールド：**
- `expectations[]`: 証拠付きの採点された expectation
- `summary`: パス/失敗の集計カウント
- `execution_metrics`: ツール使用量と出力サイズ（実行者の metrics.json より）
- `timing`: 実時間タイミング（timing.json より）
- `claims`: 出力から抽出・検証された主張
- `user_notes_summary`: 実行者がフラグした問題
- `eval_feedback`: （オプション）eval の改善提案。採点者が指摘すべき問題を特定した場合のみ含まれる

---

## metrics.json

実行者エージェントの出力。`<run-dir>/outputs/metrics.json` に配置する。

```json
{
  "tool_calls": {
    "Read": 5,
    "Write": 2,
    "Bash": 8,
    "Edit": 1,
    "Glob": 2,
    "Grep": 0
  },
  "total_tool_calls": 18,
  "total_steps": 6,
  "files_created": ["filled_form.pdf", "field_values.json"],
  "errors_encountered": 0,
  "output_chars": 12450,
  "transcript_chars": 3200
}
```

**フィールド：**
- `tool_calls`: ツール種別ごとのカウント
- `total_tool_calls`: すべてのツール呼び出しの合計
- `total_steps`: 主要な実行ステップの数
- `files_created`: 作成された出力ファイルのリスト
- `errors_encountered`: 実行中に発生したエラーの数
- `output_chars`: 出力ファイルの合計文字数
- `transcript_chars`: トランスクリプトの文字数

---

## timing.json

実行の実時間タイミング。`<run-dir>/timing.json` に配置する。

**記録方法:** サブエージェントのタスクが完了すると、タスク通知に `total_tokens` と `duration_ms` が含まれる。これらは他の場所に永続化されず、事後に復元できないため、直ちに保存する。

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3,
  "executor_start": "2026-01-15T10:30:00Z",
  "executor_end": "2026-01-15T10:32:45Z",
  "executor_duration_seconds": 165.0,
  "grader_start": "2026-01-15T10:32:46Z",
  "grader_end": "2026-01-15T10:33:12Z",
  "grader_duration_seconds": 26.0
}
```

---

## benchmark.json

ベンチマークモードの出力。`benchmarks/<timestamp>/benchmark.json` に配置する。

```json
{
  "metadata": {
    "skill_name": "pdf",
    "skill_path": "/path/to/pdf",
    "executor_model": "claude-sonnet-4-20250514",
    "analyzer_model": "most-capable-model",
    "timestamp": "2026-01-15T10:30:00Z",
    "evals_run": [1, 2, 3],
    "runs_per_configuration": 3
  },

  "runs": [
    {
      "eval_id": 1,
      "eval_name": "Ocean",
      "configuration": "with_skill",
      "run_number": 1,
      "result": {
        "pass_rate": 0.85,
        "passed": 6,
        "failed": 1,
        "total": 7,
        "time_seconds": 42.5,
        "tokens": 3800,
        "tool_calls": 18,
        "errors": 0
      },
      "expectations": [
        {"text": "...", "passed": true, "evidence": "..."}
      ],
      "notes": [
        "Used 2023 data, may be stale",
        "Fell back to text overlay for non-fillable fields"
      ]
    }
  ],

  "run_summary": {
    "with_skill": {
      "pass_rate": {"mean": 0.85, "stddev": 0.05, "min": 0.80, "max": 0.90},
      "time_seconds": {"mean": 45.0, "stddev": 12.0, "min": 32.0, "max": 58.0},
      "tokens": {"mean": 3800, "stddev": 400, "min": 3200, "max": 4100}
    },
    "without_skill": {
      "pass_rate": {"mean": 0.35, "stddev": 0.08, "min": 0.28, "max": 0.45},
      "time_seconds": {"mean": 32.0, "stddev": 8.0, "min": 24.0, "max": 42.0},
      "tokens": {"mean": 2100, "stddev": 300, "min": 1800, "max": 2500}
    },
    "delta": {
      "pass_rate": "+0.50",
      "time_seconds": "+13.0",
      "tokens": "+1700"
    }
  },

  "notes": [
    "Assertion 'Output is a PDF file' passes 100% in both configurations - may not differentiate skill value",
    "Eval 3 shows high variance (50% ± 40%) - may be flaky or model-dependent",
    "Without-skill runs consistently fail on table extraction expectations",
    "Skill adds 13s average execution time but improves pass rate by 50%"
  ]
}
```

**フィールド：**
- `metadata`: ベンチマーク実行に関する情報
  - `skill_name`: スキルの名前
  - `timestamp`: ベンチマーク実行日時
  - `evals_run`: eval 名または ID のリスト
  - `runs_per_configuration`: 設定ごとの実行回数（例：3）
- `runs[]`: 個別の実行結果
  - `eval_id`: 数値の eval 識別子
  - `eval_name`: 人間が読める eval 名（ビューアのセクション見出しとして使用）
  - `configuration`: `"with_skill"` または `"without_skill"` でなければならない（ビューアはこの正確な文字列をグルーピングとカラーコーディングに使用する）
  - `run_number`: 整数の実行番号（1、2、3...）
  - `result`: `pass_rate`、`passed`、`total`、`time_seconds`、`tokens`、`errors` を含むネストされたオブジェクト
- `run_summary`: 設定ごとの統計集計
  - `with_skill` / `without_skill`: それぞれ `pass_rate`、`time_seconds`、`tokens` オブジェクトを含み、`mean` と `stddev` フィールドがある
  - `delta`: `"+0.50"`、`"+13.0"`、`"+1700"` のような差分文字列
- `notes`: 分析者からの自由形式の観察

**重要:** ビューアはこれらのフィールド名を正確に読み取る。`configuration` の代わりに `config` を使ったり、`pass_rate` を `result` の下ではなく実行のトップレベルに置いたりすると、ビューアが空/ゼロ値を表示する原因になる。benchmark.json を手動で生成する際は、必ずこのスキーマを参照すること。

---

## comparison.json

ブラインド比較者の出力。`<grading-dir>/comparison-N.json` に配置する。

```json
{
  "winner": "A",
  "reasoning": "Output A provides a complete solution with proper formatting and all required fields. Output B is missing the date field and has formatting inconsistencies.",
  "rubric": {
    "A": {
      "content": {
        "correctness": 5,
        "completeness": 5,
        "accuracy": 4
      },
      "structure": {
        "organization": 4,
        "formatting": 5,
        "usability": 4
      },
      "content_score": 4.7,
      "structure_score": 4.3,
      "overall_score": 9.0
    },
    "B": {
      "content": {
        "correctness": 3,
        "completeness": 2,
        "accuracy": 3
      },
      "structure": {
        "organization": 3,
        "formatting": 2,
        "usability": 3
      },
      "content_score": 2.7,
      "structure_score": 2.7,
      "overall_score": 5.4
    }
  },
  "output_quality": {
    "A": {
      "score": 9,
      "strengths": ["Complete solution", "Well-formatted", "All fields present"],
      "weaknesses": ["Minor style inconsistency in header"]
    },
    "B": {
      "score": 5,
      "strengths": ["Readable output", "Correct basic structure"],
      "weaknesses": ["Missing date field", "Formatting inconsistencies", "Partial data extraction"]
    }
  },
  "expectation_results": {
    "A": {
      "passed": 4,
      "total": 5,
      "pass_rate": 0.80,
      "details": [
        {"text": "Output includes name", "passed": true}
      ]
    },
    "B": {
      "passed": 3,
      "total": 5,
      "pass_rate": 0.60,
      "details": [
        {"text": "Output includes name", "passed": true}
      ]
    }
  }
}
```

---

## analysis.json

事後分析者の出力。`<grading-dir>/analysis.json` に配置する。

```json
{
  "comparison_summary": {
    "winner": "A",
    "winner_skill": "path/to/winner/skill",
    "loser_skill": "path/to/loser/skill",
    "comparator_reasoning": "Brief summary of why comparator chose winner"
  },
  "winner_strengths": [
    "Clear step-by-step instructions for handling multi-page documents",
    "Included validation script that caught formatting errors"
  ],
  "loser_weaknesses": [
    "Vague instruction 'process the document appropriately' led to inconsistent behavior",
    "No script for validation, agent had to improvise"
  ],
  "instruction_following": {
    "winner": {
      "score": 9,
      "issues": ["Minor: skipped optional logging step"]
    },
    "loser": {
      "score": 6,
      "issues": [
        "Did not use the skill's formatting template",
        "Invented own approach instead of following step 3"
      ]
    }
  },
  "improvement_suggestions": [
    {
      "priority": "high",
      "category": "instructions",
      "suggestion": "Replace 'process the document appropriately' with explicit steps",
      "expected_impact": "Would eliminate ambiguity that caused inconsistent behavior"
    }
  ],
  "transcript_insights": {
    "winner_execution_pattern": "Read skill -> Followed 5-step process -> Used validation script",
    "loser_execution_pattern": "Read skill -> Unclear on approach -> Tried 3 different methods"
  }
}
```
