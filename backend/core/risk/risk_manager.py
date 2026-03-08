"""
Enterprise Risk Management System
Comprehensive risk controls, position sizing, and portfolio risk analysis
"""

import asyncio
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import math
from collections import deque

from ...utils.logger import get_logger
from ...utils.metrics import track_risk_metric
from ...config import settings
from ..market.exchange_manager import ExchangeManager

logger = get_logger(__name__)


class RiskLevel(Enum):
    """Risk levels"""
    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"
    EXTREME = "EXTREME"


class PositionSide(Enum):
    """Position sides"""
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class OrderType(Enum):
    """Order types for risk calculation"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TRAILING_STOP = "TRAILING_STOP"


@dataclass
class RiskLimits:
    """Risk limits configuration"""
    max_position_size: float = 100000  # Maximum position size in quote currency
    max_leverage: float = 10.0  # Maximum leverage
    max_daily_loss: float = 5000  # Maximum daily loss
    max_drawdown: float = 0.2  # Maximum drawdown (20%)
    max_concentration: float = 0.3  # Maximum concentration in single asset (30%)
    max_correlation: float = 0.7  # Maximum correlation between positions
    max_open_positions: int = 20  # Maximum number of open positions
    min_risk_reward: float = 1.5  # Minimum risk/reward ratio
    max_slippage: float = 0.01  # Maximum slippage (1%)
    max_commission: float = 0.002  # Maximum commission (0.2%)
    var_limit: float = 0.05  # Value at Risk limit (5%)
    cvar_limit: float = 0.1  # Conditional VaR limit (10%)


@dataclass
class Position:
    """Trading position data"""
    symbol: str
    side: PositionSide
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    leverage: float
    margin: float
    liquidation_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    opened_at: datetime
    updated_at: datetime
    metadata: Dict = field(default_factory=dict)


@dataclass
class RiskMetrics:
    """Comprehensive risk metrics"""
    total_exposure: float = 0.0
    total_margin: float = 0.0
    free_margin: float = 0.0
    margin_level: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    daily_pnl: float = 0.0
    daily_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    var_95: float = 0.0  # Value at Risk (95% confidence)
    cvar_95: float = 0.0  # Conditional VaR (95% confidence)
    volatility: float = 0.0
    beta: float = 0.0
    alpha: float = 0.0
    correlation_matrix: Dict = field(default_factory=dict)
    concentration_ratio: float = 0.0
    risk_level: RiskLevel = RiskLevel.MODERATE
    risk_score: float = 50.0


class PositionSizer:
    """Advanced position sizing algorithms"""
    
    def __init__(self):
        self.methods = {
            'fixed': self.fixed_fractional,
            'kelly': self.kelly_criterion,
            'optimal_f': self.optimal_f,
            'risk_parity': self.risk_parity,
            'volatility_scaled': self.volatility_scaled,
            'var_based': self.var_based,
            'sharpe_optimal': self.sharpe_optimal
        }
    
    def fixed_fractional(self, capital: float, risk_percent: float,
                          stop_loss_percent: float) -> float:
        """Fixed fractional position sizing"""
        risk_amount = capital * (risk_percent / 100)
        position_size = risk_amount / (stop_loss_percent / 100)
        return position_size
    
    def kelly_criterion(self, win_rate: float, avg_win: float,
                         avg_loss: float, capital: float) -> float:
        """Kelly Criterion position sizing"""
        if avg_loss == 0:
            return 0
        
        b = avg_win / avg_loss  # Win/loss ratio
        p = win_rate / 100
        q = 1 - p
        
        kelly_fraction = (p * b - q) / b
        kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Cap at 25%
        
        return capital * kelly_fraction
    
    def optimal_f(self, trades: List[Dict], capital: float) -> float:
        """Optimal f position sizing"""
        if not trades:
            return 0
        
        # Calculate optimal f using historical trades
        outcomes = [t['pnl'] / t['risk'] for t in trades if t.get('risk', 0) > 0]
        
        if not outcomes:
            return 0
        
        def calculate_twr(f):
            twr = 1.0
            for outcome in outcomes:
                twr *= (1 + f * outcome)
            return twr
        
        # Find f that maximizes TWR
        best_f = 0
        best_twr = 1
        
        for f in np.arange(0, 0.5, 0.01):
            twr = calculate_twr(f)
            if twr > best_twr:
                best_twr = twr
                best_f = f
        
        return capital * best_f
    
    def risk_parity(self, assets: List[Dict], capital: float,
                     target_volatility: float = 0.2) -> Dict[str, float]:
        """Risk parity position sizing"""
        n = len(assets)
        if n == 0:
            return {}
        
        # Calculate volatilities
        volatilities = np.array([a.get('volatility', 0.2) for a in assets])
        
        # Equal risk contribution
        weights = 1 / volatilities
        weights = weights / weights.sum()
        
        # Scale to target portfolio volatility
        portfolio_vol = np.sqrt(weights @ np.diag(volatilities ** 2) @ weights)
        scale = target_volatility / portfolio_vol
        
        return {a['symbol']: capital * w * scale for a, w in zip(assets, weights)}
    
    def volatility_scaled(self, capital: float, volatility: float,
                           base_position: float, target_vol: float = 0.2) -> float:
        """Volatility-scaled position sizing"""
        if volatility == 0:
            return base_position
        
        scale = target_vol / volatility
        return base_position * min(scale, 3.0)  # Cap at 3x
    
    def var_based(self, capital: float, volatility: float,
                   confidence: float = 0.95, horizon: int = 1) -> float:
        """VaR-based position sizing"""
        # Calculate VaR
        var = volatility * np.sqrt(horizon) * stats.norm.ppf(confidence)
        
        if var == 0:
            return 0
        
        # Position size that limits VaR to 2% of capital
        max_var_amount = capital * 0.02
        position_size = max_var_amount / var
        
        return position_size
    
    def sharpe_optimal(self, expected_return: float, volatility: float,
                        risk_free_rate: float = 0.02, capital: float = 1.0) -> float:
        """Sharpe-optimal position sizing"""
        if volatility == 0:
            return 0
        
        sharpe = (expected_return - risk_free_rate) / volatility
        
        # Kelly-based scaling
        kelly = sharpe / volatility
        
        return capital * min(kelly, 0.25)  # Cap at 25%


class DrawdownTracker:
    """Track and analyze drawdowns"""
    
    def __init__(self):
        self.equity_curve = deque(maxlen=10000)
        self.peak = 0
        self.drawdowns = []
        self.current_drawdown = 0
        self.max_drawdown = 0
        self.recovery_days = []
    
    def update(self, timestamp: datetime, equity: float):
        """Update equity curve and calculate drawdown"""
        self.equity_curve.append((timestamp, equity))
        
        if equity > self.peak:
            self.peak = equity
            self.current_drawdown = 0
        else:
            self.current_drawdown = (self.peak - equity) / self.peak
            if self.current_drawdown > self.max_drawdown:
                self.max_drawdown = self.current_drawdown
    
    def get_drawdown_stats(self) -> Dict:
        """Get drawdown statistics"""
        if not self.equity_curve:
            return {}
        
        # Calculate average drawdown
        drawdowns = [d for _, d in self.drawdowns]
        avg_drawdown = np.mean(drawdowns) if drawdowns else 0
        
        # Calculate average recovery time
        avg_recovery = np.mean(self.recovery_days) if self.recovery_days else 0
        
        # Calculate ulcer index
        returns = np.diff([e for _, e in self.equity_curve]) / [e for _, e in self.equity_curve][:-1]
        ulcer_index = np.sqrt(np.mean(returns ** 2)) * 100 if len(returns) > 0 else 0
        
        return {
            'current_drawdown': self.current_drawdown * 100,
            'max_drawdown': self.max_drawdown * 100,
            'average_drawdown': avg_drawdown,
            'average_recovery_days': avg_recovery,
            'ulcer_index': ulcer_index,
            'drawdown_count': len(self.drawdowns)
        }


class VarCalculator:
    """Value at Risk calculations"""
    
    @staticmethod
    def historical_var(returns: np.ndarray, confidence: float = 0.95) -> float:
        """Historical VaR"""
        if len(returns) == 0:
            return 0
        
        return -np.percentile(returns, (1 - confidence) * 100)
    
    @staticmethod
    def parametric_var(returns: np.ndarray, confidence: float = 0.95) -> float:
        """Parametric VaR (assuming normal distribution)"""
        if len(returns) == 0:
            return 0
        
        mean = np.mean(returns)
        std = np.std(returns)
        
        from scipy import stats
        z_score = stats.norm.ppf(confidence)
        
        return -(mean - z_score * std)
    
    @staticmethod
    def monte_carlo_var(returns: np.ndarray, confidence: float = 0.95,
                        n_simulations: int = 10000) -> float:
        """Monte Carlo VaR"""
        if len(returns) == 0:
            return 0
        
        # Fit distribution
        from scipy import stats
        dist = stats.t.fit(returns)
        
        # Generate simulations
        simulations = dist.rvs(size=n_simulations)
        
        return -np.percentile(simulations, (1 - confidence) * 100)
    
    @staticmethod
    def conditional_var(returns: np.ndarray, confidence: float = 0.95) -> float:
        """Conditional VaR (Expected Shortfall)"""
        if len(returns) == 0:
            return 0
        
        var = VarCalculator.historical_var(returns, confidence)
        tail_returns = returns[returns < -var]
        
        if len(tail_returns) == 0:
            return var
        
        return -np.mean(tail_returns)


class CorrelationAnalyzer:
    """Analyze correlation between assets"""
    
    def __init__(self):
        self.returns_data = {}
        self.correlation_matrix = None
    
    def add_returns(self, symbol: str, returns: np.ndarray):
        """Add returns data for symbol"""
        self.returns_data[symbol] = returns
    
    def calculate_correlations(self) -> pd.DataFrame:
        """Calculate correlation matrix"""
        if len(self.returns_data) < 2:
            return pd.DataFrame()
        
        # Align data
        min_length = min(len(r) for r in self.returns_data.values())
        aligned_data = {}
        
        for symbol, returns in self.returns_data.items():
            aligned_data[symbol] = returns[-min_length:]
        
        df = pd.DataFrame(aligned_data)
        self.correlation_matrix = df.corr()
        
        return self.correlation_matrix
    
    def get_pair_correlation(self, symbol1: str, symbol2: str) -> float:
        """Get correlation between two symbols"""
        if self.correlation_matrix is None:
            self.calculate_correlations()
        
        if symbol1 in self.correlation_matrix.index and symbol2 in self.correlation_matrix.columns:
            return self.correlation_matrix.loc[symbol1, symbol2]
        
        return 0
    
    def get_diversification_score(self, portfolio_symbols: List[str]) -> float:
        """Calculate diversification score (0-1)"""
        if len(portfolio_symbols) < 2:
            return 1.0
        
        if self.correlation_matrix is None:
            self.calculate_correlations()
        
        correlations = []
        for i, s1 in enumerate(portfolio_symbols):
            for s2 in portfolio_symbols[i+1:]:
                if s1 in self.correlation_matrix.index and s2 in self.correlation_matrix.columns:
                    correlations.append(abs(self.correlation_matrix.loc[s1, s2]))
        
        if not correlations:
            return 1.0
        
        avg_correlation = np.mean(correlations)
        return 1 - avg_correlation


class RiskManager:
    """
    Enterprise Risk Management System
    Comprehensive risk controls and analytics
    """
    
    def __init__(self, exchange_manager: ExchangeManager):
        self.exchange_manager = exchange_manager
        self.limits = RiskLimits()
        
        # Positions
        self.positions: Dict[str, Position] = {}
        self.position_history: deque = deque(maxlen=10000)
        
        # Risk metrics
        self.metrics = RiskMetrics()
        self.historical_metrics: deque = deque(maxlen=1000)
        
        # Trackers
        self.drawdown_tracker = DrawdownTracker()
        self.var_calculator = VarCalculator()
        self.correlation_analyzer = CorrelationAnalyzer()
        self.position_sizer = PositionSizer()
        
        # P&L tracking
        self.daily_pnl = 0
        self.daily_trades = 0
        self.trade_history: List[Dict] = []
        
        # Risk limits
        self.risk_limits: Dict[str, float] = {}
        self.breached_limits: List[str] = []
        
        # Background tasks
        self.tasks = []
        self.running = False
        
        # Locks
        self.position_lock = asyncio.Lock()
        
        logger.info("🛡️ Initialized Enterprise Risk Management System")
    
    async def start(self):
        """Start risk manager"""
        self.running = True
        
        self.tasks.extend([
            asyncio.create_task(self._monitor_risk()),
            asyncio.create_task(self._calculate_metrics()),
            asyncio.create_task(self._check_limits())
        ])
        
        logger.info("✅ Risk manager started")
    
    async def stop(self):
        """Stop risk manager"""
        self.running = False
        
        for task in self.tasks:
            task.cancel()
        
        await asyncio.gather(*self.tasks, return_exceptions=True)
        
        logger.info("🛑 Risk manager stopped")
    
    async def check_order(self, order) -> bool:
        """Pre-trade risk check"""
        checks = []
        
        # Position size check
        if order.quantity * (order.price or 0) > self.limits.max_position_size:
            checks.append(("max_position_size", False))
        else:
            checks.append(("max_position_size", True))
        
        # Leverage check
        if order.metadata.get('leverage', 1) > self.limits.max_leverage:
            checks.append(("max_leverage", False))
        else:
            checks.append(("max_leverage", True))
        
        # Daily loss check
        if self.daily_pnl < -self.limits.max_daily_loss:
            checks.append(("max_daily_loss", False))
        else:
            checks.append(("max_daily_loss", True))
        
        # Open positions check
        if len(self.positions) >= self.limits.max_open_positions:
            checks.append(("max_open_positions", False))
        else:
            checks.append(("max_open_positions", True))
        
        # Concentration check
        position_value = order.quantity * (order.price or 0)
        total_exposure = self.metrics.total_exposure + position_value
        concentration = position_value / max(total_exposure, 1)
        
        if concentration > self.limits.max_concentration:
            checks.append(("max_concentration", False))
        else:
            checks.append(("max_concentration", True))
        
        # Correlation check
        if self.positions:
            for pos_symbol in self.positions:
                corr = self.correlation_analyzer.get_pair_correlation(order.symbol, pos_symbol)
                if corr > self.limits.max_correlation:
                    checks.append(("max_correlation", False))
                    break
            else:
                checks.append(("max_correlation", True))
        else:
            checks.append(("max_correlation", True))
        
        # Slippage check
        if order.type in [OrderType.MARKET]:
            estimated_slippage = await self._estimate_slippage(order)
            if estimated_slippage > self.limits.max_slippage:
                checks.append(("max_slippage", False))
            else:
                checks.append(("max_slippage", True))
        
        # Log failed checks
        failed_checks = [check[0] for check in checks if not check[1]]
        if failed_checks:
            logger.warning(f"Order rejected by risk checks: {failed_checks}")
        
        return all(check[1] for check in checks)
    
    async def update_position(self, position: Position):
        """Update position after trade"""
        async with self.position_lock:
            self.positions[position.symbol] = position
            self.position_history.append(position)
            
            # Update P&L
            self.metrics.unrealized_pnl += position.unrealized_pnl
            self.metrics.realized_pnl += position.realized_pnl
            self.daily_pnl += position.realized_pnl
    
    async def close_position(self, symbol: str) -> Optional[Position]:
        """Close position for symbol"""
        async with self.position_lock:
            if symbol in self.positions:
                position = self.positions.pop(symbol)
                position.metadata['closed_at'] = datetime.now()
                self.position_history.append(position)
                
                # Update metrics
                self.metrics.realized_pnl += position.realized_pnl
                self.daily_pnl += position.realized_pnl
                
                return position
        
        return None
    
    async def calculate_position_size(self, symbol: str, capital: float,
                                       method: str = 'fixed', **kwargs) -> float:
        """Calculate optimal position size"""
        if method not in self.position_sizer.methods:
            method = 'fixed'
        
        # Get volatility
        volatility = await self._get_volatility(symbol)
        
        # Get win rate and avg win/loss from history
        win_rate, avg_win, avg_loss = self._get_trading_stats(symbol)
        
        # Calculate position size
        if method == 'fixed':
            risk_percent = kwargs.get('risk_percent', 2)
            stop_loss = kwargs.get('stop_loss', 2)
            return self.position_sizer.fixed_fractional(capital, risk_percent, stop_loss)
        
        elif method == 'kelly':
            return self.position_sizer.kelly_criterion(win_rate, avg_win, avg_loss, capital)
        
        elif method == 'optimal_f':
            return self.position_sizer.optimal_f(self.trade_history, capital)
        
        elif method == 'volatility_scaled':
            base_size = kwargs.get('base_size', capital * 0.01)
            return self.position_sizer.volatility_scaled(capital, volatility, base_size)
        
        elif method == 'var_based':
            return self.position_sizer.var_based(capital, volatility)
        
        else:
            return self.position_sizer.fixed_fractional(capital, 2, 2)
    
    async def calculate_stop_loss(self, symbol: str, entry_price: float,
                                    side: PositionSide, method: str = 'atr') -> float:
        """Calculate optimal stop loss level"""
        if method == 'atr':
            # Get ATR
            klines = await self.exchange_manager.get_klines(symbol, '1h', 20)
            if klines:
                highs = np.array([k['high'] for k in klines])
                lows = np.array([k['low'] for k in klines])
                closes = np.array([k['close'] for k in klines])
                
                from ..analysis.technical.indicators import TechnicalIndicators
                atr = TechnicalIndicators.atr(highs, lows, closes, 14)[-1]
                
                if side == PositionSide.LONG:
                    return entry_price - (atr * 2)
                else:
                    return entry_price + (atr * 2)
        
        elif method == 'support_resistance':
            # Find nearest support/resistance
            klines = await self.exchange_manager.get_klines(symbol, '1h', 100)
            if klines:
                lows = [k['low'] for k in klines]
                highs = [k['high'] for k in klines]
                
                if side == PositionSide.LONG:
                    # Find nearest support below entry
                    supports = [l for l in lows if l < entry_price]
                    if supports:
                        return max(supports)
                else:
                    # Find nearest resistance above entry
                    resistances = [h for h in highs if h > entry_price]
                    if resistances:
                        return min(resistances)
        
        # Default to 2% stop loss
        if side == PositionSide.LONG:
            return entry_price * 0.98
        else:
            return entry_price * 1.02
    
    async def calculate_take_profit(self, symbol: str, entry_price: float,
                                      side: PositionSide, risk_reward: float = 2.0) -> float:
        """Calculate take profit level based on risk/reward"""
        stop_loss = await self.calculate_stop_loss(symbol, entry_price, side)
        
        if side == PositionSide.LONG:
            risk = entry_price - stop_loss
            return entry_price + (risk * risk_reward)
        else:
            risk = stop_loss - entry_price
            return entry_price - (risk * risk_reward)
    
    async def get_risk_metrics(self) -> RiskMetrics:
        """Get current risk metrics"""
        return self.metrics
    
    async def get_portfolio_beta(self, benchmark: str = 'BTCUSDT') -> float:
        """Calculate portfolio beta relative to benchmark"""
        if not self.positions:
            return 0
        
        # Get portfolio returns
        portfolio_returns = []
        benchmark_returns = []
        
        for symbol in self.positions:
            klines = await self.exchange_manager.get_klines(symbol, '1h', 100)
            if klines:
                closes = [k['close'] for k in klines]
                returns = np.diff(closes) / closes[:-1]
                portfolio_returns.extend(returns)
        
        # Get benchmark returns
        klines = await self.exchange_manager.get_klines(benchmark, '1h', 100)
        if klines:
            closes = [k['close'] for k in klines]
            benchmark_returns = np.diff(closes) / closes[:-1]
        
        if len(portfolio_returns) > 0 and len(benchmark_returns) > 0:
            # Align lengths
            min_len = min(len(portfolio_returns), len(benchmark_returns))
            portfolio_returns = portfolio_returns[-min_len:]
            benchmark_returns = benchmark_returns[-min_len:]
            
            # Calculate beta
            covariance = np.cov(portfolio_returns, benchmark_returns)[0, 1]
            variance = np.var(benchmark_returns)
            
            if variance > 0:
                return covariance / variance
        
        return 0
    
    async def get_sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio"""
        if not self.trade_history:
            return 0
        
        returns = [t['return'] for t in self.trade_history if 'return' in t]
        
        if len(returns) < 10:
            return 0
        
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        if std_return == 0:
            return 0
        
        return (mean_return - risk_free_rate / 252) / std_return * np.sqrt(252)
    
    async def get_sortino_ratio(self, risk_free_rate: float = 0.02) -> float:
        """Calculate Sortino ratio (uses downside deviation)"""
        if not self.trade_history:
            return 0
        
        returns = [t['return'] for t in self.trade_history if 'return' in t]
        
        if len(returns) < 10:
            return 0
        
        mean_return = np.mean(returns)
        
        # Downside deviation (only negative returns)
        negative_returns = [r for r in returns if r < 0]
        if not negative_returns:
            return float('inf')
        
        downside_std = np.std(negative_returns)
        
        if downside_std == 0:
            return 0
        
        return (mean_return - risk_free_rate / 252) / downside_std * np.sqrt(252)
    
    async def get_calmar_ratio(self) -> float:
        """Calculate Calmar ratio (return / max drawdown)"""
        if self.drawdown_tracker.max_drawdown == 0:
            return 0
        
        annualized_return = await self._get_annualized_return()
        
        return annualized_return / self.drawdown_tracker.max_drawdown
    
    async def get_var_report(self, confidence: float = 0.95) -> Dict:
        """Generate VaR report"""
        if not self.trade_history:
            return {}
        
        returns = [t['return'] for t in self.trade_history if 'return' in t]
        returns_array = np.array(returns)
        
        return {
            'historical_var': VarCalculator.historical_var(returns_array, confidence),
            'parametric_var': VarCalculator.parametric_var(returns_array, confidence),
            'monte_carlo_var': VarCalculator.monte_carlo_var(returns_array, confidence),
            'conditional_var': VarCalculator.conditional_var(returns_array, confidence),
            'confidence_level': confidence
        }
    
    async def get_stress_test(self, scenarios: List[str] = None) -> Dict:
        """Run stress tests"""
        if scenarios is None:
            scenarios = ['market_crash', 'liquidity_crisis', 'volatility_spike']
        
        results = {}
        
        for scenario in scenarios:
            if scenario == 'market_crash':
                # Simulate 20% market drop
                impact = await self._simulate_market_move(-0.2)
                results['market_crash'] = {
                    'pnl_impact': impact,
                    'margin_call_risk': impact < -self.metrics.free_margin * 0.5
                }
            
            elif scenario == 'liquidity_crisis':
                # Simulate 50% volume drop with 2x slippage
                impact = await self._simulate_liquidity_shock(0.5, 2.0)
                results['liquidity_crisis'] = {
                    'slippage_impact': impact,
                    'unwind_ability': impact < 0.1
                }
            
            elif scenario == 'volatility_spike':
                # Simulate 3x volatility
                impact = await self._simulate_volatility_shock(3.0)
                results['volatility_spike'] = {
                    'var_increase': impact,
                    'stop_loss_risk': impact > 0.5
                }
        
        return results
    
    async def _monitor_risk(self):
        """Background task to monitor risk levels"""
        while self.running:
            try:
                # Update position P&L
                for symbol, position in self.positions.items():
                    current_price = await self._get_current_price(symbol)
                    if current_price:
                        if position.side == PositionSide.LONG:
                            position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
                        else:
                            position.unrealized_pnl = (position.entry_price - current_price) * position.quantity
                        
                        position.current_price = current_price
                        position.updated_at = datetime.now()
                
                # Update total exposure
                self.metrics.total_exposure = sum(
                    p.quantity * p.current_price for p in self.positions.values()
                )
                
                # Update margin level
                if self.metrics.total_margin > 0:
                    self.metrics.margin_level = (self.metrics.total_exposure / self.metrics.total_margin) * 100
                
                # Check liquidation levels
                await self._check_liquidations()
                
                await asyncio.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"Error in risk monitor: {e}")
                await asyncio.sleep(1)
    
    async def _calculate_metrics(self):
        """Background task to calculate risk metrics"""
        while self.running:
            try:
                # Calculate P&L metrics
                if self.trade_history:
                    wins = [t for t in self.trade_history if t.get('pnl', 0) > 0]
                    losses = [t for t in self.trade_history if t.get('pnl', 0) < 0]
                    
                    self.metrics.win_rate = len(wins) / len(self.trade_history) * 100 if self.trade_history else 0
                    
                    if wins and losses:
                        avg_win = np.mean([t['pnl'] for t in wins])
                        avg_loss = abs(np.mean([t['pnl'] for t in losses]))
                        self.metrics.profit_factor = avg_win / avg_loss if avg_loss > 0 else float('inf')
                
                # Calculate risk ratios
                self.metrics.sharpe_ratio = await self.get_sharpe_ratio()
                self.metrics.sortino_ratio = await self.get_sortino_ratio()
                self.metrics.calmar_ratio = await self.get_calmar_ratio()
                
                # Calculate VaR
                if self.trade_history:
                    returns = [t['return'] for t in self.trade_history if 'return' in t]
                    if returns:
                        self.metrics.var_95 = VarCalculator.historical_var(np.array(returns), 0.95)
                        self.metrics.cvar_95 = VarCalculator.conditional_var(np.array(returns), 0.95)
                
                # Calculate concentration
                if self.metrics.total_exposure > 0:
                    exposures = [p.quantity * p.current_price for p in self.positions.values()]
                    herfindahl = sum((e / self.metrics.total_exposure) ** 2 for e in exposures)
                    self.metrics.concentration_ratio = herfindahl
                
                # Determine risk level
                self.metrics.risk_score = self._calculate_risk_score()
                self.metrics.risk_level = self._get_risk_level(self.metrics.risk_score)
                
                # Store historical metrics
                self.historical_metrics.append(self.metrics.__dict__.copy())
                
                await asyncio.sleep(60)  # Calculate every minute
                
            except Exception as e:
                logger.error(f"Error calculating metrics: {e}")
                await asyncio.sleep(60)
    
    async def _check_limits(self):
        """Background task to check risk limits"""
        while self.running:
            try:
                self.breached_limits = []
                
                # Check drawdown limit
                if self.drawdown_tracker.max_drawdown > self.limits.max_drawdown:
                    self.breached_limits.append('max_drawdown')
                
                # Check concentration limit
                if self.metrics.concentration_ratio > self.limits.max_concentration:
                    self.breached_limits.append('max_concentration')
                
                # Check VaR limit
                if self.metrics.var_95 > self.limits.var_limit * self.metrics.total_exposure:
                    self.breached_limits.append('var_limit')
                
                # Check CVaR limit
                if self.metrics.cvar_95 > self.limits.cvar_limit * self.metrics.total_exposure:
                    self.breached_limits.append('cvar_limit')
                
                if self.breached_limits:
                    logger.warning(f"Risk limits breached: {self.breached_limits}")
                    
                    # Take action based on breach severity
                    if 'max_drawdown' in self.breached_limits:
                        await self._reduce_positions(0.5)  # Reduce by 50%
                    
                    if 'var_limit' in self.breached_limits:
                        await self._hedge_positions()
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"Error checking limits: {e}")
                await asyncio.sleep(10)
    
    async def _check_liquidations(self):
        """Check for positions near liquidation"""
        for symbol, position in self.positions.items():
            if position.liquidation_price:
                current_price = await self._get_current_price(symbol)
                if current_price:
                    if position.side == PositionSide.LONG:
                        distance = (current_price - position.liquidation_price) / current_price
                    else:
                        distance = (position.liquidation_price - current_price) / current_price
                    
                    if distance < 0.05:  # Within 5% of liquidation
                        logger.warning(f"Position {symbol} within 5% of liquidation!")
                        
                        # Add margin or reduce position
                        if distance < 0.02:  # Within 2%
                            await self._reduce_positions(0.3, symbol)  # Reduce by 30%
    
    async def _reduce_positions(self, reduce_by: float, symbol: Optional[str] = None):
        """Reduce positions by percentage"""
        # This would integrate with execution engine to close positions
        logger.info(f"Reducing positions by {reduce_by*100}%")
    
    async def _hedge_positions(self):
        """Hedge positions using correlated assets"""
        # This would integrate with execution engine to place hedge orders
        logger.info("Hedging positions")
    
    async def _estimate_slippage(self, order) -> float:
        """Estimate slippage for order"""
        try:
            orderbook = await self.exchange_manager.get_orderbook(order.symbol, limit=10, exchange=order.exchange)
            
            if not orderbook:
                return 0.001  # Default 0.1%
            
            if order.side == 'BUY':
                levels = orderbook['asks']
                total_qty = 0
                weighted_price = 0
                
                for price, qty in levels:
                    take = min(order.quantity - total_qty, qty)
                    weighted_price += price * take
                    total_qty += take
                    if total_qty >= order.quantity:
                        break
                
                if total_qty > 0:
                    avg_price = weighted_price / total_qty
                    best_price = levels[0][0]
                    return abs(avg_price - best_price) / best_price
            
            else:  # SELL
                levels = orderbook['bids']
                total_qty = 0
                weighted_price = 0
                
                for price, qty in levels:
                    take = min(order.quantity - total_qty, qty)
                    weighted_price += price * take
                    total_qty += take
                    if total_qty >= order.quantity:
                        break
                
                if total_qty > 0:
                    avg_price = weighted_price / total_qty
                    best_price = levels[0][0]
                    return abs(best_price - avg_price) / best_price
            
        except Exception as e:
            logger.error(f"Error estimating slippage: {e}")
        
        return 0.001  # Default 0.1%
    
    async def _get_volatility(self, symbol: str) -> float:
        """Get volatility for symbol"""
        try:
            klines = await self.exchange_manager.get_klines(symbol, '1h', 30)
            if klines:
                closes = [k['close'] for k in klines]
                returns = np.diff(closes) / closes[:-1]
                return np.std(returns) * np.sqrt(365 * 24)  # Annualized
        except Exception as e:
            logger.error(f"Error getting volatility: {e}")
        
        return 0.2  # Default 20%
    
    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for symbol"""
        try:
            ticker = await self.exchange_manager.get_ticker(symbol)
            return ticker['last_price'] if ticker else None
        except Exception:
            return None
    
    def _get_trading_stats(self, symbol: Optional[str] = None) -> Tuple[float, float, float]:
        """Get win rate, average win, average loss from trade history"""
        if symbol:
            trades = [t for t in self.trade_history if t.get('symbol') == symbol]
        else:
            trades = self.trade_history
        
        if not trades:
            return 50, 100, 100  # Default values
        
        wins = [t['pnl'] for t in trades if t.get('pnl', 0) > 0]
        losses = [t['pnl'] for t in trades if t.get('pnl', 0) < 0]
        
        win_rate = len(wins) / len(trades) * 100
        avg_win = np.mean(wins) if wins else 100
        avg_loss = abs(np.mean(losses)) if losses else 100
        
        return win_rate, avg_win, avg_loss
    
    def _calculate_risk_score(self) -> float:
        """Calculate overall risk score (0-100)"""
        scores = []
        
        # Leverage score (0-100)
        if self.metrics.total_margin > 0:
            leverage = self.metrics.total_exposure / self.metrics.total_margin
            leverage_score = min(leverage / self.limits.max_leverage * 100, 100)
            scores.append(leverage_score)
        
        # Concentration score
        concentration_score = self.metrics.concentration_ratio / self.limits.max_concentration * 100
        scores.append(min(concentration_score, 100))
        
        # Drawdown score
        if self.limits.max_drawdown > 0:
            drawdown_score = (self.drawdown_tracker.max_drawdown / self.limits.max_drawdown) * 100
            scores.append(min(drawdown_score, 100))
        
        # VaR score
        if self.limits.var_limit > 0 and self.metrics.total_exposure > 0:
            var_score = (self.metrics.var_95 / (self.limits.var_limit * self.metrics.total_exposure)) * 100
            scores.append(min(var_score, 100))
        
        # Volatility score
        volatility_score = self.metrics.volatility * 1000  # Scale to 0-100
        scores.append(min(volatility_score, 100))
        
        return np.mean(scores) if scores else 50
    
    def _get_risk_level(self, score: float) -> RiskLevel:
        """Convert score to risk level"""
        if score < 20:
            return RiskLevel.VERY_LOW
        elif score < 40:
            return RiskLevel.LOW
        elif score < 60:
            return RiskLevel.MODERATE
        elif score < 80:
            return RiskLevel.HIGH
        elif score < 95:
            return RiskLevel.VERY_HIGH
        else:
            return RiskLevel.EXTREME
    
    async def _get_annualized_return(self) -> float:
        """Calculate annualized return"""
        if not self.trade_history:
            return 0
        
        # Calculate total return
        total_pnl = sum(t.get('pnl', 0) for t in self.trade_history)
        
        # Get time period
        if len(self.trade_history) > 1:
            start_time = self.trade_history[0].get('timestamp')
            end_time = self.trade_history[-1].get('timestamp')
            
            if start_time and end_time:
                days = (end_time - start_time).days
                if days > 0:
                    return (total_pnl / self.metrics.total_exposure) * (365 / days)
        
        return total_pnl / self.metrics.total_exposure * 100 if self.metrics.total_exposure > 0 else 0
    
    async def _simulate_market_move(self, move_percent: float) -> float:
        """Simulate market move impact on portfolio"""
        total_impact = 0
        
        for symbol, position in self.positions.items():
            if position.side == PositionSide.LONG:
                impact = position.quantity * position.current_price * move_percent
            else:
                impact = -position.quantity * position.current_price * move_percent
            
            total_impact += impact
        
        return total_impact
    
    async def _simulate_liquidity_shock(self, volume_drop: float, slippage_mult: float) -> float:
        """Simulate liquidity crisis impact"""
        # Simplified model: increased slippage on all positions
        total_impact = 0
        
        for symbol, position in self.positions.items():
            # Estimate normal slippage
            normal_slippage = 0.001
            shocked_slippage = normal_slippage * slippage_mult
            
            # Impact from wider spreads
            impact = position.quantity * position.current_price * shocked_slippage
            total_impact += impact
        
        return total_impact
    
    async def _simulate_volatility_shock(self, vol_mult: float) -> float:
        """Simulate volatility spike impact on VaR"""
        if not self.trade_history:
            return 0
        
        returns = [t['return'] for t in self.trade_history if 'return' in t]
        if returns:
            current_var = VarCalculator.historical_var(np.array(returns), 0.95)
            shocked_var = current_var * vol_mult
            
            return shocked_var / current_var - 1 if current_var > 0 else 0
        
        return 0