# スキル作成のベストプラクティス

> Claude が発見し、うまく活用できる効果的なスキルの書き方を学びます。

優れたスキルは簡潔で、よく構造化されており、実際の使用でテストされています。このガイドでは、Claude が発見し効果的に使用できるスキルを書くための実践的な判断指針を提供します。

スキルの仕組みに関する概念的な背景は、[スキル概要](/en/docs/agents-and-tools/agent-skills/overview)を参照してください。

## 基本原則

### 簡潔さが鍵

[コンテキストウィンドウ](https://platform.claude.com/docs/en/build-with-claude/context-windows)は公共財です。スキルは Claude が知る必要のある他のすべての情報とコンテキストウィンドウを共有しています：

* システムプロンプト
* 会話履歴
* 他のスキルのメタデータ
* 実際のリクエスト

スキル内のすべてのトークンに即座のコストがかかるわけではありません。起動時には、すべてのスキルからメタデータ（名前と説明）のみがプリロードされます。Claude はスキルが関連性を持つ場合にのみ SKILL.md を読み、追加ファイルは必要に応じて読みます。ただし、SKILL.md での簡潔さは依然として重要です。Claude がそれをロードすると、すべてのトークンが会話履歴や他のコンテキストと競合します。

**デフォルトの前提**: Claude はすでに非常に賢い

Claude がまだ持っていないコンテキストのみを追加してください。各情報を吟味してください：

* 「Claude は本当にこの説明を必要としているか？」
* 「Claude はこれを知っていると想定できるか？」
* 「この段落はトークンコストに見合うか？」

**良い例: 簡潔** (約50トークン):

````markdown  theme={null}
## PDF テキスト抽出

pdfplumber でテキスト抽出:

```python
import pdfplumber

with pdfplumber.open("file.pdf") as pdf:
    text = pdf.pages[0].extract_text()
```
````

**悪い例: 冗長すぎる** (約150トークン):

```markdown  theme={null}
## PDF テキスト抽出

PDF（Portable Document Format）ファイルはテキスト、画像、その他のコンテンツを含む
一般的なファイル形式です。PDFからテキストを抽出するにはライブラリを使用する
必要があります。PDF処理用のライブラリは多数ありますが、使いやすく
ほとんどのケースに対応できるpdfplumberを推奨します。
まずpipでインストールし、以下のコードを使用できます...
```

簡潔版では、Claude が PDF とは何か、ライブラリの使い方を知っていることを前提としています。

### 適切な自由度を設定する

タスクの脆弱性と変動性に合わせて具体性のレベルを調整します。

**高い自由度** (テキストベースの指示):

使用する場面：

* 複数のアプローチが有効な場合
* 判断がコンテキストに依存する場合
* ヒューリスティクスがアプローチを導く場合

例:

```markdown  theme={null}
## コードレビュープロセス

1. コードの構造と構成を分析する
2. 潜在的なバグやエッジケースを確認する
3. 可読性と保守性の改善を提案する
4. プロジェクトの慣例への準拠を検証する
```

**中程度の自由度** (パラメータ付き疑似コードまたはスクリプト):

使用する場面：

* 推奨パターンが存在する場合
* ある程度のバリエーションが許容される場合
* 設定が動作に影響する場合

例:

````markdown  theme={null}
## レポート生成

このテンプレートを使用し、必要に応じてカスタマイズ:

```python
def generate_report(data, format="markdown", include_charts=True):
    # データを処理
    # 指定フォーマットで出力を生成
    # オプションでビジュアライゼーションを含める
```
````

**低い自由度** (特定のスクリプト、パラメータなしまたは少数):

使用する場面：

* 操作が脆弱でエラーが起きやすい場合
* 一貫性が重要な場合
* 特定のシーケンスに従う必要がある場合

例:

````markdown  theme={null}
## データベースマイグレーション

このスクリプトを正確に実行:

```bash
python scripts/migrate.py --verify --backup
```

コマンドを変更したり追加のフラグを加えないでください。
````

**例え**: Claude を道を探索するロボットと考えてください：

* **両側が崖の狭い橋**: 安全な道は一つだけ。具体的なガードレールと正確な指示を提供します（低い自由度）。例: 正確な順序で実行する必要があるデータベースマイグレーション。
* **危険のない広い野原**: 多くの道が成功に繋がります。一般的な方向を示し、Claude が最適なルートを見つけることを信頼します（高い自由度）。例: コンテキストが最適なアプローチを決定するコードレビュー。

### 使用予定のすべてのモデルでテストする

スキルはモデルへの追加として機能するため、効果は基盤モデルに依存します。使用予定のすべてのモデルでスキルをテストしてください。

**モデル別のテスト考慮事項**:

* **Claude Haiku** (高速、経済的): スキルは十分なガイダンスを提供しているか？
* **Claude Sonnet** (バランス型): スキルは明確で効率的か？
* **Claude Opus** (強力な推論): スキルは過剰な説明をしていないか？

Opus で完璧に動作するものでも、Haiku ではより多くの詳細が必要かもしれません。複数のモデルでスキルを使用する予定がある場合は、すべてのモデルでうまく機能する指示を目指してください。

## スキルの構造

<Note>
  **YAML フロントマター**: SKILL.md のフロントマターは2つのフィールドをサポートしています：

  * `name` - スキルの人間が読める名前（最大64文字）
  * `description` - スキルの機能と使用タイミングの1行説明（最大1024文字）

  完全なスキル構造の詳細は、[スキル概要](/en/docs/agents-and-tools/agent-skills/overview#skill-structure)を参照してください。
</Note>

### 命名規則

一貫した命名パターンを使用して、スキルの参照や議論を容易にします。スキルが提供するアクティビティや機能を明確に説明するため、**動名詞形** (動詞 + -ing) を推奨します。

**良い命名例 (動名詞形)**:

* "Processing PDFs"
* "Analyzing spreadsheets"
* "Managing databases"
* "Testing code"
* "Writing documentation"

**許容される代替案**:

* 名詞句: "PDF Processing", "Spreadsheet Analysis"
* アクション指向: "Process PDFs", "Analyze Spreadsheets"

**避けるべきもの**:

* 曖昧な名前: "Helper", "Utils", "Tools"
* 汎用すぎる: "Documents", "Data", "Files"
* スキルコレクション内での不一致パターン

一貫した命名により以下が容易になります：

* ドキュメントや会話でスキルを参照する
* スキルの機能を一目で理解する
* 複数のスキルを整理・検索する
* プロフェッショナルで統一感のあるスキルライブラリを維持する

### 効果的な説明を書く

`description` フィールドはスキルの発見を可能にし、スキルの機能と使用タイミングの両方を含める必要があります。

<Warning>
  **常に三人称で書いてください**。説明はシステムプロンプトに注入されるため、一貫しない視点は発見の問題を引き起こす可能性があります。

  * **良い:** "Processes Excel files and generates reports"
  * **避ける:** "I can help you process Excel files"
  * **避ける:** "You can use this to process Excel files"
</Warning>

**具体的でキーワードを含めてください**。スキルの機能と使用する具体的なトリガー/コンテキストの両方を含めます。

各スキルには1つの説明フィールドがあります。説明はスキル選択において重要です：Claude は潜在的に100以上の利用可能なスキルから適切なスキルを選択するためにこれを使用します。説明は Claude がこのスキルを選択すべきタイミングを知るのに十分な詳細を提供する必要があり、SKILL.md の残りの部分が実装の詳細を提供します。

効果的な例:

**PDF処理スキル:**

```yaml  theme={null}
description: Extract text and tables from PDF files, fill forms, merge documents. Use when working with PDF files or when the user mentions PDFs, forms, or document extraction.
```

**Excel分析スキル:**

```yaml  theme={null}
description: Analyze Excel spreadsheets, create pivot tables, generate charts. Use when analyzing Excel files, spreadsheets, tabular data, or .xlsx files.
```

**Gitコミットヘルパースキル:**

```yaml  theme={null}
description: Generate descriptive commit messages by analyzing git diffs. Use when the user asks for help writing commit messages or reviewing staged changes.
```

曖昧な説明は避けてください：

```yaml  theme={null}
description: Helps with documents
```

```yaml  theme={null}
description: Processes data
```

```yaml  theme={null}
description: Does stuff with files
```

### 段階的開示パターン

SKILL.md は、オンボーディングガイドの目次のように、Claude を詳細な資料に導く概要として機能します。段階的開示の仕組みについては、概要の[スキルの仕組み](/en/docs/agents-and-tools/agent-skills/overview#how-skills-work)を参照してください。

**実践的なガイダンス:**

* 最適なパフォーマンスのため、SKILL.md の本体は500行以下に保つ
* この制限に近づいたら、コンテンツを別ファイルに分割する
* 以下のパターンを使用して、指示、コード、リソースを効果的に整理する

#### ビジュアル概要: シンプルから複雑へ

基本的なスキルは、メタデータと指示を含む SKILL.md ファイルのみで構成されます：

<img src="https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-simple-file.png?fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=87782ff239b297d9a9e8e1b72ed72db9" alt="YAMLフロントマターとマークダウン本体を含むシンプルなSKILL.mdファイル" data-og-width="2048" width="2048" data-og-height="1153" height="1153" data-path="images/agent-skills-simple-file.png" data-optimize="true" data-opv="3" srcset="https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-simple-file.png?w=280&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=c61cc33b6f5855809907f7fda94cd80e 280w, https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-simple-file.png?w=560&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=90d2c0c1c76b36e8d485f49e0810dbfd 560w, https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-simple-file.png?w=840&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=ad17d231ac7b0bea7e5b4d58fb4aeabb 840w, https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-simple-file.png?w=1100&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=f5d0a7a3c668435bb0aee9a3a8f8c329 1100w, https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-simple-file.png?w=1650&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=0e927c1af9de5799cfe557d12249f6e6 1650w, https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-simple-file.png?w=2500&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=46bbb1a51dd4c8202a470ac8c80a893d 2500w" />

スキルが成長するにつれて、Claude が必要に応じてのみロードする追加コンテンツをバンドルできます：

<img src="https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-bundling-content.png?fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=a5e0aa41e3d53985a7e3e43668a33ea3" alt="reference.mdやforms.mdなどの追加リファレンスファイルのバンドル" data-og-width="2048" width="2048" data-og-height="1327" height="1327" data-path="images/agent-skills-bundling-content.png" data-optimize="true" data-opv="3" srcset="https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-bundling-content.png?w=280&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=f8a0e73783e99b4a643d79eac86b70a2 280w, https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-bundling-content.png?w=560&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=dc510a2a9d3f14359416b706f067904a 560w, https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-bundling-content.png?w=840&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=82cd6286c966303f7dd914c28170e385 840w, https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-bundling-content.png?w=1100&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=56f3be36c77e4fe4b523df209a6824c6 1100w, https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-bundling-content.png?w=1650&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=d22b5161b2075656417d56f41a74f3dd 1650w, https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-bundling-content.png?w=2500&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=3dd4bdd6850ffcc96c6c45fcb0acd6eb 2500w" />

完全なスキルディレクトリ構造は以下のようになります：

```
pdf/
├── SKILL.md              # メインの指示（トリガー時にロード）
├── FORMS.md              # フォーム入力ガイド（必要に応じてロード）
├── reference.md          # API リファレンス（必要に応じてロード）
├── examples.md           # 使用例（必要に応じてロード）
└── scripts/
    ├── analyze_form.py   # ユーティリティスクリプト（実行用、ロード用ではない）
    ├── fill_form.py      # フォーム入力スクリプト
    └── validate.py       # バリデーションスクリプト
```

#### パターン 1: 参照付きの高レベルガイド

````markdown  theme={null}
---
name: PDF Processing
description: Extracts text and tables from PDF files, fills forms, and merges documents. Use when working with PDF files or when the user mentions PDFs, forms, or document extraction.
---

# PDF 処理

## クイックスタート

pdfplumber でテキスト抽出:
```python
import pdfplumber
with pdfplumber.open("file.pdf") as pdf:
    text = pdf.pages[0].extract_text()
```

## 高度な機能

**フォーム入力**: 完全なガイドは [FORMS.md](FORMS.md) を参照
**API リファレンス**: すべてのメソッドは [REFERENCE.md](REFERENCE.md) を参照
**使用例**: 一般的なパターンは [EXAMPLES.md](EXAMPLES.md) を参照
````

Claude は FORMS.md、REFERENCE.md、EXAMPLES.md を必要な場合にのみロードします。

#### パターン 2: ドメイン別の整理

複数のドメインを持つスキルでは、無関係なコンテキストのロードを避けるためにドメイン別にコンテンツを整理します。ユーザーが営業指標について尋ねたとき、Claude は営業関連のスキーマのみを読めばよく、財務やマーケティングのデータは不要です。これによりトークン使用量が少なく、コンテキストが焦点を絞ったものになります。

```
bigquery-skill/
├── SKILL.md (概要とナビゲーション)
└── reference/
    ├── finance.md (収益、請求メトリクス)
    ├── sales.md (商談、パイプライン)
    ├── product.md (API利用状況、機能)
    └── marketing.md (キャンペーン、アトリビューション)
```

````markdown SKILL.md theme={null}
# BigQuery データ分析

## 利用可能なデータセット

**財務**: 収益、ARR、請求 → [reference/finance.md](reference/finance.md) を参照
**営業**: 商談、パイプライン、アカウント → [reference/sales.md](reference/sales.md) を参照
**プロダクト**: API利用状況、機能、導入 → [reference/product.md](reference/product.md) を参照
**マーケティング**: キャンペーン、アトリビューション、メール → [reference/marketing.md](reference/marketing.md) を参照

## クイック検索

grep で特定のメトリクスを検索:

```bash
grep -i "revenue" reference/finance.md
grep -i "pipeline" reference/sales.md
grep -i "api usage" reference/product.md
```
````

#### パターン 3: 条件付き詳細

基本コンテンツを表示し、高度なコンテンツにリンク:

```markdown  theme={null}
# DOCX 処理

## ドキュメントの作成

新しいドキュメントには docx-js を使用。[DOCX-JS.md](DOCX-JS.md) を参照。

## ドキュメントの編集

シンプルな編集には、XML を直接変更。

**変更履歴の場合**: [REDLINING.md](REDLINING.md) を参照
**OOXML の詳細**: [OOXML.md](OOXML.md) を参照
```

Claude は REDLINING.md や OOXML.md をユーザーがその機能を必要とする場合にのみ読みます。

### 深いネストの参照を避ける

参照ファイルから参照された他のファイルに遭遇すると、Claude はファイルを部分的にしか読まない場合があります。ネストされた参照に遭遇すると、Claude はファイル全体を読む代わりに `head -100` のようなコマンドでコンテンツをプレビューする可能性があり、情報が不完全になります。

**SKILL.md からの参照は1階層までに保つ**。すべての参照ファイルは SKILL.md から直接リンクし、Claude が必要なときに完全なファイルを読めるようにします。

**悪い例: 深すぎる**:

```markdown  theme={null}
# SKILL.md
See [advanced.md](advanced.md)...

# advanced.md
See [details.md](details.md)...

# details.md
Here's the actual information...
```

**良い例: 1階層**:

```markdown  theme={null}
# SKILL.md

**基本的な使い方**: [SKILL.md 内の指示]
**高度な機能**: [advanced.md](advanced.md) を参照
**API リファレンス**: [reference.md](reference.md) を参照
**使用例**: [examples.md](examples.md) を参照
```

### 長いリファレンスファイルには目次を付ける

100行を超えるリファレンスファイルには、先頭に目次を含めてください。これにより、部分的な読み取りでプレビューする場合でも、Claude が利用可能な情報の全範囲を確認できます。

**例**:

```markdown  theme={null}
# API リファレンス

## 目次
- 認証とセットアップ
- コアメソッド (create, read, update, delete)
- 高度な機能 (バッチ操作、Webhook)
- エラーハンドリングパターン
- コード例

## 認証とセットアップ
...

## コアメソッド
...
```

Claude は必要に応じて完全なファイルを読むか、特定のセクションにジャンプできます。

このファイルシステムベースのアーキテクチャが段階的開示を実現する方法の詳細は、以下の高度なセクションの[ランタイム環境](#runtime-environment)セクションを参照してください。

## ワークフローとフィードバックループ

### 複雑なタスクにはワークフローを使用する

複雑な操作を明確な順序のステップに分解します。特に複雑なワークフローでは、Claude が応答にコピーして進行に応じてチェックできるチェックリストを提供します。

**例 1: 調査統合ワークフロー** (コードなしのスキル向け):

````markdown  theme={null}
## 調査統合ワークフロー

このチェックリストをコピーして進捗を追跡:

```
調査の進捗:
- [ ] ステップ 1: すべてのソースドキュメントを読む
- [ ] ステップ 2: 主要なテーマを特定する
- [ ] ステップ 3: 主張を相互参照する
- [ ] ステップ 4: 構造化された要約を作成する
- [ ] ステップ 5: 引用を確認する
```

**ステップ 1: すべてのソースドキュメントを読む**

`sources/` ディレクトリ内の各ドキュメントをレビュー。主要な議論と裏付けとなる証拠をメモする。

**ステップ 2: 主要なテーマを特定する**

ソース全体のパターンを探す。繰り返し出現するテーマは何か？ソース間で一致する点や不一致する点は？

**ステップ 3: 主張を相互参照する**

各主要な主張について、ソース資料に出典があることを確認する。各ポイントを裏付けるソースをメモする。

**ステップ 4: 構造化された要約を作成する**

テーマ別に調査結果を整理。含める内容:
- 主要な主張
- ソースからの裏付け証拠
- 対立する見解（ある場合）

**ステップ 5: 引用を確認する**

すべての主張が正しいソースドキュメントを参照していることを確認する。引用が不完全な場合は、ステップ 3 に戻る。
````

この例は、コードを必要としない分析タスクにワークフローがどのように適用されるかを示しています。チェックリストパターンは、複雑なマルチステッププロセスに適用できます。

**例 2: PDF フォーム入力ワークフロー** (コード付きスキル向け):

````markdown  theme={null}
## PDF フォーム入力ワークフロー

完了した項目をチェック:

```
タスクの進捗:
- [ ] ステップ 1: フォームを分析する (analyze_form.py を実行)
- [ ] ステップ 2: フィールドマッピングを作成する (fields.json を編集)
- [ ] ステップ 3: マッピングを検証する (validate_fields.py を実行)
- [ ] ステップ 4: フォームを入力する (fill_form.py を実行)
- [ ] ステップ 5: 出力を確認する (verify_output.py を実行)
```

**ステップ 1: フォームを分析する**

実行: `python scripts/analyze_form.py input.pdf`

フォームフィールドとその位置を抽出し、`fields.json` に保存します。

**ステップ 2: フィールドマッピングを作成する**

`fields.json` を編集して各フィールドに値を追加。

**ステップ 3: マッピングを検証する**

実行: `python scripts/validate_fields.py fields.json`

続行する前にバリデーションエラーを修正。

**ステップ 4: フォームを入力する**

実行: `python scripts/fill_form.py input.pdf fields.json output.pdf`

**ステップ 5: 出力を確認する**

実行: `python scripts/verify_output.py output.pdf`

検証に失敗した場合は、ステップ 2 に戻る。
````

明確なステップにより、Claude が重要なバリデーションをスキップすることを防ぎます。チェックリストは Claude とユーザーの両方がマルチステップワークフローの進捗を追跡するのに役立ちます。

### フィードバックループを実装する

**一般的なパターン**: バリデーター実行 → エラー修正 → 繰り返し

このパターンは出力品質を大幅に向上させます。

**例 1: スタイルガイド準拠** (コードなしのスキル向け):

```markdown  theme={null}
## コンテンツレビュープロセス

1. STYLE_GUIDE.md のガイドラインに従ってコンテンツを作成
2. チェックリストに照らしてレビュー:
   - 用語の一貫性を確認
   - 例が標準フォーマットに従っているか検証
   - 必須セクションがすべて存在するか確認
3. 問題が見つかった場合:
   - 各問題を具体的なセクション参照付きでメモ
   - コンテンツを修正
   - チェックリストを再度レビュー
4. すべての要件を満たした場合のみ続行
5. ドキュメントを確定して保存
```

これは、スクリプトの代わりにリファレンスドキュメントを使用するバリデーションループパターンを示しています。「バリデーター」は STYLE\_GUIDE.md であり、Claude は読み取りと比較でチェックを行います。

**例 2: ドキュメント編集プロセス** (コード付きスキル向け):

```markdown  theme={null}
## ドキュメント編集プロセス

1. `word/document.xml` を編集
2. **すぐにバリデーション**: `python ooxml/scripts/validate.py unpacked_dir/`
3. バリデーションに失敗した場合:
   - エラーメッセージを注意深くレビュー
   - XML の問題を修正
   - バリデーションを再実行
4. **バリデーションがパスした場合のみ続行**
5. 再構築: `python ooxml/scripts/pack.py unpacked_dir/ output.docx`
6. 出力ドキュメントをテスト
```

バリデーションループはエラーを早期に検出します。

## コンテンツガイドライン

### 時間に依存する情報を避ける

古くなる情報は含めないでください：

**悪い例: 時間依存** (古くなる):

```markdown  theme={null}
2025年8月以前にこれを行う場合は旧APIを使用してください。
2025年8月以降は新APIを使用してください。
```

**良い例** (「旧パターン」セクションを使用):

```markdown  theme={null}
## 現在の方法

v2 API エンドポイントを使用: `api.example.com/v2/messages`

## 旧パターン

<details>
<summary>レガシー v1 API (2025-08 廃止)</summary>

v1 API は以下を使用: `api.example.com/v1/messages`

このエンドポイントはサポートされなくなりました。
</details>
```

旧パターンセクションは、メインコンテンツを散らかすことなく歴史的コンテキストを提供します。

### 一貫した用語を使用する

1つの用語を選び、スキル全体で使用してください：

**良い - 一貫している**:

* 常に "API エンドポイント"
* 常に "フィールド"
* 常に "抽出"

**悪い - 不一致**:

* "API エンドポイント"、"URL"、"API ルート"、"パス" の混在
* "フィールド"、"ボックス"、"エレメント"、"コントロール" の混在
* "抽出"、"プル"、"取得"、"リトリーブ" の混在

一貫性は Claude が指示を理解し従うのに役立ちます。

## 一般的なパターン

### テンプレートパターン

出力フォーマットのテンプレートを提供。厳密さのレベルをニーズに合わせます。

**厳密な要件向け** (API レスポンスやデータフォーマットなど):

````markdown  theme={null}
## レポート構造

常にこの正確なテンプレート構造を使用:

```markdown
# [分析タイトル]

## エグゼクティブサマリー
[主要な発見の1段落の概要]

## 主要な発見
- データに裏付けられた発見 1
- データに裏付けられた発見 2
- データに裏付けられた発見 3

## 推奨事項
1. 具体的で実行可能な推奨事項
2. 具体的で実行可能な推奨事項
```
````

**柔軟なガイダンス向け** (適応が有用な場合):

````markdown  theme={null}
## レポート構造

以下は合理的なデフォルトフォーマットですが、分析に応じて最善の判断を行ってください:

```markdown
# [分析タイトル]

## エグゼクティブサマリー
[概要]

## 主要な発見
[発見した内容に基づいてセクションを適応]

## 推奨事項
[具体的なコンテキストに合わせて調整]
```

分析の種類に応じてセクションを調整してください。
````

### 例示パターン

出力品質が例を見ることに依存するスキルでは、通常のプロンプティングと同様に入力/出力ペアを提供します：

````markdown  theme={null}
## コミットメッセージのフォーマット

以下の例に従ってコミットメッセージを生成:

**例 1:**
入力: JWT トークンによるユーザー認証を追加
出力:
```
feat(auth): implement JWT-based authentication

Add login endpoint and token validation middleware
```

**例 2:**
入力: レポートで日付が正しく表示されないバグを修正
出力:
```
fix(reports): correct date formatting in timezone conversion

Use UTC timestamps consistently across report generation
```

**例 3:**
入力: 依存関係の更新とエラーハンドリングのリファクタリング
出力:
```
chore: update dependencies and refactor error handling

- Upgrade lodash to 4.17.21
- Standardize error response format across endpoints
```

このスタイルに従ってください: type(scope): 簡潔な説明、その後に詳細な説明。
````

例は、説明だけでは伝わりにくい望ましいスタイルと詳細レベルを Claude が理解するのに役立ちます。

### 条件付きワークフローパターン

判断ポイントで Claude を導く：

```markdown  theme={null}
## ドキュメント変更ワークフロー

1. 変更の種類を判断:

   **新しいコンテンツの作成？** → 以下の「作成ワークフロー」に従う
   **既存コンテンツの編集？** → 以下の「編集ワークフロー」に従う

2. 作成ワークフロー:
   - docx-js ライブラリを使用
   - ドキュメントをゼロから構築
   - .docx フォーマットにエクスポート

3. 編集ワークフロー:
   - 既存ドキュメントを展開
   - XML を直接変更
   - 各変更後にバリデーション
   - 完了時に再パック
```

<Tip>
  ワークフローが多くのステップで大きくなったり複雑になった場合は、別ファイルに分離し、タスクに応じて Claude に適切なファイルを読ませることを検討してください。
</Tip>

## 評価とイテレーション

### 評価を先に構築する

**広範なドキュメントを書く前に評価を作成してください。** これにより、スキルが想像上の問題ではなく実際の問題を解決することが保証されます。

**評価駆動開発:**

1. **ギャップの特定**: スキルなしで代表的なタスクに Claude を実行。具体的な失敗や不足しているコンテキストをドキュメント化
2. **評価の作成**: これらのギャップをテストする3つのシナリオを構築
3. **ベースラインの確立**: スキルなしの Claude のパフォーマンスを測定
4. **最小限の指示を記述**: ギャップに対応し評価をパスするのに十分なコンテンツのみを作成
5. **イテレーション**: 評価を実行し、ベースラインと比較し、改良

このアプローチにより、実現しない可能性のある要件を予測するのではなく、実際の問題を解決していることが保証されます。

**評価の構造**:

```json  theme={null}
{
  "skills": ["pdf-processing"],
  "query": "Extract all text from this PDF file and save it to output.txt",
  "files": ["test-files/document.pdf"],
  "expected_behavior": [
    "Successfully reads the PDF file using an appropriate PDF processing library or command-line tool",
    "Extracts text content from all pages in the document without missing any pages",
    "Saves the extracted text to a file named output.txt in a clear, readable format"
  ]
}
```

<Note>
  この例は、シンプルなテストルーブリックを持つデータ駆動型の評価を示しています。現在、これらの評価を実行する組み込みの方法は提供していません。ユーザーは独自の評価システムを作成できます。評価はスキルの有効性を測定する真実の情報源です。
</Note>

### Claude と反復的にスキルを開発する

最も効果的なスキル開発プロセスは Claude 自体を含みます。1つの Claude インスタンス（"Claude A"）と協力してスキルを作成し、他のインスタンス（"Claude B"）がテストします。Claude A は指示の設計と改良を支援し、Claude B は実際のタスクでテストします。これは、Claude モデルが効果的なエージェント指示の書き方とエージェントが必要とする情報の両方を理解しているために機能します。

**新しいスキルの作成:**

1. **スキルなしでタスクを完了する**: 通常のプロンプティングで Claude A と問題に取り組む。作業中に自然とコンテキストを提供し、好みを説明し、手続き的な知識を共有する。繰り返し提供する情報に注目する。

2. **再利用可能なパターンを特定する**: タスク完了後、今後の類似タスクに有用なコンテキストを特定する。

   **例**: BigQuery 分析に取り組んだ場合、テーブル名、フィールド定義、フィルタリングルール（「常にテストアカウントを除外する」など）、一般的なクエリパターンを提供したかもしれない。

3. **Claude A にスキルの作成を依頼する**: 「使用した BigQuery 分析パターンをキャプチャするスキルを作成してください。テーブルスキーマ、命名規則、テストアカウントのフィルタリングルールを含めてください。」

   <Tip>
     Claude モデルはスキルのフォーマットと構造をネイティブに理解しています。スキルの作成を支援するために特別なシステムプロンプトや「スキル作成スキル」は必要ありません。Claude にスキルの作成を依頼するだけで、適切なフロントマターと本文コンテンツを含む適切に構造化された SKILL.md コンテンツが生成されます。
   </Tip>

4. **簡潔さをレビューする**: Claude A が不要な説明を追加していないか確認する。「勝率の説明を削除してください - Claude はすでにそれを知っています。」と依頼する。

5. **情報アーキテクチャを改善する**: Claude A にコンテンツをより効果的に整理するよう依頼する。例: 「テーブルスキーマを別のリファレンスファイルに整理してください。後でテーブルを追加するかもしれません。」

6. **類似タスクでテストする**: Claude B（スキルがロードされた新しいインスタンス）を使用して、関連するユースケースでスキルをテストする。Claude B が適切な情報を見つけ、ルールを正しく適用し、タスクをうまく処理するか観察する。

7. **観察に基づいてイテレーションする**: Claude B が苦労したり何かを見落としたりした場合、具体的な内容を Claude A に伝える: 「Claude がこのスキルを使用したとき、Q4 の日付フィルタリングを忘れました。日付フィルタリングパターンのセクションを追加すべきでしょうか？」

**既存スキルのイテレーション:**

同じ階層的パターンがスキルの改善時にも続きます。以下を交互に行います：

* **Claude A との作業** (スキルの改良を支援する専門家)
* **Claude B でのテスト** (実際の作業を行うためにスキルを使用するエージェント)
* **Claude B の動作を観察** して洞察を Claude A に持ち帰る

1. **実際のワークフローでスキルを使用する**: Claude B（スキルがロード済み）にテストシナリオではなく実際のタスクを与える

2. **Claude B の動作を観察する**: 苦労する点、成功する点、予期しない選択をする点に注目する

   **観察の例**: 「Claude B に地域別営業レポートを依頼したとき、クエリは書いたがテストアカウントのフィルタリングを忘れた。スキルにはこのルールが記載されているのに。」

3. **改善のために Claude A に戻る**: 現在の SKILL.md と観察した内容を共有する。「Claude B が地域レポートを依頼されたときにテストアカウントのフィルタリングを忘れたのに気づきました。スキルにはフィルタリングについて記載されていますが、十分に目立たないのかもしれません？」

4. **Claude A の提案をレビューする**: Claude A はルールをより目立つようにする再構成、「always filter」ではなく「MUST filter」のような強い表現の使用、ワークフローセクションの再構築を提案するかもしれない。

5. **変更を適用してテストする**: Claude A の改良でスキルを更新し、Claude B で類似のリクエストに対して再テスト

6. **使用に基づいて繰り返す**: 新しいシナリオに遭遇するたびにこの観察-改良-テストサイクルを続ける。各イテレーションは仮定ではなく実際のエージェントの動作に基づいてスキルを改善する。

**チームフィードバックの収集:**

1. チームメイトとスキルを共有し、使用状況を観察する
2. 質問する: スキルは期待どおりに起動するか？指示は明確か？何が不足しているか？
3. フィードバックを取り入れて、自分の使用パターンの盲点に対処する

**このアプローチが機能する理由**: Claude A はエージェントのニーズを理解し、あなたはドメインの専門知識を提供し、Claude B は実際の使用を通じてギャップを明らかにし、反復的な改良が仮定ではなく観察された動作に基づいてスキルを改善します。

### Claude がスキルをナビゲートする方法を観察する

スキルのイテレーション中に、Claude が実際にスキルをどのように使用するかに注目してください。以下を監視します：

* **予期しない探索パス**: Claude が予想しない順序でファイルを読んでいないか？構造が直感的でない可能性がある
* **見落とされた接続**: Claude が重要なファイルへの参照をたどれていないか？リンクをより明示的または目立つようにする必要がある
* **特定セクションへの過度の依存**: Claude が同じファイルを繰り返し読んでいる場合、そのコンテンツをメインの SKILL.md に含めることを検討する
* **無視されたコンテンツ**: Claude がバンドルファイルにアクセスしない場合、不要であるかメインの指示で十分にシグナルされていない可能性がある

仮定ではなくこれらの観察に基づいてイテレーションしてください。スキルのメタデータの 'name' と 'description' は特に重要です。Claude は現在のタスクに応じてスキルをトリガーするかどうかを決定する際にこれらを使用します。スキルの機能と使用すべきタイミングを明確に記述してください。

## 避けるべきアンチパターン

### Windows スタイルのパスを避ける

Windows 上でも、ファイルパスには常にスラッシュを使用：

* 良い: `scripts/helper.py`, `reference/guide.md`
* 避ける: `scripts\helper.py`, `reference\guide.md`

Unix スタイルのパスはすべてのプラットフォームで動作しますが、Windows スタイルのパスは Unix システムでエラーを引き起こします。

### 選択肢を多く提示しすぎない

必要でない限り複数のアプローチを提示しないでください：

````markdown  theme={null}
**悪い例: 選択肢が多すぎる** (混乱を招く):
「pypdf、pdfplumber、PyMuPDF、pdf2image、のいずれかを使用できます...」

**良い例: デフォルトを提供** (逃げ道付き):
「テキスト抽出には pdfplumber を使用:
```python
import pdfplumber
```

OCR が必要なスキャン済み PDF には、代わりに pdf2image と pytesseract を使用。」
````

## 高度な機能: 実行可能コード付きスキル

以下のセクションは、実行可能スクリプトを含むスキルに焦点を当てています。スキルがマークダウンの指示のみを使用する場合は、[効果的なスキルのチェックリスト](#checklist-for-effective-skills)にスキップしてください。

### 問題を解決し、丸投げしない

スキル用のスクリプトを書くとき、Claude に丸投げするのではなくエラー状態を処理してください。

**良い例: エラーを明示的に処理**:

```python  theme={null}
def process_file(path):
    """Process a file, creating it if it doesn't exist."""
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        # Create file with default content instead of failing
        print(f"File {path} not found, creating default")
        with open(path, 'w') as f:
            f.write('')
        return ''
    except PermissionError:
        # Provide alternative instead of failing
        print(f"Cannot access {path}, using default")
        return ''
```

**悪い例: Claude に丸投げ**:

```python  theme={null}
def process_file(path):
    # Just fail and let Claude figure it out
    return open(path).read()
```

設定パラメータも「ブードゥー定数」(Ousterhout の法則) を避けるために正当化しドキュメント化する必要があります。正しい値がわからないなら、Claude がどうやって決定できるでしょうか？

**良い例: 自己ドキュメント化**:

```python  theme={null}
# HTTP requests typically complete within 30 seconds
# Longer timeout accounts for slow connections
REQUEST_TIMEOUT = 30

# Three retries balances reliability vs speed
# Most intermittent failures resolve by the second retry
MAX_RETRIES = 3
```

**悪い例: マジックナンバー**:

```python  theme={null}
TIMEOUT = 47  # Why 47?
RETRIES = 5   # Why 5?
```

### ユーティリティスクリプトを提供する

Claude がスクリプトを書くことは可能ですが、事前に作成されたスクリプトには利点があります：

**ユーティリティスクリプトの利点**:

* 生成されたコードよりも信頼性が高い
* トークンを節約（コンテキストにコードを含める必要がない）
* 時間を節約（コード生成が不要）
* 使用全体で一貫性を確保

<img src="https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-executable-scripts.png?fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=4bbc45f2c2e0bee9f2f0d5da669bad00" alt="指示ファイルと並べて実行可能スクリプトをバンドル" data-og-width="2048" width="2048" data-og-height="1154" height="1154" data-path="images/agent-skills-executable-scripts.png" data-optimize="true" data-opv="3" srcset="https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-executable-scripts.png?w=280&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=9a04e6535a8467bfeea492e517de389f 280w, https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-executable-scripts.png?w=560&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=e49333ad90141af17c0d7651cca7216b 560w, https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-executable-scripts.png?w=840&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=954265a5df52223d6572b6214168c428 840w, https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-executable-scripts.png?w=1100&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=2ff7a2d8f2a83ee8af132b29f10150fd 1100w, https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-executable-scripts.png?w=1650&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=48ab96245e04077f4d15e9170e081cfb 1650w, https://mintcdn.com/anthropic-claude-docs/4Bny2bjzuGBK7o00/images/agent-skills-executable-scripts.png?w=2500&fit=max&auto=format&n=4Bny2bjzuGBK7o00&q=85&s=0301a6c8b3ee879497cc5b5483177c90 2500w" />

上の図は、実行可能スクリプトが指示ファイルとどのように連携するかを示しています。指示ファイル (forms.md) がスクリプトを参照し、Claude はコンテキストにその内容をロードせずにスクリプトを実行できます。

**重要な区別**: 指示で Claude が以下のどちらを行うべきか明確にしてください：

* **スクリプトを実行する** (最も一般的): 「`analyze_form.py` を実行してフィールドを抽出」
* **参照として読む** (複雑なロジック用): 「フィールド抽出アルゴリズムは `analyze_form.py` を参照」

ほとんどのユーティリティスクリプトでは、より信頼性が高く効率的なため実行が推奨されます。スクリプト実行の仕組みの詳細は、以下の[ランタイム環境](#runtime-environment)セクションを参照してください。

**例**:

````markdown  theme={null}
## ユーティリティスクリプト

**analyze_form.py**: PDF からすべてのフォームフィールドを抽出

```bash
python scripts/analyze_form.py input.pdf > fields.json
```

出力フォーマット:
```json
{
  "field_name": {"type": "text", "x": 100, "y": 200},
  "signature": {"type": "sig", "x": 150, "y": 500}
}
```

**validate_boxes.py**: バウンディングボックスの重なりをチェック

```bash
python scripts/validate_boxes.py fields.json
# Returns: "OK" or lists conflicts
```

**fill_form.py**: フィールド値を PDF に適用

```bash
python scripts/fill_form.py input.pdf fields.json output.pdf
```
````

### ビジュアル分析を使用する

入力を画像としてレンダリングできる場合は、Claude に分析させてください：

````markdown  theme={null}
## フォームレイアウト分析

1. PDF を画像に変換:
   ```bash
   python scripts/pdf_to_images.py form.pdf
   ```

2. 各ページ画像を分析してフォームフィールドを特定
3. Claude はフィールドの位置と種類を視覚的に確認できる
````

<Note>
  この例では、`pdf_to_images.py` スクリプトを記述する必要があります。
</Note>

Claude のビジョン機能はレイアウトや構造の理解に役立ちます。

### 検証可能な中間出力を作成する

Claude が複雑でオープンエンドなタスクを実行する際、間違いが発生する可能性があります。「計画-検証-実行」パターンは、Claude にまず構造化されたフォーマットで計画を作成させ、その計画をスクリプトで検証してから実行することで、エラーを早期に検出します。

**例**: Claude に PDF の50フォームフィールドをスプレッドシートに基づいて更新するよう依頼することを想像してください。検証なしでは、Claude は存在しないフィールドを参照したり、矛盾する値を作成したり、必須フィールドを見落としたり、更新を正しく適用できない可能性があります。

**解決策**: 上記のワークフローパターン (PDF フォーム入力) を使用しますが、変更を適用する前に検証される中間の `changes.json` ファイルを追加します。ワークフローは次のようになります：分析 → **計画ファイルの作成** → **計画の検証** → 実行 → 確認。

**このパターンが機能する理由:**

* **エラーを早期に検出**: 変更が適用される前にバリデーションが問題を発見
* **機械検証可能**: スクリプトが客観的な検証を提供
* **可逆的な計画**: Claude はオリジナルに触れずに計画をイテレーションできる
* **明確なデバッグ**: エラーメッセージが具体的な問題を指摘

**使用するタイミング**: バッチ操作、破壊的な変更、複雑なバリデーションルール、ハイステークスな操作。

**実装のヒント**: バリデーションスクリプトは「Field 'signature\_date' not found. Available fields: customer\_name, order\_total, signature\_date\_signed」のような具体的なエラーメッセージで冗長にし、Claude が問題を修正するのに役立てます。

### 依存関係のパッケージ化

スキルはプラットフォーム固有の制限があるコード実行環境で実行されます：

* **claude.ai**: npm と PyPI からパッケージをインストールし、GitHub リポジトリからプルできる
* **Anthropic API**: ネットワークアクセスなし、ランタイムパッケージインストールなし

SKILL.md に必要なパッケージを一覧し、[コード実行ツールのドキュメント](/en/docs/agents-and-tools/tool-use/code-execution-tool)で利用可能であることを確認してください。

### ランタイム環境

スキルはファイルシステムアクセス、bash コマンド、コード実行機能を持つコード実行環境で実行されます。このアーキテクチャの概念的な説明については、概要の[スキルアーキテクチャ](/en/docs/agents-and-tools/agent-skills/overview#the-skills-architecture)を参照してください。

**作成への影響:**

**Claude がスキルにアクセスする方法:**

1. **メタデータのプリロード**: 起動時に、すべてのスキルの YAML フロントマターからの名前と説明がシステムプロンプトにロードされる
2. **オンデマンドのファイル読み取り**: Claude は必要に応じて bash の Read ツールを使用してファイルシステムから SKILL.md やその他のファイルにアクセス
3. **スクリプトの効率的な実行**: ユーティリティスクリプトは完全な内容をコンテキストにロードせずに bash で実行可能。スクリプトの出力のみがトークンを消費
4. **大きなファイルのコンテキストペナルティなし**: リファレンスファイル、データ、ドキュメントは実際に読み取られるまでコンテキストトークンを消費しない

* **ファイルパスが重要**: Claude はファイルシステムのようにスキルディレクトリをナビゲートする。スラッシュ (`reference/guide.md`) を使用し、バックスラッシュは使用しない
* **ファイルに説明的な名前を付ける**: 内容を示す名前を使用: `form_validation_rules.md`, `doc2.md` ではない
* **発見しやすいように整理**: ドメインまたは機能別にディレクトリを構造化
  * 良い: `reference/finance.md`, `reference/sales.md`
  * 悪い: `docs/file1.md`, `docs/file2.md`
* **包括的なリソースをバンドル**: 完全な API ドキュメント、豊富な例、大きなデータセットを含める; アクセスされるまでコンテキストペナルティなし
* **決定論的な操作にはスクリプトを推奨**: Claude にバリデーションコードを生成させるのではなく、`validate_form.py` を記述
* **実行意図を明確にする**:
  * 「`analyze_form.py` を実行してフィールドを抽出」(実行)
  * 「抽出アルゴリズムは `analyze_form.py` を参照」(参照として読む)
* **ファイルアクセスパターンをテスト**: 実際のリクエストでテストして Claude がディレクトリ構造をナビゲートできることを確認

**例:**

```
bigquery-skill/
├── SKILL.md (概要、リファレンスファイルへのポインタ)
└── reference/
    ├── finance.md (収益メトリクス)
    ├── sales.md (パイプラインデータ)
    └── product.md (使用状況分析)
```

ユーザーが収益について尋ねると、Claude は SKILL.md を読み、`reference/finance.md` への参照を確認し、bash を呼び出してそのファイルのみを読みます。sales.md と product.md ファイルはファイルシステム上に残り、必要になるまでコンテキストトークンをゼロで消費します。このファイルシステムベースのモデルが段階的開示を実現します。Claude は各タスクに必要なものを正確にナビゲートし選択的にロードできます。

技術アーキテクチャの完全な詳細は、スキル概要の[スキルの仕組み](/en/docs/agents-and-tools/agent-skills/overview#how-skills-work)を参照してください。

### MCP ツール参照

スキルが MCP (Model Context Protocol) ツールを使用する場合、「ツールが見つからない」エラーを避けるために常に完全修飾ツール名を使用してください。

**フォーマット**: `ServerName:tool_name`

**例**:

```markdown  theme={null}
Use the BigQuery:bigquery_schema tool to retrieve table schemas.
Use the GitHub:create_issue tool to create issues.
```

ここで：

* `BigQuery` と `GitHub` は MCP サーバー名
* `bigquery_schema` と `create_issue` はそのサーバー内のツール名

サーバープレフィックスがないと、特に複数の MCP サーバーが利用可能な場合に Claude がツールを見つけられない可能性があります。

### ツールがインストール済みと仮定しない

パッケージが利用可能と仮定しないでください：

````markdown  theme={null}
**悪い例: インストール済みと仮定**:
「pdf ライブラリを使用してファイルを処理してください。」

**良い例: 依存関係を明示**:
「必要なパッケージをインストール: `pip install pypdf`

使用方法:
```python
from pypdf import PdfReader
reader = PdfReader("file.pdf")
```」
````

## 技術的な注意事項

### YAML フロントマターの要件

SKILL.md のフロントマターには `name`（最大64文字）と `description`（最大1024文字）フィールドのみが含まれます。完全な構造の詳細は[スキル概要](/en/docs/agents-and-tools/agent-skills/overview#skill-structure)を参照してください。

### トークンバジェット

最適なパフォーマンスのため、SKILL.md の本体は500行以下に保ってください。コンテンツがこれを超える場合は、前述の段階的開示パターンを使用して別ファイルに分割してください。アーキテクチャの詳細は[スキル概要](/en/docs/agents-and-tools/agent-skills/overview#how-skills-work)を参照してください。

## 効果的なスキルのチェックリスト

スキルを共有する前に確認：

### コア品質

* [ ] 説明が具体的でキーワードを含んでいる
* [ ] 説明にスキルの機能と使用タイミングの両方が含まれている
* [ ] SKILL.md の本体が500行以下
* [ ] 追加の詳細が別ファイルにある（必要な場合）
* [ ] 時間に依存する情報がない（または「旧パターン」セクションに配置）
* [ ] スキル全体で用語が一貫している
* [ ] 例が抽象的ではなく具体的
* [ ] ファイル参照が1階層
* [ ] 段階的開示が適切に使用されている
* [ ] ワークフローに明確なステップがある

### コードとスクリプト

* [ ] スクリプトは Claude に丸投げせず問題を解決する
* [ ] エラーハンドリングが明示的で有用
* [ ] 「ブードゥー定数」がない（すべての値が正当化されている）
* [ ] 必要なパッケージが指示に一覧され利用可能であることが確認済み
* [ ] スクリプトに明確なドキュメントがある
* [ ] Windows スタイルのパスがない（すべてスラッシュ）
* [ ] 重要な操作にバリデーション/検証ステップがある
* [ ] 品質が重要なタスクにフィードバックループが含まれている

### テスト

* [ ] 少なくとも3つの評価を作成済み
* [ ] Haiku、Sonnet、Opus でテスト済み
* [ ] 実際の使用シナリオでテスト済み
* [ ] チームフィードバックを反映済み（該当する場合）

## 次のステップ

<CardGroup cols={2}>
  <Card title="Agent Skills を始める" icon="rocket" href="/en/docs/agents-and-tools/agent-skills/quickstart">
    最初のスキルを作成する
  </Card>

  <Card title="Claude Code でスキルを使用する" icon="terminal" href="/en/docs/claude-code/skills">
    Claude Code でスキルを作成・管理する
  </Card>

  <Card title="API でスキルを使用する" icon="code" href="/en/api/skills-guide">
    プログラムでスキルをアップロード・使用する
  </Card>
</CardGroup>
