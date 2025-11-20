"""
Analysis Service - Pattern Detection & Technical Analysis
==========================================================
Gestiona el buffer de velas en pandas, calcula indicadores técnicos (EMA 200),
detecta patrones de velas japonesas (Shooting Star) y filtra por tendencia.

CRITICAL: Solo emite señales cuando:
1. Buffer tiene suficientes datos (>= EMA_PERIOD * 3)
2. Patrón detectado es válido matemáticamente
3. Tendencia confirma la dirección (Close < EMA 200 para Shooting Star)

Author: TradingView Pattern Monitor Team
"""

import asyncio
from typing import Dict, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from collections import defaultdict

import pandas as pd
import numpy as np

from config import Config
from src.services.connection_service import CandleData
from src.utils.logger import get_logger, log_exception
from src.utils.charting import generate_chart_base64, validate_dataframe_for_chart


logger = get_logger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class PatternSignal:
    """Señal de patrón detectado."""
    symbol: str
    source: str  # "OANDA" o "FX"
    pattern: str  # "SHOOTING_STAR"
    timestamp: int
    candle: CandleData
    ema_200: float
    trend: str  # "BEARISH", "BULLISH", "NEUTRAL"
    confidence: float  # 0.0 - 1.0
    chart_base64: Optional[str] = None  # Gráfico codificado en Base64


# =============================================================================
# TECHNICAL ANALYSIS HELPERS
# =============================================================================

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """
    Calcula la Media Móvil Exponencial (EMA).
    
    Args:
        series: Serie de precios (típicamente Close)
        period: Periodo de la EMA (ej: 200)
        
    Returns:
        pd.Series: Serie con valores de EMA
    """
    return series.ewm(span=period, adjust=False).mean()


def is_shooting_star(
    open_price: float,
    high: float,
    low: float,
    close: float
) -> tuple[bool, float]:
    """
    Detecta si una vela es una Estrella Fugaz (Shooting Star).
    
    Criterios:
    - Cuerpo pequeño en la parte inferior de la vela
    - Mecha superior larga (al menos 2x el tamaño del cuerpo)
    - Mecha inferior mínima o inexistente
    - Preferiblemente vela bajista (close < open)
    
    Args:
        open_price: Precio de apertura
        high: Precio máximo
        low: Precio mínimo
        close: Precio de cierre
        
    Returns:
        tuple[bool, float]: (Es Shooting Star, Confianza 0-1)
    """
    body = abs(close - open_price)
    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low
    total_range = high - low
    
    # Evitar división por cero
    if total_range == 0 or body == 0:
        return False, 0.0
    
    # Ratios
    upper_wick_ratio = upper_wick / total_range
    body_ratio = body / total_range
    lower_wick_ratio = lower_wick / total_range
    
    # Condiciones estrictas
    is_pattern = (
        upper_wick_ratio > 0.6 and  # Mecha superior > 60% del rango total
        body_ratio < 0.3 and         # Cuerpo < 30% del rango total
        lower_wick_ratio < 0.15 and  # Mecha inferior < 15%
        upper_wick >= body * 2       # Mecha superior >= 2x cuerpo
    )
    
    # Calcular confianza basada en proporciones
    confidence = 0.0
    if is_pattern:
        # Mejor confianza si es vela bajista
        is_bearish = close < open_price
        bearish_bonus = 0.2 if is_bearish else 0.0
        
        # Confianza basada en ratios
        confidence = min(
            1.0,
            (upper_wick_ratio * 1.2) + 
            (1.0 - body_ratio) * 0.5 +
            (1.0 - lower_wick_ratio) * 0.3 +
            bearish_bonus
        )
    
    return is_pattern, confidence


# =============================================================================
# ANALYSIS SERVICE
# =============================================================================

class AnalysisService:
    """
    Servicio de análisis técnico y detección de patrones.
    
    Responsabilidades:
    - Mantener buffer de velas en pandas DataFrames
    - Calcular EMA 200 en tiempo real
    - Detectar cierre de velas (cambio de timestamp)
    - Identificar patrones de velas japonesas
    - Filtrar señales por tendencia
    - Emitir señales validadas
    """
    
    def __init__(
        self,
        on_pattern_detected: Callable[[PatternSignal], None]
    ):
        """
        Inicializa el servicio de análisis.
        
        Args:
            on_pattern_detected: Callback invocado cuando se detecta un patrón válido
        """
        self.on_pattern_detected = on_pattern_detected
        
        # Buffers separados por fuente (OANDA, FX)
        self.dataframes: Dict[str, pd.DataFrame] = {}
        
        # Tracking de última vela procesada (para detectar cierres)
        self.last_timestamps: Dict[str, int] = {}
        
        # Estado de inicialización
        self.is_initialized: Dict[str, bool] = defaultdict(bool)
        
        # Configuración
        self.ema_period = Config.EMA_PERIOD
        self.min_candles_required = Config.EMA_PERIOD * 3
        self.chart_lookback = Config.CHART_LOOKBACK
        
        logger.info(f"📊 Analysis Service initialized (EMA Period: {self.ema_period})")
    
    def process_candle(self, candle: CandleData) -> None:
        """
        Procesa una vela entrante del WebSocket.
        
        Args:
            candle: Datos de la vela recibida
        """
        source_key = f"{candle.source}_{candle.symbol}"
        
        # Inicializar DataFrame si no existe
        if source_key not in self.dataframes:
            self._initialize_dataframe(source_key)
        
        # Detectar si es un cierre de vela (timestamp diferente)
        is_new_candle = self._is_new_candle(source_key, candle.timestamp)
        
        if is_new_candle:
            # Agregar la vela anterior al buffer antes de procesar la nueva
            self._add_candle_to_buffer(source_key, candle)
            
            # Calcular indicadores
            self._update_indicators(source_key)
            
            # Verificar si hay suficientes datos para análisis
            if not self.is_initialized[source_key]:
                candle_count = len(self.dataframes[source_key])
                if candle_count >= self.min_candles_required:
                    self.is_initialized[source_key] = True
                    logger.info(
                        f"✅ {source_key} initialized with {candle_count} candles. "
                        "Pattern detection ACTIVE."
                    )
                else:
                    logger.debug(
                        f"📥 {source_key}: {candle_count}/{self.min_candles_required} "
                        "candles buffered. Waiting for initialization..."
                    )
                    return
            
            # Analizar patrón en la vela cerrada (última completa)
            asyncio.create_task(self._analyze_last_closed_candle(source_key, candle))
        
        else:
            # Actualizar la vela actual (tick intra-candle)
            self._update_current_candle(source_key, candle)
        
        # Actualizar timestamp de tracking
        self.last_timestamps[source_key] = candle.timestamp
    
    def _initialize_dataframe(self, source_key: str) -> None:
        """
        Inicializa un DataFrame vacío para una fuente de datos.
        
        Args:
            source_key: Clave única de la fuente (ej: "OANDA_EURUSD")
        """
        self.dataframes[source_key] = pd.DataFrame(columns=[
            "timestamp", "open", "high", "low", "close", "volume", "ema_200"
        ])
        logger.debug(f"📋 DataFrame initialized for {source_key}")
    
    def _is_new_candle(self, source_key: str, timestamp: int) -> bool:
        """
        Determina si la vela recibida es nueva (timestamp diferente).
        
        Args:
            source_key: Clave de la fuente
            timestamp: Timestamp de la vela recibida
            
        Returns:
            bool: True si es una nueva vela
        """
        if source_key not in self.last_timestamps:
            return True
        
        return timestamp != self.last_timestamps[source_key]
    
    def _add_candle_to_buffer(self, source_key: str, candle: CandleData) -> None:
        """
        Agrega una vela cerrada al buffer de pandas.
        
        Args:
            source_key: Clave de la fuente
            candle: Datos de la vela
        """
        new_row = pd.DataFrame([{
            "timestamp": candle.timestamp,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
            "ema_200": np.nan  # Se calculará después
        }])
        
        self.dataframes[source_key] = pd.concat(
            [self.dataframes[source_key], new_row],
            ignore_index=True
        )
        
        # Mantener solo las últimas N velas (optimización de memoria)
        max_buffer_size = self.min_candles_required + 100
        if len(self.dataframes[source_key]) > max_buffer_size:
            self.dataframes[source_key] = self.dataframes[source_key].iloc[-max_buffer_size:]
            self.dataframes[source_key].reset_index(drop=True, inplace=True)
    
    def _update_current_candle(self, source_key: str, candle: CandleData) -> None:
        """
        Actualiza los valores de la vela actual (intra-candle ticks).
        
        Args:
            source_key: Clave de la fuente
            candle: Datos actualizados de la vela
        """
        df = self.dataframes[source_key]
        if len(df) == 0:
            return
        
        # Actualizar última fila
        df.iloc[-1, df.columns.get_loc("high")] = max(df.iloc[-1]["high"], candle.high)
        df.iloc[-1, df.columns.get_loc("low")] = min(df.iloc[-1]["low"], candle.low)
        df.iloc[-1, df.columns.get_loc("close")] = candle.close
        df.iloc[-1, df.columns.get_loc("volume")] += candle.volume
    
    def _update_indicators(self, source_key: str) -> None:
        """
        Recalcula los indicadores técnicos (EMA 200).
        
        Args:
            source_key: Clave de la fuente
        """
        df = self.dataframes[source_key]
        
        if len(df) < self.ema_period:
            return
        
        # Calcular EMA 200 sobre precios de cierre
        df["ema_200"] = calculate_ema(df["close"], self.ema_period)
    
    async def _analyze_last_closed_candle(self, source_key: str, current_candle: CandleData) -> None:
        """
        Analiza la última vela cerrada en busca de patrones y genera gráfico.
        
        Args:
            source_key: Clave de la fuente
            current_candle: Vela actual (la siguiente a la cerrada)
        """
        df = self.dataframes[source_key]
        
        if len(df) < 2:
            return
        
        # Obtener la última vela CERRADA (penúltima en el buffer)
        last_closed = df.iloc[-2]
        
        # Verificar que EMA 200 esté disponible
        if pd.isna(last_closed["ema_200"]):
            return
        
        # Determinar tendencia
        trend = self._determine_trend(last_closed["close"], last_closed["ema_200"])
        
        # Detectar patrón Shooting Star
        is_pattern, confidence = is_shooting_star(
            last_closed["open"],
            last_closed["high"],
            last_closed["low"],
            last_closed["close"]
        )
        
        # Filtro: Solo señales en tendencia bajista
        if is_pattern and trend == "BEARISH":
            # Generar gráfico en Base64 (operación bloqueante en hilo separado)
            chart_base64 = None
            try:
                # Validar que hay suficientes datos para el gráfico
                is_valid, error_msg = validate_dataframe_for_chart(df, self.chart_lookback)
                
                if is_valid:
                    logger.debug(f"📊 Generating chart for {source_key}...")
                    
                    # CRITICAL: Ejecutar en hilo separado para no bloquear el Event Loop
                    chart_title = f"{current_candle.source}:{current_candle.symbol} - {current_candle.pattern if hasattr(current_candle, 'pattern') else 'SHOOTING_STAR'}"
                    chart_base64 = await asyncio.to_thread(
                        generate_chart_base64,
                        df,
                        self.chart_lookback,
                        chart_title
                    )
                    
                    logger.info(f"✅ Chart generated successfully ({len(chart_base64)} bytes Base64)")
                else:
                    logger.warning(f"⚠️  Cannot generate chart: {error_msg}")
            
            except Exception as e:
                log_exception(logger, "Failed to generate chart", e)
                # Continuar sin gráfico si hay error
                chart_base64 = None
            
            signal = PatternSignal(
                symbol=current_candle.symbol,
                source=current_candle.source,
                pattern="SHOOTING_STAR",
                timestamp=int(last_closed["timestamp"]),
                candle=CandleData(
                    timestamp=int(last_closed["timestamp"]),
                    open=last_closed["open"],
                    high=last_closed["high"],
                    low=last_closed["low"],
                    close=last_closed["close"],
                    volume=last_closed["volume"],
                    source=current_candle.source,
                    symbol=current_candle.symbol
                ),
                ema_200=last_closed["ema_200"],
                trend=trend,
                confidence=confidence,
                chart_base64=chart_base64
            )
            
            logger.info(
                f"🎯 PATTERN DETECTED | {signal.source} | {signal.pattern} | "
                f"Close={signal.candle.close:.5f} < EMA200={signal.ema_200:.5f} | "
                f"Confidence={signal.confidence:.2f} | Chart={'✓' if chart_base64 else '✗'}"
            )
            
            # Emitir señal
            if self.on_pattern_detected:
                await self.on_pattern_detected(signal)
    
    def _determine_trend(self, close: float, ema_200: float) -> str:
        """
        Determina la tendencia comparando el cierre con la EMA 200.
        
        Args:
            close: Precio de cierre
            ema_200: Valor de la EMA 200
            
        Returns:
            str: "BEARISH", "BULLISH", o "NEUTRAL"
        """
        threshold = 0.0001  # Margen de tolerancia para evitar falsos neutrales
        
        if close < ema_200 - threshold:
            return "BEARISH"
        elif close > ema_200 + threshold:
            return "BULLISH"
        else:
            return "NEUTRAL"
    
    def get_buffer_status(self) -> Dict[str, int]:
        """
        Obtiene el estado de los buffers de datos.
        
        Returns:
            Dict[str, int]: Diccionario con el conteo de velas por fuente
        """
        return {
            source_key: len(df)
            for source_key, df in self.dataframes.items()
        }
