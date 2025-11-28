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
                    # Guardar en estado del instrumento (BID)
                    state = self.iq_service.instrument_states[symbol]
                    for candle in historical_candles:
                        await state.add_bid_candle(candle)
                    
                    # ---------------------------------------------------------
                    # FIX: Inicializar también el buffer MID y AnalysisService
                    # Usamos las velas BID históricas como proxy para las MID iniciales
                    # ---------------------------------------------------------
                    from dataclasses import replace
                    mid_historical_candles = [
                        replace(c, source="IQOPTION_MID") for c in historical_candles
                    ]
                    
                    # 1. Llenar buffer MID en InstrumentState
                    await state.initialize_mid_candles(mid_historical_candles)
                    
                    # 2. Cargar en AnalysisService (usando MID para que coincida con el stream)
                    if self.analysis_service:
                        self.analysis_service.load_historical_candles(
                            mid_historical_candles
                        )
                    
                    logger.info(
                        f"✅ {len(historical_candles)} velas cargadas (BID & MID) para {symbol}"
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
    
    async def _save_candle_chart(
        self,
        symbol: str,
        closed_candle: CandleData
    ) -> None:
        """
        Genera y guarda un gráfico cuando cierra una vela.
        
        Args:
            symbol: Símbolo del instrumento
            closed_candle: La vela que acaba de cerrar
        """
        try:
            from src.utils.charting import generate_chart_base64
            import pandas as pd
            from datetime import datetime
            
            # Obtener historial reciente para el contexto del gráfico
            state = self.iq_service.instrument_states.get(symbol)
            if not state:
                return
                
            # Usar velas MID ya que son las que estamos construyendo
            candles = state.get_mid_candles_list(Config.CHART_LOOKBACK)
            
            if not candles:
                return

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
            chart_title = f"{symbol} - {datetime.fromtimestamp(closed_candle.timestamp).strftime('%H:%M')}"
            chart_base64 = await asyncio.to_thread(
                generate_chart_base64,
                df,
                Config.CHART_LOOKBACK,
                chart_title
            )
            
            # Guardar en archivo
            # Formato: data/charts/{symbol}/{timestamp}.png
            timestamp_str = str(closed_candle.timestamp)
            chart_dir = Path("data") / "charts" / symbol
            chart_dir.mkdir(parents=True, exist_ok=True)
            
            chart_path = chart_dir / f"{timestamp_str}.png"
            
            import base64
            with open(chart_path, "wb") as f:
                f.write(base64.b64decode(chart_base64))
            
            logger.info(f"📊 Gráfico guardado: {chart_path}")
            
        except Exception as e:
            logger.error(
                f"❌ Error generando gráfico para {symbol}: {e}",
                exc_info=True
            )

    async def _poll_instrument(self, symbol: str) -> None:
        """
        Loop de polling individual para un instrumento.
        Implementa la estrategia de "Polling con Snapshot de Seguridad".
        """
        logger.info(f"📡 Iniciando polling loop para {symbol}...")
        
        # Variable local para mantener el último precio conocido (fallback)
        last_known_mid: Optional[float] = None
        
        while self._should_poll:
            try:
                # 1. Obtener snapshot PEQUEÑO (solo 3 velas)
                # No necesitamos 300 velas cada 0.5s
                loop = asyncio.get_running_loop()
                snapshot = await loop.run_in_executor(
                    None,
                    self.iq_service.get_latest_candles_snapshot,
                    symbol,
                    3
                )
                
                valid_tick_found = False
                tick_to_process: Optional[TickData] = None
                
                if snapshot:
                    # 2. Algoritmo de Selección de Datos ("La Estrategia de 3 Velas")
                    # Iterar en orden INVERSO (de la más nueva a la más vieja)
                    # para encontrar la primera vela con datos válidos.
                    
                    for candle in reversed(snapshot):
                        bid = candle.get("bid")
                        ask = candle.get("ask")
                        
                        # Verificar si tiene datos de precio válidos
                        if bid is not None and ask is not None:
                            # ¡Encontrado!
                            try:
                                bid_val = float(bid)
                                ask_val = float(ask)
                                # mid_val = (bid_val + ask_val) / 2.0  <-- REMOVED: Redundant calculation
                                
                                # Use 'close' as the authoritative MID price
                                mid_val = float(candle.get("close", (bid_val + ask_val) / 2.0))
                                
                                # Actualizar fallback
                                last_known_mid = mid_val
                                
                                # Crear TickData
                                tick_to_process = TickData(
                                    timestamp=float(candle.get("from", time.time())),
                                    bid=bid_val,
                                    ask=ask_val,
                                    symbol=symbol,
                                    custom_mid=mid_val  # Pass the explicit MID
                                )
                                valid_tick_found = True
                                break # Salir del loop apenas encontremos el dato más fresco
                            except (ValueError, TypeError):
                                continue
                
                # 3. Manejo de Fallback (si no se encontró dato válido en el snapshot)
                if not valid_tick_found:
                    if last_known_mid is not None:
                        # Usar último conocido para mantener el "latido"
                        # logger.warning(f"⚠️ [POLL] {symbol} sin datos frescos. Usando fallback MID={last_known_mid:.5f}")
                        
                        # Estimamos un spread artificial pequeño para reconstruir bid/ask
                        # Esto es solo para mantener vivo el ticker, el precio importante es el MID
                        spread_proxy = 0.0001
                        tick_to_process = TickData(
                            timestamp=time.time(), # Timestamp actual
                            bid=last_known_mid - (spread_proxy/2),
                            ask=last_known_mid + (spread_proxy/2),
                            symbol=symbol
                        )
                    else:
                        # Caso crítico: Arranque sin datos
                        # logger.warning(f"⚠️ [POLL] {symbol} esperando primeros datos...")
                        pass

                # 4. Integración con el Ticker (Producer-Consumer)
                if tick_to_process:
                    # Enviar al InstrumentState para procesamiento
                    state = self.iq_service.instrument_states.get(symbol)
                    if state:
                        closed_candle = await state.process_tick(tick_to_process)
                        
                        # Si se cerró una vela y está habilitada la generación de gráficos
                        if closed_candle:
                            # ---------------------------------------------------------
                            # PASO EXTRA: Sincronizar con datos oficiales de la API
                            # Buscamos la vela correspondiente en el snapshot para corregir el cierre
                            # ---------------------------------------------------------
                            if snapshot:
                                # Buscar vela con mismo timestamp
                                # snapshot es lista de dicts. 'from' es el timestamp de inicio.
                                target_ts = closed_candle.timestamp
                                api_match = next((c for c in snapshot if int(c.get("from", 0)) == target_ts), None)
                                
                                if api_match:
                                    # Actualizar estado
                                    updated_candle = await state.update_last_candle_from_api(api_match)
                                    if updated_candle:
                                        # logger.info(f"🔄 Vela corregida con API: Close {closed_candle.close} -> {updated_candle.close}")
                                        closed_candle = updated_candle

                            # 1. Enviar a Analysis Service (CRÍTICO)
                            if self.analysis_service:
                                await self.analysis_service.process_realtime_candle(closed_candle)

                            # 2. Generar gráfico si está habilitado
                            if Config.GENERATE_HISTORICAL_CHARTS:
                                # Ejecutar en background para no bloquear el polling loop
                                asyncio.create_task(
                                    self._save_candle_chart(symbol, closed_candle)
                                )
                    
                    # Guardar debug JSON (opcional, para auditoría)
                    # Solo guardamos si hubo cambios o cada N ciclos para no saturar disco
                    # Por ahora mantenemos la lógica original de guardar siempre que haya snapshot
                    if snapshot:
                        try:
                            debug_path = Path(f"data/debug_iq_poll_{symbol}.json")
                            # Optimizacion: No crear directorios en cada ciclo si ya existen
                            if not debug_path.parent.exists():
                                debug_path.parent.mkdir(exist_ok=True, parents=True)
                            
                            await loop.run_in_executor(
                                None,
                                self._save_debug_json,
                                debug_path,
                                snapshot
                            )
                        except Exception:
                            pass

                # Esperar antes del siguiente poll
                await asyncio.sleep(self._poll_interval)
                
            except asyncio.CancelledError:
                logger.info(f"🛑 Polling cancelado para {symbol}")
                break
            except Exception as e:
                logger.error(f"❌ Error en polling loop de {symbol}: {e}")
                await asyncio.sleep(1.0)
    
    def _save_debug_json(self, path: Path, data: List[Dict]) -> None:
        """Helper para guardar JSON en disco."""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            # logger.debug(f"📝 Archivo escrito: {path}")
        except Exception as e:
            logger.error(f"❌ Error escribiendo archivo {path}: {e}")


def create_iq_option_service_multi_async(
    analysis_service,
    on_auth_failure_callback: Optional[Callable] = None
) -> IqOptionServiceMultiAsync:
    """Factory function para crear el servicio asíncrono multi-instrumento."""
    return IqOptionServiceMultiAsync(analysis_service, on_auth_failure_callback)
