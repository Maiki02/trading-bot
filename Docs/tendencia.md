# Problema: Determinación de Tendencia con Múltiples EMAs

## Contexto del Proyecto
Tengo un bot de trading que detecta patrones de velas japonesas en tiempo real (EUR/USD, temporalidad 1 minuto). Actualmente está en MVP funcional y detecta 4 patrones: Shooting Star, Hanging Man, Inverted Hammer y Hammer.

## Estado Actual: Cálculo de EMAs
El sistema **ya está calculando múltiples EMAs** en `src/logic/analysis_service.py`:
- **EMA 20** - Corto plazo
- **EMA 30** - Corto plazo
- **EMA 50** - Mediano plazo
- **EMA 100** - Mediano plazo
- **EMA 200** - Largo plazo (referencia principal actual)

Estas EMAs se calculan correctamente, están disponibles en el DataFrame de pandas y se envían en los mensajes de Telegram.

## Problema: ¿Cómo Determinar la Tendencia?

### Implementación Actual (Simplista)
La función `_determine_trend()` solo usa **EMA 200**:

```python
def _determine_trend(self, close: float, ema_200: float) -> str:
    threshold = 0.0001
    
    if close < ema_200 - threshold:
        return "BEARISH"
    elif close > ema_200 + threshold:
        return "BULLISH"
    else:
        return "NEUTRAL"
```

**Retorna:** Un string simple: "BEARISH", "BULLISH" o "NEUTRAL"

**Problema:** Esta lógica es **demasiado simplista** para un mercado de 1 minuto. No aprovecha las 5 EMAs disponibles.

---

## Preguntas Sin Resolver

### 1. ¿Cómo construir una tendencia más robusta?

**Opciones posibles:**

**A) Sistema de Votación (Ponderado o Simple)**
```python
# Cada EMA "vota" si el precio está arriba o abajo
votes_bullish = 0
votes_bearish = 0

if close > ema_20: votes_bullish += 1
if close > ema_30: votes_bullish += 1
if close > ema_50: votes_bullish += 1
if close > ema_100: votes_bullish += 1
if close > ema_200: votes_bullish += 1

# ¿Mayoría simple? ¿Ponderar las EMAs largas con más peso?
```

**B) Análisis de Alineación (Golden Cross / Death Cross)**
```python
# Verificar si las EMAs están ordenadas correctamente
# Alcista: EMA20 > EMA30 > EMA50 > EMA100 > EMA200
# Bajista: EMA20 < EMA30 < EMA50 < EMA100 < EMA200
```

**C) Análisis de Gradiente (Momentum)**
```python
# Verificar si las EMAs están subiendo o bajando
# No solo la posición, sino la dirección del movimiento
```

**D) Mantener EMA 200 como "juez final"**
```python
# Usar las EMAs cortas para detectar fuerza, pero EMA 200 como filtro macro
# Si precio < EMA200 = macro bearish, pero EMA20 > EMA50 = micro bullish
```

### 2. ¿Qué devolver en `_determine_trend()`?

**Opción A: String simple (actual)**
```python
return "BEARISH"  # o "BULLISH" o "NEUTRAL"
```
- ✅ Fácil de entender
- ❌ Pierde información de fuerza/confianza

**Opción B: String con niveles**
```python
return "STRONG_BULLISH"  # o "WEAK_BEARISH", "NEUTRAL", etc.
```
- ✅ Más detallado
- ❌ Sigue siendo discreto

**Opción C: Diccionario con detalles**
```python
return {
    "trend": "BULLISH",
    "strength": 0.85,  # 0.0 - 1.0
    "ema_alignment": True,  # ¿EMAs alineadas correctamente?
    "price_vs_ema200": "ABOVE",
    "short_term": "BULLISH",  # EMA 20-50
    "long_term": "NEUTRAL"    # EMA 100-200
}
```
- ✅ Máxima información
- ❌ Requiere refactor en varios lugares

**Opción D: Comentario por cada EMA en el mensaje**
```python
# En el mensaje de Telegram:
"📉 EMAs:
  • EMA 20: 1.08600 (ABOVE - BULLISH)
  • EMA 30: 1.08550 (ABOVE - BULLISH)
  • EMA 50: 1.08500 (ABOVE - BULLISH)
  • EMA 100: 1.08450 (ABOVE - BULLISH)
  • EMA 200: 1.08400 (ABOVE - BULLISH)
  
🎯 Tendencia Global: STRONG BULLISH (5/5 EMAs alineadas)"
```

### 3. ¿Debo graficar las EMAs?

**Estado actual del gráfico:**
- Se genera con `mplfinance`
- Muestra velas japonesas + volumen
- Actualmente **NO muestra las EMAs visualmente**

**Pregunta:** ¿Agregar las 5 EMAs al gráfico?

**Pros:**
- ✅ Visualización inmediata de la tendencia
- ✅ El trader puede interpretar cruzamientos
- ✅ Más profesional

**Contras:**
- ❌ Gráfico más "cargado" visualmente
- ❌ Puede aumentar tamaño de imagen (ya tenemos problemas con payloads >80KB)
- ❌ En 1 minuto con 30 velas, puede verse confuso con 5 líneas

**Alternativas:**
- Graficar solo EMA 20 y EMA 200 (corto vs largo)
- Graficar solo EMAs relevantes según la tendencia detectada
- Usar colores diferenciados (EMA corta en amarillo, larga en cyan)

### 4. ¿Cómo adaptar el filtro de tendencia?

**Contexto:** Actualmente tengo `USE_TREND_FILTER=false` (MVP envía todas las señales)

**Cuando reactive el filtro (`USE_TREND_FILTER=true`):**
- ¿Usar solo EMA 200 (actual)?
- ¿Requerir alineación de múltiples EMAs?
- ¿Permitir señales si al menos 3 de 5 EMAs coinciden?

**Ejemplo dilema:**
```
Precio: 1.08650
EMA 20: 1.08700 ← Precio DEBAJO (bearish)
EMA 30: 1.08650 ← Precio EN (neutral)
EMA 50: 1.08600 ← Precio ARRIBA (bullish)
EMA 100: 1.08550 ← Precio ARRIBA (bullish)
EMA 200: 1.08500 ← Precio ARRIBA (bullish)

¿Esto es BULLISH (3/5 above) o BEARISH (short term weakness)?
```

---

## Restricciones Técnicas

### 1. Formato de salida actual
La función `_determine_trend()` retorna un string que se usa en:
- **Mensaje de Telegram** (campo `trend`)
- **Logs internos**
- **Lógica de filtrado** (cuando `USE_TREND_FILTER=true`)

Si cambio el tipo de retorno, necesito modificar varios lugares del código.

### 2. Payload de Telegram
- Actualmente con `CHART_LOOKBACK=100` generamos payloads de ~80KB (problemático)
- Agregar 5 líneas de EMAs al gráfico podría aumentar el tamaño
- Recomendación actual: `CHART_LOOKBACK=30` para mantener <60KB

### 3. Temporalidad: 1 minuto
- Las EMAs en 1 minuto son **muy sensibles**
- Cruces pueden ocurrir constantemente (mucho ruido)
- EMA 200 en 1m = últimas 3.33 horas
- EMA 20 en 1m = últimos 20 minutos

---

## Lo Que Necesito Decidir

**Pregunta principal:** ¿Cómo debo usar las 5 EMAs para determinar una tendencia robusta en temporalidad de 1 minuto?

**Sub-preguntas:**
1. ¿Algoritmo de votación, alineación, gradiente o híbrido?
2. ¿Qué devuelve `_determine_trend()`? (string simple, string niveles, dict, objeto)
3. ¿Graficar las EMAs? ¿Todas o solo algunas?
4. ¿Cómo comentar/explicar la tendencia en el mensaje de Telegram?
5. ¿Cómo integrar esto con el filtro de tendencia cuando lo reactive?

**Objetivo final:** 
- Reducir falsos positivos
- Dar más contexto al trader para tomar decisiones
- Mantener el sistema simple y mantenible
- No sobrecargar el gráfico ni los payloads

---

## Archivos Relevantes

### `src/logic/analysis_service.py`
- Líneas 308-330: Cálculo de las 5 EMAs
- Líneas 556-575: Función `_determine_trend()` actual (solo usa EMA 200)
- Líneas 370-545: Análisis de vela cerrada (llama a `_determine_trend()`)

### `src/services/telegram_service.py`
- Líneas 260-285: Formato de mensaje estándar (muestra las 5 EMAs como texto)
- Líneas 328-350: Formato de mensaje fuerte (dual-source)

### `src/utils/charting.py`
- Función `generate_chart_base64()`: Genera el gráfico con mplfinance
- Actualmente NO grafica las EMAs, solo velas + volumen

### `config.py`
- `USE_TREND_FILTER`: Boolean para activar/desactivar filtro
- `CHART_LOOKBACK`: Cantidad de velas en el gráfico (default: 30)
- `EMA_PERIOD`: Período de la EMA principal (default: 200)

---

## Ejemplos de Uso Real

**Mensaje actual de Telegram:**
```
📊 Fuente: FX
📈 Patrón: SHOOTING_STAR
🕒 Timestamp: 2025-11-21 14:32:00
💰 Apertura: 1.09050
💰 Máximo: 1.09180
💰 Mínimo: 1.09020
💰 Cierre: 1.09040

📉 EMAs:
  • EMA 20: 1.09100
  • EMA 30: 1.09080
  • EMA 50: 1.09060
  • EMA 100: 1.09000
  • EMA 200: 1.08950

🎯 Tendencia: BULLISH
✨ Confianza: 85%

⚡ Verificar gráfico manualmente antes de operar.
```

**¿Cómo debería verse con mejor análisis de tendencia?**
- ¿Agregar comentarios por cada EMA?
- ¿Mostrar fuerza de tendencia?
- ¿Indicar si hay divergencia entre EMAs cortas vs largas?

---

## Petición de Ayuda

Por favor, sugiere:

1. **Algoritmo robusto** para determinar tendencia con 5 EMAs en temporalidad de 1 minuto
2. **Estructura de datos** óptima para retornar desde `_determine_trend()`
3. **Decisión sobre graficación** de EMAs (todas/algunas/ninguna)
4. **Formato de mensaje** para comunicar tendencia al usuario
5. **Estrategia de filtrado** cuando reactive `USE_TREND_FILTER=true`

Considera:
- Temporalidad muy corta (1 min) → mucho ruido
- Ya tengo las EMAs calculadas → solo necesito interpretarlas
- Busco balance entre precisión y simplicidad
- El trader final es humano → debe entender rápidamente la situación

Gracias por la ayuda. Este es el siguiente paso para mejorar el MVP. 🚀
