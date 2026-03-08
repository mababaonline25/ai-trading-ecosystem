"""
API v1 Package
Enterprise-grade REST API with versioning
"""

from fastapi import APIRouter

from .endpoints import (
    auth, users, market, trading, signals, alerts,
    portfolio, analytics, social, admin, websocket,
    strategies, backtest, subscriptions, news, webhooks
)

# Main API router
api_router = APIRouter(prefix="/api/v1")

# Include all endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(market.router, prefix="/market", tags=["Market Data"])
api_router.include_router(trading.router, prefix="/trading", tags=["Trading"])
api_router.include_router(signals.router, prefix="/signals", tags=["Signals"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(portfolio.router, prefix="/portfolio", tags=["Portfolio"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(social.router, prefix="/social", tags=["Social"])
api_router.include_router(strategies.router, prefix="/strategies", tags=["Strategies"])
api_router.include_router(backtest.router, prefix="/backtest", tags=["Backtesting"])
api_router.include_router(subscriptions.router, prefix="/subscriptions", tags=["Subscriptions"])
api_router.include_router(news.router, prefix="/news", tags=["News"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])

# WebSocket router (separate handling)
websocket_router = APIRouter()
websocket_router.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])