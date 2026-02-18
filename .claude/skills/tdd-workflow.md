---
name: tdd-workflow
description: レッド・グリーン・リファクタのTDDワークフロー。テスト先行実装を求められるときに使用。
---

# テスト駆動開発（TDD）ワークフロー

Red-Green-Refactorのサイクルで、実装前にテストを書いて機能を実装する。

## このスキルを使う場面

- ユーザーがTDDを明示的に要求したとき
- 「テストファーストで書いて」と言われたとき
- 重要なビジネスロジック実装
- 要件が明確な機能
- テスト付きで既存コードをリファクタする場合

## TDDサイクル

### Redフェーズ: 失敗するテストを書く
1. 要件を理解する
2. 最小の失敗テストを書く
3. テスト実行して失敗を確認
4. 失敗メッセージが意味のあるものか確認

### Greenフェーズ: 通す
1. テストが通る最小コードを書く
2. 完璧さは後回し
3. テスト実行して成功を確認
4. 全テストが通ればコミット

### Refactorフェーズ: 改善する
1. 実装を整理する
2. 重複を除去する
3. 命名と構造を改善
4. テストが通ることを確認
5. リファクタ後にコミット

## ステップバイステップ

### ステップ1: 要件理解
**アクション:**
- 機能要件の明確化
- エッジケースの特定
- 成功基準の定義
- テストシナリオの列挙

**出力:**
```markdown
## Feature: [Feature Name]

**Requirements:**
- Requirement 1
- Requirement 2

**Test Scenarios:**
1. Happy path: [scenario]
2. Edge case: [scenario]
3. Error case: [scenario]
```

### ステップ2: 最初のテストを書く（Red）
**アクション:**
- テストファイルがなければ作成
- 最も簡単なテストケースから書く
- 説明的なテスト名にする
- arrange/act/assertを分ける

**例:**
```typescript
describe('UserValidator', () => {
  it('should validate email format', () => {
    // Arrange
    const validator = new UserValidator();
    const validEmail = 'user@example.com';

    // Act
    const result = validator.validateEmail(validEmail);

    // Assert
    expect(result.isValid).toBe(true);
  });
});
```

### ステップ3: テストを実行して失敗を確認
**アクション:**
- テストスイートを実行
- 正しい理由で失敗しているか確認
- エラーメッセージが明確か確認
- 予想外に通る場合は調査

**コマンド:**
```bash
npm test -- --watch
```

### ステップ4: 最小実装（Green）
**アクション:**
- テストを通す最小コードを書く
- 過剰設計しない
- テストされていない機能は追加しない
- 早すぎる最適化を避ける

**例:**
```typescript
class UserValidator {
  validateEmail(email: string): { isValid: boolean } {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return { isValid: emailRegex.test(email) };
  }
}
```

### ステップ5: テストを実行して成功を確認
**アクション:**
- テストスイートを実行
- 全テストが通るか確認
- 必要に応じてカバレッジ確認
- グリーンならコミット

### ステップ6: リファクタ（必要なら）
**アクション:**
- コード品質改善
- 重複の抽出
- 命名改善
- 必要なら最適化
- 変更ごとにテスト実行

**リファクタ例:**
```typescript
class UserValidator {
  private static readonly EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  validateEmail(email: string): ValidationResult {
    return {
      isValid: UserValidator.EMAIL_REGEX.test(email),
      errors: []
    };
  }
}
```

### ステップ7: 次のテストを追加
**アクション:**
- 次の未テストシナリオを特定
- エッジケース/エラー条件のテストを書く
- サイクルを繰り返す（Red -> Green -> Refactor）

## テスト作成ガイドライン

### 良いテストの特徴
- **速い**: ミリ秒で実行
- **独立している**: 他テストに依存しない
- **再現性がある**: いつでも同じ結果
- **自己検証**: pass/failが明確
- **タイムリー**: 実装直前に書く

### テスト構造（AAAパターン）
```typescript
it('should [expected behavior]', () => {
  // Arrange: テストデータと条件を準備
  const input = createTestData();

  // Act: 対象コードを実行
  const result = systemUnderTest.method(input);

  // Assert: 結果を検証
  expect(result).toEqual(expectedOutput);
});
```

### テスト命名規則
```typescript
// 良い: 振る舞いを説明
it('should return error when email is invalid')
it('should allow alphanumeric usernames')
it('should trim whitespace from input')

// 悪い: 実装を説明
it('tests the validateEmail function')
it('check if regex works')
```

## カバレッジ目標

### 最低ライン
- **Statements**: 80%
- **Branches**: 75%
- **Functions**: 80%
- **Lines**: 80%

### 何をテストするか
OK: **テストする**
- ビジネスロジック
- データ変換
- バリデーションルール
- エラーハンドリング
- エッジケース
- 境界条件

NG: **テストしない**
- フレームワークコード
- サードパーティライブラリ
- 些末なgetter/setter
- フレームワークのボイラープレート

## よくあるテストシナリオ

### 1. ハッピーパス
```typescript
it('should successfully create user with valid data', () => {
  const userData = { email: 'test@example.com', name: 'Test User' };
  const result = createUser(userData);
  expect(result.success).toBe(true);
});
```

### 2. エッジケース
```typescript
it('should handle empty string input', () => {
  const result = processInput('');
  expect(result).toBeNull();
});

it('should handle very long input', () => {
  const longString = 'a'.repeat(10000);
  expect(() => processInput(longString)).not.toThrow();
});
```

### 3. エラーケース
```typescript
it('should throw error when required field is missing', () => {
  expect(() => createUser({ email: '' })).toThrow('Email required');
});

it('should return validation error for invalid format', () => {
  const result = validatePhone('invalid');
  expect(result.isValid).toBe(false);
  expect(result.error).toBe('Invalid phone format');
});
```

### 4. 境界条件
```typescript
it('should accept minimum valid value', () => {
  const result = validateAge(18);
  expect(result.isValid).toBe(true);
});

it('should reject value below minimum', () => {
  const result = validateAge(17);
  expect(result.isValid).toBe(false);
});
```

## TDDワークフロー例

### 機能リクエスト
"8文字以上、数字1つ以上、特殊文字1つ以上が必要なパスワードバリデータを実装"

### テスト1: 最小長（Red）
```typescript
it('should reject password shorter than 8 characters', () => {
  const result = validatePassword('Short1!');
  expect(result.isValid).toBe(false);
  expect(result.errors).toContain('Password must be at least 8 characters');
});
```

**実行**: Fail（関数が存在しない）

### 実装1（Green）
```typescript
function validatePassword(password: string) {
  return {
    isValid: password.length >= 8,
    errors: password.length < 8 ? ['Password must be at least 8 characters'] : []
  };
}
```

**実行**: Pass

### テスト2: 数字必須（Red）
```typescript
it('should require at least one number', () => {
  const result = validatePassword('NoNumber!');
  expect(result.isValid).toBe(false);
  expect(result.errors).toContain('Password must contain at least one number');
});
```

**実行**: Fail

### 実装2（Green）
```typescript
function validatePassword(password: string) {
  const errors: string[] = [];

  if (password.length < 8) {
    errors.push('Password must be at least 8 characters');
  }

  if (!/\d/.test(password)) {
    errors.push('Password must contain at least one number');
  }

  return {
    isValid: errors.length === 0,
    errors
  };
}
```

**実行**: Pass

### 以降、要件を追加して繰り返し...

## リファクタリング手法

### メソッド抽出
```typescript
// Before
function validatePassword(password: string) {
  if (password.length < 8) { /* ... */ }
  if (!/\d/.test(password)) { /* ... */ }
  // ...
}

// After
function validatePassword(password: string) {
  const errors = [
    ...checkLength(password),
    ...checkNumber(password),
    ...checkSpecialChar(password)
  ];
  return { isValid: errors.length === 0, errors };
}
```

### 定数抽出
```typescript
// Before
if (password.length < 8) { /* ... */ }

// After
const MIN_PASSWORD_LENGTH = 8;
if (password.length < MIN_PASSWORD_LENGTH) { /* ... */ }
```

## ツールとコマンド

### テスト実行
```bash
# すべてのテストを実行
npm test

# watchモード
npm test -- --watch

# 特定ファイルのみ
npm test -- path/to/test.spec.ts

# カバレッジ計測
npm test -- --coverage
```

### カバレッジレポート
```bash
# HTMLレポート生成
npm test -- --coverage --coverageReporters=html

# ブラウザーで表示
# macOS
open coverage/index.html

# Windows
start coverage/index.html
# or: explorer coverage\\index.html

# Linux
xdg-open coverage/index.html
```

## 成功基準

- すべてのテストが通る
- カバレッジ目標（80%+）を満たす
- スキップ/保留テストがない
- テストが高速（1本100ms未満）
- テストが独立している
- 実装はテストされたコードのみ

## よくある落とし穴

1. **コード後にテストを書く**: TDDの目的が失われる
2. **実装詳細のテスト**: 内部ではなく挙動をテストする
3. **アサーション過多**: 1テスト1概念
4. **遅いテスト**: I/Oはモックで高速化
5. **リファクタを省く**: 技術的負債が増える
6. **過剰なモック**: 外部依存のみモックする

## 関連スキル

- [code-review](code-review.md): テストと品質のレビュー
- [systematic-debugging](systematic-debugging.md): 体系的な原因究明
- [writing-plans](writing-plans.md): 実装計画の作成
