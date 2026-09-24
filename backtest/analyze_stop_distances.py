"""Analyze exit reasons and stop/TP distances as % of entry price."""
import argparse
import config
from backtest.data import load_universe
from backtest.engine import run_backtest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="SPY")
    p.add_argument("--strategy", default="orb_only")
    p.add_argument("--stop-mult", type=float, default=2.0)
    p.add_argument("--tp-ratio", type=float, default=3.0)
    args = p.parse_args()

    config.STRATEGY_SET = args.strategy
    config.USE_BRACKET_EXITS = True
    config.STOP_LOSS_ATR_MULT = args.stop_mult
    config.TAKE_PROFIT_RATIO = args.tp_ratio

    data = load_universe([args.symbol], config.BAR_SIZE)
    result = run_backtest(data, use_bracket_exits=True)
    fills = result.fills_df()

    entries = fills[fills["action"].isin(["buy", "sell"])].reset_index(drop=True)
    exits = fills[fills["action"] == "exit"].reset_index(drop=True)

    n = min(len(entries), len(exits))
    print(f"{args.symbol} / {args.strategy} / stop={args.stop_mult}x TP_ratio={args.tp_ratio} -> {n} round-trip trades")
    print(f"{'entry_px':>10} {'exit_px':>10} {'pct_move':>9} {'reason':>12} {'pnl':>10}")

    losers = []
    winners = []
    for i in range(n):
        entry_px = entries.loc[i, "price"]
        exit_px = exits.loc[i, "price"]
        pnl = exits.loc[i, "realized_pnl"]
        reason = exits.loc[i, "strategy"]  # exit reason ("stop_loss"/"take_profit") stored here
        pct_move = (exit_px - entry_px) / entry_px * 100
        row = (entry_px, exit_px, pct_move, pnl, reason)
        (losers if pnl < 0 else winners).append(row)
        print(f"{entry_px:>10.2f} {exit_px:>10.2f} {pct_move:>8.2f}% {reason:>12} {pnl:>10.2f}")

    def summarize(label, rows):
        if not rows:
            print(f"{label}: none")
            return
        moves = [abs(r[2]) for r in rows]
        by_reason = {}
        for r in rows:
            by_reason.setdefault(r[4], []).append(abs(r[2]))
        print(f"{label}: n={len(rows)} avg_abs_move={sum(moves)/len(moves):.2f}% "
              f"min={min(moves):.2f}% max={max(moves):.2f}%")
        for reason, vals in by_reason.items():
            print(f"    {reason}: n={len(vals)} avg={sum(vals)/len(vals):.2f}%")

    print()
    summarize("LOSERS abs % move", losers)
    summarize("WINNERS abs % move", winners)


if __name__ == "__main__":
    main()
