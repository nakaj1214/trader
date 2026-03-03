# Python Coding Style

Applies to: `**/*.py`, `**/*.pyi`

Extends [common coding style](../../common/coding-style.md).

## PEP 8 Compliance

All Python code must follow PEP 8 conventions. Use automated tools — no style debates:

```bash
black .       # Auto-format
isort .       # Sort imports
ruff check .  # Lint
```

## Type Annotations

**All function signatures must have type annotations:**

```python
# ❌ Bad
def process_user(user_id, name):
    ...

# ✅ Good
def process_user(user_id: int, name: str) -> dict[str, Any]:
    ...
```

## Immutability

Prefer immutable data structures:

```python
from dataclasses import dataclass
from typing import NamedTuple

# Frozen dataclass (preferred for complex objects)
@dataclass(frozen=True)
class UserRecord:
    id: int
    name: str
    email: str

# NamedTuple (preferred for simple structures)
class Point(NamedTuple):
    x: float
    y: float
```

## Error Handling

```python
# ❌ Bad — bare except
try:
    process()
except:
    pass

# ❌ Bad — swallowed exception
try:
    process()
except Exception:
    pass

# ✅ Good — specific exception with logging
try:
    process()
except ValueError as e:
    logger.error("Invalid value during processing", exc_info=e)
    raise ProcessingError("Invalid input") from e
```

## Mutable Default Arguments

```python
# ❌ Bad — mutable default
def append_item(item, lst=[]):
    lst.append(item)
    return lst

# ✅ Good — None sentinel
def append_item(item: Any, lst: list | None = None) -> list:
    if lst is None:
        lst = []
    lst.append(item)
    return lst
```

## Naming Conventions

- `snake_case` for functions, methods, variables
- `PascalCase` for classes
- `SCREAMING_SNAKE_CASE` for module-level constants
- `_private` for private members (single underscore)
