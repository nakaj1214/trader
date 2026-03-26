---
paths:
  - "**/*.blade.php"
---

# Blade ファイルへの JavaScript 直書き禁止

## ルール

Blade テンプレート（`.blade.php`）に `<script>...</script>` でインライン JavaScript を直接記述してはならない。

## 許可される記述

- `<script src="...">` による外部 JS ファイルの読み込み
- `@push('scripts')` 内での外部 JS ファイルの読み込み
- `data-*` 属性を使った Blade → JS のデータ受け渡し

## 禁止される記述

```html
{{-- ❌ インライン JS --}}
<script>
    $(function () {
        // 直接書かれたロジック
    });
</script>

{{-- ❌ @push 内でもインラインは禁止 --}}
@push('scripts')
    <script>
        // 直接書かれたロジック
    </script>
@endpush
```

## 正しいパターン

```html
{{-- ✅ 外部ファイルを読み込む --}}
@push('scripts')
    <script src="{{ asset('js/pages/home.js') }}"></script>
@endpush

{{-- ✅ Blade の変数は data 属性で渡す --}}
<div id="app-data"
    data-csrf-token="{{ csrf_token() }}"
    data-user-id="{{ $user->id }}"
    data-api-url="{{ route('api.endpoint') }}">
</div>
```

## JS ファイルの配置規則

| 画面 | JS ファイルパス |
|------|----------------|
| ページ固有 | `public/js/pages/{page_name}.js` |
| コンポーネント固有 | `public/js/components/{component_name}/{file}.js` |
| 共通ユーティリティ | `public/js/common/{file}.js` |

## Blade → JS へのデータ受け渡し

PHP の変数を JS に渡す場合は `data-*` 属性を使用する：

```php
{{-- Blade --}}
<div id="page-config"
    data-year="{{ $year }}"
    data-month="{{ $current_month }}"
    data-ajax-url="{{ route('analytics.daily_items.ajax') }}">
</div>
```

```javascript
// JS ファイル
$(function () {
    var $config = $('#page-config');
    var year = $config.data('year');
    var month = $config.data('month');
    var ajaxUrl = $config.data('ajax-url');
});
```
