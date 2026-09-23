"""
Out-of-sample validation for the 4 new intraday strategies (ORB, RSI
mean-reversion, Bollinger Band squeeze breakout, plus the already-built
trend_following momentum test) on single-stock candidates, all benchmarked
against buy-and-hold on the same window -- same mandatory check as
backtest/validate_momentum.py, for the same reason (see that file's
docstring / CLAUDE.md's QQQ momentum-rotation false-positive lesson).

Methodology matches backtest/validate_new_symbols.py: split 1yr of real
15-min data at the midpoint by time (first half in-sample grid search,
second half out-of-sample, never searched over), per symbol individually.

Run: python -m backtest.validate_strategies --symbols TSLA GOOGL --strategy orb
     python -m backtest.validate_strategies --symbols TSLA GOOGL --strategy all
"""
import argparse
import itertools

import config
from backtest.data import load_universe
from backtest.engine import run_backtest
from backtest.metrics import summarize

GRIDS = {
    "orb_only": {
        "ORB_RANGE_BARS": [1, 2, 4],  # 15min, 30min, 1hr opening range
        "STOP_LOSS_ATR_MULT": [2.0, 3.0, 4.0],
    },
    "rsi_reversion_only": {
        "RSI_PERIOD": [7, 14, 21],
        "RSI_OVERSOLD": [20, 25, 30],
        "RSI_OVERBOUGHT": [70, 75, 80],
        "STOP_LOSS_ATR_MULT": [2.0, 4.0],
    },
    "bb_squeeze_only": {
        "BB_PERIOD": [10, 20],
        "BB_STD_DEV": [1.5, 2.0, 2.5],
        "BB_SQUEEZE_PERCENTILE": [0.1, 0.2, 0.3],
        "STOP_LOSS_ATR_MULT": [2.0, 3.0],
    },
}


def _valid_combo(strategy_set, params):
    if strategy_set == "rsi_reversion_only":
        return params["RSI_OVERSOLD"] < params["RSI_OVERBOUGHT"]
    return True


def buy_and_hold_return_pct(df):
    first_close = df["close"].iloc[0]
    last_close = df["close"].iloc[-1]
    return (last_close / first_close - 1) * 100


def split_in_out(df):
    mid = len(df) // 2
    return df.iloc[:mid], df.iloc[mid:]


def run_grid_search(strategy_set, data, daily_data=None):
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
            results.append({**params, **{k: v for k, v in summary.items() if not isinstance(v, dict)}})
            print(f"  [{i + 1}/{len(combos)}] {params} -> total_return_pct={summary.get('total_return_pct')}")
    finally:
        config.STRATEGY_SET = original_strategy_set
        for name, value in original.items():
            setattr(config, name, value)

    results.sort(key=lambda r: r.get("total_return_pct", float("-inf")), reverse=True)
    return results


def validate_one(strategy_set, symbol, full, daily_data):
    grid = GRIDS[strategy_set]
    in_sample, out_sample = split_in_out(full)

    bh_return = buy_and_hold_return_pct(out_sample)
    print(f"\n--- {symbol} / {strategy_set} ---")
    print(f"Buy-and-hold return over out-of-sample window: {bh_return:.2f}%  <-- benchmark to beat")

    in_data = {symbol: in_sample}
    results = run_grid_search(strategy_set, in_data, daily_data=daily_data)

    top3 = results[:3]
    if not top3:
        print("No valid combos.")
        return

    original = {name: getattr(config, name) for name in grid}
    original_strategy_set = config.STRATEGY_SET

    for rank, combo in enumerate(top3, 1):
        params = {k: v for k, v in combo.items() if k in grid}
        config.STRATEGY_SET = strategy_set
        for name, value in params.items():
            setattr(config, name, value)

        out_data = {symbol: out_sample}
        out_result = run_backtest(out_data, starting_equity=config.ACCOUNT_EQUITY_USD, daily_data=daily_data)
        out_summary = summarize(out_result, starting_equity=config.ACCOUNT_EQUITY_USD)

        in_return = combo.get("total_return_pct")
        in_pf = combo.get("profit_factor")
        out_return = out_summary.get("total_return_pct")
        out_pf = out_summary.get("profit_factor")

        beats_zero = out_return is not None and out_return > 0
        beats_bh = out_return is not None and out_return > bh_return

        if beats_bh:
            verdict = "REAL EDGE (beats buy-and-hold)"
        elif beats_zero:
            verdict = "POSITIVE BUT BEATEN BY BUY-AND-HOLD (not a real edge)"
        else:
            verdict = "FAILED OOS"

        print(f"  #{rank} {params}")
        print(f"      in-sample:  return={in_return:.2f}% pf={in_pf}")
        print(f"      out-sample: return={out_return:.2f}% pf={out_pf}")
        print(f"      buy-and-hold benchmark: {bh_return:.2f}%  -> {verdict}")

    config.STRATEGY_SET = original_strategy_set
    for name, value in original.items():
        setattr(config, name, value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--strategy", default="all", choices=list(GRIDS) + ["all"])
    args = parser.parse_args()

    strategies = list(GRIDS) if args.strategy == "all" else [args.strategy]

    for symbol in args.symbols:
        print(f"\n{'=' * 70}\n{symbol}\n{'=' * 70}")
        full = load_universe([symbol], config.BAR_SIZE)[symbol]
        print(f"Full range: {full.index[0]} -> {full.index[-1]} ({len(full)} bars)")

        daily_data = None
        if config.TREND_FILTER_ENABLED:
            try:
                daily_full = load_universe([symbol], config.TREND_FILTER_BAR_SIZE)[symbol]
                daily_data = {symbol: daily_full}
            except FileNotFoundError as e:
                print(f"WARNING: no daily data for trend filter: {e}")

        for strategy_set in strategies:
            validate_one(strategy_set, symbol, full, daily_data)


if __name__ == "__main__":
    main()
