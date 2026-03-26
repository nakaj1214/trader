# スキルクリエーター — 詳細手順

新しいスキルを作成し、反復的に改善するためのスキル。

大まかなプロセスは以下の通り:

- スキルに何をさせたいか、どのようにするかを決める
- スキルのドラフトを書く
- いくつかのテストプロンプトを作成し、そのスキルにアクセスできるclaudeで実行する
- ユーザーが結果を定性的・定量的に評価するのを助ける
  - 実行中にバックグラウンドで、定量的evalがない場合はドラフトを作成する（ある場合は、そのまま使うか、変更が必要な場合は修正する）。それをユーザーに説明する
  - `eval-viewer/generate_review.py`スクリプトを使ってユーザーに結果を表示し、定量的な指標も確認できるようにする
- ユーザーの評価フィードバックに基づいてスキルを書き直す
- 満足するまで繰り返す
- テストセットを拡大し、より大規模で再試行する

このスキルを使う際のあなたの仕事は、ユーザーがこのプロセスのどこにいるかを把握し、段階を進める手助けをすること。ユーザーが既にドラフトを持っている場合は、eval/反復ループに直接進める。

ユーザーが「大量のevalは不要、感覚でやってほしい」と言えば、それに従うこと。

## ユーザーとのコミュニケーション

スキルクリエーターは、コーディングの専門用語に対する親しみの程度が幅広いユーザーに使われる可能性がある。コンテキストのヒントに注意し、コミュニケーションの言い方を理解すること。デフォルトの場合として:

- 「evaluation」と「benchmark」はギリギリOK
- 「JSON」と「assertion」については、ユーザーがそれらを知っていることを示す十分な手がかりを確認してから、説明なしに使用する

---

## スキルの作成

### 意図の把握

ユーザーの意図を理解することから始める。現在の会話には、ユーザーが取り込みたいワークフローが既に含まれている場合がある（例: 「これをスキルにして」）。その場合、まず会話履歴から回答を抽出する — 使用したツール、ステップの順序、ユーザーが行った修正など。

1. このスキルはClaudeに何を可能にすべきか？
2. このスキルはいつトリガーすべきか？（ユーザーのフレーズ/コンテキスト）
3. 期待される出力フォーマットは何か？
4. スキルが機能することを検証するためのテストケースを設定すべきか？

### インタビューとリサーチ

エッジケース、入出力フォーマット、サンプルファイル、成功基準、依存関係について積極的に質問する。この部分が整理されるまでテストプロンプトを書くのは待つこと。

### スキルファイルの作成（二段階構造で必ず作る）

新規スキルは常に **SKILL.md + INSTRUCTIONS.md の2ファイル構成** で作成する。
SKILL.md に詳細内容を書いてはいけない。

#### ステップ1: 最小化した SKILL.md を作成する

フロントマター + INSTRUCTIONS.md への参照のみ。本文に詳細を書かない。

```markdown
---
name: {スキル名}
description: >
  {いつトリガーするか}。{何をするか}。
---

# {スキルタイトル}

詳細な手順: [INSTRUCTIONS.md](INSTRUCTIONS.md)

## リソース

- [INSTRUCTIONS.md](INSTRUCTIONS.md) — {内容の一言説明}
```

フロントマターの各フィールド:
- **name**: スキルの識別子（ハイフン区切り小文字、最大64文字）。動名詞形推奨: `processing-pdfs`、`analyzing-code`（動詞 + -ing）。`anthropic`・`claude` は予約語で使用不可
- **description**: いつトリガーするか + 何をするか。**三人称**で書く（「Processes X when...」「Generates Y for...」形式）。「I can...」「You can...」は使わない — description はシステムプロンプトに注入されるため一人称は誤動作の原因になる。Claude は undertrigger しがちなので少し「積極的」に書く。最大1024文字
- **compatibility**: 必要なツール・依存関係（オプション）

#### ステップ2: INSTRUCTIONS.md に詳細内容を書く

スキルの全詳細（手順・ルール・コード例・出力フォーマット等）を INSTRUCTIONS.md に記述する。
スキルが呼び出された後に Read ツールで読み込まれるため、分量を気にせず書いてよい。

#### ステップ3: evals.json を必ず作成する（必須）

スキルの品質を担保するため、作成と同時に `evaluations/evals.json` を生成する。
後回しにしない — スキルを作るたびに必ずこのひな形を作成すること。

```json
{
  "skill_name": "{スキル名}",
  "evals": [
    {
      "id": 1,
      "prompt": "（このスキルをトリガーするユーザー発話の例）",
      "expected_behavior": "（期待される動作の説明）",
      "pass_criteria": "（合否判定の基準）",
      "assertions": []
    },
    {
      "id": 2,
      "prompt": "（別のトリガー例。エッジケースが望ましい）",
      "expected_behavior": "（期待される動作）",
      "pass_criteria": "（合否判定）",
      "assertions": []
    }
  ]
}
```

> **なぜ必須か**: `meta/health-check.py` は evals.json の有無を品質チェックする。
> evals.json がないスキルは「未テスト」として報告される。

#### ステップ4: registry に登録する

新スキルを作成したら、ルーティングインデックスを更新する:

```bash
python .claude/meta/generate-registry.py
```

これにより `.claude/registry/skills.yaml` が最新化され、
Claude がスキルを適切にルーティングできるようになる。

### スキル作成ガイド

#### スキルの構造とコンテキスト最適化

87スキルを運用した結果、SKILL.md が合計898KBに膨張した事例がある。スキルが呼ばれるたびに SKILL.md の全内容がシステムプロンプトに注入される仕組みのため、スキル数が増えるほどコンテキストを圧迫する。

**推奨構造（二段階ロード）:**

```
skill-name/
├── SKILL.md (必須) ← フロントマター + INSTRUCTIONS.md への参照のみ (~200-500バイト)
│   # 常にコンテキストに注入されるため、極力小さく保つ
├── INSTRUCTIONS.md ← 全ての詳細手順・ルール・コマンド
│   # スキル起動後に Read ツールで読み込む
├── evaluations/     ← 精度保証に必須（eval-driven development）
│   └── evals.json
└── バンドルリソース（オプション）
    ├── scripts/    - 決定論的/反復的なタスクのための実行可能コード
    ├── references/ - 必要に応じてコンテキストに読み込まれるドキュメント
    └── assets/     - 出力で使用するファイル（テンプレート、アイコン、フォント）
```

**実測値（二段階ロード適用後）:**

| 対象 | 分割前 | 分割後 | 削減率 |
|------|--------|--------|--------|
| スキル1個（例） | 37,813B | 314B | 99.2% |
| プロジェクト全体 | 898KB | 27KB | **97%削減** |

#### プログレッシブディスクロージャー（3段階ロード）

1. **フロントマター**（name + description）— 常にコンテキストに（約100ワード）
   - スキルの選択・マッチングに使われる
2. **SKILL.md 本文**— スキルがトリガーされた時に注入
   - 最小限に保つ。理想は INSTRUCTIONS.md への参照 + 関連スキルのリストのみ
3. **バンドルリソース**（INSTRUCTIONS.md、references/ 等）— 必要に応じて Read で読み込む
   - 無制限に詳細を置ける

#### SKILL.md の書き方（最小化パターン）

```markdown
---
name: skill-name
description: >
  いつ使うか（具体的なトリガー条件）+ 何をするか（出力・効果）。
  日本語でも英語でも可。
---

# スキル名

詳細な手順: [INSTRUCTIONS.md](INSTRUCTIONS.md)

## リソース

- [INSTRUCTIONS.md](INSTRUCTIONS.md) — 全手順・ルール・例
- [references/foo.md](references/foo.md) — 必要に応じて読む追加資料

## 関連スキル

- [other-skill](../other-skill/SKILL.md): 補完的なスキル
```

#### ドメイン整理

スキルが複数のドメイン/フレームワークをサポートする場合、バリアント別に整理する:

```
cloud-deploy/
├── SKILL.md（ワークフロー + 選択）
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```

#### 記述パターン

指示では命令形を使用することを好む。

**出力フォーマットの定義** — このように書ける:
```markdown
## レポート構造
常にこの正確なテンプレートを使用する:
# [タイトル]
## エグゼクティブサマリー
## 主要な発見
## 推奨事項
```

### 文章スタイル

重い「MUST」の代わりに、なぜ重要かをモデルに説明するように心がける。心の理論を使い、スキルを一般的で特定の例に超特化しないようにする。ドラフトを書いてから新鮮な目で見直して改善する。

### アンチパターン（避けること）

| アンチパターン | 理由 | 代替 |
|-------------|------|------|
| description を一人称で書く | システムプロンプト注入で誤動作 | 三人称：「Processes X...」 |
| name に `anthropic` / `claude` を含む | 予約語 | 別の表現を使う |
| ネストが2段以上の参照ファイル | Claude が途中で読み込みを止める | SKILL.md から直接参照する |
| Windows パス（`\`）を使う | クロスプラットフォームで動作しない | 常にスラッシュ（`/`）を使う |
| 複数の手法を等価に並列提示する | Claude が迷う | デフォルトを1つ決めてフォールバックを示す |
| 時限性のある情報を埋め込む | すぐ陳腐化する | 「旧パターン」セクションに移動 |

### テストケース

スキルのドラフトを作成した後、実際のユーザーが実際に言うような2〜3のリアルなテストプロンプトを考える。

テストケースを`evaluations/evals.json`に保存する。アサーションはまだ書かない — プロンプトだけ。

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "ユーザーのタスクプロンプト",
      "expected_output": "期待される結果の説明",
      "files": []
    }
  ]
}
```

完全なスキーマ（後で追加する`assertions`フィールドを含む）は`references/schemas.md`を参照。

---

## テストケースの実行と評価

このセクションは1つの連続したシーケンス — 途中で止まらないこと。`/skill-test`や他のテストスキルは使わないこと。

結果はスキルディレクトリの兄弟として`<skill-name>-workspace/`に入れる。ワークスペース内でイテレーション別（`iteration-1/`、`iteration-2/`など）に整理する。

### ステップ1: 同じターンで全実行（with-skillとbaseline）を開始する

各テストケースについて、同じターンで2つのサブエージェントを生成する — 1つはスキルあり、1つはなし。すべてを一度に起動する。

**With-skill実行:**
```
このタスクを実行する:
- スキルパス: <path-to-skill>
- タスク: <eval prompt>
- 入力ファイル: <eval filesがあれば>
- 出力の保存先: <workspace>/iteration-<N>/eval-<ID>/with_skill/outputs/
```

**Baseline実行**:
- **新しいスキルを作成する場合**: スキルなし。`without_skill/outputs/`に保存。
- **既存のスキルを改善する場合**: 古いバージョン。`old_skill/outputs/`に保存。

各テストケースに`eval_metadata.json`を書く:

```json
{
  "eval_id": 0,
  "eval_name": "descriptive-name-here",
  "prompt": "ユーザーのタスクプロンプト",
  "assertions": []
}
```

### ステップ2: 実行中にアサーションをドラフトする

実行が終わるのを待つだけでなく、この時間を生産的に使う。各テストケースの定量的アサーションをドラフトし、ユーザーに説明する。

### ステップ3: 実行が完了したらタイミングデータを取得する

各サブエージェントタスクが完了すると通知を受け取る。このデータをすぐに実行ディレクトリの`timing.json`に保存する:

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3
}
```

### ステップ4: 採点、集計、ビューアーの起動

全実行が完了したら:

1. **各実行を採点する** — `agents/grader.md`を読んで各アサーションを評価するgraderサブエージェントを生成する。結果を各実行ディレクトリの`grading.json`に保存する。

2. **ベンチマークに集計する**:
   ```bash
   python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>
   ```

3. **アナリストパスを実行する** — ベンチマークデータを読んでパターンを表面化させる。

4. **ビューアーを起動する**:
   ```bash
   nohup python <skill-creator-path>/eval-viewer/generate_review.py \
     <workspace>/iteration-N \
     --skill-name "my-skill" \
     --benchmark <workspace>/iteration-N/benchmark.json \
     > /dev/null 2>&1 &
   VIEWER_PID=$!
   ```

5. **ユーザーに伝える**: 「ブラウザで結果を開きました。2つのタブがあります — 「出力」では各テストケースをクリックしてフィードバックを残せます、「ベンチマーク」では定量的比較が表示されます。」

### ステップ5: フィードバックを読む

```json
{
  "reviews": [
    {"run_id": "eval-0-with_skill", "feedback": "グラフに軸ラベルがない", "timestamp": "..."},
    {"run_id": "eval-1-with_skill", "feedback": "", "timestamp": "..."}
  ],
  "status": "complete"
}
```

空のフィードバックはユーザーが問題ないと思ったことを意味する。

ビューアーサーバーが終わったら終了する:
```bash
kill $VIEWER_PID 2>/dev/null
```

---

## スキルの改善

### 改善のための考え方

1. **フィードバックを一般化する**: スキルは何百万回も使われる可能性がある。特定の例にオーバーフィットしないようにする。
2. **プロンプトをリーンに保つ**: 効果がないものを削除する。最終的な出力だけでなく、トランスクリプトを読む。
3. **「なぜ」を説明する**: すべてのことについて、なぜそれをモデルに求めているかを説明する。
4. **テストケース全体で繰り返される作業を探す**: 全テストケースで同じヘルパースクリプトを独自に書いた場合、それをスキルにバンドルすべきシグナル。

### イテレーションループ

スキルを改善した後:

1. スキルに改善を適用する
2. 新しい`iteration-<N+1>/`ディレクトリに全テストケースを再実行する
3. `--previous-workspace`を前のイテレーションに指定してレビュアーを起動する
4. ユーザーがレビューして完了と言うのを待つ
5. 新しいフィードバックを読み、再び改善し、繰り返す

---

## 既存スキルのコンテキスト最適化

既存の SKILL.md が肥大化している場合、以下の手順で二段階構造に分割する:

### 分割の判断基準

- SKILL.md が 50行を超えている → INSTRUCTIONS.md への分割を検討
- 複数スキルを運用していてコンテキストが重い → 優先して分割

### 手動分割手順

1. `INSTRUCTIONS.md` を新規作成し、SKILL.md の本文（フロントマター以外）を移動する
2. SKILL.md を最小化:
   ```markdown
   ---
   name: skill-name
   description: （既存のまま）
   ---

   詳細な手順: [INSTRUCTIONS.md](INSTRUCTIONS.md)

   ## リソース
   - [INSTRUCTIONS.md](INSTRUCTIONS.md) — 全手順
   ```
3. スキルが正常に機能するか動作確認する

### 効果の目安

| 状態 | SKILL.md サイズ | コンテキスト消費 |
|------|----------------|----------------|
| 分割前（詳細な指示） | 10,000〜40,000B | スキル呼び出しごとに全注入 |
| 分割後（フロントマターのみ） | 200〜500B | 97% 以上削減 |

---

## Description 最適化

SKILL.md フロントマターの description フィールドは、Claudeがスキルを呼び出すかどうかを決定する主要なメカニズム。

### ステップ1: トリガー eval クエリを生成する

should-trigger と should-not-trigger が混合した20の eval クエリを作成する:

```json
[
  {"query": "ユーザーのプロンプト", "should_trigger": true},
  {"query": "別のプロンプト", "should_trigger": false}
]
```

### ステップ2: ユーザーとレビューする

HTML テンプレートを使用して eval セットをユーザーに提示する:

1. `assets/eval_review.html`からテンプレートを読む
2. プレースホルダーを置き換える
3. 一時ファイル（例: `/tmp/eval_review_<skill-name>.html`）に書いて開く

### ステップ3: 最適化ループを実行する

バックグラウンドで実行:

```bash
python -m scripts.run_loop \
  --eval-set <path-to-trigger-eval.json> \
  --skill-path <path-to-skill> \
  --model <model-id-powering-this-session> \
  --max-iterations 5 \
  --verbose
```

### ステップ4: 結果を適用する

JSON の `best_description` を取り、スキルの SKILL.md フロントマターを更新する。

---

## SDK・Claude -p との統合（チーム・組織での運用）

個人の作業を超えてスキルをチームや自動化パイプラインで活用するには:

```bash
# Claude Code CLI での非対話実行（-p = print mode）
claude -p "このワークフローをスキルにして" \
  --skill ./skills/skill-creator/

# パイプラインでの利用
cat workflow.md | claude -p "スキルを作って" --skill ./skill-creator/
```

```python
# Anthropic Agent SDK での活用
import anthropic
client = anthropic.Anthropic()
# Agent SDK の skill 機能でスキルを組み込む
# 詳細: https://docs.anthropic.com/en/agent-sdk/skills
```

スキルを `.claude/` ディレクトリで管理し、チーム全員がリポジトリ経由で利用できるようにすることで、個人の知見を組織資産に昇華できる。

---

## 参照ファイル

- [agents/grader.md](agents/grader.md) — アサーションを出力に対して評価する方法
- [agents/comparator.md](agents/comparator.md) — 2つの出力間のブラインドA/B比較の方法
- [agents/analyzer.md](agents/analyzer.md) — あるバージョンが別のバージョンより優れている理由を分析する方法
- [references/schemas.md](references/schemas.md) — evals.json、grading.json などのJSON構造
- [evaluations/evals.json](evaluations/evals.json) — このスキル自身のテストケース
