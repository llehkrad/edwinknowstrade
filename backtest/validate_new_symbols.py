"""
Out-of-sample validation for new symbols (TSLA, GOOGL, MSFT, AAPL, NVDA),
same methodology used for SPY/QQQ/IWM (see CLAUDE.md 2026-09-18 entries):

  1. Split each symbol's 1yr of real 15-min data at the midpoint by TIME
     (first half = in-sample, second half = out-of-sample -- the search
     never sees the second half).
  2. Grid-search BOTH strategy sets (sma_zscore, vwap_donchian) on the
     in-sample half, per symbol individually (own best-fit params, not a
     shared universe search -- matches how IWM's edge was found).
  3. Re-test each strategy set's top-3 in-sample combos against the
     out-of-sample half.
  4. A combo only counts as a real candidate if it's profitable
     out-of-sample, not just "least bad" -- report profit factor and
     return for both halves side by side.

Run: python -m backtest.validate_new_symbols
"""
import config
from backtest.data import load_universe
from backtest.engine import run_backtest
from backtest.metrics import summarize
from backtest.optimize import run_grid_search

SYMBOLS = ["TSLA", "GOOGL", "MSFT", "AAPL", "NVDA"]
STRATEGY_SETS = ["sma_zscore", "vwap_donchian"]


def split_in_out(df):
    mid = len(df) // 2
    return df.iloc[:mid], df.iloc[mid:]


def main():
    for symbol in SYMBOLS:
        print(f"\n{'=' * 70}\n{symbol}\n{'=' * 70}")

        full = load_universe([symbol], config.BAR_SIZE)[symbol]
        in_sample, out_sample = split_in_out(full)
        print(f"In-sample:  {in_sample.index[0]} -> {in_sample.index[-1]} ({len(in_sample)} bars)")
        print(f"Out-sample: {out_sample.index[0]} -> {out_sample.index[-1]} ({len(out_sample)} bars)")

        daily_data = None
        if config.TREND_FILTER_ENABLED:
            try:
                daily_full = load_universe([symbol], config.TREND_FILTER_BAR_SIZE)[symbol]
                daily_data = {symbol: daily_full}
            except FileNotFoundError as e:
                print(f"WARNING: no daily data for trend filter: {e}")

        for strategy_set in STRATEGY_SETS:
            print(f"\n--- {symbol} / {strategy_set} ---")

            in_data = {symbol: in_sample}
            results = run_grid_search(in_data, strategy_set, metric="total_return_pct", daily_data=daily_data)

            top3 = results[:3]
            if not top3:
                print("No valid combos.")
                continue

            original = {name: getattr(config, name) for name in top3[0] if hasattr(config, name)}
            original_strategy_set = config.STRATEGY_SET

            for rank, combo in enumerate(top3, 1):
                params = {k: v for k, v in combo.items() if hasattr(config, k)}
                config.STRATEGY_SET = strategy_set
                for name, value in params.items():
                    setattr(config, name, value)

                out_data_slice = {symbol: out_sample}
                daily_slice = daily_data
                out_result = run_backtest(out_data_slice, starting_equity=config.ACCOUNT_EQUITY_USD,
                                           daily_data=daily_slice)
                out_summary = summarize(out_result, starting_equity=config.ACCOUNT_EQUITY_USD)

                in_return = combo.get("total_return_pct")
                in_pf = combo.get("profit_factor")
                out_return = out_summary.get("total_return_pct")
                out_pf = out_summary.get("profit_factor")

                verdict = "REAL EDGE" if (out_return is not None and out_return > 0) else "FAILED OOS"
                print(f"  #{rank} {params}")
                print(f"      in-sample:  return={in_return:.2f}% pf={in_pf}")
                print(f"      out-sample: return={out_return:.2f}% pf={out_pf}  -> {verdict}")

            config.STRATEGY_SET = original_strategy_set
            for name, value in original.items():
                setattr(config, name, value)


if __name__ == "__main__":
    main()
