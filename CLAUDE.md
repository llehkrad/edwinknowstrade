# Trading Bot Project — Context & Build Plan

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
- Strategy: mean reversion and/or trend following (both are defined-risk —
  a hard stop caps loss, no active management needed while asleep).
  Exact parameters (MA period, std-dev thresholds, timeframe — 5min/15min
  candles) still to be finalized in Claude Code.
- Position sizing: ATR-based, same principle as the original doc (size so
  1 ATR move = fixed % of account equity; risk stays constant across
  instruments regardless of individual volatility).
- Correlation consideration: SPY/QQQ/IWM are generally MORE correlated with
  each other than the original doc's SPY/QQQ/BTC mix — may want a tighter
  same-direction exposure cap across the three, not a looser one.
- Data: confirm IBKR real-time market data subscription is active (Client
  Portal → Settings → Market Data Subscriptions) before building — without
  it, data defaults to 15-min delayed, which breaks any short-timeframe
  strategy. Use `reqHistoricalData` with `keepUpToDate=True` for live
  5-min/15-min bars (simpler than manually aggregating `reqRealTimeBars`
  5-second bars).
- File structure (extend, don't rebuild, in later phases):
  ```
  bot/strategies/mean_reversion.py
  bot/strategies/trend_following.py
  bot/risk_manager.py
  bot/portfolio.py
  bot/main.py
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

## Decisions still open (resolve in Claude Code or before)
- Exact strategy parameters for Phase 1 (candle timeframe, MA period,
  std-dev entry thresholds, stop-loss %).
- Risk appetite / account size, to calibrate position sizing.
- Fixed watchlist (SPY/QQQ/IWM only) vs. later screener/scanner approach
  for a wider universe — deferred, not needed for Phase 1.
- Confirm current Telegram vs Slack integration options for Cowork before
  finalizing the reporting layer (Slack is the safer default given
  operator already has it).

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
