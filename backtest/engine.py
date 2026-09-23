"""
Event-driven backtest engine. Reuses the exact same regime filter, strategy
signal functions, and risk manager as the live bot (bot/regime.py,
bot/strategies/*, bot/risk_manager.py) so backtest and live decision logic
can't silently diverge -- only cost/fill simulation is backtest-specific.

Protective stops are checked against each bar's high/low (not just close),
simulating a resting IBKR stop order that can fill intrabar -- consistent
with the "hard stops, unsupervised overnight" requirement in CLAUDE.md.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

import config
from backtest import costs
from bot import risk_manager
from bot.indicators import atr
from bot.instrument_config import apply_instrument_overrides
from bot.portfolio import Portfolio, Position
from bot.regime import Regime, current_regime
from bot.signal import Signal
from bot.strategy_registry import get_strategies
from bot.trend_filter import build_trend_map, entry_allowed


@dataclass
class Fill:
    timestamp: pd.Timestamp
    symbol: str
    action: str  # buy / sell / exit
    quantity: float
    price: float
    commission: float
    strategy: str
    regime: str
    equity_after: float
    realized_pnl: Optional[float] = None  # set on exit fills only


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame  # indexed by timestamp, single 'equity' column
    fills: List[Fill] = field(default_factory=list)
    halted_at: Optional[pd.Timestamp] = None

    def fills_df(self) -> pd.DataFrame:
        if not self.fills:
            return pd.DataFrame(columns=[f.name for f in Fill.__dataclass_fields__.values()])
        return pd.DataFrame([f.__dict__ for f in self.fills])


def _strategy_for(regime: Regime):
    ranging_strategy, trending_strategy = get_strategies()
    return trending_strategy if regime is Regime.TRENDING else ranging_strategy


def _min_lookback() -> int:
    return max(config.MR_MA_PERIOD, config.TF_SLOW_MA_PERIOD, config.ADX_PERIOD) + 2


def run_backtest(
    data: Dict[str, pd.DataFrame], starting_equity: float = None, daily_data: Dict[str, pd.DataFrame] = None,
    use_instrument_config: bool = False, use_bracket_exits: bool = False,
) -> BacktestResult:
    """
    data: {symbol: DataFrame} indexed by timestamp with open/high/low/close/volume
    columns, as returned by backtest.data.load_universe().
    daily_data: optional {symbol: DataFrame} of daily bars (same shape), used
    for the long-term trend filter (bot/trend_filter.py). If omitted, the
    filter is skipped regardless of config.TREND_FILTER_ENABLED, since there's
    no daily data to gate against.
    use_instrument_config: if True, applies config.INSTRUMENT_CONFIG overrides
    per symbol (bot/instrument_config.py) -- the same per-instrument strategy/
    parameter selection bot/main.py uses live. Default False so grid search
    (backtest/optimize.py) and manual single-shared-config backtests keep
    sweeping one parameter set across all instruments uniformly, unaffected.
    use_bracket_exits: if True, mirrors config.USE_BRACKET_EXITS live: a
    filled entry gets a stop-loss AND a take-profit level (ATR-based, see
    risk_manager.stop_price_for/take_profit_price_for), and the strategy's
    own EXIT signal is ignored entirely -- the position only closes when the
    bar's high/low crosses one of those two levels. Default False so every
    existing (non-bracket) backtest path/result already recorded in
    CLAUDE.md is completely unaffected -- this is strictly opt-in. See
    CLAUDE.md's 2026-09-24 bracket-tp-sl entry for why intrabar high/low
    (not just close) matters here, and the same-bar tie-break convention.
    """
    starting_equity = starting_equity if starting_equity is not None else config.ACCOUNT_EQUITY_USD
    portfolio = Portfolio(equity=starting_equity, peak_equity=starting_equity)
    cash = starting_equity

    apply_trend_filter = config.TREND_FILTER_ENABLED and daily_data is not None
    trend_maps = {symbol: build_trend_map(df) for symbol, df in daily_data.items()} if apply_trend_filter else {}

    last_price: Dict[str, float] = {}
    entry_commissions: Dict[str, float] = {}
    take_profit_prices: Dict[str, float] = {}  # symbol -> level, only populated when use_bracket_exits
    fills: List[Fill] = []
    equity_curve_rows = []
    halted = False
    halted_at = None

    all_timestamps = sorted(set().union(*(df.index for df in data.values())))

    for ts in all_timestamps:
        for symbol, df in data.items():
            if ts not in df.index:
                continue

            if use_instrument_config:
                apply_instrument_overrides(symbol)

            idx = df.index.get_loc(ts)
            window = df.iloc[: idx + 1]
            if len(window) < _min_lookback():
                last_price[symbol] = window["close"].iloc[-1]
                continue

            bar = window.iloc[-1]
            last_price[symbol] = bar["close"]
            position = portfolio.get_position(symbol)

            # 1. Protective stop (and, under use_bracket_exits, take-profit)
            # check takes priority over any signal. Checked against the
            # bar's high/low, not just its close -- a resting IBKR stop or
            # limit order can fill anywhere the price traded intrabar, not
            # only at the bar's final print. Using close-only here would
            # systematically miss/mis-time intrabar exits vs. how a real
            # resting order behaves.
            if position is not None:
                stop_hit = (
                    (position.is_long and bar["low"] <= position.stop_price)
                    or (not position.is_long and bar["high"] >= position.stop_price)
                )

                if use_bracket_exits:
                    tp_price = take_profit_prices.get(symbol)
                    tp_hit = tp_price is not None and (
                        (position.is_long and bar["high"] >= tp_price)
                        or (not position.is_long and bar["low"] <= tp_price)
                    )

                    if stop_hit:
                        # Tie-break convention: if a single bar's high-low
                        # range is wide enough that BOTH the stop and the
                        # take-profit fall inside it, we can't tell from
                        # OHLC data alone which a real resting order would
                        # have hit first intrabar. We deliberately assume
                        # the WORSE outcome (stop-loss triggers first) --
                        # conservative, and avoids the backtest silently
                        # flattering itself by always picking the better of
                        # the two whenever both were technically reachable.
                        cash = _close_position(
                            portfolio, entry_commissions, cash, symbol, position,
                            position.stop_price, ts, "stop_loss", "n/a", fills,
                        )
                        take_profit_prices.pop(symbol, None)
                        portfolio.update_equity(_mark_to_market(cash, portfolio, last_price))
                        position = None
                    elif tp_hit:
                        cash = _close_position(
                            portfolio, entry_commissions, cash, symbol, position,
                            tp_price, ts, "take_profit", "n/a", fills,
                        )
                        take_profit_prices.pop(symbol, None)
                        portfolio.update_equity(_mark_to_market(cash, portfolio, last_price))
                        position = None
                elif stop_hit:
                    cash = _close_position(
                        portfolio, entry_commissions, cash, symbol, position,
                        position.stop_price, ts, "stop_loss", "n/a", fills,
                    )
                    portfolio.update_equity(_mark_to_market(cash, portfolio, last_price))
                    position = None

            if halted:
                continue

            regime = current_regime(window)
            strategy = _strategy_for(regime)
            has_position = position is not None

            sig = strategy.generate_signal(
                window, has_open_position=has_position,
                position_is_long=position.is_long if position else None,
            )

            if sig is Signal.EXIT and position is not None and not use_bracket_exits:
                cash = _close_position(
                    portfolio, entry_commissions, cash, symbol, position,
                    bar["close"], ts, strategy.__name__, regime.value, fills,
                )
                portfolio.update_equity(_mark_to_market(cash, portfolio, last_price))
                continue

            if sig is Signal.FLAT or has_position:
                continue

            if apply_trend_filter:
                trend = trend_maps.get(symbol, {}).get(ts.date())
                if not entry_allowed(sig, trend):
                    continue

            atr_value = atr(window, config.ATR_PERIOD).iloc[-1]
            if pd.isna(atr_value) or atr_value <= 0:
                continue

            is_long = sig is Signal.BUY
            qty = risk_manager.position_size(portfolio.equity, atr_value, bar["close"])
            if qty <= 0:
                continue

            notional = qty * bar["close"]
            if not risk_manager.exposure_cap_allows(portfolio, is_long, notional, last_price):
                continue

            fill_price = costs.fill_price(bar["close"], is_buy=is_long)
            commission = costs.commission(qty, fill_price)
            stop_price = risk_manager.stop_price_for(fill_price, atr_value, is_long)

            if use_bracket_exits:
                take_profit_prices[symbol] = risk_manager.take_profit_price_for(fill_price, atr_value, is_long)

            cash += (-qty * fill_price - commission) if is_long else (qty * fill_price - commission)
            entry_commissions[symbol] = commission
            portfolio.open_position(
                Position(symbol=symbol, quantity=qty if is_long else -qty,
                         entry_price=fill_price, stop_price=stop_price, opened_at=ts)
            )
            portfolio.update_equity(_mark_to_market(cash, portfolio, last_price))
            fills.append(Fill(
                timestamp=ts, symbol=symbol, action="buy" if is_long else "sell",
                quantity=qty, price=fill_price, commission=commission,
                strategy=strategy.__name__, regime=regime.value, equity_after=portfolio.equity,
            ))

        equity_curve_rows.append({"timestamp": ts, "equity": portfolio.equity})

        if not halted and risk_manager.circuit_breaker_triggered(portfolio):
            halted = True
            halted_at = ts
            cash = _flatten_all(portfolio, entry_commissions, cash, last_price, ts, fills)
            portfolio.update_equity(_mark_to_market(cash, portfolio, last_price))
            equity_curve_rows[-1]["equity"] = portfolio.equity

    equity_curve = pd.DataFrame(equity_curve_rows).set_index("timestamp")
    return BacktestResult(equity_curve=equity_curve, fills=fills, halted_at=halted_at)


def _close_position(
    portfolio: Portfolio, entry_commissions: Dict[str, float], cash: float, symbol: str,
    position: Position, price: float, ts, strategy_name: str, regime_value: str, fills: List[Fill],
) -> float:
    is_long = position.is_long
    fill_p = costs.fill_price(price, is_buy=not is_long)  # closing long = sell, closing short = buy
    qty = abs(position.quantity)
    exit_commission = costs.commission(qty, fill_p)

    gross = (fill_p - position.entry_price) * qty if is_long else (position.entry_price - fill_p) * qty
    entry_commission = entry_commissions.pop(symbol, 0.0)
    realized_pnl = gross - entry_commission - exit_commission

    cash += (qty * fill_p - exit_commission) if is_long else (-qty * fill_p - exit_commission)
    portfolio.close_position(symbol)

    fills.append(Fill(
        timestamp=ts, symbol=symbol, action="exit", quantity=qty, price=fill_p,
        commission=exit_commission, strategy=strategy_name, regime=regime_value,
        equity_after=portfolio.equity, realized_pnl=realized_pnl,
    ))
    return cash


def _flatten_all(
    portfolio: Portfolio, entry_commissions: Dict[str, float], cash: float,
    last_price: Dict[str, float], ts, fills: List[Fill],
) -> float:
    for symbol in list(portfolio.positions.keys()):
        position = portfolio.positions[symbol]
        price = last_price.get(symbol, position.entry_price)
        cash = _close_position(portfolio, entry_commissions, cash, symbol, position, price, ts, "circuit_breaker", "n/a", fills)
    return cash


def _mark_to_market(cash: float, portfolio: Portfolio, last_price: Dict[str, float]) -> float:
    unrealized = sum(
        pos.quantity * last_price.get(symbol, pos.entry_price)
        for symbol, pos in portfolio.positions.items()
    )
    return cash + unrealized
