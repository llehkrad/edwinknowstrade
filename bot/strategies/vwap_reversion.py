"""
VWAP mean reversion: fades deviation from the session VWAP (volume-weighted
average price, resetting each trading day), rather than a fixed-period SMA
(see mean_reversion.py) -- more standard for short-timeframe equity mean
reversion, since VWAP tracks where the day's actual volume traded rather
than a lagging price average. Active when bot.regime classifies the
instrument as RANGING.

Deviation is measured in ATR units so the entry/exit thresholds are
comparable across SPY/QQQ/IWM regardless of price level or volatility.
Parameters (VWAP_ENTRY_ATR_MULT, VWAP_EXIT_ATR_MULT) are placeholders in
config.py pending backtesting.
"""
import numpy as np
import pandas as pd

import config
from bot.indicators import atr
from bot.signal import Signal


def _session_vwap(df: pd.DataFrame) -> pd.Series:
    day = df.index.date
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_pv = (typical_price * df["volume"]).groupby(day).cumsum()
    cum_vol = df["volume"].groupby(day).cumsum()
    return cum_pv / cum_vol.replace(0, np.nan)


def generate_signal(df: pd.DataFrame, has_open_position: bool, position_is_long: bool = None) -> Signal:
    vwap = _session_vwap(df)
    atr_value = atr(df, config.ATR_PERIOD)

    latest_vwap = vwap.iloc[-1]
    latest_atr = atr_value.iloc[-1]

    if pd.isna(latest_vwap) or pd.isna(latest_atr) or latest_atr <= 0:
        return Signal.FLAT

    deviation_atr = (df["close"].iloc[-1] - latest_vwap) / latest_atr

    if has_open_position:
        if abs(deviation_atr) <= config.VWAP_EXIT_ATR_MULT:
            return Signal.EXIT
        return Signal.FLAT

    if deviation_atr <= -config.VWAP_ENTRY_ATR_MULT:
        return Signal.BUY
    if deviation_atr >= config.VWAP_ENTRY_ATR_MULT:
        return Signal.SELL

    return Signal.FLAT
