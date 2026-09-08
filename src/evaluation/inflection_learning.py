"""Auditable self-learning layer for JP inflection shadow snapshots.

This module never rewrites production strategy weights by itself. It learns from
immutable point-in-time snapshots, evaluates later outcomes, records prediction
misses and explosive moves, and promotes only statistically supported factor
adjustments as proposals for a future strategy version.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

import pandas as pd

from src.data.snapshot_crypto import decrypt_json
from src.evaluation.inflection_backtest import simulate_signal
from src.evaluation.inflection_forward import (
    BENCHMARK_TICKER,
    SnapshotLoadError,
    benchmark_returns_by_signal_date,
)

LEARNING_HORIZONS = (5, 20, 60, 120)
EXPLOSION_MAX_RETURN_PCT = {5: 15.0, 20: 25.0, 60: 40.0, 120: 60.0}
ROUND_TRIP_COST_PCT = 0.2
PROMOTION_MIN_OBSERVATIONS = 30
PROMOTION_POSITIVE_LIFT = 1.35
PROMOTION_NEGATIVE_LIFT = 0.75


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_learning_observations(
    snapshot_dir: Path,
    *,
    encryption_secret: str,
) -> list[dict[str, Any]]:
    """Load every deep-scan candidate, not only EARLY_CANDIDATE signals.

    Strategy/schema versions are retained per observation instead of requiring a
    single version forever. This lets the knowledge base survive future strategy
    upgrades while keeping each observation auditable.
    """
    if not snapshot_dir.exists():
        return []

    observations: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(snapshot_dir.glob("????-??-??.enc")):
        try:
            payload = decrypt_json(path.read_text(encoding="utf-8"), encryption_secret)
        except (OSError, TypeError, ValueError) as exc:
            raise SnapshotLoadError(f"Could not decrypt or decode snapshot: {path.name}") from exc

        if payload.get("mode") != "shadow":
            raise SnapshotLoadError(f"Invalid snapshot mode: {path.name}")
        strategy_version = str(payload.get("strategy_version") or "")
        schema_version = payload.get("report_schema_version")
        market_date = str(payload.get("latest_price_date") or "")
        if (
            not strategy_version
            or isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version < 1
            or market_date != path.stem
        ):
            raise SnapshotLoadError(f"Invalid snapshot metadata/schema: {path.name}")

        candidates = payload.get("candidates")
        if not isinstance(candidates, list):
            raise SnapshotLoadError(f"Invalid candidates payload: {path.name}")

        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise SnapshotLoadError(f"Invalid candidate row: {path.name}")
            ticker = str(candidate.get("ticker") or "")
            classification = str(candidate.get("classification") or "")
            score = _optional_float(candidate.get("score"))
            if not ticker or not classification or score is None:
                raise SnapshotLoadError(f"Candidate identity/score missing: {path.name}")
            key = (market_date, ticker)
            if key in observations:
                continue
            reasons = candidate.get("reasons")
            observations[key] = {
                "ticker": ticker,
                "date": market_date,
                "signal_date": market_date,
                "strategy_version": strategy_version,
                "report_schema_version": schema_version,
                "classification": classification,
                "score": score,
                "raw_inflection_score": _optional_float(candidate.get("raw_inflection_score")),
                "market": str(candidate.get("market") or ""),
                "return_5d_pct": _optional_float(candidate.get("return_5d_pct")),
                "return_20d_pct": _optional_float(candidate.get("return_20d_pct")),
                "return_60d_pct": _optional_float(candidate.get("return_60d_pct")),
                "volume_ratio_20d": _optional_float(candidate.get("volume_ratio_20d")),
                "breakout_52w": bool(candidate.get("breakout_52w")),
                "avg_turnover_20d_jpy": _optional_float(candidate.get("avg_turnover_20d_jpy")),
                "reasons": [str(value) for value in reasons] if isinstance(reasons, list) else [],
            }

    return sorted(observations.values(), key=lambda row: (str(row["signal_date"]), str(row["ticker"])))


def _bucket(value: float | None, cuts: tuple[float, ...], labels: tuple[str, ...]) -> str:
    if value is None:
        return "missing"
    for index, cut in enumerate(cuts):
        if value < cut:
            return labels[index]
    return labels[-1]


def factor_labels(observation: dict[str, Any]) -> list[str]:
    """Convert one point-in-time candidate into stable, interpretable factor labels."""
    labels = [
        f"classification:{observation.get('classification')}",
        f"market:{observation.get('market') or 'unknown'}",
        "breakout_52w:true" if observation.get("breakout_52w") else "breakout_52w:false",
        "score_band:"
        + _bucket(
            _optional_float(observation.get("score")),
            (52.0, 70.0, 85.0),
            ("lt52", "52to70", "70to85", "ge85"),
        ),
        "return20_band:"
        + _bucket(
            _optional_float(observation.get("return_20d_pct")),
            (0.0, 8.0, 15.0, 30.0, 50.0),
            ("negative", "0to8", "8to15", "15to30", "30to50", "ge50"),
        ),
        "return60_band:"
        + _bucket(
            _optional_float(observation.get("return_60d_pct")),
            (0.0, 15.0, 30.0, 60.0),
            ("negative", "0to15", "15to30", "30to60", "ge60"),
        ),
        "volume20_band:"
        + _bucket(
            _optional_float(observation.get("volume_ratio_20d")),
            (1.0, 1.25, 1.5, 2.0, 3.0),
            ("lt1", "1to1.25", "1.25to1.5", "1.5to2", "2to3", "ge3"),
        ),
    ]
    for reason in observation.get("reasons", []):
        labels.append(f"reason:{reason}")
    return labels


def _prediction_miss_reasons(row: dict[str, Any]) -> list[str]:
    if row.get("classification") != "EARLY_CANDIDATE":
        return []
    h20 = row.get("horizons", {}).get("h20", {})
    if not h20.get("completed") or h20.get("excess_return_pct") is None:
        return []
    excess = float(h20["excess_return_pct"])
    if excess > 0:
        return []

    reasons: list[str] = []
    net = _optional_float(h20.get("net_return_pct"))
    if net is not None and net <= 0:
        reasons.append("negative_absolute_return")
    elif net is not None:
        reasons.append("market_beta_only")

    if (_optional_float(row.get("return_20d_pct")) or 0.0) >= 15.0:
        reasons.append("signal_after_strong_20d_runup")
    if (_optional_float(row.get("volume_ratio_20d")) or 0.0) >= 1.5:
        max_return = _optional_float(h20.get("max_return_pct"))
        if max_return is not None and max_return < EXPLOSION_MAX_RETURN_PCT[20]:
            reasons.append("volume_without_followthrough")
    if row.get("breakout_52w"):
        reasons.append("52w_breakout_failed_to_outperform")
    if row.get("reasons"):
        reasons.append("fundamental_or_momentum_reason_not_confirmed_by_20d_excess")
    return reasons


def evaluate_learning_observations(
    observations: Iterable[dict[str, Any]],
    histories: dict[str, pd.DataFrame],
    benchmark_history: pd.DataFrame,
    *,
    horizons: tuple[int, ...] = LEARNING_HORIZONS,
    round_trip_cost_pct: float = ROUND_TRIP_COST_PCT,
) -> list[dict[str, Any]]:
    """Attach future outcomes without using them to alter the original signal."""
    observation_rows = [dict(row) for row in observations]
    signal_dates = [str(row["signal_date"]) for row in observation_rows]
    benchmark_by_horizon = {
        horizon: benchmark_returns_by_signal_date(
            signal_dates,
            benchmark_history,
            holding_days=horizon,
            round_trip_cost_pct=round_trip_cost_pct,
        )
        for horizon in horizons
    }

    evaluated: list[dict[str, Any]] = []
    for observation in observation_rows:
        row = dict(observation)
        outcomes: dict[str, Any] = {}
        explosion_horizons: list[int] = []
        for horizon in horizons:
            trade = simulate_signal(
                observation,
                histories.get(str(observation["ticker"]), pd.DataFrame()),
                holding_days=horizon,
                round_trip_cost_pct=round_trip_cost_pct,
                apply_tax=False,
            )
            benchmark_return = benchmark_by_horizon[horizon].get(str(observation["signal_date"]))
            trade_return = trade.net_return_pct
            completed = trade_return is not None
            excess_return = None
            if trade_return is not None and benchmark_return is not None:
                excess_return = round(float(trade_return) - float(benchmark_return), 6)
            max_return = trade.max_return_pct
            is_explosion = bool(
                completed
                and max_return is not None
                and float(max_return) >= EXPLOSION_MAX_RETURN_PCT[horizon]
            )
            if is_explosion:
                explosion_horizons.append(horizon)
            outcomes[f"h{horizon}"] = {
                "completed": completed,
                "entry_date": trade.entry_date,
                "exit_date": trade.exit_date,
                "net_return_pct": trade_return,
                "benchmark_net_return_pct": benchmark_return,
                "excess_return_pct": excess_return,
                "max_return_pct": max_return,
                "mfe_pct": trade.mfe_pct,
                "mae_pct": trade.mae_pct,
                "explosion_threshold_pct": EXPLOSION_MAX_RETURN_PCT[horizon],
                "explosive": is_explosion,
            }
        row["horizons"] = outcomes
        row["factor_labels"] = factor_labels(observation)
        row["explosion_horizons"] = explosion_horizons
        row["explosive"] = bool(explosion_horizons)
        row["missed_explosion"] = bool(explosion_horizons) and observation.get("classification") != "EARLY_CANDIDATE"
        row["prediction_miss_reasons"] = _prediction_miss_reasons(row)
        evaluated.append(row)
    return evaluated


def _independent_rows(rows: list[dict[str, Any]], horizon: int) -> list[dict[str, Any]]:
    """Remove overlapping same-ticker observations for one evaluation horizon."""
    key = f"h{horizon}"
    selected: list[dict[str, Any]] = []
    occupied_until: dict[str, str] = {}
    for row in sorted(rows, key=lambda item: (str(item["signal_date"]), str(item["ticker"]))):
        outcome = row.get("horizons", {}).get(key, {})
        if not outcome.get("completed") or not outcome.get("exit_date"):
            continue
        ticker = str(row["ticker"])
        signal_date = str(row["signal_date"])
        if signal_date <= occupied_until.get(ticker, ""):
            continue
        selected.append(row)
        occupied_until[ticker] = str(outcome["exit_date"])
    return selected


def _horizon_summary(rows: list[dict[str, Any]], horizon: int) -> dict[str, Any]:
    key = f"h{horizon}"
    excess_values = [
        float(row["horizons"][key]["excess_return_pct"])
        for row in rows
        if row["horizons"][key].get("excess_return_pct") is not None
    ]
    explosive = [bool(row["horizons"][key].get("explosive")) for row in rows]
    early_rows = [row for row in rows if row.get("classification") == "EARLY_CANDIDATE"]
    early_misses = [
        row
        for row in early_rows
        if row["horizons"][key].get("excess_return_pct") is not None
        and float(row["horizons"][key]["excess_return_pct"]) <= 0
    ]
    return {
        "independent_observations": len(rows),
        "mean_excess_return_pct": round(mean(excess_values), 6) if excess_values else None,
        "explosion_rate_pct": round(sum(explosive) / len(explosive) * 100.0, 3) if explosive else None,
        "early_candidate_observations": len(early_rows),
        "early_candidate_miss_rate_pct": (
            round(len(early_misses) / len(early_rows) * 100.0, 3) if early_rows else None
        ),
    }


def _factor_statistics(
    rows: list[dict[str, Any]],
    *,
    horizon: int,
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    key = f"h{horizon}"
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for label in row.get("factor_labels", []):
            grouped[str(label)].append(row)

    baseline_explosion_rate = _optional_float(baseline.get("explosion_rate_pct"))
    stats: list[dict[str, Any]] = []
    for label, factor_rows in grouped.items():
        excess = [
            float(row["horizons"][key]["excess_return_pct"])
            for row in factor_rows
            if row["horizons"][key].get("excess_return_pct") is not None
        ]
        explosions = [bool(row["horizons"][key].get("explosive")) for row in factor_rows]
        rate = sum(explosions) / len(explosions) * 100.0 if explosions else 0.0
        lift = None
        if baseline_explosion_rate is not None and baseline_explosion_rate > 0:
            lift = rate / baseline_explosion_rate
        mean_excess = mean(excess) if excess else None
        direction = "hold"
        if (
            len(factor_rows) >= PROMOTION_MIN_OBSERVATIONS
            and lift is not None
            and lift >= PROMOTION_POSITIVE_LIFT
            and mean_excess is not None
            and mean_excess > 0
        ):
            direction = "positive_candidate"
        elif (
            len(factor_rows) >= PROMOTION_MIN_OBSERVATIONS
            and lift is not None
            and lift <= PROMOTION_NEGATIVE_LIFT
            and mean_excess is not None
            and mean_excess < 0
        ):
            direction = "negative_candidate"
        stats.append(
            {
                "factor": label,
                "independent_observations": len(factor_rows),
                "mean_excess_return_pct": round(mean_excess, 6) if mean_excess is not None else None,
                "explosion_rate_pct": round(rate, 3),
                "explosion_rate_lift": round(lift, 6) if lift is not None else None,
                "promotion_status": direction,
            }
        )
    return sorted(
        stats,
        key=lambda item: (
            item["promotion_status"] == "hold",
            -int(item["independent_observations"]),
            str(item["factor"]),
        ),
    )


def _lessons(factors_by_horizon: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    promoted: list[dict[str, Any]] = []
    for horizon_key, factors in factors_by_horizon.items():
        for factor in factors:
            status = str(factor.get("promotion_status"))
            if status == "hold":
                continue
            promoted.append(
                {
                    "horizon": horizon_key,
                    "factor": factor["factor"],
                    "direction": "increase_attention" if status == "positive_candidate" else "decrease_attention",
                    "independent_observations": factor["independent_observations"],
                    "mean_excess_return_pct": factor["mean_excess_return_pct"],
                    "explosion_rate_lift": factor["explosion_rate_lift"],
                    "action": "candidate_for_next_strategy_version_not_auto_applied",
                }
            )
    return promoted[:20]


def build_learning_report(
    observations: list[dict[str, Any]],
    histories: dict[str, pd.DataFrame],
    benchmark_history: pd.DataFrame,
) -> dict[str, Any]:
    """Build cumulative knowledge while gating promotions on the latest strategy."""
    evaluated = evaluate_learning_observations(observations, histories, benchmark_history)
    strategy_versions = sorted({str(row.get("strategy_version") or "") for row in observations if row.get("strategy_version")})
    latest_strategy_version = None
    if observations:
        latest_observation = max(observations, key=lambda row: str(row.get("signal_date") or ""))
        latest_strategy_version = str(latest_observation.get("strategy_version") or "") or None

    baselines: dict[str, Any] = {}
    factors: dict[str, list[dict[str, Any]]] = {}
    independent_counts: dict[str, int] = {}
    promotion_baselines: dict[str, Any] = {}
    promotion_factors: dict[str, list[dict[str, Any]]] = {}
    promotion_counts: dict[str, int] = {}
    latest_rows = [row for row in evaluated if row.get("strategy_version") == latest_strategy_version]

    for horizon in LEARNING_HORIZONS:
        horizon_key = f"h{horizon}"
        independent = _independent_rows(evaluated, horizon)
        baseline = _horizon_summary(independent, horizon)
        baselines[horizon_key] = baseline
        independent_counts[horizon_key] = len(independent)
        factors[horizon_key] = _factor_statistics(independent, horizon=horizon, baseline=baseline)

        latest_independent = _independent_rows(latest_rows, horizon)
        promotion_baseline = _horizon_summary(latest_independent, horizon)
        promotion_baselines[horizon_key] = promotion_baseline
        promotion_counts[horizon_key] = len(latest_independent)
        promotion_factors[horizon_key] = _factor_statistics(
            latest_independent,
            horizon=horizon,
            baseline=promotion_baseline,
        )

    postmortems = [
        {
            "ticker": row["ticker"],
            "signal_date": row["signal_date"],
            "strategy_version": row["strategy_version"],
            "classification": row["classification"],
            "prediction_miss_reasons": row["prediction_miss_reasons"],
            "missed_explosion": row["missed_explosion"],
            "explosion_horizons": row["explosion_horizons"],
            "factor_labels": row["factor_labels"],
        }
        for row in evaluated
        if row["prediction_miss_reasons"] or row["missed_explosion"]
    ]

    return {
        "learning_version": "inflection-learning-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "strategy_version": latest_strategy_version,
        "strategy_versions": strategy_versions,
        "promotion_scope_strategy_version": latest_strategy_version,
        "observation_count": len(observations),
        "learning_unit": "same-ticker observations are de-overlapped independently per horizon",
        "horizons": list(LEARNING_HORIZONS),
        "explosion_definition_max_return_pct": {
            f"h{horizon}": threshold for horizon, threshold in EXPLOSION_MAX_RETURN_PCT.items()
        },
        "independent_observation_counts": independent_counts,
        "baselines": baselines,
        "factor_statistics": factors,
        "promotion_independent_observation_counts": promotion_counts,
        "promotion_baselines": promotion_baselines,
        "promotion_factor_statistics": promotion_factors,
        "lessons": _lessons(promotion_factors),
        "postmortems": postmortems,
        "observations": evaluated,
        "promotion_gate": {
            "minimum_independent_observations": PROMOTION_MIN_OBSERVATIONS,
            "positive_explosion_lift": PROMOTION_POSITIVE_LIFT,
            "negative_explosion_lift": PROMOTION_NEGATIVE_LIFT,
            "automatic_production_weight_update": False,
            "scope": "latest_strategy_version_only",
            "reason": "prevent small-sample overfitting, policy-confounding and self-reinforcing strategy drift",
        },
        "limitations": [
            "Learns only from the deep-scan candidates stored in historical snapshots; stocks outside that pool are invisible.",
            "Factor attribution is associative, not proof of causality.",
            "Cumulative factor statistics may span multiple strategy versions; promotion decisions use only the latest strategy version.",
            "News/TDnet/EDINET catalyst evidence is not yet connected point-in-time, so true event-cause attribution is unavailable.",
            f"Benchmark is {BENCHMARK_TICKER}; order-book depth, halts and price-limit fill probability remain unmodeled.",
        ],
    }


def public_learning_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Return an aggregate-only artifact with no ticker-level observations."""
    allowed = {
        "learning_version",
        "generated_at",
        "strategy_version",
        "strategy_versions",
        "promotion_scope_strategy_version",
        "observation_count",
        "learning_unit",
        "horizons",
        "explosion_definition_max_return_pct",
        "independent_observation_counts",
        "baselines",
        "factor_statistics",
        "promotion_independent_observation_counts",
        "promotion_baselines",
        "promotion_factor_statistics",
        "lessons",
        "promotion_gate",
        "limitations",
    }
    return {key: value for key, value in report.items() if key in allowed}
