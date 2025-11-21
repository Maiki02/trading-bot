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
    trend: str  # "BEARISH", "BULLISH", "NEUTRAL"
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
        
        logger.info(f"📊 Analysis Service inicializado (Período EMA: {self.ema_period})")
    
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
    
    def process_realtime_candle(self, candle: CandleData) -> None:
        """
        Procesa una vela en tiempo real del WebSocket.
        Genera gráficos y envía notificaciones a Telegram.
        
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
            
            # Agregar la vela anterior al buffer antes de procesar la nueva
            self._add_new_candle(source_key, candle)
            
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
            # Solo envía notificación si detecta uno de los 4 patrones
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
            f"📉 EMAs: 20={ema_20_val:.5f if not pd.isna(ema_20_val) else 'N/A'} | "
            f"30={ema_30_val:.5f if not pd.isna(ema_30_val) else 'N/A'} | "
            f"50={ema_50_val:.5f if not pd.isna(ema_50_val) else 'N/A'} | "
            f"100={ema_100_val:.5f if not pd.isna(ema_100_val) else 'N/A'} | "
            f"200={last_closed['ema_200']:.5f}\n"
            f"{'='*40}\n"
        )
        
        # Determinar tendencia
        trend = self._determine_trend(last_closed["close"], last_closed["ema_200"])
        
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
                trend=trend,
                confidence=pattern_confidence,
                trend_filtered=Config.USE_TREND_FILTER,
                chart_base64=chart_base64
            )
            
            logger.info(
                f"🎯 PATTERN DETECTED | {signal.source} | {signal.pattern} | "
                f"Trend={trend} | Close={signal.candle.close:.5f} vs EMA200={signal.ema_200:.5f} | "
                f"Confidence={signal.confidence:.2f} | Chart={'✓' if chart_base64 else '✗'}"
            )
            
            # Guardar vela detectada en test_data.json
            await self._save_detected_candle_to_test_data(
                last_closed["open"],
                last_closed["high"],
                last_closed["low"],
                last_closed["close"],
                pattern_detected
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
