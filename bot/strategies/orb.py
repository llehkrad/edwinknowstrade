"""
Opening Range Breakout (ORB): defines the high/low of the first N bars of
each session as the "opening range," then trades breakouts beyond that
range for the rest of the session. Active when bot.regime classifies the
instrument as TRENDING (paired with itself in strategy_registry's
"orb_only", same pattern as mean_reversion_only/vwap_reversion_only).

Mechanically distinct from donchian_breakout.py: Donchian uses a rolling
N-bar channel that slides all day; ORB anchors specifically to the first
N bars of EACH session and never updates that range again until the next
session -- a well-established, separate strategy family (the opening
range reflects overnight information getting priced in at the open).

Parameters (ORB_RANGE_BARS, ORB_STOP_AT_OPPOSITE_RANGE) are placeholders
in config.py pending backtesting. Exit uses the bot's normal ATR-based
stop (set by risk_manager after fill, same as every other strategy) --
this does NOT implement the traditional "close by end of day" ORB
convention, since the bot's architecture is swing-only
(config.ALLOW_OVERNIGHT_HOLDS) and doesn't have a same-day-flatten
mechanism; treat this as an ORB-triggered entry with the bot's standard
exit/stop handling, not a purist same-day ORB implementation.
"""
import numpy as np
import pandas as pd

import config
from bot.signal import Signal


def _session_day(df: pd.DataFrame) -> np.ndarray:
    dates = df["date"] if "date" in df.columns else df.index
    return pd.DatetimeIndex(dates).date


def _opening_range(df: pd.DataFrame, range_bars: int):
    """Returns (range_high, range_low) for the CURRENT (latest bar's)
    session, computed from that session's first `range_bars` bars only.
    Returns (None, None) if the current session doesn't have enough bars
    yet to have completed its opening range."""
    day = _session_day(df)
    latest_day = day[-1]
    session_mask = day == latest_day
    session_df = df.loc[session_mask]

    if len(session_df) <= range_bars:
        # Still inside (or exactly at the end of) the opening range itself
        # -- not enough bars past the range to judge a breakout yet.
        return None, None

    opening = session_df.iloc[:range_bars]
    return opening["high"].max(), opening["low"].min()


def _volume_confirms(df: pd.DataFrame) -> bool:
    """Optional filter (config.ORB_REQUIRE_VOLUME_CONFIRMATION): the
    breakout bar's own volume must exceed ORB_VOLUME_MULT times the
    average volume of the preceding ORB_VOLUME_LOOKBACK bars -- the idea
    being a breakout on abnormally low volume is more likely a false
    breakout/fakeout than one backed by real participation. Off by
    default (config toggle) so ORB can be tested with and without this
    confirmation layered on.
    """
    lookback = config.ORB_VOLUME_LOOKBACK
    if len(df) < lookback + 1:
        return True  # not enough history to judge -- don't block on it
    latest_volume = df["volume"].iloc[-1]
    avg_volume = df["volume"].iloc[-(lookback + 1):-1].mean()
    if pd.isna(avg_volume) or avg_volume <= 0:
        return True
    return latest_volume >= config.ORB_VOLUME_MULT * avg_volume


def generate_signal(df: pd.DataFrame, has_open_position: bool, position_is_long: bool = None) -> Signal:
    range_bars = config.ORB_RANGE_BARS
    range_high, range_low = _opening_range(df, range_bars)

    if range_high is None:
        return Signal.FLAT

    latest_close = df["close"].iloc[-1]

    if has_open_position:
        if config.ORB_STOP_AT_OPPOSITE_RANGE:
            if position_is_long and latest_close <= range_low:
                return Signal.EXIT
            if not position_is_long and latest_close >= range_high:
                return Signal.EXIT
        return Signal.FLAT

    if getattr(config, "ORB_REQUIRE_VOLUME_CONFIRMATION", False) and not _volume_confirms(df):
        return Signal.FLAT

    if latest_close > range_high:
        return Signal.BUY
    if latest_close < range_low:
        return Signal.SELL

    return Signal.FLAT
