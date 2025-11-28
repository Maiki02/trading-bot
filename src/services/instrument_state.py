"""
Instrument State Management
============================
Data structures for managing multiple instruments with dual buffer system (BID/MID).

Author: Trading Bot Team
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List, Deque
from collections import deque
from datetime import datetime
import asyncio

from src.services.connection_service import CandleData


@dataclass
class TickData:
    """Representa un tick individual con precios BID y ASK."""
    timestamp: float
    bid: float
    ask: float
    symbol: str
    
    @property
    def mid(self) -> float:
        """Calcula el precio MID como promedio de BID y ASK."""
        return (self.bid + self.ask) / 2.0


@dataclass
class CandleBuilder:
    """
    Constructor de velas que acumula ticks para formar una vela completa.
    Usado para construir velas MID a partir de ticks BID/ASK.
    """
    timestamp: int  # Timestamp del inicio del minuto (epoch en segundos)
    open: Optional[float] = None
    high: float = float('-inf')
    low: float = float('inf')
    close: Optional[float] = None
    tick_count: int = 0
    
    def add_tick(self, mid_price: float) -> None:
        """
        Añade un tick al builder de vela.
        
        Args:
            mid_price: Precio MID calculado del tick
        """
        if self.open is None:
            self.open = mid_price
        
        self.high = max(self.high, mid_price)
        self.low = min(self.low, mid_price)
        self.close = mid_price
        self.tick_count += 1
    
    def build(self, symbol: str) -> Optional[CandleData]:
        """
        Construye una vela completa si hay suficientes datos.
        
        Args:
            symbol: Símbolo del instrumento
            
        Returns:
            CandleData o None si no hay datos suficientes
        """
        if self.open is None or self.close is None or self.tick_count == 0:
            return None
        
        return CandleData(
            timestamp=self.timestamp,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=float(self.tick_count),  # Usar tick_count como proxy de volumen
            source="IQ",
            symbol=symbol
        )


@dataclass
class InstrumentState:
    """
    Estado completo de un instrumento individual.
    Mantiene buffers separados para velas BID y MID.
    """
    symbol: str
    
    # Buffers de velas (últimas N velas cerradas)
    bid_candles: Deque[CandleData] = field(default_factory=lambda: deque(maxlen=500))
    mid_candles: Deque[CandleData] = field(default_factory=lambda: deque(maxlen=500))
    
    # Builder de vela MID actual (en formación)
    current_mid_builder: Optional[CandleBuilder] = None
    
    # Última vela BID procesada
    last_bid_candle: Optional[CandleData] = None
    
    # Último timestamp procesado (para detectar cambio de minuto)
    last_processed_timestamp: Optional[int] = None
    
    # Lock para operaciones thread-safe
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    def get_current_minute_timestamp(self) -> int:
        """
        Obtiene el timestamp del minuto actual (redondeado hacia abajo).
        
        Returns:
            Timestamp epoch en segundos del inicio del minuto
        """
        from datetime import datetime
        now = datetime.utcnow()
        return int(now.replace(second=0, microsecond=0).timestamp())
    
    async def process_tick(self, tick: TickData) -> Optional[CandleData]:
        """
        Procesa un tick y construye velas MID en tiempo real.
        Detecta cambio de minuto y cierra la vela actual.
        
        Args:
            tick: Datos del tick (BID/ASK)
            
        Returns:
            CandleData si se cerró una vela MID, None si no
        """
        import logging
        logger = logging.getLogger(__name__)
        
        async with self.lock:
            current_minute = int(tick.timestamp // 60) * 60  # Redondear a minuto
            mid_price = tick.mid
            
            # LOG: Cálculo MID
            logger.debug(
                f"💱 TICK MID | {self.symbol} | "
                f"BID={tick.bid} ASK={tick.ask} → MID={mid_price}"
            )
            
            # Inicializar builder si no existe
            if self.current_mid_builder is None:
                self.current_mid_builder = CandleBuilder(timestamp=current_minute)
                logger.info(f"🆕 Nuevo builder MID iniciado para {self.symbol} @ {current_minute}")
            
            # Detectar cambio de minuto (cerrar vela anterior)
            if self.current_mid_builder.timestamp < current_minute:
                # Construir vela cerrada
                closed_candle = self.current_mid_builder.build(self.symbol)
                
                if closed_candle:
                    # FIX: Verificar si ya existe una vela con este timestamp (para evitar duplicados al inicio)
                    if self.mid_candles and self.mid_candles[-1].timestamp == closed_candle.timestamp:
                        # Actualizar la existente
                        self.mid_candles[-1] = closed_candle
                        logger.info(
                            f"🕯️ VELA MID ACTUALIZADA | {self.symbol} | "
                            f"T={closed_candle.timestamp} | "
                            f"O={closed_candle.open} H={closed_candle.high} "
                            f"L={closed_candle.low} C={closed_candle.close} | "
                            f"Ticks={int(closed_candle.volume)}"
                        )
                    else:
                        # Agregar nueva
                        self.mid_candles.append(closed_candle)
                        logger.info(
                            f"🕯️ VELA MID CERRADA | {self.symbol} | "
                            f"T={closed_candle.timestamp} | "
                            f"O={closed_candle.open} H={closed_candle.high} "
                            f"L={closed_candle.low} C={closed_candle.close} | "
                            f"Ticks={int(closed_candle.volume)}"
                        )
                
                # Iniciar nueva vela
                self.current_mid_builder = CandleBuilder(timestamp=current_minute)
                self.current_mid_builder.add_tick(mid_price)
                
                return closed_candle
            else:
                # Agregar tick a la vela actual
                self.current_mid_builder.add_tick(mid_price)
                return None
    
    async def add_bid_candle(self, candle: CandleData) -> None:
        """
        Añade una vela BID al buffer.
        
        Args:
            candle: Vela BID recibida de la API
        """
        async with self.lock:
            self.bid_candles.append(candle)
            self.last_bid_candle = candle
    
    def get_latest_bid_candle(self) -> Optional[CandleData]:
        """Obtiene la última vela BID cerrada."""
        return self.bid_candles[-1] if self.bid_candles else None
    
    def get_latest_mid_candle(self) -> Optional[CandleData]:
        """Obtiene la última vela MID cerrada."""
        return self.mid_candles[-1] if self.mid_candles else None
    
    def get_bid_candles_list(self, count: int = 100) -> List[CandleData]:
        """
        Obtiene las últimas N velas BID.
        
        Args:
            count: Número de velas a retornar
            
        Returns:
            Lista de CandleData
        """
        return list(self.bid_candles)[-count:]
    
    def get_mid_candles_list(self, count: int = 100) -> List[CandleData]:
        """
        Obtiene las últimas N velas MID.
        
        Args:
            count: Número de velas a retornar
            
        Returns:
            Lista de CandleData
        """
        return list(self.mid_candles)[-count:]

    async def initialize_mid_candles(self, candles: List[CandleData]) -> None:
        """
        Inicializa el buffer de velas MID con datos históricos.
        
        Args:
            candles: Lista de velas MID históricas
        """
        async with self.lock:
            self.mid_candles.extend(candles)

    async def update_last_candle_from_api(self, api_candle: Dict) -> Optional[CandleData]:
        """
        Actualiza la última vela cerrada con datos oficiales de la API (BID).
        Esto corrige discrepancias de cierre (close price) debido a latencia de ticks.
        
        Args:
            api_candle: Diccionario de vela cruda de la API
            
        Returns:
            CandleData actualizado o None si no hubo match
        """
        async with self.lock:
            if not self.mid_candles:
                return None
            
            last_candle = self.mid_candles[-1]
            api_ts = int(api_candle.get("from", 0))
            
            # Verificar match de timestamp
            if last_candle.timestamp != api_ts:
                return None
            
            # Actualizar valores con datos oficiales
            # NOTA: Usamos los datos BID de la API como proxy del MID final
            # O idealmente, si tuviéramos BID/ASK de cierre, recalcularíamos MID.
            # Como IQ solo da BID en histórico, asumimos Close BID ≈ Close MID para el cierre
            # O mantenemos el Close calculado si confiamos más en nuestros ticks.
            # El usuario pidió: "Actualizar nuestra ultima vela registrada con la anteultima del buffer de la librería"
            
            try:
                new_close = float(api_candle.get("close", last_candle.close))
                new_high = float(api_candle.get("max", last_candle.high))
                new_low = float(api_candle.get("min", last_candle.low))
                new_open = float(api_candle.get("open", last_candle.open))
                new_volume = float(api_candle.get("volume", last_candle.volume))
                
                # Actualizar objeto (CandleData es dataclass, pero mutable por defecto en Python)
                # Sin embargo, es mejor reemplazarlo para evitar efectos secundarios si es frozen
                updated_candle = CandleData(
                    timestamp=last_candle.timestamp,
                    open=new_open,
                    high=max(last_candle.high, new_high), # El high real es el maximo entre lo visto y lo oficial
                    low=min(last_candle.low, new_low),    # El low real es el minimo
                    close=new_close,                      # El close oficial MANDA
                    volume=new_volume,
                    source=last_candle.source,
                    symbol=last_candle.symbol
                )
                
                # Reemplazar en deque
                self.mid_candles[-1] = updated_candle
                
                return updated_candle
                
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"❌ Error actualizando vela desde API: {e}")
                return None
