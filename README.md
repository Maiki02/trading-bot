# TradingView Pattern Monitor (v0.0.6)

Sistema automatizado de soporte a la decisión para trading de alta frecuencia (opciones binarias 1 minuto) que consume datos en tiempo real mediante WebSocket de TradingView. Detecta **4 patrones de velas japonesas** con validación matemática estricta, analiza tendencia con **scoring ponderado optimizado para momentum de corto plazo**, y clasifica señales mediante **Bollinger Bands Exhaustion System** con **probabilidades históricas** basadas en Machine Learning.

El bot incluye **sistema de estadísticas en tiempo real** que consulta el dataset histórico (JSONL) para mostrar win rate, PnL promedio y rachas de cada patrón en contextos similares. Totalmente **dockerizado** para producción 24/7.

---

## ⚡ Quick Start

**¿Primera vez?** → Lee **[DOCKER_GUIDE.md](./DOCKER_GUIDE.md)** para despliegue con Docker (recomendado para producción).

```powershell
# 1. Instalar dependencias
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Configurar .env
copy .env.example .env
notepad .env

# 3. Ejecutar localmente
python main.py

# O con Docker (producción)
docker-compose up -d --build
docker logs -f trading-bot
```

**Documentación completa más abajo** ⬇️

---

## 🚀 Características Principales (v0.0.6)

### 🎯 Detección de Patrones
* **4 Patrones Implementados:** Shooting Star, Hanging Man, Inverted Hammer, Hammer
* **Validación Matemática Estricta:** Criterios de proporciones (cuerpo ≤30%, mechas ≥60%, etc.)
* **Sistema de Confianza:** Scoring de 70-100% basado en condiciones excepcionales
* **Validación de Color:** Los patrones bajistas DEBEN ser velas rojas, alcistas verdes

### 📊 Análisis Técnico Avanzado
* **Momentum Scoring System:** Score ponderado -10 a +10 optimizado para opciones binarias
  * EMA 20 vs Precio: ±4 puntos (peso máximo - momentum inmediato)
  * EMA 20 vs EMA 50: ±3 puntos (confirmación de dirección)
  * Precio vs EMA 50: ±2 puntos (zona de valor)
  * Precio vs EMA 200: ±1 punto (contexto macro)
* **5 EMAs Calculadas:** 20, 30, 50, 100, 200 (con cálculo condicional)
* **Bollinger Bands Exhaustion System (BB 20, 2.5σ):**
  * Detección de zonas PEAK/BOTTOM/NONE
  * Clasificación de fuerza: HIGH 🚨🚨 / MEDIUM ⚠️ / LOW ℹ️
  * Filtrado de patrones contra-tendencia

### 📈 Probabilidad Histórica (Machine Learning Ready)
* **StatisticsService:** Consulta probabilidades en tiempo real desde dataset JSONL
* **Fuzzy Matching:** Busca señales con score similar (±1 tolerancia configurable)
* **Métricas Mostradas:**
  * Win Rate histórico (ej: 73.3% - 11/15 señales)
  * PnL Promedio en pips
  * Racha reciente (últimos 5 resultados: ✓ ✓ ✗ ✓ ✓)
  * Score range usado para la consulta
* **Raw Data Preservation:** Campo `raw_data` en JSONL permite recalcular scores retroactivamente

### 📱 Notificaciones Inteligentes
* **Alertas de Telegram** con clasificación por fuerza de señal
* **Gráficos Automáticos** con mplfinance (5 EMAs visualizadas, encoding Base64)
* **Notificaciones Duales:**
  * Patrón detectado (inmediato)
  * Resultado de vela outcome (1 min después): VERDE/ROJA/DOJI
* **Señales informativas (`NONE`):** si `SEND_NONE_SIGNAL_NOTIFICATIONS=true`, el bot puede avisar una detección sin prioridad operativa, y el mensaje de resultado posterior se marca como `NO ACTIVADA` en lugar de `GANADA/PERDIDA`
* **Control de Costos:** Variable `SEND_CHARTS` para desactivar imágenes en producción

### 🐳 Infraestructura
* **Dockerizado:** Dockerfile optimizado + docker-compose.yml con volúmenes persistentes
* **Logs con Rotación:** json-file driver (10MB × 3 archivos)
* **Timezone Sincronizada:** TZ=America/Argentina/Buenos_Aires
* **Health Check:** Monitoreo automático del proceso main.py
* **Graceful Shutdown:** Manejo correcto de señales SIGTERM

### 📊 Dataset de Machine Learning
* **Formato:** JSONL (JSON Lines) para append eficiente
* **Estructura Completa:**
  * Trigger candle (vela donde se detectó el patrón)
  * Outcome candle (vela siguiente - resultado)
  * Signal metadata (patrón, confianza, tendencia, score, EMAs, Bollinger)
  * Raw data (para recalcular scores si cambia la lógica)
  * Outcome (dirección esperada vs real, éxito/fracaso, PnL en pips)
  * Validation (gap temporal, flags de velas salteadas)
* **Ubicación:** `data/trading_signals_dataset.jsonl`

### 🧪 Testing Automatizado
* **Suite de Tests:** `test/test_candles.py` con validación de los 4 patrones
* **Visualización:** `test/visualize_patterns.py` - genera gráficos normalizados con validación
* **Auto-guardado:** Velas detectadas se agregan a `test/test_data.json`
* **Métricas:** Reporte de fidelidad, distribución válida/inválida, código de colores

---

## 🛠 Arquitectura del Proyecto

El sistema funciona bajo un bucle de eventos asíncrono (`asyncio`) dividido en **6 servicios modulares**:

1. **Connection Service:** Gestiona conexión WebSocket a TradingView, heartbeat pasivo, reconexión automática
2. **Analysis Service:** Buffer de 1000 velas, cálculo de EMAs, detección de patrones, Bollinger Bands, momentum scoring
3. **Telegram Service:** Notificaciones con clasificación de fuerza (HIGH/MEDIUM/LOW), generación de gráficos asíncronos
4. **Storage Service:** Persistencia en JSONL con validación de estructura y raw_data
5. **Statistics Service:** Consulta probabilidades históricas, fuzzy matching, análisis de rachas
6. **Charting Utilities:** Generación de gráficos con mplfinance, encoding Base64, visualización de 5 EMAs

**Modo de Operación Actual:** `USE_TREND_FILTER=false` (notifica todos los patrones detectados - delegación al trader)

## 📋 Requisitos Previos

* Python 3.10+
* Docker & Docker Compose (recomendado para producción)
* Cuenta de TradingView (opcional - el bot funciona sin autenticación para Forex)
* API Key propia para el servicio de Telegram

**Nota sobre Autenticación:** TradingView proporciona datos de Forex (FX:EURUSD) **sin requerir sessionid**. El campo `TV_SESSION_ID` en `.env` puede dejarse con valor `not_required_for_public_data`.

## ⚙️ Instalación y Configuración

### 1. Clonar el repositorio
```bash
git clone https://github.com/Maiki02/trading-bot.git
cd trading-bot
```

### 2. Crear entorno virtual e instalar dependencias

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Dependencia local de pyquotex (nuevo):**
- Por defecto, `requirements.txt` usa el repositorio oficial: `git+https://github.com/Maiki02/pyquotex.git`.
- Para desarrollo, puedes usar una carpeta local activando `USE_QUOTEX_LOCAL=true` en el `.env`.
- El sistema prioriza automáticamente la carpeta hermana `../pyquotex` (respecto a la raíz del bot) solo si `APP_ENV=development`.
- Todas las importaciones de Quotex deben realizarse desde `src.utils.quotex_bootstrap` para asegurar que se aplique esta lógica.

### 3. Configuración .env (Simplificada)

**Autenticación NO requerida** para datos de Forex público. Puedes usar el valor por defecto.

**Política actual para Quotex (app principal):**
- Siempre usa `QUOTEX_EMAIL` y `QUOTEX_PASSWORD`.
- `session.json` se reutiliza automaticamente cuando es valido.
- Si no hay sesion valida, pyquotex hace login por credenciales.
- Se crea una unica instancia de pyquotex compartida para todos los simbolos en `QUOTEX_ASSETS`.
- El login y `change_account("PRACTICE")` se ejecutan una sola vez en el orquestador antes de iniciar workers.
- Cada worker recibe el cliente ya autenticado por inyeccion de dependencia.
- Si `session.json` tiene token vencido, pyquotex hace fallback automatico: re-autentica por credenciales y reintenta el WebSocket.
- En consultas historicas (`get_candles` snapshot), pyquotex fuerza una suscripcion minima para disparar respuesta del broker y luego desuscribe para evitar fuga de red.
- En realtime/historico se prioriza el `asset`/`symbol` explicito del payload cuando esta disponible.
- El worker de Quotex descarta payloads realtime con simbolo explicito que no coincide con su simbolo esperado y deja warning en logs.
- En realtime multi-simbolo, cada item/candle/tick tambien se valida por simbolo explicito antes de entrar al buffer del worker.
- Si llega un frame realtime ambiguo (sin simbolo) justo despues de un mismatch reciente, el worker lo descarta temporalmente para evitar contaminacion cruzada.
- El arranque multi-simbolo usa tareas paralelas con `asyncio.gather` sobre una conexion WebSocket compartida.
- La reconexion por caida de red se realiza de forma global en el orquestador, con re-suscripcion de streams en todos los workers.
- Ya no se usan `QUOTEX_AUTH_METHOD` ni `QUOTEX_SSID` en la app principal.

**Enrutamiento de tópicos Telegram por entorno:**
- `APP_ENV=production` usa por defecto: `trade:alert` y `trade:send_result`
- `APP_ENV=development` usa por defecto: `test:trade:alert` y `test:trade:send_result`
- Overrides legacy (si no están vacíos) tienen prioridad: `TELEGRAM_SUBSCRIPTION` y `TELEGRAM_OUTCOME_SUBSCRIPTION`

```env
# ============= APP / GENERAL =============
APP_ENV=development

# ============= DATA PROVIDER =============
DATA_PROVIDER=QUOTEX
TARGET_ASSETS=EURUSD-BIN,GBPUSD-BIN,USDJPY-BIN
SNAPSHOT_CANDLES=250
GENERATE_HISTORICAL_CHARTS=false

# ============= TRADINGVIEW (Opcional para Forex) =============
TV_SESSION_ID=not_required_for_public_data
TV_WS_URL=wss://data.tradingview.com/socket.io/websocket
TV_WS_ORIGIN=https://data.tradingview.com

# ============= IQOPTION =============
IQ_OPTION_USER=tu_usuario_iq
IQ_OPTION_PASS=tu_password_iq
IQ_ASSET=EURUSD-BIN

# ============= QUOTEX =============
QUOTEX_EMAIL=tu_email_quotex
QUOTEX_PASSWORD=tu_password_quotex
QUOTEX_ASSETS=AUDJPY
QUOTEX_CONNECT_TIMEOUT=45
QUOTEX_REQUEST_TIMEOUT=20
QUOTEX_WS_DEBUG=false

# ============= TELEGRAM =============
TELEGRAM_API_URL=https://api.tu-dominio.com/telegram
TELEGRAM_API_KEY=tu_api_key_secreta
TELEGRAM_SUBSCRIPTION_PROD=trade:alert
TELEGRAM_OUTCOME_SUBSCRIPTION_PROD=trade:send_result
TELEGRAM_SUBSCRIPTION_DEV=test:trade:alert
TELEGRAM_OUTCOME_SUBSCRIPTION_DEV=test:trade:send_result
TELEGRAM_SUBSCRIPTION=
TELEGRAM_OUTCOME_SUBSCRIPTION=

# ============= NOTIFICATIONS =============
ENABLE_NOTIFICATIONS=true
SEND_CHARTS=false
SEND_OUTCOME_CHARTS=true
SEND_NONE_SIGNAL_NOTIFICATIONS=false
SAVE_NOTIFICATIONS_LOCALLY=true
UPDATE_TEST_DATA=false

# ============= STRATEGY / INDICATORS =============
EMA_PERIOD=50
DUAL_SOURCE_WINDOW=0.0
CHART_LOOKBACK=40
USE_TREND_FILTER=false
SHOW_CANDLE_RESULT=true
RSI_PERIOD=7
RSI_OVERBOUGHT=75
RSI_OVERSOLD=25

# ============= RECONNECTION =============
RECONNECT_INITIAL_TIMEOUT=5
RECONNECT_MAX_TIMEOUT=300

# ============= DEBUG / LOGGING =============
LOG_LEVEL=DEBUG
LOG_FILE=logs/trading_bot.log
```

**Ejemplo rápido por entorno:**
```env
# Desarrollo
APP_ENV=development
TELEGRAM_SUBSCRIPTION_DEV=test:trade:alert
TELEGRAM_OUTCOME_SUBSCRIPTION_DEV=test:trade:send_result

# Producción
APP_ENV=production
TELEGRAM_SUBSCRIPTION_PROD=trade:alert
TELEGRAM_OUTCOME_SUBSCRIPTION_PROD=trade:send_result
```

**⚠️ IMPORTANTE:** Si usas Docker, NO necesitas configurar `TV_SESSION_ID` manualmente. El bot funciona sin autenticación para Forex.

### 4. Opción A: Ejecutar con Docker (Recomendado para Producción)

```powershell
# Construir y levantar el bot en segundo plano
docker-compose up -d --build

# Ver logs en tiempo real
docker logs -f trading-bot

# Detener el bot
docker-compose stop

# Ver estado
docker ps
```

Ver documentación completa en **[DOCKER_GUIDE.md](./DOCKER_GUIDE.md)**

### 5. Opción B: Ejecutar Localmente (Desarrollo)

```powershell
python main.py
```

Deberías ver la siguiente salida si todo está correcto:

```
INFO     | 2025-11-24 14:30:00 | main | ╔══════════════════════════════════════════════════════════════╗
INFO     | 2025-11-24 14:30:00 | main | ║  TradingView Pattern Monitor - v0.0.6                         ║
INFO     | 2025-11-24 14:30:00 | main | ║  4-Pattern Detection + Bollinger Exhaustion System            ║
INFO     | 2025-11-24 14:30:00 | main | ║  Historical Probability Analysis (ML Ready)                   ║
INFO     | 2025-11-24 14:30:00 | main | ╚══════════════════════════════════════════════════════════════╝
INFO     | 2025-11-24 14:30:01 | main | ✅ Configuration validated
INFO     | 2025-11-24 14:30:01 | main | 📊 Statistics Service initialized (dataset: 0 records)
INFO     | 2025-11-24 14:30:01 | main | 💾 Storage Service initialized
INFO     | 2025-11-24 14:30:01 | main | 📱 Telegram Service initialized
INFO     | 2025-11-24 14:30:01 | main | 📊 Analysis Service initialized
INFO     | 2025-11-24 14:30:02 | main | 📡 Connecting to TradingView WebSocket...
INFO     | 2025-11-24 14:30:03 | main | ✅ FX:EURUSD connected - Buffer: 1000 velas
```

### 6. Detener el Bot

**Docker:**
```powershell
docker-compose stop
```

**Local:**
Presiona **Ctrl+C** para detener el bot de forma limpia (graceful shutdown).

---

## 🔧 Estructura del Proyecto

```
trading-bot/
├── Dockerfile                       # Imagen Python 3.10-slim optimizada
├── docker-compose.yml               # Orquestación con volúmenes persistentes
├── DOCKER_GUIDE.md                  # Cheatsheet de comandos Docker
├── .env                             # Variables de entorno (NO COMMITEAR)
├── .env.example                     # Plantilla de configuración
├── config.py                        # Configuración centralizada
├── main.py                          # Punto de entrada
├── requirements.txt                 # Dependencias Python
├── README.md                        # Este archivo
├── data/
│   ├── trading_signals_dataset.jsonl   # Dataset de ML (persistente)
│   └── notifications/                  # Mensajes y gráficos guardados
├── logs/                               # Logs de snapshots y debug
├── Docs/
│   ├── backlog.md                   # Product Backlog
│   ├── bollinger.md                 # Sistema de Bollinger Bands
│   ├── candle.md                    # Documentación de patrones
│   ├── resumen.md                   # Especificación completa del proyecto
│   ├── rsi.md                       # RSI
│   ├── strategy.md                  # Estrategia de trading
│   ├── tendencia.md                 # Momentum Scoring System
│   └── least/
│       └── sistema_probabilidad_historica.md  # Sistema de estadísticas
├── test/
│   ├── test_candles.py              # Suite de tests automatizados
│   ├── test_data.json               # Casos de prueba guardados
│   ├── visualize_patterns.py        # Herramienta de visualización
│   └── images_patterns/             # Gráficos generados por tests
└── src/
    ├── __init__.py
    ├── logic/
    │   ├── __init__.py
    │   ├── analysis_service.py      # Detección de patrones + Bollinger + Scoring
    │   └── candle.py                # Validación matemática de patrones
    ├── services/
    │   ├── __init__.py
    │   ├── connection_service.py    # WebSocket Client
    │   ├── telegram_service.py      # Notification System
    │   ├── storage_service.py       # JSONL Persistence
    │   └── statistics_service.py    # Historical Probability Analysis
    └── utils/
        ├── __init__.py
        ├── logger.py                # Centralized Logging
        └── charting.py              # mplfinance Chart Generation
```

---

## 🧪 Testing y Debugging

### Ejecutar Tests Automatizados

```powershell
# Test de patrones con validación estricta
python test/test_candles.py

# Visualización de patrones detectados (con validación)
python test/visualize_patterns.py

# Visualizar solo un patrón específico
python test/visualize_patterns.py --pattern hammer
```

### Ver logs detallados

Cambia el nivel de log en `.env`:

```env
LOG_LEVEL=DEBUG
```

Esto mostrará información detallada de cada vela recibida y cálculos internos.

### Verificar Dataset de Machine Learning

```powershell
# Ver últimas señales registradas
Get-Content data/trading_signals_dataset.jsonl -Tail 5 | ConvertFrom-Json | Format-List
```

### Analizar Estadísticas

```powershell
# Script de prueba del StatisticsService
python test_statistics_service.py
```

---

## 📊 Funcionamiento del Sistema (v0.0.6)

### Lógica de Detección Completa

1. **Conexión WebSocket:** Conexión a `data.tradingview.com` sin autenticación (datos públicos de Forex)
2. **Suscripción:** Canal `FX:EURUSD` en temporalidad 1 minuto
3. **Buffer Inicial:** Descarga 1000 velas históricas para convergencia de EMAs
4. **Análisis en Tiempo Real (cada vela cerrada):**
   * **Cálculo de Indicadores:**
     * 5 EMAs (20, 30, 50, 100, 200) con cálculo condicional
     * Bollinger Bands (periodo 20, desviación estándar 2.5)
     * Momentum Score (-10 a +10) con pesos optimizados para opciones binarias
   
   * **Detección de Patrones:**
     * Validación matemática de 4 patrones (criterios de proporciones + color)
     * Shooting Star / Hanging Man (DEBEN ser velas rojas)
     * Inverted Hammer / Hammer (DEBEN ser velas verdes)
     * Sistema de confianza 70-100% con bonos por condiciones excepcionales
   
   * **Clasificación por Bollinger Bands:**
     * PEAK (agotamiento alcista): Vela toca banda superior
     * BOTTOM (agotamiento bajista): Vela toca banda inferior
     * NONE (zona neutra): Entre bandas
     * Signal Strength: HIGH 🚨🚨 / MEDIUM ⚠️ / LOW ℹ️
   
   * **Consulta de Probabilidades:**
     * StatisticsService busca señales históricas con score similar
     * Calcula win rate, PnL promedio, racha reciente
     * Solo muestra si hay >5 casos históricos
   
   * **Generación de Gráfico:**
     * mplfinance con 5 EMAs visualizadas (colores diferenciados)
     * Lookback parametrizable (default: 30 velas)
     * Encoding Base64 en hilo separado (no bloquea WebSocket)
   
   * **Envío de Notificación:**
     * Telegram con clasificación de fuerza (HIGH/MEDIUM/LOW)
     * Incluye gráfico si `SEND_CHARTS=true`
     * Muestra probabilidad histórica si está disponible

5. **Ciclo de Outcome (1 minuto después):**
   * Al cerrar la vela siguiente, detecta dirección (VERDE/ROJA/DOJI)
   * Envía notificación de resultado
   * Construye registro completo con raw_data
   * Persiste en `data/trading_signals_dataset.jsonl`
   * Valida gap temporal (debe ser 60s exactamente)

### Ejemplo de Alerta con Probabilidad Histórica

```
🚨🚨 ALERTA FUERTE | BTCUSDT
Agotamiento ALCISTA confirmado (Cúspide)

━━━━━━━━━━━━━━━━━━━━━━━━
📊 INFO DE VELA
━━━━━━━━━━━━━━━━━━━━━━━━
🔹 Patrón: SHOOTING_STAR
🔹 Confianza Técnica: 90%
🔹 Fuerza de Señal: HIGH

━━━━━━━━━━━━━━━━━━━━━━━━
📊 PROBABILIDAD HISTÓRICA (Últimos 30 días)
━━━━━━━━━━━━━━━━━━━━━━━━
🟢 Win Rate: 73.3% (11/15 señales)
🎯 PnL Promedio: 245.7 pips
📈 Racha reciente: ✓ ✓ ✗ ✓ ✓
🔍 Score similar: [9, 11]

━━━━━━━━━━━━━━━━━━━━━━━━
📈 MOMENTUM SCORING
━━━━━━━━━━━━━━━━━━━━━━━━
🎯 Score: +9/10 (Momentum alcista muy fuerte)
EMA 20: 85234.12
EMA 50: 85089.46
EMA 200: 84923.12

🔺 Zona: Señal de agotamiento
🔹 Banda Superior: 85811.36
🔹 Banda Inferior: 85622.99

⚡ Revisar gráfico adjunto antes de operar.
```

---

## 🚨 Troubleshooting

### El bot no arranca con Docker

**Causa:** Falta el archivo `.env` o tiene configuración incorrecta.

**Solución:**
```powershell
# Verificar que existe
Test-Path .env

# Ver configuración actual
docker logs trading-bot

# Recrear desde ejemplo
copy .env.example .env
notepad .env
docker-compose up -d --build
```

### Error: "Telegram API request failed"

**Causa:** La URL o API Key de Telegram son incorrectas.

**Solución:**
1. Verifica que `TELEGRAM_API_URL` y `TELEGRAM_API_KEY` estén bien configurados
2. Prueba la API manualmente con `curl` o Postman
3. Revisa `APP_ENV` y los tópicos `TELEGRAM_SUBSCRIPTION_*` / `TELEGRAM_OUTCOME_SUBSCRIPTION_*`
4. Si usas overrides legacy, confirma que `TELEGRAM_SUBSCRIPTION` y `TELEGRAM_OUTCOME_SUBSCRIPTION` no apunten a tópicos incorrectos

### Quotex inicia pero no carga histórico de 1 minuto

**Síntoma en logs:** timeout o payload vacío durante `Historical bootstrap`, y luego varios mensajes `Realtime websocket payload has insufficient points`.

**Qué significa:** el stream realtime de Quotex puede comenzar con una sola vela en formación. Hasta que no cierra la siguiente vela, no hay dos puntos para tomar la última vela cerrada.

**Comportamiento actual del bot:**
- Para evitar colisiones internas de pyquotex, cada activo configurado usa su propio cliente, buffer realtime y ciclo de reconexion.
- Hace hasta **2 intentos** de bootstrap histórico (activo principal + fallback) y luego continúa el arranque.
- Usa estrictamente los símbolos configurados en `.env` (`QUOTEX_ASSETS`) sin autoconvertir `EURUSD` ↔ `EURUSD_otc`.
- Respeta `QUOTEX_REQUEST_TIMEOUT` del `.env` para cada intento histórico.
- Usa credenciales (`QUOTEX_EMAIL`/`QUOTEX_PASSWORD`) y permite reutilizar `session.json` automáticamente.
- Si el stream realtime llega con **1 solo punto**, lo trata como vela en formación (generating) y espera un segundo punto para confirmar vela cerrada.
- En recuperación de GAP, reinyecta solo **velas intermedias faltantes**; la vela cerrada más reciente se procesa una sola vez desde realtime.
- Para análisis, Quotex procesa vela cerrada como `timestamps[-2]` y usa `timestamps[-1]` solo como referencia de vela en formación.

**Recomendación de configuración:**
```env
QUOTEX_REQUEST_TIMEOUT=20      # Requests normales
QUOTEX_CONNECT_TIMEOUT=45      # Login y conexión
SNAPSHOT_CANDLES=150-250       # Ajusta según EMA usada
```

### El bot no detecta patrones

**Posibles causas:**
- El mercado no está generando los patrones en este momento
- Buffer aún no tiene suficientes velas (espera 1-2 minutos tras iniciar)
- `USE_TREND_FILTER=true` está bloqueando señales (cambia a `false` para modo MVP)

**Solución:**
```env
# En .env
LOG_LEVEL=DEBUG  # Ver cada vela procesada
USE_TREND_FILTER=false  # Notificar todos los patrones
```

Verifica que aparezca en logs:
```
✅ FX:EURUSD initialized with 1000 candles
📊 Buffer ready - EMAs convergidas
```

### Los gráficos no se envían

**Causa:** `SEND_CHARTS=false` o error en generación de imagen.

**Solución:**
```env
SEND_CHARTS=true
CHART_LOOKBACK=30  # Probar con valor más bajo
```

### Guardado local por cierre de vela

**Comportamiento:** si `SAVE_NOTIFICATIONS_LOCALLY=true`, en cada cierre de vela se guarda:
- Registro `CandleData` en `data/closed_candles/{SYMBOL}/candles.jsonl`
- Imagen del gráfico en `data/closed_candles/{SYMBOL}/charts/candle_YYYYMMDD_HHMMSS.png`

**Notas:**
- Reutiliza el `CHART_LOOKBACK` definido en `.env`.
- Funciona para cualquier proveedor (TradingView, IQ Option, Quotex) porque se ejecuta en `AnalysisService`.

### Dataset vacío / Sin estadísticas

**Causa:** Aún no se han detectado suficientes señales.

**Solución:**
- Espera a que se detecten y cierren al menos 6-10 señales
- Verifica que `data/trading_signals_dataset.jsonl` exista
- Revisa que las velas outcome se estén guardando correctamente

### Logs llenan el disco (Docker)

**Solución automática:** El `docker-compose.yml` ya incluye rotación:
```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

Máximo: 30MB de logs. Si necesitas limpiar manualmente:
```powershell
docker-compose down
docker system prune -f
docker-compose up -d --build
```

---

## 📚 Documentación Adicional

* **[DOCKER_GUIDE.md](./DOCKER_GUIDE.md)** - Cheatsheet completo de comandos Docker
* **[Docs/resumen.md](./Docs/resumen.md)** - Especificación técnica completa del proyecto
* **[Docs/bollinger.md](./Docs/bollinger.md)** - Sistema de clasificación por Bollinger Bands
* **[Docs/least/sistema_probabilidad_historica.md](./Docs/least/sistema_probabilidad_historica.md)** - Sistema de estadísticas en tiempo real
* **[Docs/tendencia.md](./Docs/tendencia.md)** - Momentum Scoring System (pesos optimizados para opciones binarias)
* **[Docs/candle.md](./Docs/candle.md)** - Documentación matemática de los 4 patrones
* **[Docs/backlog.md](./Docs/backlog.md)** - Product Backlog (próximas features)

---

## 🎯 Estado Actual del Proyecto

**Versión:** v0.0.6  
**Estado:** ✅ **PRODUCCIÓN** - Sistema completamente operativo

### Features Implementadas ✅

- ✅ 4 Patrones de velas japonesas (Shooting Star, Hanging Man, Inverted Hammer, Hammer)
- ✅ Validación matemática estricta con sistema de confianza 70-100%
- ✅ Momentum Scoring System optimizado para opciones binarias (-10 a +10)
- ✅ 5 EMAs calculadas (20, 30, 50, 100, 200) con cálculo condicional
- ✅ Bollinger Bands Exhaustion System (BB 20, 2.5σ)
- ✅ Clasificación de fuerza: HIGH 🚨🚨 / MEDIUM ⚠️ / LOW ℹ️
- ✅ StatisticsService con consulta de probabilidades históricas
- ✅ Fuzzy matching para buscar señales con score similar
- ✅ Dataset JSONL con raw_data (recalculación de scores retroactiva)
- ✅ Notificaciones duales (patrón detectado + outcome de vela)
- ✅ Generación automática de gráficos con mplfinance (5 EMAs visualizadas)
- ✅ Suite de tests automatizados (`test/test_candles.py`)
- ✅ Herramienta de visualización con validación (`test/visualize_patterns.py`)
- ✅ Dockerización completa (Dockerfile + docker-compose.yml)
- ✅ Logs con rotación automática (10MB × 3 archivos)
- ✅ Health check y graceful shutdown
- ✅ Modo sin autenticación para Forex público
- ✅ Proveedor Quotex mediante `pyquotex` (`DATA_PROVIDER=QUOTEX`)
- ✅ Arquitectura multi-cliente Quotex: instancia `_QuotexSymbolWorker` aislada por símbolo, arranque en paralelo con `asyncio.gather`
- ✅ Multi-instrumento: monitoréo simultáneo de múltiples activos vía `QUOTEX_ASSETS`

### Próximas Features (Roadmap)

Ver **[Docs/backlog.md](./Docs/backlog.md)** para el Product Backlog completo. Highlights:

**v0.0.7 - Dashboard & Analytics:**
- Dashboard web con Streamlit para visualización en tiempo real
- Gráficos de distribución de win rate por patrón
- Curvas de PnL acumulado

**v0.1.0 - Nuevos Patrones:**
- Engulfing (Envolvente Alcista/Bajista)
- Doji (múltiples variantes)
- Estrella de la Mañana/Tarde (3 velas)

**v0.3.0 - Machine Learning Predictivo:**
- Modelo de Gradient Boosting para predecir probabilidad
- Features adicionales: volatilidad, hora del día, spread
- Predicción en lugar de solo consulta histórica

---

## ⚠️ Descargo de Responsabilidad

Este software es una herramienta de **análisis técnico** y **NO** ejecuta operaciones financieras. Todas las señales son sugerencias que requieren **validación manual** por parte del trader.

El uso de WebSockets no oficiales de TradingView puede conllevar riesgos de bloqueo temporal de IP (aunque el bot usa datos públicos sin autenticación, minimizando este riesgo).

**Utilice este software bajo su propia responsabilidad.** Los autores no se hacen responsables de pérdidas financieras derivadas del uso de las señales generadas por el bot.

---

**Última Actualización:** 30 de marzo de 2026  
**Mantenido por:** TradingView Pattern Monitor Team  
**Licencia:** MIT (ver LICENSE file)