"""
RSI mean reversion: fades extended moves using the Relative Strength Index
(momentum-of-momentum, based on the ratio of recent gains to losses) rather
than mean_reversion.py's SMA/z-score distance-from-average approach --
mechanically a different reversion signal (RSI measures the SPEED of
recent price change, not distance from a moving average), following the
same "test a different mechanism" pattern that led to vwap_reversion.py
after SMA-zscore mean reversion showed no edge on SPY/QQQ. Active when
bot.regime classifies the instrument as RANGING.

Parameters (RSI_PERIOD, RSI_OVERSOLD, RSI_OVERBOUGHT, RSI_EXIT_LOW,
RSI_EXIT_HIGH) are placeholders in config.py pending backtesting.
"""
import pandas as pd

import config
from bot.indicators import rsi
from bot.signal import Signal


def generate_signal(df: pd.DataFrame, has_open_position: bool, position_is_long: bool = None) -> Signal:
    """
    df must have a 'close' column, most recent bar last.

    Entry: RSI <= RSI_OVERSOLD -> BUY (fade the selloff);
           RSI >= RSI_OVERBOUGHT -> SELL (fade the rally).
    Exit: existing long position and RSI has recovered back above
          RSI_EXIT_LOW; existing short position and RSI has fallen back
          below RSI_EXIT_HIGH. Separate exit thresholds (rather than one
          "back to 50" exit) mirror mean_reversion.py's asymmetric
          entry/exit-band pattern.
    """
    latest_rsi = rsi(df["close"], config.RSI_PERIOD).iloc[-1]

    if pd.isna(latest_rsi):
        return Signal.FLAT

    if has_open_position:
        if position_is_long and latest_rsi >= config.RSI_EXIT_LOW:
            return Signal.EXIT
        if not position_is_long and latest_rsi <= config.RSI_EXIT_HIGH:
            return Signal.EXIT
        return Signal.FLAT

    if latest_rsi <= config.RSI_OVERSOLD:
        return Signal.BUY
    if latest_rsi >= config.RSI_OVERBOUGHT:
        return Signal.SELL

    return Signal.FLAT
