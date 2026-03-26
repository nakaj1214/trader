---
paths:
  - "**/*.php"
  - "**/routes/**"
  - "**/app/**"
  - "**/resources/views/**"
---

# Laravel 規約・ベストプラクティス

Laravel 10/11/12 プロジェクト向けルール。

---

## 命名規則

> **このプロジェクトではメソッド名に snake_case を採用（`project-conventions.md` 参照）。**

| 対象 | 規則 | 例 |
|------|------|-----|
| Model | 単数形 PascalCase | `User`, `BlogPost` |
| Controller | 単数形 + Controller | `StockController`, `OrderController` |
| メソッド | snake_case | `fetch_stock_json()`, `store_order()` |
| Migration | snake_case + 動詞 | `create_users_table`, `add_email_to_users_table` |
| テーブル | `{department_id}_{entity}` or snake_case | `5_stock`, `product_number` |
| FK | `{model}_id` | `user_id`, `blog_post_id` |
| Route name | ドット区切り | `ajax.fetch_stock_json`, `manager.confirm` |
| Job | 動作+名詞 | `SendWelcomeEmail`, `ProcessPayment` |
| Event | 過去形 | `UserRegistered`, `OrderPlaced` |
| Listener | 動作で始まる | `SendWelcomeEmailNotification` |

## Eloquent

**リレーションは必ずメソッドで定義する:**

```php
class User extends Model
{
    // HasMany: 複数形
    public function posts(): HasMany
    {
        return $this->hasMany(Post::class);
    }

    // BelongsTo: 単数形
    public function team(): BelongsTo
    {
        return $this->belongsTo(Team::class);
    }
}
```

**N+1 問題を防ぐ:**

```php
// ❌ N+1
$users = User::all();
foreach ($users as $user) {
    echo $user->team->name; // N回クエリ発生
}

// ✅ Eager loading
$users = User::with('team')->get();
```

**クエリはスコープで整理する:**

```php
class User extends Model
{
    public function scopeActive(Builder $query): Builder
    {
        return $query->where('status', 'active');
    }
}

// 使い方
User::active()->get();
```

## バリデーション

**FormRequest を必ず使う（コントローラーに直書きしない）:**

```php
class StoreUserRequest extends FormRequest
{
    public function authorize(): bool
    {
        return $this->user()->can('create', User::class);
    }

    public function rules(): array
    {
        return [
            'name'  => ['required', 'string', 'max:255'],
            'email' => ['required', 'email', 'unique:users'],
        ];
    }
}
```

## コントローラー

**Resourceful（RESTful）を基本とする:**

- `index`, `create`, `store`, `show`, `edit`, `update`, `destroy` の7メソッドのみ
- メソッドが増えたら新しいコントローラーに分割する
- ビジネスロジックはコントローラーに書かない → Service クラスへ

```php
class UsersController extends Controller
{
    public function store(StoreUserRequest $request, UserService $service): RedirectResponse
    {
        $user = $service->create($request->validated());
        return redirect()->route('users.show', $user);
    }
}
```

## サービス層

**複雑なビジネスロジックは Service クラスに:**

```php
// app/Services/UserService.php
class UserService
{
    public function __construct(
        private readonly UserRepository $repository,
        private readonly MailService $mail,
    ) {}

    public function create(array $data): User
    {
        $user = $this->repository->create($data);
        $this->mail->sendWelcome($user);
        return $user;
    }
}
```

## Docker 環境での Artisan

Docker で動かす場合は `docker compose exec` 経由:

```bash
# artisan コマンド
docker compose exec app php artisan migrate
docker compose exec app php artisan make:model Post -mfcrs

# Composer
docker compose exec app composer install

# テスト（Pest/PHPUnit）
docker compose exec app php artisan test
docker compose exec app ./vendor/bin/pest
```

## 設定・環境変数

- `.env` の値は `config()` 経由でアクセス（`env()` をコード内に直書きしない）
- 設定ファイルに `env()` を書き、コードからは `config('app.debug')` で参照

```php
// ❌ Bad
if (env('APP_ENV') === 'production') { ... }

// ✅ Good
if (app()->isProduction()) { ... }
if (config('app.env') === 'production') { ... }
```

## テスト

- テストは Pest（Laravel 11+ デフォルト）推奨
- Feature テスト: HTTP リクエスト〜レスポンスを通しでテスト
- Unit テスト: Service/Repository の単体テスト
- Factory を必ず使う（`User::factory()->create()`）

```php
test('ユーザーが登録できる', function () {
    $response = $this->post('/users', [
        'name' => 'John',
        'email' => 'john@example.com',
    ]);

    $response->assertRedirect('/users/1');
    $this->assertDatabaseHas('users', ['email' => 'john@example.com']);
});
```

## セキュリティ必須チェック

- [ ] ユーザー入力は必ず FormRequest でバリデーション
- [ ] 認可は Policy または Gate で行う（コントローラーに直書きしない）
- [ ] `Mass Assignment` 防止: `$fillable` または `$guarded` を設定
- [ ] ファイルアップロード: MIME タイプ・サイズを検証
- [ ] Raw SQL を使う場合は必ず prepared statement（`DB::select('... ?', [$id])`）
