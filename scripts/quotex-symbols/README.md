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
6. Guarda resultados en JSON y TXT.

## Variables de entorno usadas

- `QUOTEX_AUTH_METHOD` (`CREDENTIALS` o `SESSION`)
- `QUOTEX_EMAIL`
- `QUOTEX_PASSWORD`
- `QUOTEX_SSID` (solo para `SESSION`)
- `QUOTEX_WS_DEBUG`
- `QUOTEX_HISTORY_SYMBOL`
- `QUOTEX_HISTORY_CANDLES`
- `QUOTEX_HISTORY_ACCOUNT_MODE` (opcional, default: `PRACTICE`)
- `QUOTEX_HISTORY_OUTPUT_DIR` (opcional, default: `data/quotex-history`)

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

## Notas

- Si el broker marca simbolos como cerrados/no disponibles, no apareceran en `--scope open`.
- Si aparece `Token Rejected` en la conexion, la sesion puede estar degradada y la lista puede salir incompleta.

## Script de Historico

Este segundo utilitario hace exactamente dos cosas:

1. `login_to_quotex()`
2. `fetch_historical_candles(symbol, candles_count)`

Lee `QUOTEX_HISTORY_SYMBOL` y `QUOTEX_HISTORY_CANDLES` desde `.env`.
Intenta primero una via alternativa de la libreria basada en `get_candle_v2()` y, si falla, cae a `get_candles()`.
Luego transforma la respuesta a `CandleData` y genera una imagen PNG con las velas.
El timeout del request reutiliza `QUOTEX_REQUEST_TIMEOUT`.

### Ejecucion

```powershell
c:/Users/Pc/Desktop/Proyectos/Personales/trading-bot/.venv/Scripts/python.exe scripts/quotex-symbols/get_historical_candles.py
```

### Salida

Genera tres archivos en `data/quotex-history`:

- `historical_raw_<symbol>_<timestamp>.json`
- `historical_candle_data_<symbol>_<timestamp>.json`
- `historical_chart_<symbol>_<timestamp>.png`

### Variables esperadas en `.env`

```env
QUOTEX_HISTORY_SYMBOL=AUDJPY
QUOTEX_HISTORY_CANDLES=150
```

### Notas tecnicas

- La version abierta de `pyquotex` sigue limitada por lo que el broker devuelve por websocket. En issues publicos recientes el autor confirma el limite practico de `199` velas por request, por lo que `150` esta dentro del rango esperado.
- Si `connect()` devuelve `success=True` pero el mensaje incluye `Token Rejected`, la sesion puede quedar degradada y cualquiera de los dos metodos de historico puede devolver vacio o timeout.
- La otra forma de conexion soportada por la libreria es `QUOTEX_AUTH_METHOD=SESSION` usando `QUOTEX_SSID` con `set_session(...)`. Ademas, en modo `CREDENTIALS` este script intenta reutilizar la sesion persistida en `session.json` y reautenticar si pyquotex responde `Token Rejected`.
