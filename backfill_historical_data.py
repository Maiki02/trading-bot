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
from src.logic.analysis_service import analyze_trend, calculate_ema
from src.utils.logger import get_logger


logger = get_logger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Instrumento a analizar
SYMBOL = "BTCUSDT"
EXCHANGE = "BINANCE"
TIMEFRAME = "1"  # 1 minuto

# Cantidad de velas
TOTAL_CANDLES = 35000  # Total a descargar
SKIP_CANDLES = 1000    # Velas a saltar (para inicializar EMAs)
BUFFER_SIZE = 1000     # Tamaño del buffer para cálculo de EMAs


# =============================================================================
# PATTERN DETECTION
# =============================================================================

def detect_pattern(candle: HistoricalCandle) -> Optional[str]:
    """
    Detecta si una vela tiene algún patrón válido.
    
    Args:
        candle: Vela a analizar
        
    Returns:
        str: Nombre del patrón ("SHOOTING_STAR", "HANGING_MAN", etc.) o None
    """
    # Convertir a diccionario para compatibilidad con funciones de detección
    candle_dict = {
        'open': candle.open,
        'high': candle.high,
        'low': candle.low,
        'close': candle.close
    }
    
    # Intentar cada patrón
    if is_shooting_star(candle_dict):
        return "SHOOTING_STAR"
    elif is_hanging_man(candle_dict):
        return "HANGING_MAN"
    elif is_inverted_hammer(candle_dict):
        return "INVERTED_HAMMER"
    elif is_hammer(candle_dict):
        return "HAMMER"
    
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
        self.patterns_found = 0
        self.patterns_saved = 0
    
    async def run(self):
        """Ejecuta el proceso de backtesting completo."""
        logger.info("=" * 80)
        logger.info("🚀 INICIANDO BACKTESTING HISTÓRICO")
        logger.info("=" * 80)
        logger.info(f"📊 Instrumento: {EXCHANGE}:{SYMBOL}")
        logger.info(f"⏱️  Timeframe: {TIMEFRAME} minuto(s)")
        logger.info(f"📈 Total de velas: {TOTAL_CANDLES:,}")
        logger.info(f"⏭️  Velas a saltar: {SKIP_CANDLES:,}")
        logger.info(f"🔍 Velas a analizar: {TOTAL_CANDLES - SKIP_CANDLES:,}")
        logger.info("=" * 80)
        
        # Paso 1: Obtener velas históricas
        logger.info("\n📥 PASO 1: Obteniendo datos históricos de TradingView...")
        candles = await self._fetch_historical_data()
        
        if not candles or len(candles) < SKIP_CANDLES + 100:
            logger.error(f"❌ No se obtuvieron suficientes velas. Recibidas: {len(candles)}")
            return
        
        logger.info(f"✅ Obtenidas {len(candles):,} velas históricas")
        
        # Paso 2: Procesar velas y detectar patrones
        logger.info("\n🔍 PASO 2: Procesando velas y detectando patrones...")
        await self._process_candles(candles)
        
        # Resumen final
        logger.info("\n" + "=" * 80)
        logger.info("✅ BACKTESTING COMPLETADO")
        logger.info("=" * 80)
        logger.info(f"🎯 Patrones detectados: {self.patterns_found}")
        logger.info(f"💾 Patrones guardados: {self.patterns_saved}")
        logger.info(f"📊 Dataset: data/trading_signals_dataset.jsonl")
        logger.info("=" * 80)
    
    async def _fetch_historical_data(self) -> List[HistoricalCandle]:
        """
        Obtiene velas históricas de TradingView.
        
        Returns:
            Lista de velas históricas
        """
        service = TradingViewService()
        
        try:
            candles = await service.fetch_historical_candles(
                symbol=SYMBOL,
                exchange=EXCHANGE,
                timeframe=TIMEFRAME,
                num_candles=TOTAL_CANDLES
            )
            
            # Ordenar por timestamp (ascendente)
            candles.sort(key=lambda c: c.timestamp)
            
            return candles
        
        except Exception as e:
            logger.error(f"❌ Error obteniendo datos históricos: {e}", exc_info=True)
            return []
    
    async def _process_candles(self, candles: List[HistoricalCandle]):
        """
        Procesa las velas, detecta patrones y guarda en dataset.
        
        Args:
            candles: Lista de velas históricas
        """
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
            pattern = detect_pattern(current_candle)
            
            if pattern:
                self.patterns_found += 1
                
                # Obtener buffer de 1000 velas anteriores
                buffer_start = max(0, i - BUFFER_SIZE)
                buffer = candles[buffer_start:i]
                
                # Calcular EMAs
                emas = calculate_emas_from_buffer(buffer)
                
                # Si no hay suficientes datos para EMAs, saltar
                if np.isnan(emas['ema_200']):
                    continue
                
                # Calcular trend analysis
                trend = analyze_trend(
                    close=current_candle.close,
                    emas=emas
                )
                
                # Determinar dirección de la vela outcome
                outcome_direction = get_candle_direction(next_candle.__dict__)
                
                # Determinar dirección esperada del patrón
                expected_direction = self._get_expected_direction(pattern)
                
                # Calcular si fue acierto
                outcome_result = "WIN" if outcome_direction == expected_direction else "LOSS"
                
                # Calcular PnL (simplificado: diferencia close - open de outcome)
                pnl = abs(next_candle.close - next_candle.open)
                if outcome_result == "LOSS":
                    pnl = -pnl
                
                # Preparar registro para dataset
                record = {
                    "timestamp": current_candle.timestamp,
                    "pattern": pattern,
                    "trend": trend.status,
                    "trend_score": trend.score,
                    "is_trend_aligned": trend.is_aligned,
                    "outcome_timestamp": next_candle.timestamp,
                    "outcome_direction": outcome_direction,
                    "expected_direction": expected_direction,
                    "outcome_result": outcome_result,
                    "pnl": pnl,
                    "raw_data": {
                        "ema_200": emas['ema_200'],
                        "ema_50": emas['ema_50'],
                        "ema_30": emas['ema_30'],
                        "ema_20": emas['ema_20'],
                        "close": current_candle.close,
                        "open": current_candle.open,
                        "algo_version": Config.ALGO_VERSION
                    }
                }
                
                # Guardar en dataset
                try:
                    await self.storage_service.save_signal_outcome(record)
                    self.patterns_saved += 1
                    
                    logger.debug(
                        f"💾 Patrón guardado: {pattern} | Score: {trend.score} | "
                        f"Outcome: {outcome_result} | PnL: {pnl:.2f}"
                    )
                
                except Exception as e:
                    logger.error(f"❌ Error guardando patrón: {e}")
    
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
