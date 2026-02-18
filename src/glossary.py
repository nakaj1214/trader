"""株式用語ヘルプ機能

- CLI用語検索: python -m src.glossary RSI
- レポート埋め込み: annotate_text() で専門用語に解説を追加
- beginner_mode 用の用語メモ生成
"""

import sys
from pathlib import Path

import yaml

from src.utils import DATA_DIR

GLOSSARY_PATH = DATA_DIR / "glossary.yaml"


def load_glossary() -> dict:
    """glossary.yaml を読み込む。"""
    with open(GLOSSARY_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("terms", {})


def lookup(term: str) -> dict | None:
    """用語を検索して {short, detail} を返す。見つからなければ None。"""
    glossary = load_glossary()
    # 完全一致
    if term in glossary:
        return glossary[term]
    # 大文字小文字を無視して検索
    for key, value in glossary.items():
        if key.lower() == term.lower():
            return value
    return None


def get_annotations(terms: list[str]) -> list[str]:
    """指定された用語リストの短い解説を返す (beginner_mode用)。

    Returns:
        ["RSI = 70以上=買われすぎ、30以下=売られすぎ", ...] 形式のリスト
    """
    glossary = load_glossary()
    annotations = []
    for term in terms:
        entry = None
        if term in glossary:
            entry = glossary[term]
        else:
            for key, value in glossary.items():
                if key.lower() == term.lower():
                    entry = value
                    break
        if entry:
            annotations.append(f"{term} = {entry['short']}")
    return annotations


def generate_beginner_notes() -> str:
    """beginner_mode 用の用語メモブロックを生成する。"""
    # レポートで頻出する主要用語
    key_terms = ["予測上昇率", "信頼区間", "RSI", "MACD", "出来高", "時価総額"]
    annotations = get_annotations(key_terms)
    if not annotations:
        return ""
    lines = ["用語メモ:"]
    for ann in annotations:
        lines.append(f"  ・{ann}")
    return "\n".join(lines)


# CLI エントリポイント: python -m src.glossary <term>
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python -m src.glossary <用語>")
        print("例: python -m src.glossary RSI")
        print("\n登録済み用語一覧:")
        glossary = load_glossary()
        for key in sorted(glossary.keys()):
            print(f"  {key}: {glossary[key]['short']}")
        sys.exit(0)

    query = " ".join(sys.argv[1:])
    result = lookup(query)
    if result:
        print(f"\n【{query}】")
        print(f"  概要: {result['short']}")
        print(f"  詳細: {result['detail']}")
    else:
        print(f"'{query}' は用語集に登録されていません。")
        print("登録済み用語を確認するには引数なしで実行してください。")
