# Sistema de Mean Reversion con Agotamiento de Volatilidad (Bollinger Bands)

## 📋 Overview

Sistema refactorizado en **v0.0.5** para operar **CONTRA-TENDENCIA** (Mean Reversion) en zonas de agotamiento extremo determinadas por las Bandas de Bollinger.

**🔄 CAMBIO CRÍTICO:** La estrategia cambió de "Trend Following" a "Mean Reversion / Contratendencia".

**Nueva Filosofía:** Operar CONTRA la tendencia cuando se detecta agotamiento extremo (Cúspide o Base de Bollinger) combinado con patrones de reversión. El objetivo es capturar el rebote/retroceso inmediato tras sobre-extensión del precio.

---

## 🎯 Conceptos Clave

### 1. Bandas de Bollinger (Configuración)

**Parámetros:**
- **Periodo:** 20 velas (1 minuto cada una)
- **Desviación Estándar:** 2.0σ (estándar para detección de agotamiento)
- **Línea Central:** SMA(20)

**Fórmula:**
```
BB_Middle = SMA(Close, 20)
BB_Upper = BB_Middle + (2.0 × σ)
BB_Lower = BB_Middle - (2.0 × σ)
```

**Justificación de 2.0σ:** La desviación estándar de 2.0 captura aproximadamente el 95% de los movimientos de precio, permitiendo identificar sobre-extensiones reales sin ser demasiado restrictivo.

---

### 2. Zonas de Agotamiento

#### 🔺 PEAK (Cúspide - Sobre-extensión Alcista)
**Definición:** La vela toca o supera la banda superior.

**Condición:**
```python
candle.high >= bb_upper OR candle.close >= bb_upper
```

**Interpretación Mean Reversion:** El precio está sobre-extendido al alza. **Buscar patrones BAJISTAS** (Shooting Star, Hanging Man) para reversión bajista.

---

#### 🔻 BOTTOM (Base - Sobre-extensión Bajista)
**Definición:** La vela toca o perfora la banda inferior.

**Condición:**
```python
candle.low <= bb_lower OR candle.close <= bb_lower
```

**Interpretación Mean Reversion:** El precio está sobre-extendido a la baja. **Buscar patrones ALCISTAS** (Hammer, Inverted Hammer) para reversión alcista.

---

#### ➖ NONE (Zona Neutra)
**Definición:** La vela está entre las bandas.

**Condición:**
```python
bb_lower < candle.close < bb_upper
```

**Interpretación:** No hay sobre-extensión clara. La probabilidad de reversión es menor.

---

## 📊 Matriz de Clasificación de Fuerza (Mean Reversion)

### 🔥 SEÑALES HIGH (Máxima Prioridad)

| Patrón | Zona | Signal Strength | Interpretación |
|--------|------|-----------------|----------------|
| **SHOOTING_STAR** | **PEAK** | **HIGH** 🚨 | **Reversión bajista en sobre-extensión alcista** - IDEAL para Mean Reversion |
| **HANGING_MAN** | **PEAK** | **HIGH** 🚨 | **Reversión bajista en sobre-extensión alcista** - IDEAL para Mean Reversion |
| **HAMMER** | **BOTTOM** | **HIGH** 🚨 | **Reversión alcista en sobre-extensión bajista** - IDEAL para Mean Reversion |
| **INVERTED_HAMMER** | **BOTTOM** | **HIGH** 🚨 | **Reversión alcista en sobre-extensión bajista** - IDEAL para Mean Reversion |

**Criterio:** Patrón de reversión detectado en zona de agotamiento extremo. Mayor probabilidad de éxito.

---

### ⚠️ SEÑALES MEDIUM (Precaución)

| Patrón | Zona | Signal Strength | Interpretación |
|--------|------|-----------------|----------------|
| SHOOTING_STAR | NONE | MEDIUM ⚠️ | Reversión bajista posible pero sin agotamiento confirmado |
| HANGING_MAN | NONE | MEDIUM ⚠️ | Reversión bajista posible pero sin agotamiento confirmado |
| HAMMER | NONE | MEDIUM ⚠️ | Reversión alcista posible pero sin agotamiento confirmado |
| INVERTED_HAMMER | NONE | MEDIUM ⚠️ | Reversión alcista posible pero sin agotamiento confirmado |

**Criterio:** Patrón válido pero sin confirmación de sobre-extensión. Esperar confirmación adicional.

---

### ℹ️ SEÑALES LOW (No Operar)

| Patrón | Zona | Signal Strength | Interpretación |
|--------|------|-----------------|----------------|
| SHOOTING_STAR | BOTTOM | LOW ℹ️ | Patrón bajista en agotamiento bajista - Señal débil |
| HANGING_MAN | BOTTOM | LOW ℹ️ | Patrón bajista en agotamiento bajista - Señal débil |
| HAMMER | PEAK | LOW ℹ️ | Patrón alcista en agotamiento alcista - Señal débil |
| INVERTED_HAMMER | PEAK | LOW ℹ️ | Patrón alcista en agotamiento alcista - Señal débil |

**Criterio:** Patrón detectado en zona de agotamiento OPUESTA a su dirección natural. No operar.

---

## 🔍 Lógica de Detección (Mean Reversion)

```python
# 1. Analizar sobre-extensión (Mean Reversion Score)
trend_analysis = analyze_trend(close, emas)  # Ahora mide sobre-extensión, NO tendencia

# 2. Calcular Bandas de Bollinger
bb_upper, bb_lower = calculate_bollinger_bands(df['close'], period=20, std_dev=2.0)

# 3. Detectar zona de agotamiento
exhaustion_type = detect_exhaustion(candle.high, candle.low, candle.close, bb_upper, bb_lower)

# 4. Clasificar fuerza según estrategia Mean Reversion
pattern_is_bearish = pattern in ["SHOOTING_STAR", "HANGING_MAN"]
pattern_is_bullish = pattern in ["HAMMER", "INVERTED_HAMMER"]

if pattern_is_bearish:
    if exhaustion_type == "PEAK":
        signal_strength = "HIGH"  # 🚨 Reversión bajista en sobre-extensión alcista
    elif exhaustion_type == "NONE":
        signal_strength = "MEDIUM"  # ⚠️ Reversión posible sin agotamiento
    else:  # exhaustion_type == "BOTTOM"
        signal_strength = "LOW"  # ℹ️ Patrón bajista en agotamiento bajista (débil)

elif pattern_is_bullish:
    if exhaustion_type == "BOTTOM":
        signal_strength = "HIGH"  # 🚨 Reversión alcista en sobre-extensión bajista
    elif exhaustion_type == "NONE":
        signal_strength = "MEDIUM"  # ⚠️ Reversión posible sin agotamiento
    else:  # exhaustion_type == "PEAK"
        signal_strength = "LOW"  # ℹ️ Patrón alcista en agotamiento alcista (débil)

# 5. Validar que hay tendencia clara (no lateral)
if signal_strength == "HIGH" and not trend_analysis.is_aligned:
    signal_strength = "MEDIUM"  # Degradar si el mercado está lateral
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
