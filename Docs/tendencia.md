# Sistema de Análisis de Tendencia con Score Ponderado

## 🎉 PROBLEMA RESUELTO - Sistema Implementado

El sistema ahora utiliza un **algoritmo de scoring ponderado** con múltiples EMAs para determinar la tendencia de forma robusta.

## Contexto del Proyecto
Bot de trading que detecta patrones de velas japonesas en tiempo real (EUR/USD, temporalidad 1 minuto). Detecta 4 patrones: Shooting Star, Hanging Man, Inverted Hammer y Hammer.

## ✅ Solución Implementada: Sistema de Trend Scoring

### Arquitectura del Sistema

**Función Principal:** `analyze_trend(close, emas)` en `src/logic/analysis_service.py`

**Retorna:** Objeto `TrendAnalysis` con tres campos:
- `status` (str): Clasificación de la tendencia
- `score` (int): Puntuación de -10 a +10
- `is_aligned` (bool): Si las EMAs están alineadas correctamente

### Algoritmo de Scoring (5 Reglas Ponderadas)

El sistema evalúa **5 relaciones diferentes** entre precio y EMAs, asignando puntos según cada comparación:

#### 🔹 Regla 1: Precio vs EMA 200 (Macro Trend) - Peso: ±3 puntos
**Importancia:** Máxima - Define la tendencia macro
```python
if close > ema_200:
    score += 3  # Macro alcista
elif close < ema_200:
    score -= 3  # Macro bajista
```

#### 🔹 Regla 2: Precio vs EMA 100 (Mid-Term) - Peso: ±2 puntos
**Importancia:** Alta - Confirma tendencia de mediano plazo
```python
if close > ema_100:
    score += 2  # Medio plazo alcista
elif close < ema_100:
    score -= 2  # Medio plazo bajista
```

#### 🔹 Regla 3: EMA 50 vs EMA 200 (Alineación Macro) - Peso: ±2 puntos
**Importancia:** Alta - Verifica alineación estructural
```python
if ema_50 > ema_200:
    score += 2  # Estructura alcista
elif ema_50 < ema_200:
    score -= 2  # Estructura bajista
```

#### 🔹 Regla 4: Precio vs EMA 20 (Momentum) - Peso: ±2 puntos
**Importancia:** Alta - Detecta momentum de corto plazo
```python
if close > ema_20:
    score += 2  # Momentum alcista
elif close < ema_20:
    score -= 2  # Momentum bajista
```

#### 🔹 Regla 5: EMA 20 vs EMA 50 (Cruce Corto) - Peso: ±1 punto
**Importancia:** Moderada - Confirma cruce de corto plazo
```python
if ema_20 > ema_50:
    score += 1  # Cruce alcista
elif ema_20 < ema_50:
    score -= 1  # Cruce bajista
```

### Rango de Score Total

**Máximo Alcista:** +10 puntos (todas las condiciones alcistas)
- Precio > EMA 200: +3
- Precio > EMA 100: +2
- EMA 50 > EMA 200: +2
- Precio > EMA 20: +2
- EMA 20 > EMA 50: +1

**Máximo Bajista:** -10 puntos (todas las condiciones bajistas)

**Neutral:** 0 puntos (señales contradictorias se cancelan)

### Clasificación de Tendencia

El `score` se convierte en una clasificación textual:

| Score Range | Status | Interpretación |
|------------|--------|----------------|
| ≥ 6 | `STRONG_BULLISH` | Tendencia alcista muy fuerte |
| 1 a 5 | `WEAK_BULLISH` | Tendencia alcista débil |
| -1 a 1 | `NEUTRAL` | Sin tendencia clara (mercado lateral) |
| -5 a -1 | `WEAK_BEARISH` | Tendencia bajista débil |
| ≤ -6 | `STRONG_BEARISH` | Tendencia bajista muy fuerte |

### Detección de Alineación

**Alineación Alcista Perfecta:**
```
EMA 20 > EMA 50 > EMA 200
```
Todas las medias móviles ordenadas de menor a mayor período.

**Alineación Bajista Perfecta:**
```
EMA 20 < EMA 50 < EMA 200
```
Todas las medias móviles ordenadas de mayor a menor período.

**`is_aligned = True`** solo cuando se cumple una de estas dos condiciones exactas.

## 📊 EMAs Calculadas

El sistema calcula **5 EMAs** con cálculo condicional:

| EMA | Período | Velas Mínimas | Propósito |
|-----|---------|---------------|-----------|
| EMA 20 | 20 min | 20 | Momentum de muy corto plazo |
| EMA 30 | 30 min | 30 | Momentum de corto plazo |
| EMA 50 | 50 min | 50 | Tendencia de mediano plazo |
| EMA 100 | 100 min | 100 | Tendencia de mediano-largo plazo |
| EMA 200 | 200 min | 600* | Tendencia macro (3x para convergencia) |

**Nota:** Si no hay suficientes velas, la EMA se marca como `NaN` y no participa en el scoring.

## 🎯 Sistema de Alertas Inteligentes

El sistema clasifica las alertas en **3 niveles** según la relación patrón-tendencia:

### 🔴/🟢 ALERTA FUERTE (Alta Probabilidad)
**Condiciones:**
- Shooting Star + Tendencia BULLISH (fuerte o débil) → Reversión bajista probable
- Hammer + Tendencia BEARISH (fuerte o débil) → Reversión alcista probable

**Mensaje:** "Alta probabilidad de apertura BAJISTA/ALCISTA"

### ⚠️ AVISO (Debilitamiento - Requiere Cautela)
**Condiciones:**
- Inverted Hammer + Tendencia BULLISH → Posible operación a la baja
- Hanging Man + Tendencia BEARISH → Posible operación al alza

**Mensaje:**
- "⚠️ AVISO | EURUSD | Posible operación a la baja"
- "⚠️ AVISO | EURUSD | Posible operación al alza"

**⚠️ IMPORTANTE - Interpretación de AVISO:**
- Estas alertas **NO son reversiones confirmadas**
- Indican **señales de cautela** sobre posible debilitamiento de tendencia
- El trader debe **validar manualmente** con la siguiente vela
- Recomendación: Esperar confirmación antes de entrar (no es señal de alta probabilidad)
- Útil para: Cerrar posiciones existentes o prepararse para posible cambio

### 📊 DETECCIÓN (Informativo)
**Condiciones:**
- Cualquier otro caso (patrón sin alineación de tendencia clara)

**Mensaje:** "Solo informativo - Requiere análisis adicional"

## 🖼️ Visualización en Gráficos

**EMAs Graficadas:** Solo 2 para evitar saturación visual
- **EMA 200:** Línea cyan (#00D4FF), grosor 1.5 - Referencia macro
- **EMA 20:** Línea amarilla (#FFD700), grosor 1.0 - Momentum

**EMAs NO Graficadas:** EMA 30, 50, 100 (evita ruido visual en gráficos de 1 minuto)

**Razón:** Gráficos pequeños de Telegram se saturan con 5 líneas. Se muestran solo extremos (corto vs largo).

## 📱 Formato de Mensaje en Telegram

Cada alerta incluye **3 secciones**:

### Sección 1: Información de la Vela
- Fuente, Patrón, Timestamp
- OHLC (Open, High, Low, Close)
- Confianza del patrón (70-100%)

### Sección 2: Análisis de EMAs
- Valores de las 5 EMAs (o "N/A" si no disponible)
- Estructura interpretada (ej: "Precio > EMA20 > EMA200 (Alineación alcista)")
- Estado de alineación: ✓ Confirmada o ✗ No confirmada

### Sección 3: Análisis de Tendencia
- **Estado:** STRONG_BULLISH, WEAK_BULLISH, NEUTRAL, etc.
- **Score:** Valor de -10 a +10 (ej: "+7/10" o "-4/10")
- **Interpretación:** Texto en español explicando el score

**Ejemplo de interpretación:**
- Score +8: "Tendencia alcista muy fuerte"
- Score +3: "Tendencia alcista débil"
- Score 0: "Sin tendencia clara (Mercado lateral)"
- Score -5: "Tendencia bajista débil"
- Score -9: "Tendencia bajista muy fuerte"

## ⚙️ Configuración y Variables

**Implementación Actual (MVP):**
```python
USE_TREND_FILTER = False  # Notifica todos los patrones sin filtro
```

**Modo Futuro (Producción):**
```python
USE_TREND_FILTER = True  # Solo notifica patrones alineados con tendencia
```

**Lógica cuando el filtro esté activo:**
- Requiere `score >= 1` (al menos tendencia débil) para notificar
- Valida que el patrón sea coherente con la tendencia detectada
- Reduce falsos positivos significativamente

## 🔬 Ejemplo de Cálculo Real

**Escenario:**
```
Precio actual: 1.08650
EMA 20: 1.08700 (precio DEBAJO)
EMA 50: 1.08600 (precio ARRIBA)
EMA 100: 1.08550 (precio ARRIBA)
EMA 200: 1.08500 (precio ARRIBA)
```

**Cálculo del Score:**
1. Precio > EMA 200 → +3 ✓
2. Precio > EMA 100 → +2 ✓
3. EMA 50 > EMA 200 → +2 ✓
4. Precio < EMA 20 → -2 ✗ (momentum negativo)
5. EMA 20 > EMA 50 → +1 ✓

**Score Total:** +3 +2 +2 -2 +1 = **+6 puntos**

**Clasificación:** `STRONG_BULLISH` (≥6)

**Alineación:** ✗ No confirmada (EMA20 > precio, rompe la secuencia)

**Interpretación:** "Tendencia alcista muy fuerte con momentum débil de corto plazo"

## 📝 Estado del Sistema

**✅ Completamente Implementado y Operativo**

**Ubicación del código:**
- `src/logic/analysis_service.py` - Función `analyze_trend()` (líneas 73-190)
- `src/services/telegram_service.py` - Clasificación de alertas (líneas 248-276)
- `src/utils/charting.py` - Visualización de EMAs en gráficos

**⚠️ SUJETO A CAMBIOS:**
Este sistema de scoring está en fase de validación. Los pesos de las reglas, los umbrales de clasificación y la lógica de alertas pueden ajustarse según los resultados en producción.

**Próximos pasos sugeridos:**
- Implementar tracking histórico de scores en `logs/trend_scores.jsonl`
- Validar correlación entre score y movimiento real del precio 5 min después
- Ajustar pesos si se detecta sesgo sistemático
- Considerar añadir volumen como factor adicional

---

## 📚 Referencias de Documentación

Para entender el contexto completo del sistema:
- **Arquitectura general:** Ver `Docs/resumen.md`
- **Implementación técnica:** Ver `src/logic/analysis_service.py` (función `analyze_trend`)
- **Mensajes de alerta:** Ver `src/services/telegram_service.py` (clasificación 3 niveles)
- **Detección de patrones:** Ver `src/logic/candle.py` (validación matemática)

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
