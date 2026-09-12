"""
Mean reversion strategy: fade extended moves back toward a moving average.
Active when bot.regime classifies the instrument as RANGING.

Parameters (MR_MA_PERIOD, MR_ENTRY_STD_DEV, MR_EXIT_STD_DEV) are placeholders
in config.py pending backtesting -- see CLAUDE.md's pre-live checklist.
"""
import pandas as pd

import config
from bot.indicators import zscore
from bot.signal import Signal


def generate_signal(df: pd.DataFrame, has_open_position: bool, position_is_long: bool = None) -> Signal:
    """
    df must have a 'close' column, most recent bar last.

    Entry: |z-score| >= MR_ENTRY_STD_DEV -> fade the move (buy if price is
    far below the MA, sell if far above).
    Exit: existing position and price has reverted back inside
    MR_EXIT_STD_DEV of the MA.
    """
    z = zscore(df["close"], config.MR_MA_PERIOD)
    latest_z = z.iloc[-1]

    if pd.isna(latest_z):
        return Signal.FLAT

    if has_open_position:
        if abs(latest_z) <= config.MR_EXIT_STD_DEV:
            return Signal.EXIT
        return Signal.FLAT

    if latest_z <= -config.MR_ENTRY_STD_DEV:
        return Signal.BUY
    if latest_z >= config.MR_ENTRY_STD_DEV:
        return Signal.SELL

    return Signal.FLAT
