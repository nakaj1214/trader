---
name: css-modern
description: 2024+向けのモダンCSS手法とベストプラクティス。詳細パターンは関連スキル参照。
sources:
  - https://frontendmasters.com/blog/what-you-need-to-know-about-modern-css-spring-2024-edition/
  - https://developer.mozilla.org/en-US/docs/Learn/CSS/Building_blocks/Organizing
---

# モダンCSS スキル

モダンCSSの手法・機能・ベストプラクティスをまとめた包括的ガイド。

## このスキルを使う場面

- 新しいスタイルシートの作成
- レガシーCSSのリファクタ
- レスポンシブデザインの実装
- CSSパフォーマンスの最適化
- デザインシステムの構築

## クイックリファレンス

このスキルは以下のサブスキルに分割:

| スキル | 説明 |
|-------|-------------|
| [css-features](css-features.md) | ネイティブネスト、コンテナクエリ、:has()、@layer、モダンな色 |
| [css-layout](css-layout.md) | Grid、Flexbox、レスポンシブパターン |
| [css-organization](css-organization.md) | ファイル構成、BEM、CSS変数、アニメーション、アクセシビリティ |

## 必須機能（2024+）

### ネイティブCSSネスト

```css
.card {
  padding: 1rem;

  & .title { font-size: 1.5rem; }
  &:hover { box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); }
}
```

### コンテナクエリ

```css
.container { container-type: inline-size; }

@container (min-width: 400px) {
  .card { display: grid; }
}
```

### :has() セレクタ

```css
.form-group:has(input:invalid) { border-color: red; }
.card:has(img) { grid-template-rows: 200px 1fr; }
```

### CSSレイヤー

```css
@layer reset, base, components, utilities;

@layer utilities {
  .hidden { display: none !important; }
}
```

## レイアウト クイックリファレンス

### Grid

```css
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.5rem;
}
```

### Flexbox

```css
.flex-center {
  display: flex;
  justify-content: center;
  align-items: center;
}
```

### 流体タイポグラフィ

```css
h1 { font-size: clamp(1.5rem, 4vw + 1rem, 3rem); }
```

## CSS変数

```css
:root {
  --color-primary: #3b82f6;
  --space-md: 1rem;
  --radius-md: 0.5rem;
}

.button {
  background: var(--color-primary);
  padding: var(--space-md);
  border-radius: var(--radius-md);
}
```

## 関連スキル

- [css-features](css-features.md): モダンCSS機能
- [css-layout](css-layout.md): レイアウト技法
- [css-organization](css-organization.md): コード整理
- [react-patterns](react-patterns.md): Reactコンポーネントパターン
