# Patrones de Velas Japonesas - Documentación Matemática

## Descripción General

Este documento describe las fórmulas matemáticas y criterios de validación para la detección de 4 patrones de velas japonesas implementados en `src/logic/candle.py`.

Todos los patrones utilizan umbrales configurables definidos en `config.py` mediante la clase `CandleConfig`.

**Persistencia de Datos:** Tras detectar un patrón, el sistema almacena automáticamente la vela trigger y la vela outcome (siguiente) en un dataset JSONL para análisis futuro de probabilidad de éxito mediante Machine Learning. Ver `Docs/dataset.md` para detalles completos.

---

## 1. Métricas Base de la Vela

Para cualquier vela con precios OHLC (Open, High, Low, Close), calculamos:

### Rangos

```
Total Range = High - Low
Body Size = |Close - Open|
Upper Wick = High - max(Open, Close)
Lower Wick = min(Open, Close) - Low
```

### Ratios (Proporciones)

```
Body Ratio = Body Size / Total Range
Upper Wick Ratio = Upper Wick / Total Range
Lower Wick Ratio = Lower Wick / Total Range
```

### Características Direccionales

```
Es Alcista: Close > Open
Es Bajista: Close < Open
```

---

## 2. Patrones de Reversión Bajista

Estos patrones aparecen típicamente en **tendencias alcistas** y sugieren una posible reversión bajista.

### 2.1 Shooting Star (Estrella Fugaz)

**Características:**
- Mecha superior larga (≥60% del rango total)
- Cuerpo pequeño (≤30% del rango total)
- Mecha inferior mínima (≤15% del rango total)
- **DEBE SER VELA ROJA O NEUTRAL** (close <= open) ⚠️ VALIDACIÓN CRÍTICA

**Sistema de Confianza por Niveles (Tiered System):**

```python
# ⚠️ VALIDACIÓN CRÍTICA: DEBE SER VELA ROJA
if close > open_price:
    return False, 0.0  # Rechaza velas verdes

# Cálculo de ratios
upper_wick_ratio = upper_wick / total_range
lower_wick_ratio = lower_wick / total_range  # Mecha contraria
body_ratio = body_size / total_range

# Safety check
if body_size > 0 and (upper_wick / body_size) < 2.0:
    return False, 0.0

# NIVEL SNIPER (100%) - Perfect Entry
if (upper_wick_ratio >= 0.70 and body_ratio <= 0.15 and lower_wick_ratio <= 0.01):
    return True, 1.0

# NIVEL EXCELENTE (90%) - High Probability
elif (upper_wick_ratio >= 0.60 and body_ratio <= 0.20 and lower_wick_ratio <= 0.05):
    return True, 0.9

# NIVEL ESTÁNDAR (80%) - Minimum Acceptable
elif (upper_wick_ratio >= 0.50 and body_ratio <= 0.30 and lower_wick_ratio <= 0.10):
    return True, 0.8

else:
    return False, 0.0
```

**Umbrales por Nivel:**

| Nivel | Mecha Rechazo | Cuerpo Máx | Mecha Contraria | Confianza |
|-------|---------------|------------|-----------------|-----------|
| 🎯 SNIPER | ≥70% | ≤15% | ≤1% | 100% |
| ⭐ EXCELENTE | ≥60% | ≤20% | ≤5% | 90% |
| ✅ ESTÁNDAR | ≥50% | ≤30% | ≤10% | 80% |

**Filosofía:** La mecha contraria es el filtro MÁS IMPORTANTE en opciones binarias de 1 minuto. Para nivel SNIPER, mecha contraria debe ser prácticamente inexistente (<1%).

**Contexto de Uso:**
- Tendencia: Alcista (Close > EMA 200)
- Interpretación: Rechazo de precios altos, posible reversión bajista

---

### 2.2 Hanging Man (Hombre Colgado)

**Características:**
- Mecha inferior larga (≥60% del rango total)
- Cuerpo pequeño (≤30% del rango total)
- Mecha superior mínima (≤15% del rango total)
- **DEBE SER VELA ROJA O NEUTRAL** (close <= open) ⚠️ VALIDACIÓN CRÍTICA

**Sistema de Confianza por Niveles (Tiered System):**

```python
# ⚠️ VALIDACIÓN CRÍTICA: DEBE SER VELA ROJA
if close > open_price:
    return False, 0.0  # Rechaza velas verdes

# Cálculo de ratios
upper_wick_ratio = upper_wick / total_range  # Mecha contraria
lower_wick_ratio = lower_wick / total_range  # Mecha de rechazo
body_ratio = body_size / total_range

# Safety check
if body_size > 0 and (lower_wick / body_size) < 2.0:
    return False, 0.0

# NIVEL SNIPER (100%) - Perfect Entry
if (lower_wick_ratio >= 0.70 and body_ratio <= 0.15 and upper_wick_ratio <= 0.01):
    return True, 1.0

# NIVEL EXCELENTE (90%) - High Probability
elif (lower_wick_ratio >= 0.60 and body_ratio <= 0.20 and upper_wick_ratio <= 0.05):
    return True, 0.9

# NIVEL ESTÁNDAR (80%) - Minimum Acceptable
elif (lower_wick_ratio >= 0.50 and body_ratio <= 0.30 and upper_wick_ratio <= 0.10):
    return True, 0.8

else:
    return False, 0.0
```

**Umbrales por Nivel:**

| Nivel | Mecha Rechazo | Cuerpo Máx | Mecha Contraria | Confianza |
|-------|---------------|------------|-----------------|-----------|
| 🎯 SNIPER | ≥70% | ≤15% | ≤1% | 100% |
| ⭐ EXCELENTE | ≥60% | ≤20% | ≤5% | 90% |
| ✅ ESTÁNDAR | ≥50% | ≤30% | ≤10% | 80% |

**Filosofía:** La mecha contraria es el filtro MÁS IMPORTANTE en opciones binarias de 1 minuto. Para nivel SNIPER, mecha contraria debe ser prácticamente inexistente (<1%).

**Contexto de Uso:**
- Tendencia: Alcista (Close > EMA 200)
- Interpretación: Intento fallido de compra, posible reversión bajista
- **En Tendencia BAJISTA:** Genera ⚠️ AVISO - Posible operación al alza (requiere cautela, no es señal fuerte)

---

## 3. Patrones de Reversión Alcista

Estos patrones aparecen típicamente en **tendencias bajistas** y sugieren una posible reversión alcista.

### 3.1 Inverted Hammer (Martillo Invertido)

**Características:**
- Mecha superior larga (≥60% del rango total)
- Cuerpo pequeño (≤30% del rango total)
- Mecha inferior mínima (≤15% del rango total)
- **DEBE SER VELA VERDE** (close > open) ⚠️ VALIDACIÓN CRÍTICA

**Sistema de Confianza por Niveles (Tiered System):**

```python
# ⚠️ VALIDACIÓN CRÍTICA: DEBE SER VELA VERDE
if close <= open_price:
    return False, 0.0  # Rechaza velas rojas

# Cálculo de ratios
upper_wick_ratio = upper_wick / total_range  # Mecha de rechazo
lower_wick_ratio = lower_wick / total_range  # Mecha contraria
body_ratio = body_size / total_range

# Safety check
if body_size > 0 and (upper_wick / body_size) < 2.0:
    return False, 0.0

# NIVEL SNIPER (100%) - Perfect Entry
if (upper_wick_ratio >= 0.70 and body_ratio <= 0.15 and lower_wick_ratio <= 0.01):
    return True, 1.0

# NIVEL EXCELENTE (90%) - High Probability
elif (upper_wick_ratio >= 0.60 and body_ratio <= 0.20 and lower_wick_ratio <= 0.05):
    return True, 0.9

# NIVEL ESTÁNDAR (80%) - Minimum Acceptable
elif (upper_wick_ratio >= 0.50 and body_ratio <= 0.30 and lower_wick_ratio <= 0.10):
    return True, 0.8

else:
    return False, 0.0
```

**Umbrales por Nivel:**

| Nivel | Mecha Rechazo | Cuerpo Máx | Mecha Contraria | Confianza |
|-------|---------------|------------|-----------------|-----------|
| 🎯 SNIPER | ≥70% | ≤15% | ≤1% | 100% |
| ⭐ EXCELENTE | ≥60% | ≤20% | ≤5% | 90% |
| ✅ ESTÁNDAR | ≥50% | ≤30% | ≤10% | 80% |

**Filosofía:** La mecha contraria es el filtro MÁS IMPORTANTE en opciones binarias de 1 minuto. Para nivel SNIPER, mecha contraria debe ser prácticamente inexistente (<1%).

**Contexto de Uso:**
- Tendencia: Bajista (Close < EMA 200)
- Interpretación: Intento de compra, posible reversión alcista
- **En Tendencia ALCISTA:** Genera ⚠️ AVISO - Posible operación a la baja (requiere cautela, no es señal fuerte)

---

### 3.2 Hammer (Martillo)

**Características:**
- Mecha inferior larga (≥60% del rango total)
- Cuerpo pequeño (≤30% del rango total)
- Mecha superior mínima (≤15% del rango total)
- **DEBE SER VELA VERDE** (close > open) ⚠️ VALIDACIÓN CRÍTICA

**Sistema de Confianza por Niveles (Tiered System):**

```python
# ⚠️ VALIDACIÓN CRÍTICA: DEBE SER VELA VERDE
if close <= open_price:
    return False, 0.0  # Rechaza velas rojas

# Cálculo de ratios
upper_wick_ratio = upper_wick / total_range  # Mecha contraria
lower_wick_ratio = lower_wick / total_range  # Mecha de rechazo
body_ratio = body_size / total_range

# Safety check
if body_size > 0 and (lower_wick / body_size) < 2.0:
    return False, 0.0

# NIVEL SNIPER (100%) - Perfect Entry
if (lower_wick_ratio >= 0.70 and body_ratio <= 0.15 and upper_wick_ratio <= 0.01):
    return True, 1.0

# NIVEL EXCELENTE (90%) - High Probability
elif (lower_wick_ratio >= 0.60 and body_ratio <= 0.20 and upper_wick_ratio <= 0.05):
    return True, 0.9

# NIVEL ESTÁNDAR (80%) - Minimum Acceptable
elif (lower_wick_ratio >= 0.50 and body_ratio <= 0.30 and upper_wick_ratio <= 0.10):
    return True, 0.8

else:
    return False, 0.0
```

**Umbrales por Nivel:**

| Nivel | Mecha Rechazo | Cuerpo Máx | Mecha Contraria | Confianza |
|-------|---------------|------------|-----------------|-----------|
| 🎯 SNIPER | ≥70% | ≤15% | ≤1% | 100% |
| ⭐ EXCELENTE | ≥60% | ≤20% | ≤5% | 90% |
| ✅ ESTÁNDAR | ≥50% | ≤30% | ≤10% | 80% |

**Filosofía:** La mecha contraria es el filtro MÁS IMPORTANTE en opciones binarias de 1 minuto. Para nivel SNIPER, mecha contraria debe ser prácticamente inexistente (<1%).

**Nota:** A diferencia del Hanging Man, el Hammer DEBE ser verde (cierre > apertura). La diferencia es: Hammer (verde) vs Hanging Man (rojo) con misma geometría.

**Contexto de Uso:**
- Tendencia: Bajista (Close < EMA 200)
- Interpretación: Rechazo de precios bajos, posible reversión alcista

---

## 4. Configuración de Umbrales (Sistema Tiered)

Todos los umbrales están centralizados en `config.py`:

```python
@dataclass(frozen=True)
class CandleConfig:
    """Configuración para detección de patrones de velas - Sistema de Niveles."""
    
    # =========================================================================
    # NIVEL SNIPER (100%) - Perfect Entry | Minimal Risk
    # =========================================================================
    SNIPER_REJECTION_WICK: float = 0.70        # Mecha de rechazo >= 70%
    SNIPER_BODY_MAX: float = 0.15              # Cuerpo <= 15%
    SNIPER_OPPOSITE_WICK_MAX: float = 0.01     # ⚠️ Mecha contraria < 1% (CRÍTICO)
    
    # =========================================================================
    # NIVEL EXCELENTE (90%) - High Probability | Low Risk
    # =========================================================================
    EXCELLENT_REJECTION_WICK: float = 0.60     # Mecha de rechazo >= 60%
    EXCELLENT_BODY_MAX: float = 0.20           # Cuerpo <= 20%
    EXCELLENT_OPPOSITE_WICK_MAX: float = 0.05  # ⚠️ Mecha contraria < 5%
    
    # =========================================================================
    # NIVEL ESTÁNDAR (80%) - Minimum Acceptable | Moderate Risk
    # =========================================================================
    STANDARD_REJECTION_WICK: float = 0.50      # Mecha de rechazo >= 50%
    STANDARD_BODY_MAX: float = 0.30            # Cuerpo <= 30%
    STANDARD_OPPOSITE_WICK_MAX: float = 0.10   # ⚠️ Mecha contraria < 10%
    
    # =========================================================================
    # Safety Checks (Transversales)
    # =========================================================================
    WICK_TO_BODY_RATIO: float = 2.0           # Mecha >= 2x cuerpo
```

**⚠️ BREAKING CHANGE:** Se eliminó el sistema de bonos acumulativos. Ahora solo existen 3 niveles de confianza fijos: 100%, 90%, 80%. No hay confianza del 70% ni acumulación de bonos.

**Filosofía del Sistema Tiered:**
- **Mecha contraria < 1% para SNIPER**: En opciones binarias de 1 minuto, la mecha contraria es el enemigo #1. Si existe mecha contraria significativa, indica indecisión del mercado.
- **Minimum 80% threshold**: Se rechaza cualquier vela que no cumpla al menos ESTÁNDAR (80%). Esto reduce drásticamente los falsos positivos.
- **No gradientes**: A diferencia del sistema anterior (70% + bonos), ahora son niveles discretos. Una vela ES o NO ES de cierto nivel.

---

## 5. Sistema de Confianza (Tiered System)

Cada patrón retorna una tupla `(bool, float)`:
- `bool`: Indica si el patrón fue detectado
- `float`: Nivel de confianza discreto: 1.0, 0.9, 0.8, o 0.0

### Niveles de Confianza (Discretos)

```
1.0 (100%) - SNIPER: Perfect Entry | Minimal Risk
0.9 (90%)  - EXCELENTE: High Probability | Low Risk  
0.8 (80%)  - ESTÁNDAR: Minimum Acceptable | Moderate Risk
0.0 (0%)   - NO CUMPLE: Patrón rechazado
```

### Criterios de Evaluación por Nivel

Cada patrón evalúa **3 métricas simultáneamente**:

1. **Mecha de Rechazo**: Debe ser >= umbral (50%/60%/70%)
2. **Cuerpo**: Debe ser <= umbral (30%/20%/15%)
3. **Mecha Contraria**: ⚠️ **CRÍTICO** - Debe ser <= umbral (10%/5%/1%)

**NO hay acumulación de bonos**. Una vela pertenece a UN solo nivel basado en el cumplimiento simultáneo de las 3 métricas.

### Ejemplo de Evaluación (Shooting Star)

```python
# Vela: upper_wick=65%, body=18%, lower_wick=3%

# ¿Es SNIPER? NO (upper_wick < 70%)
# ¿Es EXCELENTE? SÍ (upper_wick >= 60%, body <= 20%, lower_wick <= 5%)
# Resultado: return True, 0.9
```

---

## 6. Filtrado por Tendencia (EMA 200)

La detección de patrones en `AnalysisService` aplica filtrado por tendencia:

### Tendencia Alcista (Close > EMA 200)
- **Busca reversión bajista**: Shooting Star, Hanging Man

### Tendencia Bajista (Close < EMA 200)
- **Busca reversión alcista**: Hammer, Inverted Hammer

### Fórmula de Tendencia

```python
threshold = 0.0001  # Tolerancia para evitar falsos neutrales

if Close < EMA_200 - threshold:
    Trend = "BEARISH"
elif Close > EMA_200 + threshold:
    Trend = "BULLISH"
else:
    Trend = "NEUTRAL"
```

---

## 7. Casos Especiales

### División por Cero
Si `Total Range = 0`, el patrón retorna `(False, 0.0)` inmediatamente.

### Velas Doji
Velas con cuerpo muy pequeño (≈0) pueden cumplir múltiples patrones. El sistema prioriza según la tendencia actual.

### Validación de Color (⚠️ CRÍTICO - Sistema Actualizado)

**Patrones BAJISTAS (Requieren vela ROJA o NEUTRAL):**
- **Shooting Star**: `if close > open: return False, 0.0`
- **Hanging Man**: `if close > open: return False, 0.0`
- **Razón:** Velas verdes indican compras fuertes, contradicen reversión bajista

**Patrones ALCISTAS (Requieren vela VERDE):**
- **Inverted Hammer**: `if close <= open: return False, 0.0`
- **Hammer**: `if close <= open: return False, 0.0`
- **Razón:** En opciones binarias de 1 minuto, el color es señal de fuerza direccional. Martillos deben ser verdes para confirmar intención alcista.

**⚠️ BREAKING CHANGE vs Versión Anterior:**
- **Antes**: Martillos aceptaban cualquier color (verde/roja), con bono para verde
- **Ahora**: Martillos SOLO aceptan velas verdes (validación crítica al inicio de función)
- **Impacto**: Reduce falsos positivos al exigir confirmación de dirección

**Ejemplo de vela RECHAZADA (Hammer):**
```python
# Vela ROJA con mecha inferior larga
apertura = 84752.68
cierre = 84751.56  # ← cierre < apertura (ROJA)
maximo = 84755.31
minimo = 84702.73

# ❌ Aunque tiene geometría de Hammer, SE RECHAZA por ser roja
# Resultado: return False, 0.0
```

# Intento de detección
is_hanging_man(apertura, maximo, minimo, cierre)
# → (False, 0.0) ✅ Correctamente rechazada

# Pero puede ser detectada como Hammer
is_hammer(apertura, maximo, minimo, cierre)
# → (True, 1.0) si cumple criterios matemáticos
```

### Patrones Similares
- **Shooting Star vs Inverted Hammer**: MISMA geometría (mecha superior larga), DIFERENTE color (SS=rojo, IH=verde)
- **Hanging Man vs Hammer**: MISMA geometría (mecha inferior larga), DIFERENTE color (HM=rojo, H=verde)
- **Diferenciación clave:** El COLOR es el que determina si el patrón es bajista o alcista

---

## 8. Referencias

### Archivos Relacionados
- `src/logic/candle.py`: Implementación de funciones de detección
- `config.py`: Configuración de umbrales (CandleConfig)
- `src/logic/analysis_service.py`: Orquestación y filtrado por tendencia

### Literatura Técnica
- Nison, Steve. "Japanese Candlestick Charting Techniques"
- Bulkowski, Thomas. "Encyclopedia of Candlestick Charts"

---

## 9. Ejemplo de Uso

```python
from src.logic.candle import is_shooting_star, is_hammer
from config import Config

# Datos de una vela
open_price = 1.0900
high = 1.0950
low = 1.0890
close = 1.0895

# Detectar Shooting Star
is_pattern, confidence = is_shooting_star(open_price, high, low, close)

if is_pattern:
    print(f"Shooting Star detectado con confianza: {confidence:.2%}")
    # Output: "Shooting Star detectado con confianza: 85%"

# Detectar Hammer
is_pattern, confidence = is_hammer(open_price, high, low, close)

if is_pattern:
    print(f"Hammer detectado con confianza: {confidence:.2%}")
```

---

**Última actualización**: Refactorización MVP v0.0.1  
**Autor**: TradingView Pattern Monitor Team
