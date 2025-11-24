# Scripts de Backtesting v4.1

## Archivos Creados

### 1. `backfill_historical_data_v41.py`
Script actualizado para generar dataset con lógica v4.1:
- **EMAs:** 5, 7, 10, 15, 20, 30, 50 (eliminadas 100 y 200)
- **Límite:** 250 velas por request (suficiente para EMA 50)
- **Integración:** Usa `analyze_trend()` de `analysis_service`
- **Nuevos campos:** `candle_exhaustion`, `signal_strength` actualizado
- **Version:** `algo_version: "4.1"`

### 2. `test/analyze_dataset_v4.py`
Script de análisis estadístico del dataset generado:
- Filtra por `algo_version="4.1"`
- Calcula Win Rate (ITM) por patrón y signal strength
- Muestra distribución de outcomes (VERDE/ROJA/DOJI)
- Análisis por exhaustion y tendencia

---

## Uso

### Paso 1: Generar Dataset

```bash
# Ejecutar backfill para generar datos históricos
python backfill_historical_data_v41.py
```

**Configuración (dentro del script):**
- `DAYS_TO_FETCH = 30`: Días de historia a obtener
- `CANDLES_PER_REQUEST = 250`: Velas por petición
- `SKIP_CANDLES = 100`: Velas iniciales a saltar

**Salida:**
- Archivo: `data/trading_signals_dataset.jsonl`
- Cada línea es un registro JSON con los campos:
  - `algo_version`: "4.1"
  - `pattern_name`: Patrón detectado
  - `emas`: Dict con EMAs 5-50
  - `trend_score`: Score de -10.0 a +10.0
  - `bollinger_exhaustion`: Boolean
  - `candle_exhaustion`: Boolean
  - `signal_strength`: VERY_HIGH, HIGH, MEDIUM, LOW, VERY_LOW, NONE
  - `outcome`: VERDE/ROJA/DOJI (vela siguiente)

---

### Paso 2: Analizar Resultados

```bash
# Análisis completo (todos los símbolos)
python test/analyze_dataset_v4.py

# Filtrar por símbolo específico
python test/analyze_dataset_v4.py --symbol EURUSD

# Usar archivo custom
python test/analyze_dataset_v4.py --file data/custom_dataset.jsonl
```

**Salidas del análisis:**
1. **Consola:** Tablas con Win Rate por patrón y signal strength
2. **CSV:** `test/analysis_results_v41_{SYMBOL}.csv`

**Métricas mostradas:**
- Total Signals
- Wins (ITM) / Losses (OTM)
- Win Rate %
- Distribution (Verde/Roja/Doji Next)
- Análisis por exhaustion
- Análisis por tendencia

---

## Ejemplo de Salida del Análisis

```
================================================================================
📊 RESULTADOS POR PATRÓN Y SIGNAL STRENGTH
================================================================================
            Pattern Signal Strength  Total Signals  Wins (ITM)  Losses (OTM)  Win Rate %  Verde Next  Roja Next  Doji Next
      SHOOTING_STAR       VERY_HIGH             45          32            13       71.11          13         32          0
      SHOOTING_STAR            HIGH             89          54            35       60.67          35         54          0
      SHOOTING_STAR          MEDIUM             12           7             5       58.33           5          7          0
      SHOOTING_STAR             LOW            156          83            73       53.21          73         83          0
      SHOOTING_STAR        VERY_LOW            234         118           116       50.43         116        118          0
```

---

## Integración con Lógica Central

### ✅ Funciones Importadas (NO re-implementadas):

```python
from src.logic.analysis_service import (
    analyze_trend,           # Calcula trend_score con EMAs ponderadas
    calculate_ema,           # Cálculo de EMAs (misma lógica que producción)
    calculate_bollinger_bands,  # Bollinger Bands con SMA 20
    detect_exhaustion        # Detecta PEAK/BOTTOM/NONE
)

from src.logic.candle import (
    is_shooting_star,
    is_hanging_man,
    is_inverted_hammer,
    is_hammer,
    get_candle_direction
)
```

**Ventaja:** Garantiza que el backtesting use EXACTAMENTE la misma lógica que el bot en producción.

---

## Matriz de Decisión (Signal Strength)

### Tendencia ALCISTA (score > 2)
Buscamos patrones BAJISTAS:

| Patrón | Bollinger Exh | Candle Exh | Signal Strength |
|--------|---------------|------------|-----------------|
| **Shooting Star** (Principal) | ✅ | ✅ | **VERY_HIGH** |
| Shooting Star | ✅ | ❌ | HIGH |
| Shooting Star | ❌ | ✅ | LOW |
| Shooting Star | ❌ | ❌ | VERY_LOW |
| **Inverted Hammer** (Secundario) | ✅ | ✅ | **MEDIUM** |
| Inverted Hammer | ✅ | ❌ | LOW |
| Inverted Hammer | ❌ | ✅ | VERY_LOW |
| Inverted Hammer | ❌ | ❌ | NONE |

### Tendencia BAJISTA (score < -2)
Buscamos patrones ALCISTAS:

| Patrón | Bollinger Exh | Candle Exh | Signal Strength |
|--------|---------------|------------|-----------------|
| **Hammer** (Principal) | ✅ | ✅ | **VERY_HIGH** |
| Hammer | ✅ | ❌ | HIGH |
| Hammer | ❌ | ✅ | LOW |
| Hammer | ❌ | ❌ | VERY_LOW |
| **Hanging Man** (Secundario) | ✅ | ✅ | **MEDIUM** |
| Hanging Man | ✅ | ❌ | LOW |
| Hanging Man | ❌ | ✅ | VERY_LOW |
| Hanging Man | ❌ | ❌ | NONE |

### Tendencia NEUTRAL (-2 a 2)
Todas las señales se **degradan un nivel**:
- VERY_HIGH → HIGH
- HIGH → MEDIUM
- MEDIUM → LOW
- LOW → VERY_LOW
- VERY_LOW → NONE

---

## Candle Exhaustion Logic

```python
# Patrones BAJISTAS: Verificar ruptura de máximo
if pattern in ["SHOOTING_STAR", "HANGING_MAN"]:
    candle_exhaustion = current_high > previous_high

# Patrones ALCISTAS: Verificar ruptura de mínimo
elif pattern in ["HAMMER", "INVERTED_HAMMER"]:
    candle_exhaustion = current_low < previous_low
```

**Significado:** El precio intentó continuar la tendencia pero fue rechazado (mecha larga).

---

## Troubleshooting

### Error: "No se encontró el archivo"
```bash
# Verificar que existe el dataset
ls data/trading_signals_dataset.jsonl

# Si no existe, ejecutar primero:
python backfill_historical_data_v41.py
```

### Error: "No hay datos para analizar"
```bash
# Verificar que hay registros v4.1
cat data/trading_signals_dataset.jsonl | grep '"algo_version": "4.1"'

# Si está vacío, el backfill no se ejecutó correctamente
```

### Dataset muy grande
```bash
# Reducir DAYS_TO_FETCH en backfill_historical_data_v41.py
# Ejemplo: DAYS_TO_FETCH = 7  # Solo última semana
```

---

## Próximos Pasos

1. **Validar Win Rates:** Comparar con resultados reales
2. **Optimizar Pesos de EMAs:** Ajustar según backtesting
3. **Añadir más métricas:** Sharpe Ratio, Max Drawdown
4. **Comparar versiones:** v4.0 vs v4.1

---

## Notas Importantes

- ⚠️ **No modificar** `backfill_historical_data.py` original (mantener para compatibilidad)
- ✅ **Usar** `backfill_historical_data_v41.py` para nuevos datos
- 📊 **Dataset v4.1** es incompatible con análisis de versiones anteriores
- 🔄 **Re-generar dataset** si se modifican pesos de EMAs en producción

---

## Contacto

Para dudas o mejoras, contactar al equipo de Trading Bot Development.
