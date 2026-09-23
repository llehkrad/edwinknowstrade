"""
Out-of-sample validation for BRACKET-ORDER exits (stop-loss + take-profit,
one-cancels-other -- see config.USE_BRACKET_EXITS / backtest.engine's
use_bracket_exits) -- replacing each strategy's own signal-based EXIT
entirely: once a position enters, it holds until either level is hit, full
stop. Entry signal logic itself is completely unchanged; only what happens
after entry differs from every other validation script in this repo.

Tested strategies: mean_reversion_only, vwap_reversion_only, orb_only,
rsi_reversion_only, bb_squeeze_only (donchian_breakout_only and
trend_following_only skipped, see CLAUDE.md's 2026-09-24 bracket-tp-sl
entry for why).

Grid search dimensions: each strategy's own existing entry-parameter grid
(reused as-is from backtest.validate_strategies.GRIDS for orb/rsi/bb_squeeze;
mean_reversion_only/vwap_reversion_only get an analogous new grid here,
since no *_only grid for them exists elsewhere) x TAKE_PROFIT_RATIO
[2.0, 3.0] -- the new risk:reward dimension this script adds. Each grid
already includes its own STOP_LOSS_ATR_MULT sweep.

Methodology matches every other validation script in this repo
(backtest/validate_new_symbols.py, backtest/validate_strategies.py,
backtest/validate_momentum.py): split 1yr of real 15-min data at the
midpoint by TIME (first half in-sample grid search, second half
out-of-sample, never searched over), per symbol individually. Re-test the
top-3 in-sample combos out-of-sample, and benchmark every out-of-sample
result against simple buy-and-hold on the SAME window -- mandatory, not
optional (see CLAUDE.md's 2026-09-18 QQQ momentum-rotation false-positive
lesson for why: an out-of-sample return above zero is not sufficient
evidence of a real edge on its own).

NOTE on percentage scale: backtest.metrics.summarize()'s "total_return_pct"
is a raw FRACTION (e.g. 0.0066 for +0.66%), not a percent-scaled number.
The existing validate_strategies.py / validate_momentum.py /
validate_new_symbols.py scripts print/compare it directly against a
buy-and-hold figure that IS percent-scaled (computed as
`(last/first - 1) * 100`) -- a scale mismatch that makes their `beats_bh`
comparison compare a fraction like 0.0066 against a percent-scaled number
like 5.2, which is very rarely true unless buy-and-hold itself lost money.
This script keeps everything in fraction form throughout (buy-and-hold
computed WITHOUT the `* 100`) and multiplies by 100 only at print time, so
the beats-buy-and-hold comparison here is computed correctly.

Run: python -m backtest.validate_bracket_exits
     python -m backtest.validate_bracket_exits --symbols SPY QQQ --strategy mean_reversion_only
"""
import argparse
import itertools

import config
from backtest.data import load_universe
from backtest.engine import run_backtest
from backtest.metrics import summarize
from backtest.validate_strategies import GRIDS as _VS_ENTRY_GRIDS

ENTRY_GRIDS = {
    "mean_reversion_only": {
        "MR_MA_PERIOD": [10, 20, 30, 50],
        "MR_ENTRY_STD_DEV": [1.5, 2.0, 2.5],
        "STOP_LOSS_ATR_MULT": [2.0, 3.0, 4.0],
    },
    "vwap_reversion_only": {
        "VWAP_ENTRY_ATR_MULT": [1.0, 1.5, 2.0, 2.5],
        "STOP_LOSS_ATR_MULT": [2.0, 3.0, 4.0],
    },
    # orb_only / rsi_reversion_only / bb_squeeze_only reused as-is from
    # validate_strategies.py -- each already includes its own
    # STOP_LOSS_ATR_MULT sweep.
    "orb_only": _VS_ENTRY_GRIDS["orb_only"],
    "rsi_reversion_only": _VS_ENTRY_GRIDS["rsi_reversion_only"],
    "bb_squeeze_only": _VS_ENTRY_GRIDS["bb_squeeze_only"],
}

TP_RATIO_GRID = {"TAKE_PROFIT_RATIO": [2.0, 3.0]}

SYMBOLS = ["SPY", "QQQ", "IWM", "TSLA", "GOOGL"]


def _valid_combo(strategy_set, params):
    if strategy_set == "rsi_reversion_only":
        return params["RSI_OVERSOLD"] < params["RSI_OVERBOUGHT"]
    return True


def full_grid(strategy_set):
    grid = {**ENTRY_GRIDS[strategy_set], **TP_RATIO_GRID}
    keys = list(grid)
    combos = [dict(zip(keys, values)) for values in itertools.product(*grid.values())]
    return [c for c in combos if _valid_combo(strategy_set, c)]


def buy_and_hold_return_pct(df):
    """Fraction, e.g. 0.0523 for +5.23% -- see module docstring's scale note."""
    first_close = df["close"].iloc[0]
    last_close = df["close"].iloc[-1]
    return last_close / first_close - 1


def split_in_out(df):
    mid = len(df) // 2
    return df.iloc[:mid], df.iloc[mid:]


def run_grid_search(strategy_set, data, daily_data):
    combos = full_grid(strategy_set)
    param_names = list({**ENTRY_GRIDS[strategy_set], **TP_RATIO_GRID})

    original_strategy_set = config.STRATEGY_SET
    original = {name: getattr(config, name) for name in param_names}
    config.STRATEGY_SET = strategy_set

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
                  f"pf={summary.get('profit_factor')} trades={summary.get('num_round_trips')}")
    finally:
        config.STRATEGY_SET = original_strategy_set
        for name, value in original.items():
            setattr(config, name, value)

    results.sort(key=lambda r: r.get("total_return_pct", float("-inf")), reverse=True)
    return results, param_names


def validate_one(strategy_set, symbol, full, daily_data, out_rows):
    in_sample, out_sample = split_in_out(full)

    bh_return = buy_and_hold_return_pct(out_sample)
    print(f"\n--- {symbol} / {strategy_set} (bracket TP/SL) ---")
    print(f"Buy-and-hold return over out-of-sample window: {bh_return:.2%}  <-- benchmark to beat")

    in_data = {symbol: in_sample}
    results, param_names = run_grid_search(strategy_set, in_data, daily_data)

    top3 = results[:3]
    if not top3:
        print("No valid combos.")
        return

    original = {name: getattr(config, name) for name in param_names}
    original_strategy_set = config.STRATEGY_SET

    for rank, combo in enumerate(top3, 1):
        params = {k: v for k, v in combo.items() if k in param_names}
        config.STRATEGY_SET = strategy_set
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

        beats_zero = out_return is not None and out_return > 0
        beats_bh = out_return is not None and out_return > bh_return

        if beats_bh:
            verdict = "REAL EDGE (beats buy-and-hold)"
        elif beats_zero:
            verdict = "POSITIVE BUT BEATEN BY BUY-AND-HOLD (not a real edge)"
        else:
            verdict = "FAILED OOS"

        print(f"  #{rank} {params}")
        print(f"      in-sample:  return={in_return:.2%} pf={in_pf}")
        print(f"      out-sample: return={out_return:.2%} pf={out_pf} trades={out_trades}")
        print(f"      buy-and-hold benchmark: {bh_return:.2%}  -> {verdict}")

        out_rows.append({
            "symbol": symbol, "strategy": strategy_set, "rank": rank, "params": params,
            "in_return": in_return, "in_pf": in_pf,
            "out_return": out_return, "out_pf": out_pf, "out_trades": out_trades,
            "bh_return": bh_return, "verdict": verdict,
        })

    config.STRATEGY_SET = original_strategy_set
    for name, value in original.items():
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

    print(f"\n\n{'=' * 90}\nSUMMARY TABLE (best in-sample combo per symbol/strategy, out-of-sample result)\n{'=' * 90}")
    header = f"{'symbol':<7} {'strategy':<22} {'params':<55} {'oos_ret':>9} {'oos_pf':>8} {'bh_ret':>9}  verdict"
    print(header)
    for row in out_rows:
        if row["rank"] != 1:
            continue
        print(f"{row['symbol']:<7} {row['strategy']:<22} {str(row['params']):<55} "
              f"{row['out_return']:>8.2%} {row['out_pf']:>8.2f} {row['bh_return']:>8.2%}  {row['verdict']}")


if __name__ == "__main__":
    main()
