"""Migration script: Google Sheets -> SQLite.

Reads all prediction rows from Google Sheets and inserts them into
SQLite via PredictionRepository. Idempotent: duplicate (date, ticker)
pairs are skipped.

Usage:
    python scripts/migrate_sheets_to_db.py
    python scripts/migrate_sheets_to_db.py --dry-run
    python scripts/migrate_sheets_to_db.py --db-path data/trader.db
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.repository import PredictionRecord, create_database, PredictionRepository  # noqa: E402
from src.sheets import get_client, get_or_create_worksheet  # noqa: E402
from src.utils import load_config  # noqa: E402

logger = logging.getLogger(__name__)

app = typer.Typer(help="Migrate prediction data from Google Sheets to SQLite.")


def _parse_is_hit(value: str | None) -> bool | None:
    """Convert '的中'/'外れ' to bool, None for '評価不能' or blank."""
    if value == "的中":
        return True
    if value == "外れ":
        return False
    return None


def _parse_status(value: str | None) -> str:
    """Normalize status to English."""
    if value == "確定済み":
        return "confirmed"
    return "predicted"


def _parse_float(value: str | float | None) -> float | None:
    """Convert cell value to float, returning None on failure."""
    if value is None or value == "" or value == "N/A":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


@app.command()
def migrate(
    db_path: Annotated[str, typer.Option(help="Path to SQLite database.")] = "data/trader.db",
    worksheet: Annotated[str | None, typer.Option(help="Override worksheet name.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show count only.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Debug logging.")] = False,
) -> None:
    """Migrate all prediction rows from Google Sheets to SQLite."""
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s %(name)s: %(message)s")

    config = load_config()
    sheets_cfg = config["google_sheets"]
    ws_name = worksheet or sheets_cfg["worksheet_name"]

    typer.echo("Fetching rows from Google Sheets...")
    client = get_client()
    ws = get_or_create_worksheet(client, sheets_cfg["spreadsheet_name"], ws_name)
    rows = ws.get_all_records()
    typer.echo(f"Fetched {len(rows)} rows from Sheets.")

    if dry_run:
        typer.echo(f"[dry-run] Would migrate {len(rows)} rows. Exiting.")
        raise typer.Exit(0)

    candidates: list[PredictionRecord] = []
    for row in rows:
        record = PredictionRecord(
            date=str(row.get("日付", "")),
            ticker=str(row.get("ティッカー", "")),
            current_price=_parse_float(row.get("現在価格")),
            predicted_price=_parse_float(row.get("予測価格")),
            predicted_change_pct=_parse_float(row.get("予測上昇率(%)")),
            confidence_interval_pct=_parse_float(row.get("信頼区間(%)")),
            prob_up=_parse_float(row.get("prob_up")),
            actual_price=_parse_float(row.get("翌週実績価格")),
            is_hit=_parse_is_hit(row.get("的中")),
            status=_parse_status(row.get("ステータス")),
            created_at=datetime.utcnow(),
        )
        candidates.append(record)

    valid = [r for r in candidates if r.date and r.ticker]
    skipped_invalid = len(candidates) - len(valid)
    if skipped_invalid:
        logger.warning("Skipped %d rows with missing date or ticker.", skipped_invalid)

    session_factory = create_database(db_path)
    inserted = 0
    skipped_duplicate = 0

    with session_factory() as session:
        repo = PredictionRepository(session)
        for record in valid:
            existing = repo.find_by_date(record.date)
            existing_tickers = {r.ticker for r in existing}
            if record.ticker in existing_tickers:
                skipped_duplicate += 1
                continue
            repo.save(record)
            inserted += 1
        session.commit()

    typer.echo(
        f"Migration complete: {inserted} inserted, "
        f"{skipped_duplicate} duplicates skipped, "
        f"{skipped_invalid} invalid rows skipped."
    )


if __name__ == "__main__":
    app()
