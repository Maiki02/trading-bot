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
        
        # Verificar que exista raw_data
        if 'raw_data' not in self.df.columns:
            logger.warning("⚠️  Columna 'raw_data' no existe. No se pueden recalcular scores.")
            self.df['calculated_score'] = np.nan
            return
        
        calculated_scores = []
        
        for idx, row in self.df.iterrows():
            try:
                raw = row['raw_data']
                
                # Extraer datos crudos
                close = raw.get('close')
                emas = {
                    'ema_200': raw.get('ema_200'),
                    'ema_50': raw.get('ema_50'),
                    'ema_30': raw.get('ema_30'),
                    'ema_20': raw.get('ema_20')
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
        lookback_days: int = 30,
        score_tolerance: int = 1
    ) -> Dict[str, any]:
        """
        Calcula probabilidades de velas VERDE/ROJA/DOJI para opciones binarias.
        
        Args:
            pattern: Tipo de patrón (ej: "SHOOTING_STAR", "HAMMER")
            current_score: Score de tendencia actual
            lookback_days: Ventana de tiempo en días (default: 30)
            score_tolerance: Tolerancia para fuzzy matching (default: ±1)
            
        Returns:
            Dict con estructura:
            {
                "exact": {                # Estadísticas con score EXACTO
                    "total_cases": int,
                    "verde_count": int,   # Velas verdes
                    "roja_count": int,    # Velas rojas
                    "doji_count": int,    # Velas doji (empate)
                    "verde_pct": float,   # % velas verdes
                    "roja_pct": float,    # % velas rojas
                    "doji_pct": float,    # % velas doji
                    "expected_direction": str,  # Dirección esperada del patrón
                    "success_rate": float,      # % acierto dirección esperada
                    "ev": float           # Expected Value por apuesta (con payout)
                },
                "similar": {              # Estadísticas con score SIMILAR (±tolerance)
                    "total_cases": int,
                    "verde_count": int,
                    "roja_count": int,
                    "doji_count": int,
                    "verde_pct": float,
                    "roja_pct": float,
                    "doji_pct": float,
                    "expected_direction": str,
                    "success_rate": float,
                    "ev": float,
                    "score_range": tuple
                },
                "streak": list,           # Últimos 5 resultados ["VERDE", "ROJA", "DOJI", ...]
                "lookback_days": int      # Días analizados
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
        
        # Filtrar por patrón exacto
        if 'signal' not in df_filtered.columns:
            logger.warning("⚠️  Columna 'signal' no existe")
            return self._empty_stats_response()
        
        # Extraer patrón del objeto signal
        df_filtered['pattern'] = df_filtered['signal'].apply(
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
        
        # ═════════════════════════════════════════════════════════
        # ESTADÍSTICAS CON SCORE EXACTO
        # ═════════════════════════════════════════════════════════
        df_exact = df_filtered[df_filtered['calculated_score'] == current_score]
        
        exact_stats = {
            "total_cases": 0,
            "win_rate": 0.0,
            "wins": 0,
            "losses": 0
        }
        
        if not df_exact.empty:
            exact_total = len(df_exact)
            exact_wins = df_exact['success'].sum()
            exact_losses = exact_total - exact_wins
            exact_win_rate = exact_wins / exact_total if exact_total > 0 else 0.0
            
            exact_stats = {
                "total_cases": int(exact_total),
                "win_rate": float(exact_win_rate),
                "wins": int(exact_wins),
                "losses": int(exact_losses)
            }
        
        # ═════════════════════════════════════════════════════════
        # ESTADÍSTICAS CON SCORE SIMILAR (Fuzzy Match)
        # ═════════════════════════════════════════════════════════
        score_min = current_score - score_tolerance
        score_max = current_score + score_tolerance
        
        df_similar = df_filtered[
            (df_filtered['calculated_score'] >= score_min) &
            (df_filtered['calculated_score'] <= score_max)
        ]
        
        similar_stats = {
            "total_cases": 0,
            "win_rate": 0.0,
            "wins": 0,
            "losses": 0,
            "score_range": (int(score_min), int(score_max))
        }
        
        if not df_similar.empty:
            similar_total = len(df_similar)
            similar_wins = df_similar['success'].sum()
            similar_losses = similar_total - similar_wins
            similar_win_rate = similar_wins / similar_total if similar_total > 0 else 0.0
            
            similar_stats = {
                "total_cases": int(similar_total),
                "win_rate": float(similar_win_rate),
                "wins": int(similar_wins),
                "losses": int(similar_losses),
                "score_range": (int(score_min), int(score_max))
            }
        
        # ═════════════════════════════════════════════════════════
        # RACHA RECIENTE (basada en score similar para mayor muestra)
        # ═════════════════════════════════════════════════════════
        recent_results = []
        if not df_similar.empty:
            recent_results = df_similar.nlargest(5, 'timestamp_dt')['success'].tolist()
        
        # ═════════════════════════════════════════════════════════
        # RESULTADO FINAL
        # ═════════════════════════════════════════════════════════
        stats = {
            "exact": exact_stats,
            "similar": similar_stats,
            "streak": recent_results,
            "lookback_days": lookback_days
        }
        
        logger.debug(
            f"📊 Estadísticas | "
            f"Patrón: {pattern} | "
            f"Score: {current_score} | "
            f"Exactos: {exact_stats['total_cases']} (Acierto: {exact_stats['success_rate']:.1%}) | "
            f"Similares: {similar_stats['total_cases']} (Acierto: {similar_stats['success_rate']:.1%})"
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
        
        # Contar patrones
        patterns = self.df['signal'].apply(
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
