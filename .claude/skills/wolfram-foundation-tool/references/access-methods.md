# Wolfram Foundation Tool — アクセス方法詳細

出典: https://writings.stephenwolfram.com/2026/02/making-wolfram-tech-available-as-a-foundation-tool-for-llm-systems/

---

## 背景・なぜ Wolfram が必要か

LLM は「確率的なテキスト生成」であり、深い計算や正確な事実確認には本質的な限界がある。
Wolfram Language は40年かけて構築された「正確な計算と知識のエンジン」であり、両者を組み合わせることで互いの弱点を補完できる。

Wolfram のアプローチ: **CAG（Computation-Augmented Generation）**
- LLM の生成ストリームにリアルタイムで Wolfram の計算結果を注入する
- 必要なコンテンツをその場で無限に生成・供給できる

---

## 1. MCP Service

### 概要

MCP（Model Context Protocol）対応の LLM システムから直接 Wolfram を呼び出せるサービス。
Claude Code はネイティブで MCP をサポートするため、最も手軽な統合方法。

### 提供形態

| 形態 | 説明 |
|---|---|
| Web API 版 | Wolfram のクラウドエンドポイントに MCP 経由でアクセス |
| ローカル版 | Wolfram Engine をローカルに立てて MCP 接続 |

### 設定手順

1. Wolfram MCP サーバーのエンドポイント URL を取得（partner-program@wolfram.com へ問い合わせ）
2. `_shared/mcp/mcp-guide.md` の手順に従い MCP サーバーを settings.json に追加
3. Claude Code を再起動して接続確認

---

## 2. Agent One API

### 概要

Wolfram Foundation Tool と LLM foundation model を統合した "universal agent"。
既存の LLM API のドロップイン置き換えとして機能する。

### 特徴

- 単一エンドポイントで「LLM の言語能力 + Wolfram の計算精度」を提供
- アプリ側のコードを大きく変えずに導入できる
- 従来の LLM API フォーマットの代替として利用可能

### 適している場面

- 既存の LLM API アプリに Wolfram の精度を後付けしたい場合
- 計算・知識・言語生成を一体で処理したい場合

---

## 3. CAG Component APIs

### 概要

CAG（Computation-Augmented Generation）の細粒度アクセス方法。
カスタム統合・オンプレミス構成など高い柔軟性が必要な場合に使用する。

### 特徴

- ホスト型とオンプレミスの両方に対応
- 任意の規模の LLM システムへのカスタム統合が可能
- 最も詳細な制御ができるが、実装コストも最も高い

### 適している場面

- プライベートクラウド・オンプレミス環境で Wolfram を使いたい場合
- 独自の LLM パイプラインに Wolfram を組み込む場合

---

## 問い合わせ・詳細情報

- パートナープログラム: partner-program@wolfram.com
- 能力一覧 PDF: "Wolfram Foundation Tool Capabilities Listing"（公式サイトから入手）
