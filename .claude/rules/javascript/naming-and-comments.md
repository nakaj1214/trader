---
paths:
  - "**/*.js"
  - "**/*.ts"
---

# JavaScript 命名規則・コメント規約

このプロジェクトのコードから抽出した、JavaScript / jQuery の命名規則とコメントスタイル。

---

## 命名規則

### 変数・関数名: `snake_case`

> **このプロジェクトの特徴**: JavaScript でも snake_case を使う（通常の camelCase ではない）。
> PHP / Laravel 側との一貫性を保つための選択。

```javascript
// ✅ このプロジェクトのスタイル（snake_case）
let measure_value = [];
let select_factory_id = $('#factory_id').val();
let eq_masta_id = $(this).attr('id').split("area_select_")[1];

function ajax_get_area(number_id, eq_masta_id) { ... }
function restore_chart_settings(eq_id) { ... }
function clear_area_option(eq_masta_id) { ... }

// ❌ 混在させない（camelCase）
let measureValue = [];
function getAreaData(numberId) { ... }
```

### 定数: `UPPER_SNAKE_CASE`

```javascript
// ✅ 定数は大文字スネークケース
const STORAGE_KEY_PREFIX = 'chart_settings_';
const MAX_RETRY_COUNT = 3;
const API_BASE_URL = '/ajax/';
```

### グローバル変数: ファイル先頭にまとめて宣言

```javascript
// ✅ グローバル変数はファイル冒頭にまとめる
let measure_value = [];        // グラフデータの値
let measure_date = [];         // グラフデータの日時
let charts = {};               // 設備ごとのグラフインスタンス
let active_eq_id;              // 現在表示している設備タブのid

const STORAGE_KEY_PREFIX = 'chart_settings_';  // LocalStorageキーのプレフィックス
```

### jQuery セレクタ変数: `$` プレフィックス

```javascript
// ✅ jQuery オブジェクトは $ プレフィックスで区別する
const $form = $('#device-form');
const $submitBtn = $form.find('[type="submit"]');
let $activeTab = $('.tab.active');

// ❌ $ なしだと jQuery オブジェクトか不明
const form = $('#device-form');
```

### 動的セレクタ: テンプレートリテラル

```javascript
// ✅ ID に変数を含む場合はテンプレートリテラルを使う
$(`#number_select_${eq_id}`).append(option);
$(`#area_select_${eq_masta_id}`).val();
flatpickr(`#start_date_${eq_id}`, options);
```

### AJAX 関数名: 目的を明示

```javascript
// ✅ 汎用 ajax 関数: ajax(引数)
function ajax(factory_id) { ... }

// ✅ 目的を示す名前: ajax_{動詞}_{対象}
function ajax_get_area(number_id, eq_masta_id) { ... }
function ajax_get_area_data(area_id, eq_masta_id) { ... }
function ajax_save_settings(eq_id, data) { ... }
```

---

## コメント規約

### 1. 変数宣言の右側インラインコメント

変数の意味を揃えて記述する。複数行ある場合は **位置を揃える**。

```javascript
// ✅ 位置を揃えたインラインコメント
let measure_value = [];         // グラフデータの値
let measure_date = [];          // グラフデータの日時
let measure_count = [];         // グラフのx軸用のラベル
let step_size = 0.005;          // y軸の間隔の初期値
let area_data;                  // 選択した計測箇所をグローバルに格納
let charts = {};                // 設備ごとのグラフインスタンス
let color_map = {};             // ワークごとのグラフ色
let active_eq_id;               // 現在表示している設備タブのid
```

処理中の変数にも同様に:

```javascript
let eq_masta_id = $(this).attr('id').split("area_select_")[1];  // 選択されている設備マスタid
let area_id     = $(`#area_select_${eq_masta_id}`).val();       // 選択された計測箇所id
let area_text   = $(`#area_select_${eq_masta_id} option:selected`).text(); // 計測箇所のテキスト
```

### 2. 処理ブロック前のコメント: 「〜したら」「〜のとき」

イベントハンドラーや処理のまとまりの前に **1行で目的を説明** する。

```javascript
// ✅ イベントの条件をコメントで示す
// 工場を選んだら
$('#factory_id').change(function() { ... });

// 品番のセレクトボックス要素が変わったとき
$(document).on('change', '.number_select', function() { ... });

// 設備タブのクリックイベント
$('.tab').on('click', function() { ... });

// 印刷ボタンが押されたとき
$(document).on('click', '.print_btn', async function() { ... });
```

### 3. 処理の目的コメント: 「〜する」「〜を取得する」

処理の **目的・理由** を説明する（何をするかではなく、なぜするか）。

```javascript
// ✅ 目的を説明するコメント
// 工場を選択するたびに部署のoptionタグを初期化する
$("#department_id option:not(:first-child)").remove();

// 全てのタブとコンテンツを非アクティブにする
$('.tab').removeClass('active');
$('.tab_content').removeClass('active');

// 品番が変更されたら表示しているグラフを破棄
if (charts[eq_masta_id]) {
    charts[eq_masta_id].destroy();
}

// ユーザーが日付を手動選択していない場合のみデフォルトに戻す
if (!date_user_specified) {
    calc_datetime();
}
```

### 4. セクション区切りコメント

関連する処理のグループに見出しコメントを付ける。

```javascript
// ページが読み込まれたら
$(document).ready(async function() {
    ...

    // flatpickrインスタンスを設備ごとに保存
    ...

    // LocalStorageから設定を復元して再描画
    ...

    // 設備タブのクリックイベント
    ...
});
```

### 5. コメントアウトする場合: 理由を添える

削除できない場合は **理由のコメント** をセットで残す。

```javascript
// ✅ 理由付きでコメントアウト
// ※ コメントアウト: ユーザーが任意の終了日を設定できるようにするため
// if ($(this).attr('id') == `start_date_${eq_masta_id}` && start_time) {
//     ...
// }

// date_user_specified が true の場合は現在の日付範囲を維持
```

### 6. デバッグ用 `console.log` のコメントアウト

デバッグ用ログはコミット前にコメントアウト（削除推奨）。

```javascript
// ✅ コミット前にコメントアウト（完全削除が望ましい）
// console.log("設備マスタid: " + eq_masta_id);
// console.log("計測箇所id: " + area_id);

// ❌ コミットに残さない
console.log(debug_value);
```

---

## 宣言スタイル

### `let` / `const` / `var` の使い分け

```javascript
// ✅ グローバル変数（変更あり）: let
let charts = {};
let active_eq_id;

// ✅ 定数（変更なし）: const
const STORAGE_KEY_PREFIX = 'chart_settings_';
const { ja } = flatpickr.l10ns;

// ✅ ローカル変数（変更あり）: let
let eq_masta_id = $(this).attr('id').split("_")[1];

// ❌ var は使わない（スコープが広い）
var factory_str = ...;  // 古いコードに存在するが新規追加しない
```

---

## コードレイアウト

### `$(document).ready()` の構造

```javascript
// ✅ 構造の全体像
$(document).ready(function() {
    // --- 初期化処理 ---

    // グローバル変数の初期値設定
    calc_datetime();

    // DOM 初期化（セレクトボックスの設定など）
    unique_equipment.forEach(function(eq_id) {
        // セレクトボックスの初期設定
    });

    // 設定の復元
    restore_chart_settings(eq_id);

    // --- イベントバインド ---

    // 設備タブのクリックイベント
    $('.tab').on('click', function() { ... });

    // 品番のセレクトボックス変更イベント
    $(document).on('change', '.number_select', function() { ... });

    // ボタンクリックイベント
    $(document).on('click', '.print_btn', async function() { ... });
});

// --- 関数定義（ready の外）---

function ajax_get_area(number_id, eq_masta_id) { ... }
function save_chart_settings(eq_id) { ... }
function restore_chart_settings(eq_id) { ... }
```

### AJAX 関数の構造

```javascript
function ajax_get_area_data(area_id, eq_masta_id) {
    $.ajax({
        url: '/ajax/history/get_history.php',
        type: 'POST',
        dataType: 'json',
        data: {
            area_id: area_id,
            eq_masta_id: eq_masta_id,
        },
    })
    .done(function(data) {
        // 成功時の処理
        render_chart(data, eq_masta_id);
    })
    .fail(function(jqXHR, textStatus, errorThrown) {
        // エラー時: ユーザーにアラートを表示し、コンソールにも記録
        window.alert("DB接続に失敗しました。\nシステム担当にご連絡ください。");
        console.log("Ajax 失敗");
        console.log("jqXHR : " + jqXHR);
        console.log("textStatus : " + textStatus);
        console.log("errorThrown : " + errorThrown);
    });
}
```

---

## チェックリスト

### 命名
- [ ] 変数名・関数名は `snake_case`
- [ ] 定数は `UPPER_SNAKE_CASE`
- [ ] jQuery オブジェクト変数は `$` プレフィックス
- [ ] 動的セレクタはテンプレートリテラル（`` `#element_${id}` ``）
- [ ] AJAX 関数は `ajax_{動詞}_{対象}` の形式

### コメント
- [ ] グローバル変数にインラインコメントを付ける（位置揃え）
- [ ] イベントハンドラーの前に目的コメントを付ける
- [ ] 複雑な処理には「なぜそうするか」のコメントを付ける
- [ ] コメントアウトには理由を添える
- [ ] `console.log` はコミット前にコメントアウトまたは削除

### 宣言
- [ ] `var` を使わず `let` / `const` を使う
- [ ] グローバル変数はファイル先頭にまとめて宣言
- [ ] `$(document).ready()` は1ファイルに1つ

---

> ⚠️ **注意:** このファイルはコード解析から自動生成されました。
> プロジェクト固有の要件に応じて調整してください。