# Sistema de Análisis de Tendencia - Slope & Structure (V7.1)

## Descripción General
Sistema de clasificación de tendencia optimizado para **ESTRATEGIAS DE REVERSIÓN**. A diferencia de sistemas tradicionales que buscan "fuerza máxima", este algoritmo (V7.1) está diseñado para detectar la **FASE DE LA TENDENCIA**, identificando momentos de "Agotamiento de Momentum" ideales para operar en contra.

**Fecha de Implementación:** 03 de Diciembre de 2025  
**Versión:** v7.1 - Reversion Logic

---

## Indicadores Utilizados

### EMAs Clave (V7.1)
| EMA | Periodo | Función | Rol en Score |
|-----|---------|---------|--------------|
| **EMA 3** | 3 velas | **Gatillo de Velocidad** | Detecta Agotamiento (Flattening) |
| **EMA 7** | 7 velas | **Tendencia Corta** | Confirma Momentum |
| **EMA 20** | 20 velas | **Estructura Base** | Define Dirección Macro |

**Total Máximo de Puntos:** 10.0

---

## Algoritmo V7.1 (Fases de Tendencia)

El score se compone de 3 vectores:

### 1. ESTRUCTURA (Max 3.0 pts)
Verifica la "salud geométrica" de la tendencia.
- **Alcista (+3.0):** EMA 3 > EMA 7 > EMA 20
- **Bajista (-3.0):** EMA 3 < EMA 7 < EMA 20
- **Rango (0.0):** Desorden

### 2. VELOCIDAD BASE (Max 2.0 pts)
Mide la inclinación de la EMA 20 para definir la dirección de fondo.
- **Slope EMA 20 > Threshold:** +2.0
- **Slope EMA 20 < -Threshold:** -2.0

### 3. MOMENTUM & AGOTAMIENTO (Max 5.0 pts)
Aquí reside la inteligencia del sistema. Premia la velocidad pero **PENALIZA el aplanamiento**.

**Escenario Alcista (Ejemplo):**
- Si EMA 3 y 7 suben fuerte: **+5.0 pts** (Total: 10.0 -> Momentum Fuerte)
- **CRÍTICO:** Si EMA 3 se aplana (pierde velocidad) pero la estructura sigue alcista:
    - Se aplica **PENALIZACIÓN (-2.0 pts)**.
    - El Score baja de 10.0 a ~6.0.
    - **Interpretación:** "Tendencia cansada, posible reversión".

---

## Interpretación del Score para Reversión

| Score Range | Estado | Interpretación | Acción Sugerida |
|-------------|--------|----------------|-----------------|
| **[+8.0 a +10.0]** | **STRONG_BULLISH** | Momentum Fuerte | ⛔ **NO OPERAR CONTRA.** Esperar. |
| **[+5.0 a +7.9]** | **WEAK_BULLISH** | **Agotamiento** | ✅ **ZONA IDEAL.** Buscar Patrón de Reversión (Shooting Star). |
| **[-4.9 a +4.9]** | **NEUTRAL** | Rango / Ruido | ⚠️ Precaución. Falta dirección clara. |
| **[-7.9 a -5.0]** | **WEAK_BEARISH** | **Agotamiento** | ✅ **ZONA IDEAL.** Buscar Patrón de Reversión (Hammer). |
| **[-10.0 a -8.0]** | **STRONG_BEARISH** | Momentum Fuerte | ⛔ **NO OPERAR CONTRA.** Esperar. |

---

### Ejemplo de Detección de Agotamiento
1. **Fase de Impulso:** Precio sube rápido. Estructura OK, EMA 3 con pendiente fuerte. Score: **+10.0**.
2. **Fase de Techo:** Precio se frena. Estructura sigue OK (3>7>20), pero EMA 3 se aplana.
3. **Ajuste de Score:** El sistema detecta el aplanamiento y penaliza. Score baja a **+6.0**.
4. **Señal:** El bot identifica "WEAK_BULLISH" (Agotamiento) + Patrón Shooting Star -> **ALERTA DE ALTA PROBABILIDAD**.

---

### Detección de Alineación (Fanning)
Se mantiene la verificación de alineación para confirmar la "salud" de la tendencia, pero ahora es un componente aditivo del score (+2.0) en lugar de solo un flag booleano.

**Alineación Alcista Perfecta:** `EMA 3 > EMA 7 > EMA 20`
**Alineación Bajista Perfecta:** `EMA 3 < EMA 7 < EMA 20`

---

### 1. STRONG_BULLISH (Score: 6.0 a 10.0)

**Características:**
- ✅ Precio por encima de la mayoría de EMAs
- ✅ Score ponderado ≥ 6.0
- ✅ `is_aligned = True` si hay Fanning perfecto
- 🎯 **Estrategia:** Buscar patrones BAJISTAS (Shooting Star) para reversión

**Fanning Perfecto (is_aligned = True):**
```
Precio > EMA5 > EMA7 > EMA10 > EMA20 > EMA50
```

**Ejemplo:**
```
Score: +8.5
Precio: 1.10500
EMA5:   1.10450 ─┐
EMA7:   1.10420  ├─ Todas las EMAs alineadas
EMA10:  1.10380  │
EMA20:  1.10330  │
EMA50:  1.10200 ─┘
→ STRONG_BULLISH con is_aligned = True
```

---

### 2. WEAK_BULLISH (Score: 2.0 a 6.0)

**Características:**
- ⚠️ Precio por encima de algunas EMAs
- ⚠️ Score ponderado entre 2.0 y 5.9
- ❌ `is_aligned = False`
- 🎯 **Estrategia:** Señales de reversión con menor confianza

**Ejemplo:**
```
Score: +3.5
Precio: 1.10500
EMA5:   1.10480 ─ Por encima
EMA7:   1.10460 ─ Por encima
EMA10:  1.10510 ─ Por DEBAJO (desorden)
EMA20:  1.10450 ─ Por encima
EMA50:  1.10520 ─ Por DEBAJO
→ WEAK_BULLISH (EMAs desordenadas)
```

---

### 3. NEUTRAL (Score: -2.0 a 2.0)

**Características:**
- ⚖️ Precio oscila alrededor de EMAs
- ⚖️ Score ponderado cerca de 0
- ❌ `is_aligned = False`
- ⚠️ **Estrategia:** Todas las señales se **degradan un nivel**

**Ejemplo:**
```
Score: +0.5
Precio: 1.10500
EMA5:   1.10490 ─ Muy cerca
EMA7:   1.10505 ─ Muy cerca
EMA10:  1.10495 ─ Muy cerca
EMA20:  1.10510 ─ Muy cerca
→ NEUTRAL (sin dirección clara)
```

---

### 4. WEAK_BEARISH (Score: -6.0 a -2.0)

**Características:**
- ⚠️ Precio por debajo de algunas EMAs
- ⚠️ Score ponderado entre -5.9 y -2.0
- ❌ `is_aligned = False`
- 🎯 **Estrategia:** Buscar patrones ALCISTAS (Hammer) con precaución

**Ejemplo:**
```
Score: -4.0
Precio: 1.10500
EMA5:   1.10520 ─ Por debajo
EMA7:   1.10540 ─ Por debajo
EMA10:  1.10490 ─ Por ENCIMA (desorden)
EMA20:  1.10550 ─ Por debajo
→ WEAK_BEARISH (EMAs desordenadas)
```

---

### 5. STRONG_BEARISH (Score: -10.0 a -6.0)

**Características:**
- ✅ Precio por debajo de la mayoría de EMAs
- ✅ Score ponderado ≤ -6.0
- ✅ `is_aligned = True` si hay Fanning perfecto
- 🎯 **Estrategia:** Buscar patrones ALCISTAS (Hammer) para reversión

**Fanning Perfecto (is_aligned = True):**
```
Precio < EMA5 < EMA7 < EMA10 < EMA20 < EMA50
```

**Ejemplo:**
```
Score: -9.0
Precio: 1.10500
EMA5:   1.10550 ─┐
EMA7:   1.10580  ├─ Todas las EMAs alineadas
EMA10:  1.10620  │
EMA20:  1.10670  │
EMA50:  1.10800 ─┘
→ STRONG_BEARISH con is_aligned = True
```

---

## Ventajas del Sistema Ponderado

### 1. **Gradualidad**
- ❌ **Sistema Anterior:** Cambios bruscos al cruzar una EMA
- ✅ **Sistema Actual:** Transiciones suaves y graduales

### 2. **Ponderación Inteligente**
- EMAs rápidas (5, 7) tienen más peso (2.0-2.5 pts)
- EMAs lentas (50) tienen menos peso (0.5 pts)
- Refleja mejor el momentum inmediato

### 3. **Flexibilidad**
- Fácil ajustar pesos sin cambiar toda la lógica
- Permite fine-tuning según backtesting

### 4. **Transparencia**
- Score numérico claro (-10.0 a +10.0)
- Fácil entender qué EMAs influyen más

---

## Integración con Scoring Matricial

El `score` de tendencia se combina con:
1. **Bollinger Exhaustion** (PEAK/BOTTOM/NONE)
2. **Candle Exhaustion** (True/False)
3. **Tipo de Patrón** (Principal/Secundario)

Para generar el **Signal Strength** final:
- VERY_HIGH
- HIGH
- MEDIUM
- LOW
- VERY_LOW
- NONE

Ver `BOLLINGER_EXHAUSTION_SYSTEM.md` para más detalles.

---

## Visualización en Gráficos

Las 7 EMAs se muestran con colores distintivos:

| EMA | Color | Grosor | Descripción |
| EMA | Color | Grosor | Descripción |
|-----|-------|--------|-------------|
| EMA 3 | ⚪ Blanco | 3.2 | Sniper / Trigger |
| EMA 5 | 🔴 Rojo | 3.0 | Momentum Inmediato |
| EMA 7 | 🟣 Magenta | 2.8 | Muy rápida |
| EMA 10 | 🟠 Naranja | 2.5 | Rápida |
| EMA 20 | 🟢 Verde | 2.0 | Media |
| EMA 30 | 🔵 Cyan | 1.8 | Referencia |
| EMA 50 | 🟦 Azul | 1.5 | Referencia |

**Ventaja Visual:** El grosor de la línea refleja su peso en el sistema.

---

## Casos de Uso

### Caso 1: Tendencia Alcista Fuerte con Fanning
```
Precio: 1.10500 (por encima de todas)
Score: +10.0
Estado: STRONG_BULLISH
is_aligned: True (Fanning perfecto)
Estrategia: Buscar Shooting Star + PEAK para señal VERY_HIGH
```

### Caso 2: Tendencia Mixta
```
Precio: 1.10500
EMA5: 1.10490 (+2.5)
EMA7: 1.10510 (-2.0)
EMA10: 1.10480 (+1.5)
EMA50: 1.10520 (-0.5)
Score: +1.5
Estado: NEUTRAL
Estrategia: Degradar todas las señales un nivel
```

### Caso 3: Reversión en Tendencia Bajista
```
Precio: 1.10500 (debajo de todas excepto EMA5)
Score: -7.5
Estado: STRONG_BEARISH
Estrategia: Buscar Hammer + BOTTOM para señal VERY_HIGH
```

---

## Configuración en Código

```python
# config.py
class Config:
    EMA_FAST_PERIOD: int = 7  # No se usa en scoring, solo para referencia
    EMA_PERIOD: int = 200  # Obsoleto, mantener para compatibilidad
    
    # Sistema de puntuación ponderada usa directamente:
    # EMA 5, 7, 10, 15, 20, 30, 50
```

```python
# analysis_service.py
def analyze_trend(close: float, emas: Dict[str, float]) -> TrendAnalysis:
    ema_weights = {
        'ema_5': 2.5,
        'ema_7': 2.0,
        'ema_10': 1.5,
        'ema_15': 1.5,
        'ema_20': 1.0,
        'ema_30': 1.0,
        'ema_50': 0.5
    }
    # ... (ver código completo en archivo)
```

---

## Mensajes de Telegram

El mensaje incluye:
- Score ponderado con 1 decimal: `+8.5/10.0`
- Estado de tendencia: `STRONG_BULLISH`
- Todas las EMAs con su valor y peso
- Información de debug (si `SHOW_CANDLE_RESULT=true`)

---

## Conclusión

El sistema de **puntuación ponderada** ofrece:
- ✅ Transiciones suaves sin saltos bruscos
- ✅ Priorización inteligente de EMAs rápidas
- ✅ Fácil ajuste de pesos según backtesting
- ✅ Transparencia en el scoring
- ✅ Integración perfecta con Bollinger Exhaustion

**Próximos pasos:** Validar pesos óptimos mediante backtesting extensivo.

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
