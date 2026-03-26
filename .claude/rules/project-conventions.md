---
paths:
  - "**/*.php"
  - "**/*.blade.php"
  - "**/*.js"
  - "**/*.css"
---

# 刃具管理システム プロジェクト固有規約

Laravel 10 + PHP 8.1 + jQuery + MariaDB で構成された刃具（切削工具）在庫管理 Web システム。
VBA（Excel）によるレガシーシステムと並行運用中。
（解析日: 2026-03-05）

---

## ドメイン用語

| 用語 | 意味 | コード上の表現 |
|------|------|---------------|
| 刃具 | 切削工具全般 | blade |
| 品番 | 製品識別コード | product_number |
| 在庫 | 現在の在庫数管理 | stock |
| 入庫 | 仕入・受領処理 | inbound |
| 出庫 | 払出・使用処理 | outbound |
| 発注 | 商社への発注処理 | order / ordered |
| 製造課 | 工場内部門（5課など） | department |
| 商社 | 仕入先（タケダキカイ、石田商会等） | factory / supplier |
| 品番マスタ | 品番の基本情報テーブル | product_number テーブル |

---

## アーキテクチャ

### レイヤー構成

```
Request → Controller → Service → Repository → Model/DB
```

- **Controller**: HTTPリクエスト受付・レスポンス返却のみ。ビジネスロジックを書かない
- **Service**: ビジネスロジック。複数Repositoryをまたぐ処理もここに書く
- **Repository**: DB操作のみ。`CommonRepository` を継承して使う
- **Features/**: ファイル読み込み・汎用ユーティリティなど横断的機能

### 複数DB接続パターン

このプロジェクトは **2つのDB接続** を使い分ける：

| 接続名 | 内容 |
|--------|------|
| `blade_management` | 在庫・入出庫・発注データ（製造課ごとの動的テーブル） |
| `purchase` | 品番マスタ（全課共通） |

```php
// Repositoryでの接続指定
protected string $connectionName = 'blade_management';

// 別接続のテーブルをJOIN
->leftJoin(DB::raw('`purchase`.`product_number` as pn'), ...)
```

### 部署別動的テーブルパターン

在庫・発注・入出庫テーブルは **製造課ごとに物理テーブルが分かれている**：

```php
// テーブル名: "{department_id}_{entity}"
// 例: 5_stock, 5_ordered
protected function getDepartmentTable($department_id, string $suffix): string
{
    return "{$department_id}_{$suffix}";
}
```

- Model側の `department()` 静的メソッドでテーブルを切り替える
- Repositoryは必ず `CommonRepository` を継承し、`$connectionName` を設定する

---

## PHP / Laravel 命名規則

### このプロジェクト固有のルール（標準Laravelと異なる点）

```php
// ✅ このプロジェクト: メソッド名は snake_case
public function fetch_stock_json($user) { ... }
public function import_stock($path, $options) { ... }
public function store_order(Request $request) { ... }

// ❌ 標準LaravelのcamelCase（このプロジェクトでは使わない）
public function fetchStockJson($user) { ... }
```

### プライベートプロパティ・依存性注入

```php
// プライベートプロパティは _ プレフィックス付き
protected $_stockService;
protected $_stockMasterService;

// コンストラクタインジェクションで初期化
public function __construct(StockService $stockService)
{
    $this->_stockService = $stockService;
}
```

### ファイル・クラス名

| 対象 | 規則 | 例 |
|------|------|-----|
| Controller | `{Entity}Controller` | `StockController` |
| Service | `{Entity}Service` | `StockService`, `StockMasterService` |
| Repository | `{Entity}Repository` | `StockRepository` |
| FormRequest | `{Action}{Entity}Request` | `CreateStockMasterRequest`, `AjaxUpdateCellsRequest` |
| Model | 単数形 PascalCase | `Stock`, `ProductNumber`, `Ordered` |
| Feature | 機能名 PascalCase | `ExcelChunkReader`, `StrReplaceZero` |

### ルート名

```php
// Ajax用: ajax.{resource}.{action}
Route::get('/fetch', 'fetch_stock_json')->name('ajax.fetch_stock_json');
Route::post('/store', 'store_order')->name('ajax.order.store');

// 通常画面: {resource}.{action}
Route::get('/confirm', 'index')->name('manager.confirm');
Route::get('/suppliers', ...)->name('analytics.suppliers');
```

### テーブル名

```
{department_id}_{entity}  →  5_stock, 5_ordered（部署別）
{entity}                  →  product_number, factory, department（共通マスタ）
```

---

## コードスタイル（PHP）

### 波括弧はAllmanスタイル（改行後）

```php
// ✅ このプロジェクトのスタイル
if ($condition)
{
    // ...
}

foreach ($items as $item)
{
    // ...
}

class StockService
{
    public function method()
    {
        // ...
    }
}
```

### インデント・その他

- インデント: 4スペース（`.editorconfig` 定義済み）
- 文字コード: UTF-8
- 改行コード: LF
- ファイル末尾: 空行あり

### コメント

- 日本語コメントを積極的に使う（業務仕様の説明）
- メソッド冒頭に目的コメントを書く
- 複雑な処理には行内コメントを入れる

```php
// datatables用ajax
public function fetch_stock_json(Request $request)
{
    // A3からQ列の最終行まで
    $options['start_row'] = 3;      // 何行目から読み取りを開始するか
    $options['end_col'] = 'B';      // チャンクの終了判定を行う列
```

---

## FormRequest パターン

バリデーション + 正規化（`normalized()` メソッド）をセットで実装する：

```php
class AjaxUpdateCellsRequest extends FormRequest
{
    // バリデーション前の入力整形
    protected function prepareForValidation()
    {
        // 空文字はnullにする
    }

    // バリデーションルール
    public function rules()
    {
        // ...
    }

    // バリデーション後の型変換・整形
    protected ?array $normalized = null;
    public function passedValidation()
    {
        // 型キャストして $this->normalized に格納
    }

    // コントローラから呼ぶ
    public function normalized()
    {
        return $this->normalized ?? $this->validated();
    }
}
```

---

## CommonRepository パターン

全 Repository は `CommonRepository` を継承する：

```php
class StockRepository extends CommonRepository
{
    protected string $connectionName = 'blade_management';

    // 読み取り: query() を使う（トランザクションなし）
    public function fetch_stock_json($department_id)
    {
        return $this->query(function($connection) use ($department_id) {
            $table = $this->getDepartmentTable($department_id, 'stock');
            return $connection->table($this->getaliasTable($table, 'stock'))
                ->...
                ->get();
        });
    }

    // 書き込み: transaction() を使う
    public function import_stock($data, $department_id)
    {
        return $this->transaction(function() use ($data, $department_id) {
            Stock::department($department_id)->upsert(...);
        });
    }
}
```

---

## JavaScript (jQuery) パターン

### ファイル構成

```
public/js/
├── pages/          # ページ別スクリプト（stock/, order/, inbound/ など）
├── components/     # 再利用コンポーネント（モーダル、テーブル操作など）
├── common/         # 全ページ共通ユーティリティ
├── tab_switch.js   # タブ切り替え制御
├── user_log.js     # ユーザーアクションログ
└── page_state_store.js  # localStorage ラッパー（PageStateStore）
```

### コードスタイル

```javascript
// ✅ このプロジェクト: 波括弧は改行後（PHP同様）
$(document).ready(function ()
{
    function loadTabState()
    {
        if (store)
        {
            // ...
        }
    }
});
```

### Ajax

```javascript
// CSRF トークンは ajaxSetup で設定済み（laravel-breeze）
// エラーハンドリングは必ず書く
$.ajax({...})
    .done(function(res) { ... })
    .fail(function(jqXHR) { ... })
    .always(function() { ... });
```

---

## VBA（Excel マクロ）規約

`VBA/` ディレクトリにレガシーマクロを管理。Web システムへの移行過渡期のため並行運用中。

### 基本ルール

```vb
Option Explicit ' 必須
```

- 変数宣言は `Dim` で明示（`Option Explicit` 遵守）
- コメントは日本語可
- 変更箇所には `'---- YYYY/MM/DD insert {author} ----` 形式でコメントを入れる（既存慣習）

---

## よく使うコマンド（Docker経由）

```bash
# PHP Artisan
docker compose exec app php artisan migrate
docker compose exec app php artisan db:seed

# テスト
docker compose exec app php artisan test
docker compose exec app ./vendor/bin/phpunit

# Composer
docker compose exec app composer install
docker compose exec app composer require {package}

# フロントエンド
docker compose exec node npm run build
docker compose exec node npm run dev
```

---

## 注意事項

> ⚠️ このファイルはコード解析から自動生成されました。
> 実際の運用では開発チームのレビューを経て確定させてください。
