# Sistema de Clasificación de Fuerza por Agotamiento de Volatilidad (Bollinger Bands)

## 📋 Overview

Sistema implementado en **v0.0.3** para clasificar la fuerza de las señales de patrones de velas japonesas basándose en **zonas de agotamiento de tendencia** determinadas por las Bandas de Bollinger.

**Filosofía:** No todos los patrones tienen la misma probabilidad de éxito. Los patrones detectados en zonas de agotamiento (Cúspide o Base de Bollinger) tienen mayor fidelidad que los detectados en zona neutra.

---

## 🎯 Conceptos Clave

### 1. Bandas de Bollinger (Configuración)

**Parámetros:**
- **Periodo:** 20 velas (1 minuto cada una)
- **Desviación Estándar:** 2.5σ (agresivo para capturar agotamiento real)
- **Línea Central:** SMA(20)

**Fórmula:**
```
BB_Middle = SMA(Close, 20)
BB_Upper = BB_Middle + (2.5 × σ)
BB_Lower = BB_Middle - (2.5 × σ)
```

**Justificación de 2.5σ:** La desviación estándar de 2.5 (en lugar de la clásica 2.0) se usa para asegurar que solo se marquen como "agotamiento" los movimientos extremos reales, reduciendo falsos positivos.

---

### 2. Zonas de Agotamiento

#### 🔺 PEAK (Cúspide - Agotamiento Alcista)
**Definición:** La vela toca o supera la banda superior.

**Condición:**
```python
candle.high >= bb_upper OR candle.close >= bb_upper
```

**Interpretación:** El precio ha alcanzado un nivel de sobrecompra extremo. Alta probabilidad de reversión bajista.

---

#### 🔻 BOTTOM (Base - Agotamiento Bajista)
**Definición:** La vela toca o perfora la banda inferior.

**Condición:**
```python
candle.low <= bb_lower OR candle.close <= bb_lower
```

**Interpretación:** El precio ha alcanzado un nivel de sobreventa extremo. Alta probabilidad de reversión alcista.

---

#### ➖ NONE (Zona Neutra)
**Definición:** La vela está entre las bandas.

**Condición:**
```python
bb_lower < candle.close < bb_upper
```

**Interpretación:** No hay agotamiento claro. El patrón tiene menor probabilidad de éxito.

---

## 📊 Matriz de Clasificación de Fuerza

### 🟢 CONTEXTO: TENDENCIA ALCISTA (Bullish)

| Patrón | Zona | Signal Strength | Emoji | Interpretación |
|--------|------|-----------------|-------|----------------|
| **SHOOTING_STAR** | **PEAK** | **HIGH** | 🚨🚨 | **ALERTA FUERTE** - Agotamiento alcista confirmado |
| SHOOTING_STAR | NONE | LOW | ℹ️ | Informativo - Sin agotamiento |
| **INVERTED_HAMMER** | PEAK | MEDIUM | ⚠️ | **AVISO** - Posible debilitamiento |
| INVERTED_HAMMER | NONE | LOW | ℹ️ | Informativo - Sin agotamiento |
| HAMMER | PEAK | LOW | ℹ️ | Contra-tendencia (no operar) |
| HANGING_MAN | PEAK | LOW | ℹ️ | Contra-tendencia (no operar) |

---

### 🔴 CONTEXTO: TENDENCIA BAJISTA (Bearish)

| Patrón | Zona | Signal Strength | Emoji | Interpretación |
|--------|------|-----------------|-------|----------------|
| **HAMMER** | **BOTTOM** | **HIGH** | 🚨🚨 | **ALERTA FUERTE** - Agotamiento bajista confirmado |
| HAMMER | NONE | LOW | ℹ️ | Informativo - Sin agotamiento |
| **HANGING_MAN** | BOTTOM | MEDIUM | ⚠️ | **AVISO** - Posible debilitamiento |
| HANGING_MAN | NONE | LOW | ℹ️ | Informativo - Sin agotamiento |
| SHOOTING_STAR | BOTTOM | LOW | ℹ️ | Contra-tendencia (no operar) |
| INVERTED_HAMMER | BOTTOM | LOW | ℹ️ | Contra-tendencia (no operar) |

---

## 🔍 Lógica de Detección (Pseudocódigo)

```python
# 1. Determinar tendencia actual
trend = analyze_trend(close, emas)  # "STRONG_BULLISH", "WEAK_BULLISH", etc.

# 2. Calcular Bandas de Bollinger
bb_upper, bb_lower = calculate_bollinger_bands(df['close'], period=20, std_dev=2.5)

# 3. Detectar zona de agotamiento
exhaustion_type = detect_exhaustion(candle.high, candle.low, candle.close, bb_upper, bb_lower)

# 4. Clasificar fuerza según matriz
if trend == "BULLISH":
    if pattern == "SHOOTING_STAR":
        if exhaustion_type == "PEAK":
            signal_strength = "HIGH"  # 🚨 ALERTA FUERTE
        else:
            signal_strength = "LOW"   # ℹ️ Informativo
    elif pattern == "INVERTED_HAMMER":
        if exhaustion_type == "PEAK":
            signal_strength = "MEDIUM"  # ⚠️ AVISO
        else:
            signal_strength = "LOW"
elif trend == "BEARISH":
    if pattern == "HAMMER":
        if exhaustion_type == "BOTTOM":
            signal_strength = "HIGH"  # 🚨 ALERTA FUERTE
        else:
            signal_strength = "LOW"
    elif pattern == "HANGING_MAN":
        if exhaustion_type == "BOTTOM":
            signal_strength = "MEDIUM"  # ⚠️ AVISO
        else:
            signal_strength = "LOW"
```

---

## 📈 Impacto en Notificaciones

### Mensaje de Telegram

Las notificaciones ahora incluyen:

```
🚨 ALERTA FUERTE | BTCUSDT
Agotamiento ALCISTA confirmado (Cúspide)

━━━━━━━━━━━━━━━━━━━━━━━━
📊 INFO DE VELA
━━━━━━━━━━━━━━━━━━━━━━━━
🔹 Patrón: SHOOTING_STAR
🔹 Confianza Técnica: 85%
🔹 Fuerza de Señal: HIGH

━━━━━━━━━━━━━━━━━━━━━━━━
📉 BOLLINGER BANDS
━━━━━━━━━━━━━━━━━━━━━━━━
🔺 Zona: Cúspide de Bollinger
🔹 Banda Superior: 35500.50
🔹 Banda Inferior: 35200.80
```

---

## 💾 Persistencia en Dataset

Los nuevos campos se guardan en el JSONL para análisis futuro:

```json
{
  "bollinger": {
    "bb_upper": 35500.5,
    "bb_lower": 35200.8,
    "exhaustion_type": "PEAK",
    "signal_strength": "HIGH",
    "is_counter_trend": false
  }
}
```

**Utilidad para Machine Learning:**
- Filtrar señales de alta calidad (`signal_strength == "HIGH"`)
- Analizar tasas de éxito por zona de agotamiento
- Entrenar modelos con features adicionales (distancia a bandas, volatilidad implícita)

---

## ⚠️ Casos Especiales

### Patrones Contra-Tendencia

**Definición:** Un patrón alcista en tendencia alcista, o bajista en tendencia bajista.

**Ejemplo:**
- **Hammer** detectado en tendencia **BULLISH** → `is_counter_trend = True`
- **Shooting Star** detectado en tendencia **BEARISH** → `is_counter_trend = True`

**Clasificación:** Siempre `signal_strength = "LOW"` (no operar).

**Justificación:** Los patrones de reversión solo funcionan cuando hay una tendencia que revertir. Un Hammer en tendencia alcista no tiene sentido operativo.

---

## 🧪 Testing y Validación

### Comando de Prueba
```bash
python test/test_statistics_with_real_candle.py
```

### Validación Manual
1. Verificar que `bb_upper` y `bb_lower` se calculan correctamente
2. Confirmar que `exhaustion_type` se asigna según lógica de umbrales
3. Validar que `signal_strength` coincide con la matriz de clasificación

### Logs Esperados
```
🚨 ALERTA FUERTE | SHOOTING_STAR en CÚSPIDE | Agotamiento alcista confirmado | Strength: HIGH
📊 Bollinger Bands:
   • Superior: 35500.50
   • Inferior: 35200.80
   • Zona de Agotamiento: PEAK
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
