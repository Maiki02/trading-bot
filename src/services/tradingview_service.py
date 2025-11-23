"""
TradingView Service - Historical Data Fetcher
==============================================
Servicio para solicitar datos históricos de TradingView mediante WebSocket.
Permite obtener una cantidad específica de velas para análisis de backtesting.

Author: TradingView Pattern Monitor Team
"""

import asyncio
import json
import random
import string
import websockets
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from config import Config
from src.utils.logger import get_logger


logger = get_logger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class HistoricalCandle:
    """Estructura de datos para una vela histórica."""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


# =============================================================================
# PROTOCOL HELPERS
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
            i += 1
            if i < len(parts):
                try:
                    message = json.loads(parts[i])
                    messages.append(message)
                except json.JSONDecodeError:
                    pass
        i += 1
    
    return messages


# =============================================================================
# TRADINGVIEW SERVICE
# =============================================================================

class TradingViewService:
    """
    Servicio para obtener datos históricos de TradingView.
    
    Este servicio establece una conexión temporal con TradingView,
    solicita N velas históricas y luego cierra la conexión.
    """
    
    def __init__(self):
        """Inicializa el servicio."""
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.candles: List[HistoricalCandle] = []
        self.data_received: asyncio.Event = asyncio.Event()
    
    async def fetch_historical_candles(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        num_candles: int
    ) -> List[HistoricalCandle]:
        """
        Obtiene velas históricas de TradingView.
        
        Args:
            symbol: Símbolo del instrumento (ej: "BTCUSDT", "EURUSD")
            exchange: Exchange (ej: "BINANCE", "OANDA", "FX")
            timeframe: Timeframe en minutos (ej: "1" para 1 minuto)
            num_candles: Número de velas a solicitar
            
        Returns:
            List[HistoricalCandle]: Lista de velas históricas ordenadas por timestamp
            
        Example:
            >>> service = TradingViewService()
            >>> candles = await service.fetch_historical_candles(
            ...     symbol="BTCUSDT",
            ...     exchange="BINANCE",
            ...     timeframe="1",
            ...     num_candles=1000
            ... )
            >>> print(f"Obtenidas {len(candles)} velas")
        """
        self.candles = []
        self.data_received.clear()
        
        headers = Config.get_websocket_headers()
        full_symbol = f"{exchange}:{symbol}"
        
        logger.info(f"🔌 Conectando a TradingView para obtener {num_candles} velas de {full_symbol}...")
        
        try:
            async with websockets.connect(
                Config.TRADINGVIEW.ws_url,
                extra_headers=headers,
                ping_interval=30,
                ping_timeout=60,
                close_timeout=10
            ) as websocket:
                self.websocket = websocket
                
                # Autenticar (modo público)
                await self._authenticate()
                
                # Solicitar datos históricos
                await self._request_historical_data(
                    full_symbol=full_symbol,
                    timeframe=timeframe,
                    num_candles=num_candles
                )
                
                # Esperar a recibir los datos (timeout 30s)
                try:
                    await asyncio.wait_for(self.data_received.wait(), timeout=30.0)
                    logger.info(f"✅ Recibidas {len(self.candles)} velas de {full_symbol}")
                except asyncio.TimeoutError:
                    logger.error(f"❌ Timeout esperando datos de {full_symbol}")
                
                return self.candles
        
        except Exception as e:
            logger.error(f"❌ Error obteniendo datos históricos: {e}")
            return []
    
    async def _authenticate(self) -> None:
        """Inicializa sesión de TradingView (modo público)."""
        quote_session_id = generate_session_id("qs")
        quote_session_message = encode_message("quote_create_session", [quote_session_id])
        await self.websocket.send(quote_session_message)
        await asyncio.sleep(0.3)
    
    async def _request_historical_data(
        self,
        full_symbol: str,
        timeframe: str,
        num_candles: int
    ) -> None:
        """
        Solicita datos históricos mediante el protocolo de TradingView.
        
        Args:
            full_symbol: Símbolo completo (ej: "BINANCE:BTCUSDT")
            timeframe: Timeframe en minutos
            num_candles: Número de velas a solicitar
        """
        chart_session_id = generate_session_id("cs")
        
        # Crear chart session
        create_session_msg = encode_message("chart_create_session", [chart_session_id])
        await self.websocket.send(create_session_msg)
        
        # Resolver símbolo
        resolve_symbol_msg = encode_message(
            "resolve_symbol",
            [
                chart_session_id,
                "symbol_1",
                f"={json.dumps({'symbol': full_symbol, 'adjustment': 'splits'})}"
            ]
        )
        await self.websocket.send(resolve_symbol_msg)
        
        # Crear serie con timeframe
        create_series_msg = encode_message(
            "create_series",
            [
                chart_session_id,
                "s1",
                "s1",
                "symbol_1",
                timeframe,
                num_candles
            ]
        )
        await self.websocket.send(create_series_msg)
        
        # Iniciar loop de mensajes
        await self._message_loop()
    
    async def _message_loop(self) -> None:
        """Loop de procesamiento de mensajes."""
        try:
            async for raw_message in self.websocket:
                if isinstance(raw_message, bytes):
                    raw_message = raw_message.decode("utf-8")
                
                # Responder a pings
                if raw_message.startswith("~h~"):
                    await self.websocket.send(raw_message)
                    continue
                
                # Procesar mensajes
                messages = decode_message(raw_message)
                for message in messages:
                    if "m" in message and message["m"] == "timescale_update":
                        await self._process_timescale_update(message.get("p", []))
                        # Señalizar que los datos fueron recibidos
                        self.data_received.set()
                        return  # Salir del loop
        
        except Exception as e:
            logger.error(f"❌ Error en message loop: {e}")
            self.data_received.set()  # Liberar el wait
    
    async def _process_timescale_update(self, params: List[Any]) -> None:
        """
        Procesa el mensaje timescale_update con las velas históricas.
        
        Args:
            params: Parámetros del mensaje [chart_session_id, data_payload]
        """
        if len(params) < 2:
            logger.warning(f"⚠️  Params insuficientes en timescale_update: {len(params)}")
            return
        
        data_payload = params[1]
        
        # Extraer velas del payload
        # ESTRUCTURA: params[1]["s1"]["s"] = array de objetos {i: index, v: [t,o,h,l,c,vol]}
        if isinstance(data_payload, dict) and "s1" in data_payload:
            s1_data = data_payload["s1"]
            if isinstance(s1_data, dict) and "s" in s1_data:
                series_data = s1_data["s"]
                
                for candle_obj in series_data:
                    if "v" in candle_obj:
                        candle_values = candle_obj["v"]
                        
                        if len(candle_values) >= 6:
                            candle = HistoricalCandle(
                                timestamp=int(candle_values[0]),
                                open=float(candle_values[1]),
                                high=float(candle_values[2]),
                                low=float(candle_values[3]),
                                close=float(candle_values[4]),
                                volume=float(candle_values[5])
                            )
                            self.candles.append(candle)
                
                logger.debug(f"📊 Extraídas {len(self.candles)} velas del payload")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def get_historical_candles(
    symbol: str,
    exchange: str,
    timeframe: str = "1",
    num_candles: int = 1000
) -> List[HistoricalCandle]:
    """
    Helper function para obtener velas históricas.
    
    Args:
        symbol: Símbolo del instrumento
        exchange: Exchange
        timeframe: Timeframe en minutos (default: "1")
        num_candles: Número de velas (default: 1000)
        
    Returns:
        List[HistoricalCandle]: Lista de velas históricas
    """
    service = TradingViewService()
    return await service.fetch_historical_candles(
        symbol=symbol,
        exchange=exchange,
        timeframe=timeframe,
        num_candles=num_candles
    )
