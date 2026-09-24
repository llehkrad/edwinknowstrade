"""
Position sizing, exposure caps, and the drawdown circuit breaker.

All sizing is ATR-based: 1 ATR move ~= config.RISK_PER_TRADE_PCT of equity,
so risk stays constant across SPY/QQQ/IWM regardless of each instrument's
individual volatility. Fractional shares are used (config.USE_FRACTIONAL_SHARES)
since a $5k account can't get meaningful whole-share sizing on $200-500+ ETFs.
"""
from typing import Dict

import config
from bot.portfolio import Portfolio


def position_size(equity: float, atr_value: float, price: float, force_whole_shares: bool = False) -> float:
    """
    Returns a signed-agnostic quantity (always positive) of shares to trade,
    such that a 1-ATR adverse move costs config.RISK_PER_TRADE_PCT of equity --
    capped by config.MAX_POSITION_PCT_OF_EQUITY so sizing never implies more
    notional than the account can actually afford (see config.py comment).

    config.USE_FRACTIONAL_SHARES is no longer achievable for LIVE orders --
    IBKR's API rejects fractional-quantity orders outright (Error 10243,
    "Fractional-sized order cannot be placed via API", hit live 2026-09-23
    on a QQQ entry, see CLAUDE.md), even though the desktop TWS GUI accepts
    them. bot/main.py (the only live call site) passes force_whole_shares=True
    to always round to a whole share, minimum 1 when the underlying sizing
    calc is positive, regardless of config.USE_FRACTIONAL_SHARES. backtest/
    engine.py does NOT pass it, so historical backtests keep simulating
    fractional sizing exactly as before -- this flag exists specifically so
    the live-vs-backtest fidelity CLAUDE.md calls for isn't silently broken
    by a live-only API limitation.
    """
    if atr_value <= 0 or price <= 0:
        return 0.0

    dollar_risk = equity * config.RISK_PER_TRADE_PCT
    risk_based_qty = dollar_risk / atr_value

    max_notional = equity * config.MAX_POSITION_PCT_OF_EQUITY
    capital_based_qty = max_notional / price

    raw_qty = min(risk_based_qty, capital_based_qty)

    if force_whole_shares:
        return float(max(1, int(raw_qty))) if raw_qty > 0 else 0.0

    if config.USE_FRACTIONAL_SHARES:
        return round(raw_qty, 4)
    return float(int(raw_qty))


def _stop_distance(entry_price: float, atr_value: float) -> float:
    """Base '1R' distance for stop/take-profit sizing, per config.STOP_LOSS_MODE."""
    if config.STOP_LOSS_MODE == "fixed_pct":
        return entry_price * config.FIXED_STOP_LOSS_PCT
    return atr_value * config.STOP_LOSS_ATR_MULT


def stop_price_for(entry_price: float, atr_value: float, is_long: bool) -> float:
    distance = _stop_distance(entry_price, atr_value)
    return entry_price - distance if is_long else entry_price + distance


def take_profit_price_for(entry_price: float, atr_value: float, is_long: bool) -> float:
    """
    Take-profit distance = the same base stop distance (ATR-based or fixed-%,
    per config.STOP_LOSS_MODE) scaled by config.TAKE_PROFIT_RATIO (the
    risk:reward multiple) -- e.g. a 5% fixed stop and TAKE_PROFIT_RATIO=2.0
    gives a 10% take-profit, a 2:1 reward:risk bracket. Only used when
    config.USE_BRACKET_EXITS is True.
    """
    distance = _stop_distance(entry_price, atr_value) * config.TAKE_PROFIT_RATIO
    return entry_price + distance if is_long else entry_price - distance


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
