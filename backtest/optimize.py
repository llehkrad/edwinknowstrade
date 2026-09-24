"""
Grid search over Phase 1 strategy parameters, for either strategy set
(config.STRATEGY_SET) registered in bot/strategy_registry.py.

This is a first-pass parameter search, not a substitute for out-of-sample
validation -- treat results as a shortlist to sanity-check on a holdout
period before trusting any single "best" combo. A "best" combo whose whole
neighborhood is still losing money is not a working strategy -- check
whether the top results are actually profitable, not just least-bad.

Usage:
    python -m backtest.optimize
    python -m backtest.optimize --strategy-set vwap_donchian --metric sharpe_ratio --top 5
"""
import argparse
import itertools

import config
from backtest.data import load_universe
from backtest.engine import run_backtest
from backtest.metrics import summarize

GRIDS = {
    "sma_zscore": {
        "MR_MA_PERIOD": [10, 20, 30],
        "MR_ENTRY_STD_DEV": [1.5, 2.0, 2.5],
        "TF_FAST_MA_PERIOD": [5, 10, 20],
        "TF_SLOW_MA_PERIOD": [20, 30, 50],
        "ADX_TREND_THRESHOLD": [20, 25, 30],
        "STOP_LOSS_ATR_MULT": [2.0, 3.0, 4.0],
    },
    "vwap_donchian": {
        "VWAP_ENTRY_ATR_MULT": [1.0, 1.5, 2.0],
        "VWAP_EXIT_ATR_MULT": [0.2, 0.4],
        "DONCHIAN_ENTRY_PERIOD": [15, 20, 30],
        "DONCHIAN_EXIT_PERIOD": [8, 12],
        "ADX_TREND_THRESHOLD": [20, 25, 30],
        "STOP_LOSS_ATR_MULT": [2.0, 3.0],
    },
}


def _valid_combo(strategy_set: str, params: dict) -> bool:
    if strategy_set == "sma_zscore":
        return params["TF_FAST_MA_PERIOD"] < params["TF_SLOW_MA_PERIOD"]
    if strategy_set == "vwap_donchian":
        return params["DONCHIAN_EXIT_PERIOD"] < params["DONCHIAN_ENTRY_PERIOD"]
    return True


def run_grid_search(data, strategy_set: str, metric: str = "total_return_pct", max_drawdown_ceiling: float = None,
                     daily_data=None):
    grid = GRIDS[strategy_set]
    original_strategy_set = config.STRATEGY_SET
    original = {name: getattr(config, name) for name in grid}
    config.STRATEGY_SET = strategy_set

    results = []
    keys = list(grid)
    combos = [dict(zip(keys, values)) for values in itertools.product(*grid.values())]
    combos = [c for c in combos if _valid_combo(strategy_set, c)]

    try:
        for i, params in enumerate(combos):
            for name, value in params.items():
                setattr(config, name, value)

            result = run_backtest(data, starting_equity=config.ACCOUNT_EQUITY_USD, daily_data=daily_data)
            summary = summarize(result, starting_equity=config.ACCOUNT_EQUITY_USD)

            if max_drawdown_ceiling is not None and summary["max_drawdown_pct"] > max_drawdown_ceiling:
                continue

            results.append({**params, **{k: v for k, v in summary.items() if not isinstance(v, dict)}})
            print(f"[{i + 1}/{len(combos)}] {params} -> {metric}={summary.get(metric)}")
    finally:
        config.STRATEGY_SET = original_strategy_set
        for name, value in original.items():
            setattr(config, name, value)

    results.sort(key=lambda r: r.get(metric, float("-inf")), reverse=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=["SPY", "QQQ", "IWM"])
    parser.add_argument("--strategy-set", default="sma_zscore", choices=list(GRIDS))
    parser.add_argument("--metric", default="total_return_pct",
                         choices=["total_return_pct", "sharpe_ratio", "cagr", "profit_factor"])
    parser.add_argument("--max-drawdown", type=float, default=None,
                         help="Discard combos whose max drawdown exceeds this fraction, e.g. 0.15")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--no-trend-filter", action="store_true",
                         help="Disable the long-term daily trend filter even if config.TREND_FILTER_ENABLED is True")
    args = parser.parse_args()

    data = load_universe(args.symbols, config.BAR_SIZE)

    daily_data = None
    if config.TREND_FILTER_ENABLED and not args.no_trend_filter:
        try:
            daily_data = load_universe(args.symbols, config.TREND_FILTER_BAR_SIZE)
        except FileNotFoundError as e:
            print(f"WARNING: trend filter enabled but daily data missing, running WITHOUT it: {e}")

    results = run_grid_search(data, args.strategy_set, metric=args.metric, max_drawdown_ceiling=args.max_drawdown,
                               daily_data=daily_data)

    print(f"\n=== Top {args.top} combos for strategy_set={args.strategy_set} by {args.metric} ===")
    for r in results[: args.top]:
        print(r)


if __name__ == "__main__":
    main()
