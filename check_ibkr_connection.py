"""
One-off sanity check: confirms ib_insync can connect to TWS/IB Gateway,
pulls account summary, and checks whether each Phase 1 instrument is
showing LIVE market data (vs delayed) -- run this before trusting any
backtest data pulled from IBKR or before running the live bot.

Run with TWS or IB Gateway open and logged in (paper trading account
recommended for the first run).

Usage:
    python check_ibkr_connection.py
"""
import ib_compat

ib_compat.ensure_event_loop()

from ib_insync import IB, Stock

import config

MARKET_DATA_TYPE_NAMES = {1: "Live", 2: "Frozen", 3: "Delayed", 4: "Delayed Frozen"}


def main() -> None:
    ib = IB()
    ib.connect(config.IB_HOST, config.IB_PORT, clientId=config.IB_CLIENT_ID)
    print(f"Connected to IBKR at {config.IB_HOST}:{config.IB_PORT} (clientId={config.IB_CLIENT_ID})")
    print(f"Managed accounts: {ib.managedAccounts()}")

    wanted_tags = {"NetLiquidation", "AvailableFunds", "BuyingPower", "TotalCashValue"}
    print("\nAccount summary:")
    for item in ib.accountSummary():
        if item.tag in wanted_tags:
            print(f"  {item.tag}: {item.value} {item.currency}")

    print("\nMarket data status per instrument:")
    any_not_live = False
    for symbol in ["SPY", "QQQ", "IWM"]:
        contract = Stock(symbol, "SMART", "USD")
        ib.qualifyContracts(contract)
        ticker = ib.reqMktData(contract, "", False, False)
        ib.sleep(2)  # allow the first tick to arrive
        data_type = MARKET_DATA_TYPE_NAMES.get(ticker.marketDataType, "Unknown")
        print(f"  {symbol}: last={ticker.last} bid={ticker.bid} ask={ticker.ask} data_type={data_type}")
        ib.cancelMktData(contract)

        if data_type != "Live":
            any_not_live = True
            print(f"    WARNING: {symbol} is not showing Live data -- check your market data subscription.")

    if any_not_live:
        print("\nNOT all instruments are on live data. Fix this before backtesting/running the bot on short timeframes.")
    else:
        print("\nAll instruments confirmed on live data. Connection is good to go.")

    ib.disconnect()


if __name__ == "__main__":
    main()
