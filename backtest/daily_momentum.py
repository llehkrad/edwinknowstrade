"""
Daily-bar 12-1 month momentum backtest -- a genuinely different timeframe
and mechanism from the rest of this project's intraday (15-min bar) work.

Background (see CLAUDE.md 2026-09-24): extensive out-of-sample testing found
no validated edge on SPY/QQQ/TSLA/GOOGL across 7 different intraday strategy
types; IWM is the only instrument with a real edge (VWAP-reversion). The
operator's hypothesis is that a longer, position/swing timeframe -- driven
by institutional/fundamental flows rather than 15-min HFT/market-making --
might show a real edge even on the mega-cap names the intraday approach
failed on. This module tests the classic academic "12-1 month momentum
factor" (Jegadeesh & Titman): rank/trade an instrument on its own trailing
12-month return, EXCLUDING the most recent month (the most recent month is
skipped because it shows short-term MEAN REVERSION rather than momentum --
a well-documented separate effect that would otherwise contaminate the
signal).

Design choices (single-instrument, long/flat only -- this project's bot is
a systematic single-instrument trader per instrument, not a cross-sectional
portfolio ranker, so there's no "top N of universe" ranking here, just each
symbol's own trailing momentum sign):

  - Formation period: trailing FORMATION_DAYS trading days of return
    (default 252 ~= 12 months).
  - Skip period: the most recent SKIP_DAYS trading days (default 21 ~= 1
    month) are excluded from the formation window, per the standard
    academic implementation.
  - Rebalance frequency: signal is only re-evaluated every REBALANCE_DAYS
    trading days (default 21 ~= monthly), matching the standard academic
    "form portfolios monthly" cadence -- NOT re-evaluated every bar, so a
    position isn't churned by daily noise.
  - Entry: go long at the next rebalance date if trailing 12-1 month
    momentum is positive.
  - Exit: flatten at the next rebalance date if momentum has turned
    negative (or non-positive). No separate stop-loss -- this is a
    monthly-rebalanced factor strategy, not an ATR-stopped intraday trade;
    the "stop" is effectively "exit at the next monthly rebalance if the
    signal flips."
  - No shorting: mirrors the intraday bot's per-instrument long/flat
    convention and keeps this directly comparable to a long-only
    buy-and-hold benchmark (the mandatory comparison per CLAUDE.md).
  - Sizing: fully invested (all available cash) when long, flat (all cash)
    otherwise -- single instrument, no cross-instrument capital
    allocation decision to make here.

All three lookback/frequency parameters are function arguments (not hard-
coded), so backtest/validate_daily_momentum.py can grid-search them on the
in-sample half only.
"""
from typing import List, Optional

import pandas as pd

import config
from backtest import costs
from backtest.engine import BacktestResult, Fill

STRATEGY_NAME = "momentum_12_1"

DEFAULT_FORMATION_DAYS = 252
DEFAULT_SKIP_DAYS = 21
DEFAULT_REBALANCE_DAYS = 21


def momentum_signal(closes: pd.Series, i: int, formation_days: int, skip_days: int) -> Optional[bool]:
    """
    Trailing 12-1 month momentum sign as of index i (using only data up to
    and including closes[i] -- no lookahead). Returns True (long), False
    (flat), or None if there isn't enough history yet.
    """
    window_end = i - skip_days
    window_start = window_end - formation_days
    if window_start < 0:
        return None
    momentum = closes.iloc[window_end] / closes.iloc[window_start] - 1
    return bool(momentum > 0)


def run_daily_momentum_backtest(
    df: pd.DataFrame,
    symbol: str,
    formation_days: int = DEFAULT_FORMATION_DAYS,
    skip_days: int = DEFAULT_SKIP_DAYS,
    rebalance_days: int = DEFAULT_REBALANCE_DAYS,
    starting_equity: float = None,
) -> BacktestResult:
    """
    df: single-symbol DataFrame indexed by timestamp, open/high/low/close/
    volume columns (same shape as backtest.data.load_bars()), daily bars.

    Single position at a time (long or flat). Signal is only checked every
    `rebalance_days` trading days; trades execute at that day's close
    (using momentum computed from data strictly at or before skip_days ago,
    so no lookahead). Any open position still held at the last bar is
    closed there so every trade is a complete round trip for metrics.
    """
    starting_equity = starting_equity if starting_equity is not None else config.ACCOUNT_EQUITY_USD
    closes = df["close"]
    n = len(df)

    cash = starting_equity
    qty = 0.0
    entry_price = 0.0
    entry_commission = 0.0
    is_long_position = False

    fills: List[Fill] = []
    equity_curve_rows = []

    warmup = formation_days + skip_days
    rebalance_idxs = set(range(warmup, n, rebalance_days))

    for i in range(n):
        ts = df.index[i]
        price = closes.iloc[i]

        if i in rebalance_idxs:
            signal_long = momentum_signal(closes, i, formation_days, skip_days)

            if signal_long is False and is_long_position:
                fill_p = costs.fill_price(price, is_buy=False)
                commission = costs.commission(qty, fill_p)
                realized_pnl = (fill_p - entry_price) * qty - entry_commission - commission
                cash += qty * fill_p - commission
                fills.append(Fill(
                    timestamp=ts, symbol=symbol, action="exit", quantity=qty, price=fill_p,
                    commission=commission, strategy=STRATEGY_NAME, regime="n/a",
                    equity_after=cash, realized_pnl=realized_pnl,
                ))
                qty, entry_price, entry_commission, is_long_position = 0.0, 0.0, 0.0, False

            elif signal_long is True and not is_long_position:
                fill_p = costs.fill_price(price, is_buy=True)
                qty = cash / fill_p  # fully invested, fractional shares (research backtest, not live sizing)
                commission = costs.commission(qty, fill_p)
                qty = (cash - commission) / fill_p
                commission = costs.commission(qty, fill_p)
                cash -= qty * fill_p + commission
                entry_price = fill_p
                entry_commission = commission
                is_long_position = True
                fills.append(Fill(
                    timestamp=ts, symbol=symbol, action="buy", quantity=qty, price=fill_p,
                    commission=commission, strategy=STRATEGY_NAME, regime="n/a",
                    equity_after=cash + qty * fill_p, realized_pnl=None,
                ))

        equity = cash + (qty * price if is_long_position else 0.0)
        equity_curve_rows.append({"timestamp": ts, "equity": equity})

    if is_long_position:
        ts = df.index[-1]
        price = closes.iloc[-1]
        fill_p = costs.fill_price(price, is_buy=False)
        commission = costs.commission(qty, fill_p)
        realized_pnl = (fill_p - entry_price) * qty - entry_commission - commission
        cash += qty * fill_p - commission
        fills.append(Fill(
            timestamp=ts, symbol=symbol, action="exit", quantity=qty, price=fill_p,
            commission=commission, strategy=STRATEGY_NAME, regime="n/a",
            equity_after=cash, realized_pnl=realized_pnl,
        ))
        equity_curve_rows[-1]["equity"] = cash

    equity_curve = pd.DataFrame(equity_curve_rows).set_index("timestamp")
    return BacktestResult(equity_curve=equity_curve, fills=fills, halted_at=None)
