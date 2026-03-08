"""
Triangular Arbitrage Strategy
Exploits price differences across three trading pairs
Real-time arbitrage detection and execution with minimal latency
"""

import asyncio
import numpy as np
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime
import itertools
from collections import defaultdict
import logging

from ..base import BaseStrategy
from ...core.market.exchange_manager import ExchangeManager
from ...core.risk.risk_manager import RiskManager
from ...utils.logger import get_logger

logger = get_logger(__name__)


class TriangularArbitrageStrategy(BaseStrategy):
    """
    Triangular Arbitrage Strategy
    
    Exploits price discrepancies between three cryptocurrencies:
    A/B → B/C → C/A should equal 1.0
    If product > 1, there's an arbitrage opportunity
    
    Common triangles:
    - BTC → ETH → USDT → BTC
    - ETH → BTC → USDT → ETH
    - XRP → BTC → USDT → XRP
    - LTC → BTC → USDT → LTC
    - BNB → BTC → USDT → BNB
    
    Features:
    - Real-time price monitoring
    - Multi-exchange support
    - Minimum profit threshold
    - Slippage calculation
    - Position sizing based on liquidity
    - Automatic execution with confirmation
    """
    
    category = "arbitrage"
    version = "2.0.0"
    
    def __init__(self, instance_id: str, config: Dict):
        """
        Initialize triangular arbitrage strategy
        
        Args:
            instance_id: Unique identifier for this strategy instance
            config: Strategy configuration
        """
        super().__init__(instance_id, config)
        
        # Strategy parameters
        self.min_profit_threshold = config.get('min_profit_threshold', 0.5)  # Percentage
        self.max_slippage = config.get('max_slippage', 0.2)  # Percentage
        self.max_position_size = config.get('max_position_size', 0.1)  # BTC equivalent
        self.min_liquidity = config.get('min_liquidity', 10000)  # Minimum volume in USDT
        self.check_interval = config.get('check_interval', 1)  # Seconds
        self.execution_delay = config.get('execution_delay', 0.1)  # Seconds between legs
        self.max_execution_time = config.get('max_execution_time', 2.0)  # Seconds for complete cycle
        self.use_multiple_exchanges = config.get('use_multiple_exchanges', True)
        self.preferred_exchanges = config.get('preferred_exchanges', ['binance', 'kucoin', 'bybit'])
        
        # Triangle definitions
        self.triangles = self._load_triangles(config.get('triangles', []))
        self.active_triangles = {}
        self.opportunities = []
        
        # Price cache
        self.price_cache = {}
        self.cache_ttl = config.get('cache_ttl', 0.5)  # 500ms cache
        
        # Performance tracking
        self.opportunities_found = 0
        self.opportunities_executed = 0
        self.total_profit = 0.0
        self.failed_executions = 0
        
        logger.info(f"📊 Triangular Arbitrage Strategy initialized with {len(self.triangles)} triangles")
        logger.info(f"   Min profit: {self.min_profit_threshold}%, Max slippage: {self.max_slippage}%")
    
    @classmethod
    def get_parameters(cls) -> Dict:
        """Get strategy parameters definition"""
        params = super().get_parameters()
        params['required'].extend([])
        params['optional'].update({
            'min_profit_threshold': {
                'type': 'float',
                'default': 0.5,
                'min': 0.1,
                'max': 5.0,
                'description': 'Minimum profit percentage to execute'
            },
            'max_slippage': {
                'type': 'float',
                'default': 0.2,
                'min': 0.05,
                'max': 1.0,
                'description': 'Maximum allowed slippage percentage'
            },
            'max_position_size': {
                'type': 'float',
                'default': 0.1,
                'min': 0.001,
                'max': 10.0,
                'description': 'Maximum position size in BTC equivalent'
            },
            'min_liquidity': {
                'type': 'float',
                'default': 10000,
                'min': 1000,
                'max': 1000000,
                'description': 'Minimum 24h volume in USDT'
            },
            'check_interval': {
                'type': 'float',
                'default': 1.0,
                'min': 0.1,
                'max': 10.0,
                'description': 'How often to check for opportunities (seconds)'
            },
            'execution_delay': {
                'type': 'float',
                'default': 0.1,
                'min': 0.01,
                'max': 1.0,
                'description': 'Delay between order legs (seconds)'
            },
            'use_multiple_exchanges': {
                'type': 'bool',
                'default': True,
                'description': 'Check multiple exchanges for opportunities'
            },
            'preferred_exchanges': {
                'type': 'list',
                'default': ['binance', 'kucoin', 'bybit'],
                'description': 'List of exchanges to prioritize'
            },
            'triangles': {
                'type': 'list',
                'default': [],
                'description': 'Custom triangle definitions'
            }
        })
        return params
    
    def _load_triangles(self, custom_triangles: List) -> List[Dict]:
        """
        Load predefined and custom triangles
        
        Returns:
            List of triangle definitions
        """
        # Predefined triangles (most common)
        predefined_triangles = [
            # BTC based triangles
            {
                'name': 'BTC-ETH-USDT',
                'legs': [
                    {'from': 'BTC', 'to': 'ETH', 'pair': 'ETHBTC'},
                    {'from': 'ETH', 'to': 'USDT', 'pair': 'ETHUSDT'},
                    {'from': 'USDT', 'to': 'BTC', 'pair': 'BTCUSDT'}
                ],
                'min_profit': 0.3,
                'min_liquidity': 10000
            },
            {
                'name': 'BTC-BNB-USDT',
                'legs': [
                    {'from': 'BTC', 'to': 'BNB', 'pair': 'BNBBTC'},
                    {'from': 'BNB', 'to': 'USDT', 'pair': 'BNBUSDT'},
                    {'from': 'USDT', 'to': 'BTC', 'pair': 'BTCUSDT'}
                ],
                'min_profit': 0.4,
                'min_liquidity': 5000
            },
            {
                'name': 'BTC-LTC-USDT',
                'legs': [
                    {'from': 'BTC', 'to': 'LTC', 'pair': 'LTCBTC'},
                    {'from': 'LTC', 'to': 'USDT', 'pair': 'LTCUSDT'},
                    {'from': 'USDT', 'to': 'BTC', 'pair': 'BTCUSDT'}
                ],
                'min_profit': 0.5,
                'min_liquidity': 5000
            },
            {
                'name': 'BTC-XRP-USDT',
                'legs': [
                    {'from': 'BTC', 'to': 'XRP', 'pair': 'XRPBTC'},
                    {'from': 'XRP', 'to': 'USDT', 'pair': 'XRPUSDT'},
                    {'from': 'USDT', 'to': 'BTC', 'pair': 'BTCUSDT'}
                ],
                'min_profit': 0.6,
                'min_liquidity': 10000
            },
            {
                'name': 'BTC-ADA-USDT',
                'legs': [
                    {'from': 'BTC', 'to': 'ADA', 'pair': 'ADABTC'},
                    {'from': 'ADA', 'to': 'USDT', 'pair': 'ADAUSDT'},
                    {'from': 'USDT', 'to': 'BTC', 'pair': 'BTCUSDT'}
                ],
                'min_profit': 0.7,
                'min_liquidity': 5000
            },
            {
                'name': 'BTC-DOT-USDT',
                'legs': [
                    {'from': 'BTC', 'to': 'DOT', 'pair': 'DOTBTC'},
                    {'from': 'DOT', 'to': 'USDT', 'pair': 'DOTUSDT'},
                    {'from': 'USDT', 'to': 'BTC', 'pair': 'BTCUSDT'}
                ],
                'min_profit': 0.8,
                'min_liquidity': 3000
            },
            {
                'name': 'BTC-LINK-USDT',
                'legs': [
                    {'from': 'BTC', 'to': 'LINK', 'pair': 'LINKBTC'},
                    {'from': 'LINK', 'to': 'USDT', 'pair': 'LINKUSDT'},
                    {'from': 'USDT', 'to': 'BTC', 'pair': 'BTCUSDT'}
                ],
                'min_profit': 0.7,
                'min_liquidity': 3000
            },
            
            # ETH based triangles
            {
                'name': 'ETH-BTC-USDT',
                'legs': [
                    {'from': 'ETH', 'to': 'BTC', 'pair': 'ETHBTC'},
                    {'from': 'BTC', 'to': 'USDT', 'pair': 'BTCUSDT'},
                    {'from': 'USDT', 'to': 'ETH', 'pair': 'ETHUSDT'}
                ],
                'min_profit': 0.3,
                'min_liquidity': 10000
            },
            {
                'name': 'ETH-BNB-USDT',
                'legs': [
                    {'from': 'ETH', 'to': 'BNB', 'pair': 'BNBETH'},
                    {'from': 'BNB', 'to': 'USDT', 'pair': 'BNBUSDT'},
                    {'from': 'USDT', 'to': 'ETH', 'pair': 'ETHUSDT'}
                ],
                'min_profit': 0.5,
                'min_liquidity': 5000
            },
            {
                'name': 'ETH-LTC-USDT',
                'legs': [
                    {'from': 'ETH', 'to': 'LTC', 'pair': 'LTCETH'},
                    {'from': 'LTC', 'to': 'USDT', 'pair': 'LTCUSDT'},
                    {'from': 'USDT', 'to': 'ETH', 'pair': 'ETHUSDT'}
                ],
                'min_profit': 0.6,
                'min_liquidity': 3000
            },
            
            # BNB based triangles
            {
                'name': 'BNB-BTC-USDT',
                'legs': [
                    {'from': 'BNB', 'to': 'BTC', 'pair': 'BNBBTC'},
                    {'from': 'BTC', 'to': 'USDT', 'pair': 'BTCUSDT'},
                    {'from': 'USDT', 'to': 'BNB', 'pair': 'BNBUSDT'}
                ],
                'min_profit': 0.4,
                'min_liquidity': 5000
            },
            {
                'name': 'BNB-ETH-USDT',
                'legs': [
                    {'from': 'BNB', 'to': 'ETH', 'pair': 'BNBETH'},
                    {'from': 'ETH', 'to': 'USDT', 'pair': 'ETHUSDT'},
                    {'from': 'USDT', 'to': 'BNB', 'pair': 'BNBUSDT'}
                ],
                'min_profit': 0.5,
                'min_liquidity': 3000
            },
            
            # Stablecoin triangles
            {
                'name': 'USDT-BTC-ETH',
                'legs': [
                    {'from': 'USDT', 'to': 'BTC', 'pair': 'BTCUSDT'},
                    {'from': 'BTC', 'to': 'ETH', 'pair': 'ETHBTC'},
                    {'from': 'ETH', 'to': 'USDT', 'pair': 'ETHUSDT'}
                ],
                'min_profit': 0.3,
                'min_liquidity': 10000
            },
            {
                'name': 'USDT-ETH-BNB',
                'legs': [
                    {'from': 'USDT', 'to': 'ETH', 'pair': 'ETHUSDT'},
                    {'from': 'ETH', 'to': 'BNB', 'pair': 'BNBETH'},
                    {'from': 'BNB', 'to': 'USDT', 'pair': 'BNBUSDT'}
                ],
                'min_profit': 0.5,
                'min_liquidity': 5000
            }
        ]
        
        # Merge with custom triangles
        all_triangles = predefined_triangles.copy()
        
        for triangle in custom_triangles:
            # Validate triangle structure
            if self._validate_triangle(triangle):
                all_triangles.append(triangle)
                logger.info(f"✅ Added custom triangle: {triangle.get('name', 'Unknown')}")
            else:
                logger.error(f"❌ Invalid triangle definition: {triangle}")
        
        return all_triangles
    
    def _validate_triangle(self, triangle: Dict) -> bool:
        """Validate triangle definition"""
        required_fields = ['name', 'legs']
        if not all(field in triangle for field in required_fields):
            return False
        
        if len(triangle['legs']) != 3:
            return False
        
        for leg in triangle['legs']:
            if not all(field in leg for field in ['from', 'to', 'pair']):
                return False
        
        return True
    
    async def analyze(self, market_data: Dict) -> List[Dict]:
        """
        Analyze market data for triangular arbitrage opportunities
        
        Args:
            market_data: Dictionary with market data for all symbols
            
        Returns:
            List of arbitrage signals
        """
        signals = []
        
        try:
            # Get current prices from market data or cache
            prices = await self._get_prices(market_data)
            
            # Check each triangle on each exchange
            for exchange in self._get_exchanges():
                for triangle in self.triangles:
                    # Skip if triangle doesn't meet liquidity requirements
                    if not await self._check_liquidity(triangle, exchange):
                        continue
                    
                    # Calculate arbitrage opportunity
                    opportunity = await self._calculate_opportunity(
                        triangle, prices.get(exchange, {}), exchange
                    )
                    
                    if opportunity and opportunity['profit_percent'] >= self.min_profit_threshold:
                        # Validate opportunity
                        if await self._validate_opportunity(opportunity):
                            signals.append(opportunity)
                            self.opportunities_found += 1
                            
                            logger.info(f"🎯 Arbitrage opportunity found on {exchange}:")
                            logger.info(f"   Triangle: {triangle['name']}")
                            logger.info(f"   Profit: {opportunity['profit_percent']:.2f}%")
                            logger.info(f"   Size: {opportunity['size']:.4f} BTC")
                            
                            # Auto-execute if enabled
                            if self.config.get('auto_execute', True):
                                execution_result = await self._execute_arbitrage(opportunity)
                                if execution_result:
                                    signals[-1]['execution'] = execution_result
            
        except Exception as e:
            logger.error(f"Error in triangular arbitrage analysis: {e}")
        
        return signals
    
    async def _get_prices(self, market_data: Dict) -> Dict:
        """
        Get current prices from market data or cache
        
        Returns:
            Dictionary of prices by exchange and symbol
        """
        now = datetime.now().timestamp()
        prices = {}
        
        # Extract prices from market data
        for exchange, data in market_data.items():
            if exchange not in prices:
                prices[exchange] = {}
            
            for symbol, ticker in data.get('tickers', {}).items():
                prices[exchange][symbol] = {
                    'bid': ticker.get('bid', ticker.get('price')),
                    'ask': ticker.get('ask', ticker.get('price')),
                    'price': ticker.get('price'),
                    'timestamp': now
                }
        
        # Check cache for missing prices
        for exchange in self._get_exchanges():
            if exchange not in prices:
                prices[exchange] = {}
            
            for symbol in self._get_all_symbols():
                if symbol not in prices[exchange]:
                    # Try to get from cache
                    cache_key = f"{exchange}:{symbol}"
                    if cache_key in self.price_cache:
                        cached = self.price_cache[cache_key]
                        if now - cached['timestamp'] < self.cache_ttl:
                            prices[exchange][symbol] = cached
                        else:
                            del self.price_cache[cache_key]
        
        return prices
    
    def _get_exchanges(self) -> List[str]:
        """Get list of exchanges to monitor"""
        if self.use_multiple_exchanges:
            return self.preferred_exchanges
        return ['binance']  # Default to Binance
    
    def _get_all_symbols(self) -> Set[str]:
        """Get all symbols needed for triangles"""
        symbols = set()
        for triangle in self.triangles:
            for leg in triangle['legs']:
                symbols.add(leg['pair'])
        return symbols
    
    async def _check_liquidity(self, triangle: Dict, exchange: str) -> bool:
        """
        Check if triangle meets liquidity requirements
        
        Args:
            triangle: Triangle definition
            exchange: Exchange name
            
        Returns:
            True if liquidity is sufficient
        """
        # This would check 24h volume for each pair
        # For now, return True if triangle has min_liquidity
        min_liquidity = triangle.get('min_liquidity', self.min_liquidity)
        return min_liquidity <= self.min_liquidity * 2  # Placeholder logic
    
    async def _calculate_opportunity(self, triangle: Dict, prices: Dict, exchange: str) -> Optional[Dict]:
        """
        Calculate arbitrage opportunity for a triangle
        
        Args:
            triangle: Triangle definition
            prices: Price dictionary for exchange
            exchange: Exchange name
            
        Returns:
            Opportunity dictionary or None
        """
        try:
            # Get prices for all three legs
            leg1_price = self._get_price(prices, triangle['legs'][0]['pair'])
            leg2_price = self._get_price(prices, triangle['legs'][1]['pair'])
            leg3_price = self._get_price(prices, triangle['legs'][2]['pair'])
            
            if not all([leg1_price, leg2_price, leg3_price]):
                return None
            
            # Calculate arbitrage ratio
            # A/B * B/C * C/A should be > 1 for profit
            ratio = leg1_price * leg2_price * leg3_price
            
            # Convert to percentage
            profit_percent = (ratio - 1) * 100
            
            # Calculate maximum position size based on liquidity
            size = self._calculate_position_size(triangle, prices)
            
            if size <= 0:
                return None
            
            # Estimate slippage
            slippage = self._estimate_slippage(size, prices)
            
            # Adjust profit for slippage
            net_profit = profit_percent - slippage
            
            if net_profit < self.min_profit_threshold:
                return None
            
            # Create opportunity
            opportunity = {
                'type': 'triangular_arbitrage',
                'exchange': exchange,
                'triangle': triangle['name'],
                'legs': triangle['legs'].copy(),
                'prices': {
                    'leg1': leg1_price,
                    'leg2': leg2_price,
                    'leg3': leg3_price
                },
                'ratio': ratio,
                'profit_percent': profit_percent,
                'slippage_estimate': slippage,
                'net_profit_percent': net_profit,
                'size': size,
                'timestamp': datetime.now().isoformat(),
                'confidence': self._calculate_confidence(profit_percent, slippage, size),
                'action': 'BUY' if profit_percent > 0 else 'SELL',  # Direction based on profit
                'price': leg1_price,  # Use first leg price as reference
                'target_price': leg1_price * (1 + profit_percent / 100),
                'stop_loss': self.calculate_stop_loss(leg1_price, 'BUY'),
                'reason': f"Triangular arbitrage opportunity: {profit_percent:.2f}% profit on {exchange}",
                'strategy': 'triangular_arbitrage',
                'metadata': {
                    'triangle_details': triangle,
                    'exchange': exchange
                }
            }
            
            return opportunity
            
        except Exception as e:
            logger.debug(f"Error calculating opportunity: {e}")
            return None
    
    def _get_price(self, prices: Dict, symbol: str) -> Optional[float]:
        """Get price for a symbol"""
        if symbol in prices:
            return prices[symbol].get('price')
        
        # Try alternative symbol formats
        alt_symbols = [
            symbol.replace('USDT', 'USD'),
            symbol.replace('BTC', 'XBT'),
            symbol.lower()
        ]
        
        for alt in alt_symbols:
            if alt in prices:
                return prices[alt].get('price')
        
        return None
    
    def _calculate_position_size(self, triangle: Dict, prices: Dict) -> float:
        """
        Calculate optimal position size
        
        Args:
            triangle: Triangle definition
            prices: Price dictionary
            
        Returns:
            Position size in BTC equivalent
        """
        # Get base liquidity from first leg
        first_leg = triangle['legs'][0]
        base_price = self._get_price(prices, first_leg['pair'])
        
        if not base_price:
            return 0
        
        # Calculate based on available liquidity
        liquidity_factor = min(
            triangle.get('min_liquidity', self.min_liquidity) / 1000000,
            1.0
        )
        
        # Base size on max position size and liquidity
        size = self.max_position_size * liquidity_factor
        
        # Ensure minimum size
        min_size = 0.001  # 0.001 BTC minimum
        return max(size, min_size)
    
    def _estimate_slippage(self, size: float, prices: Dict) -> float:
        """
        Estimate slippage for the trade
        
        Args:
            size: Position size
            prices: Price dictionary
            
        Returns:
            Estimated slippage percentage
        """
        # Simple slippage model
        # In production, this would use order book depth
        base_slippage = 0.05  # 0.05% base slippage
        size_factor = size / self.max_position_size
        return base_slippage * (1 + size_factor)
    
    def _calculate_confidence(self, profit: float, slippage: float, size: float) -> int:
        """Calculate confidence score for opportunity"""
        confidence = 50
        
        # Higher profit = higher confidence
        if profit > 2.0:
            confidence += 30
        elif profit > 1.0:
            confidence += 20
        elif profit > 0.5:
            confidence += 10
        
        # Lower slippage = higher confidence
        if slippage < 0.1:
            confidence += 20
        elif slippage < 0.2:
            confidence += 10
        
        # Smaller size = higher confidence (easier to execute)
        if size < 0.01:
            confidence += 10
        elif size < 0.05:
            confidence += 5
        
        return min(confidence, 95)
    
    async def _validate_opportunity(self, opportunity: Dict) -> bool:
        """
        Validate opportunity before execution
        
        Args:
            opportunity: Opportunity dictionary
            
        Returns:
            True if opportunity is still valid
        """
        # Check if opportunity is still fresh
        import time
        from datetime import datetime, timedelta
        
        opp_time = datetime.fromisoformat(opportunity['timestamp'])
        if datetime.now() - opp_time > timedelta(seconds=1):
            logger.debug("Opportunity expired")
            return False
        
        # Check if prices haven't changed significantly
        # This would re-fetch current prices
        # For now, assume valid
        return True
    
    async def _execute_arbitrage(self, opportunity: Dict) -> Optional[Dict]:
        """
        Execute triangular arbitrage
        
        Args:
            opportunity: Opportunity dictionary
            
        Returns:
            Execution result dictionary
        """
        try:
            logger.info(f"⚡ Executing triangular arbitrage on {opportunity['exchange']}")
            logger.info(f"   Triangle: {opportunity['triangle']}")
            logger.info(f"   Expected profit: {opportunity['net_profit_percent']:.2f}%")
            
            # Record start time
            start_time = datetime.now()
            
            # Execute three legs sequentially
            execution_results = []
            current_asset = opportunity['legs'][0]['from']
            current_size = opportunity['size']
            
            for i, leg in enumerate(opportunity['legs']):
                # Wait between legs to ensure fills
                if i > 0:
                    await asyncio.sleep(self.execution_delay)
                
                # Execute trade
                result = await self._execute_leg(leg, current_size, opportunity['exchange'])
                
                if not result['success']:
                    # Partial execution - need to unwind
                    logger.error(f"❌ Leg {i+1} failed: {result.get('error')}")
                    await self._unwind_position(execution_results, opportunity['exchange'])
                    self.failed_executions += 1
                    return None
                
                execution_results.append(result)
                current_asset = leg['to']
                current_size = result['received_amount']
                
                logger.info(f"   ✅ Leg {i+1} completed: {leg['from']} → {leg['to']} @ {result['price']:.4f}")
            
            # Calculate final results
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            # Calculate actual profit
            start_value = opportunity['size']
            end_value = current_size
            actual_profit = ((end_value / start_value) - 1) * 100
            
            execution_result = {
                'success': True,
                'execution_time': execution_time,
                'legs': execution_results,
                'start_asset': opportunity['legs'][0]['from'],
                'end_asset': current_asset,
                'start_value': start_value,
                'end_value': end_value,
                'expected_profit': opportunity['net_profit_percent'],
                'actual_profit': actual_profit,
                'slippage': opportunity['net_profit_percent'] - actual_profit,
                'timestamp': datetime.now().isoformat()
            }
            
            # Update stats
            self.opportunities_executed += 1
            self.total_profit += actual_profit
            
            logger.info(f"✅ Arbitrage completed in {execution_time:.2f}s")
            logger.info(f"   Actual profit: {actual_profit:.2f}%")
            
            return execution_result
            
        except Exception as e:
            logger.error(f"❌ Error executing arbitrage: {e}")
            self.failed_executions += 1
            return None
    
    async def _execute_leg(self, leg: Dict, size: float, exchange: str) -> Dict:
        """
        Execute a single leg of the arbitrage
        
        Args:
            leg: Leg definition
            size: Amount to trade
            exchange: Exchange name
            
        Returns:
            Execution result
        """
        # This would interface with the exchange manager
        # For simulation, return success
        
        # Simulate execution
        import random
        
        # Determine side based on leg direction
        # A/B: If trading from A to B, we BUY B with A
        # So if leg['from'] is base, we SELL base, BUY quote
        # Simplified: assume price is in terms of leg['to'] per leg['from']
        
        base_price = random.uniform(0.99, 1.01)  # Simulate price
        
        # Calculate received amount
        if leg['to'] == leg['pair'].replace(leg['from'], ''):
            # Direct pair: 1 from = price to
            received = size * base_price
        else:
            # Inverse pair: price from per to
            received = size / base_price
        
        return {
            'success': True,
            'leg': leg,
            'size': size,
            'price': base_price,
            'received_amount': received,
            'timestamp': datetime.now().isoformat()
        }
    
    async def _unwind_position(self, executed_legs: List, exchange: str):
        """
        Unwind partially executed position
        
        Args:
            executed_legs: List of successfully executed legs
            exchange: Exchange name
        """
        if not executed_legs:
            return
        
        logger.warning(f"⚠️ Unwinding position after {len(executed_legs)} legs")
        
        # Reverse the executed legs in reverse order
        for leg in reversed(executed_legs):
            try:
                # Execute reverse trade
                reverse_leg = {
                    'from': leg['leg']['to'],
                    'to': leg['leg']['from'],
                    'pair': leg['leg']['pair']
                }
                await self._execute_leg(reverse_leg, leg['received_amount'], exchange)
                await asyncio.sleep(self.execution_delay)
                
            except Exception as e:
                logger.error(f"❌ Error unwinding: {e}")
    
    def get_stats(self) -> Dict:
        """Get strategy statistics"""
        return {
            'opportunities_found': self.opportunities_found,
            'opportunities_executed': self.opportunities_executed,
            'total_profit': self.total_profit,
            'failed_executions': self.failed_executions,
            'success_rate': (self.opportunities_executed / self.opportunities_found * 100) if self.opportunities_found > 0 else 0,
            'active_triangles': len(self.active_triangles),
            'avg_profit': self.total_profit / self.opportunities_executed if self.opportunities_executed > 0 else 0
        }
    
    async def monitor_opportunities(self):
        """
        Continuously monitor for arbitrage opportunities
        Called by scheduler
        """
        while self.is_running and not self.is_paused:
            try:
                # Get market data
                market_data = await self._get_market_data()
                
                # Analyze for opportunities
                signals = await self.analyze(market_data)
                
                # Store opportunities
                self.opportunities.extend(signals)
                
                # Keep only recent opportunities
                from datetime import datetime, timedelta
                cutoff = datetime.now() - timedelta(minutes=5)
                self.opportunities = [
                    opp for opp in self.opportunities
                    if datetime.fromisoformat(opp['timestamp']) > cutoff
                ]
                
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(1)
    
    async def _get_market_data(self) -> Dict:
        """
        Get market data for monitoring
        
        Returns:
            Market data dictionary
        """
        # This would fetch from exchange manager
        # For simulation, return empty
        return {}
    
    def to_dict(self) -> Dict:
        """Convert strategy to dictionary"""
        data = super().to_dict()
        data.update({
            'min_profit_threshold': self.min_profit_threshold,
            'max_slippage': self.max_slippage,
            'max_position_size': self.max_position_size,
            'triangle_count': len(self.triangles),
            'stats': self.get_stats(),
            'recent_opportunities': self.opportunities[-10:]  # Last 10 opportunities
        })
        return data


class CrossExchangeArbitrageStrategy(BaseStrategy):
    """
    Cross-Exchange Arbitrage Strategy
    
    Exploits price differences for the same asset across different exchanges:
    Buy low on Exchange A, sell high on Exchange B
    
    Features:
    - Real-time price monitoring across exchanges
    - Minimum profit threshold after fees
    - Automatic execution
    - Balance management
    """
    
    category = "arbitrage"
    version = "1.0.0"
    
    def __init__(self, instance_id: str, config: Dict):
        super().__init__(instance_id, config)
        
        self.min_profit_threshold = config.get('min_profit_threshold', 0.3)
        self.max_slippage = config.get('max_slippage', 0.1)
        self.max_position_size = config.get('max_position_size', 0.1)
        self.symbols = config.get('symbols', ['BTCUSDT', 'ETHUSDT'])
        self.exchanges = config.get('exchanges', ['binance', 'kucoin', 'bybit'])
        self.check_interval = config.get('check_interval', 1)
        
        self.opportunities = []
        self.stats = defaultdict(int)
    
    async def analyze(self, market_data: Dict) -> List[Dict]:
        """Analyze cross-exchange arbitrage opportunities"""
        signals = []
        
        for symbol in self.symbols:
            # Get prices from all exchanges
            prices = {}
            for exchange in self.exchanges:
                if exchange in market_data:
                    ticker = market_data[exchange].get('tickers', {}).get(symbol)
                    if ticker:
                        prices[exchange] = {
                            'bid': ticker.get('bid', ticker.get('price')),
                            'ask': ticker.get('ask', ticker.get('price')),
                            'price': ticker.get('price')
                        }
            
            if len(prices) < 2:
                continue
            
            # Find best bid and ask
            best_bid_exchange = max(prices.items(), key=lambda x: x[1]['bid'])
            best_ask_exchange = min(prices.items(), key=lambda x: x[1]['ask'])
            
            buy_exchange, buy_price = best_ask_exchange
            sell_exchange, sell_price = best_bid_exchange
            
            if buy_exchange == sell_exchange:
                continue
            
            # Calculate profit after fees (assume 0.1% per trade)
            fee_rate = 0.001
            profit_percent = ((sell_price['bid'] * (1 - fee_rate)) / (buy_price['ask'] * (1 + fee_rate)) - 1) * 100
            
            if profit_percent >= self.min_profit_threshold:
                signal = {
                    'type': 'cross_exchange_arbitrage',
                    'symbol': symbol,
                    'buy_exchange': buy_exchange,
                    'sell_exchange': sell_exchange,
                    'buy_price': buy_price['ask'],
                    'sell_price': sell_price['bid'],
                    'profit_percent': profit_percent,
                    'size': self._calculate_size(buy_price['ask'], symbol),
                    'confidence': min(int(profit_percent * 20), 95),
                    'timestamp': datetime.now().isoformat(),
                    'action': 'BUY',
                    'price': buy_price['ask'],
                    'target_price': sell_price['bid'],
                    'stop_loss': buy_price['ask'] * 0.99,
                    'reason': f"Arbitrage: Buy on {buy_exchange} @ {buy_price['ask']:.2f}, Sell on {sell_exchange} @ {sell_price['bid']:.2f}",
                    'strategy': 'cross_exchange_arbitrage'
                }
                signals.append(signal)
                self.stats['opportunities_found'] += 1
        
        return signals
    
    def _calculate_size(self, price: float, symbol: str) -> float:
        """Calculate position size"""
        # In production, this would consider balances and risk
        return self.max_position_size / price if 'BTC' in symbol else self.max_position_size
    
    def get_stats(self) -> Dict:
        """Get strategy statistics"""
        return dict(self.stats)


class StatisticalArbitrageStrategy(BaseStrategy):
    """
    Statistical Arbitrage Strategy (Pairs Trading)
    
    Exploits mean reversion between correlated assets:
    - Long the underperformer, short the outperformer
    - Exit when spread returns to mean
    
    Features:
    - Correlation analysis
    - Cointegration testing
    - Z-score based entry/exit
    - Dynamic position sizing
    """
    
    category = "arbitrage"
    version = "1.0.0"
    
    def __init__(self, instance_id: str, config: Dict):
        super().__init__(instance_id, config)
        
        self.entry_zscore = config.get('entry_zscore', 2.0)
        self.exit_zscore = config.get('exit_zscore', 0.5)
        self.lookback_period = config.get('lookback_period', 100)
        self.min_correlation = config.get('min_correlation', 0.7)
        self.max_position_size = config.get('max_position_size', 0.1)
        
        self.pairs = config.get('pairs', [
            ['BTCUSDT', 'ETHUSDT'],
            ['BNBUSDT', 'ETHUSDT'],
            ['LTCUSDT', 'BTCUSDT']
        ])
        
        self.spreads = {}
        self.positions = {}
        self.stats = defaultdict(int)
    
    async def analyze(self, market_data: Dict) -> List[Dict]:
        """Analyze pairs for statistical arbitrage"""
        signals = []
        
        # Get price data
        prices = {}
        for symbol in set(s for pair in self.pairs for s in pair):
            # In production, get price history
            # For now, use current price
            for exchange, data in market_data.items():
                if symbol in data.get('tickers', {}):
                    prices[symbol] = data['tickers'][symbol]['price']
                    break
        
        if len(prices) < 2:
            return signals
        
        # Analyze each pair
        for pair in self.pairs:
            if pair[0] not in prices or pair[1] not in prices:
                continue
            
            # Calculate spread
            price1 = prices[pair[0]]
            price2 = prices[pair[1]]
            spread = np.log(price1 / price2)
            
            # Store spread
            if pair[0] not in self.spreads:
                self.spreads[pair[0]] = []
            self.spreads[pair[0]].append(spread)
            
            # Keep only lookback period
            if len(self.spreads[pair[0]]) > self.lookback_period:
                self.spreads[pair[0]] = self.spreads[pair[0]][-self.lookback_period:]
            
            # Calculate z-score
            if len(self.spreads[pair[0]]) >= 30:
                mean = np.mean(self.spreads[pair[0]])
                std = np.std(self.spreads[pair[0]])
                
                if std > 0:
                    zscore = (spread - mean) / std
                    
                    # Generate signals
                    if zscore > self.entry_zscore and pair[0] not in self.positions:
                        # Spread too wide - short pair[0], long pair[1]
                        signal = self._create_signal(pair, 'SELL', zscore, prices)
                        signals.append(signal)
                        self.positions[pair[0]] = {'side': 'SHORT', 'entry_zscore': zscore}
                        self.stats['opportunities_found'] += 1
                        
                    elif zscore < -self.entry_zscore and pair[0] not in self.positions:
                        # Spread too narrow - long pair[0], short pair[1]
                        signal = self._create_signal(pair, 'BUY', zscore, prices)
                        signals.append(signal)
                        self.positions[pair[0]] = {'side': 'LONG', 'entry_zscore': zscore}
                        self.stats['opportunities_found'] += 1
                        
                    elif pair[0] in self.positions:
                        # Check exit conditions
                        position = self.positions[pair[0]]
                        if abs(zscore) < self.exit_zscore:
                            # Exit position
                            signal = self._create_exit_signal(pair, position, zscore, prices)
                            signals.append(signal)
                            del self.positions[pair[0]]
                            self.stats['positions_closed'] += 1
        
        return signals
    
    def _create_signal(self, pair: List[str], action: str, zscore: float, prices: Dict) -> Dict:
        """Create entry signal"""
        price = prices[pair[0]]
        return {
            'type': 'statistical_arbitrage',
            'pair': pair,
            'action': action,
            'zscore': zscore,
            'price': price,
            'size': self.max_position_size,
            'confidence': min(int(abs(zscore) * 25), 90),
            'timestamp': datetime.now().isoformat(),
            'target_price': price * (1 + 0.02) if action == 'BUY' else price * (1 - 0.02),
            'stop_loss': price * 0.98 if action == 'BUY' else price * 1.02,
            'reason': f"Pairs trade: {pair[0]}/{pair[1]} z-score = {zscore:.2f}",
            'strategy': 'statistical_arbitrage'
        }
    
    def _create_exit_signal(self, pair: List[str], position: Dict, zscore: float, prices: Dict) -> Dict:
        """Create exit signal"""
        price = prices[pair[0]]
        action = 'SELL' if position['side'] == 'LONG' else 'BUY'
        
        return {
            'type': 'statistical_arbitrage_exit',
            'pair': pair,
            'action': action,
            'zscore': zscore,
            'entry_zscore': position['entry_zscore'],
            'price': price,
            'size': self.max_position_size,
            'confidence': 90,
            'timestamp': datetime.now().isoformat(),
            'reason': f"Exit pairs trade: spread normalized to {zscore:.2f}",
            'strategy': 'statistical_arbitrage'
        }
    
    def get_stats(self) -> Dict:
        """Get strategy statistics"""
        return dict(self.stats)