"""共通ユーティリティ"""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# プロジェクトルートディレクトリ
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
CONFIG_PATH = ROOT_DIR / "config.yaml"

load_dotenv(ROOT_DIR / ".env")


def load_config() -> dict:
    """config.yaml を読み込んで辞書で返す。"""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_env(key: str) -> str:
    """環境変数を取得する。未設定なら KeyError を送出。"""
    value = os.environ.get(key)
    if value is None:
        raise KeyError(f"環境変数 {key} が設定されていません。.env を確認してください。")
    return value
