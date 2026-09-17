# Trading Bot Project — Context & Build Plan

## Current status (as of 2026-09-18, latest) — pairs trading and momentum rotation both ruled out for QQQ
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
