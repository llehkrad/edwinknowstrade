"""
Central configuration for Phase 1 (equities: SPY, QQQ, IWM).

Strategy parameters marked TODO are placeholders pending backtesting —
see CLAUDE.md "Required before going live": 6mo+ backtest with realistic
slippage/commissions -> 2+ weeks paper trading -> only then live keys.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- IBKR connection ---
IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", "7497"))  # 7497 = paper TWS, 7496 = live TWS, 4002/4001 = Gateway
IB_CLIENT_ID = int(os.getenv("IB_CLIENT_ID", "1"))

# --- Universe ---
INSTRUMENTS = ["SPY", "QQQ", "IWM"]

# --- Candle timeframe ---
# ib_insync barSizeSetting string. Start on 15 mins; drop to "5 mins" (or lower)
# once the strategy is validated. Kept as a single config value on purpose.
BAR_SIZE = "15 mins"
HISTORICAL_DURATION = "30 D"  # lookback window kept warm via keepUpToDate=True

# --- Account / risk sizing ---
# Operator-stated starting equity. In live/paper mode this should be reconciled
# against ib.accountSummary() rather than trusted blindly — see risk_manager.
ACCOUNT_EQUITY_USD = float(os.getenv("ACCOUNT_EQUITY_USD", "5000"))
RISK_PER_TRADE_PCT = 0.01  # 1 ATR move ~= this fraction of equity
USE_FRACTIONAL_SHARES = True

# Pure ATR-risk sizing (dollar_risk / ATR) can imply a notional far larger than
# available cash on a small account trading $200-500+/share ETFs -- e.g. on a
# $5k account, a $1.50 ATR on a $550 stock implies buying ~$18.3k of stock to
# risk 1% of equity, which is leverage a cash account doesn't have. This caps
# any single position's notional as a fraction of equity so sizing is always
# affordable; when it binds, realized risk-per-trade will be below the
# RISK_PER_TRADE_PCT target (capital-constrained rather than volatility-
# constrained) -- expected and safe, not a bug.
MAX_POSITION_PCT_OF_EQUITY = 0.30

# --- ATR / stop-loss ---
ATR_PERIOD = 14
STOP_LOSS_ATR_MULT = 2.0  # stop distance = this many ATRs from entry

# --- Regime filter (decides mean-reversion vs trend-following per instrument) ---
ADX_PERIOD = 14
ADX_TREND_THRESHOLD = 25  # ADX >= this => trending regime (trend-following active)
                          # ADX <  this => ranging regime (mean-reversion active)

# --- Strategy set selection ---
# "sma_zscore" = original SMA-crossover trend-following + SMA-zscore mean
# reversion (bot/strategies/trend_following.py, mean_reversion.py).
# "vwap_donchian" = VWAP-deviation reversion + Donchian channel breakout
# (bot/strategies/vwap_reversion.py, donchian_breakout.py) -- added
# 2026-09-16 after "sma_zscore" showed a negative edge across its ENTIRE
# grid-searched parameter space on real SPY/QQQ/IWM 15-min data (see
# CLAUDE.md). Both resolve through bot/strategy_registry.py so live and
# backtest can't diverge on which pair is active.
STRATEGY_SET = "sma_zscore"

# --- Mean reversion strategy (sma_zscore set; TODO: tune via backtest) ---
MR_MA_PERIOD = 20
MR_ENTRY_STD_DEV = 2.0   # enter when price is this many std-devs from the MA
MR_EXIT_STD_DEV = 0.5    # exit/flatten when price reverts back inside this band

# --- Trend following strategy (sma_zscore set; TODO: tune via backtest) ---
TF_FAST_MA_PERIOD = 10
TF_SLOW_MA_PERIOD = 30

# --- VWAP reversion strategy (vwap_donchian set; TODO: tune via backtest) ---
# Deviation from session VWAP, expressed in ATR units so it's comparable
# across SPY/QQQ/IWM regardless of each instrument's price/volatility level.
VWAP_ENTRY_ATR_MULT = 1.5  # enter when price is this many ATRs from session VWAP
VWAP_EXIT_ATR_MULT = 0.3   # exit once back within this many ATRs of VWAP

# --- Donchian breakout strategy (vwap_donchian set; TODO: tune via backtest) ---
# Dual-channel (Turtle-style): entry channel wider than exit channel so a
# position isn't kicked out by the same-magnitude noise that triggered it.
DONCHIAN_ENTRY_PERIOD = 20
DONCHIAN_EXIT_PERIOD = 10

# --- Opening Range Breakout strategy (added 2026-09-24; TODO: tune via backtest) ---
# ORB_RANGE_BARS: number of bars (at config.BAR_SIZE) that make up the
# "opening range" -- e.g. 1 bar at 15-min = the first 15 minutes of the
# session. ORB_STOP_AT_OPPOSITE_RANGE: if True, exit when price closes
# back through the OPPOSITE side of the opening range (in addition to the
# bot's normal ATR stop, which always applies regardless). Volume
# confirmation (ORB_REQUIRE_VOLUME_CONFIRMATION) is an optional filter,
# off by default -- see bot/strategies/orb.py.
ORB_RANGE_BARS = 1
ORB_STOP_AT_OPPOSITE_RANGE = True
ORB_REQUIRE_VOLUME_CONFIRMATION = False
ORB_VOLUME_LOOKBACK = 20
ORB_VOLUME_MULT = 1.5

# --- RSI mean reversion strategy (added 2026-09-24; TODO: tune via backtest) ---
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
RSI_EXIT_LOW = 50   # long position exits once RSI recovers to/above this
RSI_EXIT_HIGH = 50  # short position exits once RSI falls to/below this

# --- Bollinger Band squeeze breakout strategy (added 2026-09-24; TODO: tune via backtest) ---
BB_PERIOD = 20
BB_STD_DEV = 2.0
BB_SQUEEZE_LOOKBACK = 50       # trailing bars used to judge "is band width unusually narrow"
BB_SQUEEZE_PERCENTILE = 0.20   # squeeze = band width in the bottom 20% of its own recent history

# --- Long-term trend filter (daily bars) ---
# Added 2026-09-16 as a mechanically distinct angle after 900+ configs of
# pure 15-min TA signals showed no edge (see CLAUDE.md "Strategy search
# findings") -- gates NEW entries by the prevailing multi-month direction
# (daily close vs its own N-day SMA), using only the most recently
# COMPLETED daily bar to avoid lookahead. Does not affect exits/stops.
# 50 days chosen over the more common 200-day: with only ~1-2yr of real
# history available, 200 days of warmup would eat most of it.
TREND_FILTER_ENABLED = True
TREND_FILTER_SMA_PERIOD = 50
TREND_FILTER_BAR_SIZE = "1 day"

# --- Per-instrument strategy configuration ---
# Added 2026-09-18 after extensive out-of-sample testing found genuinely
# different validated approaches per instrument (see CLAUDE.md "Strategy
# search findings"): SPY and IWM both show real, out-of-sample-validated
# edge via VWAP-reversion; QQQ shows none across four different approaches
# tried. Applied per-symbol via bot/instrument_config.py, which overrides
# the relevant config.* attributes for whichever symbol is currently being
# processed -- the same config-monkeypatching pattern backtest/optimize.py
# already uses for grid-search combos. Safe here because both bot/main.py
# and backtest/engine.py process one symbol fully (regime read through
# entry/exit decision) before moving to the next within a given bar --
# single-threaded and strictly sequential, never interleaved.
INSTRUMENT_CONFIG = {
    "SPY": {
        "STRATEGY_SET": "vwap_reversion_only",
        "VWAP_ENTRY_ATR_MULT": 2.5,
        "VWAP_EXIT_ATR_MULT": 0.2,
        "STOP_LOSS_ATR_MULT": 4.0,
    },
    "IWM": {
        "STRATEGY_SET": "vwap_reversion_only",
        "VWAP_ENTRY_ATR_MULT": 2.5,
        "VWAP_EXIT_ATR_MULT": 0.35,
        "STOP_LOSS_ATR_MULT": 4.0,
    },
    "QQQ": {
        # QQQ's own best-fit IN-SAMPLE parameters -- already shown to fail
        # out-of-sample (see CLAUDE.md). Kept active deliberately, to
        # confirm the "no edge" finding via live paper trading, NOT to try
        # to make QQQ profitable.
        "STRATEGY_SET": "vwap_reversion_only",
        "VWAP_ENTRY_ATR_MULT": 2.5,
        "VWAP_EXIT_ATR_MULT": 0.5,
        "STOP_LOSS_ATR_MULT": 2.0,
    },
}

# --- Portfolio-level exposure cap ---
# SPY/QQQ/IWM are more correlated with each other than the original SPY/QQQ/BTC
# template, so this cap is intentionally tighter than a naive per-instrument limit.
MAX_SAME_DIRECTION_EXPOSURE_PCT = 0.6  # max fraction of equity in same-direction
                                        # exposure across all three instruments combined

# --- Circuit breaker ---
MAX_DRAWDOWN_PCT = 0.10  # halt trading and flatten all positions past this drawdown
                          # from equity peak, pending manual review

# --- Holding style ---
# Swing trading only: positions may carry across sessions. No same-day flatten
# logic exists on purpose -- this keeps the bot clear of the US Pattern Day
# Trader rule (a $5k account is far under the $25k PDT threshold, and same-day
# round trips are what count against that limit).
ALLOW_OVERNIGHT_HOLDS = True

# --- Logging / reporting ---
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "logs/trades.csv")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
