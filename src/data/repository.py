"""Persistence layer: SQLAlchemy 2.0 models and repository classes.

Replaces Google Sheets as the primary storage backend.
Models mirror the existing sheets schema (sheets.py HEADERS) plus
redesign additions (prob_up_calibrated, enrichment JSON blob).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, JSON, String, text
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = structlog.get_logger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


class PredictionRecord(Base):
    """One row per (date, ticker) prediction.

    Sheets column mapping:
        日付             -> date
        ティッカー        -> ticker
        現在価格          -> current_price
        予測価格          -> predicted_price
        予測上昇率(%)     -> predicted_change_pct
        信頼区間(%)       -> confidence_interval_pct
        翌週実績価格       -> actual_price   (filled by tracker)
        的中              -> is_hit          (filled by tracker)
        ステータス         -> status
        prob_up          -> prob_up
    """

    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False, index=True)
    ticker = Column(String, nullable=False, index=True)
    current_price = Column(Float)
    predicted_price = Column(Float)
    predicted_change_pct = Column(Float)
    confidence_interval_pct = Column(Float)
    prob_up = Column(Float)
    prob_up_calibrated = Column(Float)
    actual_price = Column(Float)
    is_hit = Column(Boolean)
    status = Column(String, default="predicted")
    enrichment = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<PredictionRecord date={self.date} ticker={self.ticker} status={self.status}>"


class BacktestRecord(Base):
    """One row per backtest run result."""

    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(String, nullable=False)
    strategy = Column(String, nullable=False)
    cagr = Column(Float)
    max_drawdown = Column(Float)
    sharpe = Column(Float)
    equity_curve = Column(JSON)

    def __repr__(self) -> str:
        return f"<BacktestRecord run_date={self.run_date} strategy={self.strategy}>"


class PredictionRepository:
    """CRUD operations for PredictionRecord."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, prediction: PredictionRecord) -> None:
        """Persist a single prediction record."""
        self._session.add(prediction)
        self._session.flush()

    def save_batch(self, predictions: list[PredictionRecord]) -> None:
        """Persist multiple prediction records."""
        self._session.add_all(predictions)
        self._session.flush()

    def find_by_date(self, date: str) -> list[PredictionRecord]:
        """Return all records for a given prediction date."""
        stmt = select(PredictionRecord).where(PredictionRecord.date == date)
        return list(self._session.scalars(stmt))

    def find_by_ticker(self, ticker: str) -> list[PredictionRecord]:
        """Return all records for a given ticker symbol."""
        stmt = select(PredictionRecord).where(PredictionRecord.ticker == ticker)
        return list(self._session.scalars(stmt))

    def find_pending_tracking(self) -> list[PredictionRecord]:
        """Return predictions awaiting actual price evaluation."""
        stmt = (
            select(PredictionRecord)
            .where(PredictionRecord.status == "predicted")
            .where(PredictionRecord.actual_price.is_(None))
        )
        return list(self._session.scalars(stmt))

    def update_tracking(
        self,
        record_id: int,
        actual_price: float,
        is_hit: bool | None,
    ) -> None:
        """Fill in actual_price and is_hit, setting status to confirmed."""
        stmt = (
            update(PredictionRecord)
            .where(PredictionRecord.id == record_id)
            .values(
                actual_price=actual_price,
                is_hit=is_hit,
                status="confirmed",
            )
        )
        self._session.execute(stmt)

    def get_all_confirmed(self) -> list[PredictionRecord]:
        """Return all confirmed records."""
        stmt = select(PredictionRecord).where(PredictionRecord.status == "confirmed")
        return list(self._session.scalars(stmt))

    def get_accuracy_stats(self) -> dict[str, Any]:
        """Compute hit-rate statistics over all evaluable confirmed records."""
        confirmed = self.get_all_confirmed()
        evaluable = [r for r in confirmed if r.is_hit is not None]

        empty_stats: dict[str, Any] = {
            "hits": 0,
            "misses": 0,
            "total": 0,
            "hit_rate_pct": 0.0,
            "cumulative_hits": 0,
            "cumulative_total": 0,
            "cumulative_hit_rate_pct": 0.0,
            "cumulative_weeks": 0,
        }
        if not evaluable:
            return empty_stats

        cumulative_hits = sum(1 for r in evaluable if r.is_hit is True)
        cumulative_total = len(evaluable)
        cumulative_hit_rate = cumulative_hits / cumulative_total * 100

        all_confirmed_dates = sorted({r.date for r in confirmed})
        latest_date = all_confirmed_dates[-1] if all_confirmed_dates else ""

        this_week = [r for r in evaluable if r.date == latest_date]
        hits = sum(1 for r in this_week if r.is_hit is True)
        total = len(this_week)
        hit_rate = hits / total * 100 if total > 0 else 0.0

        evaluable_dates = sorted({r.date for r in evaluable})

        return {
            "hits": hits,
            "misses": total - hits,
            "total": total,
            "hit_rate_pct": round(hit_rate, 1),
            "cumulative_hits": cumulative_hits,
            "cumulative_total": cumulative_total,
            "cumulative_hit_rate_pct": round(cumulative_hit_rate, 1),
            "cumulative_weeks": len(evaluable_dates),
        }


class BacktestRepository:
    """CRUD operations for BacktestRecord."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, result: BacktestRecord) -> None:
        """Persist a single backtest result."""
        self._session.add(result)
        self._session.flush()

    def get_latest(self) -> list[BacktestRecord]:
        """Return all backtest records ordered by run_date descending."""
        stmt = select(BacktestRecord).order_by(BacktestRecord.run_date.desc())
        return list(self._session.scalars(stmt))


def create_database(db_path: str = "data/trader.db") -> sessionmaker:
    """Create SQLite database with WAL mode and return a Session factory.

    Args:
        db_path: Path to the SQLite file.

    Returns:
        A sessionmaker bound to the engine.
    """
    engine = create_engine(f"sqlite:///{db_path}", echo=False)

    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))

    Base.metadata.create_all(engine)
    logger.info("database_ready", path=db_path)

    return sessionmaker(bind=engine, expire_on_commit=False)
