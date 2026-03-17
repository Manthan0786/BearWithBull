import asyncio
import os
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ib_insync import IB, Trade as IBTrade, OrderStatus
from pydantic import BaseModel

from backend.broker.fill_handler import process_entry_fill, process_exit_fill
from backend.broker.ibkr_client import IBKRClient
from backend.broker.order_executor import OrderExecutor
from backend.config import load_config
from backend.data.data_pipeline import DataPipeline
from backend.news.news_poller import NewsPoller
from backend.data.historical import bootstrap_historical
from backend.api.routes import router as api_router
from backend.models.database import SessionLocal
from backend.models.models import Order as OrderModel
from backend.risk.portfolio_state import PortfolioState
from backend.risk.risk_manager import RiskManager
from backend.strategies.strategy_engine import StrategyEngine


class IBConnectionStatus(BaseModel):
    connected: bool
    host: str
    port: int
    paper_trading: bool
    error: str | None = None


ib: IB | None = None
redis_client: redis.Redis | None = None
data_pipeline: DataPipeline | None = None
news_poller: NewsPoller | None = None
strategy_engine: StrategyEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ib, redis_client, data_pipeline, strategy_engine, news_poller

    cfg = load_config()
    app.state.cfg = cfg

    account_id = int(os.getenv("ACCOUNT_ID", "1"))
    portfolio_state = PortfolioState(account_id=account_id)
    portfolio_state.load_from_db()
    default_nav = float(os.getenv("DEFAULT_NAV", "100000"))
    if portfolio_state.nav() <= 0:
        portfolio_state._nav = default_nav  # type: ignore[attr-defined]
        portfolio_state._opening_nav = default_nav  # type: ignore[attr-defined]
    app.state.portfolio_state = portfolio_state

    risk_manager = RiskManager(cfg, portfolio_state)
    app.state.risk_manager = risk_manager

    ib = IB()
    app.state.ib = ib
    host = os.getenv("IB_GATEWAY_HOST", "ib-gateway")
    port = int(os.getenv("IB_GATEWAY_PORT", "4002"))

    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    redis_client = redis.from_url(redis_url, decode_responses=False)

    try:
        await asyncio.to_thread(ib.connect, host, port, clientId=1)
        await bootstrap_historical(ib, cfg.watchlist)
        data_pipeline = DataPipeline(ib, redis_client)
        await data_pipeline.start(cfg.watchlist)

        news_poller = NewsPoller(cfg, redis_client)
        await news_poller.start()

        ib_client = IBKRClient(ib)
        order_executor = OrderExecutor(ib_client, risk_manager)
        strategy_engine = StrategyEngine(
            cfg=cfg,
            redis_client=redis_client,
            portfolio_state=portfolio_state,
            order_executor=order_executor,
        )
        app.state.strategy_engine = strategy_engine
        await strategy_engine.start()

        # Attach IB order status handler to drive fills into positions/trades.
        def on_order_status(trade: IBTrade, status: OrderStatus) -> None:
            try:
                ib_order_id = trade.order.orderId
            except Exception:
                return
            if status.status != "Filled":
                return
            # Look up the matching DB order by ibkr_order_id
            session = SessionLocal()
            try:
                db_order = (
                    session.query(OrderModel)
                    .filter(OrderModel.ibkr_order_id == ib_order_id)
                    .one_or_none()
                )
                if not db_order:
                    return
                fill_price = status.avgFillPrice or db_order.limit_price or db_order.fill_price or 0.0
                fill_qty = status.filled or db_order.quantity or 0.0
                order_type = db_order.order_type
                oca_group = db_order.oca_group_id
            finally:
                session.close()

            if order_type == "LMT":
                # Treat as entry fill
                process_entry_fill(db_order.id, fill_price, fill_qty)
            elif order_type == "STP":
                # Find corresponding entry order in same OCA group
                entry_id = db_order.id
                if oca_group:
                    session = SessionLocal()
                    try:
                        entry = (
                            session.query(OrderModel)
                            .filter(
                                OrderModel.oca_group_id == oca_group,
                                OrderModel.order_type == "LMT",
                            )
                            .first()
                        )
                        if entry:
                            entry_id = entry.id
                    finally:
                        session.close()
                process_exit_fill(
                    exit_order_id=db_order.id,
                    entry_order_id=entry_id,
                    exit_price=fill_price,
                    fill_qty=fill_qty,
                    exit_reason="STOP",
                )

        ib.orderStatusEvent += on_order_status
    except Exception:
        ib = None
        app.state.strategy_engine = None

    yield

    if strategy_engine is not None:
        await strategy_engine.stop()
    if data_pipeline is not None:
        await data_pipeline.stop()
    if news_poller is not None:
        await news_poller.stop()
    if ib is not None and ib.isConnected():
        await asyncio.to_thread(ib.disconnect)
    if redis_client is not None:
        await redis_client.close()


app = FastAPI(lifespan=lifespan)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "app": "BWB Trading API",
        "docs": "/docs",
        "health": "/health",
        "api_status": "/api/status",
        "api_portfolio": "/api/portfolio",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ib/test", response_model=IBConnectionStatus)
async def ib_test_connection():
    host = os.getenv("IB_GATEWAY_HOST", "ib-gateway")
    port = int(os.getenv("IB_GATEWAY_PORT", "4002"))
    paper = os.getenv("PAPER_TRADING", "true").lower() == "true"

    if ib is None or not ib.isConnected():
        return IBConnectionStatus(
            connected=False,
            host=host,
            port=port,
            paper_trading=paper,
            error="Not connected to IB Gateway",
        )

    return IBConnectionStatus(
        connected=True,
        host=host,
        port=port,
        paper_trading=paper,
    )

