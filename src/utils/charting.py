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
    # Sistema de Puntuación Ponderada - Todas las EMAs con colores únicos
    additional_plots = []
    
    # EMA 5 - Ultra Rápida (Peso: 2.0) - Rojo brillante
    if 'ema_5' in df_subset.columns and not df_subset['ema_5'].isna().all():
        ema_5_data = df_subset['ema_5'].copy()
        ema_5_plot = mpf.make_addplot(
            ema_5_data,
            color='#FF0000',  # Rojo brillante
            width=3.0,
            panel=0,
            secondary_y=False,
            label='EMA 5 (2.0pts)'
        )
        additional_plots.append(ema_5_plot)
    
    # EMA 7 - Muy Rápida (Peso: 2.0) - Magenta
    if 'ema_7' in df_subset.columns and not df_subset['ema_7'].isna().all():
        ema_7_data = df_subset['ema_7'].copy()
        ema_7_plot = mpf.make_addplot(
            ema_7_data,
            color='#FF00FF',  # Magenta brillante
            width=2.8,
            panel=0,
            secondary_y=False,
            label='EMA 7 (2.0pts)'
        )
        additional_plots.append(ema_7_plot)
    
    # EMA 10 - Rápida (Peso: 1.5) - Naranja
    if 'ema_10' in df_subset.columns and not df_subset['ema_10'].isna().all():
        ema_10_data = df_subset['ema_10'].copy()
        ema_10_plot = mpf.make_addplot(
            ema_10_data,
            color='#FF8000',  # Naranja
            width=2.5,
            panel=0,
            secondary_y=False,
            label='EMA 10 (1.5pts)'
        )
        additional_plots.append(ema_10_plot)
    
    # EMA 15 - Rápida-Media (Peso: 1.5) - Amarillo
    if 'ema_15' in df_subset.columns and not df_subset['ema_15'].isna().all():
        ema_15_data = df_subset['ema_15'].copy()
        ema_15_plot = mpf.make_addplot(
            ema_15_data,
            color='#FFD700',  # Amarillo dorado
            width=2.2,
            panel=0,
            secondary_y=False,
            label='EMA 15 (1.5pts)'
        )
        additional_plots.append(ema_15_plot)
    
    # EMA 20 - Media (Peso: 1.0) - Verde Lima
    if 'ema_20' in df_subset.columns and not df_subset['ema_20'].isna().all():
        ema_20_data = df_subset['ema_20'].copy()
        ema_20_plot = mpf.make_addplot(
            ema_20_data,
            color='#00FF00',  # Verde lima
            width=2.0,
            panel=0,
            secondary_y=False,
            label='EMA 20 (1.0pt)'
        )
        additional_plots.append(ema_20_plot)
    
    # EMA 30 - Media-Lenta (Peso: 1.0) - Cyan
    if 'ema_30' in df_subset.columns and not df_subset['ema_30'].isna().all():
        ema_30_data = df_subset['ema_30'].copy()
        ema_30_plot = mpf.make_addplot(
            ema_30_data,
            color='#00FFFF',  # Cyan
            width=1.8,
            panel=0,
            secondary_y=False,
            label='EMA 30 (1.0pt)'
        )
        additional_plots.append(ema_30_plot)
    
    # EMA 50 - Lenta (Peso: 1.0) - Azul
    if 'ema_50' in df_subset.columns and not df_subset['ema_50'].isna().all():
        ema_50_data = df_subset['ema_50'].copy()
        ema_50_plot = mpf.make_addplot(
            ema_50_data,
            color='#0080FF',  # Azul brillante
            width=1.5,
            panel=0,
            secondary_y=False,
            label='EMA 50 (1.0pt)'
        )
        additional_plots.append(ema_50_plot)
    
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
        plot_kwargs = {
            'type': 'candle',
            'style': style,
            'title': dict(title=title, color='black', fontsize=14, weight='bold'),
            'ylabel': 'Price',
            'ylabel_lower': 'Volume',
            'volume': True,
            'returnfig': True,
            **fig_config
        }
        
        # Solo agregar addplot si hay plots adicionales (evitar None)
        if additional_plots:
            plot_kwargs['addplot'] = additional_plots
        
        fig, axes = mpf.plot(df_plot, **plot_kwargs)
        
        # Agregar leyenda para las EMAs en el panel principal (axes[0])
        if additional_plots:
            # Crear handles de leyenda manualmente (orden por peso descendente)
            legend_elements = []
            
            if 'ema_5' in df_subset.columns and not df_subset['ema_5'].isna().all():
                legend_elements.append(Line2D([0], [0], color='#FF0000', lw=3.0, label='EMA 5 (2.0pts)'))
            if 'ema_7' in df_subset.columns and not df_subset['ema_7'].isna().all():
                legend_elements.append(Line2D([0], [0], color='#FF00FF', lw=2.8, label='EMA 7 (2.0pts)'))
            if 'ema_10' in df_subset.columns and not df_subset['ema_10'].isna().all():
                legend_elements.append(Line2D([0], [0], color='#FF8000', lw=2.5, label='EMA 10 (1.5pts)'))
            if 'ema_15' in df_subset.columns and not df_subset['ema_15'].isna().all():
                legend_elements.append(Line2D([0], [0], color='#FFD700', lw=2.2, label='EMA 15 (1.5pts)'))
            if 'ema_20' in df_subset.columns and not df_subset['ema_20'].isna().all():
                legend_elements.append(Line2D([0], [0], color='#00FF00', lw=2.0, label='EMA 20 (1.0pt)'))
            if 'ema_30' in df_subset.columns and not df_subset['ema_30'].isna().all():
                legend_elements.append(Line2D([0], [0], color='#00FFFF', lw=1.8, label='EMA 30 (1.0pt)'))
            if 'ema_50' in df_subset.columns and not df_subset['ema_50'].isna().all():
                legend_elements.append(Line2D([0], [0], color='#0080FF', lw=1.5, label='EMA 50 (1.0pt)'))
            
            # Agregar leyenda en la esquina superior izquierda
            axes[0].legend(
                handles=legend_elements,
                loc='upper left',
                frameon=True,
                fancybox=True,
                shadow=True,
                fontsize=8,
                framealpha=0.95,
                ncol=2  # 2 columnas para mejor aprovechamiento del espacio
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
