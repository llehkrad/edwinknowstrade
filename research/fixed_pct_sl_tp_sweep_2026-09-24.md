# Fixed Stop-Loss %% / Take-Profit Ratio Sweep — Out-of-Sample Results

**Date:** 2026-09-24
**Branch:** bracket-tp-sl
**Script:** `backtest/validate_fixed_pct_sweep.py`
**Full raw log:** `backtest_results/fixed_pct_sweep_log.txt`

## What this tests

A parameter sweep of `config.STOP_LOSS_MODE = 'fixed_pct'`
(`bot/risk_manager.py`), crossing:

- **Stop-loss %:** 0.5%, 1.0%, 1.5% of entry price
- **Take-profit ratio:** 2:1, 3:1 (take-profit distance = stop % x ratio)

into **6 stop/TP combinations**:

| Combo | Stop | Take-profit |
|---|---|---|
| 0.5%SL/1.0%TP(2:1) | 0.5% | 1.0% |
| 0.5%SL/1.5%TP(3:1) | 0.5% | 1.5% |
| 1.0%SL/2.0%TP(2:1) | 1.0% | 2.0% |
| 1.0%SL/3.0%TP(3:1) | 1.0% | 3.0% |
| 1.5%SL/3.0%TP(2:1) | 1.5% | 3.0% |
| 1.5%SL/4.5%TP(3:1) | 1.5% | 4.5% |

crossed against the same 5 strategies (`mean_reversion_only`,
`vwap_reversion_only`, `orb_only`, `rsi_reversion_only`, `bb_squeeze_only`)
and 5 symbols (SPY, QQQ, IWM, TSLA, GOOGL) used throughout this repo's
bracket-exit validation work — **150 symbol x strategy x combo cells total**.

This directly follows up on `backtest/validate_fixed_pct_exits.py`
(fixed 5% stop / 15% TP, 3:1), whose out-of-sample test **failed on trade
count**: SPY had only 1 trade per strategy in the whole OOS window, far too
few to draw any conclusion from. This sweep uses much tighter stops so
trades trigger often enough to be statistically meaningful.

**Methodology** (unchanged from prior scripts in this branch): 1yr of
15-min data per symbol, split at the midpoint by time into in-sample
(first half, grid-searched) and out-of-sample (second half, never
searched). For every symbol/strategy/stop-TP-combo cell, each strategy's
own entry-parameter grid is searched in-sample; the single best in-sample
combo (by in-sample return) is re-tested out-of-sample. Only that one
best-in-sample combo's OOS result is reported per cell (not top-3, to keep
this 6x-larger sweep's output manageable).

Per explicit operator instruction: **raw numbers only — no buy-and-hold
comparison, no verdict labels.**

## Trade-count sanity check (the reason for this sweep)

The prior fixed-5%-stop test produced 0-11 trades per cell, mostly 1.
This sweep's tightest combo (0.5%SL/1.0%TP) alone produced 974 total
trades across all 25 symbol/strategy cells (avg 39/cell); even the
widest combo (1.5%SL/4.5%TP) produced 473 total trades (avg 18.9/cell).
**Every one of the 150 cells has at least 2 trades, and the vast majority
have 10+** — the trade-count problem from the 5% test is resolved.

## Aggregate results by stop/TP combo (across all 25 symbol x strategy cells)

| Combo | Avg return | Median return | % cells positive | Avg PF | Total OOS trades | Avg trades/cell |
|---|---|---|---|---|---|---|
| 0.5%SL/1.0%TP(2:1) | -1.54% | -1.36% | 8% | 0.73 | 974 | 39.0 |
| 0.5%SL/1.5%TP(3:1) | -1.38% | -1.28% | 24% | 0.88 | 1020 | 40.8 |
| 1.0%SL/2.0%TP(2:1) | -1.02% | -1.11% | 32% | 0.95 | 759 | 30.4 |
| **1.0%SL/3.0%TP(3:1)** | **-0.16%** | **+0.12%** | **52%** | **1.04** | 648 | 25.9 |
| **1.5%SL/3.0%TP(2:1)** | -0.21% | -0.10% | 48% | **1.09** | 578 | 23.1 |
| 1.5%SL/4.5%TP(3:1) | -0.71% | -0.72% | 40% | 0.91 | 473 | 18.9 |

**The tight 0.5% stops are clearly worst** across every metric (avg PF
0.73-0.88, only 8-24% of cells positive) — consistent with getting
whipsawed out by normal 15-min noise before the trade can develop.
**1.0%SL/3.0%TP(3:1) and 1.5%SL/3.0%TP(2:1) are the two standout combos**:
both have PF near/above breakeven (1.04 / 1.09) and are the only combos
where roughly half of all cells came out positive, while still keeping
healthy trade counts (23-26 trades/cell on average).

## Full results table (every symbol x strategy x stop/TP cell)

Return % / Profit Factor / Trade Count / Win Rate, out-of-sample, best
in-sample entry-param combo per cell.

### SPY

| Strategy | Combo | Return | PF | Trades | Win Rate |
|---|---|---|---|---|---|
| mean_reversion_only | 0.5%SL/1.0%TP(2:1) | -0.55% | 0.80 | 21 | 38.10% |
| mean_reversion_only | 0.5%SL/1.5%TP(3:1) | -0.13% | 0.95 | 19 | 31.58% |
| mean_reversion_only | 1.0%SL/2.0%TP(2:1) | -1.13% | 0.60 | 11 | 27.27% |
| mean_reversion_only | 1.0%SL/3.0%TP(3:1) | +0.42% | 1.12 | 16 | 31.25% |
| mean_reversion_only | 1.5%SL/3.0%TP(2:1) | +0.04% | 1.03 | 8 | 37.50% |
| mean_reversion_only | 1.5%SL/4.5%TP(3:1) | +1.39% | 1.56 | 8 | 37.50% |
| vwap_reversion_only | 0.5%SL/1.0%TP(2:1) | +1.17% | 1.85 | 17 | 58.82% |
| vwap_reversion_only | 0.5%SL/1.5%TP(3:1) | +1.46% | 2.06 | 14 | 50.00% |
| vwap_reversion_only | 1.0%SL/2.0%TP(2:1) | +0.11% | 1.06 | 10 | 40.00% |
| vwap_reversion_only | 1.0%SL/3.0%TP(3:1) | +0.45% | 1.23 | 9 | 33.33% |
| vwap_reversion_only | 1.5%SL/3.0%TP(2:1) | +0.07% | 1.03 | 8 | 37.50% |
| vwap_reversion_only | 1.5%SL/4.5%TP(3:1) | -1.18% | 0.52 | 6 | 16.67% |
| orb_only | 0.5%SL/1.0%TP(2:1) | -2.20% | 0.65 | 48 | 33.33% |
| orb_only | 0.5%SL/1.5%TP(3:1) | -0.85% | 0.84 | 38 | 28.95% |
| orb_only | 1.0%SL/2.0%TP(2:1) | +1.01% | 1.23 | 23 | 43.48% |
| orb_only | 1.0%SL/3.0%TP(3:1) | +1.80% | 1.43 | 19 | 36.84% |
| orb_only | 1.5%SL/3.0%TP(2:1) | +1.61% | 1.47 | 13 | 46.15% |
| orb_only | 1.5%SL/4.5%TP(3:1) | +1.39% | 1.56 | 8 | 37.50% |
| rsi_reversion_only | 0.5%SL/1.0%TP(2:1) | -0.33% | 0.43 | 4 | 25.00% |
| rsi_reversion_only | 0.5%SL/1.5%TP(3:1) | +0.23% | 1.23 | 8 | 37.50% |
| rsi_reversion_only | 1.0%SL/2.0%TP(2:1) | -0.31% | 0.80 | 6 | 33.33% |
| rsi_reversion_only | 1.0%SL/3.0%TP(3:1) | -1.40% | 0.00 | 4 | 0.00% |
| rsi_reversion_only | 1.5%SL/3.0%TP(2:1) | -0.64% | 0.57 | 4 | 25.00% |
| rsi_reversion_only | 1.5%SL/4.5%TP(3:1) | -0.99% | 0.00 | 2 | 0.00% |
| bb_squeeze_only | 0.5%SL/1.0%TP(2:1) | -1.14% | 0.47 | 15 | 26.67% |
| bb_squeeze_only | 0.5%SL/1.5%TP(3:1) | -0.31% | 0.90 | 23 | 30.43% |
| bb_squeeze_only | 1.0%SL/2.0%TP(2:1) | +0.34% | 1.14 | 12 | 41.67% |
| bb_squeeze_only | 1.0%SL/3.0%TP(3:1) | **+2.37%** | **3.27** | 7 | 57.14% |
| bb_squeeze_only | 1.5%SL/3.0%TP(2:1) | **+2.41%** | **3.43** | 6 | 66.67% |
| bb_squeeze_only | 1.5%SL/4.5%TP(3:1) | -0.72% | 0.65 | 5 | 20.00% |

### QQQ

| Strategy | Combo | Return | PF | Trades | Win Rate |
|---|---|---|---|---|---|
| mean_reversion_only | 0.5%SL/1.0%TP(2:1) | -2.77% | 0.65 | 60 | 33.33% |
| mean_reversion_only | 0.5%SL/1.5%TP(3:1) | -1.82% | 0.75 | 49 | 26.53% |
| mean_reversion_only | 1.0%SL/2.0%TP(2:1) | -1.28% | 0.86 | 40 | 35.00% |
| mean_reversion_only | 1.0%SL/3.0%TP(3:1) | +1.40% | 1.17 | 34 | 32.35% |
| mean_reversion_only | 1.5%SL/3.0%TP(2:1) | -1.37% | 0.79 | 19 | 31.58% |
| mean_reversion_only | 1.5%SL/4.5%TP(3:1) | +1.32% | 1.20 | 19 | 31.58% |
| vwap_reversion_only | 0.5%SL/1.0%TP(2:1) | -0.44% | 0.77 | 16 | 37.50% |
| vwap_reversion_only | 0.5%SL/1.5%TP(3:1) | +0.03% | 1.03 | 15 | 33.33% |
| vwap_reversion_only | 1.0%SL/2.0%TP(2:1) | +0.52% | 1.20 | 14 | 42.86% |
| vwap_reversion_only | 1.0%SL/3.0%TP(3:1) | +0.26% | 1.09 | 13 | 30.77% |
| vwap_reversion_only | 1.5%SL/3.0%TP(2:1) | -0.10% | 0.98 | 11 | 36.36% |
| vwap_reversion_only | 1.5%SL/4.5%TP(3:1) | +1.70% | 1.49 | 11 | 36.36% |
| orb_only | 0.5%SL/1.0%TP(2:1) | -2.76% | 0.68 | 67 | 34.33% |
| orb_only | 0.5%SL/1.5%TP(3:1) | -1.95% | 0.78 | 62 | 27.42% |
| orb_only | 1.0%SL/2.0%TP(2:1) | -2.57% | 0.78 | 49 | 32.65% |
| orb_only | 1.0%SL/3.0%TP(3:1) | -0.50% | 0.95 | 36 | 27.78% |
| orb_only | 1.5%SL/3.0%TP(2:1) | -1.57% | 0.86 | 33 | 33.33% |
| orb_only | 1.5%SL/4.5%TP(3:1) | -0.87% | 0.92 | 27 | 25.93% |
| rsi_reversion_only | 0.5%SL/1.0%TP(2:1) | -0.77% | 0.58 | 13 | 30.77% |
| rsi_reversion_only | 0.5%SL/1.5%TP(3:1) | -0.58% | 0.41 | 6 | 16.67% |
| rsi_reversion_only | 1.0%SL/2.0%TP(2:1) | -0.45% | 0.80 | 9 | 33.33% |
| rsi_reversion_only | 1.0%SL/3.0%TP(3:1) | -0.40% | 0.82 | 8 | 25.00% |
| rsi_reversion_only | 1.5%SL/3.0%TP(2:1) | -1.13% | 0.43 | 5 | 20.00% |
| rsi_reversion_only | 1.5%SL/4.5%TP(3:1) | -0.69% | 0.65 | 5 | 20.00% |
| bb_squeeze_only | 0.5%SL/1.0%TP(2:1) | -0.23% | 0.92 | 24 | 41.67% |
| bb_squeeze_only | 0.5%SL/1.5%TP(3:1) | -2.44% | 0.65 | 46 | 23.91% |
| bb_squeeze_only | 1.0%SL/2.0%TP(2:1) | -0.21% | 0.96 | 24 | 37.50% |
| bb_squeeze_only | 1.0%SL/3.0%TP(3:1) | +1.42% | 1.23 | 27 | 33.33% |
| bb_squeeze_only | 1.5%SL/3.0%TP(2:1) | +1.40% | 1.18 | 27 | 40.74% |
| bb_squeeze_only | 1.5%SL/4.5%TP(3:1) | **+3.15%** | **1.51** | 19 | 36.84% |

### IWM

| Strategy | Combo | Return | PF | Trades | Win Rate |
|---|---|---|---|---|---|
| mean_reversion_only | 0.5%SL/1.0%TP(2:1) | -0.13% | 0.94 | 19 | 42.11% |
| mean_reversion_only | 0.5%SL/1.5%TP(3:1) | +1.08% | 1.50 | 19 | 42.11% |
| mean_reversion_only | 1.0%SL/2.0%TP(2:1) | **+2.38%** | **2.12** | 14 | 57.14% |
| mean_reversion_only | 1.0%SL/3.0%TP(3:1) | +0.63% | 1.23 | 12 | 33.33% |
| mean_reversion_only | 1.5%SL/3.0%TP(2:1) | +0.11% | 1.03 | 16 | 37.50% |
| mean_reversion_only | 1.5%SL/4.5%TP(3:1) | +0.49% | 1.09 | 17 | 29.41% |
| vwap_reversion_only | 0.5%SL/1.0%TP(2:1) | +0.44% | 1.19 | 23 | 47.83% |
| vwap_reversion_only | 0.5%SL/1.5%TP(3:1) | +1.09% | 1.42 | 22 | 40.91% |
| vwap_reversion_only | 1.0%SL/2.0%TP(2:1) | +1.84% | 1.32 | 31 | 45.16% |
| vwap_reversion_only | 1.0%SL/3.0%TP(3:1) | +1.44% | 1.23 | 27 | 33.33% |
| vwap_reversion_only | 1.5%SL/3.0%TP(2:1) | **+2.51%** | **1.71** | 14 | 50.00% |
| vwap_reversion_only | 1.5%SL/4.5%TP(3:1) | -1.70% | 0.43 | 7 | 14.29% |
| orb_only | 0.5%SL/1.0%TP(2:1) | -3.21% | 0.63 | 67 | 32.84% |
| orb_only | 0.5%SL/1.5%TP(3:1) | -0.83% | 0.86 | 44 | 29.55% |
| orb_only | 1.0%SL/2.0%TP(2:1) | -2.79% | 0.67 | 34 | 29.41% |
| orb_only | 1.0%SL/3.0%TP(3:1) | -1.86% | 0.79 | 33 | 24.24% |
| orb_only | 1.5%SL/3.0%TP(2:1) | -1.80% | 0.81 | 28 | 32.14% |
| orb_only | 1.5%SL/4.5%TP(3:1) | -2.46% | 0.73 | 23 | 21.74% |
| rsi_reversion_only | 0.5%SL/1.0%TP(2:1) | -0.50% | 0.72 | 14 | 35.71% |
| rsi_reversion_only | 0.5%SL/1.5%TP(3:1) | +0.84% | 1.72 | 11 | 45.45% |
| rsi_reversion_only | 1.0%SL/2.0%TP(2:1) | +1.18% | 2.13 | 7 | 57.14% |
| rsi_reversion_only | 1.0%SL/3.0%TP(3:1) | -1.22% | 0.41 | 7 | 14.29% |
| rsi_reversion_only | 1.5%SL/3.0%TP(2:1) | +0.56% | 1.28 | 7 | 42.86% |
| rsi_reversion_only | 1.5%SL/4.5%TP(3:1) | +0.30% | 1.30 | 3 | 33.33% |
| bb_squeeze_only | 0.5%SL/1.0%TP(2:1) | -1.36% | 0.67 | 32 | 34.38% |
| bb_squeeze_only | 0.5%SL/1.5%TP(3:1) | -3.02% | 0.51 | 40 | 20.00% |
| bb_squeeze_only | 1.0%SL/2.0%TP(2:1) | -2.49% | 0.64 | 28 | 28.57% |
| bb_squeeze_only | 1.0%SL/3.0%TP(3:1) | -1.32% | 0.82 | 28 | 25.00% |
| bb_squeeze_only | 1.5%SL/3.0%TP(2:1) | -1.01% | 0.85 | 21 | 33.33% |
| bb_squeeze_only | 1.5%SL/4.5%TP(3:1) | -2.87% | 0.48 | 13 | 15.38% |

### TSLA

| Strategy | Combo | Return | PF | Trades | Win Rate |
|---|---|---|---|---|---|
| mean_reversion_only | 0.5%SL/1.0%TP(2:1) | -1.86% | 0.40 | 21 | 23.81% |
| mean_reversion_only | 0.5%SL/1.5%TP(3:1) | -4.00% | 0.44 | 45 | 17.78% |
| mean_reversion_only | 1.0%SL/2.0%TP(2:1) | -4.44% | 0.38 | 26 | 19.23% |
| mean_reversion_only | 1.0%SL/3.0%TP(3:1) | -4.39% | 0.57 | 37 | 18.92% |
| mean_reversion_only | 1.5%SL/3.0%TP(2:1) | -1.01% | 0.85 | 21 | 33.33% |
| mean_reversion_only | 1.5%SL/4.5%TP(3:1) | -3.23% | 0.61 | 21 | 19.05% |
| vwap_reversion_only | 0.5%SL/1.0%TP(2:1) | -2.50% | 0.52 | 38 | 28.95% |
| vwap_reversion_only | 0.5%SL/1.5%TP(3:1) | -2.07% | 0.63 | 38 | 23.68% |
| vwap_reversion_only | 1.0%SL/2.0%TP(2:1) | -0.24% | 0.95 | 24 | 37.50% |
| vwap_reversion_only | 1.0%SL/3.0%TP(3:1) | +1.61% | 1.31 | 23 | 34.78% |
| vwap_reversion_only | 1.5%SL/3.0%TP(2:1) | +1.70% | 1.29 | 21 | 42.86% |
| vwap_reversion_only | 1.5%SL/4.5%TP(3:1) | +0.81% | 1.12 | 20 | 30.00% |
| orb_only | 0.5%SL/1.0%TP(2:1) | -4.46% | 0.76 | 151 | 37.09% |
| orb_only | 0.5%SL/1.5%TP(3:1) | -2.61% | 0.88 | 163 | 30.06% |
| orb_only | 1.0%SL/2.0%TP(2:1) | +1.75% | 1.10 | 86 | 40.70% |
| orb_only | 1.0%SL/3.0%TP(3:1) | **+5.90%** | 1.37 | 70 | 35.71% |
| orb_only | 1.5%SL/3.0%TP(2:1) | **+5.28%** | 1.28 | 63 | 42.86% |
| orb_only | 1.5%SL/4.5%TP(3:1) | -3.69% | 0.76 | 40 | 22.50% |
| rsi_reversion_only | 0.5%SL/1.0%TP(2:1) | -3.76% | 0.37 | 40 | 22.50% |
| rsi_reversion_only | 0.5%SL/1.5%TP(3:1) | -3.62% | 0.43 | 40 | 17.50% |
| rsi_reversion_only | 1.0%SL/2.0%TP(2:1) | -1.11% | 0.60 | 11 | 27.27% |
| rsi_reversion_only | 1.0%SL/3.0%TP(3:1) | -0.22% | 0.92 | 11 | 27.27% |
| rsi_reversion_only | 1.5%SL/3.0%TP(2:1) | +0.78% | 1.22 | 12 | 41.67% |
| rsi_reversion_only | 1.5%SL/4.5%TP(3:1) | -3.51% | 0.53 | 18 | 16.67% |
| bb_squeeze_only | 0.5%SL/1.0%TP(2:1) | -0.34% | 0.89 | 27 | 40.74% |
| bb_squeeze_only | 0.5%SL/1.5%TP(3:1) | -2.56% | 0.70 | 59 | 25.42% |
| bb_squeeze_only | 1.0%SL/2.0%TP(2:1) | -1.90% | 0.77 | 34 | 32.35% |
| bb_squeeze_only | 1.0%SL/3.0%TP(3:1) | +0.12% | 1.05 | 10 | 30.00% |
| bb_squeeze_only | 1.5%SL/3.0%TP(2:1) | -1.81% | 0.88 | 47 | 34.04% |
| bb_squeeze_only | 1.5%SL/4.5%TP(3:1) | +2.24% | 1.23 | 28 | 32.14% |

### GOOGL

| Strategy | Combo | Return | PF | Trades | Win Rate |
|---|---|---|---|---|---|
| mean_reversion_only | 0.5%SL/1.0%TP(2:1) | -1.57% | 0.69 | 40 | 35.00% |
| mean_reversion_only | 0.5%SL/1.5%TP(3:1) | -1.28% | 0.77 | 40 | 27.50% |
| mean_reversion_only | 1.0%SL/2.0%TP(2:1) | -2.19% | 0.82 | 53 | 33.96% |
| mean_reversion_only | 1.0%SL/3.0%TP(3:1) | -2.96% | 0.77 | 50 | 24.00% |
| mean_reversion_only | 1.5%SL/3.0%TP(2:1) | -2.00% | 0.86 | 42 | 33.33% |
| mean_reversion_only | 1.5%SL/4.5%TP(3:1) | -0.96% | 0.93 | 38 | 26.32% |
| vwap_reversion_only | 0.5%SL/1.0%TP(2:1) | -1.86% | 0.55 | 30 | 30.00% |
| vwap_reversion_only | 0.5%SL/1.5%TP(3:1) | -3.80% | 0.53 | 53 | 20.75% |
| vwap_reversion_only | 1.0%SL/2.0%TP(2:1) | -2.25% | 0.73 | 35 | 31.43% |
| vwap_reversion_only | 1.0%SL/3.0%TP(3:1) | -3.26% | 0.72 | 44 | 22.73% |
| vwap_reversion_only | 1.5%SL/3.0%TP(2:1) | -6.06% | 0.63 | 45 | 26.67% |
| vwap_reversion_only | 1.5%SL/4.5%TP(3:1) | -6.95% | 0.53 | 36 | 16.67% |
| orb_only | 0.5%SL/1.0%TP(2:1) | -4.04% | 0.70 | 110 | 35.45% |
| orb_only | 0.5%SL/1.5%TP(3:1) | -4.07% | 0.69 | 91 | 25.27% |
| orb_only | 1.0%SL/2.0%TP(2:1) | -4.54% | 0.68 | 60 | 30.00% |
| orb_only | 1.0%SL/3.0%TP(3:1) | +1.21% | 1.13 | 38 | 31.58% |
| orb_only | 1.5%SL/3.0%TP(2:1) | +1.50% | 1.14 | 35 | 40.00% |
| orb_only | 1.5%SL/4.5%TP(3:1) | +0.75% | 1.07 | 31 | 29.03% |
| rsi_reversion_only | 0.5%SL/1.0%TP(2:1) | -0.83% | 0.64 | 18 | 33.33% |
| rsi_reversion_only | 0.5%SL/1.5%TP(3:1) | -0.72% | 0.77 | 22 | 27.27% |
| rsi_reversion_only | 1.0%SL/2.0%TP(2:1) | -3.53% | 0.79 | 75 | 33.33% |
| rsi_reversion_only | 1.0%SL/3.0%TP(3:1) | -2.70% | 0.81 | 56 | 25.00% |
| rsi_reversion_only | 1.5%SL/3.0%TP(2:1) | -2.67% | 0.83 | 46 | 32.61% |
| rsi_reversion_only | 1.5%SL/4.5%TP(3:1) | -1.49% | 0.90 | 39 | 25.64% |
| bb_squeeze_only | 0.5%SL/1.0%TP(2:1) | -2.57% | 0.66 | 59 | 33.90% |
| bb_squeeze_only | 0.5%SL/1.5%TP(3:1) | -2.59% | 0.67 | 53 | 24.53% |
| bb_squeeze_only | 1.0%SL/2.0%TP(2:1) | -3.20% | 0.69 | 43 | 30.23% |
| bb_squeeze_only | 1.0%SL/3.0%TP(3:1) | -2.83% | 0.64 | 29 | 20.69% |
| bb_squeeze_only | 1.5%SL/3.0%TP(2:1) | -2.13% | 0.76 | 26 | 30.77% |
| bb_squeeze_only | 1.5%SL/4.5%TP(3:1) | -0.07% | 0.99 | 29 | 27.59% |

## Which combo looks most promising?

Filtering for "meaningful and clearly good" cells (return > 0, PF > 1.2,
trades >= 10 — a much higher bar than the prior 5%-stop test's 1-2 trades)
gives **22 of 150 cells**, distributed across combos as:

| Combo | Qualifying cells (of 25) |
|---|---|
| 0.5%SL/1.0%TP(2:1) | 1 |
| 0.5%SL/1.5%TP(3:1) | 4 |
| 1.0%SL/2.0%TP(2:1) | 3 |
| **1.0%SL/3.0%TP(3:1)** | **6** |
| **1.5%SL/3.0%TP(2:1)** | **5** |
| 1.5%SL/4.5%TP(3:1) | 3 |

**1.0%SL/3.0%TP(3:1) and 1.5%SL/3.0%TP(2:1) are the two most promising
combos** — they win on aggregate PF, % of positive cells, and count of
strong individual cells, while both keep trade counts well above the
threshold that sank the 5%-stop test (avg 23-26 trades/cell here vs.
~1 trade/cell for the 5%-stop test).

Top individual cells by return (all with trades >= 10, satisfying the
"not just noise" bar):

1. **TSLA / orb_only / 1.0%SL/3.0%TP(3:1): +5.90%, PF 1.37, 70 trades, 35.7% win**
2. TSLA / orb_only / 1.5%SL/3.0%TP(2:1): +5.28%, PF 1.28, 63 trades, 42.9% win
3. QQQ / bb_squeeze_only / 1.5%SL/4.5%TP(3:1): +3.15%, PF 1.51, 19 trades, 36.8% win
4. IWM / vwap_reversion_only / 1.5%SL/3.0%TP(2:1): +2.51%, PF 1.71, 14 trades, 50.0% win
5. IWM / mean_reversion_only / 1.0%SL/2.0%TP(2:1): +2.38%, PF 2.12, 14 trades, 57.1% win

Caveats, still raw numbers:

- **Tight 0.5% stops are consistently the worst** — they get whipsawed by
  normal 15-min bar noise before a real move develops (8-24% of cells
  positive, avg PF 0.73-0.88). Widening the stop to at least 1.0% is what
  turns most strategies from net-negative to roughly breakeven-or-better.
- No single strategy or stop/TP combo works cleanly across every symbol.
  TSLA's `orb_only` is a standout with wider stops (1.0-1.5%), but the
  same wide stops make TSLA's `mean_reversion_only` worse, not better.
  GOOGL is negative on almost every combo/strategy pairing — the one
  partial exception is `orb_only` at 1.0-1.5% stops with 3.0-4.5% TP.
- IWM and SPY show their best results at the **2:1** ratio in several
  cells (IWM `mean_reversion_only` 1.0%/2.0%, IWM `vwap_reversion_only`
  1.5%/3.0%), while QQQ and TSLA's best cells lean **3:1**. There is no
  single stop/TP ratio that dominates across all 5 symbols.
- Even the best cells (14-70 trades over ~6 months OOS) are still modest
  sample sizes for a live trading decision; they are large enough to move
  past "1 trade = noise" but not large enough to be a fully validated edge.
