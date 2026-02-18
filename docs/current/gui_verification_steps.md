# GUI確認手順

作成日: 2026-02-18
対象: `trader-main/dashboard`

## 1. 前提

- Python が利用できること
- Google Sheets 連携に必要な `GOOGLE_CREDENTIALS_JSON` が設定済みであること

## 2. ダッシュボード用JSONを生成

```powershell
cd trader-main
python -m src.exporter
Get-ChildItem dashboard/data
```

以下の3ファイルが生成されればOK:

- `dashboard/data/predictions.json`
- `dashboard/data/accuracy.json`
- `dashboard/data/stock_history.json`

## 3. ローカルサーバーで起動

`file://` で直接開かず、HTTPサーバー経由で確認する。

```powershell
cd dashboard
python -m http.server 8000
```

## 4. ブラウザ確認URL

- サマリー: `http://localhost:8000/index.html`
- 的中率: `http://localhost:8000/accuracy.html`
- 銘柄詳細例: `http://localhost:8000/stock.html?ticker=AAPL`

## 5. よくあるエラー

1. 画面に「データを読み込めませんでした」と出る
- `dashboard/data` 配下にJSONがあるか確認
- `python -m src.exporter` の実行ログを確認

2. `src.exporter` 実行時に認証エラー
- `GOOGLE_CREDENTIALS_JSON` の値（パス or JSON文字列）を確認
- 対象スプレッドシートの共有設定を確認

3. チャートが表示されない
- ブラウザの開発者ツール（Console/Network）で `data/*.json` の取得失敗を確認

## 6. 確認チェックリスト

- [ ] `dashboard/data` に3つのJSONが存在する
- [ ] `index.html` で予測カードと累計的中率が表示される
- [ ] `accuracy.html` で週次/累計のチャートが表示される
- [ ] `stock.html?ticker=...` で銘柄別履歴が表示される
