"""
LSTM Model for Cryptocurrency Price Prediction
Enterprise-grade deep learning model with attention mechanism
"""

import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow.keras.models import Model, load_model
from tensorflow.keras.layers import (
    LSTM, Dense, Dropout, Input, Bidirectional,
    Attention, Concatenate, BatchNormalization,
    LayerNormalization, Add, GlobalAveragePooling1D,
    MultiHeadAttention, Layer
)
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import (
    EarlyStopping, ModelCheckpoint, ReduceLROnPlateau,
    TensorBoard, Callback
)
from tensorflow.keras.regularizers import l1_l2
from sklearn.preprocessing import MinMaxScaler, RobustScaler
from sklearn.model_selection import TimeSeriesSplit
import joblib
from typing import Tuple, Dict, List, Optional, Union
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

from ....utils.logger import get_logger
from ....utils.metrics import track_model_performance
from ....config import settings

logger = get_logger(__name__)


class AttentionLayer(Layer):
    """Custom Attention Layer for LSTM"""
    
    def __init__(self, **kwargs):
        super(AttentionLayer, self).__init__(**kwargs)
    
    def build(self, input_shape):
        self.W = self.add_weight(
            name='attention_weight',
            shape=(input_shape[-1], 1),
            initializer='random_normal',
            trainable=True
        )
        self.b = self.add_weight(
            name='attention_bias',
            shape=(input_shape[1], 1),
            initializer='zeros',
            trainable=True
        )
        super(AttentionLayer, self).build(input_shape)
    
    def call(self, x):
        e = tf.keras.backend.tanh(tf.keras.backend.dot(x, self.W) + self.b)
        a = tf.keras.backend.softmax(e, axis=1)
        output = x * a
        return tf.keras.backend.sum(output, axis=1)


class PositionalEncoding(Layer):
    """Positional Encoding for Transformer layers"""
    
    def __init__(self, max_len=5000, d_model=128):
        super(PositionalEncoding, self).__init__()
        self.max_len = max_len
        self.d_model = d_model
    
    def build(self, input_shape):
        position = np.arange(self.max_len)[:, np.newaxis]
        div_term = np.exp(np.arange(0, self.d_model, 2) * -(np.log(10000.0) / self.d_model))
        
        pe = np.zeros((self.max_len, self.d_model))
        pe[:, 0::2] = np.sin(position * div_term)
        pe[:, 1::2] = np.cos(position * div_term)
        
        self.pe = tf.constant(pe, dtype=tf.float32)
        super(PositionalEncoding, self).build(input_shape)
    
    def call(self, x):
        return x + self.pe[:tf.shape(x)[1], :]


class Time2Vec(Layer):
    """Time2Vec embedding for temporal features"""
    
    def __init__(self, kernel_size=1):
        super(Time2Vec, self).__init__()
        self.k = kernel_size
    
    def build(self, input_shape):
        self.wb = self.add_weight(
            name='wb',
            shape=(input_shape[-1], 1),
            initializer='uniform',
            trainable=True
        )
        self.bb = self.add_weight(
            name='bb',
            shape=(1,),
            initializer='uniform',
            trainable=True
        )
        self.wa = self.add_weight(
            name='wa',
            shape=(1, input_shape[-1], self.k),
            initializer='uniform',
            trainable=True
        )
        self.ba = self.add_weight(
            name='ba',
            shape=(1, input_shape[-1], self.k),
            initializer='uniform',
            trainable=True
        )
        super(Time2Vec, self).build(input_shape)
    
    def call(self, x):
        bias = self.wb * x + self.bb
        dp = tf.reshape(x, (-1, tf.shape(x)[1], 1))
        wg = tf.reshape(self.wa[0], (1, 1, -1))
        bg = tf.reshape(self.ba[0], (1, 1, -1))
        period = tf.sin(tf.matmul(dp, wg) + bg)
        return tf.concat([bias, tf.reshape(period, tf.shape(x))], -1)


class LSTMPredictor:
    """
    Advanced LSTM Model with Attention and Transformer layers
    For cryptocurrency price prediction
    """
    
    def __init__(self, model_name: str = "lstm_attention", version: str = "1.0.0"):
        self.model_name = model_name
        self.version = version
        self.model = None
        self.scaler_X = RobustScaler()
        self.scaler_y = RobustScaler()
        self.feature_columns = None
        self.sequence_length = 60  # 60 time steps
        self.n_features = 0
        self.n_epochs = 200
        self.batch_size = 32
        self.learning_rate = 0.001
        self.dropout_rate = 0.2
        self.l1_reg = 1e-5
        self.l2_reg = 1e-4
        
        # Model paths
        self.model_dir = settings.MODELS_DIR / self.model_name
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = self.model_dir / f"{self.model_name}_v{self.version}.h5"
        self.scaler_X_path = self.model_dir / f"scaler_X_v{self.version}.pkl"
        self.scaler_y_path = self.model_dir / f"scaler_y_v{self.version}.pkl"
        self.metadata_path = self.model_dir / f"metadata_v{self.version}.json"
        
        logger.info(f"🤖 Initialized {self.model_name} v{self.version}")
    
    def create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create technical features for the model"""
        df = df.copy()
        
        # Price-based features
        df['returns_1'] = df['close'].pct_change(1)
        df['returns_5'] = df['close'].pct_change(5)
        df['returns_10'] = df['close'].pct_change(10)
        df['returns_20'] = df['close'].pct_change(20)
        df['returns_50'] = df['close'].pct_change(50)
        
        df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
        df['volatility_5'] = df['log_returns'].rolling(5).std()
        df['volatility_10'] = df['log_returns'].rolling(10).std()
        df['volatility_20'] = df['log_returns'].rolling(20).std()
        
        # Moving averages
        df['sma_5'] = df['close'].rolling(5).mean()
        df['sma_10'] = df['close'].rolling(10).mean()
        df['sma_20'] = df['close'].rolling(20).mean()
        df['sma_50'] = df['close'].rolling(50).mean()
        df['sma_200'] = df['close'].rolling(200).mean()
        
        df['ema_12'] = df['close'].ewm(span=12).mean()
        df['ema_26'] = df['close'].ewm(span=26).mean()
        df['ema_50'] = df['close'].ewm(span=50).mean()
        
        # Price relative to MAs
        df['close_sma_5'] = df['close'] / df['sma_5']
        df['close_sma_10'] = df['close'] / df['sma_10']
        df['close_sma_20'] = df['close'] / df['sma_20']
        df['close_sma_50'] = df['close'] / df['sma_50']
        
        # MACD
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi_14'] = 100 - (100 / (1 + rs))
        
        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(20).mean()
        df['bb_std'] = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + 2 * df['bb_std']
        df['bb_lower'] = df['bb_middle'] - 2 * df['bb_std']
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr_14'] = true_range.rolling(14).mean()
        
        # Volume features
        df['volume_ma_5'] = df['volume'].rolling(5).mean()
        df['volume_ma_10'] = df['volume'].rolling(10).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma_10']
        df['volume_change'] = df['volume'].pct_change()
        
        # OBV
        df['obv'] = (np.sign(df['returns_1']) * df['volume']).cumsum()
        df['obv_ma_10'] = df['obv'].rolling(10).mean()
        
        # Price patterns
        df['high_low_ratio'] = df['high'] / df['low']
        df['close_open_ratio'] = df['close'] / df['open']
        df['high_prev_close'] = df['high'] / df['close'].shift(1)
        df['low_prev_close'] = df['low'] / df['close'].shift(1)
        
        # Time features
        if 'timestamp' in df.columns:
            df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
            df['day_of_week'] = pd.to_datetime(df['timestamp']).dt.dayofweek
            df['day_of_month'] = pd.to_datetime(df['timestamp']).dt.day
            df['month'] = pd.to_datetime(df['timestamp']).dt.month
            df['quarter'] = pd.to_datetime(df['timestamp']).dt.quarter
            df['year'] = pd.to_datetime(df['timestamp']).dt.year
            
            # Cyclical encoding
            df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
            df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
            df['dow_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
            df['dow_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
            df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
            df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
        
        # Drop NaN values
        df = df.dropna()
        
        return df
    
    def prepare_sequences(self, X: np.ndarray, y: np.ndarray, 
                          sequence_length: int = 60) -> Tuple[np.ndarray, np.ndarray]:
        """Create sequences for LSTM training"""
        X_seq, y_seq = [], []
        
        for i in range(sequence_length, len(X)):
            X_seq.append(X[i-sequence_length:i])
            y_seq.append(y[i])
        
        return np.array(X_seq), np.array(y_seq)
    
    def build_model(self, input_shape: Tuple, n_features: int) -> tf.keras.Model:
        """Build LSTM model with attention mechanism"""
        
        # Input layer
        inputs = Input(shape=input_shape, name='input')
        
        # Time2Vec embedding
        time_embedding = Time2Vec()(inputs)
        
        # First BiLSTM layer
        x = Bidirectional(
            LSTM(128, return_sequences=True, 
                 kernel_regularizer=l1_l2(l1=self.l1_reg, l2=self.l2_reg))
        )(time_embedding)
        x = LayerNormalization()(x)
        x = Dropout(self.dropout_rate)(x)
        
        # Second BiLSTM layer with attention
        x = Bidirectional(
            LSTM(64, return_sequences=True,
                 kernel_regularizer=l1_l2(l1=self.l1_reg, l2=self.l2_reg))
        )(x)
        x = LayerNormalization()(x)
        
        # Self-attention mechanism
        attention = MultiHeadAttention(num_heads=8, key_dim=64)(x, x)
        x = Add()([x, attention])
        x = LayerNormalization()(x)
        
        # Third LSTM layer
        x = LSTM(32, return_sequences=False,
                 kernel_regularizer=l1_l2(l1=self.l1_reg, l2=self.l2_reg))(x)
        x = BatchNormalization()(x)
        x = Dropout(self.dropout_rate)(x)
        
        # Dense layers
        x = Dense(64, activation='relu',
                  kernel_regularizer=l1_l2(l1=self.l1_reg, l2=self.l2_reg))(x)
        x = BatchNormalization()(x)
        x = Dropout(self.dropout_rate)(x)
        
        x = Dense(32, activation='relu',
                  kernel_regularizer=l1_l2(l1=self.l1_reg, l2=self.l2_reg))(x)
        x = BatchNormalization()(x)
        x = Dropout(self.dropout_rate / 2)(x)
        
        # Output layer
        outputs = Dense(1, activation='linear', name='output')(x)
        
        # Create model
        model = Model(inputs=inputs, outputs=outputs)
        
        # Compile model
        optimizer = Adam(learning_rate=self.learning_rate, clipnorm=1.0)
        model.compile(
            optimizer=optimizer,
            loss='mse',
            metrics=['mae', 'mape']
        )
        
        logger.info(f"✅ Model built with {model.count_params():,} parameters")
        return model
    
    def train(self, df: pd.DataFrame, target_col: str = 'close',
              validation_split: float = 0.2, test_split: float = 0.1,
              save_best: bool = True) -> Dict:
        """Train the LSTM model"""
        
        # Create features
        logger.info("🔧 Creating features...")
        df_features = self.create_features(df)
        
        # Define feature columns
        exclude_cols = ['timestamp', 'open', 'high', 'low', 'volume', target_col]
        self.feature_columns = [col for col in df_features.columns if col not in exclude_cols]
        self.n_features = len(self.feature_columns)
        
        # Prepare data
        X = df_features[self.feature_columns].values
        y = df_features[target_col].values.reshape(-1, 1)
        
        # Scale data
        logger.info("📊 Scaling data...")
        X_scaled = self.scaler_X.fit_transform(X)
        y_scaled = self.scaler_y.fit_transform(y)
        
        # Create sequences
        logger.info(f"🔄 Creating sequences (length={self.sequence_length})...")
        X_seq, y_seq = self.prepare_sequences(X_scaled, y_scaled, self.sequence_length)
        
        # Split data
        n_train = int(len(X_seq) * (1 - validation_split - test_split))
        n_val = int(len(X_seq) * (1 - test_split))
        
        X_train, y_train = X_seq[:n_train], y_seq[:n_train]
        X_val, y_val = X_seq[n_train:n_val], y_seq[n_train:n_val]
        X_test, y_test = X_seq[n_val:], y_seq[n_val:]
        
        logger.info(f"✅ Training samples: {len(X_train)}")
        logger.info(f"✅ Validation samples: {len(X_val)}")
        logger.info(f"✅ Test samples: {len(X_test)}")
        
        # Build model
        logger.info("🏗️ Building model...")
        self.model = self.build_model((self.sequence_length, self.n_features), self.n_features)
        self.model.summary(print_fn=lambda x: logger.info(x))
        
        # Callbacks
        callbacks = [
            EarlyStopping(
                monitor='val_loss',
                patience=20,
                restore_best_weights=True,
                verbose=1
            ),
            ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=10,
                min_lr=1e-7,
                verbose=1
            ),
            TensorBoard(
                log_dir=str(self.model_dir / 'logs'),
                histogram_freq=1,
                write_graph=True
            )
        ]
        
        if save_best:
            callbacks.append(
                ModelCheckpoint(
                    filepath=str(self.model_path),
                    monitor='val_loss',
                    save_best_only=True,
                    verbose=1
                )
            )
        
        # Train model
        logger.info("🎯 Training model...")
        history = self.model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=self.n_epochs,
            batch_size=self.batch_size,
            callbacks=callbacks,
            verbose=1,
            shuffle=False
        )
        
        # Evaluate on test set
        logger.info("📊 Evaluating on test set...")
        test_loss, test_mae, test_mape = self.model.evaluate(X_test, y_test, verbose=0)
        
        # Make predictions on test set
        y_pred_scaled = self.model.predict(X_test, verbose=0)
        y_pred = self.scaler_y.inverse_transform(y_pred_scaled)
        y_test_actual = self.scaler_y.inverse_transform(y_test)
        
        # Calculate metrics
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        
        mae = mean_absolute_error(y_test_actual, y_pred)
        mse = mean_squared_error(y_test_actual, y_pred)
        rmse = np.sqrt(mse)
        r2 = r2_score(y_test_actual, y_pred)
        
        # Direction accuracy
        direction_actual = np.sign(np.diff(y_test_actual.flatten()))
        direction_pred = np.sign(np.diff(y_pred.flatten()))
        direction_accuracy = np.mean(direction_actual == direction_pred) * 100
        
        results = {
            'test_loss': test_loss,
            'test_mae': test_mae,
            'test_mape': test_mape,
            'mae': mae,
            'mse': mse,
            'rmse': rmse,
            'r2': r2,
            'direction_accuracy': direction_accuracy,
            'train_samples': len(X_train),
            'val_samples': len(X_val),
            'test_samples': len(X_test),
            'n_features': self.n_features,
            'sequence_length': self.sequence_length,
            'epochs_completed': len(history.history['loss'])
        }
        
        logger.info(f"✅ Training completed:")
        logger.info(f"   MAE: ${mae:.2f}")
        logger.info(f"   RMSE: ${rmse:.2f}")
        logger.info(f"   R²: {r2:.4f}")
        logger.info(f"   Direction Accuracy: {direction_accuracy:.1f}%")
        
        # Save model and preprocessors
        self.save()
        
        return results
    
    def predict(self, df: pd.DataFrame, n_steps: int = 1) -> np.ndarray:
        """Make predictions for next n steps"""
        if self.model is None:
            self.load()
        
        # Create features
        df_features = self.create_features(df)
        
        # Get last sequence
        X = df_features[self.feature_columns].values[-self.sequence_length:]
        X_scaled = self.scaler_X.transform(X)
        
        # Reshape for LSTM
        X_seq = X_scaled.reshape(1, self.sequence_length, self.n_features)
        
        # Make prediction
        y_pred_scaled = self.model.predict(X_seq, verbose=0)
        y_pred = self.scaler_y.inverse_transform(y_pred_scaled)
        
        # Multi-step prediction
        if n_steps > 1:
            predictions = []
            current_seq = X_seq.copy()
            
            for _ in range(n_steps):
                pred = self.model.predict(current_seq, verbose=0)
                predictions.append(pred[0, 0])
                
                # Update sequence with new prediction
                new_features = current_seq[0, 1:, :]
                # This is simplified - in practice need to create all features
                current_seq = np.roll(current_seq, -1, axis=1)
                current_seq[0, -1, 0] = pred[0, 0]  # Update close price
            
            y_pred = np.array(predictions).reshape(-1, 1)
            y_pred = self.scaler_y.inverse_transform(y_pred)
        
        return y_pred
    
    def predict_with_confidence(self, df: pd.DataFrame, n_iterations: int = 100) -> Dict:
        """Make predictions with confidence intervals using Monte Carlo dropout"""
        if self.model is None:
            self.load()
        
        # Enable Monte Carlo dropout
        from tensorflow.keras import backend as K
        training_mode = K.learning_phase()
        K.set_learning_phase(1)  # Enable dropout during inference
        
        # Create features
        df_features = self.create_features(df)
        
        # Get last sequence
        X = df_features[self.feature_columns].values[-self.sequence_length:]
        X_scaled = self.scaler_X.transform(X)
        X_seq = X_scaled.reshape(1, self.sequence_length, self.n_features)
        
        # Run multiple predictions
        predictions = []
        for _ in range(n_iterations):
            pred = self.model.predict(X_seq, verbose=0)
            predictions.append(pred[0, 0])
        
        # Disable Monte Carlo dropout
        K.set_learning_phase(training_mode)
        
        predictions = np.array(predictions)
        pred_mean = np.mean(predictions)
        pred_std = np.std(predictions)
        
        # Calculate confidence intervals
        pred_5 = np.percentile(predictions, 5)
        pred_25 = np.percentile(predictions, 25)
        pred_75 = np.percentile(predictions, 75)
        pred_95 = np.percentile(predictions, 95)
        
        # Inverse transform
        pred_mean = self.scaler_y.inverse_transform([[pred_mean]])[0, 0]
        pred_std = pred_std * self.scaler_y.scale_[0]
        
        confidence_intervals = {
            'mean': pred_mean,
            'std': pred_std,
            'ci_50': [
                self.scaler_y.inverse_transform([[pred_25]])[0, 0],
                self.scaler_y.inverse_transform([[pred_75]])[0, 0]
            ],
            'ci_90': [
                self.scaler_y.inverse_transform([[pred_5]])[0, 0],
                self.scaler_y.inverse_transform([[pred_95]])[0, 0]
            ]
        }
        
        return confidence_intervals
    
    def predict_multi_timeframe(self, df_dict: Dict[str, pd.DataFrame]) -> Dict:
        """Make predictions on multiple timeframes and combine"""
        predictions = {}
        
        for tf, df in df_dict.items():
            pred = self.predict(df)
            predictions[tf] = pred[0, 0]
        
        # Calculate weighted average based on timeframe confidence
        weights = {
            '1m': 0.1,
            '5m': 0.15,
            '15m': 0.2,
            '30m': 0.25,
            '1h': 0.3,
            '4h': 0.4,
            '1d': 0.5
        }
        
        weighted_sum = 0
        total_weight = 0
        
        for tf, pred in predictions.items():
            weight = weights.get(tf, 0.1)
            weighted_sum += pred * weight
            total_weight += weight
        
        combined_pred = weighted_sum / total_weight if total_weight > 0 else 0
        
        return {
            'timeframe_predictions': predictions,
            'combined_prediction': combined_pred,
            'weights': {tf: weights.get(tf, 0.1) for tf in predictions.keys()}
        }
    
    def save(self):
        """Save model and preprocessors"""
        if self.model is not None:
            self.model.save(self.model_path)
            logger.info(f"💾 Model saved to {self.model_path}")
        
        joblib.dump(self.scaler_X, self.scaler_X_path)
        joblib.dump(self.scaler_y, self.scaler_y_path)
        logger.info(f"💾 Scalers saved")
        
        # Save metadata
        import json
        metadata = {
            'model_name': self.model_name,
            'version': self.version,
            'sequence_length': self.sequence_length,
            'n_features': self.n_features,
            'feature_columns': self.feature_columns,
            'n_epochs': self.n_epochs,
            'batch_size': self.batch_size,
            'learning_rate': self.learning_rate,
            'dropout_rate': self.dropout_rate,
            'created_at': datetime.now().isoformat()
        }
        
        with open(self.metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"💾 Metadata saved to {self.metadata_path}")
    
    def load(self):
        """Load saved model and preprocessors"""
        if self.model_path.exists():
            self.model = load_model(self.model_path, custom_objects={
                'AttentionLayer': AttentionLayer,
                'PositionalEncoding': PositionalEncoding,
                'Time2Vec': Time2Vec
            })
            logger.info(f"📂 Model loaded from {self.model_path}")
        
        if self.scaler_X_path.exists():
            self.scaler_X = joblib.load(self.scaler_X_path)
            logger.info(f"📂 X scaler loaded")
        
        if self.scaler_y_path.exists():
            self.scaler_y = joblib.load(self.scaler_y_path)
            logger.info(f"📂 y scaler loaded")
        
        if self.metadata_path.exists():
            import json
            with open(self.metadata_path, 'r') as f:
                metadata = json.load(f)
                self.sequence_length = metadata.get('sequence_length', self.sequence_length)
                self.n_features = metadata.get('n_features', self.n_features)
                self.feature_columns = metadata.get('feature_columns', [])
            logger.info(f"📂 Metadata loaded")
    
    def fine_tune(self, df: pd.DataFrame, target_col: str = 'close',
                  epochs: int = 10, learning_rate: float = 0.0001) -> Dict:
        """Fine-tune existing model on new data"""
        if self.model is None:
            self.load()
        
        # Create features
        df_features = self.create_features(df)
        
        # Prepare data
        X = df_features[self.feature_columns].values[-1000:]  # Last 1000 samples
        y = df_features[target_col].values[-1000:].reshape(-1, 1)
        
        # Scale data
        X_scaled = self.scaler_X.transform(X)
        y_scaled = self.scaler_y.transform(y)
        
        # Create sequences
        X_seq, y_seq = self.prepare_sequences(X_scaled, y_scaled, self.sequence_length)
        
        if len(X_seq) == 0:
            logger.warning("⚠️ Not enough data for fine-tuning")
            return {}
        
        # Split data
        split = int(len(X_seq) * 0.8)
        X_train, y_train = X_seq[:split], y_seq[:split]
        X_val, y_val = X_seq[split:], y_seq[split:]
        
        # Recompile with lower learning rate
        self.model.compile(
            optimizer=Adam(learning_rate=learning_rate),
            loss='mse',
            metrics=['mae', 'mape']
        )
        
        # Fine-tune
        history = self.model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=epochs,
            batch_size=self.batch_size,
            verbose=1
        )
        
        logger.info(f"✅ Fine-tuning completed")
        
        return {
            'loss': history.history['loss'][-1],
            'val_loss': history.history['val_loss'][-1],
            'mae': history.history['mae'][-1],
            'val_mae': history.history['val_mae'][-1]
        }


class EnsemblePredictor:
    """Ensemble of multiple prediction models"""
    
    def __init__(self):
        self.models = []
        self.weights = []
        logger.info("🤖 Initialized Ensemble Predictor")
    
    def add_model(self, model, weight: float = 1.0):
        """Add a model to the ensemble"""
        self.models.append(model)
        self.weights.append(weight)
        logger.info(f"✅ Added model to ensemble (weight={weight})")
    
    def predict(self, df: pd.DataFrame, n_steps: int = 1) -> np.ndarray:
        """Ensemble prediction"""
        if not self.models:
            raise ValueError("No models in ensemble")
        
        predictions = []
        for model in self.models:
            pred = model.predict(df, n_steps)
            predictions.append(pred)
        
        # Weighted average
        weights = np.array(self.weights) / sum(self.weights)
        ensemble_pred = np.average(predictions, axis=0, weights=weights)
        
        return ensemble_pred
    
    def predict_with_confidence(self, df: pd.DataFrame) -> Dict:
        """Ensemble prediction with confidence intervals"""
        if not self.models:
            raise ValueError("No models in ensemble")
        
        all_predictions = []
        for model in self.models:
            pred = model.predict(df)
            all_predictions.append(pred[0, 0])
        
        predictions = np.array(all_predictions)
        weights = np.array(self.weights) / sum(self.weights)
        
        weighted_mean = np.average(predictions, weights=weights)
        weighted_std = np.sqrt(np.average((predictions - weighted_mean)**2, weights=weights))
        
        return {
            'mean': weighted_mean,
            'std': weighted_std,
            'min': np.min(predictions),
            'max': np.max(predictions),
            'q25': np.percentile(predictions, 25),
            'q75': np.percentile(predictions, 75),
            'individual_predictions': dict(enumerate(predictions))
        }
    
    def save(self, path: str):
        """Save ensemble configuration"""
        import json
        
        config = {
            'weights': self.weights,
            'model_configs': []
        }
        
        for model in self.models:
            config['model_configs'].append({
                'name': model.model_name,
                'version': model.version,
                'path': str(model.model_path)
            })
        
        with open(path, 'w') as f:
            json.dump(config, f, indent=2)
        
        logger.info(f"💾 Ensemble config saved to {path}")
    
    def load(self, path: str):
        """Load ensemble configuration"""
        import json
        
        with open(path, 'r') as f:
            config = json.load(f)
        
        self.weights = config['weights']
        
        for model_config in config['model_configs']:
            model = LSTMPredictor(
                model_name=model_config['name'],
                version=model_config['version']
            )
            model.load()
            self.models.append(model)
        
        logger.info(f"📂 Ensemble loaded from {path}")


class ModelRegistry:
    """Central registry for all AI models"""
    
    def __init__(self):
        self.models = {}
        self.metrics = {}
        logger.info("📚 Initialized Model Registry")
    
    def register(self, name: str, model, metadata: Dict = None):
        """Register a model in the registry"""
        self.models[name] = {
            'model': model,
            'metadata': metadata or {},
            'registered_at': datetime.now().isoformat()
        }
        logger.info(f"✅ Registered model: {name}")
    
    def get(self, name: str):
        """Get a model from registry"""
        return self.models.get(name, {}).get('model')
    
    def list_models(self) -> List[str]:
        """List all registered models"""
        return list(self.models.keys())
    
    def get_best_model(self, metric: str = 'accuracy') -> str:
        """Get best performing model based on metric"""
        best_score = -1
        best_model = None
        
        for name, data in self.models.items():
            if 'performance' in data['metadata']:
                score = data['metadata']['performance'].get(metric, 0)
                if score > best_score:
                    best_score = score
                    best_model = name
        
        return best_model
    
    def update_metrics(self, name: str, metrics: Dict):
        """Update metrics for a model"""
        if name in self.models:
            self.models[name]['metadata']['performance'] = metrics
            logger.info(f"📊 Updated metrics for {name}: {metrics}")
    
    def get_model_info(self, name: str) -> Dict:
        """Get detailed info about a model"""
        return self.models.get(name, {})
    
    def save_registry(self, path: str):
        """Save registry to disk"""
        import json
        
        registry_data = {}
        for name, data in self.models.items():
            registry_data[name] = {
                'metadata': data['metadata'],
                'registered_at': data['registered_at']
            }
        
        with open(path, 'w') as f:
            json.dump(registry_data, f, indent=2)
        
        logger.info(f"💾 Registry saved to {path}")
    
    def load_registry(self, path: str):
        """Load registry from disk"""
        import json
        
        with open(path, 'r') as f:
            registry_data = json.load(f)
        
        for name, data in registry_data.items():
            if name in self.models:
                self.models[name]['metadata'] = data['metadata']
                self.models[name]['registered_at'] = data['registered_at']
        
        logger.info(f"📂 Registry loaded from {path}")