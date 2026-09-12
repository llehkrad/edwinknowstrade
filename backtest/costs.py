"""
IBKR is NOT commission-free like the original Alpaca-based template --
these models must be applied in every backtest (see CLAUDE.md pre-live
checklist: "realistic slippage/commissions").
"""

# IBKR US stocks/ETFs "tiered" commission schedule (approximate, as of
# writing -- recheck https://www.interactivebrokers.com/en/pricing before
# relying on this for real capital decisions).
COMMISSION_PER_SHARE = 0.005
COMMISSION_MIN = 1.00
COMMISSION_MAX_PCT_OF_TRADE = 0.01

# Slippage: assumed fill is this many basis points worse than the bar's
# close, in the direction of the trade. A placeholder -- real slippage
# depends on the instrument's liquidity/spread and should be revisited
# once paper-trading fills are observed.
SLIPPAGE_BPS = 2.0


def commission(shares: float, price: float) -> float:
    trade_value = abs(shares) * price
    if trade_value <= 0:
        return 0.0
    raw = abs(shares) * COMMISSION_PER_SHARE
    capped = min(raw, trade_value * COMMISSION_MAX_PCT_OF_TRADE)
    return max(capped, COMMISSION_MIN)


def fill_price(reference_price: float, is_buy: bool, bps: float = SLIPPAGE_BPS) -> float:
    """Buys fill slightly above, sells slightly below, the reference price."""
    adjustment = reference_price * (bps / 10_000)
    return reference_price + adjustment if is_buy else reference_price - adjustment
