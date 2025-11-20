"""
Centralized Logging Module - Trading Bot MVP v0.0.1
====================================================
Sistema de logging centralizado con formato estandarizado,
niveles de severidad y soporte para múltiples outputs.

NO usar print() en ningún módulo. Importar logger desde aquí.

Author: TradingView Pattern Monitor Team
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime


# =============================================================================
# CONFIGURACIÓN DE COLORES PARA CONSOLA (ANSI Codes)
# =============================================================================

class LogColors:
    """Códigos ANSI para colorear logs en terminal."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    # Niveles
    DEBUG = "\033[36m"      # Cyan
    INFO = "\033[32m"       # Green
    WARNING = "\033[33m"    # Yellow
    ERROR = "\033[31m"      # Red
    CRITICAL = "\033[35m\033[1m"  # Magenta Bold


# =============================================================================
# FORMATEADOR PERSONALIZADO
# =============================================================================

class ColoredFormatter(logging.Formatter):
    """
    Formateador que añade colores a los logs en consola según el nivel.
    """
    
    FORMATS = {
        logging.DEBUG: f"{LogColors.DEBUG}%(levelname)-8s{LogColors.RESET} | %(asctime)s | %(name)s | %(message)s",
        logging.INFO: f"{LogColors.INFO}%(levelname)-8s{LogColors.RESET} | %(asctime)s | %(name)s | %(message)s",
        logging.WARNING: f"{LogColors.WARNING}%(levelname)-8s{LogColors.RESET} | %(asctime)s | %(name)s | %(message)s",
        logging.ERROR: f"{LogColors.ERROR}%(levelname)-8s{LogColors.RESET} | %(asctime)s | %(name)s | %(message)s",
        logging.CRITICAL: f"{LogColors.CRITICAL}%(levelname)-8s{LogColors.RESET} | %(asctime)s | %(name)s | %(message)s",
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Formatea el mensaje de log con colores según el nivel.
        
        Args:
            record: Registro de log
            
        Returns:
            str: Mensaje formateado
        """
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


class FileFormatter(logging.Formatter):
    """
    Formateador para archivos sin colores ANSI.
    """
    
    def __init__(self):
        super().__init__(
            fmt="%(levelname)-8s | %(asctime)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )


# =============================================================================
# CONFIGURACIÓN DEL LOGGER
# =============================================================================

def setup_logger(
    name: str,
    level: str = "INFO",
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Configura y retorna un logger con formato estandarizado.
    
    Args:
        name: Nombre del módulo (ej: "connection_service")
        level: Nivel de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Ruta opcional del archivo de log
        
    Returns:
        logging.Logger: Logger configurado
        
    Example:
        >>> from src.utils.logger import setup_logger
        >>> logger = setup_logger(__name__)
        >>> logger.info("Sistema iniciado")
    """
    logger = logging.getLogger(name)
    
    # Evitar duplicar handlers si se llama múltiples veces
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    
    # Handler para consola con colores
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)
    
    # Handler para archivo (opcional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(FileFormatter())
        logger.addHandler(file_handler)
    
    return logger


# =============================================================================
# LOGGER POR DEFECTO (PARA IMPORTS RÁPIDOS)
# =============================================================================

def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger ya configurado o crea uno nuevo con la configuración por defecto.
    
    Args:
        name: Nombre del módulo
        
    Returns:
        logging.Logger: Logger configurado
        
    Example:
        >>> from src.utils.logger import get_logger
        >>> logger = get_logger(__name__)
    """
    # Importar aquí para evitar dependencia circular
    try:
        from config import Config
        return setup_logger(name, Config.LOG_LEVEL, Config.LOG_FILE)
    except ImportError:
        # Fallback si config.py no está disponible
        return setup_logger(name, "INFO", None)


# =============================================================================
# FUNCIONES DE UTILIDAD
# =============================================================================

def log_exception(logger: logging.Logger, message: str, exc: Exception) -> None:
    """
    Registra una excepción con contexto completo.
    
    Args:
        logger: Logger a utilizar
        message: Mensaje descriptivo del error
        exc: Excepción capturada
        
    Example:
        >>> try:
        ...     risky_operation()
        ... except Exception as e:
        ...     log_exception(logger, "Failed to connect", e)
    """
    logger.error(f"{message}: {type(exc).__name__}: {str(exc)}", exc_info=True)


def log_critical_auth_failure(logger: logging.Logger) -> None:
    """
    Registra un fallo crítico de autenticación con TradingView.
    
    Args:
        logger: Logger a utilizar
    """
    logger.critical(
        "⚠️  CRITICAL AUTH FAILURE: TradingView SessionID expired or invalid. "
        "Bot cannot continue. Please update TV_SESSION_ID in .env file."
    )


def log_startup_banner(logger: logging.Logger, version: str = "0.0.1") -> None:
    """
    Registra un banner de inicio con información del sistema.
    
    Args:
        logger: Logger a utilizar
        version: Versión del bot
    """
    banner = f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║  TradingView Pattern Monitor - MVP v{version}                   ║
    ║  Shooting Star Detection System                              ║
    ║  Real-Time Data Feed (No Login Required)                     ║
    ╚══════════════════════════════════════════════════════════════╝
    """
    for line in banner.strip().split('\n'):
        logger.info(line)


def log_shutdown(logger: logging.Logger) -> None:
    """
    Registra el apagado limpio del sistema.
    
    Args:
        logger: Logger a utilizar
    """
    logger.info("=" * 60)
    logger.info("Graceful shutdown completed. All services stopped.")
    logger.info("=" * 60)


# =============================================================================
# TESTING / DEBUGGING
# =============================================================================

if __name__ == "__main__":
    # Demostración del sistema de logging
    test_logger = setup_logger("test_module", "DEBUG")
    
    log_startup_banner(test_logger)
    
    test_logger.debug("This is a DEBUG message")
    test_logger.info("This is an INFO message")
    test_logger.warning("This is a WARNING message")
    test_logger.error("This is an ERROR message")
    test_logger.critical("This is a CRITICAL message")
    
    # Simulación de error
    try:
        raise ValueError("Example exception for testing")
    except Exception as e:
        log_exception(test_logger, "Test error simulation", e)
    
    log_critical_auth_failure(test_logger)
    log_shutdown(test_logger)
