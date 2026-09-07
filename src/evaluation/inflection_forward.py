"""Load immutable JP inflection snapshots into tradable forward-validation signals."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_inflection_signals(
    snapshot_dir: Path,
    *,
    classifications: tuple[str, ...] = ("EARLY_CANDIDATE",),
) -> list[dict[str, Any]]:
    """Return one immutable signal row per snapshot date/ticker.

    Snapshot filenames are the signal date. Only explicitly requested
    classifications are evaluated so WATCH/NONE rows cannot silently enter the
    trading statistics.
    """
    signals: dict[tuple[str, str], dict[str, Any]] = {}
    if not snapshot_dir.exists():
        return []

    for path in sorted(snapshot_dir.glob("????-??-??.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("mode") != "shadow":
            continue
        strategy_version = str(payload.get("strategy_version") or "")
        source_commit = str(payload.get("source_commit_sha") or "")
        schema_version = payload.get("report_schema_version")
        if not strategy_version or not source_commit or schema_version is None:
            continue

        signal_date = path.stem
        candidates = payload.get("candidates")
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            classification = str(candidate.get("classification") or "")
            ticker = str(candidate.get("ticker") or "")
            if classification not in classifications or not ticker:
                continue
            key = (signal_date, ticker)
            if key in signals:
                continue
            signals[key] = {
                "ticker": ticker,
                "signal_date": signal_date,
                "date": signal_date,
                "score": float(candidate.get("score") or 0.0),
                "classification": classification,
                "strategy_version": strategy_version,
                "report_schema_version": schema_version,
                "source_commit_sha": source_commit,
                "jquants_plan": (payload.get("data_policy") or {}).get("jquants_plan"),
                "jquants_data_delay_weeks": (payload.get("data_policy") or {}).get(
                    "jquants_data_delay_weeks"
                ),
            }

    return sorted(signals.values(), key=lambda row: (row["signal_date"], row["ticker"]))
