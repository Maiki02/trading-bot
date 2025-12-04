"""
Backtesting Historical Data V8 (IQ Option)
==========================================
Descarga data histórica masiva de IQ Option y genera un dataset JSONL tipado
para validar estrategias de "Limit Entry" (entrada al 50% de retroceso).

Features:
- Descarga inversa (Reverse Iteration) para superar límites de API.
- Reordenamiento y limpieza de duplicados.
- Cálculo de indicadores técnicos (EMAs, BB, RSI).
- Detección de patrones (Shooting Star, Hammer, etc.).
- Análisis de tendencia V7.1 (Slope & Structure).
- Salida en formato JSONL estricto (Raw Data).

Usage:
    python scripts/backtesting_historical_data_v8.py [--days 30]
"""

import os
import sys
import time
import json
import logging
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super(NumpyEncoder, self).default(obj)

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from iqoptionapi.stable_api import IQ_Option
from config import Config

# Import logic modules
from src.utils.indicators import calculate_ema, calculate_bollinger_bands, calculate_rsi
from src.logic.candle import (
    is_shooting_star, is_hanging_man, is_inverted_hammer, is_hammer,
    get_candle_direction, detect_candle_exhaustion
)
from src.logic.analysis_service import analyze_trend, detect_exhaustion

# =============================================================================
# CONFIGURATION
# =============================================================================

# Logging Setup
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/backtesting_v8.log", mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True
)
logger = logging.getLogger("BacktestingV8")

# Suppress verbose libraries
logging.getLogger("iqoptionapi").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("websocket").setLevel(logging.WARNING)

# Constants
OUTPUT_FILE = "data/trading_signals_dataset_v8.jsonl"
CHUNK_SIZE = 1000
DELAY_BETWEEN_CHUNKS = 0.0
WARMUP_CANDLES = 100

# =============================================================================
# DATA FETCHING LOGIC
# =============================================================================

def inject_custom_actives():
    """Inyecta los activos personalizados definidos en Config."""
    import iqoptionapi.constants
    
    if not Config.CUSTOM_ACTIVES:
        return

    logger.info(f"💉 Inyectando {len(Config.CUSTOM_ACTIVES)} activos personalizados en la librería...")

    count = 0
    for item in Config.CUSTOM_ACTIVES:
        key = item.get("key")
        active_id = item.get("id")

        if key and active_id:
            iqoptionapi.constants.ACTIVES[key] = active_id
            logger.debug(f"   + Activo inyectado: {key} -> {active_id}")
            count += 1
        else:
            logger.warning(f"⚠️ Formato inválido en activo personalizado: {item}")

    logger.info(f"✅ Se agregaron {count} nuevos activos a IQ Option API.")

def connect_iq_option() -> IQ_Option:
    """Connects to IQ Option."""
    email = Config.IQOPTION.email
    password = Config.IQOPTION.password
    
    if not email or not password:
        logger.error("❌ IQ Option credentials missing in .env")
        sys.exit(1)
        
    logger.info(f"🔌 Connecting to IQ Option ({email})...")
    iq = IQ_Option(email, password)
    check, reason = iq.connect()
    
    if check:
        logger.info("✅ Connected successfully!")
    else:
        logger.error(f"❌ Connection failed: {reason}")
        sys.exit(1)
        
    return iq

def fetch_historical_data(iq: IQ_Option, asset: str, start_ts: int, end_ts: int) -> List[Dict]:
    """Fetches historical candles using reverse iteration."""
    all_candles = []
    current_to_ts = end_ts
    
    logger.info(f"📥 Fetching {asset} from {datetime.fromtimestamp(start_ts)} to {datetime.fromtimestamp(end_ts)}")
    
    while current_to_ts > start_ts:
        try:
            candles = iq.get_candles(asset, 60, CHUNK_SIZE, current_to_ts)
            
            if not candles:
                logger.warning(f"⚠️  No candles received for {asset} at {current_to_ts}")
                break
                
            chunk_candles = [c for c in candles if c['from'] >= start_ts and c['from'] <= end_ts]
            
            if not chunk_candles:
                logger.info("⏹️  Reached start of requested range.")
                break
                
            all_candles.extend(chunk_candles)
            
            min_ts = min(c['from'] for c in candles)
            current_to_ts = min_ts - 1
            
            logger.info(f"   Got {len(chunk_candles)} candles. Newest: {datetime.fromtimestamp(chunk_candles[-1]['from'])}, Oldest: {datetime.fromtimestamp(chunk_candles[0]['from'])}")
            
            time.sleep(DELAY_BETWEEN_CHUNKS)
            
        except Exception as e:
            logger.error(f"❌ Error fetching chunk: {e}")
            time.sleep(5)
            break
            
    unique_candles = {c['from']: c for c in all_candles}
    sorted_candles = sorted(unique_candles.values(), key=lambda x: x['from'])
    
    logger.info(f"✅ Total unique candles for {asset}: {len(sorted_candles)}")
    return sorted_candles

# =============================================================================
# PROCESSING LOGIC
# =============================================================================

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculates all technical indicators required for V8 analysis."""
    for period in [3, 5, 7, 10, 15, 20, 30, 50]:
        df[f'ema_{period}'] = calculate_ema(df['close'], period)
        
    df['bb_upper'], df['bb_middle'], df['bb_lower'] = calculate_bollinger_bands(
        df['close'], Config.CANDLE.BB_PERIOD, Config.CANDLE.BB_STD_DEV
    )
    
    df['rsi'] = calculate_rsi(df['close'], Config.RSI_PERIOD)
    
    return df

def analyze_candle_row(row: pd.Series, prev_row: pd.Series, prev_emas: Dict[str, float]) -> Optional[Dict]:
    """
    Analyzes a single candle row for patterns and signals.
    Returns a signal dict if found, else None.
    """
    open_p = row['open']
    high = row['max']
    low = row['min']
    close = row['close']
    timestamp = int(row['from'])
    
    emas = {
        'ema_3': row['ema_3'], 'ema_5': row['ema_5'], 'ema_7': row['ema_7'],
        'ema_10': row['ema_10'], 'ema_15': row['ema_15'], 'ema_20': row['ema_20'],
        'ema_30': row['ema_30'], 'ema_50': row['ema_50']
    }
    
    # Analyze Trend
    trend_analysis = analyze_trend(close, emas, prev_emas)
    
    # Detect Patterns
    patterns = []
    
    is_ss, conf_ss, _ = is_shooting_star(open_p, high, low, close)
    if is_ss: patterns.append(('SHOOTING_STAR', conf_ss, 'PUT'))
    
    is_hm, conf_hm, _ = is_hanging_man(open_p, high, low, close)
    if is_hm: patterns.append(('HANGING_MAN', conf_hm, 'CALL'))
    
    is_ih, conf_ih, _ = is_inverted_hammer(open_p, high, low, close)
    if is_ih: patterns.append(('INVERTED_HAMMER', conf_ih, 'PUT'))
    
    is_h, conf_h, _ = is_hammer(open_p, high, low, close)
    if is_h: patterns.append(('HAMMER', conf_h, 'CALL'))
    
    if not patterns:
        return None
        
    # Filter & Validate Signals
    best_signal = None
    
    for pattern_name, confidence, direction in patterns:
        # Trend Filter
        is_bullish_trend = "BULLISH" in trend_analysis.status
        is_bearish_trend = "BEARISH" in trend_analysis.status
        
        valid_trend = False
        if direction == 'PUT' and is_bullish_trend: valid_trend = True
        if direction == 'CALL' and is_bearish_trend: valid_trend = True
        
        if not valid_trend and trend_analysis.status != "NEUTRAL":
            continue
            
        # Indicators
        exhaustion = detect_exhaustion(high, low, close, row['bb_upper'], row['bb_lower'])
        candle_exhaustion = detect_candle_exhaustion(pattern_name, high, low, prev_row['max'], prev_row['min'])
        rsi_val = row['rsi']
        
        # Signal Strength
        signal_strength = "NONE"
        bollinger_exhaustion = exhaustion in ["PEAK", "BOTTOM"]
        
        if is_bullish_trend:
            if pattern_name == "SHOOTING_STAR":
                if bollinger_exhaustion and candle_exhaustion: signal_strength = "VERY_HIGH"
                elif bollinger_exhaustion: signal_strength = "HIGH"
                elif candle_exhaustion: signal_strength = "LOW"
                else: signal_strength = "VERY_LOW"
            elif pattern_name == "INVERTED_HAMMER":
                if bollinger_exhaustion and candle_exhaustion: signal_strength = "MEDIUM"
                elif bollinger_exhaustion: signal_strength = "LOW"
                elif candle_exhaustion: signal_strength = "VERY_LOW"
                else: signal_strength = "NONE"
        elif is_bearish_trend:
            if pattern_name == "HAMMER":
                if bollinger_exhaustion and candle_exhaustion: signal_strength = "VERY_HIGH"
                elif bollinger_exhaustion: signal_strength = "HIGH"
                elif candle_exhaustion: signal_strength = "LOW"
                else: signal_strength = "VERY_LOW"
            elif pattern_name == "HANGING_MAN":
                if bollinger_exhaustion and candle_exhaustion: signal_strength = "MEDIUM"
                elif bollinger_exhaustion: signal_strength = "LOW"
                elif candle_exhaustion: signal_strength = "VERY_LOW"
                else: signal_strength = "NONE"

        # Construct Clean Signal Object
        signal = {
            'metadata': {
                'algo_version': Config.ALGO_VERSION,
                'symbol': row['symbol'],
                'timestamp': timestamp,
                'datetime': datetime.fromtimestamp(timestamp).isoformat()
            },
            'signal': {
                'pattern_name': pattern_name,
                'direction': direction,
                'confidence': confidence,
                'signal_strength': signal_strength,
                'rsi_filter_passed': True # Placeholder, logic moved to analyzer
            },
            'pattern_candle': {
                'timestamp': int(timestamp),
                'open': float(row['open']),
                'high': float(high),
                'low': float(low),
                'close': float(row['close']),
                'volume': float(row['volume']),
                'pattern': pattern_name,
                'confidence': float(confidence)
            },
            'technical': {
                'ema_values': emas,
                'rsi_value': rsi_val,
                'trend_score': trend_analysis.score,
                'trend_status': trend_analysis.status,
                'exhaustion_bb': exhaustion,
                'exhaustion_candle': candle_exhaustion
            }
        }
        
        best_signal = signal
        break
        
    return best_signal

# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Backtesting Data Generator V8')
    parser.add_argument('--days', type=int, default=30, help='Days of history to fetch')
    args = parser.parse_args()
    
    if Config.DATA_PROVIDER != "IQOPTION":
        logger.error("❌ Config.DATA_PROVIDER must be 'IQOPTION'")
        sys.exit(1)
    
    inject_custom_actives()
    iq = connect_iq_option()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    
    start_ts = int(start_date.timestamp())
    end_ts = int(end_date.timestamp())
    
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    existing_keys = set()
    if os.path.exists(OUTPUT_FILE):
        logger.info(f"📖 Reading existing data from {OUTPUT_FILE} to prevent duplicates...")
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        meta = record.get('metadata', {})
                        key = (
                            meta.get('algo_version'),
                            meta.get('source', 'IQOPTION'),
                            meta.get('symbol'),
                            meta.get('timestamp')
                        )
                        existing_keys.add(key)
                    except json.JSONDecodeError:
                        continue
            logger.info(f"ℹ️  Found {len(existing_keys)} existing records.")
        except Exception as e:
            logger.error(f"⚠️  Error reading existing file: {e}")

    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f_out:
        for asset in Config.TARGET_ASSETS:
            logger.info(f"🚀 Processing {asset}...")
            
            raw_candles = fetch_historical_data(iq, asset, start_ts, end_ts)
            
            if len(raw_candles) < WARMUP_CANDLES:
                logger.warning(f"⚠️  Not enough candles for {asset}. Skipping.")
                continue
                
            df = pd.DataFrame(raw_candles)
            df['symbol'] = asset
            df = calculate_indicators(df)
            
            signals_count = 0
            
            for i in range(WARMUP_CANDLES, len(df) - 1):
                row = df.iloc[i]
                prev_row = df.iloc[i-1]
                
                prev_emas = {
                    'ema_3': prev_row['ema_3'], 'ema_5': prev_row['ema_5'], 'ema_20': prev_row['ema_20']
                }
                
                signal = analyze_candle_row(row, prev_row, prev_emas)
                
                if signal:
                    outcome_row = df.iloc[i+1]
                    
                    signal['outcome_candle'] = {
                        'timestamp': int(outcome_row['from']),
                        'open': float(outcome_row['open']),
                        'high': float(outcome_row['max']),
                        'low': float(outcome_row['min']),
                        'close': float(outcome_row['close']),
                        'volume': float(outcome_row['volume'])
                    }
                    
                    current_key = (
                        Config.ALGO_VERSION,
                        "IQOPTION",
                        row['symbol'],
                        int(row['from'])
                    )
                    
                    if current_key in existing_keys:
                        continue

                    f_out.write(json.dumps(signal, cls=NumpyEncoder) + "\n")
                    signals_count += 1
                    existing_keys.add(current_key)
            
            logger.info(f"✅ Generated {signals_count} signals for {asset}")
            
    logger.info(f"🎉 Done! Dataset saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
