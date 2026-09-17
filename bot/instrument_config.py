"""
Applies per-instrument strategy/parameter overrides from
config.INSTRUMENT_CONFIG before that symbol's regime/strategy logic runs.

Uses the same config-monkeypatching pattern backtest/optimize.py already
uses for grid search combos. Safe here because both bot/main.py and
backtest/engine.py process one symbol fully (regime read through
entry/exit decision) before moving to the next within a given bar --
single-threaded and strictly sequential, never interleaved. If two
instruments were ever processed concurrently (e.g. a multi-threaded
rewrite), this pattern would break -- it relies on config being a
single shared, globally-read module.
"""
import config


def apply_instrument_overrides(symbol: str) -> None:
    for name, value in config.INSTRUMENT_CONFIG.get(symbol, {}).items():
        setattr(config, name, value)
