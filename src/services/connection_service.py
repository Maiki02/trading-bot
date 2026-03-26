"""
Connection Service - TradingView WebSocket Multiplexer
=======================================================
Maneja la conexión persistente con TradingView mediante WebSocket.
Implementa multiplexación para suscripciones múltiples, autenticación,
heartbeat, reconexión con backoff exponencial y graceful shutdown.

CRITICAL: Este módulo NO debe abrir múltiples sockets. Usa un solo socket
con múltiples suscripciones para evitar baneos de IP.

Author: TradingView Pattern Monitor Team
"""

import asyncio
import json
import random
import string
from typing import Dict, Callable, Optional, Any, List
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from config import Config, InstrumentConfig
from src.utils.logger import get_logger, log_exception, log_critical_auth_failure


logger = get_logger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class CandleData:
    """Estructura de datos para una vela recibida."""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str  # "OANDA" o "FX"
    symbol: str  # "EURUSD"


# =============================================================================
# TRADINGVIEW PROTOCOL HELPERS
# =============================================================================

def generate_session_id(prefix: str = "qs") -> str:
    """
    Genera un ID de sesión aleatorio para el protocolo de TradingView.
    
    Args:
        prefix: Prefijo del ID (qs para quote session, cs para chart session)
        
    Returns:
        str: Session ID único (ej: "qs_abc123xyz")
    """
    random_part = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
    return f"{prefix}_{random_part}"


def encode_message(func_name: str, params: List[Any]) -> str:
    """
    Codifica un mensaje en el formato del protocolo TradingView.
    
    Formato: ~m~<length>~m~<json_payload>
    
    Args:
        func_name: Nombre de la función a invocar
        params: Lista de parámetros
        
    Returns:
        str: Mensaje codificado
        
    Example:
        >>> encode_message("set_auth_token", ["your_token"])
        '~m~47~m~{"m":"set_auth_token","p":["your_token"]}'
    """
    payload = json.dumps({"m": func_name, "p": params})
    return f"~m~{len(payload)}~m~{payload}"


def decode_message(raw_message: str) -> List[Dict[str, Any]]:
    """
    Decodifica mensajes del protocolo TradingView.
    
    Args:
        raw_message: Mensaje crudo recibido del WebSocket
        
    Returns:
        List[Dict]: Lista de mensajes decodificados
    """
    messages = []
    parts = raw_message.split("~m~")
    
    i = 0
    while i < len(parts):
        if parts[i].isdigit():
            length = int(parts[i])
            if i + 1 < len(parts) and len(parts[i + 1]) == length:
                try:
                    data = json.loads(parts[i + 1])
                    messages.append(data)
                except json.JSONDecodeError:
                    pass
            i += 2
        else:
            i += 1
    
    return messages


# =============================================================================
# CONNECTION SERVICE
# =============================================================================

class ConnectionService:
    """
    Servicio de conexión WebSocket multiplexado para TradingView.
    
    Responsabilidades:
    - Establecer y mantener conexión WebSocket única
    - Autenticación con SessionID
    - Suscripción a múltiples instrumentos
    - Heartbeat automático
    - Reconexión con backoff exponencial
    - Procesamiento de mensajes entrantes
    """
    
    def __init__(
        self,
        analysis_service,  # Type hint se pone después para evitar imports circulares
        on_auth_failure_callback: Optional[Callable[[], None]] = None
    ):
        """
        Inicializa el servicio de conexión.
        
        Args:
            analysis_service: Instancia de AnalysisService para procesamiento de velas
            on_auth_failure_callback: Callback invocado si la autenticación falla
        """
        self.analysis_service = analysis_service
        self.on_auth_failure_callback = on_auth_failure_callback
        
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.is_running: bool = False
        self.is_authenticated: bool = False
        
        # Session IDs para el protocolo TradingView
        self.quote_session_id: str = generate_session_id("qs")
        self.chart_sessions: Dict[str, str] = {}  # key: "primary"/"secondary"
        
        # Control de reconexión
        self.reconnect_attempts: int = 0
        self.max_reconnect_attempts: int = 10
        
        # Tracking de snapshot inicial (para guardar en JSON)
        self.snapshot_received: Dict[str, bool] = {}
        self.snapshot_completed: Dict[str, bool] = {}  # Track cuando termina el snapshot
        self.first_connection: bool = True  # Flag para saber si es la primera conexión
        
        # Message task
        self.message_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """
        Inicia el servicio de conexión y entra en loop de reconexión.
        """
        self.is_running = True
        logger.info("🚀 Connection Service starting...")
        
        while self.is_running and self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                await self._connect_and_run()
            except KeyboardInterrupt:
                logger.info("Interrupción de teclado recibida. Cerrando...")
                break
            except Exception as e:
                log_exception(logger, "Unexpected error in connection loop", e)
                await self._handle_reconnection()
        
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.critical(
                f"⛔ Max reconnection attempts ({self.max_reconnect_attempts}) reached. "
                "Service stopped."
            )
    
    async def stop(self) -> None:
        """
        Detiene el servicio de conexión de forma limpia (graceful shutdown).
        Envía mensajes de cierre a TradingView antes de cerrar el WebSocket.
        """
        logger.info("🛑 Deteniendo Connection Service...")
        self.is_running = False
        
        # Cancelar message task si existe
        if self.message_task and not self.message_task.done():
            self.message_task.cancel()
            try:
                await self.message_task
            except asyncio.CancelledError:
                logger.debug("Tarea de mensajes cancelada")
        
        # Cerrar chart sessions y quote session de forma limpia
        if self.websocket and not self.websocket.closed:
            try:
                logger.debug("📤 Enviando mensajes de cierre a TradingView...")
                
                # Cerrar cada chart session
                for key, chart_session_id in self.chart_sessions.items():
                    close_chart_msg = encode_message("remove_series", [chart_session_id, "s1"])
                    await self.websocket.send(close_chart_msg)
                    logger.debug(f"✅ Sesión de gráfico cerrada: {chart_session_id}")
                
                # Cerrar quote session
                close_quote_msg = encode_message("quote_remove_symbols", [self.quote_session_id])
                await self.websocket.send(close_quote_msg)
                logger.debug(f"✅ Sesión de cotizaciones cerrada: {self.quote_session_id}")
                
                # Dar tiempo para que se envíen los mensajes
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.warning(f"⚠️  Error enviando mensajes de cierre: {e}")
            finally:
                # Cerrar WebSocket
                await self.websocket.close()
                logger.debug("🔌 Conexión WebSocket cerrada")
        
        logger.info("✅ Connection Service detenido correctamente")
    
    async def _connect_and_run(self) -> None:
        """
        Establece la conexión WebSocket y procesa mensajes.
        """
        headers = Config.get_websocket_headers()
        
        # Inyectar Cookie de autenticación si session_id está presente
        if Config.TRADINGVIEW.session_id and Config.TRADINGVIEW.session_id.strip():
            headers['Cookie'] = f"sessionid={Config.TRADINGVIEW.session_id}"
            logger.info(f"🔌 Conectando como Usuario Autenticado (Session ID presente)")
        else:
            logger.info(f"👤 Conectando como Invitado (Sin Session ID - Límites estrictos aplican)")
            logger.warning(f"⚠️  ADVERTENCIA: Sin autenticación, exchanges como FXCM/IDC pueden rechazar la conexión")
        
        logger.info(f"📡 Conectando a {Config.TRADINGVIEW.ws_url}...")
        
        async with websockets.connect(
            Config.TRADINGVIEW.ws_url,
            extra_headers=headers,
            ping_interval=30,  # Ping cada 30 segundos (reduce tráfico)
            ping_timeout=60,   # Timeout de 60s (tolerante a latencia/silencio temporal)
            close_timeout=10   # Timeout al cerrar 10 segundos
        ) as websocket:
            self.websocket = websocket
            self.reconnect_attempts = 0  # Reset en conexión exitosa
            
            logger.info("✅ WebSocket conectado exitosamente")
            
            # Handshake y autenticación
            await self._authenticate()
            
            # Suscripciones a instrumentos
            await self._subscribe_instruments()
            
            # Loop de recepción de mensajes (no se necesita heartbeat proactivo)
            await self._message_loop()
    
    async def _authenticate(self) -> None:
        """
        Inicializa sesiones de TradingView sin autenticación (modo público).
        Los datos en tiempo real están disponibles sin login.
        """
        logger.info("🔐 Inicializando sesión de TradingView...")
        
        # Crear quote session
        self.quote_session_id = generate_session_id("qs")
        quote_session_message = encode_message("quote_create_session", [self.quote_session_id])
        await self.websocket.send(quote_session_message)
        logger.debug(f"📤 Sesión de cotizaciones creada: {self.quote_session_id}")
        
        # NO enviar auth token - usar modo público
        # Los datos en tiempo real están disponibles sin autenticación
        
        # Pequeña pausa para que el servidor procese
        await asyncio.sleep(0.3)
        
        self.is_authenticated = True
        logger.info("✅ Sesión inicializada (modo público)")
    
    async def _subscribe_instruments(self) -> None:
        """
        Suscribe a los instrumentos configurados (OANDA y FX).
        Solo solicita snapshot histórico en la primera conexión.
        """
        # Determinar cuántas velas solicitar
        # Primera conexión: 1000 velas para llenar buffer
        # Reconexiones: 1 vela para obtener el estado actual
        snapshot_candles = Config.TRADINGVIEW.snapshot_candles if self.first_connection else 1
        
        for key, instrument in Config.INSTRUMENTS.items():
            logger.info(f"📊 Suscribiéndose a {instrument.full_symbol} ({key})...")
            
            # Generar chart session ID único
            chart_session_id = instrument.chart_session_id
            self.chart_sessions[key] = chart_session_id
            
            # Crear chart session
            create_session_msg = encode_message("chart_create_session", [chart_session_id])
            await self.websocket.send(create_session_msg)
            
            # Solicitar snapshot de datos históricos
            if self.first_connection:
                logger.info(f"📥 Solicitando {snapshot_candles} velas (primera conexión)")
            else:
                logger.info(f"🔄 Reconexión - continuando con buffer existente")
            
            resolve_symbol_msg = encode_message(
                "resolve_symbol",
                [
                    chart_session_id,
                    "symbol_1",
                    f"={json.dumps({'symbol': instrument.full_symbol, 'adjustment': 'splits'})}"
                ]
            )
            await self.websocket.send(resolve_symbol_msg)
            
            # Crear serie con timeframe 1m
            create_series_msg = encode_message(
                "create_series",
                [
                    chart_session_id,
                    "s1",
                    "s1",
                    "symbol_1",
                    instrument.timeframe,
                    snapshot_candles  # 1000 en primera conexión, 1 en reconexiones
                ]
            )
            await self.websocket.send(create_series_msg)
            
            logger.info(f"✅ Suscrito a {instrument.full_symbol}")
        
        # Marcar que ya no es la primera conexión
        if self.first_connection:
            self.first_connection = False
        
        await asyncio.sleep(1)  # Dar tiempo para que el servidor procese
    
    async def _message_loop(self) -> None:
        """
        Loop principal de recepción y procesamiento de mensajes.
        """
        try:
            async for raw_message in self.websocket:
                if not self.is_running:
                    break
                
                # Responder a heartbeat del servidor primero (antes de procesar)
                if raw_message.startswith("~h~"):
                    heartbeat_id = raw_message.split("~h~")[1] if "~h~" in raw_message else "1"
                    await self.websocket.send(f"~h~{heartbeat_id}")
                    continue
                
                await self._process_message(raw_message)
        except ConnectionClosed as e:
            logger.warning(f"⚠️  WebSocket connection closed: {e}")
            raise
        except WebSocketException as e:
            log_exception(logger, "WebSocket error", e)
            raise
    
    async def _process_message(self, raw_message: str) -> None:
        """
        Procesa un mensaje entrante del WebSocket.
        
        Args:
            raw_message: Mensaje crudo recibido
        """
        messages = decode_message(raw_message)
        
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            
            method = msg.get("m")
            params = msg.get("p", [])
            
            # Log de TODOS los métodos recibidos para debug
            if method:
                logger.info(f"📥 Mensaje recibido | Método: {method}")
            
            # Detectar fallo de autenticación o error de protocolo
            if method == "critical_error" or method == "error" or method == "protocol_error":
                error_msg = params[0] if params else "Unknown error"
                logger.error(f"❌ TradingView Error: {error_msg}")
                
                if "auth" in error_msg.lower() or "token" in error_msg.lower():
                    log_critical_auth_failure(logger)
                    if self.on_auth_failure_callback:
                        self.on_auth_failure_callback()
                    self.is_running = False
                    return
                
                if "authorization" in error_msg.lower() or "session" in error_msg.lower():
                    log_critical_auth_failure(logger)
                    if self.on_auth_failure_callback:
                        self.on_auth_failure_callback()
                    self.is_running = False
            
            # Procesar datos de velas (snapshot inicial)
            elif method == "timescale_update":
                # Si es el primer timescale_update para esta sesión, guardar snapshot
                if params and len(params) >= 2:
                    chart_session_id = params[0]
                    if chart_session_id not in self.snapshot_received:
                        await self._save_snapshot_to_file(chart_session_id, params)
                        self.snapshot_received[chart_session_id] = True
                
                # Procesar snapshot histórico (NO genera gráficos)
                await self._load_historical_snapshot(params)
            
            # Procesar actualizaciones en tiempo real (método 'du' = data update)
            elif method == "du":
                # logger.info(f"🔄 MENSAJE DU | Params: {params[:2] if len(params) > 2 else params}")
                # Procesar vela en tiempo real (SÍ genera gráficos)
                await self._process_realtime_update(params)
            
            # Errores de símbolo o serie
            elif method == "symbol_error":
                error_details = params[1] if len(params) > 1 else "Sin detalles"
                logger.error(f"❌ SYMBOL_ERROR | Símbolo no disponible o acceso denegado | Detalles: {error_details}")
            
            elif method == "series_error":
                error_details = params[1] if len(params) > 1 else "Sin detalles"
                logger.error(f"❌ SERIES_ERROR | Error al cargar series de datos | Detalles: {error_details}")
            
            # Confirmaciones de protocolo
            elif method in ["protocol_switched", "quote_completed"]:
                pass  # No loguear confirmaciones
            
            elif method == "series_completed":
                # Marcar snapshot como completado
                if params and len(params) >= 1:
                    chart_session_id = params[0]
                    self.snapshot_completed[chart_session_id] = True
                    logger.info(f"✅ Snapshot completado para {chart_session_id}. Procesamiento en tiempo real ACTIVO.")
    
    async def _load_historical_snapshot(self, params: List[Any]) -> None:
        """
        Procesa el snapshot inicial de 1000 velas históricas (timescale_update).
        NO genera gráficos ni envía notificaciones a Telegram.
        
        Args:
            params: Parámetros del mensaje timescale_update
                    [chart_session_id, series_id, data_payload]
        """
        logger.info(f"📥 CARGANDO SNAPSHOT HISTÓRICO | Longitud params: {len(params)}")
        
        if len(params) < 2:
            logger.warning(f"⚠️  CARGA DE SNAPSHOT FALLÓ | Params insuficientes: {len(params)}")
            return
        
        chart_session_id = params[0]
        data_payload = params[1]  # ✅ El payload está en params[1] para timescale_update
        
        # Identificar la fuente (OANDA o FX)
        source = None
        symbol = None
        source_key = None
        for key, session_id in self.chart_sessions.items():
            if session_id == chart_session_id:
                source = Config.INSTRUMENTS[key].exchange
                symbol = Config.INSTRUMENTS[key].symbol
                source_key = key
                break
        
        if not source:
            logger.warning(f"⚠️  CARGA DE SNAPSHOT FALLÓ | Sesión de gráfico desconocida: {chart_session_id}")
            return
        
        logger.info(f"📥 Cargando 1000 velas históricas para {source_key}...")
        
        # Extraer todas las velas del snapshot
        # ESTRUCTURA: params[1]["s1"]["s"] = array de 1000 objetos {i: index, v: [t,o,h,l,c,vol]}
        candle_list = []
        if isinstance(data_payload, dict) and "s1" in data_payload:
            s1_data = data_payload["s1"]
            if isinstance(s1_data, dict) and "s" in s1_data:
                series_data = s1_data["s"]
                
                for candle_obj in series_data:
                    if "v" in candle_obj:
                        candle_values = candle_obj["v"]
                        
                        if len(candle_values) >= 6:
                            candle = CandleData(
                                timestamp=int(candle_values[0]),
                                open=float(candle_values[1]),
                                high=float(candle_values[2]),
                                low=float(candle_values[3]),
                                close=float(candle_values[4]),
                                volume=float(candle_values[5]),
                                source=source,
                                symbol=symbol
                            )
                            candle_list.append(candle)
        
        # Cargar todas las velas de una vez en el AnalysisService
        if candle_list and self.analysis_service:
            if len(candle_list) == 1 and chart_session_id in self.snapshot_completed:
                # Si es UNA sola vela Y ya se completó el snapshot inicial, procesarla como tiempo real
                logger.info(f"✅ Cargada 1 vela cerrada. Procesando como tiempo real...")
                await self.analysis_service.process_realtime_candle(candle_list[0])
            elif len(candle_list) == 1:
                # Si es UNA vela pero es reconexión (sin snapshot previo), ignorarla
                logger.info(f"🔄 Reconexión detectada. Ignorando vela de sincronización. Continuando con buffer existente.")
            else:
                # Si son múltiples velas (snapshot inicial), cargarlas sin análisis
                logger.info(f"✅ Cargadas {len(candle_list)} velas históricas. Enviando a AnalysisService...")
                self.analysis_service.load_historical_candles(candle_list)
        else:
            logger.warning(f"⚠️  No se extrajeron velas del snapshot")
    
    async def _process_realtime_update(self, params: List[Any]) -> None:
        """
        Procesa una actualización en tiempo real (du) - una sola vela nueva.
        GENERA gráficos y envía notificaciones a Telegram cuando se detectan patrones.
        
        Args:
            params: Parámetros del mensaje du
        """
        # LOG COMENTADO: Demasiado verbose en producción
        # logger.info(f"🕒 PROCESANDO ACTUALIZACIÓN EN TIEMPO REAL | Longitud params: {len(params)}")
        
        if len(params) < 2:
            logger.warning(f"⚠️  ACTUALIZACIÓN EN TIEMPO REAL FALLÓ | Params insuficientes: {len(params)}")
            return
        
        chart_session_id = params[0]
        data_payload = params[1]
        
        # Identificar la fuente (OANDA o FX)
        source = None
        symbol = None
        for key, session_id in self.chart_sessions.items():
            if session_id == chart_session_id:
                source = Config.INSTRUMENTS[key].exchange
                symbol = Config.INSTRUMENTS[key].symbol
                break
        
        if not source:
            logger.warning(f"⚠️  ACTUALIZACIÓN EN TIEMPO REAL FALLÓ | Sesión de gráfico desconocida: {chart_session_id}")
            return
        
        # Extraer la vela del mensaje 'du'
        if isinstance(data_payload, dict) and "s1" in data_payload:
            s1_data = data_payload["s1"]
            if isinstance(s1_data, dict) and "s" in s1_data:
                series_data = s1_data["s"]
                
                # Solo debería haber UNA vela en un mensaje 'du'
                if len(series_data) > 0 and "v" in series_data[0]:
                    candle_values = series_data[0]["v"]
                    
                    if len(candle_values) >= 6:
                        candle = CandleData(
                            timestamp=int(candle_values[0]),
                            open=float(candle_values[1]),
                            high=float(candle_values[2]),
                            low=float(candle_values[3]),
                            close=float(candle_values[4]),
                            volume=float(candle_values[5]),
                            source=source,
                            symbol=symbol
                        )
                        
                        # Detectar si es actualización o nueva vela
                        candle_index = series_data[0].get("i", -1)
                        
                        # LOG COMENTADO: Demasiado verbose en producción
                        # logger.info(
                        #     f"🕒 ACTUALIZACIÓN VELA #{candle_index} | {source}:{symbol} | "
                        #     f"T={candle.timestamp} | O={candle.open:.5f} H={candle.high:.5f} "
                        #     f"L={candle.low:.5f} C={candle.close:.5f} | Vol={candle.volume:.0f}"
                        # )
                        
                        # Procesar vela en tiempo real - genera gráficos y alertas
                        if self.analysis_service:
                            await self.analysis_service.process_realtime_candle(candle)
                    else:
                        logger.warning(f"⚠️  Valores de vela muy cortos: {len(candle_values)}")
        else:
            logger.warning(f"⚠️  Formato de actualización en tiempo real inválido")
    
    async def _save_snapshot_to_file(self, chart_session_id: str, params: List[Any]) -> None:
        """
        Guarda el snapshot inicial de 1000 velas en un archivo JSON.
        
        Args:
            chart_session_id: ID de la sesión del gráfico
            params: Parámetros completos del mensaje timescale_update
        """
        try:
            # Crear directorio logs si no existe
            logs_dir = Path("logs")
            logs_dir.mkdir(exist_ok=True)
            
            # Identificar la fuente
            source = "unknown"
            for key, session_id in self.chart_sessions.items():
                if session_id == chart_session_id:
                    source = Config.INSTRUMENTS[key].exchange
                    break
            
            # Nombre del archivo con timestamp
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = logs_dir / f"snapshot_{source}_{timestamp_str}.json"
            
            # Preparar datos para guardar
            snapshot_data = {
                "chart_session_id": chart_session_id,
                "source": source,
                "timestamp": timestamp_str,
                "raw_params": params
            }
            
            # Guardar en archivo
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(snapshot_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Snapshot guardado: {filename} ({source})")
        
        except Exception as e:
            log_exception(logger, f"Fallo al guardar snapshot para {chart_session_id}", e)
    
    async def _handle_reconnection(self) -> None:
        """
        Maneja la lógica de reconexión con backoff exponencial.
        """
        self.reconnect_attempts += 1
        
        # Calcular delay con backoff exponencial
        delay = min(
            Config.RECONNECT_INITIAL_TIMEOUT * (2 ** (self.reconnect_attempts - 1)),
            Config.RECONNECT_MAX_TIMEOUT
        )
        
        logger.warning(
            f"🔄 RECONNECTION #{self.reconnect_attempts}/{self.max_reconnect_attempts} | "
            f"Waiting {delay}s before retry | Reason: Connection lost"
        )
        
        await asyncio.sleep(delay)


# =============================================================================
# MARKET DATA SERVICE FACTORY
# =============================================================================

def get_market_data_service(analysis_service, on_auth_failure_callback=None):
    """
    Factory function que retorna el servicio de datos de mercado configurado.
    
    Según la variable DATA_PROVIDER en config.py, instancia:
    - TradingViewService: Si DATA_PROVIDER == "TRADINGVIEW" (implementación pendiente)
    - IqOptionServiceMultiAsync: Si DATA_PROVIDER == "IQOPTION" (multi-instrumento con MID)
    
    Args:
        analysis_service: Instancia de AnalysisService para procesar velas
        on_auth_failure_callback: Callback para manejar fallos de autenticación
    
    Returns:
        MarketDataService: Instancia del servicio de datos configurado
        
    Raises:
        ValueError: Si DATA_PROVIDER no es válido
        
    Example:
        >>> from src.services.connection_service import get_market_data_service
        >>> service = get_market_data_service(analysis_service)
        >>> await service.start()
    """
    from config import Config
    
    if Config.DATA_PROVIDER == "TRADINGVIEW":
        logger.info(f"🔌 Using TradingView as data provider")
        return ConnectionService(
            analysis_service=analysis_service,
            on_auth_failure_callback=on_auth_failure_callback
        )
    
    elif Config.DATA_PROVIDER == "IQOPTION":
        logger.info(
            f"🔌 Using IQ Option Multi-Instrument as data provider | "
            f"Instruments: {', '.join(Config.TARGET_ASSETS)}"
        )
        from src.services.iq_option_service_multi import create_iq_option_service_multi_async
        return create_iq_option_service_multi_async(
            analysis_service=analysis_service,
            on_auth_failure_callback=on_auth_failure_callback
        )
    
    elif Config.DATA_PROVIDER == "QUOTEX":
        logger.info(
            f"🔌 Using Quotex Multi-Instrument as data provider | "
            f"Instruments: {', '.join(Config.TARGET_ASSETS)}"
        )
        from src.services.quotex_service_multi import create_quotex_service_multi_async
        return create_quotex_service_multi_async(
            analysis_service=analysis_service,
            on_auth_failure_callback=on_auth_failure_callback
        )
    
    else:
        raise ValueError(
            f"Invalid DATA_PROVIDER: {Config.DATA_PROVIDER}. "
            "Must be 'TRADINGVIEW', 'IQOPTION', or 'QUOTEX'"
        )

