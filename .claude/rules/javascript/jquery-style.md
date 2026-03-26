---
paths:
  - "**/*.js"
  - "**/*.ts"
  - "**/*.jsx"
  - "**/*.tsx"
---

# JavaScript / jQuery コーディングスタイル

jQuery を主軸としたフロントエンド開発向けルール。
Laravel バックエンドとの AJAX 連携・アニメーション・イベント処理を想定。

---

## 基本方針

- **jQuery をグローバルに使う** — `$` はエイリアスとして使用。`jQuery` と混在させない
- **セレクタはキャッシュする** — 同じセレクタを2回以上使う場合は変数に保持
- **イベントは委譲（delegation）を基本とする** — 動的追加要素に対応するため
- **`$(document).ready()` は1ファイル1回** — 複数の ready ブロックは避ける

```javascript
// ✅ Good: セレクタキャッシュ
const $form = $('#contact-form');
const $submitBtn = $form.find('.submit-btn');
$submitBtn.prop('disabled', true);

// ❌ Bad: 毎回 DOM 検索
$('#contact-form .submit-btn').prop('disabled', true);
$('#contact-form .submit-btn').addClass('loading');
```

---

## イベント処理

### イベント委譲を使う（動的要素に必須）

```javascript
// ✅ Good: 委譲 — 動的追加された .item にも対応
$(document).on('click', '.item', function () {
    $(this).toggleClass('active');
});

// ❌ Bad: 静的バインド — 後から追加された要素に効かない
$('.item').on('click', function () { ... });
```

### 委譲の親要素は適切に絞る

```javascript
// ✅ Good: スコープを絞る（パフォーマンス向上）
$('#list-container').on('click', '.list-item', handler);

// ❌ Bad: document 全体に紐付け（必要以上に広い）
$(document).on('click', '.list-item', handler);
```

### イベント名に名前空間を付ける

```javascript
// ✅ Good: 後で .off() できる
$('#modal').on('click.modal', '.close-btn', closeModal);
$('#modal').off('click.modal'); // 特定イベントだけ解除できる

// ❌ Bad: 名前空間なし
$('#modal').on('click', '.close-btn', closeModal);
$('#modal').off('click'); // 他の click イベントも消えてしまう
```

---

## AJAX

### 基本パターン（Laravel バックエンド向け）

```javascript
// CSRF トークンをすべての AJAX リクエストに自動付与（必須）
$.ajaxSetup({
    headers: {
        'X-CSRF-TOKEN': $('meta[name="csrf-token"]').attr('content')
    }
});

// GET リクエスト
$.get('/api/users', { page: 1 })
    .done(function (data) {
        renderUsers(data.users);
    })
    .fail(function (jqXHR) {
        handleError(jqXHR);
    });

// POST リクエスト（JSON）
$.ajax({
    url: '/api/posts',
    method: 'POST',
    contentType: 'application/json',
    data: JSON.stringify({ title: title, body: body }),
    success: function (response) {
        showSuccess('投稿しました');
    },
    error: function (jqXHR) {
        handleError(jqXHR);
    }
});
```

### エラーハンドリングを必ず書く

```javascript
// 共通エラーハンドラー
function handleError(jqXHR) {
    const status = jqXHR.status;
    if (status === 422) {
        // バリデーションエラー（Laravel）
        const errors = jqXHR.responseJSON.errors;
        showValidationErrors(errors);
    } else if (status === 401) {
        window.location.href = '/login';
    } else {
        showToast('エラーが発生しました。再度お試しください。', 'error');
    }
}
```

### ローディング状態を管理する

```javascript
function submitForm($form) {
    const $btn = $form.find('[type="submit"]');

    // 送信前: ボタンを無効化
    $btn.prop('disabled', true).text('送信中...');

    $.post($form.attr('action'), $form.serialize())
        .done(function (res) {
            showSuccess(res.message);
        })
        .fail(handleError)
        .always(function () {
            // 完了後: ボタンを復元（成功・失敗どちらでも）
            $btn.prop('disabled', false).text('送信');
        });
}
```

---

## アニメーション

### jQuery 組み込みアニメーション

```javascript
// 表示・非表示
$('#panel').fadeIn(300);
$('#panel').fadeOut(300);
$('#panel').fadeToggle(300);

// スライド
$('#menu').slideDown(200);
$('#menu').slideUp(200);
$('#menu').slideToggle(200);

// カスタム .animate()
$('#box').animate({
    opacity: 0.8,
    left: '+=50px',
    height: 'toggle'
}, 400, 'swing');
```

### アニメーション完了後の処理

```javascript
// コールバック
$('#overlay').fadeIn(300, function () {
    // fadeIn 完了後に実行
    $(this).find('.modal-content').slideDown(200);
});

// Promise チェーン
$('#step1').fadeOut(300)
    .promise()
    .done(function () {
        $('#step2').fadeIn(300);
    });
```

### アニメーションのキャンセル（競合防止）

```javascript
// ✅ Good: 新しいアニメーション前に既存を止める
$('#box').stop(true, true).fadeIn(300);

// ❌ Bad: アニメーションが積み重なる
$('#box').fadeIn(300); // 連打すると queue が詰まる
```

### CSS トランジション推奨（重いアニメーション）

```javascript
// JS は class 切り替えだけ、アニメーションは CSS に任せる
// → GPU 加速・パフォーマンス向上
$('#panel').addClass('is-visible'); // CSS transition で動かす

// CSS 側
// .panel { opacity: 0; transition: opacity 0.3s ease; }
// .panel.is-visible { opacity: 1; }
```

---

## ユーザーアクション / インタラクション

### フォーム入力のリアルタイムバリデーション

```javascript
// debounce で連続呼び出しを間引く
let validateTimer;
$('#email-input').on('input', function () {
    clearTimeout(validateTimer);
    validateTimer = setTimeout(() => {
        validateEmail($(this).val());
    }, 300);
});
```

### スクロール連動

```javascript
// スクロール量を throttle（頻繁な発火を抑制）
let scrollTimer;
$(window).on('scroll', function () {
    if (scrollTimer) return;
    scrollTimer = setTimeout(function () {
        const scrollY = $(window).scrollTop();
        if (scrollY > 300) {
            $('#back-to-top').fadeIn(200);
        } else {
            $('#back-to-top').fadeOut(200);
        }
        scrollTimer = null;
    }, 100);
});
```

### モーダル制御パターン

```javascript
// 開く
function openModal($modal) {
    $modal.fadeIn(200);
    $('body').addClass('modal-open'); // スクロール抑制
    $modal.find('[autofocus]').focus(); // アクセシビリティ
}

// 閉じる
function closeModal($modal) {
    $modal.fadeOut(200, function () {
        $('body').removeClass('modal-open');
    });
}

// キーボード（Esc）で閉じる
$(document).on('keydown', function (e) {
    if (e.key === 'Escape') {
        closeModal($('.modal:visible'));
    }
});
```

---

## 禁止パターン

```javascript
// ❌ インラインスクリプト（HTML に onclick を書かない）
// <button onclick="doSomething()">NG</button>

// ❌ eval()
eval('someCode()');

// ❌ グローバル変数の乱用
var myData = {}; // グローバルスコープに書く

// ✅ IIFE または $(document).ready() でスコープを閉じる
(function ($) {
    'use strict';
    // ここに書く
})(jQuery);
```

---

## Laravel との連携チェックリスト

- [ ] `<meta name="csrf-token" content="{{ csrf_token() }}">` を `<head>` に追加済み
- [ ] `$.ajaxSetup` で CSRF ヘッダーを自動付与済み
- [ ] Laravel の JSON レスポンスは `response()->json()` で返す
- [ ] エラーは HTTP ステータスコード + `errors` キーで返す（422 = バリデーション）
- [ ] ファイルアップロードは `FormData` を使い `processData: false, contentType: false`
