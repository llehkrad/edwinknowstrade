"""
One-off script to populate data/historical/ from IBKR, for backtesting.

Requires IB Gateway or TWS running and logged in (paper or live -- historical
data works the same either way) with a real-time or delayed data subscription
for the requested symbols. Run this from a machine that has that (e.g. your
desktop with TWS, or the Lightsail box once IB Gateway is set up there) --
it will NOT run in a plain dev sandbox with no IB connection.

Usage:
    python backtest/fetch_ibkr_data.py --duration "6 M" --bar-size "15 mins"
"""
import argparse
import os

from ib_insync import IB, Stock, util

import config
from backtest.data import DATA_DIR, csv_path


def fetch_and_save(ib: IB, symbol: str, duration: str, bar_size: str) -> None:
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)

    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=duration,
        barSizeSetting=bar_size,
        whatToShow="TRADES",
        useRTH=True,
        keepUpToDate=False,
    )
    df = util.df(bars)
    if df is None or df.empty:
        print(f"WARNING: no data returned for {symbol}")
        return

    df = df.rename(columns={"date": "date"})[["date", "open", "high", "low", "close", "volume"]]

    os.makedirs(DATA_DIR, exist_ok=True)
    out_path = csv_path(symbol, bar_size)
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} bars for {symbol} -> {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", default="6 M", help='IBKR durationStr, e.g. "6 M", "1 Y"')
    parser.add_argument("--bar-size", default=config.BAR_SIZE, help='IBKR barSizeSetting, e.g. "15 mins"')
    parser.add_argument("--symbols", nargs="+", default=config.INSTRUMENTS)
    args = parser.parse_args()

    ib = IB()
    ib.connect(config.IB_HOST, config.IB_PORT, clientId=config.IB_CLIENT_ID)
    try:
        for symbol in args.symbols:
            fetch_and_save(ib, symbol, args.duration, args.bar_size)
    finally:
        ib.disconnect()


if __name__ == "__main__":
    main()
