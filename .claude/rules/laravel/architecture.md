---
paths:
  - "**/*.php"
  - "**/routes/**"
  - "**/app/**"
---

# Laravel アーキテクチャ規約

汎用的な Laravel プロジェクト向けのアーキテクチャ設計ルール。

---

## レイヤードアーキテクチャ

### 基本レイヤー構成

```
Controller → Service → Repository → Model
```

**各レイヤーの責務:**

| レイヤー | 責務 | 例 |
|---------|------|-----|
| **Controller** | HTTPリクエスト処理、レスポンス返却、バリデーション | `DeviceController` |
| **Service** | ビジネスロジック、複数Repositoryの調整 | `DeviceService` |
| **Repository** | データアクセス、クエリ構築 | `DeviceRepository` |
| **Model** | DBテーブルとのマッピング、リレーション定義 | `Device` |

### 依存性注入 (DI)

**コンストラクタインジェクションを使用する:**

```php
// Controller
class DeviceController extends Controller
{
    protected $_deviceService;
    protected $_mastaService;

    public function __construct(
        DeviceService $deviceService,
        MastaService $mastaService
    ) {
        $this->_deviceService = $deviceService;
        $this->_mastaService = $mastaService;
    }
}

// Service
class DeviceService
{
    protected $_deviceRepository;

    public function __construct(DeviceRepository $deviceRepository)
    {
        $this->_deviceRepository = $deviceRepository;
    }
}
```

---

## ディレクトリ構成

```
app/
├── Http/
│   ├── Controllers/      # HTTPリクエスト処理
│   ├── Requests/         # FormRequest（バリデーション）
│   └── Middleware/
├── Services/             # ビジネスロジック
├── Repositories/         # データアクセス層
├── Models/               # Eloquent Model
├── Exports/              # Excel等のエクスポート処理
└── Providers/

database/
├── migrations/           # DBマイグレーション
├── seeders/              # 初期データ投入
└── factories/            # テストデータ生成

resources/
├── views/                # Bladeテンプレート
├── css/
└── js/

public/
├── ajax/                 # AJAX専用スクリプト（配置先はプロジェクト次第）
├── css/
├── js/
└── img/

routes/
├── web.php               # Web routes
└── api.php               # API routes
```

---

## Controller パターン

### RESTful コントローラー

```php
class DeviceController extends Controller
{
    // 一覧表示
    public function index(Request $request)
    {
        return view('device.index');
    }

    // 新規作成フォーム表示
    public function new(Request $request)
    {
        $data = $this->_mastaService->getData();
        return view('device.new', compact('data'));
    }

    // 確認画面表示
    public function new_confirm(DeviceRequest $request)
    {
        $data = $request->validated();
        return view('device.new_confirm', compact('data'));
    }

    // 登録処理
    public function new_store(Request $request)
    {
        $data = $request->only(['field1', 'field2']);
        $this->_deviceService->create($data);
        return redirect()->route('device.index');
    }
}
```

**命名規則:**
- 一覧: `index()`
- 新規作成フォーム: `new()` または `create()`
- 確認画面: `{action}_confirm()`
- 保存処理: `{action}_store()`
- 編集フォーム: `edit($id)`
- 更新処理: `update($id)`

### FormRequest によるバリデーション

```php
// app/Http/Requests/Device/DeviceRequest.php
class DeviceRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true; // 認可チェック
    }

    public function rules(): array
    {
        return [
            'name' => 'required|string|max:255',
            'email' => 'required|email|unique:users',
        ];
    }
}
```

---

## Service パターン

**ビジネスロジックを Service に集約:**

```php
class DeviceService
{
    protected $_deviceRepository;
    protected $_logRepository;

    public function __construct(
        DeviceRepository $deviceRepository,
        LogRepository $logRepository
    ) {
        $this->_deviceRepository = $deviceRepository;
        $this->_logRepository = $logRepository;
    }

    // ビジネスロジック: デバイス作成 + ログ記録
    public function createDevice(array $data): Device
    {
        $device = $this->_deviceRepository->create($data);
        $this->_logRepository->log('device_created', $device->id);
        return $device;
    }

    // Repository への委譲（単純なCRUD）
    public function findById(int $id): ?Device
    {
        return $this->_deviceRepository->findById($id);
    }
}
```

**Service のルール:**
- 複数 Repository を調整する場合に使用
- トランザクション制御は Service で行う
- 単純な CRUD は Repository に委譲

---

## Repository パターン

**データアクセスを Repository に集約:**

```php
class DeviceRepository
{
    // Eloquent を使ったデータ取得
    public function findById(int $id): ?Device
    {
        return Device::find($id);
    }

    // JOIN クエリ
    public function getDevicesWithRelations()
    {
        return Device::join('department', 'department.id', '=', 'device.department_id')
                     ->leftJoin('equipment as eq1', 'eq1.id', '=', 'device.equipment1_id')
                     ->select('device.*', 'department.name as dept_name', 'eq1.model as eq_model')
                     ->get();
    }

    // Upsert（存在すれば更新、なければ挿入）
    public function upsert(array $data): int
    {
        return Device::upsert(
            [$data],
            ['id'],  // ユニークキー
            ['name', 'status', 'updated_at']  // 更新カラム
        );
    }
}
```

**Repository のルール:**
- Eloquent クエリビルダーを使用
- 生 SQL は Schema ビルダーで安全に構築
- トランザクションは Service 層で管理

---

## Model パターン

```php
class Device extends Model
{
    use HasFactory;

    // 複数DB接続がある場合は明示
    protected $connection = 'measure';

    // テーブル名（省略可能だが明示推奨）
    protected $table = 'device';

    // Mass Assignment 保護
    protected $fillable = [
        'id',
        'department_id',
        'equipment1_id',
        'equipment2_id',
        'top',
        'left',
    ];

    // リレーション定義
    public function department()
    {
        return $this->belongsTo(Department::class);
    }

    public function equipment1()
    {
        return $this->belongsTo(Equipment::class, 'equipment1_id');
    }
}
```

---

## トランザクション管理

```php
// Service 層でトランザクション制御
use Illuminate\Support\Facades\DB;

public function createDeviceWithPattern(array $data): Device
{
    DB::beginTransaction();
    try {
        $device = $this->_deviceRepository->create($data);
        $this->_patternRepository->createForDevice($device->id);

        DB::commit();
        return $device;
    } catch (\Exception $e) {
        DB::rollBack();
        throw $e;
    }
}
```

---

## Docker 開発環境

```yaml
# docker-compose.yml の典型的な構成
services:
  mariadb:
    image: mariadb:10.11
    ports:
      - "3306:3306"
    volumes:
      - ./mariadb/data:/var/lib/mysql
    environment:
      MARIADB_ROOT_PASSWORD: password
      MARIADB_DATABASE: laravel
      TZ: Asia/Tokyo

  laravel:
    build: ./php
    ports:
      - "80:80"
    volumes:
      - ./src:/var/www/html
    depends_on:
      - mariadb
```

**Docker でのコマンド実行:**
```bash
# Artisan コマンド
docker compose exec laravel php artisan migrate
docker compose exec laravel php artisan make:model Device -mfcrs

# Composer
docker compose exec laravel composer install

# テスト
docker compose exec laravel php artisan test
```

---

## チェックリスト

### アーキテクチャ
- [ ] Controller は HTTP 処理のみ（ビジネスロジックを書かない）
- [ ] Service にビジネスロジックを集約
- [ ] Repository にデータアクセスを集約
- [ ] Model にリレーションを定義

### DI（依存性注入）
- [ ] コンストラクタインジェクションを使用
- [ ] protected プロパティに `_` プレフィックス（任意）

### トランザクション
- [ ] DB トランザクションは Service 層で管理
- [ ] try-catch で例外ハンドリング
- [ ] ロールバック処理を実装

### FormRequest
- [ ] バリデーションは FormRequest で定義
- [ ] Controller に直接バリデーションを書かない

---

> ⚠️ **注意:** このファイルはコード解析から自動生成されました。
> プロジェクト固有の要件に応じて調整してください。
