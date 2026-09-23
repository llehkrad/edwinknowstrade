"""
Momentum (trend_following) validation for single-stock candidates, with a
mandatory buy-and-hold benchmark on the SAME out-of-sample window.

Why the buy-and-hold check is mandatory, not optional: the project already
has one false-positive lesson on exactly this mistake (see CLAUDE.md
2026-09-18 "pairs trading and momentum rotation both ruled out for QQQ") --
a cross-sectional momentum rotation backtest on SPY/QQQ/IWM looked like a
huge out-of-sample win (+9% to +14.5%) until checked against simple
buy-and-hold on the same window (13.6%-17.9%), which revealed the apparent
edge was pure market beta from a rally, not real signal. Any momentum
result here must beat buy-and-hold, not just beat zero, to count as a real
candidate.

Methodology matches backtest/validate_new_symbols.py: split 1yr of real
15-min data at the midpoint by time (first half in-sample grid search,
second half out-of-sample, never searched over), per symbol individually.

Run: python -m backtest.validate_momentum --symbols TSLA GOOGL
"""
import argparse

import config
from backtest.data import load_universe
from backtest.engine import run_backtest
from backtest.metrics import summarize
from backtest.optimize import run_grid_search

STRATEGY_SET = "trend_following_only"

# Same grid as the TF_* portion of the sma_zscore grid in optimize.py --
# trend_following only has 2 real params (fast/slow MA) plus the shared
# stop-loss multiplier; ADX_TREND_THRESHOLD is irrelevant here since both
# regime branches map to the same strategy, but optimize.py's GRIDS dict
# for sma_zscore still varies it -- reuse a trimmed version so we don't
# waste time grid-searching a parameter that can't change the outcome.
GRID = {
    "TF_FAST_MA_PERIOD": [5, 10, 20],
    "TF_SLOW_MA_PERIOD": [20, 30, 50],
    "STOP_LOSS_ATR_MULT": [2.0, 3.0, 4.0],
}


def _valid_combo(params):
    return params["TF_FAST_MA_PERIOD"] < params["TF_SLOW_MA_PERIOD"]


def run_grid_search_tf(data, daily_data=None):
    """Same shape as backtest.optimize.run_grid_search but scoped to the
    trimmed trend_following-only GRID above (optimize.py's GRIDS dict
    doesn't have a trend_following_only entry)."""
    import itertools

    original_strategy_set = config.STRATEGY_SET
    original = {name: getattr(config, name) for name in GRID}
    config.STRATEGY_SET = STRATEGY_SET

    results = []
    keys = list(GRID)
    combos = [dict(zip(keys, values)) for values in itertools.product(*GRID.values())]
    combos = [c for c in combos if _valid_combo(c)]

    try:
        for i, params in enumerate(combos):
            for name, value in params.items():
                setattr(config, name, value)

            result = run_backtest(data, starting_equity=config.ACCOUNT_EQUITY_USD, daily_data=daily_data)
            summary = summarize(result, starting_equity=config.ACCOUNT_EQUITY_USD)
            results.append({**params, **{k: v for k, v in summary.items() if not isinstance(v, dict)}})
            print(f"[{i + 1}/{len(combos)}] {params} -> total_return_pct={summary.get('total_return_pct')}")
    finally:
        config.STRATEGY_SET = original_strategy_set
        for name, value in original.items():
            setattr(config, name, value)

    results.sort(key=lambda r: r.get("total_return_pct", float("-inf")), reverse=True)
    return results


def buy_and_hold_return_pct(df):
    first_close = df["close"].iloc[0]
    last_close = df["close"].iloc[-1]
    return (last_close / first_close - 1) * 100


def split_in_out(df):
    mid = len(df) // 2
    return df.iloc[:mid], df.iloc[mid:]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", required=True)
    args = parser.parse_args()

    for symbol in args.symbols:
        print(f"\n{'=' * 70}\n{symbol} -- trend_following_only (momentum)\n{'=' * 70}")

        full = load_universe([symbol], config.BAR_SIZE)[symbol]
        in_sample, out_sample = split_in_out(full)
        print(f"In-sample:  {in_sample.index[0]} -> {in_sample.index[-1]} ({len(in_sample)} bars)")
        print(f"Out-sample: {out_sample.index[0]} -> {out_sample.index[-1]} ({len(out_sample)} bars)")

        bh_return = buy_and_hold_return_pct(out_sample)
        print(f"\nBuy-and-hold return over out-of-sample window: {bh_return:.2f}%  <-- benchmark to beat")

        daily_data = None
        if config.TREND_FILTER_ENABLED:
            try:
                daily_full = load_universe([symbol], config.TREND_FILTER_BAR_SIZE)[symbol]
                daily_data = {symbol: daily_full}
            except FileNotFoundError as e:
                print(f"WARNING: no daily data for trend filter: {e}")

        in_data = {symbol: in_sample}
        results = run_grid_search_tf(in_data, daily_data=daily_data)

        top3 = results[:3]
        if not top3:
            print("No valid combos.")
            continue

        original = {name: getattr(config, name) for name in GRID}
        original_strategy_set = config.STRATEGY_SET

        print(f"\n--- {symbol} out-of-sample results (top 3 in-sample combos) ---")
        for rank, combo in enumerate(top3, 1):
            params = {k: v for k, v in combo.items() if k in GRID}
            config.STRATEGY_SET = STRATEGY_SET
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


if __name__ == "__main__":
    main()
