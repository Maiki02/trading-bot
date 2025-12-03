# Sistema de Análisis de Tendencia - Slope & Structure (V7.1)

## Descripción General
Sistema de clasificación de tendencia optimizado para **ESTRATEGIAS DE REVERSIÓN**. A diferencia de sistemas tradicionales que buscan "fuerza máxima", este algoritmo (V7.1) está diseñado para detectar la **FASE DE LA TENDENCIA**, identificando momentos de "Agotamiento de Momentum" ideales para operar en contra.

**Fecha de Implementación:** 03 de Diciembre de 2025  
**Versión:** v7.1 - Reversion Logic (Slope %)

---

## Indicadores Utilizados

### EMAs Clave (V7.1)
| EMA | Periodo | Función | Rol en Score |
|-----|---------|---------|--------------|
| **EMA 3** | 3 velas | **Gatillo de Velocidad** | Detecta Agotamiento (Flattening) y Pausas |
| **EMA 5** | 5 velas | **Confirmación Rápida** | Soporte de velocidad inmediata |
| **EMA 20** | 20 velas | **Estructura Base** | Define Dirección Macro y Alineación |

**Total Máximo de Puntos:** 10.0

---

## Algoritmo V7.1 (Fases de Tendencia)

El score se compone de 3 vectores:

### 1. ESTRUCTURA (Max 3.0 pts)
Verifica la "salud geométrica" de la tendencia.
- **Alcista (+3.0):** EMA 3 > EMA 5 > EMA 20
- **Bajista (-3.0):** EMA 3 < EMA 5 < EMA 20
- **Rango (0.0):** Desorden

### 2. VELOCIDAD BASE (Max 2.0 pts)
Mide la inclinación de la EMA 20 para definir la dirección de fondo.
- **Slope % EMA 20 > Threshold:** +2.0
- **Slope % EMA 20 < -Threshold:** -2.0

### 3. MOMENTUM & AGOTAMIENTO (Max 5.0 pts)
Aquí reside la inteligencia del sistema. Premia la velocidad pero **PENALIZA el aplanamiento**.

**Slope Porcentual:**
La pendiente se calcula como porcentaje de cambio: `(EMA_Actual - EMA_Prev) / EMA_Prev`.
Esto normaliza la medición para cualquier activo (Forex, Crypto, Stocks).

**Lógica de Penalización (Flattening):**
- Si la tendencia es ALCISTA y el Slope de EMA 3 disminuye (se aplana) -> **PENALIZACIÓN**.
- Detecta pausas de 2-3 velas que suelen preceder a una reversión o continuación.
- **Objetivo:** Bajar el Score de "STRONG" (+10) a "WEAK" (+6) justo cuando el precio se detiene, habilitando la señal de reversión.

---

## Interpretación del Score para Reversión

| Score Range | Estado | Interpretación | Acción Sugerida |
|-------------|--------|----------------|-----------------|
| **[+8.0 a +10.0]** | **STRONG_BULLISH** | Momentum Fuerte | ⛔ **NO OPERAR CONTRA.** Esperar. |
| **[+5.0 a +7.9]** | **WEAK_BULLISH** | **Agotamiento** | ✅ **ZONA IDEAL.** Buscar Patrón de Reversión (Shooting Star). |
| **[-4.9 a +4.9]** | **NEUTRAL** | Rango / Ruido | ⚠️ Precaución. Falta dirección clara. |
| **[-7.9 a -5.0]** | **WEAK_BEARISH** | **Agotamiento** | ✅ **ZONA IDEAL.** Buscar Patrón de Reversión (Hammer). |
| **[-10.0 a -8.0]** | **STRONG_BEARISH** | Momentum Fuerte | ⛔ **NO OPERAR CONTRA.** Esperar. |

---

## Configuración Técnica

### Slope Threshold (Porcentual)
Valor base sugerido: `0.0001` (0.01%).
- Si el cambio porcentual de la EMA es menor a este umbral, se considera "plana".

### Penalización
- Si `Slope EMA 3 < Threshold` en tendencia alcista: Resta 2.0 puntos.
- Si `Slope EMA 3 > -Threshold` en tendencia bajista: Suma 2.0 puntos (acerca a 0).

---

## Visualización
El gráfico debe mostrar claramente la EMA 3, 5 y 20. La EMA 3 es la "línea de vida" del precio; si se aplana, alerta visual.
