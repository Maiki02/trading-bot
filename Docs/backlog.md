# Product Backlog - TradingView Pattern Monitor (Binary Options Focus)
- Última actualización: 22 de Noviembre de 2025
- Objetivo: Evolucionar el MVP v0.0.2 hacia una herramienta profesional de señales para Opciones Binarias (IQ Option).

## 🟢 Nivel 1: Simple / Quick Wins (Prioridad Alta)
Mejoras de alto impacto en la calidad de la señal o usabilidad que requieren baja complejidad arquitectónica.

1. Implementación de Patrón "Engulfing" (Envolvente) 🚀
Contexto Binarias: Señal de reversión inmediata muy fuerte. Ideal para operaciones de 1 a 5 minutos.
Descripción: Detectar cuando el cuerpo de la vela actual cubre totalmente el cuerpo de la vela anterior con color opuesto.
Tarea:
Crear lógica matemática en src/logic/candle.py.
Integrar en analysis_service.py manteniendo la lógica de tendencia.
Actualizar formateo en telegram_service.py.
2. Filtro de RSI (Relative Strength Index)
Contexto Binarias: Evita entrar en operaciones cuando el movimiento ya se agotó (trampa común en binarias).
Descripción: Calcular RSI (14 periodos).
Regla:
VENTA (Shooting Star/Engulfing Bearish): Solo si RSI > 70 (Sobrecompra) o bajando de 70.
COMPRA (Hammer/Engulfing Bullish): Solo si RSI < 30 (Sobreventa) o subiendo de 30.
3. Sugerencia de Tiempo de Expiración
Contexto Binarias: Reemplaza el Stop Loss/Take Profit.
Descripción: Analizar la volatilidad (cuerpo promedio de las últimas 5 velas).
Regla:
Volatilidad Alta: Sugerir "Expiración: 1-2 minutos" (movimiento rápido).
Volatilidad Baja: Sugerir "Expiración: 5+ minutos" (el precio tarda en reaccionar).
4. Gestión de Capital (Martingala/Interés Compuesto)
Contexto Binarias: Estrategia de recuperación común.
Descripción: Agregar un contador de rachas en memoria (no persistente necesariamente).
Regla: Si la señal anterior falló (detectado por el ciclo de cierre de vela), sugerir en la siguiente alerta: "Inversión sugerida: x2.2 para recuperar". Nota: Debe ser opcional/configurable.
5. Comando de Estado /status
Descripción: Endpoint en Telegram para verificar salud del sistema.
Output: "🟢 Online | Uptime: 4h 20m | Última vela: 1.0540 | Tendencia: BULLISH | Buffer: 1000 velas".

## 🟡 Nivel 2: Intermedia (Arquitectura y Estabilidad)
Requieren cambios estructurales en ConnectionService o gestión de datos.
6. Multi-Timeframe Analysis (MTA) - Confirmación de Tendencia 🛡️
Contexto Binarias: "La tendencia es tu amiga". Filtrar ruido de 1m.
Descripción: Validar la señal de 1m consultando la tendencia en 5m.
Tarea:
Modificar ConnectionService para suscribirse al canal de 5 minutos en paralelo.
Crear un segundo buffer de datos en AnalysisService.
Regla: Solo emitir señal BAJISTA en 1m si EMA 200 en 5m indica BAJISTA.
7. Dockerización (Despliegue)
Descripción: Contenerizar la aplicación para despliegue agnóstico.
Entregables: Dockerfile optimizado (multi-stage build) y docker-compose.yml con variables de entorno y volúmenes para logs/data.
8. Reactivación de "Dual-Source" (Arbitraje de Data)
Descripción: Reactivar la comparación OANDA vs FX.
Regla: Si la diferencia de precio entre brokers es > 2 pips (spread alto/manipulación), pausar alertas temporalmente para evitar entradas falsas en IQ Option.
9. Script de Backtesting Real
Descripción: Utilizar el dataset trading_signals_dataset.jsonl generado.
Tarea: Script que simule operaciones pasadas y calcule el Win Rate real si se hubieran tomado todas las señales. Fundamental para ajustar umbrales de confianza.

## 🔴 Nivel 3: Compleja (Estratégicas / I+D)
Features avanzadas que requieren integraciones externas o lógica matemática pesada.
10. Detección de Divergencias (MACD/RSI) 💎
Contexto Binarias: La señal "Sniper". Probabilidad de acierto muy alta.
Descripción: El precio hace un máximo más alto, pero el RSI hace un máximo más bajo.
Complejidad: Requiere analizar picos y valles en series temporales históricas, no solo la vela actual.
11. Filtro de Noticias Fundamentales (News Filter)
Contexto Binarias: Evitar operar durante NFP, FOMC, CPI (el análisis técnico no sirve ahí).
Descripción: Integrar API externa (ej. ForexFactory o similar).
Regla: Bloquear alertas 30 min antes y después de noticias de "Alto Impacto" (Carpeta Roja).
12. Dashboard Web de Monitoreo
Descripción: Interfaz visual (Angular/React) que consuma una API del bot.
Funcionalidad: Ver gráfico en tiempo real con los patrones marcados, historial de señales y métricas de rendimiento sin depender de Telegram.
13. Diagnóstico con IA (Experimental)
Descripción: Enviar snapshot de datos a LLM (GPT-4o/Claude) para análisis de sentimiento.
Constraint: Evaluar latencia vs beneficio. Posiblemente solo para resumen diario post-mercado, no para señales en tiempo real de 1m.
Prioridad del Próximo Sprint:
Implementación Patrón Engulfing (Simple).
Filtro RSI (Simple).
Dockerización (Intermedia).
