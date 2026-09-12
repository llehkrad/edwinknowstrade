"""
Regime filter: decides which single strategy (mean reversion vs trend
following) is active for a given instrument at a given bar.

Chosen over running both strategies in parallel or requiring confluence --
see memory/project_trading_bot_plan.md for why. One strategy trades a given
instrument at a time.
"""
from enum import Enum

import pandas as pd

import config
from bot.indicators import adx


class Regime(Enum):
    TRENDING = "trending"
    RANGING = "ranging"


def current_regime(df: pd.DataFrame) -> Regime:
    """
    df must have 'high', 'low', 'close' columns, most recent bar last.
    Returns TRENDING when ADX >= config.ADX_TREND_THRESHOLD, else RANGING.
    """
    adx_series = adx(df, config.ADX_PERIOD)
    latest_adx = adx_series.iloc[-1]

    if pd.isna(latest_adx):
        # Not enough history yet to compute ADX -- default to ranging
        # (mean reversion) since it's the more conservative of the two.
        return Regime.RANGING

    return Regime.TRENDING if latest_adx >= config.ADX_TREND_THRESHOLD else Regime.RANGING
