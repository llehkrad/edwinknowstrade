# Trading Bot Project — Context & Build Plan

## Repository
Code lives at https://github.com/llehkrad/edwinknowstrade (`main` branch).
Local git identity for this repo: user.name "Edwin", user.email
darkhell85@gmail.com (repo-local config, not global).

## Current status (as of 2026-09-12) — paused, waiting on IBKR paper account
Phase 1 scaffolding, backtest harness, and tooling are built and pushed.
Work is paused here because the IBKR paper trading account needs a business
day to finish provisioning. Resume checklist below once it's ready.

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
- Paper trading account requested; IBKR said to allow until the next
  business day for it to provision. **This is the current blocker.**

## Resume checklist (once the paper account is ready)
1. Log into TWS with paper trading credentials (not live) — confirm the
   title bar says "Paper Trading". Verify API settings survived (Enable
   ActiveX/Socket Clients, Read-Only API unchecked, port 7497).
2. Run `python check_ibkr_connection.py` — confirms connectivity and that
   SPY/QQQ/IWM show Live (not delayed) data.
3. Run `python -m backtest.fetch_ibkr_data --duration "6 M"` to pull real
   historical bars (replaces the synthetic data in `data/historical/`). Must
   be run with `-m` (module form), not as a plain script path.
4. Re-run `python -m backtest.run_backtest` and
   `python -m backtest.optimize` on the real data — this result is the one
   that actually matters, unlike the synthetic-data run above.
5. Regenerate the dashboard with `python -m backtest.build_dashboard
   --real-data` (drops the synthetic-data warning banner).
6. Run `python -m backtest.run_monte_carlo` on the real `fills.csv` to see
   the range of possible drawdowns/returns from the same trade outcomes in
   a different order — not required, but worth checking before trusting a
   single backtest run's drawdown number.
7. Only after backtest results look reasonable: begin the 2+ week paper
   trading track record required before touching live keys (see "Required
   before going live" under Phase 1). Avoid the Client Portal "Paper Trading
   Account Reset" button once this clock starts — it wipes the track record.

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
  backtest/data.py
  backtest/fetch_ibkr_data.py
  backtest/generate_synthetic_data.py
  backtest/build_dashboard.py
  check_ibkr_connection.py
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

## Decisions still open (resolve once real backtest data is available)
- Exact strategy parameter VALUES (MA periods, std-dev entry thresholds,
  ADX threshold, stop-loss ATR multiple) — placeholders in `config.py` until
  `backtest/optimize.py` is re-run against real IBKR historical data (the
  synthetic-data grid search run on 2026-09-12 found parameters that overfit
  to the synthetic generator's artificial sine-wave drift; those results are
  meaningless and were discarded).
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
