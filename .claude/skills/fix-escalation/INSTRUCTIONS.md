# 修正エスカレーション — 詳細手順

同じバグに2回失敗したら方針転換を強制する。
試行履歴を `tasks/fix-attempts.md` に自動記録し、堂々巡りを防止する。

---

## トリガー条件

以下のいずれかでこのスキルが起動する:

- ユーザーが「改善されていない」「N回目」「また同じ」「直っていない」「まだ動かない」と報告
- `verify-before-fix` の停止条件（2回修正失敗）が発動
- `fix-escalation-detector.py` フックがコンテキストに警告を注入

---

## Step 1: 履歴確認と試行回数の判定

`tasks/fix-attempts.md` を読む。ファイルが存在しなければ新規作成する
（テンプレート: [references/attempt-template.md](references/attempt-template.md)）。

### 処理

1. ユーザーの報告内容から、該当する Issue セクション（`## Issue:`）を探す
2. キーワードマッチで該当 Issue を特定する（候補が複数あればユーザーに確認）
3. 該当 Issue の `### Attempt N` セクション数をカウントする

### 分岐

| 試行回数 | 次のステップ |
|---------|------------|
| 0（新規）| Step 2（通常デバッグ記録） |
| 1（1回失敗）| Step 2（通常デバッグ記録） |
| 2以上 | **Step 3（エスカレーション調査を強制）** |

---

## Step 2: 通常デバッグ記録（0-1回失敗時）

初回または2回目未満の試行。証拠を集めて仮説を立て、試行を記録する。

### 処理

1. `tasks/fix-attempts.md` に新しい `### Attempt N` セクションを追記
2. **証拠収集**: `verify-before-fix` の Phase 1-3 の手順で実施
   - フロントエンド: スクリーンショット・DOM・コンソールログ
   - バックエンド: ログ確認・クエリ確認
   - Python: テスト実行
3. **仮説生成**: `systematic-debugging` の Stage 1-2 の手順で実施
   - 症状を観測として記録（推測と混ぜない）
   - 最低3つの仮説を立てる（可能性と検証方法を併記）
4. 最も可能性の高い仮説に基づいて修正方針を記録

### fix-attempts.md への記録フォーマット

```markdown
### Attempt N
<!-- date: YYYY-MM-DD -->
<!-- result: PENDING -->

#### Hypothesis
[仮説の内容]

#### Evidence Collected
- [検証手段]: [結果]

#### Fix Applied
- File: [変更したファイル]
- Change: [何をどう変えたか]

#### Result
- **Outcome**: PENDING
```

→ Step 5 へ進む

---

## Step 3: エスカレーション調査（2回以上失敗時 — 強制）

**過去と同じアプローチでの修正は禁止する。**
方針転換なしの3回目修正を試みてはならない。

### 処理

#### 3-1. 過去の全試行を要約

fix-attempts.md から該当 Issue の全 Attempt を読み、以下を整理する:

```
## エスカレーション分析

### 過去の試行まとめ
| # | 仮説 | 修正内容 | 結果 | 学び |
|---|------|---------|------|------|
| 1 | ... | ... | FAILED | ... |
| 2 | ... | ... | FAILED | ... |

### パターン分析
- 同じカテゴリの修正を繰り返していないか？（例: CSS微調整、timeout変更）
- 同じファイルばかり変更していないか？
- 仮説の前提自体が間違っていないか？
```

#### 3-2. 三者構造サブエージェント分析

`neutral-analysis` ルールの三者構造パターンを適用する。

**列挙役（Explore サブエージェント）**:
- 過去の仮説と**異なる**原因候補を最低5つ列挙する
- 過去に試した仮説は除外する
- 「コードを読んだだけで断定」は禁止。実行パスを追って根拠を示す
- 以下の観点を必ず含める:
  - 別のファイルが原因ではないか？
  - CSS/JS の優先度（specificity, !important, 読み込み順）の問題ではないか？
  - キャッシュ・ビルド・デプロイの問題ではないか？
  - タイミング・非同期処理の問題ではないか？
  - 環境固有の問題ではないか？

**反証役（別の Explore サブエージェント）**:
- 列挙された候補を1つずつ検証・反論する
- 根拠のない候補を棄却する
- 残った候補に対して具体的な検証方法を提案する

**審判役（メインスレッド）**:
- 両方の結果を見て新仮説を **2つ以内** に絞る
- 過去の仮説と重複していないことを確認する

#### 3-3. 禁止事項の確認

以下に該当する場合は **修正に進まない**:

- 新仮説が過去の仮説と同じカテゴリ（例: 前回も CSS 修正 → 今回も CSS 修正）
- 修正対象ファイルが過去と全く同じ
- 「前回の修正をもう少し調整する」系の微修正

該当する場合、ユーザーに状況を報告し、追加調査か別の手法（手動テスト、ペアデバッグ等）を提案する。

→ Step 4 へ進む

---

## Step 4: 方針転換の明示的宣言（エスカレーション時のみ）

### 処理

1. `tasks/fix-attempts.md` に `### Escalation Triggered` セクションを追記:

```markdown
### Escalation Triggered (Attempt N failed)
<!-- date: YYYY-MM-DD -->

#### Past Hypotheses (all rejected)
1. [仮説1] — rejected because [理由]
2. [仮説2] — rejected because [理由]

#### Pivot Declaration
- **Old approach**: [これまでの方向性]
- **New approach**: [新しい方向性]
- **Why pivot**: [方針転換の根拠]

#### New Hypotheses (from escalation analysis)
1. [新仮説1] — verification: [検証方法]
2. [新仮説2] — verification: [検証方法]
```

2. ユーザーに方針転換の内容を報告し、確認を得る:

```
## エスカレーション: 方針転換

過去 N 回の修正が失敗したため、アプローチを変更します。

### 棄却した仮説
- [仮説1]: [棄却理由]
- [仮説2]: [棄却理由]

### 新しいアプローチ
[方針転換の内容と根拠]

### 次の検証計画
[具体的な検証手順]

この方向で進めてよいですか？
```

→ ユーザー承認後、Step 5 へ進む

---

## Step 5: 修正実施 + 結果記録

### 処理

1. 確定した方針に基づいて修正を実施する
2. `tasks/fix-attempts.md` の当該 Attempt に修正内容を記録する:
   - `#### Fix Applied` に変更ファイルと内容を記載
3. 修正後、`verify-before-fix` の Phase 5（修正後再検証）に相当する検証を実施する

→ Step 6 へ進む

---

## Step 6: 検証と記録

### 成功の場合

1. `tasks/fix-attempts.md` に結果を記録:

```markdown
#### Result
- **Outcome**: SUCCESS
- **Root cause**: [最終的に判明した根本原因]
- **Why previous attempts failed**: [過去の試行がなぜ的外れだったか]
```

2. `### Resolution Summary` セクションを追記:

```markdown
### Resolution Summary
- **Total attempts**: N
- **Root cause**: [根本原因]
- **Key learning**: [最も重要な学び]
- **Playbook candidate**: Yes/No
```

3. `feedback-loop` スキルの手順に従い学習を記録する:
   - `.claude/docs/lessons.md` に追記
   - `.claude/docs/feedback-log.md` に追記
   - `.claude/docs/improvement-tracker.md` を更新

4. 試行回数が3回以上だった場合、`.claude/docs/playbooks.md` への追記を提案する

5. 完了報告:

```
## バグ修正完了

- **根本原因**: [根本原因]
- **試行回数**: N回
- **学び**: [最も重要な学び]
- **lessons.md**: 更新済み
```

### 失敗の場合

1. `tasks/fix-attempts.md` に失敗を記録:

```markdown
#### Result
- **Outcome**: FAILED
- **Why it failed**: [なぜ効かなかったか]
- **What was learned**: [この試行から分かったこと]
```

2. **Step 1 に戻る**（次の試行で自動的に試行回数がインクリメントされ、エスカレーションが発動する）

---

## 判定の柔軟性

- ユーザーが「エスカレーション不要、そのまま修正して」と言った場合はスキップ可能
- ただし「方針転換なしの同じ修正」は引き続き警告する
- 試行回数が5回を超えた場合、ユーザーに「手動での確認」または「別の人に相談」を強く推奨する
