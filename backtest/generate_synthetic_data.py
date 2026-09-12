"""
Generates fake OHLCV bars so the backtest engine can be smoke-tested without
a real IBKR connection. NOT a substitute for the real 6mo+ historical
backtest required before paper trading -- see fetch_ibkr_data.py for that.

Usage:
    python backtest/generate_synthetic_data.py
"""
import os

import numpy as np
import pandas as pd

import config
from backtest.data import DATA_DIR, csv_path

RNG_SEED = 7


def generate_bars(symbol: str, start_price: float, num_bars: int, bar_minutes: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    # Random walk with a small amount of autocorrelation so trend-following
    # and mean-reversion both occasionally find signal, purely for exercising
    # the engine end-to-end -- not a realistic price model.
    returns = rng.normal(loc=0.0, scale=0.0015, size=num_bars)
    drift = np.sin(np.linspace(0, 6 * np.pi, num_bars)) * 0.0008
    log_returns = returns + drift
    close = start_price * np.exp(np.cumsum(log_returns))

    high = close * (1 + np.abs(rng.normal(0, 0.0008, num_bars)))
    low = close * (1 - np.abs(rng.normal(0, 0.0008, num_bars)))
    open_ = np.roll(close, 1)
    open_[0] = start_price
    volume = rng.integers(50_000, 500_000, num_bars)

    # Only stamp bars during a fake RTH session so gaps look plausible;
    # actual session alignment doesn't matter for a synthetic smoke test.
    timestamps = pd.date_range(
        start="2025-01-02 09:30:00", periods=num_bars, freq=f"{bar_minutes}min", tz="America/New_York"
    )

    return pd.DataFrame(
        {"date": timestamps, "open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    start_prices = {"SPY": 550.0, "QQQ": 480.0, "IWM": 220.0}

    for i, symbol in enumerate(config.INSTRUMENTS):
        df = generate_bars(
            symbol,
            start_price=start_prices.get(symbol, 100.0),
            num_bars=3000,
            bar_minutes=15,
            seed=RNG_SEED + i,
        )
        out_path = csv_path(symbol, config.BAR_SIZE)
        df.to_csv(out_path, index=False)
        print(f"Wrote {len(df)} synthetic bars for {symbol} -> {out_path}")


if __name__ == "__main__":
    main()
