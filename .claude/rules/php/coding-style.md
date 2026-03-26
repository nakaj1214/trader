---
paths:
  - "**/*.php"
---

# PHP コーディングスタイル

PHP 8.x プロジェクトに適用するルール。PSR-12 準拠。

---

## 型システム

**常に型宣言を使う。`mixed` は最後の手段。**

```php
// ✅ Good
function createUser(string $name, int $age): User { ... }

// ❌ Bad
function createUser($name, $age) { ... }
```

- 引数・戻り値・プロパティすべてに型宣言
- nullable は `?string` ではなく `string|null` を推奨（明示的）
- Union 型: `int|string`, `User|null`
- readonly プロパティ: 変更不要な値に使う

```php
class User
{
    public function __construct(
        public readonly int $id,
        public readonly string $name,
        private string|null $email = null,
    ) {}
}
```

## モダン PHP 8.x 構文

**新機能を積極的に使う:**

```php
// match 式（switch の代替）
$label = match($status) {
    'active' => 'アクティブ',
    'inactive', 'banned' => '無効',
    default => '不明',
};

// Null合体代入
$config['timeout'] ??= 30;

// Named arguments（引数の順序依存を排除）
sendEmail(to: $user->email, subject: 'Welcome', body: $content);

// Enum（PHP 8.1+）
enum Status: string {
    case Active = 'active';
    case Inactive = 'inactive';
}

// First-class callable syntax（PHP 8.1+）
$lengths = array_map(strlen(...), $strings);
```

## 命名規則

> **このプロジェクトでは `project-conventions.md` に従い snake_case を採用。**
> 標準 Laravel (camelCase) とは異なるため注意。

| 対象 | 規則 | 例 |
|------|------|-----|
| クラス | PascalCase | `UserRepository` |
| メソッド・関数 | snake_case | `get_user_by_id()` |
| 変数 | snake_case | `$user_id` |
| 定数 | UPPER_SNAKE | `MAX_RETRY_COUNT` |
| Enum ケース | PascalCase | `Status::Active` |
| プロパティ（DI） | `_` プレフィックス | `$_userService` |

## 配列・コレクション

```php
// 短縮記法を使う
$items = ['foo', 'bar', 'baz'];

// スプレッド演算子
$merged = [...$array1, ...$array2];

// array_* 関数より array_map/filter/reduce を関数型スタイルで
$activeUsers = array_filter($users, fn(User $u) => $u->isActive());
```

## エラーハンドリング

- 例外は具体的なクラスで捕捉（`catch (Exception $e)` は避ける）
- カスタム例外クラスを用途別に作る（`UserNotFoundException`, `ValidationException`）
- `@` エラー抑制演算子は使用禁止

```php
try {
    $user = $this->repository->findOrFail($id);
} catch (UserNotFoundException $e) {
    // 専用処理
} catch (DatabaseException $e) {
    Log::error('DB error', ['exception' => $e]);
    throw new ServiceException('Database unavailable', previous: $e);
}
```

## PSR-12 フォーマット

- インデント: 4スペース（タブ不可）
- 行末の余分な空白は禁止
- ファイル末尾に改行1つ
- `declare(strict_types=1);` をすべての PHP ファイルの先頭に記載

```php
<?php

declare(strict_types=1);

namespace App\Services;
```

## 禁止パターン

- `var_dump()` / `print_r()` をコミットしない（デバッグ出力）
- グローバル変数（`global $var`）
- `eval()`
- `extract()` - スコープ汚染の原因
- 動的変数（`$$variable`）
