---
paths:
  - "**/*.php"
  - "**/database/**"
  - "**/app/Models/**"
---

# Laravel データベース規約

汎用的な Laravel プロジェクト向けのデータベース設計・操作ルール。

---

## Migration（マイグレーション）

### 命名規則

```
{日時}_{動詞}_{テーブル名}_table.php

例:
2024_06_18_130603_create_equipment_table.php
2024_07_01_120000_add_status_to_users_table.php
2024_07_15_140000_modify_name_in_devices_table.php
```

### Migration の書き方

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('equipment', function (Blueprint $table) {
            $table->id();
            $table->unsignedBigInteger('department_id')->comment('部署ID');
            $table->string('line', 255)->comment('ライン');
            $table->integer('equipment_id')->comment('設備番号');
            $table->string('category', 255)->comment('種類');
            $table->string('model', 255)->comment('型式');
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('equipment');
    }
};
```

### カラム定義のベストプラクティス

```php
// ID カラム
$table->id();  // unsignedBigInteger の AUTO_INCREMENT

// 外部キー
$table->unsignedBigInteger('user_id')->comment('ユーザーID');
$table->foreign('user_id')->references('id')->on('users')->onDelete('cascade');

// 文字列（長さ指定必須）
$table->string('name', 255)->comment('名前');

// テキスト
$table->text('description')->nullable()->comment('説明');

// 整数
$table->integer('count')->default(0)->comment('カウント');

// 日時
$table->timestamp('published_at')->nullable()->comment('公開日時');
$table->timestamps();  // created_at, updated_at

// 論理値
$table->boolean('is_active')->default(true)->comment('有効フラグ');

// JSON
$table->json('metadata')->nullable()->comment('メタデータ');
```

**ルール:**
- すべてのカラムに `comment()` を付ける
- NULL許可は明示的に `nullable()` を指定
- デフォルト値は `default()` で明示
- 文字列は必ず長さを指定（`string('name', 255)`）

---

## 初期データ投入（Seeder）

### Migration 内で初期データを投入

```php
public function up(): void
{
    Schema::create('equipment', function (Blueprint $table) {
        // カラム定義...
    });

    // 初期データ投入
    DB::table('equipment')->insert([
        [
            'department_id' => 1,
            'line' => 'A',
            'equipment_id' => 1,
            'category' => 'AAA',
            'model' => '設備A',
        ],
        [
            'department_id' => 1,
            'line' => 'B',
            'equipment_id' => 2,
            'category' => 'BBB',
            'model' => '設備B',
        ],
    ]);
}
```

### Seeder クラスを使う場合

```php
// database/seeders/EquipmentSeeder.php
class EquipmentSeeder extends Seeder
{
    public function run(): void
    {
        Equipment::create([
            'department_id' => 1,
            'line' => 'A',
            'equipment_id' => 1,
            'category' => 'AAA',
            'model' => '設備A',
        ]);
    }
}
```

```bash
# Seeder 実行
php artisan db:seed --class=EquipmentSeeder
```

---

## Eloquent クエリパターン

### 基本的な取得

```php
// 全件取得
$devices = Device::all();

// WHERE条件
$devices = Device::where('status', 'active')->get();

// 単一レコード取得
$device = Device::find($id);
$device = Device::where('name', 'Device1')->first();
$device = Device::findOrFail($id);  // 見つからなければ例外
```

### JOIN クエリ

```php
$devices = Device::join('department', 'department.id', '=', 'device.department_id')
                 ->leftJoin('equipment as eq1', 'eq1.id', '=', 'device.equipment1_id')
                 ->leftJoin('equipment as eq2', 'eq2.id', '=', 'device.equipment2_id')
                 ->select(
                     'device.*',
                     'department.name as dept_name',
                     'eq1.model as eq1_model',
                     'eq2.model as eq2_model'
                 )
                 ->get();
```

**ポイント:**
- `leftJoin` で NULL許可の関連データを取得
- `as` で別名を付けると、元の名前では参照できない
- `select()` で取得カラムを明示（`device.*` で全カラム + 追加カラム）

### Eager Loading（N+1問題の回避）

```php
// ❌ Bad: N+1問題が発生
$devices = Device::all();
foreach ($devices as $device) {
    echo $device->department->name;  // 毎回クエリ発行
}

// ✅ Good: Eager Loading
$devices = Device::with('department', 'equipment1')->get();
foreach ($devices as $device) {
    echo $device->department->name;  // 事前に取得済み
}
```

---

## Upsert（存在すれば更新、なければ挿入）

```php
Device::upsert(
    [
        ['id' => 1, 'name' => 'Device1', 'status' => 'active'],
        ['id' => 2, 'name' => 'Device2', 'status' => 'inactive'],
    ],
    ['id'],  // ユニークキー（存在チェック用）
    ['name', 'status', 'updated_at']  // 更新対象カラム
);
```

**使用例:**
- バルクインサート時に重複を避ける
- 既存レコードを上書き更新したい場合

---

## 動的テーブル作成（Schema Builder）

```php
use Illuminate\Support\Facades\Schema;
use Illuminate\Database\Schema\Blueprint;

public function createPatternTable(string $id, array $data): void
{
    $tableName = $id . '_pattern';

    // テーブル存在チェック
    if (!Schema::connection('measure_dev')->hasTable($tableName)) {
        Schema::connection('measure_dev')->create($tableName, function (Blueprint $table) {
            $table->id();
            $table->unsignedBigInteger('format')->nullable()->default(2)->comment('フォーマット');
            $table->unsignedBigInteger('eq_id1')->nullable()->comment('設備1');
            $table->unsignedBigInteger('eq_id2')->nullable()->comment('設備2');
            $table->string('port1', 255)->nullable()->comment('ポート1');
            $table->timestamps();
        });
    }
}
```

**注意点:**
- テーブル名が数字のみの場合はバッククォートで囲む必要がある場合がある
- 動的テーブル作成は慎重に（Migration では管理できない）

---

## 複数データベース接続

### config/database.php

```php
'connections' => [
    'mysql' => [
        'driver' => 'mysql',
        'host' => env('DB_HOST', '127.0.0.1'),
        'database' => env('DB_DATABASE', 'laravel'),
        // ...
    ],
    'measure' => [
        'driver' => 'mysql',
        'host' => env('MEASURE_DB_HOST', '127.0.0.1'),
        'database' => env('MEASURE_DB_DATABASE', 'measure'),
        // ...
    ],
],
```

### Model で接続先を指定

```php
class Device extends Model
{
    protected $connection = 'measure';  // 明示的に接続先を指定
    protected $table = 'device';
}
```

### クエリビルダーで接続先を指定

```php
DB::connection('measure')->table('device')->get();
Schema::connection('measure')->hasTable('device');
```

---

## トランザクション

```php
use Illuminate\Support\Facades\DB;

DB::beginTransaction();
try {
    $device = Device::create($data);
    Pattern::create(['device_id' => $device->id]);

    DB::commit();
} catch (\Exception $e) {
    DB::rollBack();
    Log::error('Transaction failed', ['error' => $e->getMessage()]);
    throw $e;
}
```

**接続先を指定する場合:**
```php
DB::connection('measure')->beginTransaction();
try {
    // ...
    DB::connection('measure')->commit();
} catch (\Exception $e) {
    DB::connection('measure')->rollBack();
    throw $e;
}
```

---

## 生SQLの実行（安全な方法）

```php
// ✅ プレースホルダーを使う（SQLインジェクション対策）
$devices = DB::select('SELECT * FROM device WHERE id = ?', [$id]);

// ✅ 名前付きプレースホルダー
$devices = DB::select('SELECT * FROM device WHERE status = :status', ['status' => 'active']);

// ❌ 危険: 直接文字列結合
$devices = DB::select("SELECT * FROM device WHERE id = $id");  // SQLインジェクション脆弱性
```

---

## チェックリスト

### Migration
- [ ] コメント (`comment()`) をすべてのカラムに付ける
- [ ] NULL許可は `nullable()` を明示
- [ ] デフォルト値は `default()` で明示
- [ ] 外部キー制約を定義（必要に応じて）
- [ ] `down()` メソッドでロールバック処理を実装

### Eloquent
- [ ] N+1問題を回避（`with()` で Eager Loading）
- [ ] JOIN は必要最小限に（リレーション推奨）
- [ ] Mass Assignment 保護（`$fillable` または `$guarded`）

### 生SQL
- [ ] プレースホルダー (`?` または `:name`) を使用
- [ ] 文字列結合でSQLを構築しない

### トランザクション
- [ ] Service 層でトランザクション管理
- [ ] `try-catch` で例外ハンドリング
- [ ] ロールバック処理を実装

---

> ⚠️ **注意:** このファイルはコード解析から自動生成されました。
> プロジェクト固有の要件に応じて調整してください。
