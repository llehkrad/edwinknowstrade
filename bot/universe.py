"""
Hot-reloadable symbol universe (config/universe.json), replacing the old
static config.INSTRUMENTS/config.INSTRUMENT_CONFIG lists so symbols can be
activated/deactivated without a code change or bot restart. See
research/unified_strategy_universe_plan_2026-09-24.md for the full design
and CLAUDE.md's 2026-09-24 entry.

Kept as a separate module (not folded into bot/main.py) so backtest/engine.py
can import this same load_universe/diff_universe logic later if a backtest
ever needs to simulate the universe changing mid-run.
"""
import json
import logging

import config

logger = logging.getLogger("bot.universe")

VALID_STATUSES = {"active", "pending_disable", "disabled"}

# Last successfully-parsed universe, per module (not per-path -- this
# project only ever has one universe file). Used as the fallback on a
# malformed file so a bad hand-edit can't crash the live bot.
_last_known_good: dict = {}


def load_universe(path: str) -> dict:
    """
    Reads + parses the universe JSON file into {symbol: status}. On a
    malformed file (bad JSON, wrong shape, invalid status value), logs an
    error and returns the last successfully-loaded universe instead of
    raising (or {} if nothing has ever loaded successfully) -- a bad
    hand-edit to config/universe.json must not crash the live bot.
    """
    global _last_known_good
    try:
        with open(path, "r") as f:
            raw = json.load(f)

        universe = {}
        for symbol, entry in raw.items():
            status = entry.get("status") if isinstance(entry, dict) else None
            if status not in VALID_STATUSES:
                raise ValueError(f"symbol {symbol!r} has invalid status {status!r}")
            universe[symbol] = status

        _last_known_good = universe
        return dict(universe)
    except Exception:
        logger.error(
            "Failed to load universe file %s -- falling back to last-known-good universe %s",
            path, _last_known_good, exc_info=True,
        )
        return dict(_last_known_good)


def _write_statuses(path: str, updates: dict) -> None:
    """Rewrites `path`, setting raw[symbol]["status"] for each symbol in `updates`."""
    with open(path, "r") as f:
        raw = json.load(f)
    for symbol, status in updates.items():
        raw.setdefault(symbol, {})["status"] = status
    with open(path, "w") as f:
        json.dump(raw, f, indent=2)
        f.write("\n")


def request_disable(path: str, symbol: str, has_open_position: bool) -> str:
    """
    Writes "pending_disable" (if has_open_position) or "disabled" (if flat)
    for `symbol` directly to the universe file at `path`. Returns the
    status written.

    This is the function an operator-facing CLI/script calls to request a
    disable; bot/main.py itself never calls this -- it only READS the file
    and reconciles pending_disables going flat (see reconcile_pending_disables).
    """
    status = "pending_disable" if has_open_position else "disabled"
    _write_statuses(path, {symbol: status})
    return status


def reconcile_pending_disables(universe: dict, portfolio) -> list:
    """
    For every symbol with status=="pending_disable" and no open position in
    `portfolio`, flips it to "disabled" IN THE FILE (config.UNIVERSE_CONFIG_PATH,
    so the on-disk state stays truthful) and in the passed-in `universe`
    dict, and returns the list of symbols that just transitioned so
    bot/main.py can unsubscribe them.
    """
    transitioned = [
        symbol for symbol, status in universe.items()
        if status == "pending_disable" and not portfolio.has_position(symbol)
    ]
    if not transitioned:
        return []

    for symbol in transitioned:
        universe[symbol] = "disabled"

    _write_statuses(config.UNIVERSE_CONFIG_PATH, {symbol: "disabled" for symbol in transitioned})
    return transitioned


def diff_universe(old: dict, new: dict):
    """
    Compares two loaded universes (e.g. across an mtime-triggered reload)
    and returns (newly_active, newly_disabled) -- which symbols need
    subscribing/unsubscribing.

    newly_active = active in `new` but not already active in `old` (covers
    a brand-new symbol appearing, or one flipping back from
    disabled/pending_disable to active).
    newly_disabled = disabled in `new` but currently subscribed in `old`
    (active OR pending_disable -- pending_disable symbols stay subscribed
    right up until they flip to disabled, see the state machine in the
    plan doc) -- covers both auto-transitions via reconcile_pending_disables
    and manual file edits that directly set "disabled".
    """
    newly_active = [
        symbol for symbol, status in new.items()
        if status == "active" and old.get(symbol) != "active"
    ]
    newly_disabled = [
        symbol for symbol, status in new.items()
        if status == "disabled" and old.get(symbol) in ("active", "pending_disable")
    ]
    return newly_active, newly_disabled
