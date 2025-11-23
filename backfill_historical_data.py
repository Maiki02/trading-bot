"""
Historical Backtesting - Dataset Generator
===========================================
Este script obtiene 35,000 velas históricas de TradingView y genera
un dataset de backtesting detectando patrones y calculando probabilidades.

Proceso:
1. Obtener 35,000 velas históricas
2. Saltar las primeras 1,000 (usadas para inicializar EMAs)
3. Recorrer velas 1,001 a 35,000
4. Para cada vela:
   - Detectar si hay patrón (SHOOTING_STAR, HANGING_MAN, INVERTED_HAMMER, HAMMER)
   - Si hay patrón:
     * Calcular EMAs con las 1,000 velas anteriores
     * Calcular alineación de EMAs
     * Calcular score de tendencia
     * Obtener siguiente vela (outcome)
     * Guardar en dataset JSONL

Author: TradingView Pattern Monitor Team
"""

import asyncio
import sys
import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path

# Agregar el directorio raíz al path para imports
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
from src.logic.analysis_service import analyze_trend, calculate_ema, calculate_bollinger_bands, detect_exhaustion
from src.utils.logger import get_logger


logger = get_logger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Rango de fechas para backtesting
# NOTA: TradingView tiene un límite de ~10,000 velas por request
# Para 1 minuto: 10,000 velas = ~7 días de datos continuos
# Sistema divide automáticamente en chunks de DAYS_PER_REQUEST días
from datetime import datetime, timedelta

END_DATE = datetime.now()  # Fecha final (ahora)
DAYS_TO_FETCH = 30  # Días hacia atrás (último mes)
START_DATE = END_DATE - timedelta(days=DAYS_TO_FETCH)

DAYS_PER_REQUEST = 5  # Días por petición (5 días = ~7,200 velas para 1min)
REQUEST_DELAY = 0.5  # Segundos entre peticiones (evitar rate limiting)

# Buffer y skip
SKIP_CANDLES = 1000    # Velas a saltar (para inicializar EMAs)
BUFFER_SIZE = 1000     # Tamaño del buffer para cálculo de EMAs


# =============================================================================
# PATTERN DETECTION
# =============================================================================

def detect_pattern(candle: HistoricalCandle) -> Optional[tuple]:
    """
    Detecta si una vela tiene algún patrón válido.
    
    Optimización: Solo verifica patrones compatibles con el color de la vela.
    - ROJA: Shooting Star o Hanging Man
    - VERDE: Hammer o Inverted Hammer
    - DOJI: No se analiza (sin patrón claro)
    
    Args:
        candle: Vela a analizar
        
    Returns:
        tuple: (nombre_patrón, confianza) o None
    """
    # Determinar color de la vela
    direction = get_candle_direction(candle.open, candle.close)
    
    # DOJI no tiene patrones claros
    if direction == "DOJI":
        return None
    
    # Las funciones de detección retornan (is_pattern: bool, confidence: float)
    
    if direction == "ROJA":
        # Solo patrones bajistas para velas rojas
        is_pattern, confidence = is_shooting_star(candle.open, candle.high, candle.low, candle.close)
        if is_pattern:
            return ("SHOOTING_STAR", confidence)
        
        is_pattern, confidence = is_hanging_man(candle.open, candle.high, candle.low, candle.close)
        if is_pattern:
            return ("HANGING_MAN", confidence)
    
    elif direction == "VERDE":
        # Solo patrones alcistas para velas verdes
        is_pattern, confidence = is_inverted_hammer(candle.open, candle.high, candle.low, candle.close)
        if is_pattern:
            return ("INVERTED_HAMMER", confidence)
        
        is_pattern, confidence = is_hammer(candle.open, candle.high, candle.low, candle.close)
        if is_pattern:
            return ("HAMMER", confidence)
    
    return None


# =============================================================================
# EMA CALCULATION
# =============================================================================

def calculate_emas_from_buffer(buffer: List[HistoricalCandle]) -> Dict[str, float]:
    """
    Calcula las EMAs 200, 50, 30, 20 desde un buffer de velas.
    
    Args:
        buffer: Lista de velas (debe tener al menos 1000 velas)
        
    Returns:
        Dict con ema_200, ema_50, ema_30, ema_20
    """
    if len(buffer) < 200:
        return {
            'ema_200': np.nan,
            'ema_50': np.nan,
            'ema_30': np.nan,
            'ema_20': np.nan
        }
    
    # Crear DataFrame con precios de cierre
    df = pd.DataFrame([{
        'timestamp': c.timestamp,
        'close': c.close
    } for c in buffer])
    
    # Calcular EMAs
    ema_200 = calculate_ema(df['close'], 200).iloc[-1] if len(buffer) >= 200 else np.nan
    ema_50 = calculate_ema(df['close'], 50).iloc[-1] if len(buffer) >= 50 else np.nan
    ema_30 = calculate_ema(df['close'], 30).iloc[-1] if len(buffer) >= 30 else np.nan
    ema_20 = calculate_ema(df['close'], 20).iloc[-1] if len(buffer) >= 20 else np.nan
    
    return {
        'ema_200': ema_200,
        'ema_50': ema_50,
        'ema_30': ema_30,
        'ema_20': ema_20
    }


def calculate_bollinger_bands_from_buffer(buffer: List[HistoricalCandle]) -> Dict[str, float]:
    """
    Calcula las Bollinger Bands desde un buffer de velas.
    
    Args:
        buffer: Lista de velas (debe tener al menos BB_PERIOD velas)
        
    Returns:
        Dict con upper, lower, middle
    """
    if len(buffer) < Config.CANDLE.BB_PERIOD:
        return {
            'upper': np.nan,
            'lower': np.nan,
            'middle': np.nan
        }
    
    # Crear Series con precios de cierre
    df = pd.DataFrame([{
        'close': c.close
    } for c in buffer])
    
    # Calcular Bollinger Bands
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
        return {
            'upper': np.nan,
            'lower': np.nan,
            'middle': np.nan
        }


# =============================================================================
# BACKTESTING ENGINE
# =============================================================================

class BacktestingEngine:
    """Motor de backtesting para generar dataset histórico."""
    
    def __init__(self, storage_service: StorageService):
        """
        Inicializa el motor de backtesting.
        
        Args:
            storage_service: Servicio de almacenamiento
        """
        self.storage_service = storage_service
        self.total_patterns_found = 0
        self.total_patterns_saved = 0
    
    async def run(self):
        """Ejecuta el proceso de backtesting completo para todos los instrumentos."""
        logger.info("=" * 80)
        logger.info("🚀 INICIANDO BACKTESTING HISTÓRICO MULTI-INSTRUMENTO")
        logger.info("=" * 80)
        logger.info(f"📅 Rango: {START_DATE.strftime('%Y-%m-%d')} a {END_DATE.strftime('%Y-%m-%d')} ({DAYS_TO_FETCH} días)")
        logger.info(f"📦 Estrategia: Peticiones de {DAYS_PER_REQUEST} días cada una")
        logger.info(f"⏭️  Velas a saltar: {SKIP_CANDLES:,}")
        logger.info(f"📊 Instrumentos a procesar: {len(Config.INSTRUMENTS)}")
        logger.info("=" * 80)
        
        # Procesar cada instrumento
        for instrument_key, instrument_config in Config.INSTRUMENTS.items():
            logger.info(f"\n{'=' * 80}")
            logger.info(f"📊 PROCESANDO: {instrument_config.exchange}:{instrument_config.symbol}")
            logger.info(f"⏱️  Timeframe: {instrument_config.timeframe} minuto(s)")
            logger.info(f"{'=' * 80}")
            
            patterns_found = 0
            patterns_saved = 0
            
            try:
                # Paso 1: Obtener velas históricas por chunks
                logger.info("\n📥 PASO 1: Obteniendo datos históricos de TradingView...")
                candles = await self._fetch_historical_data_in_chunks(
                    symbol=instrument_config.symbol,
                    exchange=instrument_config.exchange,
                    timeframe=instrument_config.timeframe
                )
                
                if not candles or len(candles) < SKIP_CANDLES + 100:
                    logger.warning(f"⚠️  Insuficientes velas para {instrument_config.symbol}. Recibidas: {len(candles) if candles else 0}")
                    continue
                
                logger.info(f"✅ Total obtenidas: {len(candles):,} velas históricas")
                logger.info(f"🔍 Velas a analizar: {len(candles) - SKIP_CANDLES:,}")
                
                # Paso 2: Procesar velas y detectar patrones
                logger.info("\n🔍 PASO 2: Procesando velas y detectando patrones...")
                patterns_found, patterns_saved = await self._process_candles(
                    candles=candles,
                    symbol=instrument_config.symbol,
                    exchange=instrument_config.exchange
                )
                
                # Resumen del instrumento
                logger.info(f"\n✅ {instrument_config.symbol} completado:")
                logger.info(f"   🎯 Patrones detectados: {patterns_found}")
                logger.info(f"   💾 Patrones guardados: {patterns_saved}")
                
                # Acumular totales
                self.total_patterns_found += patterns_found
                self.total_patterns_saved += patterns_saved
            
            except Exception as e:
                logger.error(f"❌ Error procesando {instrument_config.symbol}: {e}", exc_info=True)
                continue
        
        # Resumen final
        logger.info("\n" + "=" * 80)
        logger.info("✅ BACKTESTING MULTI-INSTRUMENTO COMPLETADO")
        logger.info("=" * 80)
        logger.info(f"📊 Instrumentos procesados: {len(Config.INSTRUMENTS)}")
        logger.info(f"🎯 Total patrones detectados: {self.total_patterns_found}")
        logger.info(f"💾 Total patrones guardados: {self.total_patterns_saved}")
        logger.info(f"📂 Dataset: data/trading_signals_dataset.jsonl")
        logger.info("=" * 80)
    
    
    async def _fetch_historical_data_in_chunks(
        self,
        symbol: str,
        exchange: str,
        timeframe: str
    ) -> List[HistoricalCandle]:
        """
        Obtiene velas históricas de TradingView dividiendo en chunks por fecha.
        
        Estrategia:
        1. Divide el rango total en chunks de DAYS_PER_REQUEST días
        2. Solicita cada chunk secuencialmente
        3. Espera REQUEST_DELAY segundos entre peticiones
        4. Combina y ordena todas las velas
        
        Args:
            symbol: Símbolo del instrumento (ej: "BTCUSDT", "EURUSD")
            exchange: Exchange (ej: "BINANCE", "OANDA")
            timeframe: Timeframe en minutos (ej: "1")
        
        Returns:
            Lista de velas históricas ordenadas por timestamp
        """
        all_candles = []
        
        # Calcular número de chunks necesarios
        num_chunks = (DAYS_TO_FETCH + DAYS_PER_REQUEST - 1) // DAYS_PER_REQUEST
        
        logger.info(f"📦 Dividiendo {DAYS_TO_FETCH} días en {num_chunks} peticiones de ~{DAYS_PER_REQUEST} días")
        
        service = TradingViewService()
        
        # Iterar sobre cada chunk
        current_end = END_DATE
        for chunk_num in range(num_chunks):
            # Calcular rango de este chunk
            chunk_start = max(START_DATE, current_end - timedelta(days=DAYS_PER_REQUEST))
            chunk_days = (current_end - chunk_start).days
            
            # Calcular velas aproximadas (1 minuto = 1440 velas/día)
            estimated_candles = chunk_days * 1440
            
            logger.info(f"\n📥 Chunk {chunk_num + 1}/{num_chunks}: {chunk_start.strftime('%Y-%m-%d')} a {current_end.strftime('%Y-%m-%d')} (~{chunk_days} días, ~{estimated_candles:,} velas)")
            
            try:
                # Solicitar velas (TradingView devuelve las más recientes)
                candles = await service.fetch_historical_candles(
                    symbol=symbol,
                    exchange=exchange,
                    timeframe=timeframe,
                    num_candles=estimated_candles + 500  # Buffer extra
                )
                
                if candles:
                    # Filtrar solo velas dentro del rango de fechas del chunk
                    chunk_start_ts = int(chunk_start.timestamp())
                    chunk_end_ts = int(current_end.timestamp())
                    
                    filtered_candles = [
                        c for c in candles 
                        if chunk_start_ts <= c.timestamp <= chunk_end_ts
                    ]
                    
                    logger.info(f"✅ Recibidas: {len(candles):,} velas | Filtradas al rango: {len(filtered_candles):,} velas")
                    all_candles.extend(filtered_candles)
                else:
                    logger.warning(f"⚠️  No se recibieron velas para este chunk")
                
                # Esperar entre peticiones (evitar rate limiting)
                if chunk_num < num_chunks - 1:
                    logger.info(f"⏳ Esperando {REQUEST_DELAY}s antes de la siguiente petición...")
                    await asyncio.sleep(REQUEST_DELAY)
                
                # Mover al siguiente chunk
                current_end = chunk_start
            
            except Exception as e:
                logger.error(f"❌ Error en chunk {chunk_num + 1}: {e}")
                continue
        
        # Eliminar duplicados por timestamp y ordenar
        if all_candles:
            # Usar dict para eliminar duplicados (mantiene el último)
            unique_candles = {c.timestamp: c for c in all_candles}
            sorted_candles = sorted(unique_candles.values(), key=lambda c: c.timestamp)
            
            logger.info(f"\n📊 Resumen de obtención:")
            logger.info(f"   Total recibidas: {len(all_candles):,} velas")
            logger.info(f"   Duplicados eliminados: {len(all_candles) - len(sorted_candles):,}")
            logger.info(f"   Total únicas: {len(sorted_candles):,} velas")
            
            return sorted_candles
        
        return []
    
    async def _process_candles(
        self,
        candles: List[HistoricalCandle],
        symbol: str,
        exchange: str
    ) -> tuple:
        """
        Procesa las velas, detecta patrones y guarda en dataset.
        
        Args:
            candles: Lista de velas históricas
            symbol: Símbolo del instrumento
            exchange: Exchange
            
        Returns:
            tuple: (patterns_found, patterns_saved)
        """
        patterns_found = 0
        patterns_saved = 0
        total_to_analyze = len(candles) - SKIP_CANDLES
        
        # Iterar desde la vela SKIP_CANDLES hasta la penúltima
        for i in range(SKIP_CANDLES, len(candles) - 1):
            current_candle = candles[i]
            next_candle = candles[i + 1]  # Outcome candle
            
            # Progreso cada 1000 velas
            if (i - SKIP_CANDLES) % 1000 == 0:
                progress = ((i - SKIP_CANDLES) / total_to_analyze) * 100
                logger.info(f"📊 Progreso: {progress:.1f}% ({i - SKIP_CANDLES:,}/{total_to_analyze:,} velas procesadas)")
            
            # Detectar patrón
            pattern_result = detect_pattern(current_candle)
            
            if pattern_result:
                pattern, confidence = pattern_result
                patterns_found += 1
                
                # Obtener buffer de 1000 velas anteriores
                buffer_start = max(0, i - BUFFER_SIZE)
                buffer = candles[buffer_start:i]
                
                # Calcular EMAs
                emas = calculate_emas_from_buffer(buffer)
                
                # Si no hay suficientes datos para EMAs, saltar
                if np.isnan(emas['ema_200']):
                    continue
                
                # Calcular Bollinger Bands
                bollinger_bands = calculate_bollinger_bands_from_buffer(buffer)
                
                # Detectar zona de agotamiento
                if not np.isnan(bollinger_bands['upper']) and not np.isnan(bollinger_bands['lower']):
                    exhaustion_type = detect_exhaustion(
                        current_candle.high,
                        current_candle.low,
                        current_candle.close,
                        bollinger_bands['upper'],
                        bollinger_bands['lower']
                    )
                else:
                    exhaustion_type = "NONE"
                
                # Calcular trend analysis
                trend = analyze_trend(
                    close=current_candle.close,
                    emas=emas
                )
                
                # Determinar dirección de la vela outcome
                outcome_direction = get_candle_direction(next_candle.open, next_candle.close)
                
                # Determinar dirección esperada del patrón
                expected_direction = self._get_expected_direction(pattern)
                
                # Calcular si fue acierto
                outcome_result = outcome_direction == expected_direction
                
                # Calcular alineación de EMAs en formato string
                ema_alignment = self._get_ema_alignment(emas)
                
                # Calcular orden explícito de EMAs con precio
                ema_order = self._get_ema_order(current_candle.close, emas)
                
                # Preparar registro para dataset con estructura optimizada
                record = {
                    "timestamp": current_candle.timestamp,
                    "source": exchange,
                    "symbol": symbol,
                    "pattern_candle": {
                        "timestamp": current_candle.timestamp,
                        "open": current_candle.open,
                        "high": current_candle.high,
                        "low": current_candle.low,
                        "close": current_candle.close,
                        "volume": current_candle.volume,
                        "pattern": pattern,
                        "confidence": confidence
                    },
                    "emas": {
                        "ema_200": emas['ema_200'],
                        "ema_50": emas['ema_50'],
                        "ema_30": emas['ema_30'],
                        "ema_20": emas['ema_20'],
                        "alignment": ema_alignment,
                        "ema_order": ema_order,
                        "trend_score": trend.score
                    },
                    "bollinger": {
                        "upper": bollinger_bands['upper'],
                        "lower": bollinger_bands['lower'],
                        "middle": bollinger_bands['middle'],
                        "std_dev": Config.CANDLE.BB_STD_DEV,
                        "exhaustion_type": exhaustion_type,
                        "signal_strength": self._calculate_signal_strength(pattern, exhaustion_type, trend.status),
                        "is_counter_trend": self._is_counter_trend(pattern, trend.status)
                    },
                    "outcome_candle": {
                        "timestamp": next_candle.timestamp,
                        "open": next_candle.open,
                        "high": next_candle.high,
                        "low": next_candle.low,
                        "close": next_candle.close,
                        "volume": next_candle.volume,
                        "direction": outcome_direction
                    },
                    "outcome": {
                        "expected_direction": expected_direction,
                        "actual_direction": outcome_direction,
                        "success": outcome_result
                    },
                    "metadata": {
                        "algo_version": Config.ALGO_VERSION,
                        "created_at": datetime.utcnow().isoformat() + "Z"
                    }
                }
                
                # Guardar en dataset
                try:
                    await self.storage_service.save_signal_outcome(record)
                    patterns_saved += 1
                    
                    result_text = "WIN" if outcome_result else "LOSS"
                    logger.debug(
                        f"💾 Patrón guardado: {pattern} | Confianza: {confidence:.2f} | "
                        f"Score: {trend.score} | Outcome: {result_text}"
                    )
                
                except Exception as e:
                    logger.error(f"❌ Error guardando patrón: {e}")
        
        return patterns_found, patterns_saved
    
    def _get_expected_direction(self, pattern: str) -> str:
        """
        Determina la dirección esperada según el patrón.
        
        Args:
            pattern: Nombre del patrón
            
        Returns:
            "VERDE" o "ROJA"
        """
        if pattern in ["SHOOTING_STAR", "HANGING_MAN"]:
            return "ROJA"  # Patrones bajistas
        elif pattern in ["INVERTED_HAMMER", "HAMMER"]:
            return "VERDE"  # Patrones alcistas
        else:
            return "DOJI"  # Fallback
    
    def _calculate_signal_strength(self, pattern: str, exhaustion_type: str, trend_status: str) -> str:
        """
        Calcula la fuerza de la señal basándose en Bollinger Bands y tendencia.
        
        Args:
            pattern: Nombre del patrón
            exhaustion_type: Tipo de agotamiento (PEAK, BOTTOM, NONE)
            trend_status: Estado de la tendencia
            
        Returns:
            "HIGH", "MEDIUM", o "LOW"
        """
        is_bullish_pattern = pattern in ["HAMMER", "INVERTED_HAMMER"]
        is_bearish_pattern = pattern in ["SHOOTING_STAR", "HANGING_MAN"]
        is_bullish_trend = "BULLISH" in trend_status
        is_bearish_trend = "BEARISH" in trend_status
        
        # HIGH: Patrón en zona de agotamiento alineado con tendencia
        if exhaustion_type == "PEAK" and is_bearish_pattern and is_bullish_trend:
            return "HIGH"
        elif exhaustion_type == "BOTTOM" and is_bullish_pattern and is_bearish_trend:
            return "HIGH"
        
        # MEDIUM: Patrón secundario en zona de agotamiento
        elif exhaustion_type == "PEAK" and is_bullish_pattern:
            return "MEDIUM"
        elif exhaustion_type == "BOTTOM" and is_bearish_pattern:
            return "MEDIUM"
        
        # LOW: Zona neutra o patrón contratrend
        else:
            return "LOW"
    
    def _is_counter_trend(self, pattern: str, trend_status: str) -> bool:
        """
        Determina si el patrón es contratrend.
        
        Args:
            pattern: Nombre del patrón
            trend_status: Estado de la tendencia
            
        Returns:
            True si es contratrend
        """
        is_bullish_pattern = pattern in ["HAMMER", "INVERTED_HAMMER"]
        is_bearish_pattern = pattern in ["SHOOTING_STAR", "HANGING_MAN"]
        is_bullish_trend = "BULLISH" in trend_status
        is_bearish_trend = "BEARISH" in trend_status
        
        # Contratrend: Patrón alcista en tendencia alcista o bajista en tendencia bajista
        return (is_bullish_pattern and is_bullish_trend) or (is_bearish_pattern and is_bearish_trend)
    
    def _get_ema_alignment(self, emas: Dict[str, float]) -> str:
        """
        Determina la alineación de las EMAs en formato string.
        
        Args:
            emas: Diccionario con valores de EMAs
            
        Returns:
            String describiendo la alineación (ej: "BULLISH_ALIGNED", "BEARISH_ALIGNED", "MIXED")
        """
        ema_20 = emas.get('ema_20', np.nan)
        ema_30 = emas.get('ema_30', np.nan)
        ema_50 = emas.get('ema_50', np.nan)
        ema_200 = emas.get('ema_200', np.nan)
        
        # Verificar que todas las EMAs tengan valores válidos
        if any(np.isnan([ema_20, ema_30, ema_50, ema_200])):
            return "INCOMPLETE"
        
        # Alineación alcista perfecta: 20 > 30 > 50 > 200
        if ema_20 > ema_30 > ema_50 > ema_200:
            return "BULLISH_ALIGNED"
        
        # Alineación bajista perfecta: 20 < 30 < 50 < 200
        elif ema_20 < ema_30 < ema_50 < ema_200:
            return "BEARISH_ALIGNED"
        
        # Alineación parcial alcista: 20 > 50 > 200
        elif ema_20 > ema_50 > ema_200:
            return "BULLISH_PARTIAL"
        
        # Alineación parcial bajista: 20 < 50 < 200
        elif ema_20 < ema_50 < ema_200:
            return "BEARISH_PARTIAL"
        
        # Sin alineación clara
        else:
            return "MIXED"
    
    def _get_ema_order(self, price: float, emas: Dict[str, float]) -> str:
        """
        Calcula el orden explícito de Precio y EMAs en formato string.
        
        Args:
            price: Precio actual de cierre
            emas: Diccionario con valores de EMAs
            
        Returns:
            String con el orden explícito (ej: "P>20>30>50>200", "200>50>P>30>20")
        """
        ema_20 = emas.get('ema_20', np.nan)
        ema_30 = emas.get('ema_30', np.nan)
        ema_50 = emas.get('ema_50', np.nan)
        ema_200 = emas.get('ema_200', np.nan)
        
        # Verificar que todas las EMAs tengan valores válidos
        if any(np.isnan([ema_20, ema_30, ema_50, ema_200])):
            return "INCOMPLETE"
        
        # Crear lista de tuplas (nombre, valor)
        items = [
            ('P', price),
            ('20', ema_20),
            ('30', ema_30),
            ('50', ema_50),
            ('200', ema_200)
        ]
        
        # Ordenar por valor descendente (mayor a menor)
        items_sorted = sorted(items, key=lambda x: x[1], reverse=True)
        
        # Construir string con el orden
        order_string = '>'.join([item[0] for item in items_sorted])
        
        return order_string


# =============================================================================
# ENTRY POINT
# =============================================================================

async def main():
    """Función principal."""
    try:
        # Inicializar Storage Service
        storage_service = StorageService(
            data_dir="data",
            filename="trading_signals_dataset.jsonl"
        )
        
        # Crear motor de backtesting
        engine = BacktestingEngine(storage_service)
        
        # Ejecutar backtesting
        await engine.run()
        
        # Cerrar storage
        await storage_service.close()
    
    except KeyboardInterrupt:
        logger.info("\n⚠️  Backtesting interrumpido por el usuario")
    
    except Exception as e:
        logger.critical(f"❌ Error fatal en backtesting: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Configuración de políticas de asyncio para Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
