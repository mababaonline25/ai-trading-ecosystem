"""
Signal generation and management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Optional
from datetime import datetime

from ....core.signals.signal_generator import SignalGenerator
from ....core.signals.signal_validator import SignalValidator
from ....core.signals.signal_aggregator import SignalAggregator
from ....core.analysis.technical.indicators import TechnicalIndicators
from ....core.analysis.fundamental.news_sentiment import NewsSentimentAnalyzer
from ....core.analysis.onchain.whale_tracker import WhaleTracker
from ....core.analysis.sentiment.social_analyzer import SocialAnalyzer
from ....core.ai.models.price_prediction.lstm_model import LSTMPredictor
from ....data.repositories.signal_repo import SignalRepository
from ....utils.auth import get_current_user
from ....utils.rate_limiter import rate_limit

router = APIRouter()
signal_generator = SignalGenerator()
signal_validator = SignalValidator()
signal_aggregator = SignalAggregator()
signal_repo = SignalRepository()
news_analyzer = NewsSentimentAnalyzer()
whale_tracker = WhaleTracker()
social_analyzer = SocialAnalyzer()
lstm_predictor = LSTMPredictor()


@router.get("/generate/{symbol}")
@rate_limit(requests=50, period=60)
async def generate_signal(
    symbol: str,
    interval: str = "1h",
    include_ai: bool = True,
    current_user = Depends(get_current_user)
):
    """ট্রেডিং সিগন্যাল জেনারেট করুন"""
    
    # মার্কেট ডেটা সংগ্রহ
    market_data = await signal_generator.collect_market_data(symbol, interval)
    if not market_data:
        raise HTTPException(status_code=404, detail="Market data not found")
    
    # টেকনিক্যাল সিগন্যাল
    technical_signal = await signal_generator.generate_technical_signal(market_data)
    
    # ফান্ডামেন্টাল সিগন্যাল
    fundamental_signal = await news_analyzer.analyze(symbol)
    
    # অন-চেইন সিগন্যাল
    onchain_signal = await whale_tracker.analyze(symbol)
    
    # সেন্টিমেন্ট সিগন্যাল
    sentiment_signal = await social_analyzer.analyze(symbol)
    
    # AI প্রেডিকশন
    ai_signal = None
    if include_ai:
        ai_signal = await lstm_predictor.predict(market_data)
    
    # সব সিগন্যাল একত্রিত
    combined_signal = signal_aggregator.aggregate([
        technical_signal,
        fundamental_signal,
        onchain_signal,
        sentiment_signal,
        ai_signal
    ])
    
    # সিগন্যাল ভ্যালিডেশন
    validated_signal = signal_validator.validate(combined_signal)
    
    # সিগন্যাল সংরক্ষণ
    signal_data = {
        "symbol": symbol,
        "interval": interval,
        "generated_by": current_user.id,
        "signal": validated_signal,
        "components": {
            "technical": technical_signal,
            "fundamental": fundamental_signal,
            "onchain": onchain_signal,
            "sentiment": sentiment_signal,
            "ai": ai_signal
        },
        "created_at": datetime.utcnow().isoformat()
    }
    await signal_repo.save_signal(signal_data)
    
    return signal_data


@router.get("/recent")
@rate_limit(requests=100, period=60)
async def get_recent_signals(
    limit: int = 20,
    symbol: Optional[str] = None,
    current_user = Depends(get_current_user)
):
    """সাম্প্রতিক সিগন্যাল"""
    signals = await signal_repo.get_recent_signals(limit, symbol)
    return {
        "total": len(signals),
        "signals": signals
    }


@router.get("/{signal_id}")
async def get_signal(
    signal_id: str,
    current_user = Depends(get_current_user)
):
    """নির্দিষ্ট সিগন্যাল দেখুন"""
    signal = await signal_repo.get_signal(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal


@router.post("/{signal_id}/feedback")
async def submit_signal_feedback(
    signal_id: str,
    feedback: dict,
    current_user = Depends(get_current_user)
):
    """সিগন্যাল ফিডব্যাক দিন"""
    await signal_repo.add_feedback(signal_id, current_user.id, feedback)
    return {"message": "Feedback submitted"}


@router.get("/stats/performance")
async def get_signal_performance(
    days: int = 30,
    current_user = Depends(get_current_user)
):
    """সিগন্যাল পারফরম্যান্স স্ট্যাটস"""
    stats = await signal_repo.get_performance_stats(days)
    return stats


@router.post("/subscribe/{symbol}")
async def subscribe_to_symbol(
    symbol: str,
    current_user = Depends(get_current_user)
):
    """নির্দিষ্ট সিম্বলের সিগন্যাল সাবস্ক্রাইব"""
    await signal_repo.subscribe(current_user.id, symbol)
    return {"message": f"Subscribed to {symbol} signals"}


@router.delete("/unsubscribe/{symbol}")
async def unsubscribe_from_symbol(
    symbol: str,
    current_user = Depends(get_current_user)
):
    """সাবস্ক্রিপশন বাতিল"""
    await signal_repo.unsubscribe(current_user.id, symbol)
    return {"message": f"Unsubscribed from {symbol}"}


@router.get("/subscriptions")
async def get_subscriptions(current_user = Depends(get_current_user)):
    """আমার সাবস্ক্রিপশন"""
    subscriptions = await signal_repo.get_subscriptions(current_user.id)
    return {"subscriptions": subscriptions}


@router.post("/batch-generate")
async def batch_generate_signals(
    background_tasks: BackgroundTasks,
    symbols: List[str],
    interval: str = "1h",
    current_user = Depends(get_current_user)
):
    """একাধিক সিম্বলের জন্য সিগন্যাল জেনারেট করুন"""
    background_tasks.add_task(
        signal_generator.batch_generate,
        symbols,
        interval,
        current_user.id
    )
    return {"message": "Signal generation started in background"}