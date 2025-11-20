# Patrones de Velas Japonesas - Documentación Matemática

## Descripción General

Este documento describe las fórmulas matemáticas y criterios de validación para la detección de 4 patrones de velas japonesas implementados en `src/logic/candle.py`.

Todos los patrones utilizan umbrales configurables definidos en `config.py` mediante la clase `CandleConfig`.

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
- Preferencia por vela bajista

**Fórmulas de Validación:**

```python
upper_wick_ratio ≥ UPPER_WICK_RATIO_MIN (0.60)
body_ratio ≤ SMALL_BODY_RATIO (0.30)
lower_wick_ratio ≤ OPPOSITE_WICK_MAX (0.15)
upper_wick ≥ body * WICK_TO_BODY_RATIO (2.0)
```

**Cálculo de Confianza:**

```
Base Confidence = 0.70

Bonuses:
- Upper Wick Ratio ≥ 0.70: +0.10
- Body Ratio ≤ 0.20: +0.10
- Lower Wick Ratio ≤ 0.10: +0.10

Confidence = min(1.0, Base + Σ Bonuses)
```

**Contexto de Uso:**
- Tendencia: Alcista (Close > EMA 200)
- Interpretación: Rechazo de precios altos, posible reversión bajista

---

### 2.2 Hanging Man (Hombre Colgado)

**Características:**
- Mecha inferior larga (≥60% del rango total)
- Cuerpo pequeño (≤30% del rango total)
- Mecha superior mínima (≤15% del rango total)
- Puede ser alcista o bajista

**Fórmulas de Validación:**

```python
lower_wick_ratio ≥ LOWER_WICK_RATIO_MIN (0.60)
body_ratio ≤ SMALL_BODY_RATIO (0.30)
upper_wick_ratio ≤ OPPOSITE_WICK_MAX (0.15)
lower_wick ≥ body * WICK_TO_BODY_RATIO (2.0)
```

**Cálculo de Confianza:**

```
Base Confidence = 0.70

Bonuses:
- Lower Wick Ratio ≥ 0.70: +0.10
- Body Ratio ≤ 0.20: +0.10
- Upper Wick Ratio ≤ 0.10: +0.10

Confidence = min(1.0, Base + Σ Bonuses)
```

**Contexto de Uso:**
- Tendencia: Alcista (Close > EMA 200)
- Interpretación: Intento fallido de compra, posible reversión bajista

---

## 3. Patrones de Reversión Alcista

Estos patrones aparecen típicamente en **tendencias bajistas** y sugieren una posible reversión alcista.

### 3.1 Inverted Hammer (Martillo Invertido)

**Características:**
- Mecha superior larga (≥60% del rango total)
- Cuerpo pequeño (≤30% del rango total)
- Mecha inferior mínima (≤15% del rango total)
- Preferencia por vela alcista

**Fórmulas de Validación:**

```python
upper_wick_ratio ≥ UPPER_WICK_RATIO_MIN (0.60)
body_ratio ≤ SMALL_BODY_RATIO (0.30)
lower_wick_ratio ≤ OPPOSITE_WICK_MAX (0.15)
upper_wick ≥ body * WICK_TO_BODY_RATIO (2.0)
```

**Cálculo de Confianza:**

```
Base Confidence = 0.70

Bonuses:
- Upper Wick Ratio ≥ 0.70: +0.10
- Body Ratio ≤ 0.20: +0.10
- Lower Wick Ratio ≤ 0.10: +0.10
- Es vela alcista (Close > Open): +0.10

Confidence = min(1.0, Base + Σ Bonuses)
```

**Contexto de Uso:**
- Tendencia: Bajista (Close < EMA 200)
- Interpretación: Intento de compra, posible reversión alcista

---

### 3.2 Hammer (Martillo)

**Características:**
- Mecha inferior larga (≥60% del rango total)
- Cuerpo pequeño (≤30% del rango total)
- Mecha superior mínima (≤15% del rango total)
- Preferencia por vela alcista

**Fórmulas de Validación:**

```python
lower_wick_ratio ≥ LOWER_WICK_RATIO_MIN (0.60)
body_ratio ≤ SMALL_BODY_RATIO (0.30)
upper_wick_ratio ≤ OPPOSITE_WICK_MAX (0.15)
lower_wick ≥ body * WICK_TO_BODY_RATIO (2.0)
```

**Cálculo de Confianza:**

```
Base Confidence = 0.70

Bonuses:
- Lower Wick Ratio ≥ 0.70: +0.10
- Body Ratio ≤ 0.20: +0.10
- Upper Wick Ratio ≤ 0.10: +0.10
- Es vela alcista (Close > Open): +0.10

Confidence = min(1.0, Base + Σ Bonuses)
```

**Contexto de Uso:**
- Tendencia: Bajista (Close < EMA 200)
- Interpretación: Rechazo de precios bajos, posible reversión alcista

---

## 4. Configuración de Umbrales

Todos los umbrales están centralizados en `config.py`:

```python
@dataclass(frozen=True)
class CandleConfig:
    """Configuración para detección de patrones de velas."""
    
    # Ratios de cuerpo
    BODY_RATIO_MIN: float = 0.30          # Cuerpo mínimo para validación
    SMALL_BODY_RATIO: float = 0.30        # Cuerpo pequeño (patrones de reversión)
    
    # Ratios de mechas
    UPPER_WICK_RATIO_MIN: float = 0.60    # Mecha superior mínima
    LOWER_WICK_RATIO_MIN: float = 0.60    # Mecha inferior mínima
    WICK_TO_BODY_RATIO: float = 2.0       # Relación mecha/cuerpo
    OPPOSITE_WICK_MAX: float = 0.15       # Mecha opuesta máxima
    
    # Sistema de confianza
    BASE_CONFIDENCE: float = 0.70          # Confianza base
    BONUS_CONFIDENCE_PER_CONDITION: float = 0.10  # Bonus por condición cumplida
```

---

## 5. Sistema de Confianza

Cada patrón retorna una tupla `(bool, float)`:
- `bool`: Indica si el patrón fue detectado
- `float`: Nivel de confianza entre 0.0 y 1.0

### Niveles de Confianza

```
0.70 - 0.79: Patrón detectado (criterios básicos)
0.80 - 0.89: Alta confianza (1-2 bonuses)
0.90 - 1.00: Muy alta confianza (3+ bonuses)
```

### Condiciones de Bonus

Cada patrón evalúa condiciones adicionales que otorgan +0.10 de confianza:

1. **Ratios excepcionales**: Mechas muy largas (≥70%) o cuerpos muy pequeños (≤20%)
2. **Mecha opuesta mínima**: Mecha contraria casi inexistente (≤10%)
3. **Color apropiado**: Vela con dirección favorable al patrón

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
Si `Total Range = 0` o `Body Size = 0`, el patrón retorna `(False, 0.0)`.

### Velas Doji
Velas con cuerpo muy pequeño (≈0) pueden detectarse como múltiples patrones. El sistema prioriza según la tendencia actual.

### Patrones Similares
- **Shooting Star vs Inverted Hammer**: Mismas métricas, diferente contexto de tendencia
- **Hanging Man vs Hammer**: Mismas métricas, el Hammer prefiere velas alcistas

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
