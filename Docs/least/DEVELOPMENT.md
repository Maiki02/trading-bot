# Guía de Desarrollo - Trading Bot MVP v0.0.1

## Arquitectura del Sistema

### Principios de Diseño

1. **Event-Driven Architecture:** Todo el sistema opera bajo un único event loop de `asyncio`
2. **Dependency Injection:** Los servicios reciben callbacks como parámetros
3. **Single Responsibility:** Cada módulo tiene una responsabilidad claramente definida
4. **Graceful Degradation:** Reconexión automática con backoff exponencial

### Flujo de Datos

```
┌─────────────────────────────────────────────────────────────┐
│                      TradingView WebSocket                   │
│                 wss://data.tradingview.com                   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ Raw Messages
                         ▼
          ┌──────────────────────────────┐
          │   Connection Service         │
          │   - Multiplexing             │
          │   - Authentication           │
          │   - Heartbeat                │
          │   - Protocol Decoding        │
          │                              │
          │   TWO SEPARATE METHODS:      │
          │   📥 _load_historical_       │
          │       snapshot()             │
          │       (timescale_update)     │
          │                              │
          │   🕒 _process_realtime_      │
          │       update()               │
          │       (du)                   │
          └──────────────┬───────────────┘
                         │
                         │ List[CandleData] or CandleData
                         ▼
          ┌──────────────────────────────┐
          │   Analysis Service           │
          │                              │
          │   TWO SEPARATE METHODS:      │
          │   📥 load_historical_        │
          │       candles()              │
          │       (NO charts, NO alerts) │
          │                              │
          │   🕒 process_realtime_       │
          │       candle()               │
          │       (YES charts, alerts)   │
          │                              │
          │   - pandas DataFrame Buffer  │
          │   - EMA 200 Calculation      │
          │   - Pattern Detection        │
          │   - Trend Filtering          │
          └──────────────┬───────────────┘
                         │
                         │ PatternSignal Objects
                         ▼
          ┌──────────────────────────────┐
          │   Telegram Service           │
          │   - Dual-Source Logic        │
          │   - Temporal Window (2s)     │
          │   - Alert Formatting         │
          │   - Chart Generation         │
          │   - Base64 Image Saving      │
          │   - HTTP API Client          │
          └──────────────┬───────────────┘
                         │
                         │ HTTP POST
                         ▼
          ┌──────────────────────────────┐
          │   Telegram API               │
          │   (External Service)         │
          └──────────────────────────────┘
```

### Arquitectura de Procesamiento de Velas

**PROBLEMA RESUELTO:** Antes se usaba un solo método con flags (`is_realtime`) para procesar tanto el snapshot inicial (1000 velas) como las velas en tiempo real (WebSocket). Esto causaba:
- 330+ logs de "GENERATING CHART" durante el inicio
- DataFrame no se cargaba correctamente (mostraba 18/600 velas)
- Lógica confusa con múltiples flags

**SOLUCIÓN:** Separación completa de responsabilidades

#### 1. Snapshot Inicial (1000 velas históricas)

**TradingView Message:** `timescale_update`
```json
{
  "m": "timescale_update",
  "p": [
    "cs_abc123",
    {
      "s": [
        {"v": [timestamp1, open1, high1, low1, close1, volume1]},
        {"v": [timestamp2, open2, high2, low2, close2, volume2]},
        ...  // 1000 candles total
      ]
    }
  ]
}
```

**Flow:**
```
ConnectionService._load_historical_snapshot()
  └─> Extrae array completo de 1000 velas
  └─> Crea List[CandleData]
  └─> AnalysisService.load_historical_candles(candle_list)
      └─> Carga en bloque al DataFrame
      └─> NO genera gráficos
      └─> NO envía alertas a Telegram
      └─> Log: "✅ FX_EURUSD initialized with 1000 candles"
```

#### 2. Actualización en Tiempo Real (1 vela nueva)

**TradingView Message:** `du` (data update)
```json
{
  "m": "du",
  "p": [
    "cs_abc123",
    {
      "s1": {
        "s": [
          {"v": [timestamp, open, high, low, close, volume]}
        ]
      }
    }
  ]
}
```

**Flow:**
```
ConnectionService._process_realtime_update()
  └─> Extrae UNA sola vela
  └─> Crea CandleData
  └─> AnalysisService.process_realtime_candle(candle)
      └─> Detecta si es nueva vela (timestamp diferente)
      └─> Agrega al DataFrame
      └─> Calcula EMA 200
      └─> Detecta patrones (Shooting Star, Doji, etc.)
      └─> GENERA gráfico con mplfinance
      └─> ENVÍA alerta a Telegram
      └─> Guarda chart en logs/chart_*.png
```

---

## Extendiendo el Sistema

### Agregar un Nuevo Patrón de Vela

**1. Definir la función de detección en `analysis_service.py`:**

```python
def is_hammer(
    open_price: float,
    high: float,
    low: float,
    close: float
) -> tuple[bool, float]:
    """
    Detecta si una vela es un Martillo (Hammer).
    
    Criterios:
    - Cuerpo pequeño en la parte superior
    - Mecha inferior larga (>= 2x cuerpo)
    - Mecha superior mínima
    """
    body = abs(close - open_price)
    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low
    total_range = high - low
    
    if total_range == 0 or body == 0:
        return False, 0.0
    
    is_pattern = (
        lower_wick / total_range > 0.6 and
        body / total_range < 0.3 and
        upper_wick / total_range < 0.15 and
        lower_wick >= body * 2
    )
    
    confidence = 0.8 if is_pattern else 0.0
    return is_pattern, confidence
```

**2. Modificar `_analyze_last_closed_candle` para incluir el nuevo patrón:**

```python
# Detectar Shooting Star (venta)
is_shooting_star, conf_ss = is_shooting_star(...)
if is_shooting_star and trend == "BEARISH":
    self._emit_signal("SHOOTING_STAR", ...)

# Detectar Hammer (compra)
is_hammer_pattern, conf_h = is_hammer(...)
if is_hammer_pattern and trend == "BULLISH":
    self._emit_signal("HAMMER", ...)
```

---

### Agregar un Nuevo Par de Trading

**1. Modificar `config.py` para incluir el nuevo instrumento:**

```python
INSTRUMENTS: Dict[str, InstrumentConfig] = {
    "eurusd_primary": InstrumentConfig(
        symbol="EURUSD",
        exchange="OANDA",
        timeframe="1",
        full_symbol="OANDA:EURUSD"
    ),
    "eurusd_secondary": InstrumentConfig(
        symbol="EURUSD",
        exchange="FX",
        timeframe="1",
        full_symbol="FX:EURUSD"
    ),
    # NUEVO PAR
    "gbpusd_primary": InstrumentConfig(
        symbol="GBPUSD",
        exchange="OANDA",
        timeframe="1",
        full_symbol="OANDA:GBPUSD"
    ),
    "gbpusd_secondary": InstrumentConfig(
        symbol="GBPUSD",
        exchange="FX",
        timeframe="1",
        full_symbol="FX:GBPUSD"
    )
}
```

**2. No se requieren cambios en el código:** El sistema automáticamente suscribirá todos los instrumentos definidos en `Config.INSTRUMENTS`.

---

### Agregar un Nuevo Indicador Técnico

**Ejemplo: RSI (Relative Strength Index)**

**1. Crear función de cálculo en `analysis_service.py`:**

```python
def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Calcula el Relative Strength Index (RSI).
    """
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi
```

**2. Agregar columna al DataFrame en `_initialize_dataframe`:**

```python
self.dataframes[source_key] = pd.DataFrame(columns=[
    "timestamp", "open", "high", "low", "close", "volume", 
    "ema_200", "rsi_14"  # NUEVA COLUMNA
])
```

**3. Calcular en `_update_indicators`:**

```python
df["rsi_14"] = calculate_rsi(df["close"], period=14)
```

**4. Usar en la lógica de filtrado:**

```python
# Filtro adicional: RSI debe estar en sobreventa (<30) para compras
if is_hammer and trend == "BULLISH" and last_closed["rsi_14"] < 30:
    self._emit_signal(...)
```

---

## Testing

### Test Manual del Logger

```bash
python -m src.utils.logger
```

Esto ejecutará la demostración de todos los niveles de log con colores.

### Test de Configuración

```python
# test_config.py
from config import Config

try:
    Config.validate_all()
    print("✅ Configuration is valid")
    print(f"EMA Period: {Config.EMA_PERIOD}")
    print(f"Instruments: {list(Config.INSTRUMENTS.keys())}")
except ValueError as e:
    print(f"❌ Configuration error: {e}")
```

### Test de Patrón de Vela

```python
# test_pattern.py
from src.services.analysis_service import is_shooting_star

# Ejemplo de Shooting Star perfecta
open_price = 1.0540
high = 1.0580  # Mecha larga superior
low = 1.0535
close = 1.0542  # Cuerpo pequeño

is_pattern, confidence = is_shooting_star(open_price, high, low, close)
print(f"Is Shooting Star: {is_pattern}")
print(f"Confidence: {confidence:.2%}")
```

---

## Deployment en Oracle Cloud (OCI)

### Requisitos

- Instancia OCI Compute (Always Free Tier: VM.Standard.E2.1.Micro)
- Ubuntu 22.04 LTS
- Python 3.10+
- Systemd para gestión del servicio

### Setup

**1. Conectar vía SSH:**

```bash
ssh ubuntu@<IP_PUBLICA_OCI>
```

**2. Instalar dependencias del sistema:**

```bash
sudo apt update
sudo apt install -y python3.10 python3-pip python3-venv git
```

**3. Clonar el repositorio:**

```bash
git clone https://github.com/Maiki02/trading-bot.git
cd trading-bot
```

**4. Configurar entorno:**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**5. Crear archivo `.env`:**

```bash
nano .env
# Pegar la configuración con SessionID, API Keys, etc.
```

**6. Crear servicio Systemd:**

```bash
sudo nano /etc/systemd/system/tradingbot.service
```

Contenido:

```ini
[Unit]
Description=TradingView Pattern Monitor Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/trading-bot
Environment="PATH=/home/ubuntu/trading-bot/venv/bin"
ExecStart=/home/ubuntu/trading-bot/venv/bin/python main.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

**7. Habilitar e iniciar el servicio:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable tradingbot
sudo systemctl start tradingbot
```

**8. Verificar estado:**

```bash
sudo systemctl status tradingbot
sudo journalctl -u tradingbot -f  # Ver logs en tiempo real
```

---

## Monitoreo y Mantenimiento

### Ver logs en tiempo real

```bash
tail -f logs/trading_bot.log
```

### Verificar uso de CPU/RAM

```bash
top -p $(pgrep -f "python main.py")
```

### Reiniciar el servicio

```bash
sudo systemctl restart tradingbot
```

### Actualizar código

```bash
cd trading-bot
git pull origin main
sudo systemctl restart tradingbot
```

---

## Mejoras Futuras (Post-MVP)

- [ ] **Backtesting Engine:** Simular estrategia sobre datos históricos
- [ ] **Dashboard Web:** Visualización en tiempo real con Flask/FastAPI
- [ ] **Base de Datos:** Persistir señales en PostgreSQL/SQLite
- [ ] **Multi-Timeframe:** Análisis combinado (1m + 5m + 15m)
- [ ] **Machine Learning:** Optimización de umbrales con scikit-learn
- [ ] **Alertas por Email:** Redundancia de notificaciones
- [ ] **Trading Automation:** Integración con brokers (Oanda API, MetaTrader)

---

## Contribución

Para contribuir al proyecto:

1. Fork el repositorio
2. Crea una rama para tu feature: `git checkout -b feature/nueva-funcionalidad`
3. Commit tus cambios: `git commit -am 'Add nueva funcionalidad'`
4. Push a la rama: `git push origin feature/nueva-funcionalidad`
5. Crea un Pull Request

### Estándares de Código

- **PEP 8** compliance (usar `black` para formateo automático)
- **Type Hints** en todas las funciones
- **Docstrings** para funciones públicas
- **Logging** en lugar de `print()`
- **Tests** unitarios para lógica crítica

---

## Licencia

Este proyecto es de código abierto bajo licencia MIT.

---

## Contacto

Para preguntas técnicas o soporte, contacta a: **Maiki02** en GitHub.
