"""
IQ Option Market Data Service
==============================
Implementa la interfaz MarketDataService para obtener datos de mercado
desde IQ Option en tiempo real mediante iqoptionapi.

NOTA: Este servicio incluye un wrapper asíncrono para integrarse con
el sistema asíncrono del bot (compatible con TradingViewService).

Author: Trading Bot Architecture Team
"""

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Callable
from iqoptionapi.stable_api import IQ_Option

from config import Config

logger = logging.getLogger(__name__)


class IqOptionService:
    """
    Servicio de datos de mercado para IQ Option.
    
    Implementa la interfaz MarketDataService y maneja:
    - Conexión/reconexión automática
    - Suscripción a velas en tiempo real
    - Mapeo de datos al formato estándar
    - Thread-safety para acceso concurrente
    """
    
    def __init__(self, email: str, password: str, asset: str):
        """
        Inicializa el servicio de IQ Option.
        
        Args:
            email: Email de la cuenta de IQ Option
            password: Contraseña de la cuenta
            asset: Par a operar (ej: "EURUSD-OTC", "EURUSD")
        """
        self.email = email
        self.password = password
        self.asset = asset
        
        # API de IQ Option
        self.api: Optional[IQ_Option] = None
        self._connected = False
        
        # Última vela recibida (thread-safe)
        self._latest_candle: Optional[Dict[str, Any]] = None
        self._candle_lock = threading.Lock()
        
        # Control de reconexión
        self._reconnect_thread: Optional[threading.Thread] = None
        self._should_reconnect = True
        
        logger.info(f"IQ Option Service initialized for {asset}")
    
    def connect(self) -> bool:
        """
        Establece conexión con IQ Option y suscribe al stream de velas.
        
        Returns:
            bool: True si la conexión fue exitosa
        """
        try:
            logger.info(f"Connecting to IQ Option as {self.email}...")
            
            # Inicializar API
            self.api = IQ_Option(self.email, self.password)
            
            # Conectar (esto puede tomar unos segundos)
            check, reason = self.api.connect()
            
            if not check:
                logger.error(f"Failed to connect to IQ Option: {reason}")
                self._connected = False
                return False
            
            logger.info("✓ Connected to IQ Option successfully")
            self._connected = True
            
            # Cambiar a cuenta PRACTICE (demo) - Cambiar a "REAL" si quieres operar real
            self.api.change_balance("PRACTICE")
            logger.info("✓ Using PRACTICE account")
            
            # Suscribirse al stream de velas de 1 minuto
            self._subscribe_to_candles()
            
            # Iniciar monitoreo de reconexión
            self._start_reconnect_monitor()
            
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to IQ Option: {e}", exc_info=True)
            self._connected = False
            return False
    
    def _subscribe_to_candles(self) -> None:
        """
        Suscribe al stream de velas en tiempo real.
        """
        try:
            logger.info(f"Subscribing to candle stream for {self.asset}...")
            
            # Suscribirse a velas de 60 segundos (1 minuto)
            self.api.start_candles_stream(self.asset, 60, 1)
            
            # Dar tiempo para que llegue la primera vela
            time.sleep(2)
            
            logger.info(f"✓ Subscribed to {self.asset} candle stream")
            
        except Exception as e:
            logger.error(f"Error subscribing to candles: {e}", exc_info=True)
    
    def disconnect(self) -> None:
        """
        Cierra la conexión y detiene el monitoreo.
        """
        logger.info("Disconnecting from IQ Option...")
        
        self._should_reconnect = False
        self._connected = False
        
        if self.api:
            try:
                # Detener stream de velas
                self.api.stop_candles_stream(self.asset, 60)
                logger.info("✓ Stopped candle stream")
            except Exception as e:
                logger.warning(f"Error stopping candle stream: {e}")
        
        logger.info("✓ Disconnected from IQ Option")
    
    def get_latest_candle(self) -> Optional[Dict[str, Any]]:
        """
        Obtiene la última vela en formato estandarizado.
        
        MAPEO DE DATOS IQ OPTION -> FORMATO ESTÁNDAR:
        - 'max' -> 'high'
        - 'min' -> 'low'
        - 'at' (unix timestamp) -> 'time' (datetime)
        - 'open', 'close' -> sin cambios
        - 'volume' -> 0 (IQ Option no provee volumen real en velas de 1min)
        
        Returns:
            Optional[Dict[str, Any]]: Vela estandarizada o None
        """
        if not self._connected or not self.api:
            return None
        
        try:
            # Obtener velas desde la API (devuelve las últimas velas del stream)
            candles_data = self.api.get_realtime_candles(self.asset, 60)
            
            if not candles_data:
                return self._latest_candle  # Retornar la última conocida
            
            # Obtener la vela más reciente
            # candles_data es un dict con timestamp como keys
            latest_timestamp = max(candles_data.keys())
            raw_candle = candles_data[latest_timestamp]
            
            # Mapear al formato estándar
            with self._candle_lock:
                self._latest_candle = self._map_candle_data(raw_candle)
            
            return self._latest_candle
            
        except Exception as e:
            logger.error(f"Error getting latest candle: {e}", exc_info=True)
            return self._latest_candle  # Retornar la última conocida
    
    def _map_candle_data(self, raw_candle: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convierte una vela de IQ Option al formato estándar.
        
        Formato IQ Option:
        {
            'open': 1.05123,
            'close': 1.05145,
            'max': 1.05167,    # high
            'min': 1.05100,    # low
            'at': 1700000000,  # unix timestamp
            'volume': 0        # no disponible para velas de 1min
        }
        
        Formato Estándar:
        {
            'time': datetime,
            'open': float,
            'high': float,
            'low': float,
            'close': float,
            'volume': float
        }
        
        Args:
            raw_candle: Vela en formato IQ Option
            
        Returns:
            Dict[str, Any]: Vela en formato estándar
        """
        try:
            # Convertir timestamp unix a datetime
            # IQ Option devuelve timestamps en segundos
            timestamp = raw_candle.get('at', raw_candle.get('from', time.time()))
            candle_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            
            return {
                'time': candle_time,
                'open': float(raw_candle['open']),
                'high': float(raw_candle['max']),    # MAPEO: max -> high
                'low': float(raw_candle['min']),     # MAPEO: min -> low
                'close': float(raw_candle['close']),
                'volume': 0.0  # IQ Option no provee volumen real en 1min
            }
            
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error mapping candle data: {e}, raw_candle={raw_candle}")
            raise
    
    def is_connected(self) -> bool:
        """
        Verifica si la conexión está activa.
        
        Returns:
            bool: True si está conectado
        """
        if not self._connected or not self.api:
            return False
        
        # Verificar que la API sigue conectada
        try:
            # check_connect() retorna True si la sesión está activa
            return self.api.check_connect()
        except Exception as e:
            logger.warning(f"Error checking connection: {e}")
            return False
    
    def _start_reconnect_monitor(self) -> None:
        """
        Inicia un hilo que monitorea la conexión y reconecta automáticamente.
        """
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return
        
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            daemon=True,
            name="IQOptionReconnectMonitor"
        )
        self._reconnect_thread.start()
        logger.info("✓ Reconnect monitor started")
    
    def _reconnect_loop(self) -> None:
        """
        Loop que verifica la conexión y reconecta si es necesario.
        """
        reconnect_timeout = Config.RECONNECT_INITIAL_TIMEOUT
        
        while self._should_reconnect:
            time.sleep(10)  # Verificar cada 10 segundos
            
            if not self.is_connected():
                logger.warning("Connection lost. Attempting to reconnect...")
                
                # Intentar reconectar
                success = self.connect()
                
                if success:
                    logger.info("✓ Reconnection successful")
                    reconnect_timeout = Config.RECONNECT_INITIAL_TIMEOUT
                else:
                    logger.error(f"Reconnection failed. Waiting {reconnect_timeout}s...")
                    time.sleep(reconnect_timeout)
                    
                    # Exponential backoff
                    reconnect_timeout = min(
                        reconnect_timeout * 2,
                        Config.RECONNECT_MAX_TIMEOUT
                    )


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_iq_option_service() -> IqOptionService:
    """
    Factory function para crear una instancia del servicio IQ Option
    usando la configuración global.
    
    Returns:
        IqOptionService: Instancia configurada del servicio
    """
    return IqOptionService(
        email=Config.IQOPTION.email,
        password=Config.IQOPTION.password,
        asset=Config.IQOPTION.asset
    )


# =============================================================================
# ASYNC WRAPPER (Compatibilidad con TradingViewService asíncrono)
# =============================================================================

class IqOptionServiceAsync:
    """
    Wrapper asíncrono para IqOptionService.
    
    Proporciona la misma interfaz asíncrona que TradingViewService para que
    main.py pueda usar cualquiera de los dos proveedores de forma transparente.
    """
    
    def __init__(self, analysis_service, on_auth_failure_callback: Optional[Callable] = None):
        """
        Inicializa el wrapper asíncrono.
        
        Args:
            analysis_service: Instancia de AnalysisService para procesar velas
            on_auth_failure_callback: Callback para manejar fallos de autenticación
        """
        self.analysis_service = analysis_service
        self.on_auth_failure_callback = on_auth_failure_callback
        
        # Servicio IQ Option subyacente (síncrono)
        self.iq_service: Optional[IqOptionService] = None
        
        # Control de polling
        self._polling_task: Optional[asyncio.Task] = None
        self._should_poll = False
        self._poll_interval = 1.0  # Verificar cada 1 segundo por nuevas velas
    
    async def start(self) -> None:
        """
        Inicia el servicio de IQ Option y el polling de velas.
        """
        logger.info("🚀 Starting IQ Option Service (Async Wrapper)...")
        
        # Crear e iniciar servicio subyacente en hilo separado
        loop = asyncio.get_running_loop()
        self.iq_service = await loop.run_in_executor(None, create_iq_option_service)
        
        # Conectar (bloqueante, ejecutar en executor)
        success = await loop.run_in_executor(None, self.iq_service.connect)
        
        if not success:
            logger.error("❌ Failed to connect to IQ Option")
            if self.on_auth_failure_callback:
                self.on_auth_failure_callback()
            return
        
        logger.info("✅ IQ Option connected successfully")
        
        # Iniciar polling de velas
        self._should_poll = True
        self._polling_task = asyncio.create_task(self._poll_candles())
        
        logger.info("✅ IQ Option Service started")
    
    async def stop(self) -> None:
        """
        Detiene el servicio y el polling.
        """
        logger.info("🛑 Stopping IQ Option Service...")
        
        self._should_poll = False
        
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        
        if self.iq_service:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.iq_service.disconnect)
        
        logger.info("✅ IQ Option Service stopped")
    
    async def _poll_candles(self) -> None:
        """
        Loop que consulta periódicamente por nuevas velas y las procesa.
        """
        last_candle_time = None
        
        while self._should_poll:
            try:
                # Obtener última vela (operación bloqueante en executor)
                loop = asyncio.get_running_loop()
                candle = await loop.run_in_executor(
                    None,
                    self.iq_service.get_latest_candle
                )
                
                if candle and candle.get('time'):
                    candle_time = candle['time']
                    
                    # Solo procesar si es una vela nueva
                    if last_candle_time is None or candle_time > last_candle_time:
                        logger.info(
                            f"📊 New candle: {candle_time.strftime('%H:%M:%S')} | "
                            f"O:{candle['open']:.5f} H:{candle['high']:.5f} "
                            f"L:{candle['low']:.5f} C:{candle['close']:.5f}"
                        )
                        
                        # Procesar vela con AnalysisService
                        if self.analysis_service:
                            await self.analysis_service.process_realtime_candle(candle)
                        
                        last_candle_time = candle_time
                
                # Esperar antes de la siguiente consulta
                await asyncio.sleep(self._poll_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Esperar más tiempo en caso de error


def create_iq_option_service_async(analysis_service, on_auth_failure_callback: Optional[Callable] = None) -> IqOptionServiceAsync:
    """
    Factory function para crear una instancia del wrapper asíncrono de IQ Option.
    
    Args:
        analysis_service: Instancia de AnalysisService
        on_auth_failure_callback: Callback para manejar fallos de autenticación
        
    Returns:
        IqOptionServiceAsync: Instancia del wrapper asíncrono
    """
    return IqOptionServiceAsync(
        analysis_service=analysis_service,
        on_auth_failure_callback=on_auth_failure_callback
    )

