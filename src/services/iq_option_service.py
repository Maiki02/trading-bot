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
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from iqoptionapi.stable_api import IQ_Option

from config import Config
from src.services.connection_service import CandleData

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
        # Inicializar logger como atributo de instancia
        self.logger = logging.getLogger(__name__)
        
        self.email = email
        self.password = password
        self.asset = asset.upper()  # Asegurar mayúsculas
        
        # API de IQ Option
        self.api: Optional[IQ_Option] = None
        self._connected = False
        
        # Última vela recibida (thread-safe)
        self._latest_candle: Optional[CandleData] = None
        self._candle_lock = threading.Lock()
        
        # Control de reconexión
        self._reconnect_thread: Optional[threading.Thread] = None
        self._should_reconnect = True
        
        self.logger.info(f"IQ Option Service initialized for {asset}")
    
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
        
        Configura el buffer de velas (maxdict) desde Config.SNAPSHOT_CANDLES
        para asegurar que tengamos suficiente historial para análisis.
        """
        try:
            # Obtener tamaño del buffer desde configuración global
            buffer_size = Config.SNAPSHOT_CANDLES
            
            logger.info(f"Subscribing to candle stream for {self.asset} (buffer: {buffer_size} velas)...")
            
            # Suscribirse a velas de 60 segundos (1 minuto) con buffer configurado
            # maxdict: Número de velas a mantener en el buffer interno de iqoptionapi
            self.api.start_candles_stream(self.asset, 60, buffer_size)
            
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
    
    def get_historical_candles(self, count: int) -> list:
        """
        Obtiene velas históricas de IQ Option.
        
        Args:
            count: Número de velas a obtener (máximo ~1000)
            
        Returns:
            list: Lista de objetos CandleData ordenados por timestamp (más antiguo primero)
        """
        if not self._connected or not self.api:
            logger.error("Cannot get historical candles: not connected")
            return []
        
        try:
            logger.info(f"📥 Requesting {count} historical candles for {self.asset}...")
            
            # Calcular timestamps
            # IQ Option get_candles(asset, interval_seconds, count, end_time)
            # end_time: tiempo Unix en segundos (time.time())
            end_time = time.time()
            
            # Obtener velas históricas (60 segundos = 1 minuto)
            raw_candles = self.api.get_candles(self.asset, 60, count, end_time)
            
            logger.info(f"📡 Respuesta del servidor IQ Option: {len(raw_candles) if raw_candles else 0} velas recibidas")
            
            if not raw_candles:
                logger.warning(f"⚠️  No historical candles received for {self.asset}")
                return []
            
            # Convertir a lista de CandleData
            candle_list = []
            for raw_candle in raw_candles:
                try:
                    candle = self._map_candle_data(raw_candle)
                    candle_list.append(candle)
                except Exception as e:
                    logger.warning(f"Skipping invalid candle: {e}")
                    continue
            
            # Ordenar por timestamp (más antiguo primero)
            candle_list.sort(key=lambda c: c.timestamp)
            
            logger.info(f"✅ Loaded {len(candle_list)} historical candles for {self.asset}")
            return candle_list
            
        except Exception as e:
            logger.error(f"❌ Error getting historical candles: {e}", exc_info=True)
            return []
    
    def get_latest_candle(self, symbol: str, timeframe: int = 60) -> Optional[Dict]:
        """
        Obtiene la última vela CERRADA del stream.
        
        CRÍTICO: 
        - iqoptionapi devuelve la vela actual (en formación) como última.
        - Debemos tomar la ANTERIOR (timestamps[-2]) para tener la vela cerrada completa.
        - Usamos solo el campo 'from' (segundos Unix), NO 'at' (nanosegundos).
        """
        try:
            # Obtener tamaño del buffer desde configuración
            buffer_size = Config.SNAPSHOT_CANDLES
            
            # 1. Obtener velas del buffer local de la librería
            # get_realtime_candles devuelve un dict {timestamp: {data}}
            symbol_upper = symbol.upper()  # Asegurar mayúsculas
            candles_dict = self.api.get_realtime_candles(symbol_upper, timeframe)
            
            # --- DEBUGGING: DUMP RAW DATA ---
            # Guardar en archivo para inspección manual del usuario
            try:
                debug_path = Path("data/debug_iq_response.json")
                debug_path.parent.mkdir(exist_ok=True)
                with open(debug_path, "w", encoding="utf-8") as f:
                    json.dump(candles_dict, f, indent=2, default=str)
                self.logger.debug(f"🔍 Raw IQ data saved to {debug_path}")
            except Exception as debug_err:
                self.logger.warning(f"Could not save debug data: {debug_err}")
            # --------------------------------
            
            # 2. Validación de Flujo (Evitar Crash)
            if not candles_dict:
                self.logger.warning(f"⚠️ Stream vacío para {symbol_upper}. Esperando datos...")
                return None

            # 3. Ordenar por timestamp
            timestamps = sorted(list(candles_dict.keys()))
            
            # 4. Validación de Longitud (FIX PRINCIPAL - Necesitamos al menos 2 velas)
            # La última vela está en formación (actualización en tiempo real)
            # La anteúltima es la última vela CERRADA
            if len(timestamps) < 2:
                self.logger.info(
                    f"⏳ Buffer cargando... ({len(timestamps)}/{buffer_size} velas, mínimo 2 necesarias para {symbol_upper})"
                )
                return None
            
            # 5. Seleccionar la vela CERRADA (La anteúltima del stream)
            # La última (timestamps[-1]) es la que se está moviendo ahora (segundo a segundo).
            # La anteúltima (timestamps[-2]) es la que acaba de cerrar.
            closed_candle_ts = timestamps[-2]
            raw_candle = candles_dict[closed_candle_ts]

            # 6. MAPEO DE DATOS (IQ Option -> Nuestro Formato)
            # CRÍTICO: Usar solo 'from' (segundos Unix estándar)
            # NO usar 'at' (viene en nanosegundos y causa confusión)
            timestamp_seconds = raw_candle.get('from')
            
            if not timestamp_seconds:
                self.logger.error(f"⚠️ Timestamp 'from' no encontrado en vela: {raw_candle}")
                return None
            
            # IQ usa 'max'/'min', nosotros 'high'/'low'
            mapped_candle = {
                "timestamp": int(timestamp_seconds),  # Asegurar que sea int
                "open": float(raw_candle["open"]),
                "high": float(raw_candle["max"]),
                "low": float(raw_candle["min"]),
                "close": float(raw_candle["close"]),
                "volume": float(raw_candle.get("volume", 0)),
                "symbol": symbol_upper,
                "source": "IQOPTION"
            }

            # 7. Validación de integridad (evitar Dojis vacíos si la API falló)
            if mapped_candle['high'] == 0 or mapped_candle['low'] == 0:
                self.logger.warning(f"⚠️ Vela inválida con high/low en cero para {symbol_upper}")
                return None

            return mapped_candle

        except Exception as e:
            self.logger.error(f"❌ Error crítico en get_latest_candle: {e}", exc_info=True)
            return None
    
    def _map_candle_data(self, raw_candle: Dict[str, Any]) -> CandleData:
        """
        Convierte una vela de IQ Option al formato estándar CandleData.
        
        Estructura IQ Option:
        {
            'from': 1764027300,        # timestamp inicio (segundos Unix) - USAR ESTE
            'to': 1764027360,          # timestamp fin (segundos Unix)
            'at': 1764027083000000000, # timestamp en nanosegundos - NO USAR
            'open': 1.159475,
            'close': 1.159735,
            'min': 1.159375,           # low
            'max': 1.159785,           # high
            'volume': 0
        }
        
        Returns:
            CandleData: Objeto con la estructura esperada por AnalysisService
        """
        try:
            # CRÍTICO: Usar solo 'from' (segundos Unix estándar)
            # NO usar 'at' (nanosegundos) ni 'to' (fin de vela)
            timestamp_seconds = raw_candle.get('from')
            
            if not timestamp_seconds:
                raise ValueError(f"Campo 'from' no encontrado en vela. Keys disponibles: {raw_candle.keys()}")
            
            # Crear objeto CandleData (dataclass)
            return CandleData(
                timestamp=int(timestamp_seconds),  # Asegurar que sea int
                open=float(raw_candle['open']),
                high=float(raw_candle['max']),    # MAPEO: max -> high
                low=float(raw_candle['min']),     # MAPEO: min -> low
                close=float(raw_candle['close']),
                volume=0.0,  # IQ Option no provee volumen real
                source="IQOPTION",
                symbol=Config.IQOPTION.asset.replace("-OTC", "")  # "EURUSD-OTC" -> "EURUSD"
            )
            
        except Exception as e:
            logger.error(f"❌ MAPPING ERROR: {e}, raw_candle={raw_candle}")
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
            
            # Salir si se pidió desconectar
            if not self._should_reconnect:
                break
            
            if not self.is_connected():
                logger.warning("Connection lost. Attempting to reconnect...")
                
                # Intentar reconectar
                success = self.connect()
                
                if success:
                    logger.info("✓ Reconnection successful")
                    reconnect_timeout = Config.RECONNECT_INITIAL_TIMEOUT
                else:
                    # No seguir reintentando durante el shutdown
                    if not self._should_reconnect:
                        break
                        
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
        self._should_poll = False
        self._poll_interval = 1.0  # Verificar cada 1 segundo por nuevas velas
    
    async def start(self) -> None:
        """
        Inicia el servicio de IQ Option y el polling de velas.
        Este método es BLOQUEANTE y debe correr indefinidamente (como TradingViewService).
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
        
        # Cargar velas históricas para inicializar EMAs
        await self._load_historical_candles()
        
        # Iniciar polling de velas (BLOQUEANTE - espera aquí indefinidamente)
        self._should_poll = True
        logger.info("✅ IQ Option Service started - Monitoring candles...")
        
        # Este await bloquea hasta que se cancele el servicio
        await self._poll_candles()
    
    async def stop(self) -> None:
        """
        Detiene el servicio y el polling.
        """
        logger.info("🛑 Stopping IQ Option Service...")
        
        # Detener el loop de polling
        self._should_poll = False
        
        # Dar tiempo para que el loop termine limpiamente
        await asyncio.sleep(0.5)
        
        # Desconectar del servicio IQ Option
        if self.iq_service:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.iq_service.disconnect)
        
        logger.info("✅ IQ Option Service stopped")
    
    async def _load_historical_candles(self) -> None:
        """
        Carga velas históricas al iniciar para llenar el buffer de EMAs.
        """
        try:
            # Calcular cantidad de velas necesarias (3x EMA_PERIOD mínimo)
            min_candles = Config.EMA_PERIOD * 3
            
            # Pedir un poco más para asegurar suficientes datos
            candles_to_request = min(min_candles + 50, 1000)  # Máximo 1000
            
            logger.info(f"📥 Loading {candles_to_request} historical candles to initialize EMAs...")
            
            # Obtener velas históricas (operación bloqueante en executor)
            loop = asyncio.get_running_loop()
            historical_candles = await loop.run_in_executor(
                None,
                self.iq_service.get_historical_candles,
                candles_to_request
            )
            
            if not historical_candles:
                logger.warning("⚠️  No historical candles received - EMAs may not be accurate initially")
                return
            
            # Cargar todas las velas en el AnalysisService (sin generar notificaciones)
            logger.info(f"📊 Loading {len(historical_candles)} candles into AnalysisService...")
            self.analysis_service.load_historical_candles(historical_candles)
            
            logger.info(f"✅ Historical data loaded successfully")
            
        except Exception as e:
            logger.error(f"❌ Error loading historical candles: {e}", exc_info=True)
    
    async def _poll_candles(self) -> None:
        """
        Loop que consulta periódicamente por nuevas velas y las procesa.
        """
        last_candle_time = None
        iteration = 0
        
        logger.info(f"📡 Starting candle polling loop for {Config.IQOPTION.asset}...")
        
        while self._should_poll:
            try:
                iteration += 1
                
                # Log cada 30 iteraciones para mostrar que sigue vivo
                if iteration % 30 == 0:
                    logger.debug(f"💓 Polling loop alive (iteration {iteration})")
                
                # Obtener última vela (operación bloqueante en executor)
                loop = asyncio.get_running_loop()
                candle = await loop.run_in_executor(
                    None,
                    self.iq_service.get_latest_candle,  # La función
                    self.iq_service.asset               # <--- EL ARGUMENTO QUE FALTABA
                )
                
                # LOG: Mostrar vela recibida (INMEDIATAMENTE después de obtenerla)
                if candle:
                    logger.info(
                        f"🔵 VELA RECIBIDA DE IQ OPTION | "
                        f"timestamp={candle.timestamp}, "
                        f"open={candle.open:.5f}, "
                        f"high={candle.high:.5f}, "
                        f"low={candle.low:.5f}, "
                        f"close={candle.close:.5f}, "
                        f"volume={candle.volume}, "
                        f"source={candle.source}, "
                        f"symbol={candle.symbol}"
                    )
                
                if candle and candle.timestamp:
                    candle_timestamp = candle.timestamp
                    
                    # Solo procesar si es una vela nueva
                    if last_candle_time is None or candle_timestamp > last_candle_time:
                        # Formatear timestamp para mostrar fecha y hora completa
                        candle_dt = datetime.utcfromtimestamp(candle_timestamp)
                        
                        logger.info(
                            f"🕯️ VELA CERRADA | {Config.IQOPTION.asset} | "
                            f"Fecha: {candle_dt.strftime('%Y-%m-%d %H:%M:%S')} | "
                            f"Apertura: {candle.open:.5f} | "
                            f"Máximo: {candle.high:.5f} | "
                            f"Mínimo: {candle.low:.5f} | "
                            f"Cierre: {candle.close:.5f}"
                        )
                        
                        # Procesar vela con AnalysisService
                        if self.analysis_service:
                            await self.analysis_service.process_realtime_candle(candle)
                        
                        last_candle_time = candle_timestamp
                else:
                    # Log si no hay vela disponible (primera iteración)
                    if iteration == 1:
                        logger.warning("⚠️  No candle data available yet, waiting...")
                
                # Esperar antes de la siguiente consulta
                await asyncio.sleep(self._poll_interval)
                
            except asyncio.CancelledError:
                logger.info("🛑 Polling loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Esperar más tiempo en caso de error
        
        logger.info("✅ Polling loop terminated")


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

