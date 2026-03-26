# Docker 開発ワークフロー — 詳細手順

Docker Compose で動作する Laravel / Python プロジェクトの開発フロー。

---

## 基本原則

- **すべてのコマンドはコンテナ内で実行する**（ホスト側の PHP / Python を使わない）
- サービス名は `docker compose ps` で確認してから使う
- コンテナが落ちている場合は先に `docker compose up -d` で起動する

---

## よく使うコマンド一覧

### コンテナ管理

```bash
# 起動（バックグラウンド）
docker compose up -d

# 停止
docker compose down

# 再ビルド（Dockerfile や依存関係が変わったとき）
docker compose build --no-cache
docker compose up -d --build

# 状態確認
docker compose ps

# ログ確認（全サービス）
docker compose logs -f

# 特定サービスのログ
docker compose logs -f app
docker compose logs -f python
```

### コンテナ内でのコマンド実行

```bash
# シェルに入る
docker compose exec app bash
docker compose exec python bash

# 1回だけ実行（シェルに入らない）
docker compose exec app php artisan migrate
docker compose exec python python manage.py migrate
```

---

## Laravel 操作（Docker 内）

### Artisan コマンド

```bash
# マイグレーション
docker compose exec app php artisan migrate
docker compose exec app php artisan migrate:fresh --seed

# モデル・コントローラー生成
docker compose exec app php artisan make:model Post -mfcrs
docker compose exec app php artisan make:controller PostsController --resource

# キャッシュクリア
docker compose exec app php artisan config:clear
docker compose exec app php artisan cache:clear
docker compose exec app php artisan route:clear

# テスト実行
docker compose exec app php artisan test
docker compose exec app ./vendor/bin/pest

# キューワーカー（フォアグラウンド）
docker compose exec app php artisan queue:work
```

### Composer

```bash
docker compose exec app composer install
docker compose exec app composer require vendor/package
docker compose exec app composer update
```

### テーブル・モデルの確認

```bash
# テーブル一覧
docker compose exec app php artisan db:show

# ルート一覧
docker compose exec app php artisan route:list

# スケジュール一覧
docker compose exec app php artisan schedule:list
```

---

## Python 操作（Docker 内）

### 基本

```bash
# 依存関係インストール
docker compose exec python pip install -r requirements.txt

# スクリプト実行
docker compose exec python python script.py

# Django の場合
docker compose exec python python manage.py migrate
docker compose exec python python manage.py createsuperuser
docker compose exec python python manage.py shell
```

### 仮想環境について

Docker コンテナ内では仮想環境（venv / virtualenv）は通常不要。
コンテナ自体が分離環境のため、直接 `pip install` する。

```bash
# コンテナ内での pip
docker compose exec python pip install package-name

# または Dockerfile に追記してリビルド（推奨）
# RUN pip install package-name
```

---

## デバッグ

### コンテナが起動しない場合

```bash
# エラーログを確認
docker compose logs app

# 設定ファイルの構文チェック
docker compose config

# コンテナを止めずにフォアグラウンドで起動してログを見る
docker compose up app
```

### コンテナ内でのデバッグ

```bash
# コンテナ内のファイル確認
docker compose exec app ls -la /var/www/html

# 環境変数確認
docker compose exec app env | grep APP

# PHP バージョン確認
docker compose exec app php -v

# インストール済みパッケージ確認
docker compose exec app php -m
```

### DB 接続確認（Laravel）

```bash
# DB 接続テスト
docker compose exec app php artisan db:monitor

# Tinker でモデルを試す
docker compose exec app php artisan tinker
# >>> User::count()
# >>> User::first()
```

---

## ファイル同期・パーミッション

```bash
# ストレージ・キャッシュのパーミッション修正
docker compose exec app chmod -R 775 storage bootstrap/cache
docker compose exec app chown -R www-data:www-data storage bootstrap/cache

# ファイルが書き込めない場合
docker compose exec app php artisan storage:link
```

---

## よくあるトラブル

| 症状 | 原因 | 対処 |
|------|------|------|
| `Connection refused` | DB コンテナが起動前にアプリが起動 | `depends_on` / `healthcheck` を設定 |
| `.env` が反映されない | キャッシュが古い | `php artisan config:clear` |
| `Permission denied` | コンテナ内のユーザー権限 | `chown` / `chmod` で修正 |
| `Class not found` | Composer autoload が古い | `composer dump-autoload` |
| ポートが使えない | ホスト側でポートが使用中 | `docker compose down` 後に再起動 |

---

## docker-compose.yml の典型的な構成（参考）

```yaml
services:
  app:          # Laravel PHP アプリ
  nginx:        # Web サーバー
  python:       # Python サービス
  db:           # MySQL / PostgreSQL
  redis:        # キャッシュ / キュー

  # よく使うポートマッピング
  # app: 9000 (PHP-FPM)
  # nginx: 80:80
  # db: 3306:3306 または 5432:5432
  # redis: 6379:6379
```

サービス名は実際の `docker compose ps` で確認して使うこと。
