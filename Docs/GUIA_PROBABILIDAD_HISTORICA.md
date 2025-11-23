# 🚀 Sistema de Probabilidad Histórica - Guía de Inicio Rápido

## ✅ ¿Qué se implementó?

Un sistema completo que:

1. **Almacena datos crudos** (`raw_data`) en el dataset para poder recalcular scores retroactivamente.
2. **Calcula probabilidades históricas** en tiempo real basadas en patrones y scores similares.
3. **Muestra estadísticas** en alertas de Telegram (win rate, PnL promedio, racha reciente).

---

## 📦 Archivos Modificados/Creados

### Nuevos Archivos
- `src/services/statistics_service.py` - Servicio de análisis de probabilidad
- `test_statistics_service.py` - Script de prueba del sistema
- `migrate_add_raw_data.py` - Script de migración (opcional)
- `Docs/sistema_probabilidad_historica.md` - Documentación técnica completa
- `Docs/ejemplo_mensaje_telegram_con_probabilidad.md` - Ejemplos visuales

### Archivos Modificados
- `src/services/storage_service.py` - Validación de `raw_data` obligatorio
- `src/logic/analysis_service.py` - Consulta de estadísticas y agregado de `raw_data`
- `src/services/telegram_service.py` - Bloque de estadísticas en mensajes
- `main.py` - Integración de StatisticsService
- `src/services/__init__.py` - Export de StatisticsService

---

## 🏃 Cómo Ejecutar

### Paso 1: Instalar Dependencias (si es necesario)

El sistema usa pandas (ya debería estar instalado):

```bash
pip install pandas
```

### Paso 2: Ejecutar el Bot

```bash
python main.py
```

El sistema ahora:
- Guarda `raw_data` en cada registro JSONL.
- Consulta estadísticas históricas antes de emitir alertas.
- Muestra probabilidades en mensajes de Telegram (si hay >5 casos).

### Paso 3: Probar el Sistema de Estadísticas (Opcional)

Ejecuta el script de prueba para verificar que funcione correctamente:

```bash
python test_statistics_service.py
```

Esto mostrará:
- Resumen del dataset.
- Probabilidades por patrón y score.
- Distribución de scores recalculados.

### Paso 4: Migrar Registros Antiguos (Opcional)

Si tienes registros antiguos sin `raw_data`, puedes ejecutar:

```bash
python migrate_add_raw_data.py
```

⚠️ **IMPORTANTE:** Este script crea un backup automático antes de modificar.

Los registros migrados tendrán `raw_data` con valores `None` para EMAs (no disponibles en registros antiguos). El `StatisticsService` los ignorará al recalcular scores.

---

## 📊 Ejemplo de Alerta con Estadísticas

Cuando el sistema tenga suficientes datos históricos (>5 casos similares), las alertas de Telegram incluirán:

```
🔴 ALERTA FUERTE | BTCUSDT
Alta probabilidad de apertura BAJISTA

━━━━━━━━━━━━━━━━━━━━━━━━
📊 INFORMACIÓN DE LA VELA
━━━━━━━━━━━━━━━━━━━━━━━━
🔹 Fuente: BINANCE
🔹 Patrón: SHOOTING_STAR
🔹 Timestamp: 2025-11-23 01:47:00
...

━━━━━━━━━━━━━━━━━━━━━━━━
📊 PROBABILIDAD HISTÓRICA (Últimos 30 días)
━━━━━━━━━━━━━━━━━━━━━━━━
🟢 Win Rate: 73.3% (11/15 señales)
🎯 PnL Promedio: 245.7 pips
📈 Racha reciente: ✓ ✓ ✗ ✓ ✓
🔍 Score similar: [9, 11]

⚡ IMPORTANTE: Verificar gráfico y contexto de mercado antes de operar.
```

Ver `Docs/ejemplo_mensaje_telegram_con_probabilidad.md` para más ejemplos.

---

## 🔧 Configuración Avanzada

### Cambiar Umbral de Datos Mínimos

Por defecto, las estadísticas se muestran solo si hay **más de 5 casos** similares.

Para cambiar esto, modifica en `src/services/telegram_service.py`:

```python
if signal.statistics and signal.statistics.get("total_cases", 0) > 5:
    # Cambiar 5 por el número deseado (ej: 10)
```

### Ajustar Ventana de Tiempo

Por defecto, se analizan los **últimos 30 días**.

Para cambiar esto, modifica en `src/logic/analysis_service.py`:

```python
statistics = self.statistics_service.get_probability(
    pattern=pattern_detected,
    current_score=trend_analysis.score,
    lookback_days=30,  # Cambiar aquí
    score_tolerance=1
)
```

### Ajustar Tolerancia de Score (Fuzzy Matching)

Por defecto, busca scores **±1** del actual.

Para cambiar esto, modifica en `src/logic/analysis_service.py`:

```python
statistics = self.statistics_service.get_probability(
    pattern=pattern_detected,
    current_score=trend_analysis.score,
    lookback_days=30,
    score_tolerance=1  # Cambiar aquí (ej: 2 para ±2)
)
```

---

## 📚 Documentación Completa

- **Resumen Técnico:** `Docs/sistema_probabilidad_historica.md`
- **Ejemplos de Mensajes:** `Docs/ejemplo_mensaje_telegram_con_probabilidad.md`

---

## ❓ FAQ

### ¿Por qué las estadísticas no aparecen en las alertas?

**Respuesta:** Puede ser por:
1. No hay suficientes datos históricos (≤5 casos similares).
2. El patrón/score actual no tiene coincidencias en los últimos 30 días.
3. El dataset está vacío o no existe.

**Solución:** Deja que el bot acumule más datos.

### ¿Qué pasa si cambio la lógica de `analyze_trend`?

**Respuesta:** El sistema recalculará automáticamente los scores históricos usando los datos de `raw_data`. No perderás el historial.

### ¿Los registros antiguos (sin `raw_data`) afectan las estadísticas?

**Respuesta:** Si ejecutaste el script de migración, los registros antiguos tendrán `raw_data` con valores `None` para EMAs. El `StatisticsService` los detectará y **no los usará** para recalcular scores. Solo los registros nuevos (con EMAs completas) se usarán para análisis de probabilidad.

### ¿Puedo deshabilitar las estadísticas en mensajes?

**Respuesta:** Sí, modifica en `src/services/telegram_service.py`:

```python
# Cambiar esto:
if signal.statistics and signal.statistics.get("total_cases", 0) > 5:

# Por esto:
if False:  # Nunca mostrará estadísticas
```

---

## 🎯 Próximos Pasos Sugeridos

1. **Ejecutar el bot** para acumular datos con `raw_data`.
2. **Monitorear alertas** y verificar que las estadísticas aparezcan correctamente.
3. **Ajustar umbrales** según preferencia (total_cases, lookback_days, score_tolerance).
4. **Análisis avanzado** (futuro): Entrenar modelos ML para predicción de probabilidad.

---

## ✅ Estado

**Sistema:** ✅ **OPERATIVO Y LISTO PARA PRODUCCIÓN**

**Próxima ejecución:** El bot empezará a guardar `raw_data` automáticamente en cada señal detectada.

---

## 🆘 Soporte

Si encuentras algún problema:

1. Verifica los logs del bot.
2. Ejecuta `test_statistics_service.py` para diagnosticar.
3. Revisa la documentación técnica en `Docs/sistema_probabilidad_historica.md`.

¡Listo para operar! 🚀
