# Sistema de Dataset de Backtesting

## Arquitectura Implementada

### 1. Capa de Persistencia (`StorageService`)

**Ubicación:** `src/services/storage_service.py`

**Responsabilidades:**
- Almacenamiento asíncrono en formato JSONL (JSON Lines)
- Gestión automática de directorios (`data/`)
- Validación de estructura de registros
- Enriquecimiento con metadata
- No bloquea el Event Loop (usa `asyncio.to_thread`)

**Formato JSONL:**
- Cada línea es un JSON válido independiente
- Ventajas: No corrupción si se interrumpe, append eficiente
- Archivo: `data/trading_signals_dataset.jsonl`

### 2. State Machine en `AnalysisService`

**Nueva Lógica de Procesamiento:**

#### Flujo en `process_realtime_candle`:

```
┌─────────────────────────────────────────┐
│  1. Recibir Nueva Vela en Tiempo Real  │
└─────────────────────────────────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │ ¿Es nueva vela? │
         │ (timestamp ≠)   │
         └─────────────────┘
                   │
          ┌────────┴────────┐
          │ NO              │ SÍ
          ▼                 ▼
  ┌──────────────┐   ┌──────────────────────┐
  │ Actualizar   │   │ PASO 1:              │
  │ vela actual  │   │ ¿Hay señal pendiente?│
  └──────────────┘   └──────────────────────┘
                              │
                     ┌────────┴────────┐
                     │ SÍ              │ NO
                     ▼                 │
            ┌────────────────────┐     │
            │ _close_signal_cycle│     │
            │ - Calcular outcome │     │
            │ - Guardar en JSONL │     │
            │ - Limpiar pending  │     │
            └────────────────────┘     │
                     │                 │
                     └────────┬────────┘
                              ▼
                   ┌──────────────────────┐
                   │ PASO 2:              │
                   │ Agregar nueva vela   │
                   │ Calcular indicadores │
                   └──────────────────────┘
                              │
                              ▼
                   ┌──────────────────────┐
                   │ PASO 3:              │
                   │ Analizar patrón      │
                   │ ¿Patrón detectado?   │
                   └──────────────────────┘
                              │
                     ┌────────┴────────┐
                     │ SÍ              │ NO
                     ▼                 │
          ┌─────────────────────┐     │
          │ Guardar en          │     │
          │ pending_signals     │     │
          │ Notificar Telegram  │     │
          └─────────────────────┘     │
                     │                 │
                     └────────┬────────┘
                              ▼
                         [Fin ciclo]
```

#### Atributos Nuevos:

```python
self.pending_signals: Dict[str, PatternSignal] = {}
# Key: source_key (ej: "FX_EURUSD")
# Value: PatternSignal completo
```

### 3. Estructura del Registro JSONL

```json
{
  "timestamp": "2025-11-21T20:15:00Z",
  "signal": {
    "pattern": "SHOOTING_STAR",
    "source": "FX",
    "symbol": "EURUSD",
    "confidence": 0.85,
    "trend": "STRONG_BULLISH",
    "trend_score": 6,
    "is_trend_aligned": false
  },
  "trigger_candle": {
    "timestamp": 1732226100,
    "open": 1.05420,
    "high": 1.05680,
    "low": 1.05400,
    "close": 1.05430,
    "volume": 12500
  },
  "outcome_candle": {
    "timestamp": 1732226160,
    "open": 1.05430,
    "high": 1.05450,
    "low": 1.05210,
    "close": 1.05230,
    "volume": 15200
  },
  "outcome": {
    "expected_direction": "ROJO",
    "actual_direction": "ROJO",
    "success": true,
    "pnl_pips": 20.0,
    "outcome_timestamp": "2025-11-21T20:16:00Z"
  },
  "_metadata": {
    "written_at": "2025-11-21T20:16:05Z",
    "record_id": 1,
    "version": "1.0"
  }
}
```

### 4. Cálculo de PnL

**Lógica implementada:**

- **SHORT (patrones bajistas: Shooting Star, Hanging Man):**
  ```python
  pnl_pips = (precio_entrada - precio_salida) * 10000
  ```
  
- **LONG (patrones alcistas: Hammer, Inverted Hammer):**
  ```python
  pnl_pips = (precio_salida - precio_entrada) * 10000
  ```

**Nota:** Asume 4 decimales (EUR/USD estándar). Factor 10000 convierte a pips.

### 5. Direcciones Esperadas por Patrón

| Patrón | Tipo Reversión | Dirección Esperada | Operación |
|--------|----------------|-------------------|-----------|
| Shooting Star | Bajista | ROJO | SHORT |
| Hanging Man | Bajista | ROJO | SHORT |
| Hammer | Alcista | VERDE | LONG |
| Inverted Hammer | Alcista | VERDE | LONG |

### 6. Inicialización en `main.py`

**Orden de inyección:**

```python
# 1. StorageService (sin dependencias)
storage_service = StorageService()

# 2. TelegramService (sin dependencias)
telegram_service = TelegramService()

# 3. AnalysisService (depende de Storage + Telegram)
analysis_service = AnalysisService(
    on_pattern_detected=telegram_service.handle_pattern_signal,
    storage_service=storage_service
)

# 4. ConnectionService (depende de Analysis)
connection_service = ConnectionService(
    analysis_service=analysis_service
)
```

## Uso del Dataset

### Lectura del Archivo JSONL

```python
import json
from pathlib import Path

def load_dataset(file_path="data/trading_signals_dataset.jsonl"):
    """Carga el dataset completo."""
    records = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            records.append(record)
    return records
```

### Análisis de Éxito por Patrón

```python
def analyze_pattern_success(records):
    """Calcula tasa de éxito por patrón."""
    from collections import defaultdict
    
    stats = defaultdict(lambda: {"total": 0, "success": 0})
    
    for record in records:
        pattern = record["signal"]["pattern"]
        success = record["outcome"]["success"]
        
        stats[pattern]["total"] += 1
        if success:
            stats[pattern]["success"] += 1
    
    # Calcular tasas
    for pattern, data in stats.items():
        success_rate = (data["success"] / data["total"]) * 100
        print(f"{pattern}: {success_rate:.1f}% ({data['success']}/{data['total']})")
```

### Filtrado por Score de Tendencia

```python
def filter_by_trend_score(records, min_score=6):
    """Filtra señales con score de tendencia fuerte."""
    return [
        r for r in records 
        if abs(r["signal"]["trend_score"]) >= min_score
    ]
```

## Ventajas del Sistema

### 1. Desacoplamiento
- `StorageService` es independiente de la lógica de negocio
- Fácil de testear y modificar
- Puede migrar a base de datos sin cambiar `AnalysisService`

### 2. Integridad de Datos
- JSONL previene corrupción parcial
- Validación antes de escribir
- Metadata para auditoría

### 3. Performance
- Escritura asíncrona no bloquea Event Loop
- Append eficiente (no reescribe archivo completo)
- Sin overhead de base de datos

### 4. Machine Learning Ready
- Formato estándar (JSONL)
- Features completas (EMAs, trend, confidence)
- Labels claros (success: true/false)
- PnL numérico para regresión

## Próximas Mejoras Posibles

### 1. Rotación de Archivos
```python
# Crear nuevo archivo cada día
filename = f"trading_signals_{date.today().isoformat()}.jsonl"
```

### 2. Compresión
```python
import gzip
# Comprimir archivos antiguos
with gzip.open(f"{file_path}.gz", "wb") as gz_file:
    gz_file.write(file_path.read_bytes())
```

### 3. Migración a Base de Datos
```python
# SQLite para análisis más complejos
import sqlite3
# O PostgreSQL/MongoDB para producción a escala
```

### 4. Validación de Esquema
```python
from pydantic import BaseModel
# Validar estructura con Pydantic
```

### 5. Análisis Estadístico Automático
```python
# Generar reportes periódicos
# Detectar degradación de performance
# Alertar si tasa de éxito cae < umbral
```

## Debugging

### Ver Estadísticas del Storage

```python
# En el código
stats = storage_service.get_stats()
print(stats)
# Output: {"records_written": 42, "file_size_mb": 0.15, ...}
```

### Logs Relevantes

```
💾 Storage Service inicializado | Archivo: data/trading_signals_dataset.jsonl
🔄 CERRANDO CICLO DE SEÑAL | Patrón Previo: SHOOTING_STAR
✅ CICLO CERRADO | Éxito: ✓ | PnL: +20.0 pips
⏳ SEÑAL GUARDADA COMO PENDIENTE | FX_EURUSD | HAMMER
💾 Registro guardado | Patrón: HAMMER | Éxito: true | PnL: 15.5 pips
```

### Verificar Archivo

```bash
# Ver últimas 3 líneas del dataset
tail -n 3 data/trading_signals_dataset.jsonl | jq .

# Contar registros
wc -l data/trading_signals_dataset.jsonl

# Ver todos los patrones únicos
cat data/trading_signals_dataset.jsonl | jq -r '.signal.pattern' | sort | uniq -c
```

## Consideraciones de Producción

### 1. Manejo de Errores
- `StorageService` NO propaga excepciones (no detiene el bot)
- Logs detallados de errores
- Continúa operando incluso si falla storage

### 2. Concurrencia
- Un `pending_signal` por `source_key` (evita race conditions)
- Escrituras serializadas por fuente

### 3. Pérdida de Datos
- Si el bot se reinicia, las señales pendientes se pierden
- Solución futura: Persistir `pending_signals` en JSON

### 4. Consumo de Disco
- Estimación: ~0.5 KB por registro
- 1000 señales ≈ 500 KB
- 10,000 señales ≈ 5 MB (manejable)

## Testing

### Test Manual

1. Iniciar el bot
2. Esperar detección de patrón
3. Verificar log: `⏳ SEÑAL GUARDADA COMO PENDIENTE`
4. Esperar cierre de siguiente vela
5. Verificar log: `🔄 CERRANDO CICLO DE SEÑAL`
6. Verificar archivo: `cat data/trading_signals_dataset.jsonl`

### Test Unitario (Futuro)

```python
import pytest
from src.services.storage_service import StorageService

@pytest.mark.asyncio
async def test_save_signal_outcome():
    storage = StorageService(data_dir="test_data")
    record = {...}  # Mock record
    await storage.save_signal_outcome(record)
    assert storage.records_written == 1
```

## Conclusión

Sistema robusto de dataset implementado con:
- ✅ Arquitectura desacoplada y testeable
- ✅ Persistencia confiable en JSONL
- ✅ State Machine para ciclo de vida de señales
- ✅ Cálculo automático de PnL
- ✅ Listo para análisis de Machine Learning
