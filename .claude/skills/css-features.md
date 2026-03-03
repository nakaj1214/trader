---
name: css-features
description: モダンCSS機能（2024+）- ネイティブネスト、コンテナクエリ、:has()、レイヤー、モダンな色関数。
---

# モダンCSS機能

2024+のブラウザーで利用できる新しいCSS機能。

## 使う場面

- モダンなスタイルシートを書く
- プリプロセッサ機能の置き換え
- レスポンシブなコンポーネント構築
- デザインシステムの作成

## CSSネスト（ネイティブ）

ネストスタイルにプリプロセッサは不要。

```css
/* ネイティブCSSネスト */
.card {
  padding: 1rem;
  background: white;

  & .title {
    font-size: 1.5rem;
    font-weight: bold;
  }

  & .content {
    color: #666;
  }

  &:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }

  @media (min-width: 768px) {
    padding: 2rem;
  }
}
```

## コンテナクエリ

ビューポートではなくコンテナサイズに応じてスタイルを適用。

```css
/* コンテナを定義 */
.card-container {
  container-type: inline-size;
  container-name: card;
}

/* コンテナ幅に基づいてスタイル */
@container card (min-width: 400px) {
  .card {
    display: grid;
    grid-template-columns: 150px 1fr;
  }
}

@container card (min-width: 600px) {
  .card {
    grid-template-columns: 200px 1fr;
  }
}

/* 省略構文 */
.sidebar {
  container: sidebar / inline-size;
}

@container sidebar (width > 300px) {
  .nav-item {
    display: flex;
    gap: 0.5rem;
  }
}
```

## :has() 疑似クラス

親セレクタ的な利用が可能。

```css
/* 子要素に基づいて親をスタイル */
.form-group:has(input:invalid) {
  border-color: red;
}

/* 画像あり/なしでカードを分岐 */
.card:has(img) {
  grid-template-rows: 200px 1fr;
}

.card:not(:has(img)) {
  padding-top: 2rem;
}

/* チェック済みでボタン有効化 */
.form:has(input[type="checkbox"]:checked) button {
  opacity: 1;
  pointer-events: auto;
}

/* 兄弟要素に基づくスタイル */
h2:has(+ p) {
  margin-bottom: 0.5rem;
}

/* 空状態のスタイリング */
.list:not(:has(li)) {
  display: flex;
  align-items: center;
  justify-content: center;
}

.list:not(:has(li))::before {
  content: 'No items';
  color: #666;
}
```

## CSSレイヤー（@layer）

カスケード順序を明示的に制御。

```css
/* レイヤーの順序を定義 */
@layer reset, base, components, utilities;

/* リセットスタイル（最優先度が低い） */
@layer reset {
  *, *::before, *::after {
    box-sizing: border-box;
    margin: 0;
  }
}

/* ベーススタイル */
@layer base {
  body {
    font-family: system-ui, sans-serif;
    line-height: 1.6;
  }
}

/* コンポーネントスタイル */
@layer components {
  .button {
    padding: 0.5rem 1rem;
    border-radius: 0.25rem;
  }
}

/* ユーティリティ（最優先度が高い） */
@layer utilities {
  .hidden { display: none !important; }
  .flex { display: flex; }
}

/* レイヤー指定のimport */
@import url('reset.css') layer(reset);
@import url('framework.css') layer(framework);
```

## モダンな色関数

### OKLCH - 知覚的に均一な色

```css
:root {
  --primary: oklch(60% 0.15 250);
  --primary-light: oklch(80% 0.1 250);
  --primary-dark: oklch(40% 0.2 250);
}
```

### color-mix() - 色のブレンド

```css
.button:hover {
  background: color-mix(in oklch, var(--primary), black 20%);
}

.button:active {
  background: color-mix(in oklch, var(--primary), black 40%);
}

/* 明度差のバリエーションを作る */
.card {
  --tint: color-mix(in srgb, var(--brand), white 80%);
  --shade: color-mix(in srgb, var(--brand), black 20%);
}
```

### 相対色構文

```css
.card {
  --base: oklch(50% 0.2 250);
  /* 明度を調整して明るくする */
  background: oklch(from var(--base) calc(l + 0.3) c h);
}

/* 彩度を下げる */
.muted {
  color: oklch(from var(--text) l calc(c * 0.5) h);
}
```

## 論理プロパティ

方向に依存しないレイアウトプロパティ。

```css
/* margin-left/rightの代わり */
.element {
  margin-inline-start: 1rem;  /* LTRなら左、RTLなら右 */
  margin-inline-end: 1rem;
  padding-block: 2rem;        /* 上下 */
  border-inline-end: 1px solid #ccc;
}

/* 論理サイズ */
.container {
  max-inline-size: 1200px;    /* 横書きではmax-width */
  min-block-size: 100vh;      /* min-height */
}

/* 論理位置指定 */
.tooltip {
  inset-block-start: 100%;    /* top */
  inset-inline-start: 0;      /* LTRでは左 */
}
```

## ビューポート単位

```css
/* 動的ビューポート単位（モバイルUIを考慮） */
.hero {
  min-height: 100dvh;  /* 動的ビューポート高さ */
}

/* Small/Largeビューポート単位 */
.sticky-header {
  height: 100svh;  /* Small viewport */
}

.full-page {
  height: 100lvh;  /* Large viewport */
}
```

## 関連スキル

- [css-layout](css-layout.md): GridとFlexboxのパターン
- [css-organization](css-organization.md): コード整理
