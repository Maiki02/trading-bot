"""
Ejemplo de Uso - TradingView Service
=====================================
Este script demuestra cómo usar el TradingViewService para
obtener velas históricas de cualquier instrumento.

Author: TradingView Pattern Monitor Team
"""

import asyncio
import sys
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.tradingview_service import TradingViewService, get_historical_candles
from src.utils.logger import get_logger


logger = get_logger(__name__)


async def example_basic():
    """Ejemplo básico: Obtener 1000 velas de BTC/USDT."""
    logger.info("=" * 80)
    logger.info("📊 EJEMPLO 1: Obtener 1000 velas de BTC/USDT")
    logger.info("=" * 80)
    
    service = TradingViewService()
    candles = await service.fetch_historical_candles(
        symbol="BTCUSDT",
        exchange="BINANCE",
        timeframe="1",
        num_candles=1000
    )
    
    if candles:
        logger.info(f"✅ Obtenidas {len(candles)} velas")
        logger.info(f"📅 Primera vela: {candles[0].timestamp} - Close: {candles[0].close}")
        logger.info(f"📅 Última vela: {candles[-1].timestamp} - Close: {candles[-1].close}")
    else:
        logger.error("❌ No se obtuvieron velas")


async def example_multiple_instruments():
    """Ejemplo avanzado: Obtener velas de múltiples instrumentos."""
    logger.info("\n" + "=" * 80)
    logger.info("📊 EJEMPLO 2: Obtener velas de múltiples instrumentos")
    logger.info("=" * 80)
    
    instruments = [
        {"symbol": "BTCUSDT", "exchange": "BINANCE"},
        {"symbol": "EURUSD", "exchange": "OANDA"},
        {"symbol": "EURUSD", "exchange": "FX"},
    ]
    
    for instrument in instruments:
        logger.info(f"\n🔍 Obteniendo {instrument['exchange']}:{instrument['symbol']}...")
        
        candles = await get_historical_candles(
            symbol=instrument["symbol"],
            exchange=instrument["exchange"],
            timeframe="1",
            num_candles=500
        )
        
        if candles:
            logger.info(f"✅ Obtenidas {len(candles)} velas")
            
            # Calcular estadísticas básicas
            closes = [c.close for c in candles]
            avg_close = sum(closes) / len(closes)
            max_close = max(closes)
            min_close = min(closes)
            
            logger.info(f"📊 Precio promedio: {avg_close:.5f}")
            logger.info(f"📈 Precio máximo: {max_close:.5f}")
            logger.info(f"📉 Precio mínimo: {min_close:.5f}")
        else:
            logger.error(f"❌ No se obtuvieron velas de {instrument['exchange']}:{instrument['symbol']}")


async def example_helper_function():
    """Ejemplo con función helper: Uso simplificado."""
    logger.info("\n" + "=" * 80)
    logger.info("📊 EJEMPLO 3: Uso de función helper get_historical_candles()")
    logger.info("=" * 80)
    
    # Uso simplificado con función helper
    candles = await get_historical_candles(
        symbol="BTCUSDT",
        exchange="BINANCE",
        num_candles=100
    )
    
    if candles:
        logger.info(f"✅ Obtenidas {len(candles)} velas con 1 línea de código")
        
        # Mostrar las últimas 5 velas
        logger.info("\n📊 Últimas 5 velas:")
        for candle in candles[-5:]:
            logger.info(
                f"  Timestamp: {candle.timestamp} | "
                f"O: {candle.open:.2f} | H: {candle.high:.2f} | "
                f"L: {candle.low:.2f} | C: {candle.close:.2f}"
            )


async def main():
    """Ejecuta todos los ejemplos."""
    logger.info("🚀 Iniciando ejemplos de TradingView Service\n")
    
    try:
        # Ejemplo 1: Básico
        await example_basic()
        
        # Ejemplo 2: Múltiples instrumentos
        await example_multiple_instruments()
        
        # Ejemplo 3: Función helper
        await example_helper_function()
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ Todos los ejemplos completados exitosamente")
        logger.info("=" * 80)
    
    except KeyboardInterrupt:
        logger.info("\n⚠️  Ejemplos interrumpidos por el usuario")
    
    except Exception as e:
        logger.error(f"❌ Error en ejemplos: {e}", exc_info=True)


if __name__ == "__main__":
    # Configuración de políticas de asyncio para Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
