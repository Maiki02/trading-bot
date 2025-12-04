
#### ÉPICA 1: Refinamiento de Micro-Estructura (CORE) 🟥 *Alta Prioridad*
*El objetivo es limpiar el ruido y adaptar el bot a la velocidad de 1 minuto.*

* **TASK-1.1: Purga de EMAs Lentas.** ✅ *Completado el 03/12/2025*
    * Eliminar cálculo y graficación de EMA 50, 100 y 200.
    * Implementar cálculo de EMA 3.
    * Reajustar el *Weighted Score* para usar solo: EMA 3, 5, 7, 10, 20.
* **TASK-1.2: Implementación de RSI (Relative Strength Index).** ✅ *Completado el 03/12/2025*
    * Calcular RSI de 14 periodos (estándar) o 7 periodos (más reactivo para M1).
    * Agregar condición de filtrado: Solo operar reversión bajista si $RSI > 70$ (o 75). Solo reversión alcista si $RSI < 30$ (o 25).

#### ÉPICA 2: Optimización de Latencia y Despliegue 🟧 *Alta Prioridad*
*En binarias, 200ms es la diferencia entre un buen punto de entrada y uno malo.*

* **TASK-2.1: Modo "Low Latency" (Switch de Gráficos).** ✅ *Completado el 02/12/2025*
    * Actualmente generar el gráfico tarda ~220ms. Implementar lógica para enviar la señal de texto **inmediatamente** (`await telegram.send_text(...)`) y generar/enviar la imagen en un hilo secundario *después*.
    * El trader necesita la alerta textual YA. La foto puede llegar 2 segundos después.
* **TASK-2.2: Despliegue en VPS/Cloud.**
    * Configurar Droplet en DigitalOcean, AWS EC2 (t2.micro) o Google Cloud.
    * Desplegar contenedor Docker. Asegurar reinicio automático (`restart: always`).
    * Esto elimina el riesgo de cortes de luz/internet en tu PC local.

#### ÉPICA 3: Expansión del Arsenal de Patrones 🟨 *Media Prioridad*
*Más herramientas para detectar agotamiento.*

* **TASK-3.1: Detección de Engulfing (Envolventes).**
    * Implementar lógica matemática para *Bullish* y *Bearish Engulfing*.
    * Integrar al sistema de *Weighted Score*.
* **TASK-3.2: Detección de Doji.**
    * Implementar lógica para Doji clásico, Dragonfly y Gravestone.
    * El Doji por sí solo no es señal, pero Doji + Bollinger Peak = Señal muy fuerte.

#### ÉPICA 4: Data Science & Backtesting (Simulación) 🟩 *Media/Baja Prioridad*
*Validar si la estrategia gana dinero antes de arriesgar capital.*

* **TASK-4.1: Motor de Backtesting sobre JSONL.**
    * Crear script que recorra `trading_signals_dataset.jsonl`.
    * **Lógica de Simulación:**
        * Entrada: Cierre de la vela *Trigger*.
        * Resultado: Cierre de la vela *Outcome*.
        * Calcular PnL asumiendo payout fijo (ej. 85%).
    * Generar reporte: "Si hubieras operado todas las señales HIGH SCORE con RSI > 70, tu PnL sería $X".
* **TASK-4.2: Análisis de "Retroceso al 50%".**
    * Analizar en el dataset (si tienes datos OHLC tick a tick o de segundos, si no, no se puede hacer preciso con velas de 1m cerradas) si el precio tocó el 50% de la mecha antes de revertir. *Nota: Esto es difícil si solo guardas OHLC de 1 min. Necesitarías guardar datos de velas de 5 segundos o Ticks para validar esto.*
* **TASK-4.X: Validación de Entry Point en Backtesting.** 🟥 *Alta Prioridad*
    * **Descripción:** Modificar `backfill_historical_data.py` para validar trades basados en la regla de entrada de la estrategia (retroceso del 50%) usando High/Low de la vela outcome.
    * **Criterios de Aceptación:** El dataset debe distinguir entre "WIN", "LOSS" y "NO_ENTRY" (el precio no llegó a la orden límite).
    * **Nota:** Diferenciar PnL de "Entrada al Cierre" vs "Entrada al 50%".

---

### Resumen de Cambios en la Lógica de Negocio

Actualmente tu bot (v0.0.5) piensa así:
1.  **Trend & Slope (V7):** Calcula la pendiente de la EMA 3 y la estructura de EMAs (3, 5, 7, 10, 20) para determinar el momentum inmediato.
2.  **RSI (v8.0):** Observa el RSI (7 periodos) para detectar sobre-extensión, aunque aún no filtra estrictamente por este valor (fase de recolección de datos).
3.  **Patrón de Vela:** Busca gatillos (Shooting Star, Hammer, etc.).
4.  **Dispara alerta de texto inmediato.**
5.  Procesa imagen y estadísticas después.