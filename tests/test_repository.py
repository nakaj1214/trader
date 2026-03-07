"""Tests for src.data.repository."""

from __future__ import annotations

import pytest

from src.data.repository import (
    BacktestRecord,
    BacktestRepository,
    PredictionRecord,
    PredictionRepository,
    create_database,
)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite DB session."""
    session_factory = create_database(":memory:")
    with session_factory() as session:
        yield session


class TestPredictionRepository:

    def test_save_and_find_by_date(self, db_session) -> None:
        repo = PredictionRepository(db_session)
        record = PredictionRecord(
            date="2025-01-06",
            ticker="AAPL",
            current_price=150.0,
            predicted_price=158.0,
            predicted_change_pct=5.33,
            status="predicted",
        )
        repo.save(record)
        db_session.commit()

        found = repo.find_by_date("2025-01-06")
        assert len(found) == 1
        assert found[0].ticker == "AAPL"

    def test_find_by_ticker(self, db_session) -> None:
        repo = PredictionRepository(db_session)
        for date in ["2025-01-06", "2025-01-13"]:
            repo.save(PredictionRecord(
                date=date, ticker="AAPL", current_price=150.0,
                predicted_price=158.0, status="predicted",
            ))
        db_session.commit()

        found = repo.find_by_ticker("AAPL")
        assert len(found) == 2

    def test_save_batch(self, db_session) -> None:
        repo = PredictionRepository(db_session)
        records = [
            PredictionRecord(date="2025-01-06", ticker="AAPL", status="predicted"),
            PredictionRecord(date="2025-01-06", ticker="MSFT", status="predicted"),
        ]
        repo.save_batch(records)
        db_session.commit()

        assert len(repo.find_by_date("2025-01-06")) == 2

    def test_find_pending_tracking(self, db_session) -> None:
        repo = PredictionRepository(db_session)
        repo.save(PredictionRecord(
            date="2025-01-06", ticker="AAPL",
            current_price=150.0, predicted_price=158.0,
            status="predicted", actual_price=None,
        ))
        repo.save(PredictionRecord(
            date="2025-01-06", ticker="MSFT",
            current_price=300.0, predicted_price=312.0,
            status="confirmed", actual_price=310.0,
        ))
        db_session.commit()

        pending = repo.find_pending_tracking()
        assert len(pending) == 1
        assert pending[0].ticker == "AAPL"

    def test_update_tracking(self, db_session) -> None:
        repo = PredictionRepository(db_session)
        record = PredictionRecord(
            date="2025-01-06", ticker="AAPL",
            current_price=150.0, predicted_price=158.0,
            status="predicted",
        )
        repo.save(record)
        db_session.commit()

        repo.update_tracking(record.id, actual_price=155.0, is_hit=True)
        db_session.commit()

        updated = repo.find_by_date("2025-01-06")[0]
        assert updated.actual_price == 155.0
        assert updated.is_hit is True
        assert updated.status == "confirmed"

    def test_get_accuracy_stats_empty(self, db_session) -> None:
        repo = PredictionRepository(db_session)
        stats = repo.get_accuracy_stats()
        assert stats["total"] == 0
        assert stats["hit_rate_pct"] == 0.0

    def test_get_accuracy_stats_with_data(self, db_session) -> None:
        repo = PredictionRepository(db_session)
        for ticker, is_hit in [("AAPL", True), ("MSFT", False), ("GOOGL", True)]:
            repo.save(PredictionRecord(
                date="2025-01-06", ticker=ticker,
                current_price=100.0, predicted_price=110.0,
                status="confirmed", actual_price=105.0, is_hit=is_hit,
            ))
        db_session.commit()

        stats = repo.get_accuracy_stats()
        assert stats["cumulative_total"] == 3
        assert stats["cumulative_hits"] == 2


class TestBacktestRepository:

    def test_save_and_get_latest(self, db_session) -> None:
        repo = BacktestRepository(db_session)
        repo.save(BacktestRecord(
            run_date="2025-01-06", strategy="ai",
            cagr=0.15, max_drawdown=-0.10, sharpe=1.5,
        ))
        db_session.commit()

        latest = repo.get_latest()
        assert len(latest) == 1
        assert latest[0].strategy == "ai"


class TestCreateDatabase:

    def test_creates_tables(self) -> None:
        session_factory = create_database(":memory:")
        with session_factory() as session:
            repo = PredictionRepository(session)
            assert repo.find_by_date("2099-01-01") == []
