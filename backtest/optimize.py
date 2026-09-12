"""
Grid search over the Phase 1 strategy parameters that CLAUDE.md flags as
still-to-be-finalized (MA periods, std-dev thresholds, ADX regime threshold).

This is a first-pass parameter search, not a substitute for out-of-sample
validation -- treat results as a shortlist to sanity-check on a holdout
period before trusting any single "best" combo.

Usage:
    python backtest/optimize.py
    python backtest/optimize.py --metric sharpe_ratio --top 5
"""
import argparse
import itertools

import config
from backtest.data import load_universe
from backtest.engine import run_backtest
from backtest.metrics import summarize

PARAM_GRID = {
    "MR_MA_PERIOD": [10, 20, 30],
    "MR_ENTRY_STD_DEV": [1.5, 2.0, 2.5],
    "TF_FAST_MA_PERIOD": [5, 10, 20],
    "TF_SLOW_MA_PERIOD": [20, 30, 50],
    "ADX_TREND_THRESHOLD": [20, 25, 30],
}


def _valid_combo(params: dict) -> bool:
    return params["TF_FAST_MA_PERIOD"] < params["TF_SLOW_MA_PERIOD"]


def run_grid_search(data, metric: str = "total_return_pct", max_drawdown_ceiling: float = None):
    original = {name: getattr(config, name) for name in PARAM_GRID}
    results = []

    keys = list(PARAM_GRID)
    combos = [dict(zip(keys, values)) for values in itertools.product(*PARAM_GRID.values())]
    combos = [c for c in combos if _valid_combo(c)]

    try:
        for i, params in enumerate(combos):
            for name, value in params.items():
                setattr(config, name, value)

            result = run_backtest(data, starting_equity=config.ACCOUNT_EQUITY_USD)
            summary = summarize(result, starting_equity=config.ACCOUNT_EQUITY_USD)

            if max_drawdown_ceiling is not None and summary["max_drawdown_pct"] > max_drawdown_ceiling:
                continue

            results.append({**params, **{k: v for k, v in summary.items() if not isinstance(v, dict)}})
            print(f"[{i + 1}/{len(combos)}] {params} -> {metric}={summary.get(metric)}")
    finally:
        for name, value in original.items():
            setattr(config, name, value)

    results.sort(key=lambda r: r.get(metric, float("-inf")), reverse=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=config.INSTRUMENTS)
    parser.add_argument("--metric", default="total_return_pct",
                         choices=["total_return_pct", "sharpe_ratio", "cagr", "profit_factor"])
    parser.add_argument("--max-drawdown", type=float, default=None,
                         help="Discard combos whose max drawdown exceeds this fraction, e.g. 0.15")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    data = load_universe(args.symbols, config.BAR_SIZE)
    results = run_grid_search(data, metric=args.metric, max_drawdown_ceiling=args.max_drawdown)

    print(f"\n=== Top {args.top} combos by {args.metric} ===")
    for r in results[: args.top]:
        print(r)


if __name__ == "__main__":
    main()
