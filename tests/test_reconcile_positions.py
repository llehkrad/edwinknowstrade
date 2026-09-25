"""
Unit tests for bot/main.py's reconcile_positions_from_ibkr() -- specifically
the 2026-09-25 duplicate-stop-order incident.

Real incident: portfolio.has_position() is purely in-memory and resets on
every process restart. Reconciliation used to treat that in-memory "no
record" state as proof a position was unprotected, and placed a FRESH stop
order for it every single time the bot restarted -- even though the
original bracket from a prior run was still resting live at IBKR. After two
restarts, GOOGL and IWM each had two separate, non-OCA-linked BUY-to-cover
stop orders for the FULL position size. If price had moved against either
position, both stops could have triggered, buying back double the shares
needed and flipping the position net long.

Fix: reconciliation now checks IBKR's own reqAllOpenOrders() for an
existing closing-direction order on that symbol before ever placing a new
stop -- only a position with genuinely no resting closing order gets a
fresh one.

No live IBKR connection needed: bot.main.ib and bot.main.portfolio are
monkeypatched with lightweight stubs.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import ib_compat

ib_compat.ensure_event_loop()

import bot.main as bot_main
from bot.portfolio import Portfolio


def make_ib_position(symbol, qty, avg_cost):
    return SimpleNamespace(
        contract=SimpleNamespace(symbol=symbol),
        position=qty,
        avgCost=avg_cost,
    )


def make_open_order(symbol, order_id, action, order_type="STP", aux_price=0.0, lmt_price=0.0):
    return SimpleNamespace(
        contract=SimpleNamespace(symbol=symbol),
        order=SimpleNamespace(orderId=order_id, action=action, orderType=order_type,
                               auxPrice=aux_price, lmtPrice=lmt_price),
    )


class TestReconcileSkipsExistingBracket(unittest.TestCase):
    def setUp(self):
        self._real_ib = bot_main.ib
        self._real_portfolio = bot_main.portfolio
        self._real_cash = bot_main.cash
        bot_main.portfolio = Portfolio()

    def tearDown(self):
        bot_main.ib = self._real_ib
        bot_main.portfolio = self._real_portfolio
        bot_main.cash = self._real_cash

    def test_existing_resting_stop_is_not_duplicated(self):
        # GOOGL short position, with a BUY stop + BUY limit already resting
        # at IBKR from a prior run -- exactly the real incident scenario.
        fake_ib = MagicMock()
        fake_ib.positions.return_value = [make_ib_position("GOOGL", -4.0, 341.97)]
        fake_ib.reqAllOpenOrders.return_value = [
            make_open_order("GOOGL", 87, "BUY", "STP", aux_price=345.67),
            make_open_order("GOOGL", 88, "BUY", "LMT", lmt_price=331.98),
        ]
        bot_main.ib = fake_ib

        contracts = {"GOOGL": SimpleNamespace(symbol="GOOGL")}
        bot_main.reconcile_positions_from_ibkr(contracts)

        fake_ib.placeOrder.assert_not_called()
        self.assertTrue(bot_main.portfolio.has_position("GOOGL"))
        pos = bot_main.portfolio.get_position("GOOGL")
        self.assertEqual(pos.quantity, -4.0)
        self.assertEqual(pos.stop_price, 345.67)

    def test_reconciled_short_credits_cash_correctly(self):
        # The core 2026-09-25 incident: reconciliation adds the position to
        # portfolio.positions (marked-to-market every bar) but must ALSO
        # credit `cash` for the short sale, exactly as place_entry's
        # on_fill would have. Before the fix, cash stayed untouched at
        # ACCOUNT_EQUITY_USD while mark_to_market subtracted the full
        # notional of the short as a pure liability -- fabricating a huge
        # phantom loss (two reconciled shorts collapsed equity from $5000
        # to ~$2216, a fake 55.6% drawdown that tripped the real circuit
        # breaker). Uses the exact real numbers from that incident.
        fake_ib = MagicMock()
        fake_ib.positions.return_value = [
            make_ib_position("GOOGL", -4.0, 341.9696),
            make_ib_position("IWM", -5.0, 281.48546),
        ]
        fake_ib.reqAllOpenOrders.return_value = [
            make_open_order("GOOGL", 87, "BUY", "STP", aux_price=345.67),
            make_open_order("IWM", 90, "BUY", "STP", aux_price=284.53),
        ]
        bot_main.ib = fake_ib
        bot_main.cash = 5000.0  # config.ACCOUNT_EQUITY_USD

        contracts = {"GOOGL": SimpleNamespace(symbol="GOOGL"), "IWM": SimpleNamespace(symbol="IWM")}
        bot_main.reconcile_positions_from_ibkr(contracts)

        # A short sale must CREDIT cash by qty*price (mirrors place_entry's
        # on_fill: `cash += qty * fill_price` for the SELL/short branch).
        expected_cash = 5000.0 + (4.0 * 341.9696) + (5.0 * 281.48546)
        self.assertAlmostEqual(bot_main.cash, expected_cash, places=4)

        # And equity computed from cash + mark-to-market at the SAME price
        # the position was reconciled at must round-trip back to
        # approximately the starting equity, NOT collapse into a phantom
        # ~44% loss.
        bar_lists = {
            "GOOGL": [SimpleNamespace(close=341.9696)],
            "IWM": [SimpleNamespace(close=281.48546)],
        }
        equity = bot_main.mark_to_market_equity(bar_lists)
        self.assertAlmostEqual(equity, 5000.0, places=4)

    def test_genuinely_orphaned_position_still_gets_a_fresh_stop(self):
        # No resting closing order at all -- this IS the case that should
        # still place a brand-new protective stop (the original 2026-09-24
        # SPY-incident fix must keep working).
        fake_ib = MagicMock()
        fake_ib.positions.return_value = [make_ib_position("SPY", 1.0, 763.55)]
        fake_ib.reqAllOpenOrders.return_value = []  # nothing resting at all
        bot_main.ib = fake_ib

        contracts = {"SPY": SimpleNamespace(symbol="SPY")}
        bot_main.reconcile_positions_from_ibkr(contracts)

        fake_ib.placeOrder.assert_called_once()
        self.assertTrue(bot_main.portfolio.has_position("SPY"))

    def test_already_locally_tracked_position_is_skipped_entirely(self):
        # Normal case: on_fill already ran in THIS process, portfolio has
        # a record -- reconciliation must not touch IBKR at all for it.
        from bot.portfolio import Position
        from datetime import datetime
        bot_main.portfolio.open_position(
            Position(symbol="TSLA", quantity=2.0, entry_price=250.0, stop_price=245.0, opened_at=datetime.now())
        )
        fake_ib = MagicMock()
        fake_ib.positions.return_value = [make_ib_position("TSLA", 2.0, 250.0)]
        bot_main.ib = fake_ib

        contracts = {"TSLA": SimpleNamespace(symbol="TSLA")}
        bot_main.reconcile_positions_from_ibkr(contracts)

        fake_ib.reqAllOpenOrders.assert_not_called()
        fake_ib.placeOrder.assert_not_called()


if __name__ == "__main__":
    unittest.main()
