"""Auditable self-learning layer for JP inflection shadow snapshots.

This module never rewrites production strategy weights by itself. It learns from
immutable point-in-time snapshots, evaluates later outcomes, records prediction
misses and explosive moves, and promotes only statistically supported factor
adjustments as proposals for a future strategy version.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from statistics import mean
from typing import Any

import pandas as pd

from src.data.snapshot_crypto import decrypt_json
from src.data.validation import is_finite_number
from src.evaluation.explosion import (
    HORIZON_MAX_RETURN_PCT,
    explosion_definitions,
    is_vol_explosion,
    realized_volatility,
)
from src.evaluation.inflection_backtest import _series, simulate_signal
from src.evaluation.inflection_forward import (
    BENCHMARK_TICKER,
    SnapshotLoadError,
    paired_benchmark_returns,
)
from src.evaluation.regime import regime_labels

LEARNING_HORIZONS = (5, 20, 60, 120)
EXPLOSION_MAX_RETURN_PCT = HORIZON_MAX_RETURN_PCT  # alias kept for existing imports
ROUND_TRIP_COST_PCT = 0.2
PROMOTION_MIN_OBSERVATIONS = 30
PROMOTION_POSITIVE_LIFT = 1.35
PROMOTION_NEGATIVE_LIFT = 0.75
# Benjamini-Hochberg false-discovery rate over every factor x horizon tested in one report.
PROMOTION_MAX_Q_VALUE = 0.10

# Fixed diagnostic bands; they do not change production scores or weights.
AGE_BANDS = ((31.0, 61.0, 91.0), ("le30", "31to60", "61to90", "gt90"))  # ages are whole calendar days
GROWTH_BANDS = ((-10.0, 0.0, 10.0), ("lt-10", "-10to0", "0to10", "ge10"))
FEATURE_BANDS: dict[str, tuple[str, tuple[float, ...], tuple[str, ...]]] = {
    "disclosure_age_days": ("disclosure_age_band", *AGE_BANDS),
    "forecast_age_days": ("forecast_age_band", *AGE_BANDS),
    "up_day_ratio_60d": ("up_day_ratio_60d_band", (0.4, 0.5, 0.6), ("lt0.4", "0.4to0.5", "0.5to0.6", "ge0.6")),
    "max_daily_return_20d_pct": ("max_daily_return_20d_band", (5.0, 10.0, 20.0), ("lt5", "5to10", "10to20", "ge20")),
    "daily_volatility_20d_pct": ("daily_volatility_20d_band", (2.0, 4.0, 6.0), ("lt2", "2to4", "4to6", "ge6")),
    "distance_from_period_high_pct": (
        "distance_from_period_high_band", (-20.0, -10.0, -5.0), ("lt-20", "-20to-10", "-10to-5", "ge-5")
    ),
    "quarterly_sales_growth_accel_pctpt": ("quarterly_sales_growth_accel_band", *GROWTH_BANDS),
    "quarterly_op_growth_accel_pctpt": ("quarterly_op_growth_accel_band", *GROWTH_BANDS),
    "relative_return_20d_vs_sector_pct": ("relative_return_20d_vs_sector_band", *GROWTH_BANDS),
    "relative_return_60d_vs_sector_pct": ("relative_return_60d_vs_sector_band", *GROWTH_BANDS),
}

# schema 3 (jp-inflection-shadow-v2) used a single breakout_52w flag; schema 4
# (jp-inflection-shadow-v3+) split it into near_52w_high/near_listing_high. Both
# are accepted so old snapshots remain usable as learning material, but schema 3
# rows never populate the schema-4 fields (or vice versa) so the two are never
# silently conflated. Schema 5 keeps the schema-4 candidate fields and adds raw
# features, score details, pre_score and sector (plus a control sample that this
# loader intentionally does not read yet).
LEGACY_SCHEMA_VERSION = 3
NEAR_HIGH_FLAGS_SINCE_SCHEMA = 4
RAW_FEATURES_SINCE_SCHEMA = 5
CURRENT_SCHEMA_VERSION = 5
SUPPORTED_SCHEMA_VERSIONS = (LEGACY_SCHEMA_VERSION, 4, CURRENT_SCHEMA_VERSION)


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def load_inflection_learning_observations(
    snapshot_dir: Path,
    *,
    encryption_secret: str,
) -> list[dict[str, Any]]:
    """Load every deep-scan candidate, not only EARLY_CANDIDATE signals.

    Strategy versions are retained per observation so learning survives strategy
    upgrades. Schema 3 (legacy breakout_52w) and schema 4 (near_52w_high /
    near_listing_high) are both supported; a schema-3 row never populates the
    schema-4 fields and vice versa, so their differing definitions are never
    conflated. New candidate schema changes must also be reflected here and in
    ``load_inflection_signals``.
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
        source_commit = payload.get("source_commit_sha")
        schema_version = payload.get("report_schema_version")
        market_date = str(payload.get("latest_price_date") or "")
        storage = payload.get("storage")
        if (
            not strategy_version
            or not isinstance(source_commit, str)
            or not source_commit
            or isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version not in SUPPORTED_SCHEMA_VERSIONS
            or market_date != path.stem
            or not isinstance(storage, dict)
            or storage.get("encrypted") is not True
            or storage.get("snapshot_date_basis") != "latest_price_date"
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
            raw_score = candidate.get("score")
            if isinstance(raw_score, bool) or raw_score is None:
                raise SnapshotLoadError(f"Invalid candidate score: {path.name}:{ticker}")
            try:
                score = float(raw_score)
            except (TypeError, ValueError) as exc:
                raise SnapshotLoadError(f"Invalid candidate score: {path.name}:{ticker}") from exc
            if not ticker or not classification:
                raise SnapshotLoadError(f"Candidate identity/score missing: {path.name}")
            if not isfinite(score) or not 0.0 <= score <= 100.0:
                raise SnapshotLoadError(f"Invalid candidate score: {path.name}:{ticker}")
            if schema_version >= NEAR_HIGH_FLAGS_SINCE_SCHEMA:
                near_52w_high = candidate.get("near_52w_high")
                near_listing_high = candidate.get("near_listing_high")
                if not isinstance(near_52w_high, bool) or not isinstance(near_listing_high, bool):
                    raise SnapshotLoadError(f"Invalid candidate high-proximity flags: {path.name}")
                legacy_breakout_52w = None
            else:
                legacy_breakout_52w = candidate.get("breakout_52w")
                if not isinstance(legacy_breakout_52w, bool):
                    raise SnapshotLoadError(f"Invalid legacy candidate breakout flag: {path.name}")
                near_52w_high = None
                near_listing_high = None
            features = score_details = pre_score = sector33_code = None
            if schema_version >= RAW_FEATURES_SINCE_SCHEMA:
                features = candidate.get("features")
                score_details = candidate.get("score_details")
                pre_score = candidate.get("pre_score")
                if (
                    not isinstance(features, dict)
                    or not isinstance(score_details, dict)
                    or not is_finite_number(pre_score)
                ):
                    raise SnapshotLoadError(f"Invalid schema-5 candidate fields: {path.name}:{ticker}")
                sector33_code = candidate.get("sector33_code")
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
                "near_52w_high": near_52w_high,
                "near_listing_high": near_listing_high,
                "legacy_breakout_52w": legacy_breakout_52w,
                "avg_turnover_20d_jpy": _optional_float(candidate.get("avg_turnover_20d_jpy")),
                "reasons": [str(value) for value in reasons] if isinstance(reasons, list) else [],
                "features": features,
                "score_details": score_details,
                "pre_score": float(pre_score) if pre_score is not None else None,
                "sector33_code": str(sector33_code) if sector33_code else None,
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
    near_52w_high = observation.get("near_52w_high")
    if near_52w_high is not None:
        labels.append(f"near_52w_high:{bool(near_52w_high)}")
    near_listing_high = observation.get("near_listing_high")
    if near_listing_high is not None:
        labels.append(f"near_listing_high:{bool(near_listing_high)}")
    legacy_breakout_52w = observation.get("legacy_breakout_52w")
    if legacy_breakout_52w is not None:
        labels.append(f"legacy_breakout_52w:{bool(legacy_breakout_52w)}")
    for reason in observation.get("reasons", []):
        labels.append(f"reason:{reason}")
    features = observation.get("features")
    if isinstance(features, dict):
        for key, (label, cuts, bands) in FEATURE_BANDS.items():
            value = features.get(key)
            if value is not None and is_finite_number(value):
                labels.append(f"{label}:{_bucket(float(value), cuts, bands)}")
    sector = observation.get("sector33_code")
    if isinstance(sector, str) and sector.strip():
        labels.append(f"sector33:{sector}")
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
    if row.get("near_52w_high"):
        reasons.append("near_52w_high_failed_to_outperform")
    if row.get("near_listing_high"):
        reasons.append("near_listing_high_failed_to_outperform")
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
    benchmark_closes = _series(benchmark_history, "Close")
    trades_by_horizon = {
        horizon: [
            simulate_signal(
                observation,
                histories.get(str(observation["ticker"]), pd.DataFrame()),
                holding_days=horizon,
                round_trip_cost_pct=round_trip_cost_pct,
                apply_tax=False,
            )
            for observation in observation_rows
        ]
        for horizon in horizons
    }
    benchmarks_by_horizon = {
        horizon: paired_benchmark_returns(
            trades_by_horizon[horizon],
            benchmark_history,
            round_trip_cost_pct=round_trip_cost_pct,
        )
        for horizon in horizons
    }

    evaluated: list[dict[str, Any]] = []
    for index, observation in enumerate(observation_rows):
        row = dict(observation)
        sigma = realized_volatility(
            _series(histories.get(str(observation["ticker"]), pd.DataFrame()), "Close"),
            str(observation["signal_date"]),
        )
        row["realized_volatility_60d"] = sigma
        outcomes: dict[str, Any] = {}
        explosion_horizons: list[int] = []
        for horizon in horizons:
            trade = trades_by_horizon[horizon][index]
            benchmark = benchmarks_by_horizon[horizon][index]
            benchmark_return = benchmark["benchmark_net_return_pct"]
            trade_return = trade.net_return_pct
            completed = trade_return is not None
            max_return = trade.max_return_pct
            is_explosion = bool(
                completed and max_return is not None and float(max_return) >= EXPLOSION_MAX_RETURN_PCT[horizon]
            )
            if is_explosion:
                explosion_horizons.append(horizon)
            outcomes[f"h{horizon}"] = {
                "completed": completed,
                "entry_date": trade.entry_date,
                "exit_date": trade.exit_date,
                "net_return_pct": trade_return,
                "benchmark_entry_date": benchmark["benchmark_entry_date"],
                "benchmark_exit_date": benchmark["benchmark_exit_date"],
                "benchmark_net_return_pct": benchmark_return,
                "excess_return_pct": benchmark["excess_return_pct"],
                "max_return_pct": max_return,
                "mfe_pct": trade.mfe_pct,
                "mae_pct": trade.mae_pct,
                "explosion_threshold_pct": EXPLOSION_MAX_RETURN_PCT[horizon],
                "explosive": is_explosion,
                # Diagnostic only; None while the horizon is incomplete or the history is short.
                "vol_explosive": is_vol_explosion(max_return, sigma, horizon) if completed else None,
            }
        row["horizons"] = outcomes
        regimes = regime_labels(benchmark_closes, str(observation["signal_date"]))
        row["regime_trend"] = regimes["trend"]
        row["regime_volatility"] = regimes["volatility"]
        row["factor_labels"] = [
            *factor_labels(observation),
            f"regime_trend:{regimes['trend']}",
            f"regime_vol:{regimes['volatility']}",
        ]
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

    def entry_key(item: dict[str, Any]) -> tuple[str, str, str]:
        outcome = item.get("horizons", {}).get(key, {})
        return (str(outcome.get("entry_date") or ""), str(item["ticker"]), str(item["signal_date"]))

    for row in sorted(rows, key=entry_key):
        outcome = row.get("horizons", {}).get(key, {})
        if not outcome.get("completed") or not outcome.get("entry_date") or not outcome.get("exit_date"):
            continue
        ticker = str(row["ticker"])
        entry_date = str(outcome["entry_date"])
        if entry_date <= occupied_until.get(ticker, ""):
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


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p-value for the 2x2 table [[a, b], [c, d]] (standard library only).

    Sums the probability of every table with the same margins that is no more likely than the
    observed one (relative tolerance 1e-7, as scipy does).
    """
    if min(a, b, c, d) < 0:
        raise ValueError("counts must not be negative")
    row1, row2, col1 = a + b, c + d, a + c
    total = row1 + row2
    if total == 0:
        return 1.0
    low, high = max(0, col1 - row2), min(row1, col1)
    weights = {x: math.comb(row1, x) * math.comb(row2, col1 - x) for x in range(low, high + 1)}
    observed = weights[a]
    tolerance = 10**7
    favourable = sum(weight for weight in weights.values() if weight * tolerance <= observed * (tolerance + 1))
    return min(1.0, favourable / math.comb(total, col1))


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    """BH-adjusted q-values, returned in the input order (monotone, capped at 1)."""
    count = len(p_values)
    order = sorted(range(count), key=lambda index: p_values[index])
    adjusted = [0.0] * count
    running_min = 1.0
    for rank in range(count, 0, -1):
        index = order[rank - 1]
        running_min = min(running_min, p_values[index] * count / rank)
        adjusted[index] = running_min
    return adjusted


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for a proportion; ``None`` when there are no observations."""
    if n <= 0:
        return None
    proportion = successes / n
    denominator = 1.0 + z * z / n
    centre = (proportion + z * z / (2 * n)) / denominator
    half = z * math.sqrt(proportion * (1.0 - proportion) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


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
    total_rows = len(rows)
    total_explosions = sum(bool(row["horizons"][key].get("explosive")) for row in rows)
    stats: list[dict[str, Any]] = []
    for label, factor_rows in grouped.items():
        excess = [
            float(row["horizons"][key]["excess_return_pct"])
            for row in factor_rows
            if row["horizons"][key].get("excess_return_pct") is not None
        ]
        explosions = [bool(row["horizons"][key].get("explosive")) for row in factor_rows]
        rate = sum(explosions) / len(explosions) * 100.0 if explosions else 0.0
        # 2x2 table: factor present/absent x exploded/not, over the same independent observations.
        others = total_rows - len(factor_rows)
        fisher_p = None
        if factor_rows and others > 0:
            others_exploded = total_explosions - sum(explosions)
            fisher_p = fisher_exact_two_sided(
                sum(explosions), len(explosions) - sum(explosions), others_exploded, others - others_exploded
            )
        interval = wilson_interval(sum(explosions), len(explosions))
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
                "explosion_rate_ci95": (
                    [round(interval[0] * 100.0, 3), round(interval[1] * 100.0, 3)] if interval else None
                ),
                # 6 significant digits keep tiny p-values meaningful (a fixed-decimal round would flatten them).
                "fisher_p_value": float(f"{fisher_p:.6g}") if fisher_p is not None else None,
                "bh_q_value": None,
                "uncorrected_direction": direction,
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


def _status_sort_key(item: dict[str, Any]) -> tuple[bool, int, str]:
    return (
        item["promotion_status"] == "hold",
        -int(item["independent_observations"]),
        str(item["factor"]),
    )


def _apply_multiple_testing(factors_by_horizon: dict[str, list[dict[str, Any]]]) -> int:
    """Gate promotions on a Benjamini-Hochberg q-value over the whole factor x horizon family.

    Returns the number of tests in the family. A candidate whose q-value is missing or above
    ``PROMOTION_MAX_Q_VALUE`` is demoted to ``hold`` (its ``uncorrected_direction`` is kept).
    """
    tested = [stat for stats in factors_by_horizon.values() for stat in stats if stat["fisher_p_value"] is not None]
    for stat, q_value in zip(
        tested, benjamini_hochberg([float(stat["fisher_p_value"]) for stat in tested]), strict=True
    ):
        stat["bh_q_value"] = q_value
    for stats in factors_by_horizon.values():
        for stat in stats:
            q_value = stat["bh_q_value"]
            if stat["promotion_status"] != "hold" and (q_value is None or q_value > PROMOTION_MAX_Q_VALUE):
                stat["promotion_status"] = "hold"
            if q_value is not None:
                stat["bh_q_value"] = round(q_value, 6)
        stats.sort(key=_status_sort_key)
    return len(tested)


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
                    "fisher_p_value": factor["fisher_p_value"],
                    "bh_q_value": factor["bh_q_value"],
                    "action": "candidate_for_next_strategy_version_not_auto_applied",
                }
            )
    return promoted[:20]


def build_learning_report(
    observations: list[dict[str, Any]],
    histories: dict[str, pd.DataFrame],
    benchmark_history: pd.DataFrame,
    *,
    promotion_strategy_version: str,
) -> dict[str, Any]:
    """Build cumulative knowledge from every strategy, but gate promotions on
    ``promotion_strategy_version`` only. This must be passed explicitly (e.g. the
    current production strategy) rather than inferred from the newest observation,
    since a stale or legacy snapshot with a later signal_date would otherwise
    silently become the promotion target.
    """
    evaluated = evaluate_learning_observations(observations, histories, benchmark_history)
    strategy_versions = sorted(
        {str(row.get("strategy_version") or "") for row in observations if row.get("strategy_version")}
    )
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
    promotion_rows = [row for row in evaluated if row.get("strategy_version") == promotion_strategy_version]

    for horizon in LEARNING_HORIZONS:
        horizon_key = f"h{horizon}"
        independent = _independent_rows(evaluated, horizon)
        baseline = _horizon_summary(independent, horizon)
        baselines[horizon_key] = baseline
        independent_counts[horizon_key] = len(independent)
        factors[horizon_key] = _factor_statistics(independent, horizon=horizon, baseline=baseline)

        latest_independent = _independent_rows(promotion_rows, horizon)
        promotion_baseline = _horizon_summary(latest_independent, horizon)
        promotion_baselines[horizon_key] = promotion_baseline
        promotion_counts[horizon_key] = len(latest_independent)
        promotion_factors[horizon_key] = _factor_statistics(
            latest_independent,
            horizon=horizon,
            baseline=promotion_baseline,
        )
    # Promotion is gated by a family-wide BH q-value, so it can only be decided after every horizon.
    tests_in_family = _apply_multiple_testing(promotion_factors)

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
        "promotion_scope_strategy_version": promotion_strategy_version,
        "observation_count": len(observations),
        "learning_unit": "same-ticker observations are de-overlapped independently per horizon",
        "horizons": list(LEARNING_HORIZONS),
        "explosion_definitions": explosion_definitions(),
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
            "maximum_bh_q_value": PROMOTION_MAX_Q_VALUE,
            "test": "fisher_exact_two_sided (factor present vs absent, exploded vs not)",
            "correction": "benjamini_hochberg over every factor x horizon with a computable table",
            "tests_in_family": tests_in_family,
            "automatic_production_weight_update": False,
            "scope": "explicit_promotion_strategy_version_only",
            "reason": "prevent small-sample overfitting, policy-confounding and self-reinforcing strategy drift",
        },
        "limitations": [
            "Learns only from the deep-scan candidates stored in historical snapshots; stocks outside that pool are invisible.",
            "Separate near-52-week and near-listing-high factors may take longer to reach the promotion sample threshold.",
            "Factor attribution is associative, not proof of causality.",
            "Cumulative factor statistics may span multiple strategy versions; promotion decisions use only the explicitly configured promotion strategy version.",
            "Statuses in the cumulative factor_statistics are uncorrected and informational; only promotion_factor_statistics is gated by the BH q-value.",
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
        "price_unavailable_ticker_count",
        "learning_unit",
        "horizons",
        "explosion_definition_max_return_pct",
        "explosion_definitions",
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
