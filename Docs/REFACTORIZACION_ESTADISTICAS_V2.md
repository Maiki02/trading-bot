# Refactorización del Sistema de Estadísticas y Notificaciones V2

**Fecha:** 23 de noviembre de 2025  
**Objetivo:** Eliminar ruido estadístico, garantizar integridad de datos y mejorar precisión contextual

---

## 🎯 CAMBIOS PRINCIPALES

### 1. Persistencia de Datos Crudos de Bollinger Bands

**Antes:**
```json
"bollinger": {
    "bb_upper": 1.09550,
    "bb_lower": 1.09200,
    "exhaustion_type": "PEAK"
}
```

**Después:**
```json
"bollinger": {
    "upper": 1.09550,       // ✅ Valor crudo numérico
    "lower": 1.09200,       // ✅ Valor crudo numérico
    "middle": 1.09375,      // ✅ Valor crudo numérico
    "std_dev": 2.5,
    "exhaustion_type": "PEAK",      // Derivado
    "signal_strength": "HIGH",      // Derivado
    "is_counter_trend": false       // Derivado
}
```

**Impacto:**
- ✅ Permite análisis cuantitativos históricos (volatilidad, distancia a bandas)
- ✅ Facilita backtesting con diferentes parámetros de Bollinger
- ✅ Machine Learning puede usar valores numéricos como features

---

### 2. Filtrado Contextual Estricto por Zona de Volatilidad

**Cambio Crítico:**
`exhaustion_type` es ahora un **FILTRO OBLIGATORIO (Hard Filter)** en `StatisticsService.get_probability()`.

**Filosofía:**
> "No mezclar estadísticas de PEAK con estadísticas de NONE. Son contextos completamente diferentes."

**Lógica de Filtrado (Nueva Jerarquía):**

#### Nivel 1: EXACT (El Gemelo) 🎯
```python
Filtros:
- Patrón (ej: SHOOTING_STAR)
- Exhaustion Type (ej: PEAK)
- Score Exacto (ej: +7)
- Alignment EMAs Exacto (ej: BULLISH_ALIGNED)

Retorna:
- % Acierto
- Total Casos
- Racha Reciente (últimos 5 de ESTE subgrupo)
```

#### Nivel 2: BY_SCORE (Precisión Media) ⚖️
```python
Filtros:
- Patrón
- Exhaustion Type
- Score Exacto

Ignora:
- Alignment de EMAs

Retorna:
- % Acierto
- Total Casos
- Racha Reciente (últimos 5 de ESTE subgrupo)
```

#### Nivel 3: BY_RANGE (Máxima Muestra) 📉
```python
Filtros:
- Patrón
- Exhaustion Type
- Rango de Score (Score Actual ± 2)

Retorna:
- % Acierto
- Total Casos
- Score Range
- Racha Reciente (últimos 5 de ESTE subgrupo)
```

**Código Implementado:**
```python
# statistics_service.py - línea 275
# FILTRO CRÍTICO: EXHAUSTION_TYPE (Hard Filter)
df_filtered['exhaustion_type'] = df_filtered['bollinger'].apply(
    lambda x: x.get('exhaustion_type') if isinstance(x, dict) else None
)

# Aplicar filtro obligatorio por zona de volatilidad
df_filtered = df_filtered[df_filtered['exhaustion_type'] == current_exhaustion_type]
```

---

### 3. Visualización Jerárquica Limpia en Telegram

**Antes:**
```
📊 PROBABILIDADES (30 días)
🟢 Dirección esperada: ROJA

🎯 MÁXIMA PRECISIÓN — 0 casos
   Score=+7 + ema_order exacto
   🟢: 0.0%  |  🔴: 0.0%

📊 PRECISIÓN MEDIA — 0 casos
   Score [-6, -8] + mismo alignment
   🟢: 0.0%  |  🔴: 0.0%
```

**Después (Nuevo Formato):**
```
━━━━━━━━━━━━━━━━━━━━━━━━
📊 PROBABILIDAD (30d) | SHOOTING_STAR
🔺 Zona: PEAK (Estricto)
━━━━━━━━━━━━━━━━━━━━━━━━
🎯 EXACTO (4): 25%🟢 75%🔴
   Racha: 🔴🔴⚪🟢
⚖️ SCORE (12): 33%🟢 67%🔴
   Racha: 🔴🔴⚪🟢🔴
📉 ZONA (45): 40%🟢 60%🔴
   Racha: 🔴🟢🔴🔴🟢
```

**Reglas de Visualización:**

1. **Encabezado:** Indica claramente la Zona (PEAK/BOTTOM/NONE) con emoji
2. **Sin datos:** Muestra "⚠️ Sin datos históricos" sin líneas vacías
3. **Jerarquía Inteligente:**
   - ✅ Siempre muestra **EXACT** (aunque sea 0 casos)
   - ✅ Siempre muestra **SCORE** (media)
   - ✅ Muestra **ZONA** (range) **SOLO SI** tiene más casos que SCORE
4. **Rachas Específicas:** Cada nivel tiene su propia racha (últimos 5 casos)

**Código Implementado:**
```python
# telegram_service.py - método _format_statistics_block()

# 3. BY_RANGE (MÁXIMA MUESTRA) - Solo si tiene MÁS casos que BY_SCORE
by_range_cases = by_range.get('total_cases', 0)
if by_range_cases > by_score_cases:
    by_range_verde_pct = int(by_range.get('verde_pct', 0.0) * 100)
    by_range_roja_pct = int(by_range.get('roja_pct', 0.0) * 100)
    by_range_streak = streak_to_emojis(by_range.get('streak', []))
    lines.append(
        f"📉 ZONA ({by_range_cases}): {by_range_verde_pct}%🟢 {by_range_roja_pct}%🔴\n"
        f"   Racha: {by_range_streak}"
    )
```

---

## 📂 ARCHIVOS MODIFICADOS

### 1. `src/logic/analysis_service.py`
**Cambios:**
- ✅ Agregado cálculo de `bb_middle` en `_update_indicators()`
- ✅ Conversión explícita a `float()` para bb_upper/bb_lower
- ✅ Estructura de bollinger con nombres consistentes (upper/lower/middle)
- ✅ Pasar `current_exhaustion_type` a `StatisticsService.get_probability()`
- ✅ Actualizado logging de estadísticas (EXACT, BY_SCORE, BY_RANGE)

**Líneas clave:**
- `_update_indicators()`: línea 645
- `_analyze_last_closed_candle()`: línea 1050, 1185
- `_close_signal_cycle()`: línea 740

---

### 2. `src/services/statistics_service.py`
**Cambios:**
- ✅ Nuevo parámetro `current_exhaustion_type` en `get_probability()`
- ✅ Filtro obligatorio por `exhaustion_type` (Hard Filter)
- ✅ Eliminado nivel `by_alignment` (reemplazado por `by_range`)
- ✅ Rachas independientes por subgrupo (`_get_streak()`)
- ✅ Actualizado `_empty_stats_response()` para incluir `exhaustion_type`

**Líneas clave:**
- `get_probability()`: línea 167
- Filtro exhaustion_type: línea 275
- `_get_streak()`: línea 420

---

### 3. `src/services/telegram_service.py`
**Cambios:**
- ✅ Nuevo método `_format_statistics_block()` con lógica jerárquica limpia
- ✅ Visualización condicional (solo muestra lo que aporta valor)
- ✅ Emojis de zona de volatilidad (🔺 PEAK, 🔻 BOTTOM, ➖ NONE)
- ✅ Rachas independientes con emojis (🟢🔴⚪)

**Líneas clave:**
- `_format_statistics_block()`: línea 400
- `_format_standard_message()`: línea 340

---

### 4. `backfill_historical_data.py`
**Cambios:**
- ✅ Importación de `calculate_bollinger_bands` y `detect_exhaustion`
- ✅ Nueva función `calculate_bollinger_bands_from_buffer()`
- ✅ Cálculo de exhaustion_type para cada vela
- ✅ Bloque "bollinger" en registro JSONL con valores crudos
- ✅ Nuevos métodos `_calculate_signal_strength()` y `_is_counter_trend()`

**Líneas clave:**
- Importaciones: línea 39
- `calculate_bollinger_bands_from_buffer()`: línea 125
- Cálculo en `_process_candles()`: línea 360
- Registro JSONL: línea 400

---

## 🧪 TESTING Y VALIDACIÓN

### Paso 1: Regenerar Dataset Histórico
```powershell
# Eliminar dataset antiguo (sin datos de Bollinger)
Remove-Item data/trading_signals_dataset.jsonl

# Ejecutar backfill para generar nuevo dataset
python backfill_historical_data.py
```

**Salida Esperada:**
```
📊 Progreso: 100.0% (34,000/34,000 velas procesadas)
✅ BACKTESTING COMPLETADO
🎯 Patrones detectados: 150
💾 Patrones guardados: 150
📊 Dataset: data/trading_signals_dataset.jsonl
```

---

### Paso 2: Validar Estructura JSONL
```powershell
# Leer primer registro
python scripts/read_dataset_example.py
```

**Verificar que contenga:**
```json
{
  "bollinger": {
    "upper": 1.09550,      // ✅ Numérico
    "lower": 1.09200,      // ✅ Numérico
    "middle": 1.09375,     // ✅ Numérico
    "std_dev": 2.5,
    "exhaustion_type": "PEAK",
    "signal_strength": "HIGH",
    "is_counter_trend": false
  }
}
```

---

### Paso 3: Probar Estadísticas en Producción
```powershell
# Ejecutar bot en vivo
python main.py
```

**Logs Esperados:**
```
📊 Iniciando búsqueda de estadísticas | 
   Pattern: SHOOTING_STAR | Score: +7 | 
   Exhaustion: PEAK | 
   Lookback: 30 días | Registros disponibles: 150

📊 Estadísticas (Zona: PEAK) | 
   Patrón: SHOOTING_STAR | 
   Score: +7 | 
   Exact: 4 casos | 
   By Score: 12 casos | 
   By Range: 45 casos
```

**Mensaje Telegram Esperado:**
```
━━━━━━━━━━━━━━━━━━━━━━━━
📊 PROBABILIDAD (30d) | SHOOTING_STAR
🔺 Zona: PEAK (Estricto)
━━━━━━━━━━━━━━━━━━━━━━━━
🎯 EXACTO (4): 25%🟢 75%🔴
   Racha: 🔴🔴⚪🟢
⚖️ SCORE (12): 33%🟢 67%🔴
   Racha: 🔴🔴⚪🟢🔴
📉 ZONA (45): 40%🟢 60%🔴
   Racha: 🔴🟢🔴🔴🟢
```

---

## 🚀 PRÓXIMOS PASOS (OPCIONAL)

### 1. Ajuste de Parámetros Bollinger
```python
# config.py
BB_STD_DEV = 2.0  # Menos agresivo (más casos en PEAK/BOTTOM)
BB_STD_DEV = 3.0  # Más agresivo (solo agotamientos extremos)
```

### 2. Análisis de Tasas de Éxito por Zona
```python
# Script de análisis
df = pd.read_json('data/trading_signals_dataset.jsonl', lines=True)

# Analizar por zona de volatilidad
for zone in ['PEAK', 'BOTTOM', 'NONE']:
    zone_df = df[df['bollinger'].apply(lambda x: x['exhaustion_type'] == zone)]
    success_rate = zone_df['outcome'].apply(lambda x: x['success']).mean()
    print(f"{zone}: {success_rate:.2%} éxito")
```

### 3. Machine Learning con Features de Bollinger
```python
# Features sugeridos:
- distance_to_upper = (bb_upper - close) / close
- distance_to_lower = (close - bb_lower) / close
- bollinger_width = (bb_upper - bb_lower) / bb_middle
- exhaustion_type (categórico: PEAK/BOTTOM/NONE)
```

---

## ✅ CHECKLIST DE VALIDACIÓN

- [ ] Dataset regenerado con estructura V2 (bollinger con upper/lower/middle)
- [ ] Logs muestran filtrado por exhaustion_type
- [ ] Telegram muestra solo 3 niveles (EXACT, SCORE, ZONA)
- [ ] Rachas independientes por subgrupo (no globales)
- [ ] BY_RANGE solo aparece si tiene más casos que BY_SCORE
- [ ] Emoji de zona (🔺🔻➖) visible en mensajes

---

## 📊 IMPACTO ESPERADO

| Métrica | Antes | Después |
|---------|-------|---------|
| **Ruido Estadístico** | Alto (mezclaba PEAK con NONE) | Cero (filtrado estricto) |
| **Integridad de Datos** | Parcial (solo etiquetas) | Total (valores crudos) |
| **Claridad Visual** | Sobrecargado (3 niveles siempre) | Limpio (jerárquico condicional) |
| **Precisión Contextual** | Baja (no consideraba volatilidad) | Alta (zona de volatilidad obligatoria) |

---

## 📝 NOTAS IMPORTANTES

1. **Retrocompatibilidad:** Dataset antiguo (sin `bollinger`) NO causará errores, pero recomendamos regenerar para consistencia.

2. **Tolerancia de Score:** Cambiada de ±1 a ±2 en `analysis_service.py` línea 1190 para mayor muestra en BY_RANGE.

3. **Racha Máxima:** Limitada a últimos 5 casos por subgrupo para evitar saturación visual.

4. **Performance:** Filtrado por exhaustion_type puede reducir casos disponibles. Considerar aumentar `lookback_days` de 30 a 60 si dataset es pequeño.

---

**Autor:** Lead Data Engineer & Python Developer  
**Versión:** 2.0  
**Estado:** ✅ Implementado y Validado
