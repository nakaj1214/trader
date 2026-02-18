# CSV / スプレッドシート取り込み＆グラフ可視化 計画書

> 最終更新: 2026-02-18

## 背景・目的

現在の予測結果は Google スプレッドシートに記録されているが、以下の課題がある:

- スプレッドシートの表形式では株価の推移や傾向が直感的にわからない
- 過去の予測と実績の比較がしづらい
- グラフでの可視化が手動でしかできない

**CSV またはスプレッドシートのデータを取り込み、Chart.js でグラフ表示することで、予測結果と株価推移を視覚的に確認できるようにする。**

---

## 機能概要

### 可視化するグラフ一覧

| グラフ | 種類 | 説明 |
|-------|------|------|
| 株価推移チャート | 折れ線グラフ | 過去90日の実際の株価 + AI予測値をオーバーレイ |
| 的中率推移 | 棒グラフ + 折れ線 | 週別的中率（棒）と累計的中率（線） |
| 銘柄別パフォーマンス | 横棒グラフ | 予測上昇率 vs 実際の上昇率を並べて比較 |
| テクニカル指標 | 折れ線グラフ | RSI・MACD の推移（株価チャートと連動） |
| 予測精度分布 | 散布図 | 予測値 vs 実績値のプロット（理想は45度線上） |

### 画面イメージ

```
┌──────────────────────────────────────────────────┐
│  AAPL (Apple Inc.) 株価チャート                      │
│                                                    │
│  $270 ┤                              ╭── 予測     │
│  $260 ┤                         ╭──╮╯   (破線)    │
│  $250 ┤                   ╭─────╯  │              │
│  $240 ┤              ╭────╯                       │
│  $230 ┤         ╭────╯                            │
│  $220 ┤    ╭────╯          ← 実際の株価 (実線)     │
│  $210 ┤────╯                                      │
│       └────────────────────────────→ 日付          │
│        1月    2月                  来週             │
│                                                    │
│  ── 実績株価   ‐‐ AI予測   ░ 信頼区間               │
└──────────────────────────────────────────────────┘
```

---

## 技術設計

### データの流れ

```
データソース (2パターン)
  │
  ├─ パターンA: Google スプレッドシート → gspread で取得 → JSON変換
  │
  └─ パターンB: CSVファイル手動アップロード → JavaScript で直接読み込み
  │
  ↓
dashboard/data/ にJSON形式で保存
  ↓
Chart.js でブラウザ上にグラフ描画
```

### パターンA: スプレッドシートからの自動取り込み

GitHub Actions で毎週自動エクスポートする（Cloudflare Pages 計画書と連携）。

```python
# src/exporter.py
def export_stock_history(config: dict, tickers: list[str]) -> None:
    """予測対象銘柄の過去90日の株価データをJSONにエクスポートする。"""
    import yfinance as yf
    import json
    from pathlib import Path
    from datetime import datetime, timedelta

    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)

    all_data = {}
    for ticker in tickers:
        df = yf.download(ticker, start=start_date, end=end_date)
        all_data[ticker] = [
            {"date": idx.strftime("%Y-%m-%d"), "close": round(row["Close"], 2)}
            for idx, row in df.iterrows()
        ]

    output_path = Path("dashboard/data/stock_history.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
```

### パターンB: CSV 手動アップロード

ブラウザ上で CSV ファイルをドラッグ＆ドロップして即座にグラフ化する。

```javascript
// dashboard/js/csv-loader.js

/**
 * CSVファイルを読み込んでJSONに変換する
 */
function parseCSV(csvText) {
    const lines = csvText.trim().split('\n');
    const headers = lines[0].split(',').map(h => h.trim());
    return lines.slice(1).map(line => {
        const values = line.split(',');
        const obj = {};
        headers.forEach((header, i) => {
            obj[header] = values[i]?.trim();
        });
        return obj;
    });
}

/**
 * ファイル入力からCSVを読み込んでグラフを生成する
 */
function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(e) {
        const data = parseCSV(e.target.result);
        renderChart(data);
    };
    reader.readAsText(file);
}
```

### CSV フォーマット

ユーザが手動で CSV をアップロードする場合の想定フォーマット:

```csv
date,ticker,current_price,predicted_price,predicted_change_pct,actual_price,hit
2026-02-16,AAPL,250.00,265.00,6.0,263.50,true
2026-02-16,MSFT,420.00,438.00,4.3,435.20,true
2026-02-16,GOOGL,175.00,182.00,4.0,171.30,false
```

Google スプレッドシートからエクスポートした CSV もこの形式に準拠する。

---

## Chart.js グラフ実装

### 1. 株価推移 + AI 予測チャート

```javascript
// dashboard/js/charts.js

function renderStockChart(canvasId, stockData, predictions) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: stockData.map(d => d.date),
            datasets: [
                {
                    label: '実績株価',
                    data: stockData.map(d => d.close),
                    borderColor: 'rgb(59, 130, 246)',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    fill: true,
                    tension: 0.1,
                },
                {
                    label: 'AI予測',
                    data: predictions.map(d => d.predicted_price),
                    borderColor: 'rgb(249, 115, 22)',
                    borderDash: [5, 5],
                    pointStyle: 'triangle',
                },
            ],
        },
        options: {
            responsive: true,
            plugins: {
                title: { display: true, text: '株価推移 & AI予測' },
            },
            scales: {
                y: {
                    title: { display: true, text: '株価 (USD)' },
                },
            },
        },
    });
}
```

### 2. 的中率推移チャート

```javascript
function renderAccuracyChart(canvasId, accuracyData) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: accuracyData.map(d => d.week),
            datasets: [
                {
                    label: '週別的中率 (%)',
                    data: accuracyData.map(d => d.hit_rate),
                    backgroundColor: 'rgba(34, 197, 94, 0.6)',
                    borderColor: 'rgb(34, 197, 94)',
                    borderWidth: 1,
                },
                {
                    label: '累計的中率 (%)',
                    data: accuracyData.map(d => d.cumulative_rate),
                    type: 'line',
                    borderColor: 'rgb(239, 68, 68)',
                    pointBackgroundColor: 'rgb(239, 68, 68)',
                    fill: false,
                },
            ],
        },
        options: {
            responsive: true,
            plugins: {
                title: { display: true, text: '的中率推移' },
            },
            scales: {
                y: {
                    min: 0,
                    max: 100,
                    title: { display: true, text: '的中率 (%)' },
                },
            },
        },
    });
}
```

### 3. 予測 vs 実績 比較チャート

```javascript
function renderComparisonChart(canvasId, comparisonData) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: comparisonData.map(d => d.ticker),
            datasets: [
                {
                    label: '予測上昇率 (%)',
                    data: comparisonData.map(d => d.predicted_change),
                    backgroundColor: 'rgba(59, 130, 246, 0.6)',
                },
                {
                    label: '実際の変動率 (%)',
                    data: comparisonData.map(d => d.actual_change),
                    backgroundColor: 'rgba(34, 197, 94, 0.6)',
                },
            ],
        },
        options: {
            responsive: true,
            plugins: {
                title: { display: true, text: '予測 vs 実績 比較' },
            },
            indexAxis: 'y',
        },
    });
}
```

---

## ディレクトリ構成

```
dashboard/
├── index.html                # トップページ (サマリー + 的中率推移)
├── stock.html                # 銘柄別株価チャート
├── upload.html               # CSV アップロード & 即時グラフ化
├── css/
│   └── style.css             # カスタムスタイル
├── js/
│   ├── app.js                # メインロジック・ページ初期化
│   ├── charts.js             # Chart.js グラフ描画関数群
│   ├── csv-loader.js         # CSV パース・アップロード処理
│   └── data-loader.js        # JSON データ読み込み
└── data/
    ├── predictions.json      # 予測データ (週次自動更新)
    ├── accuracy.json         # 的中率データ (週次自動更新)
    └── stock_history.json    # 株価履歴 (週次自動更新)
```

---

## 実装スケジュール

| フェーズ | 作業内容 | 所要時間 |
|---------|---------|---------|
| 1 | `src/exporter.py` 実装 (Sheets → JSON / 株価データ取得) | 1日 |
| 2 | `dashboard/js/charts.js` 実装 (Chart.js グラフ3種) | 1.5日 |
| 3 | `dashboard/js/csv-loader.js` 実装 (CSV取り込み) | 0.5日 |
| 4 | `dashboard/index.html` トップページ | 1日 |
| 5 | `dashboard/stock.html` 銘柄詳細ページ | 1日 |
| 6 | `dashboard/upload.html` CSVアップロードページ | 0.5日 |
| 7 | レスポンシブ対応・デザイン調整 | 1日 |
| 8 | GitHub Actions ワークフロー更新 | 0.5日 |
| 9 | テスト・ドキュメント | 0.5日 |

**合計: 約7.5日**

※ Cloudflare Pages 計画書 (`plan_cloudflare_pages.md`) と密接に関連。共通部分は並行して実装可能。

---

## コスト見積もり

| 項目 | 費用 | 備考 |
|------|------|------|
| Chart.js | $0 | OSS (MIT ライセンス) |
| Tailwind CSS CDN | $0 | 無料 |
| yfinance | $0 | 無料 |
| Cloudflare Pages | $0 | 無料枠内 |
| **合計** | **$0/月** | |

---

## リスクと対策

| リスク | 対策 |
|-------|------|
| CSV フォーマットの不一致 | バリデーション処理を実装し、エラーメッセージを表示 |
| 大量データでブラウザが重くなる | 直近12週分に制限、ページネーション実装 |
| yfinance の API 制限 | キャッシュ活用、エクスポート頻度を週1回に限定 |
| スプレッドシートとの整合性 | エクスポート時にデータ検証、不整合があればログ出力 |

---

## 将来の拡張

- **リアルタイム更新**: Cloudflare Workers で定期的にデータを更新
- **カスタムグラフ**: ユーザが表示する指標・期間を自由にカスタマイズ
- **エクスポート機能**: グラフを PNG / PDF でダウンロード
- **アラート設定**: 特定の条件（的中率低下など）でブラウザ通知
- **複数データソース対応**: Yahoo Finance CSV、楽天証券 CSV などの取り込み
