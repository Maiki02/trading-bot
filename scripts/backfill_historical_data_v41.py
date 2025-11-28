"""
Historical Backtesting - Dataset Generator v4.1
================================================
Genera dataset de backtest con lógica actualizada para opciones binarias.

CAMBIOS v4.1:
- EMAs: 5, 7, 10, 15, 20, 30, 50 (eliminadas 100 y 200)
- Límite: 250 velas por request (suficiente para EMA 50)
- Integración directa con analyze_trend() de analysis_service
- Candle exhaustion basado en ruptura de niveles
- Signal strength según matriz de decisión actualizada
- algo_version: "4.1"

Author: Trading Bot Team
"""

import asyncio
import sys
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from src.services.tradingview_service import TradingViewService, HistoricalCandle
from src.services.storage_service import StorageService
from src.logic.candle import (
    is_shooting_star,
    is_hanging_man,
    is_inverted_hammer,
    is_hammer,
    get_candle_direction
)
from src.logic.analysis_service import (
    analyze_trend,
    calculate_ema,
    calculate_bollinger_bands,
    detect_exhaustion
)
from src.utils.logger import get_logger


logger = get_logger(__name__)


# =============================================================================
# CONFIGURATION v4.1
# =============================================================================

END_DATE = datetime.now()
DAYS_TO_FETCH = 30
START_DATE = END_DATE - timedelta(days=DAYS_TO_FETCH)

DAYS_PER_REQUEST = 5
REQUEST_DELAY = 0.5

SKIP_CANDLES = 100         # Suficiente para EMA 50
BUFFER_SIZE = 100
CANDLES_PER_REQUEST = 250  # Optimizado para EMA 50


# =============================================================================
# PATTERN DETECTION
# =============================================================================

def detect_pattern(candle: HistoricalCandle) -> Optional[Tuple[str, float]]:
    """Detecta patrón de vela."""
    direction = get_candle_direction(candle.open, candle.close)
    
    if direction == "DOJI":
        return None
    
    if direction == "ROJA":
        is_pattern, confidence = is_shooting_star(candle.open, candle.high, candle.low, candle.close)
        if is_pattern:
            return ("SHOOTING_STAR", confidence)
        
        is_pattern, confidence = is_hanging_man(candle.open, candle.high, candle.low, candle.close)
        if is_pattern:
            return ("HANGING_MAN", confidence)
    
    elif direction == "VERDE":
        is_pattern, confidence = is_inverted_hammer(candle.open, candle.high, candle.low, candle.close)
        if is_pattern:
            return ("INVERTED_HAMMER", confidence)
        
        is_pattern, confidence = is_hammer(candle.open, candle.high, candle.low, candle.close)
        if is_pattern:
            return ("HAMMER", confidence)
    
    return None


# =============================================================================
# INDICATOR CALCULATION v4.1
# =============================================================================

def calculate_emas_from_buffer(buffer: List[HistoricalCandle]) -> Dict[str, float]:
    """
    Calcula EMAs 5, 7, 10, 15, 20, 30, 50.
    
    IMPORTANTE: Usa calculate_ema() de analysis_service (misma lógica que producción).
    """
    if len(buffer) < 50:
        return {
            'ema_5': np.nan,
            'ema_7': np.nan,
            'ema_10': np.nan,
            'ema_15': np.nan,
            'ema_20': np.nan,
            'ema_30': np.nan,
            'ema_50': np.nan
        }
    
    df = pd.DataFrame([{'close': c.close} for c in buffer])
    
    return {
        'ema_5': calculate_ema(df['close'], 5).iloc[-1] if len(buffer) >= 5 else np.nan,
        'ema_7': calculate_ema(df['close'], 7).iloc[-1] if len(buffer) >= 7 else np.nan,
        'ema_10': calculate_ema(df['close'], 10).iloc[-1] if len(buffer) >= 10 else np.nan,
        'ema_15': calculate_ema(df['close'], 15).iloc[-1] if len(buffer) >= 15 else np.nan,
        'ema_20': calculate_ema(df['close'], 20).iloc[-1] if len(buffer) >= 20 else np.nan,
        'ema_30': calculate_ema(df['close'], 30).iloc[-1] if len(buffer) >= 30 else np.nan,
        'ema_50': calculate_ema(df['close'], 50).iloc[-1] if len(buffer) >= 50 else np.nan
    }


def calculate_bollinger_bands_from_buffer(buffer: List[HistoricalCandle]) -> Dict[str, float]:
    """Calcula Bollinger Bands usando lógica de analysis_service."""
    if len(buffer) < Config.CANDLE.BB_PERIOD:
        return {'upper': np.nan, 'lower': np.nan, 'middle': np.nan}
    
    df = pd.DataFrame([{'close': c.close} for c in buffer])
    
    try:
        bb_middle, bb_upper, bb_lower = calculate_bollinger_bands(
            df['close'],
            period=Config.CANDLE.BB_PERIOD,
            std_dev=Config.CANDLE.BB_STD_DEV
        )
        
        return {
            'upper': float(bb_upper.iloc[-1]),
            'lower': float(bb_lower.iloc[-1]),
            'middle': float(bb_middle.iloc[-1])
        }
    except Exception as e:
        logger.warning(f"⚠️ Error calculando Bollinger Bands: {e}")
        return {'upper': np.nan, 'lower': np.nan, 'middle': np.nan}


# =============================================================================
# EXHAUSTION DETECTION v4.1
# =============================================================================

def detect_candle_exhaustion(
    pattern_name: str,
    current_candle: HistoricalCandle,
    previous_candle: HistoricalCandle
) -> bool:
    """
    Detecta exhaustion de vela (ruptura de nivel).
    
    Lógica v4.1:
    - Bajista (Shooting Star, Hanging Man): High actual > High anterior
    - Alcista (Hammer, Inverted Hammer): Low actual < Low anterior
    """
    if pattern_name in ["SHOOTING_STAR", "HANGING_MAN"]:
        return current_candle.high > previous_candle.high
    
    elif pattern_name in ["HAMMER", "INVERTED_HAMMER"]:
        return current_candle.low < previous_candle.low
    
    return False


def calculate_signal_strength(
    pattern_name: str,
    trend_score: float,
    bollinger_exhaustion: bool,
    candle_exhaustion: bool
) -> str:
    """
    Calcula signal_strength según matriz de decisión v4.1.
    
    REGLAS DE NEGOCIO:
    - Tendencia ALCISTA (score > 2): Buscamos VENTAS
      * Shooting Star (Principal): VERY_HIGH/HIGH/LOW/VERY_LOW
      * Inverted Hammer (Secundario): MEDIUM/LOW/VERY_LOW/NONE
    
    - Tendencia BAJISTA (score < -2): Buscamos COMPRAS
      * Hammer (Principal): VERY_HIGH/HIGH/LOW/VERY_LOW
      * Hanging Man (Secundario): MEDIUM/LOW/VERY_LOW/NONE
    
    - Tendencia NEUTRAL (-2 a 2): Degradar un nivel
    """
    is_bullish_trend = trend_score > 2.0
    is_bearish_trend = trend_score < -2.0
    is_neutral = -2.0 <= trend_score <= 2.0
    
    primary_bearish = pattern_name == "SHOOTING_STAR"
    secondary_bearish = pattern_name == "INVERTED_HAMMER"
    primary_bullish = pattern_name == "HAMMER"
    secondary_bullish = pattern_name == "HANGING_MAN"
    
    strength = "NONE"
    
    # CASO A: TENDENCIA ALCISTA (Buscamos VENTAS)
    if is_bullish_trend:
        if primary_bearish:
            if bollinger_exhaustion and candle_exhaustion:
                strength = "VERY_HIGH"
            elif bollinger_exhaustion:
                strength = "HIGH"
            elif candle_exhaustion:
                strength = "LOW"
            else:
                strength = "VERY_LOW"
        
        elif secondary_bearish:
            if bollinger_exhaustion and candle_exhaustion:
                strength = "MEDIUM"
            elif bollinger_exhaustion:
                strength = "LOW"
            elif candle_exhaustion:
                strength = "VERY_LOW"
            else:
                strength = "NONE"
    
    # CASO B: TENDENCIA BAJISTA (Buscamos COMPRAS)
    elif is_bearish_trend:
        if primary_bullish:
            if bollinger_exhaustion and candle_exhaustion:
                strength = "VERY_HIGH"
            elif bollinger_exhaustion:
                strength = "HIGH"
            elif candle_exhaustion:
                strength = "LOW"
            else:
                strength = "VERY_LOW"
        
        elif secondary_bullish:
            if bollinger_exhaustion and candle_exhaustion:
                strength = "MEDIUM"
            elif bollinger_exhaustion:
                strength = "LOW"
            elif candle_exhaustion:
                strength = "VERY_LOW"
            else:
                strength = "NONE"
    
    # CASO C: TENDENCIA NEUTRAL (Degradar)
    if is_neutral and strength != "NONE":
        degradation_map = {
            "VERY_HIGH": "HIGH",
            "HIGH": "MEDIUM",
            "MEDIUM": "LOW",
            "LOW": "VERY_LOW",
            "VERY_LOW": "NONE"
        }
        strength = degradation_map.get(strength, "NONE")
    
    return strength


# =============================================================================
# BACKTESTING ENGINE v4.1
# =============================================================================

class BacktestingEngine:
    """Motor de backtesting v4.1."""
    
    def __init__(self, storage_service: StorageService):
        self.storage_service = storage_service
        self.total_patterns_found = 0
        self.total_patterns_saved = 0
    
    async def run(self):
        """Ejecuta backtesting para todos los instrumentos."""
        logger.info("=" * 80)
        logger.info("🚀 BACKTESTING v4.1 - MULTI-INSTRUMENTO")
        logger.info("=" * 80)
        logger.info(f"📅 Rango: {START_DATE.strftime('%Y-%m-%d')} a {END_DATE.strftime('%Y-%m-%d')}")
        logger.info(f"📦 Velas por request: {CANDLES_PER_REQUEST}")
        logger.info(f"⏭️  Skip: {SKIP_CANDLES}")
        logger.info(f"📊 EMAs: 5, 7, 10, 15, 20, 30, 50")
        logger.info("=" * 80)
        
        for instrument_key, instrument_config in Config.INSTRUMENTS.items():
            logger.info(f"\n{'=' * 80}")
            logger.info(f"📊 {instrument_config.exchange}:{instrument_config.symbol}")
            logger.info(f"{'=' * 80}")
            
            try:
                tv_service = TradingViewService()
                
                logger.info(f"📥 Obteniendo velas históricas...")
                all_candles = await self._fetch_historical_candles_chunked(
                    tv_service,
                    instrument_config,
                    START_DATE,
                    END_DATE
                )
                
                if not all_candles:
                    logger.warning(f"⚠️ Sin velas para {instrument_config.symbol}")
                    continue
                
                logger.info(f"✅ Total velas: {len(all_candles):,}")
                
                patterns_found, patterns_saved = await self._process_candles(
                    all_candles,
                    instrument_config
                )
                
                logger.info(f"\n✅ Completado: {patterns_found} encontrados, {patterns_saved} guardados")
                
                self.total_patterns_found += patterns_found
                self.total_patterns_saved += patterns_saved
            
            except Exception as e:
                logger.error(f"❌ Error: {e}")
                continue
        
        logger.info(f"\n{'=' * 80}")
        logger.info("🎉 COMPLETADO")
        logger.info(f"Total encontrados: {self.total_patterns_found}")
        logger.info(f"Total guardados: {self.total_patterns_saved}")
        logger.info(f"{'=' * 80}")
    
    async def _fetch_historical_candles_chunked(
        self,
        tv_service: TradingViewService,
        instrument_config,
        start_date: datetime,
        end_date: datetime
    ) -> List[HistoricalCandle]:
        """Obtiene velas en chunks."""
        all_candles = []
        current_end = end_date
        chunk_number = 1
        
        # Calcular número de chunks necesarios
        days_to_fetch = (end_date - start_date).days
        num_chunks = (days_to_fetch + DAYS_PER_REQUEST - 1) // DAYS_PER_REQUEST
        
        logger.info(f"📦 Dividiendo {days_to_fetch} días en {num_chunks} chunks de ~{DAYS_PER_REQUEST} días")
        
        for chunk_num in range(num_chunks):
            # Calcular rango de este chunk
            chunk_start = max(start_date, current_end - timedelta(days=DAYS_PER_REQUEST))
            chunk_days = (current_end - chunk_start).days
            
            # Calcular velas aproximadas (1 minuto = 1440 velas/día)
            estimated_candles = chunk_days * 1440
            
            logger.info(f"\n📥 Chunk {chunk_num + 1}/{num_chunks}: {chunk_start.strftime('%Y-%m-%d')} a {current_end.strftime('%Y-%m-%d')} (~{chunk_days} días)")
            
            try:
                candles = await tv_service.fetch_historical_candles(
                    symbol=instrument_config.symbol,
                    exchange=instrument_config.exchange,
                    timeframe=instrument_config.timeframe,
                    num_candles=estimated_candles + 500  # Buffer extra
                )
                
                if candles:
                    # No filtrar por timestamp aquí - TradingView devuelve las últimas velas disponibles
                    # El filtro por fecha se hace después eliminando duplicados
                    logger.info(f"✅ Recibidas: {len(candles):,} velas")
                    all_candles.extend(candles)
                else:
                    logger.warning(f"⚠️  No se recibieron velas")
                
                # Esperar entre peticiones
                if chunk_num < num_chunks - 1:
                    await asyncio.sleep(REQUEST_DELAY)
                
                # Mover al siguiente chunk
                current_end = chunk_start
            
            except Exception as e:
                logger.error(f"❌ Error en chunk {chunk_num + 1}: {e}")
                continue
        
        # Eliminar duplicados y ordenar
        if all_candles:
            unique_candles = {c.timestamp: c for c in all_candles}
            sorted_candles = sorted(unique_candles.values(), key=lambda c: c.timestamp)
            
            logger.info(f"\n📊 Total únicas: {len(sorted_candles):,} velas")
            return sorted_candles
        
        return []
    
    async def _process_candles(
        self,
        all_candles: List[HistoricalCandle],
        instrument_config
    ) -> Tuple[int, int]:
        """
        Procesa velas y genera dataset v4.1.
        
        Returns:
            (patrones_encontrados, patrones_guardados)
        """
        patterns_found = 0
        patterns_saved = 0
        
        logger.info(f"🔍 Analizando desde vela {SKIP_CANDLES} hasta {len(all_candles) - 1}...")
        
        for i in range(SKIP_CANDLES, len(all_candles) - 1):
            current_candle = all_candles[i]
            
            pattern_result = detect_pattern(current_candle)
            if not pattern_result:
                continue
            
            pattern_name, confidence = pattern_result
            patterns_found += 1
            
            # Buffer de velas previas
            buffer_start = max(0, i - BUFFER_SIZE)
            buffer = all_candles[buffer_start:i + 1]
            
            # Calcular EMAs v4.1 usando lógica de analysis_service
            emas = calculate_emas_from_buffer(buffer)
            
            # Calcular trend usando analyze_trend() IMPORTADO
            trend_analysis = analyze_trend(current_candle.close, emas)
            
            # Bollinger Bands
            bb = calculate_bollinger_bands_from_buffer(buffer)
            
            # Detect exhaustion usando lógica de analysis_service
            exhaustion_type = detect_exhaustion(
                candle_high=current_candle.high,
                candle_low=current_candle.low,
                candle_close=current_candle.close,
                upper_band=bb['upper'],
                lower_band=bb['lower']
            )
            bollinger_exhaustion = exhaustion_type in ["PEAK", "BOTTOM"]
            
            # Candle exhaustion (nueva lógica v4.1)
            previous_candle = all_candles[i - 1]
            candle_exhaustion = detect_candle_exhaustion(
                pattern_name,
                current_candle,
                previous_candle
            )
            
            # Signal strength (matriz v4.1)
            signal_strength = calculate_signal_strength(
                pattern_name,
                trend_analysis.score,
                bollinger_exhaustion,
                candle_exhaustion
            )
            
            # Outcome (vela siguiente)
            next_candle = all_candles[i + 1]
            outcome = get_candle_direction(next_candle.open, next_candle.close)
            
            # Registro v4.1 (estructura híbrida: compatible con StorageService y análisis)
            record = {
                # Campos de nivel superior para análisis fácil
                "algo_version": "4.1",
                "timestamp": current_candle.timestamp,
                "source": instrument_config.exchange,
                "symbol": instrument_config.symbol,
                "timeframe": instrument_config.timeframe,
                
                # Pattern info flat (para análisis)
                "pattern_name": pattern_name,
                "pattern_confidence": confidence,
                
                # EMAs flat (para análisis)
                "ema_5": emas['ema_5'],
                "ema_7": emas['ema_7'],
                "ema_10": emas['ema_10'],
                "ema_15": emas['ema_15'],
                "ema_20": emas['ema_20'],
                "ema_30": emas['ema_30'],
                "ema_50": emas['ema_50'],
                
                # Trend flat
                "trend_status": trend_analysis.status,
                "trend_score": trend_analysis.score,
                "trend_is_aligned": trend_analysis.is_aligned,
                
                # Bollinger flat
                "bb_upper": bb['upper'],
                "bb_lower": bb['lower'],
                "bb_middle": bb['middle'],
                
                # Exhaustion flat
                "bollinger_exhaustion": bollinger_exhaustion,
                "exhaustion_type": exhaustion_type,
                "candle_exhaustion": candle_exhaustion,
                "signal_strength": signal_strength,
                
                # Outcome flat
                "outcome": outcome,
                
                # Estructura anidada para compatibilidad con StorageService
                "pattern_candle": {
                    "timestamp": current_candle.timestamp,
                    "open": current_candle.open,
                    "high": current_candle.high,
                    "low": current_candle.low,
                    "close": current_candle.close,
                    "volume": current_candle.volume,
                    "pattern": pattern_name,
                    "confidence": confidence
                },
                "emas": {
                    "ema_5": emas['ema_5'],
                    "ema_7": emas['ema_7'],
                    "ema_10": emas['ema_10'],
                    "ema_15": emas['ema_15'],
                    "ema_20": emas['ema_20'],
                    "ema_30": emas['ema_30'],
                    "ema_50": emas['ema_50'],
                    "trend_status": trend_analysis.status,
                    "trend_score": trend_analysis.score,
                    "trend_is_aligned": trend_analysis.is_aligned
                },
                "outcome_candle": {
                    "timestamp": next_candle.timestamp,
                    "open": next_candle.open,
                    "high": next_candle.high,
                    "low": next_candle.low,
                    "close": next_candle.close,
                    "volume": next_candle.volume,
                    "direction": outcome
                },
                "metadata": {
                    "algo_version": "4.1",
                    "created_at": datetime.now().isoformat()
                }
            }
            
            await self.storage_service.save_signal_outcome(record)
            patterns_saved += 1
            
            if patterns_saved % 100 == 0:
                logger.info(f"  💾 {patterns_saved} guardados...")
        
        return patterns_found, patterns_saved


# =============================================================================
# MAIN
# =============================================================================

async def main():
    """Función principal."""
    logger.info("=" * 80)
    logger.info("📊 HISTORICAL BACKTESTING v4.1")
    logger.info("=" * 80)
    
    storage_service = StorageService()
    engine = BacktestingEngine(storage_service)
    
    await engine.run()
    
    logger.info("\n✅ Proceso completado")


if __name__ == "__main__":
    asyncio.run(main())
