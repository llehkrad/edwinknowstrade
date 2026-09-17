"""
QQQ/SPY pairs trading research backtest.

Trades the SPREAD between two correlated instruments (log(QQQ) - log(SPY))
rather than either instrument's absolute price -- a genuinely different
mechanism than the mean-reversion/VWAP-reversion strategies already tested,
motivated by QQQ having no validated edge from either single-instrument
approach. Standalone script, not wired into bot/backtest.engine's
architecture, since managing two simultaneous correlated legs as one
logical trade is a different execution model than the rest of the project.

Result (2026-09-18): ruled out. Every top-5 in-sample combo was already
negative (best -0.44%), degrading further out-of-sample (-2.04% to
-2.93%). All top combos converged on the longest lookback tested (400
bars) with very few trades -- the QQQ/SPY log-ratio spread doesn't
mean-revert cleanly at this timeframe. See CLAUDE.md for the full writeup.

Sizing: dollar-neutral (equal notional long/short per leg), a simplified
first-pass model -- not the full ATR-risk sizing framework used elsewhere.
Commissions apply per leg per entry/exit (4 commission charges per round
trip: QQQ entry, SPY entry, QQQ exit, SPY exit) -- a real cost consideration
specific to pairs trading, worth flagging explicitly.

Usage (must be run as a module):
    python -m research.pairs_trading
"""
import itertools

import numpy as np
import pandas as pd

import config
from backtest import costs
from backtest.data import load_bars

SPLIT_DATE = "2026-03-18"


def compute_zscore_spread(qqq: pd.DataFrame, spy: pd.DataFrame, lookback: int):
    common_idx = qqq.index.intersection(spy.index)
    qqq_c = qqq.loc[common_idx, "close"]
    spy_c = spy.loc[common_idx, "close"]
    spread = np.log(qqq_c) - np.log(spy_c)
    mean = spread.rolling(lookback).mean()
    std = spread.rolling(lookback).std()
    zscore = (spread - mean) / std
    return common_idx, qqq_c, spy_c, zscore


def backtest_pairs(qqq_df, spy_df, lookback, entry_z, exit_z, stop_z,
                    starting_equity, notional_pct=0.30, max_drawdown_pct=0.10):
    idx, qqq_c, spy_c, zscore = compute_zscore_spread(qqq_df, spy_df, lookback)

    cash = starting_equity
    equity = starting_equity
    peak_equity = starting_equity
    position = None  # dict: direction, qty_qqq, qty_spy, entry prices, entry commissions
    fills = []
    halted = False

    for i in range(len(idx)):
        z = zscore.iloc[i]
        if pd.isna(z):
            continue

        qqq_price = qqq_c.iloc[i]
        spy_price = spy_c.iloc[i]

        if position is not None:
            qqq_pnl = (qqq_price - position["qqq_entry"]) * position["qty_qqq"] * (1 if position["direction"] == "long_qqq_short_spy" else -1)
            spy_pnl = (spy_price - position["spy_entry"]) * position["qty_spy"] * (1 if position["direction"] == "short_qqq_long_spy" else -1)
            equity = cash + qqq_pnl + spy_pnl
        else:
            equity = cash
        peak_equity = max(peak_equity, equity)

        if not halted and peak_equity > 0 and (peak_equity - equity) / peak_equity >= max_drawdown_pct:
            halted = True
            if position is not None:
                cash = _close_pair(cash, position, qqq_price, spy_price, fills, idx[i], "circuit_breaker")
                position = None
            continue

        if halted:
            continue

        if position is not None:
            reverted = abs(z) <= exit_z
            stopped = abs(z) >= stop_z
            if reverted or stopped:
                cash = _close_pair(cash, position, qqq_price, spy_price, fills, idx[i],
                                    "stop" if stopped else "signal_exit")
                position = None
            continue

        if z >= entry_z or z <= -entry_z:
            notional = starting_equity * notional_pct
            qty_qqq = notional / qqq_price
            qty_spy = notional / spy_price
            direction = "short_qqq_long_spy" if z >= entry_z else "long_qqq_short_spy"

            qqq_action_is_buy = direction == "long_qqq_short_spy"
            spy_action_is_buy = direction == "short_qqq_long_spy"
            qqq_fill = costs.fill_price(qqq_price, is_buy=qqq_action_is_buy)
            spy_fill = costs.fill_price(spy_price, is_buy=spy_action_is_buy)
            qqq_comm = costs.commission(qty_qqq, qqq_fill)
            spy_comm = costs.commission(qty_spy, spy_fill)

            cash += (-qty_qqq * qqq_fill if qqq_action_is_buy else qty_qqq * qqq_fill) - qqq_comm
            cash += (-qty_spy * spy_fill if spy_action_is_buy else qty_spy * spy_fill) - spy_comm

            position = {
                "direction": direction, "qty_qqq": qty_qqq, "qty_spy": qty_spy,
                "qqq_entry": qqq_fill, "spy_entry": spy_fill,
                "entry_commission": qqq_comm + spy_comm,
            }
            fills.append({"timestamp": idx[i], "action": "enter_" + direction, "zscore": z,
                          "qqq_price": qqq_fill, "spy_price": spy_fill, "realized_pnl": None})

    final_equity = equity
    round_trips = [f for f in fills if f["realized_pnl"] is not None]
    wins = [f for f in round_trips if f["realized_pnl"] > 0]

    return {
        "final_equity": final_equity,
        "total_return_pct": final_equity / starting_equity - 1,
        "num_round_trips": len(round_trips),
        "win_rate": len(wins) / len(round_trips) if round_trips else 0.0,
        "profit_factor": (sum(f["realized_pnl"] for f in wins) /
                           abs(sum(f["realized_pnl"] for f in round_trips if f["realized_pnl"] <= 0))
                           if any(f["realized_pnl"] <= 0 for f in round_trips) else float("inf")) if round_trips else 0.0,
        "halted": halted,
        "fills": fills,
    }


def _close_pair(cash, position, qqq_price, spy_price, fills, ts, reason):
    qqq_action_is_buy = position["direction"] == "short_qqq_long_spy"  # closing short_qqq means buying back
    spy_action_is_buy = position["direction"] == "long_qqq_short_spy"  # closing short_spy means buying back
    qqq_fill = costs.fill_price(qqq_price, is_buy=qqq_action_is_buy)
    spy_fill = costs.fill_price(spy_price, is_buy=spy_action_is_buy)
    qqq_comm = costs.commission(position["qty_qqq"], qqq_fill)
    spy_comm = costs.commission(position["qty_spy"], spy_fill)

    if position["direction"] == "long_qqq_short_spy":
        qqq_pnl = (qqq_fill - position["qqq_entry"]) * position["qty_qqq"]
        spy_pnl = (position["spy_entry"] - spy_fill) * position["qty_spy"]
        cash += position["qty_qqq"] * qqq_fill - qqq_comm  # sell qqq
        cash += -position["qty_spy"] * spy_fill - spy_comm  # buy back spy
    else:
        qqq_pnl = (position["qqq_entry"] - qqq_fill) * position["qty_qqq"]
        spy_pnl = (spy_fill - position["spy_entry"]) * position["qty_spy"]
        cash += -position["qty_qqq"] * qqq_fill - qqq_comm  # buy back qqq
        cash += position["qty_spy"] * spy_fill - spy_comm  # sell spy

    realized_pnl = qqq_pnl + spy_pnl - position["entry_commission"] - qqq_comm - spy_comm
    fills.append({"timestamp": ts, "action": "exit_" + reason, "zscore": None,
                  "qqq_price": qqq_fill, "spy_price": spy_fill, "realized_pnl": realized_pnl})
    return cash


def main() -> None:
    qqq_full = load_bars("QQQ", config.BAR_SIZE)
    spy_full = load_bars("SPY", config.BAR_SIZE)

    qqq_in = qqq_full[qqq_full.index <= pd.Timestamp("2026-03-17", tz=qqq_full.index.tz)]
    spy_in = spy_full[spy_full.index <= pd.Timestamp("2026-03-17", tz=spy_full.index.tz)]
    qqq_out = qqq_full[qqq_full.index >= pd.Timestamp(SPLIT_DATE, tz=qqq_full.index.tz)]
    spy_out = spy_full[spy_full.index >= pd.Timestamp(SPLIT_DATE, tz=spy_full.index.tz)]

    print(f"In-sample: {len(qqq_in)} bars, out-of-sample: {len(qqq_out)} bars")

    GRID = {
        "lookback": [50, 100, 200, 400],
        "entry_z": [1.5, 2.0, 2.5],
        "exit_z": [0.2, 0.5],
        "stop_z": [3.0, 4.0],
    }
    keys = list(GRID)
    combos = [dict(zip(keys, values)) for values in itertools.product(*GRID.values())]
    print(f"Testing {len(combos)} pairs-trading combos on IN-SAMPLE data...")

    results = []
    for params in combos:
        r = backtest_pairs(qqq_in, spy_in, starting_equity=config.ACCOUNT_EQUITY_USD, **params)
        results.append({**params, **{k: v for k, v in r.items() if k != "fills"}})

    results.sort(key=lambda r: r["total_return_pct"], reverse=True)

    print("\n=== Top 5 in-sample pairs combos, tested out-of-sample ===")
    for r in results[:5]:
        combo = {k: r[k] for k in GRID}
        oos = backtest_pairs(qqq_out, spy_out, starting_equity=config.ACCOUNT_EQUITY_USD, **combo)
        print(f"\nCombo: {combo}")
        print(f"  IN-SAMPLE:      return={r['total_return_pct']:.2%}  trips={r['num_round_trips']}  "
              f"win_rate={r['win_rate']:.1%}  pf={r['profit_factor']:.2f}")
        print(f"  OUT-OF-SAMPLE:  return={oos['total_return_pct']:.2%}  trips={oos['num_round_trips']}  "
              f"win_rate={oos['win_rate']:.1%}  pf={oos['profit_factor']:.2f}  halted={oos['halted']}")


if __name__ == "__main__":
    main()
