"""
Execution layer entry point. Pure deterministic if/then logic -- no AI/model
involved at runtime (see CLAUDE.md non-goals). Polls candles via ib_insync's
keepUpToDate live bars -> computes indicators -> regime filter picks a
strategy -> risk manager sizes/vets the trade -> places a market order,
confirms the actual IBKR fill, and attaches a hard stop -> logs to CSV.

Equity is tracked internally (cash + mark-to-market of open positions),
starting from config.ACCOUNT_EQUITY_USD, the same cash-accounting approach
backtest/engine.py uses -- NOT reconciled against ib.accountSummary()'s
NetLiquidation. This is deliberate: a paper trading account is seeded by
IBKR with an unrelated ~$1M balance, not the operator's real target account
size, so trusting the broker's reported equity would size positions and
gate the drawdown circuit breaker against the wrong number entirely.

Run under systemd with Restart=always on the dedicated Lightsail box, per
CLAUDE.md. NOT a finished live-trading system: strategy parameters in
config.py are placeholders pending backtesting, and the pre-live checklist
(6mo+ backtest -> 2+ weeks paper trading -> live keys) has not been done yet.
"""
import logging
import signal
import sys
from typing import Dict

import ib_compat

ib_compat.ensure_event_loop()

from ib_insync import IB, LimitOrder, MarketOrder, Stock, StopOrder, util

import config
from bot import risk_manager, trade_log
from bot.alerts import send_slack_alert
from bot.indicators import atr
from bot.instrument_config import apply_instrument_overrides
from bot.portfolio import Portfolio, Position
from bot.regime import Regime, current_regime
from bot.signal import Signal
from bot.strategy_registry import get_strategies
from bot.trend_filter import build_trend_map, entry_allowed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bot.main")

ib = IB()
portfolio = Portfolio()
cash = config.ACCOUNT_EQUITY_USD
entry_commissions: Dict[str, float] = {}
trend_maps: Dict[str, dict] = {}  # symbol -> {date: "bullish"|"bearish"|None}, see bot/trend_filter.py
halted = False  # set True once the circuit breaker fires; blocks new entries


def strategy_for(regime: Regime):
    ranging_strategy, trending_strategy = get_strategies()
    return trending_strategy if regime is Regime.TRENDING else ranging_strategy


def current_open_price_map(bar_lists) -> dict:
    return {symbol: bar_list[-1].close for symbol, bar_list in bar_lists.items() if bar_list}


def mark_to_market_equity(bar_lists) -> float:
    prices = current_open_price_map(bar_lists)
    unrealized = sum(
        pos.quantity * prices.get(symbol, pos.entry_price)
        for symbol, pos in portfolio.positions.items()
    )
    return cash + unrealized


def _watch_trade(trade, symbol: str, on_result, timeout: float = 15.0) -> None:
    """
    Non-blocking replacement for the old ib.sleep()-polling wait-for-fill loop.

    place_entry()/place_exit() are called synchronously from inside
    on_bar_update()'s handler(), which is itself an ib_insync event callback
    already running on the asyncio event loop. ib.sleep() (and anything else
    that goes through ib_insync's util.run()) calls loop.run_until_complete()
    internally, which crashes with 'RuntimeError: This event loop is already
    running' when invoked from a callback that the loop is already inside --
    hit live 2026-09-23 on a QQQ entry, see CLAUDE.md. There is no way to
    block-and-pump from inside a running-loop callback, so this doesn't poll
    at all: it races trade.statusEvent (fires on every status change,
    including fills and cancels) against a call_later timeout, and invokes
    on_result(avg_price, commission) exactly once, whichever happens first --
    same effective timeout/logging behavior as the old polling loop, just
    event-driven instead of blocking.
    """
    done = False

    def finish(avg_price: float, commission: float) -> None:
        nonlocal done
        if done:
            return
        done = True
        trade.statusEvent -= on_status
        timeout_handle.cancel()
        if avg_price <= 0:
            logger.error(
                "Order for %s did not report a fill within %.0fs (status=%s)",
                symbol, timeout, trade.orderStatus.status,
            )
        on_result(avg_price, commission)

    def commission_total() -> float:
        return sum(
            fill.commissionReport.commission
            for fill in trade.fills
            if fill.commissionReport is not None
        )

    def on_status(t) -> None:
        if not t.isDone():
            return
        finish(t.orderStatus.avgFillPrice or 0.0, commission_total())

    def on_timeout() -> None:
        finish(trade.orderStatus.avgFillPrice or 0.0, commission_total())

    trade.statusEvent += on_status
    timeout_handle = util.getLoop().call_later(timeout, on_timeout)

    if trade.isDone():  # already terminal (e.g. filled before we attached the listener)
        on_status(trade)


def _watch_bracket(stop_trade, tp_trade, symbol: str, on_result) -> None:
    """
    Watches a resting stop-loss/take-profit OCO pair placed by place_entry()
    when config.USE_BRACKET_EXITS is True.

    Unlike _watch_trade() (built for an immediate market order's fill
    confirmation, with a 15s timeout), a bracket leg is a resting order that
    may sit for hours or days before filling -- holds can carry overnight
    (config.ALLOW_OVERNIGHT_HOLDS, swing-only design) -- so this listens
    indefinitely on both legs' statusEvent, no timeout. Whichever leg fills
    first calls on_result(fill_price, commission, was_stop) exactly once.
    IBKR's own OCO group (matching ocaGroup + ocaType=1 on both orders, set
    in place_entry) cancels the other leg automatically once one fills --
    that resulting "Cancelled" status on the sibling is swallowed here, not
    treated as an error or a second fill.
    """
    done = False

    def commission_total(trade) -> float:
        return sum(
            fill.commissionReport.commission
            for fill in trade.fills
            if fill.commissionReport is not None
        )

    def finish(trade, was_stop: bool) -> None:
        nonlocal done
        if done:
            return
        done = True
        stop_trade.statusEvent -= on_stop_status
        tp_trade.statusEvent -= on_tp_status
        on_result(trade.orderStatus.avgFillPrice or 0.0, commission_total(trade), was_stop)

    def on_stop_status(t) -> None:
        if t.orderStatus.status == "Filled":
            finish(t, True)

    def on_tp_status(t) -> None:
        if t.orderStatus.status == "Filled":
            finish(t, False)

    stop_trade.statusEvent += on_stop_status
    tp_trade.statusEvent += on_tp_status

    # Handle the (unlikely but possible) case where a leg is already
    # filled by the time we attach the listener.
    if stop_trade.orderStatus.status == "Filled":
        finish(stop_trade, True)
    elif tp_trade.orderStatus.status == "Filled":
        finish(tp_trade, False)


def place_entry(contract, symbol: str, is_long: bool, qty: float, atr_value: float, strategy_name: str, regime: Regime) -> None:
    action = "BUY" if is_long else "SELL"
    stop_action = "SELL" if is_long else "BUY"

    def on_fill(fill_price: float, commission: float) -> None:
        global cash
        if fill_price <= 0:
            logger.error("Entry for %s did not fill -- no position opened, no order left resting.", symbol)
            return

        stop_price = risk_manager.stop_price_for(fill_price, atr_value, is_long)

        cash += (-qty * fill_price - commission) if is_long else (qty * fill_price - commission)
        entry_commissions[symbol] = commission
        portfolio.open_position(
            Position(symbol=symbol, quantity=qty if is_long else -qty, entry_price=fill_price, stop_price=stop_price, opened_at=util.now())
        )
        trade_log.log_trade(
            symbol=symbol, action=action.lower(), quantity=qty, price=fill_price, commission=commission,
            stop_price=stop_price, strategy=strategy_name, regime=regime.value,
            equity_after=portfolio.equity, realized_pnl=None,
        )

        if config.USE_BRACKET_EXITS:
            take_profit_price = risk_manager.take_profit_price_for(fill_price, atr_value, is_long)

            oca_group = f"{symbol}_{util.now().timestamp()}"
            stop_order = StopOrder(stop_action, qty, stop_price)
            stop_order.tif = "GTC"
            stop_order.ocaGroup = oca_group
            stop_order.ocaType = 1  # cancel remaining orders in the group on any fill, no blocking

            tp_order = LimitOrder(stop_action, qty, take_profit_price)
            tp_order.tif = "GTC"
            tp_order.ocaGroup = oca_group
            tp_order.ocaType = 1

            stop_trade = ib.placeOrder(contract, stop_order)
            tp_trade = ib.placeOrder(contract, tp_order)
            logger.info("Opened %s %s qty=%s @ %s bracket: stop=%s take_profit=%s commission=%.2f (%s/%s)",
                        action, symbol, qty, fill_price, stop_price, take_profit_price, commission, strategy_name, regime.value)
            _watch_bracket(stop_trade, tp_trade, symbol, _make_bracket_exit_handler(symbol, fill_price, is_long, qty))
        else:
            stop_order = StopOrder(stop_action, qty, stop_price)
            stop_order.tif = "GTC"  # good-til-cancelled -- must survive across sessions
                                     # since holds may carry overnight (swing-only design)
            ib.placeOrder(contract, stop_order)
            logger.info("Opened %s %s qty=%s @ %s stop=%s commission=%.2f (%s/%s)",
                        action, symbol, qty, fill_price, stop_price, commission, strategy_name, regime.value)

    entry_trade = ib.placeOrder(contract, MarketOrder(action, qty))
    _watch_trade(entry_trade, symbol, on_fill)


def _make_bracket_exit_handler(symbol: str, entry_price: float, is_long: bool, qty: float):
    """
    Returns the on_result callback _watch_bracket() invokes when either the
    stop-loss or take-profit leg fills. Mirrors place_exit()'s on_fill
    accounting (realized PnL, cash, portfolio, trade log) since this is the
    bracket-exit equivalent of that path -- the position is closed by IBKR
    filling a resting order, not by the bot placing a market exit order.
    """
    def on_result(fill_price: float, commission: float, was_stop: bool) -> None:
        global cash
        if fill_price <= 0:
            logger.error("Bracket exit for %s did not report a fill -- position left open in local state, check IBKR manually.", symbol)
            return

        gross = (fill_price - entry_price) * qty if is_long else (entry_price - fill_price) * qty
        entry_commission = entry_commissions.pop(symbol, 0.0)
        realized_pnl = gross - entry_commission - commission

        cash += (qty * fill_price - commission) if is_long else (-qty * fill_price - commission)
        position = portfolio.get_position(symbol)
        stop_price = position.stop_price if position else None
        portfolio.close_position(symbol)

        exit_kind = "stop_loss" if was_stop else "take_profit"
        trade_log.log_trade(
            symbol=symbol, action="exit", quantity=qty, price=fill_price, commission=commission,
            stop_price=stop_price, strategy=exit_kind, regime="n/a",
            equity_after=portfolio.equity, realized_pnl=realized_pnl,
        )
        logger.info("Closed %s @ %s via %s commission=%.2f realized_pnl=%.2f", symbol, fill_price, exit_kind, commission, realized_pnl)

    return on_result


def place_exit(contract, symbol: str, strategy_name: str, regime: Regime) -> None:
    position = portfolio.get_position(symbol)
    if position is None:
        return

    is_long = position.is_long
    action = "SELL" if is_long else "BUY"
    qty = abs(position.quantity)

    def on_fill(fill_price: float, commission: float) -> None:
        global cash
        if fill_price <= 0:
            logger.error("Exit for %s did not report a fill -- position left open in local state, check IBKR manually.", symbol)
            return

        gross = (fill_price - position.entry_price) * qty if is_long else (position.entry_price - fill_price) * qty
        entry_commission = entry_commissions.pop(symbol, 0.0)
        realized_pnl = gross - entry_commission - commission

        cash += (qty * fill_price - commission) if is_long else (-qty * fill_price - commission)
        portfolio.close_position(symbol)

        trade_log.log_trade(
            symbol=symbol, action="exit", quantity=qty, price=fill_price, commission=commission,
            stop_price=position.stop_price, strategy=strategy_name, regime=regime.value,
            equity_after=portfolio.equity, realized_pnl=realized_pnl,
        )
        logger.info("Closed %s @ %s commission=%.2f realized_pnl=%.2f", symbol, fill_price, commission, realized_pnl)

    exit_trade = ib.placeOrder(contract, MarketOrder(action, qty))
    _watch_trade(exit_trade, symbol, on_fill)


def flatten_all(contracts: dict) -> None:
    # NOTE: this places a market order to close each position but does not
    # explicitly cancel that position's resting protective order(s) (the
    # single StopOrder in normal mode, or the stop+take-profit OCO pair
    # under config.USE_BRACKET_EXITS) -- a pre-existing gap (not introduced
    # by bracket exits) that predates this function. IBKR will reject a
    # resting order against a symbol with no position once it's flat, so
    # this is not expected to open a new unintended position, but stale
    # orders can still show up in TWS until manually cancelled.
    for symbol in list(portfolio.positions.keys()):
        place_exit(contracts[symbol], symbol, "circuit_breaker", Regime.RANGING)


def on_bar_update(symbol: str, contract, bar_lists: dict, contracts: dict):
    def handler(bars, has_new_bar: bool = False):
        # On reconnect, ib_insync re-fires updateEvent with just `bars` (no
        # has_new_bar) while resyncing subscriptions -- default to False so
        # that resync blip is ignored like any other intrabar tick, instead
        # of crashing with a missing-argument TypeError.
        global halted
        if not has_new_bar:
            return  # ignore intrabar ticks; only act on completed bars

        apply_instrument_overrides(symbol)

        df = util.df(bars)
        if df is None or len(df) < max(config.MR_MA_PERIOD, config.TF_SLOW_MA_PERIOD, config.ADX_PERIOD) + 1:
            return  # not enough history yet

        latest_price = df["close"].iloc[-1]
        atr_value = atr(df, config.ATR_PERIOD).iloc[-1]

        portfolio.update_equity(mark_to_market_equity(bar_lists))

        if risk_manager.circuit_breaker_triggered(portfolio) and not halted:
            halted = True
            send_slack_alert(
                f":rotating_light: Drawdown circuit breaker triggered "
                f"({portfolio.current_drawdown_pct():.1%} from peak). Flattening all positions and halting."
            )
            flatten_all(contracts)
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
            if config.USE_BRACKET_EXITS:
                # Exits are bracket-driven only (resting stop-loss/take-profit
                # OCO pair placed at entry, see place_entry) -- the strategy's
                # own EXIT signal is ignored entirely while a bracket is
                # active, per config.USE_BRACKET_EXITS's contract.
                return
            place_exit(contract, symbol, strategy.__name__, regime)
            return

        if signal is Signal.FLAT or has_position or pd_isna(atr_value):
            return

        bar_date = df["date"].iloc[-1]
        bar_date = bar_date.date() if hasattr(bar_date, "date") else bar_date
        trend = trend_maps.get(symbol, {}).get(bar_date)
        if not entry_allowed(signal, trend):
            logger.info("Skipping %s entry for %s: against long-term trend filter (trend=%s)", signal.value, symbol, trend)
            return

        is_long = signal is Signal.BUY
        qty = risk_manager.position_size(portfolio.equity, atr_value, latest_price, force_whole_shares=True)
        if qty <= 0:
            return

        notional = qty * latest_price
        prices = current_open_price_map(bar_lists)
        if not risk_manager.exposure_cap_allows(portfolio, is_long, notional, prices):
            logger.info("Skipping %s entry for %s: same-direction exposure cap reached", signal.value, symbol)
            return

        place_entry(contract, symbol, is_long, qty, atr_value, strategy.__name__, regime)

    return handler


def pd_isna(value) -> bool:
    return value != value  # NaN check without importing pandas here


def on_daily_bar_update(symbol: str):
    def handler(bars, has_new_bar: bool = False):
        if not has_new_bar:
            return
        df = util.df(bars)
        if df is None or len(df) < 2:
            return
        trend_maps[symbol] = build_trend_map(df.set_index("date"))
    return handler


def shutdown(*_args) -> None:
    logger.info("Shutting down, disconnecting from IB...")
    ib.disconnect()
    sys.exit(0)


def main() -> None:
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    ib.connect(config.IB_HOST, config.IB_PORT, clientId=config.IB_CLIENT_ID)
    logger.info("Connected to IBKR at %s:%s", config.IB_HOST, config.IB_PORT)
    logger.info("Tracking equity internally from config.ACCOUNT_EQUITY_USD=%s (not IBKR's reported account balance)",
                config.ACCOUNT_EQUITY_USD)

    for symbol in config.INSTRUMENTS:
        logger.info("Instrument config for %s: %s", symbol, config.INSTRUMENT_CONFIG.get(symbol, "(uses global defaults)"))

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
        bars.updateEvent += on_bar_update(symbol, contract, bar_lists, contracts)
        logger.info("Subscribed to live %s bars for %s", config.BAR_SIZE, symbol)

        if config.TREND_FILTER_ENABLED:
            daily_bars = ib.reqHistoricalData(
                contract, endDateTime="", durationStr="2 Y",
                barSizeSetting=config.TREND_FILTER_BAR_SIZE, whatToShow="TRADES", useRTH=True,
                keepUpToDate=True,
            )
            daily_bars.updateEvent += on_daily_bar_update(symbol)
            daily_df = util.df(daily_bars)
            if daily_df is not None and len(daily_df) >= 2:
                trend_maps[symbol] = build_trend_map(daily_df.set_index("date"))
            logger.info("Subscribed to daily trend-filter bars for %s (%d-day SMA)", symbol, config.TREND_FILTER_SMA_PERIOD)

    ib.run()


if __name__ == "__main__":
    main()
