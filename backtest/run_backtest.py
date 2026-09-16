"""
CLI entry point for running a Phase 1 backtest.

Usage:
    python backtest/run_backtest.py
    python backtest/run_backtest.py --symbols SPY QQQ --start 2025-01-01

Requires cached historical data under data/historical/ -- see
backtest/fetch_ibkr_data.py (real data, needs IB Gateway/TWS) or
backtest/generate_synthetic_data.py (fake data, for smoke-testing the engine).
"""
import argparse
import os

import config
from backtest.data import load_universe
from backtest.engine import run_backtest
from backtest.metrics import print_summary, summarize

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "backtest_results")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=config.INSTRUMENTS)
    parser.add_argument("--bar-size", default=config.BAR_SIZE)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--equity", type=float, default=config.ACCOUNT_EQUITY_USD)
    parser.add_argument("--no-trend-filter", action="store_true",
                         help="Disable the long-term daily trend filter even if config.TREND_FILTER_ENABLED is True")
    args = parser.parse_args()

    data = load_universe(args.symbols, args.bar_size, args.start, args.end)

    daily_data = None
    if config.TREND_FILTER_ENABLED and not args.no_trend_filter:
        try:
            daily_data = load_universe(args.symbols, config.TREND_FILTER_BAR_SIZE)
        except FileNotFoundError as e:
            print(f"WARNING: trend filter enabled but daily data missing, running WITHOUT it: {e}")

    result = run_backtest(data, starting_equity=args.equity, daily_data=daily_data)
    summary = summarize(result, starting_equity=args.equity)
    print_summary(summary)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    result.equity_curve.to_csv(os.path.join(RESULTS_DIR, "equity_curve.csv"))
    result.fills_df().to_csv(os.path.join(RESULTS_DIR, "fills.csv"), index=False)
    print(f"\nSaved equity_curve.csv and fills.csv to {os.path.abspath(RESULTS_DIR)}")


if __name__ == "__main__":
    main()
