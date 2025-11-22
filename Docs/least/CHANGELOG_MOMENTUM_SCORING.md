# CHANGELOG - Sistema de Momentum Scoring para Opciones Binarias

**Fecha:** 22 de noviembre de 2025  
**Tipo:** Actualización Crítica - Optimización para Opciones Binarias  
**Afecta:** Sistema de análisis de tendencia y scoring de EMAs

---

## 📋 Resumen Ejecutivo

Se ha **reoptimizado el algoritmo de scoring** de tendencia para adaptarlo específicamente a **OPCIONES BINARIAS con velas de 1 minuto**. El sistema ahora prioriza el **momentum de corto plazo** sobre la tendencia macro, permitiendo operaciones contra-tendencia cuando hay fuerza inmediata.

---

## 🔄 Cambios en el Algoritmo de Scoring

### Versión Anterior (Trend-Focused)

**Filosofía:** "No operar contra la tendencia macro de EMA 200"

| Regla | Peso | Prioridad |
|-------|------|-----------|
| Precio vs EMA 200 | ±3 pts | 🔴 MÁXIMA |
| Precio vs EMA 100 | ±2 pts | 🟡 ALTA |
| EMA 50 vs EMA 200 | ±2 pts | 🟡 ALTA |
| Precio vs EMA 20 | ±2 pts | 🟡 ALTA |
| EMA 20 vs EMA 50 | ±1 pt | 🟢 MEDIA |

**Total posible:** ±10 puntos

---

### Versión Actual (Momentum-Focused)

**Filosofía:** "Priorizar momentum inmediato - EMA 200 es solo contexto"

| Regla | Peso | Prioridad | Cambio |
|-------|------|-----------|--------|
| Precio vs EMA 20 | **±4 pts** | 🔴 CRÍTICA | +2 pts (2x) |
| EMA 20 vs EMA 50 | **±3 pts** | 🔴 CRÍTICA | +2 pts (3x) |
| Precio vs EMA 50 | ±2 pts | 🟡 MEDIA | Sin cambio |
| Precio vs EMA 200 | **±1 pt** | 🟢 BAJA | -2 pts (÷3) |
| ~~Precio vs EMA 100~~ | ~~Eliminada~~ | - | -2 pts |
| ~~EMA 50 vs EMA 200~~ | ~~Eliminada~~ | - | -2 pts |

**Total posible:** ±10 puntos (distribuidos de forma distinta)

---

## 📊 Impacto en la Distribución del Score

### Ejemplo 1: Momentum Alcista Fuerte (Contra Tendencia Macro)

**Escenario:**
```
Precio: 1.08650
EMA 20: 1.08600 (precio ARRIBA) ✓
EMA 50: 1.08550 (precio ARRIBA) ✓
EMA 200: 1.08700 (precio DEBAJO) ✗
```

| Versión | Cálculo | Score | Clasificación | ¿Alerta? |
|---------|---------|-------|---------------|----------|
| **Anterior** | +2 -3 +2 +1 = **+2** | +2 | WEAK_BULLISH | ⚠️ Débil |
| **Actual** | **+4 +3 +2 -1** = **+8** | +8 | **STRONG_BULLISH** | ✅ Fuerte |

**Interpretación:**
- ✅ **Actual:** "Momentum alcista MUY FUERTE - válido para CALL"
- ❌ **Anterior:** "Tendencia débil por macro bajista - dudar"

---

### Ejemplo 2: Retroceso en Tendencia Alcista

**Escenario:**
```
Precio: 1.08650
EMA 20: 1.08700 (precio DEBAJO) ✗
EMA 50: 1.08600 (precio ARRIBA) ✓
EMA 200: 1.08500 (precio ARRIBA) ✓
```

| Versión | Cálculo | Score | Clasificación | ¿Alerta? |
|---------|---------|-------|---------------|----------|
| **Anterior** | +3 +2 +2 -2 +1 = **+6** | +6 | STRONG_BULLISH | ✅ Fuerte |
| **Actual** | **-4 +2 +1** = **-1** | -1 | **NEUTRAL** | ⚠️ Evitar |

**Interpretación:**
- ✅ **Actual:** "Momentum inmediato bajista - esperar confirmación"
- ❌ **Anterior:** "Tendencia fuerte por macro - ignorar retroceso temporal"

---

## 🎯 Justificación del Cambio

### ¿Por qué priorizar corto plazo en opciones binarias?

1. **Ventana de tiempo reducida (1-5 minutos):**
   - En opciones binarias, operamos con expiración de 1-5 minutos
   - La tendencia macro (EMA 200 = 200 minutos) no es relevante para ventanas tan cortas
   - Lo que importa es el momentum **inmediato** (próximos 1-3 minutos)

2. **Reversiones rápidas:**
   - En 1 minuto, un patrón de reversión puede ejecutarse completamente antes de que la macro se manifieste
   - Un Hammer en macro bajista puede generar rebote de 10-20 pips en 2 minutos (suficiente para binarias)

3. **Reducción de falsos negativos:**
   - Sistema anterior rechazaba patrones válidos por estar contra-tendencia macro
   - Sistema actual captura oportunidades de reversión de corto plazo

4. **Alineado con estrategia de 50% Fibonacci:**
   - Buscamos retroceso del 50% en los primeros 30s de la siguiente vela
   - Este movimiento ocurre en el dominio de EMA 20/50, NO de EMA 200

---

## 📝 Archivos Modificados

### Código (Sin cambios)
- `src/logic/analysis_service.py` - Ya implementaba el nuevo algoritmo
- Sistema estaba correcto, faltaba actualizar documentación

### Documentación Actualizada
1. **`Docs/tendencia.md`**
   - ✅ Sección "Algoritmo de Scoring" reescrita con 4 reglas y nuevos pesos
   - ✅ Tabla de EMAs actualizada con prioridades (CRÍTICA/MEDIA/BAJA)
   - ✅ Ejemplos de cálculo actualizados con nuevos scores
   - ✅ Banner de actualización en el encabezado

2. **`Docs/resumen.md`**
   - ✅ Sección 4.1 "Sistema de Trend Scoring" → "Sistema de Momentum Scoring"
   - ✅ Tabla de EMAs con nueva columna "Uso en Score"
   - ✅ Algoritmo de scoring con 4 reglas en vez de 5
   - ✅ Clasificación con interpretaciones de "momentum" vs "tendencia"
   - ✅ Eliminado "⚠️ SUJETO A CAMBIOS" (sistema validado)

---

## ✅ Validación de Consistencia

### Código vs Documentación - Estado Actual

| Componente | Código | Documentación | Estado |
|------------|--------|---------------|--------|
| EMA 20 (Precio) | ±4 pts | ±4 pts | ✅ SYNC |
| EMA 20 vs 50 | ±3 pts | ±3 pts | ✅ SYNC |
| EMA 50 (Precio) | ±2 pts | ±2 pts | ✅ SYNC |
| EMA 200 (Precio) | ±1 pt | ±1 pt | ✅ SYNC |
| EMA 100 | No usado | No usado | ✅ SYNC |
| Clasificación | 5 niveles | 5 niveles | ✅ SYNC |
| Filosofía | Momentum | Momentum | ✅ SYNC |

---

## 🚀 Próximos Pasos Recomendados

### 1. Validación en Producción
- Trackear win rate por rango de score:
  - Score ≥6 (STRONG): ¿Cuántos generan profit?
  - Score 2-5 (WEAK): ¿Cuántos son breakeven?
  - Score ≤-6: ¿Cuántos PUT funcionan?

### 2. Análisis de Patrones
- Correlacionar score con éxito del patrón:
  - Hammer con score +8: ¿Mayor win rate que +3?
  - Shooting Star con score -9: ¿Mejor que -4?

### 3. Optimización Futura
- Si score alto pero win rate bajo:
  - Considerar agregar volumen como factor
  - Ajustar pesos (ej: EMA 20 de ±4 a ±5)
- Si score bajo pero win rate alto:
  - Reducir umbral STRONG_BULLISH de ≥6 a ≥5

### 4. Dashboard de Métricas
- Implementar `logs/momentum_stats.jsonl`:
  ```json
  {
    "timestamp": "2025-11-22T14:30:00Z",
    "score": 8,
    "pattern": "HAMMER",
    "outcome": "WIN",
    "pnl_pips": 15.2
  }
  ```

---

## 📚 Referencias

- **Código:** `src/logic/analysis_service.py` (líneas 88-177)
- **Docs Detallada:** `Docs/tendencia.md`
- **Resumen General:** `Docs/resumen.md` (Sección 4.1)
- **Testing:** `test/test_candles.py` (no requiere cambios)

---

**Firma:** Documentación sincronizada con código ✅  
**Autor:** TradingView Pattern Monitor Team  
**Última actualización:** 22 de noviembre de 2025
