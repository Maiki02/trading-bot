# Backtesting V8 (IQ Option y Quotex)

Esta carpeta separa la generacion de dataset historico por proveedor y deja un analizador unico para cualquier archivo JSONL de salida.

## Archivos

- backtesting_historical_data_v8_iqoption.py: genera dataset V8 usando IQ Option.
- backtesting_historical_data_v8_quotex.py: genera dataset V8 usando Quotex (chunks de 196 velas).
- analyze_backtest_v8.py: analiza cualquier dataset JSONL V8 con estrategia de entrada por retroceso.

## Requisitos

- Variables de entorno configuradas en .env.
- Dependencias instaladas (requirements.txt).
- Para Quotex: QUOTEX_EMAIL, QUOTEX_PASSWORD y QUOTEX_ASSETS.
- Para IQ Option: IQ_OPTION_USER, IQ_OPTION_PASS y TARGET_ASSETS.

### Estrategia de conexion Quotex (script V8)

- El script de Quotex usa una estrategia por fases con credenciales:
	- Fase 1: persisted (si existe sesion valida en session.json para QUOTEX_EMAIL).
	- Fase 2: fresh (login normal con email/password).
- Cada fase aplica reintentos con backoff exponencial corto.
- Al conectar, cambia la cuenta a PRACTICE automaticamente.
- No usa QUOTEX_AUTH_METHOD ni QUOTEX_SSID en este flujo.

## Uso rapido

### 1) Generar dataset desde IQ Option

```bash
python scripts/backtesting_v8/backtesting_historical_data_v8_iqoption.py --days 30
```

Salida:

- data/trading_signals_dataset_v8_iqoption.jsonl

### 2) Generar dataset desde Quotex

Descarga historico desde una fecha especifica hasta ahora (o hasta fecha fin opcional), con chunks de 196 velas por request.

```bash
python scripts/backtesting_v8/backtesting_historical_data_v8_quotex.py --start-date 2026-01-01
```

Con fecha de fin opcional:

```bash
python scripts/backtesting_v8/backtesting_historical_data_v8_quotex.py --start-date 2026-01-01 --end-date 2026-03-01
```

Salida:

- data/trading_signals_dataset_v8_quotex.jsonl

### 3) Analizar dataset (IQ o Quotex)

```bash
python scripts/backtesting_v8/analyze_backtest_v8.py --file data/trading_signals_dataset_v8_iqoption.jsonl
```

```bash
python scripts/backtesting_v8/analyze_backtest_v8.py --file data/trading_signals_dataset_v8_quotex.jsonl
```

Filtros y parametros opcionales:

```bash
python scripts/backtesting_v8/analyze_backtest_v8.py --file data/trading_signals_dataset_v8_quotex.jsonl --symbol EURUSD --entry_pct 0.5 --safety_margin 0.1
```
