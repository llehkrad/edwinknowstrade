"""
Cross-sectional momentum rotation research backtest: rank SPY/QQQ/IWM by
trailing N-bar return, hold the top-ranked instrument, rebalance
periodically. Tests whether RELATIVE momentum across instruments predicts
outperformance, even where absolute-price technicals on any one instrument
(e.g. QQQ) showed no edge. Standalone script, same reasoning as
pairs_trading.py -- a genuinely different mechanism, not wired into the
single-instrument bot architecture yet.

Result (2026-09-18): ruled out. All 15 in-sample combos were negative
(-2% to -4%), but the top-5 showed startling out-of-sample returns of +9%
to +14.5% -- checked against simple buy-and-hold on the SAME out-of-sample
window (13.6% SPY, 17.9% QQQ, 15.4% IWM) and found the rotation strategy
UNDERPERFORMED passive buy-and-hold in every case. The apparent gain was
pure market beta (the out-of-sample half was a strong sustained rally) --
an always ~90%-long, unhedged rotation strategy captures that by
construction, independent of whether the ranking signal has any value.
General lesson: any always-invested, long-only strategy must be checked
against buy-and-hold before its returns are treated as evidence of
anything. See CLAUDE.md for the full writeup.

Usage (must be run as a module):
    python -m research.momentum_rotation
"""
import itertools

import pandas as pd

import config
from backtest import costs
from backtest.data import load_universe

SPLIT_DATE = "2026-03-18"


def backtest_rotation(data: dict, lookback: int, rebalance_every: int, starting_equity: float,
                       notional_pct: float = 0.9, max_drawdown_pct: float = 0.10):
    symbols = list(data.keys())
    common_idx = data[symbols[0]].index
    for s in symbols[1:]:
        common_idx = common_idx.intersection(data[s].index)
    common_idx = common_idx.sort_values()

    closes = {s: data[s].loc[common_idx, "close"] for s in symbols}
    trailing_return = {s: closes[s].pct_change(lookback) for s in symbols}

    cash = starting_equity
    peak_equity = starting_equity
    held_symbol = None
    qty = 0.0
    entry_price = 0.0
    entry_commission = 0.0
    fills = []
    halted = False
    holdings_by_symbol = {s: 0 for s in symbols}  # bar count held, for reporting

    for i in range(lookback, len(common_idx)):
        ts = common_idx[i]
        prices = {s: closes[s].iloc[i] for s in symbols}

        equity = cash + (qty * prices[held_symbol] if held_symbol else 0.0)
        peak_equity = max(peak_equity, equity)
        if not halted and peak_equity > 0 and (peak_equity - equity) / peak_equity >= max_drawdown_pct:
            halted = True
            if held_symbol:
                cash = _close(cash, held_symbol, qty, entry_price, entry_commission, prices[held_symbol], fills, ts, "circuit_breaker")
                held_symbol, qty = None, 0.0
            continue
        if halted:
            continue

        if i % rebalance_every != 0:
            continue

        returns = {s: trailing_return[s].iloc[i] for s in symbols}
        if any(pd.isna(v) for v in returns.values()):
            continue
        ranked = sorted(symbols, key=lambda s: returns[s], reverse=True)
        top = ranked[0]

        if held_symbol == top:
            continue  # already holding the top-ranked instrument

        if held_symbol is not None:
            cash = _close(cash, held_symbol, qty, entry_price, entry_commission, prices[held_symbol], fills, ts, "rotate")
            held_symbol, qty = None, 0.0

        notional = starting_equity * notional_pct
        fill_price = costs.fill_price(prices[top], is_buy=True)
        qty = notional / fill_price
        entry_commission = costs.commission(qty, fill_price)
        cash -= qty * fill_price + entry_commission
        held_symbol, entry_price = top, fill_price
        holdings_by_symbol[top] += 1
        fills.append({"timestamp": ts, "action": f"enter_{top}", "realized_pnl": None})

    if held_symbol is not None:
        final_price = closes[held_symbol].iloc[-1]
        cash = _close(cash, held_symbol, qty, entry_price, entry_commission, final_price, fills, common_idx[-1], "end")

    round_trips = [f for f in fills if f["realized_pnl"] is not None]
    wins = [f for f in round_trips if f["realized_pnl"] > 0]
    losses_sum = abs(sum(f["realized_pnl"] for f in round_trips if f["realized_pnl"] <= 0))

    return {
        "final_equity": cash,
        "total_return_pct": cash / starting_equity - 1,
        "num_round_trips": len(round_trips),
        "win_rate": len(wins) / len(round_trips) if round_trips else 0.0,
        "profit_factor": (sum(f["realized_pnl"] for f in wins) / losses_sum) if losses_sum > 0 else (float("inf") if wins else 0.0),
        "halted": halted,
        "holdings_by_symbol": holdings_by_symbol,
    }


def _close(cash, symbol, qty, entry_price, entry_commission, exit_price_raw, fills, ts, reason):
    exit_price = costs.fill_price(exit_price_raw, is_buy=False)
    exit_commission = costs.commission(qty, exit_price)
    cash += qty * exit_price - exit_commission
    realized_pnl = (exit_price - entry_price) * qty - entry_commission - exit_commission
    fills.append({"timestamp": ts, "action": f"exit_{symbol}_{reason}", "realized_pnl": realized_pnl})
    return cash


def main() -> None:
    full = load_universe(["SPY", "QQQ", "IWM"], config.BAR_SIZE)
    in_sample = {s: df[df.index <= pd.Timestamp("2026-03-17", tz=df.index.tz)] for s, df in full.items()}
    out_sample = {s: df[df.index >= pd.Timestamp(SPLIT_DATE, tz=df.index.tz)] for s, df in full.items()}

    print(f"In-sample bars: {len(in_sample['SPY'])}, out-of-sample bars: {len(out_sample['SPY'])}")

    for symbol in ["SPY", "QQQ", "IWM"]:
        bh = out_sample[symbol]["close"].iloc[-1] / out_sample[symbol]["close"].iloc[0] - 1
        print(f"  {symbol} buy-and-hold benchmark over out-of-sample period: {bh:.2%}")

    GRID = {
        "lookback": [8, 16, 26, 52, 104],  # ~2hr, 4hr, 1 session, 2 sessions, 4 sessions
        "rebalance_every": [8, 16, 26],
    }
    keys = list(GRID)
    combos = [dict(zip(keys, values)) for values in itertools.product(*GRID.values())]
    print(f"\nTesting {len(combos)} momentum-rotation combos on IN-SAMPLE data...")

    results = []
    for params in combos:
        r = backtest_rotation(in_sample, starting_equity=config.ACCOUNT_EQUITY_USD, **params)
        results.append({**params, **{k: v for k, v in r.items() if k != "holdings_by_symbol"},
                        "holdings": r["holdings_by_symbol"]})

    results.sort(key=lambda r: r["total_return_pct"], reverse=True)

    print("\n=== Top 5 in-sample momentum-rotation combos, tested out-of-sample ===")
    print("(Compare against the buy-and-hold benchmarks above -- a rotation")
    print(" strategy that underperforms buy-and-hold isn't adding real value.)")
    for r in results[:5]:
        combo = {k: r[k] for k in GRID}
        oos = backtest_rotation(out_sample, starting_equity=config.ACCOUNT_EQUITY_USD, **combo)
        print(f"\nCombo: {combo}")
        print(f"  IN-SAMPLE:      return={r['total_return_pct']:.2%}  trips={r['num_round_trips']}  "
              f"win_rate={r['win_rate']:.1%}  pf={r['profit_factor']:.2f}  holdings={r['holdings']}")
        print(f"  OUT-OF-SAMPLE:  return={oos['total_return_pct']:.2%}  trips={oos['num_round_trips']}  "
              f"win_rate={oos['win_rate']:.1%}  pf={oos['profit_factor']:.2f}  holdings={oos['holdings_by_symbol']}  halted={oos['halted']}")


if __name__ == "__main__":
    main()
