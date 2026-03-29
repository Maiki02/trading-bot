"""
TradingView Pattern Monitor - Main Entry Point
===============================================
MVP v0.0.1 - Shooting Star Detection System
Dual-Source Validation: OANDA + FX:EURUSD

Este es el punto de entrada principal del bot. Orquesta todos los servicios:
- Connection Service (WebSocket)
- Analysis Service (Pattern Detection)
- Telegram Service (Notifications)

Author: TradingView Pattern Monitor Team
"""

import asyncio
import logging
import signal
import sys
from typing import Optional

from config import Config
from src.services import TelegramService
from src.services.connection_service import get_market_data_service
from src.services.storage_service import StorageService
from src.logic import AnalysisService
from src.utils.logger import get_logger, log_startup_banner, log_shutdown, log_critical_auth_failure

# iqoptionapi is only needed for the IQOPTION provider — import conditionally
# to avoid conflicts with pyquotex (websocket-client version clash)
if Config.DATA_PROVIDER == "IQOPTION":
    try:
        import iqoptionapi.constants as _iqoption_constants
    except ImportError:
        _iqoption_constants = None  # type: ignore[assignment]
else:
    _iqoption_constants = None  # type: ignore[assignment]

logger = get_logger(__name__)


# =============================================================================
# ORCHESTRATOR
# =============================================================================

class TradingBot:
    """
    Orquestador principal del bot de trading.
    
    Responsabilidades:
    - Inicializar y coordinar todos los servicios
    - Gestionar el ciclo de vida de la aplicación
    - Implementar graceful shutdown
    """
    
    def __init__(self):
        """Inicializa el bot y sus servicios."""
        self.connection_service = None  # Will be created by factory
        self.analysis_service: Optional[AnalysisService] = None
        self.telegram_service: Optional[TelegramService] = None
        self.storage_service: Optional[StorageService] = None
        
        self.is_running: bool = False
        self.shutdown_event: asyncio.Event = asyncio.Event()
    
    async def initialize(self) -> None:
        """
        Inicializa todos los servicios con inyección de dependencias.
        """
        logger.info("🔧 Initializing services...")
        
        # Log de instrumentos objetivo
        if Config.DATA_PROVIDER == "IQOPTION":
            logger.info(
                f"🎯 Target Assets (Multi-Instrument): {', '.join(Config.TARGET_ASSETS)}"
            )
            logger.info(
                f"📊 Generate Historical Charts: {'Enabled' if Config.GENERATE_HISTORICAL_CHARTS else 'Disabled'}"
            )
        
        # 1. Storage Service (capa de persistencia - sin dependencias)
        self.storage_service = StorageService(
            data_dir="data",
            filename="trading_signals_dataset.jsonl"
        )
        
        # 2. Statistics Service (análisis de probabilidad - sin dependencias)
        from src.services.statistics_service import StatisticsService
        self.statistics_service = StatisticsService(
            data_path="data/trading_signals_dataset.jsonl"
        )
        
        # 3. Telegram Service (notificaciones - sin dependencias)
        self.telegram_service = TelegramService()
        await self.telegram_service.start()
        
        # 4. Analysis Service (depende de Telegram, Storage y Statistics)
        self.analysis_service = AnalysisService(
            on_pattern_detected=self.telegram_service.handle_pattern_signal,
            storage_service=self.storage_service,
            telegram_service=self.telegram_service,
            statistics_service=self.statistics_service
        )
        
        # 5. Connection Service (usa factory para crear el proveedor correcto)
        self.connection_service = get_market_data_service(
            analysis_service=self.analysis_service,
            on_auth_failure_callback=self._handle_auth_failure
        )
        
        logger.info("✅ All services initialized successfully")
    
    async def start(self) -> None:
        """
        Inicia el bot y todos sus servicios.
        """
        self.is_running = True
        
        # Banner de inicio
        log_startup_banner(logger, version="0.0.1")
        
        # Validar configuración
        try:
            Config.validate_all()
            logger.info("✅ Configuration validated")
        except ValueError as e:
            logger.critical(f"❌ Configuration error: {e}")
            sys.exit(1)
        
        # Inicializar servicios
        await self.initialize()
        
        # Registrar handlers de señales para graceful shutdown
        self._register_signal_handlers()
        
        logger.info("🚀 Trading Bot started. Monitoring for patterns...")
        
        if Config.DATA_PROVIDER == "IQOPTION":
            logger.info(
                f"📊 Monitoring {len(Config.TARGET_ASSETS)} instruments: "
                f"{', '.join(Config.TARGET_ASSETS)}"
            )
        
        # Iniciar Connection Service (blocking)
        try:
            await self.connection_service.start()
        except Exception as e:
            logger.error(f"❌ Connection Service crashed: {e}")
            raise
    
    async def stop(self) -> None:
        """
        Detiene el bot de forma limpia.
        """
        if not self.is_running:
            return
        
        logger.info("🛑 Initiating graceful shutdown...")
        self.is_running = False
        
        # Detener servicios en orden inverso
        if self.connection_service:
            await self.connection_service.stop()
        
        if self.telegram_service:
            await self.telegram_service.stop()
        
        if self.storage_service:
            await self.storage_service.close()
        
        log_shutdown(logger)
        self.shutdown_event.set()
    
    def _handle_auth_failure(self) -> None:
        """
        Callback invocado cuando falla la autenticacion con el proveedor activo.
        """
        log_critical_auth_failure(logger)
        if Config.DATA_PROVIDER == "TRADINGVIEW":
            logger.critical("🚨 Bot cannot continue. Please check TV_SESSION_ID and restart.")
        elif Config.DATA_PROVIDER == "QUOTEX":
            logger.critical("🚨 Bot cannot continue. Please check QUOTEX_EMAIL/QUOTEX_PASSWORD and restart.")
        elif Config.DATA_PROVIDER == "IQOPTION":
            logger.critical("🚨 Bot cannot continue. Please check IQ_OPTION_USER/IQ_OPTION_PASS and restart.")
        else:
            logger.critical("🚨 Bot cannot continue due to provider authentication failure.")
        
        # Detener el bot
        asyncio.create_task(self.stop())
    
    def _register_signal_handlers(self) -> None:
        """
        Registra handlers para señales de sistema (SIGINT, SIGTERM).
        """
        def handle_signal(sig):
            logger.info(f"⚠️  Received signal {sig}. Initiating shutdown...")
            asyncio.create_task(self.stop())
        
        try:
            loop = asyncio.get_running_loop()
            
            # SIGINT (Ctrl+C)
            loop.add_signal_handler(signal.SIGINT, lambda: handle_signal("SIGINT"))
            
            # SIGTERM (kill)
            loop.add_signal_handler(signal.SIGTERM, lambda: handle_signal("SIGTERM"))
        
        except NotImplementedError:
            # Windows no soporta add_signal_handler
            # Se manejará con KeyboardInterrupt en el try-except
            pass



def inject_custom_actives():
    """
    Inyecta los activos personalizados definidos en Config dentro 
    de las constantes de la librería iqoptionapi.
    Solo se ejecuta cuando DATA_PROVIDER=IQOPTION.
    """
    if Config.DATA_PROVIDER != "IQOPTION":
        return

    if _iqoption_constants is None:
        return

    if not Config.CUSTOM_ACTIVES:
        return

    logger = logging.getLogger(__name__)
    logger.info(f"💉 Inyectando {len(Config.CUSTOM_ACTIVES)} activos personalizados en la librería...")

    count = 0
    for item in Config.CUSTOM_ACTIVES:
        key = item.get("key")
        active_id = item.get("id")

        if key and active_id:
            # ACÁ OCURRE LA MAGIA: Modificamos la librería en memoria
            _iqoption_constants.ACTIVES[key] = active_id
            logger.debug(f"   + Activo inyectado: {key} -> {active_id}")
            count += 1
        else:
            logger.warning(f"⚠️ Formato inválido en activo personalizado: {item}")

    logger.info(f"✅ Se agregaron {count} nuevos activos a IQ Option API.")

# =============================================================================
# ENTRY POINT
# =============================================================================

async def main() -> None:
    """
    Función principal asíncrona.
    """
    # 1. EJECUTAR LA INYECCIÓN ANTES DE CUALQUIER CONEXIÓN
    inject_custom_actives()

    # 2. INICIAR EL BOT
    bot = TradingBot()
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("⚠️  Keyboard interrupt received")
    except Exception as e:
        logger.critical(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await bot.stop()


if __name__ == "__main__":
    """
    Punto de entrada del programa.
    """
    # Configuración de políticas de asyncio para Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"❌ Fatal error in main: {e}", exc_info=True)
        sys.exit(1)
