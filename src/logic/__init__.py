"""
Business Logic Layer - TradingView Pattern Monitor
===================================================
Contiene la lógica de negocio central del sistema:
- Análisis técnico y detección de patrones
- Cálculo de indicadores (EMA, RSI, etc.)
- Reglas de disparo de señales

Esta capa es independiente de los servicios de infraestructura.
"""

from .analysis_service import AnalysisService, PatternSignal

__all__ = ["AnalysisService", "PatternSignal"]
