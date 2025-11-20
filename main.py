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
import signal
import sys
from typing import Optional

from config import Config
from src.services import ConnectionService, TelegramService
from src.logic import AnalysisService
from src.utils.logger import get_logger, log_startup_banner, log_shutdown, log_critical_auth_failure


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
        self.connection_service: Optional[ConnectionService] = None
        self.analysis_service: Optional[AnalysisService] = None
        self.telegram_service: Optional[TelegramService] = None
        
        self.is_running: bool = False
        self.shutdown_event: asyncio.Event = asyncio.Event()
    
    async def initialize(self) -> None:
        """
        Inicializa todos los servicios con inyección de dependencias.
        """
        logger.info("🔧 Initializing services...")
        
        # 1. Telegram Service (no tiene dependencias)
        self.telegram_service = TelegramService()
        await self.telegram_service.start()
        
        # 2. Analysis Service (depende de Telegram para notificaciones)
        self.analysis_service = AnalysisService(
            on_pattern_detected=self.telegram_service.handle_pattern_signal
        )
        
        # 3. Connection Service (recibe AnalysisService completo, NO callback)
        self.connection_service = ConnectionService(
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
        
        logger.info("🚀 Trading Bot started. Monitoring EUR/USD for Shooting Star patterns...")
        logger.info(f"📊 Primary Source: OANDA | Secondary Source: FX")
        logger.info(f"⏱️  Dual-Source Window: {Config.DUAL_SOURCE_WINDOW}s")
        logger.info(f"📈 EMA Period: {Config.EMA_PERIOD}")
        
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
        
        log_shutdown(logger)
        self.shutdown_event.set()
    
    def _handle_auth_failure(self) -> None:
        """
        Callback invocado cuando falla la autenticación con TradingView.
        """
        log_critical_auth_failure(logger)
        logger.critical("🚨 Bot cannot continue. Please update TV_SESSION_ID and restart.")
        
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


# =============================================================================
# ENTRY POINT
# =============================================================================

async def main() -> None:
    """
    Función principal asíncrona.
    """
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
