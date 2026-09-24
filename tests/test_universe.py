"""
Standalone unit tests for bot/universe.py (hot-reloadable config/universe.json
handling). Uses only stdlib unittest -- no pytest dependency required.

Deliberately does NOT import bot/main.py or ib_insync: this project's
Windows dev environment cannot import ib_insync at all (eventkit calls
asyncio.get_event_loop() at import time, which Python 3.14 no longer
implicitly creates -- see ib_compat.py), so bot/main.py itself can't be
imported/run here. bot/universe.py has no ib_insync dependency, so it's
fully testable in isolation.

Run: python -m unittest tests.test_universe -v
"""
import json
import os
import tempfile
import unittest

import config
import bot.universe as universe_module
from bot.universe import (
    diff_universe,
    load_universe,
    reconcile_pending_disables,
    request_disable,
)


class FakePortfolio:
    """Minimal stand-in for bot.portfolio.Portfolio -- only has_position() is used."""

    def __init__(self, open_symbols=()):
        self._open_symbols = set(open_symbols)

    def has_position(self, symbol: str) -> bool:
        return symbol in self._open_symbols


class UniverseTestCase(unittest.TestCase):
    def setUp(self):
        # bot.universe keeps a module-level _last_known_good cache so a
        # malformed file can fall back to the last successfully-parsed
        # universe -- reset it before each test so tests can't leak state
        # into each other via that shared global.
        universe_module._last_known_good = {}

        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self._orig_universe_config_path = config.UNIVERSE_CONFIG_PATH
        config.UNIVERSE_CONFIG_PATH = self.path

    def tearDown(self):
        config.UNIVERSE_CONFIG_PATH = self._orig_universe_config_path
        if os.path.exists(self.path):
            os.remove(self.path)

    def _write(self, obj) -> None:
        with open(self.path, "w") as f:
            json.dump(obj, f)

    def _read_raw(self) -> dict:
        with open(self.path, "r") as f:
            return json.load(f)


class TestLoadUniverse(UniverseTestCase):
    def test_valid_file(self):
        self._write({
            "SPY": {"status": "active"},
            "QQQ": {"status": "pending_disable"},
            "IWM": {"status": "disabled"},
        })
        result = load_universe(self.path)
        self.assertEqual(result, {"SPY": "active", "QQQ": "pending_disable", "IWM": "disabled"})

    def test_malformed_file_first_load_falls_back_to_empty(self):
        self._write("this is not a valid universe object, just a string")
        result = load_universe(self.path)
        self.assertEqual(result, {})  # no prior good state to fall back to

    def test_malformed_file_falls_back_to_last_known_good(self):
        self._write({"SPY": {"status": "active"}})
        first = load_universe(self.path)
        self.assertEqual(first, {"SPY": "active"})

        # Now corrupt the file (invalid JSON) and reload -- must not crash,
        # must fall back to the previously successfully-loaded universe.
        with open(self.path, "w") as f:
            f.write("{not valid json!!!")

        second = load_universe(self.path)
        self.assertEqual(second, {"SPY": "active"})

    def test_invalid_status_value_falls_back(self):
        self._write({"SPY": {"status": "active"}})
        load_universe(self.path)  # prime last-known-good

        self._write({"SPY": {"status": "not_a_real_status"}})
        result = load_universe(self.path)
        self.assertEqual(result, {"SPY": "active"})  # fell back, didn't crash

    def test_missing_file_does_not_crash(self):
        missing_path = self.path + ".does-not-exist"
        result = load_universe(missing_path)
        self.assertEqual(result, {})


class TestRequestDisable(UniverseTestCase):
    def test_disable_with_open_position_sets_pending_disable(self):
        self._write({"SPY": {"status": "active"}})
        status = request_disable(self.path, "SPY", has_open_position=True)
        self.assertEqual(status, "pending_disable")
        self.assertEqual(self._read_raw()["SPY"]["status"], "pending_disable")

    def test_disable_while_flat_sets_disabled(self):
        self._write({"SPY": {"status": "active"}})
        status = request_disable(self.path, "SPY", has_open_position=False)
        self.assertEqual(status, "disabled")
        self.assertEqual(self._read_raw()["SPY"]["status"], "disabled")

    def test_disable_preserves_other_symbols(self):
        self._write({"SPY": {"status": "active"}, "QQQ": {"status": "active"}})
        request_disable(self.path, "SPY", has_open_position=False)
        raw = self._read_raw()
        self.assertEqual(raw["SPY"]["status"], "disabled")
        self.assertEqual(raw["QQQ"]["status"], "active")


class TestReconcilePendingDisables(UniverseTestCase):
    def test_flips_pending_disable_to_disabled_once_flat(self):
        self._write({"SPY": {"status": "pending_disable"}, "QQQ": {"status": "active"}})
        universe = {"SPY": "pending_disable", "QQQ": "active"}
        portfolio = FakePortfolio(open_symbols=())  # SPY has no open position -- flat

        transitioned = reconcile_pending_disables(universe, portfolio)

        self.assertEqual(transitioned, ["SPY"])
        self.assertEqual(universe["SPY"], "disabled")
        self.assertEqual(universe["QQQ"], "active")  # untouched
        self.assertEqual(self._read_raw()["SPY"]["status"], "disabled")  # written to disk too

    def test_leaves_pending_disable_alone_while_position_still_open(self):
        self._write({"SPY": {"status": "pending_disable"}})
        universe = {"SPY": "pending_disable"}
        portfolio = FakePortfolio(open_symbols=("SPY",))  # still open

        transitioned = reconcile_pending_disables(universe, portfolio)

        self.assertEqual(transitioned, [])
        self.assertEqual(universe["SPY"], "pending_disable")
        self.assertEqual(self._read_raw()["SPY"]["status"], "pending_disable")  # file untouched

    def test_no_pending_disable_symbols_is_a_noop(self):
        self._write({"SPY": {"status": "active"}})
        universe = {"SPY": "active"}
        portfolio = FakePortfolio(open_symbols=("SPY",))

        transitioned = reconcile_pending_disables(universe, portfolio)

        self.assertEqual(transitioned, [])
        self.assertEqual(universe["SPY"], "active")


class TestDiffUniverse(unittest.TestCase):
    def test_newly_active_detects_new_and_reactivated_symbols(self):
        old = {"SPY": "active", "QQQ": "disabled", "IWM": "pending_disable"}
        new = {"SPY": "active", "QQQ": "active", "IWM": "active", "TSLA": "active"}

        newly_active, newly_disabled = diff_universe(old, new)

        self.assertEqual(set(newly_active), {"QQQ", "IWM", "TSLA"})
        self.assertEqual(newly_disabled, [])

    def test_newly_disabled_detects_transitions_from_active_and_pending_disable(self):
        old = {"SPY": "active", "QQQ": "pending_disable", "IWM": "active"}
        new = {"SPY": "disabled", "QQQ": "disabled", "IWM": "active"}

        newly_active, newly_disabled = diff_universe(old, new)

        self.assertEqual(newly_active, [])
        self.assertEqual(set(newly_disabled), {"SPY", "QQQ"})

    def test_unchanged_symbols_are_not_flagged(self):
        old = {"SPY": "active", "QQQ": "disabled"}
        new = {"SPY": "active", "QQQ": "disabled"}

        newly_active, newly_disabled = diff_universe(old, new)

        self.assertEqual(newly_active, [])
        self.assertEqual(newly_disabled, [])

    def test_symbol_removed_entirely_from_new_is_not_newly_disabled(self):
        # diff_universe only iterates new.items() -- a symbol dropped from
        # the file entirely (not set to "disabled") is not reported as a
        # transition either way; this documents that behavior.
        old = {"SPY": "active", "QQQ": "active"}
        new = {"SPY": "active"}

        newly_active, newly_disabled = diff_universe(old, new)

        self.assertEqual(newly_active, [])
        self.assertEqual(newly_disabled, [])


if __name__ == "__main__":
    unittest.main()
