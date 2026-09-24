"""
Parameter sweep across FIXED stop-loss % and take-profit ratio combinations,
using config.STOP_LOSS_MODE = 'fixed_pct' (bot/risk_manager.py already
respects this). This is a direct extension of
backtest/validate_fixed_pct_exits.py (read that one first -- it is this
script's template) which only tested a single 5% stop / 3:1 (15% TP) combo
and found trades far too rare on SPY (1 trade in the whole OOS window) to
trust the result.

This script sweeps:
    config.FIXED_STOP_LOSS_PCT in [0.005, 0.01, 0.015]   (0.5%, 1.0%, 1.5%)
    config.TAKE_PROFIT_RATIO   in [2.0, 3.0]             (2:1, 3:1)
-> 6 stop/TP combinations:
    0.5%/1.0% TP, 0.5%/1.5% TP, 1.0%/2.0% TP, 1.0%/3.0% TP,
    1.5%/3.0% TP, 1.5%/4.5% TP  (TP distance = stop_pct * ratio)

crossed with the same 5 strategies (mean_reversion_only, vwap_reversion_only,
orb_only, rsi_reversion_only, bb_squeeze_only) and 5 symbols
(SPY, QQQ, IWM, TSLA, GOOGL) used throughout this repo's bracket-exit work.

Per explicit operator instruction: NO buy-and-hold comparison, no verdict
labels -- raw numbers only (return %, profit factor, trade count, win rate).

SIMPLIFICATION vs. validate_fixed_pct_exits.py: to keep this 6x-larger sweep's
output manageable, only the SINGLE best in-sample entry-param combo (rank #1
by in-sample return) is re-tested out-of-sample for each
symbol/strategy/stop-TP-combo cell -- not the top-3. Everything else
(in-sample/out-of-sample time split: first half of 1yr 15-min data in-sample,
second half out-of-sample, per symbol; each strategy's own entry-parameter
grid search performed in-sample under every stop/TP combo) matches
validate_fixed_pct_exits.py exactly.

Run: python -m backtest.validate_fixed_pct_sweep
     python -m backtest.validate_fixed_pct_sweep --symbols SPY QQQ --strategy mean_reversion_only
"""
import argparse
import itertools

import config
from backtest.data import load_universe
from backtest.engine import run_backtest
from backtest.metrics import summarize
from backtest.validate_fixed_pct_exits import ENTRY_GRIDS, full_grid

SYMBOLS = ["SPY", "QQQ", "IWM", "TSLA", "GOOGL"]
STRATEGIES = list(ENTRY_GRIDS)

STOP_PCTS = [0.005, 0.01, 0.015]
TP_RATIOS = [2.0, 3.0]
STOP_TP_COMBOS = [(sp, tp) for sp in STOP_PCTS for tp in TP_RATIOS]


def combo_label(stop_pct, tp_ratio):
    tp_pct = stop_pct * tp_ratio
    return f"{stop_pct * 100:.1f}%SL/{tp_pct * 100:.1f}%TP({tp_ratio:.0f}:1)"


def split_in_out(df):
    mid = len(df) // 2
    return df.iloc[:mid], df.iloc[mid:]


def run_grid_search(strategy_set, stop_pct, tp_ratio, data, daily_data):
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
    config.FIXED_STOP_LOSS_PCT = stop_pct
    config.TAKE_PROFIT_RATIO = tp_ratio

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


def validate_one(strategy_set, symbol, stop_pct, tp_ratio, full, daily_data, out_rows):
    label = combo_label(stop_pct, tp_ratio)
    in_sample, out_sample = split_in_out(full)

    print(f"\n--- {symbol} / {strategy_set} / {label} ---")

    in_data = {symbol: in_sample}
    results, param_names = run_grid_search(strategy_set, stop_pct, tp_ratio, in_data, daily_data)

    if not results:
        print("No valid combos.")
        return

    best = results[0]
    params = {k: v for k, v in best.items() if k in param_names}

    original = {name: getattr(config, name) for name in param_names}
    original_strategy_set = config.STRATEGY_SET
    original_fixed = {
        "STOP_LOSS_MODE": config.STOP_LOSS_MODE,
        "FIXED_STOP_LOSS_PCT": config.FIXED_STOP_LOSS_PCT,
        "TAKE_PROFIT_RATIO": config.TAKE_PROFIT_RATIO,
    }

    config.STRATEGY_SET = strategy_set
    config.STOP_LOSS_MODE = "fixed_pct"
    config.FIXED_STOP_LOSS_PCT = stop_pct
    config.TAKE_PROFIT_RATIO = tp_ratio
    for name, value in params.items():
        setattr(config, name, value)

    out_data = {symbol: out_sample}
    out_result = run_backtest(
        out_data, starting_equity=config.ACCOUNT_EQUITY_USD, daily_data=daily_data,
        use_bracket_exits=True,
    )
    out_summary = summarize(out_result, starting_equity=config.ACCOUNT_EQUITY_USD)

    in_return = best.get("total_return_pct")
    in_pf = best.get("profit_factor")
    out_return = out_summary.get("total_return_pct")
    out_pf = out_summary.get("profit_factor")
    out_trades = out_summary.get("num_round_trips")
    out_win_rate = out_summary.get("win_rate")

    print(f"  BEST {params}")
    print(f"      in-sample:  return={in_return:.2%} pf={in_pf}")
    print(f"      out-sample: return={out_return:.2%} pf={out_pf} trades={out_trades} "
          f"win_rate={out_win_rate:.2%}")

    out_rows.append({
        "symbol": symbol, "strategy": strategy_set, "stop_pct": stop_pct, "tp_ratio": tp_ratio,
        "label": label, "params": params,
        "in_return": in_return, "in_pf": in_pf,
        "out_return": out_return, "out_pf": out_pf, "out_trades": out_trades,
        "out_win_rate": out_win_rate,
    })

    config.STRATEGY_SET = original_strategy_set
    for name, value in original.items():
        setattr(config, name, value)
    for name, value in original_fixed.items():
        setattr(config, name, value)


def print_summary(out_rows):
    print(f"\n\n{'=' * 120}")
    print("SUMMARY -- fixed stop-loss %% / take-profit ratio sweep, best in-sample entry-param")
    print("combo per symbol/strategy/stop-TP-combo, re-tested out-of-sample.")
    print("Raw numbers only, no buy-and-hold comparison.")
    print(f"{'=' * 120}")

    labels = [combo_label(sp, tp) for sp, tp in STOP_TP_COMBOS]

    # Return% table: rows = symbol/strategy, columns = stop/TP combos
    print("\n--- OOS RETURN %% (rows = symbol/strategy, columns = stop/TP combo) ---")
    header = f"{'symbol':<7} {'strategy':<22} " + " ".join(f"{l:>16}" for l in labels)
    print(header)
    by_key = {(r["symbol"], r["strategy"], r["label"]): r for r in out_rows}
    for symbol in SYMBOLS:
        for strategy in STRATEGIES:
            cells = []
            for label in labels:
                r = by_key.get((symbol, strategy, label))
                cells.append(f"{r['out_return']:>15.2%} " if r else f"{'n/a':>15} ")
            print(f"{symbol:<7} {strategy:<22} " + "".join(cells))

    # Trade count table
    print("\n--- OOS TRADE COUNT (rows = symbol/strategy, columns = stop/TP combo) ---")
    print(header)
    for symbol in SYMBOLS:
        for strategy in STRATEGIES:
            cells = []
            for label in labels:
                r = by_key.get((symbol, strategy, label))
                cells.append(f"{r['out_trades']:>15} " if r else f"{'n/a':>15} ")
            print(f"{symbol:<7} {strategy:<22} " + "".join(cells))

    # Profit factor table
    print("\n--- OOS PROFIT FACTOR (rows = symbol/strategy, columns = stop/TP combo) ---")
    print(header)
    for symbol in SYMBOLS:
        for strategy in STRATEGIES:
            cells = []
            for label in labels:
                r = by_key.get((symbol, strategy, label))
                if r:
                    pf = r["out_pf"]
                    pf_str = f"{pf:.2f}" if pf not in (None, float("inf")) else str(pf)
                else:
                    pf_str = "n/a"
                cells.append(f"{pf_str:>15} ")
            print(f"{symbol:<7} {strategy:<22} " + "".join(cells))

    # Win rate table
    print("\n--- OOS WIN RATE %% (rows = symbol/strategy, columns = stop/TP combo) ---")
    print(header)
    for symbol in SYMBOLS:
        for strategy in STRATEGIES:
            cells = []
            for label in labels:
                r = by_key.get((symbol, strategy, label))
                cells.append(f"{r['out_win_rate']:>15.2%} " if r else f"{'n/a':>15} ")
            print(f"{symbol:<7} {strategy:<22} " + "".join(cells))

    # Flat detail table too, for grep-ability
    print("\n--- FLAT DETAIL TABLE ---")
    dh = (f"{'symbol':<7} {'strategy':<22} {'combo':<18} {'params':<50} "
          f"{'oos_ret':>9} {'oos_pf':>8} {'trades':>7} {'win_rate':>9}")
    print(dh)
    for r in out_rows:
        pf_str = f"{r['out_pf']:.2f}" if r["out_pf"] not in (None, float("inf")) else str(r["out_pf"])
        print(f"{r['symbol']:<7} {r['strategy']:<22} {r['label']:<18} {str(r['params']):<50} "
              f"{r['out_return']:>8.2%} {pf_str:>8} {r['out_trades']:>7} {r['out_win_rate']:>8.2%}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=SYMBOLS)
    parser.add_argument("--strategy", default="all", choices=STRATEGIES + ["all"])
    args = parser.parse_args()

    strategies = STRATEGIES if args.strategy == "all" else [args.strategy]

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
            for stop_pct, tp_ratio in STOP_TP_COMBOS:
                validate_one(strategy_set, symbol, stop_pct, tp_ratio, full, daily_data, out_rows)

        # Print a running summary after each symbol so partial progress is
        # always visible in the log if this run is interrupted.
        print(f"\n\n>>> Running summary after completing symbol {symbol} <<<")
        print_summary(out_rows)

    print("\n\nFINAL:")
    print_summary(out_rows)


if __name__ == "__main__":
    main()
