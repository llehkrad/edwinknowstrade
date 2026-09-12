"""
Trend following strategy: fast/slow moving-average crossover.
Active when bot.regime classifies the instrument as TRENDING.

Parameters (TF_FAST_MA_PERIOD, TF_SLOW_MA_PERIOD) are placeholders in
config.py pending backtesting -- see CLAUDE.md's pre-live checklist.
"""
import pandas as pd

import config
from bot.indicators import sma
from bot.signal import Signal


def generate_signal(df: pd.DataFrame, has_open_position: bool, position_is_long: bool = None) -> Signal:
    """
    df must have a 'close' column, most recent bar last.

    Entry: fast MA crosses above slow MA -> BUY; fast MA crosses below
    slow MA -> SELL.
    Exit: existing position and the crossover reverses against it.
    """
    fast = sma(df["close"], config.TF_FAST_MA_PERIOD)
    slow = sma(df["close"], config.TF_SLOW_MA_PERIOD)

    if pd.isna(fast.iloc[-1]) or pd.isna(slow.iloc[-1]) or pd.isna(fast.iloc[-2]) or pd.isna(slow.iloc[-2]):
        return Signal.FLAT

    was_fast_above = fast.iloc[-2] > slow.iloc[-2]
    is_fast_above = fast.iloc[-1] > slow.iloc[-1]
    crossed_up = is_fast_above and not was_fast_above
    crossed_down = (not is_fast_above) and was_fast_above

    if has_open_position:
        if position_is_long and crossed_down:
            return Signal.EXIT
        if not position_is_long and crossed_up:
            return Signal.EXIT
        return Signal.FLAT

    if crossed_up:
        return Signal.BUY
    if crossed_down:
        return Signal.SELL

    return Signal.FLAT
