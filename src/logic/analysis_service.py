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
from src.logic.candle import is_shooting_star, is_hanging_man, is_inverted_hammer, is_hammer, get_candle_direction
from src.utils.logger import get_logger, log_exception
from src.utils.charting import generate_chart_base64, validate_dataframe_for_chart


logger = get_logger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class TrendAnalysis:
    """Análisis completo de tendencia basado en sistema de puntuación ponderada."""
    status: str      # "STRONG_BULLISH", "WEAK_BULLISH", "NEUTRAL", "WEAK_BEARISH", "STRONG_BEARISH"
    score: float     # De -10.0 a +10.0 (weighted score)
    is_aligned: bool # True si EMAs están ordenadas correctamente
    
    def __str__(self) -> str:
        """Representación legible para logs."""
        alignment_str = "Alineadas" if self.is_aligned else "Desalineadas"
        return f"{self.status} (Score: {self.score:+.1f}, {alignment_str})"


@dataclass
class PatternSignal:
    """Señal de patrón detectado."""
    symbol: str
    source: str  # "OANDA" o "FX"
    pattern: str  # "SHOOTING_STAR", "HANGING_MAN", "INVERTED_HAMMER", "HAMMER"
    timestamp: int
    candle: CandleData
    ema_5: float
    ema_7: float
    ema_10: float
    ema_15: float
    ema_20: float
    ema_30: float
    ema_50: float
    trend: str  # "STRONG_BULLISH", "WEAK_BULLISH", "NEUTRAL", "WEAK_BEARISH", "STRONG_BEARISH"
    trend_score: float  # Score numérico de -10.0 a +10.0 (weighted)
    is_trend_aligned: bool  # Si las EMAs están alineadas correctamente
    confidence: float  # 0.0 - 1.0 (del patrón de vela)
    trend_filtered: bool  # True si se aplicó filtro de tendencia
    chart_base64: Optional[str] = None  # Gráfico codificado en Base64
    statistics: Optional[Dict] = None  # Estadísticas históricas de probabilidad
    # Sistema de scoring matricial
    signal_strength: str = "NONE"  # "VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW", "NONE"
    exhaustion_type: str = "NONE"  # "PEAK", "BOTTOM", "NONE" (Bollinger Exhaustion)
    candle_exhaustion: bool = False  # True si rompe high/low de vela anterior
    is_counter_trend: bool = False  # True si patrón va contra la tendencia principal
    bb_upper: Optional[float] = None  # Banda superior de Bollinger
    bb_lower: Optional[float] = None  # Banda inferior de Bollinger


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


def calculate_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.5) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calcula las Bandas de Bollinger (Upper, Middle, Lower).
    
    Args:
        series: Serie de precios (típicamente Close)
        period: Periodo de la media móvil (default: 20)
        std_dev: Multiplicador de desviación estándar (default: 2.5 para agotamiento)
        
    Returns:
        tuple: (middle_band, upper_band, lower_band)
            - middle_band: Media móvil simple (SMA)
            - upper_band: SMA + (std_dev * desviación estándar)
            - lower_band: SMA - (std_dev * desviación estándar)
    """
    # Media móvil simple (línea central)
    middle_band = series.rolling(window=period).mean()
    
    # Desviación estándar
    rolling_std = series.rolling(window=period).std()
    
    # Bandas superior e inferior
    upper_band = middle_band + (rolling_std * std_dev)
    lower_band = middle_band - (rolling_std * std_dev)
    
    return middle_band, upper_band, lower_band


def detect_exhaustion(candle_high: float, candle_low: float, candle_close: float, 
                      upper_band: float, lower_band: float) -> str:
    """
    Detecta si una vela está en zona de agotamiento de tendencia (Cúspide o Base).
    
    Definiciones:
    - PEAK (Cúspide): El High o Close de la vela toca/supera la banda superior.
    - BOTTOM (Base): El Low o Close de la vela toca/perfora la banda inferior.
    - NONE: La vela está en zona neutra (entre bandas).
    
    Args:
        candle_high: Precio máximo de la vela
        candle_low: Precio mínimo de la vela
        candle_close: Precio de cierre de la vela
        upper_band: Valor de la banda superior de Bollinger
        lower_band: Valor de la banda inferior de Bollinger
        
    Returns:
        str: "PEAK", "BOTTOM" o "NONE"
    """
    # Si alguna banda es NaN, no podemos determinar agotamiento
    if pd.isna(upper_band) or pd.isna(lower_band):
        return "NONE"
    
    # Verificar si está en Cúspide (agotamiento alcista)
    if candle_high >= upper_band or candle_close >= upper_band:
        return "PEAK"
    
    # Verificar si está en Base (agotamiento bajista)
    if candle_low <= lower_band or candle_close <= lower_band:
        return "BOTTOM"
    
    # Zona neutra
    return "NONE"


def get_candle_result_debug(
    pattern: str,
    trend_status: str,
    bollinger_exhaustion: bool,
    candle_exhaustion: bool
) -> str:
    """
    Genera un mensaje de debug mostrando qué condiciones se cumplieron para el scoring.
    
    Args:
        pattern: Tipo de patrón (SHOOTING_STAR, HAMMER, etc.)
        trend_status: Estado de tendencia (STRONG_BULLISH, WEAK_BULLISH, etc.)
        bollinger_exhaustion: Si hay agotamiento Bollinger (PEAK o BOTTOM)
        candle_exhaustion: Si hay agotamiento de vela (rompió high/low anterior)
        
    Returns:
        String con información de debug formateada
    """
    # Determinar si es tendencia alcista o bajista
    is_bullish_trend = "BULLISH" in trend_status
    is_bearish_trend = "BEARISH" in trend_status
    is_neutral = trend_status == "NEUTRAL"
    
    # Determinar si el patrón es bajista o alcista
    pattern_is_bearish = pattern in ["SHOOTING_STAR", "INVERTED_HAMMER"]
    pattern_is_bullish = pattern in ["HAMMER", "HANGING_MAN"]
    
    # Construir mensaje
    lines = []
    lines.append("\n")
    lines.append("🔍 Mensaje de info")
    
    # 1. Verificar tendencia requerida
    if pattern_is_bearish and is_bullish_trend:
        # Patrón bajista necesita tendencia alcista
        lines.append("✅ Cumple Tendencia Alcista")
    elif pattern_is_bullish and is_bearish_trend:
        # Patrón alcista necesita tendencia bajista
        lines.append("✅ Cumple Tendencia Bajista")
    elif is_neutral:
        lines.append("⚠️ Tendencia NEUTRAL (penaliza score)")
    else:
        # Tendencia no coincide con el patrón
        if pattern_is_bearish:
            lines.append("❌ Cumple Tendencia alcista")
        else:
            lines.append("❌ Cumple Tendencia bajista")
    
    # 2. Verificar Bollinger Exhaustion
    if bollinger_exhaustion:
        lines.append("✅ Agotamiento Bollinger (PEAK/BOTTOM)")
    else:
        lines.append("❌ Agotamiento Bollinger (NO)")
    
    # 3. Verificar Candle Exhaustion
    if candle_exhaustion:
        lines.append("✅ Agotamiento de Vela (rompió nivel anterior)")
    else:
        lines.append("❌ Agotamiento de Vela (NO)")

    lines.append("\n")
    
    return "\n".join(lines)


def analyze_trend(close: float, emas: Dict[str, float]) -> TrendAnalysis:
    """
    Analiza tendencia usando sistema de PUNTUACIÓN PONDERADA.
    Cada EMA contribuye con un peso específico al score total.
    
    SISTEMA DE PESOS (Total: 10.0):
    - EMA 5:  2.0 puntos
    - EMA 7:  2.0 puntos
    - EMA 10: 1.5 puntos
    - EMA 15: 1.5 puntos
    - EMA 20: 1.0 punto
    - EMA 30: 1.0 punto
    - EMA 50: 1.0 punto
    
    CLASIFICACIÓN:
    - [6.0 a 10.0]:   STRONG_BULLISH
    - [2.0 a 6.0):    WEAK_BULLISH
    - (-2.0 a 2.0):   NEUTRAL
    - (-6.0 a -2.0]:  WEAK_BEARISH
    - [-10.0 a -6.0]: STRONG_BEARISH
    
    Args:
        close: Precio de cierre actual
        emas: Diccionario con valores de EMAs (ema_5, ema_7, ema_10, ema_15, ema_20, ema_30, ema_50)
        
    Returns:
        TrendAnalysis con estado, score (float) e is_aligned
    """
    # Definir pesos de EMAs (Total: 10.0)
    ema_weights = {
        'ema_5': 2.5,
        'ema_7': 2.0,
        'ema_10': 1.5,
        'ema_15': 1.5,
        'ema_20': 1.0,
        'ema_30': 1.0,
        'ema_50': 0.5
    }
    
    # Inicializar score
    score = 0.0
    
    # Calcular score ponderado iterando sobre cada EMA
    for ema_key, weight in ema_weights.items():
        ema_value = emas.get(ema_key, np.nan)
        
        # Si la EMA no existe o es NaN, omitir (no afecta el score)
        if pd.isna(ema_value):
            continue
        
        # Comparar precio con EMA y sumar/restar peso
        if close > ema_value:
            score += weight  # Alcista
        elif close < ema_value:
            score -= weight  # Bajista
        # Si close == ema_value, no suma ni resta (neutral)
    
    # Redondear score a 1 decimal
    score = round(score, 1)
    
    # Clasificar tendencia según umbrales
    if score >= 6.0:
        status = "STRONG_BULLISH"
    elif score >= 2.0:
        status = "WEAK_BULLISH"
    elif score > -2.0:
        status = "NEUTRAL"
    elif score > -6.0:
        status = "WEAK_BEARISH"
    else:  # score <= -6.0
        status = "STRONG_BEARISH"
    
    # Verificar alineación perfecta (Fanning)
    # Para considerar alineado, las EMAs deben estar en orden estricto
    is_aligned = False
    
    # Obtener EMAs principales para verificar alineación
    ema_5 = emas.get('ema_5', np.nan)
    ema_7 = emas.get('ema_7', np.nan)
    ema_10 = emas.get('ema_10', np.nan)
    ema_20 = emas.get('ema_20', np.nan)
    ema_50 = emas.get('ema_50', np.nan)
    
    # Verificar si todas las EMAs críticas están disponibles
    if not any(np.isnan([ema_5, ema_7, ema_10, ema_20, ema_50])):
        # Alineación alcista perfecta: Precio > EMA5 > EMA7 > EMA10 > EMA20 > EMA50
        if close > ema_5 > ema_7 > ema_10 > ema_20 > ema_50:
            is_aligned = True
        # Alineación bajista perfecta: Precio < EMA5 < EMA7 < EMA10 < EMA20 < EMA50
        elif close < ema_5 < ema_7 < ema_10 < ema_20 < ema_50:
            is_aligned = True
    
    return TrendAnalysis(
        status=status,
        score=score,
        is_aligned=is_aligned
    )


def get_ema_alignment_string(emas: Dict[str, float]) -> str:
    """
    Determina la alineación de las EMAs en formato string.
    Sistema de puntuación ponderada - verifica orden de EMAs principales.
    
    Args:
        emas: Diccionario con valores de EMAs (ema_5, ema_7, ema_10, ema_15, ema_20, ema_30, ema_50)
        
    Returns:
        String describiendo la alineación
    """
    ema_5 = emas.get('ema_5', np.nan)
    ema_7 = emas.get('ema_7', np.nan)
    ema_10 = emas.get('ema_10', np.nan)
    ema_20 = emas.get('ema_20', np.nan)
    ema_50 = emas.get('ema_50', np.nan)
    
    # Verificar datos completos (al menos las EMAs principales)
    if any(np.isnan([ema_7, ema_20, ema_50])):
        return "INCOMPLETE"
    
    # Alineación perfecta alcista: EMA5 > EMA7 > EMA10 > EMA20 > EMA50
    if not np.isnan(ema_5) and not np.isnan(ema_10):
        if ema_5 > ema_7 > ema_10 > ema_20 > ema_50:
            return "BULLISH_ALIGNED"
        elif ema_5 < ema_7 < ema_10 < ema_20 < ema_50:
            return "BEARISH_ALIGNED"
    
    # Alineación parcial (solo EMAs principales)
    if ema_7 > ema_20 > ema_50:
        return "BULLISH_PARTIAL"
    elif ema_7 < ema_20 < ema_50:
        return "BEARISH_PARTIAL"
    else:
        return "MIXED"


def get_ema_order_string(price: float, emas: Dict[str, float]) -> str:
    """
    Calcula el orden explícito de Precio y EMAs en formato string.
    Sistema de puntuación ponderada.
    
    Args:
        price: Precio actual de cierre
        emas: Diccionario con valores de EMAs del sistema ponderado
        
    Returns:
        String con el orden explícito (ej: "P>5>7>10>15>20>30>50", "50>30>20>P>15>10>7>5")
    """
    # Crear lista de tuplas (nombre, valor) solo con EMAs disponibles
    items = [('P', price)]
    
    ema_labels = {
        'ema_5': '5',
        'ema_7': '7',
        'ema_10': '10',
        'ema_15': '15',
        'ema_20': '20',
        'ema_30': '30',
        'ema_50': '50'
    }
    
    # Agregar solo las EMAs que existen y no son NaN
    for ema_key, ema_label in ema_labels.items():
        ema_value = emas.get(ema_key, np.nan)
        if not np.isnan(ema_value):
            items.append((ema_label, ema_value))
    
    # Verificar que tengamos suficientes datos
    if len(items) < 4:  # Al menos precio + 3 EMAs
        return "INCOMPLETE"
    
    # Ordenar por valor descendente (mayor a menor)
    items_sorted = sorted(items, key=lambda x: x[1], reverse=True)
    
    # Construir string con el orden
    order_string = '>'.join([item[0] for item in items_sorted])
    
    return order_string


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
        storage_service: Optional[object] = None,  # StorageService (evitamos import circular)
        telegram_service: Optional[object] = None,  # TelegramService para notificaciones de resultados
        statistics_service: Optional[object] = None  # StatisticsService para probabilidades
    ):
        """
        Inicializa el servicio de análisis.
        
        Args:
            on_pattern_detected: Callback invocado cuando se detecta un patrón válido
            storage_service: Instancia de StorageService para persistencia de dataset
            telegram_service: Instancia de TelegramService para notificaciones de resultados
            statistics_service: Instancia de StatisticsService para análisis de probabilidad
        """
        self.on_pattern_detected = on_pattern_detected
        self.storage_service = storage_service
        self.telegram_service = telegram_service
        self.statistics_service = statistics_service
        
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
            # LOG: Vela cerrada con hora y detalles OHLC
            from datetime import datetime
            candle_time = datetime.fromtimestamp(candle.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            logger.info(
                f"🕯️ VELA CERRADA | {source_key} | "
                f"Fecha: {candle_time} | "
                f"Apertura: {candle.open:.5f} | "
                f"Máximo: {candle.high:.5f} | "
                f"Mínimo: {candle.low:.5f} | "
                f"Cierre: {candle.close:.5f}"
            )
            
            # ═════════════════════════════════════════════════════════════
            # PASO 1: CERRAR CICLO ANTERIOR (Si existe señal pendiente)
            # ═════════════════════════════════════════════════════════════
            # CRÍTICO: Buscar la vela SIGUIENTE al trigger (trigger_timestamp + 60s)
            # NO usar df.iloc[-1] porque es la vela del patrón, no el outcome
            if source_key in self.pending_signals:
                pending_signal = self.pending_signals[source_key]
                df = self.dataframes[source_key]
                
                # Buscar la primera vela DESPUÉS del trigger (outcome candle)
                outcome_candidates = df[df['timestamp'] > pending_signal.timestamp]
                
                if len(outcome_candidates) > 0:
                    # Tomar la primera vela disponible después del trigger
                    outcome_row = outcome_candidates.iloc[0]
                    
                    # Calcular gap de timestamp
                    timestamp_diff = int(outcome_row['timestamp']) - pending_signal.timestamp
                    
                    # LOG: Mostrar vela encontrada y gap
                    logger.info(
                        f"📊 OUTCOME CANDLE ENCONTRADA:\n"
                        f"   Trigger: T={pending_signal.timestamp}\n"
                        f"   Outcome: T={int(outcome_row['timestamp'])} "
                        f"O={outcome_row['open']:.5f} H={outcome_row['high']:.5f} "
                        f"L={outcome_row['low']:.5f} C={outcome_row['close']:.5f}\n"
                        f"   Gap: {timestamp_diff}s {'✅' if timestamp_diff == 60 else '⚠️ (esperado: 60s)'}"
                    )
                    
                    outcome_candle = CandleData(
                        timestamp=int(outcome_row["timestamp"]),
                        open=outcome_row["open"],
                        high=outcome_row["high"],
                        low=outcome_row["low"],
                        close=outcome_row["close"],
                        volume=outcome_row["volume"],
                        source=candle.source,
                        symbol=candle.symbol
                    )
                    await self._close_signal_cycle(source_key, outcome_candle)
                else:
                    logger.warning(
                        f"⚠️  Señal pendiente pero no hay vela siguiente en DataFrame para {source_key}. "
                        f"Esperando más datos..."
                    )
            
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
            
            # PASO 4: GENERAR GRÁFICO SI ESTÁ HABILITADO (Config.GENERATE_HISTORICAL_CHARTS)
            if Config.GENERATE_HISTORICAL_CHARTS:
                asyncio.create_task(self._generate_realtime_chart(source_key, candle))
        
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
            "ema_5", "ema_7", "ema_10", "ema_15", "ema_20", "ema_30", "ema_50",
            "bb_middle", "bb_upper", "bb_lower"
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
        Si el timestamp ya existe (última vela), actualiza sus valores.
        Si es nueva, la agrega y mantiene el tamaño del buffer.
        
        Args:
            source_key: Clave de la fuente
            candle: Datos de la vela
        """
        df = self.dataframes[source_key]
        
        # Verificar si el DataFrame no está vacío y si el último timestamp coincide
        if not df.empty and df.iloc[-1]["timestamp"] == candle.timestamp:
            # ACTUALIZAR vela existente (Update in place)
            idx = df.index[-1]
            df.at[idx, "open"] = candle.open
            df.at[idx, "high"] = candle.high
            df.at[idx, "low"] = candle.low
            df.at[idx, "close"] = candle.close
            df.at[idx, "volume"] = candle.volume
            # Nota: Los indicadores se recalcularán en _update_indicators
            # logger.debug(f"🔄 Vela actualizada en buffer para {source_key} (T={candle.timestamp})")
            return

        # Si no existe, crear nueva fila
        new_row = pd.DataFrame([{
            "timestamp": candle.timestamp,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
            "ema_5": np.nan,
            "ema_7": np.nan,
            "ema_10": np.nan,
            "ema_15": np.nan,
            "ema_20": np.nan,
            "ema_30": np.nan,
            "ema_50": np.nan,
            "bb_middle": np.nan,
            "bb_upper": np.nan,
            "bb_lower": np.nan
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
        
        indexToSearch = -1  # Última fila
        # Actualizar última fila
        df.iloc[indexToSearch, df.columns.get_loc("high")] = max(df.iloc[indexToSearch]["high"], candle.high)
        df.iloc[indexToSearch, df.columns.get_loc("low")] = min(df.iloc[indexToSearch]["low"], candle.low)
        df.iloc[indexToSearch, df.columns.get_loc("close")] = candle.close
        df.iloc[indexToSearch, df.columns.get_loc("volume")] += candle.volume
    
    def _update_indicators(self, source_key: str) -> None:
        """
        Recalcula los indicadores técnicos para estrategia Mean Reversion.
        
        EMAs Calculadas (Sistema Ponderado):
        - EMA 5:  2.0 puntos - Ultra rápida
        - EMA 7:  2.0 puntos - Muy rápida
        - EMA 10: 1.5 puntos - Rápida
        - EMA 15: 1.5 puntos - Rápida-Media
        - EMA 20: 1.0 punto  - Media
        - EMA 30: 1.0 punto  - Media-Lenta
        - EMA 50: 1.0 punto  - Lenta
        
        Args:
            source_key: Clave de la fuente
        """
        df = self.dataframes[source_key]
        
        # Calcular EMAs sobre precios de cierre (sistema ponderado)
        # EMA 5 - Ultra rápida (peso: 2.0)
        if len(df) >= 5:
            df["ema_5"] = calculate_ema(df["close"], 5)
        
        # EMA 7 - Muy rápida (peso: 2.0)
        if len(df) >= 7:
            df["ema_7"] = calculate_ema(df["close"], 7)
        
        # EMA 10 - Rápida (peso: 1.5)
        if len(df) >= 10:
            df["ema_10"] = calculate_ema(df["close"], 10)
        
        # EMA 15 - Rápida-Media (peso: 1.5)
        if len(df) >= 15:
            df["ema_15"] = calculate_ema(df["close"], 15)
        
        # EMA 20 - Media (peso: 1.0)
        if len(df) >= 20:
            df["ema_20"] = calculate_ema(df["close"], 20)
        
        # EMA 30 - Media-Lenta (peso: 1.0)
        if len(df) >= 30:
            df["ema_30"] = calculate_ema(df["close"], 30)
        
        # EMA 50 - Lenta (peso: 1.0)
        if len(df) >= 50:
            df["ema_50"] = calculate_ema(df["close"], 50)
        
        # Calcular Bollinger Bands (requiere al menos BB_PERIOD velas)
        bb_period = Config.CANDLE.BB_PERIOD
        bb_std_dev = Config.CANDLE.BB_STD_DEV
        
        if len(df) >= bb_period:
            bb_middle, bb_upper, bb_lower = calculate_bollinger_bands(
                df["close"], 
                period=bb_period, 
                std_dev=bb_std_dev
            )
            df["bb_middle"] = bb_middle
            df["bb_upper"] = bb_upper
            df["bb_lower"] = bb_lower
    
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
        
        # Validar que el timestamp del outcome sea exactamente 60 segundos después
        timestamp_diff = outcome_candle.timestamp - pending_signal.timestamp
        expected_diff = 60  # 1 minuto (timeframe M1)
        
        if timestamp_diff != expected_diff:
            logger.warning(
                f"⚠️  ALERTA: GAP DE TIMESTAMP DETECTADO\n"
                f"   Señal: {pending_signal.timestamp}\n"
                f"   Resultado: {outcome_candle.timestamp}\n"
                f"   Diferencia: {timestamp_diff}s (esperado: {expected_diff}s)\n"
                f"   ❌ POSIBLE VELA SALTEADA - Dataset puede estar inconsistente\n"
            )
        
        logger.info(
            f"\n{'═'*60}\n"
            f"🔄 CERRANDO CICLO DE SEÑAL\n"
            f"{'═'*60}\n"
            f"📊 Fuente: {source_key}\n"
            f"🎯 Patrón Previo: {pending_signal.pattern}\n"
            f"🕒 Timestamp Señal: {pending_signal.timestamp}\n"
            f"🕒 Timestamp Resultado: {outcome_candle.timestamp}\n"
            f"⏱️  Diferencia: {timestamp_diff}s\n"
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
        
        # Determinar dirección actual de la vela de resultado usando la función de candle.py
        actual_direction = get_candle_direction(outcome_candle.open, outcome_candle.close)
        
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
        
        # Calcular alineación de EMAs en formato string
        emas_dict = {
            'ema_5': pending_signal.ema_5,
            'ema_7': pending_signal.ema_7,
            'ema_10': pending_signal.ema_10,
            'ema_15': pending_signal.ema_15,
            'ema_20': pending_signal.ema_20,
            'ema_30': pending_signal.ema_30,
            'ema_50': pending_signal.ema_50
        }
        ema_alignment = get_ema_alignment_string(emas_dict)
        
        # Calcular orden explícito de EMAs con precio
        ema_order = get_ema_order_string(pending_signal.candle.close, emas_dict)
        
        # Construir registro completo con nueva estructura optimizada
        from datetime import datetime
        record = {
            "timestamp": pending_signal.timestamp,
            "source": pending_signal.source,
            "symbol": pending_signal.symbol,
            "pattern_candle": {
                "timestamp": pending_signal.candle.timestamp,
                "open": pending_signal.candle.open,
                "high": pending_signal.candle.high,
                "low": pending_signal.candle.low,
                "close": pending_signal.candle.close,
                "volume": pending_signal.candle.volume,
                "pattern": pending_signal.pattern,
                "confidence": pending_signal.confidence
            },
            "emas": {
                "ema_5": pending_signal.ema_5,
                "ema_7": pending_signal.ema_7,
                "ema_10": pending_signal.ema_10,
                "ema_15": pending_signal.ema_15,
                "ema_20": pending_signal.ema_20,
                "ema_30": pending_signal.ema_30,
                "ema_50": pending_signal.ema_50,
                "alignment": ema_alignment,
                "ema_order": ema_order,
                "trend_score": pending_signal.trend_score
            },
            "bollinger": {
                "upper": pending_signal.bb_upper,
                "lower": pending_signal.bb_lower,
                "middle": None,  # Calculado en backfill, aquí no disponible
                "std_dev": Config.CANDLE.BB_STD_DEV,
                "exhaustion_type": pending_signal.exhaustion_type,
                "signal_strength": pending_signal.signal_strength,
                "is_counter_trend": pending_signal.is_counter_trend
            },
            "outcome_candle": {
                "timestamp": outcome_candle.timestamp,
                "open": outcome_candle.open,
                "high": outcome_candle.high,
                "low": outcome_candle.low,
                "close": outcome_candle.close,
                "volume": outcome_candle.volume,
                "direction": actual_direction
            },
            "outcome": {
                "expected_direction": expected_direction,
                "actual_direction": actual_direction,
                "success": success
            },
            "metadata": {
                "algo_version": Config.ALGO_VERSION,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "timestamp_gap_seconds": timestamp_diff,
                "expected_gap_seconds": expected_diff,
                "has_skipped_candles": timestamp_diff != expected_diff
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
        
        # Enviar notificación del resultado a Telegram si está disponible
        if self.telegram_service:
            try:
                # Obtener el chart del patrón original si existe
                chart_base64 = pending_signal.chart_base64 if hasattr(pending_signal, 'chart_base64') else None
                
                await self.telegram_service.send_outcome_notification(
                    source=pending_signal.source,
                    symbol=pending_signal.symbol,
                    direction=actual_direction,
                    chart_base64=chart_base64
                )
                logger.info(f"📨 Notificación de resultado enviada | Dirección: {actual_direction}")
            except Exception as e:
                log_exception(logger, "Error enviando notificación de resultado", e)
        else:
            logger.debug("⚠️  TelegramService no disponible - notificación de resultado no enviada")
        
        # Limpiar señal pendiente
        del self.pending_signals[source_key]
        
        logger.info(
            f"✅ CICLO CERRADO | "
            f"Éxito: {'✓' if success else '✗'} | "
            f"Esperado: {expected_direction} | Actual: {actual_direction}\n"
            f"{'═'*60}\n"
        )
    
    async def _analyze_last_closed_candle(self, source_key: str, current_candle: CandleData, force_notification: bool = False) -> None:
        """
        Analiza la última vela cerrada en busca de patrones y genera gráfico.
        Solo envía notificación si detecta uno de los 4 patrones con tendencia apropiada.
        
        AISLAMIENTO: Esta función se ejecuta de forma totalmente aislada por instrumento.
        El procesamiento de EURUSD no bloquea a GBPUSD.
        
        Args:
            source_key: Clave de la fuente
            current_candle: Vela actual (la siguiente a la cerrada)
            force_notification: Si True, envía notificación incluso sin patrón (uso interno)
        """
        # AISLAMIENTO: Crear task independiente para no bloquear otros instrumentos
        # Cada instrumento se procesa en su propia tarea asíncrona
        await asyncio.create_task(
            self._analyze_last_closed_candle_isolated(
                source_key,
                current_candle,
                force_notification
            )
        )
    
    async def _analyze_last_closed_candle_isolated(
        self,
        source_key: str,
        current_candle: CandleData,
        force_notification: bool = False
    ) -> None:
        """
        Análisis aislado de vela cerrada (ejecución independiente por instrumento).
        Esta función se ejecuta completamente aislada del resto de instrumentos.
        
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
        
        # ⚠️ VALIDACIÓN: Filtrar velas vacías (sin movimiento real)
        # TradingView envía primer tick de vela nueva con todos los valores iguales
        total_range = last_closed["high"] - last_closed["low"]
        if total_range == 0 or last_closed["volume"] == 0:
            logger.debug(
                f"⏭️  Vela vacía detectada (Range: {total_range}, Vol: {last_closed['volume']:.2f}). "
                "Saltando análisis."
            )
            return
        
        # # Verificar que EMA 200 esté disponible
        # if pd.isna(last_closed["ema_200"]):
        #     return
        
        # LOG: Información de la vela cerrada con todas las EMAs
        ema_5_val = last_closed.get('ema_5', np.nan)
        ema_7_val = last_closed.get('ema_7', np.nan)
        ema_10_val = last_closed.get('ema_10', np.nan)
        ema_15_val = last_closed.get('ema_15', np.nan)
        ema_20_val = last_closed.get('ema_20', np.nan)
        ema_30_val = last_closed.get('ema_30', np.nan)
        ema_50_val = last_closed.get('ema_50', np.nan)
        
        # Formatear EMAs (convertir a string antes)
        ema_5_str = f"{ema_5_val:.5f}" if not pd.isna(ema_5_val) else "N/A"
        ema_7_str = f"{ema_7_val:.5f}" if not pd.isna(ema_7_val) else "N/A"
        ema_10_str = f"{ema_10_val:.5f}" if not pd.isna(ema_10_val) else "N/A"
        ema_15_str = f"{ema_15_val:.5f}" if not pd.isna(ema_15_val) else "N/A"
        ema_20_str = f"{ema_20_val:.5f}" if not pd.isna(ema_20_val) else "N/A"
        ema_30_str = f"{ema_30_val:.5f}" if not pd.isna(ema_30_val) else "N/A"
        ema_50_str = f"{ema_50_val:.5f}" if not pd.isna(ema_50_val) else "N/A"
        
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
            f"📉 EMAs: 5={ema_5_str} | 7={ema_7_str} | 10={ema_10_str} | 15={ema_15_str} | 20={ema_20_str} | 30={ema_30_str} | 50={ema_50_str}\n"
            f"{'='*40}\n"
        )
        
        # Analizar tendencia con sistema de scoring ponderado
        emas_dict = {
            'ema_5': last_closed.get('ema_5', np.nan),
            'ema_7': last_closed.get('ema_7', np.nan),
            'ema_10': last_closed.get('ema_10', np.nan),
            'ema_15': last_closed.get('ema_15', np.nan),
            'ema_20': last_closed.get('ema_20', np.nan),
            'ema_30': last_closed.get('ema_30', np.nan),
            'ema_50': last_closed.get('ema_50', np.nan)
        }
        trend_analysis = analyze_trend(last_closed["close"], emas_dict)
        
        # Obtener Bollinger Bands para detección de agotamiento
        bb_upper = last_closed.get('bb_upper', np.nan)
        bb_lower = last_closed.get('bb_lower', np.nan)
        bb_middle = last_closed.get('bb_middle', np.nan)
        
        # Detectar si está en zona de agotamiento (Cúspide o Base)
        exhaustion_type = detect_exhaustion(
            last_closed["high"],
            last_closed["low"],
            last_closed["close"],
            bb_upper,
            bb_lower
        )
        
        # Formatear Bollinger Bands para logging (manejar NaN)
        bb_upper_str = f"{bb_upper:.5f}" if not pd.isna(bb_upper) else "N/A"
        bb_middle_str = f"{bb_middle:.5f}" if not pd.isna(bb_middle) else "N/A"
        bb_lower_str = f"{bb_lower:.5f}" if not pd.isna(bb_lower) else "N/A"
        
        logger.info(
            f"📈 Análisis de Tendencia: {trend_analysis}\n"
            f"   • Status: {trend_analysis.status}\n"
            f"   • Score: {trend_analysis.score:+.1f}/10.0 (weighted)\n"
            f"   • Alineación EMAs: {'✓' if trend_analysis.is_aligned else '✗'}\n"
            f"📊 Bollinger Bands:\n"
            f"   • Superior: {bb_upper_str}\n"
            f"   • Media: {bb_middle_str}\n"
            f"   • Inferior: {bb_lower_str}\n"
            f"   • Zona de Agotamiento: {exhaustion_type}\n"
        )
        
        # Detectar los 4 patrones de velas japonesas
        shooting_star_detected, shooting_star_conf, shooting_star_reason = is_shooting_star(
            last_closed["open"],
            last_closed["high"],
            last_closed["low"],
            last_closed["close"]
        )
        
        hanging_man_detected, hanging_man_conf, hanging_man_reason = is_hanging_man(
            last_closed["open"],
            last_closed["high"],
            last_closed["low"],
            last_closed["close"]
        )
        
        inverted_hammer_detected, inverted_hammer_conf, inverted_hammer_reason = is_inverted_hammer(
            last_closed["open"],
            last_closed["high"],
            last_closed["low"],
            last_closed["close"]
        )
        
        hammer_detected, hammer_conf, hammer_reason = is_hammer(
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
            # Mapear estados granulares a direcciones generales
            current_status = trend_analysis.status
            is_bearish = "BEARISH" in current_status  # STRONG_BEARISH o WEAK_BEARISH
            is_bullish = "BULLISH" in current_status  # STRONG_BULLISH o WEAK_BULLISH
            
            if is_bearish:
                # En tendencia bajista, buscar reversión alcista
                if hammer_detected:
                    pattern_detected = "HAMMER"
                    pattern_confidence = hammer_conf
                elif inverted_hammer_detected:
                    pattern_detected = "INVERTED_HAMMER"
                    pattern_confidence = inverted_hammer_conf
            elif is_bullish:
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
        
        # Si no hay patrón detectado, salir (force_notification no puede forzar patrones inexistentes)
        if not pattern_detected:
            logger.info("ℹ️  No se detectó ningún patrón relevante en esta vela.")
            return
        
        # ═════════════════════════════════════════════════════════════════════
        # CLASIFICACIÓN DE FUERZA DE SEÑAL - Mean Reversion Strategy (NUEVO)
        # ═════════════════════════════════════════════════════════════════════
        
        # NUEVA MATRIZ DE DECISIÓN con Candle Exhaustion
        # Importar función de candle.py
        from src.logic.candle import detect_candle_exhaustion
        
        # Obtener vela anterior para cálculo de Candle Exhaustion
        prev_candle_high = None
        prev_candle_low = None
        if len(df) >= 2:
            prev_row = df.iloc[-2]
            prev_candle_high = prev_row["high"]
            prev_candle_low = prev_row["low"]
        
        # Calcular Candle Exhaustion
        candle_exhaustion = False
        if prev_candle_high is not None and prev_candle_low is not None:
            candle_exhaustion = detect_candle_exhaustion(
                pattern=pattern_detected,
                current_high=last_closed["high"],
                current_low=last_closed["low"],
                prev_high=prev_candle_high,
                prev_low=prev_candle_low
            )
        
        # Determinar Bollinger Exhaustion (PEAK o BOTTOM)
        bollinger_exhaustion = exhaustion_type in ["PEAK", "BOTTOM"]
        
        # Clasificar patrones por tipo
        pattern_is_bearish = pattern_detected in ["SHOOTING_STAR", "HANGING_MAN"]
        pattern_is_bullish = pattern_detected in ["HAMMER", "INVERTED_HAMMER"]
        pattern_is_primary = pattern_detected in ["SHOOTING_STAR", "HAMMER"]
        
        # Determinar contexto de tendencia
        current_status = trend_analysis.status
        is_strong_bullish = current_status == "STRONG_BULLISH"
        is_weak_bullish = current_status == "WEAK_BULLISH"
        is_strong_bearish = current_status == "STRONG_BEARISH"
        is_weak_bearish = current_status == "WEAK_BEARISH"
        is_neutral = current_status == "NEUTRAL"
        
        is_bullish_trend = is_strong_bullish or is_weak_bullish
        is_bearish_trend = is_strong_bearish or is_weak_bearish
        
        # Variable de scoring
        signal_strength = "NONE"
        
        # ═════════════════════════════════════════════════════════════════════
        # CASO A: TENDENCIA ALCISTA (Buscamos VENTAS - Patrones Bajistas)
        # ═════════════════════════════════════════════════════════════════════
        if is_bullish_trend:
            if pattern_detected == "SHOOTING_STAR":
                # Patrón PRINCIPAL bajista
                if bollinger_exhaustion and candle_exhaustion:
                    signal_strength = "VERY_HIGH"
                    logger.info(f"🔥 VERY HIGH | Shooting Star + Bollinger + Candle Exhaustion en tendencia alcista")
                elif bollinger_exhaustion:
                    signal_strength = "HIGH"
                    logger.info(f"🚨 HIGH | Shooting Star + Bollinger Exhaustion en tendencia alcista")
                elif candle_exhaustion:
                    signal_strength = "LOW"
                    logger.info(f"ℹ️  LOW | Shooting Star + Candle Exhaustion (sin Bollinger)")
                else:
                    signal_strength = "VERY_LOW"
                    logger.info(f"⚪ VERY LOW | Shooting Star sin exhaustion")
            
            elif pattern_detected == "INVERTED_HAMMER":
                # Patrón SECUNDARIO bajista
                if bollinger_exhaustion and candle_exhaustion:
                    signal_strength = "MEDIUM"
                    logger.info(f"⚠️  MEDIUM | Inverted Hammer + ambos exhaustion en tendencia alcista")
                elif bollinger_exhaustion:
                    signal_strength = "LOW"
                    logger.info(f"ℹ️  LOW | Inverted Hammer + Bollinger Exhaustion")
                elif candle_exhaustion:
                    signal_strength = "VERY_LOW"
                    logger.info(f"⚪ VERY LOW | Inverted Hammer + Candle Exhaustion solamente")
                else:
                    signal_strength = "NONE"
                    logger.info(f"⛔ NONE | Inverted Hammer sin exhaustion - Descartado")
            
            # HANGING_MAN y HAMMER no son válidos en tendencia alcista para Mean Reversion
            elif pattern_detected == "HANGING_MAN":
                signal_strength = "NONE"
                logger.info(f"⛔ NONE | Hanging Man en tendencia alcista - Patrón no aplicable")
            
            elif pattern_detected == "HAMMER":
                signal_strength = "NONE"
                logger.info(f"⛔ NONE | Hammer en tendencia alcista - Contra-estrategia Mean Reversion")
        
        # ═════════════════════════════════════════════════════════════════════
        # CASO B: TENDENCIA BAJISTA (Buscamos COMPRAS - Patrones Alcistas)
        # ═════════════════════════════════════════════════════════════════════
        elif is_bearish_trend:
            if pattern_detected == "HAMMER":
                # Patrón PRINCIPAL alcista
                if bollinger_exhaustion and candle_exhaustion:
                    signal_strength = "VERY_HIGH"
                    logger.info(f"🔥 VERY HIGH | Hammer + Bollinger + Candle Exhaustion en tendencia bajista")
                elif bollinger_exhaustion:
                    signal_strength = "HIGH"
                    logger.info(f"🚨 HIGH | Hammer + Bollinger Exhaustion en tendencia bajista")
                elif candle_exhaustion:
                    signal_strength = "LOW"
                    logger.info(f"ℹ️  LOW | Hammer + Candle Exhaustion (sin Bollinger)")
                else:
                    signal_strength = "VERY_LOW"
                    logger.info(f"⚪ VERY LOW | Hammer sin exhaustion")
            
            elif pattern_detected == "HANGING_MAN":
                # Patrón SECUNDARIO alcista
                if bollinger_exhaustion and candle_exhaustion:
                    signal_strength = "MEDIUM"
                    logger.info(f"⚠️  MEDIUM | Hanging Man + ambos exhaustion en tendencia bajista")
                elif bollinger_exhaustion:
                    signal_strength = "LOW"
                    logger.info(f"ℹ️  LOW | Hanging Man + Bollinger Exhaustion")
                elif candle_exhaustion:
                    signal_strength = "VERY_LOW"
                    logger.info(f"⚪ VERY LOW | Hanging Man + Candle Exhaustion solamente")
                else:
                    signal_strength = "NONE"
                    logger.info(f"⛔ NONE | Hanging Man sin exhaustion - Descartado")
            
            # SHOOTING_STAR e INVERTED_HAMMER no son válidos en tendencia bajista para Mean Reversion
            elif pattern_detected == "SHOOTING_STAR":
                signal_strength = "NONE"
                logger.info(f"⛔ NONE | Shooting Star en tendencia bajista - Contra-estrategia Mean Reversion")
            
            elif pattern_detected == "INVERTED_HAMMER":
                signal_strength = "NONE"
                logger.info(f"⛔ NONE | Inverted Hammer en tendencia bajista - Patrón no aplicable")
        
        # ═════════════════════════════════════════════════════════════════════
        # CASO C: NEUTRAL (Reducir un nivel de fuerza)
        # ═════════════════════════════════════════════════════════════════════
        elif is_neutral:
            logger.info(f"⚖️  Tendencia NEUTRAL detectada - Reduciendo scoring un nivel")
            
            # Evaluar igual que si hubiera tendencia, pero degradar resultado
            temp_strength = "NONE"
            
            if pattern_detected == "SHOOTING_STAR":
                if bollinger_exhaustion and candle_exhaustion:
                    temp_strength = "HIGH"  # Se degradará a MEDIUM
                elif bollinger_exhaustion:
                    temp_strength = "MEDIUM"  # Se degradará a LOW
                elif candle_exhaustion:
                    temp_strength = "VERY_LOW"  # Se degradará a NONE
                else:
                    temp_strength = "NONE"
            
            elif pattern_detected == "HAMMER":
                if bollinger_exhaustion and candle_exhaustion:
                    temp_strength = "HIGH"  # Se degradará a MEDIUM
                elif bollinger_exhaustion:
                    temp_strength = "MEDIUM"  # Se degradará a LOW
                elif candle_exhaustion:
                    temp_strength = "VERY_LOW"  # Se degradará a NONE
                else:
                    temp_strength = "NONE"
            
            elif pattern_detected in ["INVERTED_HAMMER", "HANGING_MAN"]:
                if bollinger_exhaustion and candle_exhaustion:
                    temp_strength = "LOW"  # Se degradará a VERY_LOW
                elif bollinger_exhaustion:
                    temp_strength = "VERY_LOW"  # Se degradará a NONE
                else:
                    temp_strength = "NONE"
            
            # Degradar un nivel
            downgrade_map = {
                "VERY_HIGH": "HIGH",
                "HIGH": "MEDIUM",
                "MEDIUM": "LOW",
                "LOW": "VERY_LOW",
                "VERY_LOW": "NONE",
                "NONE": "NONE"
            }
            signal_strength = downgrade_map.get(temp_strength, "NONE")
            logger.info(f"➡️  Score degradado de {temp_strength} a {signal_strength} por tendencia NEUTRAL")
        
        # Determinar si el patrón es "contra-tendencia" (para compatibilidad con storage)
        is_counter_trend = False
        if pattern_is_bearish and is_bearish_trend:
            is_counter_trend = True  # Patrón bajista en tendencia bajista
        elif pattern_is_bullish and is_bullish_trend:
            is_counter_trend = True  # Patrón alcista en tendencia alcista
        
        # Determinar alineación tradicional (para compatibilidad)
        is_trend_aligned = False
        if pattern_is_bearish:
            is_trend_aligned = is_bullish_trend  # Bajista espera tendencia alcista
        elif pattern_is_bullish:
            is_trend_aligned = is_bearish_trend  # Alcista espera tendencia bajista
        
        logger.info(
            f"\n{'═'*60}\n"
            f"🎯 PATRÓN DETECTADO: {pattern_detected}\n"
            f"{'═'*60}\n"
            f"📊 Confianza Técnica: {pattern_confidence:.1%}\n"
            f"📈 Tendencia: {trend_analysis.status} (Score: {trend_analysis.score:+.1f}/10.0)\n"
            f"🔄 Alineación: {'✓ Alineado' if is_trend_aligned else '✗ No alineado'}\n"
            f"💥 Candle Exhaustion: {'✅ SÍ' if candle_exhaustion else '❌ NO'}\n"
            f"📍 Bollinger Exhaustion: {'✅ ' + exhaustion_type if bollinger_exhaustion else '❌ NONE'}\n"
            f"🎚️  Fuerza de Señal: {signal_strength}\n"
            f"⚠️  Contra-Tendencia: {'SÍ' if is_counter_trend else 'NO'}\n"
        )
        
        # Notificar al TelegramService con la información completa
        # force_notification omite validación de confianza mínima (útil para testing/debug)
        should_notify = pattern_confidence >= 0.70 or force_notification
        
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
                    import time
                    start_time = time.perf_counter()
                    
                    chart_base64 = await asyncio.to_thread(
                        generate_chart_base64,
                        df,
                        self.chart_lookback,
                        chart_title
                    )
                    
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    
                    logger.info(
                        f"✅ GRÁFICO GENERADO | {source_key} | "
                        f"Tamaño: {len(chart_base64)} bytes Base64 | "
                        f"Tiempo: {elapsed_ms:.1f}ms | Patrón: {pattern_detected}"
                    )
                else:
                    logger.warning(f"⚠️  No se pudo generar gráfico: {error_msg}")
            
            except Exception as e:
                log_exception(logger, "Failed to generate chart", e)
                # Continuar sin gráfico si hay error
                chart_base64 = None
            
            # En este punto siempre hay un patrón detectado
            
            # Consultar estadísticas históricas si hay StatisticsService disponible
            statistics = None
            if self.statistics_service:
                try:
                    # Calcular alignment y ema_order para búsqueda precisa
                    emas_dict = {
                        'ema_200': last_closed["ema_200"],
                        'ema_50': last_closed.get("ema_50", np.nan),
                        'ema_30': last_closed.get("ema_30", np.nan),
                        'ema_20': last_closed.get("ema_20", np.nan)
                    }
                    current_alignment = get_ema_alignment_string(emas_dict)
                    current_ema_order = get_ema_order_string(last_closed["close"], emas_dict)
                    
                    # Extraer source y symbol del source_key (formato: "SOURCE_SYMBOL")
                    source, symbol = source_key.split("_", 1) if "_" in source_key else (source_key, "UNKNOWN")
                    
                    statistics = self.statistics_service.get_probability(
                        pattern=pattern_detected,
                        current_score=trend_analysis.score,
                        current_exhaustion_type=exhaustion_type,
                        source=source,
                        symbol=symbol,
                        current_alignment=current_alignment,
                        current_ema_order=current_ema_order,
                        lookback_days=30,
                        score_tolerance=2
                    )
                    
                    exact_cases = statistics.get('exact', {}).get('total_cases', 0)
                    by_score_cases = statistics.get('by_score', {}).get('total_cases', 0)
                    by_range_cases = statistics.get('by_range', {}).get('total_cases', 0)
                    
                    logger.debug(
                        f"📊 Estadísticas obtenidas (Zona: {exhaustion_type}) | "
                        f"Exact: {exact_cases} | "
                        f"By Score: {by_score_cases} | "
                        f"By Range: {by_range_cases}"
                    )
                except Exception as e:
                    logger.warning(f"⚠️  Error obteniendo estadísticas: {e}")
            
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
                ema_5=last_closed.get("ema_5", np.nan),
                ema_7=last_closed.get("ema_7", np.nan),
                ema_10=last_closed.get("ema_10", np.nan),
                ema_15=last_closed.get("ema_15", np.nan),
                ema_20=last_closed.get("ema_20", np.nan),
                ema_30=last_closed.get("ema_30", np.nan),
                ema_50=last_closed.get("ema_50", np.nan),
                trend=trend_analysis.status,
                trend_score=trend_analysis.score,
                is_trend_aligned=trend_analysis.is_aligned,
                confidence=pattern_confidence,
                trend_filtered=Config.USE_TREND_FILTER,
                chart_base64=chart_base64,
                statistics=statistics,
                # Campos del nuevo sistema de scoring
                signal_strength=signal_strength,
                exhaustion_type=exhaustion_type,
                candle_exhaustion=candle_exhaustion,
                is_counter_trend=is_counter_trend,
                bb_upper=float(bb_upper) if not pd.isna(bb_upper) else None,
                bb_lower=float(bb_lower) if not pd.isna(bb_lower) else None
            )
            
            logger.info(
                f"🎯 PATTERN DETECTED | {signal.source} | {signal.pattern} | "
                f"Trend={trend_analysis.status} (Score: {trend_analysis.score:+.1f}/10.0) | "
                f"Strength={signal_strength} | Exhaustion={exhaustion_type} | "
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
    
    async def _generate_realtime_chart(self, source_key: str, candle: CandleData) -> None:
        """
        Genera y guarda un gráfico PNG para la vela cerrada actual.
        Solo se ejecuta si Config.GENERATE_HISTORICAL_CHARTS == True.
        
        Args:
            source_key: Clave de la fuente (ej: "IQOPTION_BID_EURUSD")
            candle: Vela que acaba de cerrar
        """
        try:
            from pathlib import Path
            from datetime import datetime
            import base64
            from src.utils.charting import generate_chart_base64
            
            df = self.dataframes.get(source_key)
            if df is None or len(df) < 10:
                return
            
            # Generar gráfico
            chart_title = f"{candle.source}:{candle.symbol} - Real-Time"
            chart_base64 = await asyncio.to_thread(
                generate_chart_base64,
                df,
                self.chart_lookback,
                chart_title
            )
            
            # Guardar en archivo
            candle_time = datetime.fromtimestamp(candle.timestamp)
            timestamp_str = candle_time.strftime("%Y%m%d_%H%M%S")
            
            chart_dir = Path("data") / "charts" / candle.symbol / "realtime"
            chart_dir.mkdir(parents=True, exist_ok=True)
            
            chart_path = chart_dir / f"candle_{timestamp_str}.png"
            
            with open(chart_path, "wb") as f:
                f.write(base64.b64decode(chart_base64))
            
            logger.info(f"📊 Gráfico en tiempo real guardado: {chart_path}")
            
        except Exception as e:
            log_exception(logger, "Error generando gráfico en tiempo real", e)
    
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
