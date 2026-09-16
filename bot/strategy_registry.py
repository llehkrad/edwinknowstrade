"""
Maps config.STRATEGY_SET to the (ranging_strategy, trending_strategy)
module pair the regime filter picks between. Both bot/main.py (live) and
backtest/engine.py resolve through this so they can't diverge on which
pair is active.
"""
import config
from bot.strategies import donchian_breakout, mean_reversion, trend_following, vwap_reversion

_REGISTRY = {
    "sma_zscore": (mean_reversion, trend_following),
    "vwap_donchian": (vwap_reversion, donchian_breakout),
}


def get_strategies():
    """Returns (ranging_strategy_module, trending_strategy_module)."""
    try:
        return _REGISTRY[config.STRATEGY_SET]
    except KeyError:
        raise ValueError(f"Unknown config.STRATEGY_SET={config.STRATEGY_SET!r}; expected one of {list(_REGISTRY)}")
