# Información

Estoy realizando un bot que al detectar cierto patrones de velas en una tendencia alcista o bajista, al detectar un agotamiento, dispara una notificación hacia telegram para que la vea un humano y decida si operar.

# Estrategia

Opero en velas de un minuto. Opero en binarias en IQ OPTION. Tengo 30 segundos en la formación de la vela para definir si sube o baja y una vez que cierra la vela, se define si gané o perdí (desde mi punto de entrada inicial).

Opero a contra tendencia. Son tendencias cortas (10 velas aproximadamente). Cuando noto un agotamiento, puede ser que el precio corrija o sea el inicio de un cambio de tendencia, por tal motivo, opero a contra tendencia.

## Mis puntos de entrada:

Tenemos las velas "gatillo" en tendencias alcistas: SHOOTING_STAR o INVERTED_HAMMER.

Tenemos las velas "gatillo" en tendencias bajistas: HAMMER o HANGING_MAN.

Cuando se presenta un patrón de esos, opero en los 30 segundos de la siguiente vela.

Si es en una tendencia alcista, espero que la vela en formación llegue al 50% del cuerpo de la vela anterior para operar a la baja.

Si es en una tendencia bajista, espero que la vela en formación llegue al 50% del cuerpo de la vela siguiente para operar a la baja.
