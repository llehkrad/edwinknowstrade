# Plan: Unified Entry Strategy + Hot-Reloadable Symbol Universe

**Status:** DRAFT — for review before any code changes land, especially bot/main.py (live).
**Owner decision log:** see bottom.

## Goal

1. Replace per-symbol strategy selection (`config.INSTRUMENT_CONFIG`) with ONE
   standardized entry strategy (`vwap_reversion_only`) and ONE standardized
   exit (fixed 1.0% stop / 3.0% take-profit bracket, 3:1), applied uniformly
   to every symbol. No per-symbol tuning, no regime switch.
2. Move the symbol list out of `config.py` (static, requires code+restart)
   into a hot-reloadable `config/universe.json`, so symbols can be
   activated/deactivated without a restart.
3. Symbols can't be disabled out from under an open position: requesting
   disable on a symbol with an open position marks it `pending_disable`
   (keeps trading normally) and it auto-flips to `disabled` the instant it
   goes flat.

## Why vwap_reversion_only (not a merge)

From `research/fixed_pct_sl_tp_sweep_2026-09-24.md` and a follow-up check:
best-tuned per symbol, `vwap_reversion_only` is positive on 4/5 symbols
(SPY, IWM, QQQ, TSLA; only GOOGL negative at -1.86% worst case), the best
breadth of any single strategy tested. Other strategies (orb_only,
bb_squeeze_only) score higher on individual symbols but only 3/5 symbols
each, and are concentrated in a couple of names (e.g. orb_only is carried
almost entirely by TSLA). No strategy MERGE has been backtested — a
regime-gated reversion+breakout combo is a plausible complementary idea
but stays a separate future backtest task, not something built into this
architecture on a guess.

## Why 1.0%SL/3.0%TP (3:1)

From the same sweep: this combo and 1.5%SL/3.0%TP(2:1) were the only two
of six tested averaging positive OOS return with PF > 1.0 across all 25
symbol/strategy cells. 1.0%/3.0% chosen (over 1.5%/3.0%) for its higher
trade count per cell (avg 25.9 vs 23.1) — more data to confirm the edge is
real, at a near-identical aggregate PF (1.04 vs 1.09).

## Files touched

### New: `config/universe.json`

```json
{
  "SPY":   {"status": "active"},
  "QQQ":   {"status": "active"},
  "IWM":   {"status": "active"},
  "TSLA":  {"status": "active"},
  "GOOGL": {"status": "active"}
}
```

`status` is one of `"active"`, `"pending_disable"`, `"disabled"`. No
per-symbol strategy/params fields — strategy and exits are global/unified
now, this file is purely the on/off switch list. Adding a new symbol later
= add a line with `"status": "active"` and save; the bot picks it up
within one bar (see main.py changes below).

### New: `bot/universe.py`

```
load_universe(path) -> dict[symbol, status]
    Reads + parses the JSON. Raises/logs clearly on malformed file
    (must not crash the live bot on a bad hand-edit -- fall back to
    the last-known-good in-memory universe and log an error).

request_disable(path, symbol, has_open_position: bool) -> str
    Writes "pending_disable" if has_open_position else "disabled"
    directly to the file. Returns the status written. This is the
    function an operator-facing CLI/script calls to request a disable;
    bot/main.py itself never calls this -- it only READS the file and
    reconciles pending_disables going flat (see below).

reconcile_pending_disables(universe: dict, portfolio) -> list[str]
    For every symbol with status=="pending_disable" and no open
    position in `portfolio`, flips it to "disabled" IN THE FILE (so the
    on-disk state stays truthful) and returns the list of symbols that
    just transitioned, so main.py can unsubscribe them.

diff_universe(old: dict, new: dict) -> (newly_active: list[str], newly_disabled: list[str])
    Compares two loaded universes (e.g. across an mtime-triggered
    reload) and returns which symbols need subscribing/unsubscribing.
    "newly_active" = active in new but not currently subscribed.
    "newly_disabled" = disabled in new but currently subscribed
    (covers both auto-transitions via reconcile and manual file edits
    that directly set "disabled").
```

Kept as a separate module (not folded into main.py) so backtest/engine.py
can import the same `load_universe`/`diff_universe` logic later if a
backtest ever needs to simulate the universe changing mid-run — not
needed for the current backtest scripts (they take an explicit symbol
list via `--symbols`), but keeps live and backtest reading the identical
file format if that need comes up.

### Changed: `config.py`

Removed:
- `INSTRUMENTS = [...]` (moves to `config/universe.json`)
- `INSTRUMENT_CONFIG = {...}` (no longer needed -- no per-symbol
  strategy/param overrides once strategy+exits are unified)

Changed:
- `STRATEGY_SET = "vwap_reversion_only"` (was `"sma_zscore"`) -- now the
  PERMANENT default, not swapped per-symbol.
- `USE_BRACKET_EXITS = True` (was `False`)
- `STOP_LOSS_MODE = "fixed_pct"` (was `"atr"`)
- `FIXED_STOP_LOSS_PCT = 0.01` (was `0.05`)
- `TAKE_PROFIT_RATIO = 3.0` (was `2.0` -- already 3.0 is possible
  depending on current value from the 5%-stop test commit; verify at
  implementation time)

Added:
- `UNIVERSE_CONFIG_PATH = "config/universe.json"`

Unaffected (kept as-is): VWAP_ENTRY_ATR_MULT, VWAP_EXIT_ATR_MULT, and every
other strategy's params (mean_reversion, orb, rsi_reversion, bb_squeeze
params stay in config.py even though unused by the live bot now -- still
needed by backtest scripts that test those strategies standalone).

### Changed: `bot/strategy_registry.py`

No structural change. `get_strategies()` still resolves
`config.STRATEGY_SET`; it's simply now permanently `"vwap_reversion_only"`
in live config, so both `(ranging_strategy, trending_strategy)` slots
resolve to the same vwap_reversion module (identical pattern to the
existing `mean_reversion_only`/`orb_only`/etc. entries -- no new code
needed here at all). Registry keeps every other `_only` entry so backtest
scripts can still test them standalone.

### Removed: `bot/instrument_config.py`

No longer needed -- no per-symbol overrides once strategy+exits are
unified. `apply_instrument_overrides()` calls removed from bot/main.py.

### Changed: `bot/main.py`

1. Remove `from bot.instrument_config import apply_instrument_overrides`
   and its call inside `on_bar_update`'s handler.
2. `main()`:
   - Replace `for symbol in config.INSTRUMENTS:` startup loop with
     `universe = load_universe(config.UNIVERSE_CONFIG_PATH)`, then
     subscribe every symbol with `status == "active"`.
   - Track `universe` and a `last_universe_mtime` as module-level state
     alongside the existing `portfolio`/`cash`/`trend_maps` globals.
3. New helper `subscribe_symbol(symbol, ib, bar_lists, contracts)` --
   extracts the existing per-symbol subscribe block (contract qualify +
   `reqHistoricalData(keepUpToDate=True)` + `updateEvent +=` + optional
   daily trend-filter subscribe) out of `main()`'s startup loop into a
   standalone function, so it's callable again later when a new symbol
   goes active mid-run. New helper `unsubscribe_symbol(symbol, ...)` --
   cancels the live bar subscription(s) via `ib.cancelHistoricalData(...)`
   and drops symbol from `bar_lists`/`contracts`/`trend_maps`.
4. Inside `on_bar_update`'s handler (runs once per completed bar, already
   the natural cadence for this check per the operator's "check every
   bar" decision):
   - Check `config/universe.json`'s mtime; if changed since last check,
     reload via `load_universe`, reconcile pending_disables via
     `reconcile_pending_disables(universe, portfolio)` (this can flip
     THIS bar's own symbol to disabled if it just went flat), then
     `diff_universe(old, new)` and subscribe/unsubscribe accordingly.
   - This means a manual edit to universe.json (adding a new symbol,
     or force-setting one to "disabled") takes effect within one bar
     across ALL currently-subscribed symbols, since every symbol's
     handler does this check independently. Slight redundancy (N
     symbols all doing the same file stat/reload each bar) but
     negligible cost and simplest to reason about -- matches the
     "check every bar" decision.
   - A symbol whose status is "disabled" or "pending_disable" is
     skipped for NEW entries (no `place_entry` call) but its exit path
     (bracket fill / stop / strategy EXIT signal) still processes
     normally regardless of status -- this is what lets pending_disable
     ride out to flat naturally without special-casing the exit logic.

### Changed: `backtest/engine.py`, `backtest/data.py` (deferred)

Not required for this change to ship, since every backtest script already
takes an explicit `--symbols` list and a single `STRATEGY_SET` override --
they don't currently read `config.INSTRUMENTS`/`INSTRUMENT_CONFIG` at all
(confirmed: those are main.py-only). No backtest script changes needed.
If a future backtest wants to simulate the universe changing mid-run,
`bot/universe.py`'s functions are reusable then.

## Symbol lifecycle (state machine)

```
        request_disable() while FLAT
active ────────────────────────────────► disabled
   │                                          ▲
   │ request_disable() while POSITION OPEN    │ reconcile_pending_disables()
   ▼                                          │ (position just went flat)
pending_disable ─────────────────────────────┘
   │
   │ (keeps trading normally the whole time -- entries AND exits both
   │  process as if still "active", right up until it goes flat)
   ▼
 (flat) -> auto-flips to disabled

 disabled -> active: direct manual edit to the file, no gating needed
             (no position exists on a disabled symbol by construction --
             it can't have gone disabled while one was open)
```

## What does NOT change

- `Portfolio`/`Position` (still one position per symbol, unaffected).
- `bot/risk_manager.py` (stop/TP price math -- config values change, code
  doesn't).
- Exit execution path (`place_exit`, `_watch_bracket`, bracket order
  placement) -- unaffected, already generic across any strategy/symbol.
- Circuit breaker, exposure cap logic -- unaffected.
- Every backtest script -- unaffected (already take explicit symbol
  lists and don't read `config.INSTRUMENTS`).

## Operator decisions locked in (2026-09-24)

- Strategy: `vwap_reversion_only` unified, no merge (merge deferred to
  future backtest).
- Exit: fixed_pct stop 1.0%, take-profit ratio 3.0 (3:1).
- Universe file format: JSON, path `config/universe.json`.
- Universe reload cadence: every bar (mtime check, negligible cost).
- Disable-with-open-position: `pending_disable`, auto-flips to
  `disabled` on going flat, no forced flatten.

## Still open / to confirm at implementation time

- Exact current value of `config.TAKE_PROFIT_RATIO` before this change
  (verify against latest committed config.py, since the 5%-stop-test
  commit may have left it at a different value than the vwap_donchian-era
  default).
- Whether `request_disable()`/an enable-a-new-symbol workflow needs a
  small CLI wrapper (e.g. `python -m bot.universe_cli disable TSLA`) for
  convenience, or hand-editing the JSON file directly is fine. Leaning
  toward: ship hand-editable JSON now, add a CLI wrapper later only if
  editing the file by hand proves annoying in practice.
- `ib.cancelHistoricalData()` exact call signature / confirm it fully
  detaches the `updateEvent` handler too (need to check ib_insync docs
  at implementation time, not guess).
