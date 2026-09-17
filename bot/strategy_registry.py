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
    # Added 2026-09-18 after an ADX autocorrelation audit found "trending"
    # bars show NEGATIVE forward autocorrelation on real 15-min SPY/QQQ/IWM
    # data -- the opposite of what trend_following assumes -- while
    # mean_reversion alone cleared out-of-sample testing for the first time
    # in the project (see CLAUDE.md). Both regime branches map to the same
    # module, so the ADX regime read becomes irrelevant to which strategy
    # trades -- cleaner than the ADX_TREND_THRESHOLD=999 hack used to first
    # test this.
    "mean_reversion_only": (mean_reversion, mean_reversion),
}


def get_strategies():
    """Returns (ranging_strategy_module, trending_strategy_module)."""
    try:
        return _REGISTRY[config.STRATEGY_SET]
    except KeyError:
        raise ValueError(f"Unknown config.STRATEGY_SET={config.STRATEGY_SET!r}; expected one of {list(_REGISTRY)}")
