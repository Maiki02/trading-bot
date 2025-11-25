"""
IQ Option Market Data Service
==============================
Implementa la interfaz MarketDataService para obtener datos de mercado
desde IQ Option en tiempo real mediante iqoptionapi.

ARQUITECTURA: Buffer Local + Detección de Eventos
- Mantiene un buffer interno de velas en tiempo real
- Detecta cambios de timestamp para identificar velas cerradas
- Notifica al sistema de análisis solo cuando hay nuevas velas

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
    
    Implementa:
    - Conexión/reconexión automática
    - Suscripción a stream de velas en tiempo real
    - Detección de velas cerradas por cambio de timestamp
    - Mapeo de datos al formato estándar CandleData
    """
    
    def __init__(self, email: str, password: str, asset: str):
        """
        Inicializa el servicio de IQ Option.
        
        Args:
            email: Email de la cuenta de IQ Option
            password: Contraseña de la cuenta
            asset: Par a operar (ej: "EURUSD-OTC", "EURUSD")
        """
        self.logger = logging.getLogger(__name__)
        
        self.email = email
        self.password = password
        self.asset = asset.upper()  # Asegurar mayúsculas
        
        # API de IQ Option
        self.api: Optional[IQ_Option] = None
        self._connected = False
        
        # Control de reconexión
        self._reconnect_thread: Optional[threading.Thread] = None
        self._should_reconnect = True
        
        self.logger.info(f"✅ IQ Option Service initialized for {self.asset}")
    
    def connect(self) -> bool:
        """
        Establece conexión con IQ Option y suscribe al stream de velas.
        
        Returns:
            bool: True si la conexión fue exitosa
        """
        try:
            self.logger.info(f"🔌 Connecting to IQ Option as {self.email}...")
            
            # Inicializar API
            self.api = IQ_Option(self.email, self.password)
            
            # Conectar (esto puede tomar unos segundos)
            check, reason = self.api.connect()
            
            if not check:
                self.logger.error(f"❌ Failed to connect to IQ Option: {reason}")
                self._connected = False
                return False
            
            self.logger.info("✅ Connected to IQ Option successfully")
            self._connected = True
            
            # Cambiar a cuenta PRACTICE (demo) - Cambiar a "REAL" si quieres operar real
            self.api.change_balance("PRACTICE")
            self.logger.info("💰 Using PRACTICE account")
            
            # Suscribirse al stream de velas de 1 minuto
            self._subscribe_to_candles()
            
            # Iniciar monitoreo de reconexión
            self._start_reconnect_monitor()
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error connecting to IQ Option: {e}", exc_info=True)
            self._connected = False
            return False
    
    def _subscribe_to_candles(self) -> None:
        """
        Suscribe al stream de velas en tiempo real.
        
        Configura el buffer (maxdict) con margen adicional para evitar pérdida de datos.
        """
        try:
            # Buffer size: CHART_LOOKBACK + margen de 10 velas
            buffer_size = Config.CHART_LOOKBACK + 10
            
            self.logger.info(
                f"📡 Subscribing to candle stream for {self.asset} "
                f"(buffer: {buffer_size} velas)..."
            )
            
            # Suscribirse a velas de 60 segundos (1 minuto)
            # maxdict: Número de velas a mantener en el buffer interno
            self.api.start_candles_stream(self.asset, 60, buffer_size)
            
            # Dar tiempo para que llegue la primera vela
            time.sleep(2)
            
            self.logger.info(f"✅ Subscribed to {self.asset} candle stream")
            
        except Exception as e:
            self.logger.error(f"❌ Error subscribing to candles: {e}", exc_info=True)
    
    def disconnect(self) -> None:
        """
        Cierra la conexión y detiene el monitoreo.
        """
        self.logger.info("🔌 Disconnecting from IQ Option...")
        
        self._should_reconnect = False
        self._connected = False
        
        if self.api:
            try:
                # Detener stream de velas
                self.api.stop_candles_stream(self.asset, 60)
                self.logger.info("✅ Stopped candle stream")
            except Exception as e:
                self.logger.warning(f"⚠️ Error stopping candle stream: {e}")
        
        self.logger.info("✅ Disconnected from IQ Option")
    
    def get_historical_candles(self, count: int) -> list:
        """
        Obtiene velas históricas de IQ Option para llenar el buffer inicial.
        
        Args:
            count: Número de velas a obtener (máximo ~1000)
            
        Returns:
            list: Lista de objetos CandleData ordenados por timestamp (más antiguo primero)
        """
        if not self._connected or not self.api:
            self.logger.error("❌ Cannot get historical candles: not connected")
            return []
        
        try:
            self.logger.info(f"📥 Requesting {count} historical candles for {self.asset}...")
            
            # Obtener velas históricas
            # get_candles(asset, interval_seconds, count, end_time)
            end_time = time.time()
            raw_candles = self.api.get_candles(self.asset, 60, count, end_time)
            
            # --- DEBUG: GUARDAR RESPUESTA INICIAL ---
            try:
                debug_path = Path("data/debug_start_iq_response.json")
                debug_path.parent.mkdir(exist_ok=True)
                with open(debug_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "asset": self.asset,
                        "requested_count": count,
                        "received_count": len(raw_candles) if raw_candles else 0,
                        "end_time": end_time,
                        "candles": raw_candles
                    }, f, indent=2, default=str)
                self.logger.info(f"🔍 DEBUG: Initial response saved to {debug_path}")
            except Exception as debug_err:
                self.logger.warning(f"⚠️ Could not save debug data: {debug_err}")
            # -----------------------------------------
            
            self.logger.info(
                f"📊 IQ Option response: {len(raw_candles) if raw_candles else 0} candles received"
            )
            
            if not raw_candles:
                self.logger.warning(f"⚠️ No historical candles received for {self.asset}")
                return []
            
            # Convertir a lista de CandleData
            candle_list = []
            for raw_candle in raw_candles:
                try:
                    candle = self._map_candle_data(raw_candle)
                    candle_list.append(candle)
                except Exception as e:
                    self.logger.warning(f"⚠️ Skipping invalid candle: {e}")
                    continue
            
            # Ordenar por timestamp (más antiguo primero)
            candle_list.sort(key=lambda c: c.timestamp)
            
            self.logger.info(f"✅ Loaded {len(candle_list)} historical candles for {self.asset}")
            return candle_list
            
        except Exception as e:
            self.logger.error(f"❌ Error getting historical candles: {e}", exc_info=True)
            return []
    
    def get_latest_closed_candle(self) -> Optional[CandleData]:
        """
        Obtiene la vela más reciente del stream en tiempo real.
        
        ESTRATEGIA CORREGIDA:
        1. Lee el buffer interno de la API (get_realtime_candles)
        2. Retorna la ÚLTIMA vela (timestamps[-1])
        3. El polling loop detectará cuando el timestamp cambia
        4. Un cambio en timestamp[-1] indica que la vela anterior cerró
        
        IMPORTANTE: Esta función retorna la vela actual (que puede estar cerrándose
        en este momento). El sistema de detección compara timestamps para notificar
        solo cuando hay un cambio (nueva vela cerrada).
        
        Returns:
            Optional[CandleData]: Vela más reciente, o None si no hay datos
        """
        try:
            # Obtener buffer de velas en tiempo real
            candles_dict = self.api.get_realtime_candles(self.asset, 60)
            
            # --- DEBUG: GUARDAR ESTADO ACTUAL DEL WEBSOCKET ---
            try:
                debug_path = Path("data/debug_current_candle_iq_response.json")
                debug_path.parent.mkdir(exist_ok=True)
                
                # Ordenar timestamps para mostrar estructura clara
                timestamps = sorted(list(candles_dict.keys())) if candles_dict else []
                
                debug_data = {
                    "asset": self.asset,
                    "timestamp_query": datetime.utcnow().isoformat(),
                    "buffer_size": len(timestamps),
                    "timestamps": timestamps,
                    "candles": candles_dict
                }
                
                with open(debug_path, "w", encoding="utf-8") as f:
                    json.dump(debug_data, f, indent=2, default=str)
                
                self.logger.debug(f"🔍 DEBUG: Current candle buffer saved to {debug_path}")
            except Exception as debug_err:
                self.logger.warning(f"⚠️ Could not save current candle debug: {debug_err}")
            # ---------------------------------------------------
            
            # Validación: Buffer vacío
            if not candles_dict:
                self.logger.debug("⏳ Buffer vacío, esperando datos del stream...")
                return None
            
            # Ordenar timestamps
            timestamps = sorted(list(candles_dict.keys()))
            
            # Validación: Necesitamos al menos 1 vela
            if len(timestamps) < 1:
                self.logger.debug(
                    f"⏳ Buffer vacío... (0 velas)"
                )
                return None
            
            # ESTRATEGIA CORREGIDA:
            # - timestamps[-1]: Vela más reciente (puede ser cerrada O en formación)
            # - Nuestro sistema detectará el CAMBIO de timestamp de [-1]
            # - Cuando [-1] cambia, significa que la vela anterior cerró
            # 
            # Por lo tanto: SIEMPRE retornamos timestamps[-1]
            # El loop de detección se encargará de notificar solo cuando cambie
            latest_candle_ts = timestamps[-1]
            raw_candle = candles_dict[latest_candle_ts]
            
            # Mapear a CandleData
            candle = self._map_realtime_candle(raw_candle)
            
            return candle
            
        except Exception as e:
            self.logger.error(f"❌ Error en get_latest_closed_candle: {e}", exc_info=True)
            return None
    
    def _map_realtime_candle(self, raw_candle: Dict[str, Any]) -> Optional[CandleData]:
        """
        Mapea una vela del stream en tiempo real a CandleData.
        
        Args:
            raw_candle: Diccionario con datos de IQ Option
            
        Returns:
            Optional[CandleData]: Vela mapeada, o None si es inválida
        """
        try:
            # CRÍTICO: Usar solo 'from' (segundos Unix estándar)
            timestamp_seconds = raw_candle.get('from')
            
            if not timestamp_seconds:
                self.logger.warning(f"⚠️ Campo 'from' no encontrado en vela: {raw_candle}")
                return None
            
            # Validación de integridad: Descartar velas con datos inválidos
            if raw_candle.get('max', 0) == 0 or raw_candle.get('min', 0) == 0:
                self.logger.warning(
                    f"⚠️ Vela inválida con high/low en cero (timestamp: {timestamp_seconds})"
                )
                return None
            
            # Crear objeto CandleData
            return CandleData(
                timestamp=int(timestamp_seconds),
                open=float(raw_candle["open"]),
                high=float(raw_candle["max"]),   # IQ usa 'max' -> 'high'
                low=float(raw_candle["min"]),    # IQ usa 'min' -> 'low'
                close=float(raw_candle["close"]),
                volume=float(raw_candle.get("volume", 0)),
                source="IQOPTION",
                symbol=self.asset
            )
            
        except Exception as e:
            self.logger.error(f"❌ Error mapeando vela en tiempo real: {e}", exc_info=True)
            return None
    
    def _map_candle_data(self, raw_candle: Dict[str, Any]) -> CandleData:
        """
        Mapea una vela histórica de IQ Option a CandleData.
        
        Estructura IQ Option (históricas):
        {
            'from': 1764027300,  # timestamp inicio (segundos Unix)
            'to': 1764027360,    # timestamp fin (segundos Unix)
            'open': 1.159475,
            'close': 1.159735,
            'min': 1.159375,     # low
            'max': 1.159785,     # high
            'volume': 0
        }
        
        Args:
            raw_candle: Diccionario con datos de IQ Option
            
        Returns:
            CandleData: Vela mapeada
            
        Raises:
            ValueError: Si falta el campo 'from' o datos inválidos
        """
        # CRÍTICO: Usar solo 'from' (segundos Unix estándar)
        timestamp_seconds = raw_candle.get('from')
        
        if not timestamp_seconds:
            raise ValueError(
                f"Campo 'from' no encontrado. Keys: {list(raw_candle.keys())}"
            )
        
        return CandleData(
            timestamp=int(timestamp_seconds),
            open=float(raw_candle['open']),
            high=float(raw_candle['max']),
            low=float(raw_candle['min']),
            close=float(raw_candle['close']),
            volume=0.0,  # IQ Option no provee volumen real
            source="IQOPTION",
            symbol=self.asset
        )
    
    def is_connected(self) -> bool:
        """
        Verifica si la conexión está activa.
        
        Returns:
            bool: True si está conectado
        """
        if not self._connected or not self.api:
            return False
        
        try:
            return self.api.check_connect()
        except Exception as e:
            self.logger.warning(f"⚠️ Error checking connection: {e}")
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
        self.logger.info("✅ Reconnect monitor started")
    
    def _reconnect_loop(self) -> None:
        """
        Loop que verifica la conexión y reconecta si es necesario.
        """
        reconnect_timeout = Config.RECONNECT_INITIAL_TIMEOUT
        
        while self._should_reconnect:
            time.sleep(10)  # Verificar cada 10 segundos
            
            if not self._should_reconnect:
                break
            
            if not self.is_connected():
                self.logger.warning("⚠️ Connection lost. Attempting to reconnect...")
                
                success = self.connect()
                
                if success:
                    self.logger.info("✅ Reconnection successful")
                    reconnect_timeout = Config.RECONNECT_INITIAL_TIMEOUT
                else:
                    if not self._should_reconnect:
                        break
                    
                    self.logger.error(f"❌ Reconnection failed. Waiting {reconnect_timeout}s...")
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
    Factory function para crear una instancia del servicio IQ Option.
    
    Returns:
        IqOptionService: Instancia configurada del servicio
    """
    return IqOptionService(
        email=Config.IQOPTION.email,
        password=Config.IQOPTION.password,
        asset=Config.IQOPTION.asset
    )


# =============================================================================
# ASYNC WRAPPER - Event-Driven Architecture
# =============================================================================

class IqOptionServiceAsync:
    """
    Wrapper asíncrono para IqOptionService con arquitectura de eventos.
    
    ESTRATEGIA:
    - Polling de alta frecuencia (0.1s) para detectar nuevas velas cerradas
    - Comparación de timestamps para evitar procesamiento duplicado
    - Notificación inmediata al AnalysisService cuando se detecta una nueva vela
    """
    
    def __init__(
        self, 
        analysis_service, 
        on_auth_failure_callback: Optional[Callable] = None
    ):
        """
        Inicializa el wrapper asíncrono.
        
        Args:
            analysis_service: Instancia de AnalysisService
            on_auth_failure_callback: Callback para fallos de autenticación
        """
        self.analysis_service = analysis_service
        self.on_auth_failure_callback = on_auth_failure_callback
        
        # Servicio IQ Option subyacente (síncrono)
        self.iq_service: Optional[IqOptionService] = None
        
        # Control de polling
        self._should_poll = False
        self._poll_interval = 0.5  # 100ms - Alta frecuencia para detección rápida
        
        # Timestamp de la última vela procesada (para evitar duplicados)
        self.last_processed_timestamp: Optional[int] = None
    
    async def start(self) -> None:
        """
        Inicia el servicio de IQ Option y el loop de detección de velas.
        
        Este método es BLOQUEANTE y corre indefinidamente hasta que se cancele.
        """
        logger.info("🚀 Starting IQ Option Service (Event-Driven Mode)...")
        
        # Crear servicio subyacente en executor
        loop = asyncio.get_running_loop()
        self.iq_service = await loop.run_in_executor(None, create_iq_option_service)
        
        # Conectar
        success = await loop.run_in_executor(None, self.iq_service.connect)
        
        if not success:
            logger.error("❌ Failed to connect to IQ Option")
            if self.on_auth_failure_callback:
                self.on_auth_failure_callback()
            return
        
        logger.info("✅ IQ Option connected successfully")
        
        # Cargar velas históricas para inicializar EMAs
        await self._load_historical_candles()
        
        # Iniciar loop de detección de velas (BLOQUEANTE)
        self._should_poll = True
        logger.info("🔄 Starting candle detection loop...")
        
        await self._poll_candles()
    
    async def stop(self) -> None:
        """
        Detiene el servicio y el polling.
        """
        logger.info("🛑 Stopping IQ Option Service...")
        
        self._should_poll = False
        await asyncio.sleep(0.5)
        
        if self.iq_service:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.iq_service.disconnect)
        
        logger.info("✅ IQ Option Service stopped")
    
    async def _load_historical_candles(self) -> None:
        """
        Carga velas históricas para llenar el buffer de EMAs.
        """
        try:
            # Calcular velas necesarias (3x EMA_PERIOD + margen)
            min_candles = Config.EMA_PERIOD * 3
            candles_to_request = min(min_candles + 50, 1000)
            
            logger.info(f"📥 Loading {candles_to_request} historical candles...")
            
            # Obtener velas históricas
            loop = asyncio.get_running_loop()
            historical_candles = await loop.run_in_executor(
                None,
                self.iq_service.get_historical_candles,
                candles_to_request
            )
            
            if not historical_candles:
                logger.warning("⚠️ No historical candles received")
                return
            
            # Cargar en AnalysisService
            logger.info(f"📊 Loading {len(historical_candles)} candles into AnalysisService...")
            self.analysis_service.load_historical_candles(historical_candles)
            
            logger.info("✅ Historical data loaded successfully")
            
        except Exception as e:
            logger.error(f"❌ Error loading historical candles: {e}", exc_info=True)
    
    async def _poll_candles(self) -> None:
        """
        Loop de detección de velas cerradas (Event-Driven).
        
        ALGORITMO:
        1. Cada 100ms, consultar get_latest_closed_candle()
        2. Comparar timestamp con self.last_processed_timestamp
        3. Si es diferente -> Nueva vela -> Procesar y notificar
        4. Si es igual -> Misma vela -> Esperar siguiente iteración
        """
        iteration = 0
        clock_started = False  # Flag para loguear cuando inicia el reloj
        
        logger.info(f"🕐 Candle detection loop started for {Config.IQOPTION.asset}")
        
        while self._should_poll:
            try:
                iteration += 1
                
                # Log heartbeat cada 300 iteraciones (~30 segundos)
                if iteration % 300 == 0:
                    logger.debug(f"💓 Detection loop alive (iteration {iteration})")
                
                # Obtener última vela cerrada (en executor para no bloquear)
                loop = asyncio.get_running_loop()
                candle = await loop.run_in_executor(
                    None,
                    self.iq_service.get_latest_closed_candle
                )
                
                # Si no hay vela disponible, esperar
                if not candle:
                    if iteration == 1:
                        logger.info("⏳ Waiting for first candle from stream...")
                    await asyncio.sleep(self._poll_interval)
                    continue
                
                # --- LOG: RELOJ INICIADO (Primera vez que detectamos vela) ---
                if not clock_started:
                    candle_dt = datetime.utcfromtimestamp(candle.timestamp)
                    logger.info(
                        f"⏰ RELOJ INICIADO | Escuchando vela activa | "
                        f"Última vela cerrada: {candle_dt.strftime('%Y-%m-%d %H:%M:%S')} | "
                        f"Esperando cierre de la siguiente..."
                    )
                    clock_started = True
                # -------------------------------------------------------------
                
                # DETECCIÓN DE NUEVA VELA CERRADA
                candle_timestamp = candle.timestamp
                
                if (self.last_processed_timestamp is None or 
                    candle_timestamp > self.last_processed_timestamp):
                    
                    # ¡NUEVA VELA DETECTADA!
                    candle_dt = datetime.utcfromtimestamp(candle_timestamp)
                    
                    # --- LOG: VELA ACTIVA CERRÓ ---
                    if self.last_processed_timestamp is not None:
                        # Solo loguear cierre si NO es la primera vela
                        previous_dt = datetime.utcfromtimestamp(self.last_processed_timestamp)
                        logger.info(
                            f"🔔 VELA ACTIVA CERRÓ | {previous_dt.strftime('%H:%M:%S')} -> "
                            f"{candle_dt.strftime('%H:%M:%S')} | Nueva vela detectada"
                        )
                    # ------------------------------
                    
                    logger.info(
                        f"🕯️ VELA CERRADA DETECTADA | {Config.IQOPTION.asset} | "
                        f"{candle_dt.strftime('%Y-%m-%d %H:%M:%S')} | "
                        f"O:{candle.open:.5f} H:{candle.high:.5f} "
                        f"L:{candle.low:.5f} C:{candle.close:.5f}"
                    )
                    
                    # Procesar con AnalysisService
                    if self.analysis_service:
                        await self.analysis_service.process_realtime_candle(candle)
                    
                    # Actualizar timestamp procesado
                    self.last_processed_timestamp = candle_timestamp
                
                # Esperar antes de la siguiente iteración
                await asyncio.sleep(self._poll_interval)
                
            except asyncio.CancelledError:
                logger.info("🛑 Detection loop cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in detection loop: {e}", exc_info=True)
                # Esperar más tiempo en caso de error para no saturar logs
                await asyncio.sleep(5)
        
        logger.info("✅ Detection loop terminated")


def create_iq_option_service_async(
    analysis_service, 
    on_auth_failure_callback: Optional[Callable] = None
) -> IqOptionServiceAsync:
    """
    Factory function para crear el wrapper asíncrono de IQ Option.
    
    Args:
        analysis_service: Instancia de AnalysisService
        on_auth_failure_callback: Callback para fallos de autenticación
        
    Returns:
        IqOptionServiceAsync: Instancia del wrapper asíncrono
    """
    return IqOptionServiceAsync(
        analysis_service=analysis_service,
        on_auth_failure_callback=on_auth_failure_callback
    )

