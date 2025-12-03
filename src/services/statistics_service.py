"""
Statistics Service - Historical Probability Analysis
=====================================================
Servicio de análisis de probabilidades históricas basado en datos crudos.
Recalcula scores al vuelo para permitir cambios en la lógica de análisis.

Responsabilidades:
- Cargar dataset JSONL en pandas DataFrame
- Normalizar scores usando lógica actual de análisis
- Calcular probabilidades de éxito por patrón y score
- Proporcionar estadísticas en tiempo real para alertas

Author: TradingView Pattern Monitor Team
"""
import os
import json
import pandas as pd
import numpy as np
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.utils.logger import get_logger
from src.logic.analysis_service import analyze_trend


logger = get_logger(__name__)


class StatisticsService:
    """
    Servicio de análisis estadístico de señales históricas.
    
    Funcionalidades:
    - Carga de dataset JSONL con validación
    - Normalización de scores usando lógica actual
    - Queries de probabilidad con fuzzy matching
    - Análisis de rachas (streaks) de éxito/fracaso
    """
    
    def __init__(self, data_path: str = "data/trading_signals_dataset.jsonl"):
        """
        Inicializa el servicio de estadísticas.
        
        Args:
            data_path: Ruta al archivo JSONL con el dataset
        """
        self.data_path = Path(data_path)
        self.df: Optional[pd.DataFrame] = None
        self.last_load_time: Optional[datetime] = None
        self.records_loaded: int = 0
        
        # Cargar dataset al inicializar
        self._load_dataset()
        
        logger.info(
            f"📊 Statistics Service inicializado | "
            f"Registros: {self.records_loaded} | "
            f"Archivo: {self.data_path}"
        )
    
    def _load_dataset(self) -> None:
        """
        Carga el dataset JSONL en un DataFrame de pandas.
        Maneja casos donde el archivo no existe o está vacío.
        """
        if not self.data_path.exists():
            logger.warning(f"⚠️  Dataset no existe: {self.data_path}. Creando DataFrame vacío.")
            self.df = pd.DataFrame()
            self.records_loaded = 0
            return
        
        try:
            # Leer JSONL línea por línea
            records = []
            with open(self.data_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:  # Ignorar líneas vacías
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError as e:
                            logger.warning(f"⚠️  Línea JSONL inválida ignorada: {e}")
            
            if not records:
                logger.warning(f"⚠️  Dataset vacío: {self.data_path}")
                self.df = pd.DataFrame()
                self.records_loaded = 0
                return
            
            # Crear DataFrame
            self.df = pd.DataFrame(records)
            self.records_loaded = len(self.df)
            self.last_load_time = datetime.utcnow()
            
            # Normalizar scores usando lógica actual
            self._normalize_scores()
            
            logger.info(
                f"✅ Dataset cargado | "
                f"Registros: {self.records_loaded} | "
                f"Columnas: {list(self.df.columns)}"
            )
            
        except Exception as e:
            logger.error(f"❌ Error al cargar dataset: {e}", exc_info=True)
            self.df = pd.DataFrame()
            self.records_loaded = 0
    
    def _normalize_scores(self) -> None:
        """
        Recalcula scores usando la lógica actual de analyze_trend.
        Esto permite "viajar en el tiempo" y aplicar la lógica de hoy
        a datos históricos guardados con versiones anteriores del algoritmo.
        
        Crea/actualiza la columna 'calculated_score' en el DataFrame.
        """
        if self.df is None or self.df.empty:
            return
        
        # Verificar que existan las columnas de estructura V2
        if 'emas' not in self.df.columns or 'pattern_candle' not in self.df.columns:
            logger.warning("⚠️  Estructura V2 no detectada. No se pueden recalcular scores.")
            self.df['calculated_score'] = np.nan
            return
        
        calculated_scores = []
        
        for idx, row in self.df.iterrows():
            try:
                # Extraer datos de la nueva estructura V2
                emas_data = row['emas']
                pattern_candle = row['pattern_candle']
                
                # Extraer close de pattern_candle
                close = pattern_candle.get('close')
                
                # Extraer EMAs (Sistema V6)
                emas = {
                    'ema_3': emas_data.get('ema_3'),
                    'ema_5': emas_data.get('ema_5'),
                    'ema_7': emas_data.get('ema_7'),
                    'ema_10': emas_data.get('ema_10'),
                    'ema_20': emas_data.get('ema_20')
                }
                
                # Validar que tengamos los datos necesarios
                if close is None or any(v is None for v in emas.values()):
                    calculated_scores.append(np.nan)
                    continue
                
                # Recalcular score usando lógica actual
                trend_analysis = analyze_trend(close, emas)
                calculated_scores.append(trend_analysis.score)
                
            except Exception as e:
                logger.warning(f"⚠️  Error al recalcular score en fila {idx}: {e}")
                calculated_scores.append(np.nan)
        
        # Agregar columna al DataFrame
        self.df['calculated_score'] = calculated_scores
        
        valid_scores = sum(1 for s in calculated_scores if not pd.isna(s))
        logger.info(
            f"✅ Scores recalculados | "
            f"Válidos: {valid_scores}/{len(calculated_scores)}"
        )
    
    def get_probability(
        self,
        pattern: str,
        current_score: int,
        current_exhaustion_type: str,
        source: str,
        symbol: str,
        current_alignment: Optional[str] = None,
        current_ema_order: Optional[str] = None,
        lookback_days: int = 30,
        score_tolerance: int = 2
    ) -> Dict[str, any]:
        """
        Calcula probabilidades con filtrado contextual estricto por zona de volatilidad.
        
        CAMBIO CRÍTICO: exhaustion_type es ahora un FILTRO OBLIGATORIO (Hard Filter).
        Nunca mezcla estadísticas de PEAK con BOTTOM o NONE.
        
        FILTRADO POR INSTRUMENTO: Solo usa datos del mismo source+symbol para evitar
        mezclar estadísticas de diferentes instrumentos con características distintas.
        
        Args:
            pattern: Tipo de patrón (ej: "SHOOTING_STAR", "HAMMER")
            current_score: Score de tendencia actual
            current_exhaustion_type: Zona de volatilidad actual ("PEAK", "BOTTOM", "NONE")
            source: Fuente del dato (ej: "BINANCE", "OANDA")
            symbol: Símbolo del instrumento (ej: "BTCUSDT", "EURUSD")
            current_alignment: Alineación actual (ej: "BULLISH_ALIGNED")
            current_ema_order: Orden explícito actual (ej: "P>20>30>50>200")
            lookback_days: Ventana de tiempo en días (default: 30)
            score_tolerance: Tolerancia para fuzzy matching (default: ±2)
            
        Returns:
            Dict con estructura:
            {
                "exact": {                # 🎯 GEMELO: Patrón + Exhaustion + Score + Alignment
                    "total_cases": int,
                    "verde_count": int,
                    "roja_count": int,
                    "verde_pct": float,
                    "roja_pct": float,
                    "expected_direction": str,
                    "streak": list  # Racha específica de este subgrupo
                },
                "by_score": {             # ⚖️ PRECISIÓN MEDIA: Patrón + Exhaustion + Score Exacto
                    "total_cases": int,
                    "verde_count": int,
                    "roja_count": int,
                    "verde_pct": float,
                    "roja_pct": float,
                    "expected_direction": str,
                    "streak": list
                },
                "by_range": {             # 📉 MÁXIMA MUESTRA: Patrón + Exhaustion + Score ±tolerance
                    "total_cases": int,
                    "verde_count": int,
                    "roja_count": int,
                    "verde_pct": float,
                    "roja_pct": float,
                    "expected_direction": str,
                    "score_range": tuple,
                    "streak": list
                },
                "exhaustion_type": str,   # Zona de volatilidad filtrada
                "lookback_days": int
            }
        """
        if self.df is None or self.df.empty:
            logger.warning(
                f"⚠️  Dataset vacío | "
                f"Buscando: source={source}, symbol={symbol}, pattern={pattern}, "
                f"score={current_score}, exhaustion={current_exhaustion_type}"
            )
            return self._empty_stats_response(current_exhaustion_type)
        
        # Filtrar por ventana de tiempo (usar UTC con timezone para comparación correcta)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        
        # Convertir timestamp a datetime (timestamp está en SEGUNDOS Unix)
        try:
            self.df['timestamp_dt'] = pd.to_datetime(self.df['timestamp'], unit='s', utc=True)
        except Exception as e:
            logger.warning(f"⚠️  No se pudo parsear columna 'timestamp': {e}")
            return self._empty_stats_response(current_exhaustion_type)
        
        df_filtered = self.df[self.df['timestamp_dt'] >= cutoff_date].copy()
        
        logger.info(
            f"📊 Iniciando búsqueda de estadísticas | "
            f"Source: {source} | Symbol: {symbol} | "
            f"Pattern: {pattern} | Score: {current_score} | "
            f"Exhaustion: {current_exhaustion_type} | "
            f"Lookback: {lookback_days} días | Registros disponibles: {len(self.df)}"
        )
        
        if df_filtered.empty:
            logger.warning(
                f"⚠️  No hay datos en ventana de {lookback_days} días | "
                f"Total registros en dataset: {len(self.df)} | "
                f"Fecha de corte: {cutoff_date.isoformat()}"
            )
            return self._empty_stats_response(current_exhaustion_type)
        
        # ═════════════════════════════════════════════════════════
        # FILTRO CRÍTICO: SOURCE Y SYMBOL (Hard Filter)
        # ═════════════════════════════════════════════════════════
        # Filtrar por source y symbol exactos
        df_filtered = df_filtered[
            (df_filtered['source'] == source) &
            (df_filtered['symbol'] == symbol)
        ]
        
        if df_filtered.empty:
            logger.info(
                f"📊 No hay datos para el instrumento {source}:{symbol} en ventana de {lookback_days} días"
            )
            return self._empty_stats_response(current_exhaustion_type)
        
        # Filtrar por patrón exacto (nueva estructura V2)
        if 'pattern_candle' not in df_filtered.columns:
            logger.warning("⚠️  Columna 'pattern_candle' no existe")
            return self._empty_stats_response(current_exhaustion_type)
        
        # Extraer patrón del objeto pattern_candle
        df_filtered['pattern'] = df_filtered['pattern_candle'].apply(
            lambda x: x.get('pattern') if isinstance(x, dict) else None
        )
        
        df_filtered = df_filtered[df_filtered['pattern'] == pattern]
        
        if df_filtered.empty:
            logger.info(f"📊 No hay datos para {source}:{symbol} con patrón {pattern}")
            return self._empty_stats_response(current_exhaustion_type)
        
        # ═════════════════════════════════════════════════════════
        # FILTRO CRÍTICO: EXHAUSTION_TYPE (Hard Filter)
        # ═════════════════════════════════════════════════════════
        # Extraer exhaustion_type del bloque bollinger
        df_filtered['exhaustion_type'] = df_filtered['bollinger'].apply(
            lambda x: x.get('exhaustion_type') if isinstance(x, dict) else None
        )
        
        # Aplicar filtro obligatorio por zona de volatilidad
        df_filtered = df_filtered[df_filtered['exhaustion_type'] == current_exhaustion_type]
        
        if df_filtered.empty:
            logger.info(
                f"📊 No hay datos para {source}:{symbol} con patrón {pattern} en zona {current_exhaustion_type}"
            )
            return self._empty_stats_response(current_exhaustion_type)
        
        # Extraer columnas necesarias de la estructura V2
        df_filtered['success'] = df_filtered['outcome'].apply(
            lambda x: x.get('success') if isinstance(x, dict) else False
        )
        df_filtered['expected_direction'] = df_filtered['outcome'].apply(
            lambda x: x.get('expected_direction') if isinstance(x, dict) else None
        )
        df_filtered['actual_direction'] = df_filtered['outcome'].apply(
            lambda x: x.get('actual_direction') if isinstance(x, dict) else None
        )
        df_filtered['alignment'] = df_filtered['emas'].apply(
            lambda x: x.get('alignment') if isinstance(x, dict) else None
        )
        
        # ═════════════════════════════════════════════════════════
        # 1. EXACT (GEMELO): Patrón + Exhaustion + Score + Alignment
        # ═════════════════════════════════════════════════════════
        exact_stats = self._empty_single_stats()
        
        if current_alignment:
            df_exact = df_filtered[
                (df_filtered['calculated_score'] == current_score) &
                (df_filtered['alignment'] == current_alignment)
            ]
            
            if not df_exact.empty:
                exact_stats = self._calculate_direction_stats(df_exact, pattern)
                # Racha específica de este subgrupo (últimos 5)
                exact_stats['streak'] = self._get_streak(df_exact, max_items=5)
        
        # ═════════════════════════════════════════════════════════
        # 2. BY_SCORE (PRECISIÓN MEDIA): Patrón + Exhaustion + Score Exacto
        # ═════════════════════════════════════════════════════════
        df_by_score = df_filtered[df_filtered['calculated_score'] == current_score]
        
        by_score_stats = self._empty_single_stats()
        
        if not df_by_score.empty:
            by_score_stats = self._calculate_direction_stats(df_by_score, pattern)
            # Racha específica de este subgrupo (últimos 5)
            by_score_stats['streak'] = self._get_streak(df_by_score, max_items=5)
        
        # ═════════════════════════════════════════════════════════
        # 3. BY_RANGE (MÁXIMA MUESTRA): Patrón + Exhaustion + Score ±tolerance
        # ═════════════════════════════════════════════════════════
        score_min = current_score - score_tolerance
        score_max = current_score + score_tolerance
        
        df_by_range = df_filtered[
            (df_filtered['calculated_score'] >= score_min) &
            (df_filtered['calculated_score'] <= score_max)
        ]
        
        by_range_stats = self._empty_single_stats()
        by_range_stats['score_range'] = (int(score_min), int(score_max))
        
        if not df_by_range.empty:
            by_range_stats = self._calculate_direction_stats(df_by_range, pattern)
            by_range_stats['score_range'] = (int(score_min), int(score_max))
            # Racha específica de este subgrupo (últimos 5)
            by_range_stats['streak'] = self._get_streak(df_by_range, max_items=5)
        
        # ═════════════════════════════════════════════════════════
        # RESULTADO FINAL (3 niveles de precisión)
        # ═════════════════════════════════════════════════════════
        stats = {
            "exact": exact_stats,
            "by_score": by_score_stats,
            "by_range": by_range_stats,
            "exhaustion_type": current_exhaustion_type,
            "lookback_days": lookback_days
        }
        
        logger.debug(
            f"📊 Estadísticas ({source}:{symbol} | Zona: {current_exhaustion_type}) | "
            f"Patrón: {pattern} | "
            f"Score: {current_score} | "
            f"Exact: {exact_stats['total_cases']} casos | "
            f"By Score: {by_score_stats['total_cases']} casos | "
            f"By Range: {by_range_stats['total_cases']} casos"
        )
        
        return stats
    
    def _calculate_direction_stats(self, df: pd.DataFrame, pattern: str) -> Dict[str, any]:
        """
        Calcula estadísticas completas de direcciones para un DataFrame filtrado.
        
        Args:
            df: DataFrame con registros filtrados
            pattern: Tipo de patrón para determinar dirección esperada
            
        Returns:
            Dict con estadísticas completas (sin streak, se agrega luego)
        """
        total_cases = len(df)
        
        # Contar direcciones (solo VERDE y ROJA)
        verde_count = (df['actual_direction'] == 'VERDE').sum()
        roja_count = (df['actual_direction'] == 'ROJA').sum()
        
        # Calcular porcentajes
        verde_pct = verde_count / total_cases if total_cases > 0 else 0.0
        roja_pct = roja_count / total_cases if total_cases > 0 else 0.0
        
        # Determinar dirección esperada del patrón
        # SHOOTING_STAR y HANGING_MAN son bajistas → esperan ROJA
        # HAMMER e INVERTED_HAMMER son alcistas → esperan VERDE
        if pattern in ["SHOOTING_STAR", "HANGING_MAN"]:
            expected_direction = "ROJA"
        elif pattern in ["HAMMER", "INVERTED_HAMMER"]:
            expected_direction = "VERDE"
        else:
            expected_direction = "UNKNOWN"
        
        return {
            "total_cases": int(total_cases),
            "verde_count": int(verde_count),
            "roja_count": int(roja_count),
            "verde_pct": float(verde_pct),
            "roja_pct": float(roja_pct),
            "expected_direction": expected_direction
        }
    
    def _get_streak(self, df: pd.DataFrame, max_items: int = 5) -> List[str]:
        """
        Obtiene la racha de direcciones más recientes de un DataFrame.
        
        Args:
            df: DataFrame filtrado con columna 'actual_direction' y 'timestamp_dt'
            max_items: Número máximo de elementos a retornar
            
        Returns:
            Lista de direcciones (ej: ["VERDE", "ROJA", "VERDE"])
        """
        if df.empty or 'actual_direction' not in df.columns or 'timestamp_dt' not in df.columns:
            return []
        
        # Ordenar por timestamp descendente (más reciente primero)
        recent_df = df.nlargest(max_items, 'timestamp_dt')
        
        # Retornar lista de direcciones
        return recent_df['actual_direction'].tolist()
    
    def _empty_single_stats(self) -> Dict[str, any]:
        """
        Retorna estructura de estadísticas vacía para un nivel.
        """
        return {
            "total_cases": 0,
            "verde_count": 0,
            "roja_count": 0,
            "verde_pct": 0.0,
            "roja_pct": 0.0,
            "expected_direction": "UNKNOWN",
            "streak": []
        }
    
    def _empty_stats_response(self, exhaustion_type: str = "NONE") -> Dict[str, any]:
        """
        Retorna respuesta vacía cuando no hay datos disponibles.
        """
        exact_empty = self._empty_single_stats()
        by_score_empty = self._empty_single_stats()
        by_range_empty = self._empty_single_stats()
        by_range_empty['score_range'] = (0, 0)
        
        return {
            "exact": exact_empty,
            "by_score": by_score_empty,
            "by_range": by_range_empty,
            "exhaustion_type": exhaustion_type,
            "lookback_days": 0
        }
    
    def reload_dataset(self) -> None:
        """
        Recarga el dataset desde disco.
        Útil para actualizar estadísticas después de que se guarden nuevas señales.
        """
        logger.info("🔄 Recargando dataset...")
        self._load_dataset()
    
    def get_stats_summary(self) -> Dict[str, any]:
        """
        Retorna resumen general de estadísticas del dataset.
        
        Returns:
            Dict con métricas generales del dataset cargado
        """
        if self.df is None or self.df.empty:
            return {
                "records_loaded": 0,
                "last_load_time": None,
                "patterns_detected": {},
                "overall_win_rate": 0.0
            }
        
        # Contar patrones (nueva estructura V2)
        patterns = self.df['pattern_candle'].apply(
            lambda x: x.get('pattern') if isinstance(x, dict) else None
        ).value_counts().to_dict()
        
        # Win rate general
        success_rate = self.df['outcome'].apply(
            lambda x: x.get('success', False) if isinstance(x, dict) else False
        ).mean()
        
        return {
            "records_loaded": self.records_loaded,
            "last_load_time": self.last_load_time.isoformat() if self.last_load_time else None,
            "patterns_detected": patterns,
            "overall_win_rate": float(success_rate)
        }
