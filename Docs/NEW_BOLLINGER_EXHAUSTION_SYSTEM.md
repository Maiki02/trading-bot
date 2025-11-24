# Sistema de Scoring Matricial - Bollinger & Candle Exhaustion

## Descripción General
Sistema de puntuación y clasificación de señales basado en la combinación de:
1. **Bollinger Exhaustion**: Precio toca/rompe bandas de Bollinger
2. **Candle Exhaustion**: Vela actual rompe high/low de vela anterior
3. **Patrón de Vela**: Shooting Star, Hanging Man, Hammer, Inverted Hammer
4. **Tendencia**: 5 estados (STRONG_BULLISH, WEAK_BULLISH, NEUTRAL, WEAK_BEARISH, STRONG_BEARISH)

**Fecha de Implementación:** 24 de Noviembre de 2025  
**Versión:** v4.0 - Sistema Matricial Completo

---

## Componentes del Sistema

### 1. Bollinger Exhaustion (Zona de Agotamiento)

#### Configuración
```python
BB_PERIOD = 20  # SMA, NO EMA
BB_STD_DEV = 2.0  # Desviaciones estándar
```

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
Tendencia: STRONG_BULLISH ✅
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
Tendencia: WEAK_BULLISH ✅
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
Tendencia: STRONG_BEARISH ✅
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
Tendencia: WEAK_BEARISH ✅
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
Cuando la tendencia es **NEUTRAL**, todas las señales se **degradan un nivel**:

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
# Caso: Shooting Star + Ambos Exhaustion + Tendencia NEUTRAL
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

### Tendencia BAJISTA (STRONG/WEAK_BEARISH)

| Patrón | Bollinger | Candle | Score | Dir. |
|--------|-----------|--------|-------|------|
| Hammer | ✅ BOTTOM | ✅ SÍ | VERY_HIGH | 🟢 COMPRA |
| Hammer | ✅ BOTTOM | ❌ NO | HIGH | 🟢 COMPRA |
| Hammer | ❌ NONE | ✅ SÍ | LOW | 🟢 COMPRA |
| Hammer | ❌ NONE | ❌ NO | VERY_LOW | 🟢 COMPRA |
| Hanging Man | ✅ BOTTOM | ✅ SÍ | MEDIUM | 🟢 COMPRA |
| Hanging Man | ✅ BOTTOM | ❌ NO | LOW | 🟢 COMPRA |
| Hanging Man | ❌ NONE | ✅ SÍ | VERY_LOW | 🟢 COMPRA |
| Hanging Man | ❌ NONE | ❌ NO | NONE | ❌ Descartado |
| **Shooting Star** | - | - | **NONE** | ❌ Contra-estrategia |
| **Inverted Hammer** | - | - | **NONE** | ❌ No aplicable |

---

## Ejemplos Prácticos Completos

### Ejemplo 1: VERY_HIGH en Tendencia Alcista 🔥

**Contexto:**
```
Símbolo: EUR/USD
Timeframe: 1 minuto
Tendencia: STRONG_BULLISH (Score: +10)
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
Tendencia: WEAK_BEARISH (Score: -3)
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
Tendencia: STRONG_BULLISH (Score: +10)
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
🔹 Score: +10/10
━━━━━━━━━━━━━━━━━━━━━━
```

---

## Implementación Técnica

### Archivos Modificados
```
src/logic/analysis_service.py
├── _analyze_last_closed_candle()  ← Matriz de decisión
└── PatternSignal                   ← Incluye candle_exhaustion

src/logic/candle.py
└── detect_candle_exhaustion()      ← Nueva función

src/services/telegram_service.py
└── _format_standard_message()      ← Actualizado para 6 niveles
```

### Pseudocódigo Simplificado
```python
# 1. Detectar patrón
pattern = detect_pattern(candle)

# 2. Analizar tendencia
trend = analyze_trend(close, emas)  # 5 estados

# 3. Bollinger Exhaustion
bollinger_exh = detect_exhaustion(candle, bb_upper, bb_lower)

# 4. Candle Exhaustion
candle_exh = detect_candle_exhaustion(pattern, current, prev)

# 5. Aplicar matriz de decisión
if trend in ["STRONG_BULLISH", "WEAK_BULLISH"]:
    if pattern == "SHOOTING_STAR":
        if bollinger_exh and candle_exh:
            return "VERY_HIGH"
        elif bollinger_exh:
            return "HIGH"
        # ... etc
    elif pattern == "HAMMER":
        return "NONE"  # Contra-estrategia

# 6. Degradar si NEUTRAL
if trend == "NEUTRAL":
    score = downgrade(score)

# 7. Emitir señal
emit_signal(pattern, score, trend)
```

---

## Testing y Validación

### Casos de Prueba Críticos

```python
def test_very_high_bullish_trend():
    """VERY_HIGH: Shooting Star + Ambos Exhaustion en STRONG_BULLISH"""
    signal = analyze(
        pattern="SHOOTING_STAR",
        trend="STRONG_BULLISH",
        bollinger_exhaustion="PEAK",
        candle_exhaustion=True
    )
    assert signal.strength == "VERY_HIGH"
    assert signal.direction == "PUT"

def test_none_counter_trend():
    """NONE: Hammer en tendencia alcista"""
    signal = analyze(
        pattern="HAMMER",
        trend="STRONG_BULLISH",
        bollinger_exhaustion="PEAK",
        candle_exhaustion=True
    )
    assert signal.strength == "NONE"

def test_downgrade_neutral():
    """Degradación por tendencia NEUTRAL"""
    signal = analyze(
        pattern="SHOOTING_STAR",
        trend="NEUTRAL",
        bollinger_exhaustion="PEAK",
        candle_exhaustion=True
    )
    # Normalmente sería VERY_HIGH, pero se degrada a HIGH
    assert signal.strength == "HIGH"
```

---

## Estadísticas y Probabilidad

El sistema se integra con `StatisticsService` para calcular probabilidades históricas:

```python
statistics = {
    'exact': {  # Mismo patrón + score + exhaustion_type
        'total_cases': 45,
        'verde_pct': 0.73,
        'roja_pct': 0.27
    },
    'by_score': {  # Mismo patrón + score (tolerance ±2)
        'total_cases': 120,
        'verde_pct': 0.68,
        'roja_pct': 0.32
    }
}
```

---

## Changelog

### v4.0 (24/Nov/2025) - Sistema Matricial Completo
- ✅ Agregado **Candle Exhaustion**
- ✅ 6 niveles de señal (VERY_HIGH/HIGH/MEDIUM/LOW/VERY_LOW/NONE)
- ✅ Matriz de decisión completa (todas las combinaciones)
- ✅ Degradación automática en tendencia NEUTRAL
- ✅ Bollinger usa SMA 20 (no EMA)

### v3.1 (23/Nov/2025) - Sistema Anterior
- Solo Bollinger Exhaustion
- 4 niveles de señal (HIGH/MEDIUM/LOW/NONE)
- Sin Candle Exhaustion

---

**Fecha de Actualización:** 24 de Noviembre de 2025  
**Autor:** Senior Python Developer - Trading Bot Team  
**Versión:** v4.0
