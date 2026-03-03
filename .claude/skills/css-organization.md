---
name: css-organization
description: CSSコードの整理 - ファイル構成、BEM命名、CSS変数、アニメーション、アクセシビリティ。
---

# CSSコード整理

CSSコードを整理・保守するためのベストプラクティス。

## 使う場面

- 新規プロジェクト開始時
- CSSアーキテクチャの確立
- デザインシステムの作成
- 保守性の向上

## ファイル構成

```
styles/
  base/
    reset.css
    typography.css
    variables.css
  components/
    button.css
    card.css
    form.css
  layouts/
    grid.css
    header.css
  utilities/
    helpers.css
  main.css
```

## BEM命名規則

```css
/* Block */
.card { }

/* Element */
.card__title { }
.card__content { }
.card__footer { }

/* Modifier */
.card--featured { }
.card--compact { }
.card__title--large { }
```

### BEMの実例

```css
.button {
  padding: 0.5rem 1rem;
  border-radius: 0.25rem;
}

.button--primary {
  background: var(--color-primary);
  color: white;
}

.button--secondary {
  background: transparent;
  border: 1px solid var(--color-primary);
}

.button__icon {
  margin-right: 0.5rem;
}

.button--loading .button__icon {
  animation: spin 1s linear infinite;
}
```

## CSS変数（カスタムプロパティ）

### グローバル変数

```css
:root {
  /* 命名: category-property-variant */
  --color-primary-500: #3b82f6;
  --color-primary-600: #2563eb;
  --color-gray-100: #f3f4f6;
  --color-gray-900: #111827;

  --space-xs: 0.25rem;
  --space-sm: 0.5rem;
  --space-md: 1rem;
  --space-lg: 1.5rem;
  --space-xl: 2rem;

  --font-size-sm: 0.875rem;
  --font-size-base: 1rem;
  --font-size-lg: 1.125rem;
  --font-weight-normal: 400;
  --font-weight-bold: 700;

  --radius-sm: 0.25rem;
  --radius-md: 0.5rem;
  --radius-lg: 1rem;

  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.1);
  --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.1);
}
```

### コンポーネント単位の変数

```css
.button {
  --button-padding: var(--space-sm) var(--space-md);
  --button-radius: var(--radius-md);
  --button-bg: var(--color-primary-500);

  padding: var(--button-padding);
  border-radius: var(--button-radius);
  background: var(--button-bg);
}

.button--large {
  --button-padding: var(--space-md) var(--space-lg);
}

.button--rounded {
  --button-radius: var(--radius-lg);
}
```

### 変数でダークモード

```css
:root {
  --bg: white;
  --text: #111827;
  --border: #e5e7eb;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111827;
    --text: #f9fafb;
    --border: #374151;
  }
}

/* クラス切替の場合 */
.dark {
  --bg: #111827;
  --text: #f9fafb;
  --border: #374151;
}
```

## アニメーションとトランジション

### 滑らかなトランジション

```css
/* 変化するプロパティを明示 */
.button {
  transition: background-color 0.2s ease, transform 0.2s ease;
}

.button:hover {
  transform: translateY(-1px);
}

.button:active {
  transform: translateY(0);
}
```

### CSSアニメーション

```css
@keyframes fade-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-in {
  animation: fade-in 0.3s ease-out forwards;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.spinner {
  animation: spin 1s linear infinite;
}
```

### ユーザー設定を尊重

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

## アクセシビリティ

### フォーカススタイル

```css
/* キーボード利用者向けに見えるフォーカス */
:focus-visible {
  outline: 2px solid var(--color-primary-500);
  outline-offset: 2px;
}

/* カスタムスタイルがある場合のみデフォルトを消す */
:focus:not(:focus-visible) {
  outline: none;
}

/* 高コントラスト時のフォーカス */
@media (prefers-contrast: high) {
  :focus-visible {
    outline-width: 3px;
  }
}
```

### 高コントラストモード

```css
@media (prefers-contrast: high) {
  .button {
    border: 2px solid currentColor;
  }

  .card {
    border: 1px solid currentColor;
  }
}
```

### 低減モーション

```css
@media (prefers-reduced-motion: reduce) {
  .carousel {
    scroll-behavior: auto;
  }

  .modal {
    transition: none;
  }

  .skeleton {
    animation: none;
    background: var(--gray-200);
  }
}
```

## パフォーマンス

### 効率的なセレクタ

```css
/* OK: シンプルなクラスセレクタ */
.nav-link { }
.card-title { }
.button-primary { }

/* NG: 過度に詳細なセレクタ */
header nav ul li a { }
div.container > div.row > div.col { }
#header .nav .link { }
```

### content-visibility

```css
/* 画面外コンテンツの描画を遅延 */
.below-fold-section {
  content-visibility: auto;
  contain-intrinsic-size: 500px;
}
```

### Critical CSSパターン

```html
<!-- クリティカルCSSをインライン化 -->
<style>
  /* ファーストビューのみ */
  .header, .hero, .nav { /* ... */ }
</style>

<!-- 非クリティカルCSSを遅延 -->
<link rel="preload" href="styles.css" as="style" onload="this.rel='stylesheet'">
<noscript><link rel="stylesheet" href="styles.css"></noscript>
```

## 関連スキル

- [css-features](css-features.md): モダンCSS機能
- [css-layout](css-layout.md): レイアウト技法
