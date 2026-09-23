"""
Maps config.STRATEGY_SET to the (ranging_strategy, trending_strategy)
module pair the regime filter picks between. Both bot/main.py (live) and
backtest/engine.py resolve through this so they can't diverge on which
pair is active.
"""
import config
from bot.strategies import bb_squeeze, donchian_breakout, mean_reversion, orb, rsi_reversion, trend_following, vwap_reversion

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
    # Added 2026-09-18: mean_reversion_only cleared out-of-sample validation
    # on IWM but not SPY/QQQ. Testing whether a different reversion
    # mechanism (VWAP deviation, volume-weighted and session-reset, vs.
    # mean_reversion's fixed-period SMA/z-score) fares differently on
    # SPY/QQQ specifically -- never tested in isolation before, only inside
    # the now-discredited ADX-gated vwap_donchian hybrid.
    "vwap_reversion_only": (vwap_reversion, vwap_reversion),
    # Added 2026-09-24: testing trend_following (SMA fast/slow crossover) in
    # isolation on single-stock names (TSLA, GOOGL, and more if promising) --
    # never tested alone before, only ever mixed with mean_reversion inside
    # "sma_zscore" (which failed out-of-sample on TSLA/GOOGL, see CLAUDE.md).
    # Single stocks are more news/catalyst-driven than SPY/QQQ/IWM, so
    # momentum may fare differently even though it was ruled out for the
    # index ETFs (see the 2026-09-18 ADX autocorrelation audit -- that audit
    # was run on SPY/QQQ/IWM only, not re-checked on single stocks).
    "trend_following_only": (trend_following, trend_following),
    # Added 2026-09-24: Opening Range Breakout, testing single-stock
    # candidates (TSLA, GOOGL) -- mechanically distinct from Donchian
    # breakout (rolling channel) and from every mean-reversion/momentum
    # strategy tried so far: anchors specifically to the first N bars of
    # EACH session rather than sliding all day. See bot/strategies/orb.py.
    "orb_only": (orb, orb),
    # Added 2026-09-24: RSI mean reversion, testing single-stock candidates
    # -- a mechanically different reversion signal (speed of price change
    # via gain/loss ratio) than mean_reversion.py's SMA/z-score distance-
    # from-average or vwap_reversion.py's VWAP-deviation approach.
    "rsi_reversion_only": (rsi_reversion, rsi_reversion),
    # Added 2026-09-24: Bollinger Band squeeze breakout, testing
    # single-stock candidates -- gates breakout entries on a prior
    # volatility CONTRACTION (band width in the bottom percentile of its
    # own recent history), distinct from donchian_breakout.py's plain
    # price-channel breakout with no volatility-regime gating.
    "bb_squeeze_only": (bb_squeeze, bb_squeeze),
}


def get_strategies():
    """Returns (ranging_strategy_module, trending_strategy_module)."""
    try:
        return _REGISTRY[config.STRATEGY_SET]
    except KeyError:
        raise ValueError(f"Unknown config.STRATEGY_SET={config.STRATEGY_SET!r}; expected one of {list(_REGISTRY)}")
