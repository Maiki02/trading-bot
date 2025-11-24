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
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


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
    
    # Preparar EMAs como additional plots
    # Estrategia Mean Reversion: Priorizar EMAs cortas (7, 20, 50)
    additional_plots = []
    
    # EMA 7 - CRÍTICA para Mean Reversion (Magenta/Fucsia)
    if 'ema_7' in df_subset.columns and not df_subset['ema_7'].isna().all():
        ema_7_data = df_subset['ema_7'].copy()
        ema_7_plot = mpf.make_addplot(
            ema_7_data,
            color='#FF00FF',  # Magenta brillante
            width=2.5,
            panel=0,
            secondary_y=False,
            label='EMA 7'
        )
        additional_plots.append(ema_7_plot)
    
    # EMA 20 - Confirmación Momentum (Naranja)
    if 'ema_20' in df_subset.columns and not df_subset['ema_20'].isna().all():
        ema_20_data = df_subset['ema_20'].copy()
        ema_20_plot = mpf.make_addplot(
            ema_20_data,
            color='#FF8000',  # Naranja
            width=2.0,
            panel=0,
            secondary_y=False,
            label='EMA 20'
        )
        additional_plots.append(ema_20_plot)
    
    # EMA 50 - Validación Tendencia (Verde)
    if 'ema_50' in df_subset.columns and not df_subset['ema_50'].isna().all():
        ema_50_data = df_subset['ema_50'].copy()
        ema_50_plot = mpf.make_addplot(
            ema_50_data,
            color='#00FF80',  # Verde brillante
            width=1.5,
            panel=0,
            secondary_y=False,
            label='EMA 50'
        )
        additional_plots.append(ema_50_plot)
    
    # EMA 200 - Solo Referencia Visual (Cyan, opcional)
    # Nota: Ya NO se usa en lógica de Mean Reversion, solo visualización
    if 'ema_200' in df_subset.columns and not df_subset['ema_200'].isna().all():
        ema_200_data = df_subset['ema_200'].copy()
        ema_200_plot = mpf.make_addplot(
            ema_200_data,
            color='#00D4FF',  # Cyan brillante (más tenue)
            width=1.0,
            panel=0,
            secondary_y=False,
            label='EMA 200',
            alpha=0.6  # Semi-transparente para no distraer
        )
        additional_plots.append(ema_200_plot)
    
    # Configurar estilo del gráfico
    # Colores: Velas alcistas (verdes), velas bajistas (rojas)
    market_colors = mpf.make_marketcolors(
        up='#00FF00',      # Verde para velas alcistas (cierre > apertura)
        down='#FF0000',    # Rojo para velas bajistas (cierre < apertura)
        edge='inherit',    # Borde del mismo color que el cuerpo
        wick='inherit',    # Mechas del mismo color que el cuerpo
        volume='in',       # Volumen: verde si sube, rojo si baja
        alpha=0.9
    )
    
    style = mpf.make_mpf_style(
        base_mpf_style='yahoo',        # Estilo claro con fondo blanco
        marketcolors=market_colors,     # ← Aplicar colores personalizados
        gridstyle='--',
        gridcolor='#CCCCCC',           # Grilla gris clara
        facecolor='#FFFFFF',           # Fondo blanco del área de gráfico
        edgecolor='#E0E0E0',           # Borde gris muy claro
        figcolor='#FFFFFF',            # Fondo blanco de la figura completa
        rc={
            'axes.labelcolor': '#000000',    # Etiquetas negras
            'xtick.color': '#000000',        # Números eje X negros
            'ytick.color': '#000000',        # Números eje Y negros
            'axes.edgecolor': '#000000',     # Borde del gráfico negro
            'text.color': '#000000'          # Texto general negro
        },
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
        # Generar gráfico con returnfig=True para acceder a la figura
        fig, axes = mpf.plot(
            df_plot,
            type='candle',
            style=style,
            title=dict(title=title, color='black', fontsize=14, weight='bold'),
            ylabel='Price',
            ylabel_lower='Volume',
            volume=True,
            addplot=additional_plots if additional_plots else None,
            returnfig=True,
            **fig_config
        )
        
        # Agregar leyenda para las EMAs en el panel principal (axes[0])
        if additional_plots:
            # Crear handles de leyenda manualmente (orden de prioridad)
            legend_elements = []
            
            if 'ema_7' in df_subset.columns and not df_subset['ema_7'].isna().all():
                legend_elements.append(Line2D([0], [0], color='#FF00FF', lw=2.5, label='EMA 7 (Agotamiento)'))
            if 'ema_20' in df_subset.columns and not df_subset['ema_20'].isna().all():
                legend_elements.append(Line2D([0], [0], color='#FF8000', lw=2.0, label='EMA 20 (Momentum)'))
            if 'ema_50' in df_subset.columns and not df_subset['ema_50'].isna().all():
                legend_elements.append(Line2D([0], [0], color='#00FF80', lw=1.5, label='EMA 50 (Tendencia)'))
            if 'ema_200' in df_subset.columns and not df_subset['ema_200'].isna().all():
                legend_elements.append(Line2D([0], [0], color='#00D4FF', lw=1.0, label='EMA 200 (Referencia)', alpha=0.6))
            
            # Agregar leyenda en la esquina superior izquierda
            axes[0].legend(
                handles=legend_elements,
                loc='upper left',
                frameon=True,
                fancybox=True,
                shadow=True,
                fontsize=9,
                framealpha=0.9
            )
        
        # Guardar figura en buffer
        fig.savefig(buffer, dpi=100, bbox_inches='tight')
        
        # Cerrar figura para liberar memoria
        plt.close(fig)
        
        # Obtener bytes de la imagen
        buffer.seek(0)
        image_bytes = buffer.read()
        
        # Codificar en Base64
        base64_string = base64.b64encode(image_bytes).decode('utf-8')
        
        # Validar que el Base64 sea válido (sin espacios, saltos de línea, etc.)
        # Nota: No debe tener prefijo data:image/png;base64,
        base64_length = len(base64_string)
        has_newlines = '\n' in base64_string or '\r' in base64_string
        has_spaces = ' ' in base64_string
        
        # Log de depuración
        print(f"🖼️ CHART BASE64 INFO:")
        print(f"  • Image size: {len(image_bytes)} bytes")
        print(f"  • Base64 length: {base64_length} chars")
        print(f"  • Has newlines: {has_newlines}")
        print(f"  • Has spaces: {has_spaces}")
        print(f"  • First 50 chars: {base64_string[:50]}")
        print(f"  • Last 50 chars: {base64_string[-50:]}")
        
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
