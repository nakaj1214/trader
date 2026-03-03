---
name: frontend-ui-ux
description: フロントエンド開発のためのモダンUI/UX設計原則。UI設計、UX改善、フロントエンド設計判断のレビュー時に使用。
sources:
  - https://www.index.dev/blog/top-front-end-design-principles
  - https://www.keitaro.com/insights/2024/06/11/effective-ui-ux-design-principles-for-front-end-developers/
  - https://www.geeksforgeeks.org/blogs/top-ui-ux-trends-for-frontend-developers/
---

# フロントエンドUI/UXデザイン スキル

プロフェッショナルでユーザー中心のフロントエンド設計を行うための包括的ガイド。

## このスキルを使う場面

- 新しいUI設計
- 既存UI/UX実装のレビュー
- コンポーネントの設計判断
- ユーザー体験の改善
- レスポンシブレイアウト作成
- デザインシステム構築

## コア設計原則

### 1. モバイルファースト

まずモバイルを設計し、その後に大画面へ拡張する。

**実装例:**
```css
/* モバイルファースト */
.container {
  padding: 16px;
  display: flex;
  flex-direction: column;
}

/* タブレット以上 */
@media (min-width: 768px) {
  .container {
    padding: 24px;
    flex-direction: row;
  }
}

/* デスクトップ */
@media (min-width: 1024px) {
  .container {
    padding: 32px;
    max-width: 1200px;
    margin: 0 auto;
  }
}
```

**チェックリスト:**
- [ ] 小さな画面向けに簡素化したレイアウト
- [ ] タップしやすい要素（最小44x44px）
- [ ] レスポンシブなタイポグラフィ
- [ ] 大画面向けの段階的拡張

### 2. ミニマリズムと明快さ

少ないほど良い。必須要素に集中する。

**原則:**
- すべての要素に明確な目的がある
- 余白（ネガティブスペース）を十分に使う
- 認知負荷を減らす
- 明確な視覚階層を作る

**良い例:**
```jsx
// シンプルで焦点の合ったコンポーネント
function ProductCard({ title, price, image }) {
  return (
    <article className="product-card">
      <img src={image} alt={title} />
      <h3>{title}</h3>
      <p className="price">{price}</p>
      <button>Add to Cart</button>
    </article>
  );
}
```

**避けること:**
- 情報過多なUI
- 不要な装飾要素
- 競合するCTAの多用
- 情報の詰め込み

### 3. 視覚的ヒエラルキー

明確な階層でユーザーを誘導する。

**手法:**
```css
/* タイポグラフィ階層 */
h1 { font-size: 2.5rem; font-weight: 700; }
h2 { font-size: 2rem; font-weight: 600; }
h3 { font-size: 1.5rem; font-weight: 600; }
body { font-size: 1rem; font-weight: 400; }
.caption { font-size: 0.875rem; color: #666; }

/* サイズ階層 */
.primary-button { padding: 16px 32px; font-size: 1.125rem; }
.secondary-button { padding: 12px 24px; font-size: 1rem; }
.tertiary-button { padding: 8px 16px; font-size: 0.875rem; }

/* 色の階層 */
.primary { color: #2563eb; }    /* 最重要 */
.secondary { color: #64748b; }  /* 補助 */
.muted { color: #94a3b8; }      /* 優先度低 */
```

### 4. 一貫性とデザインシステム

すべてのインターフェースで一貫性を保つ。

**デザイントークン:**
```css
:root {
  /* Colors */
  --color-primary: #2563eb;
  --color-secondary: #64748b;
  --color-success: #22c55e;
  --color-error: #ef4444;
  --color-warning: #f59e0b;

  /* Spacing */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;

  /* Typography */
  --font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-size-sm: 0.875rem;
  --font-size-base: 1rem;
  --font-size-lg: 1.125rem;

  /* Border Radius */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-full: 9999px;

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.1);
  --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.1);
}
```

### 5. ユーザーフィードバックとマイクロインタラクション

ユーザー操作に対して即時フィードバックを返す。

**ローディング状態:**
```jsx
function Button({ loading, children, onClick }) {
  return (
    <button onClick={onClick} disabled={loading}>
      {loading ? (
        <span className="spinner" aria-label="Loading" />
      ) : (
        children
      )}
    </button>
  );
}
```

**ホバー/フォーカス状態:**
```css
.button {
  transition: all 0.2s ease;
}

.button:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.button:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.button:active {
  transform: translateY(0);
}
```

**成功/エラーフィードバック:**
```jsx
function FormField({ error, success }) {
  return (
    <div className={`field ${error ? 'field--error' : ''} ${success ? 'field--success' : ''}`}>
      <input type="text" />
      {error && <span className="error-message">{error}</span>}
      {success && <span className="success-message">Success</span>}
    </div>
  );
}
```

## レイアウトパターン

### カードレイアウト
```css
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--space-lg);
}

.card {
  background: white;
  border-radius: var(--radius-lg);
  padding: var(--space-lg);
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.2s;
}

.card:hover {
  box-shadow: var(--shadow-md);
}
```

### ホーリーグレイルレイアウト
```css
.layout {
  display: grid;
  grid-template-areas:
    "header header header"
    "nav main aside"
    "footer footer footer";
  grid-template-columns: 200px 1fr 200px;
  grid-template-rows: auto 1fr auto;
  min-height: 100vh;
}

@media (max-width: 768px) {
  .layout {
    grid-template-areas:
      "header"
      "main"
      "footer";
    grid-template-columns: 1fr;
  }
}
```

## 色のガイドライン

### コントラスト比（WCAG）
- **通常テキスト**: 最低4.5:1
- **大きなテキスト（18px+）**: 最低3:1
- **UIコンポーネント**: 最低3:1

### カラーパレット構成
```css
/* Primary palette */
--primary-50: #eff6ff;
--primary-100: #dbeafe;
--primary-500: #3b82f6;  /* Main */
--primary-600: #2563eb;  /* Hover */
--primary-700: #1d4ed8;  /* Active */

/* Neutral palette */
--gray-50: #f9fafb;
--gray-100: #f3f4f6;
--gray-500: #6b7280;
--gray-900: #111827;

/* Semantic colors */
--success: #22c55e;
--error: #ef4444;
--warning: #f59e0b;
--info: #3b82f6;
```

## タイポグラフィ ガイドライン

### フォントスケール
```css
/* モジュラースケール（1.25比） */
--text-xs: 0.64rem;   /* 10.24px */
--text-sm: 0.8rem;    /* 12.8px */
--text-base: 1rem;    /* 16px */
--text-lg: 1.25rem;   /* 20px */
--text-xl: 1.563rem;  /* 25px */
--text-2xl: 1.953rem; /* 31.25px */
--text-3xl: 2.441rem; /* 39px */
```

### 行間
```css
/* 見出しは詰め気味 */
h1, h2, h3 { line-height: 1.2; }

/* 本文は読みやすく */
p, li { line-height: 1.6; }

/* 小さい文字はゆったり */
.caption { line-height: 1.8; }
```

### 可読性
- **行長**: 45〜75文字が最適
- **段落間隔**: 行高の1.5倍
- **文字間隔**: 小さな文字はやや広め

## よくあるミス（避けること）

### NG
1. フォントを使いすぎる（最大2〜3）
2. モバイルのタップサイズを無視
3. 余白の不整合を放置
4. 低コントラストの文字
5. アニメーション過多
6. ローディング/エラー状態の欠落
7. キーボード操作を無視

### OK
1. 明確な視覚的ヒエラルキーを作る
2. 一貫した余白スケールを使う
3. すべての操作にフィードバックを返す
4. 実機で検証する
5. アクセシビリティガイドラインに従う
6. セマンティックHTMLを使う
7. パフォーマンス最適化を意識する

## パフォーマンス考慮

### 画像最適化
```html
<!-- レスポンシブ画像 -->
<img
  src="image-800.jpg"
  srcset="image-400.jpg 400w, image-800.jpg 800w, image-1200.jpg 1200w"
  sizes="(max-width: 400px) 100vw, (max-width: 800px) 50vw, 33vw"
  alt="Description"
  loading="lazy"
/>
```

### Critical CSS
```html
<!-- クリティカルCSSをインライン化 -->
<style>
  /* ファーストビューのみ */
  .header { ... }
  .hero { ... }
</style>

<!-- 非クリティカルCSSを遅延 -->
<link rel="preload" href="styles.css" as="style" onload="this.onload=null;this.rel='stylesheet'">
```

## 関連スキル

- **css-modern**: モダンCSS手法と機能
- **react-patterns**: Reactコンポーネント設計パターン
- **accessibility**: Webアクセシビリティ指針
- **code-review**: 品質・セキュリティ監査
