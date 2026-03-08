"""
Trading Strategies Module
Enterprise-grade strategy management system
"""

from typing import Dict, List, Optional, Type
from datetime import datetime
import importlib
import inspect
import logging

from .base import BaseStrategy
from .technical import (
    MovingAverageCrossStrategy,
    RSIDivergenceStrategy,
    MACDStrategy,
    BollingerBandsStrategy,
    IchimokuStrategy,
    FibonacciStrategy
)
from .ml import (
    LSTMPredictionStrategy,
    RandomForestStrategy,
    XGBoostStrategy,
    TransformerStrategy
)
from .arbitrage import (
    TriangularArbitrageStrategy,
    CrossExchangeArbitrageStrategy,
    StatisticalArbitrageStrategy
)
from .sentiment import (
    NewsSentimentStrategy,
    SocialMediaStrategy,
    WhaleTrackingStrategy
)
from .portfolio import (
    GridTradingStrategy,
    DCAStrategy,
    MartingaleStrategy,
    KellyStrategy
)

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """
    Central registry for all trading strategies
    Manages strategy lifecycle, configuration, and execution
    """
    
    def __init__(self):
        self.strategies = {}
        self.active_strategies = {}
        self.strategy_instances = {}
        self.performance_metrics = {}
        self._load_builtin_strategies()
    
    def _load_builtin_strategies(self):
        """Load all built-in strategies"""
        builtin_strategies = {
            # Technical Analysis
            'ma_cross': MovingAverageCrossStrategy,
            'rsi_divergence': RSIDivergenceStrategy,
            'macd': MACDStrategy,
            'bollinger': BollingerBandsStrategy,
            'ichimoku': IchimokuStrategy,
            'fibonacci': FibonacciStrategy,
            
            # Machine Learning
            'lstm': LSTMPredictionStrategy,
            'random_forest': RandomForestStrategy,
            'xgboost': XGBoostStrategy,
            'transformer': TransformerStrategy,
            
            # Arbitrage
            'triangular_arb': TriangularArbitrageStrategy,
            'cross_exchange_arb': CrossExchangeArbitrageStrategy,
            'stat_arb': StatisticalArbitrageStrategy,
            
            # Sentiment
            'news_sentiment': NewsSentimentStrategy,
            'social_sentiment': SocialMediaStrategy,
            'whale_tracking': WhaleTrackingStrategy,
            
            # Portfolio
            'grid_trading': GridTradingStrategy,
            'dca': DCAStrategy,
            'martingale': MartingaleStrategy,
            'kelly': KellyStrategy
        }
        
        for name, strategy_class in builtin_strategies.items():
            self.register_strategy(name, strategy_class)
            logger.info(f"✅ Loaded built-in strategy: {name}")
    
    def register_strategy(self, name: str, strategy_class: Type[BaseStrategy]):
        """Register a new strategy"""
        self.strategies[name] = {
            'class': strategy_class,
            'description': strategy_class.__doc__,
            'parameters': strategy_class.get_parameters(),
            'registered_at': datetime.now()
        }
        logger.info(f"📝 Registered strategy: {name}")
    
    def get_strategy(self, name: str) -> Optional[Dict]:
        """Get strategy by name"""
        return self.strategies.get(name)
    
    def list_strategies(self, category: Optional[str] = None) -> List[Dict]:
        """List all available strategies"""
        strategies = []
        for name, info in self.strategies.items():
            if category and info['class'].category != category:
                continue
            strategies.append({
                'name': name,
                'description': info['description'],
                'category': info['class'].category,
                'parameters': info['parameters']
            })
        return strategies
    
    def create_instance(self, strategy_name: str, instance_id: str,
                        config: Dict) -> BaseStrategy:
        """Create a strategy instance"""
        if strategy_name not in self.strategies:
            raise ValueError(f"Strategy {strategy_name} not found")
        
        strategy_class = self.strategies[strategy_name]['class']
        instance = strategy_class(instance_id, config)
        
        self.strategy_instances[instance_id] = {
            'instance': instance,
            'name': strategy_name,
            'config': config,
            'created_at': datetime.now(),
            'status': 'initialized'
        }
        
        logger.info(f"🚀 Created strategy instance: {instance_id} ({strategy_name})")
        return instance
    
    def start_strategy(self, instance_id: str):
        """Start a strategy instance"""
        if instance_id not in self.strategy_instances:
            raise ValueError(f"Strategy instance {instance_id} not found")
        
        instance_info = self.strategy_instances[instance_id]
        instance = instance_info['instance']
        
        try:
            instance.start()
            instance_info['status'] = 'running'
            instance_info['started_at'] = datetime.now()
            self.active_strategies[instance_id] = instance_info
            logger.info(f"▶️ Started strategy: {instance_id}")
        except Exception as e:
            logger.error(f"❌ Failed to start strategy {instance_id}: {e}")
            raise
    
    def stop_strategy(self, instance_id: str):
        """Stop a strategy instance"""
        if instance_id in self.active_strategies:
            instance_info = self.active_strategies[instance_id]
            instance = instance_info['instance']
            
            try:
                instance.stop()
                instance_info['status'] = 'stopped'
                instance_info['stopped_at'] = datetime.now()
                del self.active_strategies[instance_id]
                logger.info(f"⏹️ Stopped strategy: {instance_id}")
            except Exception as e:
                logger.error(f"❌ Failed to stop strategy {instance_id}: {e}")
                raise
    
    def get_instance(self, instance_id: str) -> Optional[BaseStrategy]:
        """Get strategy instance by ID"""
        if instance_id in self.strategy_instances:
            return self.strategy_instances[instance_id]['instance']
        return None
    
    def list_instances(self, status: Optional[str] = None) -> List[Dict]:
        """List all strategy instances"""
        instances = []
        for instance_id, info in self.strategy_instances.items():
            if status and info['status'] != status:
                continue
            instances.append({
                'id': instance_id,
                'name': info['name'],
                'config': info['config'],
                'status': info['status'],
                'created_at': info['created_at'].isoformat(),
                'started_at': info.get('started_at', '').isoformat() if 'started_at' in info else None,
                'performance': self.performance_metrics.get(instance_id, {})
            })
        return instances
    
    def update_performance(self, instance_id: str, metrics: Dict):
        """Update performance metrics for a strategy"""
        self.performance_metrics[instance_id] = metrics
    
    def get_performance(self, instance_id: str) -> Dict:
        """Get performance metrics for a strategy"""
        return self.performance_metrics.get(instance_id, {})


class StrategyManager:
    """
    High-level strategy management
    Handles strategy lifecycle, resource allocation, and coordination
    """
    
    def __init__(self, exchange_manager, risk_manager, portfolio_manager):
        self.registry = StrategyRegistry()
        self.exchange_manager = exchange_manager
        self.risk_manager = risk_manager
        self.portfolio_manager = portfolio_manager
        self.running_strategies = {}
        self.strategy_scheduler = {}
        self.resource_allocator = ResourceAllocator()
        self.performance_tracker = PerformanceTracker()
        
        logger.info("📊 Strategy Manager initialized")
    
    async def deploy_strategy(self, strategy_name: str, config: Dict) -> str:
        """Deploy a new strategy"""
        # Validate configuration
        self._validate_config(strategy_name, config)
        
        # Check resource availability
        if not self.resource_allocator.can_allocate(config):
            raise InsufficientResourcesError("Not enough resources for strategy")
        
        # Create instance
        instance_id = self._generate_instance_id(strategy_name)
        instance = self.registry.create_instance(strategy_name, instance_id, config)
        
        # Allocate resources
        self.resource_allocator.allocate(instance_id, config)
        
        # Start if auto-start enabled
        if config.get('auto_start', True):
            await self.start_strategy(instance_id)
        
        logger.info(f"🎯 Deployed strategy: {instance_id}")
        return instance_id
    
    async def start_strategy(self, instance_id: str):
        """Start a strategy"""
        instance = self.registry.get_instance(instance_id)
        if not instance:
            raise ValueError(f"Strategy {instance_id} not found")
        
        # Register with scheduler
        schedule = instance.get_schedule()
        if schedule:
            self.strategy_scheduler[instance_id] = schedule
        
        # Start the strategy
        self.registry.start_strategy(instance_id)
        self.running_strategies[instance_id] = instance
        
        logger.info(f"▶️ Started strategy: {instance_id}")
    
    async def stop_strategy(self, instance_id: str):
        """Stop a strategy"""
        if instance_id in self.running_strategies:
            self.registry.stop_strategy(instance_id)
            del self.running_strategies[instance_id]
            
            if instance_id in self.strategy_scheduler:
                del self.strategy_scheduler[instance_id]
            
            logger.info(f"⏹️ Stopped strategy: {instance_id}")
    
    async def pause_strategy(self, instance_id: str):
        """Pause a strategy temporarily"""
        instance = self.registry.get_instance(instance_id)
        if instance:
            instance.pause()
            logger.info(f"⏸️ Paused strategy: {instance_id}")
    
    async def resume_strategy(self, instance_id: str):
        """Resume a paused strategy"""
        instance = self.registry.get_instance(instance_id)
        if instance:
            instance.resume()
            logger.info(f"▶️ Resumed strategy: {instance_id}")
    
    async def execute_strategy(self, instance_id: str, market_data: Dict) -> List[Dict]:
        """Execute a strategy once"""
        instance = self.registry.get_instance(instance_id)
        if not instance:
            raise ValueError(f"Strategy {instance_id} not found")
        
        # Check if strategy is running
        if instance_id not in self.running_strategies:
            logger.warning(f"Strategy {instance_id} not running")
            return []
        
        # Execute strategy
        signals = await instance.analyze(market_data)
        
        # Validate signals
        validated_signals = []
        for signal in signals:
            if await self._validate_signal(signal):
                validated_signals.append(signal)
        
        # Track performance
        self.performance_tracker.record_execution(instance_id, validated_signals)
        
        return validated_signals
    
    async def run_scheduled_strategies(self):
        """Run all scheduled strategies"""
        import asyncio
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        
        scheduler = AsyncIOScheduler()
        
        for instance_id, schedule in self.strategy_scheduler.items():
            scheduler.add_job(
                self._execute_scheduled_strategy,
                'interval',
                args=[instance_id],
                **schedule
            )
        
        scheduler.start()
        logger.info(f"📅 Started strategy scheduler with {len(self.strategy_scheduler)} jobs")
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            scheduler.shutdown()
    
    async def _execute_scheduled_strategy(self, instance_id: str):
        """Execute a scheduled strategy"""
        try:
            # Get market data
            market_data = await self._get_market_data(instance_id)
            
            # Execute strategy
            signals = await self.execute_strategy(instance_id, market_data)
            
            # Execute signals
            for signal in signals:
                await self._execute_signal(signal)
                
        except Exception as e:
            logger.error(f"Error executing scheduled strategy {instance_id}: {e}")
    
    async def _validate_signal(self, signal: Dict) -> bool:
        """Validate a trading signal"""
        # Check risk limits
        if not await self.risk_manager.check_signal(signal):
            return False
        
        # Check portfolio constraints
        if not self.portfolio_manager.can_trade(signal):
            return False
        
        # Validate signal parameters
        required_fields = ['symbol', 'action', 'confidence', 'price']
        if not all(field in signal for field in required_fields):
            return False
        
        # Check confidence threshold
        if signal.get('confidence', 0) < 50:
            return False
        
        return True
    
    async def _execute_signal(self, signal: Dict):
        """Execute a validated signal"""
        # Place order through trading engine
        order = await self.exchange_manager.place_order(
            symbol=signal['symbol'],
            side=signal['action'],
            quantity=signal.get('quantity', 0.001),
            order_type=signal.get('order_type', 'market')
        )
        
        # Record trade
        self.portfolio_manager.record_trade(order, signal)
        
        logger.info(f"📈 Executed signal: {signal['symbol']} {signal['action']} @ {signal['price']}")
    
    async def _get_market_data(self, instance_id: str) -> Dict:
        """Get market data for strategy"""
        instance = self.registry.get_instance(instance_id)
        symbols = instance.get_symbols()
        
        market_data = {}
        for symbol in symbols:
            # Get ticker
            ticker = await self.exchange_manager.get_ticker(symbol)
            
            # Get klines
            klines = await self.exchange_manager.get_klines(symbol, '1h', 100)
            
            # Get orderbook
            orderbook = await self.exchange_manager.get_orderbook(symbol)
            
            market_data[symbol] = {
                'ticker': ticker,
                'klines': klines,
                'orderbook': orderbook,
                'timestamp': datetime.now().isoformat()
            }
        
        return market_data
    
    def _validate_config(self, strategy_name: str, config: Dict):
        """Validate strategy configuration"""
        strategy_info = self.registry.get_strategy(strategy_name)
        if not strategy_info:
            raise ValueError(f"Strategy {strategy_name} not found")
        
        required_params = strategy_info['parameters'].get('required', [])
        for param in required_params:
            if param not in config:
                raise ValueError(f"Missing required parameter: {param}")
    
    def _generate_instance_id(self, strategy_name: str) -> str:
        """Generate unique instance ID"""
        import uuid
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        return f"{strategy_name}_{timestamp}_{unique_id}"
    
    def get_strategy_status(self, instance_id: str) -> Dict:
        """Get detailed strategy status"""
        instance_info = self.registry.strategy_instances.get(instance_id)
        if not instance_info:
            return {}
        
        return {
            'id': instance_id,
            'name': instance_info['name'],
            'status': instance_info['status'],
            'created_at': instance_info['created_at'].isoformat(),
            'started_at': instance_info.get('started_at', '').isoformat() if 'started_at' in instance_info else None,
            'config': instance_info['config'],
            'performance': self.performance_tracker.get_metrics(instance_id),
            'resources': self.resource_allocator.get_allocation(instance_id)
        }
    
    def get_system_status(self) -> Dict:
        """Get overall system status"""
        return {
            'total_strategies': len(self.registry.strategies),
            'active_instances': len(self.running_strategies),
            'total_instances': len(self.registry.strategy_instances),
            'scheduled_jobs': len(self.strategy_scheduler),
            'resource_usage': self.resource_allocator.get_usage(),
            'performance_summary': self.performance_tracker.get_summary()
        }


class ResourceAllocator:
    """Manage resource allocation for strategies"""
    
    def __init__(self):
        self.allocations = {}
        self.total_resources = {
            'cpu': 100,  # Percentage
            'memory': 32,  # GB
            'connections': 1000,
            'api_calls': 10000  # Per minute
        }
        self.used_resources = {
            'cpu': 0,
            'memory': 0,
            'connections': 0,
            'api_calls': 0
        }
    
    def can_allocate(self, config: Dict) -> bool:
        """Check if resources are available"""
        required = config.get('resources', {})
        
        for resource, amount in required.items():
            if resource in self.total_resources:
                if self.used_resources[resource] + amount > self.total_resources[resource]:
                    return False
        
        return True
    
    def allocate(self, instance_id: str, config: Dict):
        """Allocate resources for strategy"""
        required = config.get('resources', {})
        self.allocations[instance_id] = required
        
        for resource, amount in required.items():
            if resource in self.used_resources:
                self.used_resources[resource] += amount
    
    def deallocate(self, instance_id: str):
        """Deallocate resources"""
        if instance_id in self.allocations:
            for resource, amount in self.allocations[instance_id].items():
                if resource in self.used_resources:
                    self.used_resources[resource] -= amount
            del self.allocations[instance_id]
    
    def get_allocation(self, instance_id: str) -> Dict:
        """Get allocation for strategy"""
        return self.allocations.get(instance_id, {})
    
    def get_usage(self) -> Dict:
        """Get current resource usage"""
        return {
            'total': self.total_resources,
            'used': self.used_resources,
            'available': {
                k: self.total_resources[k] - self.used_resources[k]
                for k in self.total_resources
            }
        }


class PerformanceTracker:
    """Track strategy performance metrics"""
    
    def __init__(self):
        self.metrics = {}
        self.history = {}
        self.summary_stats = {}
    
    def record_execution(self, instance_id: str, signals: List[Dict]):
        """Record strategy execution"""
        if instance_id not in self.metrics:
            self.metrics[instance_id] = {
                'executions': 0,
                'signals_generated': 0,
                'signals_executed': 0,
                'total_pnl': 0.0,
                'winning_trades': 0,
                'losing_trades': 0,
                'last_execution': None
            }
        
        metrics = self.metrics[instance_id]
        metrics['executions'] += 1
        metrics['signals_generated'] += len(signals)
        metrics['last_execution'] = datetime.now()
        
        # Record in history
        if instance_id not in self.history:
            self.history[instance_id] = []
        
        self.history[instance_id].append({
            'timestamp': datetime.now(),
            'signals': len(signals),
            'metrics': metrics.copy()
        })
        
        # Keep last 1000 records
        if len(self.history[instance_id]) > 1000:
            self.history[instance_id].pop(0)
    
    def record_trade(self, instance_id: str, trade_result: Dict):
        """Record individual trade result"""
        if instance_id not in self.metrics:
            return
        
        metrics = self.metrics[instance_id]
        metrics['signals_executed'] += 1
        metrics['total_pnl'] += trade_result.get('pnl', 0)
        
        if trade_result.get('pnl', 0) > 0:
            metrics['winning_trades'] += 1
        else:
            metrics['losing_trades'] += 1
    
    def get_metrics(self, instance_id: str) -> Dict:
        """Get metrics for strategy"""
        if instance_id not in self.metrics:
            return {}
        
        metrics = self.metrics[instance_id].copy()
        
        # Calculate derived metrics
        total_trades = metrics['winning_trades'] + metrics['losing_trades']
        if total_trades > 0:
            metrics['win_rate'] = (metrics['winning_trades'] / total_trades) * 100
        else:
            metrics['win_rate'] = 0
        
        if metrics['signals_generated'] > 0:
            metrics['execution_rate'] = (metrics['signals_executed'] / metrics['signals_generated']) * 100
        else:
            metrics['execution_rate'] = 0
        
        return metrics
    
    def get_summary(self) -> Dict:
        """Get performance summary across all strategies"""
        total_strategies = len(self.metrics)
        total_executions = sum(m['executions'] for m in self.metrics.values())
        total_signals = sum(m['signals_generated'] for m in self.metrics.values())
        total_trades = sum(m['signals_executed'] for m in self.metrics.values())
        total_pnl = sum(m['total_pnl'] for m in self.metrics.values())
        
        winning_strategies = sum(1 for m in self.metrics.values() if m['total_pnl'] > 0)
        
        return {
            'total_strategies': total_strategies,
            'total_executions': total_executions,
            'total_signals': total_signals,
            'total_trades': total_trades,
            'total_pnl': total_pnl,
            'winning_strategies': winning_strategies,
            'average_pnl_per_strategy': total_pnl / total_strategies if total_strategies > 0 else 0,
            'average_signals_per_execution': total_signals / total_executions if total_executions > 0 else 0
        }