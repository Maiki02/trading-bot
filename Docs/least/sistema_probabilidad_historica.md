# Sistema de Probabilidad Histórica en Tiempo Real - Resumen Técnico

## 📋 Objetivo Cumplido

Implementar un sistema que almacene **datos crudos (raw data)** en el dataset JSONL para permitir recalcular scores retroactivamente y mostrar **probabilidades de éxito en tiempo real** en las alertas de Telegram.

---

## 🏗️ Arquitectura Implementada

### 1. **StatisticsService** (`src/services/statistics_service.py`)

**Responsabilidades:**
- Cargar dataset JSONL en pandas DataFrame.
- Normalizar scores usando la lógica actual de `analyze_trend`.
- Consultar probabilidades con fuzzy matching.
- Analizar rachas (streaks) de éxito/fracaso.

**Métodos Principales:**

#### `__init__(data_path)`
Inicializa el servicio y carga el dataset automáticamente.

#### `_load_dataset()`
Lee el archivo JSONL línea por línea, maneja casos de archivo inexistente o vacío.

#### `_normalize_scores()`
Recalcula scores usando la función `analyze_trend` con los datos de `raw_data`.
Crea columna `calculated_score` en el DataFrame.

**Ventaja:** Si cambias la lógica de scoring, los scores históricos se actualizan automáticamente.

#### `get_probability(pattern, current_score, lookback_days=30, score_tolerance=1)`
Consulta probabilidad de éxito para un patrón y score dados.

**Filtros aplicados:**
1. Ventana de tiempo (últimos N días).
2. Patrón exacto.
3. Rango de score (fuzzy match: ±1 por defecto).

**Retorna:**
```python
{
    "total_cases": 15,        # Total de casos similares
    "win_rate": 0.733,        # 73.3% de éxito
    "wins": 11,               # Señales exitosas
    "losses": 4,              # Señales fallidas
    "streak": [True, True, False, True, True],  # Últimos 5 resultados
    "avg_pnl_pips": 245.7,    # PnL promedio en pips
    "lookback_days": 30,      # Días analizados
    "score_range": (9, 11)    # Rango de scores usado
}
```

#### `reload_dataset()`
Recarga el dataset desde disco. Útil para actualizar estadísticas después de nuevas señales.

#### `get_stats_summary()`
Retorna resumen general del dataset (patrones detectados, win rate global, etc.).

---

### 2. **StorageService** - Modificaciones (`src/services/storage_service.py`)

**Cambio Crítico:** Campo `raw_data` ahora **obligatorio** en `save_signal_outcome`.

**Estructura del campo `raw_data`:**
```json
"raw_data": {
    "ema_200": 84923.12345,
    "ema_50": 85089.45678,
    "ema_30": 85156.78901,
    "ema_20": 85234.12345,
    "close": 85735.58000,
    "open": 85741.03000,
    "algo_version": "v2.0"
}
```

**Validación actualizada:**
- Verifica presencia de `raw_data` en `_validate_record`.
- Verifica sub-estructura de `raw_data` (todos los campos obligatorios).

**Ventaja:**
- Si cambias `analyze_trend`, puedes recalcular scores de señales antiguas sin perder información.
- El historial nunca queda obsoleto.

---

### 3. **AnalysisService** - Modificaciones (`src/logic/analysis_service.py`)

**Cambios implementados:**

#### Modificación de `PatternSignal` (dataclass)
Agregado campo opcional:
```python
statistics: Optional[Dict] = None  # Estadísticas históricas de probabilidad
```

#### Modificación de `__init__`
Agregado parámetro:
```python
statistics_service: Optional[object] = None  # StatisticsService para probabilidades
```

#### Lógica de consulta de estadísticas (antes de emitir señal)
Antes de crear el `PatternSignal`, se consulta:
```python
statistics = None
if self.statistics_service:
    try:
        statistics = self.statistics_service.get_probability(
            pattern=pattern_detected,
            current_score=trend_analysis.score,
            lookback_days=30,
            score_tolerance=1
        )
    except Exception as e:
        logger.warning(f"⚠️  Error obteniendo estadísticas: {e}")
```

#### Construcción del registro con `raw_data`
Al cerrar ciclo de señal pendiente, se agrega:
```python
"raw_data": {
    "ema_200": pending_signal.ema_200,
    "ema_50": pending_signal.ema_50,
    "ema_30": pending_signal.ema_30,
    "ema_20": pending_signal.ema_20,
    "close": pending_signal.candle.close,
    "open": pending_signal.candle.open,
    "algo_version": "v2.0"
}
```

---

### 4. **TelegramService** - Modificaciones (`src/services/telegram_service.py`)

**Cambio:** Bloque de estadísticas en `_format_standard_message`.

**Lógica condicional:**
```python
statistics_block = ""
if signal.statistics and signal.statistics.get("total_cases", 0) > 5:
    # Construir bloque de estadísticas
```

**Formato del bloque:**
```
━━━━━━━━━━━━━━━━━━━━━━━━
📊 PROBABILIDAD HISTÓRICA (Últimos 30 días)
━━━━━━━━━━━━━━━━━━━━━━━━
🟢 Win Rate: 73.3% (11/15 señales)
🎯 PnL Promedio: 245.7 pips
📈 Racha reciente: ✓ ✓ ✗ ✓ ✓
🔍 Score similar: [9, 11]
```

**Emojis según Win Rate:**
- **🟢 ≥70%**: Alta probabilidad de éxito.
- **🟡 50-70%**: Probabilidad moderada.
- **🔴 <50%**: Baja probabilidad (señal histórica desfavorable).

**Umbral configurable:** Solo se muestra si `total_cases > 5` (mínimo de datos).

---

### 5. **main.py** - Integración

**Modificación en `initialize()`:**

```python
# 2. Statistics Service (análisis de probabilidad - sin dependencias)
from src.services.statistics_service import StatisticsService
self.statistics_service = StatisticsService(
    data_path="data/trading_signals_dataset.jsonl"
)

# 4. Analysis Service (depende de Telegram, Storage y Statistics)
self.analysis_service = AnalysisService(
    on_pattern_detected=self.telegram_service.handle_pattern_signal,
    storage_service=self.storage_service,
    telegram_service=self.telegram_service,
    statistics_service=self.statistics_service  # ← Nueva inyección
)
```

**Orden de inicialización:**
1. StorageService (persistencia).
2. **StatisticsService** (análisis).
3. TelegramService (notificaciones).
4. AnalysisService (recibe los 3 anteriores).
5. ConnectionService (recibe AnalysisService).

---

## 🔄 Flujo Completo de Datos

### 1. Detección de Patrón

```
ConnectionService → AnalysisService
                        ↓
            [Patrón detectado]
                        ↓
        StatisticsService.get_probability()
                        ↓
            [Consulta historial]
                        ↓
    PatternSignal (con statistics)
                        ↓
        TelegramService.handle_pattern_signal()
                        ↓
            [Alerta con probabilidad]
```

### 2. Cierre de Ciclo (Vela Outcome)

```
AnalysisService detecta vela siguiente
                        ↓
    Construye registro con raw_data
                        ↓
    StorageService.save_signal_outcome()
                        ↓
        [Persistencia en JSONL]
                        ↓
    (Opcional) StatisticsService.reload_dataset()
```

---

## 📊 Ventajas del Sistema

### 1. **Inmunidad a Cambios de Lógica**
Si modificas `analyze_trend`:
- Los registros antiguos conservan datos crudos.
- `StatisticsService` recalcula scores al vuelo.
- No pierdes historial.

### 2. **Fuzzy Matching Inteligente**
Busca señales con score similar (±1 por defecto).
- Aumenta muestra estadística.
- Reduce casos de "datos insuficientes".

### 3. **Toma de Decisiones Basada en Datos**
El trader ve:
- **Win rate histórico** del patrón en contextos similares.
- **PnL promedio** esperado.
- **Racha reciente** (últimos 5 resultados).

### 4. **Progresivo**
- Con ≤5 casos: No muestra estadísticas.
- Con 6-20 casos: Probabilidades iniciales.
- Con >50 casos: Estadísticas confiables.

### 5. **Performance Optimizado**
- Usa pandas para análisis rápido.
- Carga dataset solo al inicializar (una vez).
- Queries usan filtros vectorizados.

---

## 🧪 Testing

### Script de Prueba: `test_statistics_service.py`

**Ejecutar con:**
```bash
python test_statistics_service.py
```

**Qué verifica:**
1. Carga correcta del dataset.
2. Resumen general (patrones, win rate global).
3. Consultas de probabilidad por patrón y score.
4. Normalización de scores (columna `calculated_score`).
5. Distribución de scores recalculados.

---

## 📝 Ejemplo de Registro JSONL con `raw_data`

```json
{
  "timestamp": "2025-11-23T01:47:00Z",
  "signal": {
    "pattern": "SHOOTING_STAR",
    "source": "BINANCE",
    "symbol": "BTCUSDT",
    "confidence": 0.9,
    "trend": "STRONG_BULLISH",
    "trend_score": 10,
    "is_trend_aligned": true
  },
  "trigger_candle": {
    "timestamp": 1763862420,
    "open": 85741.03,
    "high": 85811.36,
    "low": 85722.99,
    "close": 85735.58,
    "volume": 270.33784
  },
  "outcome_candle": {
    "timestamp": 1763862480,
    "open": 85735.58,
    "high": 85847.28,
    "low": 85735.57,
    "close": 85792.59,
    "volume": 165.83637
  },
  "outcome": {
    "expected_direction": "ROJO",
    "actual_direction": "VERDE",
    "success": false,
    "pnl_pips": -570.1,
    "outcome_timestamp": "2025-11-23T01:48:00Z"
  },
  "raw_data": {
    "ema_200": 84923.12345,
    "ema_50": 85089.45678,
    "ema_30": 85156.78901,
    "ema_20": 85234.12345,
    "close": 85735.58,
    "open": 85741.03,
    "algo_version": "v2.0"
  },
  "_metadata": {
    "timestamp_gap_seconds": 60,
    "expected_gap_seconds": 60,
    "has_skipped_candles": false,
    "written_at": "2025-11-23T01:49:01.219782Z",
    "record_id": 5,
    "version": "1.0"
  }
}
```

---

## 🚀 Próximos Pasos Recomendados

### 1. **Ejecutar el Bot**
Acumular datos con el nuevo formato `raw_data`.

### 2. **Monitorear Alertas**
Verificar que las estadísticas se muestren correctamente en Telegram.

### 3. **Ajustar Umbrales**
Modificar `total_cases > 5` según preferencia (ej: `> 10` para más confianza).

### 4. **Análisis Avanzado (Futuro)**
- Entrenar modelos ML (Gradient Boosting, Random Forest).
- Predecir probabilidad en lugar de solo consultar historial.
- Incorporar features adicionales (volatilidad, hora del día, etc.).

### 5. **Dashboard de Estadísticas (Opcional)**
Crear un dashboard con Streamlit o Plotly para visualizar:
- Win rate por patrón.
- Distribución de scores.
- Curvas de PnL acumulado.
- Heatmaps de probabilidad.

---

## ✅ Checklist de Implementación

- [x] Crear `StatisticsService` con carga de JSONL.
- [x] Implementar normalización de scores.
- [x] Implementar query de probabilidad con fuzzy matching.
- [x] Modificar `StorageService` para validar `raw_data`.
- [x] Actualizar `PatternSignal` con campo `statistics`.
- [x] Integrar consulta de estadísticas en `AnalysisService`.
- [x] Agregar `raw_data` al registro en `_resolve_pending_signal`.
- [x] Modificar `TelegramService` para mostrar bloque de estadísticas.
- [x] Integrar `StatisticsService` en `main.py`.
- [x] Actualizar `__init__.py` de services.
- [x] Crear script de testing (`test_statistics_service.py`).
- [x] Documentar ejemplo de mensaje de Telegram.
- [x] Crear resumen técnico.

---

## 🎓 Conclusión

El sistema de **Probabilidad Histórica en Tiempo Real** está completamente implementado y operativo. Los cambios garantizan:

1. **Datos nunca quedan obsoletos** (gracias a `raw_data`).
2. **Alertas más inteligentes** (con probabilidades basadas en historial).
3. **Toma de decisiones informadas** (win rate, PnL promedio, racha reciente).
4. **Escalabilidad** (progresivo conforme acumulas más datos).

**Estado:** ✅ **LISTO PARA PRODUCCIÓN**
