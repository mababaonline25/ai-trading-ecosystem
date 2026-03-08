"""
Moving Average Crossover Strategy
Classic trend-following strategy using multiple MAs
"""

import numpy as np
from typing import Dict, List, Optional
from datetime import datetime

from ..base import BaseStrategy
from ...analysis.technical.indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class MovingAverageCrossStrategy(BaseStrategy):
    """
    Moving Average Crossover Strategy
    
    Generates signals when faster MA crosses slower MA:
    - Golden Cross: Fast MA crosses above Slow MA (BUY)
    - Death Cross: Fast MA crosses below Slow MA (SELL)
    
    Multiple MA combinations supported:
    - SMA 10/20, 20/50, 50/200
    - EMA 12/26 (MACD basis)
    - Hull MA with different periods
    """
    
    category = "technical"
    version = "2.0.0"
    
    def __init__(self, instance_id: str, config: Dict):
        super().__init__(instance_id, config)
        
        # Strategy parameters
        self.fast_period = config.get('fast_period', 10)
        self.slow_period = config.get('slow_period', 30)
        self.ma_type = config.get('ma_type', 'sma')  # sma, ema, hma, alma
        self.signal_threshold = config.get('signal_threshold', 0.5)  # % crossover threshold
        self.use_volume_confirmation = config.get('use_volume_confirmation', True)
        self.volume_threshold = config.get('volume_threshold', 1.5)  # 1.5x average
        
        # State
        self.last_cross = {}
        self.ma_history = {}
        
        logger.info(f"📊 MA Cross Strategy configured: {self.fast_period}/{self.slow_period} {self.ma_type}")
    
    @classmethod
    def get_parameters(cls) -> Dict:
        params = super().get_parameters()
        params['required'].extend([])
        params['optional'].update({
            'fast_period': {'type': 'int', 'default': 10, 'min': 5, 'max': 50},
            'slow_period': {'type': 'int', 'default': 30, 'min': 10, 'max': 200},
            'ma_type': {'type': 'str', 'default': 'sma', 'options': ['sma', 'ema', 'hma', 'alma']},
            'signal_threshold': {'type': 'float', 'default': 0.5, 'min': 0.1, 'max': 5},
            'use_volume_confirmation': {'type': 'bool', 'default': True},
            'volume_threshold': {'type': 'float', 'default': 1.5, 'min': 1.0, 'max': 5.0}
        })
        return params
    
    async def analyze(self, market_data: Dict) -> List[Dict]:
        signals = []
        
        for symbol in self.symbols:
            if symbol not in market_data:
                continue
            
            data = market_data[symbol]
            klines = data.get('klines', [])
            
            if len(klines) < self.slow_period + 10:
                logger.warning(f"Insufficient data for {symbol}")
                continue
            
            # Extract prices
            closes = np.array([k['close'] for k in klines])
            volumes = np.array([k['volume'] for k in klines])
            
            # Calculate moving averages
            fast_ma = self._calculate_ma(closes, self.fast_period)
            slow_ma = self._calculate_ma(closes, self.slow_period)
            
            if fast_ma is None or slow_ma is None:
                continue
            
            # Get current and previous values
            current_fast = fast_ma[-1]
            current_slow = slow_ma[-1]
            prev_fast = fast_ma[-2] if len(fast_ma) > 1 else current_fast
            prev_slow = slow_ma[-2] if len(slow_ma) > 1 else current_slow
            
            # Calculate crossover
            current_diff = (current_fast - current_slow) / current_slow * 100
            prev_diff = (prev_fast - prev_slow) / prev_slow * 100
            
            # Check for crossover
            signal = None
            confidence = 0
            reason = []
            
            # Golden Cross (Fast crosses above Slow)
            if prev_diff <= self.signal_threshold and current_diff > self.signal_threshold:
                signal = 'BUY'
                confidence = 70
                reason.append(f"Golden cross: {self.ma_type.upper()} {self.fast_period} crossed above {self.slow_period}")
                
                # Check volume confirmation
                if self.use_volume_confirmation:
                    avg_volume = np.mean(volumes[-20:])
                    current_volume = volumes[-1]
                    if current_volume > avg_volume * self.volume_threshold:
                        confidence += 10
                        reason.append("Volume confirmation")
                    else:
                        confidence -= 10
                        reason.append("Low volume")
            
            # Death Cross (Fast crosses below Slow)
            elif prev_diff >= -self.signal_threshold and current_diff < -self.signal_threshold:
                signal = 'SELL'
                confidence = 70
                reason.append(f"Death cross: {self.ma_type.upper()} {self.fast_period} crossed below {self.slow_period}")
                
                if self.use_volume_confirmation:
                    avg_volume = np.mean(volumes[-20:])
                    current_volume = volumes[-1]
                    if current_volume > avg_volume * self.volume_threshold:
                        confidence += 10
                        reason.append("Volume confirmation")
                    else:
                        confidence -= 10
                        reason.append("Low volume")
            
            # Check for trend strength
            if signal:
                # Calculate trend strength using ADX
                highs = np.array([k['high'] for k in klines])
                lows = np.array([k['low'] for k in klines])
                
                from ...analysis.technical.indicators import TechnicalIndicators
                adx_data = TechnicalIndicators.adx(highs, lows, closes, 14)
                adx = adx_data['adx'][-1]
                
                if adx > 25:
                    confidence += 10
                    reason.append(f"Strong trend (ADX: {adx:.1f})")
                elif adx < 20:
                    confidence -= 10
                    reason.append(f"Weak trend (ADX: {adx:.1f})")
                
                # Create signal
                current_price = closes[-1]
                signal_data = {
                    'symbol': symbol,
                    'action': signal,
                    'confidence': min(confidence, 95),
                    'price': current_price,
                    'target_price': self.calculate_take_profit(current_price, signal, 2.0),
                    'stop_loss': self.calculate_stop_loss(current_price, signal),
                    'reason': ', '.join(reason),
                    'indicators': {
                        'fast_ma': float(current_fast),
                        'slow_ma': float(current_slow),
                        'crossover': float(current_diff),
                        'adx': float(adx)
                    },
                    'strategy': 'ma_cross',
                    'timestamp': datetime.now().isoformat()
                }
                
                signals.append(signal_data)
                
                # Update state
                self.last_cross[symbol] = {
                    'type': signal,
                    'timestamp': datetime.now(),
                    'fast': current_fast,
                    'slow': current_slow
                }
        
        return signals
    
    def _calculate_ma(self, prices: np.ndarray, period: int) -> Optional[np.ndarray]:
        """Calculate moving average based on type"""
        if len(prices) < period:
            return None
        
        if self.ma_type == 'sma':
            # Simple Moving Average
            result = np.zeros_like(prices)
            for i in range(period - 1, len(prices)):
                result[i] = np.mean(prices[i - period + 1:i + 1])
            result[:period - 1] = np.nan
            return result
        
        elif self.ma_type == 'ema':
            # Exponential Moving Average
            result = np.zeros_like(prices)
            multiplier = 2 / (period + 1)
            result[0] = prices[0]
            for i in range(1, len(prices)):
                result[i] = (prices[i] - result[i - 1]) * multiplier + result[i - 1]
            return result
        
        elif self.ma_type == 'hma':
            # Hull Moving Average
            half_period = period // 2
            sqrt_period = int(np.sqrt(period))
            
            # Calculate WMA
            def wma(data, p):
                weights = np.arange(1, p + 1)
                result = np.zeros_like(data)
                for i in range(p - 1, len(data)):
                    result[i] = np.sum(data[i - p + 1:i + 1] * weights) / weights.sum()
                return result
            
            wma_half = wma(prices, half_period)
            wma_full = wma(prices, period)
            
            raw_hma = 2 * wma_half - wma_full
            hma = wma(raw_hma, sqrt_period)
            return hma
        
        elif self.ma_type == 'alma':
            # Arnaud Legoux Moving Average
            sigma = self.config.get('alma_sigma', 6.0)
            offset = self.config.get('alma_offset', 0.85)
            
            result = np.zeros_like(prices)
            m = offset * (period - 1)
            s = period / sigma
            
            weights = np.zeros(period)
            for i in range(period):
                weights[i] = np.exp(-((i - m) ** 2) / (2 * s ** 2))
            weights /= weights.sum()
            
            for i in range(period - 1, len(prices)):
                result[i] = np.sum(prices[i - period + 1:i + 1] * weights[::-1])
            return result
        
        else:
            raise ValueError(f"Unknown MA type: {self.ma_type}")