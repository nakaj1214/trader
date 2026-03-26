---
paths:
  - "**/*.py"
  - "**/*.pyi"
---

# Python コーディングスタイル

適用対象: `**/*.py`, `**/*.pyi`

[共通コーディングスタイル](../../common/coding-style.md) を拡張。

## PEP 8 準拠

すべての Python コードは PEP 8 規約に従うこと。自動化ツールを使用し、スタイルの議論は不要:

```bash
black .       # 自動フォーマット
isort .       # インポートのソート
ruff check .  # リント
```

## 型アノテーション

**すべての関数シグネチャに型アノテーションを付けること:**

```python
# ❌ 悪い例
def process_user(user_id, name):
    ...

# ✅ 良い例
def process_user(user_id: int, name: str) -> dict[str, Any]:
    ...
```

## イミュータビリティ

イミュータブルなデータ構造を優先する:

```python
from dataclasses import dataclass
from typing import NamedTuple

# Frozen dataclass（複雑なオブジェクトに推奨）
@dataclass(frozen=True)
class UserRecord:
    id: int
    name: str
    email: str

# NamedTuple（シンプルな構造に推奨）
class Point(NamedTuple):
    x: float
    y: float
```

## エラーハンドリング

```python
# ❌ 悪い例 — 素の except
try:
    process()
except:
    pass

# ❌ 悪い例 — 例外の握りつぶし
try:
    process()
except Exception:
    pass

# ✅ 良い例 — 具体的な例外をキャッチしてログ出力
try:
    process()
except ValueError as e:
    logger.error("Invalid value during processing", exc_info=e)
    raise ProcessingError("Invalid input") from e
```

## ミュータブルなデフォルト引数

```python
# ❌ 悪い例 — ミュータブルなデフォルト値
def append_item(item, lst=[]):
    lst.append(item)
    return lst

# ✅ 良い例 — None をセンチネルとして使用
def append_item(item: Any, lst: list | None = None) -> list:
    if lst is None:
        lst = []
    lst.append(item)
    return lst
```

## 命名規則

- `snake_case`: 関数、メソッド、変数
- `PascalCase`: クラス
- `SCREAMING_SNAKE_CASE`: モジュールレベルの定数
- `_private`: プライベートメンバー（アンダースコア1つ）
