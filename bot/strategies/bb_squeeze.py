"""
Bollinger Band squeeze breakout: identifies periods of unusually LOW
volatility (bands compressed relative to their own recent history), then
trades the breakout once price closes outside the bands as volatility
expands again. Mechanically distinct from donchian_breakout.py (a pure
price-channel breakout with no volatility-regime gating) and from
mean_reversion.py/vwap_reversion.py (which fade extremes rather than
trade breakouts) -- this strategy specifically waits for a volatility
CONTRACTION before treating a subsequent breakout as meaningful. Active
when bot.regime classifies the instrument as TRENDING.

Squeeze detection: band width (upper - lower, in price terms) relative to
its own BB_SQUEEZE_LOOKBACK-bar history, in the bottom BB_SQUEEZE_PERCENTILE
of that history -- a squeeze is a LOCAL volatility contraction, not an
absolute threshold, so this works across differently-priced/differently-
volatile instruments without extra normalization.

Parameters (BB_PERIOD, BB_STD_DEV, BB_SQUEEZE_LOOKBACK,
BB_SQUEEZE_PERCENTILE) are placeholders in config.py pending backtesting.
"""
import pandas as pd

import config
from bot.indicators import rolling_std, sma
from bot.signal import Signal


def _bands(df: pd.DataFrame):
    mid = sma(df["close"], config.BB_PERIOD)
    std = rolling_std(df["close"], config.BB_PERIOD)
    upper = mid + config.BB_STD_DEV * std
    lower = mid - config.BB_STD_DEV * std
    return upper, mid, lower


def _was_squeezed(width: pd.Series) -> bool:
    """True if the band width JUST BEFORE the current bar sat in the
    bottom BB_SQUEEZE_PERCENTILE of its own trailing BB_SQUEEZE_LOOKBACK
    history -- checked on the prior bar so today's/this bar's own
    (already-expanding, breakout-causing) width doesn't get compared
    against itself."""
    lookback = config.BB_SQUEEZE_LOOKBACK
    if len(width) < lookback + 2:
        return False

    prior_width = width.iloc[-2]  # width as of the bar before this one
    history = width.iloc[-(lookback + 1):-1]  # trailing window, excluding current bar
    if history.isna().any() or pd.isna(prior_width):
        return False

    threshold = history.quantile(config.BB_SQUEEZE_PERCENTILE)
    return prior_width <= threshold


def generate_signal(df: pd.DataFrame, has_open_position: bool, position_is_long: bool = None) -> Signal:
    upper, mid, lower = _bands(df)
    width = upper - lower

    latest_upper = upper.iloc[-1]
    latest_lower = lower.iloc[-1]
    latest_close = df["close"].iloc[-1]

    if pd.isna(latest_upper) or pd.isna(latest_lower):
        return Signal.FLAT

    if has_open_position:
        latest_mid = mid.iloc[-1]
        if position_is_long and latest_close <= latest_mid:
            return Signal.EXIT
        if not position_is_long and latest_close >= latest_mid:
            return Signal.EXIT
        return Signal.FLAT

    if not _was_squeezed(width):
        return Signal.FLAT

    if latest_close > latest_upper:
        return Signal.BUY
    if latest_close < latest_lower:
        return Signal.SELL

    return Signal.FLAT
