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
        
        self.logger.info(
            f"✅ IQ Option Multi-Service inicializado | "
            f"Instrumentos: {', '.join(self.target_assets)}"
        )

    # def _hijack_websocket_stream(self):
    #     """
    #     DEPRECATED: Monkey Patch para interceptar mensajes crudos del WebSocket.
    #     Se ha reemplazado por el método de polling directo al buffer de la librería.
    #     """
    #     pass

    def _get_symbol_by_id(self, active_id: int) -> Optional[str]:
        """
        Intenta resolver el nombre del símbolo a partir de su ID.
        """
        if not active_id:
            return None
            
        # 1. Intentar usar la API si tiene el método
        try:
            if hasattr(self.api, 'get_name_by_active_id'):
                name = self.api.get_name_by_active_id(active_id)
                if name:
                    return name.replace("t.c.", "").upper()
        except:
            pass
            
        # 2. Fallback: Iterar sobre nuestros assets y ver si podemos hacer match
        # Esto es difícil sin un mapa. Asumiremos que si solo hay 1 activo, es ese.
        if len(self.target_assets) == 1:
            return self.target_assets[0]
            
        return None
    
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
            
            # INTERCEPTAR WEBSOCKET (Monkey Patch) - DESACTIVADO
            # print("DEBUG: Calling _hijack_websocket_stream from connect...")
            # self._hijack_websocket_stream()
            
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
        """
        Suscribe a los streams de velas usando el método estándar de la librería.
        Esto es necesario para que get_realtime_candles() tenga datos.
        """
        buffer_size = Config.SNAPSHOT_CANDLES
        
        for symbol in self.target_assets:
            try:
                self.logger.info(f"📡 Suscribiendo a stream de velas para {symbol}...")
                
                # Método estándar de la librería para iniciar el stream
                # Esto llena el diccionario self.api.real_time_candles
                # MODIFICADO: Usar Config.SNAPSHOT_CANDLES para asegurar histórico inicial suficiente
                self.api.start_candles_stream(symbol, 60, buffer_size)
                
                self.logger.info(f"✅ Suscripción iniciada para {symbol}")
                
            except Exception as e:
                self.logger.error(f"❌ Error suscribiendo a {symbol}: {e}")
    
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
    
    def get_latest_candles_snapshot(self, symbol: str, count: int = 3) -> List[Dict]:
        """
        Obtiene una instantánea de las últimas 'count' velas del buffer en tiempo real.
        """
        try:
            # self.logger.debug(f"📸 Solicitando snapshot para {symbol}...")
            # Obtener buffer completo (maxdict=60 por defecto en la librería)
            candles_dict = self.api.get_realtime_candles(symbol, 60)
            
            if not candles_dict:
                self.logger.warning(f"⚠️ Buffer vacío para {symbol}")
                return []
            
            # Ordenar por timestamp
            timestamps = sorted(list(candles_dict.keys()))
            
            # Filtrar las últimas 'count'
            last_timestamps = timestamps[-count:] if count > 0 else timestamps
            
            # Construir lista de resultados
            snapshot = []
            for ts in last_timestamps:
                snapshot.append(candles_dict[ts])
                
            # self.logger.debug(f"✅ Snapshot obtenido para {symbol}: {len(snapshot)} velas")
            return snapshot
            
        except Exception as e:
            self.logger.error(f"❌ Error en get_latest_candles_snapshot para {symbol}: {e}")
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
        """
        Loop de reconexión automática con backoff exponencial.
        Utiliza RECONNECT_INITIAL_TIMEOUT y RECONNECT_MAX_TIMEOUT de la configuración.
        """
        attempt = 0
        current_timeout = Config.RECONNECT_INITIAL_TIMEOUT
        
        while self._should_reconnect:
            time.sleep(1) # Chequeo frecuente de conexión
            
            if not self._should_reconnect:
                break
                
            if not self.is_connected():
                self.logger.warning(f"🔄 Conexión perdida. Intentando reconectar en {current_timeout}s... (Intento {attempt + 1})")
                
                # Esperar el tiempo de backoff
                time.sleep(current_timeout)
                
                if self.connect():
                    self.logger.info("✅ Reconexión exitosa")
                    # Resetear contadores
                    attempt = 0
                    current_timeout = Config.RECONNECT_INITIAL_TIMEOUT
                else:
                    attempt += 1
                    # Backoff exponencial: duplicar tiempo hasta el máximo
                    current_timeout = min(current_timeout * 2, Config.RECONNECT_MAX_TIMEOUT)
                    self.logger.error(f"❌ Fallo al reconectar. Próximo intento en {current_timeout}s")


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
        self._poll_interval = 1
        self.poll_tasks: List[asyncio.Task] = []
        
        # Tracking por instrumento
        self.last_processed_timestamps: Dict[str, Optional[int]] = {}
        
        # Nuevas variables de rastreo de timestamps
        self.last_candle_timestamps: Dict[str, int] = {}    # Última vela cerrada (usada en gráfico)
        self.current_candle_timestamps: Dict[str, int] = {} # Vela generándose actualmente

    def _update_candle_timestamps(self, symbol: str, closed_ts: int, generating_ts: int) -> None:
        """
        Actualiza los timestamps de seguimiento para un instrumento.
        """
        self.last_candle_timestamps[symbol] = closed_ts
        self.current_candle_timestamps[symbol] = generating_ts
    
    async def start(self) -> None:
        """Inicia el servicio asíncrono."""
        loop = asyncio.get_running_loop()
        
        logger.debug("Iniciando IqOptionServiceMultiAsync...")

        # Crear servicio en thread pool
        self.iq_service = await loop.run_in_executor(
            None,
            create_iq_option_multi_service
        )

        logger.debug("Servicio creado en thread pool...")
        
        # Conectar
        success = await loop.run_in_executor(None, self.iq_service.connect)
        if not success:
            logger.error("❌ Fallo al conectar a IQ Option")
            if self.on_auth_failure_callback:
                self.on_auth_failure_callback()
            return
        
        logger.debug("Conectado a IQ Option...")
                
        # Iniciar polling para cada instrumento (ANTES de cargar históricos para evitar bloqueos)
        self._should_poll = True
        for symbol in Config.TARGET_ASSETS:
            task = asyncio.create_task(self._poll_instrument(symbol))
            self.poll_tasks.append(task)
    
        logger.debug("Polling iniciado...")
        
        logger.info(
            f"🚀 IQ Option Multi-Service iniciado | "
            f"Monitoreando {len(Config.TARGET_ASSETS)} instrumentos | "
            f"Tareas de polling: {len(self.poll_tasks)}"
        )

        # Cargar datos históricos para cada instrumento
        await self._load_all_historical_candles()
        
        logger.debug("Datos históricos cargados...")
        
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
        
        # Desconectar
        if self.iq_service:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.iq_service.disconnect)
    
    async def _load_all_historical_candles(self) -> None:
        """Carga velas históricas BID para todos los instrumentos."""
        min_candles = Config.EMA_PERIOD * 3
        # Solicitamos +1 vela para tener margen de descartar la última (generándose)
        candles_to_request = min(min_candles + 1, 1000)
        
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
                    # ---------------------------------------------------------
                    # MODIFICACIÓN: Separar última vela (generándose) de las históricas (cerradas)
                    # ---------------------------------------------------------
                    
                    # La última vela de la lista es la que se está generando actualmente
                    current_generating_candle = historical_candles[-1]
                    
                    # Las velas cerradas son todas menos la última
                    closed_candles = historical_candles[:-1]
                    
                    if not closed_candles:
                        logger.warning(f"⚠️ Pocas velas históricas para {symbol}, no se pudo separar cerrada/actual")
                        continue

                    # Guardar timestamps usando helper
                    last_closed_candle = closed_candles[-1]
                    self._update_candle_timestamps(
                        symbol, 
                        last_closed_candle.timestamp, 
                        current_generating_candle.timestamp
                    )
                    
                    # Imprimir Debug con horas legibles
                    last_closed_time = datetime.fromtimestamp(last_closed_candle.timestamp).strftime('%Y-%m-%d %H:%M:%S')
                    current_gen_time = datetime.fromtimestamp(current_generating_candle.timestamp).strftime('%Y-%m-%d %H:%M:%S')
                    
                    logger.info(
                        f"⏱️ TIMESTAMPS INICIALES {symbol} | "
                        f"Última Cerrada: {last_closed_time} ({last_closed_candle.timestamp}) | "
                        f"Generando: {current_gen_time} ({current_generating_candle.timestamp})"
                    )

                    # Guardar en estado del instrumento (BID) - SOLO LAS CERRADAS
                    state = self.iq_service.instrument_states[symbol]
                    for candle in closed_candles:
                        await state.add_bid_candle(candle)
                
            except Exception as e:
                logger.error(
                    f"❌ Error cargando velas para {symbol}: {e}",
                    exc_info=True
                )

    async def _poll_instrument(self, symbol: str) -> None:
        """
        Loop de polling individual para un instrumento.
        Implementa estrategia "Sleep & Burst":
        1. Duerme hasta el segundo 59 del minuto actual.
        2. Despierta y hace polling de alta frecuencia (0.1s) al buffer interno.
        3. Detecta cambio de vela comparando con self.last_candle_timestamps.
        """
        logger.info(f"📡 Iniciando polling loop INTELIGENTE para {symbol}...")
        
        from datetime import datetime, timedelta
        
        while self._should_poll:
            try:
                # ---------------------------------------------------------
                # FASE 0: PRE-CHECK (Verificar si ya hay vela nueva antes de dormir)
                # ---------------------------------------------------------
                # Esto cubre el caso donde el proceso de arranque o el ciclo anterior
                # tomaron tiempo y justo cruzamos la frontera del minuto.
                await self._check_and_process_candle(symbol)

                # ---------------------------------------------------------
                # FASE 1: SLEEP (Dormir hasta el segundo 59.9)
                # ---------------------------------------------------------
                now = datetime.now()
                # Objetivo: Segundo 59 del minuto actual
                target_time = now.replace(second=59, microsecond=900000) # 59.9s
                
                if now > target_time:
                    # Si ya pasamos el 59.9, apuntar al siguiente minuto
                    target_time += timedelta(minutes=1)
                
                wait_seconds = (target_time - now).total_seconds()
                
                if wait_seconds > 0.1:
                    # logger.debug(f"💤 {symbol} durmiendo {wait_seconds:.2f}s hasta burst...")
                    await asyncio.sleep(wait_seconds)
                
                # ---------------------------------------------------------
                # FASE 2: BURST (Polling de Alta Frecuencia)
                # ---------------------------------------------------------
                # logger.debug(f"⚡ {symbol} iniciando BURST polling...")
                
                candle_detected = False
                burst_start = time.time()
                
                # Mantenemos el burst por un máximo de 5 segundos para seguridad
                while self._should_poll and (time.time() - burst_start < 5.0):
                    
                    if await self._check_and_process_candle(symbol):
                        candle_detected = True
                        break # Salir del burst, volver a dormir
                    
                    # Pequeña pausa en el burst para no saturar CPU (10ms - 100ms)
                    await asyncio.sleep(0.1)
                
                if not candle_detected:
                    pass

            except asyncio.CancelledError:
                logger.info(f"🛑 Polling cancelado para {symbol}")
                break
            except Exception as e:
                logger.error(f"❌ Error en polling loop de {symbol}: {e}", exc_info=True)
                await asyncio.sleep(1.0)


    async def _check_and_process_candle(self, symbol: str) -> bool:
        """
        Verifica si hay una nueva vela cerrada en el buffer y la procesa.
        También detecta GAPS de datos (desconexiones) y los rellena.
        Retorna True si se detectó y procesó una nueva vela.
        """
        try:
            loop = asyncio.get_running_loop()
            snapshot = await loop.run_in_executor(
                None,
                self.iq_service.get_latest_candles_snapshot,
                symbol,
                3 # Solo necesitamos las últimas 3 para ver el cambio
            )
            
            if snapshot and len(snapshot) >= 2:
                # La estructura del snapshot es cronológica: [..., antepenultima, penultima, ultima]
                # La "última" (índice -1) es la que se está generando (current)
                # La "penúltima" (índice -2) es la candidata a ser la nueva vela cerrada
                
                candidate_closed_candle = snapshot[-2]
                candidate_ts = int(candidate_closed_candle.get("from", 0))
                
                last_stored_ts = self.last_candle_timestamps.get(symbol, 0)
                
                # ---------------------------------------------------------
                # DETECCIÓN DE GAPS
                # ---------------------------------------------------------
                # Si la diferencia es mayor a 60s, perdimos velas intermedias
                if last_stored_ts > 0 and (candidate_ts - last_stored_ts) > 60:
                    logger.warning(f"⚠️ GAP DETECTADO en {symbol}: Última {last_stored_ts} -> Nueva {candidate_ts} (Diff: {candidate_ts - last_stored_ts}s)")
                    await self._fill_data_gaps(symbol, last_stored_ts, candidate_ts)
                    # Después de rellenar, actualizamos last_stored_ts para que el siguiente check pase normal
                    last_stored_ts = self.last_candle_timestamps.get(symbol, 0)

                # Si el timestamp de la candidata es MAYOR que el último almacenado,
                # significa que se ha cerrado una nueva vela.
                if candidate_ts > last_stored_ts:
                    logger.info(f"🕯️ NUEVA VELA DETECTADA {symbol} | TS: {candidate_ts} (Anterior: {last_stored_ts})")
                    
                    # Procesar la nueva vela cerrada
                    await self._process_new_candle(symbol, candidate_closed_candle, snapshot[-1])
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error en check_and_process_candle {symbol}: {e}")
            return False

    async def _fill_data_gaps(self, symbol: str, last_stored_ts: int, current_ts: int) -> None:
        """
        Rellena huecos de datos solicitando velas históricas.
        Respeta la regla de NO incluir la vela en generación.
        """
        try:
            # Calcular cuántas velas faltan
            # Ejemplo: Last=100, Current=340. Diff=240. Missing = 240/60 = 4 velas.
            # Queremos las velas 160, 220, 280, 340.
            # Pero ojo, 'current_ts' es la vela CERRADA más reciente que vimos en el snapshot.
            
            missing_seconds = current_ts - last_stored_ts
            candles_needed = int(missing_seconds / 60)
            
            if candles_needed <= 0:
                return

            logger.info(f"📥 Rellenando GAP de {candles_needed} velas para {symbol}...")
            
            # Solicitamos +1 por seguridad, aunque 'current_ts' ya es cerrada.
            # La API de IQ devuelve las últimas N velas hasta AHORA.
            # Si pedimos N, nos dará hasta la que se está generando.
            # Por eso pedimos candles_needed + 1 (la generándose) y filtramos.
            
            loop = asyncio.get_running_loop()
            historical_candles = await loop.run_in_executor(
                None,
                self.iq_service.get_historical_candles,
                symbol,
                candles_needed + 2 # Margen de seguridad
            )
            
            if not historical_candles:
                logger.warning(f"⚠️ No se pudieron recuperar velas para el gap de {symbol}")
                return

            # Filtrar: Queremos velas > last_stored_ts y <= current_ts
            # Y descartamos explícitamente cualquier vela > current_ts (la generándose)
            
            gap_candles = []
            for candle in historical_candles:
                if candle.timestamp > last_stored_ts and candle.timestamp <= current_ts:
                    gap_candles.append(candle)
            
            if gap_candles:
                logger.info(f"✅ Recuperadas {len(gap_candles)} velas de gap para {symbol}")
                
                state = self.iq_service.instrument_states.get(symbol)
                
                for candle in gap_candles:
                    # 1. Actualizar Estado
                    if state:
                        await state.add_bid_candle(candle)
                        async with state.lock:
                            state.mid_candles.append(candle)
                    
                    # 2. Enviar a Analysis
                    if self.analysis_service:
                        # Procesar como histórica o realtime? 
                        # Mejor load_historical para no disparar alertas masivas, 
                        # o process_realtime si queremos que se analicen.
                        # Dado que es recuperación, 'process_realtime_candle' es más seguro 
                        # para que el bot "se ponga al día" con señales.
                        await self.analysis_service.process_realtime_candle(candle)
                
                # Actualizar timestamp final
                # (El último de gap_candles debería ser current_ts)
                last_gap_candle = gap_candles[-1]
                # No actualizamos 'current_candle_timestamp' aquí porque eso depende de la vela generándose,
                # que se actualizará en el siguiente ciclo normal o en process_new_candle.
                # Pero sí actualizamos last_candle_timestamps para evitar re-procesar.
                self.last_candle_timestamps[symbol] = last_gap_candle.timestamp
                
        except Exception as e:
            logger.error(f"❌ Error rellenando gap para {symbol}: {e}", exc_info=True)

    async def _process_new_candle(self, symbol: str, closed_candle_dict: Dict, new_generating_candle_dict: Dict) -> None:
        """
        Procesa una nueva vela cerrada detectada durante el polling.
        """
        try:
            # 1. Actualizar Timestamps
            closed_ts = int(closed_candle_dict.get("from", 0))
            generating_ts = int(new_generating_candle_dict.get("from", 0))
            
            self._update_candle_timestamps(symbol, closed_ts, generating_ts)
            
            # 2. Mapear a objeto CandleData
            # Usamos el helper del servicio síncrono
            closed_candle = self.iq_service._map_realtime_candle(closed_candle_dict, symbol)
            
            if closed_candle:
                # 3. Actualizar Estado (InstrumentState)
                state = self.iq_service.instrument_states.get(symbol)
                if state:
                    # Añadir a buffers (BID y MID)
                    # Nota: Al venir de IQ, es data BID. Asumimos MID = BID para el cierre histórico
                    await state.add_bid_candle(closed_candle)
                    
                    # Para el buffer MID, lo añadimos directamente
                    # (En un futuro podríamos refinar esto si tuviéramos ticks reales de cierre)
                    async with state.lock:
                        state.mid_candles.append(closed_candle)
                
                # 4. Enviar a Analysis Service
                if self.analysis_service:
                    await self.analysis_service.process_realtime_candle(closed_candle)
                    
                # Log de confirmación
                closed_time_str = datetime.fromtimestamp(closed_ts).strftime('%H:%M:%S')
                logger.info(f"✅ Vela procesada {symbol} @ {closed_time_str} | Close: {closed_candle.close}")
                
        except Exception as e:
            logger.error(f"❌ Error procesando nueva vela {symbol}: {e}", exc_info=True)


def create_iq_option_service_multi_async(
    analysis_service,
    on_auth_failure_callback: Optional[Callable] = None
) -> IqOptionServiceMultiAsync:
    """Factory function para crear el servicio asíncrono multi-instrumento."""
    return IqOptionServiceMultiAsync(analysis_service, on_auth_failure_callback)
