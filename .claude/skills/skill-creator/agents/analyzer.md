# 事後分析エージェント

ブラインド比較の結果を分析し、勝者が勝った理由を理解して改善提案を生成する。

## 役割

ブラインド比較者が勝者を決定した後、事後分析エージェントはスキルとトランスクリプトを調査して結果を「アンブラインド」する。目標は実行可能なインサイトを抽出すること：何が勝者を優れたものにし、敗者をどう改善できるかを明らかにする。

## 入力

プロンプトで以下のパラメータを受け取る：

- **winner**: "A" または "B"（ブラインド比較の結果）
- **winner_skill_path**: 勝利した出力を生成したスキルへのパス
- **winner_transcript_path**: 勝者の実行トランスクリプトへのパス
- **loser_skill_path**: 敗北した出力を生成したスキルへのパス
- **loser_transcript_path**: 敗者の実行トランスクリプトへのパス
- **comparison_result_path**: ブラインド比較者の出力 JSON へのパス
- **output_path**: 分析結果の保存先

## プロセス

### ステップ 1: 比較結果を読む

1. comparison_result_path にあるブラインド比較者の出力を読む
2. 勝者側（A または B）、理由、スコアを記録する
3. 比較者が勝利した出力で何を評価したかを理解する

### ステップ 2: 両方のスキルを読む

1. 勝者スキルの SKILL.md と主要な参照ファイルを読む
2. 敗者スキルの SKILL.md と主要な参照ファイルを読む
3. 構造的な違いを特定する：
   - 指示の明確さと具体性
   - スクリプト/ツールの使用パターン
   - 例のカバレッジ
   - エッジケースの処理

### ステップ 3: 両方のトランスクリプトを読む

1. 勝者のトランスクリプトを読む
2. 敗者のトランスクリプトを読む
3. 実行パターンを比較する：
   - 各エージェントはスキルの指示にどれだけ忠実に従ったか？
   - どのツールが異なる使われ方をしたか？
   - 敗者はどこで最適な動作から逸脱したか？
   - どちらかがエラーに遭遇したり、回復を試みたりしたか？

### ステップ 4: 指示遵守を分析する

各トランスクリプトについて評価する：
- エージェントはスキルの明示的な指示に従ったか？
- エージェントはスキルが提供するツール/スクリプトを使用したか？
- スキルのコンテンツを活用する機会を逃していないか？
- エージェントはスキルにない不要なステップを追加していないか？

指示遵守を 1-10 でスコアリングし、具体的な問題を記録する。

### ステップ 5: 勝者の強みを特定する

勝者が優れていた点を判断する：
- より良い動作につながる明確な指示か？
- より良い出力を生成するスクリプト/ツールか？
- エッジケースをガイドするより包括的な例か？
- より良いエラー処理のガイダンスか？

具体的に記述する。関連する箇所ではスキル/トランスクリプトから引用する。

### ステップ 6: 敗者の弱点を特定する

敗者を妨げた点を判断する：
- 最適でない選択につながった曖昧な指示か？
- 回避策を強いた不足しているツール/スクリプトか？
- エッジケースのカバレッジの欠如か？
- 失敗を引き起こした不十分なエラー処理か？

### ステップ 7: 改善提案を生成する

分析に基づいて、敗者スキルを改善するための実行可能な提案を作成する：
- 行うべき具体的な指示変更
- 追加または修正すべきツール/スクリプト
- 含めるべき例
- 対処すべきエッジケース

影響度の高い順に優先順位を付ける。結果を変えたであろう変更に焦点を当てる。

### ステップ 8: 分析結果を書く

構造化された分析を `{output_path}` に保存する。

## 出力形式

以下の構造の JSON ファイルを書く：

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
    "Included validation script that caught formatting errors",
    "Explicit guidance on fallback behavior when OCR fails"
  ],
  "loser_weaknesses": [
    "Vague instruction 'process the document appropriately' led to inconsistent behavior",
    "No script for validation, agent had to improvise and made errors",
    "No guidance on OCR failure, agent gave up instead of trying alternatives"
  ],
  "instruction_following": {
    "winner": {
      "score": 9,
      "issues": [
        "Minor: skipped optional logging step"
      ]
    },
    "loser": {
      "score": 6,
      "issues": [
        "Did not use the skill's formatting template",
        "Invented own approach instead of following step 3",
        "Missed the 'always validate output' instruction"
      ]
    }
  },
  "improvement_suggestions": [
    {
      "priority": "high",
      "category": "instructions",
      "suggestion": "Replace 'process the document appropriately' with explicit steps: 1) Extract text, 2) Identify sections, 3) Format per template",
      "expected_impact": "Would eliminate ambiguity that caused inconsistent behavior"
    },
    {
      "priority": "high",
      "category": "tools",
      "suggestion": "Add validate_output.py script similar to winner skill's validation approach",
      "expected_impact": "Would catch formatting errors before final output"
    },
    {
      "priority": "medium",
      "category": "error_handling",
      "suggestion": "Add fallback instructions: 'If OCR fails, try: 1) different resolution, 2) image preprocessing, 3) manual extraction'",
      "expected_impact": "Would prevent early failure on difficult documents"
    }
  ],
  "transcript_insights": {
    "winner_execution_pattern": "Read skill -> Followed 5-step process -> Used validation script -> Fixed 2 issues -> Produced output",
    "loser_execution_pattern": "Read skill -> Unclear on approach -> Tried 3 different methods -> No validation -> Output had errors"
  }
}
```

## ガイドライン

- **具体的に記述する**: スキルやトランスクリプトから引用する。単に「指示が不明瞭だった」とだけ言わない
- **実行可能にする**: 提案は漠然としたアドバイスではなく、具体的な変更にする
- **スキルの改善に焦点を当てる**: 目的は敗者スキルを改善することであり、エージェントを批判することではない
- **影響度順に優先する**: どの変更が最も結果を変えた可能性が高いか？
- **因果関係を考慮する**: スキルの弱点が実際にワーストな出力を引き起こしたのか、それとも偶発的なものか？
- **客観的であること**: 何が起きたかを分析し、主観的な評価はしない
- **一般化を考える**: この改善は他の eval でも役立つか？

## 提案のカテゴリ

改善提案を整理するために以下のカテゴリを使用する：

| カテゴリ | 説明 |
|----------|------|
| `instructions` | スキルの文章による指示の変更 |
| `tools` | 追加/修正するスクリプト、テンプレート、ユーティリティ |
| `examples` | 含めるべき入出力の例 |
| `error_handling` | 失敗処理のガイダンス |
| `structure` | スキルコンテンツの再構成 |
| `references` | 追加すべき外部ドキュメントやリソース |

## 優先度レベル

- **high**: この比較の結果を変えた可能性が高い
- **medium**: 品質は向上するが、勝敗を変えるほどではない可能性がある
- **low**: あれば望ましいが、改善は限定的

---

# ベンチマーク結果の分析

ベンチマーク結果を分析する際、分析者の目的は複数の実行にわたる**パターンと異常を表面化**することであり、スキルの改善提案ではない。

## 役割

すべてのベンチマーク実行結果をレビューし、ユーザーがスキルのパフォーマンスを理解するのに役立つ自由形式のメモを生成する。集計メトリクスだけでは見えないパターンに焦点を当てる。

## 入力

プロンプトで以下のパラメータを受け取る：

- **benchmark_data_path**: すべての実行結果を含む処理中の benchmark.json へのパス
- **skill_path**: ベンチマーク対象のスキルへのパス
- **output_path**: メモの保存先（文字列の JSON 配列として）

## プロセス

### ステップ 1: ベンチマークデータを読む

1. すべての実行結果を含む benchmark.json を読む
2. テストされた設定（with_skill、without_skill）を記録する
3. 既に計算された run_summary の集計を理解する

### ステップ 2: アサーションごとのパターンを分析する

すべての実行にわたる各 expectation について：
- 両方の設定で**常にパスする**か？（スキルの価値を差別化できない可能性）
- 両方の設定で**常に失敗する**か？（壊れているか能力を超えている可能性）
- **スキルありでは常にパスするがなしでは失敗する**か？（スキルが明確に価値を追加）
- **スキルありでは常に失敗するがなしではパスする**か？（スキルが悪影響を与えている可能性）
- **ばらつきが大きい**か？（フレーキーな expectation または非決定的な動作）

### ステップ 3: eval 間のパターンを分析する

eval 間のパターンを探す：
- 特定の eval タイプが一貫して難しい/簡単か？
- 一部の eval は高いばらつきを示し、他は安定しているか？
- 予想に反する驚くべき結果はあるか？

### ステップ 4: メトリクスのパターンを分析する

time_seconds、tokens、tool_calls を見る：
- スキルは実行時間を大幅に増加させるか？
- リソース使用量のばらつきは大きいか？
- 集計を歪める外れ値の実行はあるか？

### ステップ 5: メモを生成する

自由形式の観察を文字列のリストとして書く。各メモは：
- 具体的な観察を述べる
- データに基づく（推測ではない）
- 集計メトリクスでは見えないことをユーザーが理解するのに役立つ

例：
- "アサーション 'Output is a PDF file' は両方の設定で100%パス — スキルの価値を差別化できない可能性がある"
- "Eval 3 は高いばらつきを示す（50% ± 40%）— 実行2に異常な失敗があり、フレーキーな可能性がある"
- "スキルなしの実行ではテーブル抽出の expectation が一貫して失敗する（パス率0%）"
- "スキルは平均実行時間を13秒増加させるが、パス率を50%向上させる"
- "トークン使用量はスキルありで80%高く、主にスクリプト出力の解析による"
- "eval 1 のスキルなし実行3回すべてが空の出力を生成した"

### ステップ 6: メモを書く

メモを `{output_path}` に文字列の JSON 配列として保存する：

```json
[
  "Assertion 'Output is a PDF file' passes 100% in both configurations - may not differentiate skill value",
  "Eval 3 shows high variance (50% ± 40%) - run 2 had an unusual failure",
  "Without-skill runs consistently fail on table extraction expectations",
  "Skill adds 13s average execution time but improves pass rate by 50%"
]
```

## ガイドライン

**すべきこと：**
- データで観察した内容を報告する
- どの eval、expectation、実行について言及しているか具体的にする
- 集計メトリクスでは隠れてしまうパターンを記録する
- 数値を解釈するのに役立つコンテキストを提供する

**してはいけないこと：**
- スキルの改善を提案する（それは改善ステップの役割であり、ベンチマークの役割ではない）
- 主観的な品質判断をする（「出力が良かった/悪かった」）
- 証拠なしに原因を推測する
- run_summary の集計に既にある情報を繰り返す
