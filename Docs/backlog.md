# Product Backlog - TradingView Pattern Monitor (Binary Options Focus)
- Última actualización: 24 de Noviembre de 2025
- Versión Actual: **v0.0.4** (Sistema de Bollinger Bands + Probabilidad Histórica + Docker implementados)
- Objetivo: Evolucionar hacia una herramienta profesional de señales para Opciones Binarias (IQ Option).

## ✅ Features Implementadas (v0.0.4)

Las siguientes funcionalidades YA ESTÁN COMPLETADAS y operativas en producción:

1. ✅ **4 Patrones de Velas Japonesas** (v0.0.2)
   - Shooting Star, Hanging Man, Inverted Hammer, Hammer
   - Validación matemática estricta + sistema de confianza 70-100%

2. ✅ **Sistema de Bollinger Bands** (v0.0.3)
   - Detección de exhaustion zones (PEAK/BOTTOM/NONE)
   - Clasificación de fuerza: HIGH 🚨🚨 / MEDIUM ⚠️ / LOW ℹ️
   - Filtrado de patrones contra-tendencia
   - BB configuración: periodo 20, desviación estándar 2.5

3. ✅ **Sistema de Probabilidad Histórica** (v0.0.4)
   - StatisticsService con consulta de dataset JSONL
   - Fuzzy matching (score ±1 tolerancia)
   - Win rate, PnL promedio, racha reciente mostrados en alertas
   - Campo `raw_data` para recalcular scores retroactivamente

4. ✅ **Dockerización Completa** (v0.0.4)
   - Dockerfile optimizado (Python 3.10-slim, usuario no-root)
   - docker-compose.yml con volúmenes persistentes
   - Logs con rotación (10MB × 3 archivos)
   - Health check + graceful shutdown
   - DOCKER_GUIDE.md con cheatsheet

5. ✅ **Testing Automatizado** (v0.0.2)
   - Suite de tests en `test/test_candles.py`
   - Herramienta de visualización con validación
   - Auto-guardado de casos detectados

6. ✅ **Momentum Scoring System** (v0.0.2)
   - Score -10 a +10 optimizado para opciones binarias
   - 5 EMAs calculadas (20, 30, 50, 100, 200)
   - Pesos priorizando corto plazo sobre macro

---

## 🟢 Nivel 1: Simple / Quick Wins (Prioridad Alta)
Mejoras de alto impacto en la calidad de la señal o usabilidad que requieren baja complejidad arquitectónica.

1. **Implementación de Patrón "Engulfing" (Envolvente)** 🚀
   - Contexto Binarias: Señal de reversión inmediata muy fuerte. Ideal para operaciones de 1 a 5 minutos.
   - Descripción: Detectar cuando el cuerpo de la vela actual cubre totalmente el cuerpo de la vela anterior con color opuesto.
   - Tarea:
     * Crear lógica matemática en `src/logic/candle.py` (función `is_engulfing_bullish` e `is_engulfing_bearish`)
     * Integrar en `analysis_service.py` manteniendo la lógica de Bollinger Bands
     * Actualizar formateo en `telegram_service.py`
     * Agregar casos de prueba a `test/test_candles.py`

2. **Filtro de RSI (Relative Strength Index)**
   - Contexto Binarias: Evita entrar en operaciones cuando el movimiento ya se agotó (trampa común en binarias).
   - Descripción: Calcular RSI (14 periodos).
   - Regla:
     * VENTA (Shooting Star/Engulfing Bearish): Solo si RSI > 70 (Sobrecompra) o bajando de 70.
     * COMPRA (Hammer/Engulfing Bullish): Solo si RSI < 30 (Sobreventa) o subiendo de 30.
   - Implementación:
     * Función `calculate_rsi()` en `analysis_service.py`
     * Integrar en lógica de `_analyze_last_closed_candle`
     * Agregar campo `rsi` a PatternSignal dataclass
     * Mostrar RSI en notificaciones de Telegram

3. **Sugerencia de Tiempo de Expiración**
   - Contexto Binarias: Reemplaza el Stop Loss/Take Profit.
   - Descripción: Analizar la volatilidad (cuerpo promedio de las últimas 5 velas).
   - Regla:
     * Volatilidad Alta: Sugerir "Expiración: 1-2 minutos" (movimiento rápido).
     * Volatilidad Baja: Sugerir "Expiración: 5+ minutos" (el precio tarda en reaccionar).
   - Implementación:
     * Función `calculate_volatility_index()` en `analysis_service.py`
     * Umbral configurable en `config.py` (HIGH_VOLATILITY_THRESHOLD)
     * Campo `suggested_expiration` en PatternSignal
     * Mostrar en bloque separado de notificaciones

4. **Comando de Estado /status para Telegram**
   - Descripción: Endpoint para verificar salud del sistema sin revisar logs.
   - Output sugerido: "🟢 Online | Uptime: 4h 20m | Última vela: 1.0540 | Tendencia: BULLISH | Buffer: 1000 velas"
   - Implementación:
     * Webhook en `telegram_service.py` para recibir comandos
     * Función `get_system_status()` en `main.py`
     * Integración con API de Telegram (POST endpoint)

5. **Dashboard de Estadísticas (Web con Streamlit)**
   - Descripción: Interfaz visual para analizar performance sin depender de Telegram.
   - Funcionalidad:
     * Gráfico de win rate por patrón (bar chart)
     * Distribución de scores (histogram)
     * Heatmap de probabilidad por score y patrón
     * Curva de PnL acumulado (line chart)
     * Tabla de últimas 20 señales con resultado
   - Stack:
     * Streamlit + Plotly para gráficos interactivos
     * Consume `data/trading_signals_dataset.jsonl`
     * Dockerizar en contenedor separado (puerto 8501)

---

## 🟡 Nivel 2: Intermedia (Arquitectura y Estabilidad)
Requieren cambios estructurales en ConnectionService o gestión de datos.

6. **Multi-Timeframe Analysis (MTA) - Confirmación de Tendencia** 🛡️
   - Contexto Binarias: "La tendencia es tu amiga". Filtrar ruido de 1m.
   - Descripción: Validar la señal de 1m consultando la tendencia en 5m.
   - Tarea:
     * Modificar `ConnectionService` para suscribirse al canal de 5 minutos en paralelo
     * Crear un segundo buffer de datos en `AnalysisService`
     * Regla: Solo emitir señal BAJISTA en 1m si EMA 200 en 5m indica BAJISTA
   - Configuración: `USE_MTF_CONFIRMATION=true/false` en `.env`

7. **Reactivación de "Dual-Source" (Arbitraje de Data)**
   - Descripción: Reactivar la comparación OANDA vs FX.
   - Regla: Si la diferencia de precio entre brokers es > 2 pips (spread alto/manipulación), pausar alertas temporalmente para evitar entradas falsas en IQ Option.
   - Tarea:
     * Descomentar configuración de OANDA en `config.py`
     * Validar lógica de buffer dual en `telegram_service.py`
     * Agregar campo `price_spread` en notificaciones

8. **Script de Backtesting Real**
   - Descripción: Utilizar el dataset `trading_signals_dataset.jsonl` generado.
   - Tarea: 
     * Script `scripts/backtest_dataset.py` que simule operaciones pasadas
     * Calcular Win Rate real, PnL total, drawdown máximo
     * Análisis por patrón, por signal_strength, por score range
   - Output: Reporte HTML con gráficos de performance
   - Fundamental para ajustar umbrales de confianza

---

## 🔴 Nivel 3: Compleja (Estratégicas / I+D)
Features avanzadas que requieren integraciones externas o lógica matemática pesada.

9. **Detección de Divergencias (MACD/RSI)** 💎
   - Contexto Binarias: La señal "Sniper". Probabilidad de acierto muy alta.
   - Descripción: El precio hace un máximo más alto, pero el RSI hace un máximo más bajo.
   - Complejidad: Requiere analizar picos y valles en series temporales históricas, no solo la vela actual.
   - Implementación:
     * Función `detect_divergence()` con análisis de últimas 20 velas
     * Detección de swing highs/lows usando `scipy.signal.find_peaks`
     * Comparación de pendiente precio vs RSI/MACD
     * Nuevo tipo de señal: `DIVERGENCE_BULLISH` / `DIVERGENCE_BEARISH`

10. **Filtro de Noticias Fundamentales (News Filter)**
    - Contexto Binarias: Evitar operar durante NFP, FOMC, CPI (el análisis técnico no sirve ahí).
    - Descripción: Integrar API externa (ej. ForexFactory o Investing.com).
    - Regla: Bloquear alertas 30 min antes y después de noticias de "Alto Impacto" (Carpeta Roja).
    - Implementación:
      * Servicio `news_service.py` con cache de eventos económicos
      * Cronjob diario para actualizar calendario
      * Variable `ENABLE_NEWS_FILTER=true/false`
      * Mostrar próximo evento en comando `/status`

11. **Machine Learning Predictivo (Gradient Boosting)**
    - Descripción: Entrenar modelo que PREDIGA probabilidad en lugar de solo consultar historial.
    - Features de entrada:
      * Patrón detectado (one-hot encoding)
      * Momentum score (-10 a +10)
      * Exhaustion type (PEAK/BOTTOM/NONE)
      * Volatilidad reciente
      * Hora del día (sesión asiática/europea/americana)
      * RSI, MACD, ATR
    - Target: Probabilidad de éxito (0-1)
    - Stack: `scikit-learn` (GradientBoostingClassifier) o `xgboost`
    - Entrenamiento: Script `scripts/train_model.py` que lee dataset JSONL
    - Integración: Nuevo servicio `ml_service.py` que carga modelo .pkl
    - Mostrar predicción en alertas junto a probabilidad histórica

12. **Gestión de Capital (Martingala/Interés Compuesto)**
    - Contexto Binarias: Estrategia de recuperación común.
    - Descripción: Agregar un contador de rachas en memoria (no persistente necesariamente).
    - Regla: Si la señal anterior falló (detectado por el ciclo de cierre de vela), sugerir en la siguiente alerta: "Inversión sugerida: x2.2 para recuperar". 
    - **Nota:** Debe ser opcional/configurable. Martingala es arriesgado.
    - Implementación:
      * Variable `ENABLE_MARTINGALE=true/false`
      * Variable `MARTINGALE_MULTIPLIER=2.2` (configurable)
      * Contador de rachas perdidas en `AnalysisService`
      * Campo `suggested_investment_multiplier` en PatternSignal
      * Mostrar con advertencia en notificación: "⚠️ Martingala activa: 2.2x"

---

## Prioridad del Próximo Sprint (v0.0.5)

1. Implementación Patrón Engulfing (Simple) - 2-3 días
2. Dashboard de Estadísticas con Streamlit (Intermedia) - 3-5 días
3. Script de Backtesting Real (Intermedia) - 2-3 días

**Total estimado:** 7-11 días de desarrollo

---

**Notas:**
- Las features completadas (✅) ya NO deben ser trabajadas de nuevo.
- El backlog se actualiza tras cada sprint para reflejar el progreso real.
- Las estimaciones de complejidad son aproximadas y pueden variar según descubrimientos técnicos.
