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
        on_candle_callback: Callable[[CandleData], None],
        on_auth_failure_callback: Optional[Callable[[], None]] = None
    ):
        """
        Inicializa el servicio de conexión.
        
        Args:
            on_candle_callback: Callback invocado cuando se recibe una vela nueva
            on_auth_failure_callback: Callback invocado si la autenticación falla
        """
        self.on_candle_callback = on_candle_callback
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
                logger.info("Keyboard interrupt received. Shutting down...")
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
        logger.info("🛑 Stopping Connection Service...")
        self.is_running = False
        
        # Cancelar message task si existe
        if self.message_task and not self.message_task.done():
            self.message_task.cancel()
            try:
                await self.message_task
            except asyncio.CancelledError:
                logger.debug("Message task cancelled")
        
        # Cerrar chart sessions y quote session de forma limpia
        if self.websocket and not self.websocket.closed:
            try:
                logger.debug("📤 Sending close messages to TradingView...")
                
                # Cerrar cada chart session
                for key, chart_session_id in self.chart_sessions.items():
                    close_chart_msg = encode_message("remove_series", [chart_session_id, "s1"])
                    await self.websocket.send(close_chart_msg)
                    logger.debug(f"✅ Closed chart session: {chart_session_id}")
                
                # Cerrar quote session
                close_quote_msg = encode_message("quote_remove_symbols", [self.quote_session_id])
                await self.websocket.send(close_quote_msg)
                logger.debug(f"✅ Closed quote session: {self.quote_session_id}")
                
                # Dar tiempo para que se envíen los mensajes
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.warning(f"⚠️  Error sending close messages: {e}")
            finally:
                # Cerrar WebSocket
                await self.websocket.close()
                logger.debug("🔌 WebSocket connection closed")
        
        logger.info("✅ Connection Service stopped cleanly")
    
    async def _connect_and_run(self) -> None:
        """
        Establece la conexión WebSocket y procesa mensajes.
        """
        headers = Config.get_websocket_headers()
        
        logger.info(f"📡 Connecting to {Config.TRADINGVIEW.ws_url}...")
        
        async with websockets.connect(
            Config.TRADINGVIEW.ws_url,
            extra_headers=headers,
            ping_interval=20,  # Ping cada 20 segundos para mantener la conexión viva
            ping_timeout=20,   # Timeout de ping 20 segundos
            close_timeout=10   # Timeout al cerrar 10 segundos
        ) as websocket:
            self.websocket = websocket
            self.reconnect_attempts = 0  # Reset en conexión exitosa
            
            logger.info("✅ WebSocket connected successfully")
            
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
        logger.info("🔐 Initializing TradingView session...")
        
        # Crear quote session
        self.quote_session_id = generate_session_id("qs")
        quote_session_message = encode_message("quote_create_session", [self.quote_session_id])
        await self.websocket.send(quote_session_message)
        logger.debug(f"📤 Created quote session: {self.quote_session_id}")
        
        # NO enviar auth token - usar modo público
        # Los datos en tiempo real están disponibles sin autenticación
        
        # Pequeña pausa para que el servidor procese
        await asyncio.sleep(0.3)
        
        self.is_authenticated = True
        logger.info("✅ Session initialized (public mode)")
    
    async def _subscribe_instruments(self) -> None:
        """
        Suscribe a los instrumentos configurados (OANDA y FX).
        Solo solicita snapshot histórico en la primera conexión.
        """
        # Determinar cuántas velas solicitar
        snapshot_candles = Config.TRADINGVIEW.snapshot_candles if self.first_connection else 10
        
        for key, instrument in Config.INSTRUMENTS.items():
            logger.info(f"📊 Subscribing to {instrument.full_symbol} ({key})...")
            
            # Generar chart session ID único
            chart_session_id = instrument.chart_session_id
            self.chart_sessions[key] = chart_session_id
            
            # Crear chart session
            create_session_msg = encode_message("chart_create_session", [chart_session_id])
            await self.websocket.send(create_session_msg)
            
            # Solicitar snapshot de datos históricos
            if self.first_connection:
                logger.info(f"📥 Requesting {snapshot_candles} candles (first connection)")
            
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
                    snapshot_candles  # Usar valor dinámico
                ]
            )
            await self.websocket.send(create_series_msg)
            
            logger.info(f"✅ Subscribed to {instrument.full_symbol}")
        
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
                logger.info(f"🔔 MESSAGE RECEIVED | Method: {method}")
            
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
                
                await self._parse_candle_data(params)
            
            # Procesar actualizaciones en tiempo real (método 'du' = data update)
            elif method == "du":
                logger.info(f"🔄 DU MESSAGE | Params: {params[:2] if len(params) > 2 else params}")
                await self._parse_candle_data(params, is_realtime=True)
            
            # Confirmaciones de protocolo
            elif method in ["protocol_switched", "quote_completed"]:
                pass  # No loguear confirmaciones
            
            elif method == "series_completed":
                # Marcar snapshot como completado
                if params and len(params) >= 1:
                    chart_session_id = params[0]
                    self.snapshot_completed[chart_session_id] = True
                    logger.info(f"✅ Snapshot completed for {chart_session_id}. Real-time processing ACTIVE.")
    
    async def _parse_candle_data(self, params: List[Any], is_realtime: bool = False) -> None:
        """
        Parsea datos de velas desde los parámetros del mensaje.
        
        Args:
            params: Parámetros del mensaje timescale_update o du
            is_realtime: True si es un mensaje en tiempo real (post-snapshot)
        """
        logger.info(f"🔍 PARSING CANDLE DATA | Params length: {len(params)} | Realtime: {is_realtime}")
        
        if len(params) < 2:
            logger.warning(f"⚠️  PARSE FAILED | Not enough params: {len(params)}")
            return
        
        chart_session_id = params[0]
        data_payload = params[1]
        
        # Verificar si el snapshot ya se completó para esta sesión
        snapshot_done = self.snapshot_completed.get(chart_session_id, False)
        
        logger.info(f"🔍 Chart Session: {chart_session_id} | Payload type: {type(data_payload).__name__} | Snapshot done: {snapshot_done}")
        
        # Identificar la fuente (OANDA o FX)
        source = None
        symbol = None
        for key, session_id in self.chart_sessions.items():
            if session_id == chart_session_id:
                source = Config.INSTRUMENTS[key].exchange
                symbol = Config.INSTRUMENTS[key].symbol
                break
        
        if not source:
            logger.warning(f"⚠️  PARSE FAILED | Unknown chart session: {chart_session_id}")
            logger.warning(f"    Known sessions: {list(self.chart_sessions.values())}")
            return
        
        logger.info(f"🔍 Source identified: {source}:{symbol}")
        
        # Extraer datos de velas del payload
        if isinstance(data_payload, dict):
            logger.info(f"🔍 Payload keys: {list(data_payload.keys())}")
            
            # El método 'du' puede tener estructura anidada diferente
            # Buscar en diferentes ubicaciones posibles
            series_data = None
            
            if "s1" in data_payload:
                # Formato: params[1]["s1"]["s"][0]["v"]
                logger.info(f"🔍 Found 's1' key (du format)")
                s1_data = data_payload["s1"]
                if isinstance(s1_data, dict) and "s" in s1_data:
                    series_data = s1_data["s"]
            elif "s" in data_payload:
                # Formato: params[1]["s"][0]["v"]
                logger.info(f"🔍 Found 's' key (timescale_update format)")
                series_data = data_payload["s"]
            
            if series_data:
                logger.info(f"🔍 Processing {len(series_data)} series...")
                for series in series_data:
                    if "v" in series:  # v = values (OHLCV)
                        candle_values = series["v"]
                        logger.info(f"🔍 Candle values found: {candle_values}")
                        
                        # Formato típico: [timestamp, open, high, low, close, volume]
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
                            
                            # Log de vela recibida
                            logger.info(
                                f"🔵 CANDLE TICK | {source}:{symbol} | "
                                f"T={candle.timestamp} | C={candle.close:.5f} | V={candle.volume:.0f}"
                            )
                            
                            # Solo invocar callback si:
                            # 1. Es un mensaje en tiempo real (du), O
                            # 2. El snapshot ya se completó (series_completed recibido)
                            if is_realtime or snapshot_done:
                                if self.on_candle_callback:
                                    self.on_candle_callback(candle)
                            else:
                                logger.debug(
                                    f"📥 Historical candle buffered (no callback) | "
                                    f"T={candle.timestamp} | Snapshot in progress"
                                )
                        else:
                            logger.warning(f"⚠️  Candle values too short: {len(candle_values)}")
                    else:
                        logger.warning(f"⚠️  No 'v' key in series: {list(series.keys())}")
            else:
                logger.warning(f"⚠️  No series data found in payload")
        else:
            logger.warning(f"⚠️  Payload is not a dict: {type(data_payload).__name__}")
    
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
            
            logger.info(f"💾 Snapshot saved: {filename} ({source})")
            
        except Exception as e:
            log_exception(logger, f"Failed to save snapshot for {chart_session_id}", e)
    
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
