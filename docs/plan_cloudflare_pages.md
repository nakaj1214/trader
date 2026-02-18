# Cloudflare Pages GUI 計画書

> 最終更新: 2026-02-18

## 背景・目的

現在の分析結果の確認方法は以下に限られている:

- Slack 通知（テキスト形式のみ）
- Google スプレッドシート（表形式のみ）

**Cloudflare Pages を使って Web ベースの GUI を構築し、株価の推移や予測結果をグラフで視覚的に確認できるようにする。**

---

## 機能概要

### ページ構成

```
トップページ (/)
├── 今週の予測サマリー
├── 的中率の推移グラフ
└── 予測銘柄一覧 (カード形式)

銘柄詳細ページ (/stock/:ticker)
├── 株価チャート (過去90日 + 予測)
├── テクニカル指標 (RSI, MACD)
└── 予測履歴テーブル

的中率ダッシュボード (/accuracy)
├── 週別的中率の推移グラフ
├── 累計的中率
└── 銘柄別的中率ランキング
```

### 画面イメージ

```
┌──────────────────────────────────────────────┐
│  📊 AI Stock Predictor Dashboard             │
├──────────────────────────────────────────────┤
│                                              │
│  今週の予測 (2026-02-22)     的中率: 75.0%   │
│                                              │
│  ┌────────┐ ┌────────┐ ┌────────┐           │
│  │ AAPL   │ │ MSFT   │ │ GOOGL  │  ...      │
│  │ +6.0%  │ │ +4.3%  │ │ +3.8%  │           │
│  │ $265   │ │ $438   │ │ $185   │           │
│  └────────┘ └────────┘ └────────┘           │
│                                              │
│  的中率推移                                    │
│  80% ┤      ╭─╮                              │
│  70% ┤  ╭─╮ │ │ ╭─╮                          │
│  60% ┤──╯ ╰─╯ ╰─╯ ╰──                       │
│  50% ┤                                       │
│      └──────────────────→ 週                  │
│                                              │
└──────────────────────────────────────────────┘
```

---

## 技術設計

### 技術スタック

| カテゴリ | 技術 | 理由 |
|---------|------|------|
| ホスティング | Cloudflare Pages | 無料枠が豊富、CDN 配信で高速、GitHub 連携でデプロイ自動化 |
| フレームワーク | 静的サイト (HTML/CSS/JS) | シンプルで軽量、ビルド不要で管理が容易 |
| グラフ描画 | Chart.js | 軽量、簡単に美しいグラフを生成、CDN から読み込み可能 |
| データ形式 | JSON (CSV から変換) | JavaScript で直接読み込み可能 |
| スタイリング | Tailwind CSS (CDN) | ユーティリティファースト、デザイン統一が容易 |

### アーキテクチャ

```
Google スプレッドシート
  ↓ (GitHub Actions で週次エクスポート)
CSV / JSON ファイル
  ↓ (git push で自動デプロイ)
Cloudflare Pages (静的サイト)
  ↓
ユーザのブラウザ (Chart.js でグラフ描画)
```

### データフロー

```
毎週日曜 (GitHub Actions)
  ↓
① 既存ワークフロー実行 (予測・記録・通知)
  ↓
② Google Sheets → CSV エクスポート (新規ステップ)
  ↓
③ CSV → JSON 変換
  ↓
④ dashboard/ ディレクトリにデータファイルをコミット
  ↓
⑤ Cloudflare Pages が自動デプロイ
```

### ディレクトリ構成

```
trader/
├── dashboard/                    # Cloudflare Pages デプロイ対象
│   ├── index.html               # トップページ
│   ├── stock.html               # 銘柄詳細ページ
│   ├── accuracy.html            # 的中率ダッシュボード
│   ├── css/
│   │   └── style.css            # カスタムスタイル
│   ├── js/
│   │   ├── app.js               # メインロジック
│   │   ├── charts.js            # Chart.js グラフ描画
│   │   └── data-loader.js       # データ読み込み
│   └── data/
│       ├── predictions.json     # 予測データ (週次更新)
│       ├── accuracy.json        # 的中率データ (週次更新)
│       └── stock_history.json   # 株価履歴データ
├── src/
│   ├── ... (既存)
│   └── exporter.py              # 新規: Sheets → JSON エクスポート
└── ...
```

---

## 新規コンポーネント

### 1. データエクスポーター (`src/exporter.py`)

Google スプレッドシートから予測データを JSON 形式でエクスポートする。

```python
"""Google Sheets のデータを dashboard 用 JSON にエクスポートする"""

import json
from pathlib import Path
from src.sheets import get_worksheet


def export_predictions_json(config: dict) -> None:
    """予測データをJSONファイルにエクスポートする。"""
    ws = get_worksheet(config)
    records = ws.get_all_records()

    output_path = Path("dashboard/data/predictions.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
```

### 2. ダッシュボード HTML (`dashboard/index.html`)

Chart.js と JSON データを組み合わせた静的ページ。

```html
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Stock Predictor Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 min-h-screen">
    <header class="bg-blue-600 text-white p-4">
        <h1 class="text-2xl font-bold">📊 AI Stock Predictor</h1>
    </header>
    <main class="container mx-auto p-4">
        <div id="summary-cards" class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <!-- 予測銘柄カード (JavaScript で動的生成) -->
        </div>
        <div class="bg-white rounded-lg shadow p-6">
            <h2 class="text-xl font-bold mb-4">的中率推移</h2>
            <canvas id="accuracy-chart"></canvas>
        </div>
    </main>
    <script src="js/data-loader.js"></script>
    <script src="js/charts.js"></script>
    <script src="js/app.js"></script>
</body>
</html>
```

### 3. GitHub Actions ワークフローへの追加

```yaml
# .github/workflows/weekly_run.yml に追加
- name: Export dashboard data
  run: python -m src.exporter

- name: Commit dashboard data
  run: |
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git add dashboard/data/
    git diff --staged --quiet || git commit -m "Update dashboard data [skip ci]"
    git push
```

---

## Cloudflare Pages セットアップ手順

### 1. Cloudflare アカウント作成

1. [Cloudflare](https://dash.cloudflare.com/sign-up) でアカウントを作成（無料）

### 2. Pages プロジェクト作成

1. Cloudflare ダッシュボード → 「Workers & Pages」→「Create」
2. 「Pages」タブ →「Connect to Git」
3. GitHub リポジトリ `trader` を選択
4. ビルド設定:
   - **ビルドコマンド**: (空欄 — ビルド不要)
   - **ビルド出力ディレクトリ**: `dashboard`
5. 「Save and Deploy」をクリック

### 3. 自動デプロイ

- `main` ブランチに push されるたびに Cloudflare Pages が自動デプロイ
- GitHub Actions でデータ更新 → push → 自動反映

---

## コスト見積もり

| 項目 | 費用 | 備考 |
|------|------|------|
| Cloudflare Pages (Free プラン) | $0 | 月500ビルド、無制限帯域 |
| Chart.js | $0 | OSS (MIT ライセンス) |
| Tailwind CSS CDN | $0 | 無料 |
| **合計** | **$0/月** | |

---

## 実装スケジュール

| フェーズ | 作業内容 | 所要時間 |
|---------|---------|---------|
| 1 | `src/exporter.py` 作成 (Sheets → JSON) | 1日 |
| 2 | `dashboard/index.html` 基本レイアウト | 1日 |
| 3 | Chart.js グラフ実装 (的中率推移・株価チャート) | 1.5日 |
| 4 | 銘柄詳細ページ作成 | 1日 |
| 5 | Cloudflare Pages デプロイ設定 | 0.5日 |
| 6 | GitHub Actions ワークフロー更新 | 0.5日 |
| 7 | レスポンシブ対応・デザイン調整 | 1日 |
| 8 | テスト・ドキュメント | 0.5日 |

**合計: 約7日**

---

## リスクと対策

| リスク | 対策 |
|-------|------|
| データ量増加による JSON ファイル肥大化 | 直近12週分のみ保持、古いデータはアーカイブ |
| Cloudflare Pages の無料枠超過 | 月500ビルドは週1更新では十分 |
| スプレッドシートのエクスポート失敗 | エラーハンドリング、前回データをフォールバック表示 |
| ブラウザ互換性 | Chart.js が主要ブラウザ対応済み |

---

## 将来の拡張

- **リアルタイムデータ**: Cloudflare Workers で yfinance API をプロキシし、リアルタイム株価を表示
- **カスタムドメイン**: 独自ドメインの設定（Cloudflare で無料 SSL）
- **PWA 対応**: スマホのホーム画面に追加してアプリのように使える
- **銘柄比較機能**: 複数銘柄の株価チャートを重ねて表示
- **フィルタ・検索**: 業種別・指標別の絞り込み機能
