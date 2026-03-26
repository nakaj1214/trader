# .claude メンテナンスチートシート

`.claude/` をクリーンかつ賢く維持するために覚えておくべきファイル一覧。

---

## 日常メンテナンス（使うたびに .claude が賢くなる）

### スキル

| スキル | コマンド | やること |
|--------|---------|---------|
| `feedback-loop` | （自動トリガー） | 修正指摘を受けたら分類・記録。同カテゴリ3件で自動対策を提案 |
| `handover` | `/handover` | セッション終了時に引き継ぎドキュメントを生成 |
| `design-tracker` | （自動トリガー） | 設計決定を DESIGN.md に自動記録 |

### コマンド

| コマンド | やること |
|---------|---------|
| `/learn-edits` | 編集ログを分析してパターン抽出 → hook/skill 候補を提案 |
| `/materialize` | 提案された候補を `staging/` にドラフト生成 |
| `/review-staged` | ドラフトを確認・承認 → 本番配置 |
| `/revise-claude-md` | セッション中の学びを CLAUDE.md に反映 |

### フック

| フック | トリガー | やること |
|--------|---------|---------|
| `pre-compact-handover.py` | コンパクション直前 | HANDOVER + SKILL-SUGGESTIONS + EDIT-PATTERNS を自動生成 |
| `edit-tracker.py` | Edit/Write 後 | 編集ログを蓄積（`/learn-edits` の分析元） |
| `fix-escalation-detector.py` | ユーザーメッセージ | 失敗パターンを検知して fix-escalation を促す |

> **自己改善サイクル**: `edit-tracker` → `/learn-edits` → `/materialize` → `/review-staged`
> このサイクルを回すと、繰り返しの手作業が自動的に skill/hook に昇格する。

---

## 定期メンテナンス（月1回）

### メタスクリプト

| スクリプト | コマンド | やること |
|-----------|---------|---------|
| `meta/generate-registry.py` | `python .claude/meta/generate-registry.py` | 全スキルの SKILL.md を読んで `registry/skills.yaml` を再生成 |
| `meta/health-check.py` | `python .claude/meta/health-check.py` | evals.json 欠損・SKILL.md 肥大化・未登録・重複を検出 |

### スキル

| スキル | コマンド | やること |
|--------|---------|---------|
| `claude-md-management` | 「CLAUDE.md を監査して」 | 全 CLAUDE.md を品質ルーブリックで評価・改善 |
| `claude-template-sync` | 「テンプレート同期して」 | `.claude_remote/` の変更を安全に取り込む |

### 月次チェックリスト（CLAUDE.md に記載）

```
- [ ] 矛盾するルールがないか
- [ ] 重複するスキル/ルールがないか
- [ ] 使われていないスキル/エージェントがないか
- [ ] 常時ロードのルール行数が 1,000行以内か
- [ ] paths: 指定で条件付きロードにできるルールがないか
```

---

## 新プロジェクト・大きな変更時

### スキル

| スキル | コマンド | やること |
|--------|---------|---------|
| `init` | `/init` | プロジェクト分析 → CLAUDE.md 初期設定 + ローカル CLAUDE.md 配置提案 |
| `analyze-project` | 「プロジェクト分析して」 | コーディング規約・パターンを抽出 → rules/ と skills/ を自動生成 |
| `claude-code-setup` | 「Claude Code 最適化して」 | フック・スキル・MCP の推奨を出す |
| `skill-creator` | `/skill-creator` | 新スキルの作成・テスト・description 最適化 |
| `hookify` | `/hookify` | 対話的にフック設定を自動生成 |

---

## ルール管理の原則

### 知っておくべきルールファイル

| ファイル | 役割 | なぜ重要か |
|---------|------|-----------|
| `rules/skill-execution.md` | スキル実行時のルール | スキルの指示を勝手に変更しない・無効フックをスキップする |
| `rules/work-modes.md` | 開発/調査/レビューモード | ユーザーの意図に合った動作モードを自動選択 |
| `rules/neutral-analysis.md` | 迎合防止・三者構造分析 | 結論を誘導しない中立的な分析を保証 |

### コンテキスト節約のコツ

| テクニック | 方法 | 効果 |
|-----------|------|------|
| **paths: フロントマター** | ルールファイル冒頭に `paths:` を追加 | 対象ファイル操作時のみロード（常時ロード行数を削減） |
| **二段階ロード** | SKILL.md（概要）と INSTRUCTIONS.md（詳細）を分離 | description だけがシステムプロンプトに入り、詳細はトリガー時のみ |
| **ローカル CLAUDE.md** | リスクの高いディレクトリに小さな CLAUDE.md を配置 | そのディレクトリの操作時だけ注意事項がロードされる |
| **memory/ のクリーンアップ** | 古い HANDOVER-*.md を定期削除 | メモリディレクトリの肥大化を防ぐ |

---

## クイックリファレンス

```
# 日常（セッション終了時）
/handover

# 自己改善（編集パターンが溜まったら）
/learn-edits → /materialize → /review-staged

# 月次メンテナンス
python .claude/meta/health-check.py
python .claude/meta/generate-registry.py
「CLAUDE.md を監査して」

# 新プロジェクト
/init

# スキル追加後は必ず
python .claude/meta/generate-registry.py
```
