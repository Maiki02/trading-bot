"""
Candle Pattern Detection - Mathematical Logic
==============================================
Módulo que implementa la detección matemática de patrones de velas japonesas.

Patrones implementados:
1. Shooting Star (Estrella Fugaz) - Patrón de reversión bajista
2. Hanging Man (Hombre Colgado) - Patrón de reversión bajista
3. Inverted Hammer (Martillo Invertido) - Patrón de reversión alcista
4. Hammer (Martillo) - Patrón de reversión alcista

Cada función retorna una tupla (is_pattern: bool, confidence: float)
donde confidence es un score de 0.0 a 1.0.

Author: TradingView Pattern Monitor Team
"""

from typing import Tuple
from config import Config


def _calculate_candle_metrics(
    open_price: float,
    high: float,
    low: float,
    close: float
) -> Tuple[float, float, float, float, float]:
    """
    Calcula las métricas básicas de una vela.
    
    Args:
        open_price: Precio de apertura
        high: Precio máximo
        low: Precio mínimo
        close: Precio de cierre
        
    Returns:
        Tuple con (total_range, body_size, upper_wick, lower_wick, body_ratio)
    """
    total_range = high - low
    
    # Evitar división por cero
    if total_range == 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    
    # Cálculo del cuerpo
    body_size = abs(close - open_price)
    body_ratio = body_size / total_range
    
    # Cálculo de mechas
    if close > open_price:  # Vela alcista (verde)
        upper_wick = high - close
        lower_wick = open_price - low
    else:  # Vela bajista (roja) o doji
        upper_wick = high - open_price
        lower_wick = close - low
    
    return total_range, body_size, upper_wick, lower_wick, body_ratio


def is_shooting_star(
    open_price: float,
    high: float,
    low: float,
    close: float
) -> Tuple[bool, float]:
    """
    Detecta el patrón Shooting Star (Estrella Fugaz) con Sistema de Confianza por Niveles.
    
    SISTEMA TIERED (Opciones Binarias 1m):
    - SNIPER (100%): Rechazo >= 70%, Cuerpo <= 15%, Mecha contraria < 1%
    - EXCELENTE (90%): Rechazo >= 60%, Cuerpo <= 20%, Mecha contraria < 5%
    - ESTÁNDAR (80%): Rechazo >= 50%, Cuerpo <= 30%, Mecha contraria < 10%
    
    VALIDACIONES CRÍTICAS:
    - DEBE SER VELA ROJA O NEUTRAL (close <= open)
    - Mecha contraria es el filtro MÁS IMPORTANTE (causa #1 de falsos positivos)
    
    INTERPRETACIÓN:
    Indica rechazo de precios altos. Válido en tendencia alcista
    para señalar posible reversión bajista.
    
    Args:
        open_price: Precio de apertura
        high: Precio máximo
        low: Precio mínimo
        close: Precio de cierre
        
    Returns:
        Tuple[bool, float]: (es_shooting_star, confianza)
    """
    total_range, body_size, upper_wick, lower_wick, body_ratio = _calculate_candle_metrics(
        open_price, high, low, close
    )
    
    if total_range == 0:
        return False, 0.0
    
    # ⚠️ VALIDACIÓN CRÍTICA: Shooting Star debe ser ROJO o neutral
    if close > open_price:
        return False, 0.0
    
    # Cálculo de ratios
    upper_wick_ratio = upper_wick / total_range
    lower_wick_ratio = lower_wick / total_range
    
    # Safety check: Mecha debe ser >= 2x el cuerpo
    if body_size > 0:
        wick_to_body = upper_wick / body_size
        if wick_to_body < Config.CANDLE.WICK_TO_BODY_RATIO:
            return False, 0.0
    
    # =========================================================================
    # NIVEL SNIPER (100%) - Perfect Entry
    # =========================================================================
    if (upper_wick_ratio >= Config.CANDLE.SNIPER_REJECTION_WICK and
        body_ratio <= Config.CANDLE.SNIPER_BODY_MAX and
        lower_wick_ratio <= Config.CANDLE.SNIPER_OPPOSITE_WICK_MAX):
        return True, 1.0
    
    # =========================================================================
    # NIVEL EXCELENTE (90%) - High Probability
    # =========================================================================
    elif (upper_wick_ratio >= Config.CANDLE.EXCELLENT_REJECTION_WICK and
          body_ratio <= Config.CANDLE.EXCELLENT_BODY_MAX and
          lower_wick_ratio <= Config.CANDLE.EXCELLENT_OPPOSITE_WICK_MAX):
        return True, 0.9
    
    # =========================================================================
    # NIVEL ESTÁNDAR (80%) - Minimum Acceptable
    # =========================================================================
    elif (upper_wick_ratio >= Config.CANDLE.STANDARD_REJECTION_WICK and
          body_ratio <= Config.CANDLE.STANDARD_BODY_MAX and
          lower_wick_ratio <= Config.CANDLE.STANDARD_OPPOSITE_WICK_MAX):
        return True, 0.8
    
    # =========================================================================
    # NO CUMPLE NINGÚN NIVEL - Descartado
    # =========================================================================
    else:
        return False, 0.0


def is_hanging_man(
    open_price: float,
    high: float,
    low: float,
    close: float
) -> Tuple[bool, float]:
    """
    Detecta el patrón Hanging Man (Hombre Colgado) con Sistema de Confianza por Niveles.
    
    SISTEMA TIERED (Opciones Binarias 1m):
    - SNIPER (100%): Rechazo >= 70%, Cuerpo <= 15%, Mecha contraria < 1%
    - EXCELENTE (90%): Rechazo >= 60%, Cuerpo <= 20%, Mecha contraria < 5%
    - ESTÁNDAR (80%): Rechazo >= 50%, Cuerpo <= 30%, Mecha contraria < 10%
    
    VALIDACIONES CRÍTICAS:
    - DEBE SER VELA ROJA O NEUTRAL (close <= open)
    - Mecha contraria es el filtro MÁS IMPORTANTE
    - Cuerpo debe estar en la parte superior de la vela
    
    INTERPRETACIÓN:
    Indica rechazo de precios bajos pero debilidad. Válido en tendencia
    alcista para señalar posible reversión bajista.
    
    Args:
        open_price: Precio de apertura
        high: Precio máximo
        low: Precio mínimo
        close: Precio de cierre
        
    Returns:
        Tuple[bool, float]: (es_hanging_man, confianza)
    """
    total_range, body_size, upper_wick, lower_wick, body_ratio = _calculate_candle_metrics(
        open_price, high, low, close
    )
    
    if total_range == 0:
        return False, 0.0
    
    # ⚠️ VALIDACIÓN CRÍTICA: Hanging Man debe ser ROJO o neutral
    if close > open_price:
        return False, 0.0
    
    # Cálculo de ratios
    upper_wick_ratio = upper_wick / total_range
    lower_wick_ratio = lower_wick / total_range
    
    # Safety check: Mecha debe ser >= 2x el cuerpo
    if body_size > 0:
        wick_to_body = lower_wick / body_size
        if wick_to_body < Config.CANDLE.WICK_TO_BODY_RATIO:
            return False, 0.0
    
    # =========================================================================
    # NIVEL SNIPER (100%) - Perfect Entry
    # =========================================================================
    if (lower_wick_ratio >= Config.CANDLE.SNIPER_REJECTION_WICK and
        body_ratio <= Config.CANDLE.SNIPER_BODY_MAX and
        upper_wick_ratio <= Config.CANDLE.SNIPER_OPPOSITE_WICK_MAX):
        return True, 1.0
    
    # =========================================================================
    # NIVEL EXCELENTE (90%) - High Probability
    # =========================================================================
    elif (lower_wick_ratio >= Config.CANDLE.EXCELLENT_REJECTION_WICK and
          body_ratio <= Config.CANDLE.EXCELLENT_BODY_MAX and
          upper_wick_ratio <= Config.CANDLE.EXCELLENT_OPPOSITE_WICK_MAX):
        return True, 0.9
    
    # =========================================================================
    # NIVEL ESTÁNDAR (80%) - Minimum Acceptable
    # =========================================================================
    elif (lower_wick_ratio >= Config.CANDLE.STANDARD_REJECTION_WICK and
          body_ratio <= Config.CANDLE.STANDARD_BODY_MAX and
          upper_wick_ratio <= Config.CANDLE.STANDARD_OPPOSITE_WICK_MAX):
        return True, 0.8
    
    # =========================================================================
    # NO CUMPLE NINGÚN NIVEL - Descartado
    # =========================================================================
    else:
        return False, 0.0


def is_inverted_hammer(
    open_price: float,
    high: float,
    low: float,
    close: float
) -> Tuple[bool, float]:
    """
    Detecta el patrón Inverted Hammer (Martillo Invertido) con Sistema de Confianza por Niveles.
    
    SISTEMA TIERED (Opciones Binarias 1m):
    - SNIPER (100%): Rechazo >= 70%, Cuerpo <= 15%, Mecha contraria < 1%
    - EXCELENTE (90%): Rechazo >= 60%, Cuerpo <= 20%, Mecha contraria < 5%
    - ESTÁNDAR (80%): Rechazo >= 50%, Cuerpo <= 30%, Mecha contraria < 10%
    
    VALIDACIONES CRÍTICAS:
    - DEBE SER VELA VERDE (close > open)
    - Mecha contraria es el filtro MÁS IMPORTANTE
    - Cuerpo ubicado en la parte inferior de la vela
    
    INTERPRETACIÓN:
    Indica que los compradores intentaron empujar el precio pero fueron rechazados.
    Sin embargo, la presencia de compradores (vela verde) sugiere posible reversión.
    Válido en tendencia bajista como señal de posible reversión alcista.
    
    Args:
        open_price: Precio de apertura
        high: Precio máximo
        low: Precio mínimo
        close: Precio de cierre
        
    Returns:
        Tuple[bool, float]: (es_inverted_hammer, confianza)
    """
    total_range, body_size, upper_wick, lower_wick, body_ratio = _calculate_candle_metrics(
        open_price, high, low, close
    )
    
    if total_range == 0:
        return False, 0.0
    
    # ⚠️ VALIDACIÓN CRÍTICA: Inverted Hammer debe ser VERDE
    if close <= open_price:
        return False, 0.0
    
    # Cálculo de ratios
    upper_wick_ratio = upper_wick / total_range
    lower_wick_ratio = lower_wick / total_range
    
    # Safety check: Mecha debe ser >= 2x el cuerpo
    if body_size > 0:
        wick_to_body = upper_wick / body_size
        if wick_to_body < Config.CANDLE.WICK_TO_BODY_RATIO:
            return False, 0.0
    
    # =========================================================================
    # NIVEL SNIPER (100%) - Perfect Entry
    # =========================================================================
    if (upper_wick_ratio >= Config.CANDLE.SNIPER_REJECTION_WICK and
        body_ratio <= Config.CANDLE.SNIPER_BODY_MAX and
        lower_wick_ratio <= Config.CANDLE.SNIPER_OPPOSITE_WICK_MAX):
        return True, 1.0
    
    # =========================================================================
    # NIVEL EXCELENTE (90%) - High Probability
    # =========================================================================
    elif (upper_wick_ratio >= Config.CANDLE.EXCELLENT_REJECTION_WICK and
          body_ratio <= Config.CANDLE.EXCELLENT_BODY_MAX and
          lower_wick_ratio <= Config.CANDLE.EXCELLENT_OPPOSITE_WICK_MAX):
        return True, 0.9
    
    # =========================================================================
    # NIVEL ESTÁNDAR (80%) - Minimum Acceptable
    # =========================================================================
    elif (upper_wick_ratio >= Config.CANDLE.STANDARD_REJECTION_WICK and
          body_ratio <= Config.CANDLE.STANDARD_BODY_MAX and
          lower_wick_ratio <= Config.CANDLE.STANDARD_OPPOSITE_WICK_MAX):
        return True, 0.8
    
    # =========================================================================
    # NO CUMPLE NINGÚN NIVEL - Descartado
    # =========================================================================
    else:
        return False, 0.0


def is_hammer(
    open_price: float,
    high: float,
    low: float,
    close: float
) -> Tuple[bool, float]:
    """
    Detecta el patrón Hammer (Martillo) con Sistema de Confianza por Niveles.
    
    SISTEMA TIERED (Opciones Binarias 1m):
    - SNIPER (100%): Rechazo >= 70%, Cuerpo <= 15%, Mecha contraria < 1%
    - EXCELENTE (90%): Rechazo >= 60%, Cuerpo <= 20%, Mecha contraria < 5%
    - ESTÁNDAR (80%): Rechazo >= 50%, Cuerpo <= 30%, Mecha contraria < 10%
    
    VALIDACIONES CRÍTICAS:
    - DEBE SER VELA VERDE (close > open)
    - Mecha contraria es el filtro MÁS IMPORTANTE
    - Cuerpo ubicado en la parte superior de la vela
    
    NOTA: A diferencia del Hanging Man, el Hammer DEBE ser verde (cierre > apertura).
    La diferencia entre Hammer y Hanging Man es:
    - Hammer: Verde + Tendencia Bajista = Reversión Alcista
    - Hanging Man: Rojo + Tendencia Alcista = Reversión Bajista
    
    INTERPRETACIÓN:
    Indica rechazo fuerte de precios bajos por parte de compradores.
    Válido en tendencia bajista como señal de posible reversión alcista.
    
    Args:
        open_price: Precio de apertura
        high: Precio máximo
        low: Precio mínimo
        close: Precio de cierre
        
    Returns:
        Tuple[bool, float]: (es_hammer, confianza)
    """
    total_range, body_size, upper_wick, lower_wick, body_ratio = _calculate_candle_metrics(
        open_price, high, low, close
    )
    
    if total_range == 0:
        return False, 0.0
    
    # ⚠️ VALIDACIÓN CRÍTICA: Hammer debe ser VERDE
    if close <= open_price:
        return False, 0.0
    
    # Cálculo de ratios
    upper_wick_ratio = upper_wick / total_range
    lower_wick_ratio = lower_wick / total_range
    
    # Safety check: Mecha debe ser >= 2x el cuerpo
    if body_size > 0:
        wick_to_body = lower_wick / body_size
        if wick_to_body < Config.CANDLE.WICK_TO_BODY_RATIO:
            return False, 0.0
    
    # =========================================================================
    # NIVEL SNIPER (100%) - Perfect Entry
    # =========================================================================
    if (lower_wick_ratio >= Config.CANDLE.SNIPER_REJECTION_WICK and
        body_ratio <= Config.CANDLE.SNIPER_BODY_MAX and
        upper_wick_ratio <= Config.CANDLE.SNIPER_OPPOSITE_WICK_MAX):
        return True, 1.0
    
    # =========================================================================
    # NIVEL EXCELENTE (90%) - High Probability
    # =========================================================================
    elif (lower_wick_ratio >= Config.CANDLE.EXCELLENT_REJECTION_WICK and
          body_ratio <= Config.CANDLE.EXCELLENT_BODY_MAX and
          upper_wick_ratio <= Config.CANDLE.EXCELLENT_OPPOSITE_WICK_MAX):
        return True, 0.9
    
    # =========================================================================
    # NIVEL ESTÁNDAR (80%) - Minimum Acceptable
    # =========================================================================
    elif (lower_wick_ratio >= Config.CANDLE.STANDARD_REJECTION_WICK and
          body_ratio <= Config.CANDLE.STANDARD_BODY_MAX and
          upper_wick_ratio <= Config.CANDLE.STANDARD_OPPOSITE_WICK_MAX):
        return True, 0.8
    
    # =========================================================================
    # NO CUMPLE NINGÚN NIVEL - Descartado
    # =========================================================================
    else:
        return False, 0.0
