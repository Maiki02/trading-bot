# Dataset de Señales para Machine Learning

## Descripción General

El sistema almacena automáticamente cada patrón detectado junto con su resultado en un archivo JSONL para análisis futuro de probabilidad de éxito mediante Machine Learning.

## Propósito

Construir un dataset histórico que permita:
1. **Análisis de probabilidad de éxito** por tipo de patrón, instrumento, score de tendencia y nivel de confianza.
2. **Entrenamiento de modelos predictivos** para mejorar el filtrado de señales.
3. **Backtesting de estrategias** con datos reales históricos.
4. **Optimización de umbrales** basada en resultados observados.

## Arquitectura

### Formato de Almacenamiento

**Archivo:** `data/trading_signals_dataset.jsonl`

**Formato:** JSONL (JSON Lines) - Un registro JSON por línea, optimizado para:
- Append eficiente (no requiere reescribir todo el archivo)
- Procesamiento streaming (lectura línea por línea)
- Compatibilidad con herramientas de análisis (pandas, jq, etc.)

### Flujo de Persistencia

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Sistema detecta patrón (ej: SHOOTING_STAR)              │
│    → Timestamp: 17:10:00                                    │
│    → Almacena en pending_signals                            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Siguiente vela cierra (ej: 17:11:00)                    │
│    → Sistema busca vela outcome en DataFrame                │
│    → Validación: timestamp_gap = 60 segundos                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Construcción del registro completo                      │
│    → trigger_candle: Vela donde se detectó el patrón       │
│    → outcome_candle: Vela siguiente (resultado)            │
│    → outcome: Dirección esperada vs real, éxito, PnL       │
│    → _metadata: Validación temporal, versión                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Persistencia asíncrona                                  │
│    → Sanitización de tipos NumPy → tipos JSON              │
│    → Escritura JSONL con asyncio.to_thread()               │
│    → No bloquea event loop del WebSocket                    │
└─────────────────────────────────────────────────────────────┘
```

## Estructura del Registro

### Campos Principales

```json
{
  "timestamp": "2025-11-22T17:10:00Z",
  "signal": {
    "pattern": "SHOOTING_STAR",
    "source": "FX",
    "symbol": "EURUSD",
    "confidence": 0.85,
    "trend": "STRONG_BULLISH",
    "trend_score": 7,
    "is_trend_aligned": true
  },
  "trigger_candle": {
    "timestamp": 1763831400,
    "open": 1.09050,
    "high": 1.09180,
    "low": 1.09020,
    "close": 1.09040,
    "volume": 120.5
  },
  "outcome_candle": {
    "timestamp": 1763831460,
    "open": 1.09040,
    "high": 1.09060,
    "low": 1.08990,
    "close": 1.09000,
    "volume": 95.3
  },
  "outcome": {
    "expected_direction": "ROJO",
    "actual_direction": "ROJO",
    "success": true,
    "pnl_pips": 40.0,
    "outcome_timestamp": "2025-11-22T17:11:00Z"
  },
  "_metadata": {
    "timestamp_gap_seconds": 60,
    "expected_gap_seconds": 60,
    "has_skipped_candles": false,
    "written_at": "2025-11-22T17:11:01.123456Z",
    "record_id": 42,
    "version": "1.0"
  }
}
```

### Descripción de Campos

#### `signal` - Metadata de la Señal
- **pattern:** Tipo de patrón detectado (`SHOOTING_STAR`, `HANGING_MAN`, `INVERTED_HAMMER`, `HAMMER`)
- **source:** Fuente de datos (`FX`, `OANDA`)
- **symbol:** Instrumento (`EURUSD`, `GBPUSD`, etc.)
- **confidence:** Nivel de confianza del patrón (0.70 - 1.00)
- **trend:** Estado de tendencia (`STRONG_BULLISH`, `WEAK_BULLISH`, `NEUTRAL`, `WEAK_BEARISH`, `STRONG_BEARISH`)
- **trend_score:** Puntuación de tendencia (-10 a +10)
- **is_trend_aligned:** Si las EMAs están perfectamente alineadas

#### `trigger_candle` - Vela de Detección
- **timestamp:** Unix timestamp (segundos desde epoch)
- **open, high, low, close:** Precios OHLC
- **volume:** Volumen negociado en la vela

#### `outcome_candle` - Vela Resultado
- Misma estructura que `trigger_candle`
- Representa la vela siguiente (timestamp + 60 segundos en timeframe M1)

#### `outcome` - Análisis del Resultado
- **expected_direction:** Dirección esperada según el patrón (`ROJO` para bajista, `VERDE` para alcista)
- **actual_direction:** Dirección real de la vela outcome (`ROJO`, `VERDE`, `DOJI`)
- **success:** Boolean indicando si el resultado coincidió con la expectativa
- **pnl_pips:** Ganancia/pérdida en pips (positivo si success=true)
- **outcome_timestamp:** ISO 8601 de la vela outcome

#### `_metadata` - Validación y Tracking
- **timestamp_gap_seconds:** Gap real entre trigger y outcome (debería ser 60)
- **expected_gap_seconds:** Gap esperado (60 para M1)
- **has_skipped_candles:** Flag que indica si hubo velas faltantes (gap != 60)
- **written_at:** Timestamp ISO 8601 de persistencia del registro
- **record_id:** ID secuencial del registro en el archivo
- **version:** Versión del formato de registro (para compatibilidad futura)

## Validación Temporal

### Detección de Velas Salteadas

El sistema valida que la vela outcome sea **exactamente 60 segundos** después de la vela trigger (en timeframe M1).

**Casos válidos:**
```
trigger: 17:10:00 → outcome: 17:11:00 → gap: 60s ✅
```

**Casos inválidos (detectados y marcados):**
```
trigger: 17:10:00 → outcome: 17:12:00 → gap: 120s ⚠️ (vela 17:11 faltante)
trigger: 17:10:00 → outcome: 17:10:30 → gap: 30s ⚠️ (timestamp inconsistente)
```

**Cuando se detecta gap anormal:**
1. Se loguea warning en consola con detalles del gap
2. Campo `has_skipped_candles` se marca como `true`
3. Registro se guarda de todos modos (para análisis posterior)

**Razones de velas faltantes:**
- TradingView no envió la vela (silencio en feed)
- Reconexión del WebSocket durante ese minuto
- Baja liquidez sin trades en ese período

## Sanitización de Tipos

Pandas y NumPy utilizan tipos especiales (`numpy.bool_`, `numpy.int64`, `numpy.float64`) que no son JSON-compatibles.

**Conversión automática:**
```python
numpy.bool_    → bool
numpy.int64    → int
numpy.float64  → float
numpy.ndarray  → list
```

Esta conversión se realiza recursivamente en todo el registro antes de persistir.

## Performance

**Escritura asíncrona:**
- Ejecución: `asyncio.to_thread()` - no bloquea event loop
- Tiempo: ~5-10 ms por registro
- Impacto: Cero en detección de patrones en tiempo real

**Tamaño estimado:**
- ~500-800 bytes por registro (comprimido con espacios mínimos)
- 1000 registros ≈ 600 KB
- 10,000 registros ≈ 6 MB

## Uso Futuro

### Análisis de Probabilidad

**Objetivo:** Determinar probabilidad de éxito por patrón según contexto.

**Variables predictivas:**
- Tipo de patrón
- Instrumento
- Score de tendencia
- Nivel de confianza
- Alineación de EMAs
- Hora del día
- Volumen
- Volatilidad reciente

**Salida esperada:**
```python
pattern = "SHOOTING_STAR"
instrument = "EURUSD"
trend_score = 7
confidence = 0.85

predicted_probability = model.predict({
    "pattern": pattern,
    "trend_score": trend_score,
    "confidence": confidence,
    ...
})
# → 0.72 (72% probabilidad de éxito)
```

### Backtesting

**Objetivo:** Evaluar estrategias con datos históricos reales.

**Ejemplo de análisis:**
```python
import pandas as pd

# Cargar dataset
df = pd.read_json("data/trading_signals_dataset.jsonl", lines=True)

# Filtrar señales de alta probabilidad
high_prob = df[
    (df["signal.confidence"] >= 0.80) &
    (df["signal.trend_score"].abs() >= 6) &
    (df["_metadata.has_skipped_candles"] == False)
]

# Calcular tasa de éxito
success_rate = high_prob["outcome.success"].mean()
avg_pnl = high_prob["outcome.pnl_pips"].mean()

print(f"Success Rate: {success_rate:.2%}")
print(f"Average PnL: {avg_pnl:.1f} pips")
```

### Optimización de Umbrales

**Objetivo:** Ajustar configuración según resultados observados.

**Preguntas a responder:**
- ¿Debería aumentar `SMALL_BODY_RATIO` de 0.30 a 0.25?
- ¿Score ≥6 es buen umbral para STRONG_BULLISH?
- ¿Patrones con confidence <0.80 son rentables?

## Estado Actual

**✅ Implementado:**
- Estructura de datos completa
- Persistencia automática tras cada detección
- Validación temporal de velas
- Sanitización de tipos NumPy
- Metadata enriquecida

**⏳ Pendiente (versiones futuras):**
- Script de análisis de probabilidades
- Entrenamiento de modelos predictivos
- Dashboard de visualización de métricas
- Integración con filtro de señales en tiempo real

---

## Archivos Relacionados

- **Implementación:** `src/services/storage_service.py`
- **State Machine:** `src/logic/analysis_service.py` (función `_close_signal_cycle`)
- **Configuración:** No requiere variables de entorno adicionales
- **Ubicación del dataset:** `data/trading_signals_dataset.jsonl`

## Referencias

- **Formato JSONL:** http://jsonlines.org/
- **Análisis con pandas:** `pd.read_json(path, lines=True)`
- **Procesamiento streaming:** Lectura línea por línea con `open()`

---

**Última actualización:** 22 de noviembre de 2025  
**Versión del formato:** 1.0  
**Autor:** TradingView Pattern Monitor Team
