"""
Signal Classifier Module
========================
Centralizes the logic for classifying the strength of a trading signal based on:
- Pattern Type
- Trend Status
- Bollinger Band Exhaustion
- Candle Exhaustion
- RSI (Optional)

Author: TradingView Pattern Monitor Team
"""

from typing import Optional
from config import Config

def classify_signal(
    pattern: str,
    trend_status: str,
    exhaustion_bb: str,
    candle_exhaustion: bool,
    rsi_val: Optional[float] = None
) -> str:
    """
    Classifies the strength of a signal based on multiple factors.
    
    Args:
        pattern: Pattern name (SHOOTING_STAR, HANGING_MAN, INVERTED_HAMMER, HAMMER)
        trend_status: Trend status (STRONG_BULLISH, WEAK_BULLISH, NEUTRAL, etc.)
        exhaustion_bb: Bollinger exhaustion type (PEAK, BOTTOM, NONE)
        candle_exhaustion: Boolean indicating if candle exhaustion occurred
        rsi_val: RSI value (optional)
        
    Returns:
        str: Signal strength (VERY_HIGH, HIGH, MEDIUM, LOW, VERY_LOW, NONE)
    """
    
    # 1. Determine Trend Context
    is_bullish_trend = "BULLISH" in trend_status
    is_bearish_trend = "BEARISH" in trend_status
    
    # 2. Determine Bollinger Exhaustion
    bollinger_exhaustion = exhaustion_bb in ["PEAK", "BOTTOM"]
    
    # 3. Initialize Strength
    signal_strength = "NONE"
    
    # 4. Classification Logic
    if is_bullish_trend:
        if pattern == "SHOOTING_STAR":
            if bollinger_exhaustion and candle_exhaustion:
                signal_strength = "VERY_HIGH"
            elif bollinger_exhaustion:
                signal_strength = "HIGH"
            elif candle_exhaustion:
                signal_strength = "LOW"
            else:
                signal_strength = "VERY_LOW"
                
        elif pattern == "INVERTED_HAMMER":
            if bollinger_exhaustion and candle_exhaustion:
                signal_strength = "MEDIUM"
            elif bollinger_exhaustion:
                signal_strength = "LOW"
            elif candle_exhaustion:
                signal_strength = "VERY_LOW"
            else:
                signal_strength = "NONE"
                
    elif is_bearish_trend:
        if pattern == "HAMMER":
            if bollinger_exhaustion and candle_exhaustion:
                signal_strength = "VERY_HIGH"
            elif bollinger_exhaustion:
                signal_strength = "HIGH"
            elif candle_exhaustion:
                signal_strength = "LOW"
            else:
                signal_strength = "VERY_LOW"
                
        elif pattern == "HANGING_MAN":
            if bollinger_exhaustion and candle_exhaustion:
                signal_strength = "MEDIUM"
            elif bollinger_exhaustion:
                signal_strength = "LOW"
            elif candle_exhaustion:
                signal_strength = "VERY_LOW"
            else:
                signal_strength = "NONE"
                
    # 5. Optional RSI Filter (Can be added here if needed to downgrade strength)
    # Currently handled outside or as a hard filter, but could be integrated here.
    
    return signal_strength
