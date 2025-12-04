# RSI Strategy - The Elastic Band (M1)

## Concepto: La Banda Elástica
El RSI (Relative Strength Index) en M1 no debe verse como un indicador de "sobrecompra/sobreventa" tradicional, sino como una **Banda Elástica**.

*   **RSI < 30:** La banda está estirada hacia abajo. La tensión sugiere un rebote inminente (Snap-back).
*   **RSI > 70:** La banda está estirada hacia arriba. La tensión sugiere una corrección inminente.
*   **RSI 50:** La banda está en reposo. No hay tensión, no hay operación.

## Configuración para M1: RSI 7
Para scalping en 1 minuto, el RSI estándar de 14 periodos es demasiado lento (lag). Necesitamos reactividad.

*   **Periodo:** 7 (Siete)
*   **Justificación:** El RSI 7 es más sensible a las micro-tendencias de 5-10 velas, típicas en M1. Detecta los extremos de volatilidad local mucho antes que el RSI 14.

## Cálculo Técnico
El RSI se calcula utilizando el método de **Wilder's Smoothing** (Media Móvil Exponencial), que es el estándar en la industria (TradingView, MT4).

*   **Fórmula:** `RSI = 100 - (100 / (1 + RS))`
*   **RS:** `AvgGain / AvgLoss`
*   **Suavizado:** `alpha = 1/period` (equivalente a `span=2*period-1` en EMA tradicional, pero específico para RSI).
*   **Librería:** Implementado en `src/utils/indicators.py` usando `pandas.ewm(alpha=1/7, adjust=False)`.

## Niveles Clave

### Reversión Estándar (Probabilidad Media)
*   **Nivel Superior:** 70
*   **Nivel Inferior:** 30
*   **Acción:** Buscar patrones de reversión si el precio toca Bollinger Bands.

### Reversión Fuerte (Probabilidad Alta)
*   **Nivel Superior:** 80
*   **Nivel Inferior:** 20
*   **Acción:** Señal de "Extremo". Si coincide con un patrón de vela (Shooting Star/Hammer) y Agotamiento de Tendencia, es una entrada de alta probabilidad.

## Reglas de Operación

1.  **NO operar en zona neutra (40-60).** Es ruido.
2.  **Divergencia:** Si el precio hace un nuevo High pero el RSI 7 hace un High más bajo -> **Señal de Venta Fuerte**.
3.  **Confirmación:** El RSI debe estar en zona extrema EN EL MOMENTO del cierre de la vela gatillo.

## Visualización en Gráficos
El sistema genera automáticamente un gráfico adjunto a cada alerta de Telegram.
*   **Panel Principal:** Velas Japonesas + EMAs.
*   **Panel Inferior:** Oscilador RSI (Línea Morada).
    *   **Líneas de Referencia:** Definidas en `config.py` (Default: 75 y 25) en gris discontinuo.
    *   **Propósito:** Confirmación visual rápida de la tensión del precio ("Banda Elástica").
