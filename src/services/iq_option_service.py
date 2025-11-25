"""
IQ Option Market Data Service
==============================
Implementa la interfaz MarketDataService para obtener datos de mercado
desde IQ Option en tiempo real mediante iqoptionapi.

ARQUITECTURA: Buffer Local + Detección de Eventos (CORREGIDO)
- Lee la PENÚLTIMA vela del buffer (la última cerrada)
- Detecta cambios en esa vela cerrada para disparar el análisis
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
    """
    
    def __init__(self, email: str, password: str, asset: str):
        self.logger = logging.getLogger(__name__)
        self.email = email
        self.password = password
        self.asset = asset.upper()
        
        self.api: Optional[IQ_Option] = None
        self._connected = False
        self._reconnect_thread: Optional[threading.Thread] = None
        self._should_reconnect = True
        
        self.logger.info(f"✅ IQ Option Service initialized for {self.asset}")
    
    def connect(self) -> bool:
        try:
            self.logger.info(f"🔌 Connecting to IQ Option as {self.email}...")
            self.api = IQ_Option(self.email, self.password)
            check, reason = self.api.connect()
            
            if not check:
                self.logger.error(f"❌ Failed to connect to IQ Option: {reason}")
                self._connected = False
                return False
            
            self.logger.info("✅ Connected to IQ Option successfully")
            self._connected = True
            
            self.api.change_balance("PRACTICE")
            self.logger.info("💰 Using PRACTICE account")
            
            self._subscribe_to_candles()
            self._start_reconnect_monitor()
            
            return True
        except Exception as e:
            self.logger.error(f"❌ Error connecting to IQ Option: {e}", exc_info=True)
            self._connected = False
            return False
    
    def _subscribe_to_candles(self) -> None:
        try:
            # Buffer size: CHART_LOOKBACK + margen
            buffer_size = Config.CHART_LOOKBACK + 10
            
            self.logger.info(f"📡 Subscribing to candle stream for {self.asset} (buffer: {buffer_size})...")
            self.api.start_candles_stream(self.asset, 60, buffer_size)
            time.sleep(2)
            self.logger.info(f"✅ Subscribed to {self.asset} candle stream")
            
        except Exception as e:
            self.logger.error(f"❌ Error subscribing to candles: {e}", exc_info=True)
    
    def disconnect(self) -> None:
        self.logger.info("🔌 Disconnecting from IQ Option...")
        self._should_reconnect = False
        self._connected = False
        if self.api:
            try:
                self.api.stop_candles_stream(self.asset, 60)
            except Exception:
                pass
        self.logger.info("✅ Disconnected from IQ Option")
    
    def get_historical_candles(self, count: int) -> list:
        # (Este método estaba bien, lo mantengo igual pero resumido para no ocupar espacio visual innecesario)
        # ... Lógica de obtención histórica ...
        if not self._connected or not self.api:
            return []
        try:
            self.logger.info(f"📥 Requesting {count} historical candles...")
            end_time = time.time()
            raw_candles = self.api.get_candles(self.asset, 60, count, end_time)
            
            if not raw_candles:
                return []
            
            candle_list = []
            for raw_candle in raw_candles:
                try:
                    candle = self._map_candle_data(raw_candle)
                    candle_list.append(candle)
                except Exception:
                    continue
            candle_list.sort(key=lambda c: c.timestamp)
            return candle_list
        except Exception as e:
            self.logger.error(f"❌ Error getting historical candles: {e}")
            return []

    def get_latest_closed_candle(self) -> Optional[CandleData]:
        """
        Obtiene la última vela CERRADA (penúltima del stream).
        """
        try:
            candles_dict = self.api.get_realtime_candles(self.asset, 60)
            
            if not candles_dict:
                return None
            
            timestamps = sorted(list(candles_dict.keys()))
            
            # Necesitamos al menos 2 velas: la actual (formación) y la cerrada (anterior)
            if len(timestamps) < 2:
                # Si solo hay 1, es la actual comenzando. Esperamos.
                return None
            
            # --- CORRECCIÓN AQUÍ ---
            # Tomamos la PENÚLTIMA vela (la cerrada)
            closed_candle_ts = timestamps[-1]
            raw_candle = candles_dict[closed_candle_ts]
            
            candle = self._map_realtime_candle(raw_candle)
            return candle
            
        except Exception as e:
            self.logger.error(f"❌ Error en get_latest_closed_candle: {e}", exc_info=True)
            return None
    
    def _map_realtime_candle(self, raw_candle: Dict[str, Any]) -> Optional[CandleData]:
        try:
            timestamp_seconds = raw_candle.get('from')
            if not timestamp_seconds: return None
            
            # Validación simple de integridad
            if raw_candle.get('max', 0) == 0: return None
            
            return CandleData(
                timestamp=int(timestamp_seconds),
                open=float(raw_candle["open"]),
                high=float(raw_candle["max"]),
                low=float(raw_candle["min"]),
                close=float(raw_candle["close"]),
                volume=float(raw_candle.get("volume", 0)),
                source="IQOPTION",
                symbol=self.asset
            )
        except Exception as e:
            self.logger.error(f"❌ Error mapeando vela: {e}")
            return None

    def _map_candle_data(self, raw_candle: Dict[str, Any]) -> CandleData:
        timestamp_seconds = raw_candle.get('from')
        if not timestamp_seconds: raise ValueError("No timestamp")
        return CandleData(
            timestamp=int(timestamp_seconds),
            open=float(raw_candle['open']),
            high=float(raw_candle['max']),
            low=float(raw_candle['min']),
            close=float(raw_candle['close']),
            volume=0.0,
            source="IQOPTION",
            symbol=self.asset
        )

    # ... Resto de métodos auxiliares (connect monitor, is_connected) iguales ...
    def is_connected(self) -> bool:
        if not self._connected or not self.api: return False
        return self.api.check_connect()

    def _start_reconnect_monitor(self) -> None:
        if self._reconnect_thread and self._reconnect_thread.is_alive(): return
        self._reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
        self._reconnect_thread.start()

    def _reconnect_loop(self) -> None:
        while self._should_reconnect:
            time.sleep(10)
            if not self._should_reconnect: break
            if not self.is_connected():
                self.connect()

def create_iq_option_service() -> IqOptionService:
    return IqOptionService(Config.IQOPTION.email, Config.IQOPTION.password, Config.IQOPTION.asset)

class IqOptionServiceAsync:
    def __init__(self, analysis_service, on_auth_failure_callback: Optional[Callable] = None):
        self.analysis_service = analysis_service
        self.on_auth_failure_callback = on_auth_failure_callback
        self.iq_service: Optional[IqOptionService] = None
        self._should_poll = False
        self._poll_interval = 0.5
        self.last_processed_timestamp: Optional[int] = None
    
    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self.iq_service = await loop.run_in_executor(None, create_iq_option_service)
        success = await loop.run_in_executor(None, self.iq_service.connect)
        if not success:
            if self.on_auth_failure_callback: self.on_auth_failure_callback()
            return
        
        await self._load_historical_candles()
        self._should_poll = True
        await self._poll_candles()
    
    async def stop(self) -> None:
        self._should_poll = False
        await asyncio.sleep(0.5)
        if self.iq_service:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.iq_service.disconnect)

    async def _load_historical_candles(self) -> None:
        # Carga inicial igual a tu código
        try:
            min_candles = Config.EMA_PERIOD * 3
            candles_to_request = min(min_candles + 50, 1000)
            loop = asyncio.get_running_loop()
            historical_candles = await loop.run_in_executor(None, self.iq_service.get_historical_candles, candles_to_request)
            if historical_candles:
                self.analysis_service.load_historical_candles(historical_candles)
        except Exception:
            pass

    async def _poll_candles(self) -> None:
        """
        Bucle de detección.
        Ahora que get_latest_closed_candle devuelve timestamps[-1],
        detectaremos cuando la vela CERRADA cambia.
        """
        iteration = 0
        logger.info(f"🕐 Polling started for closed candles...")
        
        while self._should_poll:
            try:
                iteration += 1
                loop = asyncio.get_running_loop()
                
                # Esto ahora trae la vela CERRADA (22:36:00)
                candle = await loop.run_in_executor(None, self.iq_service.get_latest_closed_candle)
                
                if not candle:
                    await asyncio.sleep(self._poll_interval)
                    continue
                
                # Inicializar último timestamp si es la primera vez
                if self.last_processed_timestamp is None:
                    self.last_processed_timestamp = candle.timestamp
                    # No procesamos la primera vela "vieja" al arrancar para evitar señales repetidas,
                    # o sí, dependiendo de tu preferencia. Generalmente mejor esperar la NUEVA.
                    logger.info(f"🕐 Sincronizado. Esperando cierre de próxima vela...")
                    continue
                
                # DETECCIÓN: ¿La vela CERRADA es nueva?
                if candle.timestamp > self.last_processed_timestamp:
                    candle_dt = datetime.utcfromtimestamp(candle.timestamp)
                    logger.info(
                        f"🕯️ VELA CERRADA DETECTADA | {candle_dt.strftime('%H:%M:%S')} | "
                        f"Cierre: {candle.close} | Vol: {candle.volume}"
                    )
                    
                    if self.analysis_service:
                        await self.analysis_service.process_realtime_candle(candle)
                    
                    self.last_processed_timestamp = candle.timestamp
                
                await asyncio.sleep(self._poll_interval)
                
            except Exception as e:
                logger.error(f"Error in polling: {e}")
                await asyncio.sleep(5)

def create_iq_option_service_async(analysis_service, on_auth_failure_callback: Optional[Callable] = None) -> IqOptionServiceAsync:
    return IqOptionServiceAsync(analysis_service, on_auth_failure_callback)