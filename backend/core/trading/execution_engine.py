"""
Real-time Trading Execution Engine
High-frequency trading with smart order routing and risk management
"""

import asyncio
import time
import uuid
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import numpy as np
from datetime import datetime, timedelta
import json
import threading
import queue

import redis.asyncio as redis
from prometheus_client import Counter, Histogram, Gauge

from ...utils.logger import get_logger
from ...utils.metrics import track_execution
from ...config import settings
from ..market.exchange_manager import ExchangeManager
from ..risk.risk_manager import RiskManager
from ..analysis.technical.indicators import TechnicalIndicators

logger = get_logger(__name__)

# Metrics
orders_placed = Counter('orders_placed_total', 'Total orders placed', ['exchange', 'side'])
orders_filled = Counter('orders_filled_total', 'Total orders filled', ['exchange', 'side'])
orders_cancelled = Counter('orders_cancelled_total', 'Total orders cancelled', ['exchange'])
execution_latency = Histogram('execution_latency_seconds', 'Order execution latency')
slippage_gauge = Gauge('execution_slippage', 'Order execution slippage', ['symbol'])
active_orders = Gauge('active_orders', 'Number of active orders')


class OrderType(Enum):
    """Order types supported"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TRAILING_STOP = "TRAILING_STOP"
    OCO = "OCO"  # One-Cancels-Other
    ICEBERG = "ICEBERG"
    TWAP = "TWAP"  # Time-Weighted Average Price
    VWAP = "VWAP"  # Volume-Weighted Average Price
    POV = "POV"    # Percentage of Volume


class OrderSide(Enum):
    """Order sides"""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    """Order statuses"""
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class TimeInForce(Enum):
    """Time in force options"""
    GTC = "GTC"  # Good Till Cancelled
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill
    DAY = "DAY"  # Day order


@dataclass
class Order:
    """Order data structure"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    client_order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = ""
    side: OrderSide = None
    type: OrderType = OrderType.MARKET
    quantity: float = 0.0
    price: Optional[float] = None
    stop_price: Optional[float] = None
    limit_price: Optional[float] = None
    iceberg_qty: Optional[float] = None
    time_in_force: TimeInForce = TimeInForce.GTC
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    remaining_quantity: float = 0.0
    executed_price: Optional[float] = None
    commissions: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    executed_at: Optional[datetime] = None
    exchange: str = "binance"
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'client_order_id': self.client_order_id,
            'symbol': self.symbol,
            'side': self.side.value if self.side else None,
            'type': self.type.value if self.type else None,
            'quantity': self.quantity,
            'price': self.price,
            'stop_price': self.stop_price,
            'limit_price': self.limit_price,
            'iceberg_qty': self.iceberg_qty,
            'time_in_force': self.time_in_force.value if self.time_in_force else None,
            'status': self.status.value if self.status else None,
            'filled_quantity': self.filled_quantity,
            'remaining_quantity': self.remaining_quantity,
            'executed_price': self.executed_price,
            'commissions': self.commissions,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'executed_at': self.executed_at.isoformat() if self.executed_at else None,
            'exchange': self.exchange,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Order':
        """Create from dictionary"""
        order = cls(
            id=data.get('id', str(uuid.uuid4())),
            client_order_id=data.get('client_order_id', str(uuid.uuid4())),
            symbol=data['symbol'],
            side=OrderSide(data['side']) if data.get('side') else None,
            type=OrderType(data['type']) if data.get('type') else None,
            quantity=data['quantity'],
            price=data.get('price'),
            stop_price=data.get('stop_price'),
            limit_price=data.get('limit_price'),
            iceberg_qty=data.get('iceberg_qty'),
            time_in_force=TimeInForce(data['time_in_force']) if data.get('time_in_force') else None,
            status=OrderStatus(data['status']) if data.get('status') else None,
            filled_quantity=data.get('filled_quantity', 0),
            remaining_quantity=data.get('remaining_quantity', 0),
            executed_price=data.get('executed_price'),
            commissions=data.get('commissions', 0),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else datetime.now(),
            updated_at=datetime.fromisoformat(data['updated_at']) if data.get('updated_at') else datetime.now(),
            executed_at=datetime.fromisoformat(data['executed_at']) if data.get('executed_at') else None,
            exchange=data.get('exchange', 'binance'),
            metadata=data.get('metadata', {})
        )
        return order


@dataclass
class Fill:
    """Order fill data"""
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float
    commission_asset: str
    trade_id: str
    timestamp: datetime
    exchange: str


class OrderBook:
    """Local order book for smart routing"""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.bids = []  # List of (price, quantity)
        self.asks = []  # List of (price, quantity)
        self.last_update = 0
        self.sequence = 0
    
    def update(self, bids: List[Tuple[float, float]], asks: List[Tuple[float, float]]):
        """Update order book"""
        self.bids = sorted(bids, key=lambda x: -x[0])  # Descending price
        self.asks = sorted(asks, key=lambda x: x[0])   # Ascending price
        self.last_update = time.time()
        self.sequence += 1
    
    def get_best_bid(self) -> Optional[Tuple[float, float]]:
        """Get best bid"""
        return self.bids[0] if self.bids else None
    
    def get_best_ask(self) -> Optional[Tuple[float, float]]:
        """Get best ask"""
        return self.asks[0] if self.asks else None
    
    def get_mid_price(self) -> Optional[float]:
        """Get mid price"""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        if best_bid and best_ask:
            return (best_bid[0] + best_ask[0]) / 2
        return None
    
    def get_spread(self) -> Optional[float]:
        """Get bid-ask spread"""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        if best_bid and best_ask:
            return best_ask[0] - best_bid[0]
        return None
    
    def get_market_impact(self, quantity: float, side: OrderSide) -> float:
        """Estimate market impact for order"""
        if side == OrderSide.BUY:
            levels = self.asks
        else:
            levels = self.bids
        
        remaining = quantity
        weighted_price = 0
        total_qty = 0
        
        for price, qty in levels:
            take = min(remaining, qty)
            weighted_price += price * take
            total_qty += take
            remaining -= take
            if remaining <= 0:
                break
        
        if total_qty > 0:
            avg_price = weighted_price / total_qty
            mid_price = self.get_mid_price()
            if mid_price:
                return abs(avg_price - mid_price) / mid_price
        return 0


class SmartOrderRouter:
    """Smart order routing across multiple exchanges"""
    
    def __init__(self, exchange_manager: ExchangeManager):
        self.exchange_manager = exchange_manager
        self.order_books: Dict[str, Dict[str, OrderBook]] = {}  # exchange -> symbol -> OrderBook
        self.exchange_latency: Dict[str, float] = {}  # Historical latency
        self.exchange_fees: Dict[str, Dict[str, float]] = {}  # Maker/taker fees
        self.exchange_health: Dict[str, bool] = {}
        
    async def update_order_book(self, exchange: str, symbol: str, 
                                bids: List[Tuple[float, float]], 
                                asks: List[Tuple[float, float]]):
        """Update order book for an exchange"""
        if exchange not in self.order_books:
            self.order_books[exchange] = {}
        
        if symbol not in self.order_books[exchange]:
            self.order_books[exchange][symbol] = OrderBook(symbol)
        
        self.order_books[exchange][symbol].update(bids, asks)
    
    def get_best_price(self, symbol: str, side: OrderSide, 
                       exchanges: Optional[List[str]] = None) -> Dict:
        """Get best price across exchanges"""
        best_price = None
        best_exchange = None
        best_liquidity = 0
        results = {}
        
        target_exchanges = exchanges or list(self.order_books.keys())
        
        for exchange in target_exchanges:
            if exchange not in self.order_books:
                continue
            if symbol not in self.order_books[exchange]:
                continue
            
            ob = self.order_books[exchange][symbol]
            if side == OrderSide.BUY:
                price, qty = ob.get_best_ask() or (float('inf'), 0)
                if price < best_price if best_price else True:
                    best_price = price
                    best_exchange = exchange
                    best_liquidity = qty
            else:
                price, qty = ob.get_best_bid() or (0, 0)
                if price > best_price if best_price else True:
                    best_price = price
                    best_exchange = exchange
                    best_liquidity = qty
            
            results[exchange] = {
                'price': price,
                'liquidity': qty,
                'latency': self.exchange_latency.get(exchange, 0),
                'fee': self.exchange_fees.get(exchange, {}).get('taker', 0.001)
            }
        
        if best_exchange:
            results['best'] = {
                'exchange': best_exchange,
                'price': best_price,
                'liquidity': best_liquidity
            }
        
        return results
    
    def calculate_smart_route(self, order: Order) -> List[Dict]:
        """Calculate optimal routing for order"""
        routes = []
        
        # Get quotes from all exchanges
        quotes = self.get_best_price(order.symbol, order.side)
        
        if not quotes:
            return routes
        
        # Sort by effective price including fees
        for exchange, quote in quotes.items():
            if exchange == 'best':
                continue
            
            fee = self.exchange_fees.get(exchange, {}).get('taker', 0.001)
            if order.side == OrderSide.BUY:
                effective_price = quote['price'] * (1 + fee)
            else:
                effective_price = quote['price'] * (1 - fee)
            
            routes.append({
                'exchange': exchange,
                'price': quote['price'],
                'effective_price': effective_price,
                'liquidity': quote['liquidity'],
                'latency': quote['latency'],
                'fee': fee,
                'score': self._calculate_route_score(quote, fee)
            })
        
        # Sort by score
        routes.sort(key=lambda x: x['score'], reverse=True)
        
        return routes
    
    def _calculate_route_score(self, quote: Dict, fee: float) -> float:
        """Calculate route score based on multiple factors"""
        price_score = 1 / (1 + quote['price'])  # Better price = higher score
        liquidity_score = min(quote['liquidity'] / 10, 1)  # Normalize liquidity
        latency_score = 1 / (1 + quote['latency'])  # Lower latency = higher score
        fee_score = 1 / (1 + fee * 10)  # Lower fee = higher score
        
        # Weighted combination
        score = (
            price_score * 0.4 +
            liquidity_score * 0.3 +
            latency_score * 0.2 +
            fee_score * 0.1
        )
        
        return score
    
    async def execute_smart_order(self, order: Order) -> List[Fill]:
        """Execute order using smart routing"""
        fills = []
        remaining_qty = order.quantity
        
        # Calculate optimal routes
        routes = self.calculate_smart_route(order)
        
        for route in routes:
            if remaining_qty <= 0:
                break
            
            # Calculate quantity for this route
            route_qty = min(remaining_qty, route['liquidity'] * 0.5)  # Use max 50% of liquidity
            
            if route_qty <= 0:
                continue
            
            # Execute on exchange
            try:
                exchange = self.exchange_manager.connections.get(route['exchange'])
                if not exchange or not exchange.connected:
                    continue
                
                # Place order
                exchange_order = await exchange.place_order(
                    symbol=order.symbol,
                    side=order.side.value.lower(),
                    quantity=route_qty,
                    order_type='market'
                )
                
                if exchange_order and 'fills' in exchange_order:
                    for fill_data in exchange_order['fills']:
                        fill = Fill(
                            order_id=order.id,
                            symbol=order.symbol,
                            side=order.side,
                            quantity=float(fill_data['qty']),
                            price=float(fill_data['price']),
                            commission=float(fill_data.get('commission', 0)),
                            commission_asset=fill_data.get('commissionAsset', 'USDT'),
                            trade_id=fill_data['tradeId'],
                            timestamp=datetime.now(),
                            exchange=route['exchange']
                        )
                        fills.append(fill)
                        remaining_qty -= fill.quantity
                
                # Update metrics
                orders_placed.labels(exchange=route['exchange'], side=order.side.value).inc()
                
            except Exception as e:
                logger.error(f"Error executing on {route['exchange']}: {e}")
                continue
        
        return fills


class ExecutionEngine:
    """
    High-Frequency Trading Execution Engine
    Handles order placement, monitoring, and risk management
    """
    
    def __init__(self, exchange_manager: ExchangeManager, risk_manager: RiskManager):
        self.exchange_manager = exchange_manager
        self.risk_manager = risk_manager
        self.router = SmartOrderRouter(exchange_manager)
        
        # Order management
        self.orders: Dict[str, Order] = {}
        self.active_orders: Dict[str, Order] = {}
        self.order_history: deque = deque(maxlen=10000)
        self.fills: List[Fill] = []
        
        # Queues
        self.order_queue = asyncio.Queue()
        self.fill_queue = asyncio.Queue()
        
        # Locks
        self.order_lock = asyncio.Lock()
        
        # Statistics
        self.total_orders = 0
        self.total_volume = 0
        self.total_fees = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        # Background tasks
        self.tasks = []
        self.running = False
        
        logger.info("⚡ Initialized High-Frequency Trading Execution Engine")
    
    async def start(self):
        """Start execution engine"""
        self.running = True
        
        # Start background tasks
        self.tasks.extend([
            asyncio.create_task(self._process_orders()),
            asyncio.create_task(self._monitor_orders()),
            asyncio.create_task(self._update_order_books()),
            asyncio.create_task(self._collect_metrics())
        ])
        
        logger.info("✅ Execution engine started")
    
    async def stop(self):
        """Stop execution engine"""
        self.running = False
        
        # Cancel all tasks
        for task in self.tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Cancel all active orders
        await self.cancel_all_orders()
        
        logger.info("🛑 Execution engine stopped")
    
    async def place_order(self, order: Order) -> str:
        """Place a new order"""
        # Pre-trade risk check
        if not await self.risk_manager.check_order(order):
            order.status = OrderStatus.REJECTED
            order.metadata['reject_reason'] = 'Risk check failed'
            logger.warning(f"Order {order.id} rejected by risk manager")
            return order.id
        
        # Check exchange connection
        if order.exchange not in self.exchange_manager.connections:
            order.status = OrderStatus.REJECTED
            order.metadata['reject_reason'] = 'Exchange not connected'
            logger.warning(f"Order {order.id} rejected: exchange not connected")
            return order.id
        
        # Add to order queue
        order.status = OrderStatus.PENDING
        async with self.order_lock:
            self.orders[order.id] = order
        
        await self.order_queue.put(order)
        
        logger.info(f"📤 Order queued: {order.id} - {order.side.value} {order.quantity} {order.symbol}")
        
        return order.id
    
    async def place_market_order(self, symbol: str, side: OrderSide, 
                                  quantity: float, exchange: str = 'binance',
                                  metadata: Dict = None) -> str:
        """Place a market order"""
        order = Order(
            symbol=symbol,
            side=side,
            type=OrderType.MARKET,
            quantity=quantity,
            exchange=exchange,
            metadata=metadata or {}
        )
        return await self.place_order(order)
    
    async def place_limit_order(self, symbol: str, side: OrderSide,
                                 quantity: float, price: float,
                                 exchange: str = 'binance',
                                 time_in_force: TimeInForce = TimeInForce.GTC,
                                 metadata: Dict = None) -> str:
        """Place a limit order"""
        order = Order(
            symbol=symbol,
            side=side,
            type=OrderType.LIMIT,
            quantity=quantity,
            price=price,
            time_in_force=time_in_force,
            exchange=exchange,
            metadata=metadata or {}
        )
        return await self.place_order(order)
    
    async def place_stop_order(self, symbol: str, side: OrderSide,
                                quantity: float, stop_price: float,
                                limit_price: Optional[float] = None,
                                exchange: str = 'binance',
                                metadata: Dict = None) -> str:
        """Place a stop or stop-limit order"""
        order_type = OrderType.STOP_LIMIT if limit_price else OrderType.STOP
        order = Order(
            symbol=symbol,
            side=side,
            type=order_type,
            quantity=quantity,
            stop_price=stop_price,
            limit_price=limit_price,
            exchange=exchange,
            metadata=metadata or {}
        )
        return await self.place_order(order)
    
    async def place_trailing_stop(self, symbol: str, side: OrderSide,
                                   quantity: float, trail_percent: float,
                                   exchange: str = 'binance',
                                   metadata: Dict = None) -> str:
        """Place a trailing stop order"""
        # Get current price
        connection = self.exchange_manager.connections.get(exchange)
        if not connection:
            raise ValueError(f"Exchange {exchange} not connected")
        
        ticker = await connection.get_ticker(symbol)
        current_price = ticker['last_price']
        
        if side == OrderSide.BUY:
            stop_price = current_price * (1 - trail_percent / 100)
        else:
            stop_price = current_price * (1 + trail_percent / 100)
        
        order = Order(
            symbol=symbol,
            side=side,
            type=OrderType.TRAILING_STOP,
            quantity=quantity,
            stop_price=stop_price,
            exchange=exchange,
            metadata={
                'trail_percent': trail_percent,
                'initial_price': current_price
            }
        )
        
        return await self.place_order(order)
    
    async def place_twap_order(self, symbol: str, side: OrderSide,
                                total_quantity: float, duration_minutes: int,
                                slices: int = 10, exchange: str = 'binance',
                                metadata: Dict = None) -> List[str]:
        """Place a TWAP order (split into multiple orders over time)"""
        order_ids = []
        slice_quantity = total_quantity / slices
        interval = (duration_minutes * 60) / slices
        
        for i in range(slices):
            order = Order(
                symbol=symbol,
                side=side,
                type=OrderType.TWAP,
                quantity=slice_quantity,
                exchange=exchange,
                metadata={
                    'twap_slice': i + 1,
                    'total_slices': slices,
                    'parent_order': 'twap_' + str(uuid.uuid4())
                }
            )
            order_id = await self.place_order(order)
            order_ids.append(order_id)
            
            if i < slices - 1:
                await asyncio.sleep(interval)
        
        return order_ids
    
    async def place_vwap_order(self, symbol: str, side: OrderSide,
                                total_quantity: float, exchange: str = 'binance',
                                metadata: Dict = None) -> str:
        """Place a VWAP order (smart routing based on volume profile)"""
        # Get volume profile
        klines = await self.exchange_manager.get_klines(symbol, '1h', 24, exchange)
        
        if klines:
            volumes = [k['volume'] for k in klines]
            total_volume = sum(volumes)
            volume_profile = [v / total_volume for v in volumes]
            
            order = Order(
                symbol=symbol,
                side=side,
                type=OrderType.VWAP,
                quantity=total_quantity,
                exchange=exchange,
                metadata={
                    'volume_profile': volume_profile,
                    'expected_price': None  # Will be calculated during execution
                }
            )
        else:
            order = Order(
                symbol=symbol,
                side=side,
                type=OrderType.MARKET,
                quantity=total_quantity,
                exchange=exchange,
                metadata=metadata or {}
            )
        
        return await self.place_order(order)
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an active order"""
        async with self.order_lock:
            if order_id not in self.active_orders:
                logger.warning(f"Order {order_id} not found or not active")
                return False
            
            order = self.active_orders[order_id]
            
            try:
                connection = self.exchange_manager.connections.get(order.exchange)
                if connection:
                    await connection.cancel_order(order.symbol, order.client_order_id)
                
                order.status = OrderStatus.CANCELLED
                order.updated_at = datetime.now()
                
                del self.active_orders[order_id]
                self.order_history.append(order)
                
                orders_cancelled.labels(exchange=order.exchange).inc()
                active_orders.set(len(self.active_orders))
                
                logger.info(f"✅ Order cancelled: {order_id}")
                return True
                
            except Exception as e:
                logger.error(f"Error cancelling order {order_id}: {e}")
                return False
    
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """Cancel all active orders (optionally for specific symbol)"""
        cancelled = 0
        
        async with self.order_lock:
            order_ids = list(self.active_orders.keys())
            
            for order_id in order_ids:
                order = self.active_orders.get(order_id)
                if order and (not symbol or order.symbol == symbol):
                    if await self.cancel_order(order_id):
                        cancelled += 1
        
        logger.info(f"✅ Cancelled {cancelled} orders")
        return cancelled
    
    async def get_order(self, order_id: str) -> Optional[Order]:
        """Get order details"""
        async with self.order_lock:
            if order_id in self.active_orders:
                return self.active_orders[order_id]
            
            # Check history
            for order in self.order_history:
                if order.id == order_id:
                    return order
        
        return None
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all open orders"""
        async with self.order_lock:
            orders = list(self.active_orders.values())
            if symbol:
                orders = [o for o in orders if o.symbol == symbol]
            return orders
    
    async def _process_orders(self):
        """Background task to process orders from queue"""
        while self.running:
            try:
                order = await self.order_queue.get()
                
                # Smart routing for market orders
                if order.type == OrderType.MARKET:
                    fills = await self.router.execute_smart_order(order)
                    
                    if fills:
                        total_qty = sum(f.quantity for f in fills)
                        avg_price = sum(f.price * f.quantity for f in fills) / total_qty
                        
                        order.status = OrderStatus.FILLED
                        order.filled_quantity = total_qty
                        order.executed_price = avg_price
                        order.executed_at = datetime.now()
                        order.updated_at = datetime.now()
                        
                        for fill in fills:
                            self.fills.append(fill)
                            await self.fill_queue.put(fill)
                        
                        # Update metrics
                        orders_filled.labels(exchange=order.exchange, side=order.side.value).inc()
                        self.total_orders += 1
                        self.total_volume += total_qty * avg_price
                        
                        logger.info(f"✅ Order filled: {order.id} - {avg_price:.2f} @ {total_qty}")
                        
                    else:
                        order.status = OrderStatus.FAILED
                        logger.error(f"❌ Order failed: {order.id}")
                
                # Limit orders
                elif order.type == OrderType.LIMIT:
                    connection = self.exchange_manager.connections.get(order.exchange)
                    if connection:
                        try:
                            exchange_order = await connection.place_limit_order(
                                symbol=order.symbol,
                                side=order.side.value.lower(),
                                quantity=order.quantity,
                                price=order.price,
                                time_in_force=order.time_in_force.value
                            )
                            
                            if exchange_order:
                                order.client_order_id = exchange_order.get('clientOrderId', order.client_order_id)
                                order.status = OrderStatus.OPEN
                                async with self.order_lock:
                                    self.active_orders[order.id] = order
                                
                                active_orders.set(len(self.active_orders))
                                orders_placed.labels(exchange=order.exchange, side=order.side.value).inc()
                                
                                logger.info(f"📈 Limit order placed: {order.id} at {order.price}")
                            else:
                                order.status = OrderStatus.REJECTED
                                logger.warning(f"Order {order.id} rejected by exchange")
                                
                        except Exception as e:
                            order.status = OrderStatus.FAILED
                            order.metadata['error'] = str(e)
                            logger.error(f"Error placing limit order {order.id}: {e}")
                
                # Other order types
                else:
                    logger.warning(f"Unsupported order type: {order.type}")
                    order.status = OrderStatus.REJECTED
                
                # Update order in history
                self.order_history.append(order)
                
            except Exception as e:
                logger.error(f"Error processing order: {e}")
                await asyncio.sleep(0.1)
    
    async def _monitor_orders(self):
        """Background task to monitor active orders"""
        while self.running:
            try:
                async with self.order_lock:
                    for order_id, order in list(self.active_orders.items()):
                        # Check if order should be updated from exchange
                        connection = self.exchange_manager.connections.get(order.exchange)
                        if connection:
                            try:
                                exchange_order = await connection.get_order(
                                    order.symbol, order.client_order_id
                                )
                                
                                if exchange_order:
                                    # Update order status
                                    old_status = order.status
                                    
                                    if exchange_order['status'] == 'FILLED':
                                        order.status = OrderStatus.FILLED
                                        order.filled_quantity = float(exchange_order['executedQty'])
                                        order.executed_price = float(exchange_order['avgPrice'])
                                        order.executed_at = datetime.now()
                                        
                                        del self.active_orders[order_id]
                                        
                                        orders_filled.labels(exchange=order.exchange, side=order.side.value).inc()
                                        logger.info(f"✅ Order filled (monitor): {order_id}")
                                    
                                    elif exchange_order['status'] == 'PARTIALLY_FILLED':
                                        order.status = OrderStatus.PARTIALLY_FILLED
                                        order.filled_quantity = float(exchange_order['executedQty'])
                                    
                                    elif exchange_order['status'] in ['CANCELED', 'EXPIRED', 'REJECTED']:
                                        order.status = OrderStatus.CANCELLED
                                        del self.active_orders[order_id]
                                    
                                    if old_status != order.status:
                                        order.updated_at = datetime.now()
                                        self.order_history.append(order)
                                        
                            except Exception as e:
                                logger.error(f"Error monitoring order {order_id}: {e}")
                
                active_orders.set(len(self.active_orders))
                await asyncio.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"Error in order monitor: {e}")
                await asyncio.sleep(1)
    
    async def _update_order_books(self):
        """Background task to update order books"""
        while self.running:
            try:
                # Get top symbols
                symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']  # Could be dynamic
                
                for exchange_name, connection in self.exchange_manager.connections.items():
                    if not connection.connected:
                        continue
                    
                    for symbol in symbols:
                        try:
                            # Get order book
                            orderbook = await connection.get_orderbook(symbol, limit=10)
                            
                            if orderbook:
                                bids = [(float(b[0]), float(b[1])) for b in orderbook['bids']]
                                asks = [(float(a[0]), float(a[1])) for a in orderbook['asks']]
                                
                                await self.router.update_order_book(exchange_name, symbol, bids, asks)
                                
                        except Exception as e:
                            logger.error(f"Error updating order book for {exchange_name}/{symbol}: {e}")
                    
                    await asyncio.sleep(0.1)  # Small delay between exchanges
                
                await asyncio.sleep(1)  # Update every second
                
            except Exception as e:
                logger.error(f"Error in order book updater: {e}")
                await asyncio.sleep(1)
    
    async def _collect_metrics(self):
        """Background task to collect and report metrics"""
        while self.running:
            try:
                # Calculate win rate
                total_closed = self.winning_trades + self.losing_trades
                if total_closed > 0:
                    win_rate = (self.winning_trades / total_closed) * 100
                else:
                    win_rate = 0
                
                # Log metrics
                logger.info(f"📊 Execution Metrics:")
                logger.info(f"   Total Orders: {self.total_orders}")
                logger.info(f"   Total Volume: ${self.total_volume:,.2f}")
                logger.info(f"   Total Fees: ${self.total_fees:,.2f}")
                logger.info(f"   Active Orders: {len(self.active_orders)}")
                logger.info(f"   Win Rate: {win_rate:.1f}%")
                
                await asyncio.sleep(60)  # Report every minute
                
            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")
                await asyncio.sleep(60)


class OrderManager:
    """High-level order management with strategy integration"""
    
    def __init__(self, execution_engine: ExecutionEngine):
        self.execution_engine = execution_engine
        self.strategies = {}
        self.position_tracker = {}
        
    async def execute_strategy_signal(self, strategy_name: str, signal: Dict) -> List[str]:
        """Execute trading signal from strategy"""
        order_ids = []
        
        symbol = signal['symbol']
        action = signal['action']
        confidence = signal.get('confidence', 1.0)
        
        # Calculate position size based on confidence
        base_size = signal.get('quantity', 0.01)
        quantity = base_size * confidence
        
        if action == 'BUY':
            order_id = await self.execution_engine.place_market_order(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                metadata={'strategy': strategy_name, 'signal': signal}
            )
            order_ids.append(order_id)
            
        elif action == 'SELL':
            order_id = await self.execution_engine.place_market_order(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                metadata={'strategy': strategy_name, 'signal': signal}
            )
            order_ids.append(order_id)
            
        elif action == 'CLOSE':
            # Close all positions for symbol
            open_orders = await self.execution_engine.get_open_orders(symbol)
            for order in open_orders:
                await self.execution_engine.cancel_order(order.id)
        
        elif action == 'HEDGE':
            # Place hedge orders
            pass
        
        return order_ids
    
    async def execute_bracket_order(self, symbol: str, side: OrderSide,
                                     entry_price: float, quantity: float,
                                     take_profit: float, stop_loss: float,
                                     exchange: str = 'binance') -> List[str]:
        """Execute bracket order (entry + take profit + stop loss)"""
        order_ids = []
        
        # Entry order
        entry_id = await self.execution_engine.place_limit_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=entry_price,
            exchange=exchange,
            time_in_force=TimeInForce.GTC
        )
        order_ids.append(entry_id)
        
        if entry_id:
            # Take profit order (opposite side)
            tp_side = OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY
            tp_id = await self.execution_engine.place_limit_order(
                symbol=symbol,
                side=tp_side,
                quantity=quantity,
                price=take_profit,
                exchange=exchange,
                time_in_force=TimeInForce.GTC,
                metadata={'parent_order': entry_id, 'type': 'take_profit'}
            )
            order_ids.append(tp_id)
            
            # Stop loss order (opposite side)
            sl_id = await self.execution_engine.place_stop_order(
                symbol=symbol,
                side=tp_side,
                quantity=quantity,
                stop_price=stop_loss,
                limit_price=stop_loss * 0.99 if side == OrderSide.BUY else stop_loss * 1.01,
                exchange=exchange,
                metadata={'parent_order': entry_id, 'type': 'stop_loss'}
            )
            order_ids.append(sl_id)
        
        return order_ids
    
    async def execute_scalping_strategy(self, symbol: str, quantity: float,
                                         target_profit: float, stop_loss: float,
                                         max_trades: int = 10) -> List[str]:
        """Execute scalping strategy with multiple quick trades"""
        order_ids = []
        
        for i in range(max_trades):
            # Get current price
            price = await self._get_current_price(symbol)
            
            if not price:
                continue
            
            # Place buy order
            buy_id = await self.execution_engine.place_market_order(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                metadata={'strategy': 'scalping', 'trade_number': i + 1}
            )
            order_ids.append(buy_id)
            
            # Wait for fill
            await asyncio.sleep(1)
            
            # Place sell order at profit target
            sell_price = price * (1 + target_profit / 100)
            sell_id = await self.execution_engine.place_limit_order(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                price=sell_price,
                time_in_force=TimeInForce.IOC,
                metadata={'strategy': 'scalping', 'trade_number': i + 1}
            )
            order_ids.append(sell_id)
            
            # Place stop loss
            stop_price = price * (1 - stop_loss / 100)
            stop_id = await self.execution_engine.place_stop_order(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                stop_price=stop_price,
                metadata={'strategy': 'scalping', 'trade_number': i + 1}
            )
            order_ids.append(stop_id)
            
            # Small delay between trades
            await asyncio.sleep(0.5)
        
        return order_ids
    
    async def execute_grid_trading(self, symbol: str, grid_levels: int,
                                    lower_price: float, upper_price: float,
                                    quantity_per_grid: float) -> List[str]:
        """Execute grid trading strategy"""
        order_ids = []
        
        # Calculate grid levels
        price_step = (upper_price - lower_price) / grid_levels
        grid_prices = [lower_price + i * price_step for i in range(grid_levels + 1)]
        
        # Place buy orders at lower levels
        for i, price in enumerate(grid_prices[:-1]):
            order_id = await self.execution_engine.place_limit_order(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity_per_grid,
                price=price,
                time_in_force=TimeInForce.GTC,
                metadata={'strategy': 'grid', 'level': i, 'type': 'buy'}
            )
            order_ids.append(order_id)
        
        # Place sell orders at higher levels
        for i, price in enumerate(grid_prices[1:], 1):
            order_id = await self.execution_engine.place_limit_order(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity_per_grid,
                price=price,
                time_in_force=TimeInForce.GTC,
                metadata={'strategy': 'grid', 'level': i, 'type': 'sell'}
            )
            order_ids.append(order_id)
        
        return order_ids
    
    async def execute_dca_strategy(self, symbol: str, total_quantity: float,
                                     entry_price: float, num_entries: int,
                                     price_step_percent: float) -> List[str]:
        """Execute Dollar Cost Averaging strategy"""
        order_ids = []
        
        quantity_per_entry = total_quantity / num_entries
        
        for i in range(num_entries):
            price = entry_price * (1 - i * price_step_percent / 100)
            
            order_id = await self.execution_engine.place_limit_order(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity_per_entry,
                price=price,
                time_in_force=TimeInForce.GTC,
                metadata={'strategy': 'dca', 'entry_number': i + 1}
            )
            order_ids.append(order_id)
            
            # Stagger entries
            await asyncio.sleep(1)
        
        return order_ids
    
    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for symbol"""
        try:
            connection = self.execution_engine.exchange_manager.connections.get('binance')
            if connection:
                ticker = await connection.get_ticker(symbol)
                return ticker['last_price']
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
        return None
    
    async def get_position_summary(self, symbol: Optional[str] = None) -> Dict:
        """Get summary of current positions"""
        positions = {}
        
        orders = await self.execution_engine.get_open_orders(symbol)
        
        for order in orders:
            if order.symbol not in positions:
                positions[order.symbol] = {
                    'buy_orders': 0,
                    'sell_orders': 0,
                    'buy_quantity': 0,
                    'sell_quantity': 0,
                    'buy_value': 0,
                    'sell_value': 0
                }
            
            if order.side == OrderSide.BUY:
                positions[order.symbol]['buy_orders'] += 1
                positions[order.symbol]['buy_quantity'] += order.remaining_quantity
                positions[order.symbol]['buy_value'] += order.remaining_quantity * (order.price or 0)
            else:
                positions[order.symbol]['sell_orders'] += 1
                positions[order.symbol]['sell_quantity'] += order.remaining_quantity
                positions[order.symbol]['sell_value'] += order.remaining_quantity * (order.price or 0)
        
        return positions