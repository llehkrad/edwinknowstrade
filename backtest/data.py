"""
Historical bar loading for backtests.

Expects CSV files at data/historical/{SYMBOL}_{bar_size_slug}.csv with
columns: date, open, high, low, close, volume (the same shape ib_insync's
util.df() produces from reqHistoricalData, minus a couple of IB-specific
columns). Use fetch_ibkr_data.py to populate this cache from IBKR, or
generate_synthetic_data.py for a quick smoke test with fake data.
"""
import os

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "historical")


def bar_size_slug(bar_size: str) -> str:
    return bar_size.replace(" ", "")  # "15 mins" -> "15mins"


def csv_path(symbol: str, bar_size: str) -> str:
    return os.path.join(DATA_DIR, f"{symbol}_{bar_size_slug(bar_size)}.csv")


def load_bars(symbol: str, bar_size: str, start: str = None, end: str = None) -> pd.DataFrame:
    """
    Returns a DataFrame indexed by tz-aware timestamp, columns
    open/high/low/close/volume, sorted ascending. Raises FileNotFoundError
    with a helpful message if the cache doesn't exist yet.
    """
    path = csv_path(symbol, bar_size)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No cached historical data for {symbol} at {bar_size}: {path}\n"
            f"Run fetch_ibkr_data.py (needs IB Gateway/TWS running) or "
            f"generate_synthetic_data.py (for a smoke test) first."
        )

    df = pd.read_csv(path)
    # A 1yr+ pull spans a US DST transition, so raw timestamps have mixed
    # UTC offsets (-04:00 EDT vs -05:00 EST). read_csv's parse_dates can't
    # unify mixed offsets into a single dtype and silently leaves the
    # column as plain strings instead of raising -- normalize through UTC
    # first, then convert back to Eastern for a consistent tz-aware index.
    df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_convert("America/New_York")
    df = df.set_index("date").sort_index()

    if start:
        df = df[df.index >= pd.Timestamp(start, tz=df.index.tz)]
    if end:
        df = df[df.index <= pd.Timestamp(end, tz=df.index.tz)]

    return df[["open", "high", "low", "close", "volume"]]


def load_universe(symbols, bar_size: str, start: str = None, end: str = None) -> dict:
    return {symbol: load_bars(symbol, bar_size, start, end) for symbol in symbols}
