# Información

Estoy realizando un bot que al detectar cierto patrones de velas en una tendencia alcista o bajista, al detectar un agotamiento, dispara una notificación hacia telegram para que la vea un humano y decida si operar.

# Estrategia

Opero en velas de un minuto. Opero en binarias en IQ OPTION. Tengo 30 segundos en la formación de la vela para definir si sube o baja y una vez que cierra la vela, se define si gané o perdí (desde mi punto de entrada inicial).

Opero a contra tendencia. Son tendencias cortas (10 velas aproximadamente). Cuando noto un agotamiento, puede ser que el precio corrija o sea el inicio de un cambio de tendencia, por tal motivo, opero a contra tendencia.

## Mis puntos de entrada (Bot vs Humano):

El sistema funciona con una **colaboración Bot-Humano**:

1.  **Notificación del Bot (Trigger):**
    *   El bot analiza el mercado y detecta el patrón (Shooting Star, Hammer, etc.) **al cierre de la vela**.
    *   Envía la alerta inmediatamente a Telegram.
    *   *En este punto NO se entra al mercado todavía.*

2.  **Ejecución Humana (Entry):**
    *   El trader recibe la alerta y observa el inicio de la siguiente vela (Vela de Confirmación).
    *   **Regla de Oro:** Esperar un **retroceso del 50%** del cuerpo de la vela trigger.
        *   *Ejemplo Bajista:* Si la vela trigger fue verde y cerró arriba, esperamos que la siguiente vela suba un poco más (retest) hasta el 50% del cuerpo anterior antes de entrar a la BAJA.
        *   *Ejemplo Alcista:* Si la vela trigger fue roja y cerró abajo, esperamos que la siguiente vela baje un poco más (retest) hasta el 50% del cuerpo anterior antes de entrar al ALZA.
    *   Esta "finessing" o ajuste fino es manual. El bot provee la señal, el humano ejecuta la entrada precisa.
