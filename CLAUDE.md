# Trading Bot Project — Context & Build Plan

## Current status (2026-09-24, branch `unified-strategy-universe`) — unified vwap_reversion_only strategy + standardized bracket exit + hot-reloadable symbol universe, implemented per plan doc; not yet observed live

Implemented `research/unified_strategy_universe_plan_2026-09-24.md` in full
(now marked IMPLEMENTED, with an "Additional issues found during
implementation" addendum -- see that doc for details). Two changes, per
operator decision:

1. **One standardized entry strategy + exit for every symbol, replacing
   per-symbol tuning.** `config.STRATEGY_SET` is now permanently
   `"vwap_reversion_only"` (was per-symbol via the now-deleted
   `config.INSTRUMENT_CONFIG`/`bot/instrument_config.py`) -- chosen because
   it was the only strategy with positive breadth across 4/5 symbols
   (SPY/IWM/QQQ/TSLA) in the fixed-pct SL/TP sweep. Exit is now permanently
   `config.USE_BRACKET_EXITS = True`, `STOP_LOSS_MODE = "fixed_pct"`,
   `FIXED_STOP_LOSS_PCT = 0.01` (1.0%), `TAKE_PROFIT_RATIO = 3.0` (was 2.0)
   -- a 1.0%/3.0% (3:1) bracket, chosen over the also-viable 1.5%/3.0%(2:1)
   combo for its higher trade count (avg 25.9 vs 23.1 per cell) at a
   near-identical aggregate profit factor. No strategy MERGE was built --
   deferred to a future backtest, not guessed at here.
2. **Symbol universe moved out of static `config.py` into hot-reloadable
   `config/universe.json`** (`{"SYMBOL": {"status": "active"|"pending_disable"|
   "disabled"}}`, currently SPY/QQQ/IWM/TSLA/GOOGL all `"active"`), via new
   `bot/universe.py` (`load_universe`, `request_disable`,
   `reconcile_pending_disables`, `diff_universe` -- stdlib-only, no
   ib_insync dependency, so it's independently unit-testable). `bot/main.py`
   reads this file for its startup subscribe loop instead of
   `config.INSTRUMENTS` (now removed), and checks the file's mtime every
   completed bar (`_sync_universe()`, called from `on_bar_update()`'s
   handler) to pick up manual edits within one bar -- new symbols get
   subscribed, `"disabled"` symbols get unsubscribed, with no restart
   needed. Disabling a symbol with an open position marks it
   `"pending_disable"` (keeps trading normally, both entries and exits)
   and it auto-flips to `"disabled"` the instant it goes flat, no forced
   flatten. New `subscribe_symbol()`/`unsubscribe_symbol()` helpers in
   `bot/main.py` extract what used to be main()'s inline startup loop so
   they're callable again mid-run. A symbol with status `"pending_disable"`
   or `"disabled"` is skipped for NEW entries only -- every exit path
   (bracket fill, stop, strategy EXIT signal) is completely unaffected by
   status, so a pending-disable position rides out to flat exactly as if
   still active.

**Found and fixed three things this plan doc got wrong, beyond its own
scope**, all now documented in the plan doc's "Additional issues found
during implementation" section:
- `backtest/engine.py` was NOT already decoupled from the per-symbol
  config system as claimed -- it had a dead `use_instrument_config`
  parameter that imported `bot.instrument_config` at module level.
  Deleting that module (as planned) would have broken the import and
  crashed every backtest script transitively. Confirmed via grep that no
  real call site ever passed `use_instrument_config=True`, so removed the
  dead parameter/import with no behavioral change to any existing result.
- Six more files read `config.INSTRUMENTS` directly and would have crashed
  on import/argparse setup once it was removed (`backtest/optimize.py`,
  `backtest/run_backtest.py`, `backtest/fetch_ibkr_data.py`,
  `backtest/generate_synthetic_data.py`, `check_ibkr_connection.py`,
  `research/momentum_rotation.py`) -- none covered by the "don't touch"
  list (`backtest/engine.py`, `backtest/data.py`, `backtest/validate_*.py`
  scripts, which correctly didn't need changes). Fixed by replacing each
  with a literal `["SPY", "QQQ", "IWM"]` (the value `config.INSTRUMENTS`
  held before removal) -- no behavior change.
- **A real live-crash bug in the plan's own mid-run subscribe design**:
  calling the blocking `ib.qualifyContracts()`/`ib.reqHistoricalData()`
  (both go through `util.run()` -> `loop.run_until_complete()`) from
  inside `on_bar_update()`'s handler -- i.e. while `ib.run()`'s loop is
  already running -- would crash with `RuntimeError: This event loop is
  already running`, the exact same failure class as the 2026-09-23
  entry/exit-fill bug documented below. Fixed by having `subscribe_symbol()`
  dispatch to a non-blocking async path (`asyncio.ensure_future()` +
  `ib.qualifyContractsAsync()`/`ib.reqHistoricalDataAsync()`, the same
  event-driven pattern `_watch_trade`/`_watch_bracket` already established
  for this exact problem) whenever `util.getLoop().is_running()`, falling
  back to a plain blocking call only at startup (before `ib.run()` starts
  pumping). Also found (and worked around, not just noted) that the plan's
  literal step-4 wording would have gated `reconcile_pending_disables()`
  behind the file's mtime check, silently breaking its own "auto-flips ...
  the instant it goes flat" goal for a symbol whose position closes
  without anyone touching the file again -- `_sync_universe()` now runs
  the reconcile every bar unconditionally, independent of the mtime-gated
  file reload.

**Testing done**: this Windows dev environment cannot import `ib_insync` at
all (a pre-existing limitation -- `eventkit` calls
`asyncio.get_event_loop()` at import time, which Python 3.14 no longer
implicitly creates; see `ib_compat.py`), so `bot/main.py` itself could not
be run/imported here, live or otherwise -- same constraint noted throughout
this file's history. Per that constraint: `bot/universe.py` was written
with zero `ib_insync` dependency specifically so it's independently
testable -- new `tests/test_universe.py` (stdlib `unittest`, 15 cases:
valid/malformed/missing-file loads and fallback-to-last-known-good,
`request_disable` under both open-position and flat, `reconcile_pending_disables`
flipping and not-flipping, `diff_universe` across several transition
shapes) all pass (`python -m unittest tests.test_universe -v`). Also
re-ran `python -m backtest.validate_fixed_pct_exits --symbols SPY
--strategy vwap_reversion_only` and `python -m backtest.run_backtest
--symbols SPY QQQ IWM` end-to-end against real cached historical data to
confirm `config.py`'s changes (removed `INSTRUMENTS`/`INSTRUMENT_CONFIG`,
new `STRATEGY_SET`/bracket-exit defaults) didn't break the backtest
pipeline -- both completed cleanly. **Not yet exercised**: `bot/main.py`'s
own live subscribe/unsubscribe/reconcile wiring against a real IBKR
connection -- treat as unverified-live, same as every other live-only code
path in this project's history, until actually observed running.

## Current status (2026-09-24, branch `bracket-tp-sl`) — bracket-order exits (ATR-based and fixed-%) tested; no validated edge yet, but a real quality signal (win rate) identified

Per operator request, redesigned exit handling from "strategy's own signal
reversal + single ATR stop" to a proper **bracket order**: stop-loss AND
take-profit placed together at entry (one-cancels-other), replacing each
strategy's own EXIT signal entirely for this test — a position holds until
either level is hit, full stop. Entry signal logic is unchanged.

**Live bot** (`bot/main.py`): now places a real IBKR OCO bracket (StopOrder
+ LimitOrder) instead of just a stop. **Backtest engine**
(`backtest/engine.py`, `use_bracket_exits=True`, opt-in): checks each bar's
HIGH/LOW (not just close) to correctly simulate intrabar stop/TP hits —
if both levels fall within the same bar's range, the stop-loss is assumed
to trigger first (conservative tie-break, documented in code). Both are
strictly opt-in; every existing non-bracket backtest path/result is
unaffected.

**Two stop-sizing modes added** (`config.STOP_LOSS_MODE`):
- `"atr"` (default, unchanged): stop = `STOP_LOSS_ATR_MULT * ATR`
- `"fixed_pct"` (new): stop = `FIXED_STOP_LOSS_PCT * entry_price` (flat %,
  symbol/volatility-agnostic). Take-profit = stop distance * `TAKE_PROFIT_RATIO`
  in both modes, so R:R semantics are identical — only how the base "1R"
  distance is computed differs.

### ATR-based bracket results (`backtest/validate_bracket_exits.py`)
Grid search (entry params x `STOP_LOSS_ATR_MULT` [2/3/4] x `TAKE_PROFIT_RATIO`
[2:1/3:1]) on SPY, QQQ, IWM, TSLA (GOOGL run was stopped by operator request
before completing — see `backtest_results/bracket_validation_log.txt` for
partial data through TSLA). Per operator preference, read raw OOS
return/PF/trades, not the buy-and-hold comparison the script also prints:

- **VWAP-reversion is the standout across SPY, QQQ, and IWM** — consistently
  positive OOS returns with real profit factors (up to ~3.0), best result
  IWM +2.85% PF 2.96 (19 trades).
- **ORB and BB-squeeze lose money consistently on SPY/QQQ/IWM**, regardless
  of stop/TP tuning.
- **TSLA is much noisier** — no strategy held up consistently OOS; several
  combos with strong in-sample returns (7-8%) fell apart out-of-sample
  (-3% to -7%), a clear overfitting signature. One ORB combo hit +5.16% OOS
  but neighboring combos in the same top-3 lost 5-9%, i.e. not robust to
  parameter choice.

**Root-cause analysis** (`backtest/analyze_stop_distances.py`, ad-hoc,
SPY-specific): compared a losing combo (ORB, 2x ATR stop, 3:1 TP) against a
winning one (VWAP-reversion, 3x ATR stop, 2:1 TP). Stop/TP distances landed
close to their configured ATR multiples in both cases (~0.5% stop / ~1.3%
TP for ORB; ~0.6% stop / ~1.2% TP for VWAP-reversion) — the bracket
mechanics work as designed. **The actual differentiator is win rate, not
R:R sizing**: ORB won only ~23% of trades (needs >25% to clear its 3:1
payoff breakeven) vs. VWAP-reversion's ~37% (clears its 2:1 breakeven
comfortably). Entry signal quality, not stop/TP distance, is the lever
that matters here.

### Fixed 5% stop / 15% TP (3:1) results (`backtest/validate_fixed_pct_exits.py`)
Full write-up: `research/fixed_pct_validation_2026-09-24.md`, raw log:
`backtest_results/fixed_pct_validation_log.txt`. Same 5 strategies x 5
symbols, no buy-and-hold comparison (raw numbers only, per operator
request).

**Worse than the ATR-based version, not better.** A flat 5% stop is too
wide for 15-min bars: SPY only produced **1 trade in the entire 6-month
OOS window across all 5 strategies**, since price rarely moves 5%
intraday before the underlying signal would exit anyway — sample sizes
(1-11 trades per combo) are too thin to draw conclusions. Only IWM
VWAP-reversion (+2.81%, PF 2.84) and ORB (+1.22%, PF 1.40) were positive,
each on just 2-3 trades. TSLA and GOOGL were clearly negative across the
board (down to -10.6%). **Conclusion: fixed-% stops don't fit this
timeframe — ATR-based sizing (which naturally scales to each instrument's
actual intraday volatility) remains the more sensible approach for a
15-min bot.**

### Open next step
VWAP-reversion's win-rate edge (SPY/QQQ/IWM) under ATR-based brackets is
the most promising thread from today's work — worth tuning further (entry
threshold, stop/TP ratio) rather than pursuing fixed-% stops or ORB/
BB-squeeze further on these instruments.

## Current status (2026-09-24) — TSLA/GOOGL/MSFT/AAPL/NVDA explored: no edge with existing mean-reversion/VWAP strategies; momentum testing planned next
**Operator asked to add TSLA, GOOGL, MSFT, AAPL, NVDA to the bot's universe.**
Before any live/paper trading, ran the same out-of-sample discipline used
for SPY/QQQ/IWM: pulled 1yr real 15-min + daily bars for all 5 via
`backtest.fetch_ibkr_data` (saved to `data/historical/`), then wrote
`backtest/validate_new_symbols.py` — per-symbol grid search on the first
half of the year (in-sample), re-tested top-3 combos per strategy set on
the second half (out-of-sample, never searched over) — same split
methodology as the SPY/QQQ/IWM validation.

**TSLA and GOOGL both completed** (full grid search on `sma_zscore` and
`vwap_donchian`, both strategy sets, out-of-sample re-tested):
- **`sma_zscore` (mean-reversion + trend-following mix): failed out-of-sample
  on both, badly.** GOOGL's in-sample profit factor reached as high as 2.93,
  collapsing to 0.42-0.47 out-of-sample (clear losses) — a textbook
  overfitting signature, same shape as the SPY/QQQ failures already
  documented below. TSLA similarly went from PF ~1.1-1.2 in-sample to
  0.19-0.62 out-of-sample.
- **`vwap_donchian` (VWAP-reversion + Donchian breakout): technically
  cleared the out-of-sample bar (return > 0%) on both, but the margin is
  negligible** — returns of 0.00% to 0.02%, profit factors barely above 1.0
  (1.01-1.18). Compare to IWM's real out-of-sample result (+1.42% return,
  PF 3.10) — this is noise-level performance, not a validated edge.
  **Verdict: neither TSLA nor GOOGL has a real edge with the bot's current
  mean-reversion/VWAP-reversion strategies.**

**MSFT/AAPL/NVDA validation was started (historical data pulled, daily bars
pulled) but killed partway through MSFT's grid search** at the operator's
call — TSLA/GOOGL's clean, consistent "no edge" result made it a reasonable
bet that MSFT/AAPL/NVDA (all similarly large, liquid, heavily-arbitraged
mega-cap names) would show the same pattern, and continuing would have cost
several more hours of grid search for low expected new information. Their
1yr 15-min + daily historical CSVs are already saved in `data/historical/`
if this needs revisiting — no need to re-fetch.

**Why this result makes sense**: this matches the project's own established
pattern — SPY/QQQ (also large, efficiently-arbitraged, heavily-traded)
showed no edge either, while IWM (small-cap, less efficiently arbitraged)
is the one validated success. TSLA/GOOGL/MSFT/AAPL/NVDA are all mega-cap,
extremely liquid, heavily-traded names — the same market-efficiency
argument that explains SPY/QQQ's failure plausibly extends to them too.

**Next: momentum strategy testing on TSLA and GOOGL first.** Operator's
reasoning: single-stock names are more news/catalyst-driven (earnings,
product announcements, etc.) than SPY/QQQ/IWM, so they may show real
momentum/trend behavior even though mean-reversion and VWAP-reversion don't
work on them. Plan:
1. Isolate `bot/strategies/trend_following.py` (SMA fast/slow crossover) —
   already exists in the codebase, only ever tested mixed with
   `mean_reversion` inside `sma_zscore` (which failed on TSLA/GOOGL above)
   — never tested alone. Add a `trend_following_only` entry to
   `bot/strategy_registry.py` (same pattern as the existing
   `mean_reversion_only`/`vwap_reversion_only` entries), out-of-sample
   validate on TSLA and GOOGL first.
2. **Must benchmark against simple buy-and-hold on the same out-of-sample
   window** — the project already has one false-positive lesson on exactly
   this mistake: the 2026-09-18 cross-sectional momentum rotation test on
   SPY/QQQ/IWM looked like a huge out-of-sample win (+9% to +14.5%) until
   checked against buy-and-hold (13.6%-17.9% on the same window), which
   revealed the "edge" was pure market beta from a rally, not real signal.
   Any momentum result on TSLA/GOOGL must clear this same bar before being
   trusted.
3. **If TSLA/GOOGL results are promising or neutral (not a clear failure),
   proceed to test the same momentum approach on MSFT, AAPL, NVDA.** If
   TSLA/GOOGL both fail outright, likely not worth continuing to the other
   three on this same strategy type — matches the same "consistent failure
   across similarly-structured instruments" reasoning used to stop the
   mean-reversion/VWAP validation above.
4. The existing `trend_following` is intraday (15-min bar SMA crossover) —
   if this also fails, a genuinely different, longer-timeframe momentum
   approach (e.g. daily-bar, weeks-long holding, academic 12-1 month
   momentum factor style) would be a bigger, separate build, not a quick
   backtest tweak — not yet started, only noted as a fallback option.

**Status: paused for a machine restart (RDP setup work), to resume after.**
No trend_following_only work has been committed yet — reverted an
in-progress `bot/strategy_registry.py` edit to keep the working tree clean
before the restart; redo this step when resuming.

## Current status (2026-09-23, night) — two live bugs fixed: event-loop crash on entry fill, and IBKR rejecting fractional-share orders
**Found from the live log** (`logs/bot_20260923_210445.log`, ~22:15:05) on a
QQQ entry attempt, running under the Hermes market-hours supervisor from
the entry below. Both bugs are fixed; not yet re-observed live (the next
QQQ entry attempt during market hours will be the real test).

**BUG 1 (crash): `RuntimeError: This event loop is already running` on
every entry/exit fill wait.** `bot/main.py`'s old `_wait_for_fill()` polled
`trade.isDone()` in a loop calling `ib.sleep(0.2)` -- but `place_entry()`/
`place_exit()` are called synchronously from inside `on_bar_update()`'s
`handler()`, which is itself an `ib_insync` event callback already running
on the asyncio event loop. `ib.sleep()` goes through `ib_insync.util.run()`,
which calls `loop.run_until_complete()` -- illegal from inside a callback
the loop is already inside, so it crashed immediately on the QQQ entry
attempt. **Fixed** by replacing the blocking poll with a non-blocking
`_watch_trade()` helper: it listens on `trade.statusEvent` (fires on every
status change, including fills and cancels) and races it against a
`loop.call_later()` timeout, invoking a callback exactly once with
`(avg_fill_price, commission)` whichever happens first -- same 15s timeout
and same "did not report a fill" error log as before, just event-driven
instead of blocking. `place_entry()`/`place_exit()` were restructured
accordingly: the post-fill logic (attach stop order, update cash/portfolio,
log trade) now lives in an `on_fill` closure passed to `_watch_trade()`
rather than running inline after a blocking wait.

**BUG 2 (order rejected): `Error 10243: Fractional-sized order cannot be
placed via API`.** IBKR's API flatly rejects fractional-quantity orders --
only the desktop TWS GUI can place them -- which `bot/risk_manager.py`'s
`position_size()` never accounted for: with `config.USE_FRACTIONAL_SHARES
= True` it always returned `round(raw_qty, 4)`, a fractional quantity, for
every live order. **Fixed per the operator's explicit instruction**: added
a `force_whole_shares: bool = False` parameter to `position_size()`. When
`True`, it always rounds down to a whole share, minimum 1 whenever the
risk/capital-based sizing calc is positive, regardless of
`config.USE_FRACTIONAL_SHARES`. `bot/main.py`'s live call site now passes
`force_whole_shares=True`. **`backtest/engine.py`'s call site was
deliberately left unchanged** (no new argument, defaults to `False`) --
per this file's own "backtest reuses live `bot/` modules directly so
backtest and live logic can't diverge" design, silently forcing whole
shares into the backtest as well would have changed every historical
result and broken comparability with all the grid-search/Monte Carlo
findings already recorded in this file. Confirmed `python -m
backtest.run_backtest` still runs against the same call path/defaults as
before (198 round trips, -6.72% return on the current unvalidated
defaults -- consistent with this being an unrelated sizing-path change,
not a strategy change). `config.USE_FRACTIONAL_SHARES` itself is left in
place for backtest-only fractional simulation, per the risk_manager.py
docstring now explaining why it's no longer achievable live.

## Current status (2026-09-22, midday) — market-hours supervisor added; bot now only runs around the US session, not 24/7
**New cron job: `trading-bot-market-hours-supervisor`** (Hermes cron, job ID
`3b7482a48215`, script `bot_monitor_state/market_hours_supervisor.py`, runs
every 5 minutes, `no_agent` mode -- pure script, no LLM call, silent unless
it errors). Added at the operator's request to stop the bot running 24/7
and instead only run it around the actual US market session.

**What it does, each tick:** computes whether "now" falls inside NYSE
regular session hours (9:30am-4:00pm America/New_York) +/- a 30-minute
buffer on each side, using `zoneinfo` (so DST transitions in Mar/Nov are
handled automatically, no manual SGT-offset math) plus a hardcoded
`NYSE_HOLIDAYS` set in the script (full-day closures only -- half-days/
early closes are NOT modeled, see script docstring). Then:
- **In window + bot not running** -> starts it (`python -m bot.main`, same
  command/interpreter/cwd as always: `C:\Users\Edwin\AppData\Local\Python\
  pythoncore-3.14-64\python.exe`, cwd = this folder), writes a fresh
  `logs/bot_<timestamp>.log` and updates `logs/bot_pid.txt` /
  `logs/current_log_path.txt` the same way the existing handoff setup did.
- **Out of window + bot running** -> stops it cleanly via `taskkill /F`.
- **Otherwise** -> no-op, prints `no_change` (empty/no-op output on
  `no_agent` jobs sends nothing, so this job stays silent in normal
  operation).

**Deliberately stdlib-only** (`zoneinfo` + hardcoded holiday list), NOT
`pandas_market_calendars` -- first version used that library and worked
fine when tested manually, but failed every real cron tick with
`ModuleNotFoundError` because Hermes's cron scheduler runs scripts under
Hermes's own venv (Python 3.11), not the bot's Python 3.14 interpreter the
package had been installed into. Lesson: a script handed to Hermes cron
must not assume it runs under the same interpreter as manual testing --
verify by actually firing the job (`cronjob run`), not just running the
script by hand.

**Verified working**: manually fired the job after the interpreter fix;
it correctly identified the bot's existing 24/7 process (PID 38412, been
running since the pre-supervisor setup) as **outside** the trading window
at the time (11:2x SGT, well after the prior night's session end +30min
buffer) and stopped it. A second manual fire afterward correctly reported
`no_change (outside window, bot not running)`. Coexists with the existing
`trading-bot-log-monitor` job (still tails the log and alerts via
Telegram) without conflict -- that job continues to watch whatever log
file `logs/current_log_path.txt` currently points to, including one this
supervisor creates.

**Not yet exercised**: an actual automatic start at the next session's
open-minus-30min, or an automatic stop at close-plus-30min -- both were
inferred correct from the window-boundary logic and a manual stop, not yet
observed live at a real boundary. Worth a spot-check the first time either
boundary passes.

## Current status (2026-09-22, late morning) — execution + monitoring handed off to Hermes Agent, decoupled from Claude Code
**The bot is no longer run/watched from inside a Claude Code session.** Up
through the second live night, `python -m bot.main` ran as a Claude Code
background task, watched by a Claude Code `Monitor` log-tail with desktop +
attempted mobile push notifications -- mobile push to the operator's phone
never worked (config confirmed correct, notifications never arrived; root
cause never found). The operator separately has **Hermes Agent** (Nous
Research's agent runtime, `hermes` CLI, already running as a persistent
gateway daemon on this machine with a working Telegram pairing) set up
independently of this project.

**Moved ownership of the execution + reporting layers to Hermes** (see
"Architecture" below -- this is that layer split, just Hermes instead of
Cowork/Slack): Claude Code stopped its own background bot process and
instructed Hermes (one `hermes chat -q ... --oneshot` call) to (1) start
`python -m bot.main` as its own detached OS process, independent of any
chat/session lifetime, (2) verify clean startup, (3) create a Hermes cron
job (`trading-bot-log-monitor`, 1-minute interval) running a small
change-detector script that tails the bot's log by byte offset and alerts
via Telegram only when something actually matches -- trade opens/closes,
circuit breaker, ERROR/Traceback/Exception, process death (PID liveness
check), or an ERROR 1100 (IBKR connection lost) with no 1102 (restored)
within 2 minutes (explicitly tells the operator to manually relogin to TWS
in that case, matching the lesson from the 2026-09-18/2026-09-22 outages
above). Independently verified after Hermes reported completion: process
is the real bot (correct interpreter -- Hermes's own default `python`
resolves to its own venv without `ib_insync`, had to point at
`C:\Users\Edwin\AppData\Local\Python\pythoncore-3.14-64\python.exe`
instead), log shows clean IBKR connect + all 3 instrument subscriptions,
cron job active and already fired once successfully.

**Why this is better for the unsupervised-overnight goal**: Hermes's
process is a genuine standalone OS process and its gateway is already a
persistent daemon independent of any interactive coding session -- closer
to the project's original "execution layer runs 24/7, decoupled from the
build/maintenance layer" design intent than a Claude Code background task
ever was (a Claude Code session's background tasks are not guaranteed to
survive the session ending). Telegram delivery is also a working, already-
verified notification channel, unlike Claude Code's mobile push.

**Still true / unaffected by this handoff**: the reconnect-crash fix
earlier today, the trend-filter/vwap_reversion live-data-shape fixes from
2026-09-18, and the no-reconnect-logic gap in `bot/main.py` itself (Hermes
restarting the process from the outside is a workaround for that gap, not
a fix to it -- still worth the reconnect-with-backoff or IBC work described
below before any non-Windows/Lightsail unattended deployment). If resuming
work on the bot's own code, check `logs/current_log_path.txt` and
`logs/bot_pid.txt` (maintained by Hermes, not by `bot/main.py` itself) to
find the live process/log rather than assuming a Claude Code background
task owns it.

## Status history (2026-09-22, early morning) — second night live; brief TWS blip this time self-healed, but exposed a real reconnect-resync crash
**Restarted the bot after the 2026-09-18 TWS outage** (operator relogged into
TWS, confirmed via `check_ibkr_connection.py`) and let it run through the
full second live session, supervised via a `Monitor` log watch + push
notifications. Result: SPY/QQQ repeatedly signaled short entries (VWAP
deviation crossed threshold) that the long-term trend filter correctly
blocked all session (`trend=bullish`) -- exactly the intended behavior, not
a bug. IWM stayed quiet all night. No trades filled. A few data-farm
warnings (`hfarm`, `apachmds`, `secdefhk`) auto-recovered within seconds
each time, as expected.

**At 05:10 (near/after US market close), `ERROR 1100: Connectivity between
IBKR and Trader Workstation has been lost` fired** -- initially assumed to
be a repeat of the 2026-09-18 full nightly-restart outage and the operator
was paged. **This time it was NOT a full outage**: ~45 seconds later,
`ERROR 1102: Connectivity...has been restored - data maintained` came
through on its own, no manual TWS relogin needed. So IBKR/TWS connectivity
blips can apparently be brief and self-healing, not always the full
"TWS forced a restart" scenario from 2026-09-18 -- don't assume every 1100
needs operator intervention; wait to see if 1101/1102 follows before
paging, though the existing page-then-correct approach (page immediately,
follow up if it self-resolves) is an acceptable tradeoff given the
alternative is silently missing a real outage.

**But the reconnect resync itself crashed both bar-update handlers on every
symbol**, newly discovered via this real blip (never seen before because
the first outage never recovered on its own to test this path): on
reconnect, `ib_insync` re-fires each `BarDataList.updateEvent` with only
one positional argument (`bars`, an empty list) while resubscribing --
`bot/main.py`'s `on_bar_update`/`on_daily_bar_update` handlers required
`has_new_bar` as a second positional argument with no default, so every
resync emit crashed with `TypeError: handler() missing 1 required
positional argument: 'has_new_bar'`. Caught per-callback by `eventkit`
(logged as ERROR, process stayed alive) -- same silent-failure shape as
the 2026-09-18 live-only bugs, just triggered by a different live-only
code path (reconnect resync, not routine bar updates) that only a real
disconnect/reconnect cycle exercises. **Fixed** by defaulting
`has_new_bar: bool = False` in both handlers (`bot/main.py`), so a
resync-triggered single-arg emit is treated like any other ignored
intrabar tick instead of crashing. Restarted the bot with the fix live;
clean startup, all three instruments resubscribed. This specific fix was
not re-exercised by a matching 1100->1102 resync blip afterward (see next
paragraph for what happened instead) -- still worth treating as
unconfirmed-live until a real resubscribe-while-connected event is
observed again.

**Lesson reinforced**: this is the *third* live-only bug found purely by
running the bot and watching real IBKR event traffic (after the two
2026-09-18 `df.index`-shape bugs) -- specifically the reconnect/resync path
is its own untested code path, distinct from routine live bar updates,
and apparently also undertested by anything short of a real disconnect.
Worth treating "connection recovery" as its own thing to watch for during
supervised runs, not just "did it crash on startup."

**Second, different disconnect at 11:00 (still 2026-09-22, late morning,
after market close)**: `ERROR Peer closed connection.` fired again -- same
message as the 2026-09-18 full outage, but this time `check_ibkr_connection.py`
(a separate diagnostic connection, same clientId) connected successfully
immediately afterward with live quotes for all three symbols, proving TWS
itself was healthy and reachable -- only the bot's own socket had dropped,
not a TWS restart. **No manual relogin was needed.** Stopped and restarted
the bot process (same command, same clientId); clean startup, no changes
needed to the code. Take-away for future incidents: `ERROR Peer closed
connection.` is NOT on its own proof of a full TWS outage the way the
2026-09-18 incident assumed -- always try a plain reconnect/restart first
and only escalate to "operator must relogin to TWS" if that reconnect
itself fails (e.g. `ConnectionRefusedError`, as it did on 2026-09-18).
This second restart is also the last thing Claude Code did before handing
bot execution and monitoring off to Hermes Agent entirely -- see the
"Current status" section at the top of this file for that handoff, which
supersedes Claude Code directly running/restarting the bot going forward.

## Status history (2026-09-18, late night) — TWS's nightly restart disconnected the bot; no auto-reconnect exists yet
**~28 minutes into the first live run** (after both bugs below were fixed),
the bot's log showed `ERROR Peer closed connection.` and went silent --
TWS itself had closed the socket, not just the API. A reconnect attempt
got `ConnectionRefusedError: [WinError 1225]` (connection actively
refused, not just an API-side rejection), confirming TWS itself had gone
down, not just the API layer -- consistent with IBKR TWS's well-known
behavior of forcing a full restart roughly once every 24 hours (commonly
around this time of night) that requires a manual relogin; it does not
come back on its own. `bot/main.py` has no reconnect/retry logic at all --
`ib.connect()` is called once in `main()`, and a lost connection just
leaves `ib.run()` idling forever with a dead socket, no new bars, no
ability to trade, and (as of this incident) no alert distinct from any
other ERROR-level log line.

**This directly threatens the project's core design constraint** ("the bot
runs fully unsupervised overnight while the operator sleeps," see
"Operator context" below) -- as built, one nightly TWS restart silently
ends the trading session for the rest of the night with nobody watching.
**Not yet fixed, next step when resuming**: before any unattended/Lightsail
deployment, `bot/main.py` needs either (a) reconnect-with-backoff logic
around `ib.connect()`/`ib.run()`, and/or (b) IBC ("IB Controller" -- the
standard community tool for automating TWS's login and restart handling,
widely used for exactly this problem), and either way a Slack alert
specifically for "lost connection to TWS" distinct from routine ERROR
logs, since this failure mode is silent otherwise. Until this is solved,
this bot is not safe to leave running unattended overnight -- tonight's
run was manually restarted by the operator after being paged.

## Status history (2026-09-18, late night) — live paper trading started; two live-only bugs found and fixed
**First live run of `bot/main.py` against the paper account (DUT119165), supervised.**
Both bugs below share the same root cause: `backtest/data.py` returns bars
indexed by a `DatetimeIndex` (no separate `date` column), but live bars from
`ib_insync`'s `util.df(bars)` come back with a plain `RangeIndex` and the
timestamp in a `'date'` column instead. Code written and tested only against
backtest-shaped DataFrames silently assumed the former. Neither bug was
caught by backtesting (which never exercises this shape) or by static review
-- both only surfaced once real live bars started flowing.

1. **`bot/trend_filter.py` `build_trend_map()`** -- crashed on startup with
   `AttributeError: 'datetime.date' object has no attribute 'date'` (live
   daily bars from `on_daily_bar_update` are plain `datetime.date`, not
   pandas `Timestamp`). Fixed, restarted, ran cleanly.
2. **`bot/strategies/vwap_reversion.py` `_session_vwap()`** -- `day =
   df.index.date` raised `AttributeError: 'RangeIndex' object has no
   attribute 'date'` on every single 15-min bar update, for all three
   symbols, from the moment bug #1's fix let the bot run. Caught internally
   by `eventkit` per-callback (logged as ERROR, process stayed alive), which
   made this a *silent* failure, not a crash -- the bot looked "up" in the
   logs but zero VWAP signal checks succeeded for ~10 minutes, meaning no
   trade could possibly have fired the entire time. Fixed by reading the
   `'date'` column when present, falling back to the index otherwise (same
   pattern as bug #1's fix); verified against real backtest data
   (`SPY` produced a normal signal, backtest path's `DatetimeIndex`/no-`date`-
   column shape untouched). Restarted; ran cleanly with no errors afterward.

**Lesson for anything still live-only-untested**: any strategy/filter code
that touches `df.index` or assumes a `'date'` column should be treated as
unverified against live data shape until actually observed running live --
backtest passing is not sufficient evidence. Worth a quick audit of
`mean_reversion.py`, `trend_following.py`, and `donchian_breakout.py` for
the same assumption before ever switching an instrument's `STRATEGY_SET`
to one of them live, even though they're inactive under the current
all-`vwap_reversion_only` `INSTRUMENT_CONFIG`.

**Monitoring**: a live log watch (grepping for `Opened`/`Closed`/errors/
circuit-breaker in the bot's stdout) is running in the operator's Claude
Code session and pushes a notification the moment a trade fills or
anything breaks -- not a substitute for periodically checking TWS directly
during this first supervised run.

## Status history (2026-09-18, earlier) — paused before first live paper trade
**Decision: pause today's research, move toward actually paper trading
the validated findings.** Also verify QQQ live, specifically to confirm
(not to fix) that it doesn't work, per the operator's explicit request.

**Built: per-instrument strategy configuration** (`config.INSTRUMENT_CONFIG`,
`bot/instrument_config.py`) -- `bot/main.py` previously applied one
`STRATEGY_SET` globally to every instrument; today's findings need
different strategies per symbol. Configured:
- **SPY**: `vwap_reversion_only`, entry=2.5, exit=0.2, stop=4.0x ATR --
  validated out-of-sample.
- **IWM**: `vwap_reversion_only`, entry=2.5, exit=0.35, stop=4.0x ATR --
  validated out-of-sample two independent ways.
- **QQQ**: `vwap_reversion_only` with its OWN best-fit in-sample
  parameters (entry=2.5, exit=0.5, stop=2.0x ATR), already known to fail
  out-of-sample in backtest. Kept active on purpose, to watch it fail live
  as a real-time confirmation, not to try to fix it.

Applied via the same config-monkeypatching pattern `backtest/optimize.py`
already used for grid search, wired into both `bot/main.py` (live) and
`backtest/engine.py` (new `use_instrument_config=False`-by-default param
so existing grid-search/manual-backtest behavior is untouched). Verified:
default backtest path reproduces the prior 1yr baseline bit-for-bit (no
regression), and a combined 3-instrument backtest with per-instrument
config correctly applied `vwap_reversion` to all three, producing results
directionally consistent with each instrument's isolated test -- and the
COMBINED portfolio outperformed any single instrument alone (+1.56%
return, 0.71% max drawdown, profit factor 1.70) via diversification.

**Not yet done**: actually running `bot/main.py` live against the paper
account. This is a genuinely different category of action than anything
done today (real order placement, even if paper) -- first run should be
supervised (operator watching TWS/logs), not started and left unattended,
since this exact code has never placed a live order before. Also currently
would run on the operator's own machine, not the Lightsail box (not set up
yet) -- fine for an initial pipeline test, not yet the final production
setup. This is the next step when resuming.

## Status history (2026-09-18, earlier) — pairs trading and momentum rotation both ruled out for QQQ
**Follow-up: tested two genuinely different strategy types for QQQ**
specifically, since two reversion mechanisms had already failed on it.
Both built as standalone research scripts (not wired into the
single-instrument bot architecture -- pairs/rotation need cross-instrument
logic the rest of the project doesn't have), same out-of-sample discipline.

- **QQQ/SPY pairs trading** (log-price-ratio spread, z-scored, dollar-
  neutral long/short legs): every one of the top-5 in-sample combos was
  ALREADY negative before out-of-sample testing (best in-sample: -0.44%,
  degrading to -2.04% to -2.93% out-of-sample). All top combos converged
  on the longest lookback tested (400 bars) with very few trades (3-13
  over 6 months) -- the spread doesn't mean-revert cleanly. Plausible
  reason: QQQ (tech-heavy) vs. SPY (broad market) reflects real, persistent
  sector rotation (rates, growth-vs-value cycles), not noise around a
  stable equilibrium -- correlation between two instruments does not imply
  their ratio is mean-reverting (cointegration is a stronger, different
  property). Ruled out.
- **Cross-sectional momentum rotation** (rank SPY/QQQ/IWM by trailing
  return, hold the top-ranked, rebalance periodically): ALL 15 in-sample
  combos were negative (-2% to -4%), but the same top-5 combos showed
  startling out-of-sample returns of +9% to +14.5% -- initially looked like
  a huge out-of-sample-positive discovery. **Checked against simple
  buy-and-hold on the same out-of-sample window first, which returned
  13.6% (SPY), 17.9% (QQQ), 15.4% (IWM) -- the rotation strategy
  underperformed passive buy-and-hold in every case.** The apparent gain
  was pure market beta (the second half was a strong sustained rally) --
  an always ~90%-long, unhedged rotation strategy captures that rally by
  construction, regardless of whether the ranking signal itself has any
  value. Not a validated edge; ruled out. Important general lesson: any
  always-invested, long-only strategy MUST be checked against buy-and-hold
  before treating its returns as evidence of anything, not just judged on
  absolute return.

**Where this leaves QQQ**: four different approaches now ruled out
(SMA-zscore mean-reversion, VWAP-reversion, QQQ/SPY pairs trading,
momentum rotation). Remaining untried, lower-priority ideas: a
regression/cointegration-tested hedge ratio for pairs (rather than
dollar-neutral 1:1), a market-neutral long-top/short-bottom rotation
variant (removes the beta-capture problem the long-only version had), or
accepting QQQ may need Phase 2's options/volatility-premium approach
instead of any directional strategy.

## Status history (2026-09-18, earlier) — VWAP-reversion rescues SPY, confirms IWM independently
**Follow-up to the "IWM-specific" finding below: tested VWAP-reversion in
isolation** (`config.STRATEGY_SET = "vwap_reversion_only"`, added to
`bot/strategy_registry.py` — both regime branches map to `vwap_reversion`,
same pattern as `mean_reversion_only`) — never tested standalone before,
only inside the discredited ADX-gated `vwap_donchian` hybrid. Same
instrument-specific grid search + train/test split methodology (48 combos:
`VWAP_ENTRY_ATR_MULT`, `VWAP_EXIT_ATR_MULT`, `STOP_LOSS_ATR_MULT`).

- **SPY — previously zero edge with SMA-zscore mean-reversion, now shows a
  real signal with VWAP-reversion.** All 3 of SPY's own top in-sample
  combos stayed non-negative out-of-sample (best:
  `VWAP_ENTRY_ATR_MULT=2.5, VWAP_EXIT_ATR_MULT=0.2, STOP_LOSS_ATR_MULT=4.0`
  → in-sample +0.26%/PF 1.32, out-of-sample **+0.35%/PF 1.50**, actually
  IMPROVED out-of-sample). Monte Carlo (5000 resamples of the 16 actual
  out-of-sample trades): median +0.4%, **P(loss) 25.1%** (~3-in-4 odds of
  profit), worst drawdown 1.7%. Confirms SPY's earlier "no edge" finding
  was specific to the SMA-zscore mechanism, not SPY itself — it needed a
  different reversion type (volume-weighted, session-anchored vs.
  fixed-period SMA/z-score).
- **IWM — now the strongest result in the entire project, confirmed via a
  SECOND, structurally different reversion mechanism.** Best combo
  (`VWAP_ENTRY_ATR_MULT=2.5, VWAP_EXIT_ATR_MULT=0.35, STOP_LOSS_ATR_MULT=4.0`)
  → in-sample +0.84%/PF 1.55, out-of-sample **+1.42%/PF 3.10** (also
  IMPROVED out-of-sample). All 3 of IWM's top combos improved
  out-of-sample rather than degrading. Monte Carlo (5000 resamples of the
  18 actual out-of-sample trades): median +1.4%, **P(loss) just 2.2%**
  (97.8% of resampled simulations profitable), worst drawdown across all
  5000 sims only 1.7%. Two independent, mechanistically different
  strategies (SMA-zscore mean-reversion AND VWAP deviation) both find real,
  out-of-sample-validated edge in IWM specifically — strong convergent
  evidence this is real, not a fluke of one particular technique.
- **QQQ — still nothing.** Both reversion mechanisms tested (SMA-zscore,
  VWAP) failed out-of-sample on QQQ with its own best-fit parameters.
  QQQ looks like the genuinely hardest of the three — consistent with
  being an extremely liquid, heavily-arbitraged large-cap tech index.

**Updated recommendation**: IWM is validated two independent ways and is
the strongest candidate by far. SPY now also has a real (more modest)
signal, but specifically via VWAP-reversion, NOT SMA-zscore — don't
conflate the two mechanisms when deciding what to trade on SPY. QQQ has
no validated edge from mean-reversion approaches; if pursued further it
needs a genuinely different strategy type (momentum ranking, pairs/spread
vs. another instrument, or move to Phase 2's volatility-premium concept
for QQQ specifically) rather than more reversion-parameter tuning.
Sample sizes remain modest (SPY: 16 out-of-sample trades, IWM: 18) —
real and consistent findings, not yet "large-sample proven."
**Follow-up to the mean-reversion-only finding below: investigated why the
aggregate out-of-sample profit was concentrated in IWM.** Ran the SAME
combo per-instrument alone, then ran a full instrument-specific parameter
search (same 144-combo MR grid, same train/test split) separately for
each of SPY, QQQ, IWM rather than forcing them to share one parameter set.

- **SPY, own best-fit params** (`MR_MA_PERIOD=10, MR_ENTRY_STD_DEV=2.5,
  MR_EXIT_STD_DEV=0.75, STOP_LOSS_ATR_MULT=2.0`): in-sample profit factor
  as high as 2.51 -- but ALL 3 of SPY's own top candidates collapsed
  out-of-sample (PF 0.62-0.87, every one negative). Instrument-specific
  tuning did not rescue SPY. No validated edge.
- **QQQ, own best-fit params** (`MR_MA_PERIOD=30, MR_ENTRY_STD_DEV=2.5,
  MR_EXIT_STD_DEV=0.2, STOP_LOSS_ATR_MULT=4.0`): the top-ranked in-sample
  combo was actually slightly NEGATIVE in-sample (-0.13%) and only ranked
  #1 because everything else in QQQ's grid was worse. Its positive
  out-of-sample flip (+1.32%) is far more likely noise than signal, since
  it was never good to begin with. No validated edge.
- **IWM, own best-fit params**: all 3 of IWM's own top candidates
  independently converged on essentially the SAME recipe the shared-
  universe search already found (`MR_MA_PERIOD=50, MR_ENTRY_STD_DEV=2.5,
  STOP_LOSS_ATR_MULT=4.0`, varying only the exit threshold) -- and all 3
  held up strongly out-of-sample: **profit factor 2.22-3.24, returns
  +1.12% to +1.61%, win rate ~71% in every case.** Two independent search
  paths (shared-universe grid, and IWM-only grid) arrived at the same
  answer -- this isn't one lucky combo.

**Conclusion: the edge is real but IWM-specific, not a general SPY/QQQ/IWM
phenomenon.** Economically plausible: IWM (Russell 2000 small-caps) is
meaningfully less efficiently arbitraged than SPY (S&P 500) and QQQ
(Nasdaq-100), which are among the most heavily-traded, most efficiently
priced instruments in the world -- short-term mean-reversion surviving
specifically in the least-efficient of the three is a sensible pattern,
not a coincidence.

**Recommendation, not yet acted on:** narrow Phase 1's mean-reversion
strategy to IWM specifically rather than continuing to force SPY/QQQ into
an approach that isn't working for them. This changes the "fixed watchlist"
question in "Decisions still open" from deferred/theoretical to something
with an actual answer: IWM looks tradeable with this approach, SPY/QQQ do
not (at least not with mean-reversion at 15-min bars -- they were never
tested with a genuinely different approach post-ADX-audit). Sample size
caveat still applies: IWM's validation rests on ~31 total trades across
the 1yr split (17 in-sample + 14 out-of-sample) -- a real, consistent
signal, but still a modest sample. Worth continuing to validate with more
history before increasing confidence further or considering paper trading.

## Status history (2026-09-18, morning) — mean-reversion-only clears out-of-sample for the first time
**The strongest validated result in the project so far**, found by auditing
the ADX regime filter (see "ADX regime-filter audit" below) and testing
mean-reversion in isolation instead of the ADX-gated hybrid.

**What changed:** an autocorrelation audit of the ADX regime filter found
that "trending" (high-ADX) 15-min bars consistently show NEGATIVE forward
autocorrelation across every horizon tested (15min to a full session) for
SPY/QQQ/IWM -- the opposite of what trend-following assumes. This explains
why trend-following contributed near-zero/negative PnL across every prior
backtest. Tested disabling the regime switch entirely (`ADX_TREND_THRESHOLD
= 999`, so mean-reversion runs 100% of the time) with a proper time-based
train/test split from the start (grid search on first half of 1yr real
data, test on second half never searched over):

- **Best combo: `MR_MA_PERIOD=50, MR_ENTRY_STD_DEV=2.5,
  MR_EXIT_STD_DEV=0.35, STOP_LOSS_ATR_MULT=4.0`** (trend filter still
  enabled) -> in-sample +0.75% (PF 1.23), **out-of-sample +0.66% (PF
  1.18)** -- stayed profitable on data the search never touched. A second
  nearby combo (exit=0.2 instead of 0.35) also held up: +0.67% in-sample ->
  +0.59% out-of-sample (PF 1.16).
- The other 3 of the top-5 in-sample combos degraded to near-breakeven
  (PF 0.92-0.97) rather than collapsing to a clear loss like the
  2026-09-17 regime-switching finding did -- a much gentler degradation.
- All 5 top combos converged on the SAME entry parameters (`MR_MA_PERIOD=50`,
  the longest tested; `MR_ENTRY_STD_DEV=2.5`, the most selective) -- a
  stable choice, not scattered noise. The two combos that stayed profitable
  both used the WIDEST stop (4.0x ATR), consistent with the standing
  finding that premature stop-outs are the dominant loss driver.
- Monte Carlo (5000 bootstrap resamples of the actual 36 out-of-sample
  trades): median return **+0.7%**, P(loss) **34.3%** (roughly 2-in-3 odds
  of profit, not a coin flip), P(hit circuit breaker) 0.0%, worst drawdown
  across all 5000 sims 5.8% (well inside the 10% threshold).

**Important caveat, not yet resolved:** the aggregate out-of-sample profit
is concentrated in IWM (+$83) while QQQ (-$18) and SPY (-$32) were both
slightly negative individually. This is real progress, not a disqualifier,
but it means the result currently rests more on one instrument than on a
broadly consistent effect across all three -- worth investigating (e.g.
does it hold on IWM alone with more history, or on SPY/QQQ separately)
before trusting this as a robust, instrument-agnostic edge.

**Also tested and ruled out same day:** dropping from 15-min to 5-min bars.
Same autocorrelation audit on 6mo of real 5-min data gave inconsistent
results across instruments (SPY showed a theory-consistent flip to positive
trending-bar autocorrelation at longer horizons; QQQ and IWM did not) --
not a clear enough signal to justify the added trading frequency and
commission drag of finer bars. Stuck with 15-min.

**Honest read:** this is the first result in the project to survive genuine
out-of-sample testing with a positive outcome, not just "less negative."
Still based on a modest 36-trade out-of-sample sample and concentrated in
one instrument -- promising and worth taking seriously, not yet "proven."
Don't set this as `config.py`'s defaults or start paper trading purely on
this without addressing the IWM-concentration question first.

### ADX regime-filter audit (2026-09-18) — the finding that led to the above
Before testing mean-reversion alone, audited whether the ADX-based regime
filter (`bot/regime.py`) actually does what its design assumes: high ADX
should mean price continues trending (favoring `trend_following`), low ADX
should mean price mean-reverts (favoring `mean_reversion`). Checked on real
15-min data for all three instruments:

- **ADX distribution**: median ADX sits almost exactly at the default
  threshold of 25 for all three (SPY 25.6, QQQ 26.6, IWM 25.4) -- an
  almost even trending/ranging split at the default setting, not an
  extreme or unusual configuration.
- **Regime persistence**: median run length 18-23 bars (roughly half a
  trading day) before flipping -- not erratic bar-to-bar noise, some
  genuine stickiness, only 8-17% of runs are very short (<=3 bars).
  Persistence itself isn't obviously broken.
- **The actual test that mattered**: computed autocorrelation of
  return[t] vs. forward return over K bars (K = 1, 4, 8, 16, 26, i.e.
  15min to a full session), split by regime label. Trend-following theory
  predicts trending bars should show POSITIVE autocorrelation (momentum
  persists); mean-reversion theory predicts ranging bars should show
  NEGATIVE autocorrelation (price reverts). Result: **"trending" bars
  showed NEGATIVE autocorrelation at every single horizon, for all three
  instruments** -- the opposite of the trend-following assumption.
  "Ranging" bars were also mostly negative (consistent with mean-reversion)
  and in several cases MORE strongly mean-reverting than the "trending"
  bars. Example (SPY, K=8 bars): trending=-0.017, ranging=-0.037.

**Conclusion**: at 15-min bars, SPY/QQQ/IWM don't show the trend-
continuation behavior the regime filter's trend-following branch assumes.
Both regimes lean mean-reverting; ADX just isn't cleanly separating two
behaviorally-different states the way the architecture assumes. This is
also consistent with every prior backtest's PnL-by-strategy breakdown,
where `trend_following`/`donchian_breakout` consistently contributed near-
zero or negative PnL vs. `mean_reversion`/`vwap_reversion` contributing
positively, and with the ADX threshold (20/25/30) barely moving grid-search
results -- tuning a gate built on a false premise doesn't matter much. This
directly motivated testing mean-reversion in isolation (see above), which
produced the first out-of-sample-positive result in the project.

## Repository
Code lives at https://github.com/llehkrad/edwinknowstrade (`main` branch).
Local git identity for this repo: user.name "Edwin", user.email
darkhell85@gmail.com (repo-local config, not global).

## Status history (2026-09-17) — trend filter found real improvement, not yet profitable
**Update 2026-09-17: added a 50-day daily trend filter (`bot/trend_filter.py`)
that changed the picture.** After the 2026-09-16 pause, gated NEW entries
(never exits/stops) by whether yesterday's daily close was above/below its
own 50-day SMA — a completely different timescale than the 900+ configs
already tested. Re-ran both grid searches (648 `sma_zscore` + 216
`vwap_donchian` combos) on the full 1-year real data with the filter on:

- **Best result: `MR_MA_PERIOD=30, MR_ENTRY_STD_DEV=2.5,
  TF_FAST_MA_PERIOD=10, TF_SLOW_MA_PERIOD=50, ADX_TREND_THRESHOLD=25,
  STOP_LOSS_ATR_MULT=4.0`** → -0.09% return (essentially flat), 2.5% max
  drawdown (down from 9-10%), 46.9% win rate (up from ~30-38%), profit
  factor 0.99, 98 round trips, circuit breaker never fired. Top 15 combos
  cluster tightly between -0.09% and -1.8% (vs. wildly scattered negative
  outcomes before) — a healthier sign than one lucky spike.
- Applying the SAME filter to the previous best-known combo and to
  untuned defaults also improved both broadly (losses roughly halved,
  drawdown roughly halved, circuit breaker stopped firing on defaults) --
  see git history 2026-09-16 commit for those numbers.
- Monte Carlo stress test (5000 bootstrap resamples) of the new best
  combo's 98 real trades: P(loss) 51.8% (a coin flip, not "almost
  certain loss" like every prior config), P(hit circuit breaker) **0.0%**
  across all 5000 resequenced simulations (worst-case drawdown seen: 9.5%,
  never crossing 10%), return range -4.3% to +4.2% (p5-p95), median -0.1%.
- `vwap_donchian` improved more modestly with the same filter (best -7.4%
  -> -6.46%), reinforcing that `sma_zscore` is the more promising family.

**CORRECTED same day after proper out-of-sample validation -- the
"breakthrough" above does NOT hold up.** Ran a true time-based train/test
split: grid-searched `sma_zscore` + trend filter on the FIRST HALF of the
1yr data only (Sep 2025-Mar 2026), then re-tested the top 5 in-sample
combos against the SECOND HALF (Mar-Sep 2026), which the search never saw.
Result: **every one of the top 5 in-sample winners -- including combos
with in-sample profit factor above 1.0 (genuinely profitable-looking, not
just least-bad) -- turned into a clear loss out-of-sample** (profit factor
0.37-0.79, returns -0.97% to -3.78%). This is a textbook overfitting
signature. It also explains the "-0.09% essentially flat" full-year number
above: that exact combo's full-year result was quietly an average of a
+0.40% first half and a -0.97% second half, not genuinely flat performance
throughout -- the full-year single-window search was not, in fact, a
sufficient generalization check.

**What DOES still look real: the drawdown/risk reduction.** Out-of-sample
drawdowns stayed contained (2.5%-3.8%, no circuit breaker trips) across
all 5 combos tested -- consistent with the trend filter being a mechanical
effect (it structurally blocks counter-trend entries regardless of which
window you're in) rather than something curve-fit to one dataset. So:
**the risk reduction from the trend filter looks durable; profitability
from the specific entry/exit parameters does not.**

**Updated honest assessment (2026-09-17, end of day): still no validated
profitable edge.** The trend filter is a legitimate, keep-it improvement
for risk management, but no parameter combination has cleared a genuine
out-of-sample bar. Don't re-describe the trend filter as a "breakthrough"
or the -0.09% full-year number as meaningful without this correction
attached. Next steps, if resuming: (a) don't trust single-window full-
period grid search results again without an out-of-sample check baked in
by default, (b) consider whether 1yr of data is simply too little to
reliably validate a 6-parameter search space without overfitting, (c) the
options listed in "Strategy search findings" (2026-09-16) below remain
open (different timeframe, different instruments, audit the regime
filter, or accept this approach may not have edge here).

## Status history (2026-09-16) — for context on how we got here
Phase 1 scaffolding, backtest harness, and the IBKR paper connection are
all built and working end-to-end. **Extensive real-data testing found no
profitable configuration of either strategy family built so far** — see
"Strategy search findings" below. Decision made 2026-09-16: stop automated
parameter/strategy hunting for now and think from first principles before
writing more variations, rather than keep grid-searching into overfit noise.
The execution/backtest/risk infrastructure itself is considered solid and
reusable regardless of which signal logic eventually goes into it.

### Strategy search findings (2026-09-16) — read before trying another variant
Tested across **900+ configurations total**, all losing money:
- 216 combos, `sma_zscore` set (SMA-crossover trend-following + SMA-zscore
  mean reversion), 6mo real data: best -2.9% return, but every combo negative.
- 216 combos, `vwap_donchian` set (VWAP-deviation reversion + Donchian
  breakout — added specifically as a structurally different alternative,
  see `bot/strategies/vwap_reversion.py` / `donchian_breakout.py`), 6mo real
  data: best -7.4% return, every combo negative, and worse overall than
  `sma_zscore`.
- 648 combos, `sma_zscore` set with `STOP_LOSS_ATR_MULT` added to the grid
  (2.0-4.0x), 6mo real data: widening the stop did NOT help — the single
  best combo across all 648 still used the original 2.0x multiplier.
- 18 targeted combos isolating `MR_EXIT_STD_DEV` (exit threshold) against
  the top 3 known entry-param combos: confirmed exits matter (one combo
  improved monotonically from -5.6% to -2.2% as the exit got looser/faster),
  but the effect was inconsistent/non-monotonic across the other two combos,
  and NONE reached profitability. Best result found anywhere: -2.23%.
- The single best 6-month combo, re-tested on a full 1-year pull
  (Sep 2025-Sep 2026, 6482 bars/symbol): return degraded from -2.9% to
  -8.67% — a classic overfitting signature (looked good on the exact slice
  it was fitted on, didn't generalize). Default/untuned params scored
  almost identically on both windows (-9.92% vs -9.81%), confirming this
  isn't just an unlucky short sample.
- Consistent pattern across ALL of the above: `stop_loss` exits dominate
  the PnL-by-strategy breakdown (typically -$700 to -$850), while the
  underlying entry signals (mean_reversion/trend_following/vwap_reversion/
  donchian_breakout) are usually mildly profitable on their own. The
  losses come specifically from how positions get stopped out, not from
  bad entries -- but no amount of stop-widening or exit-threshold tuning
  tested so far fixed it.

**Options considered for resuming this, not yet acted on:**
1. Try a fundamentally different timeframe (daily/4hr bars instead of
   15-min) -- untested, would also change the bot from intraday-monitoring
   to something needing far less unsupervised infrastructure.
2. Check whether SPY/QQQ/IWM specifically (famously liquid/efficient,
   heavily arbitraged) are just a bad fit for this style of edge, by
   backtesting the same strategies on historically choppier/less efficient
   names.
3. Revisit the regime filter itself (ADX-based trending/ranging split) --
   never independently audited; both failing strategy families sit behind
   it, so a bad regime split could be sabotaging both.
4. Consider that simple technical rules on this instrument/timeframe combo
   may not have edge at all, and Phase 1's approach needs to change more
   fundamentally rather than be re-tuned.

Don't silently re-run the same grids again without picking one of the
above (or something new) first -- 900+ trials already run without success
means another blind grid search is more likely to find noise than edge.

**Two real bugs found and fixed while getting the paper connection working
(2026-09-16), before any order was placed:**
1. `ib_insync`'s `eventkit` dependency calls `asyncio.get_event_loop()` at
   import time, relying on implicit loop-creation behavior Python 3.14
   removed — raised `RuntimeError` before `ib_insync` finished importing.
   Fixed with a shared shim (`ib_compat.py`), applied before every
   `ib_insync` import.
2. `bot/main.py`'s equity tracking was a no-op placeholder
   (`portfolio.update_equity(portfolio.equity)` — reassigning a value to
   itself). Equity never actually moved from `config.ACCOUNT_EQUITY_USD` in
   live/paper mode, which meant **the drawdown circuit breaker could never
   fire** — the exact safety mechanism this whole project's unsupervised-
   overnight design depends on. Fixed with real cash + mark-to-market
   accounting (same approach `backtest/engine.py` already used), driven by
   actual IBKR fill prices/commissions rather than assumed bar-close prices.
   Deliberately NOT reconciled against `ib.accountSummary()`'s
   NetLiquidation — IBKR seeded this paper account with an unrelated ~$1M,
   not the $5k the strategy is actually sized against.

**Built so far:**
- `config.py` — all Phase 1 parameters (see "Decisions resolved" below).
- `bot/` — full execution-layer scaffold: `main.py` (ib_insync live loop),
  `regime.py` (ADX regime filter), `strategies/mean_reversion.py`,
  `strategies/trend_following.py`, `risk_manager.py` (ATR + capital-capped
  position sizing, exposure cap, circuit breaker), `portfolio.py`,
  `indicators.py`, `signal.py`, `alerts.py` (Slack webhook), `trade_log.py`
  (CSV logging).
- `backtest/` — engine (`engine.py`, reuses the live `bot/` modules directly
  so backtest and live logic can't diverge), IBKR commission/slippage model
  (`costs.py`), metrics (`metrics.py`), parameter grid search (`optimize.py`),
  Monte Carlo resampling on completed trades (`monte_carlo.py` /
  `run_monte_carlo.py` — bootstrap or shuffle the real round-trip PnLs a
  backtest produced to see the range of possible drawdowns/returns from the
  same trade outcomes in a different order, not just the one historical
  sequence; added 2026-09-14), historical data loading (`data.py`), a real
  IBKR fetcher (`fetch_ibkr_data.py`, needs Gateway/TWS running), a
  synthetic-data generator for smoke-testing without a live connection
  (`generate_synthetic_data.py`), and a self-contained HTML dashboard builder
  (`build_dashboard.py` — equity curve, drawdown, daily trading calendar,
  PnL breakdowns, filterable trades table).
- `check_ibkr_connection.py` — one-command sanity check: connects via
  ib_insync, prints account summary, flags any instrument not showing Live
  (vs delayed) market data.
- Smoke-tested the entire backtest engine end-to-end against synthetic data
  (real historical data isn't pulled yet — that needs the IBKR connection).
  This caught and fixed a real bug: pure ATR-risk position sizing proposed
  positions 3-4x account equity on $200-500+/share ETFs; fixed with a new
  `config.MAX_POSITION_PCT_OF_EQUITY` capital cap in `bot/risk_manager.py`.
- Ran the parameter grid search (`backtest/optimize.py`) end-to-end on
  synthetic data to confirm the mechanism works. The "winning" parameters
  from that run are meaningless and must be discarded — synthetic data has a
  deterministic sine-wave drift baked in for testing purposes, so the grid
  search was just fitting to that artifact, not to anything resembling real
  market behavior. Re-run on real data once available.

**IBKR account setup status:**
- Market data subscriptions active: US Securities Snapshot and Futures Value
  Bundle (NP,L1) ($10/mo, waived at $30/mo commissions) + US Equity and
  Options Add-On Streaming Bundle (NP) ($4.50/mo) — covers real-time
  streaming for SPY/QQQ/IWM (NYSE Arca + Nasdaq) plus OPRA options data for
  Phase 2 later.
- Confirmed **TWS** (Trader Workstation) is required for the API, NOT IBKR
  Desktop (a separate, newer IBKR app with no API support as of 2026).
- Paper trading account provisioned and confirmed working 2026-09-16
  (username `llehkradpaper`, account `DUT119165`). Note: IBKR seeds paper
  accounts with an unrelated ~$1M NetLiquidation by default — irrelevant to
  this project since equity is tracked internally from
  `config.ACCOUNT_EQUITY_USD`, not from the broker's reported balance (see
  bug #2 above).
- Historical-data pulls occasionally fail with IBKR error 162 ("Trading TWS
  session is connected from a different IP address") even with only TWS
  connected — seems to be a stale historical-data-farm connection inside
  TWS. Fix: fully close and reopen TWS (not just log out), log back into
  paper trading, wait for all data-farm status icons to go green, retry.

## Resume checklist
1. Log into TWS with paper trading credentials (not live) — confirm the
   title bar says "Paper Trading". Verify API settings survived (Enable
   ActiveX/Socket Clients, Read-Only API unchecked, port 7497). ✅ done
   2026-09-16.
2. Run `python check_ibkr_connection.py` — confirms connectivity and that
   SPY/QQQ/IWM show Live (not delayed) data. ✅ done 2026-09-16.
3. Run `python -m backtest.fetch_ibkr_data --duration "6 M"` to pull real
   historical bars (replaces the synthetic data in `data/historical/`). Must
   be run with `-m` (module form), not as a plain script path. ✅ done
   2026-09-16 (3198 bars/symbol, Mar-Sep 2026).
4. Re-run `python -m backtest.run_backtest` and `python -m backtest.optimize`
   on real data — ✅ done 2026-09-16 (900+ configs, all losing) and again
   2026-09-17 with the new 50-day trend filter (best combo ~flat, see
   "Current status" above). Don't re-run the same grids again without a
   new hypothesis — see out-of-sample validation note below.
5. Regenerate the dashboard with `python -m backtest.build_dashboard
   --real-data` (drops the synthetic-data warning banner). ✅ done
   2026-09-16 for the 6mo untuned baseline; not yet regenerated for the
   2026-09-17 trend-filtered best combo.
6. Run `python -m backtest.run_monte_carlo` on the real `fills.csv` — ✅
   done 2026-09-17 for the trend-filtered best combo (P(loss) 51.8%,
   P(circuit breaker) 0.0% across 5000 sims — see "Current status" above).
7. **Do not begin paper trading yet.** Still not a demonstrated edge —
   run proper out-of-sample validation first (fit/select on the first half
   of the 1yr data, test on the second half you didn't search over) before
   trusting the 2026-09-17 result enough to start the 2+ week paper track
   record.

Note: `backtest/fetch_ibkr_data.py --duration "1 Y"` was also pulled and
tested 2026-09-16 (6482 bars/symbol, Sep 2025-Sep 2026) — this surfaced and
fixed a real bug in `backtest/data.py`: a pull spanning a US DST transition
has mixed UTC offsets (-04:00/-05:00) in the raw timestamps, which pandas'
`read_csv(parse_dates=...)` silently failed to parse (left as plain
strings) rather than raising. Fixed by parsing through
`pd.to_datetime(..., utc=True)` then converting to `America/New_York`.

## Background
Inspired by a marketing doc ("How to Build a Trading Bot with Claude Fable")
promoting Alpaca + a 5-instrument (SPY/QQQ/BTC/GLD/USO) system with 3 strategy
types. That doc is a reasonable structural template but built for the wrong
broker and doesn't account for the operator's timezone or asset scope. This
file captures the adapted plan actually decided on.

## Operator context
- Based in Singapore (SGT, UTC+8).
- Broker: **Interactive Brokers (IBKR)** — NOT Alpaca. Use `ib_insync`
  connecting to IB Gateway / TWS, not `alpaca-trade-api`.
- US regular market hours (9:30am–4:00pm ET) land at **~9:30pm–4:00am SGT**
  (shifts by the DST offset, since Singapore doesn't observe DST but the US
  does — recheck the mapping around US DST transitions in Mar/Nov).
- **The bot runs fully unsupervised overnight while the operator sleeps.**
  This is the single biggest design constraint — every strategy must be
  safe with zero human intervention for 6+ hours. Defined-risk structures
  only (hard stops on equities; spreads not naked options).
- Hosting: dedicated AWS Lightsail instance (separate from the operator's
  existing Lightsail, which runs an unrelated KTV/karaoke pitch-shifter
  project — do not co-locate, different resource/latency profiles).
  Recommended tier: ~$10/month (1GB RAM) for headroom to run IB Gateway
  alongside the Python bot. Use `systemd` with `Restart=always` (not pm2 —
  no Node ecosystem here). Static IP attached.
- Reporting: operator has **Slack** (first-party Cowork connector) — use
  this, not Telegram (Telegram integration path is less mature/native as of
  this writing — recheck current state if revisiting).

## Architecture (3 layers, don't conflate them)
1. **Execution layer** — standalone Python process (ib_insync), runs 24/7 via
   systemd on the dedicated Lightsail box. Deterministic if/then logic only,
   no AI/model involved at runtime. Polls candles → computes indicators →
   checks rule → places order via IBKR API → logs to CSV.
2. **Build/maintenance layer** — Claude Code, used interactively to write and
   later extend the bot. Not running in the background; only active when the
   operator is working on it.
3. **Reporting layer** — Claude Cowork scheduled tasks, reading trade logs
   (via Google Drive sync and/or a Slack webhook feed from the bot) and
   posting narrative summaries to Slack on a schedule. Also not running
   continuously — wakes on cadence only.
   - Instant alerts (e.g. drawdown circuit breaker firing) should be a
     direct webhook call from the Python bot itself, NOT dependent on the
     Cowork schedule — don't let something urgent wait for the next digest.

## Phased build plan
### Phase 1 — Equities (build this first)
- Instruments: **SPY, QQQ, IWM** (dropped BTC/GLD/USO from the original doc
  — narrower, equity-index-only scope for now; IWM added for small-cap
  diversification vs SPY/QQQ's large-cap overlap).
- Strategy: mean reversion AND trend following, combined via an **ADX-based
  regime filter** (`bot/regime.py`) rather than run in parallel or requiring
  confluence — ADX >= `config.ADX_TREND_THRESHOLD` picks trend-following,
  below it picks mean reversion. Only one strategy trades a given instrument
  at a time. Both are defined-risk (hard stop caps loss, no active
  management needed while asleep). Exact parameter VALUES (MA periods,
  std-dev thresholds, ADX threshold) are still placeholders in `config.py`
  pending a real backtest — see "Resume checklist" above.
- Timeframe: 15-min bars to start (`config.BAR_SIZE`), kept as a single
  config value so it's easy to drop to 5-min or lower later.
- Holding style: **swing trading only** (positions may carry across
  sessions, no same-day flatten) — deliberate choice to stay clear of the US
  Pattern Day Trader rule, since the account is far under the $25k PDT
  threshold and same-day round trips are what count against that limit.
- Position sizing: ATR-based (1 ATR move = `config.RISK_PER_TRADE_PCT`, 1%,
  of account equity; risk stays constant across instruments regardless of
  individual volatility), using IBKR fractional shares
  (`config.USE_FRACTIONAL_SHARES`) since $5k equity against $200-500+/share
  ETFs needs fractional sizing to be meaningful. Also capped by
  `config.MAX_POSITION_PCT_OF_EQUITY` (30% of equity per position) so sizing
  never implies more notional than the account can actually afford — see
  "Current status" above for the bug this caught.
- Correlation consideration: SPY/QQQ/IWM are generally MORE correlated with
  each other than the original doc's SPY/QQQ/BTC mix — may want a tighter
  same-direction exposure cap across the three, not a looser one.
- Data: confirm IBKR real-time market data subscription is active (Client
  Portal → Settings → Market Data Subscriptions) before building — without
  it, data defaults to 15-min delayed, which breaks any short-timeframe
  strategy. Use `reqHistoricalData` with `keepUpToDate=True` for live
  5-min/15-min bars (simpler than manually aggregating `reqRealTimeBars`
  5-second bars).
- File structure (extend, don't rebuild, in later phases) — built as of
  2026-09-12, see "Current status" above for details:
  ```
  bot/strategies/mean_reversion.py
  bot/strategies/trend_following.py
  bot/strategies/vwap_reversion.py
  bot/strategies/donchian_breakout.py
  bot/strategy_registry.py
  bot/regime.py
  bot/risk_manager.py
  bot/portfolio.py
  bot/indicators.py
  bot/signal.py
  bot/alerts.py
  bot/trade_log.py
  bot/main.py
  backtest/engine.py
  backtest/costs.py
  backtest/metrics.py
  backtest/optimize.py
  backtest/monte_carlo.py
  backtest/run_monte_carlo.py
  backtest/data.py
  backtest/fetch_ibkr_data.py
  backtest/generate_synthetic_data.py
  backtest/build_dashboard.py
  check_ibkr_connection.py
  ib_compat.py
  config.py
  .env
  ```
- Required before going live: backtest (6mo+ historical data, realistic
  slippage/commissions — IBKR options/equities are NOT commission-free like
  Alpaca, factor real per-trade costs in) → minimum 2 weeks paper trading →
  only then switch `.env` to live API keys.
- Circuit breaker: close all positions and halt if total equity drawdown
  exceeds a set threshold (doc used 10%) until manually reviewed.

### Phase 2 — Options (build after Phase 1 is live and stable)
- Same underlyings (SPY/QQQ/IWM) — reuse Phase 1's connection/logging/
  reporting scaffolding as much as possible.
- Confirm IBKR account has the required options trading permission tier
  before building (based on account disclosures — check this early, it can
  block order submission even after code is ready).
- Strategy preference: **defined-risk only** — credit spreads (bull put /
  bear call) or iron condors. Explicitly avoid naked puts/calls or
  undefined-risk structures for anything running unsupervised overnight.
- New modules needed (none of this exists in the original doc, which never
  covers options): options chain retrieval, strike/expiration (DTE)
  selection logic, Greeks-based entry filters, assignment-risk handling,
  pre-expiration close-out logic.
- Real per-contract commissions must be modeled in backtests (unlike the
  Alpaca doc's $0 commission assumption).

### Phase 3 — Crypto (build last)
- Reintroduces 24/7 trading (no market-hours boundary) — different failure
  mode than equities/options (weekend gaps, no natural "market close" reset
  point).
- Reintroduce a correlation filter across asset classes — e.g. don't stack
  new long crypto exposure on top of already-long SPY/QQQ/IWM, similar
  intent to the original doc's SPY/QQQ vs BTC filter.

## Decisions resolved (2026-09-12)
- Risk appetite / account size: **$5,000** (`config.ACCOUNT_EQUITY_USD`;
  corrected same day from an initial placeholder of $1,000). Risk per trade:
  **1%** of equity (`config.RISK_PER_TRADE_PCT`).
- Candle timeframe: **15-min bars** to start (`config.BAR_SIZE`), easy to
  change later.
- Strategy combination: **ADX regime filter** (`bot.regime`), not parallel
  strategies or confluence-required entries.
- Holding style: **swing trading only**, no same-day flatten — avoids the
  PDT rule.
- Capital allocation: **IBKR fractional shares**, with a capital cap
  (`config.MAX_POSITION_PCT_OF_EQUITY`) layered on top of ATR-risk sizing.
- Reporting integration: confirmed **Slack** (Cowork connector) over
  Telegram.

## Decisions still open
- **Whether the current strategy approach has a real, robust edge —
  resolved for IWM, unresolved/negative for SPY and QQQ, as of 2026-09-18.**
  Mean-reversion-only (`STRATEGY_SET = "mean_reversion_only"`) with
  `MR_MA_PERIOD=50, MR_ENTRY_STD_DEV=2.5, STOP_LOSS_ATR_MULT=4.0` cleared
  out-of-sample validation on IWM specifically via two independent search
  paths (shared-universe grid AND an IWM-only grid), both converging on
  the same parameters with profit factor 2.2-3.9 in/out of sample. Ran the
  SAME rigor on SPY and QQQ individually with their OWN best-fit
  parameters -- both failed out-of-sample (SPY: PF up to 2.51 in-sample
  collapsing to 0.62-0.87 out-of-sample; QQQ: never positive in-sample to
  begin with). See "Current status" above for full numbers. Plausible
  explanation: IWM (small-caps) is less efficiently arbitraged than SPY/QQQ
  (mega-cap index products), so real short-term mean-reversion surviving
  there specifically, and not in the other two, is economically sensible.
  Still only ~31 total IWM trades across the 1yr split -- real and
  consistent, but a modest sample. Don't set as `config.py` defaults or
  begin paper trading without more history to further confirm IWM.
- **Fixed watchlist question, now has a real answer**: narrow Phase 1's
  mean-reversion strategy to IWM alone rather than forcing SPY/QQQ into an
  approach that isn't validated for them. SPY/QQQ were only tested with
  mean-reversion post-ADX-audit -- they haven't been tried with a
  genuinely different strategy type, so "no edge" is specific to this
  approach, not a final word on those two instruments.
- The 2026-09-17 finding (ADX-gated hybrid + trend filter) did NOT survive
  out-of-sample testing and should not be revisited as a candidate — see
  "Status history (2026-09-17)" below for what was tried and ruled out.
- Remaining open: whether 1yr of real data is enough to reliably validate
  even a simpler 4-parameter search without overfitting (IWM's result
  suggests yes when the signal is real and simple; SPY's suggests no when
  it isn't). If pursuing SPY/QQQ further, a different strategy type
  (post-ADX-audit, not more mean-reversion tuning) is the more promising
  angle than more parameter search on an approach already shown not to
  fit them.
- Fixed watchlist (SPY/QQQ/IWM only) vs. later screener/scanner approach
  for a wider universe — deferred, not needed for Phase 1.

## Explicit non-goals / things to avoid
- No LLM/AI making live trade decisions — all execution logic is
  deterministic, backtestable, and reviewed before deployment.
- Don't co-locate this bot on the operator's existing KTV Lightsail
  instance.
- Don't build naked/undefined-risk options strategies given the
  unsupervised-overnight operating constraint.
- This is not financial advice; standard trading risk disclaimers apply —
  paper trade extensively, never risk money the operator can't afford to
  lose.
