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
from typing import Dict, Optional, Callable, List
from dataclasses import dataclass
from datetime import datetime
from collections import defaultdict

import pandas as pd
import numpy as np

from config import Config
from src.services.connection_service import CandleData
from src.logic.candle import is_shooting_star, is_hanging_man, is_inverted_hammer, is_hammer
from src.utils.logger import get_logger, log_exception
from src.utils.charting import generate_chart_base64, validate_dataframe_for_chart


logger = get_logger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class TrendAnalysis:
    """Análisis completo de tendencia basado en múltiples EMAs."""
    status: str      # "STRONG_BULLISH", "WEAK_BULLISH", "NEUTRAL", "WEAK_BEARISH", "STRONG_BEARISH"
    score: int       # De -10 a +10
    is_aligned: bool # True si EMAs están ordenadas correctamente (EMA20 > EMA50 > EMA200 o inversa)
    
    def __str__(self) -> str:
        """Representación legible para logs."""
        alignment_str = "Alineadas" if self.is_aligned else "Desalineadas"
        return f"{self.status} (Score: {self.score:+d}, {alignment_str})"


@dataclass
class PatternSignal:
    """Señal de patrón detectado."""
    symbol: str
    source: str  # "OANDA" o "FX"
    pattern: str  # "SHOOTING_STAR", "HANGING_MAN", "INVERTED_HAMMER", "HAMMER"
    timestamp: int
    candle: CandleData
    ema_200: float
    ema_100: float
    ema_50: float
    ema_30: float
    ema_20: float
    trend: str  # "STRONG_BULLISH", "WEAK_BULLISH", "NEUTRAL", "WEAK_BEARISH", "STRONG_BEARISH"
    trend_score: int  # Score numérico de -10 a +10
    is_trend_aligned: bool  # Si las EMAs están alineadas correctamente
    confidence: float  # 0.0 - 1.0
    trend_filtered: bool  # True si se aplicó filtro de tendencia
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


def analyze_trend(close: float, emas: Dict[str, float]) -> TrendAnalysis:
    """
    Analiza la tendencia usando sistema de puntuación ponderada con múltiples EMAs.
    
    Estrategia de Scoring (Weighted Score):
    - Precio > EMA 200: +3 pts | Precio < EMA 200: -3 pts  (Macro Trend)
    - Precio > EMA 100: +2 pts | Precio < EMA 100: -2 pts  (Mid-Term)
    - EMA 50 > EMA 200: +2 pts | EMA 50 < EMA 200: -2 pts  (Alineación Macro)
    - Precio > EMA 20: +2 pts | Precio < EMA 20: -2 pts    (Momentum)
    - EMA 20 > EMA 50: +1 pt | EMA 20 < EMA 50: -1 pt      (Cruce Corto)
    
    Clasificación:
    - Score >= 6: STRONG_BULLISH
    - Score 1 a 5: WEAK_BULLISH
    - Score -1 a 1: NEUTRAL
    - Score -5 a -1: WEAK_BEARISH
    - Score <= -6: STRONG_BEARISH
    
    Args:
        close: Precio de cierre actual
        emas: Diccionario con claves 'ema_20', 'ema_50', 'ema_100', 'ema_200'
              (pueden ser NaN si no hay suficientes datos)
    
    Returns:
        TrendAnalysis: Objeto con status, score e is_aligned
    """
    score = 0
    
    # Extraer EMAs (manejar NaN)
    ema_20 = emas.get('ema_20', np.nan)
    ema_50 = emas.get('ema_50', np.nan)
    ema_100 = emas.get('ema_100', np.nan)
    ema_200 = emas.get('ema_200', np.nan)
    
    # Regla 1: Precio vs EMA 200 (Macro Trend) - Peso: 3
    if not np.isnan(ema_200):
        if close > ema_200:
            score += 3
        elif close < ema_200:
            score -= 3
    
    # Regla 2: Precio vs EMA 100 (Mid-Term) - Peso: 2
    if not np.isnan(ema_100):
        if close > ema_100:
            score += 2
        elif close < ema_100:
            score -= 2
    
    # Regla 3: EMA 50 vs EMA 200 (Alineación Macro) - Peso: 2
    if not np.isnan(ema_50) and not np.isnan(ema_200):
        if ema_50 > ema_200:
            score += 2
        elif ema_50 < ema_200:
            score -= 2
    
    # Regla 4: Precio vs EMA 20 (Momentum) - Peso: 2
    if not np.isnan(ema_20):
        if close > ema_20:
            score += 2
        elif close < ema_20:
            score -= 2
    
    # Regla 5: EMA 20 vs EMA 50 (Cruce Corto) - Peso: 1
    if not np.isnan(ema_20) and not np.isnan(ema_50):
        if ema_20 > ema_50:
            score += 1
        elif ema_20 < ema_50:
            score -= 1
    
    # Clasificar según score
    if score >= 6:
        status = "STRONG_BULLISH"
    elif score >= 1:
        status = "WEAK_BULLISH"
    elif score >= -1:
        status = "NEUTRAL"
    elif score >= -5:
        status = "WEAK_BEARISH"
    else:
        status = "STRONG_BEARISH"
    
    # Verificar alineación de EMAs
    # Alcista: EMA20 > EMA50 > EMA200
    # Bajista: EMA20 < EMA50 < EMA200
    is_aligned = False
    if not any(np.isnan([ema_20, ema_50, ema_200])):
        is_aligned = (ema_20 > ema_50 > ema_200) or (ema_20 < ema_50 < ema_200)
    
    return TrendAnalysis(
        status=status,
        score=score,
        is_aligned=is_aligned
    )


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
    - Gestionar ciclo de vida de señales para dataset de backtesting
    """
    
    def __init__(
        self,
        on_pattern_detected: Callable[[PatternSignal], None],
        storage_service: Optional[object] = None  # StorageService (evitamos import circular)
    ):
        """
        Inicializa el servicio de análisis.
        
        Args:
            on_pattern_detected: Callback invocado cuando se detecta un patrón válido
            storage_service: Instancia de StorageService para persistencia de dataset
        """
        self.on_pattern_detected = on_pattern_detected
        self.storage_service = storage_service
        
        # Buffers separados por fuente (OANDA, FX)
        self.dataframes: Dict[str, pd.DataFrame] = {}
        
        # Tracking de última vela procesada (para detectar cierres)
        self.last_timestamps: Dict[str, int] = {}
        
        # Estado de inicialización
        self.is_initialized: Dict[str, bool] = defaultdict(bool)
        
        # State Machine: Señal pendiente esperando resolución
        # Key: source_key, Value: PatternSignal
        self.pending_signals: Dict[str, PatternSignal] = {}
        
        # Configuración
        self.ema_period = Config.EMA_PERIOD
        self.min_candles_required = Config.EMA_PERIOD * 3
        self.chart_lookback = Config.CHART_LOOKBACK
        
        logger.info(
            f"📊 Analysis Service inicializado "
            f"(Período EMA: {self.ema_period}, Storage: {'✓' if storage_service else '✗'})"
        )
    
    def load_historical_candles(self, candles: List[CandleData]) -> None:
        """
        Carga velas históricas (snapshot inicial) en el DataFrame.
        NO genera gráficos ni envía notificaciones.
        
        Args:
            candles: Lista de velas históricas (del snapshot de 1000 velas)
        """
        if not candles:
            return
        
        # Todas las velas deben ser de la misma fuente
        first_candle = candles[0]
        source_key = f"{first_candle.source}_{first_candle.symbol}"
        
        # Inicializar DataFrame si no existe
        if source_key not in self.dataframes:
            self._initialize_dataframe(source_key)
        
        logger.info(f"📥 Cargando {len(candles)} velas históricas para {source_key}...")
        
        # Agregar todas las velas al DataFrame en batch
        for candle in candles:
            self._add_new_candle(source_key, candle)
        
        # Calcular indicadores una sola vez al final
        self._update_indicators(source_key)
        
        # Marcar como inicializado si tiene suficientes velas
        candle_count = len(self.dataframes[source_key])
        if candle_count >= self.min_candles_required:
            self.is_initialized[source_key] = True
            logger.info(
                f"✅ {source_key} initialized with {candle_count} historical candles. "
                "Pattern detection ACTIVE."
            )
        else:
            logger.warning(
                f"⚠️  {source_key}: Only {candle_count}/{self.min_candles_required} "
                "candles loaded. Need more data."
            )
        
        # Actualizar último timestamp
        if candles:
            self.last_timestamps[source_key] = candles[-1].timestamp
    
    async def process_realtime_candle(self, candle: CandleData) -> None:
        """
        Procesa una vela en tiempo real del WebSocket.
        Implementa State Machine para cerrar ciclo anterior y abrir nuevo.
        
        Flujo Crítico (en orden):
        1. Verificar si existe señal pendiente (del cierre anterior)
        2. Si existe: Construir registro {Señal, Resultado} y guardar en dataset
        3. Detectar si la vela actual es un cierre nuevo
        4. Si es cierre: Analizar patrón y guardar como nueva señal pendiente
        
        Args:
            candle: Datos de la vela recibida del WebSocket
        """
        source_key = f"{candle.source}_{candle.symbol}"
        
        # Inicializar DataFrame si no existe
        if source_key not in self.dataframes:
            self._initialize_dataframe(source_key)
        
        # Detectar si es un cierre de vela (timestamp diferente)
        is_new_candle = self._is_new_candle(source_key, candle.timestamp)
        
        if is_new_candle:
            # LOG: Vela cerrada con hora
            from datetime import datetime
            candle_time = datetime.fromtimestamp(candle.timestamp).strftime("%H:%M")
            logger.info(f"🕯️ VELA CERRADA | {source_key} | Hora: {candle_time}")
            
            # ═════════════════════════════════════════════════════════════
            # PASO 1: CERRAR CICLO ANTERIOR (Si existe señal pendiente)
            # ═════════════════════════════════════════════════════════════
            if source_key in self.pending_signals:
                await self._close_signal_cycle(source_key, candle)
            
            # ═════════════════════════════════════════════════════════════
            # PASO 2: AGREGAR NUEVA VELA Y CALCULAR INDICADORES
            # ═════════════════════════════════════════════════════════════
            self._add_new_candle(source_key, candle)
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
            
            # ═════════════════════════════════════════════════════════════
            # PASO 3: ANALIZAR NUEVA VELA Y ABRIR NUEVO CICLO
            # ═════════════════════════════════════════════════════════════
            asyncio.create_task(self._analyze_last_closed_candle(source_key, candle, force_notification=False))
        
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
            "timestamp", "open", "high", "low", "close", "volume", 
            "ema_200", "ema_100", "ema_50", "ema_30", "ema_20"
        ])
        logger.debug(f"📋 DataFrame inicializado para {source_key}")
    
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
    
    def _add_new_candle(self, source_key: str, candle: CandleData) -> None:
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
            "ema_200": np.nan,  # Se calculará después
            "ema_100": np.nan,
            "ema_50": np.nan,
            "ema_30": np.nan,
            "ema_20": np.nan
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
        Recalcula los indicadores técnicos (EMAs: 200, 100, 50, 30, 20).
        
        Args:
            source_key: Clave de la fuente
        """
        df = self.dataframes[source_key]
        
        # Calcular EMAs sobre precios de cierre
        # EMA 20 - Siempre se puede calcular si hay >= 20 velas
        if len(df) >= 20:
            df["ema_20"] = calculate_ema(df["close"], 20)
        
        # EMA 30
        if len(df) >= 30:
            df["ema_30"] = calculate_ema(df["close"], 30)
        
        # EMA 50
        if len(df) >= 50:
            df["ema_50"] = calculate_ema(df["close"], 50)
        
        # EMA 100
        if len(df) >= 100:
            df["ema_100"] = calculate_ema(df["close"], 100)
        
        # EMA 200 - La principal para detección de tendencia
        if len(df) >= self.ema_period:
            df["ema_200"] = calculate_ema(df["close"], self.ema_period)
    
    async def _close_signal_cycle(self, source_key: str, outcome_candle: CandleData) -> None:
        """
        Cierra el ciclo de una señal pendiente guardando el resultado en el dataset.
        
        Flujo:
        1. Recuperar señal pendiente
        2. Determinar dirección esperada según patrón
        3. Calcular dirección actual de la vela de resultado
        4. Determinar éxito/fracaso
        5. Calcular PnL en pips
        6. Construir registro completo
        7. Guardar en StorageService
        8. Limpiar señal pendiente
        
        Args:
            source_key: Clave de la fuente (ej: "FX_EURUSD")
            outcome_candle: Vela que cierra (resultado de la señal anterior)
        """
        if source_key not in self.pending_signals:
            return
        
        pending_signal = self.pending_signals[source_key]
        
        logger.info(
            f"\n{'═'*60}\n"
            f"🔄 CERRANDO CICLO DE SEÑAL\n"
            f"{'═'*60}\n"
            f"📊 Fuente: {source_key}\n"
            f"🎯 Patrón Previo: {pending_signal.pattern}\n"
            f"🕒 Timestamp Señal: {pending_signal.timestamp}\n"
            f"🕒 Timestamp Resultado: {outcome_candle.timestamp}\n"
        )
        
        # Determinar dirección esperada según tipo de patrón
        # BAJISTA (reversión bajista): Shooting Star, Hanging Man
        # ALCISTA (reversión alcista): Hammer, Inverted Hammer
        if pending_signal.pattern in ["SHOOTING_STAR", "HANGING_MAN"]:
            expected_direction = "ROJO"  # Bajista
        elif pending_signal.pattern in ["HAMMER", "INVERTED_HAMMER"]:
            expected_direction = "VERDE"  # Alcista
        else:
            logger.warning(f"⚠️  Patrón desconocido: {pending_signal.pattern}")
            expected_direction = "UNKNOWN"
        
        # Determinar dirección actual de la vela de resultado
        if outcome_candle.close < outcome_candle.open:
            actual_direction = "ROJO"  # Bajista
        elif outcome_candle.close > outcome_candle.open:
            actual_direction = "VERDE"  # Alcista
        else:
            actual_direction = "DOJI"  # Sin dirección clara
        
        # Determinar éxito
        success = (expected_direction == actual_direction)
        
        # Calcular PnL en pips (asumiendo 4 decimales para EUR/USD)
        # PnL = (Precio_Final - Precio_Inicial) * 10000
        # Si esperábamos bajista (SHORT): PnL = (Precio_Inicial - Precio_Final) * 10000
        # Si esperábamos alcista (LONG): PnL = (Precio_Final - Precio_Inicial) * 10000
        
        if expected_direction == "ROJO":  # SHORT position
            pnl_pips = (pending_signal.candle.close - outcome_candle.close) * 10000
        elif expected_direction == "VERDE":  # LONG position
            pnl_pips = (outcome_candle.close - pending_signal.candle.close) * 10000
        else:
            pnl_pips = 0.0
        
        # Construir registro completo
        from datetime import datetime
        record = {
            "timestamp": datetime.utcfromtimestamp(pending_signal.timestamp).isoformat() + "Z",
            "signal": {
                "pattern": pending_signal.pattern,
                "source": pending_signal.source,
                "symbol": pending_signal.symbol,
                "confidence": pending_signal.confidence,
                "trend": pending_signal.trend,
                "trend_score": pending_signal.trend_score,
                "is_trend_aligned": pending_signal.is_trend_aligned,
            },
            "trigger_candle": {
                "timestamp": pending_signal.candle.timestamp,
                "open": pending_signal.candle.open,
                "high": pending_signal.candle.high,
                "low": pending_signal.candle.low,
                "close": pending_signal.candle.close,
                "volume": pending_signal.candle.volume,
            },
            "outcome_candle": {
                "timestamp": outcome_candle.timestamp,
                "open": outcome_candle.open,
                "high": outcome_candle.high,
                "low": outcome_candle.low,
                "close": outcome_candle.close,
                "volume": outcome_candle.volume,
            },
            "outcome": {
                "expected_direction": expected_direction,
                "actual_direction": actual_direction,
                "success": success,
                "pnl_pips": round(pnl_pips, 1),
                "outcome_timestamp": datetime.utcfromtimestamp(outcome_candle.timestamp).isoformat() + "Z"
            }
        }
        
        # Guardar en StorageService si está disponible
        if self.storage_service:
            try:
                await self.storage_service.save_signal_outcome(record)
            except Exception as e:
                log_exception(logger, "Error guardando registro en StorageService", e)
        else:
            logger.warning("⚠️  StorageService no disponible - registro no guardado")
        
        # Limpiar señal pendiente
        del self.pending_signals[source_key]
        
        logger.info(
            f"✅ CICLO CERRADO | "
            f"Éxito: {'✓' if success else '✗'} | "
            f"PnL: {pnl_pips:+.1f} pips | "
            f"Esperado: {expected_direction} | Actual: {actual_direction}\n"
            f"{'═'*60}\n"
        )
    
    async def _analyze_last_closed_candle(self, source_key: str, current_candle: CandleData, force_notification: bool = False) -> None:
        """
        Analiza la última vela cerrada en busca de patrones y genera gráfico.
        Solo envía notificación si detecta uno de los 4 patrones con tendencia apropiada.
        
        Args:
            source_key: Clave de la fuente
            current_candle: Vela actual (la siguiente a la cerrada)
            force_notification: Si True, envía notificación incluso sin patrón (uso interno)
        """
        df = self.dataframes[source_key]
        
        if len(df) < 2:
            return
        
        # Obtener la última vela CERRADA (penúltima en el buffer)
        last_closed = df.iloc[-2]
        
        # Verificar que EMA 200 esté disponible
        if pd.isna(last_closed["ema_200"]):
            return
        
        # LOG: Información de la vela cerrada con todas las EMAs
        ema_20_val = last_closed.get('ema_20', np.nan)
        ema_30_val = last_closed.get('ema_30', np.nan)
        ema_50_val = last_closed.get('ema_50', np.nan)
        ema_100_val = last_closed.get('ema_100', np.nan)
        
        # Formatear EMAs (convertir a string antes)
        ema_20_str = f"{ema_20_val:.5f}" if not pd.isna(ema_20_val) else "N/A"
        ema_30_str = f"{ema_30_val:.5f}" if not pd.isna(ema_30_val) else "N/A"
        ema_50_str = f"{ema_50_val:.5f}" if not pd.isna(ema_50_val) else "N/A"
        ema_100_str = f"{ema_100_val:.5f}" if not pd.isna(ema_100_val) else "N/A"
        
        logger.info(
            f"\n\n"
            f"🕯️  VELA CERRADA - INICIANDO ANÁLISIS\n"
            f"{'='*40}\n"
            f"📊 Fuente: {source_key}\n"
            f"🕒 Timestamp: {last_closed['timestamp']}\n"
            f"💰 Apertura: {last_closed['open']:.5f}\n"
            f"💰 Máximo: {last_closed['high']:.5f}\n"
            f"💰 Mínimo: {last_closed['low']:.5f}\n"
            f"💰 Cierre: {last_closed['close']:.5f}\n"
            f"📊 Volumen: {last_closed['volume']:.2f}\n"
            f"📉 EMAs: 20={ema_20_str} | 30={ema_30_str} | 50={ema_50_str} | 100={ema_100_str} | 200={last_closed['ema_200']:.5f}\n"
            f"{'='*40}\n"
        )
        
        # Analizar tendencia con sistema de scoring
        emas_dict = {
            'ema_20': last_closed.get('ema_20', np.nan),
            'ema_50': last_closed.get('ema_50', np.nan),
            'ema_100': last_closed.get('ema_100', np.nan),
            'ema_200': last_closed['ema_200']
        }
        trend_analysis = analyze_trend(last_closed["close"], emas_dict)
        
        logger.info(
            f"📈 Análisis de Tendencia: {trend_analysis}\n"
            f"   • Status: {trend_analysis.status}\n"
            f"   • Score: {trend_analysis.score:+d}/10\n"
            f"   • Alineación EMAs: {'✓' if trend_analysis.is_aligned else '✗'}\n"
        )
        
        # Detectar los 4 patrones de velas japonesas
        shooting_star_detected, shooting_star_conf = is_shooting_star(
            last_closed["open"],
            last_closed["high"],
            last_closed["low"],
            last_closed["close"]
        )
        
        hanging_man_detected, hanging_man_conf = is_hanging_man(
            last_closed["open"],
            last_closed["high"],
            last_closed["low"],
            last_closed["close"]
        )
        
        inverted_hammer_detected, inverted_hammer_conf = is_inverted_hammer(
            last_closed["open"],
            last_closed["high"],
            last_closed["low"],
            last_closed["close"]
        )
        
        hammer_detected, hammer_conf = is_hammer(
            last_closed["open"],
            last_closed["high"],
            last_closed["low"],
            last_closed["close"]
        )
        
        # Filtrar patrones por tendencia apropiada (solo si USE_TREND_FILTER está activo)
        # BEARISH signals (reversión bajista): Shooting Star y Hanging Man en tendencia alcista
        # BULLISH signals (reversión alcista): Hammer e Inverted Hammer en tendencia bajista
        pattern_detected = None
        pattern_confidence = 0.0
        
        if Config.USE_TREND_FILTER:
            # Modo CON filtro de tendencia (comportamiento original)
            if trend == "BEARISH":
                # En tendencia bajista, buscar reversión alcista
                if hammer_detected:
                    pattern_detected = "HAMMER"
                    pattern_confidence = hammer_conf
                elif inverted_hammer_detected:
                    pattern_detected = "INVERTED_HAMMER"
                    pattern_confidence = inverted_hammer_conf
            elif trend == "BULLISH":
                # En tendencia alcista, buscar reversión bajista
                if shooting_star_detected:
                    pattern_detected = "SHOOTING_STAR"
                    pattern_confidence = shooting_star_conf
                elif hanging_man_detected:
                    pattern_detected = "HANGING_MAN"
                    pattern_confidence = hanging_man_conf
        else:
            # Modo SIN filtro de tendencia: detectar cualquier patrón sin importar tendencia
            # Prioridad: Shooting Star > Hanging Man > Hammer > Inverted Hammer
            if shooting_star_detected:
                pattern_detected = "SHOOTING_STAR"
                pattern_confidence = shooting_star_conf
            elif hanging_man_detected:
                pattern_detected = "HANGING_MAN"
                pattern_confidence = hanging_man_conf
            elif hammer_detected:
                pattern_detected = "HAMMER"
                pattern_confidence = hammer_conf
            elif inverted_hammer_detected:
                pattern_detected = "INVERTED_HAMMER"
                pattern_confidence = inverted_hammer_conf
        
        # Determinar si se debe enviar notificación
        # SOLO enviar si hay patrón válido
        should_notify = (pattern_detected is not None)
        
        if should_notify:
            # Generar gráfico en Base64 (operación bloqueante en hilo separado)
            chart_base64 = None
            try:
                # Validar que hay suficientes datos para el gráfico
                is_valid, error_msg = validate_dataframe_for_chart(df, self.chart_lookback)
                logger.debug(
                    f"Validación de DataFrame para gráfico: is_valid={is_valid}, error_msg='{error_msg}'"
                )
                if is_valid:
                    chart_title = f"{current_candle.source}:{current_candle.symbol} - {pattern_detected}"
                    
                    logger.info(
                        f"📋 GENERANDO GRÁFICO | {source_key} | "
                        f"Últimas {self.chart_lookback} velas | Patrón: {pattern_detected}"
                    )
                    
                    # CRITICAL: Ejecutar en hilo separado para no bloquear el Event Loop
                    chart_base64 = await asyncio.to_thread(
                        generate_chart_base64,
                        df,
                        self.chart_lookback,
                        chart_title
                    )
                    
                    logger.info(
                        f"✅ GRÁFICO GENERADO | {source_key} | "
                        f"Tamaño: {len(chart_base64)} bytes Base64 | Patrón: {pattern_detected}"
                    )
                else:
                    logger.warning(f"⚠️  No se pudo generar gráfico: {error_msg}")
            
            except Exception as e:
                log_exception(logger, "Failed to generate chart", e)
                # Continuar sin gráfico si hay error
                chart_base64 = None
            
            # En este punto siempre hay un patrón detectado
            signal = PatternSignal(
                symbol=current_candle.symbol,
                source=current_candle.source,
                pattern=pattern_detected,
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
                ema_100=last_closed.get("ema_100", np.nan),
                ema_50=last_closed.get("ema_50", np.nan),
                ema_30=last_closed.get("ema_30", np.nan),
                ema_20=last_closed.get("ema_20", np.nan),
                trend=trend_analysis.status,
                trend_score=trend_analysis.score,
                is_trend_aligned=trend_analysis.is_aligned,
                confidence=pattern_confidence,
                trend_filtered=Config.USE_TREND_FILTER,
                chart_base64=chart_base64
            )
            
            logger.info(
                f"🎯 PATTERN DETECTED | {signal.source} | {signal.pattern} | "
                f"Trend={trend_analysis.status} (Score: {trend_analysis.score:+d}) | "
                f"Close={signal.candle.close:.5f} | Confidence={signal.confidence:.2f} | "
                f"Chart={'✓' if chart_base64 else '✗'}"
            )
            
            # Guardar vela detectada en test_data.json
            await self._save_detected_candle_to_test_data(
                last_closed["open"],
                last_closed["high"],
                last_closed["low"],
                last_closed["close"],
                pattern_detected
            )
            
            logger.info(
                f"✅ Señal de patrón emitida para {signal.source} | "
                f"{signal.pattern} @ {signal.timestamp}"
            )
            
            # ═════════════════════════════════════════════════════════════
            # GUARDAR SEÑAL COMO PENDIENTE (State Machine)
            # ═════════════════════════════════════════════════════════════
            self.pending_signals[source_key] = signal
            logger.info(
                f"⏳ SEÑAL GUARDADA COMO PENDIENTE | {source_key} | "
                f"{signal.pattern} | Esperando próxima vela para cerrar ciclo"
            )
            
            # Emitir señal a Telegram en tiempo real (notificación inmediata)
            if self.on_pattern_detected:
                await self.on_pattern_detected(signal)
    
    async def _save_detected_candle_to_test_data(
        self,
        apertura: float,
        maximo: float,
        minimo: float,
        cierre: float,
        pattern: str
    ) -> None:
        """
        Guarda una vela detectada en test/test_data.json.
        
        Args:
            apertura: Precio de apertura
            maximo: Precio máximo
            minimo: Precio mínimo
            cierre: Precio de cierre
            pattern: Tipo de patrón detectado (SHOOTING_STAR, HANGING_MAN, etc.)
        """
        try:
            from pathlib import Path
            import json
            
            # Mapear nombres de patrones a formato del test
            pattern_map = {
                "SHOOTING_STAR": "shooting_star",
                "HANGING_MAN": "hanging_man",
                "INVERTED_HAMMER": "inverted_hammer",
                "HAMMER": "hammer"
            }
            
            tipo_vela = pattern_map.get(pattern)
            if not tipo_vela:
                logger.warning(f"⚠️  Patrón desconocido para guardar: {pattern}")
                return
            
            # Ruta al archivo test_data.json
            test_file = Path("test") / "test_data.json"
            
            # Crear directorio si no existe
            test_file.parent.mkdir(exist_ok=True)
            
            # Leer datos existentes
            if test_file.exists():
                with open(test_file, "r", encoding="utf-8") as f:
                    test_data = json.load(f)
            else:
                test_data = []
            
            # Crear nuevo elemento
            new_entry = {
                "apertura": float(apertura),
                "cierre": float(cierre),
                "maximo": float(maximo),
                "minimo": float(minimo),
                "tipo_vela": tipo_vela
            }
            
            # Agregar al array
            test_data.append(new_entry)
            
            # Guardar archivo actualizado
            with open(test_file, "w", encoding="utf-8") as f:
                json.dump(test_data, f, indent=2, ensure_ascii=False)
            
            logger.info(
                f"💾 VELA GUARDADA EN TEST_DATA.JSON | Tipo: {tipo_vela} | "
                f"Total velas: {len(test_data)}"
            )
            
        except Exception as e:
            log_exception(logger, "Error guardando vela en test_data.json", e)
    
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
