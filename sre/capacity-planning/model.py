"""
Capacity Planning Model
Predictive modeling for infrastructure scaling
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
import tensorflow as tf
from tensorflow.keras import layers, models

from ..monitoring.prometheus_client import PrometheusClient
from ..config import settings


@dataclass
class CapacityMetrics:
    """Capacity planning metrics"""
    timestamp: datetime
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    network_in: float
    network_out: float
    requests_per_second: float
    active_users: int
    orders_per_second: float
    data_growth_gb_per_day: float


@dataclass
class CapacityForecast:
    """Capacity forecast results"""
    forecast_date: datetime
    predicted_cpu: float
    predicted_memory: float
    predicted_disk: float
    predicted_requests: float
    confidence_lower: float
    confidence_upper: float
    days_until_exhaustion: int
    recommended_actions: List[str]


class CapacityPlanner:
    """AI-powered capacity planning system"""
    
    def __init__(self):
        self.prometheus = PrometheusClient()
        self.models = {}
        self.scalers = {}
        self.historical_data = pd.DataFrame()
        
    def collect_metrics(self, days: int = 90) -> pd.DataFrame:
        """Collect historical metrics from Prometheus"""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        metrics = []
        
        # CPU Usage
        cpu_query = 'sum(rate(container_cpu_usage_seconds_total[5m])) by (pod)'
        cpu_data = self.prometheus.query_range(cpu_query, start_time, end_time, '1h')
        
        # Memory Usage
        mem_query = 'sum(container_memory_usage_bytes) by (pod)'
        mem_data = self.prometheus.query_range(mem_query, start_time, end_time, '1h')
        
        # Request Rate
        req_query = 'sum(rate(http_requests_total[5m]))'
        req_data = self.prometheus.query_range(req_query, start_time, end_time, '1h')
        
        # Active Users
        users_query = 'sum(active_users_total)'
        users_data = self.prometheus.query_range(users_query, start_time, end_time, '1h')
        
        # Orders Rate
        orders_query = 'sum(rate(orders_total[5m]))'
        orders_data = self.prometheus.query_range(orders_query, start_time, end_time, '1h')
        
        # Combine into DataFrame
        df = pd.DataFrame({
            'timestamp': cpu_data['timestamps'],
            'cpu_usage': cpu_data['values'],
            'memory_usage': mem_data['values'],
            'requests_per_second': req_data['values'],
            'active_users': users_data['values'],
            'orders_per_second': orders_data['values']
        })
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        
        # Add derived features
        df['cpu_usage_rolling_avg_7d'] = df['cpu_usage'].rolling(window=168).mean()  # 7 days
        df['cpu_usage_rolling_avg_30d'] = df['cpu_usage'].rolling(window=720).mean()  # 30 days
        df['growth_rate'] = df['cpu_usage'].pct_change()
        
        # Add time features
        df['hour'] = df.index.hour
        df['day_of_week'] = df.index.dayofweek
        df['month'] = df.index.month
        df['quarter'] = df.index.quarter
        df['weekend'] = (df['day_of_week'] >= 5).astype(int)
        
        self.historical_data = df
        return df
    
    def build_prophet_model(self) -> 'Prophet':
        """Build Facebook Prophet model for time series forecasting"""
        from prophet import Prophet
        
        # Prepare data
        df_prophet = self.historical_data[['cpu_usage']].reset_index()
        df_prophet.columns = ['ds', 'y']
        
        # Create model with seasonality
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=True,
            seasonality_mode='multiplicative',
            changepoint_prior_scale=0.05,
            seasonality_prior_scale=10.0
        )
        
        # Add custom seasonalities
        model.add_seasonality(name='monthly', period=30.5, fourier_order=5)
        model.add_seasonality(name='quarterly', period=91.25, fourier_order=5)
        
        # Add regressors
        model.add_regressor('hour')
        model.add_regressor('day_of_week')
        model.add_regressor('weekend')
        
        # Fit model
        model.fit(df_prophet)
        
        self.models['prophet'] = model
        return model
    
    def build_lstm_model(self) -> tf.keras.Model:
        """Build LSTM model for sequence prediction"""
        
        # Prepare sequences
        sequence_length = 168  # 7 days of hourly data
        
        X, y = self._prepare_sequences(sequence_length)
        
        # Build LSTM model
        model = models.Sequential([
            layers.LSTM(128, return_sequences=True, input_shape=(sequence_length, X.shape[2])),
            layers.Dropout(0.2),
            layers.LSTM(64, return_sequences=True),
            layers.Dropout(0.2),
            layers.LSTM(32),
            layers.Dense(64, activation='relu'),
            layers.Dropout(0.2),
            layers.Dense(1)
        ])
        
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
            loss='mse',
            metrics=['mae', 'mape']
        )
        
        # Train model
        history = model.fit(
            X, y,
            epochs=100,
            batch_size=32,
            validation_split=0.2,
            callbacks=[
                tf.keras.callbacks.EarlyStopping(patience=10, restore_best_weights=True),
                tf.keras.callbacks.ReduceLROnPlateau(factor=0.5, patience=5)
            ]
        )
        
        self.models['lstm'] = model
        return model
    
    def _prepare_sequences(self, sequence_length: int) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare sequences for LSTM training"""
        
        # Select features
        feature_columns = [
            'cpu_usage', 'memory_usage', 'requests_per_second',
            'active_users', 'orders_per_second', 'hour',
            'day_of_week', 'weekend'
        ]
        
        data = self.historical_data[feature_columns].values
        
        # Normalize data
        from sklearn.preprocessing import MinMaxScaler
        scaler = MinMaxScaler()
        data_scaled = scaler.fit_transform(data)
        self.scalers['lstm'] = scaler
        
        # Create sequences
        X, y = [], []
        for i in range(sequence_length, len(data_scaled)):
            X.append(data_scaled[i-sequence_length:i])
            y.append(data_scaled[i, 0])  # Predict CPU usage
        
        return np.array(X), np.array(y)
    
    def forecast(self, days: int = 30, method: str = 'ensemble') -> CapacityForecast:
        """Generate capacity forecast"""
        
        if method == 'prophet':
            forecast = self._forecast_prophet(days)
        elif method == 'lstm':
            forecast = self._forecast_lstm(days)
        else:
            # Ensemble forecast
            forecast1 = self._forecast_prophet(days)
            forecast2 = self._forecast_lstm(days)
            
            forecast = CapacityForecast(
                forecast_date=forecast1.forecast_date,
                predicted_cpu=(forecast1.predicted_cpu + forecast2.predicted_cpu) / 2,
                predicted_memory=(forecast1.predicted_memory + forecast2.predicted_memory) / 2,
                predicted_disk=(forecast1.predicted_disk + forecast2.predicted_disk) / 2,
                predicted_requests=(forecast1.predicted_requests + forecast2.predicted_requests) / 2,
                confidence_lower=min(forecast1.confidence_lower, forecast2.confidence_lower),
                confidence_upper=max(forecast1.confidence_upper, forecast2.confidence_upper),
                days_until_exhaustion=int((forecast1.days_until_exhaustion + forecast2.days_until_exhaustion) / 2),
                recommended_actions=self._generate_recommendations(
                    forecast1, forecast2
                )
            )
        
        return forecast
    
    def _forecast_prophet(self, days: int) -> CapacityForecast:
        """Forecast using Prophet"""
        
        model = self.models.get('prophet')
        if not model:
            model = self.build_prophet_model()
        
        # Create future dataframe
        future = model.make_future_dataframe(periods=days * 24, freq='H')
        
        # Add regressors
        future['hour'] = future['ds'].dt.hour
        future['day_of_week'] = future['ds'].dt.dayofweek
        future['weekend'] = (future['day_of_week'] >= 5).astype(int)
        
        # Predict
        forecast = model.predict(future)
        
        # Get latest actual value
        latest_cpu = self.historical_data['cpu_usage'].iloc[-1]
        latest_memory = self.historical_data['memory_usage'].iloc[-1]
        latest_disk = self.historical_data['disk_usage'].iloc[-1] if 'disk_usage' in self.historical_data else 500  # GB
        latest_requests = self.historical_data['requests_per_second'].iloc[-1]
        
        # Get forecasted values
        predicted_cpu = forecast['yhat'].iloc[-1]
        predicted_memory = latest_memory * (predicted_cpu / latest_cpu)  # Approximate
        predicted_requests = latest_requests * (predicted_cpu / latest_cpu)  # Approximate
        
        # Calculate disk usage based on growth rate
        disk_growth_rate = 2  # GB per day
        predicted_disk = latest_disk + (disk_growth_rate * days)
        
        # Confidence intervals
        confidence_lower = forecast['yhat_lower'].iloc[-1]
        confidence_upper = forecast['yhat_upper'].iloc[-1]
        
        # Calculate days until exhaustion (at 80% threshold)
        threshold = 80  # 80% CPU threshold
        growth_rate = (predicted_cpu - latest_cpu) / days
        if growth_rate > 0:
            days_until_exhaustion = int((threshold - latest_cpu) / growth_rate)
        else:
            days_until_exhaustion = 365  # More than a year
        
        return CapacityForecast(
            forecast_date=datetime.now() + timedelta(days=days),
            predicted_cpu=predicted_cpu,
            predicted_memory=predicted_memory,
            predicted_disk=predicted_disk,
            predicted_requests=predicted_requests,
            confidence_lower=confidence_lower,
            confidence_upper=confidence_upper,
            days_until_exhaustion=days_until_exhaustion,
            recommended_actions=[]
        )
    
    def _forecast_lstm(self, days: int) -> CapacityForecast:
        """Forecast using LSTM"""
        
        model = self.models.get('lstm')
        if not model:
            model = self.build_lstm_model()
        
        scaler = self.scalers.get('lstm')
        
        # Get last sequence
        sequence_length = 168
        last_sequence = self.historical_data.iloc[-sequence_length:][[
            'cpu_usage', 'memory_usage', 'requests_per_second',
            'active_users', 'orders_per_second', 'hour',
            'day_of_week', 'weekend'
        ]].values
        
        last_sequence_scaled = scaler.transform(last_sequence)
        
        # Predict iteratively
        predictions = []
        current_sequence = last_sequence_scaled.copy()
        
        for _ in range(days * 24):  # Hourly predictions
            X = current_sequence[-sequence_length:].reshape(1, sequence_length, -1)
            pred = model.predict(X, verbose=0)
            predictions.append(pred[0, 0])
            
            # Update sequence
            new_row = current_sequence[-1].copy()
            new_row[0] = pred[0, 0]
            current_sequence = np.vstack([current_sequence, new_row])
        
        # Convert predictions back to original scale
        predictions = np.array(predictions).reshape(-1, 1)
        dummy_features = np.zeros((len(predictions), 7))
        dummy = np.hstack([predictions, dummy_features])
        predictions_original = scaler.inverse_transform(dummy)[:, 0]
        
        # Get latest values
        latest_cpu = self.historical_data['cpu_usage'].iloc[-1]
        latest_memory = self.historical_data['memory_usage'].iloc[-1]
        latest_disk = 500  # GB
        latest_requests = self.historical_data['requests_per_second'].iloc[-1]
        
        # Calculate growth
        predicted_cpu = predictions_original[-1]
        predicted_memory = latest_memory * (predicted_cpu / latest_cpu)
        predicted_requests = latest_requests * (predicted_cpu / latest_cpu)
        predicted_disk = latest_disk + (2 * days)  # 2GB per day growth
        
        # Confidence (using prediction variance)
        confidence_std = np.std(predictions_original[-24:])  # Last day
        confidence_lower = predicted_cpu - 2 * confidence_std
        confidence_upper = predicted_cpu + 2 * confidence_std
        
        # Days until exhaustion
        growth_rate = (predicted_cpu - latest_cpu) / days
        if growth_rate > 0:
            days_until_exhaustion = int((80 - latest_cpu) / growth_rate)
        else:
            days_until_exhaustion = 365
        
        return CapacityForecast(
            forecast_date=datetime.now() + timedelta(days=days),
            predicted_cpu=predicted_cpu,
            predicted_memory=predicted_memory,
            predicted_disk=predicted_disk,
            predicted_requests=predicted_requests,
            confidence_lower=confidence_lower,
            confidence_upper=confidence_upper,
            days_until_exhaustion=days_until_exhaustion,
            recommended_actions=[]
        )
    
    def _generate_recommendations(self, f1: CapacityForecast, f2: CapacityForecast) -> List[str]:
        """Generate actionable recommendations"""
        
        recommendations = []
        avg_days = (f1.days_until_exhaustion + f2.days_until_exhaustion) / 2
        
        if avg_days < 7:
            recommendations.append("🚨 URGENT: Scale up immediately - capacity exhaustion within a week!")
            recommendations.append("Add 50% more nodes to cluster")
            recommendations.append("Increase pod limits by 2x")
            recommendations.append("Enable aggressive autoscaling")
        
        elif avg_days < 30:
            recommendations.append("⚠️ Scale up within 30 days")
            recommendations.append("Add 25% more capacity")
            recommendations.append("Review resource requests/limits")
            recommendations.append("Optimize application performance")
        
        elif avg_days < 90:
            recommendations.append("📊 Plan capacity increase within 3 months")
            recommendations.append("Order new hardware/instances")
            recommendations.append("Review growth projections")
            recommendations.append("Consider architecture improvements")
        
        else:
            recommendations.append("✅ Current capacity sufficient for 3+ months")
            recommendations.append("Continue monitoring growth trends")
            recommendations.append("Review annually for capacity planning")
        
        return recommendations
    
    def generate_report(self) -> Dict:
        """Generate comprehensive capacity planning report"""
        
        # Collect latest data
        df = self.collect_metrics(days=90)
        
        # Generate forecasts for different horizons
        forecast_30d = self.forecast(days=30)
        forecast_90d = self.forecast(days=90)
        forecast_365d = self.forecast(days=365)
        
        # Calculate trends
        growth_rate_7d = df['growth_rate'].rolling(168).mean().iloc[-1] * 100
        growth_rate_30d = df['growth_rate'].rolling(720).mean().iloc[-1] * 100
        
        # Peak usage
        peak_cpu = df['cpu_usage'].max()
        peak_memory = df['memory_usage'].max()
        peak_requests = df['requests_per_second'].max()
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'data_period_days': 90,
            'current_metrics': {
                'cpu_usage': float(df['cpu_usage'].iloc[-1]),
                'memory_usage': float(df['memory_usage'].iloc[-1]),
                'requests_per_second': float(df['requests_per_second'].iloc[-1]),
                'active_users': int(df['active_users'].iloc[-1]),
                'orders_per_second': float(df['orders_per_second'].iloc[-1])
            },
            'peak_metrics': {
                'cpu_usage': float(peak_cpu),
                'memory_usage': float(peak_memory),
                'requests_per_second': float(peak_requests)
            },
            'trends': {
                'growth_rate_7d': float(growth_rate_7d),
                'growth_rate_30d': float(growth_rate_30d)
            },
            'forecasts': {
                '30_days': {
                    'cpu': float(forecast_30d.predicted_cpu),
                    'memory': float(forecast_30d.predicted_memory),
                    'requests': float(forecast_30d.predicted_requests),
                    'days_until_exhaustion': forecast_30d.days_until_exhaustion,
                    'confidence_range': [
                        float(forecast_30d.confidence_lower),
                        float(forecast_30d.confidence_upper)
                    ]
                },
                '90_days': {
                    'cpu': float(forecast_90d.predicted_cpu),
                    'memory': float(forecast_90d.predicted_memory),
                    'requests': float(forecast_90d.predicted_requests),
                    'days_until_exhaustion': forecast_90d.days_until_exhaustion
                },
                '365_days': {
                    'cpu': float(forecast_365d.predicted_cpu),
                    'memory': float(forecast_365d.predicted_memory),
                    'requests': float(forecast_365d.predicted_requests),
                    'days_until_exhaustion': forecast_365d.days_until_exhaustion
                }
            },
            'recommendations': {
                'immediate': forecast_30d.recommended_actions,
                'short_term': forecast_90d.recommended_actions,
                'long_term': forecast_365d.recommended_actions
            },
            'cost_projections': self._project_costs(forecast_365d)
        }
        
        return report
    
    def _project_costs(self, forecast: CapacityForecast) -> Dict:
        """Project infrastructure costs"""
        
        # Current costs (example values)
        current_costs = {
            'compute': 5000,
            'storage': 1000,
            'network': 800,
            'database': 2000,
            'total': 8800
        }
        
        # Growth factor based on CPU forecast
        growth_factor = forecast.predicted_cpu / 50  # Assuming 50% current CPU
        
        projected_costs = {
            'compute': current_costs['compute'] * growth_factor,
            'storage': current_costs['storage'] * (forecast.predicted_disk / 500),
            'network': current_costs['network'] * (forecast.predicted_requests / 1000),
            'database': current_costs['database'] * growth_factor,
            'total': current_costs['total'] * growth_factor
        }
        
        return {
            'current_monthly': current_costs,
            'projected_monthly': projected_costs,
            'annual_increase': (projected_costs['total'] - current_costs['total']) * 12
        }