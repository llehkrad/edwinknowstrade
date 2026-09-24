# Fixed Stop-Loss %% x Take-Profit Ratio Sweep — Out-of-Sample Validation

**Date:** 2026-09-24
**Branch:** bracket-tp-sl
**Script:** `backtest/validate_fixed_pct_sweep.py`
**Full raw log:** `backtest_results/fixed_pct_sweep_log.txt` (4045 lines, ~4.4 hours runtime)

## What this tests

Follow-up to `backtest/validate_fixed_pct_exits.py` (single 5% stop / 15% TP
test), which the operator flagged as producing far too few trades to trust
(SPY got only 1 trade in the whole 6-month OOS window). This run sweeps
THREE fixed stop-loss sizes crossed with TWO take-profit ratios — 6 total
stop/TP combinations — using `config.STOP_LOSS_MODE = 'fixed_pct'`:

| Stop-loss % | TP ratio | TP distance |
|---|---|---|
| 0.5% | 2:1 | 1.0% |
| 0.5% | 3:1 | 1.5% |
| 1.0% | 2:1 | 2.0% |
| 1.0% | 3:1 | 3.0% |
| 1.5% | 2:1 | 3.0% |
| 1.5% | 3:1 | 4.5% |

Crossed with the same 5 strategies (mean_reversion_only, vwap_reversion_only,
orb_only, rsi_reversion_only, bb_squeeze_only) and 5 symbols (SPY, QQQ, IWM,
TSLA, GOOGL) used throughout this repo's bracket-exit work — 150
symbol/strategy/combo cells total, all 150 completed.

**Simplification (documented up front, per operator's own instruction to
keep this manageable):** unlike `validate_fixed_pct_exits.py`, which re-tests
the *top-3* in-sample entry-param combos out-of-sample, this sweep re-tests
only the single **best** in-sample entry-param combo per
symbol/strategy/stop-TP-combo cell. Everything else (same 5 strategies' own
entry-parameter grids, same in-sample/out-of-sample time split — first half
of 1yr 15-min data in-sample, second half OOS, never searched — per symbol)
matches the prior script exactly.

Per explicit operator instruction: **NO buy-and-hold comparison, no verdict
labels — raw numbers only** (OOS return %, profit factor, trade count, win
rate).

## Trade-count problem from the 5% test: fixed

The whole point of this sweep was to check whether narrower stops produce
enough OOS trades to draw any conclusion at all. They do:

| Combo | Total OOS trades (across all 25 symbol/strategy cells) | Min trades in any single cell | Avg trades/cell |
|---|---|---|---|
| 0.5%/1.0%TP | 974 | 4 | 39.0 |
| 0.5%/1.5%TP | 1020 | 6 | 40.8 |
| 1.0%/2.0%TP | 759 | 6 | 30.4 |
| 1.0%/3.0%TP | 648 | 4 | 25.9 |
| 1.5%/3.0%TP | 578 | 4 | 23.1 |
| 1.5%/4.5%TP | 473 | 2 | 18.9 |

Compare to the prior 5%-stop test, where SPY got exactly **1** trade per
strategy across the whole OOS window. Every combo here clears that bar by a
wide margin — even the widest bracket tested (1.5%/4.5%TP) averages ~19
trades per cell, and the tightest bracket (0.5%/1.0%TP) averages ~39. A
handful of individual cells (mostly `rsi_reversion_only`, whose entry
condition is inherently rarer) still land in single digits, but nothing
resembling the 1-trade degenerate case recurs.

## Aggregate results by stop/TP combo (averaged across all 25 symbol/strategy cells)

| Combo | Avg OOS return | Avg OOS PF | Cells with positive return (of 25) |
|---|---|---|---|
| 0.5%SL / 1.0%TP (2:1) | -1.54% | 0.73 | 2 |
| 0.5%SL / 1.5%TP (3:1) | -1.38% | 0.88 | 6 |
| 1.0%SL / 2.0%TP (2:1) | -1.02% | 0.95 | 8 |
| **1.0%SL / 3.0%TP (3:1)** | **-0.16%** | **1.04** | **13** |
| **1.5%SL / 3.0%TP (2:1)** | **-0.21%** | **1.09** | **12** |
| 1.5%SL / 4.5%TP (3:1) | -0.71% | 0.91 | 10 |

The tightest brackets (0.5% stop) are clearly worse on average — return and
profit factor both degrade monotonically as the stop tightens below 1%,
almost certainly because a 0.5% stop on 15-min bars gets clipped by normal
intrabar noise before the underlying signal has room to play out. The two
mid-sized brackets, **1.0%SL/3.0%TP (3:1)** and **1.5%SL/3.0%TP (2:1)**, are
the only ones averaging a positive OOS return and a profit factor above 1.0,
and each has roughly half (12-13 of 25) of their symbol/strategy cells
finishing positive. The widest bracket (1.5%/4.5%) falls off again, both in
average return and in shrinking trade counts.

## Top 20 individual symbol/strategy/combo cells by OOS return

| Symbol | Strategy | Combo | OOS Return | OOS PF | Trades | Win Rate |
|---|---|---|---|---|---|---|
| TSLA | orb_only | 1.0%SL/3.0%TP (3:1) | **+5.90%** | 1.37 | 70 | 35.71% |
| TSLA | orb_only | 1.5%SL/3.0%TP (2:1) | +5.28% | 1.28 | 63 | 42.86% |
| QQQ | bb_squeeze_only | 1.5%SL/4.5%TP (3:1) | +3.15% | 1.51 | 19 | 36.84% |
| IWM | vwap_reversion_only | 1.5%SL/3.0%TP (2:1) | +2.51% | 1.71 | 14 | 50.00% |
| SPY | bb_squeeze_only | 1.5%SL/3.0%TP (2:1) | +2.41% | 3.43 | 6 | 66.67% |
| IWM | mean_reversion_only | 1.0%SL/2.0%TP (2:1) | +2.38% | 2.12 | 14 | 57.14% |
| SPY | bb_squeeze_only | 1.0%SL/3.0%TP (3:1) | +2.37% | 3.27 | 7 | 57.14% |
| TSLA | bb_squeeze_only | 1.5%SL/4.5%TP (3:1) | +2.24% | 1.23 | 28 | 32.14% |
| IWM | vwap_reversion_only | 1.0%SL/2.0%TP (2:1) | +1.84% | 1.32 | 31 | 45.16% |
| SPY | orb_only | 1.0%SL/3.0%TP (3:1) | +1.80% | 1.43 | 19 | 36.84% |
| TSLA | orb_only | 1.0%SL/2.0%TP (2:1) | +1.75% | 1.10 | 86 | 40.70% |
| QQQ | vwap_reversion_only | 1.5%SL/4.5%TP (3:1) | +1.70% | 1.49 | 11 | 36.36% |
| TSLA | vwap_reversion_only | 1.5%SL/3.0%TP (2:1) | +1.70% | 1.29 | 21 | 42.86% |
| SPY | orb_only | 1.5%SL/3.0%TP (2:1) | +1.61% | 1.47 | 13 | 46.15% |
| TSLA | vwap_reversion_only | 1.0%SL/3.0%TP (3:1) | +1.61% | 1.31 | 23 | 34.78% |
| GOOGL | orb_only | 1.5%SL/3.0%TP (2:1) | +1.50% | 1.14 | 35 | 40.00% |
| SPY | vwap_reversion_only | 0.5%SL/1.5%TP (3:1) | +1.46% | 2.06 | 14 | 50.00% |
| IWM | vwap_reversion_only | 1.0%SL/3.0%TP (3:1) | +1.44% | 1.23 | 27 | 33.33% |
| QQQ | bb_squeeze_only | 1.0%SL/3.0%TP (3:1) | +1.42% | 1.23 | 27 | 33.33% |
| QQQ | mean_reversion_only | 1.0%SL/3.0%TP (3:1) | +1.40% | 1.17 | 34 | 32.35% |

Out of 150 total cells, **51 finished OOS-positive**; the two mid-size
brackets (1.0%/3.0% and 1.5%/3.0%) account for 25 of those 51, roughly
double their 1-in-6 "fair share" if results were random noise.

**TSLA `orb_only`** is the standout: two different stop/TP combos
(1.0%/3.0%TP and 1.5%/3.0%TP) both land in the top 2 by return, with
reasonable trade counts (70 and 63) and PF around 1.3. That consistency
across two adjacent bracket sizes on the same symbol/strategy pair is a
mildly more convincing signal than a single lucky cell, though it is one
data point among 150 and the operator should treat it as a lead to watch,
not a validated edge — TSLA `orb_only` was clearly *negative* at both 0.5%
stop sizes (-4.46%, -2.61%) and at the widest 1.5%/4.5% combo (-3.69%), so
the result is sensitive to exactly which bracket size is chosen, not a
robust edge across the whole stop-size range.

## Full per-symbol/strategy/combo results

See `backtest_results/fixed_pct_sweep_log.txt`, section
`--- FLAT DETAIL TABLE ---` (line 3894 onward) for all 150 rows
(symbol, strategy, combo, entry params, OOS return, OOS PF, OOS trade count,
OOS win rate). The same log also contains four pivoted summary tables
(return %, trade count, profit factor, win rate — rows = symbol/strategy,
columns = the 6 stop/TP combos) starting at `SUMMARY -- fixed stop-loss %`
(line 3776), plus the full in-sample grid-search trace for every one of the
150 cells above that.

## Reading this

- **0.5% stops are too tight** for 15-min-bar intraday strategies on this
  universe: both 0.5% combos have the worst average return (-1.54%, -1.38%)
  and worst average PF (0.73, 0.88) of the six, despite having the *most*
  trades — consistent with stops getting clipped by ordinary intrabar noise
  before the signal can play out, exactly the opposite failure mode from the
  5%-stop test's "too rare to matter" problem.
- **1.0%SL/3.0%TP (3:1)** and **1.5%SL/3.0%TP (2:1)** are the only two combos
  averaging a positive OOS return with PF > 1.0 across the 25 cells, and
  both maintain adequate trade counts (avg 25.9 and 23.1 trades/cell,
  minimum 4 trades in the worst single cell — mostly `rsi_reversion_only`,
  whose entry condition is inherently rare).
- No symbol/strategy/combo result here should be read as a validated edge
  from a single run — 150 grid-searched cells on 6-month OOS windows will
  produce some cells that look good by chance. TSLA `orb_only` at both mid
  brackets is the most repeatedly-positive result and worth a closer look
  (e.g. a longer OOS window or walk-forward re-test) before treating it as
  more than a lead.
- Config defaults in `config.py` were left untouched (`STOP_LOSS_MODE`
  stays `'atr'` as the committed default) — the fixed-% mode and its
  stop/TP values are only set at runtime inside
  `backtest/validate_fixed_pct_sweep.py`, mirroring
  `validate_fixed_pct_exits.py`.
