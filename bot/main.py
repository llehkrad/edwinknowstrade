"""
Execution layer entry point. Pure deterministic if/then logic -- no AI/model
involved at runtime (see CLAUDE.md non-goals). Polls candles via ib_insync's
keepUpToDate live bars -> computes indicators -> regime filter picks a
strategy -> risk manager sizes/vets the trade -> places a bracket order with
a hard stop -> logs to CSV.

Run under systemd with Restart=always on the dedicated Lightsail box, per
CLAUDE.md. NOT a finished live-trading system: strategy parameters in
config.py are placeholders pending backtesting, and the pre-live checklist
(6mo+ backtest -> 2+ weeks paper trading -> live keys) has not been done yet.
"""
import logging
import signal
import sys

from ib_insync import IB, MarketOrder, Stock, StopOrder, util

import config
from bot import risk_manager, trade_log
from bot.alerts import send_slack_alert
from bot.indicators import atr
from bot.portfolio import Portfolio, Position
from bot.regime import Regime, current_regime
from bot.signal import Signal
from bot.strategies import mean_reversion, trend_following

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bot.main")

ib = IB()
portfolio = Portfolio()
halted = False  # set True once the circuit breaker fires; blocks new entries


def strategy_for(regime: Regime):
    return trend_following if regime is Regime.TRENDING else mean_reversion


def current_open_price_map(bar_lists) -> dict:
    return {symbol: bar_list[-1].close for symbol, bar_list in bar_lists.items() if bar_list}


def place_entry(contract, symbol: str, is_long: bool, qty: float, price: float, stop_price: float, strategy_name: str, regime: Regime) -> None:
    action = "BUY" if is_long else "SELL"
    stop_action = "SELL" if is_long else "BUY"

    entry_order = MarketOrder(action, qty)
    entry_trade = ib.placeOrder(contract, entry_order)
    ib.sleep(1)  # allow the entry to fill before attaching the protective stop

    stop_order = StopOrder(stop_action, qty, stop_price)
    stop_order.tif = "GTC"  # good-til-cancelled -- must survive across sessions
                             # since holds may carry overnight (swing-only design)
    ib.placeOrder(contract, stop_order)

    portfolio.open_position(
        Position(symbol=symbol, quantity=qty if is_long else -qty, entry_price=price, stop_price=stop_price, opened_at=util.now())
    )
    trade_log.log_trade(
        symbol=symbol, action=action.lower(), quantity=qty, price=price,
        stop_price=stop_price, strategy=strategy_name, regime=regime.value,
        equity_after=portfolio.equity,
    )
    logger.info("Opened %s %s qty=%s @ %s stop=%s (%s/%s)", action, symbol, qty, price, stop_price, strategy_name, regime.value)


def place_exit(contract, symbol: str, price: float, strategy_name: str, regime: Regime) -> None:
    position = portfolio.get_position(symbol)
    if position is None:
        return

    action = "SELL" if position.is_long else "BUY"
    ib.placeOrder(contract, MarketOrder(action, abs(position.quantity)))
    portfolio.close_position(symbol)
    trade_log.log_trade(
        symbol=symbol, action="exit", quantity=abs(position.quantity), price=price,
        stop_price=position.stop_price, strategy=strategy_name, regime=regime.value,
        equity_after=portfolio.equity,
    )
    logger.info("Closed %s @ %s", symbol, price)


def flatten_all(bar_lists, contracts) -> None:
    prices = current_open_price_map(bar_lists)
    for symbol in list(portfolio.positions.keys()):
        place_exit(contracts[symbol], symbol, prices.get(symbol, 0.0), "circuit_breaker", Regime.RANGING)


def on_bar_update(symbol: str, contract, bar_lists: dict):
    def handler(bars, has_new_bar: bool):
        global halted
        if not has_new_bar:
            return  # ignore intrabar ticks; only act on completed bars

        df = util.df(bars)
        if df is None or len(df) < max(config.MR_MA_PERIOD, config.TF_SLOW_MA_PERIOD, config.ADX_PERIOD) + 1:
            return  # not enough history yet

        latest_price = df["close"].iloc[-1]
        atr_value = atr(df, config.ATR_PERIOD).iloc[-1]

        portfolio.update_equity(portfolio.equity)  # placeholder until reconciled with ib.accountSummary()

        if risk_manager.circuit_breaker_triggered(portfolio) and not halted:
            halted = True
            send_slack_alert(
                f":rotating_light: Drawdown circuit breaker triggered "
                f"({portfolio.current_drawdown_pct():.1%} from peak). Flattening all positions and halting."
            )
            flatten_all(bar_lists, {symbol: contract})
            return

        if halted:
            return  # no new entries until manually reviewed and restarted

        regime = current_regime(df)
        strategy = strategy_for(regime)
        has_position = portfolio.has_position(symbol)
        position = portfolio.get_position(symbol)

        signal = strategy.generate_signal(
            df, has_open_position=has_position,
            position_is_long=position.is_long if position else None,
        )

        if signal is Signal.EXIT:
            place_exit(contract, symbol, latest_price, strategy.__name__, regime)
            return

        if signal is Signal.FLAT or has_position or pd_isna(atr_value):
            return

        is_long = signal is Signal.BUY
        qty = risk_manager.position_size(portfolio.equity, atr_value, latest_price)
        if qty <= 0:
            return

        notional = qty * latest_price
        prices = current_open_price_map(bar_lists)
        if not risk_manager.exposure_cap_allows(portfolio, is_long, notional, prices):
            logger.info("Skipping %s entry for %s: same-direction exposure cap reached", signal.value, symbol)
            return

        stop_price = risk_manager.stop_price_for(latest_price, atr_value, is_long)
        place_entry(contract, symbol, is_long, qty, latest_price, stop_price, strategy.__name__, regime)

    return handler


def pd_isna(value) -> bool:
    return value != value  # NaN check without importing pandas here


def shutdown(*_args) -> None:
    logger.info("Shutting down, disconnecting from IB...")
    ib.disconnect()
    sys.exit(0)


def main() -> None:
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    ib.connect(config.IB_HOST, config.IB_PORT, clientId=config.IB_CLIENT_ID)
    logger.info("Connected to IBKR at %s:%s", config.IB_HOST, config.IB_PORT)

    bar_lists = {}
    contracts = {}
    for symbol in config.INSTRUMENTS:
        contract = Stock(symbol, "SMART", "USD")
        ib.qualifyContracts(contract)
        contracts[symbol] = contract

        bars = ib.reqHistoricalData(
            contract, endDateTime="", durationStr=config.HISTORICAL_DURATION,
            barSizeSetting=config.BAR_SIZE, whatToShow="TRADES", useRTH=True,
            keepUpToDate=True,
        )
        bar_lists[symbol] = bars
        bars.updateEvent += on_bar_update(symbol, contract, bar_lists)
        logger.info("Subscribed to live %s bars for %s", config.BAR_SIZE, symbol)

    ib.run()


if __name__ == "__main__":
    main()
