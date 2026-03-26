# jQuery インタラクション・AJAX — 実装パターン集

Laravel + Docker バックエンドと jQuery フロントエンドの実装パターン。
アニメーション・ユーザーアクション・AJAX の3軸で整理。

---

## セットアップ（必須）

### HTML head に CSRF トークンを追加

```html
<meta name="csrf-token" content="{{ csrf_token() }}">
```

### jQuery 初期化テンプレート

```javascript
(function ($) {
    'use strict';

    // すべての AJAX に CSRF トークンを自動付与
    $.ajaxSetup({
        headers: {
            'X-CSRF-TOKEN': $('meta[name="csrf-token"]').attr('content')
        }
    });

    // DOM 準備完了後に実行
    $(function () {
        initEvents();
        initAnimations();
    });

    function initEvents() { /* イベント初期化 */ }
    function initAnimations() { /* アニメーション初期化 */ }

})(jQuery);
```

---

## アニメーションパターン

### 1. 表示・非表示の切り替え

```javascript
// フェード
$('#panel').fadeIn(300);
$('#panel').fadeOut(300);
$('#panel').fadeToggle(300);

// スライド
$('#menu').slideDown(250);
$('#menu').slideUp(250);
$('#menu').slideToggle(250);

// 競合防止（連打対策）
$('#target').stop(true, true).fadeIn(300);
```

### 2. クラスで CSS トランジションを動かす（推奨）

重いアニメーションは CSS に任せる。jQuery は class 切り替えだけ担当。

```javascript
// JS 側: class を付け外しするだけ
$('#hero').addClass('is-visible');
$('#hero').removeClass('is-visible');
$('#nav').toggleClass('is-open');

// CSS 側（別ファイルで定義）
// .hero { opacity: 0; transform: translateY(20px); transition: all 0.4s ease; }
// .hero.is-visible { opacity: 1; transform: translateY(0); }
```

### 3. スクロール連動アニメーション

```javascript
// 画面内に入った要素をフェードイン
function checkInView() {
    const windowBottom = $(window).scrollTop() + $(window).height();
    $('.fade-in-on-scroll:not(.visible)').each(function () {
        if ($(this).offset().top < windowBottom - 50) {
            $(this).addClass('visible');
        }
    });
}

// throttle でパフォーマンス確保
let scrollTimer;
$(window).on('scroll', function () {
    if (scrollTimer) return;
    scrollTimer = setTimeout(function () {
        checkInView();
        scrollTimer = null;
    }, 100);
});
checkInView(); // 初回実行
```

### 4. ステップ式アニメーション（順序制御）

```javascript
// フェードアウト → フェードイン の順序を保証
$('#step1').fadeOut(300, function () {
    $('#step2').fadeIn(300);
});

// Promise を使ったチェーン
function animateSequence() {
    return $('#overlay').fadeIn(200)
        .promise()
        .then(function () {
            return $('#modal-content').slideDown(300).promise();
        })
        .then(function () {
            $('#modal-content').find('input:first').focus();
        });
}
```

### 5. カスタム .animate()

```javascript
$('#progress-bar').animate(
    { width: progress + '%' },
    { duration: 600, easing: 'swing' }
);

// 数値カウントアップ
$({ count: 0 }).animate({ count: targetValue }, {
    duration: 1000,
    step: function () {
        $('#counter').text(Math.floor(this.count).toLocaleString());
    }
});
```

---

## ユーザーアクション / イベント処理

### 1. イベント委譲（動的要素に必須）

```javascript
// 動的に追加された要素にも効く
$('#list').on('click', '.list-item', function () {
    const id = $(this).data('id');
    loadDetail(id);
});

// 削除ボタン
$('#table').on('click', '.btn-delete', function () {
    const $row = $(this).closest('tr');
    confirmAndDelete($row);
});
```

### 2. フォーム送信

```javascript
$('#myForm').on('submit', function (e) {
    e.preventDefault(); // デフォルト送信をキャンセル
    submitForm($(this));
});

function submitForm($form) {
    const $btn = $form.find('[type="submit"]');
    $btn.prop('disabled', true).text('送信中...');

    $.ajax({
        url: $form.attr('action'),
        method: $form.attr('method') || 'POST',
        data: $form.serialize(),
        success: function (res) {
            showToast(res.message, 'success');
            $form[0].reset();
        },
        error: function (jqXHR) {
            handleAjaxError(jqXHR, $form);
        },
        complete: function () {
            $btn.prop('disabled', false).text('送信');
        }
    });
}
```

### 3. リアルタイム入力バリデーション

```javascript
// debounce: 入力が止まってから 300ms 後に実行
let inputTimer;
$('#search-input').on('input', function () {
    const query = $(this).val().trim();
    clearTimeout(inputTimer);
    if (query.length < 2) {
        $('#search-results').empty();
        return;
    }
    inputTimer = setTimeout(() => searchUsers(query), 300);
});

function searchUsers(query) {
    $.get('/api/users/search', { q: query })
        .done(function (data) {
            renderSearchResults(data);
        });
}
```

### 4. モーダル

```javascript
// 開く
$(document).on('click', '[data-modal]', function () {
    const target = $(this).data('modal');
    openModal($('#' + target));
});

function openModal($modal) {
    $modal.fadeIn(250);
    $('body').addClass('is-modal-open');
    $modal.find('[autofocus]').focus();
}

// 閉じる（複数の方法に対応）
$(document).on('click', '.modal-close, .modal-overlay', function () {
    closeModal($(this).closest('.modal'));
});
$(document).on('keydown', function (e) {
    if (e.key === 'Escape') closeModal($('.modal:visible'));
});

function closeModal($modal) {
    $modal.fadeOut(200, function () {
        $('body').removeClass('is-modal-open');
    });
}
```

### 5. タブ・アコーディオン

```javascript
// タブ切り替え
$(document).on('click', '.tab-btn', function () {
    const target = $(this).data('tab');
    $('.tab-btn').removeClass('active');
    $(this).addClass('active');
    $('.tab-panel').hide();
    $('#tab-' + target).fadeIn(200);
});

// アコーディオン
$(document).on('click', '.accordion-header', function () {
    const $content = $(this).next('.accordion-body');
    const isOpen = $content.is(':visible');
    // 他をすべて閉じる
    $('.accordion-body').slideUp(200);
    $('.accordion-header').removeClass('active');
    if (!isOpen) {
        $content.slideDown(250);
        $(this).addClass('active');
    }
});
```

---

## AJAX パターン

### 1. GET でデータ取得・描画

```javascript
function loadPosts(page) {
    const $container = $('#posts-container');
    $container.addClass('loading');

    $.get('/api/posts', { page: page, per_page: 10 })
        .done(function (data) {
            renderPosts(data.posts);
            renderPagination(data.meta);
        })
        .fail(function (jqXHR) {
            handleAjaxError(jqXHR);
        })
        .always(function () {
            $container.removeClass('loading');
        });
}

function renderPosts(posts) {
    const $container = $('#posts-container').empty();
    posts.forEach(function (post) {
        $container.append(
            $('<div class="post-card">').html(
                `<h3>${post.title}</h3><p>${post.excerpt}</p>`
            )
        );
    });
}
```

### 2. POST / PUT / DELETE

```javascript
// POST（JSON）
function createPost(data) {
    return $.ajax({
        url: '/api/posts',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(data)
    });
}

// DELETE（Laravel の route model binding 対応）
function deletePost(id) {
    return $.ajax({
        url: `/api/posts/${id}`,
        method: 'DELETE'
    });
}

// 使い方
deletePost(postId)
    .done(function () {
        $(`[data-post-id="${postId}"]`).closest('.post-card').fadeOut(300, function () {
            $(this).remove();
        });
        showToast('削除しました', 'success');
    })
    .fail(handleAjaxError);
```

### 3. ファイルアップロード

```javascript
$('#upload-form').on('submit', function (e) {
    e.preventDefault();
    const formData = new FormData(this);

    $.ajax({
        url: '/api/upload',
        method: 'POST',
        data: formData,
        processData: false,   // FormData を変換しない
        contentType: false,   // multipart/form-data を自動設定
        xhr: function () {
            const xhr = new XMLHttpRequest();
            xhr.upload.addEventListener('progress', function (e) {
                if (e.lengthComputable) {
                    const pct = Math.round((e.loaded / e.total) * 100);
                    $('#upload-progress').val(pct);
                }
            });
            return xhr;
        },
        success: function (res) {
            showToast('アップロード完了', 'success');
        },
        error: handleAjaxError
    });
});
```

### 4. 無限スクロール / もっと見るボタン

```javascript
let currentPage = 1;
let isLoading = false;
let hasMore = true;

$('#load-more-btn').on('click', function () {
    if (isLoading || !hasMore) return;
    loadMore();
});

function loadMore() {
    isLoading = true;
    $('#load-more-btn').text('読み込み中...');

    $.get('/api/posts', { page: ++currentPage })
        .done(function (data) {
            appendPosts(data.posts);
            hasMore = data.meta.has_more;
            if (!hasMore) $('#load-more-btn').hide();
        })
        .fail(handleAjaxError)
        .always(function () {
            isLoading = false;
            $('#load-more-btn').text('もっと見る');
        });
}
```

---

## エラーハンドリング共通関数

```javascript
function handleAjaxError(jqXHR, $form) {
    const status = jqXHR.status;
    const data = jqXHR.responseJSON;

    if (status === 422 && data && data.errors) {
        // Laravel バリデーションエラー
        clearFormErrors($form);
        Object.entries(data.errors).forEach(function ([field, messages]) {
            const $input = $form ? $form.find(`[name="${field}"]`) : $(`[name="${field}"]`);
            $input.addClass('is-invalid');
            $input.after(`<div class="invalid-feedback">${messages[0]}</div>`);
        });
    } else if (status === 401) {
        window.location.href = '/login';
    } else if (status === 403) {
        showToast('権限がありません', 'error');
    } else if (status === 404) {
        showToast('データが見つかりません', 'error');
    } else {
        showToast('エラーが発生しました。再度お試しください。', 'error');
        console.error('AJAX Error:', status, data);
    }
}

function clearFormErrors($form) {
    if (!$form) return;
    $form.find('.is-invalid').removeClass('is-invalid');
    $form.find('.invalid-feedback').remove();
}

// トースト通知（Bootstrap 5 対応）
function showToast(message, type = 'info') {
    const $toast = $(`
        <div class="toast align-items-center text-white bg-${type === 'success' ? 'success' : 'danger'} border-0" role="alert">
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `);
    $('#toast-container').append($toast);
    const bsToast = new bootstrap.Toast($toast[0], { delay: 3000 });
    bsToast.show();
    $toast.on('hidden.bs.toast', function () { $(this).remove(); });
}
```

---

## よくある実装チェックリスト

### AJAX 実装前確認

- [ ] `$.ajaxSetup` で CSRF ヘッダー設定済み
- [ ] ローディング状態（ボタン無効化・スピナー）を実装
- [ ] `.done()` / `.fail()` / `.always()` を揃える
- [ ] Laravel 側のレスポンスが JSON 形式

### アニメーション実装前確認

- [ ] `.stop(true, true)` で競合防止（連打対策）
- [ ] 重いアニメーションは CSS トランジションへ移行を検討
- [ ] `prefers-reduced-motion` メディアクエリ対応を検討

### イベント実装前確認

- [ ] 動的要素には委譲（`.on('event', 'selector', handler)`）を使用
- [ ] イベント名に名前空間（`.modal`, `.accordion` 等）を付与
- [ ] scroll/resize イベントは throttle/debounce で抑制
