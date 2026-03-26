---
paths:
  - "**/*.php"
---

# PHP コメント規約

このプロジェクトのコードから抽出した、PHPのコメントスタイル。

---

## コメントの基本スタイル

### 1. メソッドの前コメント: 一行で目的を説明

メソッド定義の直前に `// 〜する` の形で記述する。PHPDoc は使わず、簡潔な日本語コメントを使う。

```php
// ✅ このプロジェクトのスタイル
// デバイスの設定を各マスタから取得する
public function devices_get()

// デバイスを新規登録する
public function device_upsert($data)

// デバイスごとにpatternテーブル作成
public function create_pattern_table($id, $data)

// トップページ
public function home(Request $request)

// デバイス新規登録の入力画面
public function new(Request $request)

// デバイス新規登録の内容確認
public function new_confirm(newRequest $request)
```

### 2. 処理ブロック内のコメント: 何をするかを説明

複数行にわたる処理のまとまりの前に、目的を一行で付ける。

```php
// テーブルが既にあるかチェック
if (!Schema::connection('measure_dev')->hasTable($table_name)) {

// patternテーブル作成
Schema::connection('measure_dev')->create($table_name, function (Blueprint $table) {

// 作成したpatternテーブルに初期値を入力するためにデータを作成
$columns = array_keys($data);
```

### 3. インラインコメント: 右側に説明

コードの右側に揃えて、簡潔な説明を付ける。

```php
return Device::upsert(
    [$data],    // 追加もしくは更新するデータ（idがnullの場合は追加）
    ['id'],     // 存在するかどうかを確認するためのカラム
    ['id', 'department_id', 'equipment1_id', 'top', 'left']  // 更新したいカラム
);
```

```php
// JOINのコメント
return Device::join('department', 'department.id', '=', 'device.department_id')  // 製造課
             ->join('factory', 'factory.id', '=', 'department.factory_id')        // 工場
             ->leftJoin('equipment as eq1', 'eq1.id', '=', 'device.equipment1_id')
```

### 4. 注意事項コメント: ハマりやすい点を記録

技術的な制約や注意点は、その処理の直前にコメントで残す。

```php
// ✅ 制約・注意を記録するコメント

// テーブル名が数字だけだとうまく認識してくれないので ` ` で囲む
$table_name = $id . '_pattern';

// table名をasで別名で定義したら、元の名前ではなく定義した名前でしか使えない
return Device::join('department', ...)->leftJoin('equipment as eq1', ...)
```

### 5. クラスプロパティのコメント

```php
class DeviceController extends Controller
{
    // サービスクラスとの紐付け
    protected $_mastaService, $_deviceService;

    public function __construct(
        MastaService $mastaService,
        DeviceService $deviceService
    ) {
        $this->_mastaService = $mastaService;
        $this->_deviceService = $deviceService;
    }
}
```

### 6. Migration カラムのコメント: `comment()` を必須とする

```php
// ✅ すべてのカラムに comment() を付ける
$table->id();
$table->unsignedBigInteger('format')->nullable()->default('2')->comment('フォーマット');
$table->unsignedBigInteger('eq_id1')->nullable()->comment('設備 1');
$table->string('port1', 255)->nullable()->comment('ポート1');
$table->timestamps();
```

### 7. コメントアウト: 理由があれば残す

削除できないコードは、理由のコメントとセットで残す。

```php
// ✅ 理由付きでコメントアウト
// if(empty($data['device_id']))
// {
//     $data['device_id'] = null;
// }

// 設備2が未入力ならnullを入れる（設備2は任意項目のため）
if(empty($data['equipment_2'])) {
    $data['equipment_2_name'] = null;
}
```

---

## 命名規則

### メソッド名: `snake_case`

> **このプロジェクトの特徴**: PHP メソッドも `camelCase` ではなく `snake_case` を使う。

```php
// ✅ このプロジェクトのスタイル
public function devices_get() { ... }
public function device_upsert($data) { ... }
public function create_pattern_table($id, $data) { ... }
public function factory_get() { ... }
public function factory_join_depertment() { ... }
public function equipment_get() { ... }

// 動詞_対象 の形式
public function new_confirm(newRequest $request) { ... }
public function new_store(Request $request) { ... }
public function pattern_update(Request $request) { ... }
```

### プライベート変数: `_` プレフィックス

```php
// ✅ サービス・リポジトリの変数は _ プレフィックス
protected $_mastaService;
protected $_deviceService;
protected $_deviceRepository;
protected $_historyRepository;
```

### 変数名: snake_case

```php
// ✅ 変数は snake_case
$factory = $this->_mastaService->factory_get();
$department = $this->_mastaService->factory_join_depertment();
$table_name = $id . '_pattern';
$columns = array_keys($data);
```

---

## コメントの書き分け

| 場面 | スタイル | 例 |
|------|---------|-----|
| メソッド定義前 | `// 〜する` | `// デバイスを新規登録する` |
| 処理ブロック前 | `// 〜する` / `// 〜のとき` | `// テーブルが既にあるかチェック` |
| 引数・配列要素の右 | `// 説明（補足）` | `['id'],     // 存在確認カラム` |
| JOINの右 | `// テーブルの役割` | `// 製造課` |
| 注意・制約 | `// ※ 〜に注意` | `// テーブル名が数字だけだと...` |
| Migration カラム | `.comment('日本語')` | `->comment('設備 1')` |

---

## やってはいけない

```php
// ❌ コメントなしのメソッド（何をするか不明）
public function get($id) { ... }

// ❌ コードと乖離したコメント
// ユーザーを取得する
return Device::all();  // Deviceを全件取得しているのにコメントがUser

// ❌ 冗長なコメント（コードを読めばわかる）
// $idにidを代入する
$id = $request->input('id');

// ❌ Migration でコメントなし
$table->string('eq_id1', 255);  // どの設備か不明
```

---

## チェックリスト

- [ ] publicメソッドの前に目的コメントを付ける
- [ ] 複雑な処理のブロック前にコメントを付ける
- [ ] ハマりやすい制約・注意事項をコメントで記録する
- [ ] Migrationの全カラムに `comment()` を付ける
- [ ] 右側インラインコメントは揃えて書く
- [ ] コメントアウトには理由を添える

---

> ⚠️ **注意:** このファイルはコード解析から自動生成されました。
> プロジェクト固有の要件に応じて調整してください。