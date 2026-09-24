"""
Standalone unit tests for bot/main.py's _watch_trade() -- the fill-watcher
that handles two real incidents from 2026-09-24 (see CLAUDE.md):

1. A 15s "give up on timeout" path that silently detached its listener
   and missed a SPY fill that landed ~19 minutes later, leaving the
   position live and completely unprotected.
2. A spurious IBKR `Cancelled` orderStatus transition (fired while IBKR
   auto-corrects a missing TIF, e.g. "Error 10349: Order TIF was set to
   DAY based on order preset") being treated as unconditionally final --
   the same order then continued and filled seconds later under the same
   orderId, invisible to the bot because the listener was already
   detached. Two GOOGL SELL signals each silently filled this way,
   stacking into an untracked, unprotected 10-share short.

Uses ib_insync's own Trade/Order/OrderStatus/Fill dataclasses directly
(no live IBKR connection) so the exact statusEvent-driven code path in
_watch_trade is exercised for real, not just reasoned about. Needs
ib_compat.ensure_event_loop() before importing ib_insync, same as every
other entry point in this project.

Run: python -m unittest tests.test_watch_trade -v
"""
import asyncio
import unittest

import ib_compat

ib_compat.ensure_event_loop()

from ib_insync import CommissionReport, Contract, Fill, MarketOrder, OrderStatus, Trade

import bot.main as bot_main


def make_trade(symbol="TEST", action="BUY", qty=1.0):
    contract = Contract(symbol=symbol)
    order = MarketOrder(action, qty)
    trade = Trade(contract=contract, order=order, orderStatus=OrderStatus(status="PendingSubmit"))
    return trade


def add_fill(trade, price, commission=1.0):
    fill = Fill(
        contract=trade.contract, execution=None,
        commissionReport=CommissionReport(commission=commission),
        time=None,
    )
    trade.fills.append(fill)


async def _run_watch_trade_scenario(events_and_delays, timeout=15.0, cancel_grace=0.05):
    """
    events_and_delays: list of (delay_seconds, status, avgFillPrice) tuples.
    Schedules each status transition at its delay, drives _watch_trade for
    real via the asyncio loop, and returns the (avg_price, commission)
    on_result was eventually called with (or None if never called within
    a short settle window after the last scheduled event).
    """
    trade = make_trade()
    result = {}

    def on_result(avg_price, commission):
        result["avg_price"] = avg_price
        result["commission"] = commission

    bot_main._watch_trade(trade, "TEST", on_result, timeout=timeout, cancel_grace=cancel_grace)

    async def fire(delay, status, avg_price):
        await asyncio.sleep(delay)
        trade.orderStatus.status = status
        trade.orderStatus.avgFillPrice = avg_price
        if status == "Filled":
            add_fill(trade, avg_price)
        trade.statusEvent.emit(trade)

    await asyncio.gather(*(fire(d, s, p) for d, s, p in events_and_delays))
    # Let any grace-period call_later callbacks scheduled by the last event
    # actually run before we check the result.
    await asyncio.sleep(cancel_grace + 0.1)
    return result


class TestWatchTradeSpuriousCancel(unittest.TestCase):
    """Incident #2 (2026-09-24): a Cancelled status that isn't really final."""

    def test_spurious_cancelled_then_filled_is_not_treated_as_dead(self):
        # Mirrors the real GOOGL incident: PendingSubmit -> Cancelled
        # (IBKR's TIF-autocorrect notice) -> Filled, all within a couple
        # hundred ms in reality. _watch_trade must end up reporting the
        # FILL, not silently giving up on the Cancelled snapshot.
        result = asyncio.run(_run_watch_trade_scenario([
            (0.0, "Cancelled", 0.0),
            (0.02, "Filled", 340.63),
        ]))
        self.assertIn("avg_price", result, "on_result was never called -- the fill was dropped")
        self.assertEqual(result["avg_price"], 340.63)

    def test_genuinely_cancelled_order_is_still_reported_as_not_filled(self):
        # A real cancel (no resurrection afterward) must still resolve --
        # the grace period must not make _watch_trade hang forever on an
        # order that's actually dead.
        result = asyncio.run(_run_watch_trade_scenario([
            (0.0, "Cancelled", 0.0),
        ]))
        self.assertIn("avg_price", result, "a genuinely cancelled order should still resolve")
        self.assertEqual(result["avg_price"], 0.0)

    def test_api_cancelled_also_gets_grace_period(self):
        result = asyncio.run(_run_watch_trade_scenario([
            (0.0, "ApiCancelled", 0.0),
            (0.02, "Filled", 100.0),
        ]))
        self.assertIn("avg_price", result)
        self.assertEqual(result["avg_price"], 100.0)

    def test_plain_fill_resolves_immediately_no_grace_needed(self):
        # Sanity check: a normal, uncomplicated fill (the overwhelmingly
        # common case) must not be slowed down by the new grace-period
        # logic at all -- it isn't a Cancelled/ApiCancelled status.
        result = asyncio.run(_run_watch_trade_scenario([
            (0.0, "Filled", 50.0),
        ], cancel_grace=5.0))  # even a large grace value shouldn't matter here
        self.assertIn("avg_price", result)
        self.assertEqual(result["avg_price"], 50.0)


if __name__ == "__main__":
    unittest.main()
