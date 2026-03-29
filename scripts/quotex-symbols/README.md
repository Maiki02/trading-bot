# Script: Listado de Simbolos Validos de Quotex

Este utilitario inicia sesion en Quotex y devuelve simbolos validos para usar en configuracion.

## Archivo

- `scripts/quotex-symbols/get_valid_symbols.py`
- `scripts/quotex-symbols/get_historical_candles.py`

## Que hace

1. Carga credenciales desde `.env`.
2. Se conecta a Quotex.
3. Cambia al modo de cuenta indicado (`PRACTICE` o `REAL`).
4. Consulta simbolos via `get_all_assets()`.
5. Filtra:
- `--scope all`: todos los simbolos descubiertos.
- `--scope open`: solo simbolos abiertos al momento de la consulta.
6. Guarda resultados en JSON y TXT manteniendo compatibilidad con consumidores anteriores.

## Variables de entorno usadas

- `QUOTEX_AUTH_METHOD` (`CREDENTIALS` o `SESSION`)
- `QUOTEX_EMAIL`
- `QUOTEX_PASSWORD`
- `QUOTEX_SSID` (solo para `SESSION`)
- `QUOTEX_WS_DEBUG`
- `QUOTEX_HISTORY_SYMBOL`
- `QUOTEX_HISTORY_ASSET_ID` (opcional, prioridad sobre `QUOTEX_HISTORY_SYMBOL`)
- `QUOTEX_HISTORY_CANDLES`
- `QUOTEX_HISTORY_ACCOUNT_MODE` (opcional, default: `PRACTICE`)
- `QUOTEX_HISTORY_OUTPUT_DIR` (opcional, default: `data/quotex-history`)
- `QUOTEX_SESSION_STRATEGY` (`AUTO` | `PERSISTED_ONLY` | `FRESH_ONLY`, default: `AUTO`)
- `QUOTEX_CONNECT_RETRIES` (opcional, default: `3`)
- `QUOTEX_CONNECT_RETRY_DELAY_SECONDS` (opcional, default: `2`)

## Uso

### PowerShell

```powershell
c:/Users/Pc/Desktop/Proyectos/Personales/trading-bot/.venv/Scripts/python.exe scripts/quotex-symbols/get_valid_symbols.py --scope open
```

### Opciones

- `--scope open|all` (default: `open`)
- `--account-mode PRACTICE|REAL` (default: `PRACTICE`)
- `--output-dir <ruta>` (default: `data/quotex-symbols`)

Ejemplo:

```powershell
c:/Users/Pc/Desktop/Proyectos/Personales/trading-bot/.venv/Scripts/python.exe scripts/quotex-symbols/get_valid_symbols.py --scope all --account-mode PRACTICE
```

## Salida

Se generan dos archivos en `data/quotex-symbols`:

- `valid_symbols_<scope>_<timestamp>.json`
- `valid_symbols_<scope>_<timestamp>.txt`

### Estructura del JSON (comportamiento actual)

El JSON exporta metadata completa por simbolo:

- `symbols`: lista plana de simbolos (compatibilidad hacia atras).
- `assets`: lista de objetos por activo con:
	- `id`
	- `symbol`
	- `name`
	- `open`
	- `payment`
	- `turbo_payment`
	- `profit_24h`
	- `profit_1m`
	- `profit_5m`

El TXT sigue exportando solo simbolos (uno por linea) para integraciones legacy.

## Notas

- Si el broker marca simbolos como cerrados/no disponibles, no apareceran en `--scope open`.
- Si aparece `Token Rejected` en la conexion, la sesion puede estar degradada y la lista puede salir incompleta.

## Script de Historico

Este utilitario autentica y solicita historico de velas japonesas usando siempre `WS_STREAM`:

1. Inicia `start_candles_stream(symbol, period=60)`.
2. Solicita bloque historico inicial con `get_candle_v2(symbol, period=60)`.
3. Normaliza OHLC (`time/open/high/low/close/ticks`) y detiene el stream de forma segura.

Siempre guarda respuesta cruda en JSON diagnostico para analisis, con `method_requested=WS_STREAM`, `method_used=GET_CANDLE_V2` y payload capturado.
Si hay OHLC valida, normaliza a `CandleData` y genera salidas de `raw`, `candle_data` y `chart`.

La conexion aplica una estrategia configurable por `.env`:

1. `AUTO` (default): intenta primero sesion persistida (`session.json`) y, si falla por token/sesion/connect false, pasa a sesion fresca.
2. `PERSISTED_ONLY`: solo usa bootstrap de `session.json`.
3. `FRESH_ONLY`: fuerza login fresco y no carga bootstrap de `session.json`.

En todos los modos aplica reintentos limitados con backoff corto y deja trazas por fase (`persisted`, `fresh`, `session_token`) en consola y en JSON raw.

Lee `QUOTEX_HISTORY_CANDLES` y resuelve el activo desde `.env` con esta prioridad:

1. `QUOTEX_HISTORY_ASSET_ID` (ejemplo: `69`)
2. `QUOTEX_HISTORY_SYMBOL` (fallback)

Usa `end_from_time` como entero estricto, imprime diagnostico del payload crudo en consola (`count`, `first`, `last`), normaliza la salida para mantener compatibilidad con `CandleData` y genera una imagen PNG con las velas cuando hay OHLC valida.
El timeout del request reutiliza `QUOTEX_REQUEST_TIMEOUT`.

### Ejecucion

```powershell
c:/Users/Pc/Desktop/Proyectos/Personales/trading-bot/.venv/Scripts/python.exe scripts/quotex-symbols/get_historical_candles.py
```

Modo urgente recomendado cuando hay sospecha de sesion stale/token bloqueado:

```powershell
$env:QUOTEX_SESSION_STRATEGY="FRESH_ONLY"
$env:QUOTEX_CONNECT_RETRIES="3"
$env:QUOTEX_CONNECT_RETRY_DELAY_SECONDS="2"
c:/Users/Pc/Desktop/Proyectos/Personales/trading-bot/.venv/Scripts/python.exe scripts/quotex-symbols/get_historical_candles.py
```

Configurar polling websocket:

```powershell
c:/Users/Pc/Desktop/Proyectos/Personales/trading-bot/.venv/Scripts/python.exe scripts/quotex-symbols/get_historical_candles.py
```

Prueba forzando resolucion por asset ID (`69`):

```powershell
$env:QUOTEX_HISTORY_ASSET_ID="69"
$env:QUOTEX_HISTORY_SYMBOL="AUDJPY"
c:/Users/Pc/Desktop/Proyectos/Personales/trading-bot/.venv/Scripts/python.exe scripts/quotex-symbols/get_historical_candles.py
```

### Salida

Genera siempre este archivo en `data/quotex-history`:

- `historical_api_raw_<symbol>_<timestamp>.json`

Cuando hay OHLC valida, ademas genera:

- `historical_raw_<symbol>_<timestamp>.json`
- `historical_candle_data_<symbol>_<timestamp>.json`
- `historical_chart_<symbol>_<timestamp>.png`

### Variables esperadas en `.env`

```env
QUOTEX_HISTORY_ASSET_ID=69
QUOTEX_HISTORY_SYMBOL=AUDJPY
QUOTEX_HISTORY_CANDLES=150
QUOTEX_SESSION_STRATEGY=AUTO
QUOTEX_CONNECT_RETRIES=3
QUOTEX_CONNECT_RETRY_DELAY_SECONDS=2
```

Si `QUOTEX_HISTORY_ASSET_ID` esta definido, se usa primero y `QUOTEX_HISTORY_SYMBOL` queda como respaldo.

### Notas tecnicas

- Los scripts usan import estandar desde `pyquotex.stable_api` (libreria instalada en el entorno).
- La version abierta de `pyquotex` sigue limitada por lo que el broker devuelve por websocket. En issues publicos recientes el autor confirma el limite practico de `199` velas por request, por lo que `150` esta dentro del rango esperado.
- Si `connect()` devuelve `success=True` pero el mensaje incluye `Token Rejected`, la sesion puede quedar degradada y la consulta de velas puede devolver vacio o timeout.
- La otra forma de conexion soportada por la libreria es `QUOTEX_AUTH_METHOD=SESSION` usando `QUOTEX_SSID` con `set_session(...)`. Ademas, en modo `CREDENTIALS` este script intenta reutilizar la sesion persistida en `session.json` y reautenticar si pyquotex responde `Token Rejected`.
- El JSON `historical_api_raw_*.json` incluye metadata de conexion (`strategy_requested`, `effective_phase`, intentos y categoria de error) para diagnosticar bloqueos de token/sesion.
- `WS_STREAM` usa `get_candle_v2(period=60)` para capturar el bloque historico inicial y normalizar OHLC para el pipeline de `CandleData`.
- Durante la captura se imprime resumen del payload crudo (`count`, `first`, `last`) para diagnostico rapido en consola.
- Se exporta `historical_api_raw_*.json` con `method_used` real y payload capturado para depuracion, incluso si no hubo OHLC valida.
- Limitacion conocida de este entorno: no se pudo ejecutar validacion con `py_compile` por falta/rotura del interprete Python disponible.

## Raw WebSocket Historical Probe

Diagnostico por conexion oficial de `pyquotex` + envio manual de evento `history/load` via sender interno (`send_websocket_request`), sin usar metodos historicos `get_candles/get_candle_v2/get_history_line`.

Archivo:

- `scripts/quotex-symbols/get_historical_candles_raw_ws.py`

Ejecutar (PowerShell):

```powershell
$env:QUOTEX_HISTORY_SYMBOL="AUDJPY_otc"
c:/Users/Pc/Desktop/Proyectos/Personales/trading-bot/.venv/Scripts/python.exe scripts/quotex-symbols/get_historical_candles_raw_ws.py
```

Variables usadas:

- `QUOTEX_AUTH_METHOD` (`CREDENTIALS` o `SESSION`)
- `QUOTEX_EMAIL`, `QUOTEX_PASSWORD`
- `QUOTEX_SSID` (solo cuando `QUOTEX_AUTH_METHOD=SESSION`)
- `QUOTEX_HISTORY_ACCOUNT_MODE` (default: `PRACTICE`)
- `QUOTEX_WS_DEBUG` (default: `false`)
- `QUOTEX_HISTORY_SYMBOL` (default: `AUDJPY_otc`)
- `QUOTEX_HISTORY_OFFSET` (default: `3600`)
- `QUOTEX_HISTORY_PERIOD` (default: `60`)
- `QUOTEX_WS_TIMEOUT` (default: `20`)
- `QUOTEX_WS_POLL_INTERVAL_SECONDS` (default: `0.2`)
- `QUOTEX_HISTORY_OUTPUT_DIR` (default: `data/quotex-history`)

Salida diagnostica JSON:

- `method_used=RAW_HISTORY_LOAD_VIA_LIB_WS`
- `auth_status` (resultado de `connect()`/`change_account(...)`)
- `request` (payload enviado a `history/load`)
- `history` (respuesta `history/list` o `history/list/v2` si aparece)
- `diagnostics` (sender usado, intentos de envio, polling y timeout)
