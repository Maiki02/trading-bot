# Sistema de Scoring Matricial - Bollinger & Candle Exhaustion

## Descripción General
Sistema de puntuación y clasificación de señales basado en la combinación de:
1. **Bollinger Exhaustion**: Precio toca/rompe bandas de Bollinger
2. **Candle Exhaustion**: Vela actual rompe high/low de vela anterior
3. **Patrón de Vela**: Shooting Star, Hanging Man, Hammer, Inverted Hammer
4. **Tendencia**: 5 estados basados en **scoring ponderado de EMAs**

**Fecha de Implementación:** 24 de Noviembre de 2025  
**Versión:** v5 - Sistema Matricial con Puntuación Ponderada

---

## Componentes del Sistema

### 1. Bollinger Exhaustion (Zona de Agotamiento)

#### Configuración
```python
BB_PERIOD = 20  # SMA, NO EMA
BB_STD_DEV = 2.0  # Desviaciones estándar
```

**Fórmula:**
```
BB_Middle = SMA(Close, 20)
BB_Upper = BB_Middle + (2.0 × σ)
BB_Lower = BB_Middle - (2.0 × σ)
```

**Justificación de 2.0σ:** Captura aproximadamente el 95% de los movimientos de precio, permitiendo identificar sobre-extensiones reales sin ser demasiado restrictivo.

#### Detección
```python
def detect_exhaustion(candle_high, candle_low, candle_close, upper_band, lower_band):
    # PEAK (Cúspide): Agotamiento alcista
    if candle_high >= upper_band or candle_close >= upper_band:
        return "PEAK"
    
    # BOTTOM (Base): Agotamiento bajista
    if candle_low <= lower_band or candle_close <= lower_band:
        return "BOTTOM"
    
    # Zona neutra
    return "NONE"
```

**Zonas:**
- **PEAK** (Cúspide): Sobre-extensión alcista → Buscar patrones BAJISTAS
- **BOTTOM** (Base): Sobre-extensión bajista → Buscar patrones ALCISTAS
- **NONE**: Sin sobre-extensión clara

---

### 2. Candle Exhaustion (Ruptura de Nivel)

#### Lógica
```python
def detect_candle_exhaustion(pattern, current_high, current_low, prev_high, prev_low):
    # Patrones BAJISTAS: verificar ruptura de máximo
    if pattern in ["SHOOTING_STAR", "HANGING_MAN"]:
        return current_high > prev_high
    
    # Patrones ALCISTAS: verificar ruptura de mínimo
    elif pattern in ["HAMMER", "INVERTED_HAMMER"]:
        return current_low < prev_low
    
    return False
```

**Significado:**
- El precio intentó continuar la tendencia
- Fue **rechazado** creando una mecha larga
- Aumenta probabilidad de reversión

---

### 3. Tendencia (Sistema de Puntuación Ponderada)

**5 Estados basados en scoring de 7 EMAs:**

| Score Range | Estado | EMAs Totales |
|-------------|--------|--------------|
| [6.0 a 10.0] | STRONG_BULLISH | 10.0 pts |
| [2.0 a 6.0) | WEAK_BULLISH | 10.0 pts |
| (-2.0 a 2.0) | NEUTRAL | 10.0 pts |
| (-6.0 a -2.0] | WEAK_BEARISH | 10.0 pts |
| [-10.0 a -6.0] | STRONG_BEARISH | 10.0 pts |

Ver `tendencia.md` para detalles completos del sistema ponderado.

---

## Niveles de Señal

| Nivel | Descripción | Probabilidad | Emoji |
|-------|-------------|--------------|-------|
| **VERY_HIGH** | Patrón Principal + Ambos Exhaustion | Muy Alta | 🔥 |
| **HIGH** | Patrón Principal + Bollinger Exhaustion | Alta | 🚨 |
| **MEDIUM** | Patrón Secundario + Ambos Exhaustion | Media | ⚠️ |
| **LOW** | Patrón Principal + Candle Exhaustion | Baja | ℹ️ |
| **VERY_LOW** | Patrón Principal sin Exhaustion | Muy Baja | ⚪ |
| **NONE** | Patrón inválido o contra-estrategia | Ninguna | ❌ |

---

## CASO A: TENDENCIA ALCISTA (Buscamos VENTAS)

### Objetivo
Detectar reversiones bajistas en zonas de sobre-compra.

### Patrones Válidos
- **Principal:** Shooting Star (patrón bajista)
- **Secundario:** Inverted Hammer (patrón bajista débil)

### Matriz de Decisión

#### Shooting Star (Patrón Principal)

| Bollinger Exhaustion | Candle Exhaustion | SCORE | Interpretación |
|---------------------|-------------------|-------|----------------|
| ✅ SÍ (PEAK) | ✅ SÍ | **VERY_HIGH** | 🔥 Reversión bajista con confirmación máxima |
| ✅ SÍ (PEAK) | ❌ NO | **HIGH** | 🚨 Reversión bajista en agotamiento alcista |
| ❌ NO | ✅ SÍ | **LOW** | ℹ️ Posible reversión (sin Bollinger) |
| ❌ NO | ❌ NO | **VERY_LOW** | ⚪ Patrón detectado pero sin exhaustion |

**Ejemplo VERY_HIGH:**
```
Precio toca Banda Superior (PEAK) ✅
Shooting Star rompe high de vela anterior ✅
Tendencia: STRONG_BULLISH (score +8.0) ✅
→ Señal: 🔥 VERY_HIGH (operar PUT)
```

---

#### Inverted Hammer (Patrón Secundario)

| Bollinger Exhaustion | Candle Exhaustion | SCORE | Interpretación |
|---------------------|-------------------|-------|----------------|
| ✅ SÍ (PEAK) | ✅ SÍ | **MEDIUM** | ⚠️ Reversión bajista moderada |
| ✅ SÍ (PEAK) | ❌ NO | **LOW** | ℹ️ Reversión bajista débil |
| ❌ NO | ✅ SÍ | **VERY_LOW** | ⚪ Patrón débil con ruptura |
| ❌ NO | ❌ NO | **NONE** | ❌ Descartado (patrón secundario sin exhaustion) |

**Ejemplo MEDIUM:**
```
Precio toca Banda Superior (PEAK) ✅
Inverted Hammer rompe high de vela anterior ✅
Tendencia: WEAK_BULLISH (score +3.5) ✅
→ Señal: ⚠️ MEDIUM (operar PUT con precaución)
```

---

### Patrones NO Válidos en Tendencia Alcista
| Patrón | Score | Razón |
|--------|-------|-------|
| **Hammer** | **NONE** | ❌ Patrón alcista en tendencia alcista = Contra-estrategia |
| **Hanging Man** | **NONE** | ❌ No aplicable en tendencia alcista |

---

## CASO B: TENDENCIA BAJISTA (Buscamos COMPRAS)

### Objetivo
Detectar reversiones alcistas en zonas de sobre-venta.

### Patrones Válidos
- **Principal:** Hammer (patrón alcista)
- **Secundario:** Hanging Man (patrón alcista débil)

### Matriz de Decisión

#### Hammer (Patrón Principal)

| Bollinger Exhaustion | Candle Exhaustion | SCORE | Interpretación |
|---------------------|-------------------|-------|----------------|
| ✅ SÍ (BOTTOM) | ✅ SÍ | **VERY_HIGH** | 🔥 Reversión alcista con confirmación máxima |
| ✅ SÍ (BOTTOM) | ❌ NO | **HIGH** | 🚨 Reversión alcista en agotamiento bajista |
| ❌ NO | ✅ SÍ | **LOW** | ℹ️ Posible reversión (sin Bollinger) |
| ❌ NO | ❌ NO | **VERY_LOW** | ⚪ Patrón detectado pero sin exhaustion |

**Ejemplo VERY_HIGH:**
```
Precio toca Banda Inferior (BOTTOM) ✅
Hammer rompe low de vela anterior ✅
Tendencia: STRONG_BEARISH (score -9.0) ✅
→ Señal: 🔥 VERY_HIGH (operar CALL)
```

---

#### Hanging Man (Patrón Secundario)

| Bollinger Exhaustion | Candle Exhaustion | SCORE | Interpretación |
|---------------------|-------------------|-------|----------------|
| ✅ SÍ (BOTTOM) | ✅ SÍ | **MEDIUM** | ⚠️ Reversión alcista moderada |
| ✅ SÍ (BOTTOM) | ❌ NO | **LOW** | ℹ️ Reversión alcista débil |
| ❌ NO | ✅ SÍ | **VERY_LOW** | ⚪ Patrón débil con ruptura |
| ❌ NO | ❌ NO | **NONE** | ❌ Descartado (patrón secundario sin exhaustion) |

**Ejemplo MEDIUM:**
```
Precio toca Banda Inferior (BOTTOM) ✅
Hanging Man rompe low de vela anterior ✅
Tendencia: WEAK_BEARISH (score -4.0) ✅
→ Señal: ⚠️ MEDIUM (operar CALL con precaución)
```

---

### Patrones NO Válidos en Tendencia Bajista
| Patrón | Score | Razón |
|--------|-------|-------|
| **Shooting Star** | **NONE** | ❌ Patrón bajista en tendencia bajista = Contra-estrategia |
| **Inverted Hammer** | **NONE** | ❌ No aplicable en tendencia bajista |

---

## CASO C: TENDENCIA NEUTRAL (Degradación Automática)

### Regla de Degradación
Cuando la tendencia es **NEUTRAL** (score entre -2.0 y 2.0), todas las señales se **degradan un nivel**:

| Score Original | Score Degradado |
|----------------|-----------------|
| VERY_HIGH | → HIGH |
| HIGH | → MEDIUM |
| MEDIUM | → LOW |
| LOW | → VERY_LOW |
| VERY_LOW | → NONE |
| NONE | → NONE |

**Ejemplo:**
```python
# Caso: Shooting Star + Ambos Exhaustion + Tendencia NEUTRAL (score +1.0)
if tendencia == "NEUTRAL":
    # Normalmente sería VERY_HIGH
    signal_strength = downgrade("VERY_HIGH")  # → HIGH
```

**Razón:** Sin tendencia clara, la probabilidad de reversión efectiva disminuye.

---

## Resumen de Todas las Combinaciones Válidas

### Tendencia ALCISTA (STRONG/WEAK_BULLISH)

| Patrón | Bollinger | Candle | Score | Dir. |
|--------|-----------|--------|-------|------|
| Shooting Star | ✅ PEAK | ✅ SÍ | VERY_HIGH | 🔴 VENTA |
| Shooting Star | ✅ PEAK | ❌ NO | HIGH | 🔴 VENTA |
| Shooting Star | ❌ NONE | ✅ SÍ | LOW | 🔴 VENTA |
| Shooting Star | ❌ NONE | ❌ NO | VERY_LOW | 🔴 VENTA |
| Inverted Hammer | ✅ PEAK | ✅ SÍ | MEDIUM | 🔴 VENTA |
| Inverted Hammer | ✅ PEAK | ❌ NO | LOW | 🔴 VENTA |
| Inverted Hammer | ❌ NONE | ✅ SÍ | VERY_LOW | 🔴 VENTA |
| Inverted Hammer | ❌ NONE | ❌ NO | NONE | ❌ Descartado |
| **Hammer** | - | - | **NONE** | ❌ Contra-estrategia |
| **Hanging Man** | - | - | **NONE** | ❌ No aplicable |

## Ejemplos Prácticos Completos

### Ejemplo 1: VERY_HIGH en Tendencia Alcista 🔥

**Contexto:**
```
Símbolo: EUR/USD
Timeframe: 1 minuto
Tendencia: STRONG_BULLISH (Score: +10.0)
EMAs: Precio por encima de todas las EMAs (Fanning perfecto)
```

**Vela Anterior:**
```
Open: 1.10400
High: 1.10450 ← Máximo anterior
Low: 1.10390
Close: 1.10440
```

**Vela Actual (Shooting Star):**
```
Open: 1.10440
High: 1.10520 ← Rompe máximo anterior ✅
Low: 1.10430
Close: 1.10445 ← Cerca del Open (cuerpo pequeño)
Upper Wick: 0.00075 (largo)
Lower Wick: 0.00015 (pequeño)
```

**Bollinger Bands:**
```
Upper Band: 1.10515
Lower Band: 1.10300
Candle High (1.10520) > Upper Band ✅ → PEAK
```

**Resultado:**
- ✅ Patrón: Shooting Star (Principal)
- ✅ Bollinger Exhaustion: PEAK
- ✅ Candle Exhaustion: 1.10520 > 1.10450
- ✅ Tendencia: STRONG_BULLISH
- **Score: VERY_HIGH 🔥**
- **Acción: Operar PUT con alta confianza**

---

### Ejemplo 2: MEDIUM en Tendencia Bajista ⚠️

**Contexto:**
```
Símbolo: EUR/USD
Timeframe: 1 minuto
Tendencia: WEAK_BEARISH (Score: -3.5)
EMAs: Precio por debajo de EMAs 5, 7, 10 pero por encima de 20, 30
```

**Vela Anterior:**
```
Open: 1.09850
High: 1.09870
Low: 1.09820 ← Mínimo anterior
Close: 1.09830
```

**Vela Actual (Hanging Man):**
```
Open: 1.09830
High: 1.09850
Low: 1.09780 ← Rompe mínimo anterior ✅
Close: 1.09840 ← Cerca del High (cuerpo pequeño)
Upper Wick: 0.00010 (pequeño)
Lower Wick: 0.00060 (largo)
```

**Bollinger Bands:**
```
Upper Band: 1.09950
Lower Band: 1.09790
Candle Low (1.09780) < Lower Band ✅ → BOTTOM
```

**Resultado:**
- ✅ Patrón: Hanging Man (Secundario)
- ✅ Bollinger Exhaustion: BOTTOM
- ✅ Candle Exhaustion: 1.09780 < 1.09820
- ⚠️ Tendencia: WEAK_BEARISH (no STRONG)
- **Score: MEDIUM ⚠️**
- **Acción: Operar CALL con precaución moderada**

---

### Ejemplo 3: NONE - Patrón Contra-Estrategia ❌

**Contexto:**
```
Símbolo: EUR/USD
Timeframe: 1 minuto
Tendencia: STRONG_BULLISH (Score: +10.0)
```

**Vela Actual (Hammer):**
```
Open: 1.10400
High: 1.10420
Low: 1.10350 ← Mecha inferior larga
Close: 1.10410 ← Vela verde
```

**Bollinger Bands:**
```
Lower Band: 1.10300
Candle Low (1.10350) > Lower Band → NONE (no agotamiento)
```

**Resultado:**
- ❌ Patrón: Hammer (Alcista)
- ❌ Tendencia: STRONG_BULLISH (Alcista)
- ❌ Conflicto: Patrón alcista EN tendencia alcista
- **Score: NONE ❌**
- **Razón: Contra-estrategia Mean Reversion**
- **Acción: NO operar**

---

## Integración con Telegram

### Formato de Notificaciones

```markdown
🔥🔴 SEÑAL MUY FUERTE | *EURUSD* 🔴🔥
🔴 Siguiente operación a la BAJA (Alta Probabilidad).

━━━━━━━━━━━━━━━━━━━━━━
🔹 Señal: VERY_HIGH

🔹 Fuente: OANDA
🔹 Patrón: SHOOTING_STAR
🔹 Fecha: 2025-11-24 15:30:45
🔺 Señal de agotamiento alcista (Cúspide)
💥 Rompió nivel anterior
🔹 Tendencia: STRONG_BULLISH
🔹 Score: +10.0/10.0
━━━━━━━━━━━━━━━━━━━━━━

📊 SISTEMA DE PUNTUACIÓN
━━━━━━━━━━━━━━━━━━━━━━
Precio > EMA5: +2.5
Precio > EMA7: +2.0
Precio > EMA10: +1.5
Precio > EMA15: +1.5
Precio > EMA20: +1.0
Precio > EMA30: +1.0
Precio > EMA50: +0.5
━━━━━━━━━━━━━━━━━━━━━━
Score Total: +10.0 → STRONG_BULLISH
━━━━━━━━━━━━━━━━━━━━━━
```

---

## Implementación Técnica

### Archivos Modificados
```
src/logic/analysis_service.py
  - analyze_trend(): Sistema de puntuación ponderada con 7 EMAs
  - detect_bollinger_exhaustion(): Detección de PEAK/BOTTOM/NONE
  - detect_candle_exhaustion(): Verificación de ruptura de nivel
  - _calculate_signal_strength(): Matriz de scoring completa

src/services/telegram_service.py
  - _format_standard_message(): Mensajes con scoring detallado
  - Emojis diferenciados por nivel (🔥, 🚨, ⚠️, ℹ️, ⚪)

src/utils/charting.py
  - Visualización de 7 EMAs con colores distintivos
  - Bandas de Bollinger en gráfico
```

---

## Conclusión

El **Sistema de Scoring Matricial** combina:
1. ✅ **Puntuación Ponderada de Tendencia**: 7 EMAs con pesos específicos (total 10.0 pts)
2. ✅ **Bollinger Exhaustion**: Detección de sobre-extensión (PEAK/BOTTOM)
3. ✅ **Candle Exhaustion**: Ruptura de niveles anteriores
4. ✅ **Clasificación en 6 Niveles**: VERY_HIGH, HIGH, MEDIUM, LOW, VERY_LOW, NONE
5. ✅ **Degradación Automática**: En tendencias NEUTRAL

**Próximos pasos:**
- Validar win rate por nivel de señal mediante backtesting
- Ajustar pesos de EMAs según resultados en producción
- Considerar añadir RSI como factor adicional de confirmación

**Referencias:**
- Ver `tendencia.md` para detalles del sistema de puntuación ponderada
- Ver `candle.md` para validación matemática de patrones
        if exhaustion_type == "BOTTOM":
            signal_strength = "MEDIUM"  # ⚠️ Reversión moderada
        else:
            signal_strength = "LOW"
    elif pattern == "HANGING_MAN":
        if exhaustion_type == "BOTTOM":
            signal_strength = "MEDIUM"  # ⚠️ Continuación bajista
        else:
            signal_strength = "LOW"
    elif pattern == "SHOOTING_STAR":
        signal_strength = "NONE"  # ⚪ Contra-estrategia

# 6. Validar que hay tendencia clara (no lateral)
if signal_strength in ["HIGH", "MEDIUM"] and not trend_analysis.is_aligned:
    signal_strength = "LOW"  # Degradar si el mercado está lateral
```

---

## 🆕 Sistema de EMAs para Mean Reversion

### Nueva Configuración

| EMA | Propósito | Peso en Score |
|-----|-----------|---------------|
| **EMA 7** | **Detección de sobre-extensión** (CRÍTICA) | ±5 pts |
| **EMA 20** | Confirmación de momentum a revertir | ±3 pts |
| **EMA 50** | Validación de tendencia (evitar laterales) | ±2 pts |
| EMA 200 | Solo referencia visual | 0 pts (no usada) |

### Scoring de Sobre-Extensión

El nuevo algoritmo `analyze_trend()` mide **sobre-extensión** en lugar de alineación:

**Score NEGATIVO (-10 a -1):** Sobre-extensión ALCISTA → Reversión BAJISTA probable  
**Score POSITIVO (+1 a +10):** Sobre-extensión BAJISTA → Reversión ALCISTA probable

**Ejemplo:**
```
Precio: 1.08750
EMA 7:  1.08600  (precio 15 pips arriba - sobre-extensión alcista)
EMA 20: 1.08550
EMA 50: 1.08500

Score: -8 (STRONG_BEARISH)
Interpretación: Sobre-extensión alcista extrema → Buscar patrones BAJISTAS
```

---

## 📈 Impacto en Notificaciones

### Mensaje de Telegram (Mean Reversion)

Las notificaciones ahora reflejan la estrategia de reversión:

```
🚨 SEÑAL HIGH | EURUSD
Reversión BAJISTA en sobre-extensión alcista

━━━━━━━━━━━━━━━━━━━━━━━━
📊 INFO DE VELA
━━━━━━━━━━━━━━━━━━━━━━━━
🔹 Patrón: SHOOTING_STAR
🔹 Confianza Técnica: 85%
🔹 Fuerza de Señal: HIGH

━━━━━━━━━━━━━━━━━━━━━━━━
📉 ANÁLISIS DE SOBRE-EXTENSIÓN
━━━━━━━━━━━━━━━━━━━━━━━━
🔺 Zona: PEAK (Cúspide de Bollinger)
🔹 EMA 7: 1.08600 (CRÍTICA - Agotamiento)
🔹 EMA 20: 1.08550 (Momentum)
🔹 EMA 50: 1.08500 (Tendencia)
🔹 Score: -8/10 (Sobre-extensión alcista extrema)

💡 Estrategia: Mean Reversion - Operar CONTRA la tendencia
```

---

## 💾 Persistencia en Dataset

Los nuevos campos se guardan en el JSONL para análisis futuro:

```json
{
  "emas": {
    "ema_7": 1.08600,
    "ema_20": 1.08550,
    "ema_30": 1.08520,
    "ema_50": 1.08500,
    "ema_200": 1.08300,
    "trend_score": -8
  },
  "bollinger": {
    "bb_upper": 1.08750,
    "bb_lower": 1.08450,
    "exhaustion_type": "PEAK",
    "signal_strength": "HIGH",
    "is_counter_trend": false
  }
}
```

**Utilidad para Machine Learning:**
- Filtrar señales de alta calidad (`signal_strength == "HIGH"`)
- Analizar tasas de éxito por zona de agotamiento y score de sobre-extensión
- Entrenar modelos con features de Mean Reversion (distancia precio-EMA7, separación EMAs)
- Validar umbral de sobre-extensión óptimo (actualmente 0.15% para Forex)

---

## ⚠️ Casos Especiales

### Mercado Lateral (Rango)

**Definición:** EMA 20 y EMA 50 están muy cercanas (separación < 0.08%).

**Acción:** Degradar señales HIGH → MEDIUM.

**Justificación:** En Mean Reversion necesitamos tendencia clara para revertir. En laterales, los rebotes son impredecibles.

---

### Validación de Sobre-Extensión

**Umbral actual:** 0.15% de desviación precio-EMA7 para Forex.

**Ejemplo:**
```
Precio: 1.08750
EMA 7:  1.08600
Desviación: |1.08750 - 1.08600| / 1.08600 = 0.00138 (0.138%)

Si ≥ 0.15%: Score = ±5 pts (sobre-extensión extrema)
Si ≥ 0.08%: Score = ±3 pts (sobre-extensión moderada)
```

---

## 🧪 Testing y Validación

### Comando de Prueba
```bash
python test/test_statistics_with_real_candle.py
```

### Validación Manual Mean Reversion
1. Verificar que EMA 7 se calcula correctamente
2. Confirmar que `trend_score` es NEGATIVO en sobre-extensión alcista
3. Validar que patrones BAJISTAS reciben HIGH en PEAK
4. Validar que patrones ALCISTAS reciben HIGH en BOTTOM

### Logs Esperados
```
🚨 SEÑAL HIGH | SHOOTING_STAR en PEAK | Reversión bajista en agotamiento alcista | Mean Reversion PERFECTA
📊 Sobre-Extensión:
   • EMA 7: 1.08600 (precio +15 pips arriba)
   • Score: -8 (Sobre-extensión alcista extrema)
   • Zona Bollinger: PEAK
```

---

## 📚 Referencias Técnicas

- **Función de Cálculo:** `calculate_bollinger_bands()` en `src/logic/analysis_service.py`
- **Función de Detección:** `detect_exhaustion()` en `src/logic/analysis_service.py`
- **Lógica de Clasificación:** `_analyze_last_closed_candle()` en `src/logic/analysis_service.py`
- **Configuración:** `Config.CANDLE.BB_PERIOD` y `Config.CANDLE.BB_STD_DEV` en `config.py`

---

## 🎯 Próximos Pasos (Roadmap)

1. **Backtesting:** Analizar tasas de éxito históricas por `signal_strength`
2. **Machine Learning:** Entrenar modelo predictivo usando `exhaustion_type` como feature
3. **Optimización de Parámetros:** Ajustar `BB_STD_DEV` según volatilidad del instrumento
4. **Alertas Inteligentes:** Solo notificar señales con `signal_strength == "HIGH"`
