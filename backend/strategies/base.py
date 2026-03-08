"""
Base Strategy Class
Abstract base class for all trading strategies
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies
    Provides common interface and utility methods
    """
    
    # Class attributes
    category = "base"
    version = "1.0.0"
    
    def __init__(self, instance_id: str, config: Dict):
        """
        Initialize strategy
        
        Args:
            instance_id: Unique identifier for this strategy instance
            config: Strategy configuration parameters
        """
        self.instance_id = instance_id
        self.config = config
        self.name = config.get('name', self.__class__.__name__)
        self.symbols = config.get('symbols', [])
        self.timeframe = config.get('timeframe', '1h')
        self.risk_per_trade = config.get('risk_per_trade', 2.0)  # Percentage
        self.max_positions = config.get('max_positions', 5)
        self.position_size = config.get('position_size', 0.01)
        
        # State
        self.is_running = False
        self.is_paused = False
        self.created_at = datetime.now()
        self.started_at = None
        self.stopped_at = None
        self.positions = []
        self.signals = []
        self.metrics = {}
        
        logger.info(f"📈 Initialized strategy: {self.name} ({self.instance_id})")
    
    @classmethod
    def get_parameters(cls) -> Dict:
        """
        Get strategy parameters definition
        
        Returns:
            Dictionary with parameter specifications
        """
        return {
            'required': ['symbols'],
            'optional': {
                'timeframe': {'type': 'str', 'default': '1h', 'options': ['1m', '5m', '15m', '1h', '4h', '1d']},
                'risk_per_trade': {'type': 'float', 'default': 2.0, 'min': 0.1, 'max': 10},
                'max_positions': {'type': 'int', 'default': 5, 'min': 1, 'max': 20},
                'position_size': {'type': 'float', 'default': 0.01, 'min': 0.001, 'max': 10}
            },
            'description': cls.__doc__
        }
    
    @abstractmethod
    async def analyze(self, market_data: Dict) -> List[Dict]:
        """
        Analyze market data and generate trading signals
        
        Args:
            market_data: Dictionary with market data for all symbols
            
        Returns:
            List of trading signals
        """
        pass
    
    def get_schedule(self) -> Optional[Dict]:
        """
        Get execution schedule for strategy
        
        Returns:
            Schedule configuration or None if not scheduled
        """
        return self.config.get('schedule')
    
    def get_symbols(self) -> List[str]:
        """Get symbols traded by strategy"""
        return self.symbols
    
    def start(self):
        """Start the strategy"""
        self.is_running = True
        self.started_at = datetime.now()
        logger.info(f"▶️ Strategy {self.name} started")
    
    def stop(self):
        """Stop the strategy"""
        self.is_running = False
        self.stopped_at = datetime.now()
        logger.info(f"⏹️ Strategy {self.name} stopped")
    
    def pause(self):
        """Pause the strategy temporarily"""
        self.is_paused = True
        logger.info(f"⏸️ Strategy {self.name} paused")
    
    def resume(self):
        """Resume paused strategy"""
        self.is_paused = False
        logger.info(f"▶️ Strategy {self.name} resumed")
    
    def validate_signal(self, signal: Dict) -> bool:
        """
        Validate a trading signal
        
        Args:
            signal: Signal dictionary
            
        Returns:
            True if signal is valid
        """
        required_fields = ['symbol', 'action', 'confidence', 'price']
        return all(field in signal for field in required_fields)
    
    def calculate_position_size(self, price: float, confidence: float) -> float:
        """
        Calculate position size based on confidence and risk
        
        Args:
            price: Current price
            confidence: Signal confidence (0-100)
            
        Returns:
            Position size in base currency
        """
        base_size = self.position_size
        confidence_factor = confidence / 50  # 0.5x to 2x
        return base_size * min(confidence_factor, 2.0)
    
    def calculate_stop_loss(self, entry_price: float, side: str) -> float:
        """
        Calculate stop loss price
        
        Args:
            entry_price: Entry price
            side: 'BUY' or 'SELL'
            
        Returns:
            Stop loss price
        """
        risk_amount = entry_price * (self.risk_per_trade / 100)
        
        if side == 'BUY':
            return entry_price - risk_amount
        else:
            return entry_price + risk_amount
    
    def calculate_take_profit(self, entry_price: float, side: str,
                              risk_reward: float = 2.0) -> float:
        """
        Calculate take profit price
        
        Args:
            entry_price: Entry price
            side: 'BUY' or 'SELL'
            risk_reward: Risk/reward ratio
            
        Returns:
            Take profit price
        """
        risk_amount = entry_price * (self.risk_per_trade / 100)
        reward_amount = risk_amount * risk_reward
        
        if side == 'BUY':
            return entry_price + reward_amount
        else:
            return entry_price - reward_amount
    
    def to_dict(self) -> Dict:
        """Convert strategy to dictionary"""
        return {
            'instance_id': self.instance_id,
            'name': self.name,
            'category': self.category,
            'version': self.version,
            'config': self.config,
            'symbols': self.symbols,
            'timeframe': self.timeframe,
            'is_running': self.is_running,
            'is_paused': self.is_paused,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'stopped_at': self.stopped_at.isoformat() if self.stopped_at else None,
            'metrics': self.metrics
        }