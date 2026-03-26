---
paths:
  - "**/*.py"
  - "**/*.pyi"
  - "**/pyproject.toml"
---

# 開発環境

プロジェクトの開発環境とツールチェーン。

## パッケージ管理: uv

**pip を直接使用しないこと。すべてのコマンドは uv を経由すること。**

```bash
# パッケージの追加
uv add <package>
uv add --dev <package>    # 開発用依存関係

# 依存関係の同期
uv sync

# スクリプトの実行
uv run <command>
uv run python script.py
uv run pytest
```

### pyproject.toml

`pyproject.toml` で依存関係を管理する:

```toml
[project]
dependencies = [
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.8",
]
```

## リント & フォーマット: ruff

```bash
# チェック
uv run ruff check .

# 自動修正
uv run ruff check --fix .

# フォーマット
uv run ruff format .
```

### ruff 設定 (pyproject.toml)

```toml
[tool.ruff]
target-version = "py312"
line-length = 88

[tool.ruff.lint]
select = [
    "E",      # pycodestyle エラー
    "W",      # pycodestyle 警告
    "F",      # pyflakes
    "I",      # isort
    "B",      # flake8-bugbear
    "UP",     # pyupgrade
]
ignore = ["E501"]  # 行の長さ（フォーマッターが処理）

[tool.ruff.format]
quote-style = "double"
```

## 型チェック: ty

```bash
# 型チェックの実行
uv run ty check src/
```

### ty の特徴

- Rust ベースの高速型チェッカー（Astral 製）
- ruff / uv と同じエコシステム
- mypy 互換の型アノテーション

## ノートブック: marimo

インタラクティブな Python ノートブック環境。

```bash
# ノートブックの作成/編集
uv run marimo edit notebook.py

# ノートブックの実行（CLI）
uv run marimo run notebook.py

# アプリとしてデプロイ
uv run marimo run notebook.py --host 0.0.0.0 --port 8080
```

### marimo の特徴

- **純粋な Python ファイル** (.py): Git フレンドリー
- **リアクティブ**: セル間の依存関係を自動追跡
- **再現可能**: 実行順序に依存しない

### marimo ベストプラクティス

```python
# 悪い例: グローバルステートの変更
data = []
def add_item(item):
    data.append(item)  # 副作用

# 良い例: 純粋関数
def add_item(data: list, item) -> list:
    return [*data, item]
```

## タスクランナー

`pyproject.toml` のスクリプトまたは poe で複数のツール実行を管理する:

```toml
[tool.poe.tasks]
lint = "ruff check . && ruff format --check ."
format = "ruff check --fix . && ruff format ."
typecheck = "ty check src/"
test = "pytest -v"
all = ["lint", "typecheck", "test"]
```

## よく使うコマンド

```bash
# 初期化
uv init
uv venv
source .venv/bin/activate

# 開発用依存関係のインストール
uv sync --all-extras

# 品質チェック（すべて）
uv run ruff check . && uv run ruff format --check . && uv run ty check src/ && uv run pytest

# poe 経由の場合
poe all
```

## コミット前チェックリスト

- [ ] `uv run ruff check .` が通る
- [ ] `uv run ruff format --check .` が通る
- [ ] `uv run ty check src/` が通る
- [ ] `uv run pytest` が通る
