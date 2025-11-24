# Sistema de Análisis de Tendencia - 5 Estados (Fanning)

## Descripción General
Sistema de clasificación de tendencia basado en **Fanning** (alineación de EMAs) optimizado para operaciones en velas de 1 minuto (M1) en opciones binarias.

**Fecha de Implementación:** 24 de Noviembre de 2025  
**Versión:** v4.0 - Refactorización completa

---

## Indicadores Utilizados

### EMAs Principales
| EMA | Periodo | Uso Principal |
|-----|---------|---------------|
| **EMA 7** | 7 velas | Señales inmediatas y detección de sobre-extensión |
| **EMA 10** | 10 velas | Confirmación de momentum ultra corto plazo |
| **EMA 20** | 20 velas | Confirmación de momentum corto plazo |
| **EMA 30** | 30 velas | Contexto de tendencia mediano plazo |
| **EMA 50** | 50 velas | Validación de tendencia establecida (evita laterales) |

### ❌ Indicadores Eliminados
- **EMA 100**: Removida (lag excesivo)
- **EMA 200**: Removida (lag excesivo)

### Bollinger Bands
- **Periodo**: 20 (usa **SMA**, NO EMA)
- **Desviaciones Estándar**: 2.0
- **Uso**: Detección de zonas de agotamiento (Cúspide/Piso)

---

## Los 5 Estados de Tendencia

### 1. STRONG_BULLISH (Alcista Fuerte) - Score: +10
**Condición:**
```
Precio > EMA7 > EMA20 > EMA50
```
**Características:**
- ✅ Alineación alcista perfecta (Fanning)
- ✅ `is_aligned = True`
- 🎯 **Estrategia:** Buscar patrones BAJISTAS (Shooting Star) para reversión

**Ejemplo Visual:**
```
Precio: 1.10500 ───┐
EMA7:   1.10400 ───┤ Alineación perfecta
EMA20:  1.10300 ───┤
EMA50:  1.10100 ───┘
```

---

### 2. WEAK_BULLISH (Alcista Débil) - Score: +2 a +5
**Condiciones:**
```
Precio > EMA50 
PERO sin alineación perfecta de EMAs
```

**Subcasos:**
| Condición | Score | Descripción |
|-----------|-------|-------------|
| Precio > EMA7 > EMA20 | +5 | Orden parcial alcista |
| Precio > EMA20 | +3 | Solo encima de EMA20 |
| Precio entre EMA50 y EMAs rápidas | +2 | Zona confusa |

**Características:**
- ❌ `is_aligned = False`
- 🎯 **Estrategia:** Señales de reversión con menor confianza

---

### 3. NEUTRAL - Score: 0
**Condiciones:**
```
abs(Precio - EMA50) / EMA50 < 0.001 (±0.1%)
O EMAs planas/entrelazadas
```

**Características:**
- ❌ `is_aligned = False`
- ⚠️ **Estrategia:** Todas las señales se **degradan un nivel**

**Ejemplo:**
```
Precio: 1.10000
EMA50:  1.09990  → Diferencia: 0.09% ≈ NEUTRAL
```

---

### 4. WEAK_BEARISH (Bajista Débil) - Score: -2 a -5
**Condiciones:**
```
Precio < EMA50
PERO sin alineación perfecta de EMAs
```

**Subcasos:**
| Condición | Score | Descripción |
|-----------|-------|-------------|
| Precio < EMA7 < EMA20 | -5 | Orden parcial bajista |
| Precio < EMA20 | -3 | Solo debajo de EMA20 |
| Precio entre EMA50 y EMAs rápidas | -2 | Zona confusa |

**Características:**
- ❌ `is_aligned = False`
- 🎯 **Estrategia:** Señales de reversión con menor confianza

---

### 5. STRONG_BEARISH (Bajista Fuerte) - Score: -10
**Condición:**
```
Precio < EMA7 < EMA20 < EMA50
```
**Características:**
- ✅ Alineación bajista perfecta (Fanning)
- ✅ `is_aligned = True`
- 🎯 **Estrategia:** Buscar patrones ALCISTAS (Hammer) para reversión

**Ejemplo Visual:**
```
EMA50:  1.10100 ───┐
EMA20:  1.10300 ───┤ Alineación perfecta
EMA7:   1.10400 ───┤
Precio: 1.10500 ───┘
```

---

## Flujo de Decisión (Diagrama)

```
┌─────────────────────────────────────────────┐
│         ANÁLISIS DE TENDENCIA               │
└─────────────────────────────────────────────┘
                    │
                    ▼
       ┌────────────────────────────┐
       │ Comparar Precio vs EMA50   │
       └────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
    Precio > EMA50          Precio < EMA50
        │                       │
        ▼                       ▼
 ┌──────────────┐        ┌──────────────┐
 │ Verificar    │        │ Verificar    │
 │ Alineación   │        │ Alineación   │
 │ Alcista      │        │ Bajista      │
 └──────────────┘        └──────────────┘
        │                       │
   ┌────┴────┐            ┌────┴────┐
   │         │            │         │
 Perfect  Partial      Perfect  Partial
   │         │            │         │
   ▼         ▼            ▼         ▼
STRONG    WEAK        STRONG    WEAK
BULLISH   BULLISH     BEARISH   BEARISH
 (+10)    (+2/+5)     (-10)     (-2/-5)
```

---

## Uso en Estrategia Mean Reversion

### Tabla de Decisión

| Tendencia | Buscar Patrón | Dirección Operación | Confianza |
|-----------|---------------|---------------------|-----------|
| **STRONG_BULLISH** | Shooting Star | 🔴 VENTA (PUT) | Alta |
| **WEAK_BULLISH** | Shooting Star | 🔴 VENTA (PUT) | Baja |
| **NEUTRAL** | Cualquiera | ⚠️ Degradar señal | Mínima |
| **WEAK_BEARISH** | Hammer | 🟢 COMPRA (CALL) | Baja |
| **STRONG_BEARISH** | Hammer | 🟢 COMPRA (CALL) | Alta |

### Filosofía
> "Operar **contra la tendencia dominante** cuando hay señales de agotamiento"

- En tendencia **alcista**: Buscar reversiones **bajistas** (Shooting Star)
- En tendencia **bajista**: Buscar reversiones **alcistas** (Hammer)

---

## Ejemplos Prácticos

### Ejemplo 1: STRONG_BULLISH ✅
```python
Precio: 1.10500
EMA7:   1.10400
EMA20:  1.10300
EMA50:  1.10100
```
**Resultado:**
- ✅ Condición: `1.10500 > 1.10400 > 1.10300 > 1.10100`
- ✅ Score: **+10**
- ✅ `is_aligned = True`
- 🎯 **Acción:** Buscar Shooting Star en Bollinger PEAK

---

### Ejemplo 2: WEAK_BEARISH ⚠️
```python
Precio: 1.09900
EMA7:   1.10000  ← Mayor que Precio (✓)
EMA20:  1.09950  ← Menor que EMA7 (✗ Desorden)
EMA50:  1.10100
```
**Resultado:**
- ❌ No hay alineación perfecta
- ⚠️ Score: **-3** (Precio < EMA20)
- ❌ `is_aligned = False`
- 🎯 **Acción:** Buscar Hammer, pero con BAJA confianza

---

### Ejemplo 3: NEUTRAL 🔄
```python
Precio: 1.10000
EMA50:  1.09990
```
**Cálculo:**
```
Diferencia% = abs(1.10000 - 1.09990) / 1.09990
            = 0.00009 = 0.009% < 0.1%
```
**Resultado:**
- ⚖️ Zona neutral detectada
- Score: **0**
- ❌ `is_aligned = False`
- 🎯 **Acción:** Degradar todas las señales un nivel

---

## Migración desde Sistema Anterior

### Tabla Comparativa

| Indicador | Sistema Anterior | Sistema Nuevo | Estado |
|-----------|------------------|---------------|--------|
| EMA 200 | ✅ Usada (scoring) | ❌ Eliminada | Removida |
| EMA 100 | ✅ Usada (scoring) | ❌ Eliminada | Removida |
| EMA 7 | ✅ Detección exhaustion | ✅ Señales inmediatas | Mantenida |
| EMA 10 | ❌ No existía | ✅ **NUEVA** | Agregada |
| EMA 20 | ✅ Momentum | ✅ Momentum | Mantenida |
| EMA 30 | ✅ Contexto | ✅ Contexto | Mantenida |
| EMA 50 | ✅ Validación | ✅ Validación | Mantenida |

### Cambios en Lógica
| Aspecto | Antes | Ahora |
|---------|-------|-------|
| **Método** | Desviación % de EMAs | Fanning (alineación) |
| **Estados** | 2 (alcista/bajista) | **5 estados graduales** |
| **Scoring** | ±9 puntos máximo | **±10 puntos máximo** |
| **Lag** | Alto (EMA 200) | **Bajo (sin EMAs lentas)** |
| **Precisión M1** | Baja | **Alta** |

---

## Beneficios del Nuevo Sistema

### 1. 🚀 Menor Lag
- Eliminación de EMAs lentas (100, 200)
- Respuesta más rápida a cambios de precio

### 2. 🎯 Mayor Precisión en M1
- EMAs ajustadas a temporalidad de 1 minuto
- Scoring graduado (5 niveles vs 2 anteriores)

### 3. 🔍 Fanning Claro
- Alineación visual evidente
- Más fácil de validar manualmente

### 4. 📊 Granularidad
- **5 estados** vs 2 anteriores
- Distinción entre STRONG y WEAK

---

## Implementación Técnica

### Archivos Modificados
```
src/logic/analysis_service.py
├── analyze_trend()         ← Función principal REFACTORIZADA
├── _update_indicators()    ← Cálculo de EMAs actualizado
└── PatternSignal           ← Dataclass actualizada (sin ema_200)
```

### Función Principal
```python
def analyze_trend(close: float, emas: Dict[str, float]) -> TrendAnalysis:
    """
    Analiza tendencia basándose en Fanning (alineación) de EMAs.
    
    Returns:
        TrendAnalysis con:
        - status: "STRONG_BULLISH", "WEAK_BULLISH", "NEUTRAL", 
                  "WEAK_BEARISH", "STRONG_BEARISH"
        - score: -10 a +10
        - is_aligned: True si EMAs están en Fanning perfecto
    """
```

### Dataclass
```python
@dataclass
class TrendAnalysis:
    status: str       # 5 estados posibles
    score: int        # -10 a +10
    is_aligned: bool  # Fanning perfecto: Sí/No
```

---

## Testing y Validación

### Casos de Prueba
```python
# Caso 1: STRONG_BULLISH
assert analyze_trend(1.105, {
    'ema_7': 1.104, 'ema_20': 1.103, 'ema_50': 1.101
}).status == "STRONG_BULLISH"

# Caso 2: NEUTRAL
assert analyze_trend(1.100, {
    'ema_7': 1.099, 'ema_20': 1.101, 'ema_50': 1.0999
}).status == "NEUTRAL"

# Caso 3: WEAK_BEARISH
assert analyze_trend(1.099, {
    'ema_7': 1.100, 'ema_20': 1.0995, 'ema_50': 1.101
}).status == "WEAK_BEARISH"
```

---

## Integración con Sistema de Scoring

Este sistema de tendencia se combina con:
1. **Bollinger Exhaustion** (PEAK/BOTTOM/NONE)
2. **Candle Exhaustion** (ruptura de high/low anterior)
3. **Matriz de Decisión** (VERY_HIGH/HIGH/MEDIUM/LOW/VERY_LOW/NONE)

Ver: `BOLLINGER_EXHAUSTION_SYSTEM.md` para detalles completos.

---

## Notas Técnicas

### Optimizaciones
- ✅ Sin cálculos de desviación porcentual (más rápido)
- ✅ Solo comparaciones directas (< > ==)
- ✅ Sin loops o iteraciones complejas

### Compatibilidad
- ✅ Compatible con sistema de storage existente
- ✅ Compatible con estadísticas históricas
- ✅ Compatible con Telegram notifications

---

## Changelog

### v4.0 (24/Nov/2025) - Refactorización Completa
- ❌ Eliminadas EMA 100 y EMA 200
- ✅ Agregada EMA 10
- ✅ Nuevo sistema de 5 estados (Fanning)
- ✅ Scoring simplificado (±10 puntos)
- ✅ Bollinger con SMA 20 (no EMA)

### v3.1 (23/Nov/2025) - Sistema Anterior
- Sistema basado en desviación % de EMAs
- Solo 2 estados principales
- Uso de EMA 200 para scoring

---

**Fecha de Actualización:** 24 de Noviembre de 2025  
**Autor:** Senior Python Developer - Trading Bot Team  
**Versión:** v4.0
