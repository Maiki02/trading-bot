"""
Configuration Module - Trading Bot MVP v0.0.2
==============================================
Gestiona la carga de variables de entorno, configuración de instrumentos,
headers HTTP Anti-WAF y validación de parámetros críticos.

Author: TradingView Pattern Monitor Team
"""

import os
import random
from typing import Dict, List, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()


# =============================================================================
# DATA CLASSES PARA CONFIGURACIÓN ESTRUCTURADA
# =============================================================================

@dataclass(frozen=True)
class CandleConfig:
    """
    Configuración de umbrales para detección de patrones de velas japonesas.
    
    Estos valores son constantes matemáticas optimizadas para la identificación
    de patrones en temporalidad de 1 minuto.
    """
    # Umbrales generales
    BODY_RATIO_MIN: float = 0.30  # Cuerpo mínimo como % del rango total
    SMALL_BODY_RATIO: float = 0.30  # Cuerpo pequeño como % del rango (para martillos)
    
    # Umbrales de mechas
    UPPER_WICK_RATIO_MIN: float = 0.60  # Mecha superior mínima (Shooting Star)
    LOWER_WICK_RATIO_MIN: float = 0.60  # Mecha inferior mínima (Hammer)
    WICK_TO_BODY_RATIO: float = 2.0  # Mecha debe ser >= 2x el cuerpo
    
    # Umbrales de mechas opuestas (deben ser pequeñas)
    OPPOSITE_WICK_MAX: float = 0.15  # Mecha opuesta máxima permitida
    
    # Confianza base para patrones válidos
    BASE_CONFIDENCE: float = 0.70  # Confianza inicial (70%)
    BONUS_CONFIDENCE_PER_CONDITION: float = 0.10  # +10% por cada condición adicional cumplida
    
    # Bollinger Bands para detección de agotamiento de tendencia
    BB_PERIOD: int = 20  # Periodo de la media móvil para Bollinger Bands
    BB_STD_DEV: float = 2.0  # Desviación estándar (2.0 para asegurar agotamiento real)


@dataclass(frozen=True)
class InstrumentConfig:
    """Configuración de un instrumento de trading."""
    symbol: str  # Ej: "EURUSD"
    exchange: str  # Ej: "OANDA", "FX"
    timeframe: str  # Ej: "1" para 1 minuto
    full_symbol: str  # Ej: "OANDA:EURUSD"
    chart_lookback: int = 30  # Número de velas hacia atrás para el gráfico
    
    @property
    def chart_session_id(self) -> str:
        """Genera un ID único para la sesión del gráfico."""
        return f"cs_{self.exchange.lower()}_{self.symbol.lower()}"


@dataclass(frozen=True)
class TelegramConfig:
    """Configuración del servicio de notificaciones Telegram."""
    api_url: str
    api_key: str
    subscription: str
    outcome_subscription: str  # Subscription para notificaciones de resultados
    send_charts: bool  # Enviar gráficos en Base64 (aumenta costos API Gateway ~10x)
    enable_notifications: bool  # Habilitar/deshabilitar envío de notificaciones
    save_notifications_locally: bool  # Guardar notificaciones localmente en PNG y JSON
    
    def validate(self) -> None:
        """Valida que todos los parámetros estén configurados."""
        # Solo validar credenciales si las notificaciones están habilitadas
        if self.enable_notifications and (not self.api_url or not self.api_key or not self.subscription):
            raise ValueError(
                "Telegram configuration incomplete. Check TELEGRAM_API_URL, "
                "TELEGRAM_API_KEY, and TELEGRAM_SUBSCRIPTION in .env"
            )


@dataclass(frozen=True)
class TradingViewConfig:
    """Configuración de la conexión a TradingView."""
    session_id: str
    ws_url: str
    origin: str
    snapshot_candles: int
    
    def validate(self) -> None:
        """Valida que los parámetros críticos estén configurados."""
        # NOTA: SessionID NO ES CRÍTICO
        # El sistema usa feeds públicos de TradingView sin autenticación.
        # Los headers Anti-WAF (User-Agent, Origin) son suficientes para bypass.
        # Si en el futuro se requiere autenticación, descomentar:
        #
        # if not self.session_id or self.session_id == "your_session_id_here":
        #     raise ValueError(
        #         "CRITICAL: TV_SESSION_ID not configured. "
        #         "Extract sessionid cookie from TradingView (F12 > Application > Cookies)"
        #     )
        pass


# =============================================================================
# USER-AGENT ROTATION (ANTI-WAF)
# =============================================================================

USER_AGENTS: List[str] = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def get_random_user_agent() -> str:
    """
    Retorna un User-Agent aleatorio de la lista para evitar detección de bots.
    
    Returns:
        str: User-Agent string válido
    """
    return random.choice(USER_AGENTS)


# =============================================================================
# CONFIGURACIÓN PRINCIPAL
# =============================================================================

class Config:
    """Clase Singleton para acceso global a la configuración."""
    
    # Versión del algoritmo de análisis (para tracking en raw_data)
    ALGO_VERSION: str = "v4.0"
    
    # Payout de opciones binarias (ganancia neta si aciertas, en decimal)
    # Ejemplo: 0.86 = 86% de ganancia sobre la inversión
    BINARY_PAYOUT: float = 0.86
    
    # Configuración de patrones de velas
    CANDLE = CandleConfig()
    
    # TradingView Authentication & WebSocket
    TRADINGVIEW = TradingViewConfig(
        session_id=os.getenv("TV_SESSION_ID", ""),
        ws_url=os.getenv("TV_WS_URL", "wss://data.tradingview.com/socket.io/websocket"),
        origin=os.getenv("TV_WS_ORIGIN", "https://data.tradingview.com"),
        snapshot_candles=int(os.getenv("SNAPSHOT_CANDLES", "1000"))
    )
    
    # Telegram Notifications
    TELEGRAM = TelegramConfig(
        api_url=os.getenv("TELEGRAM_API_URL", ""),
        api_key=os.getenv("TELEGRAM_API_KEY", ""),
        subscription=os.getenv("TELEGRAM_SUBSCRIPTION", "trading_signals"),
        outcome_subscription=os.getenv("TELEGRAM_OUTCOME_SUBSCRIPTION", "trading_signals"),
        send_charts=os.getenv("SEND_CHARTS", "true").lower() == "true",
        enable_notifications=os.getenv("ENABLE_NOTIFICATIONS", "true").lower() == "true",
        save_notifications_locally=os.getenv("SAVE_NOTIFICATIONS_LOCALLY", "false").lower() == "true"
    )
    
    # Trading Parameters - Mean Reversion Strategy
    EMA_FAST_PERIOD: int = int(os.getenv("EMA_FAST_PERIOD", "7"))  # EMA rápida para detección de agotamiento
    EMA_PERIOD: int = int(os.getenv("EMA_PERIOD", "200"))  # Mantener para visualización
    DUAL_SOURCE_WINDOW: float = float(os.getenv("DUAL_SOURCE_WINDOW", "2.0"))
    CHART_LOOKBACK: int = int(os.getenv("CHART_LOOKBACK", "30"))
    USE_TREND_FILTER: bool = os.getenv("USE_TREND_FILTER", "false").lower() == "true"
    
    # Reconnection Strategy
    RECONNECT_INITIAL_TIMEOUT: int = int(os.getenv("RECONNECT_INITIAL_TIMEOUT", "5"))
    RECONNECT_MAX_TIMEOUT: int = int(os.getenv("RECONNECT_MAX_TIMEOUT", "300"))
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_FILE: Optional[str] = os.getenv("LOG_FILE") or None
    
    # Instruments Configuration (MVP: EUR/USD only)
    INSTRUMENTS: Dict[str, InstrumentConfig] = {

        # CRIPTO
    # "btc": InstrumentConfig(symbol="BTCUSDT", exchange="BINANCE", timeframe="1", full_symbol="BINANCE:BTCUSDT"),
    # "eth": InstrumentConfig(symbol="ETHUSDT", exchange="BINANCE", timeframe="1", full_symbol="BINANCE:ETHUSDT"),
    # "sol": InstrumentConfig(symbol="SOLUSDT", exchange="BINANCE", timeframe="1", full_symbol="BINANCE:SOLUSDT"),

    # FOREX (Ojo: El mercado cierra fines de semana)
    # "eurusd": InstrumentConfig(symbol="EURUSD", exchange="OANDA", timeframe="1", full_symbol="OANDA:EURUSD"),
    # "gbpusd": InstrumentConfig(symbol="GBPUSD", exchange="OANDA", timeframe="1", full_symbol="OANDA:GBPUSD"),
    # "usdjpy": InstrumentConfig(symbol="USDJPY", exchange="OANDA", timeframe="1", full_symbol="OANDA:USDJPY"),
    # "usdchf": InstrumentConfig(symbol="USDCHF", exchange="OANDA", timeframe="1", full_symbol="OANDA:USDCHF"),
    
    # FXCM (Requiere cuenta Premium en TradingView)
    "eurusd1": InstrumentConfig(symbol="EURUSD", exchange="FX", timeframe="1", full_symbol="FX:EURUSD"),
    "gbpusd1": InstrumentConfig(symbol="GBPUSD", exchange="FX", timeframe="1", full_symbol="FX:GBPUSD"),
    "usdjpy1": InstrumentConfig(symbol="USDJPY", exchange="FX", timeframe="1", full_symbol="FX:USDJPY"),
    #"usdchf1": InstrumentConfig(symbol="USDCHF", exchange="FX", timeframe="1", full_symbol="FX:USDCHF"),

    # IDC (Requiere cuenta Premium en TradingView)
    "eurusd2": InstrumentConfig(symbol="EURUSD", exchange="FX_IDC", timeframe="1", full_symbol="FX_IDC:EURUSD"),
    "gbpusd2": InstrumentConfig(symbol="GBPUSD", exchange="FX_IDC", timeframe="1", full_symbol="FX_IDC:GBPUSD"),
    "usdjpy2": InstrumentConfig(symbol="USDJPY", exchange="FX_IDC", timeframe="1", full_symbol="FX_IDC:USDJPY"),
    #"usdchf2": InstrumentConfig(symbol="USDCHF", exchange="FX_IDC", timeframe="1", full_symbol="FX_IDC:USDCHF"),
    
    }
    
    @classmethod
    def validate_all(cls) -> None:
        """
        Valida toda la configuración crítica antes de iniciar el bot.
        
        Raises:
            ValueError: Si alguna configuración crítica falta o es inválida
        """
        cls.TRADINGVIEW.validate()
        cls.TELEGRAM.validate()
        
        # Validar parámetros numéricos
        if cls.EMA_PERIOD < 20:
            raise ValueError(f"EMA_PERIOD must be >= 20, got {cls.EMA_PERIOD}")
        
        if cls.TRADINGVIEW.snapshot_candles < cls.EMA_PERIOD * 3:
            raise ValueError(
                f"SNAPSHOT_CANDLES ({cls.TRADINGVIEW.snapshot_candles}) must be "
                f"at least 3x EMA_PERIOD ({cls.EMA_PERIOD * 3})"
            )
    
    @classmethod
    def get_websocket_headers(cls) -> Dict[str, str]:
        """
        Genera headers HTTP para la conexión WebSocket con User-Agent rotativo.
        
        Returns:
            Dict[str, str]: Headers completos para bypass Anti-WAF
        """
        return {
            "Origin": cls.TRADINGVIEW.origin,
            "User-Agent": get_random_user_agent(),
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }


# =============================================================================
# VALIDACIÓN AL IMPORTAR
# =============================================================================

# Validar configuración automáticamente cuando se importa el módulo
try:
    Config.validate_all()
except ValueError as e:
    # No lanzar excepción aquí para permitir imports de testing
    # La validación se hará explícitamente en main.py
    print(f"⚠️  Configuration Warning: {e}")
