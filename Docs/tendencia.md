# Sistema de Análisis de Tendencia con Score Ponderado

## 🎉 ACTUALIZACIÓN CRÍTICA - Optimizado para Opciones Binarias (22/Nov/2025)

**⚠️ CAMBIO IMPORTANTE:** El sistema ha sido **reoptimizado para OPCIONES BINARIAS** con temporalidad de 1 minuto. Los pesos del scoring ahora priorizan el **momentum de corto plazo** sobre la tendencia macro.

**Cambios clave:**
- ✅ EMA 20 ahora tiene **4x más peso** que EMA 200
- ✅ Cruce EMA 20/50 tiene **3x más peso** que antes
- ✅ EMA 100 eliminada del scoring (simplificación)
- ✅ Se permite operar contra-tendencia macro si hay momentum fuerte

**Filosofía anterior:** "No operar contra la tendencia de EMA 200"  
**Filosofía actual:** "Priorizar momentum inmediato - EMA 200 es solo contexto"

---

## Contexto del Proyecto
Bot de trading que detecta patrones de velas japonesas en tiempo real (EUR/USD, temporalidad 1 minuto). Detecta 4 patrones: Shooting Star, Hanging Man, Inverted Hammer y Hammer.

## ✅ Solución Implementada: Sistema de Momentum Scoring

### Arquitectura del Sistema

**Función Principal:** `analyze_trend(close, emas)` en `src/logic/analysis_service.py`

**Retorna:** Objeto `TrendAnalysis` con tres campos:
- `status` (str): Clasificación de la tendencia
- `score` (int): Puntuación de -10 a +10
- `is_aligned` (bool): Si las EMAs están alineadas correctamente

### Algoritmo de Scoring (4 Reglas Ponderadas - Optimizado para Opciones Binarias)

**Filosofía:** Sistema optimizado para **OPCIONES BINARIAS (1 minuto)** donde el momentum de corto plazo es CRÍTICO. Los pesos priorizan las EMAs más cercanas al precio actual, ya que en temporalidades tan cortas la tendencia macro es menos relevante.

El sistema evalúa **4 relaciones clave** entre precio y EMAs, con pesos que reflejan su importancia en operaciones de 1 minuto:

#### 🔴 PRIORIDAD ALTA - Corto Plazo (70% del score)

**Regla 1: Precio vs EMA 20 (Momentum Inmediato)** - Peso: ±4 puntos
**Importancia:** CRÍTICA - Indica la fuerza inmediata del flujo de órdenes
```python
if close > ema_20:
    score += 4  # Fuerza alcista inmediata
elif close < ema_20:
    score -= 4  # Fuerza bajista inmediata
```
**Justificación:** En 1 minuto, la EMA 20 refleja la dirección ACTUAL del mercado. Es 4x más importante que la tendencia macro.

**Regla 2: EMA 20 vs EMA 50 (Dirección del Flujo)** - Peso: ±3 puntos
**Importancia:** CRÍTICA - Confirma que el momentum no es solo un spike temporal
```python
if ema_20 > ema_50:
    score += 3  # Cruce alcista confirmado
elif ema_20 < ema_50:
    score -= 3  # Cruce bajista confirmado
```
**Justificación:** Un cruce 20/50 indica que hay una tendencia de corto plazo establecida, no solo ruido.

#### 🟡 PRIORIDAD MEDIA - Contexto (20% del score)

**Regla 3: Precio vs EMA 50 (Zona de Valor)** - Peso: ±2 puntos
**Importancia:** MEDIA - Indica si el precio está "caro" o "barato" a mediano plazo
```python
if close > ema_50:
    score += 2  # Soporte dinámico alcista
elif close < ema_50:
    score -= 2  # Resistencia dinámica bajista
```
**Justificación:** Ayuda a identificar zonas de soporte/resistencia dinámicas.

#### 🟢 PRIORIDAD BAJA - Filtro Macro (10% del score)

**Regla 4: Precio vs EMA 200 (Filtro Macro)** - Peso: ±1 punto
**Importancia:** BAJA - Solo contexto general, NO penaliza operaciones contra-tendencia
```python
if close > ema_200:
    score += 1  # Macro alcista
elif close < ema_200:
    score -= 1  # Macro bajista
```
**Justificación:** En opciones binarias, un momentum fuerte de corto plazo puede superar la tendencia macro.

### Rango de Score Total

**Máximo Alcista:** +10 puntos (todas las condiciones alcistas)
- Precio > EMA 20: +4 🔴 (Momentum inmediato)
- EMA 20 > EMA 50: +3 🔴 (Dirección confirmada)
- Precio > EMA 50: +2 🟡 (Zona de valor)
- Precio > EMA 200: +1 🟢 (Contexto macro)

**Máximo Bajista:** -10 puntos (todas las condiciones bajistas)

**Neutral:** 0 puntos (señales contradictorias se cancelan)

**⚠️ IMPORTANTE para Opciones Binarias:**
Un score de +7 (sin EMA 200 favorable) es válido para entrar:
- Precio > EMA 20: +4
- EMA 20 > EMA 50: +3
- Total: +7 = STRONG_BULLISH

Esto significa que priorizamos el momentum inmediato sobre la tendencia macro.

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

| EMA | Período | Velas Mínimas | Propósito | Peso en Score | Prioridad |
|-----|---------|---------------|-----------|---------------|----------|
| EMA 20 | 20 min | 20 | Momentum inmediato (flujo de órdenes) | ±4 pts | 🔴 CRÍTICA |
| EMA 30 | 30 min | 30 | Visualización (no usado en scoring) | 0 pts | - |
| EMA 50 | 50 min | 50 | Zona de valor / Soporte dinámico | ±2 pts | 🟡 MEDIA |
| EMA 100 | 100 min | 100 | Visualización (no usado en scoring) | 0 pts | - |
| EMA 200 | 200 min | 600* | Contexto macro (filtro opcional) | ±1 pt | 🟢 BAJA |

**⚠️ Cambio Clave vs Versión Anterior:**
- **EMA 20:** Aumentó de ±2 pts a **±4 pts** (2x más peso)
- **EMA 20 vs EMA 50:** Aumentó de ±1 pt a **±3 pts** (3x más peso)
- **EMA 200:** Disminuyó de ±3 pts a **±1 pt** (3x menos peso)
- **EMA 100:** Eliminada del scoring (solo visualización)

**Justificación:** En opciones binarias (1 min), el momentum de corto plazo es 4x más importante que la tendencia macro.

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

**EMAs Graficadas:** Las 5 EMAs calculadas se visualizan con colores y grosores diferenciados:
- **EMA 200:** Línea cyan (#00D4FF), grosor 2.0 - Tendencia macro
- **EMA 100:** Línea azul (#0080FF), grosor 1.8 - Tendencia media
- **EMA 50:** Línea verde (#00FF80), grosor 1.5 - Corto plazo
- **EMA 30:** Línea amarilla (#FFFF00), grosor 1.2 - Momentum medio
- **EMA 20:** Línea naranja (#FF8000), grosor 1.0 - Momentum corto

**Leyenda Integrada:** Esquina superior izquierda del gráfico muestra todas las EMAs con sus colores correspondientes.

**Performance de Generación:**
- Preparación de datos: 5-10 ms
- Render matplotlib (5 EMAs + velas + volumen): 150-300 ms
- Encoding Base64: 50-100 ms
- **Tiempo total: ~220 ms** (ejecutado en hilo separado, no bloquea WebSocket)

**Ventaja:** Visualización completa del contexto de tendencia en un solo gráfico, permitiendo al trader identificar rápidamente la alineación de las medias móviles.

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

## 🔬 Ejemplo de Cálculo Real (Nuevo Sistema)

### Escenario 1: Momentum Alcista Fuerte (Contra Tendencia Macro)
```
Precio actual: 1.08650
EMA 20: 1.08600 (precio ARRIBA) ✓
EMA 50: 1.08550 (precio ARRIBA) ✓
EMA 200: 1.08700 (precio DEBAJO) ✗
```

**Cálculo del Score:**
1. Precio > EMA 20 → **+4** ✓ (momentum alcista inmediato)
2. EMA 20 > EMA 50 → **+3** ✓ (dirección confirmada)
3. Precio > EMA 50 → **+2** ✓ (zona de valor alcista)
4. Precio < EMA 200 → **-1** ✗ (macro bajista)

**Score Total:** +4 +3 +2 -1 = **+8 puntos**

**Clasificación:** `STRONG_BULLISH` (≥6)

**Alineación:** ✗ No confirmada (EMA 200 por encima)

**Interpretación Opciones Binarias:** "Momentum alcista MUY FUERTE de corto plazo. Válido para entrada CALL a pesar de tendencia macro bajista. Score +8 domina sobre -1 del macro."

---

### Escenario 2: Momentum Débil en Tendencia Alcista
```
Precio actual: 1.08650
EMA 20: 1.08700 (precio DEBAJO) ✗
EMA 50: 1.08600 (precio ARRIBA) ✓
EMA 200: 1.08500 (precio ARRIBA) ✓
```

**Cálculo del Score:**
1. Precio < EMA 20 → **-4** ✗ (momentum bajista inmediato)
2. EMA 20 > EMA 50 → **+3** ✓ (dirección alcista confirmada)
3. Precio > EMA 50 → **+2** ✓ (zona de valor alcista)
4. Precio > EMA 200 → **+1** ✓ (macro alcista)

**Score Total:** -4 +3 +2 +1 = **+2 puntos**

**Clasificación:** `WEAK_BULLISH` (2 a 5)

**Interpretación Opciones Binarias:** "Retroceso temporal en tendencia alcista. Momentum inmediato bajista (-4) contradice contexto alcista (+6). Zona de indecisión - esperar confirmación."

## 📝 Estado del Sistema

**✅ Completamente Implementado y Operativo - Optimizado para Opciones Binarias**

**Ubicación del código:**
- `src/logic/analysis_service.py` - Función `analyze_trend()` (líneas 88-177)
  - Sistema de scoring con 4 reglas ponderadas
  - Prioridad en EMAs de corto plazo (20/50)
  - Clasificación en 5 niveles de momentum

- `src/services/telegram_service.py` - Clasificación de alertas (líneas 248-276)
  - Mensajes adaptados a momentum vs tendencia
  - Información completa de las 5 EMAs calculadas

**⚠️ CAMBIOS CRÍTICOS vs Versión Anterior:**

| Componente | Versión Anterior | Versión Actual | Impacto |
|------------|-----------------|----------------|---------|
| **EMA 20 (Precio)** | ±2 pts | **±4 pts** | 2x más peso en momentum inmediato |
| **EMA 20 vs 50** | ±1 pt | **±3 pts** | 3x más peso en confirmación de flujo |
| **EMA 200** | ±3 pts | **±1 pt** | 3x menos peso, solo contexto |
| **EMA 100** | ±2 pts | **Eliminada** | Simplificación del algoritmo |
| **Filosofía** | Tendencia macro | **Momentum corto** | Apto para binarias 1min |

**Validación en Producción:**
- ✅ Permite operar contra-tendencia macro si hay momentum fuerte
- ✅ Score +7 (sin EMA 200) genera alertas STRONG_BULLISH
- ✅ Clasificación refleja "momentum" en vez de "tendencia"
- ✅ Sistema alineado con estrategia de opciones binarias

**Próximos pasos sugeridos:**
- Implementar tracking histórico de scores en `logs/trend_scores.jsonl`
- Validar correlación entre score y movimiento real del precio en ventana de 1-5 minutos
- Analizar win rate por rango de score (≥6 vs 2-5 vs ≤-6)
- Considerar añadir volumen como factor de confirmación adicional
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
