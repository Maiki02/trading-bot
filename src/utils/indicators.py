"""
Technical Analysis Indicators
=============================
Funciones de utilidad para calcular indicadores técnicos usando pandas.
"""

import pandas as pd

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


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Calcula el Relative Strength Index (RSI).
    
    Args:
        series: Serie de precios (típicamente Close)
        period: Periodo del RSI (default: 14)
        
    Returns:
        pd.Series: Serie con valores de RSI (0-100)
    """
    # Calcular cambios de precio
    delta = series.diff()
    
    # Separar ganancias y pérdidas
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    
    # Calcular medias móviles exponenciales (Wilder's Smoothing)
    # alpha = 1/period
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    # Calcular RS
    rs = avg_gain / avg_loss
    
    # Calcular RSI
    rsi = 100 - (100 / (1 + rs))
    
    # Manejar división por cero (si avg_loss es 0, RSI es 100)
    rsi = rsi.fillna(100)
    
    # Si avg_gain es 0, RSI es 0 (ya manejado por la fórmula usualmente, pero por seguridad)
    # Si ambos son 0, RSI es 50 (mercado plano)
    
    return rsi
