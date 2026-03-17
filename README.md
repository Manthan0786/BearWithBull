## BWB Autonomous Trading System

Single-user, production-style autonomous US equities trading system for an Interactive Brokers account, designed for paper/live trading with strict risk controls and a monitoring dashboard.

### 1. Architecture

- **Backend**: FastAPI, SQLAlchemy, Redis, ib_insync.
  - Strategies: MomentumBreakout (5m), StatMeanReversion (15m), SentimentCatalyst (news-driven).
  - Risk: position and portfolio limits, daily loss limit, circuit breaker, cash reserve, mandatory stops, emergency stop.
  - Data: daily `ohlcv_daily` table, intraday bar/indicator cache in Redis.
  - Execution: OrderExecutor → RiskManager → IB Gateway; fills feed `positions` and `trades`.
- **Frontend**: React + TypeScript + Tailwind + Recharts.
  - Pages: Overview, Risk Monitor, Strategy Panel, Trade Log, Backtester.
- **Infra**: Docker Compose: ib-gateway, backend, frontend, postgres, redis.

### 2. Prerequisites

- Docker & Docker Compose.
- Interactive Brokers account (paper or live) and IB Gateway credentials.
- NewsAPI key (for SentimentCatalyst) if you want news-driven trading.

### 3. Configuration

1. **Environment**: copy `.env.example` to `.env` and fill:

   - `IB_GATEWAY_USER`, `IB_GATEWAY_PASSWORD`, `IB_ACCOUNT_ID`
   - `ACCOUNT_ID`, `DEFAULT_NAV`
   - `DATABASE_URL`, `REDIS_URL`
   - `NEWSAPI_KEY` for news; other keys (email/Telegram) are optional.

2. **Trading config**: `config.yaml`

   - Global trading settings (paper mode, daily loss limit %, max positions, etc.).
   - Per-strategy settings:
     - `risk_per_trade_pct`
     - `max_concurrent`
     - Extra fields (e.g. `vix_threshold`, `sentiment_threshold`, `max_hold_minutes`).
   - `watchlist`: tickers to trade (universe basis for all strategies).

### 4. Running the stack

From the repo root:

```bash
docker compose up -d --build
```

This starts:

- IB Gateway (`ib-gateway`) in paper mode by default.
- Postgres (`trading-postgres`) and Redis (`trading-redis`).
- Backend API at `http://localhost:8000`.
- Frontend dashboard at `http://localhost:3000`.

Check backend health:

- `http://localhost:8000/` → API info.
- `http://localhost:8000/health` → `{"status": "ok"}`.
- `http://localhost:8000/api/status` → trading status (`PAPER`/`ACTIVE`).

### 5. Dashboard

- **Overview**: NAV, cash, daily/all-time P&L, win rate, positions, today’s closed trades.
- **Risk Monitor**:
  - Risk rule statuses from `risk_audit`.
  - Daily loss gauge from PortfolioState and config limit.
  - Alert feed (risk/strategy/system alerts).
- **Strategy Panel**:
  - Strategy list (Momentum, StatMean, Sentiment).
  - Enable/disable toggles (wired to backend `/api/strategies`).
  - Emergency stop (CONFIRM → calls `/api/emergency-stop`).
- **Trade Log**:
  - Filterable list of trades.
  - CSV export (client-side) of current filter.
- **Backtester**:
  - Run backtests for a strategy over date range; see equity curve and stats.

### 6. Safety & Risk

- **RiskManager** (pre-order):
  - Max position size (5% NAV).
  - Max loss per trade (1% NAV via stop).
  - Mandatory stop-loss for entries.
  - Cash reserve (e.g. 20% NAV unallocated).
  - Daily loss limit (% drawdown from open).
  - Max daily trades.
  - Consecutive-loss circuit breaker (halts new entries after N losing trades).
- **Risk audit**:
  - Every rule evaluation is stored in `risk_audit` and surfaced via `/api/risk`.
- **Emergency stop**:
  - Backend endpoint cancels all open orders and flattens all positions via IBKR.
  - Frontend Emergency stop button requires typing `CONFIRM`.

### 7. Strategies (high level)

- **MomentumBreakout**:
  - 5m bars, top 20% of universe by 20d momentum / volume surge / RS vs SPY.
  - Entries on breakouts with RSI/SMA filters.
  - Exits: ATR-based stop/target.
- **StatMeanReversion**:
  - Daily universe pre-filter (BBW percentile, VIX, SPY move).
  - 15m mean-reversion entries using Bollinger Bands, RSI(2), 200-SMA.
  - ATR-based sizing and exits.
- **SentimentCatalyst**:
  - Reacts to strong-sentiment news via NewsAPI + VADER.
  - Filters on sentiment label and simple symbol detection.
  - ATR-based sizing, 90-minute max hold, ATR-based stop/target.

### 8. Paper vs Live trading

- The stack is designed to run in **paper** mode by default:
  - IB Gateway in paper mode (`TRADING_MODE=paper`).
  - Backend treats it as real but with simulated money.
- To move toward live:
  - Use separate config and `.env` with explicit confirmation.
  - Ensure you fully understand the strategies and risk rules.
  - Consider restricting live trading to a subset of capital/tickers.

### 9. Disclaimers

- This system is for educational/experimental use.
- No guarantees on performance, reliability, or regulatory compliance.
- Use extreme caution before connecting to a live funded account.

