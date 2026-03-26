---
paths:
  - "**/*.php"
  - "**/*.blade.php"
  - "**/*.js"
  - "**/routes/**"
  - "**/app/**"
---

# Laravel + jQuery フロントエンド統合

Laravel バックエンドと jQuery フロントエンドの統合パターン。

---

## Blade テンプレート構成

### ディレクトリ構成

```
resources/views/
├── layouts/
│   └── app.blade.php        # 共通レイアウト
├── device/
│   ├── index.blade.php      # デバイス一覧
│   ├── new.blade.php        # 新規作成フォーム
│   ├── new_confirm.blade.php # 確認画面
│   └── pattern.blade.php    # パターン設定
└── history/
    ├── index.blade.php
    └── chart.blade.php
```

### レイアウト継承

```blade
{{-- resources/views/layouts/app.blade.php --}}
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>@yield('title', 'デフォルトタイトル')</title>
    <link rel="stylesheet" href="{{ asset('css/app.css') }}">
    @stack('styles')
</head>
<body>
    @yield('content')

    <script src="{{ asset('js/jquery.min.js') }}"></script>
    @stack('scripts')
</body>
</html>
```

```blade
{{-- resources/views/device/index.blade.php --}}
@extends('layouts.app')

@section('title', 'デバイス一覧')

@push('styles')
<link rel="stylesheet" href="{{ asset('css/device.css') }}">
@endpush

@section('content')
<div class="container">
    <h1>デバイス一覧</h1>
    <!-- コンテンツ -->
</div>
@endsection

@push('scripts')
<script src="{{ asset('js/device.js') }}"></script>
@endpush
```

---

## AJAX 統合

### CSRF トークンの設定（必須）

```blade
<head>
    <meta name="csrf-token" content="{{ csrf_token() }}">
</head>
```

```javascript
// すべてのAJAXリクエストに自動でCSRFトークンを付与
$.ajaxSetup({
    headers: {
        'X-CSRF-TOKEN': $('meta[name="csrf-token"]').attr('content')
    }
});
```

### GET リクエスト

```javascript
// デバイス一覧を取得
$.get('/api/devices', { status: 'active' })
    .done(function(data) {
        renderDevices(data.devices);
    })
    .fail(function(jqXHR) {
        handleError(jqXHR);
    });
```

**Laravel 側（Controller）:**
```php
public function getDevices(Request $request)
{
    $status = $request->input('status');
    $devices = Device::where('status', $status)->get();

    return response()->json([
        'devices' => $devices
    ]);
}
```

### POST リクエスト（JSON）

```javascript
// デバイスを作成
const data = {
    name: 'Device1',
    department_id: 1,
    equipment1_id: 2
};

$.ajax({
    url: '/api/devices',
    method: 'POST',
    contentType: 'application/json',
    data: JSON.stringify(data),
    success: function(response) {
        showSuccess('デバイスを作成しました');
    },
    error: function(jqXHR) {
        handleError(jqXHR);
    }
});
```

**Laravel 側（Controller）:**
```php
public function store(Request $request)
{
    $validated = $request->validate([
        'name' => 'required|string|max:255',
        'department_id' => 'required|integer|exists:departments,id',
    ]);

    $device = Device::create($validated);

    return response()->json([
        'message' => 'デバイスを作成しました',
        'device' => $device
    ], 201);
}
```

### エラーハンドリング

```javascript
function handleError(jqXHR) {
    const status = jqXHR.status;

    if (status === 422) {
        // バリデーションエラー（Laravel）
        const errors = jqXHR.responseJSON.errors;
        showValidationErrors(errors);
    } else if (status === 401) {
        // 認証エラー
        window.location.href = '/login';
    } else if (status === 404) {
        showToast('リソースが見つかりません', 'error');
    } else {
        showToast('エラーが発生しました', 'error');
    }
}
```

**Laravel 側（バリデーションエラーレスポンス）:**
```php
// FormRequest が自動で返す
{
    "message": "The given data was invalid.",
    "errors": {
        "name": ["The name field is required."],
        "email": ["The email has already been taken."]
    }
}
```

---

## データの受け渡し

### Controller から View へ（compact）

```php
public function show($id)
{
    $device = Device::with('department', 'equipment1')->findOrFail($id);
    $factory = $this->_mastaService->factory_get();
    $equipment = $this->_mastaService->equipment_get();

    return view('device.show', compact('device', 'factory', 'equipment'));
}
```

### Blade で JavaScript 変数に渡す

```blade
<script>
    // PHP変数をJavaScriptに渡す
    const device = @json($device);
    const equipmentList = @json($equipment);
    const csrfToken = '{{ csrf_token() }}';

    console.log(device.name);
    console.log(equipmentList);
</script>
```

**安全な渡し方:**
- `@json()` を使う（XSS対策済み）
- `{!! !!}` は使わない（エスケープされない）

---

## フォーム送信パターン

### 通常のフォーム送信

```blade
<form action="{{ route('device.store') }}" method="POST">
    @csrf
    <input type="text" name="name" value="{{ old('name') }}">
    <button type="submit">登録</button>
</form>
```

**バリデーションエラー表示:**
```blade
@if ($errors->any())
    <div class="alert alert-danger">
        <ul>
            @foreach ($errors->all() as $error)
                <li>{{ $error }}</li>
            @endforeach
        </ul>
    </div>
@endif

<input type="text" name="name" value="{{ old('name') }}"
       class="@error('name') is-invalid @enderror">
@error('name')
    <span class="error">{{ $message }}</span>
@enderror
```

### AJAX フォーム送信

```javascript
$('#device-form').on('submit', function(e) {
    e.preventDefault();

    const $form = $(this);
    const $btn = $form.find('[type="submit"]');

    // ボタン無効化
    $btn.prop('disabled', true).text('送信中...');

    $.post($form.attr('action'), $form.serialize())
        .done(function(response) {
            showSuccess(response.message);
            $form[0].reset();
        })
        .fail(function(jqXHR) {
            handleError(jqXHR);
        })
        .always(function() {
            $btn.prop('disabled', false).text('送信');
        });
});
```

---

## ルーティング

### 名前付きルート

```php
// routes/web.php
Route::get('/device', [DeviceController::class, 'index'])->name('device.index');
Route::get('/device/new', [DeviceController::class, 'new'])->name('device.new');
Route::post('/device/new/confirm', [DeviceController::class, 'new_confirm'])->name('device.new_confirm');
Route::post('/device/new/store', [DeviceController::class, 'new_store'])->name('device.new_store');
Route::get('/device/{id}/edit', [DeviceController::class, 'edit'])->name('device.edit');
```

**Blade でルート URL 生成:**
```blade
<a href="{{ route('device.index') }}">一覧に戻る</a>
<a href="{{ route('device.edit', ['id' => $device->id]) }}">編集</a>

<form action="{{ route('device.store') }}" method="POST">
    @csrf
    <!-- ... -->
</form>
```

**JavaScript でルート URL を使う:**
```blade
<script>
    const routes = {
        deviceIndex: '{{ route("device.index") }}',
        deviceStore: '{{ route("device.store") }}',
        deviceEdit: (id) => `/device/${id}/edit`
    };

    // 使用例
    $.get(routes.deviceIndex);
</script>
```

---

## 静的ファイル配置

```
public/
├── css/
│   ├── device/
│   │   └── index.css
│   └── history/
│       └── chart.css
├── js/
│   ├── device/
│   │   └── index.js
│   └── history/
│       └── chart.js
├── img/
└── ajax/              # AJAX専用スクリプト（オプション）
    └── history/
        └── get_history.php
```

**Blade で読み込み:**
```blade
<link rel="stylesheet" href="{{ asset('css/device/index.css') }}">
<script src="{{ asset('js/device/index.js') }}"></script>
<img src="{{ asset('img/logo.png') }}" alt="Logo">
```

---

## セッション・Flash メッセージ

### Controller でセッションに保存

```php
// 成功メッセージ
session()->flash('success', 'デバイスを作成しました');
return redirect()->route('device.index');

// エラーメッセージ
session()->flash('error', '作成に失敗しました');
return redirect()->back()->withInput();

// カスタムキー
session()->put('rpi_status', 'OK');
```

### Blade で表示

```blade
@if (session('success'))
    <div class="alert alert-success">
        {{ session('success') }}
    </div>
@endif

@if (session('error'))
    <div class="alert alert-danger">
        {{ session('error') }}
    </div>
@endif

@if (session()->has('rpi_status'))
    <p>RPI Status: {{ session('rpi_status') }}</p>
@endif
```

---

## チェックリスト

### CSRF 対策
- [ ] `<meta name="csrf-token">` をヘッダーに追加
- [ ] `$.ajaxSetup` で CSRF トークンを自動付与
- [ ] フォームに `@csrf` を追加

### データ受け渡し
- [ ] PHP → JS は `@json()` を使用
- [ ] XSS対策のため `{!! !!}` を避ける
- [ ] エスケープが必要な場所は `{{ }}` を使用

### エラーハンドリング
- [ ] AJAX エラーを適切にハンドリング（422, 401, 404等）
- [ ] Laravel バリデーションエラーを表示
- [ ] ユーザーフレンドリーなエラーメッセージ

### ルーティング
- [ ] 名前付きルートを使用（`route('name')`）
- [ ] RESTful な命名規則に従う

---

> ⚠️ **注意:** このファイルはコード解析から自動生成されました。
> プロジェクト固有の要件に応じて調整してください。
