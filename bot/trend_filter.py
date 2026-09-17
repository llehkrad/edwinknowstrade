"""
Long-term daily trend filter -- gates NEW entries by the prevailing
multi-month direction. Does not affect exits or stops.

Added 2026-09-16 as a mechanically distinct angle after 900+ configurations
of pure 15-min technical signals showed no edge across two structurally
different strategy families (see CLAUDE.md "Strategy search findings").
This operates on a completely different timescale (daily bars, 50-day
lookback) than anything in that search space -- the theory being that
15-min entries taken against the multi-month trend are more prone to the
whipsaw/stop-out pattern already diagnosed as the dominant loss driver.
"""
from datetime import date
from typing import Dict, Optional

import pandas as pd

import config
from bot.signal import Signal


def build_trend_map(daily_df: pd.DataFrame, period: int = None) -> Dict[date, Optional[str]]:
    """
    daily_df: DataFrame indexed by date/timestamp with a 'close' column, one
    row per trading day. Returns {date: "bullish" | "bearish" | None}.

    The value for a given date is the trend as of the PRECEDING trading
    day's close, not that date's own -- a session's intraday bars must use
    the trend as it stood at the start of the session, not a same-day daily
    bar that isn't complete until the close. Value is None until enough
    days have accumulated for the SMA (or for the very first date, which
    has no preceding day at all).
    """
    period = config.TREND_FILTER_SMA_PERIOD if period is None else period
    sma = daily_df["close"].rolling(period).mean()

    trend = pd.Series([None] * len(daily_df), index=daily_df.index, dtype=object)
    trend[daily_df["close"] > sma] = "bullish"
    trend[(daily_df["close"] <= sma) & sma.notna()] = "bearish"

    shifted = trend.shift(1)  # today's session uses YESTERDAY's completed trend
    # Backtest daily bars are indexed by pandas Timestamp (has .date()).
    # Live daily bars from ib_insync come back as plain datetime.date
    # already (no time component -- daily bars have none), which has no
    # .date() method -- use the index value as-is in that case.
    return {(idx.date() if hasattr(idx, "date") else idx): val for idx, val in shifted.items()}


def entry_allowed(signal: Signal, trend: Optional[str]) -> bool:
    """Gates new BUY/SELL entries only -- EXIT/FLAT signals are never blocked."""
    if not config.TREND_FILTER_ENABLED:
        return True
    if signal is Signal.BUY:
        return trend == "bullish"
    if signal is Signal.SELL:
        return trend == "bearish"
    return True
