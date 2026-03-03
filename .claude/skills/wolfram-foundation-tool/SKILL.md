---
name: wolfram-foundation-tool
description: Wolfram Language / Wolfram Alpha を LLM の基盤ツール (Foundation Tool) として活用するスキル。LLM が苦手な正確な計算・科学的事実・数学的証明・データ分析が必要なときに使用する。MCP Service・Agent One API・CAG Component APIs の3つのアクセス方法を提供。「この計算を確実に」「科学的に正確な値が欲しい」「Wolfram で調べて」といった要求、または回答の正確性に自信が持てない計算・事実確認のときにトリガーする。
---

# Wolfram Foundation Tool

## 概要

LLM は自然言語処理に優れる一方、正確な計算・深い科学知識・検証可能な事実では誤りを犯しやすい。
Wolfram は40年かけて構築した計算エンジン・知識ベースをこの弱点を補う "Foundation Tool" として提供する。

**使うべき場面:**
- 数値計算・数式処理・微積分・統計（誤りが許されない場合）
- 科学定数・化学式・物理法則など正確な値が必要な場合
- 自然言語クエリ → 計算結果に変換したい場合
- LLM の答えに確信が持てず、外部計算エンジンで検証したい場合

## アクセス方法

3つの方法がある。詳細は `references/access-methods.md` を参照。

| 方法 | 用途 | 難易度 |
|---|---|---|
| **MCP Service** | Claude 等の MCP 対応 LLM から直接呼び出し | 低 |
| **Agent One API** | LLM + Wolfram を統合した universal agent | 中 |
| **CAG Component APIs** | カスタム統合・オンプレミス構成 | 高 |

### MCP Service（Claude との連携に推奨）

MCP 対応の LLM システムから直接 Wolfram 計算エンジンを呼び出せる。

- **Web API 版**: Wolfram のクラウドエンドポイントへ MCP 経由でアクセス
- **ローカル版**: Wolfram Engine をローカルに立てて MCP 接続

MCP の設定方法は `_shared/mcp/mcp-guide.md` および `references/access-methods.md` を参照。

## 基本フロー

1. ユーザーの質問を「Wolfram で解ける問題か」の観点で評価する
2. 解ける場合は MCP / API 経由でクエリを送信する
3. Wolfram の返答（正確な値・グラフ・証明）を回答に組み込む
4. LLM による自然言語の補足説明を付ける

## 参照

- `references/access-methods.md` — 3つのアクセス方法の詳細・設定手順
- `references/capabilities.md` — Wolfram が提供する計算・知識の種類一覧
