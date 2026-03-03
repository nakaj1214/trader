---
name: accessibility
description: WCAGガイドラインに沿ったWebアクセシビリティ（a11y）のベストプラクティス。アクセシブルなUI構築、アクセシビリティレビュー、インクルーシブデザイン実装時に使用。
sources:
  - https://www.w3.org/WAI/WCAG21/quickref/
  - https://developer.mozilla.org/en-US/docs/Web/Accessibility
  - https://www.a11yproject.com/checklist/
  - https://webaim.org/resources/contrastchecker/
---

# Webアクセシビリティ スキル

WCAG 2.1ガイドラインに沿ってアクセシブルなWebアプリケーションを構築するための包括的なガイド。

## このスキルを使う場面

- 新しいUIコンポーネントの作成
- アクセシビリティ観点のコードレビュー
- フォームやインタラクティブ要素の実装
- ナビゲーションシステムの作成
- メディアコンテンツの追加
- アクセシビリティ準拠のテスト

## WCAGの原則（POUR）

### 1. Perceivable（知覚可能）
情報はユーザーが知覚できる形で提示されなければならない。

### 2. Operable（操作可能）
UIコンポーネントはすべてのユーザーが操作できなければならない。

### 3. Understandable（理解可能）
情報とUIの操作は理解可能でなければならない。

### 4. Robust（堅牢）
コンテンツは支援技術でも動作するだけの堅牢性が必要。

## セマンティックHTML

### ドキュメント構造

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Page Title - Site Name</title>
</head>
<body>
  <header role="banner">
    <nav aria-label="Main navigation">
      <!-- Navigation -->
    </nav>
  </header>

  <main id="main-content">
    <h1>Page Title</h1>
    <article>
      <h2>Section Title</h2>
      <p>Content...</p>
    </article>
  </main>

  <aside aria-label="Related content">
    <!-- Sidebar -->
  </aside>

  <footer role="contentinfo">
    <!-- Footer -->
  </footer>
</body>
</html>
```

### 見出し階層

```html
<!-- OK: 論理的な階層 -->
<h1>Main Title</h1>
  <h2>Section A</h2>
    <h3>Subsection A.1</h3>
    <h3>Subsection A.2</h3>
  <h2>Section B</h2>
    <h3>Subsection B.1</h3>

<!-- NG: レベルの飛び越し -->
<h1>Main Title</h1>
  <h3>Subsection</h3>  <!-- h2を飛ばしている -->
  <h4>Sub-subsection</h4>
```

### リスト

```html
<!-- 順序なしリスト -->
<ul>
  <li>Item one</li>
  <li>Item two</li>
</ul>

<!-- 順序ありリスト -->
<ol>
  <li>Step one</li>
  <li>Step two</li>
</ol>

<!-- 説明リスト -->
<dl>
  <dt>Term</dt>
  <dd>Definition</dd>
</dl>
```

## ARIA（Accessible Rich Internet Applications）

### ARIAロール

```html
<!-- ランドマークロール -->
<div role="banner">Header</div>
<div role="navigation">Nav</div>
<div role="main">Main content</div>
<div role="complementary">Sidebar</div>
<div role="contentinfo">Footer</div>

<!-- ウィジェットロール -->
<div role="button" tabindex="0">Click me</div>
<div role="dialog" aria-modal="true">Modal content</div>
<div role="alert">Error message</div>
<div role="status">Status update</div>
```

### ARIAの状態とプロパティ

```html
<!-- 展開/折りたたみ -->
<button aria-expanded="false" aria-controls="menu">Menu</button>
<ul id="menu" hidden>...</ul>

<!-- 選択状態 -->
<li role="option" aria-selected="true">Selected option</li>

<!-- 無効状態 -->
<button aria-disabled="true">Submit</button>

<!-- 読み込み中 -->
<div aria-busy="true" aria-live="polite">Loading...</div>

<!-- 入力エラー -->
<input aria-invalid="true" aria-describedby="error-msg">
<span id="error-msg">This field is required</span>
```

### ライブリージョン

```html
<!-- Polite: ユーザーが操作していないタイミングで通知 -->
<div aria-live="polite" aria-atomic="true">
  Status update: 5 items in cart
</div>

<!-- Assertive: 即時に通知 -->
<div role="alert" aria-live="assertive">
  Error: Form submission failed
</div>

<!-- Status: 暗黙のpoliteライブリージョン -->
<div role="status">
  Search results updated
</div>
```

## キーボードアクセシビリティ

### フォーカス管理

```css
/* 見えるフォーカスインジケータ */
:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

/* カスタムスタイルがある場合のみデフォルトを消す */
:focus:not(:focus-visible) {
  outline: none;
}

/* フォーカスを完全に消さない */
/* NG: *:focus { outline: none; } */
```

### タブ順序

```html
<!-- 自然なタブ順（推奨） -->
<button>First</button>
<button>Second</button>
<button>Third</button>

<!-- カスタムタブ順（最小限に） -->
<button tabindex="2">Second</button>
<button tabindex="1">First</button>
<button tabindex="3">Third</button>

<!-- タブ順から除外 -->
<div tabindex="-1">Programmatically focusable only</div>

<!-- 非インタラクティブ要素をフォーカス可能に -->
<div role="button" tabindex="0">Custom button</div>
```

### キーボード操作

```tsx
function CustomButton({ onClick, children }: Props) {
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick();
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={handleKeyDown}
    >
      {children}
    </div>
  );
}
```

### スキップリンク

```html
<body>
  <a href="#main-content" class="skip-link">
    Skip to main content
  </a>
  <header>...</header>
  <main id="main-content" tabindex="-1">
    <!-- Main content -->
  </main>
</body>
```

```css
.skip-link {
  position: absolute;
  top: -40px;
  left: 0;
  padding: 8px;
  background: #000;
  color: #fff;
  z-index: 100;
}

.skip-link:focus {
  top: 0;
}
```

## フォーム

### ラベル

```html
<!-- 明示的ラベル（推奨） -->
<label for="email">Email address</label>
<input type="email" id="email" name="email">

<!-- 暗黙的ラベル -->
<label>
  Email address
  <input type="email" name="email">
</label>

<!-- アイコンボタン用のaria-label -->
<button aria-label="Close modal">
  <svg>...</svg>
</button>

<!-- 複合ラベル用のaria-labelledby -->
<h2 id="form-title">Contact Form</h2>
<form aria-labelledby="form-title">...</form>
```

### エラーハンドリング

```html
<div class="form-group">
  <label for="email">Email *</label>
  <input
    type="email"
    id="email"
    aria-required="true"
    aria-invalid="true"
    aria-describedby="email-error email-hint"
  >
  <span id="email-hint" class="hint">
    We'll never share your email.
  </span>
  <span id="email-error" class="error" role="alert">
    Please enter a valid email address.
  </span>
</div>
```

### フォームグループ

```html
<fieldset>
  <legend>Shipping Address</legend>

  <label for="street">Street</label>
  <input type="text" id="street" name="street">

  <label for="city">City</label>
  <input type="text" id="city" name="city">
</fieldset>

<!-- ラジオグループ -->
<fieldset>
  <legend>Preferred contact method</legend>

  <input type="radio" id="email-opt" name="contact" value="email">
  <label for="email-opt">Email</label>

  <input type="radio" id="phone-opt" name="contact" value="phone">
  <label for="phone-opt">Phone</label>
</fieldset>
```

## 画像とメディア

### 画像

```html
<!-- 情報的な画像 -->
<img src="chart.png" alt="Q4で20%成長を示す売上チャート">

<!-- 装飾的な画像 -->
<img src="decoration.png" alt="" role="presentation">

<!-- 複雑な画像 -->
<figure>
  <img src="infographic.png" alt="組織構造の概要">
  <figcaption>
    組織構造の詳細説明...
  </figcaption>
</figure>

<!-- 拡張説明付きの画像 -->
<img src="complex-chart.png" alt="四半期売上データ" aria-describedby="chart-desc">
<div id="chart-desc" class="visually-hidden">
  Q1: $100k, Q2: $150k, Q3: $200k, Q4: $250k...
</div>
```

### 動画

```html
<video controls>
  <source src="video.mp4" type="video/mp4">
  <!-- 字幕 -->
  <track kind="captions" src="captions.vtt" srclang="en" label="English">
  <!-- 音声解説 -->
  <track kind="descriptions" src="descriptions.vtt" srclang="en">
  <!-- 文字起こしリンク -->
  お使いのブラウザーは動画に対応していません。
  <a href="transcript.html">文字起こしを読む</a>
</video>
```

### 音声

```html
<audio controls>
  <source src="podcast.mp3" type="audio/mpeg">
  <a href="podcast.mp3">ポッドキャストをダウンロード</a>
</audio>
<a href="transcript.html">文字起こしを読む</a>
```

## 色とコントラスト

### コントラスト比（WCAG AA）

| 要素 | 最小比 |
|---------|---------------|
| 通常テキスト（18px未満） | 4.5:1 |
| 大きなテキスト（18px以上、または14px以上の太字） | 3:1 |
| UIコンポーネントとグラフィック | 3:1 |

### 色だけに頼らない

```html
<!-- NG: 色だけ -->
<span style="color: red;">Error</span>

<!-- OK: 色 + アイコン + テキスト -->
<span class="error">
  <svg aria-hidden="true"><!-- Error icon --></svg>
  Error: Invalid input
</span>
```

```css
/* リンクは色以外の差異も必要 */
a {
  color: #2563eb;
  text-decoration: underline;
}

/* 必須項目 */
.required-field::after {
  content: " *";
  color: red;
}
/* 併せて aria-required="true" を使う */
```

## インタラクティブコンポーネント

### モーダルダイアログ

```tsx
function Modal({ isOpen, onClose, title, children }: ModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      previousFocus.current = document.activeElement as HTMLElement;
      modalRef.current?.focus();
    } else {
      previousFocus.current?.focus();
    }
  }, [isOpen]);

  // モーダル内にフォーカスを閉じ込める
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    }
    if (e.key === 'Tab') {
      // フォーカストラップのロジック
    }
  };

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
      ref={modalRef}
      tabIndex={-1}
      onKeyDown={handleKeyDown}
    >
      <h2 id="modal-title">{title}</h2>
      {children}
      <button onClick={onClose}>Close</button>
    </div>
  );
}
```

### ドロップダウンメニュー

```tsx
function Dropdown({ label, items }: DropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const handleKeyDown = (e: KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setActiveIndex(prev => Math.min(prev + 1, items.length - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setActiveIndex(prev => Math.max(prev - 1, 0));
        break;
      case 'Escape':
        setIsOpen(false);
        break;
      case 'Enter':
      case ' ':
        if (activeIndex >= 0) {
          items[activeIndex].onClick();
        }
        break;
    }
  };

  return (
    <div onKeyDown={handleKeyDown}>
      <button
        aria-haspopup="true"
        aria-expanded={isOpen}
        onClick={() => setIsOpen(!isOpen)}
      >
        {label}
      </button>

      {isOpen && (
        <ul role="menu">
          {items.map((item, index) => (
            <li
              key={item.id}
              role="menuitem"
              tabIndex={index === activeIndex ? 0 : -1}
            >
              {item.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

## アクセシビリティのテスト

### 自動化ツール

```bash
# axe-core CLI
npm install -g @axe-core/cli
axe https://example.com

# Lighthouse
lighthouse https://example.com --only-categories=accessibility

# Pa11y
npm install -g pa11y
pa11y https://example.com
```

### 手動テストチェックリスト

- [ ] キーボードのみで操作できるか（Tab、Shift+Tab、Enter、Space、矢印キー）
- [ ] スクリーンリーダーでテスト（NVDA、VoiceOver、JAWS）
- [ ] 200%まで拡大しても可読性が保たれるか
- [ ] ブラウザーの開発ツールでコントラスト比を確認
- [ ] フォーカスインジケータが見えているか
- [ ] CSSなしでも論理的な読み順になっているか
- [ ] 見出し構造をブラウザー拡張で確認

### スクリーンリーダーのショートカット

| 操作 | VoiceOver（Mac） | NVDA（Windows） |
|--------|-----------------|----------------|
| 開始/停止 | Cmd + F5 | Insert + Q |
| 次の見出し | VO + Cmd + H | H |
| 見出し一覧 | VO + U | Insert + F7 |
| 次のリンク | VO + Cmd + L | K |
| ページ読み上げ | VO + A | Insert + Down Arrow |

## 便利なCSSユーティリティクラス

```css
/* 視覚的には非表示だがスクリーンリーダーには見える */
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* 動きに敏感なユーザー向けにアニメーションを減らす */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}

/* 高コントラスト対応 */
@media (prefers-contrast: high) {
  .button {
    border: 2px solid currentColor;
  }
}
```

## よくあるミス（避けること）

### NG
1. 代替なくフォーカスアウトラインを消す
2. `tabindex` を0より大きい値で使う
3. アクセシブルにすべき内容を `display: none` で隠す
4. 色だけで情報を伝える
5. キーボードトラップを作る
6. プレースホルダーをラベル代わりに使う
7. 音声付きメディアを自動再生する

### OK
1. 視認可能なフォーカスインジケータを提供する
2. セマンティックHTML要素を使う
3. 意味のある画像にaltテキストを付ける
4. 十分な色コントラストを確保する
5. キーボードとスクリーンリーダーでテストする
6. ARIAは必要なときだけ使う
7. スキップリンクを提供する

## 関連スキル

- **frontend-ui-ux**: UI/UXデザイン原則
- **css-modern**: モダンCSS手法
- **react-patterns**: Reactコンポーネントパターン
- **code-review**: コード品質とセキュリティ
