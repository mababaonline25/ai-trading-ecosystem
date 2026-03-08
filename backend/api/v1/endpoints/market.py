"""
Market Data Endpoints
Real-time and historical market data with WebSocket support
"""

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import asyncio
from collections import defaultdict

from ....core.market.exchange_manager import ExchangeManager
from ....core.market.data_collector import DataCollector
from ....core.market.real_time_analyzer import RealTimeAnalyzer
from ....core.analysis.technical.indicators import TechnicalIndicators
from ....core.analysis.technical.patterns import PatternDetector
from ....data.repositories.market_repo import MarketRepository
from ....utils.auth import get_current_user_optional
from ....utils.rate_limiter import rate_limit
from ....utils.cache import cache_response, invalidate_cache
from ....utils.websocket_manager import WebSocketManager
from ....models.user import User
from ....config import settings

router = APIRouter()
exchange_manager = ExchangeManager()
data_collector = DataCollector()
market_repo = MarketRepository()
ws_manager = WebSocketManager()
real_time_analyzer = RealTimeAnalyzer()

# Active WebSocket connections for market data
market_ws_connections = defaultdict(set)


@router.get("/exchanges")
@cache_response(ttl=3600)  # Cache for 1 hour
async def get_exchanges(
    type: Optional[str] = None,
    is_active: bool = True
):
    """
    Get list of all supported exchanges
    """
    exchanges = await market_repo.get_exchanges(
        type=type,
        is_active=is_active
    )
    
    return {
        "total": len(exchanges),
        "exchanges": exchanges
    }


@router.get("/exchanges/{exchange_id}")
@cache_response(ttl=3600)
async def get_exchange_details(exchange_id: str):
    """
    Get detailed information about a specific exchange
    """
    exchange = await market_repo.get_exchange(exchange_id)
    
    if not exchange:
        raise HTTPException(status_code=404, detail="Exchange not found")
    
    # Get market count
    market_count = await market_repo.get_market_count(exchange_id)
    
    # Get 24h volume
    volume_24h = await market_repo.get_exchange_volume_24h(exchange_id)
    
    return {
        **exchange.to_dict(),
        "market_count": market_count,
        "volume_24h": volume_24h
    }


@router.get("/markets")
@cache_response(ttl=300)  # Cache for 5 minutes
async def get_markets(
    exchange_id: Optional[str] = None,
    base_asset: Optional[str] = None,
    quote_asset: Optional[str] = "USDT",
    type: Optional[str] = "spot",
    is_active: bool = True,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """
    Get list of all trading markets
    """
    markets = await market_repo.get_markets(
        exchange_id=exchange_id,
        base_asset=base_asset,
        quote_asset=quote_asset,
        type=type,
        is_active=is_active,
        limit=limit,
        offset=offset
    )
    
    total = await market_repo.get_market_count(
        exchange_id=exchange_id,
        base_asset=base_asset,
        quote_asset=quote_asset,
        type=type,
        is_active=is_active
    )
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "markets": markets
    }


@router.get("/markets/{symbol}")
@cache_response(ttl=60)  # Cache for 1 minute
async def get_market_details(
    symbol: str,
    exchange_id: Optional[str] = "binance"
):
    """
    Get detailed information about a specific market
    """
    market = await market_repo.get_market(symbol, exchange_id)
    
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    
    # Get current ticker
    ticker = await exchange_manager.get_ticker(symbol, exchange_id)
    
    # Get 24h stats
    stats = await exchange_manager.get_24h_stats(symbol, exchange_id)
    
    return {
        **market.to_dict(),
        "ticker": ticker,
        "stats_24h": stats
    }


@router.get("/ticker/{symbol}")
@cache_response(ttl=10)  # Cache for 10 seconds
async def get_ticker(
    symbol: str,
    exchange_id: Optional[str] = "binance"
):
    """
    Get real-time ticker for a symbol
    """
    ticker = await exchange_manager.get_ticker(symbol, exchange_id)
    
    if not ticker:
        raise HTTPException(status_code=404, detail="Ticker not found")
    
    return ticker


@router.get("/ticker/all/{symbol}")
@cache_response(ttl=5)  # Cache for 5 seconds
async def get_all_tickers(symbol: str):
    """
    Get ticker from all exchanges
    """
    tasks = []
    exchanges = await market_repo.get_active_exchanges()
    
    for exchange in exchanges:
        tasks.append(exchange_manager.get_ticker(symbol, exchange['id']))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    tickers = {}
    for exchange, result in zip(exchanges, results):
        if not isinstance(result, Exception) and result:
            tickers[exchange['id']] = result
    
    return {
        "symbol": symbol,
        "timestamp": datetime.utcnow().isoformat(),
        "tickers": tickers
    }


@router.get("/orderbook/{symbol}")
@cache_response(ttl=1)  # Cache for 1 second
async def get_orderbook(
    symbol: str,
    depth: int = Query(10, ge=1, le=100),
    exchange_id: Optional[str] = "binance"
):
    """
    Get order book for a symbol
    """
    orderbook = await exchange_manager.get_orderbook(symbol, depth, exchange_id)
    
    if not orderbook:
        raise HTTPException(status_code=404, detail="Orderbook not found")
    
    # Calculate spread
    if orderbook['bids'] and orderbook['asks']:
        best_bid = orderbook['bids'][0][0]
        best_ask = orderbook['asks'][0][0]
        spread = best_ask - best_bid
        spread_percent = (spread / best_bid) * 100
    else:
        spread = 0
        spread_percent = 0
    
    return {
        "symbol": symbol,
        "exchange": exchange_id,
        "timestamp": datetime.utcnow().isoformat(),
        "bids": orderbook['bids'],
        "asks": orderbook['asks'],
        "spread": spread,
        "spread_percent": spread_percent,
        "bid_depth": sum(qty for _, qty in orderbook['bids']),
        "ask_depth": sum(qty for _, qty in orderbook['asks'])
    }


@router.get("/klines/{symbol}")
@cache_response(ttl=60)  # Cache for 1 minute
async def get_klines(
    symbol: str,
    interval: str = Query("1h", regex="^(1m|5m|15m|30m|1h|4h|1d|1w|1M)$"),
    limit: int = Query(100, ge=1, le=1000),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    exchange_id: Optional[str] = "binance"
):
    """
    Get historical candlestick data
    """
    klines = await exchange_manager.get_klines(
        symbol=symbol,
        interval=interval,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        exchange=exchange_id
    )
    
    if not klines:
        raise HTTPException(status_code=404, detail="Kline data not found")
    
    return {
        "symbol": symbol,
        "exchange": exchange_id,
        "interval": interval,
        "timestamp": datetime.utcnow().isoformat(),
        "klines": klines
    }


@router.get("/trades/{symbol}")
@cache_response(ttl=5)  # Cache for 5 seconds
async def get_recent_trades(
    symbol: str,
    limit: int = Query(50, ge=1, le=1000),
    exchange_id: Optional[str] = "binance"
):
    """
    Get recent trades for a symbol
    """
    trades = await exchange_manager.get_recent_trades(symbol, limit, exchange_id)
    
    return {
        "symbol": symbol,
        "exchange": exchange_id,
        "timestamp": datetime.utcnow().isoformat(),
        "trades": trades
    }


@router.get("/stats/{symbol}")
@cache_response(ttl=60)  # Cache for 1 minute
async def get_market_stats(
    symbol: str,
    exchange_id: Optional[str] = "binance"
):
    """
    Get 24-hour market statistics
    """
    stats = await exchange_manager.get_24h_stats(symbol, exchange_id)
    
    if not stats:
        raise HTTPException(status_code=404, detail="Stats not found")
    
    return stats


@router.get("/top-gainers")
@cache_response(ttl=300)  # Cache for 5 minutes
async def get_top_gainers(
    limit: int = Query(10, ge=1, le=100),
    exchange_id: Optional[str] = "binance"
):
    """
    Get top gaining symbols
    """
    gainers = await data_collector.get_top_gainers(limit, exchange_id)
    
    return {
        "type": "gainers",
        "timestamp": datetime.utcnow().isoformat(),
        "data": gainers
    }


@router.get("/top-losers")
@cache_response(ttl=300)
async def get_top_losers(
    limit: int = Query(10, ge=1, le=100),
    exchange_id: Optional[str] = "binance"
):
    """
    Get top losing symbols
    """
    losers = await data_collector.get_top_losers(limit, exchange_id)
    
    return {
        "type": "losers",
        "timestamp": datetime.utcnow().isoformat(),
        "data": losers
    }


@router.get("/top-volume")
@cache_response(ttl=300)
async def get_top_volume(
    limit: int = Query(10, ge=1, le=100),
    exchange_id: Optional[str] = "binance"
):
    """
    Get symbols with highest volume
    """
    volume = await data_collector.get_top_volume(limit, exchange_id)
    
    return {
        "type": "volume",
        "timestamp": datetime.utcnow().isoformat(),
        "data": volume
    }


@router.get("/technical/{symbol}")
@cache_response(ttl=60)  # Cache for 1 minute
async def get_technical_analysis(
    symbol: str,
    interval: str = "1h",
    exchange_id: Optional[str] = "binance",
    indicators: Optional[str] = Query(None, description="Comma-separated list of indicators")
):
    """
    Get technical analysis for a symbol
    """
    # Get historical data
    klines = await exchange_manager.get_klines(symbol, interval, 500, exchange_id)
    
    if not klines or len(klines) < 50:
        raise HTTPException(status_code=404, detail="Insufficient data for analysis")
    
    # Extract OHLCV data
    opens = [k['open'] for k in klines]
    highs = [k['high'] for k in klines]
    lows = [k['low'] for k in klines]
    closes = [k['close'] for k in klines]
    volumes = [k['volume'] for k in klines]
    
    # Parse requested indicators
    indicator_list = indicators.split(',') if indicators else None
    
    # Calculate indicators
    result = {}
    
    # Always include basic indicators
    result['current_price'] = closes[-1]
    result['price_change_1h'] = ((closes[-1] - closes[-6]) / closes[-6]) * 100 if len(closes) >= 6 else 0
    result['price_change_24h'] = ((closes[-1] - closes[-24]) / closes[-24]) * 100 if len(closes) >= 24 else 0
    
    # Calculate all indicators
    indicators_data = TechnicalIndicators.get_all_indicators({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })
    
    # Filter requested indicators
    if indicator_list:
        for ind in indicator_list:
            if ind in indicators_data:
                result[ind] = indicators_data[ind][-1] if isinstance(indicators_data[ind], np.ndarray) else indicators_data[ind]
    else:
        # Return all indicators (last value only)
        for key, value in indicators_data.items():
            if isinstance(value, np.ndarray):
                result[key] = value[-1] if len(value) > 0 else None
            elif isinstance(value, dict):
                result[key] = {k: v[-1] if isinstance(v, np.ndarray) else v for k, v in value.items()}
            else:
                result[key] = value
    
    # Detect patterns
    patterns = PatternDetector.detect_all(closes, highs, lows)
    
    # Generate signals
    signals = TechnicalIndicators.generate_signals({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })
    
    # Get consensus
    consensus = TechnicalIndicators.get_consensus_signal({
        'close': closes,
        'high': highs,
        'low': lows,
        'volume': volumes
    })
    
    return {
        "symbol": symbol,
        "interval": interval,
        "exchange": exchange_id,
        "timestamp": datetime.utcnow().isoformat(),
        "current_price": closes[-1],
        "indicators": result,
        "patterns": patterns,
        "signals": signals,
        "consensus": consensus
    }


@router.websocket("/ws/{symbol}")
async def websocket_market_data(
    websocket: WebSocket,
    symbol: str,
    exchange_id: str = "binance",
    interval: str = "1s"
):
    """
    WebSocket connection for real-time market data
    """
    await websocket.accept()
    client_id = f"{symbol}_{exchange_id}_{id(websocket)}"
    
    # Add to connections
    market_ws_connections[symbol].add(websocket)
    
    try:
        # Send initial data
        ticker = await exchange_manager.get_ticker(symbol, exchange_id)
        if ticker:
            await websocket.send_json({
                "type": "init",
                "data": ticker
            })
        
        # Real-time updates
        while True:
            try:
                # Get latest data
                ticker = await exchange_manager.get_ticker(symbol, exchange_id)
                
                if ticker:
                    await websocket.send_json({
                        "type": "update",
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": ticker
                    })
                
                # Wait for next interval
                await asyncio.sleep(float(interval.replace('s', '')))
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
                break
                
    finally:
        # Remove from connections
        market_ws_connections[symbol].discard(websocket)


@router.websocket("/ws/orderbook/{symbol}")
async def websocket_orderbook(
    websocket: WebSocket,
    symbol: str,
    exchange_id: str = "binance",
    depth: int = 10
):
    """
    WebSocket connection for real-time orderbook updates
    """
    await websocket.accept()
    
    try:
        while True:
            orderbook = await exchange_manager.get_orderbook(symbol, depth, exchange_id)
            
            if orderbook:
                await websocket.send_json({
                    "type": "orderbook",
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": orderbook
                })
            
            await asyncio.sleep(0.5)  # Update every 500ms
            
    except WebSocketDisconnect:
        pass


@router.get("/search")
async def search_markets(
    query: str,
    limit: int = Query(10, ge=1, le=50)
):
    """
    Search for markets by symbol or name
    """
    results = await market_repo.search_markets(query, limit)
    
    return {
        "query": query,
        "results": results
    }


@router.get("/fear-greed-index")
@cache_response(ttl=3600)  # Cache for 1 hour
async def get_fear_greed_index(
    limit: int = Query(30, ge=1, le=365)
):
    """
    Get Crypto Fear & Greed Index
    """
    index = await data_collector.get_fear_greed_index(limit)
    
    return index


@router.get("/economic-calendar")
@cache_response(ttl=3600)
async def get_economic_calendar(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    country: Optional[str] = None,
    importance: Optional[str] = None
):
    """
    Get economic calendar events
    """
    events = await data_collector.get_economic_calendar(
        date_from=date_from or datetime.utcnow(),
        date_to=date_to or datetime.utcnow() + timedelta(days=7),
        country=country,
        importance=importance
    )
    
    return events


@router.post("/watchlist")
async def add_to_watchlist(
    symbol: str,
    exchange_id: str = "binance",
    current_user: User = Depends(get_current_user_optional)
):
    """
    Add symbol to user's watchlist
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    watchlist = await market_repo.add_to_watchlist(current_user.id, symbol, exchange_id)
    
    return {
        "message": f"{symbol} added to watchlist",
        "watchlist": watchlist
    }


@router.delete("/watchlist/{symbol}")
async def remove_from_watchlist(
    symbol: str,
    exchange_id: str = "binance",
    current_user: User = Depends(get_current_user_optional)
):
    """
    Remove symbol from user's watchlist
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    watchlist = await market_repo.remove_from_watchlist(current_user.id, symbol, exchange_id)
    
    return {
        "message": f"{symbol} removed from watchlist",
        "watchlist": watchlist
    }


@router.get("/watchlist")
async def get_watchlist(
    current_user: User = Depends(get_current_user_optional)
):
    """
    Get user's watchlist with current prices
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    watchlist = await market_repo.get_watchlist(current_user.id)
    
    # Enrich with current prices
    enriched = []
    for item in watchlist:
        ticker = await exchange_manager.get_ticker(item['symbol'], item['exchange_id'])
        if ticker:
            item['current_price'] = ticker['last']
            item['change_24h'] = ticker['change_percent']
        enriched.append(item)
    
    return {
        "watchlist": enriched
    }


@router.get("/popular")
@cache_response(ttl=3600)
async def get_popular_symbols(
    limit: int = Query(20, ge=1, le=100)
):
    """
    Get most popular symbols based on trading volume
    """
    popular = await market_repo.get_popular_symbols(limit)
    
    return {
        "popular": popular
    }


@router.get("/recently-added")
@cache_response(ttl=3600)
async def get_recently_added(
    limit: int = Query(20, ge=1, le=100)
):
    """
    Get recently added symbols
    """
    recent = await market_repo.get_recently_added(limit)
    
    return recent


@router.get("/volume-leaders")
@cache_response(ttl=300)
async def get_volume_leaders(
    exchange_id: Optional[str] = "binance",
    limit: int = Query(20, ge=1, le=100)
):
    """
    Get volume leaders
    """
    leaders = await data_collector.get_volume_leaders(exchange_id, limit)
    
    return leaders


@router.get("/price-alerts")
async def get_price_alerts(
    current_user: User = Depends(get_current_user_optional)
):
    """
    Get price alerts for watchlist
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    watchlist = await market_repo.get_watchlist(current_user.id)
    
    alerts = []
    for item in watchlist:
        ticker = await exchange_manager.get_ticker(item['symbol'], item['exchange_id'])
        if ticker:
            alerts.append({
                "symbol": item['symbol'],
                "exchange": item['exchange_id'],
                "current_price": ticker['last'],
                "change_24h": ticker['change_percent'],
                "high_24h": ticker['high'],
                "low_24h": ticker['low'],
                "volume_24h": ticker['volume']
            })
    
    return alerts


@router.get("/market-summary")
@cache_response(ttl=60)
async def get_market_summary(
    exchange_id: Optional[str] = "binance"
):
    """
    Get overall market summary
    """
    total_markets = await market_repo.get_market_count(exchange_id=exchange_id)
    total_volume = await data_collector.get_total_volume(exchange_id)
    
    # Get top movers
    gainers = await data_collector.get_top_gainers(5, exchange_id)
    losers = await data_collector.get_top_losers(5, exchange_id)
    volume = await data_collector.get_top_volume(5, exchange_id)
    
    # Get market dominance
    dominance = await data_collector.get_market_dominance()
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "exchange": exchange_id,
        "total_markets": total_markets,
        "total_volume_24h": total_volume,
        "market_dominance": dominance,
        "top_gainers": gainers,
        "top_losers": losers,
        "top_volume": volume
    }