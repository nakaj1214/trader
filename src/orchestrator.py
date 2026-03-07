"""Pipeline orchestrator: coordinates the full analysis workflow.

Steps:
    1. Screen   — identify top stocks (US and JP independently)
    2. Predict  — forecast prices for screened stocks
    3. Track    — evaluate past predictions against actuals
    4. Persist  — save new predictions to DB (and optionally Google Sheets)
    5. Enrich   — add supplemental data (risk, events, evidence, sentiment)
    6. Notify   — send Slack and LINE notifications
    7. Export   — generate dashboard JSON files
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class StepResult:
    """Outcome of a single pipeline step."""

    name: str
    success: bool
    error: str | None = None
    data: Any = None


@dataclass
class PipelineResult:
    """Aggregate outcome of the full pipeline run."""

    steps: list[StepResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.success for s in self.steps)

    def summary(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "steps": [
                {"name": s.name, "success": s.success, "error": s.error}
                for s in self.steps
            ],
        }


def run_pipeline(
    config: dict[str, Any],
    markets: list[str] | None = None,
    dry_run: bool = False,
) -> PipelineResult:
    """Execute the full analysis pipeline.

    Each step is independent: one step's failure does not stop subsequent steps.

    Args:
        config: Application config dict (from AppConfig.model_dump()).
        markets: Market list override. Defaults to config screening.markets.
        dry_run: If True, skip side effects (DB writes, notifications).

    Returns:
        PipelineResult with per-step outcomes.
    """
    result = PipelineResult()

    if markets is None:
        markets = config.get("screening", {}).get(
            "markets", ["sp500", "nasdaq100", "nikkei225"]
        )

    us_markets = [m for m in markets if m != "nikkei225"]
    jp_markets = [m for m in markets if m == "nikkei225"]

    # ---- Step 1: Screening ----
    screened_us = _step_screen(result, config, us_markets, label="us")
    screened_jp = _step_screen(result, config, jp_markets, label="jp")

    # ---- Step 2: Prediction ----
    predictions_us = _step_predict(result, screened_us, config, label="us")
    predictions_jp = _step_predict(result, screened_jp, config, label="jp")

    predictions = _concat_predictions(predictions_us, predictions_jp)

    # ---- Step 3: Track previous predictions ----
    accuracy = _step_track(result, config)

    # ---- Step 4: Persist new predictions ----
    if not dry_run:
        _step_persist(result, predictions, config)
    else:
        result.steps.append(StepResult(name="persist", success=True, data="dry_run"))

    # ---- Step 5: Enrichment ----
    enrichment = _step_enrich(result, predictions, config)

    # ---- Step 6: Notification ----
    if not dry_run:
        _step_notify(result, predictions, accuracy, config)
    else:
        result.steps.append(StepResult(name="notify", success=True, data="dry_run"))

    # ---- Step 7: Export dashboard JSON ----
    _step_export(result, enrichment, config, dry_run)

    logger.info("pipeline_complete", ok=result.ok, summary=result.summary())
    return result


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


def _step_screen(
    result: PipelineResult,
    config: dict[str, Any],
    markets: list[str],
    label: str,
) -> pd.DataFrame:
    """Run screening for the given markets."""
    step_name = f"screen_{label}"
    if not markets:
        result.steps.append(StepResult(name=step_name, success=True, data="skipped"))
        return pd.DataFrame()

    try:
        from src.screening.scorer import screen

        screen_config = copy.deepcopy(config)
        screen_config["screening"]["markets"] = markets

        market_arg = markets[0] if len(markets) == 1 else "us"
        screened = screen(screen_config, market=market_arg)

        if screened.empty:
            logger.warning("screening_empty", label=label, markets=markets)
        else:
            logger.info(
                "screening_done",
                label=label,
                count=len(screened),
                top_tickers=screened["ticker"].tolist()[:5],
            )

        result.steps.append(StepResult(name=step_name, success=True, data=len(screened)))
        return screened
    except Exception as exc:
        logger.exception("screening_failed", label=label)
        result.steps.append(StepResult(name=step_name, success=False, error=str(exc)))
        return pd.DataFrame()


def _step_predict(
    result: PipelineResult,
    screened: pd.DataFrame,
    config: dict[str, Any],
    label: str,
) -> pd.DataFrame:
    """Run prediction for screened stocks."""
    step_name = f"predict_{label}"
    if screened.empty:
        result.steps.append(StepResult(name=step_name, success=True, data="skipped"))
        return pd.DataFrame()

    try:
        from src.prediction.ensemble import predict

        predictions = predict(screened, config)
        logger.info("prediction_done", label=label, count=len(predictions))
        result.steps.append(StepResult(name=step_name, success=True, data=len(predictions)))
        return predictions
    except Exception as exc:
        logger.exception("prediction_failed", label=label)
        result.steps.append(StepResult(name=step_name, success=False, error=str(exc)))
        return pd.DataFrame()


def _step_track(
    result: PipelineResult,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """Evaluate previous predictions against actual prices."""
    try:
        from src.evaluation.tracker import track

        accuracy = track(config)
        if accuracy["total"] > 0:
            logger.info(
                "tracking_done",
                hits=accuracy["hits"],
                total=accuracy["total"],
                hit_rate=accuracy["hit_rate_pct"],
            )
        else:
            logger.info("tracking_no_previous_data")

        result.steps.append(StepResult(name="track", success=True, data=accuracy))
        return accuracy
    except Exception as exc:
        logger.exception("tracking_failed")
        result.steps.append(StepResult(name="track", success=False, error=str(exc)))
        return None


def _step_persist(
    result: PipelineResult,
    predictions: pd.DataFrame,
    config: dict[str, Any],
) -> None:
    """Save new predictions to DB and optionally Google Sheets."""
    if predictions.empty:
        result.steps.append(StepResult(name="persist", success=True, data="no_data"))
        return

    saved_db = 0
    saved_sheets = 0

    # DB persistence
    try:
        from src.data.repository import PredictionRecord, PredictionRepository, create_database

        db_path = config.get("data", {}).get("db_path", "data/trader.db")
        session_factory = create_database(db_path)
        today = datetime.now().strftime("%Y-%m-%d")

        with session_factory() as session:
            repo = PredictionRepository(session)
            records: list[PredictionRecord] = []
            for _, row in predictions.iterrows():
                records.append(
                    PredictionRecord(
                        date=today,
                        ticker=row["ticker"],
                        current_price=row.get("current_price"),
                        predicted_price=row.get("predicted_price"),
                        predicted_change_pct=row.get("predicted_change_pct"),
                        confidence_interval_pct=row.get("ci_pct"),
                        prob_up=row.get("prob_up"),
                        prob_up_calibrated=row.get("prob_up_calibrated"),
                        status="predicted",
                    )
                )
            repo.save_batch(records)
            session.commit()
            saved_db = len(records)
            logger.info("db_persist_done", count=saved_db)
    except Exception:
        logger.exception("db_persist_failed")

    # Google Sheets persistence (backward compat)
    try:
        from src.export.sheets_exporter import append_predictions

        sheets_cfg = config.get("export", {}).get("google_sheets", {})
        if sheets_cfg:
            flat_sheets_config = {"google_sheets": sheets_cfg}
            saved_sheets = append_predictions(predictions, flat_sheets_config)
            logger.info("sheets_persist_done", count=saved_sheets)
    except Exception:
        logger.warning("sheets_persist_skipped", exc_info=True)

    result.steps.append(
        StepResult(name="persist", success=saved_db > 0, data={"db": saved_db, "sheets": saved_sheets})
    )


def _step_enrich(
    result: PipelineResult,
    predictions: pd.DataFrame,
    config: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Run enrichment on predicted tickers."""
    if predictions.empty:
        result.steps.append(StepResult(name="enrich", success=True, data="no_data"))
        return {}

    try:
        import yfinance as yf

        from src.enrichment.base import enrich_all

        tickers = predictions["ticker"].tolist()
        today = datetime.now().strftime("%Y-%m-%d")

        # Fetch price data for enrichment (252 trading days ~ 400 calendar days)
        fetch_tickers = tickers + ["SPY"]
        raw = yf.download(" ".join(fetch_tickers), period="400d", group_by="ticker", progress=False)

        stock_data: dict[str, pd.DataFrame] = {}
        spy_df: pd.DataFrame | None = None
        for t in fetch_tickers:
            try:
                if len(fetch_tickers) == 1:
                    df = raw.copy()
                else:
                    df = raw[t].copy()
                if not df.empty:
                    if t == "SPY":
                        spy_df = df
                    else:
                        stock_data[t] = df
            except (KeyError, TypeError):
                continue

        # Fetch info cache for each ticker
        info_cache: dict[str, dict[str, Any]] = {}
        for t in tickers:
            try:
                info_cache[t] = yf.Ticker(t).info or {}
            except Exception:
                info_cache[t] = {}

        enrichment = enrich_all(
            tickers=tickers,
            date=today,
            stock_data=stock_data,
            spy_df=spy_df,
            info_cache=info_cache,
            config=config,
        )

        logger.info("enrichment_done", count=len(enrichment))
        result.steps.append(StepResult(name="enrich", success=True, data=len(enrichment)))
        return enrichment
    except Exception as exc:
        logger.exception("enrichment_failed")
        result.steps.append(StepResult(name="enrich", success=False, error=str(exc)))
        return {}


def _step_notify(
    result: PipelineResult,
    predictions: pd.DataFrame,
    accuracy: dict[str, Any] | None,
    config: dict[str, Any],
) -> None:
    """Send Slack and LINE notifications."""
    try:
        from src.notification.slack_notifier import SlackNotifier, build_report

        notifier = SlackNotifier()
        if notifier.is_enabled(config):
            report_text = build_report(predictions, accuracy, config)
            send_result = notifier.send(report_text)
            if send_result.success:
                logger.info("slack_notification_sent")
            else:
                logger.warning("slack_notification_failed", error=send_result.error_message)

            # Chart upload via Bot Token
            _send_charts(predictions, config)
        else:
            logger.info("slack_disabled")
    except Exception:
        logger.exception("slack_notification_error")

    # LINE notification
    try:
        from src.notification.line_notifier import LineNotifier

        line = LineNotifier()
        if line.is_enabled(config):
            from src.notification.slack_notifier import build_report

            report_text = build_report(predictions, accuracy, config)
            slack_channel = config.get("notification", {}).get("slack", {}).get("channel", "#stock-alerts")
            line_result = line.send(report_text, slack_channel=slack_channel)
            if line_result.success:
                logger.info("line_notification_sent")
            else:
                logger.warning("line_notification_failed", error=line_result.error_message)
        else:
            logger.info("line_disabled")
    except Exception:
        logger.exception("line_notification_error")

    result.steps.append(StepResult(name="notify", success=True))


def _step_export(
    result: PipelineResult,
    enrichment: dict[tuple[str, str], dict[str, Any]],
    config: dict[str, Any],
    dry_run: bool,
) -> None:
    """Export all dashboard JSON files."""
    if dry_run:
        result.steps.append(StepResult(name="export", success=True, data="dry_run"))
        return

    try:
        records = _load_all_records(config)

        # predictions, accuracy, stock_history
        from src.export.json_exporter import export_dashboard_json

        export_ok = export_dashboard_json(records, enrichment, config)

        # comparison.json (backtest)
        _export_comparison(records, config)

        # walkforward.json
        _export_walkforward(records, config)

        # alpha_survey.json
        _export_alpha_survey()

        # macro.json
        _export_macro(config)

        result.steps.append(StepResult(name="export", success=export_ok))
    except Exception as exc:
        logger.exception("export_failed")
        result.steps.append(StepResult(name="export", success=False, error=str(exc)))


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------


def _load_all_records(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Load all prediction records from DB, falling back to Google Sheets."""
    try:
        from sqlalchemy import select

        from src.data.repository import PredictionRecord, create_database

        db_path = config.get("data", {}).get("db_path", "data/trader.db")
        session_factory = create_database(db_path)

        with session_factory() as session:
            stmt = select(PredictionRecord)
            db_records = list(session.scalars(stmt))

            records: list[dict[str, Any]] = []
            for r in db_records:
                records.append({
                    "date": r.date,
                    "ticker": r.ticker,
                    "current_price": r.current_price,
                    "predicted_price": r.predicted_price,
                    "predicted_change_pct": r.predicted_change_pct,
                    "confidence_interval_pct": r.confidence_interval_pct,
                    "prob_up": r.prob_up,
                    "prob_up_calibrated": r.prob_up_calibrated,
                    "actual_price": r.actual_price,
                    "is_hit": r.is_hit,
                    "status": r.status,
                })
            if records:
                return records
    except Exception:
        logger.warning("db_record_load_failed", exc_info=True)

    # Fallback: Google Sheets
    try:
        from src.export.sheets_exporter import get_client, get_or_create_worksheet

        sheets_cfg = config.get("export", {}).get("google_sheets", {})
        if sheets_cfg:
            client = get_client()
            ws = get_or_create_worksheet(
                client,
                sheets_cfg.get("spreadsheet_name", "trade"),
                sheets_cfg.get("worksheet_name", "predictions"),
            )
            return ws.get_all_records()
    except Exception:
        logger.warning("sheets_record_load_failed", exc_info=True)

    return []


def _export_comparison(
    records: list[dict[str, Any]],
    config: dict[str, Any],
) -> None:
    """Generate comparison.json with 3-strategy backtest."""
    try:
        import yfinance as yf

        from src.evaluation.backtest import (
            build_backtest_hygiene,
            build_comparison_json,
            compute_ai_weekly_returns,
            compute_baseline_momentum,
            compute_spy_weekly_returns,
        )
        from src.export.json_exporter import DATA_DIR, safe_write_json

        all_tickers = list({r.get("ticker", "") for r in records if r.get("ticker")})
        if not all_tickers:
            return

        fetch_tickers = all_tickers + ["SPY"]
        raw = yf.download(" ".join(fetch_tickers), period="2y", group_by="ticker", progress=False)

        prices: dict[str, pd.DataFrame] = {}
        spy_df: pd.DataFrame | None = None
        for t in fetch_tickers:
            try:
                if len(fetch_tickers) == 1:
                    df = raw.copy()
                else:
                    df = raw[t].copy()
                if not df.empty:
                    if t == "SPY":
                        spy_df = df
                    else:
                        prices[t] = df
            except (KeyError, TypeError):
                continue

        ai_returns, ai_eq = compute_ai_weekly_returns(records)
        mom_returns, mom_eq = compute_baseline_momentum(prices, top_n=10)

        spy_returns, spy_eq = pd.Series(dtype=float), []
        if spy_df is not None and not spy_df.empty:
            spy_returns, spy_eq = compute_spy_weekly_returns(spy_df)

        comparison = build_comparison_json(
            ai_returns, ai_eq,
            mom_returns, mom_eq,
            spy_returns, spy_eq,
        )
        comparison["hygiene"] = build_backtest_hygiene(config, records)
        safe_write_json(comparison, DATA_DIR / "comparison.json")
        logger.info("comparison_exported")
    except Exception:
        logger.exception("comparison_export_failed")


def _export_walkforward(
    records: list[dict[str, Any]],
    config: dict[str, Any],
) -> None:
    """Generate walkforward.json."""
    try:
        from src.evaluation.walkforward import compute_walkforward
        from src.export.json_exporter import DATA_DIR, safe_write_json

        wf_data = compute_walkforward(records, config)
        safe_write_json(wf_data, DATA_DIR / "walkforward.json")
        logger.info("walkforward_exported")
    except Exception:
        logger.exception("walkforward_export_failed")


def _export_alpha_survey() -> None:
    """Generate alpha_survey.json."""
    try:
        from src.evaluation.alpha_survey import run_and_export

        run_and_export()
    except Exception:
        logger.exception("alpha_survey_export_failed")


def _export_macro(config: dict[str, Any]) -> None:
    """Generate macro.json from FRED data."""
    try:
        from src.data.providers.fred_provider import FREDProvider
        from src.export.json_exporter import DATA_DIR, safe_write_json

        fred = FREDProvider()
        if not fred.is_available():
            logger.info("fred_provider_unavailable")
            return

        macro_data = fred.fetch_info("")
        if macro_data:
            safe_write_json(macro_data, DATA_DIR / "macro.json")
            logger.info("macro_exported")
    except Exception:
        logger.exception("macro_export_failed")


# ---------------------------------------------------------------------------
# Notification helpers
# ---------------------------------------------------------------------------


def _send_charts(predictions: pd.DataFrame, config: dict[str, Any]) -> None:
    """Upload stock charts to Slack via Bot Token."""
    import os

    notif_cfg = config.get("notification", {})
    if not notif_cfg.get("slack", {}).get("chart_enabled", False):
        return

    bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
    channel_id = notif_cfg.get("slack", {}).get("channel_id", "")
    if not bot_token or not channel_id:
        return

    if predictions.empty or "ticker" not in predictions.columns:
        return

    try:
        from src.notification.chart_builder import build_stock_chart

        chart_lookback = notif_cfg.get("chart", {}).get("lookback_days", 60)
        for ticker in predictions["ticker"].tolist():
            chart_bytes = build_stock_chart(ticker, chart_lookback, config)
            if chart_bytes is None:
                continue
            _upload_chart_to_slack(chart_bytes, ticker, bot_token, channel_id)
    except Exception:
        logger.exception("chart_upload_error")


def _upload_chart_to_slack(
    chart_bytes: bytes,
    ticker: str,
    bot_token: str,
    channel_id: str,
) -> None:
    """Upload a single chart image to Slack."""
    import requests

    try:
        resp = requests.post(
            "https://slack.com/api/files.upload",
            headers={"Authorization": f"Bearer {bot_token}"},
            data={"channels": channel_id, "title": f"{ticker} chart"},
            files={"file": (f"{ticker}_chart.png", chart_bytes, "image/png")},
            timeout=30,
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            logger.info("chart_uploaded", ticker=ticker)
        else:
            logger.warning("chart_upload_failed", ticker=ticker, response=resp.text[:200])
    except Exception:
        logger.warning("chart_upload_error", ticker=ticker, exc_info=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _concat_predictions(
    us: pd.DataFrame,
    jp: pd.DataFrame,
) -> pd.DataFrame:
    """Concatenate US and JP predictions."""
    frames = [df for df in [us, jp] if not df.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
