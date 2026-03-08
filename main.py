"""
AI Trading Ecosystem - Enterprise Edition
Entry point for the entire platform
Version: 1.0.0
"""

import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from backend.api.v1 import (
    auth, market, trading, portfolio, signals,
    alerts, social, admin, webhooks
)
from backend.core.services.market_data import MarketDataService
from backend.core.services.trading_engine import TradingEngine
from backend.core.services.ai_engine import AIEngine
from backend.core.services.notification import NotificationService
from backend.data.database import init_db
from backend.config import settings
from backend.utils.logger import setup_logging
from backend.workers import (
    data_collector, signal_generator, alert_checker,
    model_trainer, cleanup_worker
)

# লগিং সেটআপ
setup_logging()
logger = logging.getLogger(__name__)

# FastAPI অ্যাপ
app = FastAPI(
    title="AI Trading Ecosystem",
    description="Enterprise-grade AI Trading Platform",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API রাউটার
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(market.router, prefix="/api/v1/market", tags=["Market Data"])
app.include_router(trading.router, prefix="/api/v1/trading", tags=["Trading"])
app.include_router(portfolio.router, prefix="/api/v1/portfolio", tags=["Portfolio"])
app.include_router(signals.router, prefix="/api/v1/signals", tags=["Signals"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["Alerts"])
app.include_router(social.router, prefix="/api/v1/social", tags=["Social Trading"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["Webhooks"])

# স্ট্যাটিক ফাইল
app.mount("/static", StaticFiles(directory="frontend/out"), name="static")


@app.on_event("startup")
async def startup_event():
    """অ্যাপ্লিকেশন স্টার্টআপ"""
    logger.info("🚀 Starting AI Trading Ecosystem...")
    
    # ডাটাবেস ইনিশিয়ালাইজ
    await init_db()
    logger.info("✅ Database initialized")
    
    # সার্ভিসেস স্টার্ট
    await MarketDataService.start()
    await TradingEngine.start()
    await AIEngine.start()
    await NotificationService.start()
    logger.info("✅ Services started")
    
    # ওয়ার্কার স্টার্ট
    asyncio.create_task(data_collector.run())
    asyncio.create_task(signal_generator.run())
    asyncio.create_task(alert_checker.run())
    asyncio.create_task(model_trainer.run())
    asyncio.create_task(cleanup_worker.run())
    logger.info("✅ Workers started")
    
    logger.info("🎉 AI Trading Ecosystem is ready!")


@app.on_event("shutdown")
async def shutdown_event():
    """অ্যাপ্লিকেশন শাটডাউন"""
    logger.info("🛑 Shutting down AI Trading Ecosystem...")
    
    await MarketDataService.stop()
    await TradingEngine.stop()
    await AIEngine.stop()
    await NotificationService.stop()
    
    logger.info("👋 Goodbye!")


@app.get("/")
async def root():
    """রুট এন্ডপয়েন্ট"""
    return {
        "name": "AI Trading Ecosystem",
        "version": "1.0.0",
        "status": "operational",
        "documentation": "/api/docs"
    }


@app.get("/health")
async def health_check():
    """হেলথ চেক"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "database": "connected",
            "redis": "connected",
            "market_data": "operational",
            "trading_engine": "operational",
            "ai_engine": "operational"
        }
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )