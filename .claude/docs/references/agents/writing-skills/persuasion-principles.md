# スキル設計のための説得原則

## 概要

LLM は人間と同じ説得原則に反応する。この心理学を理解することで、より効果的なスキルを設計できる — 操作するためではなく、プレッシャー下でも重要なプラクティスが確実に守られるようにするために。

**研究の基盤:** Meincke et al. (2025) が 7 つの説得原則を N=28,000 の AI 会話でテスト。説得テクニックによりコンプライアンス率が 2 倍以上に向上（33% → 72%, p < .001）。

## 7 つの原則

### 1. 権威（Authority）
**定義:** 専門知識、資格、公式ソースへの従順。

**スキルでの活用方法:**
- 命令的な言語: "YOU MUST", "Never", "Always"
- 交渉不可のフレーミング: "No exceptions"
- 判断疲れと合理化を排除

**使用タイミング:**
- 規律を強制するスキル（TDD、検証要件）
- 安全性が重要なプラクティス
- 確立されたベストプラクティス

**例:**
```markdown
✅ Write code before test? Delete it. Start over. No exceptions.
❌ Consider writing tests first when feasible.
```

### 2. コミットメント（Commitment）
**定義:** 過去の行動、発言、公的宣言との一貫性。

**スキルでの活用方法:**
- 宣言を要求: "Announce skill usage"
- 明示的な選択を強制: "Choose A, B, or C"
- 追跡を使用: チェックリストに TodoWrite

**使用タイミング:**
- スキルが実際に守られることを確保
- マルチステッププロセス
- 説明責任のメカニズム

**例:**
```markdown
✅ When you find a skill, you MUST announce: "I'm using [Skill Name]"
❌ Consider letting your partner know which skill you're using.
```

### 3. 希少性（Scarcity）
**定義:** 時間制限や限られた利用可能性からの緊急性。

**スキルでの活用方法:**
- 時間制約付き要件: "Before proceeding"
- 順序依存: "Immediately after X"
- 先延ばしを防止

**使用タイミング:**
- 即時の検証要件
- 時間に敏感なワークフロー
- "後でやる" を防ぐ

**例:**
```markdown
✅ After completing a task, IMMEDIATELY request code review before proceeding.
❌ You can review code when convenient.
```

### 4. 社会的証明（Social Proof）
**定義:** 他者の行動や「普通」とされるものへの同調。

**スキルでの活用方法:**
- 普遍的パターン: "Every time", "Always"
- 失敗モード: "X without Y = failure"
- 規範の確立

**使用タイミング:**
- 普遍的プラクティスの文書化
- よくある失敗についての警告
- 基準の強化

**例:**
```markdown
✅ Checklists without TodoWrite tracking = steps get skipped. Every time.
❌ Some people find TodoWrite helpful for checklists.
```

### 5. 一体感（Unity）
**定義:** 共有されたアイデンティティ、「私たち」感覚、内集団への帰属。

**スキルでの活用方法:**
- 協力的な言語: "our codebase", "we're colleagues"
- 共有目標: "we both want quality"

**使用タイミング:**
- 協力的なワークフロー
- チーム文化の確立
- 非階層的なプラクティス

**例:**
```markdown
✅ We're colleagues working together. I need your honest technical judgment.
❌ You should probably tell me if I'm wrong.
```

### 6. 返報性（Reciprocity）
**定義:** 受けた恩恵に対する返済の義務感。

**活用方法:**
- 控えめに使用 — 操作的に感じられる可能性がある
- スキルではほとんど必要ない

**避けるべき場面:**
- ほぼ常に（他の原則の方が効果的）

### 7. 好意（Liking）
**定義:** 好きな相手と協力したいという傾向。

**活用方法:**
- **コンプライアンスには使用しない**
- 正直なフィードバック文化と矛盾する
- おべっか（sycophancy）を生む

**避けるべき場面:**
- 規律の強制では常に避ける

## スキルタイプ別の原則の組み合わせ

| スキルタイプ | 使用する原則 | 避ける原則 |
|------------|-----|-------|
| 規律強制型 | 権威 + コミットメント + 社会的証明 | 好意、返報性 |
| ガイダンス/テクニック型 | 適度な権威 + 一体感 | 強い権威 |
| 協力型 | 一体感 + コミットメント | 権威、好意 |
| リファレンス型 | 明確さのみ | すべての説得手法 |

## なぜ効果があるのか: 心理学的背景

**明確な境界ルールが合理化を減らす:**
- "YOU MUST" が判断疲れを排除
- 絶対的な言語が「これは例外か？」という疑問を排除
- 明示的な反合理化が特定の抜け穴を塞ぐ

**実行意図が自動的な行動を生む:**
- 明確なトリガー + 必須アクション = 自動的な実行
- "When X, do Y" は "generally do Y" より効果的
- コンプライアンスの認知的負荷を軽減

**LLM は準人間的（parahuman）:**
- これらのパターンを含む人間のテキストで訓練されている
- トレーニングデータ内で権威的言語がコンプライアンスに先行
- コミットメントシーケンス（宣言 → 行動）が頻繁にモデル化されている
- 社会的証明パターン（みんなが X をする）が規範を確立

## 倫理的な使用

**正当な使用:**
- 重要なプラクティスの遵守を確保
- 効果的なドキュメントの作成
- 予測可能な失敗の防止

**不正な使用:**
- 個人的利益のための操作
- 偽の緊急性の作成
- 罪悪感に基づくコンプライアンス

**テスト:** ユーザーがこのテクニックを完全に理解した場合、ユーザーの真の利益に資するか？

## 研究引用

**Cialdini, R. B. (2021).** *Influence: The Psychology of Persuasion (New and Expanded).* Harper Business.
- 7 つの説得原則
- 影響力研究の実証的基盤

**Meincke, L., Shapiro, D., Duckworth, A. L., Mollick, E., Mollick, L., & Cialdini, R. (2025).** Call Me A Jerk: Persuading AI to Comply with Objectionable Requests. University of Pennsylvania.
- 7 つの原則を N=28,000 の LLM 会話でテスト
- 説得テクニックによりコンプライアンスが 33% → 72% に向上
- 権威、コミットメント、希少性が最も効果的
- LLM の準人間的行動モデルを検証

## クイックリファレンス

スキルを設計する際に確認すること:

1. **どのタイプか？**（規律型 vs. ガイダンス型 vs. リファレンス型）
2. **どの行動を変えようとしているか？**
3. **どの原則が適用されるか？**（通常、規律型には権威 + コミットメント）
4. **組み合わせすぎていないか？**（7 つ全部は使わない）
5. **倫理的か？**（ユーザーの真の利益に資するか？）
