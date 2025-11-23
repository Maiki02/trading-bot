# Dataset Structure V2 - Datos Crudos Optimizados

## 📋 Overview

Esta versión optimiza la estructura del dataset para almacenar **datos crudos** en lugar de datos derivados, facilitando el análisis posterior sin perder información.

## 🎯 Cambios Principales (V1 → V2)

### ❌ Eliminado (Datos Derivados)
- `pnl_pips` - Calculable desde outcome_candle
- `trend_status` - Derivado del trend_score
- `is_trend_aligned` - Reemplazado por `ema_alignment` (string)
- `version: "1.0"` - Duplicado con `algo_version`
- Campos redundantes (`close`, `open` duplicados)

### ✅ Agregado (Datos Crudos)
- `source` (nivel raíz) - Exchange/broker (ej: "BINANCE", "OANDA")
- `symbol` (nivel raíz) - Instrumento (ej: "BTCUSDT", "EURUSD")
- `pattern_candle.confidence` - Confianza **real** del patrón detectado
- `emas.alignment` - Alineación en formato string (ej: "BULLISH_ALIGNED")
- `emas.trend_score` - Score numérico (-10 a +10)
- `outcome_candle.direction` - Dirección de la vela ("VERDE", "ROJA", "DOJI")
- `metadata` - Metadatos organizados (versión, fecha de creación)

### 🔄 Reestructurado
- `signal` + `trigger_candle` → `pattern_candle` (unificado)
- `raw_data` → Distribuido en campos apropiados (`emas`, `metadata`)

## 📊 Estructura Completa

```json
{
  "timestamp": 1700000000,
  "source": "BINANCE",
  "symbol": "BTCUSDT",
  
  "pattern_candle": {
    "timestamp": 1700000000,
    "open": 35420.5,
    "high": 35480.2,
    "low": 35400.1,
    "close": 35410.3,
    "volume": 12.5,
    "pattern": "SHOOTING_STAR",
    "confidence": 0.85
  },
  
  "emas": {
    "ema_200": 35300.0,
    "ema_50": 35350.0,
    "ema_30": 35370.0,
    "ema_20": 35390.0,
    "alignment": "BULLISH_ALIGNED",
    "trend_score": 7
  },
  
  "outcome_candle": {
    "timestamp": 1700000060,
    "open": 35410.3,
    "high": 35420.0,
    "low": 35380.5,
    "close": 35385.2,
    "volume": 8.3,
    "direction": "ROJA"
  },
  
  "outcome": {
    "expected_direction": "ROJA",
    "actual_direction": "ROJA",
    "success": true
  },
  
  "metadata": {
    "algo_version": "v2.0",
    "created_at": "2024-11-23T12:00:00Z"
  },
  
  "_storage_metadata": {
    "written_at": "2024-11-23T12:00:01Z",
    "record_id": 1
  }
}
```

## 🔑 Campos Principales

### 📍 Nivel Raíz
| Campo | Tipo | Descripción |
|-------|------|-------------|
| `timestamp` | int | Unix timestamp de la vela patrón |
| `source` | string | Exchange/broker (BINANCE, OANDA, FX) |
| `symbol` | string | Instrumento (BTCUSDT, EURUSD) |

### 🕯️ pattern_candle
Contiene toda la información de la vela donde se detectó el patrón.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `timestamp` | int | Unix timestamp |
| `open` | float | Precio de apertura |
| `high` | float | Precio máximo |
| `low` | float | Precio mínimo |
| `close` | float | Precio de cierre |
| `volume` | float | Volumen |
| `pattern` | string | Patrón detectado (SHOOTING_STAR, HAMMER, etc.) |
| `confidence` | float | Confianza del patrón (0.0 - 1.0) |

### 📈 emas
Indicadores técnicos y análisis de tendencia.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ema_200` | float | EMA de 200 periodos |
| `ema_50` | float | EMA de 50 periodos |
| `ema_30` | float | EMA de 30 periodos |
| `ema_20` | float | EMA de 20 periodos |
| `alignment` | string | Alineación de EMAs (ver tabla abajo) |
| `trend_score` | int | Score de tendencia (-10 a +10) |

#### Valores de `alignment`
| Valor | Descripción | Condición |
|-------|-------------|-----------|
| `BULLISH_ALIGNED` | Alineación alcista perfecta | EMA20 > EMA30 > EMA50 > EMA200 |
| `BEARISH_ALIGNED` | Alineación bajista perfecta | EMA20 < EMA30 < EMA50 < EMA200 |
| `BULLISH_PARTIAL` | Alineación alcista parcial | EMA20 > EMA50 > EMA200 |
| `BEARISH_PARTIAL` | Alineación bajista parcial | EMA20 < EMA50 < EMA200 |
| `MIXED` | Sin alineación clara | Otras combinaciones |
| `INCOMPLETE` | EMAs incompletas | Alguna EMA es NaN |

### 🎯 outcome_candle
Información de la vela siguiente (resultado de la predicción).

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `timestamp` | int | Unix timestamp (60s después del pattern) |
| `open` | float | Precio de apertura |
| `high` | float | Precio máximo |
| `low` | float | Precio mínimo |
| `close` | float | Precio de cierre |
| `volume` | float | Volumen |
| `direction` | string | Dirección real (VERDE, ROJA, DOJI) |

### ✅ outcome
Resultado de la predicción.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `expected_direction` | string | Dirección esperada (VERDE, ROJA) |
| `actual_direction` | string | Dirección real (VERDE, ROJA, DOJI) |
| `success` | boolean | Si la predicción fue correcta |

### 📝 metadata
Metadatos del registro.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `algo_version` | string | Versión del algoritmo (ej: "v2.0") |
| `created_at` | string | Timestamp ISO8601 de creación |

### 🗄️ _storage_metadata
Metadatos internos del sistema de almacenamiento (agregados automáticamente).

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `written_at` | string | Timestamp ISO8601 de escritura |
| `record_id` | int | ID secuencial del registro |

## 🧮 Cálculos Derivados

Los siguientes valores pueden calcularse desde los datos crudos:

### PnL en Pips
```python
# Para patrones bajistas (SHOOTING_STAR, HANGING_MAN)
pnl_pips = (pattern_candle.close - outcome_candle.close) * 10000

# Para patrones alcistas (HAMMER, INVERTED_HAMMER)
pnl_pips = (outcome_candle.close - pattern_candle.close) * 10000
```

### Trend Status
```python
if trend_score >= 6:
    trend_status = "STRONG_BULLISH"
elif trend_score >= 2:
    trend_status = "WEAK_BULLISH"
elif trend_score >= -1:
    trend_status = "NEUTRAL"
elif trend_score >= -5:
    trend_status = "WEAK_BEARISH"
else:
    trend_status = "STRONG_BEARISH"
```

### Is Trend Aligned (Boolean)
```python
is_trend_aligned = alignment in ["BULLISH_ALIGNED", "BEARISH_ALIGNED"]
```

### Cuerpo de la Vela
```python
body_size = abs(pattern_candle.close - pattern_candle.open)
body_direction = "VERDE" if pattern_candle.close > pattern_candle.open else "ROJA"
```

### Rango Total
```python
total_range = pattern_candle.high - pattern_candle.low
```

### Mechas
```python
if pattern_candle.close > pattern_candle.open:
    upper_wick = pattern_candle.high - pattern_candle.close
    lower_wick = pattern_candle.open - pattern_candle.low
else:
    upper_wick = pattern_candle.high - pattern_candle.open
    lower_wick = pattern_candle.close - pattern_candle.low
```

## 📊 Ejemplo de Análisis

```python
import json
import pandas as pd

# Cargar dataset
with open('data/trading_signals_dataset.jsonl', 'r') as f:
    data = [json.loads(line) for line in f]

df = pd.DataFrame(data)

# Calcular PnL para todos los registros
def calculate_pnl(row):
    pattern = row['pattern_candle']['pattern']
    pattern_close = row['pattern_candle']['close']
    outcome_close = row['outcome_candle']['close']
    
    if pattern in ['SHOOTING_STAR', 'HANGING_MAN']:
        return (pattern_close - outcome_close) * 10000
    else:
        return (outcome_close - pattern_close) * 10000

df['pnl_pips'] = df.apply(calculate_pnl, axis=1)

# Estadísticas por patrón
df['pattern'] = df['pattern_candle'].apply(lambda x: x['pattern'])
stats = df.groupby('pattern').agg({
    'outcome': lambda x: sum([o['success'] for o in x]) / len(x),
    'pnl_pips': 'mean'
})

print("Win Rate por Patrón:")
print(stats['outcome'])
```

## 🔄 Migración desde V1

Si tienes datos en formato V1, puedes migrarlos con:

```python
def migrate_v1_to_v2(old_record):
    # Extraer source y symbol de signal.source
    source_full = old_record['signal']['source']
    source, symbol = source_full.split('_')
    
    return {
        "timestamp": old_record['timestamp'],
        "source": source,
        "symbol": symbol,
        "pattern_candle": {
            **old_record['trigger_candle'],
            "pattern": old_record['signal']['pattern'],
            "confidence": old_record['signal']['confidence']
        },
        "emas": {
            "ema_200": old_record['raw_data']['ema_200'],
            "ema_50": old_record['raw_data']['ema_50'],
            "ema_30": old_record['raw_data']['ema_30'],
            "ema_20": old_record['raw_data']['ema_20'],
            "alignment": calculate_alignment(old_record['raw_data']),
            "trend_score": old_record['signal']['trend_score']
        },
        "outcome_candle": {
            **old_record['outcome_candle'],
            "direction": old_record['outcome']['actual_direction']
        },
        "outcome": {
            "expected_direction": old_record['outcome']['expected_direction'],
            "actual_direction": old_record['outcome']['actual_direction'],
            "success": old_record['outcome']['success']
        },
        "metadata": {
            "algo_version": old_record['raw_data']['algo_version'],
            "created_at": old_record.get('_metadata', {}).get('written_at', '')
        }
    }
```

## ✅ Validación

El `StorageService` valida automáticamente que cada registro tenga:

1. **Campos raíz**: timestamp, source, symbol
2. **pattern_candle**: OHLCV completo + pattern + confidence
3. **emas**: 4 EMAs + alignment + trend_score
4. **outcome_candle**: OHLCV completo + direction
5. **outcome**: expected_direction, actual_direction, success
6. **metadata**: algo_version, created_at

Si falta algún campo, se lanza `ValueError` con detalles específicos.

## 📈 Ventajas de V2

1. **Más compacto**: Elimina redundancia
2. **Más claro**: Source y symbol en nivel raíz
3. **Más flexible**: Datos crudos permiten calcular cualquier métrica
4. **Más preciso**: Confidence real del patrón, no hardcoded
5. **Mejor organizado**: Agrupación lógica de campos relacionados

## 🔗 Referencias

- `backfill_historical_data.py`: Generador de dataset histórico
- `storage_service.py`: Capa de persistencia y validación
- `analysis_service.py`: Servicio de análisis en tiempo real
- `candle.py`: Funciones de detección de patrones
