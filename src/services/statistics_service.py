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
from datetime import datetime, timedelta
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
                
                # Extraer EMAs
                emas = {
                    'ema_200': emas_data.get('ema_200'),
                    'ema_50': emas_data.get('ema_50'),
                    'ema_30': emas_data.get('ema_30'),
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
        current_alignment: Optional[str] = None,
        current_ema_order: Optional[str] = None,
        lookback_days: int = 30,
        score_tolerance: int = 1
    ) -> Dict[str, any]:
        """
        Calcula probabilidades con 3 niveles de precisión:
        1. EXACTO: Score exacto + EMA order exacto (máxima precisión)
        2. BY_ALIGNMENT: Score similar + mismo alignment (precisión media)
        3. BY_SCORE: Solo score similar (máxima muestra)
        
        Args:
            pattern: Tipo de patrón (ej: "SHOOTING_STAR", "HAMMER")
            current_score: Score de tendencia actual
            current_alignment: Alineación actual (ej: "BULLISH_ALIGNED")
            current_ema_order: Orden explícito actual (ej: "P>20>30>50>200")
            lookback_days: Ventana de tiempo en días (default: 30)
            score_tolerance: Tolerancia para fuzzy matching (default: ±1)
            
        Returns:
            Dict con estructura:
            {
                "exact_order": {          # Score exacto + EMA order exacto
                    "total_cases": int,
                    "win_rate": float,
                    "wins": int,
                    "losses": int
                },
                "by_alignment": {         # Score similar + mismo alignment
                    "total_cases": int,
                    "win_rate": float,
                    "wins": int,
                    "losses": int,
                    "score_range": tuple
                },
                "by_score": {             # Solo score similar
                    "total_cases": int,
                    "win_rate": float,
                    "wins": int,
                    "losses": int,
                    "score_range": tuple
                },
                "streak": list,
                "lookback_days": int
            }
        """
        if self.df is None or self.df.empty:
            return self._empty_stats_response()
        
        # Filtrar por ventana de tiempo
        cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)
        
        # Convertir timestamp a datetime si es string
        try:
            self.df['timestamp_dt'] = pd.to_datetime(self.df['timestamp'])
        except Exception:
            logger.warning("⚠️  No se pudo parsear columna 'timestamp'")
            return self._empty_stats_response()
        
        df_filtered = self.df[self.df['timestamp_dt'] >= cutoff_date].copy()
        
        if df_filtered.empty:
            logger.info(f"📊 No hay datos en ventana de {lookback_days} días")
            return self._empty_stats_response()
        
        # Filtrar por patrón exacto (nueva estructura V2)
        if 'pattern_candle' not in df_filtered.columns:
            logger.warning("⚠️  Columna 'pattern_candle' no existe")
            return self._empty_stats_response()
        
        # Extraer patrón del objeto pattern_candle
        df_filtered['pattern'] = df_filtered['pattern_candle'].apply(
            lambda x: x.get('pattern') if isinstance(x, dict) else None
        )
        
        df_filtered = df_filtered[df_filtered['pattern'] == pattern]
        
        if df_filtered.empty:
            logger.info(f"📊 No hay datos para patrón {pattern}")
            return self._empty_stats_response()
        
        # Extraer columna de success para todos los cálculos
        df_filtered['success'] = df_filtered['outcome'].apply(
            lambda x: x.get('success') if isinstance(x, dict) else False
        )
        
        # Extraer ema_order y alignment de la estructura V2
        df_filtered['ema_order'] = df_filtered['emas'].apply(
            lambda x: x.get('ema_order') if isinstance(x, dict) else None
        )
        df_filtered['alignment'] = df_filtered['emas'].apply(
            lambda x: x.get('alignment') if isinstance(x, dict) else None
        )
        
        # ═════════════════════════════════════════════════════════
        # 1. EXACTO: Score exacto + EMA order exacto
        # ═════════════════════════════════════════════════════════
        exact_order_stats = {
            "total_cases": 0,
            "win_rate": 0.0,
            "wins": 0,
            "losses": 0
        }
        
        if current_ema_order:
            df_exact_order = df_filtered[
                (df_filtered['calculated_score'] == current_score) &
                (df_filtered['ema_order'] == current_ema_order)
            ]
            
            if not df_exact_order.empty:
                exact_total = len(df_exact_order)
                exact_wins = df_exact_order['success'].sum()
                exact_losses = exact_total - exact_wins
                exact_win_rate = exact_wins / exact_total if exact_total > 0 else 0.0
                
                exact_order_stats = {
                    "total_cases": int(exact_total),
                    "win_rate": float(exact_win_rate),
                    "wins": int(exact_wins),
                    "losses": int(exact_losses)
                }
        
        # ═════════════════════════════════════════════════════════
        # 2. BY_ALIGNMENT: Score similar + mismo alignment
        # ═════════════════════════════════════════════════════════
        score_min = current_score - score_tolerance
        score_max = current_score + score_tolerance
        
        by_alignment_stats = {
            "total_cases": 0,
            "win_rate": 0.0,
            "wins": 0,
            "losses": 0,
            "score_range": (int(score_min), int(score_max))
        }
        
        if current_alignment:
            df_by_alignment = df_filtered[
                (df_filtered['calculated_score'] >= score_min) &
                (df_filtered['calculated_score'] <= score_max) &
                (df_filtered['alignment'] == current_alignment)
            ]
            
            if not df_by_alignment.empty:
                alignment_total = len(df_by_alignment)
                alignment_wins = df_by_alignment['success'].sum()
                alignment_losses = alignment_total - alignment_wins
                alignment_win_rate = alignment_wins / alignment_total if alignment_total > 0 else 0.0
                
                by_alignment_stats = {
                    "total_cases": int(alignment_total),
                    "win_rate": float(alignment_win_rate),
                    "wins": int(alignment_wins),
                    "losses": int(alignment_losses),
                    "score_range": (int(score_min), int(score_max))
                }
        
        # ═════════════════════════════════════════════════════════
        # 3. BY_SCORE: Solo score similar (máxima muestra)
        # ═════════════════════════════════════════════════════════
        df_by_score = df_filtered[
            (df_filtered['calculated_score'] >= score_min) &
            (df_filtered['calculated_score'] <= score_max)
        ]
        
        by_score_stats = {
            "total_cases": 0,
            "win_rate": 0.0,
            "wins": 0,
            "losses": 0,
            "score_range": (int(score_min), int(score_max))
        }
        
        if not df_by_score.empty:
            score_total = len(df_by_score)
            score_wins = df_by_score['success'].sum()
            score_losses = score_total - score_wins
            score_win_rate = score_wins / score_total if score_total > 0 else 0.0
            
            by_score_stats = {
                "total_cases": int(score_total),
                "win_rate": float(score_win_rate),
                "wins": int(score_wins),
                "losses": int(score_losses),
                "score_range": (int(score_min), int(score_max))
            }
        
        # ═════════════════════════════════════════════════════════
        # RACHA RECIENTE (basada en by_score para mayor muestra)
        # ═════════════════════════════════════════════════════════
        recent_results = []
        if not df_by_score.empty:
            recent_results = df_by_score.nlargest(5, 'timestamp_dt')['success'].tolist()
        
        # ═════════════════════════════════════════════════════════
        # RESULTADO FINAL
        # ═════════════════════════════════════════════════════════
        stats = {
            "exact_order": exact_order_stats,
            "by_alignment": by_alignment_stats,
            "by_score": by_score_stats,
            "streak": recent_results,
            "lookback_days": lookback_days
        }
        
        logger.debug(
            f"📊 Estadísticas | "
            f"Patrón: {pattern} | "
            f"Score: {current_score} | "
            f"Orden exacto: {exact_order_stats['total_cases']} ({exact_order_stats['win_rate']:.1%}) | "
            f"Por alignment: {by_alignment_stats['total_cases']} ({by_alignment_stats['win_rate']:.1%}) | "
            f"Por score: {by_score_stats['total_cases']} ({by_score_stats['win_rate']:.1%})"
        )
        
        return stats
    
    def _empty_stats_response(self) -> Dict[str, any]:
        """
        Retorna respuesta vacía cuando no hay datos disponibles.
        """
        return {
            "exact": {
                "total_cases": 0,
                "verde_count": 0,
                "roja_count": 0,
                "doji_count": 0,
                "verde_pct": 0.0,
                "roja_pct": 0.0,
                "doji_pct": 0.0,
                "expected_direction": "UNKNOWN",
                "success_rate": 0.0,
                "ev": 0.0
            },
            "similar": {
                "total_cases": 0,
                "verde_count": 0,
                "roja_count": 0,
                "doji_count": 0,
                "verde_pct": 0.0,
                "roja_pct": 0.0,
                "doji_pct": 0.0,
                "expected_direction": "UNKNOWN",
                "success_rate": 0.0,
                "ev": 0.0,
                "score_range": (0, 0)
            },
            "streak": [],
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
