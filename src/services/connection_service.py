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
        
        # Heartbeat
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.last_heartbeat: Optional[datetime] = None
    
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
        Detiene el servicio de conexión de forma limpia.
        """
        logger.info("🛑 Stopping Connection Service...")
        self.is_running = False
        
        # Cancelar heartbeat
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Cerrar WebSocket
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()
        
        logger.info("✅ Connection Service stopped")
    
    async def _connect_and_run(self) -> None:
        """
        Establece la conexión WebSocket y procesa mensajes.
        """
        headers = Config.get_websocket_headers()
        
        logger.info(f"📡 Connecting to {Config.TRADINGVIEW.ws_url}...")
        
        async with websockets.connect(
            Config.TRADINGVIEW.ws_url,
            extra_headers=headers,
            ping_interval=None,  # Usamos nuestro propio heartbeat
            ping_timeout=None
        ) as websocket:
            self.websocket = websocket
            self.reconnect_attempts = 0  # Reset en conexión exitosa
            
            logger.info("✅ WebSocket connected successfully")
            
            # Handshake y autenticación
            await self._authenticate()
            
            # Suscripciones a instrumentos
            await self._subscribe_instruments()
            
            # Iniciar heartbeat
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            # Loop de recepción de mensajes
            await self._message_loop()
    
    async def _authenticate(self) -> None:
        """
        Realiza la autenticación con TradingView usando el SessionID.
        """
        logger.info("🔐 Authenticating with TradingView...")
        
        # Enviar token de autenticación
        auth_message = encode_message("set_auth_token", [Config.TRADINGVIEW.session_id])
        await self.websocket.send(auth_message)
        
        # Crear quote session
        quote_session_message = encode_message("quote_create_session", [self.quote_session_id])
        await self.websocket.send(quote_session_message)
        
        # Establecer data quality (verificar que no sea "delayed")
        quality_message = encode_message(
            "quote_set_fields",
            [
                self.quote_session_id,
                "ch", "chp", "current_session", "description", "local_description",
                "language", "exchange", "fractional", "is_tradable", "lp", "lp_time",
                "minmov", "minmove2", "original_name", "pricescale", "pro_name",
                "short_name", "type", "update_mode", "volume", "currency_code",
                "rchp", "rtc", "status", "fundamentals", "rch", "rtc_time", "logoid"
            ]
        )
        await self.websocket.send(quality_message)
        
        self.is_authenticated = True
        logger.info("✅ Authentication successful")
    
    async def _subscribe_instruments(self) -> None:
        """
        Suscribe a los instrumentos configurados (OANDA y FX).
        """
        for key, instrument in Config.INSTRUMENTS.items():
            logger.info(f"📊 Subscribing to {instrument.full_symbol} ({key})...")
            
            # Generar chart session ID único
            chart_session_id = instrument.chart_session_id
            self.chart_sessions[key] = chart_session_id
            
            # Crear chart session
            create_session_msg = encode_message("chart_create_session", [chart_session_id])
            await self.websocket.send(create_session_msg)
            
            # Solicitar snapshot de datos históricos (1000 velas)
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
                    Config.TRADINGVIEW.snapshot_candles
                ]
            )
            await self.websocket.send(create_series_msg)
            
            logger.info(f"✅ Subscribed to {instrument.full_symbol}")
        
        await asyncio.sleep(1)  # Dar tiempo para que el servidor procese
    
    async def _heartbeat_loop(self) -> None:
        """
        Envía heartbeats periódicos para mantener la conexión viva.
        """
        try:
            while self.is_running:
                if self.websocket and not self.websocket.closed:
                    heartbeat_msg = encode_message("quote_heartbeat", [self.quote_session_id])
                    await self.websocket.send(heartbeat_msg)
                    self.last_heartbeat = datetime.now()
                    logger.debug("💓 Heartbeat sent")
                
                await asyncio.sleep(30)  # Cada 30 segundos
        except asyncio.CancelledError:
            logger.debug("Heartbeat task cancelled")
        except Exception as e:
            log_exception(logger, "Error in heartbeat loop", e)
    
    async def _message_loop(self) -> None:
        """
        Loop principal de recepción y procesamiento de mensajes.
        """
        try:
            async for raw_message in self.websocket:
                if not self.is_running:
                    break
                
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
            
            # Detectar fallo de autenticación
            if method == "critical_error" or method == "error":
                error_msg = params[0] if params else "Unknown error"
                logger.error(f"❌ TradingView Error: {error_msg}")
                
                if "authorization" in error_msg.lower() or "session" in error_msg.lower():
                    log_critical_auth_failure(logger)
                    if self.on_auth_failure_callback:
                        self.on_auth_failure_callback()
                    self.is_running = False
            
            # Procesar datos de velas
            elif method == "timescale_update":
                await self._parse_candle_data(params)
            
            # Confirmaciones de protocolo
            elif method in ["protocol_switched", "quote_completed", "series_completed"]:
                logger.debug(f"Protocol confirmation: {method}")
    
    async def _parse_candle_data(self, params: List[Any]) -> None:
        """
        Parsea datos de velas desde los parámetros del mensaje.
        
        Args:
            params: Parámetros del mensaje timescale_update
        """
        if len(params) < 2:
            return
        
        chart_session_id = params[0]
        data_payload = params[1]
        
        # Identificar la fuente (OANDA o FX)
        source = None
        for key, session_id in self.chart_sessions.items():
            if session_id == chart_session_id:
                source = Config.INSTRUMENTS[key].exchange
                symbol = Config.INSTRUMENTS[key].symbol
                break
        
        if not source:
            return
        
        # Extraer datos de velas del payload
        if isinstance(data_payload, dict) and "s" in data_payload:
            for series in data_payload["s"]:
                if "v" in series:  # v = values (OHLCV)
                    candle_values = series["v"]
                    
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
                        
                        logger.debug(
                            f"📊 Candle received from {source}: "
                            f"C={candle.close:.5f} @ {candle.timestamp}"
                        )
                        
                        # Invocar callback
                        if self.on_candle_callback:
                            self.on_candle_callback(candle)
    
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
            f"🔄 Reconnection attempt {self.reconnect_attempts}/{self.max_reconnect_attempts} "
            f"in {delay}s..."
        )
        
        await asyncio.sleep(delay)
