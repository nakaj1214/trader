---
paths:
  - "**/*.py"
  - "**/tests/**"
  - "**/test_*.py"
---

# テストルール

テストを書くためのガイドライン。

## 基本原則

- **TDD 推奨**: テストを先に書く
- **カバレッジ目標**: 80% 以上
- **実行速度**: ユニットテストは高速であること（1テストあたり 100ms 以下）

## テスト構造

### AAA パターン

```python
def test_user_creation():
    # Arrange（準備）
    user_data = {"name": "Alice", "email": "alice@example.com"}

    # Act（実行）
    user = create_user(user_data)

    # Assert（検証）
    assert user.name == "Alice"
    assert user.email == "alice@example.com"
```

### 命名規則

```python
# test_{対象}_{条件}_{期待結果}
def test_create_user_with_valid_data_returns_user():
    ...

def test_create_user_with_invalid_email_raises_error():
    ...
```

## テストケースのカバレッジ

各機能について以下を検討する:

1. **正常系**: 基本的な機能
2. **境界値**: 最小値、最大値、空
3. **エラーケース**: 不正な入力、エラー条件
4. **エッジケース**: None、空文字列、特殊文字

## モック

外部依存関係をモック化する:

```python
from unittest.mock import Mock, patch

@patch("module.external_api_call")
def test_with_mocked_api(mock_api):
    mock_api.return_value = {"status": "ok"}
    result = function_under_test()
    assert result == expected
```

## フィクスチャ

共通のセットアップは `conftest.py` に記述する:

```python
# tests/conftest.py
import pytest

@pytest.fixture
def sample_user():
    return User(name="Test", email="test@example.com")

@pytest.fixture
def db_session():
    session = create_session()
    yield session
    session.rollback()
```

## コマンド

```bash
# 全テスト実行
uv run pytest -v

# 特定のファイル
uv run pytest tests/test_user.py -v

# 特定のテスト
uv run pytest tests/test_user.py::test_create_user -v

# カバレッジ付き
uv run pytest --cov=src --cov-report=term-missing

# 最初の失敗で停止
uv run pytest -x
```

## チェックリスト

- [ ] 正常系がテストされている
- [ ] エラーケースがテストされている
- [ ] 境界値がテストされている
- [ ] テストが独立している（順序依存がない）
- [ ] 外部依存関係がモック化されている
- [ ] テストが高速に実行される
