"""
Shared technical indicators, computed with pandas/numpy only (no TA-Lib
dependency, to keep the Lightsail install simple).

All functions take a DataFrame with at least 'high', 'low', 'close' columns
(as returned by ib_insync's util.df() on historical bars) and return a
pandas Series aligned to the input index.
"""
import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def rolling_std(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).std()


def zscore(series: pd.Series, period: int) -> pd.Series:
    mean = sma(series, period)
    std = rolling_std(series, period)
    return (series - mean) / std


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    ranges = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, period: int) -> pd.Series:
    tr = true_range(df)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def adx(df: pd.DataFrame, period: int) -> pd.Series:
    """Average Directional Index (Wilder's smoothing)."""
    up_move = df["high"].diff()
    down_move = -df["low"].diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = true_range(df)
    atr_val = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    plus_di = 100 * (
        pd.Series(plus_dm, index=df.index).ewm(
            alpha=1 / period, min_periods=period, adjust=False
        ).mean()
        / atr_val
    )
    minus_di = 100 * (
        pd.Series(minus_dm, index=df.index).ewm(
            alpha=1 / period, min_periods=period, adjust=False
        ).mean()
        / atr_val
    )

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
