"""
Out-of-sample validation for a FIXED 5% stop-loss + 3:1 take-profit ratio
(i.e. a 15% take-profit), using config.STOP_LOSS_MODE = 'fixed_pct' instead
of the ATR-based bracket sizing validated in backtest/validate_bracket_exits.py
(this script's direct template -- read that one first).

Per the operator's explicit request for this run: NO buy-and-hold comparison
and NO REAL EDGE / BEATEN BY BUY-AND-HOLD verdict labels. Only raw
gain/loss numbers are reported: out-of-sample return %, profit factor,
trade count, and win rate.

Fixed (not swept) for every combo in this script:
    config.STOP_LOSS_MODE      = "fixed_pct"
    config.FIXED_STOP_LOSS_PCT = 0.05   (5% stop distance from entry)
    config.TAKE_PROFIT_RATIO   = 3.0    (=> 15% take-profit distance)
config.STOP_LOSS_ATR_MULT is irrelevant under fixed_pct mode and is not
swept or set here.

Grid search dimensions: each strategy's own ENTRY-parameter grid, reused
as-is from backtest.validate_bracket_exits.ENTRY_GRIDS but with the
STOP_LOSS_ATR_MULT dimension stripped out (since it does nothing under
fixed_pct mode) -- see _strip_atr_mult() below.

Methodology matches validate_bracket_exits.py: split 1yr of real 15-min
data at the midpoint by TIME (first half in-sample grid search, second
half out-of-sample, never searched over), per symbol individually. Re-test
the top-3 in-sample combos out-of-sample.

Run: python -m backtest.validate_fixed_pct_exits
     python -m backtest.validate_fixed_pct_exits --symbols SPY QQQ --strategy mean_reversion_only
"""
import argparse
import itertools

import config
from backtest.data import load_universe
from backtest.engine import run_backtest
from backtest.metrics import summarize
from backtest.validate_bracket_exits import ENTRY_GRIDS as _BRACKET_ENTRY_GRIDS

FIXED_STOP_LOSS_PCT = 0.05
TAKE_PROFIT_RATIO = 3.0  # 5% * 3 = 15% take-profit


def _strip_atr_mult(grid):
    return {k: v for k, v in grid.items() if k != "STOP_LOSS_ATR_MULT"}


ENTRY_GRIDS = {name: _strip_atr_mult(grid) for name, grid in _BRACKET_ENTRY_GRIDS.items()}

SYMBOLS = ["SPY", "QQQ", "IWM", "TSLA", "GOOGL"]


def _valid_combo(strategy_set, params):
    if strategy_set == "rsi_reversion_only":
        return params["RSI_OVERSOLD"] < params["RSI_OVERBOUGHT"]
    return True


def full_grid(strategy_set):
    grid = ENTRY_GRIDS[strategy_set]
    keys = list(grid)
    combos = [dict(zip(keys, values)) for values in itertools.product(*grid.values())]
    return [c for c in combos if _valid_combo(strategy_set, c)]


def split_in_out(df):
    mid = len(df) // 2
    return df.iloc[:mid], df.iloc[mid:]


def run_grid_search(strategy_set, data, daily_data):
    combos = full_grid(strategy_set)
    param_names = list(ENTRY_GRIDS[strategy_set])

    original_strategy_set = config.STRATEGY_SET
    original = {name: getattr(config, name) for name in param_names}
    original_fixed = {
        "STOP_LOSS_MODE": config.STOP_LOSS_MODE,
        "FIXED_STOP_LOSS_PCT": config.FIXED_STOP_LOSS_PCT,
        "TAKE_PROFIT_RATIO": config.TAKE_PROFIT_RATIO,
    }
    config.STRATEGY_SET = strategy_set
    config.STOP_LOSS_MODE = "fixed_pct"
    config.FIXED_STOP_LOSS_PCT = FIXED_STOP_LOSS_PCT
    config.TAKE_PROFIT_RATIO = TAKE_PROFIT_RATIO

    results = []
    try:
        for i, params in enumerate(combos):
            for name, value in params.items():
                setattr(config, name, value)

            result = run_backtest(
                data, starting_equity=config.ACCOUNT_EQUITY_USD, daily_data=daily_data,
                use_bracket_exits=True,
            )
            summary = summarize(result, starting_equity=config.ACCOUNT_EQUITY_USD)
            results.append({**params, **{k: v for k, v in summary.items() if not isinstance(v, dict)}})
            print(f"  [{i + 1}/{len(combos)}] {params} -> total_return_pct={summary.get('total_return_pct'):.4f} "
                  f"pf={summary.get('profit_factor')} trades={summary.get('num_round_trips')} "
                  f"win_rate={summary.get('win_rate'):.2%}")
    finally:
        config.STRATEGY_SET = original_strategy_set
        for name, value in original.items():
            setattr(config, name, value)
        for name, value in original_fixed.items():
            setattr(config, name, value)

    results.sort(key=lambda r: r.get("total_return_pct", float("-inf")), reverse=True)
    return results, param_names


def validate_one(strategy_set, symbol, full, daily_data, out_rows):
    in_sample, out_sample = split_in_out(full)

    print(f"\n--- {symbol} / {strategy_set} (fixed 5% SL / 15% TP) ---")

    in_data = {symbol: in_sample}
    results, param_names = run_grid_search(strategy_set, in_data, daily_data)

    top3 = results[:3]
    if not top3:
        print("No valid combos.")
        return

    original = {name: getattr(config, name) for name in param_names}
    original_strategy_set = config.STRATEGY_SET
    original_fixed = {
        "STOP_LOSS_MODE": config.STOP_LOSS_MODE,
        "FIXED_STOP_LOSS_PCT": config.FIXED_STOP_LOSS_PCT,
        "TAKE_PROFIT_RATIO": config.TAKE_PROFIT_RATIO,
    }

    for rank, combo in enumerate(top3, 1):
        params = {k: v for k, v in combo.items() if k in param_names}
        config.STRATEGY_SET = strategy_set
        config.STOP_LOSS_MODE = "fixed_pct"
        config.FIXED_STOP_LOSS_PCT = FIXED_STOP_LOSS_PCT
        config.TAKE_PROFIT_RATIO = TAKE_PROFIT_RATIO
        for name, value in params.items():
            setattr(config, name, value)

        out_data = {symbol: out_sample}
        out_result = run_backtest(
            out_data, starting_equity=config.ACCOUNT_EQUITY_USD, daily_data=daily_data,
            use_bracket_exits=True,
        )
        out_summary = summarize(out_result, starting_equity=config.ACCOUNT_EQUITY_USD)

        in_return = combo.get("total_return_pct")
        in_pf = combo.get("profit_factor")
        out_return = out_summary.get("total_return_pct")
        out_pf = out_summary.get("profit_factor")
        out_trades = out_summary.get("num_round_trips")
        out_win_rate = out_summary.get("win_rate")

        print(f"  #{rank} {params}")
        print(f"      in-sample:  return={in_return:.2%} pf={in_pf}")
        print(f"      out-sample: return={out_return:.2%} pf={out_pf} trades={out_trades} "
              f"win_rate={out_win_rate:.2%}")

        out_rows.append({
            "symbol": symbol, "strategy": strategy_set, "rank": rank, "params": params,
            "in_return": in_return, "in_pf": in_pf,
            "out_return": out_return, "out_pf": out_pf, "out_trades": out_trades,
            "out_win_rate": out_win_rate,
        })

    config.STRATEGY_SET = original_strategy_set
    for name, value in original.items():
        setattr(config, name, value)
    for name, value in original_fixed.items():
        setattr(config, name, value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=SYMBOLS)
    parser.add_argument("--strategy", default="all", choices=list(ENTRY_GRIDS) + ["all"])
    args = parser.parse_args()

    strategies = list(ENTRY_GRIDS) if args.strategy == "all" else [args.strategy]

    out_rows = []
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
            validate_one(strategy_set, symbol, full, daily_data, out_rows)

    print(f"\n\n{'=' * 100}")
    print("SUMMARY TABLE -- fixed 5% stop-loss / 15% take-profit (3:1), best in-sample combo per")
    print("symbol/strategy, re-tested out-of-sample. Raw numbers only, no buy-and-hold comparison.")
    print(f"{'=' * 100}")
    header = (f"{'symbol':<7} {'strategy':<22} {'params':<50} "
              f"{'oos_ret':>9} {'oos_pf':>8} {'trades':>7} {'win_rate':>9}")
    print(header)
    for row in out_rows:
        if row["rank"] != 1:
            continue
        pf_str = f"{row['out_pf']:.2f}" if row["out_pf"] not in (None, float("inf")) else str(row["out_pf"])
        print(f"{row['symbol']:<7} {row['strategy']:<22} {str(row['params']):<50} "
              f"{row['out_return']:>8.2%} {pf_str:>8} {row['out_trades']:>7} {row['out_win_rate']:>8.2%}")


if __name__ == "__main__":
    main()
