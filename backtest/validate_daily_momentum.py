"""
Out-of-sample validation for backtest/daily_momentum.py (the 12-1 month
momentum factor on daily bars), same discipline used throughout this
project (see backtest/validate_strategies.py, backtest/validate_new_symbols.py):

  1. Split each symbol's 5yr daily history at the midpoint by TIME
     (first half = in-sample, second half = out-of-sample -- the grid
     search never sees the second half).
  2. Grid-search (formation_days, skip_days, rebalance_days) on the
     in-sample half only, per symbol individually.
  3. Re-test the top-3 in-sample combos against the out-of-sample half.
  4. CRITICAL (per CLAUDE.md's QQQ momentum-rotation false-positive
     lesson): benchmark every out-of-sample result against simple
     buy-and-hold over the SAME out-of-sample window for the SAME symbol.
     A result only counts as a validated edge if it BEATS buy-and-hold,
     not merely if it's positive.

Run: python -m backtest.validate_daily_momentum
     python -m backtest.validate_daily_momentum --symbols SPY QQQ
"""
import argparse
import itertools

import config
from backtest.data import load_universe
from backtest.daily_momentum import run_daily_momentum_backtest
from backtest.metrics import summarize

SYMBOLS = ["SPY", "QQQ", "IWM", "TSLA", "GOOGL"]
BAR_SIZE = "1 day"

GRID = {
    "formation_days": [126, 189, 252],   # ~6mo, ~9mo, ~12mo formation window
    "skip_days": [0, 21],                # 0 = no skip; 21 = standard "12-1" skip-most-recent-month
    "rebalance_days": [21, 63],          # monthly vs quarterly rebalance
}


def buy_and_hold_return_pct(df):
    first_close = df["close"].iloc[0]
    last_close = df["close"].iloc[-1]
    return (last_close / first_close - 1) * 100


def split_in_out(df):
    mid = len(df) // 2
    return df.iloc[:mid], df.iloc[mid:]


def run_grid_search(symbol, in_sample):
    keys = list(GRID)
    combos = [dict(zip(keys, values)) for values in itertools.product(*GRID.values())]

    results = []
    for i, params in enumerate(combos):
        result = run_daily_momentum_backtest(in_sample, symbol, starting_equity=config.ACCOUNT_EQUITY_USD, **params)
        summary = summarize(result, starting_equity=config.ACCOUNT_EQUITY_USD)
        results.append({**params, **{k: v for k, v in summary.items() if not isinstance(v, dict)}})
        print(f"  [{i + 1}/{len(combos)}] {params} -> total_return_pct={summary.get('total_return_pct'):.4f} "
              f"pf={summary.get('profit_factor')} trades={summary.get('num_round_trips')}")

    results.sort(key=lambda r: r.get("total_return_pct", float("-inf")), reverse=True)
    return results


def validate_one(symbol, full):
    in_sample, out_sample = split_in_out(full)
    print(f"\n{'=' * 70}\n{symbol}\n{'=' * 70}")
    print(f"Full range: {full.index[0].date()} -> {full.index[-1].date()} ({len(full)} bars)")
    print(f"In-sample:  {in_sample.index[0].date()} -> {in_sample.index[-1].date()} ({len(in_sample)} bars)")
    print(f"Out-sample: {out_sample.index[0].date()} -> {out_sample.index[-1].date()} ({len(out_sample)} bars)")

    bh_return = buy_and_hold_return_pct(out_sample)
    print(f"Buy-and-hold return over out-of-sample window: {bh_return:.2f}%  <-- benchmark to beat")

    print(f"\n--- {symbol} grid search (in-sample) ---")
    results = run_grid_search(symbol, in_sample)

    top3 = results[:3]
    rows = []
    if not top3:
        print("No valid combos (insufficient in-sample history for any parameter combo).")
        return rows

    for rank, combo in enumerate(top3, 1):
        params = {k: combo[k] for k in GRID}

        out_result = run_daily_momentum_backtest(out_sample, symbol, starting_equity=config.ACCOUNT_EQUITY_USD, **params)
        out_summary = summarize(out_result, starting_equity=config.ACCOUNT_EQUITY_USD)

        in_return_pct = combo.get("total_return_pct", 0.0) * 100
        in_pf = combo.get("profit_factor")
        out_return_pct = out_summary.get("total_return_pct", 0.0) * 100
        out_pf = out_summary.get("profit_factor")
        out_trades = out_summary.get("num_round_trips")

        beats_zero = out_return_pct > 0
        beats_bh = out_return_pct > bh_return

        if beats_bh:
            verdict = "REAL EDGE (beats buy-and-hold)"
        elif beats_zero:
            verdict = "POSITIVE BUT BEATEN BY BUY-AND-HOLD (not a real edge)"
        else:
            verdict = "FAILED OOS"

        print(f"  #{rank} {params}")
        print(f"      in-sample:  return={in_return_pct:.2f}% pf={in_pf}")
        print(f"      out-sample: return={out_return_pct:.2f}% pf={out_pf} trades={out_trades}")
        print(f"      buy-and-hold benchmark: {bh_return:.2f}%  -> {verdict}")

        rows.append({
            "symbol": symbol, "rank": rank, "params": params,
            "in_return_pct": in_return_pct, "in_pf": in_pf,
            "out_return_pct": out_return_pct, "out_pf": out_pf, "out_trades": out_trades,
            "bh_return_pct": bh_return, "verdict": verdict,
        })

    return rows


def print_final_table(all_rows):
    print(f"\n\n{'=' * 100}\nFINAL SUMMARY -- best (#1) in-sample combo per symbol, out-of-sample result\n{'=' * 100}")
    header = f"{'Symbol':<8}{'Params':<38}{'OOS Return':<13}{'OOS PF':<10}{'Buy&Hold':<12}{'Verdict'}"
    print(header)
    print("-" * len(header))
    for row in all_rows:
        if row["rank"] != 1:
            continue
        params_str = str(row["params"])
        pf = row["out_pf"]
        pf_str = f"{pf:.2f}" if isinstance(pf, (int, float)) else str(pf)
        print(
            f"{row['symbol']:<8}{params_str:<38}{row['out_return_pct']:>7.2f}%     "
            f"{pf_str:<10}{row['bh_return_pct']:>7.2f}%     {row['verdict']}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=SYMBOLS)
    args = parser.parse_args()

    all_rows = []
    for symbol in args.symbols:
        full = load_universe([symbol], BAR_SIZE)[symbol]
        rows = validate_one(symbol, full)
        all_rows.extend(rows)

    print_final_table(all_rows)


if __name__ == "__main__":
    main()
