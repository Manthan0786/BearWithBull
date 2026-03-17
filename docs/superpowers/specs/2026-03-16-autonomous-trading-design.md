## Autonomous Trading System — Design Spec (Modular Monolith)

### 1. Scope & Goals

- Build a production-grade, **single-user** autonomous trading system targeting **US equities (NYSE/NASDAQ, S&P 500 universe)** for a Canadian-based user trading via **IBKR**.
- Support **three strategies** running concurrently with **ticker exclusivity**:
  - `MomentumBreakout`
  - `StatMeanReversion`
  - `SentimentCatalyst`
- Enforce a **non-bypassable, multi-layer RiskManager** (position, portfolio, session) that gates every order.
- Provide a **professional dashboard UI** with real-time WebSocket updates for portfolio, risk state, backtests, and trade logs.
- Run primarily in **paper mode**, but support **live trading** with strict safety gates.

Non-goals for v1:
- Multi-tenant / multi-user SaaS.
- Non-US asset classes (no options, futures, FX).
- Sub-millisecond HFT; latency is important but secondary to correctness, risk, and observability.

---

### 2. High-Level Architecture

#### 2.1 Services (Docker Compose)

- `ib-gateway`:
  - Image: `ghcr.io/gnzsnz/ib-gateway:latest`.
  - Runs in **paper mode** by default on port **4002** (4001 reserved for live).
  - Exposes IBKR Trader Workstation API on TCP port (e.g. 7497) to the backend only.

- `backend`:
  - Python **FastAPI** app, fully async using `asyncio`.
  - Single process / modular monolith, responsible for:
    - REST API for configuration, logs, backtests.
    - WebSockets for portfolio, risk, strategies, alerts, backtests.
    - Background tasks: strategy scheduler, data pipeline, news poller, risk monitor, daily jobs.
    - IBKR connectivity and order execution via `ib_insync`.
    - Risk management and PortfolioState.

- `frontend`:
  - React + TypeScript + TailwindCSS SPA served behind Node or nginx.
  - Talks only to `backend` via HTTPS REST + WebSockets.

- `postgres`:
  - Primary relational store for:
    - Orders, positions, trades, signals, risk audit logs, OHLCV, alerts, backtests, config snapshots.

- `redis`:
  - In-memory cache and lightweight message bus:
    - Real-time bar and indicator caches.
    - Portfolio and risk snapshots.
    - Optional queues / pub-sub for signals and UI events.

All services are defined in `docker-compose.yml` with appropriate healthchecks and dependencies (e.g. backend waits for postgres and redis; backend depends on a healthy ib-gateway for live/paper trading).

#### 2.2 Backend Process Model

Single FastAPI app (`backend/main.py`) with:

- **Startup sequence**:
  1. Load environment variables from `.env` and configuration from `config.yaml`.
  2. Initialize logging (structured JSON logs with correlation IDs).
  3. Connect to PostgreSQL and run Alembic migrations (if enabled).
  4. Connect to Redis.
  5. Instantiate `IBKRClient` (wrapping `ib_insync.IB`) and establish connection to `ib-gateway`.
  6. Initialize `PortfolioState` by reconciling current IBKR positions and orders with the database:
     - Pull live positions and open orders from IBKR.
     - Compare to DB `positions` and `orders`.
     - Treat IBKR as **source of truth**, updating DB to match.
     - Ensure no new entries are generated for positions that are already open at IBKR.
  7. Instantiate `RiskManager`, `OrderExecutor`, `StrategyEngine`, `DataPipeline`, `NewsPoller`, `NotificationService`, `BacktestEngine`.
  8. Start background tasks:
     - Market calendar / market-hours scheduler.
     - Real-time data subscriptions and bar aggregation.
     - Indicator computations on bar close.
     - Strategy evaluation loops (5m/15m + news-driven).
     - Risk monitor and session metrics.
     - Daily jobs (VIX fetch, holiday cache update, daily OHLCV maintenance).

- **Shutdown sequence**:
  - Gracefully stop strategy loops (switch them to idle).
  - Cancel non-critical background tasks.
  - Attempt to keep active positions safe (existing stops remain at IBKR).
  - Close IBKR, Redis, and Postgres connections.

Failure policy:
- **Balanced** bias:
  - Core failures (IBKR connectivity, RiskManager, PortfolioState corruption) halt **new entries** and log CRITICAL alerts.
  - Non-core failures (e.g., news feed, metrics) log errors and may briefly degrade features but do **not** auto-halt trading.

---

### 3. Python Package Layout

Within `/backend`:

- `api/`
  - `routes.py` — FastAPI REST endpoints for config, trade log, backtests, etc.
  - `websocket.py` — WebSocket endpoints for portfolio, risk, alerts, strategies, backtests.

- `broker/`
  - `ibkr_client.py` — Connection management, rate-limited IBKR API wrapper.
  - `order_executor.py` — Order submission, OCA wiring, timeout & retry logic.

- `strategies/`
  - `base_strategy.py` — `BaseStrategy` ABC with the required interface.
  - `momentum_breakout.py` — MomentumBreakout implementation.
  - `stat_mean_reversion.py` — StatMeanReversion implementation.
  - `sentiment_catalyst.py` — SentimentCatalyst implementation.
  - `strategy_engine.py` — Strategy orchestration, scheduling, ticker-exclusivity enforcement.

- `risk/`
  - `risk_manager.py` — Central RiskManager implementing all position / portfolio / session rules.
  - `portfolio_state.py` — In-memory portfolio representation synchronized with IBKR and DB.

- `data/`
  - `data_pipeline.py` — Real-time data subscriptions, bar aggregation, Redis updates.
  - `historical.py` — Historical data loader from IBKR + yFinance.
  - `indicators.py` — `pandas-ta` wrapper, indicator computation and caching.

- `sentiment/`
  - `news_poller.py` — NewsAPI polling, deduplication, feed into Sentiment strategy.
  - `sentiment_scorer.py` — VADER scoring and classification.

- `notifications/`
  - `notification_service.py` — In-app, email (SendGrid/SMTP), optional Telegram.

- `backtester/`
  - `backtest_engine.py` — Shared backtest engine that reuses strategy logic and risk rules.

- `models/`
  - `database.py` — SQLAlchemy engine and session setup.
  - `models.py` — ORM models for all persistent entities.

- `config.py` — Typed loader for `.env` and `config.yaml`.
- `main.py` — FastAPI app factory and startup/shutdown events.

---

### 4. Data Model (PostgreSQL)

Core tables (simplified; exact columns may be extended in implementation):

- **`accounts`**
  - `id` (PK)
  - `ib_account_id`
  - `base_currency` (e.g., `CAD` or `USD`)
  - `created_at`

- **`positions`**
  - `id` (PK)
  - `account_id` (FK `accounts`)
  - `ticker`
  - `strategy_id` (e.g., `MOMENTUM_BREAKOUT`, `STAT_MEAN_REVERSION`, `SENTIMENT_CATALYST`)
  - `direction` (`LONG` / `SHORT`)
  - `quantity`
  - `entry_price`
  - `avg_price`
  - `entry_time`
  - `stop_price`
  - `target_price`
  - `atr_at_entry`
  - `status` (`OPEN` / `CLOSED`)
  - `exit_price`
  - `exit_time`
  - `exit_reason` (e.g., `STOP_HIT`, `TARGET_HIT`, `TIME_EXIT`, `EMERGENCY_STOP`)

- **`orders`**
  - `id` (PK)
  - `timestamp`
  - `ticker`
  - `strategy_id`
  - `direction`
  - `order_type` (`LMT`, `STP`, `STP_LMT`, `MKT`, `TRAIL`)
  - `quantity`
  - `limit_price`
  - `stop_price`
  - `status` (`NEW`, `PENDING`, `REJECTED`, `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`, `FAILED`)
  - `fill_price`
  - `fill_qty`
  - `slippage_bps`
  - `ibkr_order_id`
  - `oca_group_id`
  - `rejection_reason`
  - `time_in_force`

- **`trades`** (closed position summary)
  - `id` (PK)
  - `position_id` (FK)
  - `entry_order_id` (FK)
  - `exit_order_id` (FK)
  - `pnl_abs`
  - `pnl_pct`
  - `hold_time_sec`
  - `strategy_id`
  - `exit_reason`
  - `slippage_bps`

- **`signals`**
  - `id` (PK)
  - `timestamp`
  - `ticker`
  - `strategy_id`
  - `direction`
  - `timeframe` (e.g., `5m`, `15m`, `daily`, `news`)
  - `indicator_snapshot` (JSON: includes RSI, ATR, BBW, rolling highs/lows, etc.)
  - `reason_tags` (JSON list of strings summarizing why the signal fired)

- **`risk_audit`**
  - `id` (PK)
  - `timestamp`
  - `account_id`
  - `rule_name` (e.g., `MAX_POSITION_SIZE`, `DAILY_LOSS_LIMIT`, `CORRELATION_CHECK`)
  - `scope` (`POSITION`, `PORTFOLIO`, `SESSION`)
  - `status` (`PASS`, `FAIL`, `WARN`)
  - `details` (JSON; exact thresholds, values, portfolio snapshot)
  - `order_id` (nullable FK)
  - `position_id` (nullable FK)

- **`ohlcv_daily`**
  - `id` (PK)
  - `ticker`
  - `date`
  - `open`, `high`, `low`, `close`, `adj_close`, `volume`

- **`alerts`**
  - `id` (PK)
  - `timestamp`
  - `level` (`CRITICAL`, `HIGH`, `NORMAL`, `DAILY`)
  - `category` (`RISK`, `ORDER`, `STRATEGY`, `SYSTEM`)
  - `message`
  - `metadata` (JSON)
  - `acknowledged` (bool)

- **`backtest_runs`**
  - `id` (PK)
  - `strategy_id`
  - `start_date`, `end_date`
  - `starting_capital`
  - `created_at`
  - `status` (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`)
  - `summary_metrics` (JSON; max DD, Sharpe, Sortino, win rate, etc.)

- **`backtest_trades`**
  - `id` (PK)
  - `backtest_run_id` (FK)
  - `ticker`
  - `entry_time`, `exit_time`
  - `direction`
  - `entry_price`, `exit_price`
  - `pnl_abs`, `pnl_pct`
  - `hold_time_sec`
  - `indicator_snapshot_entry` (JSON)
  - `exit_reason`

- **`config_snapshots`** (optional)
  - `id` (PK)
  - `created_at`
  - `user` (optional text)
  - `config` (JSON representation of trading/risk/strategy settings)

---

### 5. Redis Usage & Real-Time State

Redis is used for:

- **Bar caches**
  - Keys like `bars:{ticker}:{timeframe}` storing recent N bars (e.g., last 500 `5m` bars) as serialized JSON.

- **Indicator caches**
  - `indicators:{ticker}:{timeframe}` with latest indicator values (SMA20, SMA50, SMA200, EMA, RSI(2/14), ATR(14), Bollinger Bands (20,2), BBW, MACD, Volume SMA(20), 20-day rolling highs/lows).
  - Values updated **on bar close** only.
  - TTL ~2× bar timeframe (e.g., 10 minutes for 5m bars).

- **Portfolio & session snapshots**
  - `portfolio_state:{account_id}` with NAV, cash, exposures, daily P&L, drawdown, open positions summary.
  - `session:{account_id}:metrics` for daily trade count, consecutive losses, etc.

- **WebSocket fan-out / pub-sub**
  - Channels like `ws:portfolio`, `ws:risk`, `ws:alerts`, `ws:strategies`, `ws:backtest:{run_id}` for pushing real-time updates to the FastAPI WebSocket layer.

Redis is **not** a long-term store; Postgres remains the authoritative history. On backend restart, Redis caches are rehydrated from Postgres and/or fresh market data.

---

### 6. Strategy Engine & Scheduling

#### 6.1 Base Strategy Interface

`BaseStrategy` defines:

- `generate_signals(market_data: MarketData) -> List[Signal]`
- `calculate_position_size(signal: Signal, portfolio: PortfolioState) -> float`
- `get_exit_conditions(position: Position) -> List[ExitCondition]`
- `on_fill(fill: OrderFill) -> None`
- `on_bar(bar: BarData) -> None`
- `backtest(start: date, end: date, data: DataFrame) -> BacktestResult`

Each concrete strategy:
- Encapsulates its own parameters (e.g. risk_per_trade, timeframes) but reads global ones from `config.yaml`.
- Logs every signal with a rich `indicator_snapshot` in the `signals` table.

#### 6.2 StrategyEngine

Responsibilities:

- Manage lifecycle and configuration of all strategies (enable/disable via `config.yaml` and UI).
- Schedule evaluation:
  - MomentumBreakout:
    - Evaluated every **5 minutes** during regular market hours.
    - Uses:
      - 20-day price momentum (% change).
      - Volume surge ratio (current volume vs 20-day average).
      - Relative strength vs SPY (20-day return spread).
    - Ranks the S&P 500 universe, considers only **top 20%** for entries.
  - StatMeanReversion:
    - Daily pre-filter at market open:
      - BBW percentile (bottom 15% of 90-day history).
      - VIX < configured threshold (default 25).
      - SPY not down more than 1.5% on the day.
    - Intraday checks every 15 minutes using Bollinger Bands, RSI(2), 200 SMA, and news filter.
  - SentimentCatalyst:
    - Reacts to `NewsEvent`s from `news_poller` instead of fixed bar schedules.
    - Applies VADER sentiment and confirmation filters before generating signals.

- Enforce **ticker exclusivity**:
  - Maintains a mapping `ticker -> active_strategy_id` for **open positions and pending entries**.
  - If a strategy generates a signal on a ticker already reserved or held by another strategy, the signal is rejected and logged (no order).

- Pipeline from signals to orders:
  - Strategy emits one or more `Signal` objects.
  - `StrategyEngine`:
    - Persists them in `signals`.
    - Passes them to `OrderExecutor` for position sizing, risk checks, and order submission.

---

### 7. Risk Management & PortfolioState

#### 7.1 PortfolioState

- Maintains real-time view of:
  - Open positions (ticker, qty, avg price, direction, strategy, sector).
  - Cash balance, margin, gross and net exposure.
  - Realized P&L (today and all-time), unrealized P&L.
  - NAV and intraday drawdown from market open.
  - Per-sector exposures (via GICS sectors from yFinance).
  - Correlation matrix for open positions based on 60-day returns.

- Data sources:
  - On startup: positions and account summary from IBKR (source of truth).
  - Live updates:
    - Fills and order status events from IBKR.
    - Price updates via `data_pipeline`.
    - Backfilled daily prices from `ohlcv_daily` for performance metrics.

PortfolioState exposes methods like:
- `nav()`, `cash_available()`
- `sector_exposure()`
- `correlation_with(ticker)`
- `daily_drawdown_pct()`

#### 7.2 RiskManager

Central authority invoked **before every order submission**:

- API:
  - `assess_order(order_request: OrderRequest, portfolio_state: PortfolioState) -> RiskDecision`
  - `RiskDecision` includes:
    - `allowed: bool`
    - `rule_results: List[RuleResult]` (each containing rule name, status, details)
    - `messages: List[str]`

- **Position-level rules**:
  - **Max position size**: default 5% of NAV per position (configurable).
  - **Max loss per trade**: 1% of NAV.
    - Uses ATR-based stop distance. If `qty * stop_distance` would exceed 1% NAV, position size is reduced until within limit; if min size still violates, order rejected.
  - **Mandatory stop-loss**: entry orders must be paired with a stop (OCA group). If the order request does not include a stop, it is rejected.
  - **No averaging down**: if an existing position is in loss, any order that increases size is rejected.
  - **No re-entry same day after stop-out**: track day-level flags per ticker; reject orders violating this.

- **Portfolio-level rules**:
  - **Minimum cash reserve**: at least 20% of NAV remains in cash after proposed trade.
  - **Max sector concentration**: no more than 25% of NAV in any single GICS sector.
  - **Max simultaneous open positions**: 10 (configurable).
  - **Max correlated positions**: if new position’s 60-day returns correlation with any existing open position exceeds 0.85, reject.
  - **Max positions per strategy**: no more than 3 positions per strategy.

- **Session-level rules**:
  - **Daily loss limit**: if intraday drawdown from opening NAV > 3%, immediately:
    - Halt new entries.
    - Optionally cancel all open orders.
    - Emit CRITICAL alerts.
  - **Max daily trade count**: 20 round-trips; additional trades rejected.
  - **Consecutive loss circuit breaker**: after 4 consecutive losing trades:
    - Pause all strategies for 120 minutes.
    - Notify via HIGH-priority alerts.
  - **No overnight positions** (by default):
    - 15 minutes before market close: force-close all intraday positions via market orders unless `allow_overnight` is enabled in config.

- Logging & observability:
  - Every rule evaluation (pass or fail) writes an entry in `risk_audit`.
  - Emits WebSocket events when overall risk state changes (e.g., rule breaching, circuit breaker triggers, daily loss limit hit).

---

### 8. Order Execution & IBKR Integration

#### 8.1 IBKRClient (`ibkr_client.py`)

- Wraps `ib_insync.IB`:
  - Manages IB Gateway connectivity (host/port from `.env`).
  - Applies **global rate limiting** to all IBKR API calls:
    - Historical data pacing (~50 req/s but slower for safety).
    - Low-frequency endpoints (e.g., account summary) limited to ~1 req/10s.
  - Auto-reconnect with exponential backoff (up to 5 retries).
  - Provides async methods:
    - `get_account_summary()`, `get_positions()`, `get_open_orders()`
    - `place_order(contract, order)`, `cancel_order(order_id)`
    - `request_historical_data(...)`
    - `subscribe_realtime_bars(ticker, ...)`
    - `get_market_snapshot(ticker)` → best bid/ask/last.

- All async operations are wrapped in `asyncio.wait_for` to avoid indefinite waits.

#### 8.2 OrderExecutor (`order_executor.py`)

Pipeline for a new trade:

1. Receive `Signal` from `StrategyEngine`.
2. Compute position size via `strategy.calculate_position_size(signal, portfolio_state)` (ATR-based, risk_per_trade_pct, possibly halved for SentimentCatalyst).
3. Construct `OrderRequest` struct containing:
   - Strategy, ticker, side (buy/sell/short/cover), target quantity, stop distance (ATR multiples), suggested limit price.
4. Pass `OrderRequest` to `RiskManager.assess_order`.
   - If rejected: log to `risk_audit`, create `HIGH`-priority alert, do **not** call IBKR.
5. Request current bid/ask via `IBKRClient.get_market_snapshot`.
6. Submit limit entry order at mid-price `(bid + ask) / 2`:
   - Never use market orders for entries.
7. Create stop-loss order with stop price at the configured ATR multiple from entry and link via OCA group.
8. Optionally create profit target order (STP LMT) in same OCA group depending on strategy’s exit rules.
9. Track the order with a **45-second timeout**:
   - If unfilled after 45s:
     - Check if mid-price moved > 0.3% from original mid.
     - If yes → cancel the entry (and associated OCA stop/target), mark as aborted.
     - If partially filled → keep filled quantity, cancel remaining size, adjust stop order quantity accordingly.

Error handling:
- On IB error:
  - Log error code and message.
  - Retry **once** after 3 seconds.
  - On second failure:
    - Abort and mark order as FAILED.
    - Emit CRITICAL or HIGH alert depending on context.
- Specific codes 201, 202, 110, 103 are mapped to human-readable reasons in `orders.rejection_reason`.

Order types:
- `LMT` for all entries.
- `STP` for stop-loss.
- `STP LMT` for profit targets.
- `MKT` for:
  - Stop-triggered exits (if implemented as a marketable order).
  - EOD forced closes.
  - Emergency stop.
- `TRAIL` for trailing stops when the position reaches the configured ATR profit threshold.

All orders are persisted in `orders` with full lifecycle status, and relevant events are broadcast onto WebSockets and into the `alerts` stream.

---

### 9. Data Pipeline & Indicators

#### 9.1 Real-Time Market Data (`data_pipeline.py`)

- Subscribes to **5-second bars** for all S&P 500 tickers, subject to IBKR subscription limits:
  - Prioritize:
    - Tickers with open positions.
    - Tickers in the current day’s candidate universe for MomentumBreakout/StatMeanReversion.
  - Rotate less active tickers to stay under IB limits.

- Aggregates 5-second bars into:
  - 1m, 5m, 15m bars for strategies.
  - Writes these aggregated bars to Redis (`bars:{ticker}:{timeframe}`) and optionally to Postgres for auditing/backtesting if needed.

- Subscribes to **Level 1** data (bid/ask/last) per ticker for pricing and P&L.

- Handles IBKR disconnects:
  - Detects connection loss.
  - Attempts up to 5 reconnects with backoff.
  - On persistent failure:
    - Halts new entries (via RiskManager/session-level state).
    - Emits CRITICAL alerts.

#### 9.2 Historical Data (`historical.py`)

- On initial startup or scheduled runs:
  - For each watchlist ticker:
    - Fetch last 252 trading days of daily OHLCV via IBKR historical API first.
    - Respect IBKR pacing limits.
    - On rate-limit error or failure, fallback to yFinance.
  - Upsert into `ohlcv_daily`.

- Daily maintenance:
  - At 6:00am ET on trading days:
    - Fetch the latest daily bar for each ticker and update `ohlcv_daily`.

#### 9.3 Indicator Engine (`indicators.py`)

- Uses `pandas-ta` for:
  - SMA(20, 50, 200), EMA(9, 21).
  - RSI(2, 14).
  - ATR(14).
  - Bollinger Bands(20, 2), BBW.
  - MACD(12, 26, 9).
  - Volume SMA(20).
  - 20-day rolling highs/lows.

- Indicators are recomputed **only on bar close** for each timeframe.
- Computed values for latest bar stored in Redis under `indicators:{ticker}:{timeframe}`.
- Exposes helper:
  - `get_indicator_snapshot(ticker, timeframe) -> IndicatorSnapshot` which is used by strategies to:
    - Evaluate entry/exit conditions.
    - Capture values into `signals.indicator_snapshot`.

---

### 10. Sentiment & News

#### 10.1 News Poller (`news_poller.py`)

- Every 60 seconds during market hours:
  - Queries **NewsAPI** using:
    - Ticker symbols and potentially company names.
    - Filters for US equity news.
  - Filters articles:
    - Only consider articles with `published_at` within the last **30 minutes**.
    - Deduplicate by article ID or URL hash; skip if already processed.
  - For each relevant article:
    - Creates a `NewsEvent` with ticker(s), headline, short text, timestamp, and raw metadata.

- Persistence:
  - Optionally log raw articles to a `news_articles` table (implementation detail).
  - Always log actionable sentiment events that lead to trades.

#### 10.2 Sentiment Scoring (`sentiment_scorer.py`)

- Uses VADER `SentimentIntensityAnalyzer`.
- Input: headline + first sentence of article body.
- Output:
  - `compound` score.
  - `label`:
    - `STRONG_POSITIVE` if `compound > 0.70`.
    - `STRONG_NEGATIVE` if `compound < -0.70`.
    - `IGNORE` otherwise.

Sentiment threshold (default 0.70 magnitude) is configurable via `config.yaml`.

#### 10.3 SentimentCatalyst Strategy

- On receiving `NewsEvent` with strong sentiment:
  - Filters:
    - Price move from previous close < 2.5%.
    - Volume in last 15 minutes > 2× 15-minute average.
    - No conflicting news (opposite sentiment) within last 10 minutes.
  - Position sizing:
    - 50% of normal ATR-based size (higher uncertainty).
    - Enforces max **2 open SentimentCatalyst positions**.
  - Exit rules:
    - Hard time exit at **90 minutes** after entry.
    - Stop at 1.5× ATR.
    - Profit target at 2× ATR.

---

### 11. Frontend UI Design (React + TS + Tailwind)

Shared characteristics:
- Dark, terminal-inspired theme.
- Layout optimized for 1440px+ desktop.
- All real-time data via WebSockets; no polling for live panels.
- Dollar values shown in **USD**, with **CAD mirror** when account currency is CAD.

#### 11.1 Overview Page

- Top bar:
  - Portfolio NAV (live).
  - Cash balance.
  - Daily P&L ($ and %).
  - All-time P&L.
  - Win rate (last 30 days).
- Equity curve chart:
  - Uses Recharts `LineChart`.
  - Plots daily portfolio value vs SPY % change for benchmark comparison.
- Active positions table:
  - Columns: `Ticker`, `Strategy`, `Direction`, `Entry Price`, `Current Price`, `Unrealized P&L`, `Stop Price`, `Distance to Stop`, `Hold Time`, `ATR`.
- Today’s closed trades table:
  - Columns: `Ticker`, `Strategy`, `Entry`, `Exit`, `P&L`, `P&L %`, `Hold Time`, `Exit Reason`.

#### 11.2 Strategy Control Panel

- For each strategy:
  - Toggle switch (enabled/disabled).
  - Live stats: `Total trades`, `Win rate`, `Avg win`, `Avg loss`, `Profit factor`, `Sharpe (30d)`, `Avg hold time`.
- Config controls:
  - Sliders/inputs for:
    - `Max position size %`.
    - `Daily loss limit %`.
    - `Max positions`.
    - `Risk per trade %` per strategy.
    - `Allow overnight` (toggle).
  - Save button:
    - Calls backend to update config (validated, persisted).
    - Triggers a config_snapshot entry.
- **Emergency Stop button**:
  - Prominent red button.
  - On click:
    - Confirmation modal with explicit warning.
    - On confirm:
      - Calls dedicated backend endpoint that:
        - Talks directly to `IBKRClient`.
        - Cancels all open orders.
        - Submits `MKT` orders to close all positions.
        - Sets system state to HALTED.
      - Bypasses StrategyEngine and RiskManager (for reliability), but still logs and emits alerts.

#### 11.3 Trade Log Page

- Filterable/sortable table based on `trades`:
  - Columns: `Date`, `Ticker`, `Strategy`, `Direction`, `Entry`, `Exit`, `P&L`, `P&L %`, `Hold Time`, `Exit Reason`, `Slippage (bps)`.
- Filters:
  - Date range.
  - Strategy.
  - Ticker.
  - Direction.
  - Exit reason.
- Export:
  - “Export CSV” button that requests CSV from backend.

#### 11.4 Backtester Page

- Inputs:
  - Strategy selector.
  - Date range.
  - Starting capital.
- Execution:
  - Calls `/backtest` endpoint, which returns a `run_id`.
  - Subscribes to `/ws/backtest/{run_id}` for updates and completion.
- Results:
  - Equity curve chart via Recharts.
  - Metrics: Max drawdown, Sharpe, Sortino, win rate, profit factor, total return %, average trade P&L, best/worst trade, longest streaks.
  - Trades table: all trades with associated signal details.

#### 11.5 Risk Monitor Page

- Real-time panel of each risk rule and status:
  - Visual indicators (green/amber/red) per rule.
- Daily loss gauge:
  - Progress bar from 0 to the configured daily loss limit.
- Sector exposure:
  - Pie chart (Recharts) by sector.
- Correlation heatmap:
  - Matrix of open positions colored by correlation coefficient.
- Alert feed:
  - Timestamped list of risk events, fills, stops, circuit breakers, system alerts.
- Trading status banner:
  - Always-visible banner showing `ACTIVE`, `HALTED`, `PAPER MODE`.

---

### 12. Notifications & Alerts

#### 12.1 NotificationService

- Channels:
  - **In-app**: toast + audio cues (different tones for fills, warnings, emergencies).
  - **Email** (SendGrid/SMTP):
    - Daily summary at 4:15pm ET.
    - Stop triggered.
    - Daily halt.
    - Circuit breaker firing.
    - IB Gateway disconnection > 30 seconds.
  - **Telegram** (optional):
    - Enabled when `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set.

- Priority mapping:
  - **CRITICAL**: all channels (immediate).
  - **HIGH**: in-app + email.
  - **NORMAL**: in-app only.
  - **DAILY**: email summary only.

- Integrates with `alerts` table and broadcasts notifications to frontend via WebSockets.

---

### 13. Configuration, Environment & Safety

#### 13.1 Environment Variables (`.env`)

- `IB_GATEWAY_HOST=localhost`
- `IB_GATEWAY_PORT=4002`  # 4002=paper, 4001=live
- `IB_ACCOUNT_ID=...`
- `PAPER_TRADING=true`
- `DATABASE_URL=postgresql://...`
- `REDIS_URL=redis://redis:6379`
- `NEWSAPI_KEY=...`
- `SENDGRID_API_KEY=...`
- `ALERT_EMAIL=...`
- `TELEGRAM_BOT_TOKEN=` (optional)
- `TELEGRAM_CHAT_ID=` (optional)
- `ACCOUNT_CURRENCY=CAD` (default `USD`)

An `.env.example` file mirrors these keys without secrets.

#### 13.2 Config File (`config.yaml`)

- Trading and risk parameters:
  - `trading.paper_mode`
  - `trading.allow_overnight`
  - `trading.max_positions`
  - `trading.cash_reserve_pct`
  - `trading.daily_loss_limit_pct`
  - `trading.max_daily_trades`
  - `trading.consecutive_loss_circuit_breaker`
  - `trading.circuit_breaker_pause_minutes`
- Strategy flags and parameters:
  - Per-strategy `enabled`, `risk_per_trade_pct`, `max_concurrent`, and strategy-specific thresholds.
- Watchlist:
  - Static S&P 500 tickers or subset as an array.

Config is loaded at startup and persisted changes via backend endpoints are versioned into `config_snapshots`.

#### 13.3 Paper vs Live Trading Safety

To enable **live trading**, all of the following must be true:
- `.env` has `PAPER_TRADING=false`.
- `.env` has `IB_GATEWAY_PORT=4001`.
- User completes a UI flow that:
  - Displays a warning about real-money trading risk.
  - Requires typing `CONFIRM` in a text box.
  - Sends a dedicated confirmation request to backend.

Backend enforces:
- If any of these conditions fail, **system remains in paper mode** even if UI attempts to switch.
- Current trading mode (PAPER/LIVE) is reflected in:
  - Global status banner.
  - Logs and metrics.

---

### 14. Testing Strategy

- **RiskManager tests**:
  - Coverage for all position, portfolio, and session-level rules.
  - Boundary conditions (e.g., exactly 5% NAV, exactly 3% drawdown).
  - Concurrent access patterns using asyncio tests.

- **OrderExecutor tests**:
  - Mocked IBKR client with deterministic responses.
  - Partial fills, timeouts, mid-price drift > 0.3% logic.
  - Error codes 201/202/110/103 handling and retry behavior.

- **Strategy tests**:
  - Deterministic OHLCV inputs with known indicator values.
  - Validate signal generation against expected outputs for each strategy.

- **PortfolioState tests**:
  - NAV and P&L calculations with multiple positions and currencies (CAD/USD).
  - Drawdown calculations and sector exposure.

Backtester tests:
- Ensure that backtests reproduce expected metrics given canned datasets.

---

### 15. README & Documentation

- README will include:
  - ASCII architecture diagram for the modular monolith and services.
  - Prerequisites:
    - IBKR account and IB Gateway.
    - Docker and Docker Compose.
  - Setup steps:
    - Clone repo.
    - Copy `.env.example` → `.env` and fill in values.
    - Edit `config.yaml` (watchlist, risk params).
    - Run `docker-compose up`.
  - How to add a new strategy:
    - Implement `BaseStrategy`.
    - Register with `StrategyEngine`.
    - Wire into config and UI.
  - How to adjust the watchlist.
  - How to switch from paper to live, with all warnings.
  - Legal disclaimer about educational use and trading risk.

This spec defines the architecture and behavior for the subsequent implementation and testing phases, following the required build order.

