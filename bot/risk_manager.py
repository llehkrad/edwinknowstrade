"""
Position sizing, exposure caps, and the drawdown circuit breaker.

All sizing is ATR-based: 1 ATR move ~= config.RISK_PER_TRADE_PCT of equity,
so risk stays constant across SPY/QQQ/IWM regardless of each instrument's
individual volatility. Fractional shares are used (config.USE_FRACTIONAL_SHARES)
since a $1k account can't get meaningful whole-share sizing on $200-500+ ETFs.
"""
from typing import Dict

import config
from bot.portfolio import Portfolio


def position_size(equity: float, atr_value: float, price: float) -> float:
    """
    Returns a signed-agnostic quantity (always positive) of shares to trade,
    such that a 1-ATR adverse move costs config.RISK_PER_TRADE_PCT of equity --
    capped by config.MAX_POSITION_PCT_OF_EQUITY so sizing never implies more
    notional than the account can actually afford (see config.py comment).
    """
    if atr_value <= 0 or price <= 0:
        return 0.0

    dollar_risk = equity * config.RISK_PER_TRADE_PCT
    risk_based_qty = dollar_risk / atr_value

    max_notional = equity * config.MAX_POSITION_PCT_OF_EQUITY
    capital_based_qty = max_notional / price

    raw_qty = min(risk_based_qty, capital_based_qty)

    if config.USE_FRACTIONAL_SHARES:
        return round(raw_qty, 4)
    return float(int(raw_qty))


def stop_price_for(entry_price: float, atr_value: float, is_long: bool) -> float:
    distance = atr_value * config.STOP_LOSS_ATR_MULT
    return entry_price - distance if is_long else entry_price + distance


def exposure_cap_allows(
    portfolio: Portfolio, is_long: bool, added_notional: float, current_prices: Dict[str, float]
) -> bool:
    """
    Checks the tighter same-direction exposure cap across SPY/QQQ/IWM
    (config.MAX_SAME_DIRECTION_EXPOSURE_PCT) before allowing a new entry.
    """
    if portfolio.equity <= 0:
        return False

    existing_pct = portfolio.same_direction_exposure_pct(is_long, current_prices)
    projected_pct = existing_pct + (added_notional / portfolio.equity)
    return projected_pct <= config.MAX_SAME_DIRECTION_EXPOSURE_PCT


def circuit_breaker_triggered(portfolio: Portfolio) -> bool:
    """
    True once drawdown from peak equity exceeds config.MAX_DRAWDOWN_PCT.
    Caller (main.py) is responsible for flattening all positions and
    halting new entries when this fires, and for firing an instant Slack
    alert -- this must not wait on the scheduled Cowork reporting digest.
    """
    return portfolio.current_drawdown_pct() >= config.MAX_DRAWDOWN_PCT
