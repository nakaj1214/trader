# CSSコード整理 — 詳細リファレンス

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

## デザインシステム原則（LiftKit パターン）

LiftKit の設計思想に基づく、スケーリング・間隔・色のベストプラクティス。

### ゴールデンレシオスケーリング

φ（≈1.618）を基準にタイポグラフィとスペーシングを比例設計する。

```css
:root {
  --phi: 1.618;
  --base: 1rem;

  /* φベースのタイプスケール */
  --text-xs:   0.382rem;   /* base / φ² */
  --text-sm:   0.618rem;   /* base / φ  */
  --text-base: 1rem;
  --text-md:   1.618rem;   /* base × φ  */
  --text-lg:   2.618rem;   /* base × φ² */
  --text-xl:   4.236rem;   /* base × φ³ */

  /* φベースのスペーシング */
  --space-xs:  0.25rem;    /* 4px  */
  --space-sm:  0.5rem;     /* 8px  */
  --space-md:  0.75rem;    /* 12px */
  --space-base: 1rem;      /* 16px */
  --space-lg:  1.618rem;   /* ~26px — φ比 */
  --space-xl:  2.618rem;   /* ~42px — φ² */
  --space-2xl: 4.236rem;   /* ~68px — φ³ */
}
```

### 光学対称（Optical Symmetry）

等しいパディングを指定しても視覚的にズレて見える問題を補正する。

```css
/* カード: 上下同一指定でも上が重く見えるため上を 0.875 に絞る */
.card {
  padding-block: calc(var(--space-lg) * 0.875) var(--space-lg);
  padding-inline: var(--space-lg);
}

/* ボタン: アセンダーを考慮して上パディングをわずかに削る */
.button {
  padding-block: calc(var(--space-sm) * 0.9) var(--space-sm);
  padding-inline: var(--space-md);
}

/* アイコン付きボタン: アイコン分だけ左パディングを減らす */
.button--icon {
  padding-inline: calc(var(--space-sm) * 0.75) var(--space-md);
}
```

### コントラスト比（WCAG AA準拠）

色を定義するときは必ずコントラスト比を検証・コメントとして残す。

```css
:root {
  /* WCAG AA 基準
     通常テキスト(18px未満): 4.5:1 以上
     大テキスト(18px+/Bold 14px+): 3:1 以上
     UIコンポーネント・グラフィック: 3:1 以上        */

  --color-primary: #2563eb;
  --color-on-primary: #ffffff;   /* white on #2563eb = 5.9:1  ✓ AA */

  --color-surface: #ffffff;
  --color-on-surface: #111827;   /* #111827 on white = 16.8:1 ✓ AA */

  --color-muted: #6b7280;        /* on white = 4.6:1 ✓ AA（通常テキスト最小限） */

  /* NG例 */
  /* --color-light-gray-text: #9ca3af; on white = 2.9:1 ✗ AA 不適合 */
}

/* 高コントラストモードでも確実に区別できるようにボーダーを追加 */
@media (prefers-contrast: high) {
  .button { border: 2px solid currentColor; }
  .card   { border: 1px solid currentColor; }
}
```

> **ツール**: [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/) で検証してからコメントに記録する。

---

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
