from enum import Enum


class Signal(Enum):
    BUY = "buy"
    SELL = "sell"
    FLAT = "flat"   # no new entry
    EXIT = "exit"   # close an existing position
