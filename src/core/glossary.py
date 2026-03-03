"""Stock glossary loader and lookup utilities.

Reads term definitions from data/glossary.yaml and provides
lookup, annotation, and beginner-mode note generation.
"""

from __future__ import annotations

from pathlib import Path

import yaml
import structlog

from src.core.config import ROOT_DIR

logger = structlog.get_logger(__name__)

GLOSSARY_PATH: Path = ROOT_DIR / "data" / "glossary.yaml"


def get_glossary() -> dict[str, dict]:
    """Load glossary terms from YAML.

    Returns:
        Mapping of term name to {short, detail} dict.
        Returns an empty dict if the file is missing or malformed.
    """
    if not GLOSSARY_PATH.exists():
        logger.warning("glossary_file_not_found", path=str(GLOSSARY_PATH))
        return {}
    try:
        with open(GLOSSARY_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("terms", {}) if isinstance(data, dict) else {}
    except Exception:
        logger.warning("glossary_load_failed", path=str(GLOSSARY_PATH), exc_info=True)
        return {}


def lookup(term: str) -> dict | None:
    """Look up a single term (case-insensitive).

    Returns:
        The {short, detail} dict, or None if not found.
    """
    glossary = get_glossary()
    if term in glossary:
        return glossary[term]
    for key, value in glossary.items():
        if key.lower() == term.lower():
            return value
    return None


def get_annotations(terms: list[str]) -> list[str]:
    """Return short annotations for the given terms (beginner_mode).

    Returns:
        List of strings like "RSI = 70以上=買われすぎ、30以下=売られすぎ".
    """
    glossary = get_glossary()
    annotations: list[str] = []
    for term in terms:
        entry = glossary.get(term)
        if entry is None:
            for key, value in glossary.items():
                if key.lower() == term.lower():
                    entry = value
                    break
        if entry:
            annotations.append(f"{term} = {entry['short']}")
    return annotations


def format_glossary_for_report(terms: list[str]) -> str:
    """Generate a beginner-mode glossary block for reports.

    Args:
        terms: List of term names to include.

    Returns:
        Formatted multi-line string, or empty string if no terms found.
    """
    annotations = get_annotations(terms)
    if not annotations:
        return ""
    lines = ["用語メモ:"]
    for ann in annotations:
        lines.append(f"  ・{ann}")
    return "\n".join(lines)
