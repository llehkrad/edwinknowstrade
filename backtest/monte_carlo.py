"""
Monte Carlo resampling on completed round-trip trades from a backtest run.

This does NOT invent new trades or new market scenarios -- it reorders /
resamples the trade outcomes a backtest already produced, to see the range
of equity curves that could plausibly have resulted from the same
underlying trade outcomes landing in a different sequence. A single
backtest equity curve is one specific ordering of wins/losses; this shows
how much that ordering alone affects drawdown and final return.

Only as good as the underlying trade sample -- meaningless on synthetic
smoke-test data for the same reason the parameter grid search results
were meaningless there (see CLAUDE.md). Run on real backtest fills only.
"""
from typing import Optional

import numpy as np
import pandas as pd

import config


def extract_trade_pnls(fills: pd.DataFrame) -> np.ndarray:
    """Realized PnL of each completed round trip (entry+exit pair)."""
    round_trips = fills[fills["realized_pnl"].notna()]
    return round_trips["realized_pnl"].to_numpy(dtype=float)


def _max_drawdown_pct(equity_curve: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity_curve)
    drawdown = (peak - equity_curve) / peak
    return float(drawdown.max())


def simulate(
    trade_pnls: np.ndarray,
    starting_equity: float,
    num_simulations: int = 2000,
    method: str = "bootstrap",  # "bootstrap" = sample with replacement; "shuffle" = permutation, no replacement
    drawdown_halt_pct: Optional[float] = None,
    seed: Optional[int] = None,
) -> dict:
    if len(trade_pnls) == 0:
        raise ValueError("No completed round-trip trades to resample from.")
    if method not in ("bootstrap", "shuffle"):
        raise ValueError(f"Unknown method: {method!r} (expected 'bootstrap' or 'shuffle')")

    drawdown_halt_pct = config.MAX_DRAWDOWN_PCT if drawdown_halt_pct is None else drawdown_halt_pct
    rng = np.random.default_rng(seed)
    n = len(trade_pnls)

    final_equities = np.empty(num_simulations)
    max_drawdowns = np.empty(num_simulations)
    breached_halt = np.empty(num_simulations, dtype=bool)

    for i in range(num_simulations):
        sample = rng.choice(trade_pnls, size=n, replace=True) if method == "bootstrap" else rng.permutation(trade_pnls)

        equity_curve = np.empty(n + 1)
        equity_curve[0] = starting_equity
        equity_curve[1:] = starting_equity + np.cumsum(sample)

        dd = _max_drawdown_pct(equity_curve)
        max_drawdowns[i] = dd
        final_equities[i] = equity_curve[-1]
        breached_halt[i] = dd >= drawdown_halt_pct

    returns_pct = (final_equities - starting_equity) / starting_equity

    def pct(arr, q):
        return float(np.percentile(arr, q))

    return {
        "method": method,
        "num_simulations": num_simulations,
        "num_trades_per_sim": n,
        "starting_equity": starting_equity,
        "return_pct": {
            "p5": pct(returns_pct, 5),
            "p25": pct(returns_pct, 25),
            "median": pct(returns_pct, 50),
            "p75": pct(returns_pct, 75),
            "p95": pct(returns_pct, 95),
            "mean": float(returns_pct.mean()),
        },
        "max_drawdown_pct": {
            "p5": pct(max_drawdowns, 5),
            "p25": pct(max_drawdowns, 25),
            "median": pct(max_drawdowns, 50),
            "p75": pct(max_drawdowns, 75),
            "p95": pct(max_drawdowns, 95),
            "worst": float(max_drawdowns.max()),
        },
        "prob_of_loss": float((returns_pct < 0).mean()),
        "prob_hit_circuit_breaker": float(breached_halt.mean()),
        "final_equities": final_equities,
        "max_drawdowns": max_drawdowns,
    }


def print_summary(result: dict) -> None:
    print(
        f"\n=== Monte Carlo ({result['method']}, {result['num_simulations']} sims, "
        f"{result['num_trades_per_sim']} trades/sim, start ${result['starting_equity']:,.2f}) ==="
    )
    r = result["return_pct"]
    print(
        f"Return pct  -  p5: {r['p5']:.1%}  p25: {r['p25']:.1%}  median: {r['median']:.1%}  "
        f"p75: {r['p75']:.1%}  p95: {r['p95']:.1%}  mean: {r['mean']:.1%}"
    )
    d = result["max_drawdown_pct"]
    print(
        f"Max DD pct  -  p5: {d['p5']:.1%}  p25: {d['p25']:.1%}  median: {d['median']:.1%}  "
        f"p75: {d['p75']:.1%}  p95: {d['p95']:.1%}  worst: {d['worst']:.1%}"
    )
    print(f"P(loss):                 {result['prob_of_loss']:.1%}")
    print(f"P(hit circuit breaker):  {result['prob_hit_circuit_breaker']:.1%}  (threshold: {config.MAX_DRAWDOWN_PCT:.0%})")
