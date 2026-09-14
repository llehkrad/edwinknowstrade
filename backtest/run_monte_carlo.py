"""
CLI entry point for Monte Carlo resampling on a completed backtest run.

Reads backtest_results/fills.csv (from a prior `python -m backtest.run_backtest`
run), resamples the realized round-trip PnLs thousands of times, and reports
the resulting distribution of returns and drawdowns -- see monte_carlo.py's
docstring for what this does and doesn't tell you.

Usage:
    python -m backtest.run_monte_carlo
    python -m backtest.run_monte_carlo --num-simulations 5000 --method shuffle
"""
import argparse
import os

import pandas as pd

import config
from backtest.monte_carlo import extract_trade_pnls, print_summary, simulate

DEFAULT_RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "backtest_results")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--equity", type=float, default=config.ACCOUNT_EQUITY_USD)
    parser.add_argument("--num-simulations", type=int, default=2000)
    parser.add_argument("--method", choices=["bootstrap", "shuffle"], default="bootstrap")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    fills_path = os.path.join(args.results_dir, "fills.csv")
    fills = pd.read_csv(fills_path)
    trade_pnls = extract_trade_pnls(fills)

    result = simulate(
        trade_pnls,
        starting_equity=args.equity,
        num_simulations=args.num_simulations,
        method=args.method,
        seed=args.seed,
    )
    print_summary(result)

    out_path = os.path.join(args.results_dir, "monte_carlo.csv")
    pd.DataFrame({
        "final_equity": result["final_equities"],
        "max_drawdown_pct": result["max_drawdowns"],
    }).to_csv(out_path, index=False)
    print(f"\nSaved per-simulation results to {os.path.abspath(out_path)}")


if __name__ == "__main__":
    main()
