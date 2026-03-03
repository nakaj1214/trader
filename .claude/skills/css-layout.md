---
name: css-layout
description: CSSレイアウト技法 - Grid、Flexbox、レスポンシブ設計パターン。
---

# CSSレイアウト技法

CSS GridとFlexboxを使ったモダンなレイアウトパターン。

## 使う場面

- ページレイアウトの構築
- レスポンシブデザインの作成
- コンポーネント配置
- 流体タイポグラフィ

## CSS Grid

### Auto-fitレスポンシブグリッド

```css
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.5rem;
}
```

### 名前付きグリッドエリア

```css
.layout {
  display: grid;
  grid-template-areas:
    "header header"
    "sidebar main"
    "footer footer";
  grid-template-columns: 250px 1fr;
  grid-template-rows: auto 1fr auto;
  min-height: 100vh;
}

.header { grid-area: header; }
.sidebar { grid-area: sidebar; }
.main { grid-area: main; }
.footer { grid-area: footer; }
```

### Subgrid

```css
.card-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
}

.card {
  display: grid;
  grid-template-rows: subgrid;
  grid-row: span 3; /* header, content, footer */
}

.card-header { /* 全カードで整列 */ }
.card-content { /* 全カードで整列 */ }
.card-footer { /* 全カードで整列 */ }
```

### グリッドの整列

```css
.grid-container {
  display: grid;
  place-items: center;  /* 両軸センター */

  /* 個別指定 */
  justify-items: start;  /* 水平方向 */
  align-items: center;   /* 垂直方向 */
}
```

## Flexbox

### よく使うパターン

```css
/* 中央寄せ */
.flex-center {
  display: flex;
  justify-content: center;
  align-items: center;
}

/* 間隔を空ける */
.flex-between {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 縦並び */
.flex-column {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
```

### マージンではなくgap

```css
.flex-row {
  display: flex;
  gap: 1rem;  /* マージンの小細工不要 */
}
```

### 最小サイズを保ったwrap

```css
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.tag {
  flex: 0 0 auto;  /* 伸縮しない */
}
```

### スティッキーフッター

```css
.page {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.main {
  flex: 1;  /* 残りスペースを占有 */
}

.footer {
  flex-shrink: 0;  /* 縮まない */
}
```

## レスポンシブデザイン

### 流体タイポグラフィ

```css
/* clamp()で流体サイズ */
h1 {
  font-size: clamp(1.5rem, 4vw + 1rem, 3rem);
}

p {
  font-size: clamp(1rem, 2vw + 0.5rem, 1.25rem);
}

/* 流体スペーシング */
.section {
  padding: clamp(2rem, 5vw, 4rem);
}
```

### コンテナ基準のブレークポイント

```css
/* ビューポートよりコンテナクエリ優先 */
.component-container {
  container-type: inline-size;
}

@container (min-width: 400px) {
  .component {
    flex-direction: row;
  }
}

@container (min-width: 600px) {
  .component {
    grid-template-columns: 1fr 1fr;
  }
}
```

### モバイルファーストのメディアクエリ

```css
/* モバイルのベーススタイル */
.nav {
  flex-direction: column;
}

/* タブレット以上 */
@media (min-width: 768px) {
  .nav {
    flex-direction: row;
  }
}

/* デスクトップ */
@media (min-width: 1024px) {
  .nav {
    gap: 2rem;
  }
}
```

## よく使うパターン

### アスペクト比

```css
.video-container {
  aspect-ratio: 16 / 9;
}

.avatar {
  aspect-ratio: 1;
  border-radius: 50%;
}

.card-image {
  aspect-ratio: 4 / 3;
  object-fit: cover;
}
```

### 省略表示

```css
/* 1行 */
.truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 複数行 */
.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
```

### スティッキー要素

```css
.sticky-header {
  position: sticky;
  top: 0;
  z-index: 100;
  backdrop-filter: blur(8px);
  background: rgba(255, 255, 255, 0.9);
}

.sticky-sidebar {
  position: sticky;
  top: 4rem;  /* ヘッダーの下 */
  height: fit-content;
}
```

### フルブリードレイアウト

```css
.wrapper {
  display: grid;
  grid-template-columns:
    1fr
    min(65ch, 100% - 2rem)
    1fr;
}

.wrapper > * {
  grid-column: 2;
}

.full-bleed {
  grid-column: 1 / -1;
  width: 100%;
}
```

## 関連スキル

- [css-features](css-features.md): モダンCSS機能
- [css-organization](css-organization.md): コード整理
