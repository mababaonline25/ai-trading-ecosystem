"""
Pytest Configuration and Fixtures
Comprehensive testing setup for enterprise application
"""

import asyncio
import pytest
import pytest_asyncio
from typing import Dict, Any, Generator, AsyncGenerator
from datetime import datetime, timedelta
import uuid
import json
import os
from unittest.mock import Mock, patch, AsyncMock

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from redis import Redis
import mongomock

from backend.main import app
from backend.data.database import Base, get_db
from backend.data.redis_client import get_redis
from backend.data.mongodb_client import get_mongodb
from backend.core.auth.jwt import create_access_token
from backend.core.market.exchange_manager import ExchangeManager
from backend.core.trading.execution_engine import ExecutionEngine
from backend.core.risk.risk_manager import RiskManager
from backend.utils.websocket_manager import ws_manager
from backend.config import settings
from backend.data.models.user import User
from backend.data.repositories.user_repo import UserRepository
from backend.data.repositories.market_repo import MarketRepository
from backend.data.repositories.trade_repo import TradeRepository


# ==================== Test Database Setup ====================

@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine"""
    # Use in-memory SQLite for testing
    engine = create_engine(
        "sqlite:///./test.db",
        connect_args={"check_same_thread": False}
    )
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    yield engine
    
    # Cleanup
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test.db"):
        os.remove("./test.db")


@pytest.fixture(scope="function")
def db_session(test_engine) -> Generator[Session, None, None]:
    """Create a fresh database session for each test"""
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine
    )
    
    session = TestingSessionLocal()
    
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def override_get_db(db_session):
    """Override database dependency"""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = _override_get_db
    yield
    del app.dependency_overrides[get_db]


# ==================== Redis Mock ====================

@pytest.fixture(scope="function")
def redis_mock():
    """Create a mock Redis client"""
    mock_redis = mongomock.MongoClient().db.collection
    mock_redis.get = Mock(return_value=None)
    mock_redis.set = Mock(return_value=True)
    mock_redis.delete = Mock(return_value=True)
    mock_redis.exists = Mock(return_value=False)
    mock_redis.expire = Mock(return_value=True)
    
    return mock_redis


@pytest.fixture(scope="function")
def override_get_redis(redis_mock):
    """Override Redis dependency"""
    def _override_get_redis():
        return redis_mock
    
    app.dependency_overrides[get_redis] = _override_get_redis
    yield
    del app.dependency_overrides[get_redis]


# ==================== MongoDB Mock ====================

@pytest.fixture(scope="function")
def mongodb_mock():
    """Create a mock MongoDB client"""
    client = mongomock.MongoClient()
    db = client.test_database
    
    return db


@pytest.fixture(scope="function")
def override_get_mongodb(mongodb_mock):
    """Override MongoDB dependency"""
    def _override_get_mongodb():
        return mongodb_mock
    
    app.dependency_overrides[get_mongodb] = _override_get_mongodb
    yield
    del app.dependency_overrides[get_mongodb]


# ==================== Test Client ====================

@pytest.fixture(scope="function")
def client(
    override_get_db,
    override_get_redis,
    override_get_mongodb
) -> Generator[TestClient, None, None]:
    """Create test client with all overrides"""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create async test client"""
    async with httpx.AsyncClient(app=app, base_url="http://test") as test_client:
        yield test_client


# ==================== Test Data Factories ====================

@pytest.fixture
def user_data() -> Dict[str, Any]:
    """Generate test user data"""
    return {
        "username": f"testuser_{uuid.uuid4().hex[:8]}",
        "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
        "password": "Test@123456",
        "first_name": "Test",
        "last_name": "User",
        "phone": "+1234567890",
        "country": "US"
    }


@pytest.fixture
def market_data() -> Dict[str, Any]:
    """Generate test market data"""
    return {
        "symbol": "BTCUSDT",
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "exchange_id": "binance",
        "min_quantity": 0.0001,
        "max_quantity": 1000,
        "step_size": 0.0001,
        "price_precision": 2,
        "quantity_precision": 6,
        "min_notional": 10,
        "is_active": True
    }


@pytest.fixture
def order_data() -> Dict[str, Any]:
    """Generate test order data"""
    return {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "quantity": 0.001,
        "price": 50000.0,
        "time_in_force": "GTC"
    }


@pytest.fixture
def signal_data() -> Dict[str, Any]:
    """Generate test signal data"""
    return {
        "symbol": "BTCUSDT",
        "action": "BUY",
        "type": "TECHNICAL",
        "confidence": 85,
        "entry_price": 50000.0,
        "target_price": 51000.0,
        "stop_loss": 49500.0,
        "timeframe": "1h",
        "reasoning": "RSI oversold + MACD bullish crossover"
    }


@pytest.fixture
def alert_data() -> Dict[str, Any]:
    """Generate test alert data"""
    return {
        "symbol": "BTCUSDT",
        "type": "PRICE",
        "condition": "ABOVE",
        "value": 60000.0,
        "name": "BTC $60k Alert",
        "is_recurring": False
    }


# ==================== Mock Exchange Manager ====================

@pytest.fixture
def mock_exchange_manager():
    """Create mock exchange manager"""
    mock = AsyncMock(spec=ExchangeManager)
    
    # Mock price data
    mock.get_price.return_value = 50000.0
    
    # Mock ticker data
    mock.get_ticker.return_value = {
        "symbol": "BTCUSDT",
        "last": 50000.0,
        "bid": 49990.0,
        "ask": 50010.0,
        "high": 51000.0,
        "low": 49000.0,
        "volume": 1000.0,
        "change": 500.0,
        "change_percent": 1.0
    }
    
    # Mock klines data
    mock.get_klines.return_value = [
        {
            "timestamp": datetime.utcnow().timestamp() * 1000 - i * 3600000,
            "open": 50000.0 + i * 10,
            "high": 50100.0 + i * 10,
            "low": 49900.0 + i * 10,
            "close": 50050.0 + i * 10,
            "volume": 100.0
        }
        for i in range(100)
    ]
    
    # Mock orderbook
    mock.get_orderbook.return_value = {
        "bids": [[49990.0, 1.0], [49980.0, 2.0]],
        "asks": [[50010.0, 1.0], [50020.0, 2.0]]
    }
    
    return mock


@pytest.fixture
def mock_execution_engine(mock_exchange_manager):
    """Create mock execution engine"""
    mock = AsyncMock(spec=ExecutionEngine)
    mock.exchange_manager = mock_exchange_manager
    
    # Mock order placement
    mock.place_order.return_value = str(uuid.uuid4())
    mock.place_market_order.return_value = str(uuid.uuid4())
    mock.place_limit_order.return_value = str(uuid.uuid4())
    
    # Mock order status
    mock.get_order.return_value = {
        "id": str(uuid.uuid4()),
        "status": "FILLED",
        "filled_quantity": 0.001,
        "avg_price": 50000.0
    }
    
    # Mock open orders
    mock.get_open_orders.return_value = []
    
    return mock


@pytest.fixture
def mock_risk_manager():
    """Create mock risk manager"""
    mock = AsyncMock(spec=RiskManager)
    
    # Mock risk checks
    mock.check_order.return_value = True
    
    # Mock position sizing
    mock.calculate_position_size.return_value = 0.001
    
    # Mock stop loss
    mock.calculate_stop_loss.return_value = 49000.0
    
    # Mock take profit
    mock.calculate_take_profit.return_value = 51000.0
    
    # Mock risk metrics
    mock.get_risk_metrics.return_value = {
        "total_exposure": 50000.0,
        "total_margin": 10000.0,
        "margin_level": 500.0,
        "unrealized_pnl": 500.0,
        "daily_pnl": 1000.0,
        "win_rate": 60.0,
        "sharpe_ratio": 1.5,
        "max_drawdown": 10.0
    }
    
    return mock


# ==================== Authentication Fixtures ====================

@pytest.fixture
def test_user(db_session, user_data) -> User:
    """Create a test user in database"""
    user_repo = UserRepository(db_session)
    
    from backend.core.auth.jwt import get_password_hash
    
    user_data["password_hash"] = get_password_hash(user_data["password"])
    user_data["email_verified"] = True
    user_data["is_active"] = True
    
    user = user_repo.create(user_data)
    return user


@pytest.fixture
def user_token(test_user) -> str:
    """Create JWT token for test user"""
    return create_access_token(
        data={"sub": str(test_user.id)},
        expires_delta=timedelta(minutes=30)
    )


@pytest.fixture
def auth_headers(user_token) -> Dict[str, str]:
    """Create authentication headers"""
    return {"Authorization": f"Bearer {user_token}"}


# ==================== WebSocket Fixtures ====================

@pytest.fixture
async def websocket_manager():
    """Get WebSocket manager instance"""
    await ws_manager.start()
    yield ws_manager
    await ws_manager.stop()


@pytest.fixture
def websocket_client(client):
    """Create WebSocket test client"""
    return client.websocket_connect


# ==================== Market Data Fixtures ====================

@pytest.fixture
def sample_klines() -> list:
    """Generate sample kline data"""
    klines = []
    base_time = datetime.utcnow().timestamp() * 1000
    
    for i in range(100):
        klines.append({
            "timestamp": base_time - (99 - i) * 3600000,
            "open": 50000.0 + i * 10,
            "high": 50100.0 + i * 10,
            "low": 49900.0 + i * 10,
            "close": 50050.0 + i * 10,
            "volume": 100.0 + i
        })
    
    return klines


@pytest.fixture
def sample_orderbook() -> dict:
    """Generate sample orderbook data"""
    return {
        "bids": [[50000.0 - i * 10, 1.0] for i in range(10)],
        "asks": [[50000.0 + i * 10, 1.0] for i in range(10)]
    }


@pytest.fixture
def sample_ticker() -> dict:
    """Generate sample ticker data"""
    return {
        "symbol": "BTCUSDT",
        "last": 50000.0,
        "bid": 49990.0,
        "ask": 50010.0,
        "high": 51000.0,
        "low": 49000.0,
        "volume": 1000.0,
        "quote_volume": 50000000.0,
        "change": 500.0,
        "change_percent": 1.0,
        "timestamp": datetime.utcnow().isoformat()
    }


# ==================== Repository Fixtures ====================

@pytest.fixture
def user_repo(db_session):
    """Create user repository"""
    return UserRepository(db_session)


@pytest.fixture
def market_repo(db_session):
    """Create market repository"""
    return MarketRepository(db_session)


@pytest.fixture
def trade_repo(db_session):
    """Create trade repository"""
    return TradeRepository(db_session)


# ==================== Mock API Responses ====================

@pytest.fixture
def mock_binance_response():
    """Mock Binance API response"""
    return {
        "symbol": "BTCUSDT",
        "price": "50000.00",
        "time": int(datetime.utcnow().timestamp() * 1000)
    }


@pytest.fixture
def mock_binance_klines_response():
    """Mock Binance klines response"""
    return [
        [
            1625097600000,  # open time
            "50000.0",      # open
            "51000.0",      # high
            "49000.0",      # low
            "50500.0",      # close
            "1000.0",       # volume
            1625184000000,  # close time
            "50000000.0",   # quote volume
            1000,           # number of trades
            "500.0",        # taker buy volume
            "25000000.0",   # taker buy quote volume
            "0"             # ignore
        ]
        for _ in range(100)
    ]


# ==================== Performance Testing Fixtures ====================

@pytest.fixture
def performance_test_data() -> Dict[str, Any]:
    """Generate large dataset for performance testing"""
    return {
        "users": [
            {
                "id": i,
                "username": f"user_{i}",
                "email": f"user_{i}@example.com"
            }
            for i in range(1000)
        ],
        "trades": [
            {
                "id": i,
                "symbol": "BTCUSDT",
                "side": "BUY" if i % 2 == 0 else "SELL",
                "quantity": 0.001,
                "price": 50000.0 + i,
                "timestamp": datetime.utcnow().isoformat()
            }
            for i in range(10000)
        ],
        "klines": [
            {
                "timestamp": datetime.utcnow().timestamp() * 1000 - i * 3600000,
                "open": 50000.0 + i * 0.1,
                "high": 50100.0 + i * 0.1,
                "low": 49900.0 + i * 0.1,
                "close": 50050.0 + i * 0.1,
                "volume": 100.0
            }
            for i in range(10000)
        ]
    }


# ==================== Error Simulation ====================

@pytest.fixture
def mock_api_error():
    """Simulate API error"""
    class MockAPIError(Exception):
        def __init__(self, message="API Error", code=-1000):
            self.message = message
            self.code = code
            super().__init__(message)
    
    return MockAPIError


@pytest.fixture
def mock_network_error():
    """Simulate network error"""
    class MockNetworkError(Exception):
        def __init__(self, message="Network Error"):
            self.message = message
            super().__init__(message)
    
    return MockNetworkError


# ==================== Cleanup ====================

@pytest.fixture(autouse=True)
def cleanup():
    """Cleanup after each test"""
    yield
    
    # Clear any cached data
    import gc
    gc.collect()