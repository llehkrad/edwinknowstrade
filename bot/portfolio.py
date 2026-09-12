"""
In-memory portfolio state: open positions, equity curve, and the
same-direction exposure cap across SPY/QQQ/IWM.

The bot's actual source of truth for cash/positions is IBKR itself
(reconciled via ib.portfolio()/ib.accountSummary() in main.py) -- this
class exists so risk checks can be computed synchronously against a plain
Python model without round-tripping to the API on every decision.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import config


@dataclass
class Position:
    symbol: str
    quantity: float  # signed: positive = long, negative = short
    entry_price: float
    stop_price: float
    opened_at: datetime

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    def notional(self, current_price: float) -> float:
        return abs(self.quantity) * current_price


@dataclass
class Portfolio:
    equity: float = config.ACCOUNT_EQUITY_USD
    peak_equity: float = config.ACCOUNT_EQUITY_USD
    positions: Dict[str, Position] = field(default_factory=dict)
    equity_curve: List[float] = field(default_factory=list)

    def update_equity(self, new_equity: float) -> None:
        self.equity = new_equity
        self.peak_equity = max(self.peak_equity, new_equity)
        self.equity_curve.append(new_equity)

    def current_drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return (self.peak_equity - self.equity) / self.peak_equity

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def open_position(self, position: Position) -> None:
        self.positions[position.symbol] = position

    def close_position(self, symbol: str) -> None:
        self.positions.pop(symbol, None)

    def same_direction_exposure_pct(self, direction_is_long: bool, current_prices: Dict[str, float]) -> float:
        """
        Fraction of equity currently committed to positions in the given
        direction, across all instruments -- used to enforce the tighter
        SPY/QQQ/IWM correlation cap (config.MAX_SAME_DIRECTION_EXPOSURE_PCT).
        """
        if self.equity <= 0:
            return 0.0

        total = 0.0
        for symbol, pos in self.positions.items():
            if pos.is_long == direction_is_long:
                price = current_prices.get(symbol, pos.entry_price)
                total += pos.notional(price)

        return total / self.equity
