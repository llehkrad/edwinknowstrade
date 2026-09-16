"""
Donchian channel breakout: enters on a fresh N-period high/low breakout --
a cleaner, less-lagging trend entry than an SMA crossover (see
trend_following.py), which only reacts after two averages have already
crossed. Exits on a breach of a SHORTER opposite-direction channel
(dual-channel / "Turtle" style), so the same noise that triggered entry
doesn't immediately kick the position back out. Active when bot.regime
classifies the instrument as TRENDING.

Parameters (DONCHIAN_ENTRY_PERIOD, DONCHIAN_EXIT_PERIOD) are placeholders
in config.py pending backtesting.
"""
import pandas as pd

import config
from bot.signal import Signal


def generate_signal(df: pd.DataFrame, has_open_position: bool, position_is_long: bool = None) -> Signal:
    entry_period = config.DONCHIAN_ENTRY_PERIOD
    exit_period = config.DONCHIAN_EXIT_PERIOD

    if len(df) < entry_period + 1:
        return Signal.FLAT

    # Exclude the current (still-forming) bar from the channel so the
    # breakout is judged against prior bars, not the bar creating it.
    prior = df.iloc[:-1]
    latest_close = df["close"].iloc[-1]

    if has_open_position:
        exit_high = prior["high"].iloc[-exit_period:].max()
        exit_low = prior["low"].iloc[-exit_period:].min()
        if position_is_long and latest_close <= exit_low:
            return Signal.EXIT
        if not position_is_long and latest_close >= exit_high:
            return Signal.EXIT
        return Signal.FLAT

    entry_high = prior["high"].iloc[-entry_period:].max()
    entry_low = prior["low"].iloc[-entry_period:].min()

    if latest_close > entry_high:
        return Signal.BUY
    if latest_close < entry_low:
        return Signal.SELL

    return Signal.FLAT
