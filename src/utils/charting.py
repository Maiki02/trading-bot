"""
Charting Utilities - Candlestick Chart Generation
==================================================
Módulo de utilidad para generar gráficos de velas japonesas con mplfinance.
Los gráficos se generan en memoria (BytesIO) y se codifican en Base64.

CRITICAL: Este módulo contiene operaciones bloqueantes (CPU/IO bound).
Debe ejecutarse en un hilo separado con asyncio.to_thread() para no
bloquear el Event Loop principal.

Author: TradingView Pattern Monitor Team
"""

import io
import base64
from typing import Optional

import pandas as pd
import numpy as np
import mplfinance as mpf
import matplotlib
matplotlib.use('Agg')  # Backend sin GUI para generación en memoria


# =============================================================================
# CHART GENERATION
# =============================================================================

def generate_chart_base64(
    dataframe: pd.DataFrame,
    lookback: int,
    title: str = "Price Chart"
) -> str:
    """
    Genera un gráfico de velas japonesas y lo retorna en Base64.
    
    IMPORTANTE: Esta función es bloqueante (CPU bound). Debe ejecutarse en
    un hilo separado con asyncio.to_thread() desde código asíncrono.
    
    Args:
        dataframe: DataFrame con columnas ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'ema_200']
        lookback: Número de velas hacia atrás a mostrar
        title: Título del gráfico
        
    Returns:
        str: Imagen del gráfico codificada en Base64
        
    Raises:
        ValueError: Si el DataFrame no tiene suficientes datos o columnas faltantes
    """
    # Validar datos de entrada
    required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    missing_columns = [col for col in required_columns if col not in dataframe.columns]
    
    if missing_columns:
        raise ValueError(f"DataFrame missing required columns: {missing_columns}")
    
    if len(dataframe) < lookback:
        raise ValueError(
            f"Insufficient data: DataFrame has {len(dataframe)} rows, "
            f"but lookback requires {lookback}"
        )
    
    # Seleccionar las últimas N velas
    df_subset = dataframe.tail(lookback).copy()
    
    # Preparar DataFrame para mplfinance
    # mplfinance requiere un índice de tipo DatetimeIndex
    df_subset['datetime'] = pd.to_datetime(df_subset['timestamp'], unit='s')
    df_subset.set_index('datetime', inplace=True)
    
    # Renombrar columnas para mplfinance (requiere nombres específicos en mayúsculas)
    df_plot = df_subset[['open', 'high', 'low', 'close', 'volume']].copy()
    df_plot.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    
    # Preparar EMA 200 como additional plot si está disponible
    additional_plots = []
    if 'ema_200' in df_subset.columns and not df_subset['ema_200'].isna().all():
        ema_data = df_subset['ema_200'].copy()
        ema_plot = mpf.make_addplot(
            ema_data,
            color='#00D4FF',  # Cyan brillante
            width=1.5,
            panel=0,  # Panel principal (precio)
            secondary_y=False
        )
        additional_plots.append(ema_plot)
    
    # Configurar estilo del gráfico
    style = mpf.make_mpf_style(
        base_mpf_style='nightclouds',  # Estilo oscuro predefinido
        gridstyle='--',
        gridcolor='#2A2A2A',
        facecolor='#0D1117',  # Fondo oscuro GitHub-like
        edgecolor='#1F1F1F',
        figcolor='#0D1117',
        y_on_right=False
    )
    
    # Configurar tamaño y proporciones
    fig_config = {
        'figsize': (14, 8),
        'tight_layout': True
    }
    
    # Generar gráfico en memoria
    buffer = io.BytesIO()
    
    try:
        mpf.plot(
            df_plot,
            type='candle',
            style=style,
            title=dict(title=title, color='white', fontsize=14, weight='bold'),
            ylabel='Price',
            ylabel_lower='Volume',
            volume=True,
            addplot=additional_plots if additional_plots else None,
            savefig=dict(fname=buffer, dpi=100, bbox_inches='tight'),
            **fig_config
        )
        
        # Obtener bytes de la imagen
        buffer.seek(0)
        image_bytes = buffer.read()
        
        # Codificar en Base64
        base64_string = base64.b64encode(image_bytes).decode('utf-8')
        
        return base64_string
    
    finally:
        buffer.close()


def validate_dataframe_for_chart(
    dataframe: pd.DataFrame,
    lookback: int
) -> tuple[bool, Optional[str]]:
    """
    Valida que un DataFrame sea apto para generar un gráfico.
    
    Args:
        dataframe: DataFrame a validar
        lookback: Número de velas requeridas
        
    Returns:
        tuple[bool, Optional[str]]: (Es válido, Mensaje de error si no es válido)
    """
    required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    
    # Verificar columnas
    missing_columns = [col for col in required_columns if col not in dataframe.columns]
    if missing_columns:
        return False, f"Missing columns: {', '.join(missing_columns)}"
    
    # Verificar cantidad de datos
    if len(dataframe) < lookback:
        return False, f"Insufficient data: {len(dataframe)} rows, need {lookback}"
    
    # Verificar que no haya valores NaN en columnas críticas
    critical_columns = ['open', 'high', 'low', 'close']
    for col in critical_columns:
        if dataframe[col].tail(lookback).isna().any():
            return False, f"NaN values found in column: {col}"
    
    return True, None
