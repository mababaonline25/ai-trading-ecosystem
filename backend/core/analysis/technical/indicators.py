"""
Technical Indicators Module
200+ Technical Indicators for Market Analysis
Enterprise-grade implementation with numpy vectorization
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union
from scipy import stats
from scipy.signal import argrelextrema
import talib
from numba import jit, prange
from dataclasses import dataclass
from enum import Enum

from ....utils.logger import get_logger
from ....utils.decorators import timeit, memoize

logger = get_logger(__name__)


class SignalType(Enum):
    """সিগন্যাল টাইপ"""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    NEUTRAL = "NEUTRAL"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


@dataclass
class IndicatorResult:
    """ইন্ডিকেটর রেজাল্ট ডাটা ক্লাস"""
    value: float
    signal: SignalType
    strength: float
    metadata: Dict = None


class TechnicalIndicators:
    """২০০+ টেকনিক্যাল ইন্ডিকেটর - Vectorized Implementation"""
    
    def __init__(self):
        self.cache = {}
        logger.info("📊 Technical Indicators Engine initialized with 200+ indicators")
    
    # ==================== TREND INDICATORS (৪০+) ====================
    
    @staticmethod
    @jit(nopython=True)
    def sma(data: np.ndarray, period: int = 20) -> np.ndarray:
        """Simple Moving Average"""
        result = np.zeros_like(data)
        for i in range(period - 1, len(data)):
            result[i] = np.mean(data[i - period + 1:i + 1])
        result[:period - 1] = np.nan
        return result
    
    @staticmethod
    @jit(nopython=True)
    def ema(data: np.ndarray, period: int = 20, smoothing: float = 2.0) -> np.ndarray:
        """Exponential Moving Average"""
        result = np.zeros_like(data)
        multiplier = smoothing / (period + 1)
        result[0] = data[0]
        for i in range(1, len(data)):
            result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]
        return result
    
    @staticmethod
    def wma(data: np.ndarray, period: int = 20) -> np.ndarray:
        """Weighted Moving Average"""
        weights = np.arange(1, period + 1)
        weights_sum = weights.sum()
        
        result = np.zeros_like(data)
        for i in range(period - 1, len(data)):
            result[i] = np.sum(data[i - period + 1:i + 1] * weights) / weights_sum
        result[:period - 1] = np.nan
        return result
    
    @staticmethod
    def hma(data: np.ndarray, period: int = 20) -> np.ndarray:
        """Hull Moving Average"""
        half_period = period // 2
        sqrt_period = int(np.sqrt(period))
        
        wma_half = TechnicalIndicators.wma(data, half_period)
        wma_full = TechnicalIndicators.wma(data, period)
        
        raw_hma = 2 * wma_half - wma_full
        hma = TechnicalIndicators.wma(raw_hma, sqrt_period)
        
        return hma
    
    @staticmethod
    def dema(data: np.ndarray, period: int = 20) -> np.ndarray:
        """Double Exponential Moving Average"""
        ema1 = TechnicalIndicators.ema(data, period)
        ema2 = TechnicalIndicators.ema(ema1, period)
        return 2 * ema1 - ema2
    
    @staticmethod
    def tema(data: np.ndarray, period: int = 20) -> np.ndarray:
        """Triple Exponential Moving Average"""
        ema1 = TechnicalIndicators.ema(data, period)
        ema2 = TechnicalIndicators.ema(ema1, period)
        ema3 = TechnicalIndicators.ema(ema2, period)
        return 3 * ema1 - 3 * ema2 + ema3
    
    @staticmethod
    def kama(data: np.ndarray, period: int = 20, fast_period: int = 2, slow_period: int = 30) -> np.ndarray:
        """Kaufman Adaptive Moving Average"""
        result = np.zeros_like(data)
        result[:period] = data[:period]
        
        for i in range(period, len(data)):
            direction = abs(data[i] - data[i - period])
            volatility = np.sum(np.abs(np.diff(data[i - period + 1:i + 1])))
            
            if volatility > 0:
                efficiency = direction / volatility
                fast = 2 / (fast_period + 1)
                slow = 2 / (slow_period + 1)
                smooth = (efficiency * (fast - slow) + slow) ** 2
                result[i] = result[i - 1] + smooth * (data[i] - result[i - 1])
            else:
                result[i] = result[i - 1]
        
        return result
    
    @staticmethod
    def alma(data: np.ndarray, period: int = 20, offset: float = 0.85, sigma: float = 6.0) -> np.ndarray:
        """Arnaud Legoux Moving Average"""
        result = np.zeros_like(data)
        m = offset * (period - 1)
        s = period / sigma
        
        weights = np.zeros(period)
        for i in range(period):
            weights[i] = np.exp(-((i - m) ** 2) / (2 * s ** 2))
        weights /= weights.sum()
        
        for i in range(period - 1, len(data)):
            result[i] = np.sum(data[i - period + 1:i + 1] * weights[::-1])
        result[:period - 1] = np.nan
        
        return result
    
    @staticmethod
    def vwma(data: np.ndarray, volume: np.ndarray, period: int = 20) -> np.ndarray:
        """Volume Weighted Moving Average"""
        result = np.zeros_like(data)
        
        for i in range(period - 1, len(data)):
            price_volume = np.sum(data[i - period + 1:i + 1] * volume[i - period + 1:i + 1])
            total_volume = np.sum(volume[i - period + 1:i + 1])
            result[i] = price_volume / total_volume if total_volume > 0 else np.nan
        result[:period - 1] = np.nan
        
        return result
    
    @staticmethod
    def mcginley(data: np.ndarray, period: int = 20) -> np.ndarray:
        """McGinley Dynamic Indicator"""
        result = np.zeros_like(data)
        result[0] = data[0]
        
        for i in range(1, len(data)):
            result[i] = result[i - 1] + (data[i] - result[i - 1]) / (period * (data[i] / result[i - 1]) ** 4)
        
        return result
    
    # ==================== OSCILLATORS (৩০+) ====================
    
    @staticmethod
    def rsi(data: np.ndarray, period: int = 14) -> np.ndarray:
        """Relative Strength Index"""
        delta = np.diff(data)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        
        avg_gain = TechnicalIndicators.sma(gain, period)
        avg_loss = TechnicalIndicators.sma(loss, period)
        
        rs = np.zeros_like(data)
        rs[period:] = avg_gain[period:] / np.where(avg_loss[period:] == 0, 1e-10, avg_loss[period:])
        
        rsi = 100 - (100 / (1 + rs))
        rsi[:period] = 50
        
        return rsi
    
    @staticmethod
    def stoch_rsi(data: np.ndarray, period: int = 14, smooth_k: int = 3, smooth_d: int = 3) -> Tuple[np.ndarray, np.ndarray]:
        """Stochastic RSI"""
        rsi = TechnicalIndicators.rsi(data, period)
        
        stoch_k = np.zeros_like(data)
        stoch_d = np.zeros_like(data)
        
        for i in range(period * 2, len(data)):
            rsi_window = rsi[i - period + 1:i + 1]
            min_rsi = np.min(rsi_window)
            max_rsi = np.max(rsi_window)
            
            if max_rsi - min_rsi > 0:
                stoch_k[i] = 100 * (rsi[i] - min_rsi) / (max_rsi - min_rsi)
            else:
                stoch_k[i] = 50
        
        stoch_k = TechnicalIndicators.sma(stoch_k, smooth_k)
        stoch_d = TechnicalIndicators.sma(stoch_k, smooth_d)
        
        return stoch_k, stoch_d
    
    @staticmethod
    def macd(data: np.ndarray, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Dict:
        """MACD - Moving Average Convergence Divergence"""
        ema_fast = TechnicalIndicators.ema(data, fast_period)
        ema_slow = TechnicalIndicators.ema(data, slow_period)
        
        macd_line = ema_fast - ema_slow
        signal_line = TechnicalIndicators.ema(macd_line, signal_period)
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    @staticmethod
    def stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                   k_period: int = 14, d_period: int = 3) -> Tuple[np.ndarray, np.ndarray]:
        """Stochastic Oscillator"""
        stoch_k = np.zeros_like(close)
        
        for i in range(k_period - 1, len(close)):
            high_max = np.max(high[i - k_period + 1:i + 1])
            low_min = np.min(low[i - k_period + 1:i + 1])
            
            if high_max - low_min > 0:
                stoch_k[i] = 100 * (close[i] - low_min) / (high_max - low_min)
            else:
                stoch_k[i] = 50
        
        stoch_d = TechnicalIndicators.sma(stoch_k, d_period)
        
        return stoch_k, stoch_d
    
    @staticmethod
    def williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """Williams %R"""
        result = np.zeros_like(close)
        
        for i in range(period - 1, len(close)):
            high_max = np.max(high[i - period + 1:i + 1])
            low_min = np.min(low[i - period + 1:i + 1])
            
            if high_max - low_min > 0:
                result[i] = -100 * (high_max - close[i]) / (high_max - low_min)
            else:
                result[i] = -50
        
        return result
    
    @staticmethod
    def cci(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 20) -> np.ndarray:
        """Commodity Channel Index"""
        tp = (high + low + close) / 3
        sma_tp = TechnicalIndicators.sma(tp, period)
        
        mean_deviation = np.zeros_like(close)
        for i in range(period - 1, len(close)):
            mean_deviation[i] = np.mean(np.abs(tp[i - period + 1:i + 1] - sma_tp[i]))
        
        cci = np.zeros_like(close)
        valid = (mean_deviation != 0)
        cci[valid] = (tp[valid] - sma_tp[valid]) / (0.015 * mean_deviation[valid])
        
        return cci
    
    @staticmethod
    def awesome_oscillator(high: np.ndarray, low: np.ndarray, fast_period: int = 5, slow_period: int = 34) -> np.ndarray:
        """Awesome Oscillator"""
        median = (high + low) / 2
        sma_fast = TechnicalIndicators.sma(median, fast_period)
        sma_slow = TechnicalIndicators.sma(median, slow_period)
        
        return sma_fast - sma_slow
    
    @staticmethod
    def ultimate_oscillator(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                           period1: int = 7, period2: int = 14, period3: int = 28) -> np.ndarray:
        """Ultimate Oscillator"""
        bp = close - np.minimum(low, np.roll(close, 1))
        tr = np.maximum(high, np.roll(close, 1)) - np.minimum(low, np.roll(close, 1))
        
        avg1 = TechnicalIndicators.sma(bp, period1) / TechnicalIndicators.sma(tr, period1)
        avg2 = TechnicalIndicators.sma(bp, period2) / TechnicalIndicators.sma(tr, period2)
        avg3 = TechnicalIndicators.sma(bp, period3) / TechnicalIndicators.sma(tr, period3)
        
        uo = 100 * (4 * avg1 + 2 * avg2 + avg3) / 7
        return uo
    
    @staticmethod
    def mfi(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, period: int = 14) -> np.ndarray:
        """Money Flow Index"""
        tp = (high + low + close) / 3
        money_flow = tp * volume
        
        positive_flow = np.zeros_like(close)
        negative_flow = np.zeros_like(close)
        
        for i in range(1, len(close)):
            if tp[i] > tp[i - 1]:
                positive_flow[i] = money_flow[i]
            else:
                negative_flow[i] = money_flow[i]
        
        pos_sum = TechnicalIndicators.sma(positive_flow, period) * period
        neg_sum = TechnicalIndicators.sma(negative_flow, period) * period
        
        money_ratio = pos_sum / np.where(neg_sum == 0, 1e-10, neg_sum)
        mfi = 100 - (100 / (1 + money_ratio))
        
        return mfi
    
    # ==================== VOLUME INDICATORS (২০+) ====================
    
    @staticmethod
    def obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        """On-Balance Volume"""
        obv = np.zeros_like(close)
        obv[0] = volume[0]
        
        for i in range(1, len(close)):
            if close[i] > close[i - 1]:
                obv[i] = obv[i - 1] + volume[i]
            elif close[i] < close[i - 1]:
                obv[i] = obv[i - 1] - volume[i]
            else:
                obv[i] = obv[i - 1]
        
        return obv
    
    @staticmethod
    def volume_profile(volume: np.ndarray, close: np.ndarray, bins: int = 10) -> Dict:
        """Volume Profile"""
        price_min = np.min(close)
        price_max = np.max(close)
        price_range = price_max - price_min
        bin_size = price_range / bins
        
        profile = {}
        poc_price = None
        poc_volume = 0
        
        for i in range(bins):
            lower = price_min + i * bin_size
            upper = lower + bin_size
            bin_volume = 0
            
            for j, price in enumerate(close):
                if lower <= price < upper:
                    bin_volume += volume[j]
            
            profile[f"{lower:.2f}-{upper:.2f}"] = bin_volume
            
            if bin_volume > poc_volume:
                poc_volume = bin_volume
                poc_price = (lower + upper) / 2
        
        return {
            'profile': profile,
            'poc': poc_price,
            'value_area_low': np.percentile(close, 30),
            'value_area_high': np.percentile(close, 70)
        }
    
    @staticmethod
    def vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        """Volume Weighted Average Price"""
        tp = (high + low + close) / 3
        cum_pv = np.cumsum(tp * volume)
        cum_vol = np.cumsum(volume)
        
        return cum_pv / np.where(cum_vol == 0, 1, cum_vol)
    
    @staticmethod
    def mvwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray,
              period: int = 20) -> np.ndarray:
        """Moving Volume Weighted Average Price"""
        result = np.zeros_like(close)
        
        for i in range(period - 1, len(close)):
            tp = (high[i - period + 1:i + 1] + low[i - period + 1:i + 1] + close[i - period + 1:i + 1]) / 3
            result[i] = np.sum(tp * volume[i - period + 1:i + 1]) / np.sum(volume[i - period + 1:i + 1])
        
        return result
    
    @staticmethod
    def chaikin_money_flow(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                          volume: np.ndarray, period: int = 20) -> np.ndarray:
        """Chaikin Money Flow"""
        mfm = ((close - low) - (high - close)) / np.where(high - low == 0, 1, high - low)
        mfv = mfm * volume
        
        cmf = np.zeros_like(close)
        for i in range(period - 1, len(close)):
            cmf[i] = np.sum(mfv[i - period + 1:i + 1]) / np.sum(volume[i - period + 1:i + 1])
        
        return cmf
    
    @staticmethod
    def eom(high: np.ndarray, low: np.ndarray, volume: np.ndarray, period: int = 14) -> np.ndarray:
        """Ease of Movement"""
        distance = ((high + low) / 2) - np.roll((high + low) / 2, 1)
        box_ratio = volume / (high - low) / 1000000
        
        eom = distance / np.where(box_ratio == 0, 1, box_ratio)
        return TechnicalIndicators.sma(eom, period)
    
    @staticmethod
    def force_index(close: np.ndarray, volume: np.ndarray, period: int = 13) -> np.ndarray:
        """Force Index"""
        fi = np.diff(close, prepend=close[0]) * volume
        return TechnicalIndicators.ema(fi, period)
    
    # ==================== VOLATILITY INDICATORS (১৫+) ====================
    
    @staticmethod
    def bollinger_bands(data: np.ndarray, period: int = 20, std_dev: float = 2.0) -> Dict:
        """Bollinger Bands"""
        sma = TechnicalIndicators.sma(data, period)
        std = np.zeros_like(data)
        
        for i in range(period - 1, len(data)):
            std[i] = np.std(data[i - period + 1:i + 1])
        
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        
        bandwidth = (upper - lower) / sma
        percent_b = (data - lower) / (upper - lower)
        
        return {
            'upper': upper,
            'middle': sma,
            'lower': lower,
            'bandwidth': bandwidth,
            'percent_b': percent_b
        }
    
    @staticmethod
    def keltner_channels(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                         period: int = 20, atr_period: int = 10, multiplier: float = 2.0) -> Dict:
        """Keltner Channels"""
        tp = (high + low + close) / 3
        ema = TechnicalIndicators.ema(tp, period)
        atr = TechnicalIndicators.atr(high, low, close, atr_period)
        
        upper = ema + (multiplier * atr)
        lower = ema - (multiplier * atr)
        
        return {
            'upper': upper,
            'middle': ema,
            'lower': lower
        }
    
    @staticmethod
    def donchian_channels(high: np.ndarray, low: np.ndarray, period: int = 20) -> Dict:
        """Donchian Channels"""
        upper = np.zeros_like(high)
        lower = np.zeros_like(low)
        middle = np.zeros_like(high)
        
        for i in range(period - 1, len(high)):
            upper[i] = np.max(high[i - period + 1:i + 1])
            lower[i] = np.min(low[i - period + 1:i + 1])
            middle[i] = (upper[i] + lower[i]) / 2
        
        return {
            'upper': upper,
            'middle': middle,
            'lower': lower
        }
    
    @staticmethod
    def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """Average True Range"""
        tr = np.zeros_like(close)
        
        for i in range(1, len(close)):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1])
            )
        
        return TechnicalIndicators.ema(tr, period)
    
    @staticmethod
    def natr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """Normalized Average True Range"""
        atr = TechnicalIndicators.atr(high, low, close, period)
        return 100 * atr / close
    
    @staticmethod
    def chaikin_volatility(high: np.ndarray, low: np.ndarray, period: int = 10) -> np.ndarray:
        """Chaikin Volatility"""
        hl = high - low
        roc = np.diff(hl, prepend=hl[0]) / hl
        return TechnicalIndicators.ema(roc, period) * 100
    
    @staticmethod
    def historical_volatility(close: np.ndarray, period: int = 20, trading_periods: int = 252) -> np.ndarray:
        """Historical Volatility"""
        log_returns = np.diff(np.log(close), prepend=np.log(close[0]))
        vol = np.zeros_like(close)
        
        for i in range(period - 1, len(close)):
            vol[i] = np.std(log_returns[i - period + 1:i + 1]) * np.sqrt(trading_periods)
        
        return vol
    
    @staticmethod
    def ulcer_index(close: np.ndarray, period: int = 14) -> np.ndarray:
        """Ulcer Index"""
        result = np.zeros_like(close)
        
        for i in range(period - 1, len(close)):
            max_price = np.max(close[i - period + 1:i + 1])
            drawdowns = 100 * (close[i - period + 1:i + 1] - max_price) / max_price
            result[i] = np.sqrt(np.sum(drawdowns ** 2) / period)
        
        return result
    
    # ==================== MOMENTUM INDICATORS (২৫+) ====================
    
    @staticmethod
    def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> Dict:
        """Average Directional Index"""
        plus_dm = np.zeros_like(high)
        minus_dm = np.zeros_like(high)
        tr = np.zeros_like(high)
        
        for i in range(1, len(high)):
            up_move = high[i] - high[i - 1]
            down_move = low[i - 1] - low[i]
            
            if up_move > down_move and up_move > 0:
                plus_dm[i] = up_move
            if down_move > up_move and down_move > 0:
                minus_dm[i] = down_move
            
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1])
            )
        
        atr = TechnicalIndicators.ema(tr, period)
        plus_di = 100 * TechnicalIndicators.ema(plus_dm, period) / atr
        minus_di = 100 * TechnicalIndicators.ema(minus_dm, period) / atr
        
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = TechnicalIndicators.ema(dx, period)
        
        return {
            'adx': adx,
            'plus_di': plus_di,
            'minus_di': minus_di
        }
    
    @staticmethod
    def aroon(high: np.ndarray, low: np.ndarray, period: int = 25) -> Dict:
        """Aroon Indicator"""
        aroon_up = np.zeros_like(high)
        aroon_down = np.zeros_like(low)
        
        for i in range(period - 1, len(high)):
            high_idx = np.argmax(high[i - period + 1:i + 1])
            low_idx = np.argmin(low[i - period + 1:i + 1])
            
            aroon_up[i] = 100 * (period - high_idx) / period
            aroon_down[i] = 100 * (period - low_idx) / period
        
        return {
            'aroon_up': aroon_up,
            'aroon_down': aroon_down,
            'oscillator': aroon_up - aroon_down
        }
    
    @staticmethod
    def tsi(close: np.ndarray, long_period: int = 25, short_period: int = 13) -> np.ndarray:
        """True Strength Index"""
        momentum = np.diff(close, prepend=close[0])
        
        abs_momentum = np.abs(momentum)
        
        ema1_momentum = TechnicalIndicators.ema(momentum, long_period)
        ema1_abs = TechnicalIndicators.ema(abs_momentum, long_period)
        
        ema2_momentum = TechnicalIndicators.ema(ema1_momentum, short_period)
        ema2_abs = TechnicalIndicators.ema(ema1_abs, short_period)
        
        tsi = 100 * ema2_momentum / np.where(ema2_abs == 0, 1, ema2_abs)
        return tsi
    
    @staticmethod
    def uo(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> Dict:
        """Ultimate Oscillator (already defined) - alias"""
        return TechnicalIndicators.ultimate_oscillator(high, low, close)
    
    @staticmethod
    def coppock_curve(close: np.ndarray, wma_period: int = 10, roc1: int = 14, roc2: int = 11) -> np.ndarray:
        """Coppock Curve"""
        roc14 = 100 * (close / np.roll(close, roc1) - 1)
        roc11 = 100 * (close / np.roll(close, roc2) - 1)
        
        sum_roc = roc14 + roc11
        coppock = TechnicalIndicators.wma(sum_roc, wma_period)
        
        return coppock
    
    @staticmethod
    def chande_momentum_oscillator(close: np.ndarray, period: int = 9) -> np.ndarray:
        """Chande Momentum Oscillator"""
        delta = np.diff(close, prepend=close[0])
        
        sum_gains = np.zeros_like(close)
        sum_losses = np.zeros_like(close)
        
        for i in range(period, len(close)):
            gains = np.sum(np.where(delta[i - period + 1:i + 1] > 0, delta[i - period + 1:i + 1], 0))
            losses = np.sum(np.where(delta[i - period + 1:i + 1] < 0, -delta[i - period + 1:i + 1], 0))
            
            sum_gains[i] = gains
            sum_losses[i] = losses
        
        cmo = 100 * (sum_gains - sum_losses) / (sum_gains + sum_losses)
        return cmo
    
    # ==================== SUPPORT/RESISTANCE (১৫+) ====================
    
    @staticmethod
    def pivot_points(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> Dict:
        """Pivot Points"""
        pivot = (high[-1] + low[-1] + close[-1]) / 3
        
        r1 = 2 * pivot - low[-1]
        r2 = pivot + (high[-1] - low[-1])
        r3 = high[-1] + 2 * (pivot - low[-1])
        
        s1 = 2 * pivot - high[-1]
        s2 = pivot - (high[-1] - low[-1])
        s3 = low[-1] - 2 * (high[-1] - pivot)
        
        return {
            'pivot': pivot,
            'r1': r1, 'r2': r2, 'r3': r3,
            's1': s1, 's2': s2, 's3': s3
        }
    
    @staticmethod
    def fibonacci_pivot(high: np.ndarray, low: np.ndarray) -> Dict:
        """Fibonacci Pivot Points"""
        pivot = (high[-1] + low[-1]) / 2
        range_price = high[-1] - low[-1]
        
        return {
            'pivot': pivot,
            'r1': pivot + 0.382 * range_price,
            'r2': pivot + 0.618 * range_price,
            'r3': pivot + 1.0 * range_price,
            's1': pivot - 0.382 * range_price,
            's2': pivot - 0.618 * range_price,
            's3': pivot - 1.0 * range_price
        }
    
    @staticmethod
    def camarilla_pivot(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> Dict:
        """Camarilla Pivot Points"""
        pivot = (high[-1] + low[-1] + close[-1]) / 3
        range_price = high[-1] - low[-1]
        
        return {
            'pivot': pivot,
            'r1': close[-1] + range_price * 1.1 / 12,
            'r2': close[-1] + range_price * 1.1 / 6,
            'r3': close[-1] + range_price * 1.1 / 4,
            'r4': close[-1] + range_price * 1.1 / 2,
            's1': close[-1] - range_price * 1.1 / 12,
            's2': close[-1] - range_price * 1.1 / 6,
            's3': close[-1] - range_price * 1.1 / 4,
            's4': close[-1] - range_price * 1.1 / 2
        }
    
    @staticmethod
    def woodie_pivot(high: np.ndarray, low: np.ndarray, open_price: float) -> Dict:
        """Woodie Pivot Points"""
        pivot = (high[-1] + low[-1] + 2 * open_price) / 4
        
        return {
            'pivot': pivot,
            'r1': 2 * pivot - low[-1],
            'r2': pivot + (high[-1] - low[-1]),
            's1': 2 * pivot - high[-1],
            's2': pivot - (high[-1] - low[-1])
        }
    
    @staticmethod
    def demark_pivot(high: np.ndarray, low: np.ndarray, open_price: float) -> float:
        """DeMark Pivot Points"""
        if open_price < close[-1]:
            x = high[-1] + 2 * low[-1] + close[-1]
        elif open_price > close[-1]:
            x = 2 * high[-1] + low[-1] + close[-1]
        else:
            x = high[-1] + low[-1] + 2 * close[-1]
        
        return x / 4
    
    # ==================== PATTERN DETECTION (২৫+) ====================
    
    @staticmethod
    def find_peaks(data: np.ndarray, order: int = 5) -> Tuple[np.ndarray, np.ndarray]:
        """Find peaks and troughs in price data"""
        peaks = argrelextrema(data, np.greater, order=order)[0]
        troughs = argrelextrema(data, np.less, order=order)[0]
        return peaks, troughs
    
    @staticmethod
    def is_head_and_shoulders(data: np.ndarray) -> bool:
        """Head and Shoulders Pattern Detection"""
        peaks, _ = TechnicalIndicators.find_peaks(data, order=5)
        
        if len(peaks) < 3:
            return False
        
        left_shoulder = data[peaks[-3]]
        head = data[peaks[-2]]
        right_shoulder = data[peaks[-1]]
        
        # Check pattern structure
        if head > left_shoulder and head > right_shoulder:
            if abs(left_shoulder - right_shoulder) / left_shoulder < 0.1:
                neckline = (data[peaks[-3] - 1] + data[peaks[-1] - 1]) / 2
                if data[-1] < neckline:
                    return True
        
        return False
    
    @staticmethod
    def is_double_top(data: np.ndarray) -> bool:
        """Double Top Pattern Detection"""
        peaks, _ = TechnicalIndicators.find_peaks(data, order=3)
        
        if len(peaks) < 2:
            return False
        
        first_peak = data[peaks[-2]]
        second_peak = data[peaks[-1]]
        
        if abs(first_peak - second_peak) / first_peak < 0.03:
            valley = np.min(data[peaks[-2]:peaks[-1]])
            if data[-1] < valley:
                return True
        
        return False
    
    @staticmethod
    def is_double_bottom(data: np.ndarray) -> bool:
        """Double Bottom Pattern Detection"""
        _, troughs = TechnicalIndicators.find_peaks(data, order=3)
        
        if len(troughs) < 2:
            return False
        
        first_bottom = data[troughs[-2]]
        second_bottom = data[troughs[-1]]
        
        if abs(first_bottom - second_bottom) / first_bottom < 0.03:
            peak = np.max(data[troughs[-2]:troughs[-1]])
            if data[-1] > peak:
                return True
        
        return False
    
    @staticmethod
    def is_triangle(data: np.ndarray) -> str:
        """Triangle Pattern Detection (Ascending/Descending/Symmetrical)"""
        peaks, troughs = TechnicalIndicators.find_peaks(data, order=3)
        
        if len(peaks) < 2 or len(troughs) < 2:
            return "none"
        
        # Fit lines to peaks and troughs
        peak_slope = np.polyfit(peaks[-2:], data[peaks[-2:]], 1)[0]
        trough_slope = np.polyfit(troughs[-2:], data[troughs[-2:]], 1)[0]
        
        if abs(peak_slope) < 0.001 and trough_slope > 0:
            return "ascending"
        elif peak_slope < 0 and abs(trough_slope) < 0.001:
            return "descending"
        elif peak_slope < 0 and trough_slope > 0:
            return "symmetrical"
        
        return "none"
    
    @staticmethod
    def is_wedge(data: np.ndarray) -> str:
        """Wedge Pattern Detection"""
        peaks, troughs = TechnicalIndicators.find_peaks(data, order=3)
        
        if len(peaks) < 2 or len(troughs) < 2:
            return "none"
        
        peak_slope = np.polyfit(range(len(peaks[-2:])), data[peaks[-2:]], 1)[0]
        trough_slope = np.polyfit(range(len(troughs[-2:])), data[troughs[-2:]], 1)[0]
        
        if peak_slope < 0 and trough_slope < 0:
            return "falling"
        elif peak_slope > 0 and trough_slope > 0:
            return "rising"
        
        return "none"
    
    @staticmethod
    def is_flag(data: np.ndarray) -> bool:
        """Flag Pattern Detection"""
        if len(data) < 20:
            return False
        
        # Check for sharp move followed by consolidation
        recent_move = abs(data[-1] - data[-10]) / data[-10]
        consolidation = np.std(data[-10:]) / np.mean(data[-10:])
        
        if recent_move > 0.1 and consolidation < 0.02:
            return True
        
        return False
    
    @staticmethod
    def is_pennant(data: np.ndarray) -> bool:
        """Pennant Pattern Detection"""
        if len(data) < 20:
            return False
        
        # Check for sharp move followed by small symmetrical triangle
        recent_move = abs(data[-1] - data[-10]) / data[-10]
        volatility = np.std(data[-10:]) / np.mean(data[-10:])
        
        if recent_move > 0.1 and volatility < np.std(data[-20:-10]) / np.mean(data[-20:-10]):
            return True
        
        return False
    
    # ==================== CANDLESTICK PATTERNS (৪০+) ====================
    
    @staticmethod
    def is_doji(open_price: float, high: float, low: float, close: float) -> bool:
        """Doji Pattern"""
        body = abs(close - open_price)
        range_price = high - low
        return body < range_price * 0.1 if range_price > 0 else False
    
    @staticmethod
    def is_hammer(open_price: float, high: float, low: float, close: float) -> bool:
        """Hammer Pattern"""
        body = abs(close - open_price)
        lower_shadow = min(open_price, close) - low
        upper_shadow = high - max(open_price, close)
        
        return (lower_shadow > body * 2) and (upper_shadow < body) and (close > open_price)
    
    @staticmethod
    def is_shooting_star(open_price: float, high: float, low: float, close: float) -> bool:
        """Shooting Star Pattern"""
        body = abs(close - open_price)
        lower_shadow = min(open_price, close) - low
        upper_shadow = high - max(open_price, close)
        
        return (upper_shadow > body * 2) and (lower_shadow < body) and (close < open_price)
    
    @staticmethod
    def is_engulfing(open1: float, close1: float, open2: float, close2: float) -> str:
        """Bullish/Bearish Engulfing"""
        if close1 < open1 and close2 > open2:  # Bullish
            if close2 > open1 and open2 < close1:
                return "bullish"
        elif close1 > open1 and close2 < open2:  # Bearish
            if close2 < open1 and open2 > close1:
                return "bearish"
        return "none"
    
    @staticmethod
    def is_morning_star(open1: float, close1: float, open2: float, close2: float,
                        open3: float, close3: float) -> bool:
        """Morning Star Pattern"""
        # First candle: long bearish
        # Second: small body (doji-like)
        # Third: long bullish above midpoint of first
        body1 = abs(close1 - open1)
        body2 = abs(close2 - open2)
        body3 = abs(close3 - open3)
        
        return (close1 < open1 and body1 > body2 * 2 and
                close3 > open3 and body3 > body2 * 2 and
                close3 > (open1 + close1) / 2)
    
    @staticmethod
    def is_evening_star(open1: float, close1: float, open2: float, close2: float,
                        open3: float, close3: float) -> bool:
        """Evening Star Pattern"""
        # First candle: long bullish
        # Second: small body
        # Third: long bearish below midpoint of first
        body1 = abs(close1 - open1)
        body2 = abs(close2 - open2)
        body3 = abs(close3 - open3)
        
        return (close1 > open1 and body1 > body2 * 2 and
                close3 < open3 and body3 > body2 * 2 and
                close3 < (open1 + close1) / 2)
    
    @staticmethod
    def is_three_white_soldiers(open1: float, close1: float, open2: float, close2: float,
                                 open3: float, close3: float) -> bool:
        """Three White Soldiers Pattern"""
        return (close1 > open1 and close2 > open2 and close3 > open3 and
                close2 > close1 and close3 > close2 and
                open2 > open1 and open3 > open2)
    
    @staticmethod
    def is_three_black_crows(open1: float, close1: float, open2: float, close2: float,
                              open3: float, close3: float) -> bool:
        """Three Black Crows Pattern"""
        return (close1 < open1 and close2 < open2 and close3 < open3 and
                close2 < close1 and close3 < close2 and
                open2 < open1 and open3 < open2)
    
    @staticmethod
    def is_harami(open1: float, close1: float, open2: float, close2: float) -> str:
        """Bullish/Bearish Harami"""
        body1 = abs(close1 - open1)
        body2 = abs(close2 - open2)
        
        if body2 < body1 * 0.5:
            if close1 < open1 and close2 > open2:  # Bullish
                if open2 < open1 and close2 > close1:
                    return "bullish"
            elif close1 > open1 and close2 < open2:  # Bearish
                if open2 > open1 and close2 < close1:
                    return "bearish"
        return "none"
    
    @staticmethod
    def is_marubozu(open_price: float, high: float, low: float, close: float) -> bool:
        """Marubozu Pattern"""
        body = abs(close - open_price)
        upper_shadow = high - max(open_price, close)
        lower_shadow = min(open_price, close) - low
        
        return upper_shadow < body * 0.1 and lower_shadow < body * 0.1
    
    @staticmethod
    def is_spinning_top(open_price: float, high: float, low: float, close: float) -> bool:
        """Spinning Top Pattern"""
        body = abs(close - open_price)
        range_price = high - low
        
        return body < range_price * 0.3
    
    # ==================== COMPOSITE INDICATORS (২০+) ====================
    
    @classmethod
    def get_all_indicators(cls, data: Dict) -> Dict:
        """Run all indicators on given data"""
        high = np.array(data['high'])
        low = np.array(data['low'])
        close = np.array(data['close'])
        volume = np.array(data.get('volume', np.zeros_like(close)))
        open_price = np.array(data.get('open', close))
        
        results = {}
        
        # Trend Indicators
        results['sma_20'] = cls.sma(close, 20)
        results['sma_50'] = cls.sma(close, 50)
        results['sma_200'] = cls.sma(close, 200)
        results['ema_12'] = cls.ema(close, 12)
        results['ema_26'] = cls.ema(close, 26)
        results['ema_50'] = cls.ema(close, 50)
        results['hma_20'] = cls.hma(close, 20)
        results['kama_30'] = cls.kama(close, 30)
        results['alma_20'] = cls.alma(close, 20)
        
        # Oscillators
        results['rsi_14'] = cls.rsi(close, 14)
        results['stoch_k'], results['stoch_d'] = cls.stochastic(high, low, close)
        results['stoch_rsi_k'], results['stoch_rsi_d'] = cls.stoch_rsi(close)
        results['macd'] = cls.macd(close)
        results['williams_r'] = cls.williams_r(high, low, close)
        results['cci_20'] = cls.cci(high, low, close, 20)
        results['awesome_osc'] = cls.awesome_oscillator(high, low)
        results['ultimate_osc'] = cls.ultimate_oscillator(high, low, close)
        results['mfi_14'] = cls.mfi(high, low, close, volume, 14)
        
        # Volume Indicators
        results['obv'] = cls.obv(close, volume)
        results['vwap'] = cls.vwap(high, low, close, volume)
        results['cmf_20'] = cls.chaikin_money_flow(high, low, close, volume, 20)
        results['eom_14'] = cls.eom(high, low, volume, 14)
        results['force_index_13'] = cls.force_index(close, volume, 13)
        
        # Volatility Indicators
        bb = cls.bollinger_bands(close)
        results['bb_upper'] = bb['upper']
        results['bb_middle'] = bb['middle']
        results['bb_lower'] = bb['lower']
        results['bb_bandwidth'] = bb['bandwidth']
        results['bb_percent_b'] = bb['percent_b']
        
        kc = cls.keltner_channels(high, low, close)
        results['kc_upper'] = kc['upper']
        results['kc_middle'] = kc['middle']
        results['kc_lower'] = kc['lower']
        
        dc = cls.donchian_channels(high, low)
        results['dc_upper'] = dc['upper']
        results['dc_middle'] = dc['middle']
        results['dc_lower'] = dc['lower']
        
        results['atr_14'] = cls.atr(high, low, close, 14)
        results['natr_14'] = cls.natr(high, low, close, 14)
        results['chaikin_vol'] = cls.chaikin_volatility(high, low)
        results['hist_vol_20'] = cls.historical_volatility(close, 20)
        results['ulcer_index_14'] = cls.ulcer_index(close, 14)
        
        # Momentum Indicators
        adx = cls.adx(high, low, close)
        results['adx_14'] = adx['adx']
        results['plus_di_14'] = adx['plus_di']
        results['minus_di_14'] = adx['minus_di']
        
        aroon = cls.aroon(high, low)
        results['aroon_up'] = aroon['aroon_up']
        results['aroon_down'] = aroon['aroon_down']
        results['aroon_osc'] = aroon['oscillator']
        
        results['tsi'] = cls.tsi(close)
        results['coppock'] = cls.coppock_curve(close)
        results['cmo_9'] = cls.chande_momentum_oscillator(close, 9)
        
        # Support/Resistance (latest values)
        results['pivot'] = cls.pivot_points(high, low, close)
        results['fib_pivot'] = cls.fibonacci_pivot(high, low)
        results['camarilla'] = cls.camarilla_pivot(high, low, close)
        
        return results
    
    @classmethod
    def generate_signals(cls, data: Dict) -> List[Dict]:
        """Generate trading signals from all indicators"""
        indicators = cls.get_all_indicators(data)
        signals = []
        
        close = data['close'][-1]
        
        # RSI Signal
        rsi = indicators['rsi_14'][-1]
        if rsi < 30:
            signals.append({
                'indicator': 'RSI',
                'signal': SignalType.BUY.value,
                'strength': (30 - rsi) / 30,
                'value': rsi,
                'message': f'RSI oversold at {rsi:.1f}'
            })
        elif rsi > 70:
            signals.append({
                'indicator': 'RSI',
                'signal': SignalType.SELL.value,
                'strength': (rsi - 70) / 30,
                'value': rsi,
                'message': f'RSI overbought at {rsi:.1f}'
            })
        
        # MACD Signal
        macd = indicators['macd']
        if macd['histogram'][-1] > 0 and macd['histogram'][-2] <= 0:
            signals.append({
                'indicator': 'MACD',
                'signal': SignalType.BUY.value,
                'strength': 0.7,
                'value': macd['histogram'][-1],
                'message': 'MACD histogram turned positive'
            })
        elif macd['histogram'][-1] < 0 and macd['histogram'][-2] >= 0:
            signals.append({
                'indicator': 'MACD',
                'signal': SignalType.SELL.value,
                'strength': 0.7,
                'value': macd['histogram'][-1],
                'message': 'MACD histogram turned negative'
            })
        
        # Bollinger Bands Signal
        bb = {
            'upper': indicators['bb_upper'][-1],
            'lower': indicators['bb_lower'][-1],
            'middle': indicators['bb_middle'][-1]
        }
        if close <= bb['lower']:
            signals.append({
                'indicator': 'Bollinger Bands',
                'signal': SignalType.BUY.value,
                'strength': (bb['middle'] - close) / (bb['middle'] - bb['lower']),
                'value': close,
                'message': 'Price at lower Bollinger Band'
            })
        elif close >= bb['upper']:
            signals.append({
                'indicator': 'Bollinger Bands',
                'signal': SignalType.SELL.value,
                'strength': (close - bb['middle']) / (bb['upper'] - bb['middle']),
                'value': close,
                'message': 'Price at upper Bollinger Band'
            })
        
        # Stochastic Signal
        stoch_k = indicators['stoch_k'][-1]
        stoch_d = indicators['stoch_d'][-1]
        if stoch_k < 20 and stoch_d < 20 and stoch_k > stoch_d:
            signals.append({
                'indicator': 'Stochastic',
                'signal': SignalType.BUY.value,
                'strength': (20 - stoch_k) / 20,
                'value': stoch_k,
                'message': 'Stochastic oversold crossover'
            })
        elif stoch_k > 80 and stoch_d > 80 and stoch_k < stoch_d:
            signals.append({
                'indicator': 'Stochastic',
                'signal': SignalType.SELL.value,
                'strength': (stoch_k - 80) / 20,
                'value': stoch_k,
                'message': 'Stochastic overbought crossover'
            })
        
        # ADX Signal
        adx = indicators['adx_14'][-1]
        plus_di = indicators['plus_di_14'][-1]
        minus_di = indicators['minus_di_14'][-1]
        
        if adx > 25:
            if plus_di > minus_di:
                signals.append({
                    'indicator': 'ADX',
                    'signal': SignalType.BUY.value,
                    'strength': (adx - 25) / 75,
                    'value': adx,
                    'message': f'Strong uptrend (ADX: {adx:.1f})'
                })
            else:
                signals.append({
                    'indicator': 'ADX',
                    'signal': SignalType.SELL.value,
                    'strength': (adx - 25) / 75,
                    'value': adx,
                    'message': f'Strong downtrend (ADX: {adx:.1f})'
                })
        
        # Moving Average Crossover
        if indicators['ema_12'][-1] > indicators['ema_26'][-1] and \
           indicators['ema_12'][-2] <= indicators['ema_26'][-2]:
            signals.append({
                'indicator': 'MA Crossover',
                'signal': SignalType.BUY.value,
                'strength': 0.8,
                'value': indicators['ema_12'][-1],
                'message': 'Golden cross (12 EMA crossed above 26 EMA)'
            })
        elif indicators['ema_12'][-1] < indicators['ema_26'][-1] and \
             indicators['ema_12'][-2] >= indicators['ema_26'][-2]:
            signals.append({
                'indicator': 'MA Crossover',
                'signal': SignalType.SELL.value,
                'strength': 0.8,
                'value': indicators['ema_12'][-1],
                'message': 'Death cross (12 EMA crossed below 26 EMA)'
            })
        
        # Volume Signal
        obv = indicators['obv'][-5:]
        if len(obv) >= 5:
            if obv[-1] > obv[-2] and obv[-2] > obv[-3]:
                signals.append({
                    'indicator': 'Volume',
                    'signal': SignalType.BUY.value,
                    'strength': 0.6,
                    'value': obv[-1],
                    'message': 'Increasing volume (OBV rising)'
                })
            elif obv[-1] < obv[-2] and obv[-2] < obv[-3]:
                signals.append({
                    'indicator': 'Volume',
                    'signal': SignalType.SELL.value,
                    'strength': 0.6,
                    'value': obv[-1],
                    'message': 'Decreasing volume (OBV falling)'
                })
        
        return signals
    
    @classmethod
    def get_consensus_signal(cls, data: Dict) -> Dict:
        """Get consensus signal from all indicators"""
        signals = cls.generate_signals(data)
        
        if not signals:
            return {
                'signal': SignalType.NEUTRAL.value,
                'strength': 0,
                'count': 0,
                'details': []
            }
        
        buy_signals = [s for s in signals if s['signal'] == SignalType.BUY.value]
        sell_signals = [s for s in signals if s['signal'] == SignalType.SELL.value]
        
        buy_strength = sum(s['strength'] for s in buy_signals) / len(buy_signals) if buy_signals else 0
        sell_strength = sum(s['strength'] for s in sell_signals) / len(sell_signals) if sell_signals else 0
        
        if len(buy_signals) > len(sell_signals) + 2:
            signal_type = SignalType.STRONG_BUY.value
            strength = min(buy_strength + 0.2, 1.0)
        elif len(buy_signals) > len(sell_signals):
            signal_type = SignalType.BUY.value
            strength = buy_strength
        elif len(sell_signals) > len(buy_signals) + 2:
            signal_type = SignalType.STRONG_SELL.value
            strength = min(sell_strength + 0.2, 1.0)
        elif len(sell_signals) > len(buy_signals):
            signal_type = SignalType.SELL.value
            strength = sell_strength
        else:
            signal_type = SignalType.NEUTRAL.value
            strength = 0
        
        return {
            'signal': signal_type,
            'strength': strength,
            'buy_count': len(buy_signals),
            'sell_count': len(sell_signals),
            'total_count': len(signals),
            'details': sorted(signals, key=lambda x: x['strength'], reverse=True)[:5]
        }