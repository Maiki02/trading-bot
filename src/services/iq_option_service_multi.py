"""
IQ Option Multi-Instrument Market Data Service
===============================================
Refactored service for handling multiple instruments simultaneously with dual buffer system.
Implements tick-based MID price calculation from BID/ASK spreads.

ARCHITECTURE:
- Single WebSocket connection
- Multiple instrument subscriptions
- Dual buffer system: BID (raw) + MID (synthetic from ticks)
- Asynchronous tick processing per instrument
- Real-time candle construction from tick aggregation

Author: Trading Bot Team
"""

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Callable, List
from iqoptionapi.stable_api import IQ_Option

from config import Config
from src.services.connection_service import CandleData
from src.services.instrument_state import InstrumentState, TickData
import json
import os

logger = logging.getLogger(__name__)


class CandleTicker:
    """
    Tick Processor - Procesa ticks en tiempo real y construye velas MID.
    Responsable de calcular Mid_Price = (Bid + Ask) / 2 de forma asíncrona.
    """
    
    def __init__(self, instrument_states: Dict[str, InstrumentState]):
        """
        Inicializa el procesador de ticks.
        
        Args:
            instrument_states: Diccionario de estados por símbolo
        """
        self.instrument_states = instrument_states
        self.is_running = False
        self.tick_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self.processor_task: Optional[asyncio.Task] = None
        
        logger.info("📊 CandleTicker inicializado")
    
    async def start(self) -> None:
        """Inicia el procesamiento de ticks en background."""
        self.is_running = True
        self.processor_task = asyncio.create_task(self._process_tick_queue())
        logger.info("🚀 CandleTicker iniciado")
    
    async def stop(self) -> None:
        """Detiene el procesamiento de ticks."""
        self.is_running = False
        if self.processor_task:
            self.processor_task.cancel()
            try:
                await self.processor_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 CandleTicker detenido")
    
    async def process_tick(self, tick: TickData) -> Optional[CandleData]:
        """
        Encola un tick para procesamiento asíncrono.
        
        Args:
            tick: Datos del tick (BID/ASK)
            
        Returns:
            None (procesamiento asíncrono)
        """
        try:
            await self.tick_queue.put(tick)
        except asyncio.QueueFull:
            logger.warning(f"⚠️  Cola de ticks llena para {tick.symbol}. Descartando tick.")
    
    async def _process_tick_queue(self) -> None:
        """Loop de procesamiento de ticks en background."""
        logger.info("🔄 Iniciando loop de procesamiento de ticks...")
        
        while self.is_running:
            try:
                tick = await asyncio.wait_for(self.tick_queue.get(), timeout=1.0)
                
                # Procesar tick y construir vela MID si se cierra un minuto
                state = self.instrument_states.get(tick.symbol)
                if state:
                    closed_candle = await state.process_tick(tick)
                    
                    if closed_candle:
                        logger.info(
                            f"🕯️ VELA MID CERRADA | {tick.symbol} | "
                            f"T={closed_candle.timestamp} | "
                            f"O={closed_candle.open:.5f} H={closed_candle.high:.5f} "
                            f"L={closed_candle.low:.5f} C={closed_candle.close:.5f}"
                        )
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"❌ Error procesando tick: {e}", exc_info=True)


class IqOptionMultiService:
    """
    Servicio multi-instrumento para IQ Option.
    Gestiona múltiples activos simultáneamente con buffers BID/MID separados.
    """
    
    def __init__(self, email: str, password: str, target_assets: List[str]):
        """
        Inicializa el servicio multi-instrumento.
        
        Args:
            email: Email de IQ Option
            password: Password de IQ Option
            target_assets: Lista de símbolos a monitorear (ej: ["EURUSD", "GBPUSD"])
        """
        self.logger = logging.getLogger(__name__)
        self.email = email
        self.password = password
        self.target_assets = [asset.upper() for asset in target_assets]
        
        self.api: Optional[IQ_Option] = None
        self._connected = False
        self._reconnect_thread: Optional[threading.Thread] = None
        self._should_reconnect = True
        
        # Estado por instrumento
        self.instrument_states: Dict[str, InstrumentState] = {
            symbol: InstrumentState(symbol=symbol)
            for symbol in self.target_assets
        }
        
        # Tick processor
        self.candle_ticker: Optional[CandleTicker] = None
        
        self.logger.info(
            f"✅ IQ Option Multi-Service inicializado | "
            f"Instrumentos: {', '.join(self.target_assets)}"
        )

    def _hijack_websocket_stream(self):
        """
        Intercepta el tráfico WebSocket de bajo nivel para capturar campos 'bid' y 'ask'
        que la librería estándar descarta u oculta.
        """
        print("DEBUG: Attempting to hijack websocket stream...")
        if not self.api or not hasattr(self.api, 'api') or not self.api.api.websocket_client:
            self.logger.error("❌ No se puede interceptar WebSocket: API no inicializada o estructura desconocida")
            print("DEBUG: Hijack failed - API structure mismatch")
            return

        print("DEBUG: API structure verified. Hijacking...")
        original_on_message = self.api.api.websocket_client.on_message

        def custom_on_message(wss, message):
            print(f"DEBUG: WS Message received: {message[:50]}...")
            # 1. Persistencia de Datos Crudos (Audit Log)
            try:
                # Asegurar directorio
                log_dir = Path("data/debug")
                log_dir.mkdir(parents=True, exist_ok=True)
                
                with open(log_dir / "raw_stream.jsonl", "a", encoding="utf-8") as f:
                    f.write(str(message) + "\n")
            except Exception:
                pass # No bloquear por logging

            # 2. Extracción de Inteligencia (Bid/Ask)
            try:
                data = json.loads(message)
                
                # Detectar evento candle-generated
                if data.get("name") == "candle-generated":
                    msg_data = data.get("msg", {})
                    symbol = msg_data.get("active_id") # Ojo: active_id suele ser int, mapping necesario si usamos str
                    # En iqoptionapi, el active_id viene en el mensaje.
                    # Pero para simplificar, intentaremos extraer del contenido si es posible
                    # O confiar en que el 'active_id' mapea a nuestro symbol.
                    # La librería hace este mapeo internamente.
                    
                    # NOTA: El mensaje raw de candle-generated suele tener esta estructura:
                    # {"name":"candle-generated","msg":{"active_id":1,"size":60,"at":1732628066,"from":1732628040,"to":1732628100,"id":551234,"volume":12,"open":1.0485,"close":1.04855,"min":1.0485,"max":1.04855,"ask":1.04866,"bid":1.04844,"phase":"E"}}
                    
                    # Necesitamos mapear active_id a Symbol nombre (ej: 1 -> EURUSD)
                    # self.api.instruments_categories tiene info, pero es complejo.
                    # Estrategia: Iterar sobre nuestros target_assets y ver si coincide el ID
                    # O más simple: Si tenemos el symbol en el contexto, bien. Si no, difícil.
                    # Afortunadamente, la librería ya procesa esto.
                    # Pero nosotros queremos interceptar ANTES.
                    
                    # Vamos a intentar extraer bid/ask y pasarlo si podemos identificar el activo.
                    # Si no podemos identificarlo fácil, quizás debamos confiar en que el usuario solo opera pocos pares
                    # y podemos deducirlo o hacer un lookup reverso si tenemos el mapa.
                    
                    # HACK: Por ahora, asumiremos que si encontramos bid/ask, intentamos matchear
                    # con nuestros instrumentos suscritos.
                    
                    # Mejor approach: Usar el diccionario de la api si está disponible
                    # self.api.get_name_by_active_id(active_id)
                    
                    active_id = msg_data.get("active_id")
                    if active_id:
                        # Intentar obtener nombre
                        try:
                            # Este método existe en algunas versiones de iqoptionapi, si no, fallback
                            symbol_name = self.api.get_name_by_active_id(active_id).replace("t.c.", "").upper()
                        except:
                            symbol_name = None
                        
                        if symbol_name and symbol_name in self.target_assets:
                            bid = msg_data.get("bid")
                            ask = msg_data.get("ask")
                            
                            if bid is not None and ask is not None:
                                tick = TickData(
                                    timestamp=float(msg_data.get("at", time.time())),
                                    bid=float(bid),
                                    ask=float(ask),
                                    symbol=symbol_name
                                )
                                
                                # Inyectar directamente
                                if self.candle_ticker:
                                    # Usar create_task para no bloquear el websocket thread
                                    # Pero process_tick es async, y estamos en sync callback.
                                    # Necesitamos un loop.
                                    
                                    # HACK: Acceder al loop del ticker o crear tarea thread-safe
                                    if self.candle_ticker.is_running and self.candle_ticker.processor_task:
                                         # Encolar de forma thread-safe
                                         loop = self.candle_ticker.processor_task.get_loop()
                                         if loop.is_running():
                                             asyncio.run_coroutine_threadsafe(
                                                 self.candle_ticker.process_tick(tick),
                                                 loop
                                             )

            except Exception as e:
                # self.logger.error(f"Error parsing websocket message: {e}")
                pass

            # 3. Ejecución Original
            original_on_message(wss, message)

        # Aplicar el parche
        self.api.api.websocket_client.on_message = custom_on_message
        self.logger.info("🕵️ WebSocket Stream Hijacked successfully")
    
    def connect(self) -> bool:
        """Establece conexión con IQ Option."""
        try:
            self.logger.info(f"🔌 Conectando a IQ Option como {self.email}...")
            self.api = IQ_Option(self.email, self.password)
            check, reason = self.api.connect()
            
            if not check:
                self.logger.error(f"❌ Fallo al conectar: {reason}")
                self._connected = False
                return False
            
            self.logger.info("✅ Conectado a IQ Option exitosamente")
            self._connected = True
            
            # Cambiar a cuenta PRACTICE
            self.api.change_balance("PRACTICE")
            self.logger.info("💰 Usando cuenta PRACTICE")
            
            # INTERCEPTAR WEBSOCKET (Monkey Patch)
            print("DEBUG: Calling _hijack_websocket_stream from connect...")
            self._hijack_websocket_stream()
            
            # Suscribirse a todos los instrumentos
            self._subscribe_to_all_instruments()
            
            # Iniciar monitor de reconexión
            self._start_reconnect_monitor()
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error conectando: {e}", exc_info=True)
            self._connected = False
            return False
    
    def _subscribe_to_all_instruments(self) -> None:
        """Suscribe a los streams de velas para todos los instrumentos."""
        buffer_size = Config.CHART_LOOKBACK + 10
        
        for symbol in self.target_assets:
            try:
                self.logger.info(
                    f"📡 Suscribiendo a {symbol} (buffer: {buffer_size})..."
                )
                self.api.start_candles_stream(symbol, 60, buffer_size)
                time.sleep(0.5)  # Evitar rate limiting
                self.logger.info(f"✅ Suscrito a {symbol}")
                print(f"DEBUG: Successfully subscribed to {symbol}")
                
            except Exception as e:
                self.logger.error(f"❌ Error suscribiendo a {symbol}: {e}")
                print(f"DEBUG: Failed to subscribe to {symbol}: {e}")
    
    def disconnect(self) -> None:
        """Desconecta de IQ Option."""
        self.logger.info("🔌 Desconectando de IQ Option...")
        self._should_reconnect = False
        self._connected = False
        
        if self.api:
            try:
                for symbol in self.target_assets:
                    self.api.stop_candles_stream(symbol, 60)
            except Exception:
                pass
        
        self.logger.info("✅ Desconectado de IQ Option")
    
    def get_historical_candles(self, symbol: str, count: int) -> List[CandleData]:
        """
        Obtiene velas históricas BID para un instrumento.
        
        Args:
            symbol: Símbolo del instrumento
            count: Cantidad de velas a obtener
            
        Returns:
            Lista de CandleData (BID)
        """
        if not self._connected or not self.api:
            return []
        
        try:
            self.logger.info(f"📥 Solicitando {count} velas históricas para {symbol}...")
            end_time = time.time()
            raw_candles = self.api.get_candles(symbol, 60, count, end_time)
            
            if not raw_candles:
                return []
            
            candle_list = []
            for raw_candle in raw_candles:
                try:
                    candle = self._map_candle_data(raw_candle, symbol)
                    candle_list.append(candle)
                except Exception:
                    continue
            
            candle_list.sort(key=lambda c: c.timestamp)
            self.logger.info(f"✅ Obtenidas {len(candle_list)} velas para {symbol}")
            return candle_list
            
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo velas para {symbol}: {e}")
            return []
    
    def get_latest_closed_candle(self, symbol: str) -> Optional[CandleData]:
        """
        Obtiene la última vela BID CERRADA (penúltima del stream).
        
        Args:
            symbol: Símbolo del instrumento
            
        Returns:
            CandleData BID o None
        """
        try:
            candles_dict = self.api.get_realtime_candles(symbol, 60)
            
            if not candles_dict:
                return None
            
            timestamps = sorted(list(candles_dict.keys()))
            
            if len(timestamps) < 2:
                return None
            
            # Penúltima vela (cerrada)
            closed_candle_ts = timestamps[-1]
            raw_candle = candles_dict[closed_candle_ts]
            
            candle = self._map_realtime_candle(raw_candle, symbol)
            return candle
            
        except Exception as e:
            self.logger.error(f"❌ Error en get_latest_closed_candle para {symbol}: {e}")
            return None
    
    def get_current_tick(self, symbol: str) -> Optional[TickData]:
        """
        Obtiene el tick actual (BID/ASK) para un instrumento.
        NOTA: IQ Option API no expone directamente BID/ASK separados en tiempo real.
        Esta implementación usa la vela actual como proxy.
        
        Args:
            symbol: Símbolo del instrumento
            
        Returns:
            TickData o None
        """
        try:
            candles_dict = self.api.get_realtime_candles(symbol, 60)
            
            if not candles_dict:
                return None
            
            timestamps = sorted(list(candles_dict.keys()))
            if len(timestamps) < 1:
                return None
            
            # Última vela (en formación)
            current_ts = timestamps[-1]
            raw_candle = candles_dict[current_ts]
            
            # Simular BID/ASK usando close ± spread estimado
            # NOTA: Esto es una aproximación. IQ Option no expone BID/ASK reales.
            close_price = float(raw_candle.get("close", 0))
            estimated_spread = 0.00002  # 0.2 pips para EURUSD
            
            tick = TickData(
                timestamp=float(raw_candle.get("from", time.time())),
                bid=close_price - estimated_spread / 2,
                ask=close_price + estimated_spread / 2,
                symbol=symbol
            )
            
            return tick
            
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo tick para {symbol}: {e}")
            return None
    
    def _map_realtime_candle(self, raw_candle: Dict, symbol: str) -> Optional[CandleData]:
        """Mapea vela en tiempo real a CandleData BID."""
        try:
            timestamp_seconds = raw_candle.get('from')
            if not timestamp_seconds:
                return None
            
            if raw_candle.get('max', 0) == 0:
                return None
            
            return CandleData(
                timestamp=int(timestamp_seconds),
                open=float(raw_candle["open"]),
                high=float(raw_candle["max"]),
                low=float(raw_candle["min"]),
                close=float(raw_candle["close"]),
                volume=float(raw_candle.get("volume", 0)),
                source="IQOPTION_BID",
                symbol=symbol
            )
        except Exception as e:
            self.logger.error(f"❌ Error mapeando vela: {e}")
            return None
    
    def _map_candle_data(self, raw_candle: Dict, symbol: str) -> CandleData:
        """Mapea vela histórica a CandleData BID."""
        timestamp_seconds = raw_candle.get('from')
        if not timestamp_seconds:
            raise ValueError("No timestamp")
        
        return CandleData(
            timestamp=int(timestamp_seconds),
            open=float(raw_candle['open']),
            high=float(raw_candle['max']),
            low=float(raw_candle['min']),
            close=float(raw_candle['close']),
            volume=float(raw_candle.get('volume', 0)),
            source="IQOPTION_BID",
            symbol=symbol
        )
    
    def is_connected(self) -> bool:
        """Verifica si está conectado."""
        if not self._connected or not self.api:
            return False
        return self.api.check_connect()
    
    def _start_reconnect_monitor(self) -> None:
        """Inicia thread de monitoreo de reconexión."""
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return
        
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            daemon=True
        )
        self._reconnect_thread.start()
    
    def _reconnect_loop(self) -> None:
        """Loop de reconexión automática."""
        while self._should_reconnect:
            time.sleep(10)
            if not self._should_reconnect:
                break
            if not self.is_connected():
                self.logger.warning("🔄 Conexión perdida. Reintentando...")
                self.connect()


def create_iq_option_multi_service() -> IqOptionMultiService:
    """Factory function para crear el servicio multi-instrumento."""
    return IqOptionMultiService(
        Config.IQOPTION.email,
        Config.IQOPTION.password,
        Config.TARGET_ASSETS
    )


class IqOptionServiceMultiAsync:
    """
    Wrapper asíncrono para IqOptionMultiService.
    Implementa polling de múltiples instrumentos en paralelo.
    """
    
    def __init__(
        self,
        analysis_service,
        on_auth_failure_callback: Optional[Callable] = None
    ):
        """
        Inicializa el wrapper asíncrono.
        
        Args:
            analysis_service: Servicio de análisis
            on_auth_failure_callback: Callback para fallos de autenticación
        """
        self.analysis_service = analysis_service
        self.on_auth_failure_callback = on_auth_failure_callback
        self.iq_service: Optional[IqOptionMultiService] = None
        self._should_poll = False
        self._poll_interval = 0.5
        self.poll_tasks: List[asyncio.Task] = []
        
        # Tracking por instrumento
        self.last_processed_timestamps: Dict[str, Optional[int]] = {}
    
    async def start(self) -> None:
        """Inicia el servicio asíncrono."""
        loop = asyncio.get_running_loop()
        
        # Crear servicio en thread pool
        self.iq_service = await loop.run_in_executor(
            None,
            create_iq_option_multi_service
        )
        
        # Conectar
        success = await loop.run_in_executor(None, self.iq_service.connect)
        if not success:
            if self.on_auth_failure_callback:
                self.on_auth_failure_callback()
            return
        
        # Cargar datos históricos para cada instrumento
        await self._load_all_historical_candles()
        
        # Iniciar CandleTicker
        self.iq_service.candle_ticker = CandleTicker(
            self.iq_service.instrument_states
        )
        await self.iq_service.candle_ticker.start()
        
        # Iniciar polling para cada instrumento
        self._should_poll = True
        for symbol in Config.TARGET_ASSETS:
            task = asyncio.create_task(self._poll_instrument(symbol))
            self.poll_tasks.append(task)
        
        logger.info(
            f"🚀 IQ Option Multi-Service iniciado | "
            f"Monitoreando {len(Config.TARGET_ASSETS)} instrumentos | "
            f"Tareas de polling: {len(self.poll_tasks)}"
        )
        
        # CRÍTICO: Esperar a que las tareas de polling terminen (mantiene el programa vivo)
        try:
            logger.info("⏳ Esperando tareas de polling...")
            await asyncio.gather(*self.poll_tasks)
        except asyncio.CancelledError:
            logger.info("🛑 Tareas de polling canceladas")
        except Exception as e:
            logger.error(f"❌ Error en tareas de polling: {e}", exc_info=True)
    
    async def stop(self) -> None:
        """Detiene el servicio asíncrono."""
        self._should_poll = False
        
        # Cancelar tasks de polling
        for task in self.poll_tasks:
            task.cancel()
        
        if self.poll_tasks:
            await asyncio.gather(*self.poll_tasks, return_exceptions=True)
        
        # Detener CandleTicker
        if self.iq_service and self.iq_service.candle_ticker:
            await self.iq_service.candle_ticker.stop()
        
        # Desconectar
        if self.iq_service:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.iq_service.disconnect)
    
    async def _load_all_historical_candles(self) -> None:
        """Carga velas históricas BID para todos los instrumentos."""
        min_candles = Config.EMA_PERIOD * 3
        candles_to_request = min(min_candles + 50, 1000)
        
        loop = asyncio.get_running_loop()
        
        for symbol in Config.TARGET_ASSETS:
            try:
                logger.info(
                    f"📥 Cargando {candles_to_request} velas BID para {symbol}..."
                )
                
                historical_candles = await loop.run_in_executor(
                    None,
                    self.iq_service.get_historical_candles,
                    symbol,
                    candles_to_request
                )
                
                if historical_candles:
                    # Guardar en estado del instrumento
                    state = self.iq_service.instrument_states[symbol]
                    for candle in historical_candles:
                        await state.add_bid_candle(candle)
                    
                    # Cargar en AnalysisService si está disponible
                    if self.analysis_service:
                        self.analysis_service.load_historical_candles(
                            historical_candles
                        )
                    
                    logger.info(
                        f"✅ {len(historical_candles)} velas BID cargadas para {symbol}"
                    )
                
                # Opcional: Generar gráfico histórico si está habilitado
                if Config.GENERATE_HISTORICAL_CHARTS and len(historical_candles) > 0:
                    await self._generate_historical_chart(symbol, historical_candles)
                
            except Exception as e:
                logger.error(
                    f"❌ Error cargando velas para {symbol}: {e}",
                    exc_info=True
                )
    
    async def _generate_historical_chart(
        self,
        symbol: str,
        candles: List[CandleData]
    ) -> None:
        """
        Genera gráfico histórico inicial (opcional, si GENERATE_HISTORICAL_CHARTS=true).
        
        Args:
            symbol: Símbolo del instrumento
            candles: Lista de velas históricas
        """
        try:
            from src.utils.charting import generate_chart_base64
            import pandas as pd
            from datetime import datetime
            
            # Convertir a DataFrame
            df = pd.DataFrame([
                {
                    "timestamp": c.timestamp,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume
                }
                for c in candles
            ])
            
            # Generar gráfico
            chart_title = f"{symbol} - Initial Snapshot"
            chart_base64 = await asyncio.to_thread(
                generate_chart_base64,
                df,
                Config.CHART_LOOKBACK,
                chart_title
            )
            
            # Guardar en archivo
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            chart_dir = Path("data") / "charts" / symbol
            chart_dir.mkdir(parents=True, exist_ok=True)
            
            # Guardar snapshot de inicio (siempre sobrescribe o crea uno específico)
            chart_path = chart_dir / "boot_snapshot.png"
            
            import base64
            with open(chart_path, "wb") as f:
                f.write(base64.b64decode(chart_base64))
            
            logger.info(f"📊 Gráfico histórico guardado: {chart_path}")
            
        except Exception as e:
            logger.error(
                f"❌ Error generando gráfico para {symbol}: {e}",
                exc_info=True
            )
    
    async def _poll_instrument(self, symbol: str) -> None:
        """
        Loop de monitoreo para un instrumento específico.
        Ya no hace polling activo, solo verifica salud y loguea estado.
        La data real llega por el WebSocket interceptado.
        """
        iteration = 0
        logger.info(f"👀 Monitor iniciado para {symbol} (Polling desactivado)")
        
        # Inicializar timestamp
        self.last_processed_timestamps[symbol] = None
        
        while self._should_poll:
            try:
                iteration += 1
                
                # Log cada 60 segundos (si intervalo es 0.5s -> 120 iteraciones)
                if iteration % 120 == 0:
                    state = self.iq_service.instrument_states.get(symbol)
                    last_mid = state.get_latest_mid_candle() if state else None
                    last_bid = state.get_latest_bid_candle() if state else None
                    
                    mid_info = f"MID T={last_mid.timestamp}" if last_mid else "MID=None"
                    bid_info = f"BID T={last_bid.timestamp}" if last_bid else "BID=None"
                    
                    logger.info(f"💓 Monitor {symbol} | {mid_info} | {bid_info}")
                
                # Aquí podríamos implementar lógica de watchdog:
                # Si no llegan ticks en X segundos, intentar reconectar o alertar.
                
                await asyncio.sleep(self._poll_interval)
                
            except Exception as e:
                logger.error(f"❌ Error en monitor de {symbol}: {e}", exc_info=True)
                await asyncio.sleep(5)


def create_iq_option_service_multi_async(
    analysis_service,
    on_auth_failure_callback: Optional[Callable] = None
) -> IqOptionServiceMultiAsync:
    """Factory function para crear el servicio asíncrono multi-instrumento."""
    return IqOptionServiceMultiAsync(analysis_service, on_auth_failure_callback)
