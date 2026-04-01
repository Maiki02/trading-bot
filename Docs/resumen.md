# Resumen

## 1. Objetivo del Proyecto
Integrar un monitor automatizado 24/7 que capture datos de mercado en tiempo real de IQ OPTION, TradingView o Quotex mediante ingeniería inversa de WebSocket y librerías especializadas. El sistema identificará patrones de velas japonesas en temporalidad de 1 minuto y, al detectar una configuración válida alineada con la tendencia, enviará alertas inmediatas vía Telegram con gráfico visual adjunto. **Adicionalmente, envía notificaciones de resultado** cuando cierra la vela siguiente, informando si el patrón tuvo éxito (VERDE/ROJA/DOJI).

### 1.0. Objetivo Versión 0.0.6 (Quotex Data Provider) 🆕
**Nueva Funcionalidad:** Integración de Quotex como tercer proveedor de datos de mercado.

**Cambios principales:**
- ✅ **QuotexServiceMulti:** Nuevo servicio `src/services/quotex_service_multi.py` que extiende `BaseMarketDataService` usando la librería `pyquotex` (API-Quotex).
- ✅ **Config:** `QuotexConfig` dataclass en `config.py` con validación de credenciales (`QUOTEX_EMAIL`, `QUOTEX_PASSWORD`).
- ✅ **Factory:** Caso `QUOTEX` registrado en `connection_service.py` → `get_market_data_service()`.
- ✅ **Async-Native:** Implementación 100% asíncrona sin necesidad de thread executors.
- ✅ **Sleep & Burst Polling:** Misma estrategia de polling que IQ Option para obtención de velas.
- ✅ **Arquitectura multi-cliente:** Instancia independiente de `_QuotexSymbolWorker` (con su propio cliente `Quotex`) por símbolo; arranque en paralelo mediante `asyncio.gather` y lifecycle completamente aislado por activo.
- ✅ **Verificación de disponibilidad:** Consulta `get_available_asset(force_open=False)` al arrancar; si el activo está cerrado, el worker queda inactivo sin bloquear los demás símbolos.

**Proveedor Quotex — Detalles técnicos:**
- **Librería:** `pyquotex` (GitHub: `https://github.com/Maiki02/pyquotex.git`).
- **Activación:** `DATA_PROVIDER=QUOTEX` en `.env`.
- **Desarrollo Local:** Bandera `USE_QUOTEX_LOCAL=true` en `.env` para priorizar la carpeta hermano `../pyquotex`.
- **Importación Centralizada:** Todas las importaciones deben hacerse desde `src.utils.quotex_bootstrap` para asegurar la conmutación correcta entre local/remoto.
- **Tag de fuente:** `"QX"` en el campo `source` de `CandleData`.
- **Naming de activos:** Quotex usa nombres como `"EURUSD"`, `"EURUSD_otc"` (variante OTC).
- **Transformación:** Los payloads crudos de Quotex se normalizan al modelo interno `Candle` antes del análisis.

**Filosofía:** Diversificar proveedores de datos reduce la dependencia de un solo broker y permite al trader elegir la fuente más conveniente según disponibilidad y latencia.

### 1.0.1. Objetivo Versión 0.0.5 (Trend Engine V7 & RSI Visualization)
**Nueva Funcionalidad:** Refactorización completa del motor de tendencias e integración visual de RSI.

**Cambios principales:**
- ✅ **Slope Porcentual:** Cálculo de pendiente como % de cambio `(curr - prev) / prev` para normalizar entre activos.
- ✅ **RSI 7 (Visualización):** Integración de RSI de 7 periodos con **gráfico dedicado** en el panel inferior y líneas de referencia (70/30).
- ✅ **Structure (Alineación):** Bonus por alineación perfecta (Fanning).
- ✅ **Penalización por Aplanamiento:** El Score BAJA si la EMA 3 pierde inclinación (pausas de 2-3 velas).
- ✅ **Nuevos Estados:** Clasificación más granular (Strong/Weak Bullish/Bearish + Neutral).

**Filosofía:** El precio siempre lidera. Usamos RSI 7 para detectar sobre-extensión visualmente y Slope de EMA 3 para el momentum inmediato.

Ver documentación completa en: `Docs/tendencia.md` y `Docs/rsi.md`

### 1.1. Objetivo Versión 0.0.4 (Sistema de Probabilidad Histórica en Tiempo Real)
**Nueva Funcionalidad:** Sistema de **Probabilidades Históricas** que consulta el dataset JSONL para mostrar win rate, PnL promedio y racha reciente en las alertas de Telegram.

**Cambios principales:**
- ✅ **StatisticsService** - Servicio de consulta de probabilidades históricas
- ✅ **Fuzzy Matching** - Busca señales con score similar (±1 tolerancia)
- ✅ **Raw Data Preservation** - Campo `raw_data` en JSONL permite recalcular scores retroactivamente
- ✅ **Alertas Enriquecidas** - Win rate, PnL promedio, racha reciente mostrados en tiempo real
- ✅ **Dockerización Completa** - Dockerfile + docker-compose.yml con logs rotativos y volúmenes persistentes

**Filosofía:** No todas las señales tienen la misma probabilidad de éxito. Consultar el historial de señales similares (mismo patrón + score similar) permite tomar decisiones más informadas basadas en datos reales.

Ver documentación completa en: `Docs/sistema_probabilidad_historica.md`

### 1.2. Objetivo Versión 0.0.3 (Sistema de Agotamiento de Volatilidad)
**Funcionalidad:** Sistema de **Clasificación de Fuerza de Señal** basado en **Bollinger Bands** para filtrar señales de alta calidad.

**Cambios principales:**
- ✅ **Bollinger Bands (BB_PERIOD=20, BB_STD_DEV=2.0)** - Detección de agotamiento de tendencia
- ✅ **Signal Strength Classification** - HIGH (🚨), MEDIUM (⚠️), LOW (ℹ️)
- ✅ **Exhaustion Type Detection** - PEAK (Cúspide), BOTTOM (Base), NONE (Zona Neutra)
- ✅ **Counter-Trend Filtering** - Patrones contra-tendencia clasificados como LOW
- ✅ **Dataset Enrichment** - Nuevos campos `bollinger` en JSONL para ML
- ✅ **Enhanced Notifications** - Alertas Telegram con zona de Bollinger

**Filosofía:** No todos los patrones tienen la misma probabilidad de éxito. Los patrones detectados en zonas de agotamiento extremo (Cúspide o Base de Bollinger) tienen mayor fidelidad que los detectados en zona neutra.

**Matriz de Clasificación:**
- **SHOOTING_STAR en PEAK (tendencia alcista):** `signal_strength = HIGH` 🚨🚨
- **HAMMER en BOTTOM (tendencia bajista):** `signal_strength = HIGH` 🚨🚨
- **INVERTED_HAMMER en PEAK:** `signal_strength = MEDIUM` ⚠️
- **HANGING_MAN en BOTTOM:** `signal_strength = MEDIUM` ⚠️
- **Patrones en zona neutra:** `signal_strength = LOW` ℹ️
- **Patrones contra-tendencia:** `signal_strength = LOW` ℹ️

Ver documentación completa en: `Docs/BOLLINGER_EXHAUSTION_SYSTEM.md`

### 1.3. Objetivo Versión 0.0.2 (MVP Completado) ✅
El MVP ha sido completado exitosamente con todas las funcionalidades core implementadas:
- **Par:** EUR/USD monitoreado en tiempo real.
- **Fuente de Datos:** FX:EURUSD (Feed público de TradingView - **NO requiere autenticación**).
- **Patrones:** Detección de los **4 patrones principales para MVP**:
  - ✅ Shooting Star (Estrella Fugaz)
  - ✅ Hanging Man (Hombre Colgado)
  - ✅ Inverted Hammer (Martillo Invertido)
  - ✅ Hammer (Martillo)
- **Testing:** Sistema de pruebas automatizado implementado en `test/test_candles.py` con validación estricta de los 4 patrones, reporte de fidelidad matemática y mensajes de diagnóstico detallados.
- **Visualización:** 
  - Generación automática de gráficos con `mplfinance` codificados en Base64
  - **Nueva herramienta:** `test/visualize_patterns.py` para análisis visual de patrones detectados con validación de precisión
- **Notificaciones Duales:**
  - **Patrón detectado** (inmediato): Al identificar Shooting Star, Hammer, etc.
  - **Resultado de vela** (1 min después): Informa si fue VERDE, ROJA o DOJI
- **Modo de Operación:** Sistema configurado con `USE_TREND_FILTER=false`, notifica **cualquier patrón detectado sin filtro de tendencia**, delegando la decisión final al trader.
- **Estado:** ✅ **MVP OPERATIVO** - Sistema probado, estable y listo para monitoreo 24/7.

### 1.3. Cambios Críticos Implementados vs Plan Original

#### ✅ **Autenticación No Requerida (Cuenta Gratuita)**
- **Plan Original:** Usar `sessionid` de cuenta TradingView autenticada.
- **Implementación Real:** TradingView proporciona **datos en tiempo real sin autenticación** para instrumentos Forex.
- **Ventaja:** No hay riesgo de bloqueo de cuenta, no se requiere renovación de tokens, sistema completamente autónomo.
- **Variable `.env`:** `TV_SESSION_ID` ahora es opcional (valor: `not_required_for_public_data`).

#### 📊 **Generación Automática de Gráficos**
- **Nueva Funcionalidad:** Cada alerta incluye un gráfico de velas japonesas codificado en Base64.
- **Implementación:**
  - Biblioteca: `mplfinance==0.12.10b0` para generación profesional de gráficos financieros.
  - Estilo: Tema claro con fondo blanco, velas verdes (alcistas) y rojas (bajistas).
  - **EMAs Visualizadas:** Las 4 EMAs calculadas se muestran en el gráfico con colores diferenciados:
    * **EMA 200** (Cyan #00D4FF, grosor 2.0) - Tendencia macro
    * **EMA 50** (Verde #00FF80, grosor 1.5) - Corto plazo
    * **EMA 30** (Amarillo #FFFF00, grosor 1.2) - Momentum medio
    * **EMA 20** (Naranja #FF8000, grosor 1.0) - Momentum corto
  - **Leyenda Integrada:** Esquina superior izquierda muestra las EMAs disponibles con sus colores.
  - Lookback: **Cantidad de velas parametrizable** vía `CHART_LOOKBACK` (default: 30, recomendado: 20-30).
  - **Performance de Generación:**
    * Preparación de datos: 5-10 ms
    * Render matplotlib: 150-300 ms (con 4 EMAs)
    * Encoding Base64: 50-100 ms
    * **Tiempo total: ~220 ms** (ejecutado en hilo separado con `asyncio.to_thread()`)
  - Ejecución: Generación en **hilo separado** para no bloquear WebSocket.
  - Tamaño: ~120-150 KB imagen PNG → ~160-200 KB en Base64 (con CHART_LOOKBACK=100).
  - Envío: Integrado en notificaciones de Telegram como `image_base64` en el payload.
- **Control de Costos:** Variable `SEND_CHARTS` permite deshabilitar envío de imágenes en producción.
- **Optimización:** Se recomienda `CHART_LOOKBACK=30` o menor para mantener payloads <200KB.

#### 📊 **Visualización de Patrones (Testing)**
- **Nueva Herramienta:** `test/visualize_patterns.py` para análisis de calidad de detección.
- **Funcionalidad:**
  - Genera gráficos de todas las velas guardadas en `test_data.json`
  - Normalización porcentual (apertura = 0%, resto como % de cambio)
  - **Validación automática:** Cada vela se valida contra las reglas oficiales de `candle.py`
  - **Código de colores:**
    * 🟦 AZUL: Vela válida que pasó el test
    * 🟥 ROJO: Vela inválida que NO pasó el test
  - **Filtros por patrón:** `--pattern shooting_star`, `--pattern hammer`, etc.
  - **Métricas reportadas:** Precisión de detección, distribución válidas/inválidas, estadísticas de normalización
  - **Imágenes guardadas en:** `test/images_patterns/`
- **Implementación Técnica:**
  - Importa funciones de `candle.py` usando `importlib.util` (evita imports circulares)
  - Usa las mismas funciones que el bot en producción (fuente única de verdad)
- **Uso:**
  ```bash
  python test/visualize_patterns.py                    # Todos los patrones
  python test/visualize_patterns.py --pattern hammer   # Solo Hammer
  ```

#### 📢 **Sistema de Notificaciones Duales**
- **Nueva Funcionalidad:** Envío de notificaciones en dos momentos:
  1. **Detección de Patrón** (inmediato): Cuando se identifica Shooting Star, Hammer, etc.
  2. **Resultado de Vela** (1 minuto después): Cuando cierra la vela siguiente, informa dirección (VERDE/ROJA/DOJI)
- **Configuración:**
  - Selección por entorno con `APP_ENV` (`development` | `production`)
  - `production` usa por defecto: `trade:alert` y `trade:send_result`
  - `development` usa por defecto: `test:trade:alert` y `test:trade:send_result`
  - Variables por entorno:
    - `TELEGRAM_SUBSCRIPTION_PROD`
    - `TELEGRAM_OUTCOME_SUBSCRIPTION_PROD`
    - `TELEGRAM_SUBSCRIPTION_DEV`
    - `TELEGRAM_OUTCOME_SUBSCRIPTION_DEV`
  - Overrides legacy opcionales con prioridad si no están vacíos:
    - `TELEGRAM_SUBSCRIPTION`
    - `TELEGRAM_OUTCOME_SUBSCRIPTION`
  - Refactorización: Nueva función base `_send_telegram_notification()` reutilizable
  - Nueva función pública: `send_outcome_notification(source, symbol, direction, chart_base64)`
- **Utilidad añadida:**
  - `get_candle_direction(open_price, close)` en `candle.py`: Retorna "VERDE", "ROJA" o "DOJI"
- **Flujo:**
  ```
  Vela cierra → Detecta patrón → Notificación 1 (alerta)
  ↓
  Espera 60s → Vela siguiente cierra → Notificación 2 (resultado)
  ```
- **Beneficio:** El trader recibe confirmación inmediata del resultado sin tener que monitorear manualmente.

**Ejemplo `.env` (dev/prod):**
```env
APP_ENV=development
TELEGRAM_SUBSCRIPTION_DEV=test:trade:alert
TELEGRAM_OUTCOME_SUBSCRIPTION_DEV=test:trade:send_result

APP_ENV=production
TELEGRAM_SUBSCRIPTION_PROD=trade:alert
TELEGRAM_OUTCOME_SUBSCRIPTION_PROD=trade:send_result
```

#### 📁 **Dataset de Señales para Machine Learning**
- **Propósito:** Almacenar historial de señales detectadas y sus resultados para análisis futuro.
- **Implementación:**
  - Formato: **JSONL** (JSON Lines) - un registro por línea para append eficiente.
  - Ubicación: `data/trading_signals_dataset.jsonl`
  - Persistencia: Automática tras cada detección de patrón.
- **Estructura del Registro:**
  - **Vela Trigger:** Información completa de la vela donde se detectó el patrón (timestamp, OHLC, volumen).
  - **Vela Outcome:** Información completa de la vela siguiente (resultado de la señal).
  - **Metadata de Señal:** Patrón detectado, confianza, tendencia, score, EMAs.
  - **Resultado:** Dirección esperada vs dirección real, éxito/fracaso, PnL en pips.
  - **Validación Temporal:** Gap de timestamp entre trigger y outcome (detecta velas faltantes).
- **Objetivo Futuro:**
  - Análisis de probabilidad de éxito por patrón según:
    * Tipo de instrumento (EUR/USD, GBP/USD, etc.)
    * Score de tendencia (-10 a +10)
    * Nivel de confianza del patrón (70-100%)
    * Contexto de EMAs (alineación, divergencias)
  - Entrenamiento de modelos predictivos para mejorar filtrado de señales.
  - Backtesting de estrategias con datos históricos reales.
- **Estado Actual:** Solo almacenamiento. La lógica de análisis predictivo se implementará en versiones futuras.

#### 🔄 **Protocolo de Heartbeat Optimizado**
- **Plan Original:** Heartbeat proactivo enviado por el cliente cada 30s.
- **Implementación Real:** Heartbeat **pasivo** - el servidor envía `~h~{id}` y el cliente responde `~h~{id}`.
- **Ventaja:** Evita errores `protocol_error: wrong data`, conexión más estable.

#### 📡 **Fuente Única en MVP (FX:EURUSD)**
- **Plan Original:** Dual-Source con OANDA (primaria) + FX (secundaria).
- **Implementación MVP:** Solo FX:EURUSD para validar estabilidad.
- **Justificación:** OANDA deshabilitado temporalmente (comentado en `config.py`) para testing inicial.
- **Roadmap:** Reactivar OANDA en v0.0.3 una vez validado el feed público.

#### 💰 **Optimización de Costos API Gateway**
- **Nueva Variable:** `SEND_CHARTS=false` (default) para enviar solo texto.
- **Comparativa:**
  - `SEND_CHARTS=false`: ~1 KB/request → $0.0000035/alerta
  - `SEND_CHARTS=true`: ~76 KB/request → $0.000035/alerta (10x más caro)
- **Recomendación:** Producción con `SEND_CHARTS=false`, debugging con `true`.

## 2. Estrategia de Alerta y Protocolo Operativo
El sistema funciona estrictamente como soporte a la decisión. NO ejecuta operaciones.

### 2.1. Pares a Monitorear (Versiones posteriores a 0.1)
EUR/USD
GBP/USD
USD/JPY
USD/CHF
USD/CAD
AUD/USD
NZD/USD
Nota: Esta lista es inicial. Se agregarán más pares e instrumentos en el futuro a medida que se valide la estrategia en los pares principales.

### 2.2. Temporalidad
Velas de 1 Minuto (1m): El análisis técnico y la notificación se generan estrictamente en el cierre de la vela ($t_{incoming} > t_{current}$).

### 2.3. Lógica de Notificación (Dual Source)
El sistema utiliza un modelo de confirmación cruzada para filtrar el ruido inherente a los proveedores de datos.

**Notificación ESTÁNDAR:** Se envía cuando UNA de las fuentes detecta el patrón válido.
- Mensaje (Con Filtro): "⚠️ OPORTUNIDAD ALINEADA | EURUSD"
- Mensaje (Sin Filtro): "📈 PATRÓN DETECTADO | EURUSD"
- Incluye: Apertura, Máximo, Mínimo, Cierre (palabras completas, no abreviaturas)
- Formato: Negrita con asterisco simple (*), no doble (**)
- Datos: EMA 200, Tendencia, Confianza del patrón
- Gráfico: Adjunto en Base64 (si `SEND_CHARTS=true`)

**Ejemplo de mensaje estándar:**
```
📊 *Fuente:* FX
📈 *Patrón:* SHOOTING_STAR
🕒 *Timestamp:* 2025-11-20 14:32:00
💰 *Apertura:* 1.09050
💰 *Máximo:* 1.09180
💰 *Mínimo:* 1.09020
💰 *Cierre:* 1.09040
📉 *EMA 200:* 1.08950
🎯 *Tendencia:* BULLISH
✨ *Confianza:* 85%

⚡ *Verificar gráfico manualmente antes de operar.*
```

**Notificación FUERTE (Strong):** Se envía cuando AMBAS fuentes detectan el patrón válido en el mismo cierre de vela (ventana de 2s).
- Mensaje: "🔥 ALERTA CONFIRMADA | EURUSD | Coincidencia DUAL"
- Incluye: Comparativa de ambas fuentes con datos completos
- Formato: Negrita con asterisco simple (*), palabras completas
- Gráfico: Prioriza gráfico de la fuente principal

**Ejemplo de mensaje fuerte:**
```
🎯 *CONFIRMACIÓN DUAL-SOURCE*
📊 *Fuentes:* FX + OANDA
📈 *Patrón:* SHOOTING_STAR
🕒 *Timestamp:* 2025-11-20 14:32:00

*FX:*
  • *Apertura:* 1.09050
  • *Máximo:* 1.09180
  • *Mínimo:* 1.09020
  • *Cierre:* 1.09040
  • *EMA 200:* 1.08950
  • *Confianza:* 85%

*OANDA:*
  • *Apertura:* 1.09048
  • *Máximo:* 1.09175
  • *Mínimo:* 1.09018
  • *Cierre:* 1.09038
  • *EMA 200:* 1.08948
  • *Confianza:* 82%

📉 *Tendencia:* BULLISH
✨ *Confianza Promedio:* 84%

🚀 *Alta probabilidad. Revisar retroceso del 50% en primeros 30s de la siguiente vela.*
```

**Formato JSON de Telegram API:**
```json
{
  "first_message": "🔥 ALERTA CONFIRMADA | EURUSD",
  "image_base64": "iVBORw0KGgoAAAANS...",
  "message_type": "markdown",
  "entries": [
    {
      "subscription": "trade:alert",
      "message": "Cuerpo del mensaje con detalles técnicos"
    }
  ]
}
```

**⚠️ Estado Actual (MVP v0.0.2):** Solo alertas ESTÁNDAR activas (FX única fuente). Dual-Source se activará al reintegrar OANDA.

## 3. Matriz de Patrones y Tendencia

### 3.1. Definición de Tendencia (Filtro Macro)
Se utiliza la EMA 200 como el juez principal de la tendencia para filtrar operaciones contra-corriente.
Tendencia ALCISTA: Precio de Cierre > EMA 200.
Solo se buscan compras (Martillos).
Tendencia BAJISTA: Precio de Cierre < EMA 200.
Solo se buscan ventas (Estrellas Fugaces).

### 3.2. Reglas de Disparo

**IMPORTANTE:** El sistema soporta dos modos de operación configurables mediante `USE_TREND_FILTER`:

#### Modo A: CON Filtro de Tendencia (`USE_TREND_FILTER=true`) - Por Defecto
Sistema conservador que SOLO notifica patrones alineados con la tendencia dominante:

A. Escenario: Tendencia ALCISTA (Precio > EMA 200)
Patrón: Martillo (Hammer)
Acción: 🚨 ALERTA DE COMPRA.
Contexto: Señal de rebote a favor de la tendencia.
Patrón: Hombre Colgado / Estrella Fugaz
Acción: Ignorar (contra-tendencia).

B. Escenario: Tendencia BAJISTA (Precio < EMA 200)
Patrón: Estrella Fugaz (Shooting Star)
Acción: 🚨 ALERTA DE VENTA.
Contexto: Señal de rechazo a favor de la caída.
Decisión Humana: Esperar retroceso del 50% en los primeros 30s de la siguiente vela para entrar.
Patrón: Martillo Invertido / Martillo
Acción: Ignorar (contra-tendencia).

**Título de Notificación:** "⚠️ OPORTUNIDAD ALINEADA | EURUSD"

#### Modo B: SIN Filtro de Tendencia (`USE_TREND_FILTER=false`)
Sistema más agresivo que notifica CUALQUIER patrón detectado sin importar la tendencia:

- Detecta: Shooting Star, Hanging Man, Inverted Hammer, Hammer
- Acción: 🚨 NOTIFICA SIEMPRE que se cumplen los criterios matemáticos del patrón
- Contexto: El trader decide manualmente si la tendencia es apropiada
- Ventaja: Captura más oportunidades potenciales
- Desventaja: Mayor ruido, requiere análisis adicional del trader

**Título de Notificación:** "📈 PATRÓN DETECTADO | EURUSD"

#### Comparativa de Títulos:
- **Con Filtro:** "⚠️ OPORTUNIDAD ALINEADA" - Indica que el patrón está validado por tendencia
- **Sin Filtro:** "📈 PATRÓN DETECTADO" - Indica solo detección matemática del patrón

**El contenido del mensaje (entries.message) es IDÉNTICO en ambos modos**, solo cambia el título para diferenciar el nivel de validación.

## 4. Cálculos y Algoritmos de Detección

**📅 ÚLTIMA ACTUALIZACIÓN: 22/Nov/2025** - Sistema optimizado para opciones binarias con énfasis en momentum de corto plazo.

### 4.1. Sistema de Puntuación Ponderada (Análisis de Tendencia)

El sistema utiliza un **algoritmo de scoring ponderado con 7 EMAs** optimizado para opciones binarias en velas de 1 minuto.

**Filosofía:** Gradualidad y precisión. Cada EMA contribuye con un peso específico al score total (-10.0 a +10.0).

#### EMAs y Pesos

| EMA | Peso | Velocidad | Uso Principal |
|-----|------|-----------|---------------|
| **EMA 5** | 2.5 pts | Ultra rápida | Detección inmediata de reversiones |
| **EMA 7** | 2.0 pts | Muy rápida | Señales inmediatas y sobre-extensión |
| **EMA 10** | 1.5 pts | Rápida | Confirmación de momentum ultra corto |
| **EMA 15** | 1.5 pts | Rápida-Media | Transición de momentum |
| **EMA 20** | 1.0 pt | Media | Confirmación de momentum |
| **EMA 30** | 1.0 pt | Media-Lenta | Contexto de tendencia |
| **EMA 50** | 0.5 pt | Lenta | Validación de tendencia establecida |

**Total Máximo:** 10.0 Puntos

#### Clasificación del Score

| Score Range | Estado | Descripción |
|-------------|--------|-------------|
| **(7.0 a 10.0]** | `STRONG_BULLISH` | Alcista fuerte |
| **(2.0 a 7.0]** | `WEAK_BULLISH` | Alcista débil |
| **[-2.0 a 2.0]** | `NEUTRAL` | Sin tendencia clara |
| **[-7.0 a -2.0)** | `WEAK_BEARISH` | Bajista débil |
| **[-10.0 a -7.0)** | `STRONG_BEARISH` | Bajista fuerte |

**Detección de Alineación (Fanning):**
- `is_aligned = True` solo si las EMAs están ordenadas perfectamente (ej: P > 5 > 7 > 10 > 20 > 50).

Ver `Docs/tendencia.md` para detalles completos.

### 4.2. Detección de Patrones de Velas Japonesas

Los 4 patrones se detectan mediante **validación matemática estricta** con scoring de confianza (70-100%).

**Archivo:** `src/logic/candle.py`

#### Métricas Comunes Calculadas

Para cada vela se calculan:
- **Total Range:** `high - low` (rango total de la vela)
- **Body Size:** `abs(close - open)` (tamaño del cuerpo)
- **Body Ratio:** `body_size / total_range` (proporción del cuerpo)
- **Upper Wick:** Mecha superior (depende si vela es alcista o bajista)
- **Lower Wick:** Mecha inferior (depende si vela es alcista o bajista)

#### Patrón 1: Shooting Star (Estrella Fugaz)

**Tipo:** Reversión bajista

**Criterios Matemáticos:**
- **DEBE SER VELA ROJA O NEUTRAL** (`close <= open`) ⚠️ VALIDACIÓN CRÍTICA
- Mecha superior ≥ 60% del rango total (`upper_wick_ratio >= 0.60`)
- Cuerpo pequeño ≤ 30% del rango total (`body_ratio <= 0.30`)
- Mecha inferior ≤ 15% del rango total (`lower_wick_ratio <= 0.15`)
- Mecha superior ≥ 2x el cuerpo (`upper_wick / body_size >= 2.0`)

**Scoring de Confianza:**
- Base: 70%
- +10% si mecha superior ≥ 70%
- +10% si cuerpo ≤ 20%
- +10% si mecha inferior ≤ 10%
- Máximo: 100%

**Color:** DEBE ser ROJA o NEUTRAL (velas verdes son rechazadas)

#### Patrón 2: Hanging Man (Hombre Colgado)

**Tipo:** Reversión bajista (en tendencia alcista)

**Criterios Matemáticos:**
- **DEBE SER VELA ROJA O NEUTRAL** (`close <= open`) ⚠️ VALIDACIÓN CRÍTICA
- Mecha inferior ≥ 60% del rango total
- Cuerpo pequeño ≤ 30% del rango total
- Mecha superior ≤ 15% del rango total
- Mecha inferior ≥ 2x el cuerpo
- Cuerpo ubicado en parte superior de la vela

**Scoring de Confianza:**
- Base: 70%
- +10% si mecha inferior ≥ 70%
- +10% si cuerpo ≤ 20%
- +10% si mecha superior ≤ 10%
- Máximo: 100%

#### Patrón 3: Inverted Hammer (Martillo Invertido)

**Tipo:** Reversión alcista (en tendencia bajista)

**Criterios Matemáticos:**
- **DEBE SER VELA VERDE** (`close > open`) ⚠️ VALIDACIÓN CRÍTICA
- Mecha superior ≥ 60% del rango total
- Cuerpo pequeño ≤ 30% del rango total
- Mecha inferior ≤ 15% del rango total
- Mecha superior ≥ 2x el cuerpo
- Cuerpo ubicado en parte inferior de la vela

**Scoring de Confianza:**
- Base: 70%
- +10% si mecha superior ≥ 70%
- +10% si cuerpo ≤ 20%
- +10% si mecha inferior ≤ 10%
- Máximo: 100%

#### Patrón 4: Hammer (Martillo)

**Tipo:** Reversión alcista

**Criterios Matemáticos:**
- **DEBE SER VELA VERDE** (`close > open`) ⚠️ VALIDACIÓN CRÍTICA
- Mecha inferior ≥ 60% del rango total
- Cuerpo pequeño ≤ 30% del rango total
- Mecha superior ≤ 15% del rango total
- Mecha inferior ≥ 2x el cuerpo

**Scoring de Confianza:**
- Base: 70%
- +10% si mecha inferior ≥ 70%
- +10% si cuerpo ≤ 20%
- +10% si mecha superior ≤ 10%
- Máximo: 100%

**Color:** DEBE ser verde (color obligatorio, no otorga bono)

### 4.3. Sistema de Alertas Inteligentes (3 Niveles)

El sistema clasifica alertas según la **relación entre patrón detectado y tendencia** para priorizar señales de alta probabilidad.

**Lógica:** `_format_standard_message()` en `src/services/telegram_service.py`

#### Nivel 1: 🔴/🟢 ALERTA FUERTE (Alta Probabilidad)

**Condiciones:**
- Shooting Star + Tendencia BULLISH (fuerte o débil) → 🔴 Reversión bajista probable
- Hammer + Tendencia BEARISH (fuerte o débil) → 🟢 Reversión alcista probable

**Título:** "Alta probabilidad de apertura BAJISTA/ALCISTA"

**Interpretación:** Patrón de reversión detectado CONTRA la tendencia actual → Mayor probabilidad de cambio de dirección.

#### Nivel 2: ⚠️ AVISO (Debilitamiento - Requiere Cautela)

**Condiciones:**
- Inverted Hammer + Tendencia BULLISH → ⚠️ Posible operación a la baja
- Hanging Man + Tendencia BEARISH → ⚠️ Posible operación al alza

**Título:**
- "⚠️ AVISO | EURUSD | Posible operación a la baja"
- "⚠️ AVISO | EURUSD | Posible operación al alza"

**Interpretación:**
- ⚠️ **NO es una reversión confirmada**, es una señal de CAUTELA
- El patrón sugiere **debilitamiento de la tendencia actual**
- El trader debe analizar **manualmente** si la siguiente vela confirma el cambio
- Estas alertas indican posibles movimientos contrarios, pero requieren validación adicional
- **Recomendación:** Esperar confirmación en la siguiente vela antes de entrar

#### Nivel 3: 📊 DETECCIÓN (Informativo)

**Condiciones:**
- Cualquier otro caso (patrón sin alineación clara de tendencia)

**Título:** "Solo informativo - Requiere análisis adicional"

**Interpretación:** Patrón matemáticamente válido pero sin contexto de tendencia claro.

### 4.4. Visualización en Gráficos

**Biblioteca:** `mplfinance==0.12.10b0`

**EMAs Graficadas (Solo 2):**
- EMA 200: Línea cyan (#00D4FF), grosor 1.5 - Referencia macro
- EMA 20: Línea amarilla (#FFD700), grosor 1.0 - Momentum

**EMAs NO Graficadas:** EMA 30, 50, 100 (para evitar saturación visual)

**Razón:** Gráficos pequeños en Telegram (30 velas) se saturan con 5 líneas superpuestas. Se priorizan extremos (corto plazo vs largo plazo).

### 4.5. Notas Importantes sobre Calibración

⚠️ **TODOS los valores numéricos en esta sección están sujetos a cambios:**

- **Pesos del scoring:** Actualmente ±3, ±2, ±2, ±2, ±1 → Pueden ajustarse
- **Umbrales de clasificación:** ≥6 para STRONG, ≥1 para WEAK → Pueden modificarse
- **Criterios de patrones:** 60%, 30%, 15%, 2.0x → Configurables en `config.py`
- **Bonos de confianza:** +10% por condición excepcional → Ajustables

**Proceso de validación:**
1. Monitoreo en producción con datos reales (EUR/USD 1m)
2. Tracking histórico de scores vs movimientos reales del precio
3. Análisis de correlación patrón-tendencia-resultado
4. Ajuste iterativo de pesos y umbrales
5. Documentación de cambios en changelog

**Referencia completa:** Ver `Docs/tendencia.md` para explicación detallada del sistema de scoring.

## 5. Arquitectura Tecnológica Modular

### 5.1. Estructura del Programa (main.py)

**Módulo 1: Connection Service (WebSocket Público)**
- Gestiona conexión WebSocket a `data.tradingview.com` en **modo público** (sin autenticación).
- **Headers Anti-WAF:** Rotación de User-Agent para imitar navegadores reales (Chrome/Firefox).
- **Heartbeat Pasivo:** Responde a pings del servidor (`~h~{id}`) en lugar de enviar proactivamente.
- **Snapshot Inicial:** Descarga 1000 velas históricas al conectar para convergencia de EMA 200.
- **Reconexión Automática:** Backoff exponencial (5s → 300s) en caso de desconexión.
- **Graceful Shutdown:** Envía comandos `remove_series` antes de cerrar WebSocket.

**Módulo 2: Analysis Service (Core Logic)**
- **Cálculo Vectorizado:** Usa `pandas` para gestionar arrays de precios con alta eficiencia.
- **Integridad Matemática (Buffer):**
  - Se solicitan 1000 velas al conectar.
  - EMAs (20, 30, 50, 100, 200) convergen correctamente con buffer mínimo.
  - Sistema no emite señales hasta alcanzar buffer mínimo.
- **Validación de Patrones:** Detecta **4 patrones principales del MVP**:
  - ✅ **Shooting Star** (Estrella Fugaz) - Reversión bajista
  - ✅ **Hanging Man** (Hombre Colgado) - Reversión bajista
  - ✅ **Inverted Hammer** (Martillo Invertido) - Reversión alcista
  - ✅ **Hammer** (Martillo) - Reversión alcista
  - Validación con proporciones estrictas (Cuerpo vs Mecha) y scoring de confianza (70-100%).
- **Dataset de Machine Learning:**
  - Al detectar un patrón, se almacena la vela trigger y la vela siguiente (outcome).
  - Formato: JSONL append-only en `data/trading_signals_dataset.jsonl`.
  - Campos: trigger_candle, outcome_candle, señal, resultado, metadata.
  - Validación temporal: Detecta velas salteadas (gap != 60s) y marca con flag.
  - **Objetivo futuro:** Análisis de probabilidad de éxito por patrón/instrumento/score.
  - **Estado actual:** Solo almacenamiento, análisis predictivo pendiente.
- **Sistema de Testing Automatizado:**
  - Ubicación: `test/test_candles.py` y `test/test_data.json`
  - Funcionalidades:
    - Validación estricta de los 4 tipos de patrones con criterios matemáticos.
    - Reporte de fidelidad porcentual para cada patrón detectado.
    - Mensajes de diagnóstico detallados con razones de fallo.
    - Auto-guardado de velas detectadas en producción para expandir casos de prueba.
  - Propósito: Garantizar precisión matemática y evitar falsos positivos.
- **Generación de Gráficos:**
  - Biblioteca: `mplfinance` con backend sin GUI (`matplotlib.use('Agg')`).
  - Ejecución asíncrona: `asyncio.to_thread()` para no bloquear Event Loop.
  - Output: Imagen PNG codificada en Base64.
  - Lookback: **Parametrizable** vía `CHART_LOOKBACK` (recomendado: 20-30 velas).
  - **EMAs Visualizadas:** Las 5 EMAs (200, 100, 50, 30, 20) con colores y grosores diferenciados.
  - **Leyenda:** Esquina superior izquierda identifica cada EMA por color.
  - **Performance:** ~220 ms de generación total (no bloquea WebSocket).
  - Integración: Se envía automáticamente en el campo `image_base64` del payload de Telegram.

**Módulo 3: Notification Service (Output)**
- Cliente HTTP asíncrono (`aiohttp`) con timeout de 10s.
- **Dual-Source Buffer:** Ventana temporal de 2s para correlacionar señales de múltiples fuentes.
- **Limpieza Automática:** Task periódico que elimina alertas expiradas del buffer.
- **Race Condition Fix:** Verificación doble antes de eliminar alertas del diccionario.
- **Envío de Gráficos Integrado:**
  - Imágenes Base64 generadas por `charting.py` se envían en el campo `image_base64` del payload.
  - Control parametrizable con `SEND_CHARTS` (true/false).
  - Validación automática del Base64 antes de envío (detección de espacios, saltos de línea, prefijos).
- **Guardado Local:** Imágenes Base64 se decodifican y guardan en `logs/chart_*.png` para auditoría.
- **Formato de Mensaje:** Texto plano con emojis (message_type: "text"), sin markdown para evitar errores de parsing.
- **Control de Costos:** Variable `SEND_CHARTS` permite desactivar envío de imágenes (ahorro ~90% en transfer costs).

**Módulo 4: Storage Service (Persistencia de Dataset)**
- **Propósito:** Almacenar historial de señales para análisis futuro de Machine Learning.
- **Formato:** JSONL (JSON Lines) - un registro por línea, append eficiente.
- **Archivo:** `data/trading_signals_dataset.jsonl`
- **Estructura de Registro:**
  - `timestamp`: ISO 8601 del momento de detección
  - `signal`: Metadata del patrón (tipo, confianza, tendencia, score, EMAs)
  - `trigger_candle`: OHLC de la vela donde se detectó el patrón
  - `outcome_candle`: OHLC de la vela siguiente (resultado)
  - `outcome`: Dirección esperada vs real, éxito/fracaso, PnL en pips
  - `_metadata`: Gap temporal, flags de velas salteadas, versión del registro
- **Validación Temporal:** Detecta gaps de timestamp != 60s y marca registros inconsistentes.
- **Sanitización de Tipos:** Conversión automática de tipos NumPy (numpy.bool_, numpy.int64) a tipos JSON nativos.
- **Performance:** Escritura asíncrona con `asyncio.to_thread()` para no bloquear event loop.
- **Uso Futuro:** Análisis de probabilidad de éxito por patrón, instrumento, score y contexto de EMAs.

**Módulo 5: Charting Utilities**
- **Generación de Gráficos:** `generate_chart_base64(dataframe, lookback, title)`
- **Validación:** `validate_dataframe_for_chart()` verifica columnas requeridas y datos suficientes.
- **Estilo:** Tema claro profesional con fondo blanco, velas verdes/rojas, panel de volumen.
- **EMAs Graficadas:** Las 5 EMAs calculadas (200, 100, 50, 30, 20) con:
  - Colores diferenciados: Cyan (200) → Azul (100) → Verde (50) → Amarillo (30) → Naranja (20)
  - Grosores decrecientes: 2.0 → 1.8 → 1.5 → 1.2 → 1.0
  - Leyenda integrada en esquina superior izquierda con transparencia
- **Performance Detallada:**
  - Preparación de datos (pandas): 5-10 ms
  - Render matplotlib (5 EMAs + velas + volumen): 150-300 ms
  - Encoding PNG → Base64: 50-100 ms
  - **Tiempo total promedio: ~220 ms**
  - Ejecución: Hilo separado con `asyncio.to_thread()` - no bloquea WebSocket
- **Optimización de Memoria:** `plt.close(fig)` libera recursos inmediatamente tras guardar.

### 4.2. Infraestructura
- **Proveedor:** Oracle Cloud Infrastructure (OCI) - Tier "Always Free" o desarrollo local.
- **Entorno:** Windows 10/11 (desarrollo) | Linux VM (producción).
- **Runtime:** Python 3.10+, asyncio con `WindowsSelectorEventLoopPolicy`.
- **Dependencias:**
  - `websockets==12.0` - Cliente WebSocket
  - `aiohttp==3.9.1` - Cliente HTTP asíncrono
  - `pandas==2.1.4` - Procesamiento de series temporales
  - `numpy==1.26.2` - Cálculos matemáticos
  - `mplfinance==0.12.10b0` - Generación de gráficos financieros
  - `python-dotenv==1.0.0` - Gestión de variables de entorno

## 6. Flujo de Lógica y Procesos Críticos

### 6.1. Autenticación y Calidad de Datos

**🎉 Cambio Crítico Implementado:**
- **NO se requiere autenticación:** TradingView proporciona datos en tiempo real de Forex **sin login**.
- **Cuentas gratuitas funcionan:** No se necesita suscripción paga ni SessionID válido.
- **Datos NO retrasados:** Feed público de FX:EURUSD es en tiempo real (actualización cada ~5s).
- **Validación de Calidad:** Sistema verifica flag de datos al inicio. Si detecta "Delayed" o "CBOE BZX", loguea advertencia pero continúa (no detiene operación).

**Manejo de Errores del Protocolo:**
- Si TradingView envía `critical_error` o `protocol_error`, se loguea el mensaje pero NO se detiene el bot.
- Reconexión automática ante errores de conexión.
- Heartbeat pasivo previene errores `invalid_method`.

### 6.2. Inicialización y Reconexión

**Flujo de Startup:**
1. **Conexión WebSocket:** Se conecta a `wss://data.tradingview.com/socket.io/websocket`
2. **Creación de Sesión:** Se genera `quote_session_id` único (ej: `qs_abc123xyz`)
3. **Suscripción a Instrumento:** Envía `create_series` para FX:EURUSD, temporalidad 1m
4. **Snapshot Histórico:** Recibe `timescale_update` con 1000 velas
5. **Carga en Buffer:** `AnalysisService.load_historical_candles()` puebla DataFrame
6. **Cálculo Inicial EMA:** EMA 200 converge con 600+ velas
7. **Modo Streaming:** Procesa actualizaciones en tiempo real (`du` messages)
8. **Detección Activa:** Sistema comienza a emitir señales tras validar buffer mínimo

**Reconexión Automática:**
- Backoff exponencial: 5s → 10s → 20s → ... → 300s (máximo)
- Máximo 10 intentos antes de detener el servicio
- Logs detallados de cada intento
- Reset de contador tras conexión exitosa

### 6.3. Procesamiento de Velas

**Separación de Responsabilidades (Crítico):**

**📥 Snapshot Histórico (1000 velas):**
- Mensaje TradingView: `timescale_update` (al inicio)
- Método: `ConnectionService._load_historical_snapshot()`
- Destino: `AnalysisService.load_historical_candles()`
- Comportamiento:
  - ✅ Carga masiva en DataFrame
  - ✅ Calcula EMA 200 inicial
  - ❌ NO genera gráficos
  - ❌ NO emite alertas
  - ❌ NO loguea cada vela (solo log de resumen)

**🕒 Actualización en Tiempo Real (1 vela):**
- Mensaje TradingView: `du` (data update, continuo)
- Método: `ConnectionService._process_realtime_update()`
- Destino: `AnalysisService.process_candle()`
- Comportamiento:
  - ✅ Detecta cierre de vela por cambio de timestamp
  - ✅ Genera gráfico asíncrono (`asyncio.to_thread`)
  - ✅ Emite señal si detecta patrón válido
  - ✅ Loguea cada vela cerrada con detalles

**Ventajas de la Separación:**
- Evita spam de logs (330+ "GENERATING CHART" al inicio)
- Performance optimizada (no genera 1000 gráficos innecesarios)
- Lógica clara y mantenible
- Buffer se inicializa correctamente (antes solo mostraba 18/600 velas)

### 6.4. Gestión de Memoria y Recursos

**Buffer Limitado:**
- Configuración: `Config.CHART_LOOKBACK = 30` velas para gráficos
- DataFrame: Mantiene últimas 1000 velas (se purgan las más antiguas)
- EMA 200: Requiere mínimo 600 velas para convergencia (3x el período)

**Generación Asíncrona de Gráficos:**
- Ejecución en hilo separado: `await asyncio.to_thread(generate_chart_base64, ...)`
- No bloquea Event Loop principal
- WebSocket continúa procesando ticks durante generación
- Timeout implícito: Si falla, continúa sin gráfico (no detiene alertas)

### 6.5. Definiciones Técnicas Finales

**Simbología:**
- **MVP Actual:** `FX:EURUSD` (fuente única, pública, sin auth)
- **Roadmap:** Reactivar `OANDA:EURUSD` como primaria en v0.0.3

**Gestión de Buffer:**
- Mínimo: 600 velas (3x EMA 200)
- Recomendado: 1000 velas (5x EMA 200) ← **Implementado**
- Snapshot: Se solicitan 1000 velas al conectar

**Variables Críticas `.env`:**
- `TV_SESSION_ID`: Opcional (valor: `not_required_for_public_data`)
- `TELEGRAM_API_URL`: URL completa del endpoint broadcast
- `TELEGRAM_API_KEY`: API Key para header `x-api-key`
- `APP_ENV`: Entorno de ejecución (`development` | `production`)
- `TELEGRAM_SUBSCRIPTION_PROD`: Topic de alerta para producción (ej: `trade:alert`)
- `TELEGRAM_OUTCOME_SUBSCRIPTION_PROD`: Topic de resultado para producción (ej: `trade:send_result`)
- `TELEGRAM_SUBSCRIPTION_DEV`: Topic de alerta para desarrollo (ej: `test:trade:alert`)
- `TELEGRAM_OUTCOME_SUBSCRIPTION_DEV`: Topic de resultado para desarrollo (ej: `test:trade:send_result`)
- `TELEGRAM_SUBSCRIPTION`: Override legacy opcional con prioridad si no está vacío
- `TELEGRAM_OUTCOME_SUBSCRIPTION`: Override legacy opcional con prioridad si no está vacío
- `SEND_CHARTS`: `true` o `false` para controlar envío de imágenes
- `USE_TREND_FILTER`: `true` o `false` - Habilita/deshabilita filtro de tendencia
  - `true` (default): Solo notifica patrones alineados con tendencia EMA 200
  - `false`: Notifica cualquier patrón detectado sin importar tendencia
- `CHART_LOOKBACK`: Número de velas en gráfico (default: 30)
- `EMA_PERIOD`: Período de EMA (default: 200)
- `DUAL_SOURCE_WINDOW`: Ventana de confirmación en segundos (default: 2.0)
- `LOG_LEVEL`: `DEBUG` o `INFO` (producción recomendado: `INFO`)

---

## 7. Mejoras Implementadas Post-Especificación Inicial

### 7.1. Sistema de Gráficos Visuales
- ✅ Generación automática con `mplfinance`
- ✅ Codificación Base64 para envío por API
- ✅ Guardado local en `logs/` para auditoría
- ✅ Ejecución asíncrona (no bloquea WebSocket)
- ✅ Control de costos con flag `SEND_CHARTS`

### 7.2. Autenticación Simplificada
- ✅ Modo público sin SessionID
- ✅ Sin riesgo de baneos o expiración de tokens
- ✅ Datos en tiempo real sin suscripción paga
- ✅ Sistema completamente autónomo

### 7.3. Protocolo WebSocket Optimizado
- ✅ Heartbeat pasivo (respuesta vs proactivo)
- ✅ Graceful shutdown con comandos de limpieza
- ✅ Logs truncados para mensajes grandes (>500 bytes)
- ✅ Reconexión exponencial con límite de intentos

### 7.4. Manejo de Race Conditions
- ✅ Verificación doble antes de eliminar alertas del buffer
- ✅ Sincronización correcta entre cleanup task y wait tasks
- ✅ Sin errores `KeyError` en Dual-Source logic

### 7.5. Optimización de Costos API Gateway
- ✅ Control granular de envío de imágenes Base64
- ✅ Documentación de impacto económico (10x diferencia)
- ✅ Modo producción vs debugging claramente diferenciado

### 7.6. Sistema de Testing Automatizado
- ✅ Test suite en `test/test_candles.py` con validación estricta de los 4 patrones
- ✅ Base de datos de casos de prueba en `test/test_data.json`
- ✅ Auto-guardado de velas detectadas en producción
- ✅ Reporte de fidelidad matemática y diagnósticos detallados
- ✅ Verificación de criterios: cuerpo, mechas, proporciones, direccionalidad

### 7.7. Cálculo de EMAs Múltiples
- ✅ Implementación de EMAs 20, 30, 50, 100, 200 períodos
- ✅ Cálculo condicional basado en disponibilidad de datos
- ✅ Visualización de todas las EMAs en mensajes de Telegram
- ✅ Integración completa en gráficos generados

### 7.8. Modo Sin Filtro de Tendencia (MVP Actual)
- ✅ Configuración `USE_TREND_FILTER=false` implementada
- ✅ Sistema notifica todos los patrones detectados sin restricción de tendencia
- ✅ Título diferenciado: "📈 PATRÓN DETECTADO" vs "⚠️ OPORTUNIDAD ALINEADA"
- ✅ Delegación de decisión final al trader humano

---

## 8. Estado Actual del MVP ✅

### 8.1. Funcionalidades Completadas
El MVP v0.0.2 está **100% operativo** con las siguientes características:

✅ **Detección de Patrones:**
- Shooting Star (Estrella Fugaz)
- Hanging Man (Hombre Colgado)
- Inverted Hammer (Martillo Invertido)
- Hammer (Martillo)
- Sistema de confianza matemática (70-100%)

✅ **Sistema de Testing:**
- Suite automatizada con validación estricta
- Reporte de fidelidad porcentual
- Auto-guardado de casos detectados
- Diagnósticos detallados de fallos

✅ **Generación de Gráficos:**
- Implementación con `mplfinance`
- Codificación Base64 automática
- Cantidad de velas parametrizable (`CHART_LOOKBACK`)
- Envío integrado vía Telegram

✅ **Cálculo de Indicadores:**
- EMAs múltiples (20, 30, 50, 100, 200)
- Cálculo condicional eficiente
- Visualización en mensajes y gráficos

✅ **Notificaciones Telegram:**
- Envío automático con imagen Base64
- Formato texto plano optimizado
- Control de costos con `SEND_CHARTS`
- Validación de payload antes de envío

✅ **Modo de Operación:**
- `USE_TREND_FILTER=false` (sin filtro de tendencia)
- Notifica cualquier patrón detectado
- Delegación de decisión al trader
- Título diferenciado: "📈 PATRÓN DETECTADO"

### 7.2. Configuración Recomendada
Para operación óptima del MVP:

```env
# Configuración de Gráficos
CHART_LOOKBACK=30          # Recomendado: 20-30 velas (evita payloads >80KB)
SEND_CHARTS=true           # Enviar gráficos con alertas

# Modo de Operación MVP
USE_TREND_FILTER=false     # Notificar todos los patrones (MVP actual)

# Indicadores
EMA_PERIOD=200             # EMA principal para tendencia
```

### 8.3. Próximas Mejoras Sugeridas
Basadas en la experiencia del MVP:

**Optimización de Payloads:**
- Considerar compresión de imágenes antes de Base64
- Implementar fallback a texto-solo si imagen excede límite
- Agregar validación de tamaño máximo de payload

**Expansión de Testing:**
- Agregar más casos de prueba a `test_data.json`
- Implementar tests de regresión automáticos
- Validar comportamiento con diferentes CHART_LOOKBACK

**Monitoreo:**
- Dashboard de métricas en tiempo real
- Tracking de latencia de generación de gráficos
- Estadísticas de detección por patrón

---

## 8. Próximos Pasos (Roadmap Post-MVP)

### v0.0.3 - Dual-Source Completo
- [ ] Reactivar OANDA como fuente primaria
- [ ] Validar lógica de confirmación cruzada (ventana 2s)
- [ ] Implementar alertas FUERTE con comparativa de fuentes

### v0.1.0 - Expansión de Instrumentos
- [ ] Agregar GBP/USD, USD/JPY, USD/CHF
- [ ] Configuración multi-instrumento simultánea
- [ ] Dashboard de monitoreo en tiempo real

### v0.2.0 - Nuevos Patrones
- [ ] Doji (múltiples variantes)
- [ ] Envolvente Alcista/Bajista
- [ ] Estrella de la Mañana/Tarde
- [ ] Configuración flexible de patrones por instrumento
- [ ] Filtros de confirmación adicionales (volumen, ATR)

### v0.3.0 - Persistencia y Analytics
- [ ] Base de datos PostgreSQL/SQLite
- [ ] Historial de señales y backtesting
- [ ] Métricas de precisión por patrón

---

**Versión del Documento:** v0.0.5  
**Última Actualización:** 04 de diciembre de 2025  
**Estado del Proyecto:** ✅ **PRODUCCIÓN** - Sistema completamente operativo en v0.0.5

**Logros de v0.0.4:**
- ✅ StatisticsService con consulta de probabilidades históricas en tiempo real
- ✅ Fuzzy matching para buscar señales similares (score ±1)
- ✅ Campo raw_data en JSONL para recalcular scores retroactivamente
- ✅ Alertas enriquecidas con win rate, PnL promedio y racha reciente
- ✅ Dockerización completa (Dockerfile + docker-compose.yml)
- ✅ Logs con rotación automática (10MB × 3 archivos)
- ✅ Health check y graceful shutdown
- ✅ DOCKER_GUIDE.md con cheatsheet de comandos

**Logros del MVP (v0.0.2-v0.0.3):**
- ✅ 4 patrones de velas implementados y validados
- ✅ Sistema de testing automatizado funcional
- ✅ Generación de gráficos con `mplfinance` integrada
- ✅ Envío de imágenes Base64 vía Telegram operativo
- ✅ Cálculo de EMAs múltiples (20, 30, 50, 100, 200)
- ✅ Modo sin filtro de tendencia configurado
- ✅ Cantidad de velas en gráficos parametrizable
- ✅ Sistema de notificaciones robusto y estable
- ✅ Bollinger Bands Exhaustion System implementado
- ✅ Clasificación de fuerza de señal (HIGH/MEDIUM/LOW)
