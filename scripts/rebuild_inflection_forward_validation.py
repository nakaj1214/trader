from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.forward_validation import fetch_histories_yfinance
from src.evaluation.inflection_backtest import simulate_signals, summarize_trades
from src.evaluation.inflection_forward import load_inflection_signals

ROUND_TRIP_COST_PCT = 0.2
TAX_RATE_PCT = 20.315


def main() -> int:
    parser = argparse.ArgumentParser(description="Forward-validate immutable JP inflection snapshots.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--snapshot-dir", default="dashboard/data/inflection")
    parser.add_argument("--output", default="artifacts/inflection_forward_validation.json")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    signals = load_inflection_signals(repo_root / args.snapshot_dir)
    if not signals:
        print("No immutable EARLY_CANDIDATE snapshots available yet; nothing to validate.")
        return 0

    histories = fetch_histories_yfinance(signals, max_horizon=60)
    report: dict[str, object] = {
        "signal_count": len(signals),
        "entry_rule": "next_trading_day_open",
        "round_trip_cost_pct": ROUND_TRIP_COST_PCT,
        "jquants_delay_note": "Free-tier delayed fundamentals are evaluated as the signals actually observed at the time.",
        "horizons": {},
    }
    horizons: dict[str, object] = {}
    for holding_days in (5, 20, 60):
        trades = simulate_signals(
            signals,
            histories,
            holding_days=holding_days,
            round_trip_cost_pct=ROUND_TRIP_COST_PCT,
            tax_rate_pct=TAX_RATE_PCT,
            apply_tax=False,
        )
        horizons[f"h{holding_days}"] = {
            "summary": summarize_trades(trades),
            "trades": [trade.as_dict() for trade in trades],
        }
    report["horizons"] = horizons

    output = repo_root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"signal_count": len(signals), "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
