# Fixed 5% Stop-Loss / 15% Take-Profit (3:1) — Out-of-Sample Validation

**Date:** 2026-09-24
**Branch:** bracket-tp-sl
**Script:** `backtest/validate_fixed_pct_exits.py`
**Full raw log:** `backtest_results/fixed_pct_validation_log.txt`

## What this tests

A FIXED 5% stop-loss + 3:1 take-profit ratio (i.e. 15% take-profit),
using `config.STOP_LOSS_MODE = 'fixed_pct'` (already implemented in
`bot/risk_manager.py` on this branch) instead of the ATR-based bracket
sizing already validated by `backtest/validate_bracket_exits.py`.

Fixed for every combo in this run (not swept):
- `config.STOP_LOSS_MODE = "fixed_pct"`
- `config.FIXED_STOP_LOSS_PCT = 0.05` (5% stop distance from entry)
- `config.TAKE_PROFIT_RATIO = 3.0` (=> 15% take-profit distance)

`STOP_LOSS_ATR_MULT` is irrelevant under `fixed_pct` mode and was dropped
from the grid; only each strategy's own entry parameters were searched.

Methodology: same in-sample (first half of 1yr 15-min data) / out-of-sample
(second half, never searched) per-symbol time split used throughout this
repo's validation scripts. Top-3 in-sample combos per symbol/strategy were
re-tested out-of-sample; only the best (#1) result per symbol/strategy is
shown below. **Per explicit operator instruction, this is raw
numbers only — no buy-and-hold comparison, no verdict labels.**

## Results (best in-sample combo, out-of-sample performance)

| Symbol | Strategy | OOS Return | OOS PF | Trades | Win Rate |
|---|---|---|---|---|---|
| SPY | mean_reversion_only | -1.57% | 0.00 | 1 | 0.00% |
| SPY | vwap_reversion_only | -1.57% | 0.00 | 1 | 0.00% |
| SPY | orb_only | -1.57% | 0.00 | 1 | 0.00% |
| SPY | rsi_reversion_only | -1.57% | 0.00 | 1 | 0.00% |
| SPY | bb_squeeze_only | -1.57% | 0.00 | 1 | 0.00% |
| QQQ | mean_reversion_only | -1.88% | 0.70 | 5 | 20.00% |
| QQQ | vwap_reversion_only | -1.88% | 0.70 | 5 | 20.00% |
| QQQ | orb_only | -0.34% | 0.93 | 4 | 25.00% |
| QQQ | rsi_reversion_only | -1.57% | 0.00 | 1 | 0.00% |
| QQQ | bb_squeeze_only | -0.34% | 0.93 | 4 | 25.00% |
| IWM | mean_reversion_only | -1.57% | 0.00 | 1 | 0.00% |
| IWM | vwap_reversion_only | **+2.81%** | **2.84** | 2 | 50.00% |
| IWM | orb_only | +1.22% | 1.40 | 3 | 33.33% |
| IWM | rsi_reversion_only | -1.55% | 0.00 | 1 | 0.00% |
| IWM | bb_squeeze_only | -0.03% | 0.00 | 0 | 0.00% |
| TSLA | mean_reversion_only | -10.63% | 0.28 | 11 | 9.09% |
| TSLA | vwap_reversion_only | -0.66% | 0.93 | 8 | 25.00% |
| TSLA | orb_only | -10.35% | 0.00 | 7 | 0.00% |
| TSLA | rsi_reversion_only | -4.57% | 0.00 | 3 | 0.00% |
| TSLA | bb_squeeze_only | -4.90% | 0.46 | 7 | 14.29% |
| GOOGL | mean_reversion_only | -3.40% | 0.56 | 6 | 16.67% |
| GOOGL | vwap_reversion_only | -9.22% | 0.32 | 10 | 10.00% |
| GOOGL | orb_only | -7.79% | 0.36 | 9 | 11.11% |
| GOOGL | rsi_reversion_only | -0.34% | 0.93 | 4 | 25.00% |
| GOOGL | bb_squeeze_only | -10.35% | 0.00 | 7 | 0.00% |

## Reading this

Only IWM's `vwap_reversion_only` (+2.81%, PF 2.84, 2 trades) and `orb_only`
(+1.22%, PF 1.40, 3 trades) came out positive out-of-sample — consistent
with this project's established pattern (IWM is the one instrument that's
shown a repeatable edge in prior validation work; SPY/QQQ/mega-cap singles
consistently don't). Both IWM positives here rest on a very small trade
count (2-3), too few to trust as a real edge rather than noise.

SPY is flat/negative across all 5 strategies with only 1 trade each — the
wide 5%/15% bracket rarely triggers before the out-of-sample window ends.
TSLA and GOOGL are both clearly negative across the board.

**Verdict: the fixed 5%-stop / 15%-take-profit bracket does not outperform
the ATR-based bracket or show a validated edge on any symbol/strategy
combo tested in this run.**

Config defaults in `config.py` were left untouched (`STOP_LOSS_MODE`
stays `'atr'` as the committed default) — the fixed-% mode is only set at
runtime inside `backtest/validate_fixed_pct_exits.py`, mirroring how
`validate_bracket_exits.py` applies its own grid overrides.
