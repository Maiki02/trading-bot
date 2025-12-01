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
