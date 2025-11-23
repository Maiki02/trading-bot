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


def get_candle_direction(open_price: float, close: float) -> str:
    """
    Determina la dirección de una vela basándose en apertura y cierre.
    
    Args:
        open_price: Precio de apertura
        close: Precio de cierre
        
    Returns:
        str: "VERDE" (alcista), "ROJA" (bajista), o "DOJI" (neutral)
    """
    if close > open_price:
        return "VERDE"
    elif close < open_price:
        return "ROJA"
    else:
        return "DOJI"


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
    Detecta el patrón Shooting Star (Estrella Fugaz).
    
    CARACTERÍSTICAS MATEMÁTICAS:
    - Mecha superior larga (> 60% del rango total)
    - Cuerpo pequeño (< 30% del rango total)
    - Mecha inferior mínima (< 15% del rango total)
    - Mecha superior >= 2x el tamaño del cuerpo
    - DEBE SER VELA ROJA O NEUTRAL (close <= open) ⚠️ NUEVO
    
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
    # Si es vela VERDE (close > open), NO es Shooting Star
    if close > open_price:
        return False, 0.0
    
    # Cálculo de ratios
    upper_wick_ratio = upper_wick / total_range
    lower_wick_ratio = lower_wick / total_range
    
    # Condiciones del patrón
    has_long_upper_wick = upper_wick_ratio >= Config.CANDLE.UPPER_WICK_RATIO_MIN
    has_small_body = body_ratio <= Config.CANDLE.SMALL_BODY_RATIO
    has_small_lower_wick = lower_wick_ratio <= Config.CANDLE.OPPOSITE_WICK_MAX
    wick_to_body = (upper_wick / body_size) >= Config.CANDLE.WICK_TO_BODY_RATIO if body_size > 0 else False
    
    # Validación del patrón
    is_pattern = has_long_upper_wick and has_small_body and has_small_lower_wick and wick_to_body
    
    if not is_pattern:
        return False, 0.0
    
    # Cálculo de confianza (scoring)
    confidence = Config.CANDLE.BASE_CONFIDENCE
    
    # Bonos por condiciones excepcionales
    if upper_wick_ratio >= 0.70:  # Mecha superior muy larga
        confidence += Config.CANDLE.BONUS_CONFIDENCE_PER_CONDITION
    
    if body_ratio <= 0.20:  # Cuerpo muy pequeño
        confidence += Config.CANDLE.BONUS_CONFIDENCE_PER_CONDITION
    
    if lower_wick_ratio <= 0.10:  # Mecha inferior casi inexistente
        confidence += Config.CANDLE.BONUS_CONFIDENCE_PER_CONDITION
    
    # Limitar confianza a 1.0
    confidence = min(confidence, 1.0)
    
    return True, confidence


def is_hanging_man(
    open_price: float,
    high: float,
    low: float,
    close: float
) -> Tuple[bool, float]:
    """
    Detecta el patrón Hanging Man (Hombre Colgado).
    
    CARACTERÍSTICAS MATEMÁTICAS:
    - Mecha inferior larga (> 60% del rango total)
    - Cuerpo pequeño (< 30% del rango total)
    - Mecha superior mínima (< 15% del rango total)
    - Mecha inferior >= 2x el tamaño del cuerpo
    - Cuerpo ubicado en la parte superior de la vela
    - DEBE SER VELA ROJA O NEUTRAL (close <= open) ⚠️ NUEVO
    
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
    # Si es vela VERDE (close > open), NO es Hanging Man
    if close > open_price:
        return False, 0.0
    
    # Cálculo de ratios
    upper_wick_ratio = upper_wick / total_range
    lower_wick_ratio = lower_wick / total_range
    
    # Condiciones del patrón
    has_long_lower_wick = lower_wick_ratio >= Config.CANDLE.LOWER_WICK_RATIO_MIN
    has_small_body = body_ratio <= Config.CANDLE.SMALL_BODY_RATIO
    has_small_upper_wick = upper_wick_ratio <= Config.CANDLE.OPPOSITE_WICK_MAX
    wick_to_body = (lower_wick / body_size) >= Config.CANDLE.WICK_TO_BODY_RATIO if body_size > 0 else False
    
    # Validación del patrón
    is_pattern = has_long_lower_wick and has_small_body and has_small_upper_wick and wick_to_body
    
    if not is_pattern:
        return False, 0.0
    
    # Cálculo de confianza
    confidence = Config.CANDLE.BASE_CONFIDENCE
    
    # Bonos por condiciones excepcionales
    if lower_wick_ratio >= 0.70:
        confidence += Config.CANDLE.BONUS_CONFIDENCE_PER_CONDITION
    
    if body_ratio <= 0.20:
        confidence += Config.CANDLE.BONUS_CONFIDENCE_PER_CONDITION
    
    if upper_wick_ratio <= 0.10:
        confidence += Config.CANDLE.BONUS_CONFIDENCE_PER_CONDITION
    
    confidence = min(confidence, 1.0)
    
    return True, confidence


def is_inverted_hammer(
    open_price: float,
    high: float,
    low: float,
    close: float
) -> Tuple[bool, float]:
    """
    Detecta el patrón Inverted Hammer (Martillo Invertido).
    
    CARACTERÍSTICAS MATEMÁTICAS:
    - Mecha superior larga (> 60% del rango total)
    - Cuerpo pequeño (< 30% del rango total)
    - Mecha inferior mínima (< 15% del rango total)
    - Mecha superior >= 2x el tamaño del cuerpo
    - Cuerpo ubicado en la parte inferior de la vela
    - DEBE SER VELA VERDE (close > open) ⚠️ VALIDACIÓN CRÍTICA
    
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
    # Si es vela ROJA (close <= open), NO es Inverted Hammer (sería Shooting Star)
    if close <= open_price:
        return False, 0.0
    
    # Cálculo de ratios
    upper_wick_ratio = upper_wick / total_range
    lower_wick_ratio = lower_wick / total_range
    
    # Condiciones del patrón
    has_long_upper_wick = upper_wick_ratio >= Config.CANDLE.UPPER_WICK_RATIO_MIN
    has_small_body = body_ratio <= Config.CANDLE.SMALL_BODY_RATIO
    has_small_lower_wick = lower_wick_ratio <= Config.CANDLE.OPPOSITE_WICK_MAX
    wick_to_body = (upper_wick / body_size) >= Config.CANDLE.WICK_TO_BODY_RATIO if body_size > 0 else False
    
    # Validación del patrón
    is_pattern = has_long_upper_wick and has_small_body and has_small_lower_wick and wick_to_body
    
    if not is_pattern:
        return False, 0.0
    
    # Cálculo de confianza
    confidence = Config.CANDLE.BASE_CONFIDENCE
    
    # Bonos
    if upper_wick_ratio >= 0.70:
        confidence += Config.CANDLE.BONUS_CONFIDENCE_PER_CONDITION
    
    if body_ratio <= 0.20:
        confidence += Config.CANDLE.BONUS_CONFIDENCE_PER_CONDITION
    
    if lower_wick_ratio <= 0.10:
        confidence += Config.CANDLE.BONUS_CONFIDENCE_PER_CONDITION
    
    confidence = min(confidence, 1.0)
    
    return True, confidence


def is_hammer(
    open_price: float,
    high: float,
    low: float,
    close: float
) -> Tuple[bool, float]:
    """
    Detecta el patrón Hammer (Martillo).
    
    CARACTERÍSTICAS MATEMÁTICAS:
    - Mecha inferior larga (> 60% del rango total)
    - Cuerpo pequeño (< 30% del rango total)
    - Mecha superior mínima (< 15% del rango total)
    - Mecha inferior >= 2x el tamaño del cuerpo
    - Cuerpo ubicado en la parte superior de la vela
    - DEBE SER VELA VERDE (close > open) ⚠️ VALIDACIÓN CRÍTICA
    
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
    # Si es vela ROJA (close <= open), NO es Hammer (sería Hanging Man)
    if close <= open_price:
        return False, 0.0
    
    # Cálculo de ratios
    upper_wick_ratio = upper_wick / total_range
    lower_wick_ratio = lower_wick / total_range
    
    # Condiciones del patrón
    has_long_lower_wick = lower_wick_ratio >= Config.CANDLE.LOWER_WICK_RATIO_MIN
    has_small_body = body_ratio <= Config.CANDLE.SMALL_BODY_RATIO
    has_small_upper_wick = upper_wick_ratio <= Config.CANDLE.OPPOSITE_WICK_MAX
    wick_to_body = (lower_wick / body_size) >= Config.CANDLE.WICK_TO_BODY_RATIO if body_size > 0 else False
    
    # Validación del patrón
    is_pattern = has_long_lower_wick and has_small_body and has_small_upper_wick and wick_to_body
    
    if not is_pattern:
        return False, 0.0
    
    # Cálculo de confianza
    confidence = Config.CANDLE.BASE_CONFIDENCE
    
    # Bonos
    if lower_wick_ratio >= 0.70:
        confidence += Config.CANDLE.BONUS_CONFIDENCE_PER_CONDITION
    
    if body_ratio <= 0.20:
        confidence += Config.CANDLE.BONUS_CONFIDENCE_PER_CONDITION
    
    if upper_wick_ratio <= 0.10:
        confidence += Config.CANDLE.BONUS_CONFIDENCE_PER_CONDITION
    
    # Nota: NO hay bono adicional por color verde porque ES OBLIGATORIO
    # (ya fue validado al inicio de la función)
    
    confidence = min(confidence, 1.0)
    
    return True, confidence
